# base env

npm install -g corepack@latest  
corepack enable  
corepack use pnpm@latest  
pnpm install  

## 测试

使用仓库 `packageManager` 声明的 pnpm 版本执行：

```powershell
corepack pnpm --filter @vben/plat typecheck
corepack pnpm --filter @vben/plat build
```



# 启动项目

pnpm dev

# 开发流程

1. 在`plat/src/views`中找到对应模块中开发xxx.vue后, 在`plat/src/router/routes/modules`中引用

图标用`<span class="icon-[ant-design--alipay-circle-outlined]"></span>`来显示

新增后端接口后, 要在.env.development中增加类似VITE_GLOB_API_URL的变量, 注意要以VITE_GLOB_开头, 否则可能不会被加载  
然后去配置vite.config.mts反向代理处理跨域问题. [参考](https://doc.vben.pro/guide/essentials/server.html)
> 注意  
从浏览器控制台的 Network 看，请求是 http://localhost:5555/api/user, 这是因为 proxy 配置不会改变本地请求的 url。

查看代理后的接口或者请求接口路径是否正确, 可以开启vite的debug模式, 在package.json中修改`"dev": "pnpm vite --mode development",`为`"dev": "pnpm vite --debug --mode development",`

# 部署

需提前安装 nginx 服务

/root/soft/ad-plat/frontend/dist

vim /etc/nginx/sites-available/ad-plat
写上nginx配置内容
然后执行下面命令
```shell
sudo ln -s /etc/nginx/sites-available/ad-plat /etc/nginx/sites-enabled/
sudo nginx -t
sudo nginx -s reload
sudo systemctl reload nginx
sudo systemctl restart nginx
chmod -R o+x /home/ubuntu
```

## 更新服务

```shell
cd /home/ubuntu/soft/ad-plat/frontend/dist && unzip -oq /home/ubuntu/dist.zip
等一会nginx会自动更新
```

报错排查
```shell
sudo tail -n 20 sudo tail -n 20 /var/log/nginx/error.log
tail -f /var/log/nginx/ad-plat-access.log.1
```
## 反向代理修改

plat/vite.config.mts

