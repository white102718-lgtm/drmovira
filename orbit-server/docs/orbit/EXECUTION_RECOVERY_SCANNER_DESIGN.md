# 既有过期执行代际恢复扫描入口（首阶段内部实现，真实待验）

当前仅新增 `launch_execution_recovery_scanner.py` 与同名专属纯测，未改已冻结046/050/052源码、应用/CLI/Worker或正式迁移。`ExecutionRecoveryScanner(authority_provider=None,sessions_factory=None,*,clock=None,monotonic=None).scan_once(*,max_candidates=100,max_raw_rows=1000,time_budget_seconds=10)` 已实现；51/51专属纯测通过（0.71秒），Ruff通过，尚无新真实SQL/容量验收。

可信provider为抽象 `RecoveryScanAuthorityProvider.capture/current/authority`，当前没有生产实现。其 `MaintenanceScanGrant` 精确绑定grant/principal UUID、原生actor、服务端有序唯一tenant范围、RECOVER_EXPIRED动作、revision和UTC expiry；每批及每个候选事务前当前复核，任何版本/范围/主体改变均终止。没有接受请求租户列表或布尔“已授权”的入口。

扫描器仅通过lazy sessions_factory在真实provider+当前grant通过后初始化数据库；缺provider、过期或当前来源漂移均先拒绝。三桶原始keyset每页≤200，再一次集合读取本页完整attempt/runtime/command/node提示；每个候选另开新事务，由原Store锁读最终授权和五代际。进度只在已提交/明确stale/blocked/filtered后前移，未处理余页重新读取；按tenant和桶轮转，重启重读不能制造新执行尝试。正常不适用的旧UNKNOWN是filtered，缺/坏绑定或真实来源不可验证为blocked，两者都不算恢复成功。

原始扫描行预算≤10000、每轮尝试≤200、单次总时限≤60秒是服务内部技术边界，不是新增业务接口限制。耗时内未开始下一项时返回budget_exhausted；在途达到硬deadline则TimeoutError向外传播，等待原事务上下文回滚，不返回假“已完成”。取消同样传播且无shield遗留任务；request_stop只停止新领取并等待当前事务。SQL时钟早于已冻结cutoff立即拒绝，不能用未来水位继续扫描。

候选 `docs/orbit/sql-drafts/054_execution_recovery_scan_indexes.sql` 只含三条建议索引，主线尚未正式采用/实际EXPLAIN。以下设计历史中的“建议入口”现已有上述限定内部实现；生产主体签发、事实authority、公共注入、调度/CLI、真实扫描多Worker与容量仍未完成。

## 已有边界与原合同

052单次恢复提交已实际40/40通过；默认authority仍缺失且没有生产调度注册。下一阶段只选择已持久的原attempt/runtime，调用既有受控恢复Store，不领取广告命令、不创建执行attempt、不发送、不重试排队、不释放预算/对象锁，也不实现实际平台核验。

依据 `data/ORBIT_Codex开发PRD/contracts/WORKFLOWS.md`：59行CAS/同事务audit+outbox、系统重试不绕过发起人权限；66—68行原命令与DAG分支；73行全任务聚合；105行九字段SSE/七日保留；111行UNKNOWN每五分钟只读对账至24h人工且原tasks.reconcile双人核准；113行三级kill-switch保留核验/审计；117行UNKNOWN不能自动FAILED；129行UNKNOWN超过24h继续保留预算/目标锁；139行租约过期不丢已发生事实。权限合同36/38行原launch动作与tasks.read/cancel/retry/reconcile，无“恢复扫描即可发送”的动作。

teamai-recall本轮实际检索未命中ORBIT恢复/撤权核验约定；唯一命中AdPulse账户限额通知窗口文档，经读正文不适用于持久执行恢复。不能套用其允许漏报的时间窗口或删除游标建议。

## 推荐首个可交付闭环与新文件所有权

建议第一阶段独立 `launch_execution_recovery_scanner.py`，导出 `ExecutionRecoveryScanner(authority_provider=None, sessions=None, allowed_tenants=...)`，`scan_once(*, max_candidates, deadline)` 返回纯安全计数；authority缺失或可信服务主体未配置先拒绝，尚未初始化DB/候选扫描。新纯测文件与独立真实工具后续由主线分配。入口不挂API lifespan，不以每个API worker自动启动，不提供HTTP“模拟恢复”端点。

候选内部DTO只包含tenant/task/node、原attempt完整绑定与expected五项，不能含发送令牌、可执行脚本或对象存储路径。候选是当前锁读前的提示；单条必须新session+外层事务调用 `ExecutionRecoveryStore.recover_expired`，在原Task clock→Task→preparation→command/node/runtime→attempt顺序重新核全部来源/事实。不能把一批候选放同一个大事务，也不能先锁扫描索引/维护游标再倒序取得Task锁。

第二阶段才考虑独立CLI `tools/run_execution_recovery.py` 与 `launch_execution_recovery_service.py`，显式once/serve、单进程互斥、受控周期/退出码/每轮预算、signal停止领取与排空在途事务。仅指定private_values读取口ORBIT命名空间；无任意DSN/租户列表/平台Token命令行参数。配置与公共注册由主线分配，当前不改env、应用入口或旧Worker。

## 权限撤回后的恢复主体：必须先裁决生产可信来源

不能把原广告发起人撤权解释成允许另一个管理员接手发送；也不能把任务原actor_id或原authority_hash当当前维护权限。当前 `ExecutionLeaseAuthority` 是严格抽象协议，生产实现仍缺失。SQL技术实现仅UUID/13306，绝不导入正式扫描器。

建议生产接入显式独立、受控的恢复维护主体及证据Authority，由服务器运维可信配置/注册签发、绑定允许tenant、主体原生ID、来源issuer/revision/expiry及操作RECOVER_EXPIRED；当前主体必须真实启用、源证明和范围当前有效，失效停扫描。不能凭字符串TRUSTED、数据库STARTED状态、M2/M3观察收据或当前用户tasks.read自动授予维护写能力。实际来源证明必须逐事实验证原transport/设备身份与immutable command绑定，外部I/O在事务外捕获，事务内只复验数据库/已验证来源快照。

该维护权只允许保守分类/原核验状态推进与审计，不能授广告launch.execute或tasks.retry。冻结原owner/actor/授权版本依然在attempt原绑定中，audit_actor可为明确维护主体，不能改原任务拥有者。原发起人已撤权时，仍可受控保留历史事实、将失联结果保守UNKNOWN、继续独立只读核验；FAILED.retryable只是证据上的安全分类，不意味着发起人现在有权重发。任何后续发送仍需原业务当前写权限、kill-switch/来源/预算/对象锁完整复验。

**待主线确认的生产授权缺口：**原权限表没有后台恢复服务主体签发/撤销的具体持久来源合同。不能自行新增一个菜单权限或使用超级管理员隐式绕过。建议先实现可注入生产协议与default-unavailable扫描器，真实专项仍明确技术主体；正式authority与主体注册由主线单独分配。若只允许沿原发起人当前launch.execute恢复，撤权后的任务只能阻断等待独立授权维护主体，不能假称该场景已覆盖。

## 候选分类与有界分页

先只扫描明确allowed_tenants；租户来源必须服务端可信注册，不能从请求或运行库中无界枚举所有tenant。每轮按租户轮转公平调度，冻结本轮SQL UTC cutoff；每桶每页最多200条原始行，完整记录“扫描行数”与“真正可恢复数”，先取原始有界keyset再集合读取状态/绑定。不能在JOIN状态过滤后仅LIMIT200，实际扫描百万旧UNKNOWN行却宣称有界。

三桶分开：

1. **原租约过期**：runtime active_attempt非空、lease_expires_at非空且≤cutoff，按 `(lease_expires_at,task_id,node_id)` 键集；本页集合取当前command，只有RUNNING/VERIFYING进入恢复。原UNKNOWN保存的旧lease仍会落在原始扫描范围，必须推进原始水位，不重复卡首行。
2. **已受理待核验**：command state=ACCEPTED，按 `(task_id,node_id)` 键集，再集合取runtime完整expected与原attempt；不要求租约已经过期，因为原ACCEPTED必须进入VERIFYING。这是内部恢复，不凭ACK直接SUCCEEDED。
3. **UNKNOWN人工到期**：runtime unknown_since≤cutoff−24h、needs_manual=false，按 `(unknown_since,task_id,node_id)` 键集，当前command必须UNKNOWN；只登记原manual事件/标志。五分钟对账不是此扫描器的I/O：不调用平台、不写last_reconciled_at、不增加TaskNode.attempt。实际只读核验领取仍应使用独立047 reconciliation_generation方案，不能复用广告fence。

每批候选必须一次集合读完整attempt绑定，缺行/坏来源拒绝而非给默认值。首版扫描游标只作为进程内扫描进度，重启从头可重复安全恢复；每轮到cutoff有限末端后开启新轮，候选在扫描期间移动/新增会在下轮再发现，不能用发生时间窗口永久丢弃。每轮候选数与耗时预算耗尽保留下一页位置，不静默丢未处理页；不把此进度当广告业务幂等键。

来源未配置/全局故障停止本轮；单项预期CAS冲突可计为stale并继续；无法验证的证据返回blocked，保留原状态，不伪造恢复成功。暂停/重启不解除任何原锁。针对持续坏行的公平性和全量一轮耗时必须真实压测；不能宣称五分钟核验SLA已完成。本阶段不得为了规避旧UNKNOWN扫描成本清空原lease字段或改046含义。

## 最小DDL建议（仅索引，编号待主线分配）

既有runtime索引以expiry或next_reconcile_at开头，对明确tenant扫描可能大量跨tenant过滤；原command无tenant+state候选索引。建议一个新迁移只追加三条索引，不改046/052历史表或新增状态：

- runtime `(tenant_id,lease_expires_at,task_id,node_id)`：租户内过期原始keyset；
- command `(tenant_id,state,task_id,node_id)`：原ACCEPTED候选；
- runtime `(tenant_id,needs_manual_reconciliation,unknown_since,task_id,node_id)`：24h人工到期原始keyset。

索引须实际EXPLAIN/rows与10万+混合旧UNKNOWN数据测扫描上界；第一桶仍会逐页访问旧UNKNOWN，不应仅有索引就标大容量通过。如果真实容量证明循环无法达到目标，需要另设计同事务维护的私有due目录（不是广告队列）；不得现在先建一套没有所有原写方维护的影子状态/租约表。首版无需新恢复lease或持久扫描cursor，避免额外错配来源。

## 多Worker、取消与错误恢复

推荐先单服务进程+单run_once，明确生命周期锁，不部署时自动开启。多个服务实例以后可读取同一候选，但不能SKIP LOCKED抢Task或创建新执行claim；原expected五项及052唯一after-runtime-revision负责精确单次提交。第二个恢复者等待Task锁后409 stale，不能catch后重抓新expected继续改同一业务意图。不同tenant可并行，单tenant仍受原taskclock串行；本轮不改全局锁序以追吞吐。

如确需扫描任务分片，只能可信tenant分片配置，或另分配独立维护租约/代际；绝不挪广告attempt/fencing_token，也不占047核验代际。候选读取事务结束后再开启恢复事务，避免索引/游标锁→Task反向锁。取消/停止先停候选领取，再等待当前原事务提交/回滚，超时不谎称已清理；不可在未知事务结果后立刻重发或重建广告。

## 后续可验证闭环与明确未完成项

纯测：默认无authority零SQL、tenant白名单、桶分离/分页原始水位、旧UNKNOWN不堵塞首行、批量expected不可截断、预算停止后续页、一个在途调用、停止/异常/取消不继续领取、撤权主体与历史事实身份边界。

主线真实SQL专项：所有三桶实际索引计划及稳定keyset；大量非候选夹杂后仍遍历且不丢后页；当前expected变化只一次CAS；两个扫描者不能重复事件或递增attempt；原Task/节点/SSE与052同事务；维护主体失效/证据不足仍failclosed；kill-switch打开不导致新发送；停止后无遗留在途事务。全程技术fixture无平台写。

正式Authority来源、源证据接入、维护主体注册/撤销、生产服务注入、实际平台只读核验与047、真正容量/运行SLA均未完成。不能将052的40/40局部结果或新扫描器空跑当成这些功能完成。


## 本轮纯测范围与真实待验

51项专属纯测仅验证维护grant的严格主体/范围/action/revision/expiry、无来源零DB初始化、三桶有界原始页+集合绑定形状、每条新事务、跨租户轮转、原始页剩余项不丢、旧UNKNOWN过滤不堵首行、已知CAS/来源错误分类、未知故障终止、当前授权漂移、SQL UTC回退/过期、原始预算/单候选预算、停止/取消/硬超时后原事务退出及无背景任务。事务和SQL返回均为明确pure夹具，不证明真实查询锁、索引计划、数据库提交或正式平台来源。

后续最小真实工具应由主线分配：通过原202完整受理来源+技术runtime产生三桶，注入明确本轮technical maintenance provider与真实事实authority，执行当前scanner→原052；断言raw游标/上限、实际新事务/唯一CAS/九字段SSE、054 EXPLAIN、被撤维护主体阻断与原锁/广告attempt不变。零平台调用；正式issuer不能用该fixture补齐。


## 新普通真实工具检查点（已冻结，尚待主线执行）

新增 `tools/launch_execution_recovery_scanner_checks.py`，导出 `SCANNER_CASES` 固定10组，七参 `run_execution_recovery_scanner_checks(client,admin,headers,password,cache,database,cases)`。主线独立档为初始化6+专项10，共16，当前尚未反馈真实结果。51项scanner纯测与13项工具护栏共64/64通过1.13秒，Ruff/format通过；生产源码与工具冻结。

普通混合样本通过原真实validate200/execute202生成多个完整Task，再SQL构造明确技术runtime/旧UNKNOWN，直到旧UNKNOWN至少401条；完整Task数量与实际行数由真实运行metrics记录，不预称十万容量或生产事故。没有伪造039半manifest、绕过原受理或授予平台写能力。技术provider只显式工具注入，核UUID/13306与服务主体范围；不是生产issuer。

10组包括默认DB初始化前拒绝、原完整202来源、跨200+200旧UNKNOWN原始页达到后方候选、三桶/当前授权漂移、候选预算不丢余页、两个真实scanner同一expected仅一CAS、outbox1644数据与目标进度不前进、维护来源撤销中断下一项、实际Taskclock等待后取消/timeout事务退出、三条索引中文COMMENT及EXPLAIN。

EXPLAIN同时返回未强制与FORCE INDEX计划，后者单独标记forced=true，仅证明指定索引可服务该查询，不冒充优化器自然选择或实际容量。取消/timeout使用实际performance_schema确认等待关系，只取消本轮精确asyncio Task并等待事务上下文退出，再有界确认该锁等待消失；不是以sleep或仅本地done标记假定MySQL已清理。任何失败保留原断言与主线证据，不自动跳过。


## 实际取消缺口与独占连接修复提案（待主线确认）

主线第四档已实际通过三桶、预算、双scanner、1644、维护来源撤销，13通过/1失败/2未运行；证据 `python-execution-recovery-scanner054-cancel-first-failed.json`。真实P_S在客户端Task取消后仍有被自有holder阻塞的服务端等待，2秒原断言失败。不能把Task.done或SQLAlchemy session上下文退出等同MySQL已结束，不延长断言，不释放holder或KILL其他连接冒充清理。

已只在工具加入受控诊断，输出原等待的数值连接/THREAD身份、command/state类别、WAITING状态、耗时及session innodb_lock_wait_timeout；不查询或输出PROCESSLIST_INFO、SQL/参数、对象ID、地址和env。25项tool纯测与Ruff通过，当前生产scanner未改。

本地SQLAlchemy asyncmy dialect实际实现的连接终止仅为 ensure_closed()/socket close，没有独立服务端KILL QUERY流程。现象可能是阻塞中的MySQL语句尚未感知客户端断开，应由真实新诊断确认对应会话及server timeout；不能只靠猜测宣称根因已修。

建议每条恢复使用精确owned AsyncConnection，先读原SESSION innodb_lock_wait_timeout与CONNECTION_ID，固定设1秒并同连接绑定AsyncSession贯穿业务事务；commit/rollback后在仍持有的同物理连接finally恢复原值并提交。任何reset/CID不确定必须invalidate，不返回污染连接到池；已被取消/invalidated的连接不能为还原变量而偷偷重连。server1205保持真实异常向上终止，不吞成stale/成功。纯测必须覆盖set→txn→reset同CID、取消/rollback/reset失败/invalidate、无池污染；主线实际验证P_S等待与精确自有innodb_trx在原2秒内消失。其1秒server期限不授发送、不重试，也不改变广告租约/业务超时。

## 054 实际专项最终结果（限定通过）

上述独占连接方案现已实现，不再是待实施提案。每条恢复在同一 AsyncConnection 上核对 CID、读取原 SESSION 锁等待值、设为 1 秒、关闭设置阶段 autobegin，再绑定业务 AsyncSession。正常提交或回滚后同 CID 还原并复验；取消后已 invalidated 的连接不执行任何复位查询或重连，不确定清理按失败处理。所有等待均完整 await，无自行遗留的 shield 后台任务。1205 原异常终止当前扫描，当前 hint 不前移。

主线实际 `python-execution-recovery-scanner054-http.json` **16/16 PASS，19.76 秒**，包含初始化 6 组及专项 10 组。实际验证原 202 完整来源、402 条旧 UNKNOWN 的普通分页、三桶与过期 ACCEPTED 的两次决策链、候选预算、两个 scanner 唯一 CAS、1644 整体回滚与水位、来源撤销，以及取消/0.5 秒外层 timeout/独立服务端 1205。取消与 timeout 保持原 2 秒 P_S wait 和精确自有 innodb_trx 退出断言；独占连接正常还原、失效连接丢弃及后续池参数未污染均实际通过。三个索引的自然计划和强制计划分别记录，不能互相替代。

本轮定向纯测 **87/87 PASS，1.10 秒**，Ruff/format 通过。前四个失败现场及诊断证据保留：首轮主线隔离 provider 接线遗漏、三桶工具 fixture 对二次恢复的错误预期，以及真实客户端取消后服务端仍等待的缺口，均不改写为历史通过。本文此前“尚待执行”“生产未改”的段落属于各当时检查点记录，以本节为当前结果。

本次仍是 UUID/13306 隔离技术维护主体及事实 authority，零广告 claim/send、零平台请求，不是正式维护 issuer、实际平台回读或五分钟核验 SLA。没有新建核验代际、释放预算/对象锁或增加广告 attempt；大容量、跨机运维和正式调度生命周期仍待独立交付。
