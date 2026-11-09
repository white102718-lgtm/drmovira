# T2数据库、裁剪与checkpoint边界专项

当前七组真实边界已随主线32/32、16.30秒通过，证据`python-task-event-boundaries-http.json`；blocked_cases为空。空闲流21次采样未见同trx跨一秒，精确DB七天前1毫秒200、等号/后1毫秒410；清理1644回滚、实际1205锁竞争、双发布序号与checkpoint边界均通过。SQL会话时间夹具不代表真实跨日等待，21次观测不推广为所有负载下无长事务。纯测单独支持工具断言，真实HTTP迭代器必须持有至采样后再读心跳，不能以关闭流取得假通过。

## 接线与最小前置

入口`run_task_event_boundary_checks(client,admin,headers,password,cache,database,cases,*,cipher)`；导出`TASK_EVENT_BOUNDARY_CASES`7项。cipher是主线当前UUID应用使用的CredentialCipher，仅内存使用，不能打印或写证据；用它构造实际合法MAC但已到期的checkpoint，不等候60秒、不更改服务端时钟。

仍要求`127.0.0.1:13306`与当前`orbit_py_it_<32hex>`库、应用through036、原Task GET checkpoint及SSE已注册。原生990384独占，存在即拒绝；真实角色API只给launch/tasks.read，数据角色TEAM_ADMIN且显式管理同团队。真实Task来源为隔离PLAN版本与非空B DAG，生产provider仍503，无平台请求。

主线只需新增工具导入/7个CASE与串行调用，保存返回metrics；不需要修改任一生产源或放宽数据库授权。所有Task/事件/身份及受控触发器只在本UUID库；临时故障trigger在finally删除，独立SQLAlchemy engines均dispose，主线最终drop库。

## 七个有界真实组

1. **pythonTaskEventIdleStreamNoSameTransactionBeyondOneSecond**：真实SSE开流并取得心跳，独立admin每100ms采样2.2秒，将INNODB_TRX关联PROCESSLIST并筛当前UUID库、排除自己的观察连接；只记录trx_id连续观测寿命、数量、锁数，不输出SQL文本或参数。不以Sleep连接数判断长事务，不将不同短事务累计为一条；同trx_id连续观察超过1秒真实失败。记录样本数及最大连续寿命；这是本采样窗口内证据，不代表绝对没有亚采样间隔事务。权限拒绝仅1142/1227记录blocked_cases，此CASE不追加PASS；其他errno真实失败。主线须把对应CASE记NOT_RUN/阻断并保存其他通过项，不能为凑绿修改计划数。
2. **pythonTaskEventExactDatabaseUtcSevenDayMinusEqualPlusMillisecond**：取得实际目录expires_at；仅在独立工具连接`SET timestamp`至该时间-1ms/等号/+1ms，先断言`UTC_TIMESTAMP(3)`确实精确固定，再调用原TaskEventStore.start读取真实MySQL。-1ms接受、等号与+1ms精确410 EVENT_CURSOR_EXPIRED。固定的是工具SQL session，不是HTTP服务连接或服务器全局；不能称实际跨七天等待/HTTP时钟边界。finally恢复timestamp=0并dispose独立engine；时区只改该连接为+00:00。
3. **pythonTaskEventDeleteFailureRollsBackPayloadAndRetentionWatermark**：受控SQL把独占Task事件移到八天前（payload/目录一起），BEFORE DELETE trigger注入1644，执行原purge后事务回滚。真实检查payload=1、目录=1、尚未建立retention行仍=0；未将失败清理写为完成水位。
4. **pythonTaskEventReaderAndPurgeSerializeWithoutSilentGap**：真实读事务在同Task持有SHARE；另一真实事务将自己的innodb_lock_wait_timeout设1秒后执行原purge，必须取得实际1205锁等待超时，不能只凭asyncio任务暂未调度就称存在竞争。读事务结束后重试purge真实删除1行；已读sequence后的读取合法空、未读过期范围仍410。工具设置只属于独立engine连接，最终dispose，不影响HTTP池。
5. **pythonTaskEventConcurrentPublishersKeepTaskNodeSequenceDirectoryAndAuditConsistent**：同Task两个ISOLATED_TEST publisher并发，5秒有界完成；真实Task revision/sequence=3、两节点RUNNING、三条事件/目录/审计/outbox一致，事件(1 QUEUED,2 RUNNING,3 RUNNING)，external_id仍null且attempt=0。不宣称真实平台已运行，也不覆盖全部Task/Node状态汇总算法。
6. **pythonTaskEventActuallySignedExpiredCheckpointRejected**：用当前真实MAC解出刚读header的claims，仅重签为已过期TTL，向真实HTTP带合法Last-Event-ID提交，精确400 EVENT_CURSOR_INVALID。它证明服务端拒绝实际合法签名过期checkpoint，没有把伪造签名拒绝当期限测试。
7. **pythonTaskEventReadableCrossActorCannotBorrowSnapshotCheckpoint**：同TEAM管理角色真实GET同Task先200，然后借root签发checkpoint请求SSE，精确400 EVENT_CURSOR_INVALID；先证明对象可读，避免404遮住绑定逻辑。

返回metrics只含安全数值/固定枚举：blocked_cases、空闲事务样本与寿命、SQL时间三个偏移/状态、清理注入errno与计数、真实1205等待秒数、两个publisher耗时/版本/节点数、两个checkpoint拒绝状态。不会返回Cookie、Key、MAC、原始SQL或平台ID。

## 依据与限制

MySQL官方说明SET timestamp影响NOW类时间值，UTC时区与DATETIME语义见[系统变量](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html)和[日期时间函数](https://dev.mysql.com/doc/refman/8.0/en/date-and-time-functions.html)。工具不只依赖文档推断，先核真实UTC_TIMESTAMP(3)完全等于固定毫秒；不符合即失败，不能静默改成近似阈值。

数据库观察需要现有账号可读取INNODB_TRX/PROCESSLIST，不增加任何权限。该工具覆盖当前UUID库的实际事务，不会凭采样证明所有生产副本或所有负载都无长事务。自然OS慢TCP背压、200/1000 observer容量、长期墓碑磁盘成本、生产IdP外部撤销、全部任务状态来源/平台执行仍独立未实测；阻塞ASGI-send纯测不能补成自然慢网验收。

边界工具预审修正：空闲观察必须强持HTTP响应及iter_lines迭代器至采样结束，再实际继续读keepalive，不能只用response.is_closed或四个Sleep连接数判断流仍存活。当前本机真实httpx/httpcore HTTP1协议纯测证明临时generator回收会关闭底层network stream，而response.is_closed仍可为False。独立内存network backend的4项协议测试包含此反例、四连接保活/异常清理及采样后续读；与原8项边界工具纯测合计12项通过，不计真实MySQL或服务端quota验收。Boundary尚未真实执行，无伪造历史失败回执。
