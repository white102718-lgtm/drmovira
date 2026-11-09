# 指标配置与执行版本：真实来源只读审计

2026-11-08，只读审计；没有修改schema、公共代码、私有配置或参考仓库，没有连接真实数据库/平台。040及以后迁移编号待主线统一分配。以下是合同定位与建议，不是新增功能已实现声明。

## 精确原候选接口与菜单

| 原接口 / operationId | 原权限及八菜单归属 | 原响应与过滤 | 当前缺口 |
| --- | --- | --- | --- |
| GET /api/v1/metric-profiles / listMetricProfiles | monitor.read / monitor | MetricProfilePage；q、cursor、page_size=20/50/100/200默认50、status、date_from/date_to、operator_user_id、channel_id(1..64文本)、metric_profile_id UUID、entity_type | 当前无真实profile目录/版本存储与原路由消费者；不能把返回示例当生产profile |
| GET /api/v1/capabilities / listCapabilities | launch.read / launch | CapabilityPage；同上11个原查询参数 | 当前无真实Meta能力组合目录和来源核验；原allocation/validation/execution的ABC与fixture不是目录 |
| GET /api/v1/environment-capabilities / listEnvironmentCapabilities | environments.read / environments | AgentCapabilityPage；仅cursor与page_size | 缺真实agent/profile binding/工作流与adapter发布及能力观察目录，不可由账户identity证据替代 |

依据contracts/openapi.json的x-permission、parameters与response引用，API_INDEX.md第117/118/150行，contracts/menu-action-map.json及PERMISSIONS.md。三者不是同一个capability对象。原接口仅定义GET，没有给客户端手动设置verified或任意写版本表的CRUD授权。服务端发行/注册可复用system.release.manage的受控内部入口设计，但新增HTTP管理接口需主线登记扩展，不擅造权限。

公共配置/字典不含他人业务记录，但适用性通过账户、拥有者、团队、渠道和profile绑定约束；列表不能泄露范围外账户绑定。内部预检/执行应核原launch动作及caller与目标owner的真实来源权限，不简单要求调用方额外monitor.read才能消费计划已授权profile，也不能因为可读候选就授予launch.execute/publish。

## MetricProfile原字段与转换边界

原Schema-MetricProfile：id UUID；version字符串1..64（不是整数revision）；source=META或FIXTURE；register_action_type/purchase_action_type/value_action_type为1..64文本或null；attribution_windows为1..10项、每项1..64文本；action_report_time文本1..64；timezone_policy固定ACCOUNT_LOCAL；breakdown固定TOTAL；maturity_days为整数1..90；verified严格boolean，所有字段必有、additionalProperties=false。

WORKFLOWS.md:43/47要求实际映射和版本：未映射返回null，禁止把示例当平台事件；删除需已验证归因成熟期，缺配置不得用“默认28天”绕过。reference/03原合同:17/26/439要求按唯一action_type映射actions/action_values、保存原数组，事实粒度含profile版本口径，不重复累加归因窗口/细分。

现launch_execution_contract.py:MetricProfile已严格保留原字段；ResolvedMetricProfile是内部适配DTO，另外绑定profile_source_hash、adapter_version、bound_profile_version、registry_revision及明确AttributionSpec(event_type/window_days)。_profiles要求每个adset.metric_profile_id有完整包、version/hash匹配，但纯DTO允许source=FIXTURE；TRUSTED生产Authority仍必须拒绝FIXTURE/缺权威凭据来源，不能把verified=True当写许可。原窗口文本不等于目标平台AttributionSpec，严禁从1d_click字符串猜event_type/window_days。

现launch_references.require_config_dependencies对任意非空metric_profile_id直接503 METRIC_PROFILE_DEPENDENCY_UNAVAILABLE；所以目录和真实同租户/适用范围查询接入前，原草稿引用也不能称已完成。039执行准备仅冻结调用方提供的完整ResolvedMetricProfile，不会生成这个权威包。

## workflow_version / adapter_version精确含义

FIELDS.md:1218/1224：两者默认都为“能力包”，分别是经能力验证的工作流版本与页面/API适配器版本，均不允许硬编码v1/latest。PlanWrite/Plan中为可选非空字符串1..64（非null）；launch_contract只校文本，不能核版本存在、启停或能力适用性。

ADSPOWER_WORKFLOWS.md第2/3/4/8节：两个通道按operation_kind、对象层级、语言、AdsPower客户端/内核、页面Adapter版本和测试回执逐项启用；缺验证CAPABILITY_UNVERIFIED。六个workflow_id为launch_ads_v1、set_budget_v1、pause_entity_v1、delete_entity_v1、verify_operation_v1、recover_unknown_v1，这些是工作流标识，不是可拿来自动补齐的“已验证version”。ENABLE与ARCHIVE是独立命令适配器，不假扮PAUSE/DELETE。

原AgentCapability所有字段必填：id、agent_id、profile_binding_id UUID；operation_kind=CREATE/BUDGET_SET/PAUSE/DELETE/ENABLE/ARCHIVE；entity_type=CAMPAIGN/ADSET/AD；workflow_version、adapter_version、client_version、browser_version、page_language各1..64；state=UNVERIFIED/VERIFIED/REVOKED；evidence_ref(1..255或null)、verified_at(UTC时间或null)。ExecutionLease与AgentEvent也冻结两版本，不能只有Plan字符串或通用API能力version。

023账户identity证据记录account_revision/source_config_id与revision/capability_version/complete/verified等，只证明读取时某身份资源可用；不是Agent版本、真实workflow发行、当前账户写授权或本次operation许可。039持久准备来源与冻结包也不自动注册AgentCapability。源码001—039定向检索未发现metric_profiles、workflow_versions、adapter_capabilities、agent/profile binding的实际业务注册表/消费者；009的business_agent是“总代”，绝非execution_agent。

## 参考代码可参考与不可继承内容

- D:/progress/schedulers/tasks/ad_sync_new/airbyte/runner.py:29..52：按账户时区/日范围构Insights请求，分页/异步作业与配额处理可参考；action_attribution_windows缺省1d_click只是旧项目默认值，不能作为ORBIT真实profile默认。
- 同项目transform.py:157..202：缺失指标保留None的意图可参考，但purchase/complete_registration等映射为硬编码；ORBIT必须从被版本绑定的MetricProfile选择唯一事件，不照搬成已验证META映射。
- D:/progress/adpulse-power-system/.../DorisDeliveryReportQueryProvider.java:71有purchases=账户内首购的旧项目口径；不自动覆盖ORBIT原profile的purchases/action_type语义。
- D:/progress/ai-ad-platform-vben/plat/src/domain/workflow-runtime/types.ts是creative-task/delivery-task/resource-application业务流的只读allowedActions，不是AdsPower六工作流发行/执行引擎或页面Adapter能力注册。
- 对D:/progress/backend、schedulers、adpulse-main与vben指定代码扩展名的定向检索，没有找到可直接搬用的MetricProfile或workflow_version/adapter_version真实注册表；结论是本次搜索范围未找到，并非宣称所有仓库所有文件都不存在。

参考仓库均只读，未导出密钥、连接、平台响应或用户数据。

## 待主线分配的最小SQL来源（提案，未创建DDL）

| 来源层 | 最小真实存储与版本绑定 | 索引/约束及不能伪造的事实 |
| --- | --- | --- |
| 指标profile目录 | tenant+id的受控head；不可变(tenant,id,version)快照存原MetricProfile规范JSON/hash、内部revision/状态/来源引用、映射观察时间；当前head指向明确version | 同租户复合FK；(tenant,status,id)键集，名称检索单独规范字段；不把内部revision塞回原响应；空库不预植verified META示例 |
| 指标目标参数适配绑定 | tenant+profile_id+profile_version+adapter_version唯一，存明确AttributionSpec规范JSON/hash、registry revision、来源/evidence与启停；绑定同版本profile hash | 精确主键查询/批量锁，version不变但hash替换拒绝；FIXTURE只能本机独立库，生产拒绝；缺映射仍503 |
| Meta组合能力目录 | 原Capability完整版本化记录，引用同租户metric profile确切version；额外内部范围/观察来源config revision、receipt hash、revoked_at/已知到期 | objective/budget_owner/type/asset_kind/metric_profile/id索引；媒体限制、币种最小预算、CTA国家优化组合真实验证后才verified，不用身份capability_version一列顶替完整组合 |
| 工作流/adapter受控发行 | workflow_id+version、adapter_id+version+channel的不可变artifact/hash与来源/启停/测试回执；执行冻结明确pair | 不下载latest，不仅存自由字符串；代码发布来源与“动作在特定Agent环境已验证”分开 |
| Agent能力观察 | 原AgentCapability记录和同租户agent/profile_binding FK，冻结两版本及client/browser/language/operation/entity/evidence；另存真实scope/绑定revision、证书/撤销/观察时刻 | (tenant,binding,operation,entity,state,id)及版本组合索引；读取必须交叉当前binding.owner/account权限。Agent在线/租约有效/已验证能力各自独立，不能仅VERIFIED布尔开写 |
| 各目录水位/审计 | 有界head clock、版本新增/停用与scope变化同事务event/outbox；游标签tenant/actor/filter/scope及目录版本 | q包含搜索的扫描风险单列，游标不等于容量压测。日期/status在原GET存在但业务含义未明时显式拒绝，不忽略或擅猜 |

040编号及实际拆表顺序由主线决定；本提案不要求一次建全M11。MySQL同租户FK/索引+应用范围保持本栈，不照抄原PostgreSQL RLS示例。

## 可先实现的内部闭环与继续关闭项

1. 严格原MetricProfile/Capability DTO与精确version读取服务、不可变profile适配binding、原GET候选分页和当前权限：可以本地内部开发/真实SQL验收，生产可空或UNVERIFIED，不能默认示例META通过。
2. 将launch_references的无条件503替换为当前租户/目标owner适用profile精确锁读；取得source/version/hash后交预检及039包，缺registry或mapping仍failclosed。
3. 工作流/adapter的明确来源冻结/撤销与AgentCapability候选DTO、只读列表，可在实际Agent与平台凭据未齐时开发；无证据不允许VERIFIED，更不能发送命令。
4. 真实Meta只读能力采集、指标事件映射回读和AdsPower按组合验证、Agent证书/心跳/租约/写前持久日志，仍需实际环境验收。能力候选/账户identity观察只供选择与预检，最终launch.execute/publish、当前账户平台写权、目标锁/风险账本/确认必须独立核验。UNKNOWN不得换版本/换通道重发。

本轮只交审计与实施依赖，不修改现default None门禁，不将任何候选能力或版本字符串升级成执行授权。
