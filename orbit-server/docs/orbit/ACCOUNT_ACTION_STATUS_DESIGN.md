# 账户动作状态：原任务合同核对与独立补充提案

当前决定：主线已批准阶段A最小只读命令诊断及031非唯一复合索引，已进入独立实现/专项准备；尚未注册公共接口或真实验收。保留028/029、原Ack和原Task合同，取消、人工重试/恢复及Task桥接技术扩展仍未授权。以下早期提案由本页“当前批准合同”明确收敛。

## 当前批准合同

- GET `/api/v1/accounts/{account_id}/actions/status?kind=ASSIGNMENT|SYNC|UNBIND&request_id=原Ack.request_id`，严格白名单、UUID、无写入、no-store。
- 本人actor_id及actor_subject_id、当前accounts菜单与对应动作、当前账户对象范围必须全部满足。转属后不在范围返回404，不授历史权限；撤动作即时403；沿已有到期guard，未追平503，不为诊断绕过。
- 独立DTO固定command_id/account_id/kind/accepted_request_id/revision（命令版本）/state（真实命令枚举）/attempt_count/last_error_code/effective_from/next_attempt_at/created_at/updated_at/completed_at。错误只允许固定具名白名单，未知null；数据库UTC毫秒真实序列化，不返回原异常/source/payload。
- 031仅新增非唯一复合索引；查询最多两条，重复明确503，不任选、去重或改旧命令。当前阶段没有TaskID、不创建Task、不增加取消/人工重试入口。
- 公共router注册与真实MySQL/HTTP队列由主线统一接入；纯测试和工具准备不计真实验收。

阶段A当前证据：独立account_command_contract/store/routes及031索引已完成，17项专属纯测试通过（`.runtime/account-command-diagnostics-unit.xml`），Ruff和编译检查通过；公共router由主线注册。主线随后真实专项10/10通过，同轮A107/107通过、16.01秒，回执`evidence/python-account-command-diagnostics-http.json`。本线未自行启动共享数据库/服务/浏览器。

真实专项工具`tools/account_command_checks.py`提供`run_account_command_checks(client,admin,headers,owner_user_id,owner_team_id,action_identity,database,cases)`，action_identity复用原动作夹具完整返回值，不新增原生身份。10组覆盖真实本地UNBIND受理/DTO、幂等原Ack、他人/错关联、严格查询、当前转属/人员停用、未知错误null及DB UTC、重复关联503、EXPLAIN、动作撤销、到期guard503。最后一组为隔离库持久状态故障注入，明确不冒充真实跨日/分配受理；未调用生产Meta。前置仅允许127.0.0.1:13306及本轮UUID库、through031迁移和已注册路由，由主线串行运行；实际10组通过仍不等于Task桥接、生产采集或完整模块验收。

前端独立`account-command.ts`与`AccountCommandStatus.vue`已接两个既有动作弹窗受理结果：只在明确点击时查询原account/kind/Ack.request_id，不改原回执；展示命令编号/受理请求编号/真实枚举/版本/尝试次数/错误或null/UTC时刻。失败清除上一份状态，原受理回执仍保留；切换对象或卸载中止/丢弃迟到读取，不自动轮询或重开任务、不增加取消/执行入口。55项账户相关替身测试通过（web `.runtime/account-command-ui-unit.json`），含新增SDK/状态组件20项和既有35项；类型及格式通过，真实浏览器尚未验。首轮54/55失败为测试beforeEach误返回mock函数被框架作为cleanup调用、产生零参数记录；保留attempt-01并改钩子块体，晚到AbortSignal及原全部断言保留，无生产逻辑放宽。

## 一、可直接回溯的原合同

|证据|明确内容|实现约束|
|contracts/API_SEMANTICS.md 第15行|202仅表示已受理；id/task_id/operation_ids用于查询；request_id放X-Request-ID及错误体|不将原Ack.state当实时状态，不用request_id代替权限或擅认TaskID|
|contracts/openapi-current.json /api/v1/accounts/{id}/sync|accounts.sync，Reason，202严格Ack四字段|保持现有已受测accountUUID、revision、受理state、原request_id；不追加task_id破原DTO|
|contracts/openapi-current.json /api/v1/tasks及详情/nodes/events|tasks.read，原Task/TaskNode/TaskEvent|账户动作权限不自动授统一任务菜单或读取权|
|同文件cancel/retry/resume|tasks.cancel/tasks.retry，CSRF、CAS、幂等，返回原Task|不能用accounts.assign/sync偷偷授重试/恢复任意任务|
|contracts/PERMISSIONS.md 第17—22行|当前账户按当前operator/team；任务继承计划或建议所有权；自身操作/对象事件跟随当前角色且脱敏|历史任务与当前账户不是同一范围；Worker身份不是拥有者；不得凭知道UUID扩大范围|
|contracts/WORKFLOWS.md 第105行|每任务SSE sequence，断网快照续传，权限撤销断开，7日事件保留|前端不能用定时器推测任务成功；账户当前Ack不满足完整SSE合同|
|contracts/WORKFLOWS.md 第111—117行|广告写UNKNOWN受控对账、非提交者双人核准|只读同步租约重读不是UNKNOWN写对账，不能混用权限与成功证据|
|reference/01_修订需求与删除边界.md 第2、4节|执行任务/历史/节点/失败/证据/重试/取消/SSE作为投放子功能保留|统一任务完整实施仍必须继续，不能用账户状态小接口替代|

原Task.state枚举不含SCHEDULED/WAITING_EXECUTOR，TaskNode.kind枚举不含ASSIGNMENT/SYNC。
因此现有orbit_account_command不能直接改名映射成原Task，否则会伪造节点含义或放宽严格枚举。
原Task所有权有计划/建议来源，但独立账户同步和未来分配不一定有此来源；这是一项需明确的技术补充，不能凭原发起人或当前账户拥有者猜任务历史归属。

## 二、建议先提供“原受理回执当前诊断”，不冒充原Task

历史候选路径已批准为页首所列API；本节保留早期论证，不作为额外权限授权。

建议严格独立DTO：account_id、kind、request_id、revision、state、attempt_count、last_error_code、effective_from、created_at、updated_at、completed_at。
不返回Token、来源配置ID、当前owner/team、当前名称/金额、完整source_json/payload_json、平台或数据库原始错误，不返回“可执行”权限承诺。
SYNC成功只解释已验证元数据同步；ASSIGNMENT成功是当前投影实际激活；UNBIND成功只解释本地解绑。
原Ack仍永久原受理回执，诊断状态只从真实持久command读取。

### 待批准的最小范围

第一步可只允许“原发起人读取自己的原动作回执诊断”：要求当前有效会话、accounts菜单、对应原动作仍存在，查询同时绑定tenant+accountUUID+kind+原request_id+actor_id+actor_subject_id。
request_id仅作复合查询关联，不是认证凭据；他人的原request_id统一404。
早期“不经当前账户投影/dueguard”的建议未采用。当前批准方案必须先执行当前账户动作授权、范围和到期保护，再按本人关联读取；到期未追平时503，由独立受权恢复器处理，不为诊断新增旁路。

主线已收紧该提案：账户转移后仍必须通过当前对象范围，否则404；原动作撤销立即403，不设自身历史操作例外。当前接口还必须执行既有到期guard，503时不能绕过。此范围不授任务重试、分配恢复、广告操作或跨租户能力。

团队/超级管理员读取他人动作不在该第一步默认开放。应优先走原system.audit.read或未来tasks.read的正式脱敏审计/任务范围，不能因为拥有accounts.assign就查看任意团队人员历史。
现有表中source_json有受理时旧owner/team可供后续正式历史归属设计，但尚不能把该JSON值自动提升为原Task所有权合同。

## 三、统一任务后续仍需独立闭环

1. 明确独立账户动作的任务拥有者与转移后历史范围，按原任务权限验证，而不是复用当前账户WHERE。
2. 如需新任务类别/节点类别，先定义独立版本补充及状态映射；不拿VERIFY节点冒充未定义的SYNC采集任务。
3. 建立显式command→task持久关联；只有真正存在Task时才能返回或跳转该TaskID。原accountUUID与request_id不隐式重用。
4. 真实SSE/快照、sequence/权限撤销、取消/重试/恢复/对账分别实施，用户取消不自动恢复，广告写UNKNOWN不盲重发。
5. 到期assignment恢复器在全局dueguard之外运行，但每次当前权限/来源/目标范围重验；诊断读取不因此获得推进或发送权。

任务桥接部分仍是设计，不计开发/测试/验收完成；仅页首明确的阶段A已批准独立实现。

## 四、本轮复核结论与最小交付分段

本轮重新读取原 OpenAPI 的 Task、TaskNode、Ownership、RetryTask、ResumeWorkflow 和 tasks 全部路径，并核 WORKFLOWS 第8—10节、PERMISSIONS“自己的数据”。TeamAI检索未命中ORBIT任务桥接约定，其他项目的账户通知/生命周期资料不作为本项目状态合同。

**建议先实施独立命令诊断，再做经明确合同补充的任务桥接。** 原任务状态合法集合是QUEUED/RUNNING/VERIFYING/UNKNOWN/RETRY_WAIT/SUCCEEDED/PARTIAL_SUCCESS/FAILED/CANCELLED/NEEDS_HUMAN；节点kind仅UPLOAD/CAMPAIGN/ADSET/CREATIVE/AD/VERIFY/ENABLE/ALLOCATION。独立账户动作没有合法的SYNC或ASSIGNMENT节点，且原任务所有权继承计划/建议。不能创建空nodes“任务”来绕过这两个缺口，也不能把VERIFY或ALLOCATION换个中文标题当账户同步/转属。

|阶段|最小实际交付|明确不包含|
|---|---|---|
|A，原回执诊断|受控GET状态、原Ack重放、只读状态界面、当前会话撤权和数据泄露矩阵|不新建原Task，不新增重试/取消/恢复按钮|
|B，原Task基础能力|按原合同实现计划/建议真正任务、节点、GET/SSE/取消/重试/恢复和继承所有权|不将独立账户command自动混入原Task列表|
|C，账户桥接补充|主线批准独立账户任务所有权及新类别/版本后，事务建立显式关联；使用B的真实任务基础设施|不修改原Task/TaskNode严格枚举，不给旧客户端发送新kind|

A可以独立闭环，不必等待B全部完成；C需要明确版本合同，不能仅以数据库加task_id冒充完成。若主线要求原Task严格schema完全不扩展，则C只允许关联确有计划/建议来源的既有Task，并以独立关联DTO展示账户操作诊断；没有此来源的command继续作为独立操作记录，不生成伪任务。

## 五、ID关系、查询与重放决定提案

1. `account_id`是业务账户UUID，`command_id`是持久命令UUID，`task_id`只指真实存在的任务UUID，三者不相等推断、不相互替用。原Ack.id保持已受测账户UUID；原Ack.revision仍是受理后的账户版本，状态诊断的`revision`必须明确为命令版本。
2. 原`request_id`是一次受理的关联UUID，不是任务ID、秘密或授权凭据。HTTP本次诊断的X-Request-ID和错误体request_id是本次读取请求；DTO中的`request_id`明确为原受理关联。应另用字段名`accepted_request_id`的技术补充DTO避免歧义，最终名称由主线确认，不能静默改变原Ack。
3. 建议A路径保持第二节提案，严格白名单kind/request_id，无body，Cache-Control:no-store；复合SQL查询tenant+actor_id+actor_subject_id+account_id+kind+request_id，最多一条。没有记录、他人记录、错账户/错动作统一404；无菜单/动作403；UUID/枚举/重复或未知参数按现行严格合同报错。
4. A返回独立严格DTO：`command_id/account_id/kind/accepted_request_id/revision/state/attempt_count/last_error_code/effective_from/next_attempt_at/created_at/updated_at/completed_at`，允许真实缺失时null，不返回可用Token、source/payload、原始异常、他人姓名/归属。state列举真实命令状态，含029实际WAITING_RETRY，禁止转换为原Task.state后丢失差异。完成的UNBIND依然只表示本地解绑。
5. 同原Idempotency-Key、同规范正文/If-Match重放返回原Ack，绝不创建第二command/task/租约、改时间或重新发送；相同key不同hash409。重放不延续旧权限：先做当前身份/租户/原动作及必要原对象范围校验，不能让幂等缓存绕撤权；遇真实转属是否只允许读取原回执，需按第九节明确。
6. A不从request_id搜索任意租户/历史人员，不提供“全部账户命令”列表。当前dueguard阻断业务读取时诊断同样503；GET绝不推进Worker或返回当前账户资料。

## 六、取消、重试和恢复分工（尚未实现接口）

原Task的GET/list/nodes/events必须当前tasks菜单+tasks.read+任务冻结所有权范围；cancel必须tasks.cancel；retry/resume必须tasks.retry；不借accounts.assign/sync授予这些权限。管理类写还须实时复核目标账户当前业务动作和范围、目标资源/来源/租约，不因为能读历史任务就能操作已转属账户。

|场景|允许的最小行为与必要栅栏|
|---|---|
|只读SYNC未认领|未来取消应原子标记取消请求并阻止新claim，清理活动唯一键；原command目前无CANCELLED合同，批准扩展/迁移前不伪用FAILED表示用户取消|
|只读SYNC已发送|取消不保证终止已在途HTTP；立即撤销claim回写资格，完成回包不得更新账户。取消状态与发送中状态需独立持久字段/审计；不写“平台取消成功”|
|SYNC有限自动重试|维持首次+3次、30/60/120秒及120秒租约；读故障重读不进入广告写UNKNOWN。人工重试是新的授权执行意图，需要批准的重试代次和预算，不通过旧Ack重放重置attempt_count|
|ASSIGNMENT未来SCHEDULED|取消涉及已关闭旧区间和未来区间，不能仅清active_kind。须原子检查无后续依赖/激活、恢复连续区间并审计；未定义冲突/撤销归属合同前暂不开放取消|
|ASSIGNMENT已到期BLOCKED|恢复不是再创建下一当地日的新分配；保留原effective_from及冻结未来区间，当前actor授权、原发起者授权、目标人员/团队/户商、版本及来源全复核。是否允许管理员代原已撤权发起者重新批准，需要独立裁决；当前不得绕过原发起者撤权|
|ASSIGNMENT已SUCCEEDED或UNBIND已SUCCEEDED|不可“恢复旧命令”逆转当前业务；需要新的明确业务动作。不会逆写历史日事实或删除原命令/审计|
|原广告写UNKNOWN|完全按原tasks.reconcile双人证据流程；读租约、用户取消、一般retry均不得自动重发未知广告写|

原RetryTask严格`node_ids[1..500]+reason`；原ResumeWorkflow严格`reason+binding_revision`。独立账户command没有原合法node_id/binding_revision语义，因此在C合同补充前不能接收这两个DTO并自造映射。未来Task状态和命令状态必须分别持久，只有同事务确认的进度可发布，禁止后台轮询拼接出未经提交的成功。

## 七、队列并发、授权和事务要求

沿当前真实实现固定顺序锁账户clock→account→command；诊断无副作用，clock/account持共享锁并执行dueguard，随后按命令索引查询。新桥接事务在此后以稳定Task UUID顺序锁task/event counter，所有发送/取消/重试采用同一顺序；禁止任务Worker反向先锁task再争account。

同账户同active_kind唯一键继续约束互斥，受理、取消、恢复、claim和完成用command revision及claim UUID作CAS。网络HTTP在事务外，每次实际发送和回写重新校验当前原发起人授权版本、账户范围、来源版本、到期投影和本次claim；租约失效或取消后的迟到执行者不得回写、发布成功事件。取消/恢复与另一个Worker同时发生必须只允许一个CAS成功，另一个返回冲突或无操作，不靠进程锁保证跨主机正确性。

任务状态迁移、关联command版本、每Task单调sequence和脱敏outbox同事务提交；SSE只能读提交事件。任务读取和事件续传每次重新授权，撤权发送SCOPE_REVOKED并断开，后续GET失败；事件7天清理和过期410后完整快照仍按当前权限读取。快照/游标不能冻结旧的可读权限。广告写kill-switch和UNKNOWN双人对账保持原合同，不因账户只读诊断被绕过。

## 八、需要的迁移与公共接口（A已分配031）

**阶段A最小迁移031**：只新增命令诊断非唯一复合索引`(tenant_id,actor_id,actor_subject_id,account_id,kind,request_id)`；如存在重复关联，读取明确503，不通过LIMIT1任选或删除历史。原幂等唯一键仅保证actor+request_key，不能据此声称request_id天然全表唯一。A不改028/029，不添task_id，不变更原状态枚举、不启调度。A需要专属contract/store/router及原动作门禁；公共router由主线注册，无新前端菜单/额外系统读权限。

**阶段B/C后续迁移**：由统一任务负责人统一建任务、节点、事件/outbox和幂等/执行代次表，账户线不重复建立第二套任务主表。建议独立关联表`tenant_id,command_id,task_id,relation_kind,created_at`，tenant+command唯一，tenant+task建反查索引并有同租户外键；关联由受信业务事务生成，浏览器不能提交任意task_id绑定。只有明确批准的多command聚合任务才允许同task多关联，不能反向让一command重复建立多个活动任务。

若支持取消和人工再执行，还需command cancel_requested_at/cancelled_at/执行代次或独立attempt表与防旧claim字段；不改旧028/029迁移，新增编号expand迁移并保持旧程序兼容。任务冻结owner/team、来源计划/建议ID和版本必须来源于真实合同及实际业务记录，不从当下Worker/调用者/当前账户猜填；没有来源的独立命令需先批准专门ownership规则。迁移编号、Task存储所有权及公共菜单/action桥由主线统一协调。

## 九、实施前必须明确的决定及验收矩阵

|决定|本提案默认建议|未决定时|
|---|---|---|
|账户转移后原发起者诊断|已裁决：本人、原动作/菜单及当前对象范围；转属越界404、撤权403、到期guard503|该项已决定，按当前批准合同实现，不授历史例外|
|独立账户Task ownership|新增明确版本补充；原计划/建议任务仍继承原来源|不创建原Task、不在原任务列表伪装显示|
|新节点类别|独立版本的账户执行模型或独立关联DTO，保留原严格schema|不得把VERIFY/ALLOCATION当SYNC/ASSIGNMENT|
|取消和人工恢复权限|原tasks.cancel/retry加当前业务动作/范围，并明确冻结区间撤销规则|A只读，不开放控制按钮|
|原发起者撤权后的代办|另一次实名重新批准和不可变证据链；不借worker服务身份|仍BLOCKED，不自动改actor或来源|
|幂等原回执访问与当前范围|执行重放及A诊断均维持当前动作/对象范围；转属越界不可读取|不能以旧key触发重发或读取他人资料|

A专项必须真实验证：本人状态/原Ack不变、他人request_id/错kind/错account/foreign租户404、撤动作/停用人员/过期会话403或401、转移后不泄露当前归属、dueguard期间503、未知null与脱敏、state版本变化及no-store、重复/未知参数拒绝、索引EXPLAIN。B/C增加真实多Worker认领/取消/迟到回写栅栏、恢复仍撤权、同幂等键不重复task、审计/事件失败整笔回滚、序列并发唯一、SSE断线/410/撤权、前端三视口状态与按钮权限。未运行的矩阵不计验收，真实Meta/广告写与托管部署仍独立列外测缺口。


## 十、阶段A实际交付检查点（2026-11-08 17:13，北京时间）

后台10项本人诊断真实专项及原账户回归总107/107、16.01秒通过，专属纯测17/17；证据`python-account-command-diagnostics-http.json`。当前动作/本人/对象范围、转属404、撤权403、重复关联503、实际UTC和索引均已验证；到期guard为受控持久故障注入，不冒充真实跨日。

前端在原两个动作结果内增加显式查询/刷新，不自动重发；权限失败清空旧快照并保留原Ack。全前端217项单元/组件、类型/构建/格式通过。独立正向三视口`python-account-command-browser.json`49/49通过，原Ack与13字段状态/刷新保持同命令关联，SQL核实三条命令未认领且attempt_count=0。该正向采用独立来源前置，不含身份/范围故障工具；它们仍由107项后端和原66项取消浏览器专项单独覆盖，不静默停用其他场景的来源。

首轮来源前置冲突和第二轮遗漏已知/dev-api代理前缀的三视口等待失败各自保留；仅修精确路径规范化，未缩短字段/关联/写次数断言。桌面诊断49/49单独记录，不混充三视口。前端已推送6b27c29；受控来源仅用于本地入队，不是实际Meta验证，未启动同步执行器或发送真实广告。
