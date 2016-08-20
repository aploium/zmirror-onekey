# zmirror 一键部署脚本

### 前置要求

1. 一台墙外VPS, OpenVZ/Xen/KVM均可  

2. 操作系统:    
    * 支持的操作系统:  
        * Ubuntu 14.04/15.04/15.10/16.04+  
        * Debian 8  
    * 推荐的操作系统:  
        * Ubuntu 16.04 x86_64
    
    * 全新(刚安装完成)的操作系统. 如果系统中有其他东西, 可能会产生冲突   
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

然后按照脚本给予的提示继续, 如果有不懂的, 可参考下面的安装视频  
如果遇到bug, 请发issues提出  

### 安装过程视频
请点击下面的图片打开  
"视频"中的文字可以被选中和复制  
[![asciicast](https://asciinema.org/a/83322.png)](https://asciinema.org/a/83322)  

### 特性

* 支持一次部署多个镜像, 支持同VPS多镜像  
* 自动安装 [let's encrypt](https://letsencrypt.org/) 并申请证书, 启用HTTPS  
* 自动添加 let's encrypt 的定期renew脚本到crontab  
* 启用[HTTP/2](https://zh.wikipedia.org/wiki/HTTP/2)  
* 启用[HSTS](https://zh.wikipedia.org/zh-cn/HTTP%E4%B8%A5%E6%A0%BC%E4%BC%A0%E8%BE%93%E5%AE%89%E5%85%A8)  

