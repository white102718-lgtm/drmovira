# 原execute完整清单持久接力设计（039字段稿）

当前为接口/DDL需求设计，不是execute已可用。纯准备模块42项通过；生产ExecutionAuthorityProvider、正式写命令/核验链路未接，默认None须503且零Task/命令。本文不修改旧TaskManifestStore的隔离门禁/source==head语义，不新增HTTP prepared接口或占位202。

## 1. 原合同与现有实现边界

- 原POST `/api/v1/launch-plans/{id}/execute`，严格ExecutePlan仅hash/activate_ack，If-Match为当前head；成功HTTP **202 Task**，其详情含首200个真实节点及原游标，不是HTTP200、内部runtime ID或准备ID。
- `contracts/WORKFLOWS.md:101—103`：原canonical键plan_revision取不可变配置source；15分钟及上海午夜失效；同source至多一个Task，名称/分配不能因head状态变化重绑。
- `contracts/WORKFLOWS.md:127`：完整DAG最多100000节点，完整持久后才发送；`contracts/ADSPOWER_WORKFLOWS.md:77—82,157—161`：完整源/资源/最终名，命令/Task/outbox原子；写前意图和即刻核验另有要求。
- `task_manifest.py:30—45`当前仅ISOLATED_TEST精确本地UUID库；source要求current_revision==配置revision。新execute的source<head不能借改producer或移除该判断绕过旧协议。
- 033已有BUILDING/COMPLETE内部可见性及同tenant/plan/source唯一Task；Task/Node原枚举不新增PREPARED。035已有真实DAG header；036事件目录由真实事件事务维护。
- 038成功validation不可变，source_revision与validated_head_revision分离。完整预检/瞬时scope合法不等于可发送授权；原execute不能强加launch.read/edit/tasks.read。

## 2. 内部接口与权限

```python
class ExecutionAuthorityProvider(ABC):
    async def capture(self, request: ExecutionInput) -> ExecutionEvidence: ...
    async def revalidate(self, session, current, source, evidence) -> None: ...

class LaunchExecutionStore:
    def __init__(self, tokens, provider=None): ...
    async def prepare(self, session_factory, actor, authorization, csrf, key,
                      value, plan_id, expected_head) -> ExecutionPreparation: ...
    async def stage_begin(self, session, binding, prepared) -> StageHandle: ...
    async def stage_append(self, session, handle, packet) -> None: ...
    async def stage_seal(self, session_factory, handle) -> SealedExecution: ...
    async def accept(self, session, actor, authorization, csrf, key, value,
                     plan_id, expected_head, sealed) -> dict: ...  # 原Task，路由202
```

StageHandle/SealedExecution为内部不可变Python对象，只能从Store构造，HTTP不接受prepared_id、producer_kind、verified或seal参数。对象本身也不授权限，accept从DB核全绑定。Kind为受控TRUSTED/ISOLATED_TEST；ISOLATED仅127.0.0.1:13306和`orbit_py_it_<32小写hex>`，每入口校验本轮实际DATABASE；生产None在任何stage写前503。ABC类标识也不证明平台授权，生产注册必须有真实来源实现和操作能力证据。

prepare先以launch.execute+当前计划范围读取源/validation/幂等事实、CSRF；activate_after_create再核launch.publish+activate_ack，不借edit/naming公共HTTP。capture只事务外外部只读；素材双方scope、身份/目标、policy、能力/registry、profile、渠道目的地及URL安全等由真实Provider核。完成纯prepare_execution后再进入有界私有持久阶段。

## 3. 039拟新增表及字段

所有UUID/复合FK带tenant；SHA256用CHAR(64)且严格十六进制；safe integer遵原上限。UTC DATETIME(3)、中文COMMENT；业务JSON不得带Token/Cookie/临时URL/异常正文。下列名字为给主线的字段稿，未自行创建迁移。

### orbit_launch_execution_preparation（私有构建头）

- PK `(tenant_id,id)`；task_id真实预留Task UUID，UNIQUE `(tenant_id,task_id)`，FK到033隐藏Task。
- plan_id/source_revision/payload_hash；FK `(tenant_id,plan_id,source_revision)`到021不可变版本。
- validation_id/validated_head_revision/validation_hash/validation_expires_at/naming_date；FK validation。它们是候选受理时绑定的真实038记录，不能在原stage上偷偷换validation/head。
- actor_id/subject_id/owner_user_id/owner_team_id/auth_version/authorization_fingerprint；冻结构建者和真实归属，不替代当前权限。
- intent_hash（当前纯request_payload_hash：tenant/plan/source/head/原execute两字段）；idempotency_key_hash；provider_kind/provider_fingerprint；实际受理request_id在final记录，不把准备请求号当已受理号。
- state `BUILDING|SEALING|SEALED|ACCEPTED|ABORTED`；只内部状态，Task仍原QUEUED且manifest_phase BUILDING。
- manifest_schema_version/manifest_hash/task_chunk_hash/graph_hash/plan_input_hash/allocation_input_hash；分别保留完整字节清单、033有序节点块根、拓扑及来源摘要，不能互相替代。033 orbit_task.manifest_hash继续是原节点块ordinal/count/hash根，不填新完整字节清单hash。
- expected_bytes/expected_byte_chunks/expected_node_count/expected_node_chunks/expected_command_count/expected_edge_count；实际persisted_*；下一连续byte/node ordinal。
- mutation_revision（所有合法append/abort变更+1）；sealed_revision/sealed_at；accepted_head_revision/accepted_request_id/accepted_at均起初NULL，仅成功事务一次填充。
- created_at/updated_at/expires_at；expires_at<=validation_expires_at且不得越上海命名日，用DB UTC核；无客户端任意TTL。
- 索引 `(tenant_id,actor_id,state,updated_at,id)`、`(state,expires_at,tenant_id,id)`、`(tenant_id,plan_id,source_revision,state,id)`；相同source Task唯一性继续由033保证，不另造竞争性唯一业务规则。
- CHECK：非空1..100000节点；commands==node_count（每实际DAG操作一条内部持久命令，VERIFY是只读操作）；byte/ordinal/版本合法，SEALED后各expected/persisted严格相等，ACCEPTED才有全部受理字段，provider白名单。

### orbit_launch_execution_byte_chunk（完整文档字节块）

PK `(tenant_id,preparation_id,ordinal)`；FK到构建头；byte_length、chunk_hash、payload LONGBLOB、created_at。

每块1..1MiB、连续ordinal，hash核实际字节；可跨UTF8字符，不能单块独立解析JSON。expected_bytes用BIGINT并核安全整数，不能套032 256块旧限制、也不把64MiB原始输入预算当展开总量上限。每append只持一块，配置节点数量仍遵原100000上限。完整hash必须按序实际读持久字节重新计算，不能信客户端声称的hash/count。

### orbit_launch_execution_command（完整冻结命令描述）

PK `(tenant_id,task_id,node_id)`；FK到033实际Node；UNIQUE `(tenant_id,task_id,ordinal)`。preparation_id、node_key、kind、purpose、account_id、target_key、resolved_configuration_json、resolved_configuration_hash、observation_binding_hash、created_at。resolved完整配置含最终名称/身份/素材描述/归因目标参数，不能只放hash或指针。JSON单节点有界，必须按原5MiB源和字段上限证明其上界后再定SQL字节CHECK，不擅加新的业务长度限制。

这里是不可变命令配置，**不是已经发送的WRITE_INTENT**，没有平台响应/授权Token/伪external_id。首阶段不注册发送Worker。今后lease、WRITE_INTENT、attempt、UNKNOWN/readback等可变执行状态另设专门合同及迁移，不能把QUEUED描述当写成功。命令候选读取必须join Task COMPLETE + preparation ACCEPTED +实际授权provider/执行开关，不能只扫描本表存在即发。

### orbit_launch_execution_acceptance（唯一真实受理绑定）

PK `(tenant_id,plan_id,source_revision)`；FK配置源，UNIQUE `(tenant_id,task_id)`和`(tenant_id,preparation_id)`；validation_id、validated_head_revision、submitted_head_revision、validation_hash、manifest_hash、intent_hash、accepted_request_id、accepted_by、accepted_at。

这是不可变同source唯一Task受理事实；幂等回执继续用原orbit_launch_idempotency。不同键同source必须核已有受理绑定并返回同一原Task；同键异payload409。任何准备/验证失败不得插acceptance，不得在失败响应返回Task占位。033 `ck_task_producer`仅经039显式允许TRUSTED，不修改旧构建器行为；None仍零写。

## 4. 持久构建、完整密封及最终短事务

1. begin：当前动作/范围及精确source/head/validation已核、Provider证据已捕获；短事务取得launch clock/head后保留同source隐藏Task与preparation。原state QUEUED、phase BUILDING，原读/SSE不可见；不是成功受理或任务已入执行队列。重试冲突读取既有同actor/intent构建；异actor不泄露Task/构建ID，统一当前范围后处理busy。
2. append：仅该隐藏Task→私有preparation头→块/节点锁；不再反向获取来源/launch clock。若已过期/终态/绑定不同拒绝。每次最多一字节块或500节点（原CHUNK_SIZE），集合写真实node/edge/command和chunk；Node.initial_json保持原DagNode结构，resolved配置只进新command表，不污染原graph摘要语义；父节点必须已存在，所有hash/count和ordinal同事务推进。重放同块需实际内容/hash全部相同；缺块、多块、跨Task/node、错版本拒绝。
3. seal：先短事务由BUILDING→SEALING，停止任何合法追加/删除；stream读取完整持久字节SHA、节点/边/command逐块验证（每块<=500），实际重算graph与resolved hash、完整引用/命令对应、总数。此阶段不得持来源clock/Plan/head跨全部100k扫描；内部私有stage可被租约/过期中断，失败ABORTED或保留不可见待明确恢复，不自动发布。
4. seal最终短事务只锁私有头且不等待Task/child，确认mutation_revision/phase未变，再存sealed_revision、根摘要、计数与seal时刻，置SEALED。SEALING崩溃后不能仅凭expected_count强行SEALED，必须重新全量流式核。
5. final accept在同一主线外层事务完成：当前auth/CSRF/范围→Provider当前DB来源锁→launch clock FOR UPDATE→Plan/head→validation/allocation/name头→task clock FOR UPDATE→真实Task→preparation→幂等/acceptance/受理记录。launch clock必须写锁以排斥旧TaskManifest先launch共享锁→task clock→Plan的顺序，不能升级共享锁制造反向等待；append只私有对象、不持task clock，未获Task锁的跨对象清理也不能反向获取launch锁。Provider不再网络；source<=head且真实PlanVersion/hash/归属精确，当前head必须validated_head；最终DB UTC验证TTL、上海日、观察source及actor授权版本。完整纯树/巨量字节不得在此事务重新展开或复制。
6. final只读有界头：一个PlanSource元数据、一个validation、allocation/name头及完整items的来源证据版本（必须已有受信锁/变更水位，见下一节）、一个SEALED头/真实Task头、最多节点chunk数200条与字节chunk头集合（大于有界页则seal完成后以不可变证明，不将无界列表塞final），一个acceptance和当前幂等行。核seal证明与expected/persisted/root、当前真实来源完全匹配。
7. 同事务CAS Plan SUBMITTED/head+1（source不变）；Task COMPLETE、created_at/updated_at设真实受理UTC时刻及关联request（私有开始时间留preparation.created_at）、命令配置已全部在库且无复制；写初始QUEUED TaskEvent+036 cursor目录、真实Task审计/outbox、launch审计/outbox、acceptance及原幂等回执，preparation ACCEPTED。失败任何一点全回滚，可见性不提前。
8. 原202 Task由当前execute上下文内部读取同一已发布Task首200及父边/游标，不调用需tasks.read的公共detail门禁、不授额外GET权限。只有execute无tasks.read用户仍能收到原受理响应；其后GET是否可读仍按原tasks.read权限。

## 5. 必须先闭合的seal与来源不变量

不能仅以“字段叫sealed”或预期hash相等当证明。合法写方必须先锁构建头且只BUILDING可变；SEALING/SEALED/ACCEPTED的字节、命令配置、节点initial与边不可再被合法写方修改。旧TaskManifestStore仅ISOLATED旧构建任务，必须拒绝操作带新execution_preparation绑定的Task或其旧锁路径天然冲突时需显式隔离；不能假设无交叉写入口。此项需要主线审核旧入口新旧namespace隔离方案，未落前不允许正式accept。

SQL受控篡改在seal前应重算检测；seal后到final之间的直接SQL反例也必须被实测拒绝。拟选择**新表不可变护栏/受控触发器或真实DB权限限制**，而不是把老account_clock当缓存；若039不批准该护栏，则final需要重新读全部持久事实，违背短事务目标，不能声称已满足完整协议。触发器作用域只新准备对象及被其绑定的旧Task数据，必须证明append锁序无反向死锁、Task正常运行仅改Node状态不触碰initial/边。此处是明确设计依赖，尚未采用/实现触发器。

同理allocation/name源完整items不能只信头input_hash不变；当前validation已实际读全项。execute最终若不再读10000项，必须持有经DB强制变更代次绑定的完整来源证明，任何合法/受控SQL细项变化自动失效；没有这条不变量则需有界集合重验完整items（最多10000）并实测耗时，不能静默省略。主线需确定采用哪条；本设计不伪造已存在的item-generation。

## 6. 重放、撤权、恢复和清理

- 同键成功重放先当前launch.execute、当前对象范围、activate时publish/ack、当前CSRF，再读原回执；不因旧head/TTL重做已成功提交。若当前已撤权/转属不可见，不泄漏原Task。成功回执中的Task为受理事实，状态最新读取按合同另核，不能任意改旧幂等结果。
- 没有成功回执才核当前If-Match及validations；同source不同键命中真实acceptance返回同一Task，不能创建第二Task、重新命名/分配。异intent的确切409与原source唯一规则按原WORKFLOWS，在工具逐项验证，不静默换payload。
- 准备中来源/头/租户/actor/subject/auth-version漂移、超TTL或跨上海日均不可受理；ABORTED私有数据不公开。默认无provider连隐藏Task/command也不得创建。
- 同source存在ABORTED/过期隐藏Task时先有界清理其私有command/edge/node/chunk和preparation，最后删除BUILDING Task释放033唯一键。清理任务每次有限页、明确租约，不能边删除边被append/accept；ACCEPTED原Task与完整历史不走此清理。
- accepted来源/名称/素材引用按原历史期限及真实active-reference冻结，不能被素材物理回收；失败准备引用可在安全清理时释放。两年历史与事件七天payload清理不同。
- 不自动retry/取消真实Task，不给UNKNOWN任何自动重发路径；此阶段仅安全持久与202受理，无发送Worker。

## 7. 分项开发/测试/验收计划

- [ ] 039字段/类型/复合FK/索引/CHECK、producer扩展、不可变护栏与旧构建器隔离决策获主线确认。
- [ ] 新Store缺provider503零Task/命令；精确ISOLATED guard；execute-only/publish-only/撤权/跨租户/CSRF完整纯测与真实HTTP。
- [ ] 完整流式块/node/edge/command落库；缺块/重复异内容/跨Task/FK/序号/源漂移/损坏Hash、seal前后篡改真实负例。
- [ ] 全部阶段注入实际SQL失败/崩溃，公开列表/detail/SSE及任何执行候选均看不见BUILDING；清理/重放/同source并发。
- [ ] 完整原202 Task及首200、分页遍历、0次平台请求，Task/命令/事件目录/审计/outbox/Plan CAS/幂等任一失败全回滚。
- [ ] 10000广告/100000节点有界持久与实际RSS/批耗时/final锁时，来源明细重验耗时，不能仅复用纯编译或旧T1容量作新通过。
- [ ] 生产Provider权威来源、发前即时授权与capability/policy/registry、URL/身份、正式命令链与readback/UNKNOWN验收；缺来源保持execute_available不可用。

本稿提出接口和039需求，以下第9节记录已实现的独立Store基础。未写实际迁移、未改冻结纯模块或共享入口、未启动服务/数据库或平台写入。


## 8. 主线对039的明确裁决及候选状态

主线已批准新绑定对象的DB不可变护栏/触发器；最终仍各一次集合精确重验最多10000条allocation和10000条name明细，不采用未存在的generation。候选见 `docs/orbit/sql-drafts/039_launch_execution_candidate.sql`，不是migrations，未执行；实际迁移与串行MySQL解析/锁/状态更新验收由主线负责。

新合法append/cleanup/final统一Task→prep→child，旧TaskManifest也先持Task再由触发器当前FOR SHARE读prep，避免原稿prep→Task倒置。seal短事务仅prep→SEALING，不同时等待Task/child，提交后流式读，最终只锁prep保存seal。直接SQL若先持child再等prep，仍可能1213；必须整笔回滚并保留可重试原意图，不声称任意SQL均无死锁。SEALED后意图不得成功修改，实际并发负例仍待主线证明。

候选允许原Node与command的运行字段在ACCEPTED后更新，但冻结tenant/task/node/key/ordinal/kind/来源/配置/parent边；未受理Task不能提前切COMPLETE或运行。Task公开phase只在prep已ACCEPTED且同事务acceptance匹配时可推进；原T1无绑定Task不受护栏影响。ABORTED只允许受控删私有数据，不得复活。所有触发器使用服务端BEGIN…END，无mysql客户端DELIMITER指令。

39草稿不是已通过的SQL：包含SHA2字节CHECK、复合触发器、当前锁读与严格FK，需真实MySQL证明兼容及锁序。新Store基础见第9节；尚未实现实际持久/原202受理。


## 9. 新Store独立基础纯测试检查点

`launch_execution_store.py`现只包含ExecutionAuthorityProvider ABC、require_execution_provider门禁、不可变BytePacket/NodePacket/StageBlueprint和完整有界包编码。正式缺省None及任意verified字典在任何SQL前503；ISOLATED_TEST必须真实session目标127.0.0.1:13306再查精确本轮UUID DATABASE，仅证明隔离协议目标，不证明外部来源。

完整字节块逐包SHA256；节点包<=500并同时保留原DagNode结构和独立完整resolved命令，Node.initial_json不混入resolved字段。StageBlueprint事务外重读实际完整字节，核纯准备密封hash/实际bytes/真实节点，最多保留200个节点块头；完整manifest_hash和原033 task_chunk_hash独立。没有调用外部平台、创建Task、执行INSERT或返回假202。

专属 `test_launch_execution_store.py` 11/11纯协议测试通过（0.79秒），Ruff及格式通过；session仅替身，不能当作真实MySQL、触发器、权限、并发或持久化验收。实际begin/append/seal/accept须在主线审读/真实应用039字段与DB护栏后继续接，不把当前基础文件当完整Store。


## 10. TRUSTED未绑定namespace封口及NULL复核

主线审读指出producer扩展后，不得允许直接INSERT公开TRUSTED Task，或用未绑定BUILDING Task UPDATE绕过新接力。候选新增Task BEFORE INSERT：TRUSTED只可零节点/边、QUEUED/revision1、BUILDING、latest0/null、无对账标记和完整035类型化header；节点数量与500节点块数精确。Task UPDATE若OLD或NEW为TRUSTED且当前锁读无prep一律拒绝（含ISOLATED→TRUSTED换标签）。stage_begin仅Task INSERT→prep INSERT同事务，无中间Task UPDATE，不受影响；旧无绑定ISOLATED流程维持。触发器总数24。

新表所有可NULL CHECK分支逐项显式处理：seal字段在SEALED/ACCEPTED须同时非NULL，ABORTED也只允许同时NULL或同时非NULL合法sealed版本；ACCEPTED的时间/request/head全部显式非NULL；其余状态全部NULL。Task发布分支也先核实际accepted_request/accepted_time非NULL。衍生上海DATE/下一日CAST增加非NULL，避免溢出计算返回NULL令CHECK UNKNOWN放行。

后续真实SQL负例至少包括：直接插TRUSTED COMPLETE、插TRUSTED非零/已运行/缺任一typed header、无prep的TRUSTED UPDATE发布与改state、ISOLATED改为TRUSTED、有效隐藏INSERT→同事务prep绑定→合法追加；prep/command多种非十六进制hash、单个sealed/accepted nullable字段缺失。以上尚未执行，纯字符串检查或Python镜像谓词不能算MySQL护栏验收。原Store基础11项及冻结纯prepare42项源码保持不变。


## 11. preparation与038精确关联

主线复核后，候选BI除了核隐藏Task，也按038的现复合PK `(tenant_id,id)` 当前FOR SHARE读单条真实validation，逐字段核plan_id、source_revision、payload_hash、validated_head_revision、validation_hash、expires_at、naming_date；存在但属于其他计划/版本/头/时效/日期的validation UUID也拒绝。没有新增冗余宽复合索引，FK存在性不替代这项关联完整性，更不授予生产authority。

合法stage_begin应已先持来源/038共享锁，再Task→prep，BI重入同一038锁；任意直接SQL倒序仍可能1213整笔回滚，不能错绑成功。真实负例需逐项修改上述八字段并精确拒绝，旧Provider/42项纯合同和11项基础测试源码均未改。候选仍24触发器，尚未执行或计验收。


## 12. 039实际护栏检查点与当前Store在制范围

主线已创建并实际执行 `python/orbit_api/migrations/039_launch_execution_preparation.sql`（四表/24触发器）。through039缺省Provider路径及原allocation/validation HTTP16/16通过（9.49秒），新guard复验22/22通过（9.69秒，包括初始化/原基线和11个新护栏具名组），回执 `evidence/python-execution039-guards-http.json`。11组包含真实SQL038逐字段关联、TRUSTED未绑定封口、SHA/CHECK、RR旧快照下当前锁读、seal后不可改、正常ACCEPTED运行字段、ABORTED清理、实际INNODB_TRX LOCK WAIT同步及1213受害者整笔marker回滚。

首次guard19通过后在监控等待处失败，回执 `python-execution039-guards-failed-01.json` 保留。工具改独立autocommit观察连接/120ms采样且总预算仍2秒，加入Future实际errno安全诊断；复验确实观察锁状态并通过。尚未单独实证原失败由缓存饥饿导致，不把该猜测写成已确认数据库根因。参考[MySQL8事务监控一致性说明](https://dev.mysql.com/doc/refman/8.0/en/innodb-information-schema-internal-data.html)。SQL护栏直接发布的ACCEPTED记录是明确DDL fixture，不是原execute/AuthorityProvider/202受理或平台写验收。

新Store文件已继续在制：追加ExecutionBuildSpec/每包原node与完整command双SHA、执行当前权限和缺省None零写、stage_begin隐藏Task/精确038及完整allocation/name重验、Task→prep锁定及有界append_bytes/append_nodes。新增纯协议14/14通过（0.88秒），Ruff/格式通过；这些session替身结果不证明新增持久方法已经SQL通过。没有公开route、seal或accept假成功，生产execution_available仍关闭。

BuildSpec只从受控PreparedExecution在事务外重算，<=200个节点/命令包证明不可变；节点与完整resolved命令分别绑定，防止只保留graph hash而命令被换成占位。未来seal须读实际持久数据逐包重算并与受控Spec精确一致，final还要重核当前source和两类最多10000条完整items。崩溃后无Spec须重新捕获同源权威事实/重编译并完整seal，不从DB自报expected或任意prepared_id推导成功。

## 13. 执行必填、当前在制接口及并发恢复边界

原需求 `data/ORBIT_Codex开发PRD/reference/03_原合同保留章节.md:110` 明确“每条字段的必填条件在提交时适用；草稿允许缺少业务必填”，第165行 `attribution_spec` 为必填、服务器profile引用、不接自由JSON；“账户支持默认”仍需要真实可信适配器解析出该账户支持的实际profile，不能自行猜Meta数组。故OpenAPI广告组的metric_profile_id可选表示草稿结构允许缺失，不代表最终execute允许缺少真实归因配置。当前冻结pure严格拒缺失映射，Store对TRUSTED实际profile另拒FIXTURE来源；这两者都不等于生产registry已接通或已获得外部执行权。

当前在制公开Python接口（不是HTTP新契约）：

- `LaunchExecutionStore(tokens, provider=None)`；Provider必须实现事务外`capture(ExecutionInput)`、仅来源DB锁的`revalidate(session,current,source,evidence)`，以及实际`publish_references(session,current,evidence,task_id,request_id)`。
- `await store.prepare(session_factory,actor,authorization,csrf,key,value,identifier,expected,request_id) -> ExecutionPreparation`。自有短事务捕获038与配置源，关闭事务后capture/编译；每个真实字节/节点包一个短事务，随后逐包读取实际持久内容完整seal。只返回内部接力，不返回202。
- `await store.accept(session,actor,authorization,csrf,key,value,identifier,expected,request_id,preparation) -> 原Task`。必须处于调用方外层事务，成功后由主线HTTP提交事务并返回202。受理同事务包含完整Task/节点/命令、真实EXECUTION素材引用、038与完整allocation/name逐项复验、计划状态CAS、首次TaskEvent/目录、审计/outbox及幂等。没有生产Provider时零Task/命令。
- `await store.cleanup_expired(session,*,limit=500)`仅内部监督入口：每次一个准备、每批最多一表500行，使用实际DB时钟；Task→prep当前锁后，精确state/expires/mutation_revision CAS转ABORTED。ACCEPTED竞争直接跳过，禁止扫描删除已受理历史；当前尚未接无人值守调度。

无分布式lease时禁止共用旧builder的handle。相同key已有BUILDING/SEALING/SEALED、且仍有效时固定409 `EXECUTION_PREPARATION_IN_PROGRESS`；客户端保留原key和原body，稍后仅重放真实成功Task。不得用普通409策略丢弃未知意图。过期旧阶段返回STALE_PREVIEW，需重新预检；残留私有阶段由上述有界清理后重建，不宣称TTL内跨进程接管。仅本请求真正新建的handle可在失败时负向ABORT；清理失败不替换原异常。

独立Store现28/28纯协议测试通过（1.30秒），Ruff及格式通过，包括038十字段/UTC/精确TTL损坏、三种未完成阶段不交出handle、扫描与ACCEPTED竞争不删除、过期完整CAS。所有SQL session仍是协议替身；并发builder、崩溃残留、多包seal及完整原202事务仍待主线真实MySQL/HTTP专项，不能用039护栏已有22组成功替代新Store业务验收。当前没有生产execute路由、真实权威registry或发送Worker，因此不标生产执行完成。

## 14. 独立原execute协议工具已准备，尚待真实排队

`tools/launch_execution_fixture.py`导出`IsolatedExecutionValidationProvider(session_factory,control_dir=None)`和`IsolatedExecutionProvider(session_factory,control_dir=None)`。主线仅新execution flag替换前者；其原super对所有非`_EXECUTE_`计划保持不变。专属计划首次原validate捕获时就明确WEBSITE，冻结后execute不暗改channel/原hash。后者真实读取本轮038/完整allocation/name，调用原纯完整编译，登记实际SQL EXECUTION引用；所有身份、能力、素材描述与FIXTURE归因来源明确仅隔离协议。没有伪造文件扫描已通过的证据，不计生产C CLEAN或双方素材范围跨execute验收；TRUSTED生产Provider仍缺失。

`tools/launch_execution_checks.py`导出16个`EXECUTION_CASES`，入口`run_launch_execution_checks(client,admin,headers,password,cache,database,cases,*,control_dir,cipher=None)`。必须127.0.0.1:13306/本轮UUID/实际DATABASE一致及内存Cipher，不从私有环境或命令读取凭据。新工具仅使用传入控制目录（当前没有另设握手文件）；主线可沿既有本轮validation控制目录传入，不需开放HTTP控制。

计划16组分别覆盖：原202完整真实Task/节点/命令/refs/audit/outbox；原Task GET一致；旧key旧CAS精确重放；同key异payload；newkey同source；原字段/头/CSRF零Task；仅edit无execute拒绝；实际1644最终事务回滚；final完整allocation与name项变更；未seal拒绝；第二HTTP与原builder追加并行时固定busy且不互abort；精确DB到期有界清理；ACCEPTED保护；最终TTL前1ms/等号/后1ms；上海午夜前1ms/等号。SQL时钟组仅指定独立会话，不声称自然等待十五分钟、HTTP跨日或真实平台运行。

工具自检6/6纯测通过（0.66秒），Ruff/格式通过：非隔离目标在I/O前拒绝、精确Decimal会话秒、case库存、子类不改原capture包、完整SQL样本经实际pure编译保留真实名称与resolved配置。该6项使用替身，不是新16组真实结果。Store与工具现冻结供主线串行真实验证；任何失败保留回执再定点修复，不提前打业务验收勾。

随后B只读交叉复核发现newkey同source重放先前只核validation_hash，可能把改变activate_ack或If-Match的意图重新记为已受理。主线批准定点修复后，prepare已受理分支和accept两条已受理分支均核原acceptance的intent_hash、validated_head_revision、validation_hash，不以SUBMITTED当前头推测原CAS。变化统一409 IDEMPOTENCY_CONFLICT，在新增幂等/审计/Task之前拒绝；同原body与原CAS的新key仍返回原Task。新增6条纯边界后Store34+工具6共40/40通过（1.25秒），Ruff/格式通过，再次冻结。第5真实工具组内增加两负例并断言三类记录数量不变，16计划数量不虚增；尚待真实执行。

首次真实档启动前另按真实FRAMEWORK cwd只读import发现新工具以`tools.*`包导入会缺repo根；主线批准仅新两工具修双上下文sibling导入，未改公共PYTHONPATH。真实同cwd/plain module import16库存通过，新增独立子进程回归后工具7/7通过（1.26秒），Ruff/格式通过，再次冻结。它是工具启动修复，不是SQL业务通过，16真实计划未变。

原execute首轮真实38档33通过/1失败/4未跑，保留`evidence/python-execution-provider-failed-01-clock.json`。其中前12个新execution组实际通过，包含原202完整清单、幂等负例、1644最终回滚、完整items重验；失败在清理时钟工具将Decimal转str，MySQL1232拒SET timestamp值类型，尚未执行四个后续边界组。主线允许仅工具四个同类SET绑定点改用精确Decimal，生产Store未变；新增实际PyMySQL数值escape/毫秒/重置协议测试后工具8/8通过（1.35秒），Ruff/格式通过，待真实复验，不先标16组全通过。

主线后续真实复验38/38通过（13.75秒），回执`evidence/python-execution-provider-http.json`，包含16个新增execute协议组及既有初始化/validation。原202完整manifest、原Task读取、不同意图拒绝、1644最终回滚、最终TTL与上海跨日边界实际通过。首轮失败保留。生产Store/fixture/checks继续冻结；该成功仅隔离协议，素材真实C扫描证明/双方范围跨execute及生产账户/身份/能力/指标权威来源、平台发送与核验仍未因此完成。
