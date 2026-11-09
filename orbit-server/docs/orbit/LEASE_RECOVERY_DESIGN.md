# 执行命令租约与 UNKNOWN 恢复协议（046 候选）

## 最初协议交付范围（历史，当前结果见文末）

本阶段只有 `launch_execution_lease_contract.py` 的不可变 DTO、租约恢复纯函数、Task 汇总纯函数，以及 046 三表六触发器候选。**没有领取器、发送器、恢复 Worker、HTTP 路由或实际迁移执行。** 不修改 033/039，不操作平台、预算、全局目标锁或原运行服务。纯测只证明协议分支，不证明真实 MySQL 约束、平台证据可信、正式发送或完整任务业务验收。

原资料位于 `data/ORBIT_Codex开发PRD/contracts/`。下文行号以当前原文件为准，路径从工作区根解析；原 Schema 是 `openapi-current.json`。

## 原合同与恢复边逐项对应

|判断/边|原合同位置|本阶段处理与限制|
|---|---|---|
|所有持久状态转换 CAS、revision+1、审计/outbox 同事务|WORKFLOWS 第5节第59行|纯函数返回 decision 而不写状态。未来 Store 必须同时更新 039 command、033 node/task、运行头、TaskEvent、TaskAudit、TaskOutbox；任一步失败整体回滚。|
|DRAFT→VALIDATED→QUEUED→RUNNING→ACCEPTED→VERIFYING→SUCCEEDED|第5节第66行|本阶段不领取、不发送，不将现有 QUEUED 自动视为有授权。只允许当前已 ACCEPTED 进入 VERIFYING；确切当前 ACK 可给出 RUNNING→ACCEPTED→VERIFYING 路径，不能给出 SUCCEEDED。|
|RUNNING→FAILED，必须证明未受理|第5节第67行|租约过期后，只有完整当前尝试事实、可信传输层正向 BEFORE_DISPATCH 未发送证明、精确 attempt/fence/claim/worker/全部冻结来源一致且没有 WRITE_INTENT 才建议 FAILED、retryable=true。默认 `facts_complete=False`，缺意图记录本身绝不是未发送证据。此 code 为私有 PROVED_NOT_SENT；原 UNKNOWN 人工恢复专用 CONFIRMED_NOT_SENT 不借用到此分支。|
|RUNNING→UNKNOWN|第5节第67行|过期有 WRITE_INTENT、没有正向证明或事实集不完整，建议 UNKNOWN。即使进程看似未开始，也不能凭内存/缺日志判安全重试。|
|VERIFYING→UNKNOWN/FAILED（确定拒绝证据）|第5节第67行|本阶段仅租约过期→UNKNOWN。READBACK_SUCCEEDED/REJECTED 事实可类型化但不会被租约函数直接转换成成功/失败；确切完整读回及拒绝分类由后续 Store/权威验证器实现。|
|UNKNOWN 每5分钟对账，24小时后标人工，仍为 UNKNOWN|第9节第111行|起点 `unknown_since` 不随对账刷新。到 5 分钟 inclusive 才 `readonly_reconcile_due`；到 24 小时 inclusive 标人工且停止本协议自动定时调度 (`next_reconcile_at=None`)。这是“对账到24小时后”解释；人工仍可发起只读核验，绝非释放锁/额度或终止证据保存。|
|UNKNOWN→VERIFYING→SUCCEEDED；UNKNOWN→FAILED→RETRY_WAIT|第9节第111行；第10节第117行|租约函数保持 UNKNOWN，不消费单份“未发送”或“读回成功”事实自动恢复。未来需 tasks.reconcile 两名不同有权者、唯一平台 ID、请求关联/账户父级字段重验，未发送人工核准才 FAILED + CONFIRMED_NOT_SENT + retryable=true；这条人工服务未实现。|
|FAILED→RETRY_WAIT→QUEUED，原 command 保留所有 attempt|第5节第67行、第73行|本阶段 FAILED 不直接排回队列、不增加 attempt、不创建替代 command。未来需当前原动作/风险/目标锁/预算/kill-switch/来源重校验才创建新 attempt 与更高 fence。|
|QUEUED→CANCELLED/EXPIRED/BLOCKED_AUTH、父失败 BLOCKED_DEPENDENCY|第5节第67—68行|不由租约函数猜测。取消仅未发送；父重试成功只恢复原仍有意图且未成功的依赖节点，用户取消不能复活。后续 DAG Store 负责。|
|Task 汇总：UNKNOWN 优先，运行/核验、重试等待、未运行、全终态组合|第5节第73行|使用原 Task/TaskNode enum。UNKNOWN 最高，NEEDS_HUMAN 次之；RUNNING 优于 VERIFYING；ACCEPTED 属发送已受理的活跃阶段，临时汇总 RUNNING，进入 VERIFYING 后才汇总 VERIFYING。DRAFT/VALIDATED 未运行汇总 QUEUED；受理后的完整清单实际初始均 QUEUED。失败终态包括 BLOCKED_DEPENDENCY/EXPIRED/BLOCKED_AUTH。|
|NEEDS_HUMAN 及优先级；已提交不明必须 UNKNOWN|第11节第137行|只做汇总优先级，不凭超时将已提交结果转 NEEDS_HUMAN。resume 的 binding、权限、锁、15/30分钟时效和取消仍未实现。|
|配置验证成功与投放有效状态分开|第5节第75行|任何本模块 SUCCEEDED 汇总均只指配置任务结果；不写 configuration_state/delivery_state，更不标“正在投放”。|
|晚到历史事实不能因租约过期丢弃；设备须匹配有效 fence|第11节第139行|Fact FK 绑定原 attempt 的完整代际。纯函数只消费与当前 AttemptBinding **所有字段** 相同的事实，其他事实保留资格不等于推进资格。未来 Store 可仅追加旧 fact、不能更新当前运行头/node/task。|
|UNKNOWN 保留预算和目标锁，超过24小时仍不释放|第10节第129行|本协议从不释放预算或对象锁。046 不是全局目标锁或预算账本，不能假称阻止所有跨任务冲突。|
|三级 kill-switch 保留只读核验|第9节第113行|本阶段没有发送接口；未来全局/租户/账户开关缺一不可发送，开关阻止新写与重试，不能阻断事实留档、核验及审计。|
|双通道冻结，UNKNOWN 不切通道重发|第11节第135行|AttemptBinding 明确原 META_API/ADSPOWER_UI，通道差异事实不会匹配。此处不是 AdsPower Agent 租约或其全部 mTLS 控制面。|

### 原 Schema 的边界

`openapi-current.json:37509` 为 TaskNode；第37540—37561行定义节点状态。第37608/37617行分别定义 configuration_state/delivery_state。第37659行起 Task，37674—37688行定义任务状态，第37708行定义 needs_manual_reconciliation。公开状态来自现有 `task_contract.NODE_STATES/TASK_STATES`，不新增 WAITING_RETRY、FAILED_RETRYABLE 或 WRITE_INTENT 状态。私有 `FactKind` 描述事件事实，不是业务状态扩展。READBACK_SUCCEEDED 结构必须携带原 Schema 唯一数字 external_id，仍不等于实际可信成功。

## 类型与信任边界

`AttemptBinding` 冻结 tenant/task/node/preparation、attempt_no、fencing_token、claim/worker UUID、完整 command/manifest/source/authority/authorization SHA256、真实 actor/subject/owner/team/auth_version 与 execution_mode。计数严格整数（拒 bool），attempt 沿原 INT UNSIGNED，fence/revision 限安全整数，摘要严格64位小写十六进制，时间要求明确 UTC。

`AttemptFact` 包含稳定 event UUID、精确 binding、私有 kind/source/send_phase、证据摘要、发生时间和可空 external_id。PROVED_NOT_SENT 只接受 TRANSPORT_PROVEN_NO_SEND + BEFORE_DISPATCH；不能把网络 timeout、没有 ACK 或记录缺失归成该类。收到“本地有意图”与“未发”相矛盾，保持 UNKNOWN 等核验。

交叉审查补强：同一精确当前尝试的 PROVED_NOT_SENT 与任意 READBACK_SUCCEEDED、READBACK_REJECTED、READBACK_INCONCLUSIVE 共存，过期恢复均保持 UNKNOWN、retryable=false（SEND_EVIDENCE_CONFLICT），即使同包还有 ACK 也不能绕过矛盾走安全重试或成功。三类读回均有独立反例；旧 fence 的读回或未发送事实不参与当前判断，不得借旧事实推进或污染当前代际。

**DTO、摘要、完整性 bool、TRUSTED 标签均不是授权或证据认证机制。** 这些函数只能由未来可信 Store 根据持久事实和受控 transport/平台来源调用，不接受客户端提交的 facts_complete 或 Fact。未来 Store 必须证明事实集合完整；当前最多200份输入是纯函数内存上界，不允许 `LIMIT 200` 截断后传 `facts_complete=True`。超过时应受控流式归约/完整证明或保持 UNKNOWN，不能跳过前面的 WRITE_INTENT。

本交付没有 claim API，也没有真实 Authority 实现。默认缺少正式 authority 时根本不进入领取/发送；039受理 provider、M2原始只读观察、fixture能力形状和单纯 kind='TRUSTED' 都不能授发送权。NOT_SENT 的真假、可信传输证据和 readback 关联仍需后续 Store 与 authority 实测。

## 046 候选表、约束与锁序

|表|作用|FK 与索引|
|---|---|---|
|orbit_execution_attempt|不可变尝试及当前授权/来源冻结|FK→039 command/preparation、当前租户业务身份；唯一命令 attempt、fence、tenant claim、完整运行绑定。无 attempt→runtime FK，避免非延迟 FK 环。|
|orbit_execution_command_runtime|命令唯一运行头、CAS、租约和 UNKNOWN 水位|FK→command，当前 attempt/fence/claim/worker 组合 FK→attempt；初始空指针+fence0，后续终态清租约仍保留尝试绑定。expiry/reconcile 时间+tenant/task/node keyset 索引。|
|orbit_execution_attempt_fact|不可变事实，允许旧代际补传|精确 FK→attempt；tenant/event UUID 幂等与尝试内连续 sequence 唯一；按 attempt/occurred_at/event_id 有界读取。异内容同 event 必须冲突，不能 `INSERT IGNORE` 当成功。|

六个 trigger：attempt U/D 不可变、fact U/D 不可变、runtime D 禁止、runtime U 强制原身份/创建时间不变、revision+1、代际不倒退、同 attempt 不换 claim/worker、新 attempt/fence 同时+1。所有字段中文 COMMENT；三表明确 utf8mb4_0900_as_cs；hash/basic state/source/phase/时间/完整指针 CHECK。**约束草案尚未在 MySQL 执行。** 跨表真实状态/权限/清单哈希/事实可信性不是这些 CHECK 自动提供的。

未来 Store 最小写序：在事务外获取受控、无副作用的来源证明；事务内按全局约定来源/权限→目标/预算及 kill-switch→任务运行锁的固定序重验，原 033 task clock/task→按 UUID 排序 command/node/runtime；在当前 command 锁保护下插不可变 attempt、再更新 runtime 指针和 command/node attempt/state；一并 TaskEvent、TaskAudit、TaskOutbox。**这是待主线确认的新增锁序建议，不在当前代码执行。** 不得为 renew/finish 先锁 runtime 再倒锁 task/source；来源 I/O、平台回读、媒体/设备 I/O 均在 SQL 锁外，写前锁内验证快照未变。

接管过期租约只可做当前代际 CAS 与恢复判断，不可直接发送。追加旧事实可核原 claim/source 后仅写 fact，必须与任何当前状态写路径分开；若当前 attempt 已改变，不能借旧事实通过现有 worker 的 fence。未知对账到期查询 `(next_reconcile_at,tenant_id,task_id,node_id)`，过期查询同 expiry 结构，有限批次、无 OFFSET；实际 EXPLAIN、并发双领取、1644审计失败回滚、故障断电与容量验证需后续真实工具。

## 下一阶段依赖与验收缺口

后续需主线分配 `launch_execution_lease_store.py` 与 `launch_execution_recovery_worker.py`，统一真实权限、lease/head CAS、UNKNOWN 人工双审、全局目标锁、预算账本、三级 kill-switch、权威 freshness 与不可变 manifest/source 重算。拟接口仅供评审：`claim_for_recovery(session, controlled_authority, now, limit)`、`append_fact(... exact_binding, event)`、`finish_recovery(... expected_revision/fence, decision)`；authority 缺失默认拒绝，不启动后台循环，不挪用账户只读同步 Worker 的 WAITING_RETRY 语义。

实际平台发送、可信 NOT_SENT 传输证明、平台唯一 ID 回读、UNKNOWN 双人恢复、Meta/AdsPower 发送、预算锁、任务 HTTP 增量事件都未验收。DDL/纯函数通过不能勾完整执行模块或功能验收。

## 当前检查点：046 真实有限验证

主线已采用 `python/orbit_api/migrations/046_execution_command_leases.sql`，并执行 `.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 46 --execution-lease-only`，实际 **16/16 PASS、9.39秒**；证据为 `docs/orbit/evidence/python-execution-lease046-http.json`。包括初始化/退出及10组046专项：真实3表6触发器、原validate200/execute202完整039来源、精确FK、单调fence/运行头CAS、旧事实隔离、不可变/时间/阶段约束，以及outbox1644使运行头/事实/审计/事件同事务回滚、正常整体提交。全程 **claim=0、send=0，无执行Worker**；技术SQL运行头不表示真实广告开始执行。

首轮 **14通过/1失败/1未运行** 已保留 `python-execution-lease046-failed-01.json`：工具管理连接 `autocommit=True` 却未明确begin，前几条样本写入提前提交，严格回滚baseline断言因此失败。工具改为显式begin、正常commit、异常rollback；原断言未删除，随后原16档全部真实复验通过。这是测试夹具事务边界修复，不是实际平台事故恢复成功。

原租约契约 **121项纯测通过**，包含三类READBACK与PROVED_NOT_SENT冲突、旧attempt/fence事实隔离、5分钟及24小时边界，Ruff通过。纯测与本地DDL护栏不证明可信平台证据、生产写authority或完整执行业务验收。

下一窄Store是独立在制模块 `launch_execution_lease_store.py`：当前仅受控authority抽象协议、同事务锁内恢复输入与每页200条连续键集流式事实核验，避免截断288条核验记录或丢弃后页WRITE_INTENT/冲突；没有事实追加、状态CAS、TaskEvent/审计/outbox写方法、公开入口或周期Worker。此检查点的固定全量回归与提交**不包含新Store及新测试**；它们须后续独立审查与真实SQL验证，详见 `LEASE_RECOVERY_STORE_DESIGN.md`。独立核验generation不得增加原广告执行attempt，047目前仅预留设计。
