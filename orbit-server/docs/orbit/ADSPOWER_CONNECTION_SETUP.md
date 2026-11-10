# AdsPower 自定义地址与设备连接

2026-11-10，用户要求覆盖原本仅允许localhost/127.0.0.1:50325的限制。

## 地址

前后端及执行机一致支持HTTP/HTTPS、域名、IPv4/IPv6、1—65535有效端口和代理基路径。示例：`http://local.adspower.net:50325`、`http://192.168.1.20:61000`、`https://device.example:5443/adspower`。协议必须完整；不能把密码、Key、查询参数或片段放入基址。登记不发起网络请求，不由云端探测云服务器自己的127.0.0.1。

## 从保存到在线

1. 在运行AdsPower的电脑打开Local API，确认真实地址。`/status`成功仅证明API服务可达；Profile读取可能还需要API Key。
2. 超级管理员登记设备，取得Agent ID。每台真实电脑使用自己的设备记录及证书；不要用同一电脑重复心跳冒充多台设备。
3. 运维为该ID签发受信任客户端证书并注册公钥指纹。客户端私钥只留执行机。服务器启动独立双向TLS设备监听器，不信任浏览器或代理伪造的证书头。
4. 执行机运行 `python -m orbit_agent.polling --endpoint <API基址> --device-origin <设备接收地址> --agent-id <ID> --ca-file <CA> --certificate <公钥证书> --key-file <私钥> --spool-dir <私有队列> --forever`。需要时增加 `--api-key-file <私有文件>`。默认不选Profile，不主动读取Meta页面，不执行广告操作。
5. 两次新的可信心跳后在线，重复报文不能续期。API认证失败与机器在线分别显示，Profile库存未知不冒充空库存。

本次单机部署使用SSH本地转发访问服务器回环mTLS端口，不新增公网开放端口。需要AdsPower及Mac监测进程持续运行；电脑休眠/关机或隧道中断后，90秒失联按OFFLINE展示。证书到期前须续签，不能关闭证书校验。

API Key若需要，保存为本人私有普通文本文件（0600），不要粘贴到聊天、URL或GitHub。平台不因设备在线自动发放广告写权限。后台修改登记地址后，还需将执行机启动配置改成同一地址并重启监测进程。
