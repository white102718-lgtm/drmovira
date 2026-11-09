# 分配配置源与计划状态头接力

状态：主线5d206e36检查点释放后，现已实现runtime/Worker及专属工具首稿；source/head定向纯测已通过，新增真实SQL尚待主线串行执行。未以纯测或本文代替真实验收。

## 原合同与边界

原contracts/openapi.json保留POST /api/v1/launch-plans/{id}/allocations，launch.edit、CSRF、Idempotency-Key及If-Match，202响应Allocation；GET对应allocation_id，launch.read，200响应Allocation。task_id可为null，不能改成Task包或强制新建公共Task。

WORKFLOWS第23、25行要求allocation-v1完整匹配、60秒超时延续相同输入hash、单计划单项求解，冻结allocation_id/seed/plan_revision/material_revisions/capability_version/完整映射；输入变化失效。原合同没有要求将纯状态CAS头伪造为PlanVersion，也没有要求复制历史allocation/name到新head。

现主线capture_plan_source只接受当前动作授权、对象可见、同事务已锁定的head，按tenant+plan索引倒序LIMIT1读取真实latest版本，再按复合主键校全文/所有权/hash。复用此门禁，不写另一个无限历史扫描或按head猜版本。

## 最小内部接口

保留AllocationRuntime.enqueue(session,actor,plan_id,request,expected,key,request_id)、get及Worker claim/load/publish入口，外层事务由调用者持有。路由/CSRF注册及app提供器由主线接，不在本阶段并改。

现已将AllocationProvider.capture缩为(session,current,plan,request)，不再传CAS头作plan_revision。provider只取得/锁定真实来源、当前caller与owner交集和媒体/能力完整证明，不能网络I/O持SQL事务；缺生产provider仍503，不使用ISOLATED_TEST能力当真实平台能力。prepare_publication与publish_references保持签名。

packet仍冻结真实配置source_revision，不记录或散列易变CAS head进输入。原packet字段和input_schema_version=1可保留，故不先申请新迁移；若实现发现结构必须变更先请求分配。

## 锁顺序和受理

1. 当前launch.edit授权及无锁预读Plan仅为来源定位，不能提前以旧IfMatch拒绝可能成功重放。
2. 规范请求及原意图hash保留[plan_id,expected,command]，不能用新head改写旧键业务意图。
3. provider按既有来源顺序加锁，素材clock→全局排序素材/精确引用集，避免plan→material逆锁。
4. launch clock→Plan当前head写锁，然后capture_plan_source获得真实latest配置。校来源payload与无锁预读/受控provider计划hash相同，来源异常503或变化409；绝不将expected当source。
5. 用真实source_revision冻结packet。先检查成功幂等键及其input_hash与当前完整授权/来源冻结结果相同，再对全新键校head==expected及DRAFT/VALIDATED。新键不能利用旧source绕过头CAS。
6. 原已完成键在同范围/来源下返回原allocation_id，不新增分块、guard、event或outbox；撤权、来源变化、换请求仍拒绝。旧键不重绑新source，不返回部分失效结果。
7. 单计划guard、旧active指针、seed+1、完整chunk/manifest/audit/outbox同事务保持，已有active不因新排队失败而丢失。

## 发布与状态语义

load核当前actor租户/动作/对象范围，不以旧缓存授权。CPU在事务外。publish先prepare_publication获取来源/旧新引用联合锁，再launch clock/head→capture_plan_source；当前source_revision/hash/完整payload必须等于冻结包。head可因纯状态动作增加，但不能因任意配置保存而被忽略。claim代次/租约、guard、previous allocation/input hash再精确CAS，完整items与引用、终态、审计同事务。

VALIDATED发布新分配会使预检失效：Plan须VALIDATED→DRAFT，头revision+1，WHERE原revision/state CAS及updated_at，不能仅改state。已DRAFT且配置不变不制造新PlanVersion；拟保持head不变（分配是独立资源，目录event仍更新目录clock）。此状态语义已经主线明确批准并实现；原条款无明确DRAFT分配再增头要求。不复制allocation/name，不修改历史外键；任何source变化使旧分配不可发布。

## 验证计划

纯测：源revision与head分离、packet不依赖head、provider不接旧CAS、未配置failclosed；Worker未知来源错误分类、claim失效不误写终态。

真实UUID MySQL工具保留原14组所有断言，追加至少：VALIDATED head高于source时enqueue FK正确；原键在纯状态head变化后当前来源同一可重放、全新旧head拒绝；撤权/真实source变化拒绝原键；发布配置不变但head变化可接；VALIDATED发布CAS+1且source不复制；DRAFT发布头不变；配置source改变拒旧结果并保留旧active；审计失败回滚CAS、items、引用、guard及outbox；latest来源缺失/摘要不符失败关闭。真实平台/素材能力仍单独声明，SQL fixture不冒充外部资源验收。


## 本轮检查点与真实入口

runtime原enqueue/get/load/publish签名保留；capture(session,current,plan,request)已适配唯一现有FixtureProvider及publication回调。packet原schema未改，32历史DDL与公共app/route/harness未改；没有新增迁移。

专属runtime+packet共44项纯测通过，包含source/head、旧键先当前来源重验后旧CAS、新键当前If-Match、精确isolated host/port guard等；原冻结/求解分支继续保留。真实工具仍run_launch_allocation_runtime_checks(admin,database,cases)，LAUNCH_ALLOCATION_RUNTIME_CASES由14扩为22，原14组含5MiB/万slot/500素材完整manifest全部原断言保留。新增8组覆盖真实PlanVersion/head分离、发布状态CAS审计失败回滚、旧键撤权/重放与新键旧头拒绝、DRAFT头保持、SUBMITTED/ARCHIVED拒发布、实际新配置使旧发布与旧键失效、最新版本缺失/坏摘要零队列写。此22组尚未执行，不标业务验收；测试provider继续明确ISOLATED_TEST且不是平台/素材杀毒证明。


## 原HTTP成功协议新夹具（待真实运行）

新增独立tools/launch_allocation_http_fixture.py：IsolatedHttpAllocationProvider，kind固定ISOLATED_TEST，capture仅协议兼容图/元数据，publish_references明确no-op，不证明C引用/ClamAV/Meta。没有HTTP控制后门；仅主线私有显式测试引导向app.state.launch_allocation_provider注入，生产默认None不变，运行时仍逐次强制127.0.0.1:13306+UUID库。

新增tools/launch_allocation_http_provider_checks.py，导出LAUNCH_ALLOCATION_HTTP_PROVIDER_CASES共8组，入口run_launch_allocation_http_provider_checks(client,admin,headers,database,cases)。checker仅主线串行运行；本任务没有连接SQL/运行服务/子进程。7项专属纯测通过，Ruff通过，不能代替这8项实际HTTP验收。

真实计划：SQL明确准备fixture Plan source1/head4；原POST202严格原Allocation/QUEUED/task_id null；GET200同对象；本轮真实claim/load/solve_packet/publish，发布VALIDATED→DRAFT head5且版本表不复制；GET完整SUCCEEDED双slot严格原Schema；旧键旧CAS重放、异body409、新键旧CAS409；当前launch.edit/read分别撤权403；父ID绑定404与未知query400；真实1644触发排队审计故障，503不泄内部错误、head/目录clock/所有队列行数/幂等/audit/outbox/task计数全部回滚，旧成功GET保持原值。无需轮询或模拟Task，未重跑旧万slot容量。
