# 窄执行恢复 Store：可信输入阶段与核验代际分离

## 当前阶段与证据

046 已由主线采用为 `python/orbit_api/migrations/046_execution_command_leases.sql`。本地隔离验收 `docs/orbit/evidence/python-execution-lease046-http.json` 实际 **16/16 PASS，9.39 秒**：其中10组租约SQL专项与初始化/退出，覆盖真实3表6触发器、原预检200/execute202完整039来源、精确FK、单调fence、旧事实隔离、真实outbox1644整体回滚及正常提交。没有 claim、发送或执行 Worker。首轮14通过/1失败/1未运行证据保留；原因为工具管理连接 autocommit=True 却未 begin，修为显式事务后严格原断言全部复验。不是生产事故恢复或平台写验收。

本新增 `launch_execution_lease_store.py` 的可信读取阶段已真实 **23/23 PASS、9.95秒**，见 `python-execution-lease-store046-http.json`：原10组/初始化加新7组，实际289事实后页冲突、旧RR锁读当前preparation、索引和P_S确认并发command锁等待均通过，0claim/send。新事实追加阶段已实现但尚待050真实专项；没有状态CAS、TaskEvent、公开路由或周期服务。`capture_recovery(...).decision(session)` 仍只计算纯建议，不表示任务已提交状态变更。

原业务状态与逐边依据仍见 `LEASE_RECOVERY_DESIGN.md`：WORKFLOWS第5节59/66—68/73/75行、第9节111/113行、第10节117/129行、第11节135/137/139行。核验代际不增加广告执行次数，是主线明确裁决，不能把每5分钟的只读核验算成新广告尝试。

## 方法与 authority 边界

`ExecutionLeaseStore(authority=None)` 默认不可用，`capture_recovery(session, actor_id, binding, expected)` 在任何SQL前返回503 EXECUTION_LEASE_AUTHORITY_UNAVAILABLE。仅接受显式服务器注入的 `ExecutionLeaseAuthority` 抽象类实现；没有默认实现或自动注册。`kind='TRUSTED'`、M2原始观察、数据库中的技术 authority_hash、普通布尔验证结果均不能授予权限。

`ExecutionLeaseAuthority.authorize(session,actor_id,binding,operation)` 必须真实核验后返回精确 `LeaseAuthorityGrant`，绑定actor、原AttemptBinding及私有操作。`RECOVER_EXPIRED` 是当前恢复权限/来源重验，不是放宽原动作；后续具体provider须按真实原发起人权限及拥有者/源状态核验，不能借后台系统用户替代。`HISTORICAL_FACT` 为未来历史追加预留：独立核设备/受控主体与原已发生事实的真实性，不能要求现广告写权限来丢弃历史，也不能借该操作推动当前状态。

`verify_fact(session,fact,recorded_at=...)` 必须根据真实不可变证据源核请求关联、发送阶段、实际内容hash、唯一平台ID及发生时间，再返回绑定**整份** AttemptFact 与 recorded_at 的 `FactValidationReceipt`；不能仅把现事实表的hash转抄为验证成功。此模块没有真实transport/平台验证器，因此仍不能生产恢复/发送。

所有provider方法限定有界SQL/已捕获来源重验，禁止持SQL锁做网络、设备或文件I/O。不确定来源必须拒绝，不能返回None当成功。具体provider尚待主线分配和真实专项验证。

## 锁序与当前运行头

调用者须持外层事务，Store不隐式begin/commit/rollback。授权来源先重验，再按原顺序锁：

1. tenant task clock `FOR UPDATE`；
2. 同tenant task `FOR UPDATE`，完整manifest、真实owner/team/mode/source一致；
3. 真实039 preparation 单独 `FOR SHARE`，必须是当前ACCEPTED完整来源，避免只锁command的JOIN混入旧RR快照；
4. 单个command（将来多命令按UUID）、node、runtime依次 `FOR UPDATE`；
5. 原不可变attempt `FOR SHARE`；
6. SQL `UTC_TIMESTAMP(3)`，其后完整事实读取。

`RuntimeExpectation` 必须精确提供 revision、attempt_no、fencing_token、claim_id、worker_id；当前 runtime 必须全部匹配，且绑定传入真实 AttemptBinding。command/node 当前state和attempt须一致，只接受本窄阶段 RUNNING/ACCEPTED/VERIFYING/UNKNOWN；039 preparation须已ACCEPTED、完整命令数匹配任务，manifest/source/configuration hash须一致。解析实际resolved JSON重新规范hash，不仅信存储hash字符串。原attempt读取后逐字段核actor/subject/owner/team/auth_version及全部冻结来源。

没有新attempt/fence分配、lease续期或跨worker接管。历史追加与状态CAS尚未实现，不把当前SQL技术样本当作实际已开始的广告执行。

## 流式完整事实与有界内存

事实按当前attempt的sequence键集每页200条、严格连续1..N遍历到空页；没有200总条数截断。每页校验attempt/fence/claim/worker、类型/phase/source/hash、UTC occurred_at≤recorded_at≤SQLnow，再逐条经受控authority核真实出处。任意缺口、坏行、未知来源、过时收据或超时均拒绝，不签发半包complete。

同command锁约定必须适用于未来所有追加者，避免边读边改；046 immutable U/D触发器与唯一sequence/event约束共同保护已提交事实。直接SQL技术fixture不是生产追加协议。不能删除尾事实后伪装完整，也不能 `LIMIT 200` 后直接宣称无WRITE_INTENT。数据库管理员破坏约束的情况不在普通权限可信边界内。

内存只保留一页200行、每类一个代表和计数（最多6种私有FactKind）。288条24小时核验样本会完整遍历，后续页WRITE_INTENT、三类READBACK与早期NOT_SENT冲突均被保留。30秒内部读取预算超时返回固定503并让外层回滚；超时不推断UNKNOWN已持久、更不假称安全重试。

`VerifiedFactSummary` 只由模块完整读取签发。`VerifiedRecoveryInput` 同时绑定私有issuer、精确进程内实例seal、summary及外层事务对象；复制DTO替换事实/时间/版本、跨事务使用均拒绝。调用者没有 `facts_complete=True` 参数。内部只把已核验的有界种类代表交原纯协议，既保留冲突/WRITE_INTENT，也不再受原200条纯函数输入预算限制。进程内issuer不是平台授权或可传客户端的签名令牌。

## 下一步状态写入（尚未实现）

下一窗口才可接 `append_verified_fact` 和 `recover_expired` 写方法：必须重验当前expected全部字段、原事实stable event同内容幂等、按attempt内sequence串行追加；旧fence历史事实只能写原attempt及安全审计/outbox，不修改当前运行头或任务状态。相同event异body必须冲突，不能 INSERT IGNORE。

状态推进需原command/node/runtime/task同步CAS、task clock+1、原TaskEvent/TaskAudit/outbox同事务；多步 RUNNING→ACCEPTED→VERIFYING 每条原边须保留实际事件，不直接写成功。UNKNOWN不直接FAILED、不释放预算/目标锁，needs_manual_reconciliation按实际UNKNOWN节点汇总。确定未发人工双审仍未实现，读取建议不替代原审批。

上述读取阶段已通过实际23组，但没有正式平台authority、事故恢复或业务状态写入验收。原55项读取纯测和20项新追加纯测、24项工具纯测合计99项通过，Ruff通过；新增纯测与读取阶段真实结果不能推断事实追加已完成真实SQL验收。

`tools/launch_execution_lease_store_checks.py` 的原7组读取真实专项保留；默认 `include_append=False` 仍可在046毫秒字段上运行，库中毫秒资料向后兼容。另显式 `include_append=True` 才开启4组新追加专项，须主线选择精确050额外迁移，并核正式050文件与实际两列precision=6；不是根据环境自动推断。工具自建原validate/execute202完整039来源，运行头/事实始终为明确SQL技术样本，固定证据字典逐项核语义/请求关联/阶段/时间/hash，不只抄hash，不是正式生产身份或Meta证据来源。

## 受控历史事实追加（实现、真实待验）

`append_verified_fact(session,actor_id,fact,request_id)` 只接受原精确AttemptFact，不接sequence或recorded_at。默认authority缺失在SQL前503；须单独 `HISTORICAL_FACT` grant 和完整事实验证收据，不能借 `RECOVER_EXPIRED` 或现广告写动作冒充历史证据身份。

锁序为taskclock→task→preparation共享锁→command/node/runtime→原不可变attempt。当前运行头可以已进入更高attempt/fence，不能以现广告写权限丢弃旧已发生事实；但原尝试必须存在、来源/完整manifest/command规范hash/冻结身份精确匹配，不能向尚未发布的未来或孤立attempt追加。

稳定event在tenant范围内唯一。已有事件须全部fact字段精确相等并重新验证历史证据，返回原sequence/recorded_at；异body409 EXECUTION_FACT_CONFLICT。同command锁保护服务器自增sequence，不读客户端序号，不 INSERT IGNORE。原fact与确定UUID5审计ID及outbox三表由外层同一事务提交；新事实写失败调用方必须整笔回滚，Store不擅自commit。重放还核原审计/outbox存在，不能把只有fact的损坏行当完整成功。新请求ID可以重放同事件，不重写原审计的首个实际actor/request。

该方法不写runtime、command、node、task的状态/版本/更新时间、不递增taskclock或原广告attempt、不写TaskEvent、不触碰预算/对象锁。即使追加READBACK_SUCCEEDED也只是事实留档，不能直接通过此方法标成功。

050候选仅扩事实 occurred_at/recorded_at 为DATETIME(6)，保留中文COMMENT、非NULL、全部046FK/约束/触发器，不改旧事实内容。新记录原样保存 .123499/.123500/.999999，SQLnow/recorded_at统一UTC_TIMESTAMP(6)；旧毫秒自然补000。Store在追加前核实际列precision6，避免未迁移时静默舍入；只读阶段仍可读旧046毫秒。公开Task时间字段及runtime/attempt毫秒不扩散。

4组新真实工具涵盖微秒3边界/受控SQL会话跨秒重放原recorded_at及异body409、旧fence留档不变当前全字段、实际outbox1644整笔回滚并同event重试、两连接同event产生唯一fact/audit/outbox与相同原回执。SQL会话时间在finally归零，不更改系统时间。**这些4组目前尚未真实执行**，不称追加验收通过；原只读23结果继续单独保存。

## 047 独立 reconciliation lease 设计候选（未采用）

广告 `TaskNode.attempt` / 046 execution attempt 仅表示原真实广告执行尝试；只读核验不能每轮加一，未知结果也不能创建新广告发送attempt。047需另有 `reconciliation_generation`，其值只保护只读核验领取/超时/旧结果隔离，不写原公开状态枚举。

最小候选是独立reconciliation头（tenant/task/node主键、独立generation/revision、worker/claim、lease有效期、绑定原广告attempt/fence和来源hash、下次对账水位），以及必要的不可变核验轮次/结果来源记录。若复用046事实payload，必须另有精确generation→原fact关联，不能把当前核验租约fence塞进原广告fencing_token字段。

获取/续租/完成均CAS独立generation与worker/claim；旧核验代际结果可留档，不能推进当前头；同一广告原attempt/fence未变才可能进入原UNKNOWN恢复服务，且仍需原唯一证据/双审等业务门禁。到24小时仍UNKNOWN与人工标记、保留预算/锁；停止自动领取不删历史。默认无可信authority不领取，永远没有send接口或通道切换回退。

此处只是主线预留047的设计建议，未新增候选SQL、未建表、未注册服务；具体表数、来源与归档保留协议须下一轮审核，不能作为已开发或已验收项。
