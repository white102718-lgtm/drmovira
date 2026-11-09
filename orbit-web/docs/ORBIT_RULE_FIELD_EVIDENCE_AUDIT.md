# Rule15 / RuleWrite11逐字段证据审计（建议，非总台账）

本表仅核对现有代码和已归档证据，不执行测试/浏览器/DB，不修改任何业务代码或勾选总台账。**字段出现在一份parse通过的Rule中，只证明该实际样本，不等于字段所有枚举、上下界和业务流程均验收。** 下列“可建议”仅指明确子项，最终逐字段勾选由主线审查决定。

## 证据锚点与有限来源

- 原规范：`data/ORBIT_Codex开发PRD/contracts/openapi-current.json`中Rule、RuleWrite（原POST与PUT均直接引用该11字段Schema）、Schedule、Condition/ConditionGroup、ConditionResult、Simulation；`FIELDS.md:567—744`；`contracts/WORKFLOWS.md:63`原Rule状态/同版本15分钟simulate，`:125`范围冻结与撤权。Rule输出15键，写入11键，Schedule7键。原Condition3/ConditionResult5不能混算成同一字段组。
- **H62**：后端`docs/orbit/evidence/python-rules062-schedule-preview-http.json`，executed_at=`2026-11-08T23:45:43.132478+00:00`，62/62 PASS；该62包含基础/退出以及多个专属工具，不是62个Rule字段。`summary.cases`确含下文具名用例。对应工具源码hash见该回执source_sha256，后续源码不能覆盖旧hash冒当前验收。
- **H22**：`python-rules060-definition-http.json`，22/22 PASS；原定义16组是H62中再次实际运行的子集，不重复加成38/84等新数量。
- **B13**：`python-rules062-browser-partial.json`，scope明确`PARTIAL_REAL_INTERNAL_BROWSER_HTTP_MYSQL_REDIS_NOT_FULL_ACCEPTANCE`。13条实际观察包括原菜单、20+8列表、详情/关闭Drawer进入编辑、521历史范围、真实FILTER应用与保存、三个尺寸局部列表/预览、原生预览弹窗/关闭焦点/空预览。not_run明确全字段/条件UI、真实OWNER/PROFILE分页、未知写入/撤权故障注入、UI真实DST、每视口全业务、Simulation/运行/建议/全局触发/AI。不能抬升完整三视口。
- **P**：后端现有`python/tests/test_rule_contract.py`、`test_rule_conditions.py`、`test_rule_schedule.py`；前端`tests/orbit/rules-api.test.ts`、Form/Editor/Selector/Preview专属挂载。本文只读源码核断言，不重新运行这些纯测；实际通过数量/固定源码需引用主线现存固定回执，不能以函数存在即宣称此次已跑。
- H62工具真实规则/原scope/角色走实际HTTP及MySQL/Redis，账户/profile来源含**SQL技术fixture**，不是Meta平台导入/真实生产profile发行。`rule_editor_definition_checks.publish_technical`的ENABLED/owner转移明确`ISOLATED_SQL_ONLY_NOT_ENABLE_AUTHORITY`，不能冒原enable或正式归属流程。

为便于核查，定义用例名缩写：D0=OriginalCreateDetailAndFifteenFields；D1=OriginalWriteBoundaryAndHeadersHaveNoPartialWrites；D2=NoopAndRealEditReuseImmutableManifest；D3=SuccessfulKeysPrecedeOldCasButRejectDifferentIntent；D4=ActiveNameUniqueContainsAndArchiveReleasesName；D5=Complete521MixedCurrencyMembersAndOwnerIntersection；D6=RulesOnlyEditorUsesOwnManifestWithoutOtherModules；D7=ForeignOwnerHiddenAndOriginalListFilters；D8=UnavailableProfileDoesNotBlockReadOrArchive；D9=MissingSimulationAndRunSourcesNeverFakeSuccess；D10=LiteralContainsEscapingAndSignedCursorChanges；D11=OriginalActionRevocationRejectsSuccessfulReplay；D12=CurrentMemberScopeRejectsTransferWithoutClockBump；D13=DatabaseImmutableGuardsReturnExact1644；D14=Outbox1644RollsBackAllEightTables；D15=ConcurrentSameCasHasExactlyOneAtomicWinner。它们在H62中的完整前缀均为`pythonRule`；不可凭名称扩大断言范围。

以下A—E保留首次审计时的证据与待办，不代表新增回执之后仍全部未测。**当前补证结论以F节为准**；旧结果/用例不改写成新源码成功。

## A. 原15字段主表

| 字段              | 原准确合同                                                                      | 已有实际正/反例与纯测试                                                                                                                                                                                                                                                                                                                                                                                    | 尚缺/建议勾选粒度                                                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| id                | UUID；输出必有，写入不能手填id                                                  | D0真实POST生成id、GET逐值一致；D7 foreign404；`pythonRuleEditDefinitionCurrentActionRevokedAndForeignHidden`未知UUID404；`...StrictGetAndAllPersistentRowsUnchanged`辅助路径not-a-uuid422。P响应解析拒错UUID                                                                                                                                                                                               | 可建议“真实生成/原对象回读/辅助读取UUID负例”子项；不要据辅助路由推原全部9路由UUID边界均验收。原id为bool/null/跨租户全路由矩阵仍需逐项                                                       |
| revision          | 原safe-int1..9007199254740991；当前quoted CAS                                   | D2同正文no-op不变、改cooldown真实rev2、immutable version数量；D6协作者更新rev3；D3成功旧键优先旧CAS且异intent409零写；D15双当前CAS恰一200一409及事件/outbox/version增量。B13实际rev2→3→4                                                                                                                                                                                                                   | **可建议原CAS/no-op/旧成功键子项**；safe整数极值、bool/浮点、负/超限/缺失/重复IfMatch实际HTTP逐形态不由CAS成功推成已验                                                                      |
| name              | NFC/trim后1..80码点；字面contains；当前active名称唯一为已定补充口径             | D0普通名称原样回读；D4同active名409、archive释放后新id；D10真实q=`%_\`仅命中字面样本，signed cursor过滤改变拒绝。P `test_rule_values_and_types`空/81/控制符/surrogate；`test_codepoint_count_and_zero_cooldown_boundaries`80emoji；前端NFC100查询边界                                                                                                                                                      | **不能建议整个name边界勾选**：实际HTTP尚缺1/80/81码点、解组合NFC、空白trim后空、NUL/非法UTF8、case/as_cs、大小写不同名等矩阵；现可勾“同名冲突/归档释放/字面contains”子项                    |
| ownership         | 原owner_user_id/team_id UUID；同tenant当前caller与目标owner完整范围             | D5混币521完整manifest，外owner账户混入409且八表不变；D6本人及明确管理范围编辑不借accounts/launch；D7越域404+列表不泄漏；D11当前动作撤回重放拒绝；D12无accountclock bump直接转属仍当前scope拒绝。`pythonRuleEditDefinitionCurrentOwnerNotHistoricalManifestOwner`为技术owner版本读取                                                                                                                        | 可建议“当前双方范围/撤权不被旧键绕过/当前owner显示”子项；不能把SQL技术owner转移当原UPDATE owner迁移全闭环。owner/team非法UUID、失效用户、跨tenant、跨团队组合及创建替他人完整矩阵需补       |
| target_level      | CAMPAIGN/ADSET/AD三枚举                                                         | D0/D7实际写读和筛选主要AD；P非法GROUP与类型错误，Form列出三级                                                                                                                                                                                                                                                                                                                                              | AD路径有真证；**CAMPAIGN/ADSET实际定义保存与相应真实实体模拟来源未验**。不可把枚举parser通过勾成三级业务全通过                                                                              |
| scope_snapshot_id | UUID；真实完整成员冻结，原Rule自己manifest不是浏览器页IDs                       | D5真实521/2币种成员；D2不改scope复用不可变manifest；D6协作编辑不读他人私有source。H62 `pythonRuleScopeConsumerCreateOriginalFifteenAndExactRuleManifest`、`...UpdateExactTargetCurrentCasAndFrozenSource`、`...OldSuccessfulIntentCurrentAuthorizationBeforeSource`、`...CollaboratorPublicManifestWithoutPrivateScopeRead`；原scope候选四档/FILTER/完整source真实HTTP；B13手机521 FILTER freeze+应用+保存 | **可建议521及真实scope→Rule manifest、当前完整交集、协作复用子项**；非空UUID不等于真实source。原scope五万容量/50001、所有归属/上下文并发、rule版本大规模冻结另验，不以Plan500/单页count替代 |
| logic             | AND/OR根逻辑                                                                    | D0真实AND；P `test_three_valued_complete_table`AND/OR真值表，Form可切换两种                                                                                                                                                                                                                                                                                                                                | 原OR实际持久写读和有源Simulation逐对象结果尚未验，不建议整字段勾选                                                                                                                          |
| groups            | 1..5组；每组AND/OR、1..10叶、总≤20、只根→group→leaf                             | D0实际1组/1叶；P `test_groups_total_and_no_third_layer`20与21、递归未知键拒绝；Form21叶/5组/最少1边界挂载                                                                                                                                                                                                                                                                                                  | 实际HTTP0/5/6组、0/10/11每组、20/21全叶及unknown嵌套字段尚缺；不能把1叶样本/parse根成功当整AST验收                                                                                          |
| window            | TODAY/YESTERDAY/LAST_3D/LAST_7D                                                 | D0实际LAST_3D；P枚举拒LAST_30D，S1按每账户窗口纯计算                                                                                                                                                                                                                                                                                                                                                       | 其余3枚举实际保存+账户当地业务日真实有源观测/跨时区/缺单元仍需SQL/HTTP，不能借调度时区证明指标窗口                                                                                          |
| metric_profile_id | UUID；精确profile版本/proof；读、暂停/归档不额外要求当前来源可用                | D0合法技术profile；D8禁用后原GET/旧成功key仍可读且archive真成功；H62 `pythonRuleEditorProfileOriginalTwelveFieldsAndTwentyPlusKeyset`真实候选12字段/分页；`...DisabledProfileUnavailableAndBadProofRejectsWholePage`；Editor保留历史/当前版本差异                                                                                                                                                          | 可建议“技术profile绑定与当前候选失败关闭/历史读取”子项；正式生产issuer、全部版本漂移场景以及指标事实采集不是这些fixture所证明。坏UUID/跨tenant实际各写路由需补                              |
| schedule          | 原Schedule7全required，互斥null；IANA与inclusive366                             | D0保存INTERVAL30/AsiaShanghai/2026日区间；D1缺schedule/缺weekday400零写。H62 preview真实只读UTC/DST/空，见下表；P三种频率/日期互斥                                                                                                                                                                                                                                                                         | 持久RuleWrite实际DAILY/WEEKLY、366/367、IANA非法等HTTP边界与preview算法是不同断言。不能把预览7组抬升定时执行/next_run_at                                                                    |
| cooldown_minutes  | int0..10080；按Rule+对象分析限流，不影响纯评估                                  | D0实际60、D2真实61；D1 -1实际422零写；P0/10080/10081及bool/字符串，Form清空不补0                                                                                                                                                                                                                                                                                                                           | 可建议-1拒绝和配置更新子项；0/10080原HTTP极值及真实分析冷却原子限制未验，整字段业务勿勾                                                                                                     |
| max_daily         | int1..1000；分析每日额度                                                        | D0实际5，D6实际7；D3原成功键异max_daily6拒409；P0/1000/1001、类型，Form清空                                                                                                                                                                                                                                                                                                                                | 配置样本真实，1/1000/1001原HTTP与按业务日真实额度并发尚缺，不能称“每日最多分析次数”业务已完                                                                                                 |
| state             | DRAFT/ENABLED/PAUSED/ARCHIVED；原enable需15分钟同rev成功Simulation，archive终态 | D0原create DRAFT；D4/D8原archive ARCHIVED；H62 edit-definition四态读取含**SQL技术ENABLED**，其后原pause/原archive真HTTP产生PAUSED/ARCHIVED；D9 default source simulate/enable均503零写                                                                                                                                                                                                                     | 可建议“原草稿创建/归档、技术状态投影与合法pause读取”子项。**不能勾正式enable、正向同rev模拟/15min、调度、启用后状态闭环**。技术ENABLED不是能力来源                                          |
| next_run_at       | date-time或null；输出必有                                                       | D0及技术四态均实际null；P `test_rule_response_original_exact15_and_utc`、`test_response_date_time_cannot_accept_date_or_naive_or_invalid_date`核形状；preview另DTO并不更新Rule                                                                                                                                                                                                                             | **非null实际持久值及调度正确性无当前真证**；只可核null明确/字段未省，不建议整字段验收                                                                                                       |

## B. Schedule7逐键（不得把预览等同真实运行）

H62的7个完整用例前缀`pythonRuleSchedulePreview`：CreateFirstTenantNoClockAndSqlUtcReference；CurrentEditCasAndIndependentOriginalActions；FutureDstGapFoldAndExpiredEmpty；CurrentSessionCsrfAndDuplicateHeaderRejected；StrictFourBodyKeysAndNoDualCasHeaders；ImmediateRevocationForeignAndAllRuleRowsUnchanged；AllOriginalRowsAndClockRemainUnchanged。最后一项实际证明**规则与clock不写**，所以不能用它证明调度运行成功。

| 键               | 已有准确信息                                                                                   | 未覆盖边界/勾选约束                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| frequency        | 原INTERVAL/DAILY/WEEKLY；实际RuleWrite INTERVAL，preview DAILY gap/fold；P三类与ISO weekday    | WEEKLY真实原保存/preview/调度端到端仍需逐项；默认INTERVAL不代表其它enum                                    |
| interval_minutes | 原15..1440；D0持久30，preview15真实5条经过分钟                                                 | 原HTTP15/1440/14/1441、跨DST持续间隔与故障停机恢复真实运行未全测                                           |
| time_of_day      | DAILY/WEEKLY HH:mm，INTERVAL必须null；preview真实DAILY02:30 gap、01:30 fold                    | 原持久00:00/23:59/24:00与条件必填实际HTTP未全；preview时钟注入要标SQL而非自然跨日                          |
| weekday          | WEEKLY1..7、其它null；D1漏weekday400；P WEEKLY7及非法互斥                                      | 原持久1/7、0/8/缺键/非整数实际HTTP与真实星期调度缺                                                         |
| timezone         | 原合法IANA，不取浏览器猜值；实际AsiaShanghai及preview NY时区/DST；B13用户明确添加UTC后实际预览 | 全量IANA不是目标；应至少实际非法zone/非ASCII/偏移字符串与跨账户/调度独立性负例。生产账户时区来源不由此证明 |
| start_date       | 原合法date；无业务默认today；D0实际2026-01-01，preview已结束区间空                             | 原RuleWrite非法日/闰日/开始晚于结束HTTP待补；浏览器empty预览只证明该实际区间                               |
| end_date         | >=start，含首尾≤366；D0实际2026-12-31；P2024全年366和2027-01-02拒                              | 必须原持久HTTP366与367对照后才建议边界勾选；scope/调度日期不可混为指标business_date                        |

## C. Condition3与ConditionResult5 / 三值证据

| 项                      | 当前证据                                                                                                                                                                  | 仍不能宣称的内容                                                                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| metric原11枚举          | D0真实spend；P源码列spend/impressions/clicks/registrations/purchases/purchase_value/roas/cpm/ctr/cpc/cpa；Form候选完整                                                    | 不是11项真实指标采集/聚合/缺单元质量，现生产来源/有源Simulation尚缺                                                                       |
| operator6               | D0真实GTE；P `test_all_comparators_exact_decimal`GT/GTE/LT/LTE/EQ/NEQ逐Decimal；UI6候选                                                                                   | 其余比较符原HTTP持久和真实来源Simulation逐叶尚缺                                                                                          |
| threshold               | D0真实`12.500000`保留；P整数精度>JS安全、计数不许fraction、spend1e9、roas1e6、ctr100及刚越界、前导零/负号/科学计数/7位小数/NaN拒绝                                        | 实际HTTP所有Decimal上下界/类型/长度矩阵未补，不能用parser/表单测试当金额业务验收                                                          |
| 根/组TRUE/FALSE/UNKNOWN | P `test_three_valued_complete_table`全真值表、`test_no_short_circuit_stable_indices_all_groups`全叶索引、`test_unknown_never_becomes_true_for_neq_zero`null NEQ0仍UNKNOWN | 原simulate当前503，**没有真实持久Simulation条件TRUE/FALSE/UNKNOWN的现有HTTP验收**。UNKNOWN/稀疏不等于禁止规则enable（后者需独立成功模拟） |
| entity_id/index         | 原ConditionResult真实UUID、stable condition_index；P形状/索引与全叶                                                                                                       | 真实实体全集/同snapshot/跨页keyset/缺尾或重复根由063下一实际Store证明；不能拿技术UUID或一页200当全量                                      |
| value/null              | 原Decimal文本或null；P缺指标/分数计数UNKNOWN，不补0；原SDK strict parse                                                                                                   | 未证明真实Metrics源0与缺字段、合法完整空、比率分子聚合和跨币实际计算                                                                      |
| result/reason_code      | 原三枚举、reason nullable1..64；PUNKNOWN显式原因                                                                                                                          | source错误不能降正常UNKNOWN；真实来源缺失503与可计算UNKNOWN须分开。Simulation13/cursor分页尚未发布不能勾                                  |

## D. 建议主线当前能勾的最小子项与暂缓项

**可建议、需主线核字段原子口径后才勾：** 原15/11键必填在实际样本读写与缺schedule/weekday负例；原生成UUID/对象回读/辅助UUID422及foreign404；当前CAS/no-op/旧成功键不受旧CAS影响/异intent与并发CAS；active同名409和字面contains；真实521及Rule sealed manifest/协作source权限；当前动作撤回/无clock bump转属仍拒；坏profile证明失败关闭与历史读取；原预览只读UTC6/DST/空且零Rule写。上述均有H62实际具名断言与有限fixture边界，不能把一行“Rule通过”拆成所有子字段完整验收。

**明确不建议勾整字段/模块：** name完整长度Unicode边界、三种target/四种window全部真实来源、20叶全部实际计算、next_run_at非null、正式Simulation、同rev15min enable、Scheduler/RuleRun/RuleHit/AI/执行、全量三视口、五万规则/成员容量。原62和B13不包含这些完整验收；缺内部实现不是外部凭据阻断，后续应继续开发和真实受控SQL验证。

下一最小回归建议优先补原HTTP纯定义边界矩阵（name1/80/81、target3、window4、groups5/6/20/21、Schedule366/367、cooldown0/10080/10081、max_daily1/1000/1001，错误精确path且全表零部分写），随后接063真实完整源/全三值/全叶分页/根与幂等；不能为抬字段数量先把范围外推。本文件无新验收结果，不创建假测试回执。

## E. 历史缺口记录：操作者/户商两个远程筛选（现状见F节）

### 已确认的缺口与原语义

主线实际浏览器已看到Selector两个控件均“尚无真实候选”且disabled；这不是来源已接通的空结果。`RuleScopeSelector.vue`现`operatorOptions?:{id,label}[]`、`vendorOptions?:{id,label}[]`默认空（约302—311行），模板约94—119行只显示父传候选，无自行请求来源；Editor目前没有传这两个prop。SDK/后端已有五filters并不等于UI五项都能操作，因此**完整五filters/UI筛选不得勾选**。

原`FIELDS.md:97—105`账户.operator_id是“所属投手”、远程单选、一个启用用户UUID，不是本次登录原生sys_user数字ID，也不是审计created_by或平台system user。当前规则Scope公开参数名为`operator_user_id`，`account_details_contract.filters`实际映射到`a.owner_user_id`，`account_selection.selection_sql`比较的是账户当前business owner UUID。Rule ownership是本条规则拥有者上下文；operator筛选是该上下文内账户的当前投手，二者不能不经求交就混为同一候选集合。此筛选不执行账户重新分配，不套“管理员才能分配”作为读取过滤的额外动作。

原户商ID仍为VENDOR引用目录稳定UUID，不因独立户商模块删除换自由文本；PRD-ORBIT.md:375、390明确保留最小目录和名称/状态/归属/追溯。原`FIELDS.md:1077—1085`vendor_id远程单选语义来自户商导入（一个可管理户商）；规则过滤本身是账户`a.vendor_id`，不能把导入写权限或“只可新选AVAILABLE”机械套成历史账户过滤规则。已绑定的失效户商如仍在当前可读账户集合，应能以明确失效标签筛出历史绑定，不授新建/分配权。

### 真实label与稳定ID

- **操作者**：提交`orbit_business_user.id`，按现`RuleEditorStore.LABEL_SQL`统一显示`COALESCE(NULLIF(display_name,''),NULLIF(sys_user.nick_name,''),sys_user.user_name)`及真实`orbit_business_team.name`；UI建议`姓名 · 团队 · 完整UUID`消歧，不能仅同名label，也不能把user_id数字/邮箱当筛选UUID。当前账户归属指向禁用用户时，是否保留“已停用”历史过滤项需主线明确合同；原远程启用用户约束下不能默默把停用项当可新选。
- **户商**：提交实际`reference_record.id`（kind=VENDOR），优先显示原账户要求的真实vendor alias（独立alias源）及完整UUID；alias未设置时明确“未设置代称”，可附当前资料name作为**名称**标签而非假alias。name不能静默截断成30字符代称，历史snapshot alias不能当当前目录值。disabled/不可用状态明确展示，foreign/invisible供应商不能借label暴露。
- tenant从当前授权会话确定，不接受客户端X-Target-Tenant偷跨域；同名/同alias不同UUID必须显示可区分，选择变化提交真实稳定UUID或清空null，不使用平台external ID。

### 可复用什么、现存接口不能直接冒充什么

现有`GET /rules/editor-options`仅支持kind OWNER/PROFILE；OWNER使用当前rules.create/edit、人员目录与当前可管理集合，返回OwnerOption4及Page4，有真实label/四档keyset/认证与目录水位。其label SQL、`owner_item`/`owner_active`、当前动作/owner_scope与cursor框架可以复用；**现OWNER不接owner_user_id/team_id，也未按目标owner可读账户集合去重，不能直接把整个OWNER页原封不动当operator筛选全量**。

`/rules/editor-accounts`现已用`RuleEditorScopeStore._clauses`同时叠加caller与目标owner当前visibility及原筛选。可复用这个内部范围SQL作候选集合基础，不能前端枚举账户所有页来拼候选。

不能直接调用：`/accounts/extended`或账户owner-options（accounts.read）；`/users`（人员目录权限）；`/accounts/.../assignment-options`（accounts.assign）；公开`/reference-catalogs/VENDOR`/vendor alias resolver（现`reference_context`需accounts.read或维护字典门禁）。这些均会给rules-only用户暗加其它模块动作。可复用reference_store/alias底层**已授权内部批量读取**，但需要规则专属当前scope门禁，不能把现公开accounts读resolver当无权限helper。

### 最小受控技术扩展提案（仅设计，未新增路由或代码）

建议沿既有`GET /rules/editor-options`新增明确kind `ACCOUNT_OPERATOR`与`ACCOUNT_VENDOR`，而不是新增全局人员/户商接口；这是**待主线审核的技术补充**，现接口尚不支持这两个kind，不在本文宣称可请求成功。两者必须携原action CREATE/UPDATE、rule_id（CREATE无/UPDATE精确）、owner_user_id/team_id；UPDATE还由当前Rule probe/revalidation绑定revision。当前动作沿rules.create/edit，不额外rules.read/accounts/roles/system权限。

候选只取真实`orbit_ad_account`中同时满足当前caller与目标rule owner完整可读交集的distinct owner/vendor。然后受控join真实启用人员/团队、引用资料及alias进行批量label；无关联账户的全组织用户/供应商不能仅因在目录中存在进入候选。建议query接受q与原四档page_size/cursor，并明确其余四个账户filters的联动：列举某kind时不套自己的已选filter，套其余已提交过滤器，避免只能看到单个已选项；此联动语义需合同确认，不能把它冒充原PRD已有字段。

返回原Page4（items/next_cursor/data_as_of/scope_version），items须新严格判别DTO，保留id/label与真实team或availability来源；不为了复用Option{id,label}丢失权限/状态证明，前端再投影为受控Option。q按真实label字面前缀或原已有明确规则（另需定稿），稳定排序用UUID keyset而非label/OFFSET，四档20/50/100/200。候选不授Scope写权，最终freeze仍重验完整账户集合，客户端不能拿候选数量当总账户数。

每页当前authorize/managed team显式锁读和owner_scope必须重验；cursor绑定新domain、actor/session/tenant、原action/rule/currentRuleRevision、目标owner/team、caller+owner指纹、全部已提交filters/q/page_size，及目录/引用/alias与account水位。账户转属/vendor变更、当前管理撤回、label来源变更或不同session/size/owner复用旧cursor应明确409/403并回首页，不能用旧候选缓存跨上下文。建议按既有共同锁序取得目录/引用标签来源锁，再accountclock→有界账户范围，最后Ruleclock/head/current revalidation；具体共享锁序由主线在实现前核定，不能在已有accountclock后补首次来源锁，不能用普通RR旧视图读取managed集合。

前端接线需父分别持有真实Page4和q/游标历史，在owner/action/rule/context变化时abort/清候选及已选filter，在401/403即时清敏感label；加载/错误/零候选与“未接来源”三态分开。合法分页选择后才传Selector `operatorOptions/vendorOptions`，禁止UUID自由文本当原远程单选完成，禁止硬编码当前owner或虚假“全部户商”列表。

### 该缺口最小实际验收

后续实际rules-only身份应能独立获取两类候选，另证accounts/system/字典原公开端点仍403；caller与owner双范围各撤一边、跨tenant/foreign vendor、同名不同UUID、alias null/name不误当alias、disabled历史语义、四档多页、cursor换owner/session/filter、水位变更都应有真实API断言。浏览器必须真正操作两个下拉并核POST FILTER中的稳定UUID与完整成员结果，才可考虑勾“原五filters可操作”；现H62/B13不满足，当前仅登记缺口，不抬完成数。

## F. 2026-11-09新增真实补证与最小勾选建议

### 新锚点与计数边界

- **H69**：后端`docs/orbit/evidence/python-rule-definition062-boundaries-http.json`，executed_at `2026-11-09T00:44:24.946309+00:00`，69/69 PASS。新增7个具名组实际产生15个DRAFT、19个严格拒绝；每个成功原POST201→原GET200逐值相等，每个失败精确HTTP/code/path且八张规则表完整原行hash不变。15/19是断言样本数，不能当34个新增父case再加69。
- **H79**：`python-rule-scope-options062-browser-parent.json`，executed_at `2026-11-09T00:46:46.776192+00:00`，原62+候选10+字段边界7=79/79，父总578.85秒包含人工浏览器等待、API前缀26.35秒；不是规则性能/P95。H69新增7也在此重跑，不能69+79累计148。
- **B12**：`python-rule-scope-options062-browser-partial.json`，executed_at `2026-11-09T00:56:20.476Z`，限定12项内置浏览器观察。SQL-only技术候选、非真实Meta来源；真实操作者23=20+3，跨页保留已选项使末页DOM4=缓存1+新3，户商23/alias未知22，原五filters真实freeze1、members同一ID、手机应用真实scope；1920/1440/390无document溢出。未保存新Rule，未实测本轮UI100/200分页、网络未知/撤权/DST/完整创建保存。五filter完整流程后只修placeholder，最终reload只复验非空/空文案，不能称所有过程同一源码冻结。
- 本节仅**开发/测试子项建议**，原业务整体验收仍0；本文不直接改总台账。下表`RuleWrite.x / Rule.x`为原schema字段标识，不新增PRD字段，不把一个field对象等同其全部业务语义。

具名补证简称：

| 简称 | H69/H79中精确case                                                            |
| ---- | ---------------------------------------------------------------------------- |
| N    | pythonRuleDefinitionUnicodeNameOneEightyAndOverflowNoPartialWrites           |
| E    | pythonRuleDefinitionAllThreeTargetsFourWindowsAndInvalidEnums                |
| G    | pythonRuleDefinitionFiveGroupsTwentyLeavesAndBothOverflowBoundaries          |
| S    | pythonRuleDefinitionInclusive366DaysAnd367DayRejection                       |
| C    | pythonRuleDefinitionCooldownZero10080AndOutsideBoundaries                    |
| M    | pythonRuleDefinitionMaxDailyOne1000AndOutsideBoundaries                      |
| I    | pythonRuleDefinitionStrictIntegersAndReadonlyFieldsHaveNoPartialWrites       |
| O9   | pythonRuleScopeOptionsExistingUpdateHeadCasAndArchivedStateInvalidatesCursor |
| O10  | pythonRuleScopeOptionsRealForeignTenantOwnerVendorAccountIsolation           |

### 原Rule15及RuleWrite11可新增的准确子项

| 字段标识                                             | 现在建议可勾开发/测试的最小子项（不是整字段验收）                                                                 | 必须同时保留的来源/证据                                                                                                                                   | 仍不可勾的语义                                                                                                   |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Rule.id                                              | 原POST服务器生成UUID、原GET同一对象；RuleWrite夹带id拒400 UNKNOWN_FIELD `/id`且无部分写                           | D0+N/E/G等15个真实创建、I；真实Rule head/version/event/outbox                                                                                             | 原所有9路由UUID异常/跨tenant完整矩阵；不能把候选O10扩大成Rule详情跨tenant全路径                                  |
| Rule.revision                                        | 原创建rev1；旧D2/D3/D15的no-op/CAS/成功键/单并发胜；RuleWrite夹带revision拒400 `/revision`                        | I及H62原CAS用例；O9仅证明候选绑定现有UPDATE head/归档拒绝，不替代Rule更新写测试                                                                           | safe-int极值/重复与全部IfMatch形态、实际启停状态版本链                                                           |
| RuleWrite.name / Rule.name                           | 1中文码点、80中文码点真实写读；空串/全空白/81中文码点精确422 `/name`零变；旧active冲突/归档释放/字面contains      | N+D4/D10；实际scope与技术profile依赖成功，原11字段完整                                                                                                    | 解组合NFC、80emoji真实HTTP、NUL/UTF8控制符/as_cs大小写对照仍不足；不能标完整Unicode与名称全部边界                |
| RuleWrite.ownership / Rule.ownership                 | 旧完整caller∩目标owner交集/撤权/协作manifest；候选真实业务UUID而非native ID、双方账户及资料交集、真实跨tenant隐藏 | D5/6/7/11/12，H79候选1/4/5/O10；当前动作和owner current scope；B12真实下拉                                                                                | O10候选隔离不是全Rule owner迁移流程；非法UUID/失效用户/跨团队所有写组合未全覆盖                                  |
| RuleWrite.target_level / Rule.target_level           | CAMPAIGN/ADSET/AD三枚举各自原POST201/GET同值，ACCOUNT精确422 `/target_level`                                      | E；同一个有效真实scope+技术profile；3个DRAFT而非实体事实                                                                                                  | 三种真实实体指标采集、Simulation/动作/发布结果仍无；三级业务不可整体验收                                         |
| RuleWrite.scope_snapshot_id / Rule.scope_snapshot_id | 旧521→sealed manifest与协作复用；新UI两个真候选可操作、原五filter精确提交→真实freeze1/member1同ID→回填父组件      | D5/6、scope consumer8；H79候选10+B12 fiveOriginalFiltersServerFreezesOneAndSameMember/mobileAppliesActualFrozenOneToParent；UUID必须对应真实sealed source | 本轮B12没有保存新Rule，不能声称该新scope已通过原RuleWrite持久化；五万/50001与所有并发仍待；候选数量不等账户count |
| RuleWrite.logic / Rule.logic                         | 原真实AND配置写读可保留；纯AND/OR全三值表仅独立开发/纯测试证据                                                    | D0；P完整truth table                                                                                                                                      | 本新增E/G没有测试根OR或组OR；有源整叶三值/root仍未验                                                             |
| RuleWrite.groups / Rule.groups                       | 5组×4叶共20真实持久写读；6组、单组11叶、3×7共21各精确pointer拒绝零变                                              | G；原1组1叶D0；完整11键且真实scope/profile                                                                                                                | 0组、0叶、单组恰10、未知第三层完整HTTP矩阵仍缺；20相同fixture叶不是11指标/6算子或20叶真实计算                    |
| RuleWrite.window / Rule.window                       | TODAY/YESTERDAY/LAST_3D/LAST_7D四枚举各真实保存回读，LAST_30D精确422 `/window`                                    | E；技术账户定义级样本                                                                                                                                     | 各账户当地业务日/跨DST窗口真实事实与稀疏UNKNOWN不由保存证明                                                      |
| RuleWrite.metric_profile_id / Rule.metric_profile_id | 旧技术profile精确版本/proof绑定、停用后读取/归档不借额外来源门禁；候选坏proof失败关闭                             | D0/D8及Editor profile真实组；当前MetricProfile独立来源桥                                                                                                  | 新15个DRAFT均复用技术profile，不等15种正式来源。生产发行、全版本漂移/跨tenant写路径仍需                          |
| RuleWrite.schedule / Rule.schedule                   | 原7键完整持久；2026-01-01至2027-01-01含首尾366天真实成功，至2027-01-02为367天精确422 `/schedule/end_date`         | S；原INTERVAL30/IANA上下文，H62 preview是独立只读算法证据                                                                                                 | DAILY/WEEKLY真实保存、各互斥键/weekday/time/timezone全部边界、真实调度仍未全覆盖；366日通过不是运行366日         |
| RuleWrite.cooldown_minutes / Rule.cooldown_minutes   | 0/10080真实持久；-1/10081精确422 `/cooldown_minutes`；bool精确400 INVALID_STRUCTURE                               | C/I；15DRAFT配置级原GET同值                                                                                                                               | 字符串/浮点/缺失/null全部原HTTP矩阵未齐；Rule+对象真实并发冷却/重复命中限制未实现验收                            |
| RuleWrite.max_daily / Rule.max_daily                 | 1/1000真实持久；0/1001精确422 `/max_daily`；bool精确400 INVALID_STRUCTURE                                         | M/I；原八表失败零变                                                                                                                                       | 真实每日额度/重置业务日/并发原子计数仍未验；不能把配置上限等同限流生效                                           |
| Rule.state                                           | 15个成功真实DRAFT且rev1/next null；夹带state=ENABLED拒400 UNKNOWN_FIELD；旧原ARCHIVE/PAUSE有限真证保留            | I+valid公共断言+D4/8；技术ENABLED仅读取夹具                                                                                                               | 正向Simulation15分钟同rev→ENABLE、实际调度与状态恢复未验；不可用技术ENABLED抬完成                                |
| Rule.next_run_at                                     | 15个真实DRAFT原GET明确存在null；RuleWrite夹带next_run_at即null也拒400 `/next_run_at`                              | I+valid公共断言；原Rule15 parser                                                                                                                          | 非null真实持久值、启用/停机追补/时区/DST调度仍无证；字段全部语义不足                                             |

### E节历史缺口的现有限定关闭

已采用的是**独立**`GET /rules/editor-scope-options`，不是E节早期建议在`editor-options`加kind，也不套其它四个filter联动。实际参数kind OPERATOR/VENDOR、owner_user_id/**owner_team_id**，q标签字面前缀/完整UUID；Page4、Operator5/Vendor4。源码与完整说明见`ORBIT_RULE_SCOPE_OPTIONS.md`。E节原先两个永久disabled/未接候选的实现缺口已由真实HTTP候选10与B12限定流程解决，可建议“两个远程filter具备真实来源/历史状态/null代称/原五filter可操作冻结”开发测试子项；**仍不得据此勾完整UI、所有四档UI分页、未知恢复、撤权、全部三视口业务验收**。

O9已补原存量UPDATE现head/CAS与归档失效cursor，替代之前“仅未知Rule404”的待测描述；O10已补真实foreign tenant owner/vendor/account候选隔离。未证明全系统所有写方都正确维护clock、不存在死锁或所有跨tenant业务API矩阵通过。23候选是SQL业务样本，不证明平台主体/户商真实可投。

### 仍不建议任何原field以完整业务语义整项验收

上述新增矩阵足以把若干**配置解析→真实持久→原GET**子项从“待测”改为已测，但原scope源容量/条件全算子/三值有源结果、正式profile/数据源、模拟/15分钟enable、non-null next_run_at/调度/RuleRun/RuleHit/AI/执行仍明确缺失。应优先把现有可证子项准确登记，不为增加计数把Rule15整体或每个field对象统统勾选；验收计数保持0。本次仅更新独立审计文件，未运行代码/DB/Git，也未修改总台账。
