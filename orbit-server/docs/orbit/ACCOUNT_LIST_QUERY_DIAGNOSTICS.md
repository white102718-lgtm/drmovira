# 账户列表首屏技术诊断

仅隔离测试child显式调用：
`uninstall = install_account_list_query_diagnostics(output_dir, isolated_test=True)`。
仅布尔True可安装，1/字符串不行；默认导入无Store或配置副作用。
主线负责保证实际隔离UUID数据库、安装时机与关闭，不新增生产入口。

只记录cursor为空、identifier为空的首屏list，250页后续cursor业务仍正常读取但不采样；
这样四档20并发×10共800首屏都保留，不会被分页占满1000上限。
只允许server/.runtime/account-list-query-profile/<小写32hex>目录，逐级拒symlink和Windows
junction/reparse、路径逃逸。每请求随机技术文件名，既有条目也计入1000上限。
超限不采样但仍执行原业务；`uninstall.summary()`返回first_page_only及recorded、
dropped_cursor、dropped_identifier、dropped_limit技术计数，不包含业务条件。

记录固定SQL标签的execute次数/成功失败数、总/最大墙钟、rowcount（未知null，绝不fetch结果），
list总墙钟、execute总墙钟和non_execute墙钟；后者不是CPU，可能含排队/其他await。
只读取规范page_size枚举和最终items长度，不写SQL正文/参数/ID/HTTP头/token/业务字段值，
不记录异常正文。SQL仅在内存匹配固定表标签。只覆盖Store.list内部，不包含路由前登录鉴权、
事务提交、响应编码/压缩/发送或HTTP客户端等待，不能将此报告冒充完整HTTP分解。

ContextVar只为本list段统计同步matches_current_seal真实次数与同步墙钟，非执行结果。
不同session/Task隔离；同session重叠或递归拒绝，避免包装栈相互覆盖。
finally无论成功/异常/取消均恢复原execute：原来无instance属性则delattr，有则恢复原值；
并reset ContextVar、移除运行标记。uninstall恢复原类list和模块seal函数；若包装被其他方
替换则拒绝覆盖，不悄悄撤销别人修改。应待请求结束后uninstall；重复uninstall为无操作。
诊断写失败不覆盖原返回/异常，不打印错误正文。落盘和包装有开销，不拿诊断档当容量合格证明。

28项专属纯测试覆盖路径、symlink/reparse、精确True、返回/结果透明性、敏感标记不落盘、
execute属性恢复、异常/取消、并发上下文、递归/共享session重入、重复安装、首屏采样/限额
与写失败。未实际执行HTTP/数据库/容量；主线负责真实接入。


## 同请求ASGI外层关联（新增，尚未真实HTTP验证）

`app = wrap_account_query_http(app, output_dir, isolated_test=True)`；原install接口不变。
必须同一个guard输出目录，单进程隔离child显式安装；不改应用、runner或业务响应。
只GET精确/api/v1/accounts/extended且cursor为空采样，query最多16KiB只检查cursor键，
不保存URL/query/headers/status/body；lifespan、非目标及后续游标请求全透明传递原scope、
receive、send。目标仅包装send，不调用receive，不修改任何ASGI消息或异常。

独立ContextVar携带随机32hex技术trace及同一个请求字典；Starlette child Task继承此引用，
内层list把自己的报告附入该字典，不另落盘。最终一请求一文件schema2，HTTP/list的
technical_trace完全相同，不以不同请求分位数相减。两层共享弱引用quota对象，既有文件
与在途预留共计最多1000；并发/递归拒绝重复关联。独立list模式仍原schema1。

报告含相对于HTTP入口的list_enter/list_service_exit/list_wrapper_exit、response.start
send前后、最后body send前后、app_end；缺少阶段为null，不用0伪造发生。phases给出
before_list、原service、list_wrapper、after_list_to_response_start、response_start_send、
response_start_to_last_body、last_body_send、app_total；另send_seconds和body_send_seconds
分别累计全部send/全部body的await墙钟。它们均非CPU，send完成不承诺客户端收到网络数据。

ASGI模式最终安全落盘在app_end记录且上下文reset之后，**不包含在service/list_wrapper/
app_total中**，明确output_deferred_after_app_end=true；不能捏造“list已含落盘”。
同步落盘只一次、固定有界报告/≤1000文件，不创建后台cleanup Task；文件系统操作没有
可强制的OS墙钟上界，磁盘阻塞也可能影响其他请求事件循环，因此诊断有扰动，不能将此档
当正式P95合格证明。失败写盘不覆盖原返回/异常/取消，原execute/context仍恢复。

新增ASGI测试覆盖同trace合并、原消息/receive身份透传、多chunk、无list阶段null、
异常/取消、写失败不遮原错、共享限额、编码cursor、child Task及并发上下文隔离。
总40项纯测试，真实接入及判读由主线完成。


## 精细阶段显式安装（新增）

`uninstall_stages = install_account_query_stage_diagnostics(output_dir, isolated_test=True)`；
它和原list installer及ASGI wrapper共同使用，原接口不变。同目录guard且仅精确True。
完成所有请求后分别uninstall_stages/uninstall_list；不改生产文件、依赖注册或连接策略。

固定标签：native_auth_resolve、rc_context_enter/exit、rc_checkout、rc_isolation_options、
rc_transaction_exit、rc_connection_exit/close、rc_isolation_reset、json_response_construction。
每标签输出calls/failed/cancelled/total/max、首入末出及最多64个相对时间区间；
嵌套区间不能直接相加当总耗时，可在同trace中计算独占或剩余部分。
计时均为墙钟，包括异步等待和驱动，不声称CPU或单一锁等待。

原FastAPI Depends已捕获get_current_user对象，直接替换该classmethod不会改变既有dependant。
因此只包运行时动态查找的LoginService._resolve_current_user（保留classmethod形状和原参数），
只标native resolver部分；未经过该函数时native_resolver_observed=false，Cookie和完整
CurrentUserDependency剩余部分仍UNKNOWN，不伪造覆盖。没有检查或输出token参数。

只包路由模块现有read_committed_session别名，原CM照常执行，yield原session对象；
_RC ContextVar持有该CM实际connection/session身份，仅对该连接计checkout、原隔离设置、
退出/关闭。原MySQL_asyncmy继承的reset_isolation_level仅在同连接close且同dialect时同步计时；
不读DBAPI参数或新增SQL，不更改默认/READ COMMITTED策略。原继承方法卸载时delattr还原。

AsyncSessionTransaction.__aexit__只在self.session为该RC session时计时，名称为事务exit，
可能提交或回滚，绝不统称commit。JSONResponse.__init__只围绕原同步构造，保留对象、
参数和headers，不读响应body。close原任务/取消/异常处理不变，本工具不新建cleanup Task。
任何诊断selector自省失败只不计该段，不替换原结果/业务异常。

安装先建立全部补丁计划再应用，失败回退已应用部分；卸载先核全体仍是自己的包装再精确
逆序恢复，不覆盖其他人的修改。无目标HTTP ContextVar时原方法直接透传；并发请求及
Starlette child Task保持同trace且RC上下文隔离。精细阶段随最终单份schema2落盘。

当前49项专属纯测试通过（含原40），覆盖descriptor/继承形态恢复、原返回对象、原消息、
重入/限额、非目标无计时、native/RC异常取消、selector自省异常不遮业务、并发RC隔离。
真实公开HTTP精细阶段尚未运行，不用纯测试替代容量/退出实证。

## RC checkout 的池细分（独立显式安装）

新增 `install_account_query_pool_diagnostics(output_dir, *, isolated_test=False) -> uninstall_pool`，仅精确 `isolated_test is True` 可用，相同runtime/32hex路径护栏。主线接入顺序：原 list install、stage install，**然后 pool install**；finally **先 pool uninstall，再 stage uninstall**，避免同一 AsyncConnection.__aenter__ 包装恢复顺序冲突。默认导入不加载生产配置、不安装任何钩子。

本机SQLAlchemy 2.0.55 源码核对：`pool/impl.py QueuePool._do_get` 先 queue.get(wait,timeout)，非阻塞 Empty 是可能建立新连接的正常路径；`util/queue.py AsyncAdaptedQueue.get(block=True)` 也先尝试 get_nowait，只有实际空才 await。因此不把 block=True 的全部耗时说成真实排队等待，不把 Empty 当池耗尽或错误。

只在已绑定的同一个 RC AsyncConnection 的 __aenter__ 期间，用 ContextVar 绑定其真实 engine.sync_engine.pool、该 pool._pool 与 pool._dialect。固定钩子：

| label | 本机方法 | 边界 |
| --- | --- | --- |
| rc_pool_do_get | QueuePool._do_get | 包含queue与可能的物理连接，可能递归，不能与子段相加 |
| rc_pool_queue_get_nonblocking | AsyncAdaptedQueue.get(block=False) | Empty 单列 empty 计数，不计 failed |
| rc_pool_queue_get_blocking | AsyncAdaptedQueue.get(block=True) | 可直接拿现成连接，也可greenlet await；不是纯等待计时 |
| rc_pool_physical_connect | MySQLDialect_asyncmy.connect（继承方法） | DBAPI connect 墙钟；不包含全部connect事件/初始化，不能称总新连接成本 |
| rc_pool_pre_ping | MySQLDialect_asyncmy._do_ping_w_event（继承方法） | 实际调用才计时；新连接可能跳过ping；不读响应/SQL |

所有区间沿原 detailed_stages 的同trace有限 intervals。QueuePool、queue、dialect 精确对象不一致时不计；非目标/lifespan原样。只支持 QueuePool 家族（包括 AsyncAdaptedQueuePool）；形状/自省未知时继续原调用、报告 pool_checkout_observation=UNKNOWN，不更换池或执行方法。真实观测后为OBSERVED。

`pool_checkout_samples` 每请求最多64项，只记录 checkout 调用前后固定整数 size、checkedout、overflow、max_overflow 及 RETURNED/FAILED/CANCELLED。它们是不同瞬间的共享池采样，不是峰值、同一连接归属或因果证明。负overflow是合法值，-1的无限maxoverflow也保留。自省异常/非整数时counts为null；不记录URL、连接ID、pool身份/对象repr、SQL、参数、header或业务值。

取消/异常保留原对象，ContextVar finally reset；同步方法内greenlet等待的 CancelledError 单列 cancelled。卸载先检查所有包装identity再恢复；原继承descriptor采用delattr恢复继承，不覆盖其他人后加包装。没有更改超时、连接池大小、worker、驱动、事务或隔离策略。

本轮诊断纯测试 **59/59 PASS，1.58秒**：保留原49项并增加10项；含嵌套/非阻塞Empty、固定计数、继承恢复、不同pool/非目标/不支持形状、原异常/取消、并发独立trace及真实 AsyncAdaptedQueue+SQLAlchemy greenlet 的阻塞唤醒/取消。Ruff check/format PASS。没有运行MySQL、Redis、HTTP容量或Git。后续实际仪表档仍有诊断开销，不能作为正式容量合格证据；原31PASS后200档P95=1.012793失败保留。

## 061 实际 pool 细分档分析（18344385…）

安全聚合：`.runtime/account-list-pool-analysis-18344385e865460fbb551a55cab5011d.json`。原失败回执和容量报告 `docs/orbit/evidence/python-account-query061-pool-failed.json`、`python-account-query061-pool-capacity-report.json` 保留。只有安全计数/时长/随机技术trace/源文件SHA256进入新聚合，不复制EXPLAIN的SQL正文、参数或业务ID。

809报告：schema2 808、schema1 1；24execute且items等于page_size的完整首屏801条。按完成文件mtime取最早200行首读1条单列，排除另外8条非暖样本，得到**800暖请求，四档各200**。全部OBSERVED，每请求一个pool checkout sample，24execute、seal调用0。原客户端四档P95为643.843/703.383/994.766/**1005.131ms**，结果仍FAIL；它没有与server随机trace关联，不将client/server不同样本P95相减。

### 实际新增shape与同请求子段

下表各时长都是该label在**全部200请求中缺席记0**后的均值（ms），不是把嵌套相加。physical connect有观测的条件均值另列，不能用全量P95=0声称连接免费。

|page_size|checkout|pool do_get|queue blocking|pre_ping|physical connect全请求均值|physical connect次数/条件均值|
|---|---:|---:|---:|---:|---:|---:|
|20|38.670|32.214|31.071|6.392|1.006|8 / 25.162|
|50|42.219|36.067|34.984|6.086|.977|10 / 19.536|
|100|54.841|44.505|42.572|10.260|1.701|9 / 37.806|
|200|67.498|59.946|58.948|7.480|.865|10 / 17.297|

- 每档do_get恰好200次；blocking get恰好190次，nonblocking get恰好10次；后者Empty分别8/10/9/10次，与physical connect次数相符。Empty是原建连分支，failed=cancelled=0，非错误或超时。
- pre_ping分别192/190/191/190次，且physical connect+pre_ping次数均为200；符合fresh连接可能跳过ping，不把缺席当漏测或失败。
- blocking get至少1ms请求分别170/170/167/175，至少100ms分别15/12/13/14。block=True本身不是等候证明，但长调用配合当时池计数，已经显示**取池/队列路径存在实际墙钟压力**；仍包含greenlet/事件循环调度，未分出纯服务端或纯队列等待时间。
- before sample为size20/checkedout30/overflow10/max_overflow10的请求分别170/170/167/175；这证明这些采样瞬间已到当时配置上界，不能推成全程峰值、请求与连接一对一或所有延迟由池耗尽造成。其余checkedout低于30但overflow仍10，是共享池并发时刻差，不重写采样。
- 按**每请求先做interval union**：checkout减去do_get+ping覆盖区间的剩余均值分别.064/.065/.076/.073ms；do_get减去queue+connect覆盖区间的剩余分别.136/.106/.231/.133ms。实际checkout大部分已由这两组子段解释，不能将checkout、do_get、queue、connect和ping直接全部相加。

### 全链阶段与真正同trace尾部

200行档均值：before_list314.141ms，service341.918ms，after_list→response_start114.939ms，最后body send之后到app退出68.576ms，app_total862.321ms。native resolver均值217.231ms；本次新钩子仅细分**业务RC的checkout**，不细分native resolver自己的授权DB/Redis/其它依赖，因此不能用该217ms减去RC queue时间。

实际server app_total排序P95对应技术trace `b266e3325ac641c3a55e592ed8a3062c`，不是客户端P95那个未知请求：

- app_total1045.605ms，before_list483.537ms，其中native389.522、RC enter83.943。
- 该请求RC checkout57.143ms：do_get41.253（queue41.247）+ping15.814+区间剩余.076ms；没有physical connect。RC isolation options26.597ms。
- list323.011ms，after_list→start141.756ms，start之后到最后body27.255ms，最后body之后69.961ms。

因此该P95请求的RC队列仅41ms，**不能将该尾部全归因为取池**。另50档真实app P95请求的RC context exit246.587ms、100档的ping86.134ms，显示不同请求尾部来源不同；新聚合保留各档实际同trace样本，不从不同请求各取P95凑出“典型请求”。

### 下一最小可验证方向（尚未修改生产）

优先做一个有界诊断补口：**native授权session是否与RC业务session重叠持有同池连接，以及native连接释放时刻**，只记录技术bool/计数/区间，pool/connection对象身份只在请求内存比较，不落ID，不为了观察调用session.connection()触发新checkout。原DBSessionProvider.__call__是yield session；LoginService._get_current_user_from_db在该session查询；extended另开read_committed_session。静态路径存在双session重叠可能，但当前pool计数没有标注连接持有者，尚不能宣称已实测每请求占两条。

如该诊断证明重叠，才审查**只读native身份投影的自有短事务/连接生命周期**最小方案，保留前后token、auth_version/授权当前读取、Cookie路径和末段业务当前鉴权，不能直接close/rollback传入session（它可能被其它依赖共享或已有事务）。这比立即加pool/worker或移除pre_ping更有针对性，但当前只提出验证方向，不授权改变公共auth/session。

本档physical connect仅8—10/200次、均摊≤1.701ms；禁用pre_ping只针对均摊6—10ms且会损失原健康检查，没有本证据支持。JSON/driver/并发池大小也不盲改。先验证native租约和全链释放，不把本仪表FAIL当正式容量通过，也不拿前后不同运行P95差归因pipeline。

## Native授权连接与RC租约重叠的独立诊断

入口：`install_account_query_native_lease_diagnostics(output_dir, *, isolated_test=False) -> uninstall_native_lease`。仅精确True，沿原runtime/32hex护栏。安装顺序 list→stage→pool→**native lease**；卸载必须 **native lease→pool→stage→list**，因为native与pool都包原AsyncConnection.__aenter__，native与stage都包原LoginService classmethod。默认导入不加载生产配置或注册事件。

原调用链已只读核对：CurrentUserDependency返回原LoginService依赖，DBSessionProvider提供yield session，resolver将query_db交给原用户查询，账户extended另外创建RC连接。当前诊断不改变这两个session，不以静态调用链宣称已经实测重叠。

实现只给**该真实native query_db.sync_session实例**注册after_begin，再给其实际bind对应的pool实例注册checkout/checkin。checkout可能早于after_begin，因此请求只暂存同一HTTP observation与目标pool的至多16个候选record+相对时刻；after_begin用实际Connection已有 `_dbapi_connection._connection_record` 精确关联，才记为native租约。对象仅请求内存比较，不记录ID/repr/URL/SQL。不会调用session.connection()、Connection.connection属性、执行查询、close、rollback或新增checkout。既有事务只能从其已有 `_connections` 只读观测；没有可信checkout时刻则UNKNOWN，不能补0或猜已释放。

ASGI ContextVar跨child Task传同一observation字典，但**释放事件不靠ContextVar认领**：checkin用注册时闭包里该租约exact record识别。另一个并发请求的after_begin必须匹配当前sync_session实例；其checkout没有当前HTTP匹配也不进候选。这样避免把同池其它请求当当前native连接。事件回调全同步、不await，诊断自省异常只标UNKNOWN不掩盖业务。最多16租约和16次RC进入；超出不造完整证明。

新增同schema2兼容字段 `native_lease`：

- `observation`为OBSERVED或UNKNOWN；无native路径默认UNKNOWN，未知session/bind也UNKNOWN。
- `resolver_exit_transaction_active`为原session.in_transaction()的布尔观察，未知null。它本身不证明持有物理连接。
- `native_leases[]`：checkout_seconds（未知null）、after_begin_seconds、release_seconds（尚未观察到checkin则null）、active_at_resolver_exit（未知null）。全部相对同一次ASGI开始。
- `rc_checkouts[]`：enter/exit_seconds、outcome、same_pool、active_native_leases_at_enter/exit计数、same_active_native_record布尔/null。必须同时看observation和具体checkout/release时间；UNKNOWN下不能据零计数宣称无重叠。
- `cleanup`：NOT_INSTALLED、PENDING、REMOVED、FAILED。ASGI app结束后、报告写盘前精确remove本请求注册的三个listener，不remove任何其它请求listener；state先封闭，之后迟到事件不得改已写报告。失败不遮原异常/取消，报告仍标FAILED，uninstall只重试剩余本请求listener，仍活动/清理失败则拒绝卸载，不能静默留全局钩子。

原返回/异常/取消和真实pool保持原样。类包装全体identity检查后恢复；继承descriptor删除恢复原继承。并发活动请求存在时uninstall拒绝，不拆其它请求资源；完整安装失败回滚已装class包装。

本轮针对性纯测试 **70/70 PASS，1.47秒**（原59保留+新增11），Ruff check/format PASS。覆盖checkout先于begin、确切RC同pool不同连接活跃重叠、childTask checkin、预存事务/无法认领checkout的UNKNOWN、不支持session、不同pool、非目标、异常/取消清理、两个同池并发请求不串租约、精确descriptor恢复/活动请求拒卸载、清理失败后迟到事件禁止修改已写报告及精确重试。没有运行数据库、Redis、HTTP容量或Git。真实native释放是否位于响应之后、每请求是否持两个连接，仍须主线实际仪表档给同trace证据；不得从纯协议样本或原20并发直接推断。

## 062 实际 native lease 档：同池双租约已在800暖请求证实

原回执 `docs/orbit/evidence/python-account-query062-native-lease-pass.json` 和 `python-account-query062-native-lease-capacity-report.json` 已由主线保存：44/44 PASS，133.19秒；四档客户端P95为629.722/784.436/801.893/992.033ms。**这是仪表档单轮通过，不代表稳定容量恢复**，无仪表原44仍由主线独立复验，不从不同运行P95差归因任何优化。

新增安全聚合 `.runtime/account-list-native-lease-analysis-34f2820e06854884b303d1894a94b584.json`。810报告中schema2 809、schema1 1；24execute且完整page的样本801，按完成mtime取最早200行首读1条单列，另9条非暖样本排除，得到800暖请求、四档各200。只保存安全计数/时间/当前源码SHA256，不保存SQL、参数、租户/用户/连接ID。

### 实际逐请求关联计数

以下每项均为**800/800**（各档200/200），不是根据20并发或静态代码推算：

- native_lease.observation=OBSERVED，UNKNOWN=0；cleanup=REMOVED，FAILED/PENDING=0。
- 恰好1条native lease、1条RC checkout；resolver_exit_transaction_active=true，native active_at_resolver_exit=true。
- RC同native实际pool；RC进入和返回时native活跃租约都是1；RC返回后的actual record与该活跃native record不同。
- 可信checkout事件早于after_begin；全部native checkin可见，发生在RC connection.close完成之后。
- 全部native checkin在最后body send之后、ASGI app_end之前，没有本次观察结束仍未释放的native租约。

这已经把原“默认yield session可能保留授权连接”的代码推断升级为**本档这800次原生认证路径的真实同池不同record同时活跃租约证据**。不扩大为所有用户、Cookie、缓存命中或所有接口必然如此；本诊断只认领原native resolver传入query_db，Cookie路径仍不由这些记录证明。

### 持有跨度：全部为同request配对差值

单位ms；P95为nearest-rank。没有将不同样本P95相减，也没有相加嵌套计时。

|page_size|native checkout→checkin均值/P95|resolver返回后继续持有均值/P95|确认双租约重叠下界均值/P95|最小重叠下界|
|---|---:|---:|---:|---:|
|20|412.000 / 555.125|359.679 / 487.411|225.633 / 252.676|84.706|
|50|491.100 / 693.490|429.699 / 630.907|266.994 / 316.613|147.410|
|100|545.825 / 727.270|479.429 / 651.870|295.240 / 320.782|158.375|
|200|669.768 / 933.301|587.612 / 848.212|386.693 / 536.552|222.864|

重叠下界严格采用同request的 `min(native checkin, RC connection.close 首次入口) - RC __aenter__ 返回`。特意用close**入口**，不把close内部实际checkin之后的清理时间也算成RC仍持有物理连接；所有样本下界为正。native从RC开始checkout就已经活跃，但RC等待期间还没有第二条已到手连接，故也不把整个RC checkout等待算为双连接重叠。

native checkin距最后body发送结束的均值为31.689/41.394/36.949/32.243ms；距app_end仍有20.206/24.407/24.806/30.353ms均值。由此能证明它们在响应尾部归还，不证明这些尾部时间都是数据库CPU、纯rollback成本或纯连接池等待。cleanup REMOVED证明诊断监听清理；业务租约释放结论另来自实际checkin时刻，二者不混同。

### 可实施方向仍待单独授权

当前证据支持优先审查**账户extended/details原认证的自有短生命周期session**：完整原LoginService鉴权返回已物化DTO后归还它自己创建的连接，再进原RC业务事务。不能在现原resolver直接close/rollback收到的query_db，它可能与原生controller/其它依赖共享，也可能来自已有插件事务。必须保留前后token/当前授权、原Cookie分支与业务末段重核；不改公共yield scope或扩大pool来掩盖重叠。

本轮仅分析/追加文档，没有更改生产、诊断工具或测试，也没有运行数据库/重型测试/Git。等待主线无仪表原44的结果和明确实施所有权，不因本轮通过跳过真实安全回归。
