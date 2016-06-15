# coding=utf-8
import subprocess
import os
import sys

try:
    import requests
except:
    print('package requests is required for this program, installing now')
    subprocess.call('sudo python3 -m pip install -U requests')
    try:
        import requests
    except:
        print('Could not install requests, program exit')
        exit(1)

__author__ = 'Aploium <i@z.codes>'
__version__ = '0.1.0'

if sys.platform != 'linux':
    print('This program can ONLY be used in debian-like Linux (debian, ubuntu and some others)')
    exit(1)
if os.geteuid() != 0:
    print('Root privilege is required for this program. Please use `sudo python3 deploy.py`')
    exit(2)

mirrors_info = {
    'google': {
        'domain': None,
        'cfg': [('config_google_and_zhwikipedia.py', 'config.py'), ],
        'server_cfg': {'apache': {
            'http': 'https://raw.githubusercontent.com/Aploium/mwm_onekey/master/configs_apache2/google-http.conf',
            'https': 'https://raw.githubusercontent.com/Aploium/mwm_onekey/master/configs_apache2/google-https.conf'}
        },
    },
    'youtubePC': {
        'domain': None,
        'cfg': [('config_youtube.py', 'config.py'),
                ('custom_func_youtube.py', 'custom_func.py')],
        'server_cfg': {'apache': {'http': '', 'https': ''}},
    },
    # 'youtubeMobile': {'domain': None},
    'twitterPC': {
        'domain': None,
        'cfg': [('config_twitter_pc.py', 'config.py'),
                ('custom_func_twitter.py', 'custom_func.py'), ],
        'server_cfg': {'apache': {'http': '', 'https': ''}},
    },
    'twitterMobile': {
        'domain': None,
        'cfg': [('config_twitter_mobile.py', 'config.py'),
                ('custom_func_twitter.py', 'custom_func.py'), ],
        'server_cfg': {'apache': {'http': '', 'https': ''}},
    },
    'instagram': {
        'domain': None,
        'cfg': [('config_instagram.py', 'config.py'), ],
        'server_cfg': {'apache': {'http': '', 'https': ''}},
    },
}

print('OneKey deploy script for MagicWebsiteMirror. version', __version__)
print('This script will automatically deploy mirror(s) using MagicWebsiteMirror in your ubuntu(debian)')
print('You could cancel this script in the config stage by precessing Ctrl-C')
print('This Program Only Support Ubuntu 14.04 (for now)')
print()
print('Now we need some information:')

mirrors_to_deploy = []

_input = -1
while _input:
    _input = input(
        'Please select mirror you want to deploy?\n'
        'select one mirror a time, you could select zero or more mirror(s)'
        '1. Google (include scholar, image, zh_wikipedia) %s\n'
        '2. twitter (mobile and pc) %s\n'
        '3. youtube (pc) %s\n'
        '4. instagram %s\n'
        '0. Go to next steps. (OK, I have selected all mirror(s) I want to deploy)\n'
        % (
            '[SELECTED]' if 'google' in mirrors_to_deploy else '',
            '[SELECTED]' if 'twitter' in mirrors_to_deploy else '',
            '[SELECTED]' if 'youtube' in mirrors_to_deploy else '',
            '[SELECTED]' if 'instagram' in mirrors_to_deploy else '',
        )
    )
    if not _input:
        break
    elif _input == 1:
        mirrors_to_deploy.append('google')
    elif _input == 2:
        mirrors_to_deploy.append('twitterPC')
        mirrors_to_deploy.append('twitterMobile')
    elif _input == 3:
        mirrors_to_deploy.append('youtubePC')
        # mirrors_to_deploy.append('youtubeMobile')
    elif _input == 4:
        mirrors_to_deploy.append('instagram')
    else:
        print('[ERROR] please input correct number (0-4), only select one mirror a time')

email = 'none@donotexist.com'
use_https = False
if mirrors_to_deploy:
    # _input = input('do you want to use HTTPS (will install letsencrypt for https certification)? recommend for yes. (Y/n)')
    # if _input in ('n', 'no', 'not', 'none'):
    #     use_https = False
    #     print('will NOT install letsencrypt and HTTPS would NOT be available')
    # else:
    use_https = True
    print('program will install letsencrypt and enable https')
    # _input = input('[OPTIONAL] if you don\'t want to use default https port (443), you could specify a different port(1-65535). press ENTER to skip')
    # port = None
    # if _input:
    #     try:
    #         port = int(_input)
    #     except:
    #         print('a wrong port was given, would use default port 443:', port)

    _input = input('Please input your email (because letsencrypt requires an email for certification)')
    email = _input
    print('Your email:', email)

    print('You need an domain for each mirror, please input your domain (eg: g.mydomain.com):\n'
          'And set these domain(s)\'s DNS record to this machine\n'
          'domain for every site MUST NOT BE SAME\n'
          'don\'t have an domain? Don\'t panic. Please send an email to the author (aploium email: i@z.codes), '
          'and he will be happily to give you some domains(free)\n')
    for mirror in mirrors_to_deploy:
        _input = input('Please input domain for ', mirror)
        mirrors_info[mirror]['domain'] = _input
    for mirror in mirrors_to_deploy:
        print('Domain:', mirrors_info[mirror]['domain'], 'for Mirror', mirror)
else:
    print('[ERROR] you didn\'t select any mirror.\nAbort install')
    exit(4)

_input = input('Now, we are going to install, please check your settings above, really continue?(Y/n)')
if _input in ('n', 'no', 'not', 'none'):
    print('installation aborted.')
    exit(5)

# ############### Really Install ###################
print('Installing some necessarily packages')
# 更新apt-get
subprocess.call('sudo apt-get update', shell=True)
# 安装必须的包
subprocess.call('sudo apt-get install git python3 python3-pip wget -y', shell=True)
# 安装Apache2和wsgi
subprocess.call('sudo apt-get install apache2 libapache2-mod-wsgi-py3', shell=True)
# 启用一些Apache模块
subprocess.call('sddo a2enmod rewrite mime include headers filter expires deflate autoindex setenvif ssl')

# 设置本地时间为北京时间
subprocess.call('sudo cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime', shell=True)

# 安装和更新必须的python包
subprocess.call('sudo python3 -m pip install -U requests flask', shell=True)
# 安装和更新非必须, 但是有好处的python包
subprocess.call('sudo python3 -m pip install -U chardet fastcache cchardet', shell=True)

print('Installing letsencrypt')
os.mkdir('/etc/letsencrypt')
os.chdir('/etc/letsencrypt')
subprocess.call('sudo git clone https://github.com/certbot/certbot.git')
os.chdir('/etc/letsencrypt/certbot')
subprocess.call('sudo service apache2 stop || sudo service apache2 stop')
subprocess.call('sudo chmod a+x /etc/letsencrypt/certbot/certbot-auto')
if mirrors_to_deploy:
    for mirror in mirrors_to_deploy:
        _cert_reg_str = 'sudo service apache2 stop && /etc/letsencrypt/certbot/certbot-auto certonly --agree-tos -t -m %s --standalone -d %s &&sudo service apache2 start' % (
            email, mirrors_info[mirror]['domain'])
        subprocess.call(_cert_reg_str)
        if not os.path.exists('/etc/letsencrypt/live/%s' % mirrors_info[mirror]['domain']):
            print('[ERROR] Could NOT obtain an ssl cert, '
                  'please check your DNS record, '
                  'and run again after few minutes.\n'
                  'Installation abort')
            exit(3)

    print('Obtain SSL cert successfully, now installing MagicWebsiteMirror itself')

    subprocess.call('cd /var/www')
    os.chdir('/var/www')
    subprocess.call('git clone https://github.com/Aploium/MagicWebsiteMirror.git')
    for mirror in mirrors_to_deploy:
        subprocess.call('cp -r /var/www/MagicWebsiteMirror /var/www/%s' % mirror)
        subprocess.call('sudo chown -R www-data /var/www/%s &&sudo chgrp -R www-data /var/www/%s' % (mirror, mirror))
        for file_from, file_to in mirrors_info[mirror]['cfg']:
            subprocess.call('cp /var/www/%s/more_configs/%s /var/www/%s/%s' % (mirror, file_from, mirror, file_to))

        with open('/var/www/%s/config.py' % mirror, 'a', encoding='utf-8') as fp:
            fp.write('\n####### Added By MWM_OneKeyDeploy #######\n')
            fp.write("my_host_name = '%s'\n" % mirrors_info[mirror]['domain'])

            fp.write("my_host_scheme = '%s'\n" % ('https://' if use_https else 'http://'))

    subprocess.call('rm -rf /var/www/MagicWebsiteMirror')

    subprocess.call('cd /etc/apache2/site-enabled')
    os.chdir('/etc/apache2/site-enabled')

    for mirror in mirrors_to_deploy:
        conf_text = ''
        print('downloading %s\'s config file')
        for scheme in ('http', 'https'):
            try:
                conf_text = requests.get(mirrors_to_deploy[mirror]['server_cfg']['apache'][scheme]).text
            except Exception as e:
                print('Unable to download config of %s, porgram exit', e)
                exit(1)
            # noinspection PyTypeChecker
            conf_text = conf_text.replace('{{domain}}', mirrors_info[mirror]['domain'])
            conf_text = conf_text.replace('{{mirror_name}}', mirror)
            with open('%s_%s.conf' % (mirror, scheme), 'w', encoding='utf-8') as fp:
                fp.write(conf_text)

    subprocess.call('sudo service apache2 restart')
