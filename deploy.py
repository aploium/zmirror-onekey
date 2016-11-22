#!/usr/bin/env python3
# coding=utf-8
import os
import sys
import re
import socket
import shutil
import subprocess
import traceback
import tempfile
import string
import random
from time import sleep
from datetime import datetime
from urllib.parse import urljoin
import json

try:
    from external_pkgs.ColorfulPyPrint import *
except:
    infoprint = print
    errprint = print
    warnprint = print
    importantprint = print

__AUTHOR__ = 'Aploium <i@z.codes>'
__VERSION__ = '0.12.1'
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
    errprint('This program can ONLY be used in debian-like Linux (debian, ubuntu and some others)')
    exit(1)
if os.geteuid() != 0:
    errprint('Root privilege is required for this program. Please use `sudo python3 deploy.py`')
    exit(2)

if sys.version_info < (3, 4):
    errprint("zmirror requires at least Python 3.4,\n"
             "however, your Python version is \n", sys.version)
    exit(7)

DEBUG = '--debug' in sys.argv
already_have_cert = '--i-have-cert' in sys.argv
upgrade_only = "--upgrade-only" in sys.argv

if DEBUG:
    ColorfulPyPrint_set_verbose_level(3)
else:
    ColorfulPyPrint_set_verbose_level(2)

# 初始化一些全局变量
mirrors_to_deploy = []
email = ""
question = None  # {"name":"","answer":"","hint":""}
need_answer_question = False
loaded_config = False  # 加载了上一次的配置

DUMP_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_install_dump.json")


def onekey_report(report_type=REPORT_SUCCESS, traceback_str=None, msg=None):
    """
    发送报告到服务器
    尽可能保证在致命错误发生时也能传出错误报告
    """
    try:
        import json
    except:
        import simplejson as json

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
        if mirrors_to_deploy:
            data['installing_mirror'] = ','.join(mirrors_to_deploy)
    except:
        data['installing_mirror'] = "Unable to get installing_mirror"

    if traceback_str is not None and isinstance(traceback_str, str):
        data['traceback'] = traceback_str

    try:
        import platform
    except:
        pass
    else:
        try:
            data['uname'] = json.dumps(dict(zip(
                platform.uname()._fields,
                platform.uname()
            )))
        except:
            pass
    try:
        data['python_version'] = sys.version
    except:
        pass

    try:
        if msg is not None:
            data['extra_msg'] = str(msg)
    except:
        pass

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

    dbgprint(__REPORT_URLS__[report_type], data)

    try:
        r = requests.post(__REPORT_URLS__[report_type], data=data)
    except:
        if DEBUG:
            traceback.print_exc()
        try:
            r = requests.post(
                __REPORT_URLS__[report_type],
                data={
                    "traceback": str(data)
                                 + "\n-----Except during request-----\n"
                                 + traceback.format_exc()
                },
                verify=False, )
        except:
            raise
    else:
        dbgprint(r.text, r.headers, r.request.body)


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


def cmd(command, cwd=None, no_tee=False, allow_failure=None, **kwargs):
    """运行shell命令
    :type command: str
    :type cwd: str
    :type no_tee: bool
    :type allow_failure: bool
    :rtype: bool
    """
    global stdout_logger, stdout_logger_last

    infoprint("executing:", command)

    stdout_logger_last = stdout_logger
    stdout_logger = StdLogger()

    stdout_logger.write("\n--------\nexecuting: " + command + "\n")

    if not no_tee:
        command = "({cmd} | tee -a {stdout_file}) 3>&1 1>&2 2>&3 | tee -a {stderr_file}".format(
            cmd=command, stdout_file=stdout_logger.file_path, stderr_file=stderr_logger.file_path,
        )

    try:
        result = subprocess.check_call(
            command,
            shell=True,
            cwd=cwd or os.getcwd(),
            **kwargs)
    except:
        traceback.print_exc()

        if allow_failure is True:
            try:
                onekey_report(report_type=REPORT_ERROR,
                              traceback_str=traceback.format_exc(),
                              msg="AllowedFailure"
                              )
            except:
                pass
            return False

        if allow_failure is None:
            print()
            errprint("command: \n    ", command, "\nerror, installation should be abort.")
            choice = input("Do you want to continue installation anyway?(y/N) ")
            if choice in ("y", "Y", "yes", "Yes"):
                infoprint("Installation continue...")
                try:
                    onekey_report(report_type=REPORT_ERROR,
                                  traceback_str=traceback.format_exc(),
                                  msg="Continued")
                except:
                    pass
                return False
            else:
                raise
        raise
    else:
        return True


def dump_settings(dump_file_path=DUMP_FILE_PATH):
    """将设置保存到文件"""
    # 仅自动获取证书时支持继续上次失败的设置
    if already_have_cert:
        return

    settings = {
        "mirrors_to_deploy": mirrors_to_deploy,
        "email": email,
        "question": question,
        "mirrors_settings": mirrors_settings,
        "time": str(datetime.now()),
    }
    with open(dump_file_path, "w", encoding="utf-8") as fw:
        json.dump(settings, fw)


try:
    cmd('export LC_ALL=C.UTF-8')  # 设置bash环境为utf-8

    cmd('apt-get -y -q update && apt-get -y -q install python3 python3-pip')

    # for some old version Linux, pip has bugs, causing:
    # ImportError: cannot import name 'IncompleteRead'
    # so we need to upgrade pip first
    cmd('easy_install3 -U pip')

    # 安装本脚本必须的python包
    cmd('python3 -m pip install -U setuptools')
    cmd('python3 -m pip install requests==2.11.0')
    cmd('python3 -m pip install -U distro')
except KeyboardInterrupt:
    infoprint("Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise
try:
    import distro
except:
    errprint("Could not import python package distro, abort installation")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

try:
    import requests
except:
    errprint('Could not install requests, program exit')
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

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
        "installed_path": "",
    },

    'youtubePC': {
        'domain': None,
        'cfg': [('more_configs/config_youtube.py', 'config.py'),
                ('more_configs/custom_func_youtube.py', 'custom_func.py')],
        "certs": {},
        "installed_path": "",
    },

    'youtubeMobile': {
        'domain': None,
        'cfg': [('more_configs/config_youtube_mobile.py', 'config.py'),
                ('more_configs/custom_func_youtube.py', 'custom_func.py')],
        "certs": {},
        "installed_path": "",
    },

    'twitterPC': {
        'domain': None,
        'cfg': [('more_configs/config_twitter_pc.py', 'config.py'),
                ('more_configs/custom_func_twitter.py', 'custom_func.py'), ],
        "certs": {},
        "installed_path": "",
    },

    'twitterMobile': {
        'domain': None,
        'cfg': [('more_configs/config_twitter_mobile.py', 'config.py'),
                ('more_configs/custom_func_twitter.py', 'custom_func.py'), ],
        "certs": {},
        "installed_path": "",
    },

    'instagram': {
        'domain': None,
        'cfg': [('more_configs/config_instagram.py', 'config.py'), ],
        "certs": {},
        "installed_path": "",
    },
}

infoprint('OneKey deploy script for zmirror. version', __VERSION__)
infoprint('This script will automatically deploy mirror(s) using zmirror in your ubuntu')
infoprint('You could cancel this script in the config stage by precessing Ctrl-C')
infoprint('Installation will start after 1 second')
print()
sleep(1)
# ################# 检测镜像是否已安装 ################
htdoc = server_configs["apache"]['htdoc']  # type: str
for mirror, values in list(mirrors_settings.items()):
    this_mirror_folder = os.path.join(htdoc, mirror)
    # 如果文件夹不存在, 则跳过
    if os.path.exists(this_mirror_folder):
        infoprint("Mirror:", mirror, "was already installed in", this_mirror_folder)
        mirrors_settings[mirror]["installed_path"] = this_mirror_folder

# ################# 仅升级 ##########################
if upgrade_only:
    infoprint("Upgrade Only")
    htdoc = server_configs["apache"]['htdoc']  # type: str
    success_count = 0

    infoprint("Upgrading dependencies")
    cmd("python3 -m pip install -U pip", allow_failure=True)
    cmd("python3 -m pip install flask", allow_failure=True)
    cmd("python3 -m pip install -U cchardet", allow_failure=True)
    cmd("python3 -m pip install -U fastcache", allow_failure=True)
    cmd("python3 -m pip install -U lru-dict", allow_failure=True)

    for mirror, values in mirrors_settings.items():
        this_mirror_folder = values["installed_path"]

        # 如果文件夹不存在, 则跳过
        if not this_mirror_folder or not os.path.exists(this_mirror_folder):
            infoprint("Mirror:", mirror, "not found, skipping")
            continue

        # 否则进行升级
        infoprint("Upgrading:", mirror)
        try:
            cmd("git pull", cwd=this_mirror_folder, allow_failure=False)
        except:
            errprint("Unable to upgrade:", mirror)
            onekey_report(
                report_type=REPORT_ERROR,
                traceback_str=traceback.format_exc(),
                msg="Unable to upgrade:" + mirror
            )
        else:
            success_count += 1

    if success_count:
        infoprint("zmirror upgrade complete, restarting apache2 ")
        try:
            cmd("service apache2 restart", no_tee=True, allow_failure=True)
        except:
            errprint("Unable to restart apache2, please execute `service apache2 restart` manually")
            onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
        else:
            onekey_report(report_type=REPORT_SUCCESS, msg="Success Count:{}".format(success_count))

    exit()

# ################# 安装一些依赖包 ####################
infoprint('Installing some necessarily packages')

try:
    # 设置本地时间为北京时间
    try:
        cmd('cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime', allow_failure=True)
    except:
        pass
    # 告诉apt-get要安静
    cmd('export DEBIAN_FRONTEND=noninteractive')
    os.environ['DEBIAN_FRONTEND'] = "noninteractive"
    # 更新apt-get
    cmd('apt-get -y -q update')
    # 安装必须的包
    cmd('apt-get -y -q install git python3 python3-pip wget curl')
    # 安装非必须的包
    try:
        # 更新一下openssl
        cmd('apt-get -y -q install openssl', allow_failure=True)
    except:
        pass

    # 如果安装了, 则可以启用http2
    ppa_available = cmd('apt-get -y -q install software-properties-common python-software-properties', allow_failure=True)

    if distro.id() == 'ubuntu' and ppa_available:
        # 安装高版本的Apache2(支持http2), 仅限ubuntu
        cmd("""LC_ALL=C.UTF-8 add-apt-repository -y ppa:ondrej/apache2 &&
    apt-key update &&
    apt-get -y -q update &&
    apt-get -y -q install apache2""")
    else:
        # debian 只有低版本的可以用
        cmd("apt-get -y -q install apache2")

    cmd("""a2enmod rewrite mime include headers filter expires deflate autoindex setenvif ssl""")

    if not cmd("a2enmod http2", allow_failure=True):
        warnprint("[Warning!] your server does not support http2")
        sleep(0.5)

    # (可选) 更新一下各种包
    if not (distro.id() == 'ubuntu' and distro.version() == '14.04'):  # 系统不是ubuntu 14.04
        # Ubuntu 14.04 执行本命令的时候会弹一个postfix的交互, 所以不执行
        cmd('apt-get -y -q upgrade', allow_failure=True)

    cmd("""apt-get -y -q install libapache2-mod-wsgi-py3&& a2enmod wsgi""")

    # 安装和更新必须的python包
    cmd('python3 -m pip install -U flask')
    cmd('python3 -m pip install requests==2.11.0')

    # 安装和更新非必须, 但是有好处的python包, 允许失败
    cmd('python3 -m pip install -U chardet', allow_failure=True)
    cmd("python3 -m pip install -U cchardet", allow_failure=True)
    cmd("python3 -m pip install -U fastcache", allow_failure=True)
    cmd("python3 -m pip install -U lru-dict", allow_failure=True)

    infoprint('Dependency packages install completed')
    infoprint('Installing letsencrypt...')
    sleep(1)
    if not already_have_cert:
        if not os.path.exists('/etc/certbot/'):
            # certbot 不存在, 则安装
            cmd('git clone https://github.com/certbot/certbot.git --depth=1', cwd='/etc/')
            cmd('chmod a+x /etc/certbot/certbot-auto', cwd='/etc/certbot/')
            cmd("service apache2 stop", no_tee=True)
            cmd('/etc/certbot/certbot-auto renew --agree-tos -n --standalone', cwd='/etc/certbot/')
            cmd("service apache2 start", no_tee=True, allow_failure=True)
        else:
            # 否则升级一下
            cmd('git pull', cwd='/etc/certbot/')
            infoprint("let's encrypt Installation Completed")
        sleep(1)
    else:
        infoprint("you said you already have certs, so skip let's encrypt")

        infoprint('\n\n\n-------------------------------\n'
                  'Now we need some information:')
except KeyboardInterrupt:
    infoprint("Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc(), msg="KeyboardInterrupt")
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

try:
    # 尝试读取之前中断的安装设置
    if os.path.exists(DUMP_FILE_PATH):
        with open(DUMP_FILE_PATH, "r", encoding="utf-8") as fr:
            last_cfg = json.load(fr)  # type: dict
        infoprint(
            "We detected an incomplete install in", last_cfg["time"],
            "\n    with mirror:", ",".join(last_cfg["mirrors_to_deploy"])
        )
        if input("Do you want to continue that installation (Y/n)?") not in ("n", "N", "no", "No", "NO", "NOT"):
            mirrors_to_deploy = last_cfg["mirrors_to_deploy"]
            email = last_cfg["email"]
            question = last_cfg["question"]
            mirrors_settings = last_cfg["mirrors_settings"]
            loaded_config = True

except:
    errprint("Unable to load last config, ignore")
    os.remove("last_install.dump.json")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc(), msg="Unable to load last config")
else:
    infoprint("Load last installation's settings successfully")

try:
    _input = -1
    while _input:  # 不断循环输入, 因为用户可能想要安装多个镜像
        infoprint('----------------------')
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
                google='[SELECTED]' if 'google' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["google"]["installed_path"] else ""),

                twitterPC='[SELECTED]' if 'twitterPC' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["twitterPC"]["installed_path"] else ""),

                twitterMobile='[SELECTED]' if 'twitterMobile' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["twitterMobile"]["installed_path"] else ""),

                youtubePC='[SELECTED]' if 'youtubePC' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["youtubePC"]["installed_path"] else ""),

                youtubeMobile='[SELECTED]' if 'youtubeMobile' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["youtubeMobile"]["installed_path"] else ""),

                instagram='[SELECTED]' if 'instagram' in mirrors_to_deploy else (
                    "[INSTALLED]" if mirrors_settings["instagram"]["installed_path"] else ""),
            )

        )

        if not _input:
            break

        dbgprint("input:" + _input)

        try:
            _input = int(_input)
        except:
            errprint("Please input correct number")
            sleep(1)
            _input = -1

        if _input == 0:
            break
        if not (0 <= _input <= 6):
            errprint('please input correct number (0-6), only select one mirror a time\n'
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

        # 镜像已经安装, 则不允许选择
        if mirrors_settings[mirror_type]["installed_path"]:
            errprint("You can not select this mirror", mirror_type, "because it was already installed in",
                     mirrors_settings[mirror_type]["installed_path"])
            infoprint("If you want to upgrade it, please use `python3 deploy.py --upgrade-only`")
            sleep(1)
            continue

        # 在选项里, 镜像已存在, 则删去, 并且跳过下面的步骤
        if mirror_type in mirrors_to_deploy:
            mirrors_to_deploy.remove(mirror_type)
            mirrors_settings[mirror_type]['domain'] = None
            infoprint("Mirror:{mirror_type} unchecked.".format(mirror_type=mirror_type))
            sleep(1)
            continue

        # 输入镜像对应的域名, 要求已经在DNS设置中用一个A记录指向了本服务器
        print()  # 打印一个空行
        while True:  # 这里面会检查输入的是否是三级域名
            domain = input("Please input *your* domain for this mirror ({}): ".format(mirror_type))
            domain = domain.strip(' /.\t').replace('https://', '').replace('http://', '')  # 修剪
            if domain.count('.') != 2:
                warnprint(
                    "Your domain [",
                    domain,
                    "] is not an third-level domain, which contains three parts and two dots. \n"
                    "    eg1: lovelucia.zmirrordemo.com eg2: g.mymirror.com\n"
                    "    zmirror officially only support third-level domain\n"
                    "    a none third-level domain MAY work, but may cause potential errors\n"

                )
                if input("Continue anyway (y/N)? ") in ('y', 'yes', 'Yes', 'YES'):
                    break
                    # 如果选择的是 N, 则重新输入
            else:  # 输入的是三级域名
                break

        # 初步检验域名是否已经被正确设置
        try:
            domain_ip = socket.gethostbyname(domain)
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception as e:  # 查询目标域名的IP失败
            warnprint("Sorry, your domain [{domain}] is not setting correctly. {exc}".format(domain=domain, exc=str(e)))
            continue_anyway = input("Continue anyway? (y/N): ")
            if continue_anyway not in ('y', 'yes', 'Yes', 'YES'):
                continue  # 重新来
            else:
                # 仍然继续的话, 把domain_ip当做local_ip
                local_ip = '127.0.0.1'
                domain_ip = local_ip

        # 域名检验--目标域名的IP不等于本地机器的IP
        if domain_ip != local_ip:
            warnprint("""Sorry, your domain({domain})'s ip does not equals to this machine's ip.
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
            if mirrors_settings[mirror]['domain'] == domain and mirror != mirror_type:
                errprint("Duplicated domain! conflict with mirror: " + mirror)
                sleep(0.5)
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
                    errprint("file", private_key, "does not exist")
                    sleep(0.5)
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
                    errprint("file", cert, "does not exist")
                    sleep(0.5)
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
                    errprint("file", cert_chain, "does not exist")
                    sleep(0.5)
                else:
                    break

        # 将镜像添加到待安装列表中
        mirrors_to_deploy.append(mirror_type)
        mirrors_settings[mirror_type]['domain'] = domain

        # 保存设置到文件, 以防中断
        dump_settings()

        if already_have_cert:
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['private_key'] = private_key
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['cert'] = cert
            # noinspection PyUnboundLocalVariable
            mirrors_settings[mirror_type]['certs']['intermediate'] = cert_chain

        infoprint("Mirror:{mirror_type} Domain:{domain} checked".format(mirror_type=mirror_type, domain=domain))

        dbgprint(mirrors_to_deploy)

    if not mirrors_to_deploy:
        errprint("[ERROR] you didn\'t select any mirror.\nAbort installation")
        raise RuntimeError('No mirror selected')

    if email:  # 从上次安装的配置中读取
        infoprint("You had set your email as:", email)
        if input("Does this email correct (Y/n)?") in ("n", "N", "no", "NO", "No"):
            email = ""

    if not email and not already_have_cert:
        print()
        email = input('Please input your email (because letsencrypt requires an email for certification)\n')

        infoprint('Your email:', email)

    dump_settings()

    if question:
        infoprint("You had set a question:", question["name"],
                  "answer:", question["answer"],
                  "hint:", question["hint"] or "NONE")
        if input("Does this correct (Y/n)?") in ("n", "N", "no", "NO", "No"):
            question = None
        else:
            need_answer_question = True

    if not question:
        # 是否需要输入正确的密码才能访问
        print()
        infoprint("zmirror can provide simple verification via password\n"
                  "    just as you may have seen in zmirror's demo sites (however, demo sites does not require correct answer)")
        need_answer_question = input("Do you want to protect your mirror by password? (y/N): ")
        if need_answer_question in ("y", "yes", "Yes", "YES"):
            need_answer_question = True
            print()
            infoprint(
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
                name = input("Please input the question: ")
                if not name:
                    errprint("    question should not be blank")
                    sleep(0.3)
                    continue
                answer = input("Please input the answer (act as password): ")
                if not answer:
                    errprint("    answer should not be blank")
                    sleep(0.3)
                    continue
                hint = input("Please input the hint (optional, press [ENTER] to skip): ")
                question = {"name": name, "answer": answer, "hint": hint}
                break
        else:
            need_answer_question = False

    dump_settings()

    # 最后确认一遍设置
    infoprint('----------------------')
    infoprint('Now, we are going to install, please check your settings here:')
    if not already_have_cert:
        print("  Email: " + email)
    print()
    for mirror in mirrors_to_deploy:
        print("    Mirror: {mirror} Domain: {domain}".format(mirror=mirror, domain=mirrors_settings[mirror]['domain']))
    print()
    if need_answer_question:
        infoprint("Protected with question-answer:")
        print("  Question:", question["name"])
        print("  Answer:", question["answer"])
        print("  Hint:", question["hint"])

    print()
    if input('Are these settings correct (Y/n)? ') in ('N', 'No', 'n', 'no', 'not', 'none'):
        infoprint('installation abort manually.')
        raise SystemExit('abort manually.')

    # ############### Really Install ###################
    if not already_have_cert:
        # 通过 letsencrypt 获取HTTPS证书
        infoprint("Fetching HTTPS certifications")
        cmd("service apache2 stop", no_tee=True)  # 先关掉apache
        for mirror in mirrors_to_deploy:
            domain = mirrors_settings[mirror]['domain']

            if os.path.exists('/etc/letsencrypt/live/{domain}'.format(domain=domain)):
                # 如果证书已存在, 则跳过
                warnprint("Certification for {domain} already exists, skipping".format(domain=domain))
                sleep(0.2)
                continue

            infoprint("Obtaining: {domain}".format(domain=domain))
            i = 0
            try_limit = 5
            certbot_cmd = (
                '/etc/certbot/certbot-auto certonly -n --agree-tos -t -m "{email}" --standalone -d "{domain}" '
            ).format(email=email, domain=domain)
            seconds_to_wait = 4
            while True:
                i += 1
                seconds_to_wait += i
                try:
                    result = cmd(certbot_cmd, cwd='/etc/certbot/', allow_failure=True)

                    # 检查是否成功获取证书(文件是否存在)
                    if not result or not os.path.exists('/etc/letsencrypt/live/{domain}'.format(domain=domain)):
                        warnprint("cert file for {domain} does not exist!".format(domain=domain))
                        raise RuntimeError("cert file for {domain} does not exist!".format(domain=domain))

                except:
                    warnprint("unable to obtaining cert for {domain}".format(domain=domain))
                    if i <= try_limit:
                        infoprint("wait {} seconds and retry. ({}/{})".format(seconds_to_wait, i, try_limit))
                        onekey_report(
                            report_type=REPORT_ERROR,
                            traceback_str=traceback.format_exc(),
                            msg="({}/{})".format(i, try_limit),
                        )
                        for _ in range(seconds_to_wait - 1, 0, -1):
                            sleep(1)
                            infoprint(_, "...")
                    else:
                        errprint(
                            "\n"
                            "I'm really sorry that we are not able to obtain an cert now, \n"
                            "    This problem is NOT caused by zmirror-onekey itself, but caused by your DNS setting or "
                            "the let's encrypt server. \n"
                            "    If you had already set your A record correctly, "
                            "please retry and wait, because sometimes the "
                            "let's encrypt server may takes minutes or even hours to recognize your DNS settings.\n"
                            "    If you doesn't sure whether your DNS A record are correct, please check it using "
                            "https://www.whatsmydns.net/\n"
                            "    Meanwhile, you can obtain cert manually using:" + certbot_cmd
                        )
                        importantprint("For more information, please see http://tinyurl.com/zmcert")
                        importantprint("For more information, please see http://tinyurl.com/zmcert")
                        importantprint("For more information, please see http://tinyurl.com/zmcert")
                        importantprint("For more information, please see http://tinyurl.com/zmcert")
                        ch = input("max retries exceed, do you want to continue retry?(Y/n) ")
                        if ch in ("N", "n", "No", "no", "NO", "none", "None"):
                            errprint("Aborting...")
                            raise
                        else:
                            try_limit += 100

                else:
                    infoprint("Succeed: {domain}".format(domain=domain))
                    break

        cmd("service apache2 start",  # 重新启动apache
            # ubuntu14.04下, 使用tee会出现无法正常退出的bug, 所以禁用掉
            no_tee=True, allow_failure=True,
            )

    else:  # 选择自己提供证书
        infoprint("skipping let's encrypt, for you already provided your cert")

    # ####### 安装zmirror自身 #############
    infoprint('Successfully obtain SSL cert, now installing zmirror itself...')
    sleep(1)

    this_server = server_configs['apache']
    htdoc = this_server['htdoc']  # type: str
    config_root = this_server['config_root']  # type: str

    os.chdir(htdoc)
    zmirror_source_folder = os.path.join(htdoc, 'zmirror')
    if os.path.exists(zmirror_source_folder):  # 如果存在zmirror目录, 则移除掉(可能是上一次安装未完成的残留)
        shutil.rmtree(zmirror_source_folder)
    cmd('git clone %s zmirror  --depth=1' % __ZMIRROR_GIT_URL__, cwd=htdoc)

    # 预删除文件
    for pre_delete_file in this_server['pre_delete_files']:
        abs_path = pre_delete_file.format(
            config_root=config_root, htdoc=htdoc
        )
        infoprint("deleting: " + abs_path)
        try:
            os.remove(abs_path)
        except:
            dbgprint("Unable to remove file:" + abs_path)

    # 拷贝并设置各个镜像
    for mirror in mirrors_to_deploy:
        domain = mirrors_settings[mirror]['domain']
        this_mirror_folder = os.path.join(htdoc, mirror)

        # 如果文件夹已存在, 则报错. 但是如果是加载上次的配置, 则不报错, 而是删除掉上一次安装的文件夹, 重新安装
        if os.path.exists(this_mirror_folder):
            if loaded_config:
                warnprint("Folder {} already exists, will be removed".format(this_mirror_folder))
                shutil.rmtree(this_mirror_folder)
            else:
                errprint(
                    ("Folder {folder} already exists."
                     "If you want to override, please delete that folder manually and run this script again"
                     ).format(folder=this_mirror_folder)
                )
                raise RuntimeError("Folder {folder} for mirror [{mirror_name}] already exists.".format(
                    folder=this_mirror_folder, mirror_name=mirror))

        # 将 zmirror 文件夹复制一份
        shutil.copytree(zmirror_source_folder, this_mirror_folder)
        # 更改文件夹所有者为 www-data (apache的用户)
        cmd("chown -R www-data {path} && chgrp -R www-data {path}".format(path=this_mirror_folder),
            cwd=this_mirror_folder)

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

    try:
        shutil.rmtree(zmirror_source_folder)  # 删除无用的 zmirror 文件夹
    except:
        pass

    infoprint("zmirror program folders deploy completed")

    # ############# 配置Apache ###############
    infoprint("Now installing apache configs...")
    sleep(0.5)

    os.chdir(config_root)

    # 下载通用配置文件
    for conf_name in this_server['common_configs']:
        assert isinstance(config_root, str)
        url = this_server['configs'][conf_name]['url']
        file_path = os.path.join(config_root, this_server['configs'][conf_name]['file_path'])

        if os.path.exists(file_path):  # 若配置文件已存在则跳过
            warnprint("Config {path} already exists, skipping".format(path=file_path))
            sleep(0.2)
            continue

        with open(file_path, 'w', encoding='utf-8') as fp:
            infoprint("downloading: ", conf_name)
            fp.write(requests.get(url).text)

    # 下载并设置各个镜像的Apache配置文件
    for mirror in mirrors_to_deploy:
        domain = mirrors_settings[mirror]['domain']
        this_mirror_folder = os.path.join(htdoc, mirror)

        for conf_name in this_server['site_unique_configs']:
            url = this_server['configs'][conf_name]['url']
            file_path = os.path.join(config_root, this_server['configs'][conf_name]['file_path'])
            file_path = file_path.format(mirror_name=mirror, conf_name=conf_name)

            if os.path.exists(file_path):
                if loaded_config:
                    # 若是加载上一次的配置, 则先移除掉已存在的配置文件, 再重新安装
                    warnprint("Config {path} already exists, will be removed".format(path=file_path))
                    sleep(0.2)
                    os.remove(file_path)
                else:
                    # 若配置文件已存在则跳过
                    warnprint("Config {path} already exists, skipping".format(path=file_path))
                    sleep(0.2)
                    continue

            infoprint("downloading: ", mirror, conf_name)

            conf = requests.get(url).text

            # 因为Apache conf里面有 {Ascii字符} 这种结构, 与python的string format冲突
            # 这边只能手动format
            for key, value in [
                ('domain', domain),
                ('mirror_name', mirror),
                ('path_to_wsgi_py', os.path.join(this_mirror_folder, 'wsgi.py')),
                ('this_mirror_folder', this_mirror_folder),
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
        infoprint("Adding cert auto renew script to `/etc/cron.weekly/zmirror-letsencrypt-renew.sh`")
        cron_script = """#!/bin/bash
cd /etc/certbot
/etc/certbot/certbot-auto renew -n --agree-tos --standalone --pre-hook "/usr/sbin/service apache2 stop" --post-hook "/usr/sbin/service apache2 start"
exit 0
"""
        with open("/etc/cron.weekly/zmirror-letsencrypt-renew.sh", "w", encoding='utf-8') as fp:
            fp.write(cron_script)

        cmd('chmod +x /etc/cron.weekly/zmirror-letsencrypt-renew.sh')
        cmd('/etc/cron.weekly/zmirror-letsencrypt-renew.sh')

    # 重启一下apache
    infoprint("Restarting apache2")
    cmd('service apache2 restart',
        # ubuntu14.04下, 使用tee会出现无法正常退出的bug
        no_tee=True, allow_failure=True,
        )
except KeyboardInterrupt:
    errprint("KeyboardInterrupt Aborting...")
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc(), msg="KeyboardInterrupt")
    raise
except:
    onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc())
    raise

# 已经安装成功, 移除掉设置文件
try:
    os.remove(DUMP_FILE_PATH)
except:
    pass

infoprint("Finishing...")
try:
    onekey_report(report_type=REPORT_SUCCESS)
except:
    try:
        onekey_report(report_type=REPORT_ERROR, traceback_str=traceback.format_exc(), msg="SuccessReportError")
    except:
        pass

# ####### 完成 ########
infoprint("Congratulation!")
infoprint("If apache is not running, please execute `sudo service apache2 restart`")
# 最后打印一遍配置
infoprint("------------ mirrors ------------")
for mirror in mirrors_to_deploy:
    print("    Mirror: {mirror} URL: https://{domain}/".format(mirror=mirror, domain=mirrors_settings[mirror]['domain']))
infoprint("------------ mirrors ------------")

if distro.id() == 'debian' or distro.id() == 'ubuntu' and distro.version() == '15.04':
    print()
    warnprint("[WARING] your system does NOT support HTTP/2! HTTP/2 would not be available\n"
              "If you want to use HTTP/2, please use Ubuntu 14.04/15.10/16.04")
    sleep(1)

print()
infoprint("FAQs are here: http://tinyurl.com/zmirrorfaq")
infoprint("For more information, please view zmirror's github: ", __ZMIRROR_PROJECT_URL__)
infoprint("Contribution and Issues are more than welcomed.")
infoprint("btw, if you feeling good, I'll be grateful for your Star in github :)")
