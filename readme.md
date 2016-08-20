# zmirror 一键部署脚本


### 前置要求

1. 一台VPS, OpenVZ/Xen/KVM均可

2. 操作系统:    
    * 允许的操作系统:  
        * Ubuntu 14.04/15.04/15.10/16.04+  
    * 推荐的操作系统:  
        * Ubuntu 16.04 x86_64
    * root权限  

3. 域名
    * 每个镜像要求一个三级域名(类似于`g.zmirrordemo.com`这样的, 有三部分, 两个点)  
    * 域名已经在DNS记录中正确指向你的VPS  
  
### 运行方法

```shell
sudo apt-get install python3 wget -y
wget https://raw.githubusercontent.com/aploium/zmirror-onekey/master/deploy.py
sudo python3 deploy.py
```

然后按照脚本给予的提示继续  
