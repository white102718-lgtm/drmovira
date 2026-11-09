# 规则Simulation S2最小持久化提案

状态：S2a独立纯合同、同事务输入捕获/复验协议及063 SQL候选已实现；定向36/36纯测通过（1.01秒），4个Python文件Ruff检查通过。本轮没有运行SQL、HTTP、DB服务或平台调用，也未注册路由。实际staging、SQL结果流式核验、seal发布、成功回执持久化及真实来源/授权facade尚未实现，不能称持久化Store或Simulation业务闭环已完成。S1解释器57纯测只证明计算/流完整性，不是指标权威或成功Simulation。

## 先修正两个不同的资格

原`contracts/WORKFLOWS.md §4`要求coverage=1、关键字段齐全、最旧关键observed age>30分钟为STALE、归因/稀疏等限制“可执行建议”；`§5`规则状态行只规定enable必须15分钟内同版本成功simulate。主线已复核裁决：完整授权计算可以有UNKNOWN/稀疏，不增加“所有条件TRUE”“unknown_count=0”或全成熟才可启用的业务门槛。

因此READY只代表完整已授权模拟已持久发布，结果可以TRUE/FALSE/UNKNOWN或合法完整空实体流。质量摘要是后续分析/建议原流程的证据，不能共用一个eligible字段代表所有能力。没有发行者、无法证明完整预期/授权实体全集、hash/proof损坏时503且绝不READY；不得把这些故障降为一包正常UNKNOWN。S2不实现enable，不发平台/模型请求，不授广告/分析执行资格。

## 不改变原API

原`POST /api/v1/rules/{id}/simulate`保持rules.read、当前Rule可见性、真实CSRF、单一Idempotency-Key与quoted If-Match、空正文，成功200仍原Simulation13：

`id/rule_id/revision/snapshot_id/hash/account_count/scanned_count/hit_count/unknown_count/false_count/conditions/expires_at/next_cursor`。

revision为被模拟的原Rule版本，snapshot_id为本次真实持久化的规则观察输入快照身份，不冒用Rule scope UUID或048 publication UUID。原Conditions最多10000，本方案首POST只取前200叶子但完整结果已全部落库，next_cursor有真实消费入口；统计/完整根不按页计算。

批准方向的技术扩展：`GET /api/v1/rules/{rule_id}/simulations/{simulation_id}/conditions`，rules.read+当前Rule可见性及冻结完整账户当前双方范围。query仅page_size20/50/100/200、cursor可选，未带cursor从真实首叶开始；返回同一原Simulation13（本页conditions，不重算/换快照）。新signed用途拟`RULE_SIMULATION_CONDITION_CURSOR_V1`，由root统一登记，不使用旧Rule/Metric cursor。

cursor绑定domain/version、当前session/actor/tenant、当前auth版本/完整scope指纹、Rule与Simulation UUID、被模拟revision、结果/输入根、当前页size、after_entity_id/condition_index。模拟期限只用于同版本启用确认，不等同历史明细自动删除；历史读取保留原expires_at不续期。实际保留期限尚无裁决，本轮不做物理清理/不发明retention。

幂等成功响应原样保存（包括当时next_cursor），当前rules.read/Rule可见及完整冻结范围当前交集重新核验后先返回，不能因当前head/最新profile改变额外失败或重绑旧结果；新的模拟/enable另核当前版本。原键异完整意图409。新会话拿旧成功键可能得到旧session绑定cursor：通过新GET不带cursor重新取得首叶和当前session cursor，不改旧成功JSON/expiry/结果根。上述原字节重放及新会话首叶规则已获主线裁决，不把幂等receipt偷偷改写成新cursor。

## 来源协议：默认缺失、不伪装公共Metrics权限

后续完整发布facade的来源依赖建议显式注入；当前已实现的最小构造是`RuleSimulationStore(*, access=None, source=None)`，仅提供`prepare_inputs(session, intent)`与`revalidate_inputs(session, prepared)`，不写SQL或生成READY。下面sources/expectations为后续联合facade的角色划分，不是现有方法。sources和expectations为明确内部对象，不接受请求中的TRUSTED/路径/connection/任意回调；缺失时先沿原HTTP当前授权/CSRF/旧成功读取语义，新的计算明确503，无成功快照。普通生产默认为None。ISOLATED_TEST须root显式注入且固定实际host127.0.0.1:13306、UUID库、SELECTDATABASE、当前scope/完整证据逐项核实；不靠kind字符串或直接INSERT CLEAN/READY。

后续完整来源facade接口角色（尚未落地；现有`rule_simulation_protocol.py`只声明`RuleSimulationAccess`与`RuleSimulationSource`抽象边界）：

- `RuleSimulationReadContext`：由Store同实际SessionTransaction、当前RuleAccess/OwnerScope和精确同Rule manifest签发的内部只读票据，不能由HTTP构造或跨commit重用。
- `RuleMetricSource.prepare(session, context, evaluated_at)`：只读确定profile绑定、采集cutoff、真实发行者验证回执与独立预期根；不联网，不在持SQL锁时发外部调用。
- `RuleExpectedUnits.prepare/revalidate(session, context, source)`：明确按每账户窗口给独立预期(account,date,profile)与授权实体全集根。不能把返回facts/cells COUNT当预期，不能套原uniform-date MetricReadContext/025私有snapshot。
- `RuleMetricSource.read_batch(session, fresh_context, persisted_source, cursor, limit<=200)`：只按已持久输入锚点/单元读取并核原048不可变数据，逐实体聚合原分子后比率；当前事务重新授权，不复用旧context。
- adapter结果必须可核到完整真实单元/实体清单；已知合法实体的缺单元/NULL等可诊断UNKNOWN，不能为不知道的foreign/缺清单实体造占位对象。

实际源锚点须区分一个publication cutoff与多个被选capture_cell的实际publication/generation：现MetricsQueryStore通过最新已发行anchor冻结cutoff，但选中单元可以来自不同此前完整publication。不能强行把所有cell改成anchor.id/generation，也不能每批重新“latest”。每单元明确绑定cell UUID/实际publication/generation/capture_sequence、精确profile/version/hash、历史归属与独立expected证明；全体选择有固定有序根。

可复用公开纯验证`publication_validation_binding`、040 proof严格解析/毫秒roundtrip、S1、窗口核心、MetricAccumulator。不能直接调用有monitor.read和025 scope FK的公开MetricsQueryStore/ResultStore，也不能伪造MetricReadContext或复制其整段Store私有方法。需要root分配共享内部来源验证facade或明确新的Rule专属SQL桥与authority入口；已有provider不能仅因方法名相同视为支持Rule上下文。

## 最小8表DDL轮廓（063候选，尚未执行）

全部utf8mb4_0900_as_cs、UUID同tenant组合FK、中文COMMENT；精确profile.version保留bin collation；所有hash严格64小写十六进制。JSON限于有界声明/小型证明，不把全部账户/实体/叶子塞一个JSON。

1. `orbit_rule_simulation`：tenant/id及独立snapshot_id UNIQUE（同一物理头行明确保存完整规则观察输入快照，不是只有虚构UUID）；actor/owner当前捕获上下文、Rule UUID+revision+bodyhash、同Rule manifest UUID/member根、精确profile版本/hash/proof/sourceconfig版本、algorithm/source cutoff/expected根；BUILDING/READY/FAILED/CANCELLED内部状态、build token/fence/lease、SQL evaluated_at/created_at/sealed_at/expires_at、完整统计/identity/results/business hash、固定失败码与有界质量摘要。READY要求全部统计/根/完成时间非NULL、sum计数等式、scanned INT32，不能默认0表示完成。唯一约束同时提供(tenant,id,rule,revision,manifest)/(tenant,snapshot_id)/(tenant,id,actor,intent)作为精确下游FK。
2. `orbit_rule_simulation_account`：PK(tenant,simulation,account_id)，每个真实冻结账户一行，精确同Rule manifest成员FK、capture时caller+owner校验上下文、真实currency/timezone、窗口date_from/to/local_today、独立预期单元数/根/权限根；原范围1..50000，窗口最多7日，不推测或补UTC。只存每账户常量字段。
3. `orbit_rule_simulation_unit`：PK(tenant,simulation,account_id,business_date)，FK到账户；精确profile与预期issuer证明、selected cell_id nullable（明确MISSING而非假0），实际publication/generation/capture_sequence、expected/received页/实体/fieldmask/oldest_observed/quality绑定；真实cell FK到048并由应用验证独立列一致。缺失单元也只能来自可信独立预期集合。本层窗口最多50k×7，但仍须实际容量/EXPLAIN，不以有界SELECT宣称通过。
4. `orbit_rule_simulation_entity`：PK(tenant,simulation,entity_id)按规范UUID排序，FK到账户；持久account/currency/实体TRUE|FALSE|UNKNOWN、完整叶子数/实体根/原源维度身份。真实实体必须由受控048/独立清单证明，不能生成新UUID充广告。S1每批<=200输入，SQL可按主键排序流给S1，不全图Python排序。
5. `orbit_rule_simulation_condition`：PK(tenant,simulation,entity_id,condition_index)，精确FK到实体；原ConditionResult5投影（value VARCHAR28 NULL+原Decimal regex，result三值，reason nullable<=64），index0..19且READY验证每实体正好compiled_leaf_count。分页只用此复合PK，after二元组独占绑定完整page水位，不OFFSET；FK叶子不可跨账户/Rule/代际。
6. `orbit_rule_simulation_request`：PK(tenant,actor,key_hash)，intent含操作/Rule/原IfMatch（无body）；当前构建id/epoch、PENDING/FAILED/COMPLETED、原成功Simulation13 JSON。COMPLETED永久不可改/删。失败键可原意图重新准备独立新build，不把旧半包升格；旧build token/ledger pointer CAS阻迟到seal。新build头先写再ledger精确FK，无不可延迟环；并发同key只有一份发布，未完成冲突409，不改原接口成202。
7. `orbit_rule_simulation_audit`：只追加有界事件，关联精确simulation/build/source/result根、actor/request、固定原因/前后内部状态；不写Token/全请求/全部叶子。不能借057 action CHECK（无SIMULATE）或伪造Rule revision/event。
8. `orbit_rule_simulation_outbox`：精确FK到audit，单次唯一投递，原子与READY/成功ledger/audit同事务。S2不启动dispatcher、AI、广告。

必须的实际索引：所有子表上述tenant/simulation前导PK；头当前actor/key/lease索引（是否自动恢复仍关闭）；请求主键唯一key；状态/租约索引仅供将来安全清理，不等自动重跑许可。条件分页用自然PK EXPLAIN验证；选cell/cutoff/时间窗口复用048已有索引，缺索引另提专属DDL，不修改旧源。

## BUILDING与发布的事务边界

Store拟`simulate(engine, actor, authorization, csrf, key, rule_id, expected_revision, request_id)`拥有明确独占connection/短事务分段，原route由root适配，不能在当前旧RuleStore.simulate外层begin内直接再嵌套长构建。`page_conditions(session, actor, authorization, rule_id, simulation_id, query)`为短只读新事务。不对外暴露prepare/seal或调用者可填的success/eligible。

P0短事务：当前rules.read、CSRF和完整幂等意图；原成功回执先当前对象/冻结完整scope读范围重验后原样返回。新key无provider则503。新key以非锁probe定位精确Rule版本，再按原共同顺序当前actor/owner→source config(全局UUID有序)→metric clock/profile→account clock/完整成员→rule clock/head精确CAS；不能先锁head再倒序等待account/config。原manifest成员现在tuple最多50k，S2需root授权有界cursor facade做完整ID/root/current双方检查，不复制多份50k列表或放宽私有scope。

P1先冻结SQL UTC6 evaluated_at、当前完整授权成员、每账户窗口、真实source/expected根，写BUILDING/account/unit和请求claim；所有写只属于本build。长构建不一直持actor/全账户/head SHARE，不跨事务复用授权票据。原source发行者证明与外部I/O必须在开始前完成，SQL锁内只做受控验证/读取；未知缺源不创建READY。

P2每批新事务重验当前原权限/全局scope指纹和冻结依赖，再精确源批次→S1→本build实体/叶子staging。sink只异步写本build，单批最多200实体/4000叶子，再按安全绑定数/字节拆SQL；不以单次executemany声称服务端批量。每批验证ledger pointer/token/fence/lease，原有half-open连接设置使用owned connection同CID恢复，不污染池。未知SQL失败/取消原样终止，不能改成空结果。

P3真实EOF后再流式SQL核账户/单元/实体/叶子完整有序根及数量；S1摘要不足以证明DB全部写齐。最终重新按P0顺序完整当前caller+owner范围、同Rule/同revision/body/manifest、精确profile/source配置/证据、request claim/fence/租约；任意变化409/403并不发布。一次事务写READY+原成功JSON+audit+outbox；SQL trigger核非NULL/格式/数量/精确关联/状态形态，不假称MySQL JSON CAST等于Python canonical。完整根由Store实际流读已写SQL行重算再比S1。故障1644全回滚。READY后头/子表禁止I/U/D，不能事后给READY补叶子绕manifest。

失败或取消时本次没有200/COMPLETED；已提交staging保留不可公开BUILDING或经CAS标FAILED/CANCELLED，不能声称Python异常自动回滚所有已提交批次。取消要精确await连接/本build任务退出，未证明退出保留引用/现场。S2不自动恢复、重试模型、发送或物理删除失败staging；未来清理独立受控方案。

## 15分钟与新旧来源

主线已裁决expires_at=实际完整seal SQL UTC6+15分钟，`now >= expires_at`不能用于确认；相同key重放不续期、不刷新旧事实。evaluated_at与sealed_at分开，长构建不能把旧数据时刻伪装成seal时刻；后续建议的新鲜度仍按真实最旧observed判断。微秒与到期边界已做纯测，实际SQL seal/微秒往返仍待验证。

后续enable只接受同tenant/Rule/原source revision的完整成功模拟，原状态/IfMatch/当前权限/完整范围/profile可用性必须成立；会生成新Rule revision时另保存activation(source_revision,enabled_revision,simulation_id)，不改旧Simulation.revision。S2不写activation、不将UNKNOWN/稀疏偷偷追加成enable禁止条件、不把成功确认当执行建议许可。

## 最小实施与验收顺序

建议root先批准S2a来源/持久纯合同与单一ledger/seal内部Store，再批准八表候选和只读页；最后接原POST和新GET，保持provider默认None。独占新文件建议`rule_simulation_contract.py`、`rule_simulation_source.py`、`rule_simulation_store.py`、`rule_simulation_routes.py`与专属tests/tools；共享RuleStore/原route/rootapp/凭据用途/正式迁移仍root统一分配，不自行接公共。

真实SQL技术源需沿既有048 publication/cells/facts+056独立预期语义完整发布并逐项验证，显式ISOLATED_TEST guard；不能只INSERT一个结果READY或kind=TRUSTED便称来源权威。实际工具至少：原13/全叶分页/合法空与NULL；新旧key/CAS；同Token撤权/跨tenant/全成员转属；profile/源代际漂移；BUILDING不可读/后批失败/取消；DB结果少尾/重复/坏root不seal；同key双连接唯一发布；1644八表回滚；sealed头/叶子追加与修改拒绝；200+实体/4000+叶子多页全对账和自然EXPLAIN。15min两侧与微秒、真实SQL/HTTP分别留证。

容量先小型真实完整链再针对50k账户×7日和大量实体/20叶子测量，不把schema存在、LIMIT/索引、S1纯测或固定SQLfixture当生产Meta、模型质量、10万实体容量或完整模拟模块验收。


## S2a本轮冻结与下一接点

本轮冻结`rule_simulation_contract.py`、`rule_simulation_protocol.py`、`rule_simulation_store.py`、专属`test_rule_simulation_store.py`及063候选。36项纯测覆盖深不可变输入、原Simulation13结构投影、完整计数/根匹配、.123499/.123500/.999999微秒边界、15分钟严格失效、原JSON字节重放、缺省依赖零SQL、同实例/SessionTransaction票据和授权/版本漂移、取消与来源错误。纯测抽象provider仅验证协议，不能作真实SQL来源或当前权限已实现的证据。

063草案包含8表、24个trigger，只有静态形状检查通过；正式DDL、FK/trigger语义、并发、EXPLAIN和数据容量均未执行。READY头的存在不能单独作为公开成功条件；后续读取必须同时验证精确COMPLETED请求及完整发布关联。数据库无法用延迟约束在提交时替代应用层同事务完成head/receipt的责任。所有实际根、完整叶子顺序与源证明必须由后续publisher从持久行重算，不能以SQL计数或纯投影替代。

下一步须主线审查联合授权/来源facade及候选，然后分配真实staging/seal writer：当前authorize仅允许原动作/对象探测，不应先锁Rule head导致config/profile→account→rule顺序倒置；联合source负责全体成员、真实发行、独立预期及当前Rule锁的一致复验。默认None继续在SQL/来源调用前503。当前不实现enable、不引入通用eligible、不对外发Simulation成功、不接广告/模型或清理。


## 交叉审查后：原字节/JSON/精确发布绑定

A发现候选原条件只能分别证明response_bytes自身SHA256正确和response_json对齐READY头，尚不能证明两份响应相同；当前没有发布/重放入口，不把此草案缺口描述为生产已发生漏洞。本轮补正后42/42定向纯测通过（1.07秒），4个Python文件Ruff通过；前36项记录为补正前历史范围。

OriginalSimulationReceipt不再接受单raw：必须同时提供已存JSON及由精确SQL头、按(entity_id,condition_index)原顺序读取的首批最多200叶、原next_cursor组成的完整预期响应。bind的header固定11键，加入conditions/next_cursor后按严格原Simulation13解析；raw、存储JSON、可信投影规范语义逐项相等才可使用，任何调用方提供的“预期响应”不构成来源。原byte字段仍原样保存与重放；比较时允许对象键序/空白差异，数组顺序和叶值不可变。publisher必须先证明首批完整及所有源/SQL结果根，不能把此receipt结构验证器当源issuer。

候选CHECK及request发布trigger增加JSON_VALID、CAST UTF8原字节为JSON后与response_json原生JSON相等；MySQL JSON相等对数组按顺序比较，不使用双向JSON_CONTAINS冒充相等，也不将MySQL重排的JSON字节当原bytes。纯测新增另一份合法Simulation13 raw且其自身hash正确、但与JSON/头/首叶/cursor不符的拒绝，以及叶序交换反例。实际MySQL需验证该CHECK/CAST表达式可采用，正常不同空白/对象键序可通过，wrongraw+matchingbytehash、交换叶序/叶值错误均拒绝并整事务回滚；这些SQL负例尚未执行，静态字符串检查不等于数据库护栏通过。
