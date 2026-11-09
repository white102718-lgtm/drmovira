# 邀请通知投递

此任务仅实现人员邀请的Webhook投递，不代表邮件实际送达。管理端只能读取投递元数据，不取得一次性邀请链接。

## 状态与一致性

1. 创建邀请时同事务写入AES-GCM加密的QUEUED记录，投递UUID固定且唯一。
2. Worker使用索引与 `FOR UPDATE SKIP LOCKED` 单条认领；每轮最多100条。发送前重新核对邀请有效期、人员与邮箱版本、发起人当前权限及安全版本、登录提供者与通知配置版本。
3. 任一快照失效则记录FAILED且不发送；不能把旧邀请静默发送到新配置地址。有效邀请先在短事务中提交SENDING及审计，再在事务外发出一次HTTPS请求，避免持有数据库锁等待网络。
4. 渠道明确接受才记录ACCEPTED；明确拒绝记录FAILED；超时、断连、服务端错误或无效回执记UNKNOWN，不自动重发。ACCEPTED不等于邮件送达。
5. 网络总上限15秒。超过60秒仍为SENDING的任务由恢复模式改为UNKNOWN，不重新入队。回执绑定认领版本，迟到回执不能覆盖恢复后的状态。
6. 终态更新与审计同事务。发送成功而终态审计失败时保留SENDING，后续恢复为UNKNOWN；不能重发来“补写成功”。用户明确重发才创建新邀请并撤销旧凭据。

## Webhook协议

请求为HTTPS443的JSON POST，不使用环境代理，不跟随重定向或自动重试。DNS全部结果必须为公网地址；连接固定到校验后的地址，TLS仍验证原主机名，拒绝本机、内网与云元数据服务。

请求头 `Idempotency-Key` 等于稳定投递UUID。JSON含 `event_type=ORBIT_USER_INVITATION_V1`、`delivery_id`、`recipient_email`、`activation_url`、`expires_at`。激活凭据位于 `/invite#凭据` 的片段中；接收渠道只能按配置向指定邮箱投递，不应记录或公开链接。

配置 `webhookToken` 时附带 `X-ORBIT-Timestamp`（Unix秒）与 `X-ORBIT-Signature=sha256=<hex>`；签名为HMAC-SHA256，输入是原始时间戳字节、一个英文句号和原始JSON字节。接收端须校验签名、时间窗及稳定投递ID。Token本身不出现在HTTP头、URL或日志中。

成功回执必须为2xx、JSON对象，含原始 `delivery_id` 和布尔 `accepted=true`。`accepted=false`为明确拒绝；未知ID、字符串布尔值、非JSON、重复键、超大响应等均不能冒充接受。回执不保存原文，失败仅保留固定类别。

## 受控运行

- `python tools/run_invitation_worker.py --send --limit 10`：明确发送一轮。
- `python tools/run_invitation_worker.py --recover --limit 100`：仅恢复超时认领，不发请求。

命令没有默认发送模式，不接受密码、连接字符串或Token参数。运行配置仍只从指定私有环境文件的ORBIT_PYTHON_命名空间读取。当前未将该任务自动加入调度器，也未对任何真实渠道执行命令；完整登录页面与通知渠道外部实测仍待完成。

## 验证边界

隔离HTTPS传输12项通过，覆盖签名、真实回执、重定向拒绝、响应断连与不自动重试。MySQL认领、并发、恢复和审计故障5组专项已加入144组后台检查并通过；实际来源及源码指纹见 `evidence/python-invitation-delivery.json`。命令行解析5项通过，但完整命令启动未实测；未将该任务自动加入调度器。没有真实邮件送达证据，不据此勾选完整任务验收。
