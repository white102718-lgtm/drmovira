# Task事件与SSE：T2设计检查点

主线已接036、独立SSE路由、同事务快照header与专用MAC/CORS暴露。真实20/20（10.87秒）、Cookie扩展25/25（12.66秒）、数据库边界扩展32/32（16.30秒）已通过，回执分别为`python-task-event-stream-http.json`、`python-task-event-cookie-http.json`、`python-task-event-boundaries-http.json`。前端独立解析器与详情组件已准备，真实SSE页面尚未验收；自然慢TCP、跨副本限流与生产任务来源仍未验收。下文准备阶段与提案保留历史依据，不覆盖本段实际结果。T1十万节点24/24仍是当时固定源码的独立容量证明，不能改写成当前所有事件与执行能力验收。

## 已有合同与本次边界

依据原`contracts/WORKFLOWS.md:105`、OpenAPI的`GET /tasks/{task_id}/events`及TaskEvent：事件固定event_id、sequence、schema_version=1、task_id、task_revision、node_id可null、state、occurred_at、request_id。每Task序号递增；保留7天；过期Last-Event-ID返回410 EVENT_CURSOR_EXPIRED；客户端GET快照后续传。未知或错Task的合法UUID，在该Task授权后统一400 EVENT_CURSOR_INVALID，不泄露其他Task存在。

主线已批准named `SCOPE_REVOKED` observer控制帧，data严格为`{"code":"SCOPE_REVOKED"}`，不带id、sequence或虚构Task状态。每批业务数据仍是原TaskEvent，不扩展其schema。取消、重试、恢复、平台执行不随T2设计自动授权。

T1 Task读取冻结plan版本的投手owner/team。operator_user_id筛选该冻结投手所有权；created_by只是提交审计，Worker不是任务拥有者。每次授权仍查当前身份、菜单、tasks.read及当前组织范围，不用快照保留已撤授权。

## UUID4不能由floor还原

事件UUID4没有时间或序号含义。只保存`retained_from_sequence`，删除旧payload后，拿到一个UUID无法判断它属于本Task的已过期事件，还是从未存在或属于别的Task。不能把全部未知UUID回410，也不能把全部已删真游标回400。

建议036新增独立最小游标目录，先只设计：

- `orbit_task_event_cursor`：tenant_id、task_id、event_id、sequence、occurred_at、expires_at。主键`(tenant_id,task_id,event_id)`，唯一`(tenant_id,task_id,sequence)`；可另有`(tenant_id,event_id)`唯一约束与原事件保持同租户ID唯一。FK到Task；无state、正文、错误、凭据、node payload。
- `orbit_task_event_retention`：每Task的裁剪floor/最后裁剪序号及revision，用于批量连续性核对与并发裁剪；它不能替代UUID目录。
- 新事件与Task/Node更新、递增sequence、目录行、payload、审计/outbox必须同事务。每Task锁序统一为当前身份授权→Task行→retention行→事件/目录写入，先整理所有未来事件写方；不在SSE等待期占锁。
- 036迁移只从仍真实存在的event行回填目录，不捏造已删除事件。T1目前尚无清理者，已有行可完整回填；迁移前须核验目录与event等量/同ID/同sequence，在迁移窗口阻止并发新事件写方漏双写。不可在线上先放清理后补目录。

目录身份记录至少保留至原Task获准删除/归档生命周期结束。原合同没有Task删除期限，本设计不擅设30/90天清掉墓碑。若删除目录而Task仍可读，就无法无限期保持真旧410与未知400的精确区别。该存储成本是原UUID4协议的实际代价，不能声称有限floor能够解决。

## 七天与快照续传的待裁决边界

以数据库UTC可信时钟计算`expires_at = occurred_at + 7天`，`now >= expires_at`视为过期；是否清理完成不改变过期判定。查询目录必须带当前tenant与已授权Task，错Task游标不跨Task查出解释性信息。payload尚在但已到期也返回410。

还有一个原合同组合边界需要主线裁决：一个七天没有新事件的Task，其GET.latest_event_id自身已过期。若严格拒绝所有过期游标，GET快照→用latest续传仍410，将形成循环。只凭“它恰好是latest”悄悄接受，会改变原410规则；把最后一条payload永久保留也不是已明确的七天裁剪。

建议最小技术补充是**快照续传凭证响应头**，不改Task DTO或事件ID：经授权GET完整Task时，在同一短事务取得revision/latest_sequence/latest_event_id，响应头返回MAC绑定tenant/actor/subject/auth指纹/Task/revision/sequence/event_id的checkpoint；SSE请求可携该checkpoint头及相同Last-Event-ID。该凭证仅证明客户端刚取得该持久快照，不授额外权限；服务端仍实时authorize，再从该sequence之后读取。普通过期Last-Event-ID始终410；只有已核验快照checkpoint进入“快照后订阅”路径，不重放过期payload。MAC需独立用途，具体名称与是否加时效须主线批准，不能自行硬编码TTL。原API未列该header，因此这是待批准技术扩展，尚未实现。

不批准该扩展时，必须明确另一种原合同兼容裁决，不能交付会循环的410→GET流程。不能通过客户端无Last-Event-ID重连绕过历史缺口而假装连续。

## 读取、裁剪与并发一致性

1. 首次HTTP进入时校验格式、会话与当前Task范围，再在短事务内解析Last-Event-ID目录、数据库时间、保留水位和最多200条payload；未知UUID400、真旧410均在发送HTTP200之前确定。没有cursor时的“从何处开始”也须明确：建议发送当前仍保留的首批并按真实sequence续读；若有已裁剪历史须先GET快照，不能无声补成完整历史。
2. payload清理每事务最多1000行，按`occurred_at/tenant/task/sequence`索引选候选，逐Task按固定顺序取得Task/retention锁，确认过期后删除payload并推进真实连续floor。目录不删除。分批提交，避免跨全部租户的大事务。多个Task锁按UUID排序，写方同序；不可先锁payload再倒取Task锁。
3. 读批在同一个一致事务内完成目录判定、floor核对和payload读取，不把两个无锁SELECT拼接成“没有缺口”。可用Task SHARE锁与清理Task UPDATE锁串行保护该批，不阻塞等待周期；下一轮重新取锁与当前时钟。
4. 如果先判有效后裁剪、或者发送缓冲期间跨过期边界，下一批须重新检查cursor和预期sequence。不得把缺行当没有新事件。响应流开始后HTTP状态已不能改为410：建议关闭流，由客户端使用最后真实event_id重新连接，在新HTTP上得到410并执行快照恢复；是否另加命名过期控制帧待主线决定，不虚构TaskEvent。
5. 从数据库已读出的最多200条是内存批次，不继续持锁等待网络。每次向客户端实际交付下一批前重新授权；本批读取事务授权成功到网络传输之间存在物理竞态，不宣称绝对零延迟撤权。应缩小批与发送时间并给真实撤权延迟证据。
6. 当Task在批间增加事件，按最后已发送sequence读取后续。事件和Task/Node状态更新同事务，禁止先发消息后提交。rollback不能消耗外部可见事件或制造永久序列缺口。现有T1仅初始sequence1，不计后续状态写方已经完成。

## Observer与会话撤权

SSE使用原会话，不把Last-Event-ID/checkpoint当鉴权凭证。每批和空闲轮询都重新校验：会话有效、身份auth_version、tenant/subject、launch菜单、tasks.read、当前角色/团队/managed范围以及冻结owner/team是否仍可读。Task越权首次读取404、无动作403；已经打开的observer失去范围或权限后只发送`event: SCOPE_REVOKED`与上述固定data，随后关闭，不带原Task字段或后续事件。

采用每条流单消费者、短事务轮询的首个可验证实现；空闲鉴权检查周期建议最多1秒作为待真实测试目标，不作为原合同新授权TTL。1秒周期是实现参数而非“1秒内权限仍有效”。发生DB/Redis/鉴权依赖故障时失败关闭，不用旧context继续发送。连接断开立即取消轮询与未开始事务；不因客户端断连而生成取消任务。

原客户端1/2/5/10秒退避和最长10秒轮询须由前端真实实现。T1当前仅读取轮询，不宣称已有SSE重连、重复sequence去重或缺口恢复。observer控制帧属于该连接，不能写入全局event表或推进Task.sequence。

## 存储、连接与内存上限

目录每事件保留UUID/序号/时间和必要索引，实际字节必须通过真实information_schema/表空间/进程观测测量，不能将字段名义字节冒充磁盘成本。量级为O(Task生命周期事件数)，不是O(7天事件数)。例如一千万条墓碑至少带来一千万条多索引行；具体GB只能实测后报告。100000节点不限制事件数，节点重试/核验会产生多次事件，不能用节点数推断墓碑上限。

需要租户级事件入库配额与容量告警；达到存储硬限时，状态写事务必须明确拒绝/阻断并保留既有状态，不能删除目录或虚写成功。配额数值与平台级任务生命周期待容量验证和产品决定。清理作业未运行不改变读取七天规则，但会占用磁盘并告警，不能称“七天清理已启用”。

每批200条、单条TaskEvent严格固定schema、禁止原异常正文；每连接只保留一批与最后sequence。每用户/租户/进程活跃流、待发送字节、连接期限需有界，达到限制返回明确429/503，不无限创建Task。初始建议测试小上限并测200/1000并发 observer 的连接/DB/Redis成本后定值，不凭空声称已具备生产容量。慢客户端发送超时关闭，不能持SQL锁拖累全部任务。心跳只用SSE注释，不含Task字段。

## 拟真实验收矩阵与发布门槛

- 原TaskEvent字段逐字、实际单调sequence、同事务Task/Node/outbox一致、回滚不外发、多个并发写方不重号；T1完整manifest原节点不改写。
- 七天前/精确边界/后一毫秒、payload未清理仍410、已清理真游标410、合法未知UUID400、其他TaskUUID400、先授权不泄露foreign事件；目录回填无漏重。
- 清理与读取真实并发、批中/批间跨期限、清理多批中断重启、rollback、两清理者竞争、删除Task生命周期FK规则。
- 超过七天无新事件的Task：410→GET→核准checkpoint或其他已裁决机制→新事件续传，不能无限循环或无游标跳过缺口。
- 三角色/Task-only角色、USER所有权、TEAM显式管理范围、跨租户、撤tasks.read/菜单/身份/会话/团队、空闲与持续事件中撤权，真实控制帧不含id/sequence，撤权后GET拒绝。
- 断网退避、重复sequence去重、缺口快照、旧响应不覆盖、新旧连接并存清理；三个视口真实浏览器，不用route.fulfill假成功。
- 7天事件高水位与目录长期成本、20/200/1000 observer并发、慢消费者、超限、DB故障、Redis故障、进程退出，实际OS观测必须注明采样的进程和范围。

036目前仅预留。待主线确认快照续传边界、MAC用途、初始无cursor语义及受控资源参数，再落独立event store/routes/清理工具与专项；不先注册半成品SSE。

## 当前已批准并实施的独立检查点

上方“仅预留/待批准”为设计历史。主线现已批准036、独立MAC用途`TASK_EVENT_CHECKPOINT_V1`、60秒checkpoint及同名`X-Task-Event-Checkpoint`请求/响应header。checkpoint绑定真实actor授权fingerprint/tenant/Task/revision/latest_sequence/latest_event_id；允许快照revision/sequence不大于当前，不能要求完全相同而令高频事件Task重试饥饿。已读快照之前的过期事件不重放，快照之后未读事件过期仍410，旧latest本身过期不再造成GET循环。原DTO不变。

036只从真实event回填最小UUID目录，单语句INSERT触发器保障冻结T1初始事件和后续事件与目录同事务；retention行在维护时于Task X锁后惰性创建。正文七天逻辑判定与清理分开，目录无自动淘汰，维护每批最多1000；所有维护先Task X锁，避免双SHARE升级死锁。当前仅提供内部显式调用，不称后台清理已自动托管。

新独立模块：task_event_contract/store/stream/routes/session/publisher。publisher生产默认TRUSTED缺provider即503；受控ISOLATED_TEST仅UUID库内将一个未发送节点及Task置RUNNING，原子event/目录/audit/outbox，不能因此称平台运行成功。没有任意事件写HTTP，也没有生产状态汇总来源。Task/Node全部状态迁移与汇总仍须后续真实来源和合同验证。

observer每帧发送前及慢发送期间每0.5秒重验当前会话和权限；慢发送2秒超时取消，空闲0.5秒轮询；连接60秒有界关闭重连。进程最多64连接、每actor最多4连接，每批200条。它是首个受控实现参数，不是生产容量或跨副本全局限流证据；共享限流/真实大并发尚未实现。连接退出取消待执行事务并回收名额，鉴权依赖故障关闭，不发旧Task数据。会话/范围401/403/404转固定observer SCOPE_REVOKED帧，无业务sequence。

主线接线清单：登记MAC用途；注册task_event_routes.router；原GET detail在同一个session.begin内取得payload后调用TaskEventStore.checkpoint_for_detail并写响应头，不能另事务拼接header。全局若依PreAuth及yield DB依赖是否跨完整stream持初始只读事务须主线审核；本新路由所有自有会话均短事务，不能因此声称全局层已排除。Bearer每帧使用原插件会话校验器不续期、Cookie每帧由ensure_cookie_current重验。真实Cookie退出/提供者撤销/慢消费者测量仍待专属证据。

纯测29/29、Ruff与编译通过。专属工具`TASK_EVENT_STREAM_CASES`14项、`run_task_event_stream_checks(client,admin,headers,password,cache,database,cases)`；独占native IDs990380/990381/990382，真实角色API与登录，无launch.read借权。真实计划总数由主线按初始化5+14+退出1=20登记，不同T1合算为SSE验收。时间夹具明确SQL八天/一天注入，不称实际等待七天或真实跨日；目标撤权延迟<2秒需真实网络测量。当前尚无SQL/SSE通过回执，源码与工具ready后冻结供主线串行。

Cookie初次流请求先在显式短会话调用原external resolver绑定Cookie上下文，后续每帧仍复核持久session；Bearer用原非续期插件校验。新增两项纯测使用注入认证服务验证调用协议，不计真实Cookie/IdP成功。首轮新增测试直接导入生产router触发缺少私有JwtSettings，27通过/2失败保留在.runtime/task-event-unit-attempt-01.xml；抽独立task_event_session适配并注入测试依赖后29通过，未向环境或仓库塞测试凭据。全局静态核对server.py FastAPI没有全局dependencies、ORBIT为直接include_router，原PreAuth为各原生router自行注册；新SSE自身不挂yield DB依赖。真实会话/DB连接观测仍待主线，不能将静态核对当网络验收。

## 主线首次真实接线与quota工具修正

主线已登记MAC、router、同事务GET checkpoint header及CORS公开header，首20档实际16PASS/1FAIL/3NOTRUN，回执`evidence/python-task-event-stream-attempt-01.json`；前11个新增组（含真实撤权<2秒）已通过，quota第5连接状态断言失败。失败回执未含具体actual值，不能推断一定是200。

本机真实httpx.HTTPTransport/httpcore HTTP1解析器+内存network backend已确证：临时iter_lines generator回收可关闭底层网络流，而Response.is_closed仍False；普通MockTransport没有该连接关闭链，不能拿它排除问题。专属工具定点同时持有4个manager/response/iterator，至第5请求严格429断言完成再finally关闭，保留原2秒真实断连回收复验。错误诊断只加numeric actual/expected，未修改生产quota或放宽状态。详情GET现带真实Origin并严格检查checkpoint存在及CORS expose_headers明确包含它，不新增虚构CASE。

四项连接协议纯测与八项边界工具纯测共12通过；它们是内存network替身，不能据此将真实20档记通过。修复后全部工具再次冻结，真实20→Cookie25→Boundary32由主线串行执行，结果以新回执为准。
