# 原Metrics结果构建阶段方案与纯层边界

> 当前公开查询检查点（2026-11-09）：`evidence/python-metrics-public060-three-viewports.json` 实际19/19，三视口9/9；固定Python4701与前端872通过。最新完整来源的无匹配筛选合法零值与缺失NULL已分别证明。本文早期“未接公开入口”等为历史阶段记录；当前仍缺生产Meta发行、其他业务Tab完整流程及容量验收，独立SQL技术夹具不能替代。

主线已批准独立metrics_query_result_store.py及READ必要受控恢复接口；公共路由/runner/授权/加密类不由本线修改。048/049原迁移不重写；056补充明确预期manifest持久根。同连接TEMPORARY staging仍须单独实际故障/取消/池隔离验证，纯层通过不表示Store或来源可用，生产Provider继续缺失时零SQL503。

## 1 原合同字段与范围

以baseline WORKFLOWS:49/107/123和原openapi-current为准。首阶段ACCOUNT/CAMPAIGN/ADSET/AD × SUMMARY/DAY，其他原dataset enum保留明确503；不要替它们猜映射。SUMMARY按实体，DAY另按账户当地同名业务日，不能按UTC/上海切日。MetricRow原15字段、MetricValues原12、MetricTotal原8、Metrics原8全部保留，无额外quality_flags DTO字段。实体ID首四种拟用维表真实内部entity_id（reference03:347、WORKFLOWS:53使用内部对象UUID），不把外部平台字符串转整数或混成内部身份。

金额严格原规范字符串/null，六源可加值不round；最终ratios使用现metrics_aggregation版本CPA分母purchases、6位ROUND_HALF_UP、0分母null。各group tenant/currency/profile/version完全一致；usage在首四dataset保持null。缺失字段不假零，合法完整空cell仅按已核empty_field_mask各位给对应合法零。聚合后超28字符/6小数503，不截断或浮点。totals在全过滤授权贡献上独立聚合，不累加当前页，account/ad去重跨日不重复计数。

请求13字段、四档20/50/100/200、7种sort、ASC/DESC、原CSRF+IdempotencyKey均不扩合同。cursor绑定tenant/actor/完整query（不含cursor）、page_size、queryUUID、原source/profile/scope/auth及ordinal；MAC用途METRICS_QUERY_CURSOR_V1已由主线注册并完成用途隔离纯测，结果Store尚未接入。空scope不是全部；null scope不硬套50k上限。

## 2 已确认的预期单元、元数据与质量口径

coverage原定义为完整成功的冻结预期(account,business_date,profile)数/冻结预期数，不能用实际cells/facts充当分母。原048完整cell和expected根不包含完全缺失日期的历史owner/team/currency；049 expected_account也不包含完整逐日实体集合。因此纯层先定义独立受信ExpectedUnitReceipt/有界stream，默认None503。顶层manifest绑定当前tenant/actor/subject/auth/scope/query/source/profile及完整unit/member根和数量；unit含真实历史owner/team/currency/IANA/账户快照/归属版本、selected-entity-roster根/数量；entity membership另有界流，避免单unit塞百万AD数组。严格原始完整根/数量对账，禁止True/label、缺项/重复/乱序/多项后默截。receipt结构合法不等于可信来源，生产发行独立实现；技术fixture仍ISOLATED_TEST。

主线已确认：nullable owner_team/operator/channel/product在同entity/currency/(DAY)组内所有贡献值一致时保留，存在多值或NULL混合时输出NULL，不新增按这些元数据拆组。name非nullable，从窗口内最高business_date、capture_sequence、observed_at、snapshotID的真实名称快照选取，不从当前目录或lex MAX(name)猜名。选中的name>255仍503，不截断；未选中的历史长名称不截断也不冒充当前名称。entity_id使用维表真实内部UUID，snapshot ID只参与历史版本定位。

主线已确认quality公开投影：0预期或0完整为UNKNOWN；存在缺失单元或关键字段不全PARTIAL，优先于STALE；完整关键且最旧age>30min为STALE；否则COMPLETE，恰好30min不算过期。只有COMPLETE允许派生比率，STALE的各比率也为null，保留源值供只读，不能将显示质量作为执行许可。空预期集合对外无行/无totals/missing0；内部coverage为字符串"0"并明确无可验证分母。非空但全缺失仍需受信实体/币种元数据才能合法UNKNOWN行或总计，不凭返回事实创造实体。

coverage仅为显示，以精确整数complete/expected计算六位ROUND_DOWN，完整许可只比较原整数是否相等，不比较显示小数。即使分母大于百万且只缺1，显示也不得成为"1"；金额和原比率仍保留既有ROUND_HALF_UP，不被coverage的舍入规则改变。当前算法标识为`orbit-metric-result-v1-coverage6-down-ratios6-half-up-stale-null`。

预期成员流规范已显式升级为`orbit-metric-expectation-canonical-lines-v2`：ExpectedEntityMembership增加真实name_capture_sequence和UTC name_observed_at，并纳入规范成员根。缺失cell时名称仍须来自已登记受信证据及真实不可变快照，不能填0、古早时间或猜anchor序号。v1根不能静默重解释为v2。ACCOUNT对应账户member须独立证明1项；CAMPAIGN/ADSET/AD完整零实体可items=[]，仍按真实预期unit返回分币种totals；只有unit_count=0才无币种totals。零源值仍只由完整empty cell且对应empty_field_mask位证明，没有匹配事实不能冒充合法零。

## 3 有界执行与TEMPORARY staging

由服务显式独占一个AsyncConnection，全builder周期不换连接、不回收给池；其AsyncSession始终绑定该连接。随机表名仅服务端UUID白名单，用户字段只绑定参数。CREATE/DROP TEMPORARY不当作可回滚操作，不用普通CREATE/ALTER/TRUNCATE或隐式commit清空原事务。finally精确DROP本次全部表；取消时shield有界清理，清理失败/连接状态不确定必须invalidate而非交还池。故障/取消后下一请求无临时表/数据污染需实际SQL专项证明。

分层临时表拟为：有界流装入完整预期unit及entity membership；已授权固定截止selected-cell ID集合；相关dimension匹配键；按原group键聚合状态与distinct(account,ad)键；最终有序group。名称只保维表snapshot ID，在命中组最后取全文。每批最多200，Python不保全scope ID、全事实或无限group dict/去重set。MySQL用完整键索引GROUP BY/去重与全局排序；SUM以足够宽DECIMAL中间值，NULL通过完整值计数传播，最终源和ratio由既有Decimal helper严格复验。大范围50k×93可达465万单元，预算需明确bytes/rows/time并实测，不偷偷给null scope加50k限制或截断结果。

SUM、去重和排序均只做一次，最终严格15字段单row JSON写049，完整8字段total独立写；ordinal为冻结全局排序键。NULL在ASC/DESC均末尾，数值用Decimal语义，name用原完整UTF8二进制确定性排序；平局再按稳定entity/currency/day等完整组键。后续ordinal>after LIMIT size+1，无OFFSET、无每页重扫事实。公开response经过parse_metrics严格出站检查，坏持久JSON/数字503整包拒绝。

## 4 049状态、幂等和事务（Store待确认）

T1：当前authorize_metric_scope→真实source与expected manifest→原query/request hash→按原actor/key持久请求意图及BUILDING头，同一事务提交；来源/授权字段自始不变。同key异payload409，同key成功重放必须实时授权及scope/profile/source复验，不能因有缓存越权。其他相同query可复用READY但原request key意图仍独立，不把别人的结果共享。

T2：有界租约claim，query行锁+build_generation/token CAS；未到期别的builder返回明确409 busy，不空202、不无限等。过期只在精确旧代、当前权限/source仍一致时清旧代并CAS新代；保留queryUUID/source cutoff/原意图，禁止自动换latest。构建在同owned连接临时staging，最终事务依固定锁顺序复验scope/profile/source/expected完整根，核完整row/totals hash/count，再按query+generation+token插入049子表并原子READY。中途失败不发布半包，失败状态/固定code保原key，旧builder晚到不能写或清新代。cleanup1后读取404并保留幂等墓碑，不自动删除query/request。

READ私有句柄绑定单个实际SessionTransaction，T1提交后失效。已按批准新增describe_context(session,context)，仅导出真实同事务句柄的有界只读资料；resume_persisted_query(session,actor,queryUUID)自身读取049真实header和规范query，按当前tenant/actor/scope/profile/来源及056根逐项复验，再恢复固定原水位的私有票据。它不接受任意descriptor/raw generation，cleanup或旧无manifest根行不可恢复。READ新增select_dimensions读取全部相关原始名称≤10000码点，局部select_matching_dimensions只供候选，不准用于裁剪聚合事实；结果先以全窗口最新名/精确external_id确定实体，再汇总该实体全窗口贡献，最终选中名称≤255，不丢旧日。

每页T3先当前授权/scope完整消费、对照原manifest与header，确认READY/未cleanup且profile/source有效，再只读取冻结ordinal与原totals；当新数据另发行时不混新旧事实。实际page没有新source导入、没有任务和平台动作。完整capacity/并发同key/租约恢复/审计异常/取消清理/索引计划均由主线串行测试，纯结构或fixture不能替代。

## 5 本阶段纯实现与证据范围

已实施独立`metrics_query_result_contract.py`及`metrics_query_result.py`：有界预期单元/实体成员流的数量、顺序与规范hash对账，单unit与全局成员根分别校验；首四dataset、SUMMARY/DAY的原字段投影，元数据一致性与历史名称选择，精确coverage及质量，比率禁用、原Total独立聚合、七种排序的NULL末尾与稳定平局、四档出站page严格校验。receipt结构验证不等于权威发行，provider默认缺失仍503；本次没有接路由或创建完整查询结果。

专属两文件测试最终实际141/141通过（0.48秒）；四个新Python文件Ruff检查及格式检查通过。包括1000001/10000000分母缺1仍为0.999999、0预期、0完整、30分钟边界、STALE比率null、混币种/租户/profile拒绝、原数组和字段上限。此为纯算法/严格结构证据，不计MySQL、HTTP、TEMPORARY清理、生产发行、完整Metrics查询或容量验收。该历史检查点尚未实施Store；当前后续实现与有限证据另列如下。

上述141是初始纯层历史检查点。本轮v2协议及新Store处于独立开发/回归，不能继承为当前Store验收。主线已采用正式`python/orbit_api/migrations/056_metrics_query_expected_manifest.sql`并实际通过原scope13+SQL7+056新3共23/23（10.83秒），证据`evidence/python-metrics-expected-manifest056-sql.json`。它只证明DDL、精确原32+新增1触发器、16NULL组合、非法根/计数、跨代次冻结和legacy不补签；不证明当前READ恢复或完整结果Store。T1独立冻结unit/member双根、成员数、真实账户数和规范版本；重代次不改根，不能偷用最终rows_hash/totals_hash。

清理状态只有核对原CONNECTION_ID、完成精确DROP和回滚后才为DROPPED。连接invalidated/closed时不再execute，不允许重连新CID后DROP并宣称旧连接干净。异常先脱离池，invalidate另有1秒预算；DROP/原CID核验有5秒预算，重复取消不留下自建cleanup任务。FAILED固定METRICS_STAGE_CLEANUP_UNVERIFIED，纯测的task结束不能代替实际原CID在performance_schema/innodb_trx退出、下次池请求无临时表及设置污染的证据。不得KILL或靠加超时放宽实际断言。

## 6 当前结果构建检查点与公开接线边界

当前独立Store已实现内部T1登记、租约代次、独占连接staging、全窗口实体选择、四dataset×两granularity聚合、完整分币种totals、原子READY发布和四档签名ordinal分页。`MetricsQueryResultStore.run(engine, actor, body, key, request_id, authorization)`是唯一完整拥有连接的内部入口，成功返回原Metrics八字段；仍未注册公共路由，没有生产发行者，也没有页面可用性声明。

本检查点固定八文件窄回归实际366/366通过（2.99秒）：READ101、resume39、result Store31、v2合同及纯结果150、旧schema/manifest工具29、新结果工具护栏16。运行文件为`test_metrics_query_store.py`、`test_metrics_query_resume.py`、`test_metrics_query_result_store.py`、`test_metrics_query_result_contract.py`、`test_metrics_query_result.py`、`test_metric_fact_schema_tool.py`、`test_metrics_result_manifest_tool.py`、`test_metrics_query_result_tool.py`；相关源码/工具Ruff通过。计数仅纯测试，不算SQL/HTTP/清理或容量验收。

独立真实工具`tools/metrics_query_result_checks.py::run_metrics_query_result_checks(client, admin, headers, password, cache, database, cases)`固定八业务组，需主线串行through056运行（bootstrap六组另计）。内容包括默认缺Provider零SQL、201广告全窗口与完整分页totals、三币种已核空与完全未知差异、最新名称中文和字面通配符/前导零ID、幂等意图、租约和旧代次、READY发布后故障原子回滚、真实锁等待取消后原server CID两秒退出及下一池请求无TEMP/设置污染。三个随机技术登记/锁表均仅本轮精确删除；技术profile与事实属于UUID隔离库内SQL_ONLY_NOT_PLATFORM样本，不能升级为Meta采集或发行验证。当前工具尚未执行，任一取消或容量断言失败必须保留失败证据，不能降低字节/行数或释放锁伪造通过。

公开接线最小需要原POST身份与CSRF/Idempotency-Key上下文、真实monitor权限及原13字段交由本Store解析、显式配置DirectoryTokens和内部ResultBuildBudget。两项来源依赖必须由服务端注入：完整PublicationValidationReceipt的生产验证者，以及独立绑定query、预期unit/entity流双根和完整名称证据的ExpectedUnitProvider。两者默认None保持零SQL503；本专项独立预登记原文/hash只用于技术测试，不能作为生产Provider。公共路由及现监测页面仍由主线分配并实际联调，不能把内部200 DTO纯测当作原Metrics业务交付。

首轮真实14档结果为12PASS/1FAIL/1NOTRUN，证据`evidence/python-metrics-query-result056-first-failed.json`：前七结果业务组已通过，最后取消组发现client已结束但原server CID/事务仍活，未满足两秒退出。没有放宽断言、提前释放holder或KILL。修复仅在本次独占物理会话进入业务前设置并核验`SESSION innodb_lock_wait_timeout=1`；正常路径结束在同CID核验恢复原值并commit，再返回池。失效连接不再执行SQL复位，不能以新CID冒充旧会话已退出。实际工具池状态增加原锁等待值对比；原两秒P_S/innodb_trx退出及下一请求无TEMP断言保留。新增七个纯用例覆盖设置、正常还原、取消不重连、CID变化/还原故障隔离及非法初值；仍须主线重新执行完整14档，不能凭纯测改写失败。

原临时dimension重复插入以及BINARY/VALUES语法弃用警告原样保留，未加静默过滤；本轮只处理已证实的取消清理缺陷，后续优化须保持完整来源原文对账及独立SQL验证。

第三轮安全诊断实际为P_S原线程ABSENT、锁等待0、INNODB_TRX仍1、client_closed=true、cleanup_state=FAILED；不能将其解释为原线程仍Sleep。主线保留第三轮失败，Store第三版冻结。本轮只改工具观察节奏：原20ms循环持续读取INNODB_TRX会反复推进缓存last_read，使已退出事务的旧行继续可见。已核[MySQL8.4官方一致性说明](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-internal-data.html)和[官方8.4.0 trx0i_s.cc源码](https://raw.githubusercontent.com/mysql/mysql-server/mysql-8.4.0/storage/innobase/trx/trx0i_s.cc)：can_cache_be_updated第628—644行要求距last_read严格超过100ms，trx_i_s_cache_end_read第823—828行每次结束读都刷新last_read。

因此第一次及之后每次INNODB_TRX观察前均保留125ms不读该缓存的空窗；同CID P_S线程0和刷新后的事务0仍须同时成立，原cancel_at起两秒总截止、holder释放顺序及禁KILL完全不变。安全JSON仍在失败断言前保存。缓存模型纯测证明20ms累计两秒仍可持续旧行、125ms空窗允许刷新，仅证明观察机制，不代替下一轮真实双零/连接池清理验证。未修改Store或把失败改成通过。

主线第四轮已实际14/14全部通过，证据`evidence/python-metrics-query-result056-http.json`。原两秒截止、同CID线程与刷新后事务双零、holder后释放、无TEMP/池设置污染断言均保留；前三轮失败回执继续保留。此次证明bootstrap六组与内部结果八组的真实SQL/读取、来源登记拒绝、四粒度/分页/全窗口、幂等/租约、原子故障及取消有限场景，不证明生产Meta发行、公开Metrics原POST/页面或百万事实查询容量。Store和工具已冻结供主线后续公共API接线，页面纯测另列前端文档，不相互代替验收。


### 2026-11-09：完整来源的筛选空集与总计

依据原 `WORKFLOWS.md:49`，coverage 统计完整成功的预期账户/当地日/profile
单元，不按返回行数计算；`:123` 要求 totals 为同筛选全量授权范围。
公开技术夹具已定位：原完整非空 cell 在 q 无匹配时被错误降为未完成单元。
本修复让受信最新完整 cell 的采集完成状态独立于筛选命中数；缺 cell 仍未知。

有效零逐字段证明：新增同连接、固定白名单 `cell_field_proof` 临时表，按实际已读取
原事实分组记录总行数与六源字段的非 NULL 行数。仅独立 query-bound 预期成员已完整
核验且成员数为零、原 cell.fact_count>0、实际事实数等于声明数、该字段每个原事实
均非 NULL 时，该字段允许派生零。原空 cell 仍须 empty_field_mask 明确许可；
未映射 registrations、缺失 GBP cell、带 channel 筛选或墓碑导致未完整读取的事实
均不能凭空补零。临时表参与原精确反向 DROP 与取消失效流程，不引入 TEMP 自连接。

本批定向 47 项纯测试通过，其中新增 7 项执行生成聚合 SELECT 的 SQLite 替身矩阵，
覆盖逐字段完整/NULL、事实计数不足、缺 cell、原空 mask、未核成员与非空成员。
这不是 MySQL、公开 HTTP 或三视口验收；真实原 14 项及公开筛选专项由主线串行复验。
