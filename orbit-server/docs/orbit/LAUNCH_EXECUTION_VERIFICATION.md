# 原 execute 受理阶段验证

2026-11-08，北京时间。此记录只覆盖原执行入口的内部受理，不表示平台广告已经创建，亦不表示整个投放模块验收完成。

## 已实现与实际验证

- 原 `POST /api/v1/launch-plans/{id}/execute` 先捕获来源，再分批持久准备、封存完整清单；最终事务成功后才返回原 202 Task。未受理的 BUILDING Task 不可读。
- 当前 `launch.execute`、CSRF、原预检来源和配置版本逐次复核；启用意图另核原 `launch.publish`。不以编辑或读取权限代替执行。
- 原成功键优先按完整意图重放；新键复用相同来源也必须具有原 body 与原 CAS。审核发现遗漏后三处统一检查，实际负例验证改变 activate_ack 或 If-Match 均 409，且没有新增幂等、Task 或审计。
- 最终复核真实分配及名称全部明细、封存证明、完整 Task/命令/节点、引用集合、DB UTC 到期与上海业务日。Task、计划状态、引用、审计、outbox 和幂等结果同事务。
- 活跃准备不会被另一请求接管或清理；同键返回可识别的处理中冲突。前端保留原意图供手工同键核验，不自动创建新执行。
- 到期准备有界清理，ACCEPTED 历史不删除。尚未接常驻清理调度，不能声称自动恢复流程完整。

## 实际证据

默认来源缺失档：[16/16 回执](evidence/python-launch-execution-default-http.json)。验证严格字段/头、CSRF、动作撤销、未知计划及无来源时零 Task/命令写入。X-Target-Tenant 的超级管理员路径仍是已知缺口，拒绝用例不表示该原合同已实现。

隔离来源档：[38/38 回执](evidence/python-execution-provider-http.json)，用时 13.75 秒；其中 16 组执行协议、16 组预检及 6 组初始化/退出。执行协议覆盖真实 202、原 Task/首批节点、完整意图重放、1644 整笔回滚、分配/名称篡改、未封存拒绝、活跃准备保护、过期清理及 ACCEPTED 保护。

首轮 [33 通过/1 失败/4 未执行](evidence/python-execution-provider-failed-01-clock.json) 保留。失败是测试工具将 SQL 会话 timestamp 以字符串传入而触发 MySQL 1232；修复为精确 Decimal 后完整重跑通过。毫秒与跨日为真实 SQL 会话时钟边界注入，未声称自然等待十五分钟或 HTTP 系统跨日。

## 仍未完成

上述38项成功档 Provider 明确是 ISOLATED_TEST，素材引用使用 SQL 样本。后续[30/30真实接力回执](evidence/python-execution-material-bridge-http.json)已验证真实PNG本地分片组装、正式Worker扫描证据与执行引用同事务发布，包含双方撤权和outbox拒绝的整笔回滚；它没有覆盖HTTP上传页面，平台验证提供器仍为隔离来源。正式 Meta 身份/能力、指标与 workflow/adapter 来源、执行发送/暂停创建/回读/独立启用、UNKNOWN 核验及全部任务恢复仍须继续实现和验证。生产默认无 Provider 时明确拒绝，不把隔离成功升级为生产权威。

字段台账保持逐条判断；本专项不批量勾选整个 execute API、Task Schema 或投放模块。
