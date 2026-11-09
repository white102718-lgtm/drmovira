# 规则Simulation有界当前授权facade

当前：主线原62+新access8实际70/70 PASS（23.31秒），回执`evidence/python-rule-simulation062-access-http.json`；生产/工具定向39纯测由主线另跑PASS（1.15秒）。原28项生产纯测与11项工具纯测边界不变，未注册原simulate或来源issuer。此facade只证明原rules.read、当前Rule和双方完整成员读取范围，不发行指标来源、Simulation READY、确认或执行建议资格。原S2a与候选70/70证据独立，不继承为本facade实际锁行为通过。

## 固定接口

- `RuleSimulationAccessFacade.open(session, actor, rule_id, expected_revision) -> RuleSimulationReadTicket`：要求调用者持有外层实际SessionTransaction，不建连接、不commit。沿原rules.read和当前Rule可见性，锁精确profile/账户/Rule及sealed manifest，返回仅该实例/session/transaction有效的内部票据。不是历史receipt读取入口。
- `iter_account_batches(session, ticket, *, batch_size=200) -> AsyncIterator[AuthorizedAccountBatch]`：仅允许200或1000；batch.accounts为深不可变tuple[CurrentRuleAccount]，含规范UUID、真实当前owner/team/currency/revision/timezone_name/timezone_error。每个batch绑定确切票据/实例/实际事务，并仅在下一次流推进前供`assert_batch`核验，替换/复制其字段不能伪造同等发行。
- `finish(session,ticket) -> VerifiedManifestSummary`：仅真实EOF、全count/根匹配、当前Rule/精确版本未变及双方授权末段复核后成功。summary含count、member_hash、timezone_invalid_count、currency_unknown_count；`assert_summary`核精确发行对象，调用者不能复制对象改count制造证明。无finished/count/root入参，无回调或来源label通行证。

## 当前锁序与完整性

原`rule_access.authorize_rule`实际rules.read与双方owner_scope（非写归属）→无锁Rule/head/version probe→原`rule_profile_references.lock_rule_profile(expected_version=原RuleVersion.metric_profile_version)`的source config→metric clock/head/version→account clock SHARE→同Rule sealed manifest SHARE→rule clock/current head/version SHARE→有序manifest成员/current账户SHARE。Rule当前头锁在account clock之后、开始返回成员批次之前取得，EOF末段再次当前读核对；不先锁Rule再反向锁账户/profile。

该顺序沿原RuleStore.save实际profile→account/source/member→rule路径，纯测核读取序列但不能证明实际数据库死锁/隔离行为。真实SQL专项还须旧RR、两个事务当前scope撤回/改归属与长扫描读锁对写方影响。全体成员扫描持有共享锁，正确性优先，尚无50k性能结论。

逐页查询原`orbit_rule_scope_member` LEFT JOIN当前`orbit_ad_account`，tenant/manifest/account_id > after、ORDER BY account_id、LIMIT绑定200或1000，FOR SHARE OF m,a。不OFFSET，不一次构造50k tuple/list或全图set；库仅保存当前页、常数大小原头与哈希状态。调用方若主动积攒全部批次属于其自身内存行为，不代表本facade容量证明。

ID根逐个`canonical(uuid)`、逗号、左右方括号SHA256，精确等同原RuleStore对canonical([sorted_ids])的格式；ID固定ASCII，不临时改用另一分帧域。必须严格递增/唯一、真实账户存在，完整1..50000且等于sealed manifest.member_count/member_ids_hash；多尾、少尾、重复、未知账户整流失败，不发行summary。

成员原冻结owner/team/currency/revision为历史审计，先验证其结构，但不要求等于当前值。当前账户分别核caller与Rule当前owner的原readable交集；普通改名或当前revision变化不改选择ID根，当前转属在双方均可读范围内不凭历史creator额外禁止。协作读取已绑定Rule不借025/RULE私有source的creator接口，不返回该私有scope内容。

current字段使用原SQL值，不使用冻结币种覆盖真实当前币种。currency NULL保留NULL计入unknown_count，供后续原Money条件按UNKNOWN处理，不补USD。timezone缺失/不可解析标内部TIMEZONE_INVALID并保留真实缺值/字符串；后续不能用UTC、调度时区或假业务日创建完整预期。本facade仍可证明账户授权，不能据此声称该账户可完成窗口/来源计算。未扩大公开DTO或给缺时区新增业务默认。

## 精确profile策略与历史读分离

复用的是原Rule专属`lock_rule_profile`，不是launch-only MetricProfileStore.lock_exact，也不借monitor.read。现helper只锁当前head后匹配expected原版本，并核完整原profile/hash/proof。当前版本不同明确409 METRIC_PROFILE_VERSION_CHANGED，绝不默默升级；返回profile hash和规范source_proof hash还必须匹配原RuleVersion冻结值。

这是当前内部支持限制，不是从PRD推导“head换版就废弃一切旧模拟”。若合同允许旧精确version在head换版后新计算，需主线另批Rule专属exact旧版本可用性读取；本模块不擅改原桥。历史成功receipt读取绝不调用open、不核当前latestprofile重算、不续期，沿原当前read授权和冻结范围历史读协议另实现。

## 取消、重复及能力寿命

open票据、批次、summary绑定发行实例+同一AsyncSession+真实SessionTransaction；提交/回滚再begin即失效，另Session或另Facade不得使用。iterator单次消费，重复/并发迭代拒绝；未到EOF提前finish拒绝；early close/取消/任一行错误使状态失败，不得继续finish。finish并发显式拒绝，取消或末段auth/Rule漂移失败锁存，不返回summary。没有自动重试、后台任务或隐式commit。

状态使用弱票据索引及batch/summary弱引用，避免value反向持有ticket导致长驻facade泄漏每个已完成页；专属纯测实证调用方释放票据/结果后可回收。summary/批次发行对象不是指标provider，也不是能跨事务复用的成功根。

## 验证范围及后续实际队列

28项纯测使用真实AsyncSessionTransaction与SQLAlchemy RowMapping，但授权函数和execute返回为明确纯测替身，不假称真实SQL。覆盖200/1000多页、根/count/丢失/重复/双方scope/原冻结与当前差异、NULL/时区、当前head漂移、profile严格原版本、早停/取消/重复/并发finish、事务与实例隔离、不可变/伪造批次及summary、GC无反向持有。无DB/HTTP/平台操作。

主线后续真实工具应沿原Rule/scope API构造201/1001及完整metadata，实际rules.read无monitor/accounts借权、旧RR current-head与完整双方撤权、ACCOUNT/RULE历史范围协作、普通rename/revision不改根、缺timezone/currency、末页错根与真实锁等待；默认profile换head的409限制与历史receipt独立记录。仍不直接接生产issuer或原simulate路由。真实50k/多币/业务日计算与数据容量另测，不能以28纯测或LIMIT称已通过。


## 主线真实限定结果

首轮8组全部通过，无新失败：1001账户原HTTP图、200/1000完整keyset及元数据根、实际NOTNULL精确1048与回滚、坏时区TIMEZONE_INVALID不补UTC、事务/替换/早停取消、普通改名/revision、caller原read撤回与Rule owner范围、合法RuleVersion更新的旧RR当前CAS、profile换head不默默重绑。此为1001而非50000账户，不代表容量通过；NULLcurrency/缺timezone实际列仍不可达，纯分支只由纯测证明。实际取消为generator取消，不声称阻塞SQL服务器取消；旧RR例未测试锁内并发写。真实图为SQL技术资料，不是指标source发行/模拟成功。
