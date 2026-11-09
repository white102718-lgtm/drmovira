# 受控恢复服务最小接入设计

独立生命周期模块及纯测已落盘，尚未注册生产调度、CLI、应用 lifespan 或正式维护 issuer。054 扫描器及其工具保持冻结。技术 SQL 专项 16/16 不能作为本服务生命周期验收。

## 现有体系与合同依据

若依 `python/ruoyi_fastapi/config/scheduler/manager.py` 以 AsyncIOScheduler、Redis application leader 及数据库任务定义组织 Web 进程后台任务，包含锁续约、同步与重获。该 leader 只证明调度进程所有权，不证明 ORBIT 维护主体、租户范围或事实真实性。不能把普通 sys_job invokeTarget 配置作为恢复授权来源。

`python/orbit_api/invitation_job.py` 提供显式独立循环，`material_worker_service.py` 管理单在途工作及独立 monitor；两者可参考生命周期，但不能继承它们的权限、失败重试或素材状态语义。本阶段不改变现有任务或预览。

原 `WORKFLOWS.md` 66—68 行限定命令和节点恢复边；111 行要求 UNKNOWN 每五分钟只读核验，24 小时后仍 UNKNOWN 并标人工；113 行 kill-switch 保留只读核验与审计；117 行双人确定未发送流程不能由定时器取代；129 行 UNKNOWN 保留预算和目标锁；139—141 行迟到设备事实仍需精确原 attempt 与真实性验证。当前服务只调用既有原代际恢复扫描，不实现五分钟外部回读、不创建广告或核验租约、不增广告 attempt。

## 建议文件及接口

仅新增 `python/orbit_api/launch_execution_recovery_service.py`、`python/tests/test_launch_execution_recovery_service.py` 和本文。无新 DDL。公共 runner、app、正式迁移、CLI、私有配置和生产 issuer 不在本交付内。

实现 `ExecutionRecoveryService(provider=None, scanner_factory=None, *, clock=None)`，显式 `run(*, mode, stop, interval_seconds=30, cycles=None, max_candidates=100, max_raw_rows=1000, time_budget_seconds=10, budget_interval_seconds=0.1, drain_seconds=5, report=None)`。默认 provider 缺失在 scanner_factory、DB 初始化和 create_task 前 503 拒绝。factory 必须使用已审核原 scanner 与同一可信 provider，不接受请求传租户列表或现存数据库 STARTED 记录复建授权。

`once` 单轮；`serve` 显式循环，可限定 1—1000 轮，省略表示受控常驻。正常间隔 1—300 秒，预算耗尽短间隔至少 0.1 秒且最多 300 秒；轮内原 scanner 的候选/原始行/时间上限继续严格验证。drain 必须严格为正且不超过 5 秒。不得把循环周期等同原五分钟平台核验 SLA。

## 生命周期与失败语义

服务实例一次性：NEW→RUNNING→STOPPING→STOPPED，任一未知故障或未证实清理进入 FAILED。拒绝重复或并发 run；失败后不得在同实例自动重启。先核 provider capture/current 的主体、action、租户集合、revision 和 expiry，之后才创建 scanner；每轮授权当前性继续由原 scanner 验证，不自动续签或扩租户。

同一时刻只有一个精确扫描 Task，不并发 tick、不补跑累计 misfire。停止先 request_stop 阻止后续领取，再有界等待当前事务；超过排空预算才取消当前精确 Task，再最多等待 5 秒完成原 scanner 的有界连接清理。绝不取消后立即创建下一轮，也不只凭 Task.done 假定服务端事务已结束。若清理不能证实，抛出 `RECOVERY_SERVICE_CLEANUP_UNVERIFIED`，实例 FAILED 并通过 `retained_tasks` 保留精确 Task 引用供调用者处理，不能假称 STOPPED。调用者在排空期间再次取消，同样锁存 FAILED 并保留尚未结束的精确 Task；不会自动启动新任务。

正常空轮按固定间隔等待可被 stop 唤醒；预算耗尽保留原 scanner 游标并在下轮继续，不创建无等待忙循环。blocked 是既有单项事实/授权证据不足的统计，不自动改变 UNKNOWN；连续 blocked 轮按正常间隔的 2、4、8 倍退避，封顶 300 秒，正常轮重置；不能把 unknown DB 异常包装为 blocked。1205、来源撤销/漂移、协议错误及未知 DB 故障立即失败退出，原 hint 保持 scanner 已验证语义。退避仅限正常完成但 blocked 的轮次，不自动重试失败事务或广告写动作。

服务首次 capture 的 grant 固定保留，使用内部 `_FixedProvider` 包装后交给 scanner；后续 scanner 每次 capture 仍返回最初同一 grant 并当前复核，不会通过外层每轮 capture 自动续签。启动和每轮事务外复核有 5 秒上界。日志回调仅收到固定 result/code 及非负聚合计数，不返回主体、租户、证据、SQL 或配置内容。实际来源签发仍未实现。

本阶段只保证单实例生命周期，不冒充跨进程唯一性。若多个显式服务实例同时启动，原五项 expected CAS 仍保护同一恢复，但正式部署需额外可信进程锁或独立维护租约；不能挪广告 fence 或核验 generation。通用若依 leader 的失效不自动证明本维护授权有效或无效。

## 验证边界

纯测覆盖默认缺省零 factory/DB/task、严格参数、双启动、串行轮次、空轮/预算/blocked 退避、停止唤醒、排空、取消传播、晚失败锁存、未知异常终止、有限轮数和安全统计。异步 Task 必须逐一完整结束，无遗留 sleep/stop watcher。真实 SQL 生命周期随后由 root 串行专项验证；不能从纯 fake scanner 成功推断真实事务清理。

仍缺正式维护 issuer、私有配置消费者、部署启动方式、跨进程运维与容量 SLA、五分钟真实平台回读及人工双审核验。这些缺口不由技术 provider 或调度成功填补。

## 当前验证

`test_launch_execution_recovery_service.py` **26/26 PASS，0.82 秒**，Ruff/format 通过。纯测包含缺省无 authority 零 factory/task、严格边界、单轮与不可重启、并发重复调用拒绝、固定 grant 不续签、授权变更、预算串行轮次、blocked 退避封顶与重置、等待可停止、正常排空、晚失败、调用者取消、排空超时取消且完整 await、不合作任务保留及排空中再次取消。所有不合作 Task 均由测试 finally 实际释放并 await，无遗留测试任务。

此证据只证明受控注入的 fake scanner 生命周期，不证明该服务已经运行真实 MySQL、正式 issuer 或任何平台核验。真实服务专项、CLI 和生产调度尚待主线审核及显式接入。

## 055 初始化链上的真实服务限定结果

主线 `python-execution-recovery-service055-http.json` **20/20 PASS，22.64 秒**：初始化 6、原 scanner 10、新 service 4。through055 只表示该迁移链实际初始化兼容，本回执不证明身份摘要业务护栏。

新增四组均经原 validate/execute 202 完整 Task、隔离技术 runtime 和真正 scanner：once 提交原 052 SEALED 决策及 UNKNOWN 精确版本；serve 在实际 P_S 锁等待中停止领取，只释放本轮自有 holder 后完整 await 当前事务，下一候选不处理；首轮实际提交后原 grant 漂移终止、不续签；真实服务端 1205 原异常终止、不自动重试，原数据和失败候选水位不前进。原 2 秒 wait/trx 清理与同 CID SESSION 参数还原、后续连接池无污染断言保留并通过。

源码和工具继续冻结。此限定结果仍使用 UUID/13306 技术维护主体，零 claim/send/平台请求；无生产 issuer、正式调度注册、外部五分钟回读或跨机服务验收。
