# 既有执行尝试恢复提交 CAS 最小方案（待主线确认）

本稿只提出下一阶段独立 Store 方法；当前 046/050 事实追加真实 27 档正在复验，本文不修改其生产源码、工具或测试。没有新增公开入口、执行 Worker、广告发送、重试调度或核验领取。SQL 技术 authority 不代表正式平台/设备来源授权。

## 方法与可信边界

拟新增 `ExecutionLeaseStore.recover_expired(session, actor_id, binding, expected, request_id)`，必须已有外层事务，Store 不 begin/commit/rollback。默认 authority 缺失在 SQL 前 503。内部取得独立 `RECOVER_EXPIRED` 授权，并调用既有 `capture_recovery` 完整锁读；调用者不能传 decision、事实列表、complete 标志或先前捕获结果来要求写入。

expected 精确覆盖 runtime revision、attempt_no、fencing_token、claim_id、worker_id 五项，并与绑定、当前运行头和不可变原 attempt 同时匹配。捕获、完整事实验证、纯决策、状态提交必须在同一 AsyncSession 的同一外层事务对象内；提交前再次检查该事务仍存续及封印输入未复制替换。任一不符 409 或来源未验证 503，不能自动重新捕获另一代际继续。

锁序沿现实现：task clock → Task → preparation FOR SHARE → command → node → runtime → attempt → sequence 键集事实。新的 HISTORICAL_FACT 追加只保留原尝试事实及审计，绝不调用此方法、自动恢复或提升状态。旧 fence 的事实只属于原 attempt，不能变成当前决策证据。完整事实仍每页 200 流式到结束，后页 WRITE_INTENT/任一 READBACK 不得丢失。

## 最小状态写入范围

使用既有纯协议原边，不新增枚举。WORKFLOWS.md 第 66—68、73、111、117、129、139 行是依据：

| 当前条件 | 允许的本次落库结果 | 明确不做 |
| --- | --- | --- |
| 未过期 RUNNING/VERIFYING | 无变化 | 不续租、不增加 fence/attempt |
| ACCEPTED | VERIFYING | 不把 ACK 当 SUCCEEDED |
| 过期 RUNNING，精确 ACCEPTED 事实且无 NOT_SENT/READBACK 冲突 | ACCEPTED 后 VERIFYING，两条原边均留事件 | 不跳过中间原边 |
| 过期 RUNNING，真实 PROVED_NOT_SENT，完整事实且无 WRITE_INTENT/READBACK | FAILED，retryable=true | 不立即 RETRY_WAIT/QUEUED，不自动发广告 |
| 过期 RUNNING/VERIFYING，不能证明未发送或证据冲突 | UNKNOWN | 不释放预算/对象锁，不切通道重发 |
| 已 UNKNOWN | 仍 UNKNOWN；到 24h 标需人工核验 | 不直接 FAILED，不把 READBACK 追加当独立成功核验 |

NOT_SENT 与三种 READBACK 的任意一种共存均按冲突 UNKNOWN；缺 WRITE_INTENT 本身不是未发送证明。UNKNOWN 的五分钟水位只表示允许后续独立只读核验，不能把本次恢复当已经执行一次核验，因此不更新 last_reconciled_at，也不增加 TaskNode.attempt。24h 后停自动核验仍是 UNKNOWN、保留锁；原双人确认未发送及独立 reconciliation_generation 属后续服务，不在此方法实施。

UNKNOWN 首次进入时设置可信 SQL unknown_since 与原 next_reconcile_at；再次恢复不把 unknown_since 重新开始计时。实际核验完成才可由未来受控核验服务更新 last_reconciled_at。若当前状态、人工标志、水位均无变化，返回明确 no-op，不制造新 revision/事件。

## CAS 与任务汇总

command/node/runtime 的原状态须与锁读一致，所有 UPDATE 明确带旧状态/身份条件并核 rowcount=1。runtime 本次真实变化只 UPDATE 一次，revision 恰好 +1，attempt/fence/claim/worker、lease 及原 source 保持不变；遵守 046 trigger。node 无独立 revision，不凭空增加字段。多步路径逐边更新 command/node，保留每条边事件；只有最终 runtime 头持久化一次。

Task 汇总必须使用当前完整节点集合，不能利用已存在 RR 快照。建议 Task 锁下按 ordinal 键集、每页 500 个 node FOR SHARE 当前读取，只累计原状态计数；确认数量等于完整 manifest node_count，不将缺页当完成。Task aggregate 用原优先级，任何剩余 UNKNOWN 保持 Task UNKNOWN；其他 UNKNOWN 的 24h 人工标志也要当前核验，不能因只看本节点就清掉已有 needs_manual_reconciliation。若需要读取其他 runtime 的 unknown_since，在此 Task 锁保护下按 node_id 有序读取，并用同一可信 SQL 时间判断；不跨 Task 锁序。

建议每条实际节点状态边消耗一次 Task revision 和 TaskEvent sequence（Task 汇总即使保持 RUNNING，事件仍记录原 node_id/边后状态）；Task latest_event_id/latest_sequence 对应最后一条真实事件。Task clock 在整个恢复提交中只 +1，不随两条中间边重复 +1。人工标志从 false→true 而状态仍 UNKNOWN 时，记录一个 state=UNKNOWN 的原 TaskEvent 与一个 Task revision，表示真实元数据变化，不伪造新状态边。精确事件语义请主线确认后实现。

## 时间、审计与失败原子性

事实读取保留 UTC_TIMESTAMP(6)，050 occurred_at/recorded_at 完整微秒不截断。既有 runtime/Task/Event 是 DATETIME(3)，不扩散迁移；写入这些字段使用 SQL UTC_TIMESTAMP(3) 的实际值，不能先用六位 Python 时间参数让 MySQL 舍入进位成未来时间。租约/24h 判断仍由数据库可信时间和原存储精度计算。

每条原状态边及人工标志实际变化都写原 TaskEvent、TaskAudit、TaskOutbox，与 command/node/runtime/Task/clock 处于同一外层事务。原 TaskAudit 没有 details_json；本轮不擅加列。建议 action 使用固定安全代码 RECOVERY_ACCEPTED / RECOVERY_VERIFYING / RECOVERY_FAILED / RECOVERY_UNKNOWN / RECOVERY_MANUAL，request_id 关联原事件，事件保留 node/state/Task revision/sequence。需要持久化精确决策证据序号/摘要的额外审计字段若被要求，应由主线分配新迁移，不能把无 details 的 audit 说成已存完整证据快照。

任一 CAS、审计/outbox 1644、Task 汇总不完整或 authority 失效，调用方必须回滚整笔；绝无部分 UNKNOWN、部分 revision 或丢事件。Store 返回值只能表示外层尚待提交的结果。相同旧 expected 重试在已提交后冲突，不把 request_id 自行变成无定义的写幂等协议；若需要成功结果重放需另定原合同下的持久 receipt，不用内存缓存或 INSERT IGNORE。

## 拟实施及验收顺序

先得到主线确认事件/revision规则与现审计范围，再只改专属 Store/纯测试：新增方法、当前节点汇总、单次 clock 与事件原子写；默认 authority 仍缺失，不注册 Worker 或路由。原 readonly/append 方法不增加状态副作用。

随后由主线串行真实 SQL 专项：五项 expected 各不符；同事务封印及跨事务拒绝；各原恢复边及两个中间事件；289 后页冲突；UNKNOWN 五分钟/24h 不增 attempt 且不清预算/对象锁；其他节点 UNKNOWN 汇总；旧 fence 事实不影响当前；两个恢复者只一 CAS 成功；outbox 1644 全表/clock 回滚；正常提交仅一次 task clock。技术 fixture 明示无实际平台发送/正式事故恢复证明。


## 052 已分配的可追溯账本（候选，未执行）

主线确认两表：`orbit_execution_recovery_decision` 保存完整原 attempt 七列组合外键、before/after runtime revision、Task revision/sequence 与目录 clock、完整 fact count/last_sequence、有序 hash 根、原 decision/path/code、actor/request/SQL UTC6。`orbit_execution_recovery_edge` 最多三行，保存每条实际 node 边或人工标记的原 TaskEvent UUID/sequence/revision/node/state 快照、该边后 Task aggregate，以及审计 UUID 的 tenant/task/id 精确 FK。不对七日可清理 TaskEvent 建永久 FK；发布前实际核每条事件的原字段和 request/time，再封存快照。

候选采用 BUILDING→SEALED 同一外层事务发布。头只能 BUILDING 插入；唯一允许 UPDATE 是所有业务字段不变且完整边数/连续 sequence/revision 已满足时封存。边 INSERT 必须锁同一父头且仍 BUILDING，ordinal 在声明 event_count 内；封存后不能事后追加。两表均禁止 DELETE、边禁止 UPDATE；封存后头永久不可改。应用额外逐边核原路径/事件/audit/outbox相同绑定，缺任何一行则整事务回滚。未封存行不能作为公开/内部成功结果；正常提交必须封存。无需向原 TaskEvent 增列。

完整事实根拟固定 hash_schema_version=1：先 SHA256 域隔离初始文档，包含完整 AttemptBinding；每个已验证事实按严格连续 sequence 以 `SHA256(previous_digest_bytes || canonical({sequence,fact全部字段,recorded_at UTC6}).utf8)` 滚动；初始域名 `ORBIT_EXECUTION_FACT_CHAIN_V1`。各字段用原规范 JSON 及 UTC 固定六位，整数不当字符串，NULL保持NULL。只增 32 字节根及计数，不积累无限 JSON；必须包括 event UUID、kind/phase/source/evidence hash/external ID、发生和记录微秒及原绑定，不能只 hash 六类代表。根会由原事实重放验证，不能当平台真实性本身。旧 source 的实际修改等待检查点推送解冻。

ACK 与同 attempt PROVED_NOT_SENT 即使没有 READBACK 仍是相互矛盾来源，本轮纯协议须返回 SEND_EVIDENCE_CONFLICT→UNKNOWN，绝不按 ACK 进入 ACCEPTED；旧 fence 中 ACK/NOT_SENT 不参与当前冲突或提升。

主线已确认每条 node 边 Task revision/sequence +1、整次 taskclock仅+1；node_id 非空事件 state 始终该 node 边后状态，Task.state独立汇总。manual false→true独立 UNKNOWN 事件1次。052不扩大原状态集，不用 ledger代替预算/对象锁或核验租约。

## 当前真实追加基线

主线执行050追加第三轮 27/27 PASS，10.05秒，证据 `docs/orbit/evidence/python-execution-fact050-http.json`。原两个夹具失败保留：第一轮固定时钟连接释放后换池连接，第二轮固定 AsyncConnection 对应URL读取方式不兼容；分别修复实际物理连接持有/精确重置及 get_bind().engine.url 后全原断言通过。真实范围包含三个微秒边界、跨秒同事件原回执、旧 fence 当前全字段不变、outbox1644整笔回滚重试及实际双连接同event唯一行。没有广告 claim/send或恢复状态写入；本052方案不能继承为已实测。


## 独立实现检查点（纯测，未真实采用052）

新增 `python/orbit_api/launch_execution_recovery_store.py`，入口 `ExecutionRecoveryStore(authority=None).recover_expired(session,actor_id,binding,expected,request_id)`。默认无受控 authority 在SQL前503；外层事务负责任何异常整笔回滚，方法不commit。实现有序完整事实摘要、完整当前Task节点分页500读取与每页UNKNOWN runtime集合查询（按node UUID排序，避免逐节点N+1）、精确CAS、两阶段ledger封存与实际event/audit/outbox关联核验。对UNKNOWN完整节点扫描的真实SQL锁/EXPLAIN/容量尚待专项。

052候选当前2表6trigger，声明的事件数最多3，BUILDING头只能完整封存；封存后禁止追加，边与头不可变。原事件只保留不可变关联快照，不永久FK七日SSE表。SQL触发器、JSON比较、FK及原子性尚未执行，不能把纯编排测试当数据库验收。

定向纯测包括124原契约（新增ACK/NOT_SENT含已ACCEPTED情况）、55锁读Store、20事实追加、9完整hash链、19恢复编排，共227项曾在一次固定命令全部通过（1.48秒）；随后将已ACCEPTED冲突路径进一步严格改为原 ACCEPTED→VERIFYING→UNKNOWN 两条原边（避免发明直接ACCEPTED→UNKNOWN），契约+恢复143项复验通过0.76秒。下一主线真实SQL前应以最终源码再跑该227清单，不能合并两轮为未经执行的新固定全量结论。

恢复编排19项只证明内部SQL参数/事件状态和aggregate分离、单次clock、manual事件、no-op无写、失败传播、500+1当前分页/集合UNKNOWN校验及封存关联缺失拒绝；不证明SQL事务回滚或真实fencing并发。旧050的27实际结果保留原源码范围，新hash/恢复源码须新真实复验。没有正式authority、claim/send、Worker、平台读取、预算锁释放或实际事故恢复验收。

最终上述五文件固定清单已在当前原边路径源码重新执行：227/227 PASS，1.46秒；Ruff PASS。此前小档复验记录保留，不冒充真实052结果。

真实工具已准备：tools/launch_execution_recovery_checks.py 导出 RECOVERY_COMMIT_CASES 固定13组及七参入口 run_execution_recovery_checks(client,admin,headers,password,cache,database,cases)。严格13306/UUID/SELECT DATABASE三重guard，12项护栏纯测通过；工具尚未真实执行。ACK双边同组额外读取原GET Task/nodes及有界SSE九字段帧，保持响应/迭代器完整关闭；七日清理采用明确时间故障fixture后调用原 TaskEventStore.purge，不直接删除新事件、不DROP触发器。当前生产未注册恢复writer，技术authority不能变成平台授权。


## 052 完整真实 SQL/HTTP/SSE 复验（当前限定结果）

主线完整档已实际 **40/40 PASS，12.72秒**，证据 `docs/orbit/evidence/python-execution-recovery052-http.json`。本轮包含旧只读Store/050追加基线与新13组恢复提交；当前完整stream根及冲突语义在该轮共同实测。真实内容包含默认authority零SQL、精确五代际、原FAILED/ACCEPTED/VERIFYING/UNKNOWN边、ACK与NOT_SENT及第289条READBACK冲突、未到期NOOP、UNKNOWN五分钟不伪核验/24小时人工标志、其他UNKNOWN节点人工标志保留、实际双连接唯一CAS、outbox1644整笔回滚重试、两张SEALED账本不可变、原合法七日清理不破坏恢复边快照。

ACK双边之后实际通过原GET Task、nodes及SSE九字段顺序消费；每条node事件保留本节点边后状态，Task聚合单独读取。实际事实链根从完整事实重新计算后与052保存值一致；恢复没有新增广告attempt/fence、claim/send、重试重排或资源释放。

首轮 **26通过/1失败/13未运行** 保留 `docs/orbit/evidence/python-execution-recovery052-first-failed.json`：新13组开始前，metadata SQL内裸LIKE百分号被PyMySQL参数格式器误处理。修为 `LIKE %s` 与单独绑定 `('guard_exec_recovery_%',)`，保留原2表/6trigger断言，新增参数绑定及错误trigger数量拒绝纯测后全40通过。此记录追加于原历史后，不改写此前“候选未执行/工具尚待”的阶段记录。

本轮是明确本机UUID/13306、真实完整202来源加隔离SQL技术运行头/证据authority的验收；不是正式平台authority、实际广告写入事故或持续后台调度验收。当前052生产源码/工具/测试冻结，后续受控扫描入口只设计，不擅自注册到应用或Worker。
