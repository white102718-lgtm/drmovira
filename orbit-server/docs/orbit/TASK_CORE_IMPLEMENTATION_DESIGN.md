# 原统一任务核心：合同核对与033最小实施提案

当前状态：T1真实主档22/22通过，十万节点容量档24/24通过，字段错误码修正后的专属纯测37/37通过；Task-only真实UI及完整三视口由主线验证中。033/035和本轮T1生产源保持冻结。容量回执对应错误码修正前固定源码，冷缓存/并发仍未测；不将只读持久协议计为生产执行或整个Task验收。账户命令与032运行时没有改名为Task，不继承旧Java验收。

## 合同与当前缺口

依据：contracts/openapi-current.json的Task/TaskNode/TaskPage/TaskNodePage/TaskEvent及原任务路径；API_SEMANTICS第43行；WORKFLOWS第5/8/10节；PERMISSIONS“自己的数据”；PRD FR-LCH-05及第9节；reference/01_修订需求与删除边界。

B线已新增Task SDK及launch任务子页，42项组件/SDK纯测通过；T1真实UI与三视口仍待主线当前回执，不将组件替身算浏览器验收。任务作为launch子功能，保留八一级业务模块。原tasks.read/cancel/retry/reconcile动作名不改为launch.*，当前入口仍应按launch菜单及原任务动作授权。

B现有`build_launch_dag(plan,*,plan_revision,allocation,compatibility,material_revisions)`输出不可变DagManifest：schema_version、plan_revision、plan_input_hash、allocation_input_hash、graph_hash、三层counts、total_dag_node_count、kind_counts、budget_totals、nodes及execution_authorized=False。DagNode包含稳定node_key、kind、parent_keys、account_id、target_key、source_pointer、purpose、configuration_hash和可空素材ID/版本；父key拓扑在前、单节点父≤100、总节点≤100000。已有64纯测试，不是Task落库或可信预检/平台授权证明。032生产provider缺失503，task_id=null维持真实含义。

021有真实plan/plan_version及ownership冻结配置；尚无完整PlanValidation、真实execute/preflight发送授权或建议提交持久来源可消费。graph_hash不等同PlanValidation.hash；ISOLATED_TEST兼容包不升级为可信平台授权。

## 分阶段最小闭环

|阶段|实际交付|明确未完成|
|---|---|---|
|T1，033独立持久核心|实际plan版本来源、内部build/manifest分块、非空真实DAG节点/父边、最终原子发布；严格GET任务/节点/列表；隔离fixture证明持久协议|生产execute、真实预检/建议来源、发送/Agent、控制动作、SSE未完成|
|T2，真实状态与事件|持久原Task/Node迁移及汇总、每Task sequence、7天事件/续传/410/撤权、前端任务列表/详情/节点/SSE|没有生产采集凭据时不称真实广告执行成功|
|T3，原控制与生产衔接|原execute真实冻结预检和当前安全校验；原cancel/retry/resume/reconcile分别实现并验收|未知写不得重发，成功节点不重建；账户独立命令仍不桥接|

T1只对主线隔离UUID库建立ISOLATED_TEST fixture来源的非发送任务；生产trusted构造器缺少真实preflight/authority provider时503，不开放浏览器“创建任意Task”接口，不让测试生产者存在可调用HTTP路径。所有GET只读完整已发布manifest；不能用空nodes占位返回“任务已创建”，也不让半DAG执行。

## 033建议表与强约束

1. `orbit_task`：tenant/id/revision、真实冻结owner_user_id/owner_team_id、source_kind/source_id/source_revision/source_hash、execution_mode、原Task.state、needs_manual_reconciliation、created_at/updated_at、node_count、latest_event_id/latest_sequence、published_manifest_id。初期source_kind只支持有真实FK依据的PLAN；SUGGESTION待其真实submitted_snapshot存储和接口明确后另接，不能只存任意JSON声称已核验。
2. `orbit_task_build`：task_id、BUILDING/COMPLETE/FAILED内部phase、producer_kind、预期node/edge/chunk数量、actual计数、schema_version、plan_input_hash/allocation_input_hash/graph_hash、规范输入文档摘要/字节数、manifest_hash、created_by、创建/失败时间。BUILDING不是新Task.state，不对外投影。接收稳定不可变输入，并且完整来源、政策/能力/预检/占号等尚未存在时不能填“已验证”。
3. `orbit_task_manifest_chunk`：task_id/build_id/chunk_no、连续ordinal起止、字节数、规范payload_hash、实际node/edge数。分块不可变；同块同hash重放无副作用，不同hash409。后台每块事务有界，不用单个100000节点超长事务。
4. `orbit_task_node`：tenant/task/id、稳定node_key、topological ordinal、原kind/state、account_id/target_key/source_pointer/purpose/configuration_hash/asset引用等内部冻结字段，原external_id/attempt/error_code/error_message/retryable/configuration_state/delivery_state/updated_at，execution_mode/no_op按已知实际语义写入。节点UUID由固定task namespace+稳定node_key生成或持久唯一映射，不因重试生成新ID。
5. `orbit_task_edge`：tenant/task/child_id/parent_id、child/parent ordinal，同租户同Task复合FK；父必须存在且ordinal<child，重复边拒绝/幂等同值，不允许跨Task外键或100以上父。总节点必须1..100000，100001明确PLAN_NODE_LIMIT，不截断。
6. `orbit_task_event`：严格TaskEvent字段及内部sequence唯一键、任务版本、来源request_id、UTCoccurred_at；另有持久outbox/清理水位。事件和Task/Node状态、revision/counter同事务，不从内存推测或浏览器时刻补成功。

索引：task主键(tenant,id)、源PLAN版本唯一(tenant,source_kind,source_id,source_revision)、owner/team+created_at+id列表索引、必要state组合；node唯一(tenant,task,node_key)、唯一(tenant,task,ordinal)、state+ordinal；edge按child读取父列表；event唯一(tenant,task,sequence)、(tenant,event_id)及7天occurred_at清理索引。无深OFFSET，所有关联显式同租户。当前source唯一若同时支持建议与计划需按来源精确区分，不将不同来源任意串成同Task。

最终publish事务须重新读取真实不可变来源版本和owner/team、核全部块序列/hash/字节/计数、真实完整有向无环拓扑及父存在、冻结源hash、producer权限/租户；缺块/坏摘要/多余节点/重复key/未知kind/计数不符均失败。成功一次才设置manifest COMPLETE、Task可见QUEUED及初始sequence事件，审计/outbox同事务。内部send gate独立保持关闭，COMPLETE不等于可执行授权。

原`POST /launch-plans/{id}/execute`的202响应是严格Task。T1不注册这个端点去返回空Task或半manifest；未来生产execute如何在后台分块未完成时满足该严格响应，需要真实冻结输入/完成发布边界明确后统一接入，不能增加未定义BUILDING状态/字段糊弄客户端。重入同plan/revision必须复用原Task，不因不同Idempotency-Key再造任务；原幂等保存2年，同key不同hash409。

## 原字段和状态必须完整保持

Task严格字段：id/revision/ownership/state/nodes/latest_event_id/needs_manual_reconciliation/created_at/node_count/next_node_cursor；execution_mode为原可选字段，有已核实来源则返回，未知不猜。Task.state只允许QUEUED/RUNNING/VERIFYING/UNKNOWN/RETRY_WAIT/SUCCEEDED/PARTIAL_SUCCESS/FAILED/CANCELLED/NEEDS_HUMAN。

TaskNode严格字段：id/node_key/parent_ids/kind/state/external_id/attempt/error_code/error_message/retryable/configuration_state/delivery_state/updated_at；execution_mode/no_op为原可选字段。kind仅UPLOAD/CAMPAIGN/ADSET/CREATIVE/AD/VERIFY/ENABLE/ALLOCATION。初始未发送节点可QUEUED、external_id=null、attempt=0、configuration_state=UNVERIFIED、delivery_state=UNKNOWN，不写伪平台ID/成功状态。错误只返回受控码/中文分类，不回平台响应、Token或SQL。

汇总按原优先UNKNOWN→NEEDS_HUMAN→运行/核验→重试等待→队列；全部终态后全成功SUCCEEDED，成功混失败/取消PARTIAL_SUCCESS，零成功且失败FAILED，全取消CANCELLED；BLOCKED_DEPENDENCY、EXPIRED、BLOCKED_AUTH按原失败规则保留原因。SUCCEEDED不表示ACTIVE，配置核验和实际投放分别保存。当前T1没有平台结果来源时不随时钟推进这些状态。

## GET、游标与首200

- `/tasks`、`/{id}`、`/{id}/nodes`、`/{id}/events`均实时校验会话、launch入口及tasks.read和冻结任务owner/team；USER只本人，TEAM为本人/显式管理团队，SUPER仍须动作。Task所有权来自真实plan版本或未来真实suggestion提交快照，不用创建者/Worker代替，也不随当前账户转移重写。
- 无菜单/动作403；已授权动作但越权任务404。权限/租户/本人或相关当前组织失效即时拒绝；分页数据快照不能缓存旧权限。发送动作未来另校当前账户、资源和能力，历史Task可读不等于当前可写账户。
- GET `/{id}`返回拓扑ordinal首200、真实node_count、还有节点时next_node_cursor；`/nodes`20/50/100/200默认50，按ordinal+ID键集。200后的任意合法节点可分页至100000，不沿用旧40000内嵌上限；parents按本页节点集合批量读取，禁止N+1。
- 建议MAC用途TASK_LIST_CURSOR_V1/TASK_NODE_CURSOR_V1，绑定当前actor/subject/tenant/角色/团队/managed/auth_version指纹、筛选/排序/page_size、冻结列表水位或任务revision/manifest_hash、after和data_as_of。当前授权每页重查，水位变化明确冲突/刷新，不跨版本混读，不擅改原scope_version为Task版本。
- 首200节点可能有最多20000父UUID；TaskPage最多200个Task若每项都内嵌200节点，最坏40000节点及400万父UUID。原文只要求详情首200；主线已批准列表nodes=[]+真实node_count+指向首节点next_node_cursor的稀疏投影。这里“稀疏列表”不是持久空Task，源manifest始终完整非空。

原list/nodes公开参数：q/cursor/page_size/status/date_from/date_to/operator_user_id/channel_id/metric_profile_id/entity_type。status只接受该领域枚举，未知422；重复/未知参数拒绝，不支持的组合422。owner过滤不能扩大当前范围；channel/profile/entity需真实冻结关联字段，不凭名字推断。主线决定T1只支持节点q为真实node_key前缀；列表非空q、两节点/列表接口的日期/channel/profile/entity非空参数明确422，并登记这些领域语义仍未完成。不做任意JSON全文包含，不自选UTC/北京时间。

## SSE与事件一致性

原TaskEvent固定event_id/sequence/schema_version=1/task_id/task_revision/node_id可null/state/occurred_at/request_id；sequence每Task递增且唯一，SSE id为真实event_id，state来自持久事件。7天事件过期由持久floor/清理水位判断，Task.latest_event_id及节点快照读取同持久版本，不以浏览器时间推进。

Last-Event-ID先验证任务当前范围，再按同租户同Task查游标；过期410 EVENT_CURSOR_EXPIRED，客户端GET完整Task快照再从latest_event_id续传。不能全局按他人事件UUID泄露Task存在性；主线已决定合法但未知/错Task游标在授权后统一400 EVENT_CURSOR_INVALID，不泄露存在性，不能当成无游标从头发送。事件裁剪与读取之间的竞争必须事务检测，不能丢事件而假装连续。

流式连接不能持长期数据库事务、账户锁或旧授权快照；每批事件前短事务重新授权并读取提交sequence。重复sequence忽略、缺口取快照；客户端按1/2/5/10秒指数重连，最长10秒轮询。撤权须发送SCOPE_REVOKED并断开，随后GET失败；每批发送前必须当前鉴权，空闲连接也要可感知撤权，不能等下一业务事件才处理。具体失效唤醒/轮询机制与实测响应延迟需T2验收，不以缓存TTL冒充即时撤权。

主线已批准T2协议边界：业务data保持原TaskEvent；named SCOPE_REVOKED控制帧data={code:SCOPE_REVOKED}，不带TaskEvent id/sequence，不伪造全局任务状态或序列。T1仍不开放SSE，后续T2单独真实验收。

## 原控制动作接力要求

cancel=tasks.cancel，retry/resume=tasks.retry，reconcile=tasks.reconcile；CSRF/CAS/Idempotency均保留。RetryTask严格node_ids[1..500]+reason；ResumeWorkflow严格reason+binding_revision。用户取消只阻止未发送节点，成功节点/已发送副作用不回滚。安全失败才FAILED→RETRY_WAIT→QUEUED，成功节点不重建，用户取消节点不随父重试复活。UNKNOWN只按非提交者双人证据核准流程，不能给“重试全部”按钮绕过。

AdsPower未提交挑战可NEEDS_HUMAN；提交后结果未知仍UNKNOWN。resume重新验证binding_revision/身份/当前安全锁和预览时效；过期未发节点EXPIRED。机器在线不等于可发送，现阶段没有这些真依赖不得模拟成功。

## T1主线依赖与真实专项提案

主线已登记launch下tasks.read=310206、TASK_LIST_CURSOR_V1/TASK_NODE_CURSOR_V1；033末尾仅编译已存在tasks.read业务授权，不自动授角色。上述列表/筛选/SSE边界已决策。app/权限/credentials/runner由主线修改，本线仅独立task_*模块、033和专属工具；不改B032或C素材。

T1真实矩阵：真实plan版本freeze ownership且Worker不抢拥有者；非空完整DAG与首200/第201/末节点；100000接受、100001拒绝；父跨Task/缺失/重复/循环/超过100拒绝；中间块失败可恢复但GET不可见/不发送；finalize摘要/审计/outbox失败整笔回滚；重复块/并发同plan revision唯一；三角色及越权对象404/外租户请求拒绝/动作撤销403；MAC错scope/query/manifest/revision拒绝；GET字段严格且无密钥/原异常；50/200页批量父读取和100000完整遍历hash对账。该真实矩阵尚未执行，外租户真实Task数据、完整列表遍历等仍需后续专项；ISOLATED_TEST写入只证明持久化协议，不计真实预检或平台执行验收。

T2另测7天边界/清理竞态/410→GET→续传、断网/重复/缺口/撤权、并发状态事件sequence与Task/Node一致及前端三视口。T1纯测和真实工具准备不等于SQL/HTTP验收，不能把设计文档勾为功能已实现。

T1当前自检：33项专属纯测通过（.runtime/task-core-unit.xml），含真实B编译1206节点工具smoke。首轮26PASS/1FAIL为夹具单条copies=300违反原上限50，已拆为六条copies=50，保留attempt-01，未改原合同。完整Task SQL/HTTP16组及100000节点独立容量2组均尚未执行。B确认只读复用launch_dag._configuration_hash为当前精确私有检查点依赖，未来B更改必须联动复验；不把payload_hash或graph_hash冒充预检hash。

033/035实现检查点：T1实际将BUILDING/COMPLETE内部manifest头并入orbit_task，独立chunk/node/edge/event/audit/outbox表；033已经由主线through034顺序DDL受测，未据此标Task业务通过，后续未修改。035追加dag_schema_version/plan_input_hash/allocation_input_hash三个类型化列，旧行全NULL保留读取、不猜测回填；新begin完整写入，缺头/半头不能finalize。finalize逐块重算B canonical graph_hash、块hash、真实节点/边总数及原状态，审计/outbox失败整笔回滚，不重载十万图。

当前33项专属纯测PASS（.runtime/task-core-unit.xml），Ruff/编译检查通过。run_task_core_checks(client,admin,headers,password,cache,database,cases,include_capacity=False)导出16主档+2容量档；实际SQL/HTTP仍待主线，未自行启动共享服务。容量档用B合法7142分支恰100000完整DAG、每页200完整遍历/父依赖/hash核对；7143分支明确PLAN_NODE_LIMIT，不伪造空Task。T1原operator_user_id查询按冻结投手owner_user_id筛选，实际提交者created_by仅供审计，不称Task实际操作人或Worker拥有者。

## 主线后续实际回执（覆盖上方准备阶段的待测状态）

T1主档实际22/22 PASS、11.49秒，回执`evidence/python-task-core-http.json`。首轮16PASS/1FAIL/5NOTRUN已单独保留，原因是MySQL3819被驱动归类OperationalError而专属工具只捕获IntegrityError；工具定点改MySQLError后仍严格3819，未改生产CHECK或断言。

十万节点档实际24/24 PASS、237.9秒，完整非空100000节点持久化与每页200全量遍历/父依赖/hash核对已实际执行。主线OS采样parent/oracle进程生命周期观测峰值384053248字节；这不是独立API或Worker峰值，不能据此宣称接口独占内存成本。冷缓存、20并发Task读取及生产执行均未验收。

该容量回执对应错误码规范修正前固定源码。之后只按原API_SEMANTICS将Task字段422改为FIELD_VALIDATION_FAILED，并规范共享文本helper在Task节点q边界的422原pointer；公共helper/SQL/DAG/分页算法未改。专属纯测现37/37通过（增加长度、换行、零宽、纯空白q的精确code/path），真实case9追加同类精确断言，主线正准备22主档与前端三视口复验；不把旧容量回执改写成修正后全源码验收。

最新只读UI实际三视口专项23/23、83.98秒通过，浏览器两个独立用例各三个视口，共6/6。真实Task-only USER经原菜单进入，当前计划403不借父菜单别名放权；原Task、首200节点、分页与父依赖、刷新、关闭后11秒无轮询均保留。移动菜单及初始密码提示的测试交互失败逐轮保存，最终通过原提示“取消”及原菜单交互完成，未关闭安全配置或加超时。证据`evidence/python-task-core-browser.json`；Python1479项检查点明确排除当时在制T2测试，前端275项及类型/构建/格式通过。

T2独立实现与纯测见`TASK_EVENT_STREAM_DESIGN.md`，尚未接线/真实SQL与事件流验收；033初始事件存在不等于SSE功能完成。完整列表遍历、外租户真实Task数据、原非空日期/领域筛选、suggestion权威来源、生产provider与平台执行仍保留明确缺口。
