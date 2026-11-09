# Rule Simulation S2b：暂存与完整发布的下一最小交付

状态：S2b仍为独立设计，staging/publisher尚未实现。主线候选SQL约束档原62+新8已70/70真实PASS（22.85秒），不代表完整simulate链路或来源authority。S2a六文件保持冻结；交叉复核已确认raw/JSON绑定修正的纯合同边界。本文不是新来源issuer、成功模拟或执行资格。正式迁移、公共API/facade/签名用途仍由主线批准与接入。

## 交付范围与阻断

下一步建议先做独立暂存/发布writer及真实SQL技术专项，不一次接原POST、历史GET、enable、调度或平台。writer必须接收已验证且绑定当前SessionTransaction的联合来源票据，不能接受请求提交的expected count/root、TRUSTED字符串或任意实体成功列表。生产provider默认None，新的模拟必须在创建连接、BUILDING或后台任务前503。历史成功重放由独立当前授权读取路径负责，不因生产provider缺失而重算或篡改旧结果。

持久writer本身不能补齐当前尚未实现的真实授权/来源facade：原rules.read、当前Rule可见性、Rule owner与操作者完整账户交集、独立实体/账户日预期、040精确profile与048真实发行必须由受控联合facade验证。SQL技术provider只能在主线显式本轮127.0.0.1:13306/UUID/SELECT DATABASE三重guard下使用；其SQL证据不得升格为生产平台权威。联合facade未就绪时可测试约束/暂存协议，不能声称真实simulate链路完成。

## 输入快照：真实行与原始来源根

simulation_id与snapshot_id分别生成独立UUID，前者为构建/原Simulation身份，后者为同物理头中的持久输入快照身份；二者不等于Rule scope、manifest或publication。snapshot_id只有在头、完整账户/单元行及绑定证据已持久化之后才对应真实输入，不以生成UUID视为成功。

持久输入由三部分组成：头中有界规范声明及其input_hash；账户表真实账户/币种/时区/业务日窗口/独立单元根；单元表每个预期(account,business_date)的SELECTED或已证明MISSING与精确cell/账户快照/sequence/expectation_hash/selected_hash。头固定040 profile/version/hash、publication cutoff及capture_sequence_max，不能在后批重新latest。被选cell可以来自不同此前完整publication，不能强行重写为anchor代际。

原始数值来源必须能从这些不可变引用完整重建：每个selected_hash要覆盖精确cell证明、事实成员根与原始Decimal/NULL输入、实体/账户/币种/业务日归属及预期证明；source_selection_root按固定长度分帧与版本域聚合这些选择。不是只hash返回行数或UUID。adapter按同一cutoff重新读已冻结048事实，保留NULL与合法0之别、每账户业务日和币种，不跨币求和，先聚合分子再比率。

当前063没有额外逐实体“原始metrics JSON”表；不能宣称已直接复制全部原始指标。该八表方案成立的前提是联合facade能证明引用事实/成员/值的发行后不可变、完整重读及根可复验。若现048/056护栏不足以证明这一点，必须暂停writer发布并向主线提出新增有界输入行/证据字段，不用result叶值冒充所有原始输入，不静默扩063或假设来源永不修改。NULL/未知币种仍可能形成合法UNKNOWN，但缺发行者/缺完整预期不是正常UNKNOWN。

## 准备与分批暂存

建议独立新文件rule_simulation_staging.py、rule_simulation_publisher.py及专属tests/tools，现Store只作为输入prepare/revalidate入口。具体所有权需主线批准，不直接修改冻结文件。建议方法边界：

- prepare_build(session, prepared_input)：只在新当前事务内复验精确票据/Rule CAS/完整范围/来源，分配独立头与snapshot，冻结完整输入声明；写头和精确request pointer同一外层事务。不自行commit，不把PreparedSimulationInput跨提交重用。
- append_accounts/append_units(session, build_reference, bounded_rows)：每批重新当前授权及精确已持久来源复验，绑定request当前sim/epoch、nonce摘要、BUILDING及未过期租约；真实顺序与expected根由facade逐行提供，不从写入COUNT反推预期。每批行数及编码字节双重有界；完整账户最多50000、单元最多350000，不能一次Python持有全部行。
- append_results(session, build_reference, entity_batch)：S1输出每批最多200实体、每实体最多20叶，按字节/参数上限进一步拆分；实体与全部叶在该批同事务写入。只接受原完整五字段叶投影并核实体归属/币种/AST稳定索引，不接任意客户端结果。
- verify_persisted(session, build_reference)：按账户/单元/实体/叶主键流式重读重算，返回仅绑定该事务/当前构建的私有完整性票据；不能公开接facts_complete=True或调用者提供摘要即信任。

每个批次使用独立短事务；输入/来源auth票据在事务结束失效。先可信当前主体与非锁Rule定位，再来源config全局UUID→metric/profile→account clock及完整成员→rule clock/head当前锁读，最后构建/request锁；不先锁Rule头再倒序锁来源。真实最后锁顺序须与source facade、原Rule写方共同核验；尚未批准前不自己新增共享锁序。外部I/O、issuer网络和全量hash文件读取不放SQL锁内。

已提交前缀不能因后续Python异常称全部回滚。错误/取消不发行结果，BUILDING保持不可读或按当前nonce/epoch CAS标FAILED/CANCELLED。取消必须有界完整await连接和本build任务退出；不能遗留shield任务后标清理成功。没有自动续租、自动接管、重复计算或物理删除。本轮失败键重试仅同完整意图显式新build与epoch+1，旧半包保留且旧nonce不能seal新请求。

## 封存：一次事务，不以COUNT替代完整根

先在已完成staging上做有界重读，再在最终当前事务重核所有会变化的来源/权限/Rule CAS与request/build身份；最终实际SQL校验不得使用旧RR快照掩盖刚提交的行。头排他锁必须阻止末批并发追加，子表插入父状态锁与publisher锁需真实双连接验证；若无法在短事务核完完整根，必须设计不可变stage seal/proof再请主线审定，不能把锁外旧摘要直接当最终完整性票据。

验证至少包含账户全集有序根及窗口总数、所有预期单元一一对应且MISSING有独立证明、真实实体全集identity根、每实体固定leaf_count且索引0..leaf_count-1齐全、原S1完整results_root、输入根和实际源根；count相等不排除错行/换序/换值。结果流必须真实EOF，所有批次sink确认完成。合法完整空实体流只允许独立预期数确为0，账户/单元仍完整，不靠空查询制造成功。

随后在同一最终事务取SELECT UTC_TIMESTAMP(6)作为sealed_at，要求不早于evaluated_at，并精确保留微秒；expires_at=sealed_at+15分钟。expires判定采用now>=expires失效。eval参考与真实最旧observed不改成seal时刻，15分钟不是数据新鲜度豁免。

同事务顺序依063当前约束为：精确READY audit及PENDING outbox→BUILDING头CAS为READY（填完整根/统计/seal/expiry）→当前request由PENDING变COMPLETED（写原JSON/raw/hash）。完成后再提交；任一1644/约束/CSRF授权漂移/nonce/CAS失败整笔回滚。头READY加audit但request未COMPLETED的技术不完整提交不能被公开查询或重放接受，公开门禁必须要求三者精确关联。这个多行提交责任无法用延迟FK替代。

原Rule revision、状态、clock和RuleVersion均不因模拟结果自行更改；模拟单独audit/outbox，不伪造原Rule业务事件。S2b不增加enable/分析建议资格。

## 原Simulation13与字节重放

最终封存从精确SQL头及有序首min(200,condition_count)叶构造原Simulation13；count超过200才有真实可消费cursor，完整空叶时cursor null。不能按前200叶重新计算统计/root。首叶取(entity_id,condition_index)复合主键自然顺序，不对叶数组作集合比较。

request同时持久存储JSON语义、一次序列化后的原UTF8 bytes和SHA256(bytes)。OriginalSimulationReceipt必须核raw解析、存储JSON和SQL头/实际首叶投影三方严格语义相等；保留原bytes，不以MySQL重排JSON重建旧响应。另有合法Simulation13 raw且自身hash正确但头/叶/cursor不符仍失败。SQL JSON相等表达式/原UTF8检查尚需实际MySQL验收，数组顺序必须保留。

旧成功key先当前会话/原rules.read、Rule可见性及冻结完整账户当前读取范围核验，再返回原bytes；不因当前Rule head、profile最新版本、source新代际或旧IfMatch单独重绑旧结果，不延长expiry。当前读范围失效仍拒绝且无旧正文泄露。具体原接口重放授权与历史定义可见性由主线facade核对，不通过新的write/CAS规则改写既有幂等语义。

cursor不可改写进旧bytes。新会话拿旧receipt时旧session cursor可能失效，通过新GET不带cursor取同simulation首叶，产生当前会话新cursor；不是新模拟、不续期、不改原成功receipt。历史记录即使超过expires可按当前授权只读；不授enable，也不物删。

## 条件明细分页

原POST之外的GET /rules/{rule_id}/simulations/{simulation_id}/conditions为已批准技术扩展。page_size仅20/50/100/200，复合after(entity_id,condition_index)严格签名，绑定固定domain/version/session/actor/tenant/当前auth及全范围指纹/Rule与simulation/snapshot/原revision/input与result根/size/expiry语义。签名用途待主线登记，不占用其他MAC用途。无cursor取首叶并按当前授权发行新cursor，不暴露nonce/对象路径/provider凭据。

读取只认READY+精确COMPLETED请求、完整头/绑定hash和实际子表；坏raw/JSON/头、缺行/根不合、未知发行不降为空页。过期历史页仍保留原expires；当前权限/范围变更使旧cursor409或原权限错误，不能继续泄露冻结范围。所有序列化仍原13字段，新增质量信息只保留内部证据，不擅改公开DTO。

## 资格分离与最小真实矩阵

READY是完整授权计算被持久发布，允许TRUE/FALSE/UNKNOWN及合法稀疏。原WORKFLOWS第4节的coverage/关键字段/归因成熟/最旧observed等质量约束用于后续可执行建议/分析，不新增“全TRUE”或unknown_count=0的enable门槛。第5节15分钟内同版本成功simulate是确认的必要来源；enable本身仍需原当前权限/CAS/范围等，S2b不实现确认，不用一个eligible同时代表两种能力。

主线真实队列建议先小型完整SQL技术链：

1. 缺provider零连接/零build；真实合法输入引用/根持久化及独立snapshot不别名。
2. 多账户不同时区/币种、跨日窗口、MISSING/NULL与合法0、完整空实体；独立预期错误/来源坏proof阻止READY。
3. 两批以上staging后错误/取消，无成功receipt，既提交前缀不公开；旧epoch/nonce无法写或seal新build。
4. 实际SQL少尾/重复/换叶/换归属/坏根不seal；真正完整多页全叶与S1重算一致。
5. 完整seal与audit/outbox/request原子，注入1644八表差异严格回滚；双连接同key仅一份成功、后批与seal竞争。
6. 不同空白/对象键序原bytes可精确重放；wrongraw加正确自身SHA、叶换序/错值、非法UTF8拒绝；新会话首叶不改旧receipt。
7. SQL微秒.123499/.123500/.999999、expires边界两侧；过期历史可读但不续期/不授enable。
8. 当前read撤销/跨租户/任一成员转属、Rule/profile/source漂移及cursor篡改均真实拒绝；有序页无重漏且自然EXPLAIN记录。

上面是完整S2b未来矩阵，当前仅候选SQL护栏子集已按文末回执通过，其余暂存/真实来源/模拟API未执行。先通过小链再谈50k×7日或大量实体容量；索引/候选DDL/42纯测不代表真实源、平台、全模块或大数据验收。


## 候选SQL阶段实测与联合facade精确缺口

主线原62+候选8实际70/70 PASS22.85秒，`evidence/python-rule-simulation063-candidate-sql.json`，仅约束/技术SQL形状；候选八表24trigger、raw及回滚已实际验证，仍无正式063/模拟API/来源authority。此结果不闭合下列联合facade缺口。

可直接复用的纯核验：`metrics_query_store.py:99 publication_validation_binding`核完整PUBLISHED头绑定，但函数注释及实现都明确不发行权威；`metric_profile_query.py:80 validated_public_profile`核原12字段、proof/独立observed列/当前config及hash，调用者必须先按共同顺序取得真实当前行并沿原rules.read授权，不能调用原monitor分页给Rule额外授权；`metrics_aggregation.py:50 MetricAccumulator`保留原分子/NULL/ratio及币种口径；`metrics_query_result_contract.py:276 ExpectedStreamVerifier`可复用流式排序/完整EOF的算法原则，不能直接构造旧QuerySourceIdentity冒充新Rule上下文。

048实际具备发行后不可变护栏：`048_metric_fact_versions.sql:253`实体维度U/D拒绝；`:280`PUBLISHED头U/D拒绝；`:293`起cell/fact/绑定子表仅BUILDING写入、发布后不可改/加/删。因而可按精确PUBLISHED行、完整子成员/事实根验证后保存引用；但PUBLISHED字符串与结构FK本身不证明可信issuer真实核验，必须额外调用真实source verifier，包含各cell实际publication而非只验anchor。读取历史source的当前禁用/撤销规则需正式source provider精确实现，不能用旧source字符串永久授权。

056只给原`orbit_metric_query_snapshot`追加独立unit/membership根及不可变trigger，不是面向Rule的公共预期发行表，更不是可无条件复用的Rule issuer。现`ExpectedUnitManifest`固定旧query hash、原scope身份、统一date_from/date_to；`ExpectedUnitProvider`方法收到旧scope/query/source。Rule窗口按每账户IANA业务日展开，Rule专属manifest可源自ACCOUNT或RULE，不能把它塞成025私有scope或伪造旧manifest后调用MetricsQueryResultStore。

现有`MetricsQueryStore.select_source_anchor`从`:359`调用`authorize_metric_scope`，`_profile`和各batch票据仍绑定旧MetricReadContext；旧公开入口需要monitor.read。`MetricProfileStore.lock_exact`在`:391`后仅允许launch动作，不能供simulate增加launch.read/edit。联合facade应采用公开纯profile验证+明确Rule内部来源读取接口，而不是改原公开权限或复制整个Store。

Rule侧`rule_scope_references.py:335 revalidate_rule_members`已沿原双方scope、account clock、排序ID当前SHARE读完整成员；但现签名要求tuple并将全体最多50000成员及返回值放内存，且返回字段不含timezone。不能称其已经提供有界Rule输入流。需要root授权新的manifest批次facade按account_id keyset迭代并在当前account clock下逐批验证整个成员根/归属，补真实timezone，最后Rule clock/head精确CAS；不能只调用每页可读性而漏掉全体成员撤权。`capture_rule_scope`是新范围首次消费（包含creator/action/绑定）而非已保存Rule模拟的通用读取，不借它重新给协作者加私有creator限制。

### 建议最小新接口（待批准，不已实现）

1. `RuleSimulationInputFacade.capture(session, action_ticket, intent)`：同事务当前锁完成原Rule及全部当前scope/profile/source/独立预期校验，返回不可变snapshot及该实例私有issuer的完整输入绑定。缺provider在SQL前503；不用kind字符串签发。
2. `resume(session, action_ticket, persisted_build)`：只从精确SQL头/输入行恢复固定cutoff，重验当前动作/完整范围/依赖，签发新`BuildStageTicket`。ticket绑定实例、实际SessionTransaction、tenant/actor/Rule/revision/sim/snapshot/input_hash/epoch/requestpointer/nonce摘要；不接受调用者根/count替代SQL验证。旧`PreparedSimulationInput`不能跨commit转票据。
3. `iter_account_batches/iter_unit_batches/iter_entity_inputs(session, ticket, after, limit<=200)`：分别给真实当前授权账户、有独立预期证明的完整单元、由已冻结事实重建的深不可变指标输入；每个batch为facade实例+当前ticket签发的typed batch，不接受任意字典。每批独立事务先resume重新发行；存储只保留身份/根/行，不保留跨事务能力。
4. 新staging writer `prepare_build(session, prepared)`、`append_accounts(session,ticket,batch)`、`append_units(...)`、`append_results(...)`均不commit；ticket/typedbatch必须同issuer/session/transaction且绑定精确request与当前BUILDING。append_results必须来自真实输入经S1求值的sink，不接受外部成功布尔。批次提交由明确最外层owned connection orchestration管理。
5. 新publisher `seal(session, actor, intent, build_reference)`：不收调用者summary/root/count或facts_complete。方法内部通过facade发行当前ticket，读取并验证实际SQL完整输入及结果流，重算原S1有序根/计数，再取SQL UTC6封存；按本设计audit/outbox→READY→COMPLETED同事务。公开首叶投影来自该事务验证的实际SQL行；原字节/JSON/头首叶三方一致。若原始事实/完整结果无法有界重读就明确失败关闭，不靠请求摘要发布。

`BuildReference`是普通可持久定位，不是授权；每个批次/最终seal都必须重新签发当前票据。旧成功receipt读取另以当前read可见性/冻结完整scope验证，不因新构建source不可用或当前head不同强制重新绑定。最终私有完整性票据也不得跨提交复用。上述接口需主线先裁决source/expected及scope facade文件所有权，再开发；不直接改当前冻结Metrics/Rule公共实现。
