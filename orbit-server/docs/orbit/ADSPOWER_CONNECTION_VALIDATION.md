# AdsPower 地址与连接修复验收

2026-11-10。用户明确放开旧固定回环端口限制；不改设备统一管理、可信心跳、权限、证书和广告执行边界。

## 实现与测试

- 登记、响应解析、本机适配器一致支持自定义HTTP(S)基址、域名/IP、端口及代理路径；Key不进入URL，控制面不访问登记地址。
- `Require api-key` / `Invalid api-key` 的API业务错误归类为ADSPOWER_AUTH_FAILED，且保留到发现结果摘要，避免泛化为Profile失败。
- 回归测试先失败后修复。后端完整6293通过；最后增加API Key摘要处理后，相关295项通过。前端完整108文件1388项通过，类型检查和生产构建通过。
- 初次完整后端执行因沙盒禁止绑定测试TLS端口失败（9失败、30错误），允许隔离本地监听后完整重跑通过；无修改断言绕过。
- 真实MySQL/Redis/HTTP登记专项39/39，独立设备mTLS专项50/50通过。旧测试中本应拒绝的合法域名/自定义端口，已随用户新合同改为成功登记与回读；凭据URL和非法协议仍拒绝。
- gstack在隔离前后端实际登记 `https://device.example:61000/adspower`，查询后重新打开编辑确认完整回填；再修改为 `http://local.adspower.net:50325`。测试数据未进入生产。
- 当前Mac实测 `/status`成功，Profile接口返回Require api-key；最终摘要为api_status READY、inventory_coverage UNAVAILABLE、error_code ADSPOWER_AUTH_FAILED。不将未知库存或零已观察数解释为没有Profile。

## 部署边界

代码和部署文件已准备。生产原先两条设备均无可信心跳且设备证书数为0；必须补充受控证书与持续上报进程，保存地址本身不会在线。

执行部署、签发test2证书、启用服务器常驻设备接收服务及Mac监测进程的组合命令被自动审批拒绝，要求用户明确授权；拒绝时命令未执行。部署许可及API Key私有文件路径正在等待用户提供。不能宣称线上已修复、真实设备已在线或Profile验收通过。

方案为服务器回环mTLS监听+现有SSH通道，客户端私钥留Mac、CA私钥留服务器，不新增公网入站端口。未执行广告写入。


## 已授权部署与真实设备验收（2026-11-10 16:31 北京时间）

用户随后明确批准部署及常驻监测，前述审批阻断已解除。自定义地址修复已发布，生产页面与本地构建SHA256一致，API readiness正常。

- 服务器 `orbit-device.service` 已启用，双向TLS仅监听127.0.0.1:18443；API与设备服务均active。
- Mac安装独立运行环境、`com.orbit.adspower-tunnel`及`com.orbit.adspower-monitor` LaunchAgent：登录自动启动、故障重启。SSH只转发Mac回环28443到服务器回环设备端口，不新增公网入站端口。
- 当前Mac绑定生产设备test2；另一条test未绑定该电脑，保持OFFLINE，不复制心跳冒充另一台设备。
- 实际连接发现Python严格TLS要求Authority Key Identifier，已补齐CA与叶证书SKI/AKI扩展，原客户端证书已撤销。验证未被关闭；新证书真实配置接口返回成功。叶证书有效期90天，须到期前续签。
- 用户确认原首次登录文件内容现为API Key后，识别其标准API Key标签，值保存至Mac监测程序私有文件（0600）；原登录内容没有作为AdsPower凭据发送。Key未上传服务器、GitHub或聊天。
- 重启监测后连续真实心跳ACKNOWLEDGED，test2由SUSPECT恢复READY；服务端记录seq=2、recovery_streak=2。后续序号继续增加。
- 实际Local API报告api_status=READY、inventory_coverage=FULL、observed_profile_count=1、error_code=null；服务器收到1个Profile观察。此为真实AdsPower读取结果，非测试替身。
- 当前设备没有账户/Profile关联，未选Profile读取Meta DOM，identity_report_count=0；在线与Profile库存成功不代表Meta账户身份、币种或广告执行能力已验证。

本轮生产浏览器登录验收未继续：用户已将原受控登录JSON改为API Key，不能用该文件执行平台登录。此前gstack自定义地址保存、修改、回填及手机布局的隔离前后端结果有效；本轮生产连接以真实mTLS回执、数据库接收记录及健康检查为证据。
