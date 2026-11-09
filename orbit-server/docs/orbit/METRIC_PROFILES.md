# 指标归因口径版本目录

## 字段定义与未知状态

MetricProfileGuard接收产品MetricProfile的定义投影，恰好10字段；id由可信服务端上下文预分配，verified不能由调用方声明。拒绝额外id/tenant_id/actor_id/verified。原产品合同不改写，不增加公开写API。

| 字段 | 当前行为 |
| --- | --- |
| version | 非空、NFC、首尾空白规范化，最多64个码点，无控制字符；同profile下不可覆盖 |
| source | META或FIXTURE；source本身不代表已验证 |
| register_action_type / purchase_action_type / value_action_type | 每字段显式null或非空字符串，最长64；null保持未知，不补示例事件名、不补0 |
| attribution_windows | 1—10项，每项非空最长64；规范化后重复拒绝，作为窗口集合排序冻结；不静默去重 |
| action_report_time | 非空最长64，完整保存，不凭字段合法声称Meta参数已实测 |
| timezone_policy | 仅ACCOUNT_LOCAL，存储规范枚举 |
| breakdown | 仅TOTAL，存储规范枚举 |
| maturity_days | 整数1—90，必须显式提供；产品默认28由上游表单/配置提供，不把空值猜成28 |

定义递归按JSON键排序、保留null与字符串映射，生成UTF8 SHA256。源JsonNode后续变化不改写已冻结内容；toString不输出定义。只做合同结构和明确业务边界校验，实际Meta事件映射及参数能力仍需真实验证器。

## 内部登记事务

MetricProfileRegistry.registerTrustedVersion接受可信服务端预分配的profile UUID，复核当前数据库身份及当前租户SUPER_ADMIN数据角色；menu/action和公开会话入口未接通。自然幂等键是tenant/profile/version：同定义返回原记录且不重复登记事件，不同定义409；新版本独立写入，不覆盖旧版本。

READ_COMMITTED事务预占版本并加行锁，正文、定义发布标志及事件一起提交，事件失败全回滚。published=1只表示定义和登记事件完整提交，不能显示成平台验证成功。原因为非空、最多500码点且无控制字符，存储去除首尾空白的原因；同版本重复登记不会改写首次事件。

所有新版本固定UNVERIFIED，V007数据库约束也只允许该状态。真实Meta验证发布器和对应证据迁移尚未实现，不能直接改布尔值来冒充已验证。requireVerifiedMeta对当前META定义和FIXTURE均拒绝，FIXTURE不能用于生产分析；未来验证流程必须先补证据模型及迁移，再开放可信验证发布。

本轮还修正了RuleOwnership的独立使用边界：当前租户授权查询为空时立即拒绝，不能因为另一次成员查询仍能找到旧身份，就绕过已停用租户。规则写原有activeTenant检查保留。

## 迁移与实测

V007新增orbit_metric_profile_version和orbit_metric_profile_event，显式租户、不可变版本、正文JSON_VALID及摘要、UNVERIFIED约束、UTC时间、字段与表中文COMMENT。只在本工作区隔离测试库执行V001—V007；未迁移现有业务数据库。

26项定义测试覆盖全部必填、服务端字段注入、三个映射的null/类型/长度、归因窗口数量/重复/排序、成熟期边界/类型、枚举与控制字符、规范化后的存储枚举、冻结和原合同字段对照。真实MySQL新增8项：完整定义/未知映射、同版本冻结和不同版本、并发同定义一次提交、并发异定义409、审计失败回滚、当前管理角色、META/FIXTURE未验证阻断及数据库约束、跨租户及租户停用后重放拒绝。专项证据见evidence/metric-profile-core.json及evidence/mysql-configuration-integration.json，总MySQL专项41项。

## 未完成边界

没有生产已验证profile，没有实际Meta采集或人工映射核验，不以fixture代替真实数据。公开GET /api/v1/metric-profiles的分页/筛选/游标/monitor.read权限、profile选择界面、范围快照及成员权限集合、已发布指标快照、规则引用和真实模拟均未完成。规则reference_status继续PENDING_REFERENCES，没有启用入口或模型Worker；本目录不增加完整业务勾选。
