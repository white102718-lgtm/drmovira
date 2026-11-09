# DAG 完整性与发送候选只读目录

本模块是独立内部 reader，不是发送 Worker、claim 或可跨事务使用的执行票据；默认没有生产 authority、初始化数据库前 503，无 CLI/调度/API 注册。既有 lease/recovery、正式迁移及公共入口未改。

## 接口与可信来源

`ExecutionCandidateDirectory(authority=None, sessions_factory=None, *, clock=None).page(task_id, *, after_ordinal=None, limit=200)`。只接受原 20/50/100/200 四档，ordinal 为非布尔整数 0..99999；无字符串 SQL 或请求租户集合。`ExecutionCandidateAuthority.capture(task_id)` 事务外取得 `CandidateGrant`，`revalidate(session,grant)` 在原事务内核当前真实执行动作及固定来源。无默认实现；tasks.read、tasks.reconcile、TRUSTED 字符串或维护 grant 不授目录执行权限。

grant 固定 tenant/task/原actor/subject/owner/team、当前授权版本、原 source revision/hash、完整 manifest hash、原 execute intent hash、expiry，permission 必须 launch.execute。可信 provider 必须校验当前租户、用户团队/账户/菜单动作、冻结来源与其授权真实性；不能仅查询自身 grant 后返回。外部平台 I/O 仅允许事务外捕获，事务内 revalidate 只能核固定来源的当前数据库证明；最终复核不新增或扩锁其他来源。生产 issuer、完整 kill-switch/预算/账户/设备能力消费者仍未实现，因此默认不能获取候选。

page 自建新 session/transaction，先当前授权，再 task clock SHARE→Task SHARE→preparation SHARE，最后当前授权与 SQL UTC expiry 复核。该顺序已核 039 final `launch_execution_store.py` 的 `await task_access.clock(...write=True)` 在 Task/prep 之前，后续 UPDATE 只是原锁内递增；046 capture 也是 clock→Task→prep。不能因孤立 UPDATE 行误判锁序而修改已有写方。

完整性判断与当前 grant、真实 `SessionTransaction` 同一事务，结束前确认 transaction 未替换。返回 `CandidatePage.execution_authorized=False`，仅含节点/ordinal/类别/账户/目标键/命令摘要及可能的初始 runtime revision；不返回 Token、完整配置或任何可用于发送的 capability。返回后即可过时，正式 claim 必须重新当前核验，不能重用本页结果授权。

## 表与原规范核对

使用 033 Task/Node/Edge/Chunk、035 类型化 DAG 头、039 preparation/byte_chunk/command/acceptance、原 PlanVersion、046 runtime/attempt。036 本轮不生成事件。要求 COMPLETE Task、ACCEPTED preparation、精确同 source/Task/owner/intent/validation/accepted 请求，所有 expected/persisted 计数相符且有真实 seal；历史未知 DAG 头不猜测。

每页完整流式读取实际字节块，核连续 ordinal、长度/逐块 SHA、完整字节 SHA 和总数。严格 JSON 流解析跨块 UTF8/转义/数字，拒绝重复键、尾随多值、截断、NaN/Infinity/孤立 surrogate。只保留单个顶层值和至多 200 个节点，不装载完整十万 DAG。

逐批将字节清单真实 nodes 与 033 initial_json、039 原字段/最终配置和实际规范配置 SHA 全等核对，静态字段不能仅信 count 或自填 hash。复用原 `canonical`、`node_id`、`GraphDigest`；按原 500 节点规范块增量重建节点 SHA 与块根，最多保存 200 个块头。父边集合只限当前 ≤200 子节点、每节点原 MAX_PARENTS=100，实际父节点 ordinal 必须小于子节点，集合与清单精确相等；因此在不保留全图 visited set 的情况下核原拓扑 DAG。最后核真实全表 count 以拒绝额外尾节点/命令/边/块，并校源 PlanVersion payload、文档源 payload、来源拥有者和观察引用摘要。

这些检查不是向 authority 转交一个 `complete=True`。当前没有可靠可跨事务复用且冻结所有静态字段的 proof 缓存，所以首阶段 **每页都会全量流式核验**，同时持有 share 锁阻塞相应写方。`LIMIT 200` 只限制候选页及集合，不限制完整性验证总 I/O；60 秒内部预算超时失败关闭。它只适用于当前小规模内部验证，不称十万节点容量已通过。后续证明缓存/不可变目录、锁占用和容量优化须单独设计/实测。

## 当前状态与代际筛选

原始 ordinal keyset 最多 200 行后集合读取父状态与命令/runtime/attempt。父必须全部 SUCCEEDED。仅 Task QUEUED/RUNNING、节点和命令均 QUEUED 且 attempt=0 的初次未领取项可成为提示；Task UNKNOWN 或终态保守不返回候选。取消/失败/RETRY_WAIT/UNKNOWN 不复活、不擅自增代或重试；此保守范围不能声称覆盖原完整 retry DAG 调度。

046 runtime 不存在仅接受 attempt0；初始 runtime 必须完整 null/零绑定。现役 attempt 必须验证原 tenant/task/node/preparation/source/manifest/命令摘要、原 actor/subject/owner/team/通道及当前 attempt/fence/claim/worker 精确相符，然后只过滤，不生成领取。旧 claim 的 auth_version/authorization_hash 是当时历史快照，不强行等于准备时旧快照或当前 grant；当前权限仍由真实 authority 重核。坏行拒整页，不能悄悄跳过。父状态来自已持 Task/clock 保护的同事务，不把列表读权限当发送许可。

## 内存保护与待验

16MiB 是内部单值和批次规范数据内存预算，超出 503 `EXECUTION_DIRECTORY_MEMORY_BUDGET`，**不是 PRD 新字段上限**。批次不足 200 但累计达到预算就提前消费；500 块摘要仍连续。读取大 SQL JSON 之前先取实际字节合计，MySQL JSON 空格容差上限为两倍内部批次预算，避免一次装载 200 个巨大坏 JSON；源 payload 用 SQL CASE 字节保护。此支持范围以外的合法大文档是当前 reader 容量缺口，不标功能验收通过。

当前专属纯测 **87/87 PASS，0.94 秒**，Ruff/format 通过。涵盖真实规范编码、流解析边界、byte/node/chunk/graph/命令/来源通道错绑、父依赖、原终态不复活、初始/现役代际、当前授权漂移、最终 SQL expiry、同事务证明不可跨 transaction、四档原始 keyset、内部批次预算与读前大小保护。全部是明确 pure SQL 结果夹具，不是实际数据库或生产平台证明。

后续主线真实 SQL 最小档需原 validate/execute 202 完整来源、明确 technical 目录 authority，实际验证默认零初始化、全根/额外尾行、父未完成与完成、当前 CAS 状态、现役绑定损坏、旧 RR 与 share 锁顺序、首末 keyset 页、撤权与过期、取消/60秒清理及真实 EXPLAIN。十万节点容量、正式 issuer、claim/预算/目标锁/kill-switch、transport 和回读均未完成。不得由本目录局部通过勾发送功能完成。
