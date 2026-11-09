# 首次 Worker claim 与任务生命周期设计

本阶段已实现独立首次领取纯合同与状态建议，尚无持久领取。没有新发送者、生产执行 issuer、预算/目标锁默认成功实现、公开路由或正式迁移。058 仅由主线预留给后续 claim 候选方案，本文没有执行 DDL；candidate 的真实专项修复由主线另行排队，不继承为领取验收。

## 1. 原合同及当前缺口

原 `WORKFLOWS.md:66—68,73` 要求命令/节点 QUEUED→RUNNING、完整父依赖与任务聚合，成功节点不能重建，用户取消节点不能复活；101—103/127 行要求原 source 唯一 Task、稳定幂等意图、完整 manifest 后才执行。111/117 行要求 UNKNOWN 只读核验及原双人裁决；113/129/135 行要求三级 kill-switch、未知结果保留预算和目标锁、禁止跨通道重发。

预算规则以 `WORKFLOWS.md:33—43` 为准：既有预算修改的 before 必须发送前回读且匹配预览，20% 单次、30% 滚动、币种精度和可信基线；取消或已证明未发送才释放预占，UNKNOWN 不释放。新对象初始化预算不直接套用 before=0 的修改公式，也不能默认不占风险额度；需共享 policy 对 CREATE 明确输出来源、基线语义、额度和锁键，缺失失败关闭。

`ADSPOWER_WORKFLOWS.md:53—55,83,92,151,157—159` 分别约束准确账户/层级与提交前复核、Profile 租约 120 秒/20 秒续租、WRITE_INTENT 云端确认、预算拥有者锁和绝对目标金额、历史证据补传以及完整冻结清单/有效租约素材下载。设备/worker 身份不是用户权限，M2 观察也不是写 capability。

目前 033/035/036/039 支持真实受理与完整 DAG，046 有 attempt/runtime/fact 表，050/052/054 支持原事实恢复及独立恢复服务。只读候选目录返回 `execution_authorized=False`，没有发送权。`task_routes.py` 现仅原 GET/节点读，取消/重试/resume 的持久控制链尚未实现；共享预算账本、所有通道目标锁、三级开关的权威消费链及真实 worker issuer 同样缺失。账户命令是本人账户动作诊断/导入链，不能按“也叫 command”复用其重试或权限。

团队知识库本次只命中无关 AdPulse 账户限额通知窗口学习，缺少 ORBIT claim/预算/WRITE_INTENT/UNKNOWN 专门约定；不从通知允许漏扫或 Mongo 窗口推导本任务状态与租约。

## 2. 最小可交付拆分

第一步仅 **首次领取合同与纯决策**：明确原 QUEUED/attempt0、当前完整源/父依赖、期望版本和运行绑定、稳定领取请求、禁止发送的结果。纯函数只产生建议，不签发权威证明，不创建数据库记录。

第二步在主线统一共享接口后实现 **durable first claim**：在一个外层事务完成资源预占、稳定请求回执、046 attempt/runtime、节点/命令 RUNNING、Task 聚合、原事件和 audit/outbox。缺正式授权、任一资源证明或完整来源时，在 DB 初始化/领取前 503。实际测试只能用明确 UUID/13306 technical authority，不能据此开放生产。

第三步才是 renew、受控 WRITE_INTENT、transport、ACK/readback、取消/重试/resume 和后台循环；分别交付，不能通过第一笔 RUNNING 就称投放功能完成。当前不发真实广告。无 transport 的领取样本最终停在 RUNNING 或由可信事实进入原恢复链，不伪造 SUCCEEDED。

## 3. 接口稿与权限

```python
class ExecutionClaimAuthority:
    async def capture(self, request) -> ClaimSourceSnapshot: ...
    async def lock_current_sources(self, session, request, snapshot) -> ClaimAuthorityProof: ...
    async def revalidate_locked(self, session, proof) -> ClaimAuthorityProof: ...

class ExecutionResourceCoordinator:
    async def lock_and_reserve(self, session, request, authority_proof) -> ResourceReservationProof: ...

class ExecutionClaimService:
    def __init__(self, authority=None, resources=None, sessions_factory=None): ...
    async def claim(self, request: ClaimRequest) -> ClaimReceipt: ...
```

这些是待主线统一的接口，不是新增的永真实现。authority/resources/正式 issuer 未配置必须先拒绝，不能先创建 Task、连接或预占再返回 unavailable。外部只读观测放 capture；事务内只核当前真实 SQL/已捕获签发证明，禁止网络 I/O。typed proof 绑定确切服务实例、真实 SessionTransaction、worker/grant 版本及过期时间；`verified=True`、哈希自身或继承 ABC 不构成证明。

授权分两层：后台 worker 必须持真实受控实例身份与允许的 tenant/action/mode/account 范围；原接受 Task 的 actor/subject/owner/team 仍须当前启用、原 launch.execute 和资源范围交集有效，ENABLE 另需 launch.publish。不得额外要求原用户 launch.read/tasks.read，也不得借管理员/后台身份替代原操作者。后台运行不依赖仍打开的浏览器 Cookie，但这需要明确后台执行授权契约，不能普通请求随意设置 acting_subject=False 绕门禁。

生产 issuer、生命周期和撤销由主线接线；不自行签发维护 grant 充当执行权限。当前 ClaimReceipt 固定 `transport_eligible=False`，只返回精确绑定/租约/原回执，不给 Token/CDP/任意路径、任意代码或素材库扩大读取权。原公开 execute 仍返回原 202 Task，不改成内部 receipt。

## 4. 源验证、资源与锁序

事务外可预读当前候选与静态资源集合，但不据此授权。源资源锁必须在任务锁之前按所有共享写方的既定顺序取得：当前身份/范围及 account/material/metric/config 等实际源依赖 → 安全域全局/租户/账户及有序目标树/预算拥有者 → task clock → Task → preparation → 有序 command/node/runtime/attempt。具体跨模块顺序和锁键需主线协调，不能由 C 另造一套与 API/UI 不相交的对象锁。

锁住 Task 后 CAS 复核预读 source/manifest/目标集合；发现变化直接 409/回滚，不在 Task 锁内补取新的素材、metric 或账户锁。任何 source provider 也不得偷偷扩大锁集合，避免与原 final accept 的 source→launch/task 锁序形成循环。

CandidatePage 只用于发现节点。claim 必须在当前锁内复核完整静态证明、当前父状态、取消意图和当前授权，不能复用已提交目录的 ticket。建议主线后续抽出受控 `verify_locked_manifest(session,...)` 供二者复用，返回同 txn 的不可伪造证明；当前 reader `_manifest` 为私有方法且在冻结实测队列中，本阶段不改。每节点重扫完整 DAG 的吞吐成本不可隐瞒，尚不能宣称十万节点发送容量。

ResourceReservationProof 至少包含：三级 kill-switch 实际版本/状态；当前账户币种和预算 policy/基线/观测时间；真实 budget-owner/目标树与冻结父级的精确键；同一逻辑 command 的现有预占或本次唯一预占；原 actor+worker 的动作交集。对 UPLOAD/VERIFY 等操作，零增量必须由真实 policy 明确说明，不用缺省 0 或空数组跳过互斥。创建阶段尚无平台 ID 的预算/目标需原冻结逻辑键，后续与外部 ID 的绑定不能产生第二套互不相交锁。

预占按逻辑 command 贡献一次，不能按新 attempt/fence/worker 再加 delta。迁移发送/核验状态更新同一账本行，不再新增额度。UNKNOWN 及 24 小时后仍未裁定的命令继续保留额度与目标锁，不因 worker lease/服务退出释放。

## 5. 原子 first claim 与幂等回执

首阶段只接受命令和节点均 QUEUED、attempt0、完整父节点全部 SUCCEEDED、无活跃领取、无未处置取消意图。运行头可缺失或为合法全空初始头，不能清掉旧 active_attempt 伪装第一次。原 retry/RETRY_WAIT 和 NEEDS_HUMAN 的恢复不包含在本阶段。

expected 至少绑定 Task revision、原 source/hash/manifest、node id/ordinal、命令与节点原 state/attempt、初始 runtime 缺失或 revision。当前父和所有资源证明都在锁内再核；失配回滚后返回 stale，不在同一个 claim 方法里读新 expected 再尝试。

事务顺序：先取得同事务资源预占和回执唯一键 → 插入046不可变 attempt1/fence1（server生成 claim_id） → 建立/更新 runtime 完整绑定与 SQL UTC 租约 → 命令及节点 QUEUED→RUNNING/attempt1 → 按全体当前节点聚合 Task → 一个 node RUNNING 事件及对应 Task revision/sequence → 安全 audit/outbox 与 task clock 递增一次 → 回执完成，同一外层事务提交。FK 顺序沿原 attempt 先于 runtime，绝不先填半个运行头。任一1644全部回滚，包括额度与对象锁，不留下假已领取。

稳定请求必须独立持久 receipt，不能靠随机 worker 重启键、最后一条审计或“现在没有 runtime”推断幂等。建议058候选只记录内部请求唯一键 `(tenant,worker,request_id)`、规范意图 hash、原源/目标/expected、准确 attempt/FK、before/after revision、资源证明引用、原 audit/事件快照和服务器时间。FK/永久留存不能绑7日可清理的TaskEvent行；保留有界事件快照即可。

同成功键同请求先匹配原 receipt，再处理旧 CAS；异 Task/node/source/原 expected/body 409。请求规范 hash 不吸收每次刷新产生的观察nonce/当前时间，避免同意图重试变身。当前 worker 与原回执读取范围仍须合法；返回旧 receipt 不刷新租约、不重占资源、不增加 attempt/fence，也不授新的发送能力。原幂等回执与 source 唯一 Task 是不同层次，不能用其中一个代替另一个。058正式表/唯一键/保留期由主线审定，当前没有新DDL。

## 6. 取消、暂停、授权撤销与未知结果

原 OpenAPI：`POST /tasks/{id}/cancel` 是 tasks.cancel + Reason；retry 是 tasks.retry + RetryTask；resume 是 tasks.retry + ResumeWorkflow。原 Task 枚举没有 PAUSED，原 API 没有 tasks/pause。服务进程暂停只停止新领取；三级 kill-switch 阻止新发送/重试，仍保留核验和审计；广告 PAUSE 是独立平台业务动作，不能冒充进程暂停。

建议明确裁决：QUEUED 且未领取的 cancel 按67行 QUEUED→CANCELLED；一旦已 claim 到 RUNNING，第一窄阶段 **不因本地 stop 或缺 WRITE_INTENT 行就写 CANCELLED/FAILED**。持久取消意图先阻止后续发送/依赖领取；当前 attempt 必须有精确可信“未发送”证明，按既有67行 RUNNING→FAILED（安全未受理）或 UNKNOWN。68行“未发→CANCELLED”若要覆盖已领取 RUNNING，需主线明确合法边及证据规则后再扩展；不能静默修改已实测052纯决策。此建议故意将“停止发送意图”与“已处理结果”分开，避免重复广告或伪造取消成功。

ACCEPTED/VERIFYING/UNKNOWN 不执行反向广告修改；取消不回滚已成功节点、不解除未知预算/目标锁、不让其它通道接管重发。后台身份或原权限撤回后立即禁止新 claim/新指令/续写；历史事实接收走原独立HISTORICAL_FACT主体及设备真实性门禁，不靠当前广告写权限，也不拿过期租约证明继续可发送。

retry 仅原确定安全失败分支，成功节点保持、不恢复用户已取消节点。resume 仅原 NEEDS_HUMAN，重验 binding/身份/权限/锁及15分钟预览/30分钟指标；已提交后未知不得转 NEEDS_HUMAN 掩盖结果。这些控制操作需要主线统一原API/幂等/事件Store，本阶段不另开写后门。

## 7. 与恢复 scanner 的竞争和发送前缺口

first claim 与052恢复都按 task clock→Task→prep→有序命令/节点/runtime 串行。scanner 预读到旧 expected，claim/续租已变化则原精确 CAS 返回 stale；不能在恢复内部自动重新抓 expected 改同一意图。原无 active attempt 的 QUEUED 不应被恢复 scanner 领取，claim 也不能消费 UNKNOWN/旧 fence。

续租必须单独受控操作、精确当前 worker/claim/fence/revision，不能通过重放成功 claim 请求续租。AdsPower Profile lease 与046 command attempt不同实体，不能因UUID形状相同把 claim_id 当原 agent lease_id；设备与Profile/Agent/adapter/workflow真实能力绑定需专门共享接口。续租、budget/目标锁的跨租约保留和Task是否需要额外事件由主线后续裁决，不能擅用每次心跳增加广告 attempt。

发送还缺独立 `begin_send`：当前原动作/主体/源/对象回读、三级开关、预览时效、租约与资源再次重验，持久 WRITE_INTENT 并确认后才可交受控 transport。claim 事务提交不消除之后发生的撤权/kill-switch；数据库锁也不能撤销已发的网络请求。结果无法证明未发送时保持 UNKNOWN，绝不因请求超时重试新写。当前没有 sender/transport，所以该接口只列缺口，不做调用。

## 8. 所需共享接口和下一授权文件

需要主线统一：正式 worker issuer/撤销/生命周期、完整 source 当前证明、Budget/Target/KillSwitch coordinator、原 Task 控制与事件聚合接口、稳定claim receipt持久层（058候选）、Agent/Profile租约与独立核验代际。没有这些时，生产 first claim 仍 unavailable。

已获授权并新增两个文件 `python/orbit_api/launch_execution_claim_contract.py` 与 `python/tests/test_launch_execution_claim_contract.py`，外加本文：定义严格 typed ClaimRequest/ExpectedHead/FirstClaimProposal 和纯状态/时间/绑定建议，首领仅0→1，取消/UNKNOWN/现役/父未成功不授领取，source/lease/expected不符失败关闭。纯对象不签发实际授权，不接受 verified=True 绕门禁，固定不含transport能力。058仅保留前文候选设计，不写正式迁移或Store。

随后真实SQL专项须验证两个Worker唯一claim、稳定键回执/异body409、资源与Task/节点/事件/审计同事务1644回滚、取消/领取竞争、恢复/续租CAS、旧fence历史事实隔离、三级开关和预占不重计、完整DAG不缺尾页。技术authority与不出网transport测试不能升为Meta/AdsPower验收；真实数据库/服务一律由主线排队，不自行运行。

## 9. 当前纯合同交付与验证边界

`propose_first_claim(request,snapshot,*,database_now,transaction,source_facts,resource_facts)` 缺来源/资源投影先503；投影与锁定快照必须绑定同一非空事务对象。它只消费未来受控 issuer/coordinator 已验证的数据投影，**并不验证投影的发行真实性**：构造合法 DTO/64位摘要绝不等同真实身份、平台能力或预算账本证明。后续 Store 必须在调用纯函数之前取得当前可信来源、全量manifest证明、资源锁和权限；本模块不提供默认 issuer 或绕过此过程的持久接口。

严格源绑定包含 tenant/Task/node/preparation/Plan/source revision/hash/manifest/command/intent、mode、原 actor/subject/owner/team、account/target/kind/purpose。授权投影明确执行动作、Worker身份与版本、SQL观察时间/截止时间、完整节点数和有序父ID；资源投影明确全球/租户/账户三个开关各自版本及作用域、policy来源、目标互斥锁，以及 RESERVED 的预算reservation/owner锁/基线三者，或有来源的显式 NO_BUDGET_EFFECT。后者不放松target锁/开关/policy，也不由本模块猜CREATE的预算豁免。

成功建议仅 QUEUED→RUNNING、广告attempt0→1、fence1、runtime revision新建1或旧空头+1、Task revision/sequence各+1。Task聚合复用原函数，输入仅固定状态计数键，不展开十万节点。原父节点全部精确 SUCCEEDED，否则无建议；UNKNOWN等聚合、取消意图、旧active attempt、代际/来源/租约/三级开关不符均失败关闭。建议对象始终 `claimed=False/transport_eligible=False/writes_intent=False/releases_resources=False`，只可同事务使用。

`ClaimReceipt`/`match_original_receipt` 仅未来持久回读DTO及稳定内容匹配：成功旧键使用原expected/body摘要，异body409；返回原对象/原时间，不读取当前head重绑，也不延长租约或重复预占。当前读授权仍由未来持久调用者核验。本模块不把proposal转换成receipt、不插入046或058，不提供begin_send。

本轮定向纯测 **75/75 PASS，0.74秒**，Ruff与格式检查通过；其中首轮发现旧聚合函数要求tuple/list而不能直接传计数字典，已改为固定状态键tuple，原聚合函数不改。覆盖缺来源资源、同事务、精确源、三层开关、ENABLE双动作、父所有非成功状态、取消、旧代际/计数耗尽、原回执/异正文、显式预算投影及不授发送权。未连接SQL、未领取、未发送、无资源coordinator/正式issuer验证，不能把这些纯建议计为发送Worker已完成。
