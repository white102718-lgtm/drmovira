# 执行机 AdsPower 只读状态探测

本模块在 AdsPower 所在执行机运行。控制面仅登记 API 基址，不主动访问用户提供的地址。`polling` 支持只读 Profile 发现和经设备证书验证的心跳；启动它不会授权广告写入。

使用项目现有 Python 环境（Python 3.12+、httpx 0.28.x）：

```sh
cd orbit-server
PYTHONPATH=python .venv/bin/python -m orbit_agent.adspower_status
```

默认单次请求 `GET http://127.0.0.1:50325/status`。也支持 `http://local.adspower.net:50325`、局域网 IP、HTTPS 域名、自定义有效端口及反向代理基路径。端口不再需要白名单；旧 `--allow-port` 参数仅兼容已有启动脚本。`localhost` 仍规范为 `127.0.0.1`。基址不得包含账号密码、查询参数或片段，Key 仍用独立私有文件传入。

```sh
PYTHONPATH=python .venv/bin/python -m orbit_agent.adspower_status \
  --endpoint http://local.adspower.net:50325
```

若执行机的 AdsPower 启用了 API 安全校验，由机器管理员独立保存密钥至本人拥有的私有普通文件（权限 0600），并明确传入绝对路径 `--api-key-file /absolute/private/path`。工具不会寻找或读取 AdsPower 现有密钥，也没有明文密钥参数。密钥不会放进 URL、结果或日志；拒绝符号链接、组/其他人可访问文件、超长文件及头注入内容。

响应体最大 4096 字节，总截止时间默认 3 秒、最大 10 秒；禁用环境代理、重定向和压缩。返回仅含固定状态，不返回 AdsPower 的 msg 或未知字段。失败以固定错误码和退出码 1 表示，成功退出码 0。

成功仅代表 Local API 当前可用：

```json
{"api_status":"AVAILABLE","profile_status":"UNKNOWN","meta_login_status":"UNKNOWN","execution_capability":"UNVERIFIED"}
```

不能据此签发执行能力、认定 Meta 登录有效、推导 Profile 列表、占用租约或创建广告。客户端版本由独立来源确认，本探测不伪造版本信息。

官方合同：[GET /status](https://localapi-doc-en.adspower.com/docs/6DSiws)、[API Overview / Bearer Key](https://localapi-doc-en.adspower.com/docs/Rdw7Iu)。2026-11-10用户变更覆盖旧ENV-02固定本机端口限制；新增地址可登记不等于已经可达。
