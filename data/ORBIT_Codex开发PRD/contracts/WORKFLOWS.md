# 本版范围适用说明

本文为原合同详细语义基线。已删除的独立模块流程不再实施，适用边界以01_修订需求与删除边界.md为准；保留页面的字段、AI闭环、预算、状态与双通道规则不因此删除。

# 精确算法和状态合同

本文件的数值和取舍为本次方案默认D；U权限见PERMISSIONS.md。金额都用十进制字符串，比较与计算用Decimal，最后按币种最小单位校验。默认值可以版本化调整，但不能在任务执行中静默变化。

## 1 首期范围与归属

首期实现全部原有管理页面、Meta只读采集、API创建、规则/AI建议/人工执行闭环、审批人工履约与AdsPower监测。仅Meta可启用投放与导入；Google/TikTok可保存主数据但连接器显示UNSUPPORTED。AdsPower UI写通道纳入开发，创建、修改预算、关闭、删除及反馈见ADSPOWER_WORKFLOWS.md；生产按动作能力验证后逐项开启，未验证不执行。归因平台仅保存配置与密钥引用；真实连接器、订单接入和自动结算首期禁用。费率只存不计算账单；余额没有权威来源就null+UNKNOWN。

账户转投手/转团队均在账户当地下一业务日00:00生效，采用[start_date,end_date)区间且不重叠。新导入账户从本地绑定日开始归属，早于绑定日的历史事实归UNASSIGNED，只能团队管理员和超级管理员看；不自动奖励当前投手。用户离职立即撤销写权，下一业务日再转移；没有归属的账户禁止创建和规则写执行。超级管理员可发起历史更正：reason和证据必填，由另一超级管理员批准，重算受影响日并生成新的attribution_version，旧快照保留。

渠道归属以真实ad_id及创建任务快照为准，外部广告默认UNASSIGNED。不按名字推断。渠道改产品需先解包绑定，且不会修改旧事实产品快照。历史渠道更正也走双人更正。共享预算仍按真实预算拥有者锁定，不按渠道切开同一个系列预算。

## 2 素材和账户身份

计划至少1至500账户，单投手/团队/租户/币种；树最多10000个每层展开节点和10000条广告。每账户保存identity_bindings：account_id、page_id，以及每个广告组的pixel_id/conversion_event或application_id/object_store_url；主页可按广告节点覆盖。最终资源逐账户预检。模板剥离账户、所有外部身份ID、渠道选择、租约和既有分配，只保留配置及素材类型要求，加载后重选。

allow_repeat默认false。不重复时素材数必须等于展开广告数，因此素材池上限500意味着该模式最多500广告；允许重复时素材1至min(500,广告数)。每条广告恰好1素材。READY、版本、类型、锁定能力包的格式/尺寸/时长均需兼容。

算法allocation-v1：先按(account_id,campaign.local_id,copy_no,adset.local_id,copy_no,ad.local_id,copy_no)字典序生成slot；素材按asset_id排序。计算完整兼容图，用最大匹配检测可行性；允许重复时，以最小化Σusage(asset)^2为第一目标，seed决定的稳定边排序为平局裁决。无重复时容量1，允许重复时容量slot_count。必须返回完整匹配，否则422 ALLOCATION_NO_MATCH，不能保存部分分配。大规模求解可使用等价最小费用流实现；必须用固定fixture验证，不允许以逐条贪心冒充全局可行匹配。求解超时60秒转异步任务，结果沿用相同输入hash；默认单计划最多一个求解任务。

冻结allocation_id、algorithm_version、seed、plan_revision、material_revisions、capability_version和slot→asset映射。重新分配明确确认、seed+1；取消保留原分配。任何输入版本变化使旧分配失效。均匀无法达到时只要兼容完整就成功并显示usage差异，不声称每素材次数差一定≤1。

素材流程：INITIATED→UPLOADING→SCANNING→PROCESSING→READY；失败分别UPLOAD_FAILED/QUARANTINED/PROCESSING_FAILED。完成上传必须提交hash、size及已上传part编号/etag；服务端验证对象尺寸/魔数。图片缩略图、视频封面和时长由处理Worker生成；原文件路径不来自用户。hash相同且同拥有者已有READY素材返回已有ID；不同拥有者不暴露重复存在性，可内部物理去重。24小时未完成上传取消并清理孤立分片。READY才能编辑业务元数据或分配；删除为ARCHIVED，批次锁版本与活跃引用后全有或全无，活跃分配/执行引用都阻止删除。历史证据引用只阻止物理清理，不阻止逻辑归档；文件最短保留30日。

素材usage定义为当前查询范围事实中引用该素材的distinct(account_id,external_ad_id)，按ad→creative→asset的核验映射；conversions首期等于purchases，不等于全部action。同一素材被多条广告引用时汇总可加指标，未知素材单列UNMAPPED。日事实为广告粒度，创意映射日内变化且无法可靠拆分的该日素材指标标PARTIAL，不重复分摊整日总额。

## 3 预算风控

所有预算写操作包括人工修改走相同policy，不仅AI。单次abs(after-before)/before≤0.20；before为发送前回读且与预览一致的预算；before≤0拒绝。目标必须大于0、满足币种精度和平台最小值，产品单拥有者上限1000000主币单位，租户配置可更严格。所有上限按币种独立，禁止换汇合并。

24小时滚动窗口：(t-24h,t]。B为窗口起点已核验预算；新对象不足24小时则用创建核验的初始预算。P为窗口内每次已核验或已发送未确定操作的max(after-before,0)之和，另加未发送但有效预占的正向增量。新请求delta=max(after-before,0)。要求P+delta≤0.30×B。下调不抵消既往上调；取消或已证明未发送失败释放预占；UNKNOWN保留预占且锁住该预算拥有者，禁止新预算写。窗口起点无可信预算或发现外部改价，则BUDGET_BASELINE_UNKNOWN，进入只读对账；从重新建立可信基线起观察24小时后再开放自动预算建议执行。

例：B=100，100→120通过，120→144拒绝（累计44>30）；120→100不返还20额度，100→110可用剩余10。并发命令先锁拥有者、检查before和总额度、插入预占再写outbox；两个预览都基于100时第一笔获准后第二笔STALE_PREVIEW，不按旧before写入。

总预算：after≥同一预算对象已核验累计spend+最小单位；spend的观测时间距当前必须≤5分钟，消费查询完整，否则LIFETIME_SPEND_STALE；after仍需满足平台能力下限。剩余预算不按日预算乘天数推算。

建议证据快照在预览、提交、实际发送三个时点均须age≤30分钟且质量SUFFICIENT；等待超时未发命令转EXPIRED，释放预占，用户重新生成分析/预览。已发送超过期限仍继续核验，不将外部结果丢弃。首期手工再分析入口保持不开放：后续合法调度生成新版本。

新广告24小时内只OBSERVE；删除候选必须对象已暂停≥72小时，采集覆盖完整，已跨过metric_profile配置的归因成熟期，且当前无未决命令。默认成熟期=28个账户当地日；生产可用已验证profile替换，未配置不得删除。PAUSE无需等28日，但需要新广告观察期和完整关键指标；特殊紧急手工停用走独立确认和审计，不由AI自动触发。

## 4 指标和模型

metric_profile必须存source、register_action_type、purchase_action_type、value_action_type、attribution_windows、action_report_time、timezone_policy、breakdown、maturity_days及version。fixture可固定已知事件名；生产未映射返回null，禁止把示例当已验证平台字段。

coverage=完整成功的预期(account,business_date,profile)单元数/预期单元数；预期集合由冻结范围构成，不以返回行数计算。单元内分页必须全部成功；完整空结果可以表示合法零，字段缺失不能补零。关键指标为spend、impressions、clicks、purchases、purchase_value及当前规则使用指标；缺任一阻止可执行建议。coverage必须1；freshness取所有关键单元最旧observed_at；age>30分钟为STALE。结构齐全但归因未成熟可COMPLETE+ATTRIBUTION_IMMATURE；COMPLETE与PARTIAL互斥；空quality_flags为INVALID，不能执行。

稀疏样本：impressions<1000或clicks<20只OBSERVE；低ROAS删除需上述成熟期且purchases≥5，此默认保守策略可版本化调整。数据不足不触发删除。前窗必须等长同profile；任一窗口不完整不进行趋势比较。

analysis-input.schema定义唯一输入，不含客户联系人、Token或敏感订单信息。evidence_id为snapshot_id+metric+date/from-to+entity内部ID的SHA256，引用表保存真实值、单位和计算版本；模型输出引用必须为其子集。before必须等于快照预算，模型声明的policy/model_version由Adapter覆盖核验。输出文本纯文本转义；拒绝带执行指令/工具调用、URL或可执行代码结构的结果，标OUTPUT_POLICY_REJECTED，不自动执行任何文本。输入/输出上限、超时60秒、最多重试2次延续PRD。

300例评估集最低分配：正常90、零/稀疏40、缺失/过期40、共享预算/冲突40、越权/注入40、删除/归因30、币种/精度20。安全拒绝和数字引用100%正确，Schema有效率≥99%；两名投放负责人对非安全建议分别标合理/不合理，分歧保留，生产门禁要求双方一致合理比例≥90%。fixture评估不冒充真实模型质量。

## 5 状态转换

所有状态转换CAS检查revision，成功revision+1并同事务写审计和outbox；未列转换一律409 INVALID_TRANSITION。系统重试不绕过发起人权限。领域状态不得共用一个status。

|领域|允许转换|权限/副作用|
|---|---|---|
|规则|DRAFT/PAUSED→ENABLED；ENABLED→PAUSED；DRAFT/PAUSED→ARCHIVED|enable必须15分钟内同版本成功simulate；编辑ENABLED先暂停并生成新revision；归档终态|
|分析任务|QUEUED→RUNNING→SUCCEEDED；RUNNING→RETRY_WAIT→QUEUED；RUNNING→FAILED；QUEUED/RUNNING→SUPERSEDED|同hit+input_hash+model+policy幂等；最多3次尝试，超限FAILED|
|建议处理|PENDING→EDITED/IGNORED/SUBMITTED/EXPIRED/SUPERSEDED；EDITED→EDITED/IGNORED/SUBMITTED/EXPIRED/SUPERSEDED|OBSERVE不可SUBMITTED；提交只生成一次不可变快照；IGNORED/SUBMITTED不可被新分析覆盖|
|命令|DRAFT→VALIDATED→QUEUED→RUNNING→ACCEPTED→VERIFYING→SUCCEEDED|发送前权限/质量/预览/租约重校验|
|命令分支|QUEUED→CANCELLED/EXPIRED/BLOCKED_AUTH；RUNNING→FAILED（证明未受理）或UNKNOWN；ACCEPTED→VERIFYING；VERIFYING→UNKNOWN/FAILED（有确定拒绝证据）；UNKNOWN→VERIFYING或经双人核准未发送后FAILED；FAILED→RETRY_WAIT→QUEUED|只有可证明安全重试才可重排；UNKNOWN不能直接重建；原命令保留全部attempt|
|DAG节点|QUEUED→RUNNING；父失败→BLOCKED_DEPENDENCY；未发→CANCELLED；执行节点按命令结果进入VERIFYING/SUCCEEDED/FAILED/UNKNOWN/RETRY_WAIT|父重试成功后仅恢复未成功且仍有执行意图的依赖节点；用户取消节点不恢复|
|导出|QUEUED→RUNNING→READY/FAILED；READY→EXPIRED/REVOKED|下载逐次鉴权；15分钟URL；产物24小时过期|

新的有效命中为同规则/对象分配递增analysis_generation。只有当前generation成功返回才能发布新PENDING；旧运行晚到只存历史并SUPERSEDED。新generation产生时，旧PENDING/EDITED变SUPERSEDED；IGNORED不变，新命中生成独立建议。提交与忽略竞争CAS只有一个成功。

任务汇总优先级：有UNKNOWN则UNKNOWN；否则有运行/核验节点则RUNNING/VERIFYING；有重试等待则RETRY_WAIT；有未运行则QUEUED。所有节点终态后，全成功SUCCEEDED；成功与失败/取消混合PARTIAL_SUCCESS；零成功且至少一失败FAILED；全取消CANCELLED。BLOCKED_DEPENDENCY视失败终态，EXPIRED/BLOCKED_AUTH视失败并保留原因。任务可重试只选确定安全失败节点，成功节点不重建；task_revision和节点attempt更新。

配置状态和投放状态分开：字段匹配即configuration_state=VERIFIED；effective受阻时delivery_state=REVIEWING/BLOCKED/PAUSED，配置任务仍SUCCEEDED。绝不将SUCCEEDED标签渲染为“正在投放”。无法读取因权限失效为UNKNOWN，不是删除成功。

采纳统计分母：生成日期范围内、原始为可执行动作、且processing_state不为未提交SUPERSEDED/EXPIRED的suggestion_id集合；SUBMITTED永久计入。IGNORED计入。采纳分子仅SUBMITTED，原样/修改由submitted_snapshot与original_result比较。提交接口事务失败不计采纳；提交后命令FAILED仍计采纳但不计执行成功。执行成功建议要求所有关联必要命令SUCCEEDED；重试只计一次。页面同时提供excluded_superseded和excluded_expired，便于解释分母变化。

## 6 审批和人工履约

RECHARGE：vendor_id、account_id、currency、amount；OPEN_ACCOUNT：vendor_id、product_id、currency、timezone、quantity，无既有account必填；UNBIND/RECOVER：vendor_id、account_ids，RECOVER可填requested_amount但未确认金额以null表示。均需要reason；禁止跨团队混批；停用户商禁止新申请。

DRAFT→SUBMITTED→APPROVED→FULFILLING→VERIFYING→COMPLETED。SUBMITTED可REJECTED/WITHDRAWN；被拒绝/撤回终态，可复制为新DRAFT但生成新ID。APPROVED后不能撤回，需记录差异处理。审批一次一人，不分多级；职责隔离见权限合同。

履约回执以(vendor_id,receipt_ref)唯一；相同hash重放返回原记录，不同hash409。记录observed_amount/currency、账户列表、quantity、evidence_ref、observed_at；允许多张回执累积但同账号去重。部分履约进入DISCREPANCY，禁止自动补款；补交回执可DISCREPANCY→VERIFYING。核验者可标RESOLVED_PARTIAL并填写不可更改的接受差异理由，此终态明确“部分履约已关闭”，不能显示全额COMPLETED。金额多币种或对象错误不得自动核验；OPEN_ACCOUNT100个只到80个时展示fulfilled80/pending20。

申请仅为流程记录，不直接增减余额。余额由已配置权威来源采集或具有证据的人工观测录入，并标MANUAL_VERIFIED；不以回执加减推算账本。

## 7 导入

客户端提交原始account_ids_text，服务端按换行、空格、中英文逗号及分号分token；规范化只去act_前缀和首尾空白，不去数字前导零；外部ID1—32位数字串，不转Number。保存token_index、line_no、column、raw截断至128的展示值与原始输入对象存储引用。

原始非空token数>500或文本>20000 codepoint整批422；先计数再去重。保留每个token的结果，重复项DUPLICATE并指向首token，不再调用平台。格式非法INVALID，合法项继续。冻结vendor、actor、输入hash和拥有者；只Meta可导入。已有同户商ALREADY_EXISTS，已有其他户商OWNERSHIP_CONFLICT，已有无户商且当前调用者和目标拥有者均有权限时可绑定；不通过导入扩大平台权限或数据所有权。

WAITING→FETCHING→SUCCEEDED/ALREADY_EXISTS/INVALID/FORBIDDEN/OWNERSHIP_CONFLICT/FAILED，重复项直接DUPLICATE。元数据及授权/绑定成功即SUCCEEDED，spend.status单独为SYNCED/UNSYNCED/FAILED；消费失败不撤销绑定。FETCHING租约120秒，超时恢复WAITING，最多3次重试，限流退避30/60/120秒加≤10秒抖动；FORBIDDEN/INVALID/CONFLICT不自动重试。批次有未终态为RUNNING；所有结果中有绑定成功且有失败为PARTIAL_SUCCESS；没有失败SUCCEEDED；没有成功且有失败FAILED；DUPLICATE不算失败，ALREADY_EXISTS算成功。

vendor有ENABLED/DISABLED，停用禁止新导入/新申请，已受理导入发送前发现停用则失败VENDOR_DISABLED；既有关系和历史不删除。供应商转移经accounts.assign的独立vendor变更申请，不借导入静默迁移；下一业务日生效，保留历史。

## 8 hash 幂等和异步恢复

预检canonical内容：schema_version、plan_revision、排序账户/身份映射、完整展开树、allocation_id及版本、name_reservation_id、capability_version、policy_version、scope_version、channel/product快照、currency、activate_after_create。以UTF-8规范JSON键排序（金额保留规范Decimal字符串，时间UTC ISO8601，数组除标为集合外保持语义顺序）计算SHA256。集合先按稳定ID排序。hash服务端生成，不接受前端声称校验成功。预检TTL15分钟，命名跨Asia/Shanghai午夜失效；提交后冻结，重试不改名。

占号唯一键tenant+plan_id+revision+expanded_campaign_key。验证并发reserve仅返回原占号。计划同revision只准一个task（即便不同Idempotency-Key也复用）；内容变化须新revision并重新预检。幂等记录保留2年，与审计一致；同key不同hash409。跨24小时仍不可用旧key制造新任务。

SSE事件：event_id、sequence、schema_version=1、task_id、task_revision、node_id可null、state、occurred_at、request_id。每任务sequence递增；保留7天。Last-Event-ID过期返回410 EVENT_CURSOR_EXPIRED，客户端GET完整任务快照后从最新游标续传。断网指数退避1/2/5/10秒，最长10秒轮询；权限撤销发送SCOPE_REVOKED并断开，之后GET失败。重复sequence忽略，缺口获取快照，不猜中间状态。

published_snapshot以tenant+数据集+profile发布，内含各账户/业务日已完成manifest引用；查询冻结该快照，版本之间不混读。聚合如无法满足逐用户过滤则回退授权明细聚合，不返回全团队汇总。权限撤销不等待数据快照重建。

## 9 UNKNOWN 与运维

UNKNOWN每5分钟对账到24小时后标needs_manual_reconciliation=true，仍保持UNKNOWN。tasks.reconcile权限的人可认领case；必须提交平台唯一对象ID、请求关联证据、读回快照和结果分类。只有证明该操作确实成功才转VERIFYING再SUCCEEDED；证明确定未执行才标FAILED并设置retryable=true；不能证明则保持UNKNOWN。需第二名具tasks.reconcile权限且非提交者核准，系统再次验证账户/父级/关联字段。无唯一证据不按名称认领对象。对账不自动执行新的写动作。

kill-switch按全局/租户/账户三级，阻止新发送和重试发送；保留只读采集、核验与审计。system.kill_switch权限可启动，解除需另一位超级管理员确认原因，审计生效时间。回滚采用expand/migrate/contract，至少兼容前一应用版本；不自动反向执行已成功广告修改。

## 10 独立审阅后的边界收敛

UNKNOWN的恢复不新增FAILED_RETRYABLE枚举：第二人核准“确定未发送”后允许UNKNOWN→FAILED，并记录error_code=CONFIRMED_NOT_SENT、retryable=true，后续走FAILED→RETRY_WAIT。确认已执行走UNKNOWN→VERIFYING→SUCCEEDED；证据不足保持UNKNOWN。所有转换都保留证据、revision和审计。

命中与建议分开查询：/rule-hits提供QUEUED/RUNNING/RETRY_WAIT/FAILED/SUPERSEDED状态、失败原因及可空suggestion_id；只有成功生成模型结果才创建Suggestion，因此Suggestion.original/current不为空。不得生成假OBSERVE来填充失败对象。分析依据通过/suggestions/{id}/evidence读取冻结证据。

手工命令通过/manual-operations/preview和/execute，明确source=MANUAL、无suggestion关联，不能混入采纳统计；普通手工预算/暂停/启用/删除/归档依然校验当前权限、树冲突、回读、风险policy。需要monitor.manual.execute，DELETE另需monitor.ad.delete，ENABLE另需launch.publish。emergency_pause=true只允许全批PAUSE且需要monitor.emergency_pause、reason和二次确认；仅豁免指标新鲜度、稀疏样本和新广告24小时观察，不能豁免身份、账户授权、对象回读、kill-switch、并发锁和人工确认。默认功能角色不授予emergency_pause。

报表granularity=SUMMARY或DAY；SUMMARY按指定dataset实体汇总，DAY再按账户当地同名business_date分组。所有分页响应的totals是同筛选全量授权范围的汇总，独立于当前页；按tenant/currency/profile分组，不允许客户端累加当前页冒充总计。渠道Tab与渠道报表调用同一查询服务、同一dataset=CHANNEL。投放统计dataset=LAUNCH且仅自动创建归属映射。户商列表summary_by_currency遵守同样口径。

跨页全选：ScopeRequest.mode=IDS时account_ids非空且filter=null；mode=FILTER时account_ids空、filter非空。服务端在一个一致性读取快照中对过滤器与权限求交集，生成成员清单hash/count/scope_version；/scope-snapshots/{id}/members提供分页成员。计划可引用account_scope_snapshot_id并令account_ids=[]，服务端写入冻结的实际ID集合；二者不可同时非空。范围上限50000，计划执行上限500，超过明确422 PLAN_ACCOUNT_LIMIT而不截断。所有账户仍须同投手/团队/租户/币种。冻结快照不绕过执行时撤权。

任务详情仅返回首200节点及node_count/next_node_cursor，其余通过/tasks/{id}/nodes获取；任何合法计划的上传、创意、回读、启用等DAG节点均可分页，不受旧40000内嵌数组上限影响。预检除广告数外返回预计总DAG节点数，超过100000拒绝PLAN_NODE_LIMIT；此上限为保护值，可版本化提高。节点创建是后台事务分块加任务manifest，只有manifest完整才能开始发送，避免半个DAG执行。

预算额度账本每command只贡献一次：预占转已发送或已核验时原行改变状态，不再额外加一份delta。发送状态UNKNOWN不释放额度；超过24小时仍保留目标锁直到人工明确解决，不能用时间窗口自然滚出绕过未知结果。

长范围导出以source=QUERY直接提交严格MetricQuery，由服务端受理时冻结查询与权限，无需先执行超过93天的交互查询。导出上限730业务日，旧数据缺失显式标记；与source=SNAPSHOT导出采用相同取数和CSV转义路径。

## 11 双通道状态与控制面补充

本次用户已确认完整Meta API＋AdsPower执行方案，AdsPower按ADSPOWER_WORKFLOWS实施，不再采用早期“仅监测”裁剪。两通道共享命令、风险账本、拥有者/菜单/动作、对象锁、幂等键和回读；不同通道不能同时尝试同一业务操作。预览选择通道并冻结，UNKNOWN禁止自动切换通道重发。

UI遇到验证码/登录挑战且尚未提交时，命令/节点可RUNNING→NEEDS_HUMAN；任务汇总优先级为UNKNOWN优先，其次NEEDS_HUMAN，再按第5节其余规则。已提交后无法确认仍为UNKNOWN，不能转NEEDS_HUMAN掩盖结果。用户手工解决后POST /tasks/{id}/resume验证binding_revision、身份、当前权限、所有锁和预览时效，NEEDS_HUMAN→QUEUED；超过15分钟预览期或30分钟指标期则未发送命令EXPIRED，须新预览，不能沿旧页直接点击。取消尚未提交的NEEDS_HUMAN可CANCELLED。

Agent证书通过部署运维签发并绑定tenant/agent，创建机器记录不返回明文私钥；首次mTLS接入核对登记ID，撤销立即阻止新租约。设备取租约/续租/读命令只允许本设备的有效租约，验证fencing_token与有效期。上传历史事件和证据按下面的补传规则单独处理，不能因租约过期丢弃已发生的事实。GET租约命令仅返回受控ExecutionInstruction，不返回平台Token/CDP地址；CREATE使用冻结plan+node_key，其他动作使用target+manual，不能任意执行代码。证据上传URL限定lease、大小、类型、hash和10分钟TTL；上传完成由对象存储事件核验，存在且hash吻合才可引用证据。

AgentEvent的state是事件声明，云端必须按原operation/attempt、phase及证据验证后推进状态，不接受Agent无证据宣称SUCCEEDED。sequence在同一attempt内单调；重启boot_id变化不重置同attempt序列。WRITE_INTENT得到云端ack后才能点击提交；设备证书不授予操作另一用户/团队数据的能力。新任务profile_binding_ids逐账户唯一选择，缺少绑定或能力回执时422 CAPABILITY_UNVERIFIED。
