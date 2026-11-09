# 规则定义 Python 重新实施设计

本版设计及R1纯核心检查点，2026-11-09，北京时间。057只预留给后续规则定义候选DDL，尚未编写/执行；不改公共权限、路由或已冻结055。Java历史核心和证据不计Python完成。模拟、启用、调度、AI与广告写入均不能用占位或固定样本成功替代。

## 1. 原始依据与当前代码事实

- `PRD-ORBIT.md:232—248、361—364`及保留03第195—215、309—321行：规则只定义条件、范围与分析调度，不预设预算/暂停/删除动作。名称后紧跟作用对象；原列表、条件组、频次、范围、创建人/时间、模拟、启停、归档、触发记录必须保留，没有“开始分析”按钮。
- `contracts/API_SEMANTICS.md:7—17、29、41`：严格原对象、PUT全字段、真正HTTP状态/无data包裹、quoted If-Match、成功键优先且先当前读取范围、ENABLED先暂停编辑。
- `contracts/WORKFLOWS.md:19、49、63`及`PERMISSIONS.md:15—30`：冻结范围、指标未知不补零、状态边与15分钟同revision模拟、当前caller及owner范围交集。
- 原OpenAPI及current版的本组schema/路由一致。实际没有`RuleCreate`/`RuleUpdate`/`RuleSchedule`命名schema：创建/更新都使用严格11字段`RuleWrite`，调度schema叫`Schedule`。本文按概念映射它们，不新增同义DTO或接口。原JSON Pointer是字段核对依据。
- `MODULE_LOGIC.md:237—251`所称Schedule/Conditions/Drafts/Ownership指向`ruoyi-system/.../rules/*.java`；`RULE_SCHEDULE.md`和`RULE_CONDITIONS.md`明言Java内部核心，`RULE_DRAFTS.md`仅内部PENDING_REFERENCES草稿，无HTTP/ENABLE。旧38/83/24等测试数量和MySQL旧PASS均不能继承。
- 首次审计Python没有Rule核心/Store/route/表，只有permission-registry保存原rules枚举；本轮新纯核心见第8节。现`role_bridge.BUSINESS_MENUS`和`require_business_access`没有rules分支；当前Vue原生表单校验变量`rules`和若依定时任务页面不是ORBIT规则页。Python整模块尚未实现。
- 已按本机teamai-recall skill检索；无ORBIT Rule口径命中。命中的AdPulse“HTTP恒200/包code”适用于参考项目，和本项目原API冲突，**不移植**。参考只读，未改团队知识或参考仓库。

## 2. 原接口与权限，保持原响应

| 接口 | 原动作 | 正常结果/严格body |
|---|---|---|
| GET `/api/v1/rules` | rules.read | 200 RulePage |
| POST `/api/v1/rules` | rules.create | 201 Rule；完整RuleWrite |
| GET `/api/v1/rules/{id}` | rules.read | 200 Rule |
| PUT `/api/v1/rules/{id}` | rules.edit | 200 Rule；完整RuleWrite |
| POST `/api/v1/rules/{id}/archive` | rules.archive | 200 Rule；Reason |
| POST `/api/v1/rules/{id}/simulate` | **rules.read** | 200 Simulation；原接口无body，不发明模拟输入Map |
| POST `/api/v1/rules/{id}/enable` | rules.enable | 200 Rule；EnableRule恰simulation_id UUID |
| POST `/api/v1/rules/{id}/pause` | rules.pause | 200 Rule；Reason |
| GET `/api/v1/rules/{id}/runs` | rules.read | 200 RuleRunPage |

所有POST/PUT原要求Idempotency-Key（16—128 ASCII）、X-CSRF-Token；除创建外这些变更/模拟接口要求quoted If-Match。模拟仍是需要CSRF/幂等的只读计算，不能暗加rules.edit/enable。Reason复用原schema，不从Java内部UUID幂等键约束倒推HTTP只收UUID。

所有动作核原rules菜单、当前原动作及当前对象范围；无权动作403，范围外/未知对象统一404。当前读取规则须按冻结owner_user_id或显式可管理owner_team_id，TEAM_ADMIN的本人分支不能抄旧Java“一律仅managed”而丢失；新owner必须启用、同租户/所选团队且在可指派范围。更新先核旧头归属再核新归属，不能改owner夺取他人规则。

公共注册由主线：补rules原菜单/六动作桥和`require_business_access`映射、注册原router。编号不能自行占31040或额外一级菜单。读取/动作拆分延续现框架，不加launch/monitor权限，不沿用JavaHTTP缺口。

## 3. 逐字段合同覆盖清单（纯合同已实现，业务引用/HTTP/验收待完成）

### RuleWrite：11字段，创建与编辑共用

| 字段 | 精确约束/业务 | Python落实位置与验证 |
|---|---|---|
| name | NFC、短文本trim、1—80码点/无控制字符；原保留03:198要求租户内**未归档名称唯一** | contract；DB active_name唯一，归档释放名称；并发同名只能一个成功 |
| ownership | 恰owner_user_id/owner_team_id规范业务UUID，不是native user/dept ID | access/store，旧头先授权，双主体当前启用及团队指派 |
| target_level | CAMPAIGN/ADSET/AD，默认AD；对象紧跟名称 | contract/UI；不接旧GROUP；切换失效当前模拟 |
| scope_snapshot_id | UUID，对应原scope_account_ids **1—50000**冻结成员，未来账户不自动加入 | rule scope桥，非Plan500；见第5节 |
| logic | 根AND/OR，默认AND | evaluator，和组logic分别计算 |
| groups | 1—5；组恰logic/conditions；每组1—10；全树≤20；仅两层 | contract，禁止脚本、表达式和第三层 |
| window | TODAY/YESTERDAY/LAST_3D/LAST_7D；默认LAST_3D，LAST含今天 | 每账户当地业务日；调度时区不能替代指标业务日 |
| metric_profile_id | UUID，来源/当前版本/撤销真实核验，不接受自由profile | 独立rules消费桥；原公开body不添加version字段 |
| schedule | 恰7字段，下表互斥；不是浏览器定时器 | 一个纯调度核心供预览/Worker共用 |
| cooldown_minutes | 严格int 0—10080，默认60；键为规则+对象 | 定义先完整保存；后续分析原子额度阶段接，纯模拟不消耗 |
| max_daily | 严格int 1—1000，默认5；规则+对象+**调度当地日** | 不按页面人数或规则revision重置额度 |

Rule响应恰上述11字段再加`id` UUID、`revision`正安全整数、`state`四原枚举、`next_run_at` UTC date-time/null，共15字段。不能把内部reference_status、created_by或simulation标记偷偷塞入原DTO。RulePage恰items≤200、next_cursor/null、data_as_of、scope_version；RuleRunPage同结构。

### Schedule：7字段，所有键必需，包括互斥null

| 字段 | 必填/范围/口径 |
|---|---|
| frequency | INTERVAL/DAILY/WEEKLY；默认INTERVAL |
| interval_minutes | INTERVAL严格int15—1440，默认30；其余必须显式null |
| time_of_day | DAILY/WEEKLY严格HH:mm；默认10:00；INTERVAL必须null |
| weekday | WEEKLY ISO1—7（周一1），默认1；其余必须null |
| timezone | IANA≤64字符，默认Asia/Shanghai；持久IANA，UI按参考日期显示UTC±HH:mm |
| start_date | 严格真实YYYY-MM-DD；含生效日，默认当地当天 |
| end_date | ≥start；含截止日，最多366当地日；默认+90天 |

INTERVAL从生效日当地首个有效00:00位置按**经过分钟**累加，跨午夜不重新锚定；DAILY/WEEKLY用当地墙钟，DST缺失跳过并记日志、重复只取较早UTC位置。Python用现ZoneInfo明确round-trip判定，不直接照抄Java的fold/日期默认行为；纽约23/25小时、Lord Howe半小时、Apia整日缺失都要新测。部署tzdata版本要记录，预览与调度使用同一核心/版本。

`next_run_at`建议仅ENABLED返回实际下一待运行slot，其他状态null；编辑态未来多条预览需要独立辅助合同，不能把它塞入原Rule字段。预览纯计算不是运行成功，停机只合并最近有效slot并记录遗漏，截止后不补突发任务。

### Condition / ConditionGroup

Condition恰metric/operator/threshold。metric白名单：spend、impressions、clicks、registrations、purchases、purchase_value、roas、cpm、ctr、cpc、cpa；operator恰GT/GTE/LT/LTE/EQ/NEQ。threshold为非负十进制**字符串**≤28字符、≤6小数，不收bool/数值/科学计数/符号/逗号/空值；计数impressions/clicks/registrations/purchases必须整数值（1.000000可，1.000001不可）；金额≤1000000000，roas≤1000000，ctr≤100（百分比，1表示1%）。不得用float比较或把超2^53计数转JS Number。

所有叶子保留结果，不能短路丢明细。AND有FALSE则FALSE，否则有UNKNOWN则UNKNOWN；OR有TRUE则TRUE，否则有UNKNOWN则UNKNOWN。缺失/null/非法观察值均UNKNOWN，null NEQ 0不是TRUE。只有TRUE是候选，但不是可执行建议或已满足数据安全门槛。

### Simulation与ConditionResult：不丢原字段

Simulation恰13字段：`id`、`rule_id`、`revision`、`snapshot_id`、`hash`（64字符）、`account_count`、`scanned_count`、`hit_count`、`unknown_count`、`false_count`、`conditions`、`expires_at`、`next_cursor`。五计数均int0—2147483647，revision正安全整数；逐对象分类满足hit+unknown+false=scanned，account_count是真实授权冻结账户数，不能拿返回行数或固定0代替。无命中是合法真实计算结果，不能强制hit_count>0。

conditions为0—10000个ConditionResult：恰`entity_id`（本地业务UUID，不是Meta数字串）、`condition_index`（0—2147483647）、`value`（原Decimal字符串/null）、`result`（TRUE/FALSE/UNKNOWN）、`reason_code`（1—64/null）。索引建议按组/条件语义顺序展平为稳定全树索引，不用短路后的序号；此映射作为技术补充记录。每对象最多20叶，十万对象不能一次塞200万条件到原数组。condition rows按entity UUID/index键集持久/分页，元数据计数是全扫描非首页合计。

原simulate无cursor参数，OpenAPI没有Simulation详情/明细续页路径，但response有next_cursor。**这不是允许静默截断或伪null的依据。** 原数组/所有字段先完整实现；超10000明细的续读需要主线批准辅助只读接口（建议GET某rule/simulation明细，current rules.read，cursor绑定完整冻结根/当前授权），不改原baseline、不给原POST造body。主线批准前，大范围模拟不能声称完全交付；依赖不全返回明确503而非演示样本。

RuleRun恰8字段：id/rule_id/rule_revision/schedule_slot/snapshot_id/state/hit_count/reason_code；state恰RUNNING/SUCCEEDED/SKIPPED/UNKNOWN/FAILED。没有后台真实run时，不能由模拟伪造SUCCEEDED运行或AI分析记录。

## 4. 定义版本、状态与成功重放

| 操作 | 当前状态/门槛 | 原子结果 |
|---|---|---|
| create | 当前create+新owner/range/profile合法 | DRAFT revision1，不自动模拟/启用 |
| PUT | 仅DRAFT/PAUSED；先旧归属再新归属；If-Match | 实际正文改变revision+1、清当前模拟；ENABLED必须显式pause，ARCHIVED不可改 |
| simulate | 当前read+对象范围+If-Match；真实source/完整枚举/冻结规则 | 不改Rule revision，生成持久Simulation；无模型/平台写 |
| enable | DRAFT/PAUSED；原enable动作；same rule/revision成功simulate；DB now < expiry | CAS revision+1、ENABLED、真实next_run_at、记录所用模拟/完整根 |
| pause | 仅ENABLED；原pause动作+Reason/If-Match | PAUSED revision+1，停止新slot，next_run_at=null |
| archive | 仅DRAFT/PAUSED；原archive+Reason/If-Match | ARCHIVED revision+1，终态，无硬删除、无隐式pause |

“模拟成功”应表示真实评估流程完整/引用有效，不等于所有对象TRUE或unknown_count=0；具体来源质量门槛由模拟provider明确。不得用依赖失败生成全false/全UNKNOWN来绕过真实扫描，也不凭纯Condition测试给启用资格。

启用在旧头R上校sim.revision=R，CAS后公开Rule变R+1；保留sim作为本次启用审计，不能因自己状态revision+1马上宣告已启用失效，也不能把15分钟模拟TTL当ENABLED仅能运行15分钟。后续pause→再enable须新当前revision模拟。规则配置正文很小，可每个真实版本保存完整不可变RuleWrite；状态流转沿用原正文/范围manifest与引用根，不重新分配/克隆5万成员。不增加外部source_revision字段。

同键完整intent含method/目标、原expected revision、完整规范正文或Reason/simulation_id、actor/tenant；成功优先于旧CAS，但返回前核当前会话、当前原operation动作及当前规则对象范围，不以rules.read替代create/edit/pause/archive/enable，也不猜额外读取动作。新key若版本/状态无效409，不能借别的成功任务或旧sim绕过。原成功重放不重取已换版profile/范围来改写旧结果；并发首miss在最终锁后再次核原动作及当前对象范围，不只在开始核动作。审计/outbox/幂等/头/版本/唯一名同事务，任一1644/1213整笔回滚；不靠吞1062或NULL ledger占位假成功。

pause/archive是安全停止，不应因当前数据源/profile停用而503阻止；它们核当前规则权限/CAS及状态。读定义同理可读到自己的失效配置以便修正，不能因为缺指标事实隐藏整条规则。simulate/enable及新引用才核完整实际来源。

## 5. 范围/profile/指标的真正依赖

现AccountScopeStore.resolve_for_plan限定500且走accounts.read，不能拿来实现规则50000。现`metrics_scope_access.authorize_metric_scope`硬绑monitor.read；`MetricProfileStore.lock_exact`仅准launch.*；这些不是规则可直接调用的接口。需要独立rules scope/profile消费桥，沿当前rules动作与数据范围，不能额外索要monitor.read/launch.edit来绕集成缺口。

写入范围时必须：当前caller原snapshot授权/真实hash与scope_version；当前rule owner完整账户可读交集；1—50000真实冻结ID，不截断、未来新账户不加入。管理员为他人创建不得把其自己额外可见资产转授owner。保存Rule专属不可变scope manifest/members，冻结member_hash、count及当时owner/team/currency来源；相同范围复用manifest，不在每次状态版本复制5万行。

原snapshot creator私有接口**不放宽**。后续合法rule owner读取/编辑同一规则范围通过受控Rule manifest消费，而不是冒充原snapshot creator；修改范围仍完整新caller+owner交集。模拟、启用、运行每次重新核owner当前scope和caller当前规则权限，账户转属/解绑或管理撤销不能沿历史manifest扩大权限。列表读取规则定义只核规则本身归属，不为每一行扫5万成员；真正使用/展示成员仍再授权。

profile必须冻结真实当前版本/源根/撤销和事件映射，不能把UUID格式通过当可用。RuleWrite没有profile version字段，内部写/模拟证据另存已核version，仍保留原ID响应。规则新provider/桥需和C线约定最小内部read binding，不能把MetricProfile的归因窗口字符串猜成执行配置，也不能给未验证profile自造verified。

模拟使用已发布可信事实与完整预期集合：target_level映射CAMPAIGN/ADSET/AD，保留本地稳定实体UUID（不能拿跨日dimension snapshot UUID冒同一个业务实体）；按账户当地日期TODAY/YESTERDAY/LAST_N含今天，snapshot/profile版本一致，关键字段缺失不补0。不得把200行Metrics首页当整个扫描集，也不能调用/伪造monitor权限来消费。C线当前048/050/056事实/manifest可提供基础，但完整RuleSimulationSource尚未实现，生产provider默认None→503零Simulation，不继承Metrics容量为规则扫描验收。

跨币种scope没有原Rule.currency字段。主线已裁决：每对象在其自身账户币种解释同一阈值，无转换、不跨币SUM，前端后续明确账户币种；不得加Plan单币种限制或伪汇率。纯条件核心每次只收一个对象的指标，不接跨对象聚合。原调度时区与账户业务日也必须分开。

## 6. 057定义存储与性能建议（待审，非DDL完成）

首闭环建议8表：rule_clock、rule_head、rule_version、rule_scope_manifest、rule_scope_member、rule_idempotency、rule_event、rule_outbox。中文COMMENT、当前tenant复合FK、version不可变、完整ledger receipt一次reserve、无可提交NULL/假BUILDING；具体非循环FK/首笔插入顺序随候选DDL审核。manifest成员按排序ID有界批写，版本只引用其ID/hash。

head有真实created_by/created_at不可变及updated_at、owner/team、name、state、revision、next_run_at；版本存完整规范JSON/根、精确refs/manifest。`active_name`按未归档生成并tenant唯一，ARCHIVED为NULL释放名称；NFC/trim后按本项目as_cs区分大小写，若产品另定casefold需明确裁决，不靠MySQL默认ci混同。

原型`visibleRules23`（舒适原型:1452）名称使用includes。因此q保留字面包含/LIKE转义，不偷换前缀。先授权且只扫覆盖元数据索引、匹配选出≤200主键后再读正文；大规模可增加只作候选的gram索引并最终LIKE精确复核，不能用FULLTEXT分词改原包含语义。候选索引：tenant+owner+state+created_at+id、tenant+team+state+created_at+id、tenant+active_name唯一、tenant+metric_profile_id+state+id；真实EXPLAIN/5万规则20并发再判断，不先声称快。

list分页20/50/100/200默认50，键集created_at/id、snapshot data_as_of、当前规则目录clock+当前auth/scope指纹+筛选/page_size签MAC；先权限后筛选/汇总，null末位。status严格四枚举，operator_user_id按冻结owner不是creator，entity_type映射target_level，metric_profile_id精确ID。date_from/to的日时区/所指创建还是运行时间未原文明确；channel_id不是RuleWrite字段，和范围渠道关系也未唯一确定。暂不支持时非空明确422并登记未完成，不能忽略或擅自按上海创建日猜。新增辅助filter/options仍沿rules.read/当前可见交集，不借system.users/manage。

Rule原DTO没有创建人/时间、scope名称/状态或未来多条slot，而原型列表需要。先真实持久这些metadata，后由主线批准独立批量只读辅助合同（每页≤200）补页面，不能加进原15字段、用updated_at充created_at或调用系统人员权限接口凑显示。原RuleRun详情/Simulation明细续页同样需要单独合同决定。

## 7. 分阶段开发/测试/验收接力

| 阶段 | 明确交付 | 定向测试与真实验收 | 不冒称 |
|---|---|---|---|
| R1 定义闭环 | 新rule_contract/conditions/schedule/access/scope_refs/store/routes；057候选，原列表/详情/创建/编辑/暂停/归档，完整owner+refs | 11/7/3字段全边界；Decimal/三值表；DST共核；真实当前RR撤权/名称唯一/old-key/CAS/1644；规则50001拒绝且5万不截；原201/200/错误码 | 无Simulation/ENABLE来源即明确503；未真实ENABLED不能以SQL假启用称动作验收 |
| R2 真实模拟 | 独立RuleSimulationSource与streaming evaluator，完整冻结计数/条件/manifest/TTL；根批辅助续页 | 固定**真实来源**的三层同命中与解释；全叶/UNKNOWN/无命中；>10000明细无丢重；并发改规则/profile/scope、SQL15分钟等号、审计回滚、无provider零写 | controlled SQL source是协议证据，不是Meta/AI；不是返回假0占位 |
| R3 启用/页面 | 同revision成功模拟原enable；原页面/二级页/确认框/调度预览/字段metadata | 原型保存→模拟→启用→暂停→编辑→旧模拟拒绝→新模拟；实际三视口、撤权及源变化；真实next_run_at | 模拟能显示不代表后台已调度 |
| R4 调度/分析 | 持久due队列/租约、slot唯一、停机合并；冷却/日额度/真实Hit→Job→outbox | 同rule+revision+slot唯一、重复10次只一次、重启/停机/DST；阈值变版不绕规则+对象日额度；日志可追 | 不调用AI/平台假成功；AI与执行后续完整协议，不由Rule动作直写广告 |

R1首批建议文件所有权仅新`rule_contract.py`、`rule_conditions.py`、`rule_schedule.py`、专属tests和057候选；schema/字段/范围设计获审后再分配access/store/refs及真实工具，公共roles/app/runner由主线接。不要沿Java包复制HTTP权限/幂等UUID限制或把旧PENDING_REFERENCES内部版本当原API完成。

所有阶段分别记录开发/测试/验收及固定源码证据。本轮只完成第8节纯核心，Python规则整模块验收仍为0；旧MODULE_LOGIC历史文字不改台账，需主线明确映射更新。下一需落实辅助metadata/预览/模拟续页、Rule专属scope消费与profile读桥、日期/channel过滤；不能靠默认值覆盖原未知语义。

## 8. 本轮纯核心交付与证据边界

新增独占文件：`python/orbit_api/rule_contract.py`、`rule_conditions.py`、`rule_schedule.py`及三个同名专属test文件；无SQL/HTTP/队列/AI/平台请求、无公共接线，055受测源码/工具未动。

- `parse_rule_write(raw)`严格11字段及嵌套7/3字段，原schema全部required，无表单默认补缺；拒重复JSON键、结构/类型、NaN输入、非法UTF-8、未知字段、控制符；文本按NFC码点，保留大小写。条件总数20、计数整数与金额/比例边界、原Reason 1—1000。`parse_rule_action`与`parse_rule_response`保留原DTO及嵌套错误pointer。
- `compile_conditions(rule)`形成tuple/Decimal不可变树，不保留调用方可变引用；`evaluate_conditions(tree, observations)`固定全树condition_index并计算每叶/组/根。支持Decimal/原Decimal字符串，拒float/bool、非有限/有符号/越界输出；null NEQ0仍UNKNOWN。每对象自身币种，不转换不跨对象求和。来源尚未提供，不可把本函数当真实Simulation。
- `preview_schedule(schedule, after, limit=10)`上限50；`latest_due(schedule,last,now,enabled=...)`只返回最近slot/精确遗漏数与缺失墙钟。INTERVAL按UTC经过分钟，不在午夜重锚；DAILY/WEEKLY round-trip验证，重复选较早UTC，gap不平移。最多366个当地日，墙钟扫描≤366个日位置；INTERVAL遗漏数O(1)，预览O(limit)，午夜gap转换微秒二分不逐分钟扫全年。
- 定向命令：`.venv/Scripts/python.exe -m pytest python/tests/test_rule_contract.py python/tests/test_rule_conditions.py python/tests/test_rule_schedule.py -q`，实际 **204/204 PASS，0.77秒**。Ruff仅上述六文件check/format通过，无全量冒称。包括原schema字段集合对照/必需null、所有三值组合、六比较符、超JS安全计数、全叶稳定索引、纽约23/25小时、Lord Howe半小时、Apia缺整日、Sao Paulo午夜gap、366含首尾、过期停机无补发和精确遗漏数。

这是纯代码开发/纯测试检查点，不是R1数据库/前端闭环、真实来源模拟、ENABLED调度或整模块验收。下一可独立实施rules access/scope manifest/profile消费桥及057候选；公共权限/路由/实际SQL由主线窗口统一，不自行继承Java历史PASS。

## 9. 独立权限/范围/profile桥（纯测检查点已冻结）

主线批准新增`rule_access.py`、`rule_scope_references.py`、`rule_profile_references.py`及专属`test_rule_access_references.py`。原204项核心源码保持冻结，本线未改公共authorization、scope、metrics、app、routes或正式迁移。057随后由主线采用，时间范围见下节；采用不等于专项护栏验收。

### 私有接口与授权边界

- `authorize_rule(session,actor,permission)->RuleAccess`仅接受原read/create/edit/enable/pause/archive六动作，调用公共实时rules授权（主线尚需注册，未注册时安全403）。票据绑定真实session/transaction、当前BusinessContext、auth_version、显式锁读managed集合与原snapshot格式指纹。`require_rule_visible`按规则owner或显式managed团队求交，范围外统一404。
- `owner_scope(session,access,ownership,for_write=False,previous=None)->OwnerScope`只从真实启用人员、租户、团队、当前scope/授权代际读目标拥有者。写入另走原`validate_ownership`，本人可读不意味着可指派别人，TEAM_ADMIN不在管理团队只能遵原本人/保留旧归属规则。拥有者只证明当前数据范围，不暗要其monitor/launch/accounts菜单或动作。
- `revalidate_owner`每次来源消费前复核caller当前原动作及owner当前身份、auth_version、managed完整集合；跨事务、伪造票据、权限/代际变化拒绝。没有HTTP能力令牌、运行时后台权限或跨租户例外。
- `capture_rule_scope(session,access,snapshot_id,owner)->FrozenRuleScope`使用当前actor私有、ready且未请求清理的原快照，精确scope_version/auth_fingerprint。1000行一批当前锁读m/a，核数量1—50000、完整原members_hash、每一账户caller+owner当前可读交集；缺行/篡改/越域拒绝，不沿Plan500、单投手或单币种限制。返回完整不可变tuple供未来057同外层事务持久。
- `revalidate_rule_members(session,access,owner,members)`只供未来RuleStore从自己的已核manifest载入后使用，完整唯一排序ID、≤1000一批当前锁读。它不冒原snapshot creator、不把调用方任意ID表当Rule manifest来源；manifest→rule/version绑定及hash由未来Store负责。显示名/revision变更不改变成员选择身份，当前归属必须仍在双方交集。金额按对象当前账户币种，不转换、不跨币SUM；未知币种保留null，事实模拟适配器不得虚构单位。
- `lock_rule_profile(session,access,owner,profile_id,expected_version=None)->RuleProfileBinding`只读现040已发行原MetricProfile版本。返回独立bytes/原version、规范profile hash、当前头/目录水位、原source证明，不需要投放AttributionSpec适配器，也不把adapter撤销解释为原profile撤销。冻结后引用必须带expected_version，不能默切latest。

### 锁顺序与并发失败关闭

统一调用顺序为：当前caller原rules动作/身份与显式managed→目标owner真实身份/managed→profile普通probe（只定位，不授权）→真实配置来源锁→metric clock→profile头/版本→account clock及到期投影守卫→原snapshot→排序member/account→未来rule clock/head/version/幂等。源均先于业务clock；本组只有一个profile来源，后续多来源必须global UUID排序。

profile最终头/版本若与probe的config ID/revision/source/authority_kind/version不同，409失败，不在持metric/account clock后补首次新source锁；同一当前头停用404、损坏proof/hash或来源未知503。META来源同时核真实META_BM启用/版本、原source proof及列一致；FIXTURE只在原strict localhost13306+UUID数据库边界可消费。保留原proof微秒JSON，不将DATETIME(3)舍入值当原proof时间重新散列；同时必须按040原`mysql_millisecond_instant`四舍五入规则（含跨秒进位，**不是055 floor**）核独立observed_at列，并以实际SQL `UTC_TIMESTAMP(3)`拒绝未来观察。规范bytes返回与调用者可变dict分离。

三桥仅SELECT/当前锁读，没有网络、ledger/event/outbox写入、来源发行或平台能力授权。成功scope返回不是已经提交的持久冻结；未来create/PUT成功键探测和当前读取范围仍由RuleStore先处理，不能为了重放原结果重新核已换版profile/快照。未来simulate/enable/运行再走当前双方完整范围与精确profile/事实来源，不以本轮票据充当永久许可。

### 定向验证计划与当前范围

首轮34项协议纯测通过（0.88秒，替身SQL/授权，不是MySQL证据）。随后补拥有者当前代际/managed撤回、50000完整分块、原creator退出后Rule manifest消费和缺失账户拒绝。按主线04:18容量测量窗口暂停pytest/构建，收到测量结束通知后，实际定向 **43/43 PASS，1.86秒**，上述四文件Ruff check/format通过并冻结。命令：`.venv/Scripts/python.exe -m pytest python/tests/test_rule_access_references.py -q`。其中50000是完整协议数组与51次有界SQL调用替身检查，**不是实际MySQL容量或速度验收**；来源/profile也是受控SQL结果替身，不是权威平台事实或生产能力证明。

真实SQL接力需主线注册原rules菜单/六动作及采用057后统一排队：旧RR撤管理/禁用owner、两主体交集与越域404、旧私有snapshot不放宽、真实50000/50001/空范围、不可变manifest与原hash、source变版/撤销/并发换来源无晚锁、成功键优先、CAS与1644整笔回滚。现在没有Rule HTTP成功或业务验收证据。规则专属范围创建/筛选辅助页面合同仍需接力，不能借旧accounts.read入口限制rules-only用户后声称完整。

C交叉只读审查确认首版遗漏独立observed_at列/SQL未来时刻核验，不能以原43纯测掩盖。已定点补上述040原规则，新增`.123499/.123500/.999999`、跨秒、独立列错位、非毫秒列、UTC偏移与未来负例；实际新定向 **50/50 PASS，1.90秒**、两修改文件Ruff PASS并重新冻结。没有运行真实SQL时间专项，不能将此纯测提升为045/055或真实平台时间验收。

057候选已写入`docs/orbit/sql-drafts/057_rules_definitions_candidate.sql`，8表/18触发器，原名称唯一出处写入首行注释。主线已复制为正式`migrations/057_rules_definitions.sql`，仅header差异，并安排与059指标菜单初始化及原ref/channel回归；本线未执行数据库，不把正式文件存在或初始化当作18护栏/Rule业务通过。主线裁决成功重放仍核当前**原operation动作**与实际当前对象范围，定义Store已遵此。

## 10. 定义Store检查点及真实专项接力

`rule_store.py`和专属`test_rule_store.py`已冻结，实际33/33纯测通过（1.35秒），Ruff通过。这是SQL/授权协议替身证据，没有真实MySQL回滚或HTTP成功。Store实现原Rule15读取、原RuleWrite11创建/完整PUT、归档和安全暂停状态门禁；同body且相同profile精确版本/来源根为no-op，真实编辑追加完整版本并复用同规则不可变成员manifest。成功键先当前原operation动作/实际对象范围，再原intent，优先旧CAS/已变化来源；未成功才走当前profile与双方完整成员交集。profile失败延迟到当前head范围/CAS重验后，避免旧视图和并发成功fallback被预读错误抢先。

名称冲突由rule clock写锁→当前CAS→active_name当前锁读排自己，任何manifest/event写入前明确409/name；数据库原未归档唯一键仍为并发护栏。名称保留NFC/as_cs与字面contains，不改前缀。没有吞1062后继续提交的路径。读/归档不新增profile来源就绪门槛；暂停正向仍需要真实ENABLED前置，当前工具不造假ENABLED补绿。

已批准规则专属`GET /api/v1/rules/capabilities?action=CREATE|UPDATE|ENABLE|PAUSE|ARCHIVE|SIMULATE`仅返回csrf_token，分别核原动作（SIMULATE=rules.read），不借accounts/roles/launch。MAC用途RULE_CURSOR_V1由主线注册；正式060菜单/六动作与原路由由主线接线，工具不临时mock授权。

`tools/rule_definition_checks.py`已准备16组真实专项，签名`run_rule_definition_checks(client,admin,headers,password,cache,database,cases)`，无额外参数。原数组`RULE_DEFINITION_CASES`只在每组完整真实断言成功后追加。工具护栏纯测10/10通过（0.25秒）、格式/静态检查通过；工具尚未实际执行。

专项仅本轮127.0.0.1:13306/UUID库，实际SELECT DATABASE验证，独占990570/990571占用拒绝。角色、私有Scope和规则走真实原API；521账户及040 FIXTURE来源是明确SQL技术夹具，0平台请求，不是导入/同步/Meta权限证明。16组覆盖原字段/头、no-op与不可变版本、旧键与异intent、未归档名称与释放、521全量/混币/owner交集、rules-only编辑自有manifest、外国owner404及过滤、来源停用安全读取/归档、缺provider503、contains转义与分页、原动作即时撤回、无clock bump账户转属拒绝、18触发器各1644回滚、outbox故障整8表与目录零部分写、同CAS双并发仅一个原子成功。

明确未完成：真实50k容量、独立µ秒profile SQL矩阵、旧RR角色管理撤回专项、真实Simulation13全字段及续页、15分钟资格ENABLE/真实ENABLED暂停、RuleRun调度、AI和执行。simulate/enable/runs当前分别503失败关闭，不返回模拟成功或空运行列表；日期/channel语义、规则专属新建范围与辅助metadata页面仍需后续闭环。本检查点不新增整模块验收数量。
