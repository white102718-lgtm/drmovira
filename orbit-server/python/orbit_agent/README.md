# 执行机 AdsPower 只读状态探测

本模块在 AdsPower 所在的执行机运行。不得由云端 API 路由调用本机地址，当前也没有接入任何云端路由、数据库、心跳、Profile 或执行任务。

使用项目现有 Python 环境（Python 3.12+、httpx 0.28.x）：

```sh
cd orbit-server
PYTHONPATH=python .venv/bin/python -m orbit_agent.adspower_status
```

默认单次请求 `GET http://127.0.0.1:50325/status`，不重试、不读 Profile、不启动浏览器。`localhost` 会固定转为 `127.0.0.1`，不使用 DNS，也不接受 `local.adspower.net`。自定义端口必须同时明确加入白名单：

```sh
PYTHONPATH=python .venv/bin/python -m orbit_agent.adspower_status \
  --endpoint http://localhost:50326 --allow-port 50326
```

若执行机的 AdsPower 启用了 API 安全校验，由机器管理员独立保存密钥至本人拥有的私有普通文件（权限 0600），并明确传入绝对路径 `--api-key-file /absolute/private/path`。工具不会寻找或读取 AdsPower 现有密钥，也没有明文密钥参数。密钥不会放进 URL、结果或日志；拒绝符号链接、组/其他人可访问文件、超长文件及头注入内容。

响应体最大 4096 字节，总截止时间默认 3 秒、最大 10 秒；禁用环境代理、重定向和压缩。返回仅含固定状态，不返回 AdsPower 的 msg 或未知字段。失败以固定错误码和退出码 1 表示，成功退出码 0。

成功仅代表 Local API 当前可用：

```json
{"api_status":"AVAILABLE","profile_status":"UNKNOWN","meta_login_status":"UNKNOWN","execution_capability":"UNVERIFIED"}
```

不能据此签发执行能力、认定 Meta 登录有效、推导 Profile 列表、占用租约或创建广告。客户端版本由独立来源确认，本探测不伪造版本信息。

官方合同：[GET /status](https://localapi-doc-en.adspower.com/docs/6DSiws)、[API Overview / Bearer Key](https://localapi-doc-en.adspower.com/docs/Rdw7Iu)。ENV-02 的本机地址限制比官方地址示例更严格，按产品合同执行。
