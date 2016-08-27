#!/usr/bin/env python3
# coding=utf-8
import os
import sys
from time import sleep
import re
import socket
import shutil
import subprocess
import logging
import traceback
import tempfile
import string
import random
from urllib.parse import urljoin

__AUTHOR__ = 'Aploium <i@z.codes>'
__VERSION__ = '0.9.0'
__ZMIRROR_PROJECT_URL__ = 'https://github.com/aploium/zmirror/'
__ZMIRROR_GIT_URL__ = 'https://github.com/aploium/zmirror.git'
__ONKEY_PROJECT_URL__ = 'https://github.com/aploium/zmirror-onekey/'
__ONKEY_PROJECT_URL_CONTENT__ = 'https://raw.githubusercontent.com/aploium/zmirror-onekey/master/'
REPORT_SUCCESS = "success"
REPORT_ERROR = "error"
__REPORT_URLS__ = {
    REPORT_ERROR: "https://report.zmirror.org/onekey/log/error",
    REPORT_SUCCESS: "https://report.zmirror.org/onekey/log/success",
}

if sys.platform != 'linux':
    print('This program can ONLY be used in debian-like Linux (debian, ubuntu and some others)')
    exit(1)
if os.geteuid() != 0:
    print('Root privilege is required for this program. Please use `sudo python3 deploy.py`')
    exit(2)

DEBUG = '--debug' in sys.argv
already_have_cert = '--i-have-cert' in sys.argv


def onekey_report(report_type=REPORT_SUCCESS, installing_mirror=None, traceback_str=None):
    """
    发送报告到服务器
    尽可能保证在致命错误发生时也能传出错误报告
    """
    import json
    import re
    try:
        import distro
    except:
        dist = "Unable to load package distro\n" + traceback.format_exc()
    else:
        try:
            dist = json.dumps(distro.info(best=True))
        except:
            dist = "Unable to read dist\n" + traceback.format_exc()

    try:
        stdout_str = stdout_logger_last.get_value() + stdout_logger.get_value()
    except:
        stdout_str = "Unable to read stdout.\n" + traceback.format_exc()
    try:
        stderr_str = stderr_logger.get_value()
    except:
        stderr_str = "Unable to read stderr.\n" + traceback.format_exc()

    data = {
        "linux_dist": dist,
        "stdout": stdout_str,
        "stderr": stderr_str,
    }
    try:
        if installing_mirror is not None:
            if isinstance(installing_mirror, (list, tuple)):
                installing_mirror = ','.join(installing_mirror)
            data['installing_mirror'] = installing_mirror
    except:
        data['installing_mirror'] = "Unable to get installing_mirror"

    if traceback_str is not None and isinstance(traceback_str, str):
        data['traceback'] = traceback_str

    try:
        if isinstance(email, str) and email:
            data["email"] = email
    except:
        data["email"] = "NotDefined@fake.com"

    try:
        meminfo = open('/proc/meminfo').read()
        matched = re.search(r'^MemTotal:\s+(\d+)', meminfo)
        if matched:
            mem_total_KB = int(matched.groups()[0])
            data['memory'] = mem_total_KB
    except:
        data['memory'] = 1

    if DEBUG:
        print(__REPORT_URLS__[report_type], data)

    try:
        r = requests.post(__REPORT_URLS__[report_type], data=data)
    except:
        if DEBUG:
            traceback.print_exc()
    else:
        try:
            r = requests.post(__REPORT_URLS__[report_type],
                              data={"traceback": str(data)},
                              verify=False, )
        except:
            raise
        if DEBUG:
            print(r.text, r.headers, r.request.body)


class StdLogger:
    def __init__(self, mode="stdout"):
        self._file = tempfile.NamedTemporaryFile(
            mode='w+', encoding='utf-8', prefix="zmirror_onekey_{mode}_".format(mode=mode))

    def get_value(self):
        self._file.seek(0)
        return self._file.read()

    def write(self, msg):
        """
        :type msg: str
        """
        self._file.write(msg)

    @property
    def file_path(self):
        return self._file.name


try:
    stdout_logger_last = StdLogger()
    stdout_logger = StdLogger()
    stderr_logger = StdLogger(mode="stderr")
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise


def cmd(command, cwd=None, no_tee=False, **kwargs):
    """运行shell命令
    :type command: str
    :type cwd: str
    :type no_tee: bool
    """
    global stdout_logger, stdout_logger_last

    print("[zmirror] executing:", command)

    stdout_logger_last = stdout_logger
    stdout_logger = StdLogger()

    stdout_logger.write("\n--------\n[zmirror] executing: " + command)

    if not no_tee:
        command = "({cmd} | tee -a {stdout_file}) 3>&1 1>&2 2>&3 | tee -a {stderr_file}".format(
            cmd=command, stdout_file=stdout_logger.file_path, stderr_file=stderr_logger.file_path,
        )

    return subprocess.check_call(
        command,
        shell=True,
        cwd=cwd or os.getcwd(),
        **kwargs)


try:
    cmd('export LC_ALL=C.UTF-8')  # 设置bash环境为utf-8

    cmd('apt-get -y -q update && apt-get -y -q install python3 python3-pip')

    # for some old version Linux, pip has bugs, causing:
    # ImportError: cannot import name 'IncompleteRead'
    # so we need to upgrade pip first
    cmd('easy_install3 -U pip')

    # 安装本脚本必须的python包
    cmd('python3 -m pip install -U requests')
    cmd('python3 -m pip install -U distro')
except KeyboardInterrupt:
    print("Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
try:
    import distro
except:
    print("Could not import python package distro, abort installation")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

try:
    import requests
except:
    print('Could not install requests, program exit')
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

if DEBUG:
    logging.basicConfig(
        level=logging.NOTSET,
        format='[%(levelname)s %(asctime)s %(funcName)s] %(message)s',
    )

server_configs = {
    "apache": {
        "config_root": "/etc/apache2/",
        "htdoc": "/var/www/",

        "common_configs": ["http_generic", "apache_boilerplate"],
        "site_unique_configs": ["https"],

        "pre_delete_files": [
            "{config_root}/sites-enabled/000-default.conf",
            "{config_root}/conf-enabled/apache2-doc.conf",
            "{config_root}/conf-enabled/security.conf",
        ],

        "configs": {
            "apache_boilerplate": {
                "url": urljoin(__ONKEY_PROJECT_URL_CONTENT__, "configs/apache2-boilerplate.conf"),
                "file_path": "conf-enabled/zmirror-apache-boilerplate.conf",
            },

            "http_generic": {
                "url": urljoin(__ONKEY_PROJECT_URL_CONTENT__, "configs/apache2-http.conf"),
                "file_path": "sites-enabled/zmirror-http-redirection.conf",
            },

            "https": {
                "url": urljoin(__ONKEY_PROJECT_URL_CONTENT__, "configs/apache2-https.conf"),
                "file_path": "sites-enabled/zmirror-{mirror_name}-https.conf",
            },
        }

    }
}

mirrors_settings = {
    'google': {
        'domain': None,
        'cfg': [('more_configs/config_google_and_zhwikipedia.py', 'config.py'), ],
        "certs": {
            "private_key": None,
            "cert": None,
            "intermediate": None,
        },
    },

    'youtubePC': {
        'domain': None,
        'cfg': [('more_configs/config_youtube.py', 'config.py'),
                ('more_configs/custom_func_youtube.py', 'custom_func.py')],
        "certs": {},
    },

    'youtubeMobile': {
        'domain': None,
        'cfg': [('more_configs/config_youtube_mobile.py', 'config.py'),
                ('more_configs/custom_func_youtube.py', 'custom_func.py')],
        "certs": {},
    },

    'twitterPC': {
        'domain': None,
        'cfg': [('more_configs/config_twitter_pc.py', 'config.py'),
                ('more_configs/custom_func_twitter.py', 'custom_func.py'), ],
        "certs": {},
    },

    'twitterMobile': {
        'domain': None,
        'cfg': [('more_configs/config_twitter_mobile.py', 'config.py'),
                ('more_configs/custom_func_twitter.py', 'custom_func.py'), ],
        "certs": {},
    },

    'instagram': {
        'domain': None,
        'cfg': [('more_configs/config_instagram.py', 'config.py'), ],
        "certs": {},
    },
}

print('OneKey deploy script for zmirror. version', __VERSION__)
print('This script will automatically deploy mirror(s) using zmirror in your ubuntu')
print('You could cancel this script in the config stage by precessing Ctrl-C')
print('Installation will start after 1 second')
print()
sleep(1)

# ################# 安装一些依赖包 ####################
print('[zmirror] Installing some necessarily packages')
email = ""
question = None
# {"name":"","answer":"","hint":""}
try:
    # 设置本地时间为北京时间
    cmd('cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime')
    # 告诉apt-get要安静
    cmd('export DEBIAN_FRONTEND=noninteractive')
    # 更新apt-get
    cmd('apt-get -y -q update')
    # 安装必须的包
    cmd('apt-get -y -q install git python3 python3-pip wget curl')
    # 安装非必须的包
    try:
        # 更新一下openssl
        cmd('apt-get -y -q install openssl')
    except:
        pass
    try:
        # 如果安装了, 则可以启用http2
        cmd('apt-get -y -q install software-properties-common python-software-properties')
    except:
        ppa_available = False
    else:
        ppa_available = True

    if distro.id() == 'ubuntu' and ppa_available:
        # 安装高版本的Apache2(支持http2), 仅限ubuntu
        cmd("""LC_ALL=C.UTF-8 add-apt-repository ppa:ondrej/apache2 &&
    apt-key update &&
    apt-get -y -q update &&
    apt-get -y -q install apache2""")
    else:
        # debian 只有低版本的可以用
        cmd("apt-get -y -q install apache2")

    cmd("""a2enmod rewrite mime include headers filter expires deflate autoindex setenvif ssl""")

    try:
        cmd("a2enmod http2")
    except:
        print("[Warning!] your server does not support http2")

    # (可选) 更新一下各种包
    if not (distro.id() == 'ubuntu' and distro.version() == '14.04'):  # 系统不是ubuntu 14.04
        # Ubuntu 14.04 执行本命令的时候会弹一个postfix的交互, 所以不执行
        cmd('apt-get -y -q upgrade')

    cmd("""apt-get -y -q install libapache2-mod-wsgi-py3&& a2enmod wsgi""")

    # 安装和更新必须的python包
    cmd('python3 -m pip install -U requests flask')
    # 安装和更新非必须, 但是有好处的python包
    try:
        cmd('python3 -m pip install -U chardet fastcache cchardet')
    except:
        pass  # 允许安装失败

    print('[zmirror] Dependency packages install completed')
    print('[zmirror] Installing letsencrypt...')
    sleep(1)
    if not already_have_cert:
        if not os.path.exists('/etc/certbot/'):
            # certbot 不存在, 则安装
            cmd('git clone https://github.com/certbot/certbot.git', cwd='/etc/')
            cmd('chmod a+x /etc/certbot/certbot-auto', cwd='/etc/certbot/')
            cmd('service apache2 stop')
            cmd('./certbot-auto renew --agree-tos -n --standalone '
                '--pre-hook "service apache2 stop" '
                '--post-hook "service apache2 restart"',
                cwd='/etc/certbot/',
                # ubuntu14.04下, 使用tee会出现无法正常退出的bug
                no_tee=distro.id() == 'ubuntu' and distro.version() == '14.04'
                )
        else:
            # 否则升级一下
            cmd('git pull', cwd='/etc/certbot/')
        print("[zmirror] let's encrypt Installation Completed")
        sleep(1)
    else:
        print("[zmirror] you said you already have certs, so skip let's encrypt")

    print('\n\n\n-------------------------------\n'
          '[zmirror] Now we need some information:')
except KeyboardInterrupt:
    print("Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

mirrors_to_deploy = []
try:
    _input = -1
    while _input:  # 不断循环输入, 因为用户可能想要安装多个镜像
        print('----------------------')
        _input = input(
            """Please select mirror you want to deploy?
    select one mirror a time, you could select zero or more mirror(s)

    {google}  1. Google (include scholar, image, zh_wikipedia)
    {twitterPC}  2. twitter (PC ONLY)
    {twitterMobile}  3. twitter (Mobile ONLY)
    {youtubePC}  4. youtube (PC ONLY)
    {youtubeMobile}  5. youtube (Mobile ONLY)
    {instagram}  6. instagram
      0. Go to next steps. (OK, I have selected all mirror(s) I want to deploy)

    input 0-6: """.format(
                google='[SELECTED]' if 'google' in mirrors_to_deploy else '',
                twitterPC='[SELECTED]' if 'twitterPC' in mirrors_to_deploy else '',
                twitterMobile='[SELECTED]' if 'twitterMobile' in mirrors_to_deploy else '',
                youtubePC='[SELECTED]' if 'youtubePC' in mirrors_to_deploy else '',
                youtubeMobile='[SELECTED]' if 'youtubeMobile' in mirrors_to_deploy else '',
                instagram='[SELECTED]' if 'instagram' in mirrors_to_deploy else '',
            )

        )

        if not _input:
            break

        logging.debug("input:" + _input)

        try:
            _input = int(_input)
        except:
            print("Please input correct number")
            _input = -1

        if _input == 0:
            break
        if not (0 <= _input <= 6):
            print('[ERROR] please input correct number (0-6), only select one mirror a time\n'
                  '-------------------------\n\n')
            continue

        # 将数字选项转化为字符串
        mirror_type = {
            1: "google",
            2: "twitterPC",
            3: "twitterMobile",
            4: "youtubePC",
            5: "youtubeMobile",
            6: "instagram",
        }[_input]

        # 在选项里, 镜像已存在, 则删去, 并且跳过下面的步骤
        if mirror_type in mirrors_to_deploy:
            mirrors_to_deploy.remove(mirror_type)
            print("Mirror:{mirror_type} unchecked.".format(mirror_type=mirror_type))
            continue

        # 输入镜像对应的域名, 要求已经在DNS设置中用一个A记录指向了本服务器
        print()  # 打印一个空行
        while True:  # 这里面会检查输入的是否是三级域名
            domain = input("Please input *your* domain for this mirror: ")
            domain = domain.strip(' /.\t').replace('https://', '').replace('http://', '')  # 修剪
            if domain.count('.') != 2:
                if input(("Your domain [{domain}] is not an third-level domain, "
                          "which contains three parts and two dots. \n"
                          "    eg1: lovelucia.zmirrordemo.com eg2: g.mymirror.com\n"
                          "    zmirror officially only support third-level domain\n"
                          "    a none third-level domain MAY work, but may cause potential errors\n"
                          "Continue anyway(y/N)?"
                          ).format(domain=domain)) in ('y', 'yes', 'Yes', 'YES'):
                    break
                    # 如果选择的是 N, 则重新输入
            else:  # 输入的是三级域名
                break

        # 初步检验域名是否已经被正确设置
        try:
            domain_ip = socket.gethostbyname(domain)
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception as e:  # 查询目标域名的IP失败
            print("Sorry, your domain [{domain}] is not setting correctly. {exc}".format(domain=domain, exc=str(e)))
            continue_anyway = input("Continue anyway? (y/N): ")
            if continue_anyway not in ('y', 'yes', 'Yes', 'YES'):
                continue  # 重新来
            else:
                # 仍然继续的话, 把domain_ip当做local_ip
                local_ip = '127.0.0.1'
                domain_ip = local_ip

        # 域名检验--目标域名的IP不等于本地机器的IP
        if domain_ip != local_ip:
            print("""Sorry, your domain({domain})'s ip does not equals to this machine's ip.
    domain's ip is: {domain_ip}
    this machine's ip is: {local_ip}
    """.format(domain=domain, domain_ip=domain_ip, local_ip=local_ip)
                  )
            continue_anyway = input("Continue anyway? (y/N): ")
            if continue_anyway not in ('y', 'yes', 'Yes', 'YES'):
                continue  # 重新来

        # 域名检验--域名是否重复
        _dup_flag = False
        for mirror in mirrors_to_deploy:
            if mirrors_settings[mirror_type]['domain'] == domain:
                print("Duplicated domain! conflict with mirror: " + mirror)
                _dup_flag = True
                break
        if _dup_flag:
            continue

        # 当用户选择自己提供证书时, 要求用户输入证书路径
        if already_have_cert:
            # 输入私钥
            while True:
                print()  # 打印一个空行
                private_key = input(
                    "Please input your SSL private key file path \n"
                    "    which will be used for Apache's SSLCertificateKeyFile\n"
                    "(should not be blank): "
                )
                if not private_key or not os.path.exists(private_key):
                    print("file", private_key, "does not exist")
                else:
                    break

            # 输入证书
            while True:
                print()
                cert = input(
                    "Please input your SSL cert file path \n"
                    "    which will be used for Apache's SSLCertificateFile\n"
                    "    It's name may looks like \"2_" + domain + ".crt\"\n"
                    + "(should not be blank): "
                )
                if not cert or not os.path.exists(cert):
                    print("file", cert, "does not exist")
                else:
                    break

            # 输入证书链
            while True:
                print()
                cert_chain = input(
                    "Please input your SSL cert chain file \n"
                    "    which will be used for Apache's SSLCertificateChainFile\n"
                    "    It's name may looks like \"1_root_bundle.crt\" or \"1_Intermediate.crt\"\n"
                    "(should not be blank): "
                )
                if not cert_chain or not os.path.exists(cert_chain):
                    print("file", cert_chain, "does not exist")
                else:
                    break

        # 将镜像添加到待安装列表中
        mirrors_to_deploy.append(mirror_type)
        mirrors_settings[mirror_type]['domain'] = domain

        if already_have_cert:
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['private_key'] = private_key
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['cert'] = cert
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['intermediate'] = cert_chain

        print("Mirror:{mirror_type} Domain:{domain} checked".format(mirror_type=mirror_type, domain=domain))

        logging.debug(mirrors_to_deploy)

    if not mirrors_to_deploy:
        print('[ERROR] you didn\'t select any mirror.\nAbort installation')
        exit(4)

    if not already_have_cert:
        print()
        email = input('Please input your email (because letsencrypt requires an email for certification)\n')

        print('Your email:', email)

    # 是否需要输入正确的密码才能访问
    print()
    print("zmirror can provide simple verification via password\n"
          "    just as you may have seen in zmirror's demo sites (however, demo sites does not require correct answer)")
    need_answer_question = input("Do you want to protect your mirror by password? (y/N):")
    if need_answer_question in ("y", "yes", "Yes", "YES"):
        need_answer_question = True
        print()
        print(
            "##TIPS1##\n"
            "In your bash environment, you may not able to input Chinese,\n"
            "    however, you can input English here,\n"
            "    and change them to Chinese in the config file manually, after the installation.\n"
            "    the settings are in /var/www/YOUR_MIRROR_FOLDER/config.py\n"
            "###TIPS2##\n"
            "This script here only provide BASIC settings for verification, \n"
            "    For full verification settings list, \n"
            "    please see the ##Human/IP verification## section of `config_default.py`\n"
        )
        while True:
            name = input("Please input the question:")
            if not name:
                print("    question should not be blank")
                continue
            answer = input("Please input the answer (act as password):")
            if not answer:
                print("    answer should not be blank")
                continue
            hint = input("Please input the hint (optional, press [ENTER] to skip):")
            question = {"name": name, "answer": answer, "hint": hint}
            break
    else:
        need_answer_question = False

    # 最后确认一遍设置
    print('----------------------')
    print('Now, we are going to install, please check your settings here:')
    if not already_have_cert:
        print("  Email: " + email)
    print()
    for mirror in mirrors_to_deploy:
        print("    Mirror: {mirror} Domain: {domain}".format(mirror=mirror, domain=mirrors_settings[mirror]['domain']))
    print()
    if need_answer_question:
        print("Protected with question-answer:")
        print("  Question:", question["name"])
        print("  Answer:", question["answer"])
        print("  Hint:", question["hint"])

    print()
    if input('Are these settings correct (Y/n)? ') in ('N', 'No', 'n', 'no', 'not', 'none'):
        raise SystemExit('installation abort manually.')

    # ############### Really Install ###################
    if not already_have_cert:
        # 通过 letsencrypt 获取HTTPS证书
        print("Fetching HTTPS certifications")
        cmd("service apache2 stop")  # 先关掉apache
        for mirror in mirrors_to_deploy:
            domain = mirrors_settings[mirror]['domain']

            if os.path.exists('/etc/letsencrypt/live/{domain}'.format(domain=domain)):
                # 如果证书已存在, 则跳过
                print("Certification for {domain} already exists, skipping".format(domain=domain))
                continue

            print("Obtaining: {domain}".format(domain=domain))
            cmd(
                ('./certbot-auto certonly -n --agree-tos -t -m "{email}" --standalone -d "{domain}" '
                 '--pre-hook "/usr/sbin/service apache2 stop" '
                 '--post-hook "/usr/sbin/service apache2 start"'
                 ).format(email=email, domain=domain),
                cwd='/etc/certbot/',
                # 在ubuntu 14.04下, tee会出现无法正常结束的bug, 所以此时不能再用tee #1
                no_tee=distro.id() == 'ubuntu' and distro.version() == '14.04',
            )

            # 检查是否成功获取证书
            if not os.path.exists('/etc/letsencrypt/live/{domain}'.format(domain=domain)):
                print('[ERROR] Could NOT obtain an ssl cert, '
                      'please check your DNS record, '
                      'and then run again.\n'
                      'Installation abort')
                exit(3)
            print("Succeed: {domain}".format(domain=domain))
        cmd("service apache2 start",  # 重新启动apache
            # ubuntu14.04下, 使用tee会出现无法正常退出的bug, 所以禁用掉
            no_tee=distro.id() == 'ubuntu' and distro.version() == '14.04'
            )

    else:  # 选择自己提供证书
        print("[zmirror] skipping let's encrypt, for you already provided your cert")

    # ####### 安装zmirror自身 #############
    print('[zmirror] Successfully obtain SSL cert, now installing zmirror itself...')
    sleep(1)

    this_server = server_configs['apache']
    htdoc = this_server['htdoc']  # type: str
    config_root = this_server['config_root']  # type: str

    os.chdir(htdoc)
    cmd('git clone %s zmirror' % __ZMIRROR_GIT_URL__, cwd=htdoc)
    zmirror_source_folder = os.path.join(htdoc, 'zmirror')

    # 预删除文件
    for pre_delete_file in this_server['pre_delete_files']:
        abs_path = pre_delete_file.format(
            config_root=config_root, htdoc=htdoc
        )
        print("deleting: " + abs_path)
        try:
            os.remove(abs_path)
        except:
            logging.debug("Unable to remove file:" + abs_path + "\n" + traceback.format_exc())

    # 拷贝并设置各个镜像
    for mirror in mirrors_to_deploy:
        domain = mirrors_settings[mirror]['domain']
        this_mirror_folder = os.path.join(htdoc, mirror)

        # 如果文件夹已存在, 则报错
        if os.path.exists(this_mirror_folder):
            print(
                ("Folder {folder} already exists."
                 "If you want to override, please delete that folder manually and run this script again"
                 ).format(folder=this_mirror_folder)
            )
            raise FileExistsError("Folder {folder} for mirror [{mirror_name}] already exists.".format(
                folder=this_mirror_folder, mirror_name=mirror))

        # 将 zmirror 文件夹复制一份
        shutil.copytree(zmirror_source_folder, this_mirror_folder)
        # 更改文件夹所有者为 www-data (apache的用户)
        shutil.chown(this_mirror_folder, "www-data", "www-data")

        this_mirror = mirrors_settings[mirror]

        for file_from, file_to in this_mirror['cfg']:
            shutil.copy(os.path.join(this_mirror_folder, file_from),
                        os.path.join(this_mirror_folder, file_to))

        with open(os.path.join(this_mirror_folder, 'config.py'), 'r+', encoding='utf-8') as fp:
            # noinspection PyRedeclaration
            content = fp.read()

            # 将 my_host_name 修改为对应的域名
            content = re.sub(r"""my_host_name *= *(['"])[-.\w]+\1""",
                             "my_host_name = '{domain}' # Modified by zmirror-onekey".format(domain=domain),
                             content, count=1)
            # 将 my_host_scheme 修改为 https://
            content = re.sub(r"""my_host_scheme *= *(['"])https?://\1""",
                             "my_host_scheme = 'https://' # Modified by zmirror-onekey",
                             content, count=1)
            # 在文件末尾添加 verbose_level = 2
            content += '\n\nverbose_level = 2 # Added by zmirror-onekey\n'

            # 如果需要添加验证问题
            if need_answer_question:
                content += '\n\n########## Verification (added by zmirror-onekey) ########\n' \
                           '# 这里只有最基础的单一问题-答案验证, 如果需要更加丰富的验证方式, \n' \
                           '#    请看 `config_default.py` 文件中的 `Human/IP verification` 设置区段\n' \
                           '#    PS: 下面的设置都支持中文, 可以自行修改成中文\n'
                content += 'human_ip_verification_enabled = True\n'
                content += 'human_ip_verification_answers_hash_str = \'{salt}\'  # Secret key, please keep it secret\n'.format(
                    salt="".join(random.choice(string.ascii_letters + string.digits) for _ in range(32))
                )
                content += 'human_ip_verification_questions = [\n' + \
                           '    ["{question}", "{answer}", "{hint}"],\n'.format(
                               question=question["name"], answer=question["answer"], hint=question["hint"],
                           ) + ']\n'
                content += 'human_ip_verification_identity_record = []\n'

            fp.seek(0)  # 指针返回文件头
            fp.write(content)  # 回写

    shutil.rmtree(zmirror_source_folder)  # 删除无用的 zmirror 文件夹

    print("[zmirror] zmirror program folders deploy completed")

    # ############# 配置Apache ###############
    print("[zmirror] Now installing apache configs...")
    sleep(0.5)

    os.chdir(config_root)

    # 下载通用配置文件
    for conf_name in this_server['common_configs']:
        assert isinstance(config_root, str)
        url = this_server['configs'][conf_name]['url']
        file_path = os.path.join(config_root, this_server['configs'][conf_name]['file_path'])

        if os.path.exists(file_path):  # 若配置文件已存在则跳过
            print("Config {path} already exists, skipping".format(path=file_path))
            continue

        with open(file_path, 'w', encoding='utf-8') as fp:
            print("downloading: ", conf_name)
            fp.write(requests.get(url).text)

    # 下载并设置各个镜像的Apache配置文件
    for mirror in mirrors_to_deploy:
        domain = mirrors_settings[mirror]['domain']
        this_mirror_folder = os.path.join(htdoc, mirror)

        for conf_name in this_server['site_unique_configs']:
            url = this_server['configs'][conf_name]['url']
            file_path = os.path.join(config_root, this_server['configs'][conf_name]['file_path'])
            file_path = file_path.format(mirror_name=mirror, conf_name=conf_name)

            if os.path.exists(file_path):  # 若配置文件已存在则跳过
                print("Config {path} already exists, skipping".format(path=file_path))
                continue

            print("downloading: ", mirror, conf_name)

            conf = requests.get(url).text

            # 因为Apache conf里面有 {Ascii字符} 这种结构, 与python的string format冲突
            # 这边只能手动format
            for key, value in [
                ('domain', domain),
                ('mirror_name', mirror),
                ('path_to_wsgi_py', os.path.join(this_mirror_folder, 'wsgi.py')),
            ]:
                conf = conf.replace("{{%s}}" % key, value)

            # 填写 conf 中的证书路径
            if already_have_cert:
                # 已有证书, 则在conf中填入自己的证书
                certs_dict = mirrors_settings[mirror]['certs']
                conf = conf.replace("{{cert_file}}", certs_dict['cert'])
                conf = conf.replace("{{private_key_file}}", certs_dict['private_key'])
                conf = conf.replace("{{cert_chain_file}}", certs_dict['intermediate'])
            else:
                # 若使用 let's encrypt 获取到了证书
                # 则填入 let's encrypt 的证书路径
                conf = conf.replace(
                    "{{cert_file}}",
                    "/etc/letsencrypt/live/{domain}/cert.pem".format(domain=domain),
                )
                conf = conf.replace(
                    "{{private_key_file}}",
                    "/etc/letsencrypt/live/{domain}/privkey.pem".format(domain=domain),
                )
                conf = conf.replace(
                    "{{cert_chain_file}}",
                    "/etc/letsencrypt/live/{domain}/chain.pem".format(domain=domain),
                )

            with open(file_path, 'w', encoding='utf-8') as fp:
                fp.write(conf)

    # ##### Add linux cron script for letsencrypt auto renewal ######
    if not os.path.exists("/etc/cron.weekly/zmirror-letsencrypt-renew.sh") \
            or already_have_cert:  # 若脚本已存在, 或者选择自己提供证书, 则跳过
        # 添加 let's encrypt 证书自动更新脚本
        print("Adding cert auto renew script to `/etc/cron.weekly/zmirror-letsencrypt-renew.sh`")
        cron_script = """#!/bin/bash
    cd /etc/certbot
    ./certbot-auto renew -n --agree-tos --standalone --pre-hook "/usr/sbin/service apache2 stop" --post-hook "/usr/sbin/service apache2 start"
    exit 0
    """
        with open("/etc/cron.weekly/zmirror-letsencrypt-renew.sh", "w", encoding='utf-8') as fp:
            fp.write(cron_script)

        cmd('chmod +x /etc/cron.weekly/zmirror-letsencrypt-renew.sh')
        cmd('/etc/cron.weekly/zmirror-letsencrypt-renew.sh')

    # 重启一下apache
    print("Restarting apache2")
    cmd('service apache2 restart',
        # ubuntu14.04下, 使用tee会出现无法正常退出的bug
        no_tee=distro.id() == 'ubuntu' and distro.version() == '14.04'
        )
except KeyboardInterrupt:
    print("Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc(), installing_mirror=mirrors_to_deploy)
    raise

try:
    onekey_report(report_type=REPORT_SUCCESS, installing_mirror=mirrors_to_deploy)
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())

# ####### 完成 ########
print("Completed.\n")
# 最后打印一遍配置
print("------------ mirrors ------------")
for mirror in mirrors_to_deploy:
    print("    Mirror: {mirror} URL: https://{domain}/".format(mirror=mirror, domain=mirrors_settings[mirror]['domain']))
print("------------ mirrors ------------")

if distro.id() == 'debian' or distro.id() == 'ubuntu' and distro.version() == '15.04':
    print()
    print("[WARING] your system does NOT support HTTP/2! HTTP/2 would not be available\n"
          "If you want to use HTTP/2, please use Ubuntu 14.04/15.10/16.04")

print()
print("For more information, please view zmirror's github: ", __ZMIRROR_PROJECT_URL__)
print("Contribution and Issues are more than welcomed.")
print("btw, if you feeling good, I'll be grateful for your Star in github :)")
