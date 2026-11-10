# Meta 账户列表补充字段

2026-11-10。只读 Graph v24.0；此文件记录实现和本地验证范围，不代替真实平台验收。

已授权账户的现有导入及 SYNC Worker 读取基础账户后，分别请求 business_name、business{id,name}、is_prepay_account、funding_source_details、disable_reason。LOGIN 另外读取 me{id,name}，并与冻结连接 principal_id 比较；BM 系统身份不冒充个人号。字段权限拒绝或字段不支持不阻断其他可选字段；认证失效、限流、连接版本变化、身份不匹配仍使任务失败。所有请求是 GET，令牌只在 Authorization 头中，每次请求前保持原权限/版本复验。

已有列表合同保持不变。经过白名单验证的 observations 和 BM 摘要写入 orbit_ad_account.details_json，和名称、账户版本、原 source_config_id/revision、审计、任务状态处于原 Worker 的同一事务。列表读取时按逐字段 observed_at 合并独立详情采集表，避免旧观测覆盖新值。现有账户可直接执行 SYNC，不要求重新授权或重新导入。

字段映射：

- personal_profile：LOGIN 的已核验授权主体姓名；不是推断广告账户拥有者。
- business_entity：Meta business_name；关联 BM 由账户 business 对象提供，不以配置BM猜测。
- payment_type：明确 is_prepay_account 布尔值转预付/后付；缺失保持未知。
- payment_method：仅 funding_source_details.display_string 脱敏说明，不保存原始付款对象、券或信用信息。
- lifetime_spend：amount_spent；payable：Meta balance（账单应付），绝不映射可用余额。
- blocked_reason：Meta 停用原因代码；0只表示无具体停用原因，不代表账户启用。

金额使用 Decimal 和显式 Meta currency offset 字典，未知币种不换算；不能用ISO小数位或全局除100。USD等显式100，JPY等显式1；Meta特殊整单位币种包括 HUF、ISK、TWD。接口保持十进制字符串，未返回金额不补0，真实0保留0。

官方依据：

- [Meta Python Business SDK v24 AdAccount](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/24.0.0/facebook_business/adobjects/adaccount.py)：本次成功查阅，确认请求字段和版本存在。
- [Meta currency offsets](https://developers.facebook.com/docs/marketing-api/currencies/) 与 [AdAccount reference](https://developers.facebook.com/docs/marketing-api/reference/ad-account/)：本次工具请求被站点429阻断；不能把此轮访问记为文档验证通过。映射需真实不同币种验收继续核对；本次生产关注USD。

边界：可用余额、信用额度、账单明细不推算。主页/像素/应用身份及其可投放能力继续由已有独立证据流程负责，不由本元数据读取宣称完成。所选日期消耗继续使用既有每日事实和完整覆盖合同，不从累计消费或应付推算。现已通过账户同步读取每日消费，不需要注册、购买等转化指标配置。

本地验证使用合成Graph响应与本地TLS服务器，未调用真实凭据：新增测试覆盖金额USD/JPY/HUF、未知币种和缺失值、可选权限拒绝、403认证/限流、BM对象校验、manual BM、同步同事务写入参数与来源版本。具体最终运行结果由执行回执记录。


## 每日消费接入与最终本地验证

账户 SYNC 复用同一连接及逐请求门禁，以 GET act_ID/insights 读取账户当地最近90日的 account_id、account_currency、date_start、date_stop、spend；level=account、time_increment=1，无转化归因字段。不以90天窗口缺行推断零；只有完整分页后的明确行进入既有 orbit_account_spend_day/history。显式0正常保留，空响应仍未知；币种、账户、日期范围、重复日、金额精度和分页边界均校验。

完成时再次验证原命令claim、当前权限、来源版本、账户归属及币种/时区，然后在原事务内调用 AccountDetailsStore.publish：沿用现有冻结历史归属、事实历史、水位和审计；较旧观测不覆盖更新日事实。当前范围不能完整覆盖的聚合继续显示未知。未知历史拥有者仍受原事实可见性限制。

新建的自动导入账户仅在发起人仍拥有 accounts.sync 且范围匹配时排队原 SYNC 命令；不创建另一套调度/事实系统，不覆盖重导入账户。已有账户直接同步即可。LOGIN可选Insights权限不足/请求拒绝保留元数据，details.spend_sync暴露固定原因及观测时刻；认证失效、限流、撤权、来源变化传播为原同步失败/重试。

2026-11-10最终运行：

- `PYTHONPATH=python:. /tmp/orbit-live-verification-venv/bin/python -m pytest python/tests -q`：6325 passed，72.83秒。日志 `/tmp/meta-daily-spend-full-regression.log`。
- `bash /tmp/run-meta-auto-import-sql.sh`：独立MySQL/Redis及合成Graph，78/78 PASS。日志 `/tmp/meta-auto-import-sql.log`。新增验证：导入后的应付5.67、累计12.34、授权主体/BM及来源写入、原ACCOUNT_BOUND审计，两个账户各自动排队原SYNC，明确当天0.12发布为COMPLETE每日事实。
- 测试修正仅补齐合成来源的真实字段（details_json、principal_id及/me响应），重复导入等原断言保留；新增字段亦参与前后记录相等断言。
- 上述均非真实Meta外部验收；最终生产部署与真实账户结果由主线另行核验。

## 手动同步与转化策略解耦

手动账户同步调用 enqueue_metrics(require_policy=False)：只有连接覆盖策略和租户回退策略均不存在时，跳过转化指标任务，仍受理原元数据/每日消费 SYNC。若已有策略，原指标口径、来源版本、权限和事务错误照常传播；不捕获任意错误冒充缺少配置。定时及显式指标采集默认 require_policy=True，缺少策略仍失败。

隔离MySQL新增验证真实 capabilities→sync 路径：两个策略表均空时返回 WAITING_EXECUTOR、未创建指标任务，后续原 AccountSyncWorker 完成。扩展后的原78项隔离测试全部通过（24.78秒）。

本补丁完整后端回归：6328 passed，72.26秒；日志 `/tmp/meta-manual-sync-full-regression.log`。补丁涉及的5个Python文件 Ruff 检查和格式均通过。

生产验收补记：两个授权账户分别为USD、IDR，均真实同步成功；本次只观测到Meta返回金额0，不能据此宣称非零币种换算已完成外部对账。个号、后付类型、可获得的主体/BM及停用原因已在列表显示。两账户近90个当地业务日均未返回Insights行，显示明确空数据原因。完整证据边界见 `meta-integration/AUTO_IMPORT_VALIDATION.md`。
