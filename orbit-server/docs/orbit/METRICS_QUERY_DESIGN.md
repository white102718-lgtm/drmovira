# 监测查询合同与后续查询领域边界

## 当前交付边界

最初合同阶段仅新增`python/orbit_api/metrics_contract.py`及其纯测试。随后主线已正式采用048指标事实和049查询快照并完成限定SQL专项；本页后文分别记录阶段边界。合同解析或DDL成功仍不证明指标已采集、coverage可信或可生成执行建议。

teamai-recall已检索ORBIT指标/币种/账户时区约定，没有匹配结果。本文以`data/ORBIT_Codex开发PRD/contracts/openapi-current.json`、`API_SEMANTICS.md`、`WORKFLOWS.md`、`DOMAIN.md`、`PERMISSIONS.md`及原PRD为准。只读参考仓库不构成ORBIT来源或授权。

## 原接口与权限

首个核心查询是`POST /api/v1/metrics/query`，原成功响应为200 `Metrics`，需要`monitor.read`和原monitor菜单。没有对应的指标GET查询路由。原`GET /entities`和`GET /entities/{id}`同需`monitor.read`，但Entity不是本次实现范围。

`POST /reports/channels/query`、`/reports/operators/query`使用同一MetricQuery/Metrics合同及`reports.read`；`POST /launch-stats/query`使用`launch.read`。渠道Tab和渠道报表必须走同一CHANNEL查询领域，不各自实现不同聚合。

查询型POST不创建广告写命令，但原合同仍要求16—128字符ASCII Idempotency-Key及16—255字符CSRF。相同key/原payload重放同一冻结结果，不同payload冲突；每次包括重放均须当前授权。该端点无If-Match要求。跨租户头只按原SUPER规则，不扩大当前主体数据范围。公共认证、CSRF、路由、游标purpose及门禁由主线负责，本模块不注册。

## 五种严格模型与解析入口

全部字段均必需，包含可null字段；不填默认值，不接受额外属性。模型从原baseline直接比较属性集合及required集合，防止手写漏字段。

### MetricQuery：13字段

|字段|原边界与处理|
|---|---|
|date_from、date_to|有效严格YYYY-MM-DD，端点都包含；开始不晚于结束，共1—93业务日|
|dataset|ACCOUNT、CAMPAIGN、ADSET、AD、OPERATOR、CHANNEL、ASSET、LAUNCH|
|metric_profile_id|完整UUID，允许大写并规范为小写，拒绝花括号/裸32位|
|scope_snapshot_id|UUID或null，不能把普通列表cursor当scope|
|channel_id|1—64码点文本或null；原输入不是UUID-only，不能擅自收紧；用户短文本NFC/trim并拒控制字符|
|operator_user_id|UUID或null|
|q|0—100码点；先NFC/trim再计长，拒换行/控制字符；名称/代码搜索与外部ID精确语义交Store实现|
|sort|spend、impressions、clicks、purchases、roas、cpm、name|
|direction|ASC、DESC|
|cursor|1—2048码点字符串或null，保持不透明原值，不trim/解MAC|
|page_size|严格整数20、50、100、200，拒字符串、bool和浮点类型|
|granularity|SUMMARY或DAY|

`parse_metric_query(raw: bytes, *, account_local_today: date | None = None)`返回独立dict。未知字段400 UNKNOWN_FIELD、结构/类型400 INVALID_STRUCTURE，字段值/枚举/窗口边界422 FIELD_VALIDATION_FAILED，路径为转义后的JSON Pointer。重复JSON键、非有限数及非法UTF8拒绝，说明不包含原输入值。

未来日期不能用服务进程UTC日或上海日代替。若提供可信`account_local_today`则立刻校验date_to；未提供时明确只完成格式/窗口校验。后续Store取得真实账户时区与冻结预期集合后，须对每个账户调用`validate_account_local_today`重验。该内部参数不来自HTTP正文，datetime不能冒充date，不能据未给today的解析成功宣称已完成未来日期检查。

### MetricValues：12字段

`spend`、`impressions`、`clicks`、`registrations`、`purchases`、`purchase_value`、`roas`、`cpm`、`ctr`、`cpc`、`cpa`、`usage`均为必需且允许null。

非null值严格为字符串，原正则`^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$`，最多28字符；拒float/int/bool、符号、前导零、指数表示及超过6小数。原合法字符串原样保留，不量化、不补0，不从其他字段推算。计数指标在本DTO也按原Decimal字符串合同，不偷改为Number。

### MetricRow：15字段

`tenant_id` UUID；`owner_team_id`、`operator_user_id` nullable UUID；`entity_id` 1—64字符，不要求是UUID，平台数字字符串前导零不得丢失；`name` 0—255码点；`channel_id` nullable UUID（注意与请求channel_id文本约束不同）；`product_name_snapshot` null或1—100码点；`currency`原schema仅规定长度3；`metric_profile_id` UUID；`business_date` null或有效ISO日期；`account_count`、`ad_count`严格整数0—2147483647；`values`为完整MetricValues；`quality`仅COMPLETE/PARTIAL/STALE/UNKNOWN；`coverage`为非null规范Decimal字符串。

不擅加媒体、总代、账户名、质量flags或平台状态字段。原PRD需要而本DTO无法携带的展示维度要单独提出技术扩展，不挤进name、忽略需求或增加第九模块。

### MetricTotal：原8字段

`tenant_id`、`currency`、`metric_profile_id`、`values`、`account_count`、`ad_count`、`missing_count`、`coverage`。UUID、币种长度、计数和Decimal边界同上。原合同确为8字段，不能为早期人工误数为9而添加属性。

### Metrics：8字段

`items`为0—200个MetricRow；`next_cursor` null或1—2048字符串；`scope_version`严格安全整数1—9007199254740991；`snapshot_id` UUID；`data_as_of`有效带时区ISO时间；`missing_count`严格整数0—2147483647；`query_snapshot_id` UUID；`totals`为0—1000个MetricTotal。

`parse_metrics(raw: bytes)`用于服务端出站或受信持久值边界。任一行、总计、版本或格式非法都拒绝整包，以503 METRICS_DATA_UNVERIFIED固定脱敏说明返回，不把坏持久值映成用户422、不返回剩余“正常行”。本地内部指针不暴露到503错误。合法结构仍不证明来源、质量真值、币种或totals口径，必须由后续查询/发布领域核验。

## 尚缺的真实数据与语义

当前015真实事实表是`orbit_account_spend_day`及history，只含账户日spend、币种、coverage、冻结投手/团队、来源及版本。没有`account_daily_fact`完整指标表、fact_versions、published/query snapshots或广告实体目录。账户百万事实压测只证明该消耗读模型，不能继承为监测模块容量或指标验收。

040—044 MetricProfile版本及目录提供配置来源核验，不提供指标事实。Meta PAGE/PIXEL/APPLICATION身份观察不是广告Entity或Insights。Entity需真实campaign/adset/ad内部ID、父树、预算拥有者、预算与configured/effective状态、observed_at及可信capability_version；缺失不能填unknown版本制造200。

原PERMISSIONS区分：当前Entity按账户当前归属；历史指标按事实冻结operator/team先授权再聚合，不随当前转移重写。USER本人，TEAM本人加明确管理团队，SUPER当前目标tenant；无归属历史仅TEAM/SUPER。MetricProfile为tenant配置，没有Ownership，不发明新的provider菜单动作。

监测非空scope消费须新monitor专用动作helper；不借`accounts.read`或计划500上限。必须保留原快照成员上限50000、actor/tenant/当前授权指纹与不可变成员校验。不能对所有monitor查询额外强加账户菜单，也不能绕过scope授权读取私有快照；共享接口由主线统筹与A对齐。

## 后续Store设计建议，尚未实施

1. 根线先批准048/049具体表设计，再由独立发布领域提供完整预期单元和受信分页manifest。事实grain至少tenant/account/entity_type/entity_id/business_date/profile/breakdown，加source_version、batch、observed_at、quality、is_deleted、currency和冻结投手/team/channel/product/attribution_version。完整批次才发布单调generation。先选同粒度最新完整tuple、再过滤删除、再聚合，100→120→迟到110必须保留120。
2. Query Store只消费真实已发布generation，冻结query_snapshot及输入/授权/profile版本；基于稳定generation分页，不每页重做完整事实验证。每页/幂等重放仍当前授权，撤权403、越域404、范围变化409；签名须绑定actor/tenant/全部筛选/排序/page_size/query snapshot。
3. SUMMARY按dataset实体，DAY额外按账户当地同名business_date；DST不能固定加24小时UTC。先过滤历史owner范围再聚合，同渠道跨用户不泄露别人指标。单一查询内按currency/profile分组，禁止换汇；totals是同筛选全量授权结果，独立于当前页，不由客户端累加。
4. coverage按冻结预期(account,day,profile)完整单元数/预期数，不能按返回行数；完整空单元才可为0，缺页或字段缺失不得补0。关键spend/impressions/clicks/purchases/purchase_value及规则用指标不齐不形成可执行建议；freshness用最旧关键observed_at，超过30分钟STALE。成熟期与内部quality_flags单独冻结，不擅改原响应。
5. 原`reference/03_原合同保留章节.md`给CPC=spend/clicks、CPA=spend/指定转化；WORKFLOWS第29行首期conversions=purchases，两段合读后首期CPA分母为purchases。此阶段不计算。舍入原文未定，后续如批准最终比率6位ROUND_HALF_UP须有独立algorithm_version与测试，汇总前不round，源值超过6位拒绝。参考项目registrations CPA及零分母填0不能照搬。
6. usage仅ASSET有原明确含义：当前范围distinct(account_id,external_ad_id)，依据核验ad→creative→asset映射，跨日和totals均须去重；非ASSET未定义可null，不猜广告数。日内素材映射不可可靠拆分要PARTIAL/UNMAPPED，不重复分摊整日金额。LAUNCH仅真实自动创建映射，不能按名称猜归属。
7. 第一批内部完整可信样本验证ACCOUNT/CAMPAIGN/ADSET/AD，再依赖冻结归属与映射补OPERATOR/CHANNEL/ASSET/LAUNCH；原enum不删，未就绪来源或dataset明确503，不假空成功。不先搭占位UI。q包含查询、任意比率排序需EXPLAIN和真实容量；当前账户性能不能冒充监测性能。

分工建议：B只新增合同与后续获批的查询Store/定向测试；A负责实体与monitor授权scope消费；C或主线负责精确profile发行读取及真实指标发布源；root负责共享权限/路由/CSRF/幂等/游标purpose、编号与串行真实SQL。所有这些后续实现均需主线明确授权，不修改正在开发的A/C/shared文件。

## 当前验证

### 048/049 schema设计（候选历史与正式采用状态）

候选评审原稿保留在`docs/orbit/sql-drafts/048_metric_fact_versions_candidate.sql`与`049_metric_query_snapshots_candidate.sql`。主线已正式复制至`python/orbit_api/migrations/048_metric_fact_versions.sql`和`049_metric_query_snapshots.sql`，完成初始化及下述限定SQL专项；尚无Metrics查询HTTP/生产来源验收。048为7表：租户capture/publication时钟、完整发行头、不可变实体名称层级维度、完整捕获cell、AD日版本、独立素材映射、独立自动计划映射；049为5表：查询manifest、预期账户、独立排序行、独立totals、原幂等请求。

本方案明确选择**最新完整cell优先**，不是跨cell逐AD回填：cell键为tenant/account/business_date/profile_id/精确profile_version/breakdown(TOTAL)。capture_sequence在实际采集前分配；publication generation是完成发布的全局单调顺序，两者不同。source_publication_id只锚定截止generation，实际查询的最新cells可以来自同profile/version在截止水位之前的不同完整publication，不能声称锚点批次包含所有事实。

核心SQL形状（仅说明，未执行）为：

```sql
WITH candidate_cells AS (
 SELECT c.*,p.generation,
  ROW_NUMBER() OVER (
   PARTITION BY c.tenant_id,c.account_id,c.business_date,c.profile_id,c.profile_version,c.breakdown_key
   ORDER BY c.capture_sequence DESC
  ) AS cell_rank
 FROM orbit_metric_capture_cell c
 JOIN orbit_metric_publication p
  ON p.tenant_id=c.tenant_id AND p.id=c.publication_id
 WHERE c.tenant_id=:tenant AND c.profile_id=:profile_id AND c.profile_version=:profile_version
  AND c.business_date BETWEEN :date_from AND :date_to
  AND p.state='PUBLISHED' AND p.generation<=:source_generation
), latest_cells AS (
 SELECT * FROM candidate_cells WHERE cell_rank=1
)
SELECT c.id,c.account_id,c.business_date,f.id AS fact_id
FROM latest_cells c
LEFT JOIN orbit_metric_ad_fact_version f
 ON f.tenant_id=c.tenant_id AND f.cell_id=c.id
WHERE /* 此处再应用真实历史冻结owner/team谓词；不在求最新cell之前过滤 */ 1=1;
```

预期账户/合法scope成员的集合过滤可以先限制候选账户ID，但owner/team、墓碑、指标/q/channel条件不能先筛旧版本再求最新。最新cell完整空结果会抑制所有旧AD；最新完整cell省略旧AD也不从旧cell补漏。fact的墓碑只在选定cell后过滤；LEFT JOIN位置须保留完整空单元，不能WHERE删掉全部空cell。合法空的哪些源字段确实为0使用受信`empty_field_mask`说明，缺失字段仍null；账户原name/external_id由cell的不可变ACCOUNT快照冻结，不能空结果时从当前账户目录回填。

#### 不重复存储全文名称与层级

`orbit_metric_entity_snapshot`按tenant/account/entity_kind/entity_id/content_hash查找不可变快照，ACCOUNT→CAMPAIGN→ADSET→AD逐层引用真实父快照；ACCOUNT内部ID必须等于account_id。名称原文≤10000码点和原平台数字串只在此表存一份，跨业务日/profile/cell复用不变的相同层级快照。父名称/层级变化会产生新父快照，依赖它的子快照也使用新的完整父绑定，历史快照不随当前目录改写。

content_hash仅为去重候选键：issuer须在同事务读取候选，逐字节比较原name/external_id/内部entity_id/entity_kind/account_id及parent_snapshot_id的完整规范tuple，完全相等才复用。相同hash但原文不同必须固定脱敏失败，不能`INSERT IGNORE`后复用、靠不区分大小写比较或只比较摘要；并发唯一键竞争后也执行同一完整核对。维表拒绝UPDATE/DELETE，初期不自动回收ABORTED发行留下的未引用快照，后续留存策略另审，不宣称已交付回收。

cell保存ACCOUNT snapshot ID及固定类型；fact明确保存四个snapshot ID和固定类型。组合FK同时约束tenant/account/type，系列/组/广告还约束真实entity_id及对应父snapshot ID；cell组合FK额外绑定相同account_snapshot_id。因此不能拿另租户/另账户/另层类型或合法但不相关的父快照拼接事实。AD外部ID在读取AD维度时取得，usage仍按distinct(account_id,external_ad_id)核验，保留前导零；事实不再重复四段LONGTEXT或父外部ID。

q执行次序是：固定截止选完整最新cell→当前历史授权→选定cell内实际fact/完整空账户→按dataset收集相关distinct维度ID→对这些维度原文执行原包含搜索并精确比较外部ID→以匹配维度ID半连接后聚合。名称包含使用参数化且转义`%`/`_`的原contains谓词，不能用前缀索引或FULLTEXT分词替代而漏掉中间子串。维度索引用于tenant/kind/account候选和external_id精确匹配；包含检索最坏仍须扫描相关distinct全文，尚未证明容量通过。应通过真实EXPLAIN验证先缩小相关维度，不能对百万事实每行重复取LONGTEXT；也不能先q筛旧cell导致新完整空结果回退。

排序/聚合在同一固定截止与授权范围构建一次：NULL末尾，原sort/direction及稳定entity/currency/date分组键确定ordinal。后续只读：

```sql
SELECT ordinal,payload_json FROM orbit_metric_query_sorted_row
WHERE tenant_id=:tenant AND query_id=:query_id AND ordinal>:after_ordinal
ORDER BY ordinal LIMIT :page_size_plus_one;
```

ordinal是已物化的稳定结果键，不是OFFSET；每页仍先调用`authorize_metric_scope`，比较原query/actor/tenant/profile/授权/scope证明后读取原totals，不重扫全部事实。root新增monitor-only helper已真实13/13通过10.02秒，证据`python-metrics-scope046-http.json`；该证据仅证明scope消费501/空范围/撤权/错主体/ownership边界，不证明本查询Store或容量。

索引包括完整cell版本候选、历史owner/team查询候选、fact仅按选定cell JOIN，以及query/query_id/ordinal键集。source只存六可加源值，采用DECIMAL(34,6)容纳原最多28位整数，不沿用015的DECIMAL(27,6)；发行前仍须原字符串≤28字符、小数≤6，禁止让MySQL自行round。最终SUM/DTO超28字符必须整包503，不能截断或float。ratio由主线独立`metrics_aggregation.py`负责，不在本schema计算。

FK逐列要求：tenant/id CHAR(36)沿原utf8mb4_0900_as_cs；profile版本VARCHAR(64)显式utf8mb4_bin与040相同，profile_hash与原040列一致。publication提供(tenant,id,generation)及完整profile版本组合唯一键；049组合FK同时绑定publication_id/generation/profile_id/version，不能拼另一批水位。claim子表绑定query的同一build_generation；新claim前须在父写锁下仅清理旧代，再提高代次，所有写/清理SQL必须带query_id+预期build_generation并核token，迟到旧builder不得清别人的新代。READY行和totals不可再I/U/D；cleanup_requested=1后新读404，原query/request头保幂等墓碑，不自动删除后让同key产生新UUID。

发布头绑定完整预期cell count/hash及实际count/hash；FINAL应独立校完整行数/摘要/同源/当前授权，不能只信计数列。READY之外不提供半包结果，BUILDING无第二份同key构建，失败/资源预算拒绝保留原意图状态，不新增原schema外202。authority_kind、JSON证明或表中TRUSTED字符串本身都不是可信发行证据；真正的受控生产来源核验由独立issuer完成，query不授信。

现有依赖为001 tenant、010 material_asset、012 ad_account、021 plan_version、025/043 scope_snapshot、040 profile_version/system_configuration的原复合键。010部分列继承库默认collation，空库harness创建为0900_as_cs；采用候选前还须主线实际检查information_schema列类型/charset/collation，不能以静态文本推定升级库一定相同。本页最初静态评审时尚未验证SQL可执行性；现根线已在本轮UUID隔离库实际初始化并验证下述FK/触发器边界。已有升级库差异及完整publisher/builder并发锁协议仍需后续专门验证，不能从本次SQL样本推出。业务锁顺序预期授权/账户scope→profile→短发行头→query父行→排序行/totals，不持query父锁反向取得前面的跨域锁。

保留评审项：完整Entity/account名最多10000码点，不可变维表保留全文；超过MetricRow.name的255上限时对应查询503，未批准展示投影前不截断、不伪造空名或别名。物化50k×93可能465万行，结果行与小证明均独立有界而非一个无限JSON；构建总行数/字节/CPU预算须依据实际容量明确配置和失败码，不擅定全局50k查询上限（50k只是原非空scope上限），也不截断结果/总计。query复用需匹配actor/完整query hash/发布水位/授权及scope/profile证明，不泄共享他人结果。留存/回收调度、整批全totals、50k/百万事实性能尚未交付。

仅本模块纯测试，覆盖baseline属性/required完全一致、原全部枚举、四档page size、13必需字段、NFC与精确UUID、日期93日/闰日/可信当地today、12项Decimal正反边界、nullable不补0、完整响应数组边界、出站坏数据503。没有执行HTTP/MySQL/浏览器、没有真实采集或平台执行，不据此标监测功能完成。

当前定向`pytest python/tests/test_metrics_contract.py -q`为236/236通过，0.58秒；两Python文件Ruff lint及format检查通过。首轮纯测暴露测试将28字符上界误写成29、Total误计为9，以及公共pattern错误分类不适用于此Decimal边界；均已在本模块/专属测试修正，不改共享代码。主线要求出站坏值503后，所有响应负例改为整包拒绝且不泄内部字段位置，未减字段边界覆盖。

### 候选冻结时的专项建议（后续实测状态见末节）

当前048静态自审为7表/18触发器/111个已注释列/17外键，仅1个LONGTEXT；049为5表/14触发器/64个已注释列/10外键。名称/索引标识符长度≤64、无重复触发器名、四快照绑定字段与无重复全文名称的静态断言通过；当时未执行SQL，仅为静态检查数量。随后已由主线正式采用和实测；两个候选保留评审历史，不自行回改正式迁移。

建议独立真实DDL专项按以下边界拆分，所有数据仅隔离UUID库，失败记录固定异常类别/SQL code，不打印payload：

1. 空库应用所有前置迁移后执行048/049；实际核对information_schema类型/collation/唯一键/FK/trigger。重点040 profile版本utf8mb4_bin，tenant/id 0900_as_cs，010素材列不能靠假定。已有升级库还需先检查与实际列一致；DDL成功只证明schema可执行。
2. 插入同tenant/account合法ACCOUNT→CAMPAIGN→ADSET→AD及同cell四快照正例；分别替换为foreign tenant、另account、错误kind、另一真实entity_id、同account但另一父树、fact与cell不同ACCOUNT快照，逐项真实FK或CHECK拒绝。父类型NULL与非NULL父ID组合必须拒绝，防MySQL CHECK UNKNOWN绕过。维度U/D真实拒绝；hash同键冲突只能证明唯一键，**不能证明issuer核对全文**。
3. 创建两publication，逐项拼接另一generation、另一profile_id/version的049 source锚点，组合FK必须拒绝；精确正确五元组可写。BUILDING阶段generation为NULL不能被049冒充已发布来源。此项不证明source_proof的生产权威性。
4. 独立构造BUILDING→SEALED→PUBLISHED合法头与完整cell/fact/bindings；PUBLISHED头UPDATE/DELETE、cell/fact/两个绑定INSERT/UPDATE/DELETE逐表拒绝，含试图迁移parent的UPDATE。维度自始不可变。SEALED拒绝新增child；ABORTED仅允许原受控清理。需明确BEGIN/COMMIT隔离，不能仅assert触发器文本。
5. 049 READY后行/total/预期集合I/U/D拒绝；cleanup_requested=1只在受控清理允许D，原query/request保留幂等墓碑。两个builder以不同generation竞争，旧代INSERT/清理不得影响新代；SQL工具须带真实token/CAS，这一部分需要builder协议而非FK单独保证。
6. 真实选择SQL样本：完整cell110含AD-A、120完整空、迟到再发布110必须仍选120且无AD；120完整仅AD-B时不回填旧AD-A；同profile截止锚点应可读取更早多个publication的有效cell，截止之前不能出现未来generation。此项需要执行候选SELECT和独立受控publisher夹具，**DDL本身不保证正确最新选择**；完整expected集合与count/hash核验、合法空零字段、来源分页完整性、hash碰撞核原文仍属publisher专项。
7. q样本原名包含中间子串/百分号/下划线/大小写与重音区别、原external ID前导零精确匹配；按既有原搜索口径验证，不用prefix或FULLTEXT替代contains。真实EXPLAIN应证明选定cell后只扫描相关distinct维度，不在每个fact重复读LONGTEXT；百万事实与4×10000码点名称容量仍另排，不把小样本选择正确称性能通过。

### 下一步只读QueryStore边界提案（尚未实现）

拟新增独立`metrics_query_store.py`，仅返回可信候选来源与原样冻结元数据，不发布事实、不写query物化表、不生成Metrics成功响应：

- `select_source_anchor(session, current, query) -> MetricSourceAnchor`：已由调用者完成真实monitor授权；tenant/profile版本严格匹配，读取PUBLISHED截至generation及原profile hash，未有可用可信来源明确503。TRUSTED字符串不是受信provider，正式调用须独立issuer/主线完成来源核验；当前无provider不得靠此方法将数据库样本授信。
- `iter_latest_cells(session, scope, query, anchor, *, batch_size=200)`：同一实际只读快照/事务，tenant/profile/version/date/cutoff固定；null scope不强加50k上限，非空只使用原真实冻结成员；先选最新完整cell再按真实冻结owner/team过滤。逐批稳定account/day/cell键集，支持空集合，不OFFSET，不跨页另取source head；必须拒绝复用错tenant/profile的anchor。
- `iter_selected_facts(session, cells, *, batch_size=200)`：只读取上一步精确选定cell的事实，过滤其墓碑，不找旧cell补漏；带tenant和完整cell组合，取得四快照安全字段及真实映射状态，不把asset/launch未知映射变为已核。允许批次中合法空cell无fact且保留coverage候选说明。
- `select_matching_dimensions(session, selected_snapshot_ids, query)`：仅相关distinct ID分批读取原name/external_id，完整原contains/精确ID语义由既有合同决定；不能将UUID/名字推成账户拥有者、也不能把维度存在当当前Entity读或平台能力证据。最终name>255/坏持久字段按受信数据503拒绝，不截断。

账户当地未来日必须在已核冻结timezone与可信各账户today上复验，不能用SQL服务器UTC日/上海日代替。历史owner权限、scope完整性/授权水位在后续每页仍实时重验；上面迭代器不是公开cursor或授权缓存。总计/coverage/质量/日期与币种聚合、受控构建claim/幂等和049写入另由后续明确批准阶段实现，不能用这批READ候选直接返回虚构完整Metrics。

### 真实schema工具交接与限定实测证据

新增`tools/metric_fact_schema_checks.py::run_metric_fact_schema_checks(admin, database, cases)`，固定`METRIC_FACT_SCHEMA_CASES`为7组。入口和夹具构造器同时限定127.0.0.1:13306、`orbit_py_it_`加32位小写hex数据库，并核当前DATABASE()一致才允许写；无HTTP/平台调用，不注册生产Provider。复用既有21条严格FIXTURE profile SQL种子，另建本工具随机账户/维度/发行/query；已存在的数据不覆盖、不清理其他builder，不执行任何DDL。

当前工具实际断言覆盖元数据/列注释/collation/仅一个LONGTEXT/32触发器，完整四快照FK与父层NULL防绕过、维度不可变及hash唯一键，五元发行锚点，PUBLISHED头和四个child逐表真实I/U/D拒绝，READY三个child真实I/U/D与请求墓碑、旧generation不能插入/按旧代清理不删新代，完整空120及迟到110/省略旧AD选择SQL，原包含字面通配字符与前导零外部ID。两个历史映射使用真实存在的SQL对象行：素材明确UPLOADING，计划DRAFT；不伪造CLEAN、有效素材引用或真实投放归属。每个FK负例使用新合法cell和未占用AD grain，避免先撞唯一键误当目标FK通过。

query排序行/total以技术小JSON测试DDL，不称原Metrics完整响应；expected/hash/manifest仅技术SQL值，不称独立issuer核验了来源和完整清单。未实测生产provider、hash碰撞原文核验协议、同时两个builder/token互斥、当前真实授权/coverage/质量/比率、完整q候选Store与容量/EXPLAIN；旧代清理断言仅证明工具显式generation谓词不误删，不能冒充完整并发租约协议。工具异常仅固定SQL code，不输出SQL参数/原异常正文。

专属纯护栏`python/tests/test_metric_fact_schema_tool.py`为25/25通过0.19秒，两新Python文件Ruff lint/format通过。纯测仅验证隔离目标/实际库错配/绑定SQL/标识符allowlist/失败回滚与脱敏/四快照组装/contains转义等，不执行MySQL、不计七组真实schema通过。主线已报告048/049实际初始化成功及原scope13重验，该事实与本七组未执行严格区分。


主线实际回执`docs/orbit/evidence/python-metric-facts048-query049-sql.json`为20/20 PASS、10.53秒（旧monitor scope13组+新schema7组）。048七表、049五表与合计32触发器已真实初始化；七组实际执行全部FK、发布后I/U/D、READY/代次、最新完整空/省略与迟到110、名称包含/前导零断言。证据严格为`SQL_ONLY_NOT_PLATFORM`：不是事实publisher、Metrics QueryStore/HTTP、生产采集/平台权威或百万事实容量验收。工具/正式迁移在主线检查点期间冻结；独立只读QueryStore的新源码与测试另属在制，不计本轮交付。

### 独立窄READ实现（纯测完成，未做SQL/HTTP联调）

新增`python/orbit_api/metrics_query_store.py::MetricsQueryStore`及专属`test_metrics_query_store.py`。当前100/100纯测通过0.84秒，两个新文件Ruff lint/format通过；纯测使用内存SQL替身和已登记完整头的测试Provider，**不是MySQL、生产来源或Metrics响应验收**。现默认Provider=None，四入口均在数据库/授权查询之前固定503、零SQL；无路由注册、048/049写入、发行、Task或完整Metrics返回。

准确方法为`select_source_anchor(session, actor, original_query)->MetricReadContext`、`iter_latest_cells(session, context, read_batch_size=200)`、`iter_selected_facts(session, context, cell_batch, read_batch_size=200)`、`select_matching_dimensions(session, context, cell_or_fact_batch)`。实际范围必须内部调用当前`authorize_metric_scope`，不接受调用者自造tenant/scope/generation。私有WeakKey能力绑定本Store、实际AsyncSession、实际外层SessionTransaction、原13字段副本、完整授权/scope摘要、当前profile头及固定来源截止；自行构造句柄/票据、跨Store/session/transaction、来源Provider被换、当前权限/团队/scope/profile改变均拒绝。批次处理用Store登记的不可变真实行，不信调用者改动展示用rows。每次迭代/维度读取重验当前授权，旧source publication也在同事务重新核验，不只验最后一批。

独立`MetricReadSourceProvider.verify_publications(session, scope, query, heads)`必须是纯DB锁/核验，不允许事务中网络调用；每次heads最多200。返回恰好对应全部实际头的`tuple[PublicationValidationReceipt]`，每个receipt.binding按`PUBLICATION_BINDING_FIELDS`顺序含23项：tenant/id/generation/profile/version/hash/authority、sourceConfig+revision、完整规范sourceProof哈希、state、expected/captured count及根、fact_count/capture_sequence_max/manifest根、publisher/request_id与三个UTC时刻。Store逐项严格类型和值比对，禁止True/标签、缺头、多头、重复、替换根或bool冒整数。`publication_validation_binding`只是规范化工具，**不是来源核验器**；实际Provider仍须独立核生产来源/完整登记证据，不能调用该函数后无条件返回receipt。ISOLATED_TEST执行既有127.0.0.1:13306 UUID库闸门，TRUSTED还须真实非空sourceConfig版本；kind/state字符串本身没有授信效果。

来源anchor与后续候选均在调用方同一读事务固定截止下读取。先当前锁读profile头，普通来源/事实读取沿该事务一致视图；不拿当前锁读的新anchor拼接旧RR事实快照。Provider负责独立当前来源锁重验。cell选择用更高完整PUBLISHED单元的NOT EXISTS反连接，始终在固定generation以内，历史owner/operator在外层处理，不能把newer子查询收窄到调用者本人从而回退旧数据。cell按account/day键集、fact仅选定cell的cell/id键集，各批1—200，不OFFSET、不从旧cell补AD；null scope没有50k上限。返回六个原定点源值为规范字符串/null，不浮点、不提前round、不假零；原满28位整数可读，超合同/坏值503。

q仅在当前已授权批次的related distinct维度中执行完整contains，并转义字面!/%/_；先查有界身份/长度元数据核候选无丢失，再仅传回匹配全文，避免把未命中10000码点名称整批传回Python。只有实际1—64位ASCII数字q才增加external_id精确分支，保持前导零，不把中文名称送进ASCII列比较。完整原名保留，命中结果超过公开255上限时503；未命中合法长名不会截断或假替换。尚未验证SQL执行计划/百万事实速度，不能将键集与LIMIT称容量通过。

本阶段仅对实际选中cell的冻结IANA时区+可信服务器时钟进行未来日期复验；完整预期账户中的缺失单元、当前账户时区口径/缺失覆盖、全部totals/质量/完整构建幂等仍留后续正式查询阶段。初期只支持ACCOUNT/CAMPAIGN/ADSET/AD；其他原enum保留合同但此Store明确503，不伪填映射。原cursor处理属于049完整结果层，本窄READ拒绝直接消费公开cursor，不将内部键集句柄冒充原响应cursor。


### 窄READ真实工具待执行交接

新增`tools/metrics_query_read_checks.py::run_metrics_query_read_checks(client, admin, headers, password, cache, database, cases, *, identities=None)`，固定`METRIC_QUERY_READ_CASES`为10组。默认一次复用现`prepare_plan_identities`的990360/990361真实登录/角色/TEAM关系夹具，故主线应独立档运行，不与已经创建同固定身份的旧scope函数混跑；也可明确传入现成identities，不猜复用或覆盖已有用户。

工具仅在本轮13306 UUID库建随机`it_metric_read_<16hex>`技术证据表。在任何Store读取前，独立记录完成SQL样本头的完整23字段binding JSON及hash。Provider从原登记返回receipt，严格比对登记完整tuple及当前锁读的独立METRICS/UNTESTED配置enabled/revision，不回显待查head计算值冒充来源，不注册生产authority。每批≤200，SQL参数绑定、随机表名严格allowlist；无凭据写文件/输出，无平台调用。ExitStack在创建证据表成功后即登记只删本表的退出清理，在撤去每项原accounts.read grant后立即登记原grant恢复；监测撤权、profile停用、登记篡改及source enabled临时变动均try/finally恢复。自建来源配置最后升版为2用于证明旧发行失效，属于本工具新建样本，不回拨已有配置版本或重写PUBLISHED头。

10组覆盖：实际AsyncSession默认None零SQL503；SUPER/USER/TEAM按冻结历史owner而非当前账户owner；原HTTP501/空scope在无accounts.read下完整消费；120完整空/省略旧AD/迟到110与新owner不回退；同一批多个旧publication拒一整批（清空本次观察，再断言实际同批登记核验）；真实中文/字面%_/!/前导零q；全部事实/维度原字段及六源分子的null/定点值；伪造句柄/批次及跨外层事务失效；当前monitor与profile停用；登记manifest被篡改且hash自洽仍拒、当前技术config停用/升版拒绝。它仍不是完整Metrics响应、生产来源、publisher、覆盖率/质量、并发构建或容量/执行计划验收。

专属工具纯护栏`test_metrics_query_read_tool.py`30/30通过0.61秒，工具与纯测Ruff lint/format通过；未自行执行DB。原READ源码100纯测与本30工具纯测不能相加称130个真实业务验收；后续真实档计数由主线实际回执决定。


READ独立实际回执`docs/orbit/evidence/python-metrics-query-read049-http.json`为16/16 PASS、10.63秒（bootstrap6+新READ10），不是旧scope13重验。已真实执行默认None零SQL、三身份历史归属、原501/空scope无accounts.read消费、最新120/空/省略/迟到110/新owner不回退、每个旧publication独立登记与整批拒绝、原中文/字面通配/前导零搜索、全原字段及定点/null、私有事务票据和当前动作/profile/config撤销。仍严格为技术SQL登记来源，不是生产发行、完整Metrics服务、结果构建或容量通过；保留现有VALUES弃用警告，不将警告抹为不存在。READ源码和真实工具冻结，049结果阶段独立推进。
