# T2 Cookie事件撤销：独立真实专项准备

当前真实本地HTTPS IdP/Cookie五组已随主线25/25、12.66秒通过，后续边界扩展32/32、16.30秒再次通过。证据`python-task-event-cookie-http.json`与`python-task-event-boundaries-http.json`。后者实际退出/提供者停用/提供者修订撤销观察分别0.515/0.509/0.504秒，旧Cookie不能复活；不代表生产IdP或自然慢TCP。下方准备说明保留历史边界，当前共享入口由主线接线，未写私有env。

## 当前覆盖边界

原29项纯测包括checkpoint旧快照/字段边界、observer逐帧停止、阻塞send取消、空闲401/403/404、依赖503、disconnect回收、quota、Cookie首次resolver/Bearer非续期适配。Cookie适配使用注入服务，慢send用阻塞ASGI-send替身，均不是实际IdP/慢TCP验收。

原14个真实事件case待主线执行：有Bearer撤tasks.read、八天时间注入/七天逻辑过期、目录清理、checkpoint新旧版本、回滚、配额与重新连接；没有真实Cookie退出、提供者变更、自然TCP背压或数据库跨流事务观测。以下5组独立补Cookie，不把14+5合并冒称覆盖所有事件异常。

## 精确入口和前置

`run_task_event_cookie_checks(client,admin,headers,database,idp,cases,*,provider_id=None)`，导出`TASK_EVENT_COOKIE_CASES`5项。返回只有三项观察秒数的metrics；不返回Cookie、CSRF、Token、Key或授权码。现有LocalOidcFixture由主线创建/关闭，不由工具启动额外服务。主线须将现成IdP端口/CA沿用已有ORBIT测试注入，真实HTTPS发现、签名、PKCE、一次性code及callback路径全部走现有实现，不使用route.fulfill或伪成功回执。

- 严格当前`127.0.0.1:13306`和`orbit_py_it_<32hex>`库，先核SELECT DATABASE；所有身份、配置、真实非空Task仅属本轮UUID库，最终主线drop。
- 独占原生用户990383，占用拒绝覆盖；用真实角色API创建仅launch菜单+tasks.read的角色。SQL只建立隔离用户/团队映射和明确本地issuer/subject外部身份绑定，未借launch.read或系统配置权限给Cookie用户。
- 缺省真实系统配置API创建工具独占启用OIDC。若已有其他启用来源，拒绝任意停用；主线可显式传已指向同一本地IdP的provider_id，工具核唯一启用和公开settings，真实callback还会验证secret匹配。
- root Bearer只用于合法配置创建/修订和夹具准备。Cookie自身真实回调取得，Task API没有Bearer降级。外部issuer/subject映射是明确隔离fixture，不是生产自动按邮箱绑定。
- T2 MAC/header/router必须由主线先接入并应用036；本工具不改任何公共入口。保持无生产可信publisher/无平台执行。

## 五个具名真实组

1. `pythonTaskEventCookieActualHttpsCallbackTaskCheckpointAndSse`：真实HTTPS授权与callback签发Secure/HttpOnly/SameSite Cookie；session只有launch/tasks.read；Cookie Task GET与checkpoint header、真实SSE空闲心跳。
2. `pythonTaskEventCookieActualDeleteCsrfIdempotencyAndInFlightRevocation`：错误CSRF精确403 CSRF_INVALID；正确Origin/CSRF/Idempotency执行真实DELETE `/api/v1/auth/session`，200 SIGNED_OUT；同键回放回执精确相同；已开流只有observer SCOPE_REVOKED且无id/sequence，后GET精确401 SESSION_REQUIRED。
3. `pythonTaskEventCookieActualProviderDisableRevokesIdleObserver`：新真实Cookie，root以If-Match及幂等键调用真实系统配置PUT停用此独占OIDC；在途控制帧与随后GET精确401 SESSION_REAUTH_REQUIRED。
4. `pythonTaskEventCookieActualProviderRevisionRevokesIdleObserver`：真实API重新启用，重新HTTPS callback取得新Cookie；改真实配置名称使revision实际增加，旧流控制帧与GET精确SESSION_REAUTH_REQUIRED。不是只改私有SQL版本后假称通过配置API。
5. `pythonTaskEventCookieOldSessionAndStreamCannotReviveAfterProviderRestored`：真实API恢复配置字段但revision只前进；已退出及两条失效Cookie重开流分别精确SESSION_REQUIRED/SESSION_REAUTH_REQUIRED，不能恢复旧会话。

每种撤销返回`logout_seconds`、`provider_disable_seconds`、`provider_revision_seconds`：测量从撤销HTTP动作发起至客户端实际读到控制帧，包含变更请求及网络开销；目标小于2秒。它不是精确DB提交瞬间的纯服务端延迟，不声称生产IdP端到端撤销时延。成功/失败原始证据由主线保存；工具9项解析/断言纯测仅验证安全Cookie标志、严格控制帧和阈值，没有跑SQL/HTTPS/SSE。

提供者字段清理只用真实配置API，版本不回退；新建来源保留禁用审计，复用来源恢复原启用/名称。其余fixture保留供本轮审计与统一drop。IdP.subject/email在finally恢复，不影响后续主线其他专项。

## 跨流数据库事务的最小真实观测方案

不加权限、不改旧工具。主线在UUID库打开真实空闲SSE后，独立admin连接每100ms采样至少2秒；仅记录安全数值：trx_id、线程ID、trx_state、`trx_query IS NULL`、锁数量、数据库UTC年龄与观察时间。关联`information_schema.innodb_trx.trx_mysql_thread_id = information_schema.processlist.ID`并约束`processlist.DB = 当前UUID库`、排除CONNECTION_ID。不要输出trx_query正文、SQL参数、访问Token或连接凭据。

同一个trx_id跨多次空闲采样持续存活需查明；池中Sleep连接不等于长事务，不能只按连接数判断失败。新SSE每轮短事务可能恰好落入采样，须记录连续寿命，不把任何被采到的事务都误判跨流。补关联performance_schema.data_locks按OBJECT_SCHEMA筛Task/身份表锁，检验网络空闲期间没有持续共享锁阻塞真实退出/权限变更；关闭流后确认相关事务与名额回收。若现有账号缺PROCESS/P_S读取权，只阻断该观测，不能放宽权限或称零事务已证实。

静态已核FastAPI工厂无全局dependencies，原PreAuth在各原生router单独声明，ORBIT为直接include_router；新事件route没有yield DBSession依赖，认证与业务均显式短会话。但静态审查不替代上面的真实观察。

## 保留的其他缺口

自然TCP慢消费者/实际ASGI发送背压撤权、精确七天边界、清理读取并发/清理回滚、多个publisher序号竞争、大量observer与长期墓碑容量、生产IdP撤销推送、真实生产事件来源，均不由本5组覆盖。少量200帧可能全进OS缓冲，暂停读取不自动等于已经测到背压；可用受控send gate证明协议取消，但必须标明transport替身，不能冒充慢网。
