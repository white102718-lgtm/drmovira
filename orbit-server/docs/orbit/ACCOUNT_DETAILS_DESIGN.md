# 账户18列、消耗日期与详情补充设计

状态：合同设计及015独立后端实现待集成。既有账户入口、Worker、014及前端保持受测冻结；本文不是页面/数据库/平台验收证据。主任务已确认按原型的账户当地业务日消耗窗口执行，无需重新询问用户。

## 一、证据与确定口径

| 证据位置 | 明确要求 | 实施结论 |
| --- | --- | --- |
| data/ORBIT_Codex开发PRD/PRD-ORBIT.md:150—164、337—341 | 18列、详情、日期、列设置、OAuth/同步/分配/备注/本地解绑 | 原Account14字段不能替代全部显示合同 |
| 同目录reference/01_修订需求与删除边界.md:19—21 | 余额未知不是0；原字段和日期过滤保留 | 未观测或无权限分别说明，不恢复供应商申请 |
| 同目录reference/03_原合同保留章节.md:11、32—34 | 当前户商代称同步更新；历史日志保留快照；账户当地业务日 | 当前展示批量关联最新VENDOR，历史不可重写 |
| data/ORBIT原型.html:806—807 | periodFor23按账户timezone算快捷日期；accountSpend23按事实date窗口聚合 | 日期属于消费事实business_date，不是账户created_at/synced_at |
| 原型:812 | 默认各账户当地今天；账单及总花费不受消耗日期筛选影响 | 无消费账户不从列表消失，非窗口金额保持独立观测 |
| 原型:974—980 | “账户消耗时间”；今天/昨天/7/14/30天/周/月/最大/自定义 | 快捷键由服务端固定参考时刻逐账户计算，自定义为同名业务日 |
| 原型:1366、1400—1401 | API导入未观测账单显示未提供；户商二级页消耗时间与主列表一致 | 二级页复用相同查询口径，不复制伪造金额逻辑 |
| 原合同openapi-current.json Account/AccountPage/AccountIdentities | Account14属性additionalProperties=false；identities已有独立接口 | 保留原schema，补充展示另立技术schema |

原型合成数据的reduce初值0只用于演示；生产未采集、无权限、缺失覆盖或过期均不得依该写法补0。只有覆盖完整且权威事实明确零消费，才能显示0。

## 二、参考项目仅作为来源链线索

- D:/progress/schedulers/tasks/fb_business_sync/resource_fetcher.py:35—68 请求account_status、disable_reason、amount_spent、balance、funding_source_details、is_prepay_account等；db_writer.py:100—135保存对应观测。这证明参考工程存在读取/落库链，不证明当前App权限、币种单位或API版本可用。
- D:/progress/backend/table/fb_ad_accounts.md 保留外部字符串ID、累计amount_spent、timezone_name、disable_reason、is_prepay_account、facebook_id与pixels。累计金额不得作为窗口消费；facebook_id来源个号不得当作投手或BM名称。
- D:/progress/ai-ad-platform-vben/plat/src/views/media-resources/components/ad-account-table-columns.ts:26 显示“下户日期”deliveryDate，另含库存/卡台等CRM字段。这些不是ORBIT消耗日期，不能迁入替代业务日，也不恢复已删除资源申请流程或银行卡信息。
- PRD reference/03:445明确个号名称、可用余额和付费方式并非Meta统一可提供。仅使用已授权供应商/业务维护来源并标明，当前没有该来源就null；不新增手工伪造数据入口。

## 三、独立技术补充schema（待接入）

原GET `/api/v1/accounts`、`/{id}` 的Account/Page保持不变；原GET `/{id}/identities`仍返回AccountIdentities。建议新增固定路径GET `/api/v1/accounts/extended`以及GET `/{id}/details`，前者用于18列的一次分页查询，必须在UUID动态路径之前注册。两者仅accounts.read，无独立提升范围的权限。主任务接入前复核路径与公共鉴权，禁止仅用UUID格式避免静态路径冲突。

`AccountExtendedPage`：严格对象，仅`items,next_cursor,data_as_of,scope_version,account_version,metric_snapshot_id`；items<=200，每项严格`account,details`，account复用原14属性，details复用下述AccountDetails。next_cursor与metric_snapshot_id可null；null快照明确未采集，不能伪造随机已发布快照。AccountDetails不携带Token/AppSecret/raw response。

`AccountDetails`严格字段提案：

| 字段 | 类型与限制 | 说明 |
| --- | --- | --- |
| account_id/revision | UUID/安全整数 | 与同项Account一致，禁止混合不同版本 |
| personal_profile | TextObservation | 个号名称，不等于操作者/系统用户 |
| business_entity | TextObservation | 授权来源的主体标识/展示名；原始数字ID如有单独字符串保存 |
| payment_type | TextObservation | 原始平台枚举映射，不凭balance推断预付/后付 |
| payment_method | TextObservation | 非敏感方式摘要，不含卡号/Token/账户凭证 |
| payable/lifetime_spend | 原Observation | 账单与累计总花费，两者都不按日期窗口变化 |
| blocked_reason | TextObservation | 禁用原因码与中文解释分开，保留观测时刻 |
| business_managers | 受控BM摘要数组 | 与配置BM区别，真实核验的关联资产，最多500；未知与空有别 |
| identity_status/identity_observed_at/identity_count | 枚举/nullable ISO/nullable整数 | 概览与原identities快照一致；未同步不可用0假装空 |
| authorized_at/unbound_at/blocked_observed_at | nullable ISO8601 UTC | 本地审计事件或平台观测，缺失不填当前时间 |
| note | nullable字符串<=2000码点 | 备注编辑另行CAS动作，不在只读响应时推断 |
| spend_window | SpendWindow | 逐账户解析后的from/to/timezone/参考时刻和覆盖率 |
| source_revision | 安全整数 | 单个账户附加观测快照水位，防旧观测覆盖 |

`TextObservation`严格`value,code,status,reason_code,source,observed_at`：value nullable字符串，code nullable受控原始码；status限SYNCED/UNSYNCED/FAILED/UNKNOWN，reason_code nullable固定原因码，source受控字符串<=100，observed_at nullableUTC；value未知null、不用展示文案代替数据。业务主体数字ID需专门字符串字段，不混放自由结构。展示文案由前端映射“未提供/未同步/未授权/读取失败”。“未授权”通过受控reason_code区分，不新增原Observation未定义的status枚举。

`SpendWindow`严格`mode,date_from,date_to,timezone,reference_at,coverage,snapshot_id`；mode为TODAY/YESTERDAY/LAST7/LAST14/LAST30/THISWEEK/LASTWEEK/THISMONTH/LASTMONTH/MAX/CUSTOM，coverage为COMPLETE/PARTIAL/NOT_COLLECTED，snapshot_id可null。Account.spend保留原Observation；聚合窗口自身不能塞进其单日business_date，跨日时business_date=null、精确起止由SpendWindow承担。数值使用Decimal与原字符串金额规范，不经float。

原Account.balance的kind不能未经证实标AVAILABLE；平台balance与可用余额不同。账单payable kind=BILL，累计和窗口消费kind=SPEND，来源必须区分平台累计metadata与日事实汇总。

## 四、查询、索引、快照与大数据路径

1. 先实时校验accounts.read和原tenant/actor范围，在一个一致性只读事务解析账户成员；名称/完整ID、投手、状态、户商过滤使用现有索引。日期不进入账户成员WHERE，故没有消费的账户仍显示。所有owner/vendor参数与调用者范围求交集。
2. 日期省略为TODAY，服务端冻结一个reference_at，按各账户IANA计算当地今天；显式date_from/date_to成对且合法，表示各账户同名业务日，包含两端。快捷窗口只传mode，不将浏览器时区展开成所有账户统一日期。CUSTOM必须给起止；mode和显式日期互斥。MAX需已发布事实最早业务日边界，未采集不发明某个起始日。
3. 默认按账户id键集升序分页，最大200。新增游标签名用途需主任务登记，绑定actor/tenant/权限版本/目录版本/账户版本/观测版本/过滤器/日期mode/reference_at/指标快照及最后id；旧快照失效明确409，不继续混页。暂不开放消费排序；后续全范围指标排序需物化查询结果，不能只排序当前页或深OFFSET。
4. 当前账户附加观测建议每账户一条current快照，唯一(tenant_id,account_id)，保存各字段来源/观测时间/版本及受控字段JSON；不可直接保存完整外部响应。历史快照单独保留，并按策略归档。查询当前页<=200账户批量IN读取，不逐行N+1。
5. 消费建议日汇总表唯一(tenant_id,account_id,business_date,snapshot_id)，DECIMAL金额+currency、quality/coverage、observed_at/版本/归属快照。主要索引(tenant_id,account_id,snapshot_id,business_date)服务当前页范围聚合；(tenant_id,snapshot_id,business_date,account_id)服务受控跨账户汇总。主键/索引具体顺序经真实EXPLAIN ANALYZE确认，不能仅因列存在就判性能合格。
6. 账户事实按account_id/currency/account-local业务日读取，不跨币种合计。历史事实按冻结owner/team授权，当前成员可读并不授予转移前历史；UNASSIGNED事实仅有合同规定管理员能读。查询先求事实权限交集再聚合。部分可见或部分缺失不返回完整消费假象，明确coverage，必要时amount=null。
7. 当前页JOIN最新VENDOR与可读人员名一次批量完成；户商别名失效仍可历史显示，当前别名变化不改导入/审计快照。不要为显示名称绕过系统人员管理权限；只取允许展示的最小字段。
8. 50k账户/百万事实专项记录冷暖、20并发P95/P99、扫描行、真实SQL计划/内存；列表在线目标仍按实施文档。MAX/长窗使用已发布汇总或异步物化，未有事实和容量验证前保持未通过，不造数据成功占位。

主任务已分配015；014不再增加字段。附加观测与事实发布/水位后续实现前，GET可以真实返回UNSYNCED/null及完整字段结构，不能声称已接通Meta金额或统计采集。

## 五、18列与弹窗逐字段映射

| 原列/入口 | 字段/交互 | 当前差距 |
| --- | --- | --- |
| 投手 | ownership+批量人员名称 | 筛选选择器/姓名尚未接通 |
| 名称/ID | Account.name/external_id，完整原名详情 | 已有基础值，需截断/完整值验收 |
| 户商 | 当前VENDOR alias+失效标识 | 需修正冻结JSON别名展示 |
| 个号/主体 | personal_profile/business_entity | 尚无生产观测来源 |
| 状态/授权 | Account状态+源/时间说明 | 元数据已实现待014联合验收，OAuth未完成 |
| 付费类型/方式 | payment_type/payment_method | 未提供来源时null |
| 余额/账单/总花费 | balance/payable/lifetime_spend | 不能用余额或spend_cap互推 |
| 消耗/消耗时间 | Account.spend+SpendWindow | 汇总、覆盖率和窗口需真实实现 |
| BM/主页/像素 | BM摘要+原identities快照 | 原identities尚未实现，不先补空成功 |
| 时区 | Account.timezone | 已有IANA/DST纯逻辑，需页面证据 |
| 封禁原因 | blocked_reason+blocked_observed_at | 尚无平台观测来源 |
| 操作 | 详情/同步/分配/备注/本地解绑/OAuth | 除基础详情与导入外仍需逐个动作闭环 |

- 列设置弹窗：18列ID全部可选，名称/ID默认且不可取消；其余全选/恢复默认/取消不保存/确认保存，应用当前列顺序而不是勾选点击顺序。偏好只存列ID，不存账户资料/凭据；未知旧列ID忽略。操作列固定右侧，窄屏表内横向滚动不隐藏业务字段。户商列也必须在设置中，不沿用原型后期DOM插列导致不在设置中的缺陷。
- 日期弹窗：快捷列表+双月/Element Plus日期范围、取消/确认；草稿日期不触发请求，起止反转422，默认各账户当地今天。确认后重置游标，300ms名称搜索防抖+取消旧请求，迟到响应不能覆盖新过滤。
- 详情抽屉：外部ID/原名/当前投手团队/户商/主体/个号/状态/授权时间/解绑时间/封禁原因及观测时间/最近同步/备注/币种/时区/余额账单累计和窗口消费各来源与时间/身份资源入口。加载、404不可见、403动作无权、失败重试、切换对象迟到响应均独立验收。
- 身份二级区：原identities接口仅观测真实资源，按PAGE/PIXEL/APPLICATION种类展示external_id/name/usable/reason_code；可读不等于可用于某个计划。原资源上限5000，后台读取有界分页并完整发布，超过上限明确失败而非静默截断。没有已观测快照时返回固定未就绪错误，由前端显示“尚未同步身份资源”，不能随机capability_version和当前observed_at。
- 同步/分配/备注/本地解绑/OAuth弹窗保留为后续独立闭环；不能做按钮占位后勾已实现。删除资源申请/申请记录/下户入口仍不恢复。

## 六、下一实际实施顺序与验收门槛

先由主任务完成014六组真实MySQL/TLS；随后解冻账户只读展示窗口。第一闭环实现上述独立schema、来源观测持久化/未知null、批量实时户商关联、18列/列设置/详情、明确日期窗口及未采集状态；真实金额采集和身份同步按独立连接器继续接力。

必须包含：两租户/团队/三数据角色、同Token撤权、改别名当前更新而历史不变、无消费账户仍列出、窗口账单累计不变、纽约DST/跨UTC午夜/各账户当地今天、覆盖完整0与缺失null、版本与游标失效、审计/观测写回滚、200行批量查询计数、桌面/390px/768px的18列/弹窗/错误状态。未接通平台的字段可以如实未知，但整列功能和真实来源验收不得混为已完成。


## 七、015实际实现与设计差异登记

新三模块/015及专属单测已落盘，路由暂未接入，真实集成工具8组待主线运行。事实采用当前日值+不可变历史，发布UUID和水位CAS；当前读事务与游标冻结该发布水位，旧发布续页409，不假称已有跨版本长读快照服务。附加字段也采用当前/历史双表。

新details新增owner_display与vendor_display：最小VENDOR仅name<=255且无alias，完整当前资料名带REFERENCE_CATALOG来源；原alias未明确映射则null，reason_code=ALIAS_NOT_MAPPED。该缺口不能因字段显示完整名就当代称需求完成。business_managers目前nullable，identity明确UNSYNCED；未连接器采集的字段保持未知。原unbound_at有本地记录时从真实列返回；授权时间/备注动作尚未实现。

自定义消耗窗口当前同步范围上限3660日，超过明确422，不静默截断；MAX使用已发布当前日事实最早可见日期。更长任意窗/指标排序的异步物化和真实容量仍为待实现，不能借本阶段限制放宽整产品验收要求。40项专项通过仅证明纯逻辑与会话替身控制，8组真实工具尚未执行；详情/18列前端完全尚未改动。

原AccountStore冻结期间仍读取旧value_json，015新发布balance/spend仅进入extended/details；下一解冻窗口须统一旧列表/详情的观测读取值，保持原14属性结构，避免同一账户在两个入口显示不同观测。当前该接线缺口保持未完成，不因新接口通过而勾原旧接口业务值一致性。

## 八、归属证据、已确认缺陷与018修正

进一步只读核对：WORKFLOWS.md:13规定正常转投手/团队在账户当地下一业务日00:00、区间半开且不重叠、新导入从绑定当地日开始、历史更正reason/证据/另一超级管理员批准及新attribution_version；PERMISSIONS.md:18与DOMAIN.md:31/35明确事实owner/team/attribution_version冻结，不随当前转移或当前owner join变化。未找到允许异常日内转移按零点拥有者奖励整日的条款。

原015实现只在当地零点匹配assignment，并在较晚观测时再次派生归属，存在异常日内转移误归属与普通补采改历史的真实风险；此前8组通过不能作为该边界通过。主任务已裁决保护性行为：新事实只有唯一assignment覆盖完整有效事实窗口才归属，否则UNASSIGNED；已有日补采复制旧冻结owner/team/attribution_version，不借指标更新更正归属。该裁决按合同保护原则补足异常输入口径，不伪称原文字面给出了异常算法。

018独立迁移新增current/history的attribution_version及attribution_reason，不改015；旧行标LEGACY_UNVERIFIED，不补造历史证据。新发布窗口为当地00:00至min(来源观测UTC,当地次日00:00)，使用IANA计算23/25小时DST日；中途转移、重叠、部分覆盖或空档均不奖给零点owner。旧版本历史只追加，普通补采的新指标版本也复制原归属，包括原UNASSIGNED，不因后续区间修复自动改奖；历史更正双人流程仍未实现且不能由采集器替代。

初次绑定Worker已经将bound_at按账户IANA当地绑定日00:00转换UTC写assignment，无需修改为精确now；该行为已有014真实专项。新增018专项则另验异常日内转移、迟到保持owner与旧历史、23/25小时实际窗口。合同/归属/账户对象等85项纯逻辑通过，真实018首轮在投手候选接口失败，归属新增末尾组未执行，不提前勾选。

015的JSON_TABLE锁首次真实失败errno3569已通过显式FOR SHARE OF h/FOR UPDATE OF f修复，保留物理表锁；依据 [MySQL SELECT锁定语法](https://dev.mysql.com/doc/refman/8.0/en/select.html)。主任务快速14组真实全部通过；后续018扩展首轮在owner-options状态断言失败（之前原core/extended一致性已通过），工具仅增加安全code/message/field_errors诊断，根因仍待实际响应，不猜测放宽断言。

## 九、前端当前实施范围

账户首页已改用真实extended API：17业务列+固定操作=18列、账户当地消耗模式/自定义范围、只读投手候选、取消/确认列设置与仅列ID偏好、游标分页、失败重试、300ms防抖和迟到请求作废。详情组件显示完整原名、金额与逐字段来源/观测时间、真实本地解绑时间、当前户商资料名与代称缺口；身份资源仅在用户请求时访问原identities，失败明确显示，不填空资源成功。BM未知与主页/像素/应用未同步分开。

新前端7项+原导入4项组件服务替身共11项通过，`.runtime/account-details-ui-unit.json`；类型检查与格式通过。两次未通过尝试均保留：首次竞态用例点击了加载中禁用按钮，改为真实搜索Enter触发新请求；第二次新增BM/主页分类文案使原未知提示断言失败，统一保留“尚未同步身份资源”及分类说明后通过。没有删真实业务断言或拦截网络假成功。

`tests/e2e/orbit-python-accounts.spec.ts`已准备三视口真实流程，依赖当前独立详情SQL夹具，尚未启动。前端真实Python联调/截图、投手候选失败修复、018新增真实归属组、真正alias接入、OAuth/同步/分配/备注/解绑及生产采集均仍未验收；页面显示未知不能替代这些剩余功能。

## 十、020真实代称最小接入方案（当前受测源冻结）

主任务已确认018归属/旧core一致性/投手候选等A27/27实际通过，正在全量与账户三视口；后续本节不冒充当前受测源码。主任务分配020，B拥有新内部 `vendor_alias_snapshot.py`，A仅拥有020/账户接入/专属工具。

当前读最小修改点只有AccountDetailsStore.enrich：每页<=200去重VENDOR调用B `resolve_vendor_alias_snapshots(session,current,ids)`，真实alias(string|null)填原core.vendor_alias；不从name或source_key推断，当前完整资料名仍独立vendor_display。reference_clock已在当前游标指纹，alias维护提升该时钟，续页409避免跨名水位。历史不参与该实时resolver。

020新建不可变 `orbit_account_vendor_alias_snapshot`，按tenant/resource_type/resource_id/resource_revision唯一；记录真实vendor revision、完整资料名、alias可null、alias_revision/source、request UUID与捕获UTC。IMPORT_ACCEPTED、ACCOUNT_BINDING、未来ASSIGNMENT在各自实际业务事务点写快照，与原业务/审计/outbox同事务；旧历史无快照行必须显示“当时未采集”，不按当前alias回填，不生成伪造过去captured_at。未知冻结NULL+UNSET/rev1，显式清空的真实alias记录则NULL+其真实revision/VENDOR_ALIAS，二者可解释且不混淆。

权限关键：accounts.import与accounts.read独立。B现有显示resolver每次重新要求read/目录维护，不能直接用于import-only冻结。约定新 `freeze_vendor_alias_snapshots(session,context,vendors,*,permission='accounts.import'|'accounts.assign')` 由B实现：context为原业务已授权BusinessContext，vendors为同事务原动作已验证的真实受锁reference row（非浏览器dict）；helper按原动作重新核身份/tenant/subject，重新核真实VENDOR/kind/范围/归属指纹后批量读alias，不追加read门禁、不向HTTP任意暴露。A已有AVAILABLE/team/目标owner交集继续生效，不能把helper用于绕过原验证。

新独立 `tools/account_alias_snapshot_checks.py` 已准备5组草案：从未设置NULL+UNSET冻结、当前改代称不改旧快照、原幂等重放不换历史、import-only无read仍可原动作冻结、快照写失败业务整笔回滚与同键恢复。需主线新独占VENDOR（未设置alias，分配root与同团队import-only拥有者）、现有本机绑定账户引用该VENDOR、原生import-only会话及through020；不请求平台或填充假平台资料。工具格式/Ruff通过，未执行；当前只写新迁移/设计/工具，未接入冻结产品模块。

正式B内部helper已在独立 `vendor_alias_snapshot.py` 落盘，支持acting_subject=False的Worker原actor重授权。A新独立 `account_alias_snapshots.py::append_account_alias_snapshot` 已准备：原对象锁/验证后的同事务调用，固定业务种类/permission对应，要求显式外层事务，仅INSERT020，不UPsert。A10项专属单测通过（`.runtime/account-alias-snapshot-unit.xml`），B21项纯逻辑另有其回执；这些替身结果都不计实际020事务或import-only真实验收，既有受测调用点仍未接入。

### 020当前实施回执补记

原最小方案已接线，进入主线串行实际验收队列，前述“未接入/5组草案”为历史状态。现在6组独立工具增加原core/extended同alias与双游标失效，并分别对快照INSERT和IMPORT_ACCEPTED审计注入真实数据库故障，检查业务/逐行/幂等/快照/事件/outbox/账户时钟全回滚。Worker初始归属种类IMPORT_ASSIGNMENT继续用accounts.import，后续实际分配种类ASSIGNMENT才要求accounts.assign。020DDL虽已随B独立库运行成功，不据此声称A业务通过。118纯测、11前端替身通过仅为准备证据，最终以主线through020回执为准。

## 十一、原身份资源读取的下一闭环（合同核对，尚未实现）

原接口 `GET /api/v1/accounts/{id}/identities`，accounts.read；原OpenAPI AccountIdentities只允许account_id、resources、capability_version、observed_at四属性，resources至多5000条。IdentityResource只允许external_id（1—64 ASCII数字，保留前导零）、name（0—255）、kind（PAGE/PIXEL/APPLICATION）、usable布尔、reason_code（null或1—64字符串）。原保留章节435要求对目标账户核验资源可用性，知道ID或拥有BM不等于可用于该账户。不得增加BM假资源到原枚举，不将部署配置的BM名称当已观察主页。

最小独立设计：新account_identities_contract/store/routes，迁移编号由主线分配；当前快照头按tenant/account唯一，历史按tenant/account/revision只追加，资源行按tenant/account/revision/kind/external_id唯一。读取先实时accounts.read与账户owner/team交集，再取一头+该版本至多5000资源；GET不临时外呼Meta，无OFFSET或每资源N+1。未观测或完整性未验证时明确503 ACCOUNT_IDENTITIES_UNSYNCED，不返回当前时间的空数组；只有完整遍历且逐项目标账户可用性已核验的真实成功观察才允许空资源结果。

内部发布必须显式事务、accounts.sync、受控源/来源配置版本、真实observed_at、完整读取证明及能力版本；旧/重复水位拒绝，新版本与当前头/审计/outbox原子提交，故障全回滚。已撤权或源配置变化应阻断原usable承诺，不能继续展示旧true而当有效。资源枚举/长度/重复键/布尔严格类型及敏感字段均在写前验证；调用入口不是浏览器手工录入身份，受控数据库夹具不计真实Meta能力证明。

待统一口径：原schema有Capability（launch.read的投放组合能力包），没有同名ResourceCapability表/接口；AccountIdentities.capability_version须与资源能力核验的真实版本关联，不能借META_BM配置revision冒充。资源能力版本当前权威来源与失效/有效期策略需主线裁决，不能擅自硬编码时效。生产采集与外部凭据实测单列缺口，不以内部发布读回替代它。

身份原合同纯验证模块已独立新增 `account_identities_contract.py`，26项专项通过（`.runtime/account-identities-contract-unit.xml`），Ruff/格式通过；严格拒绝额外敏感字段、类型强转、Unicode数字/act_路径、跨账户快照与重复kind+ID。该结构验证既不查询权限，也不承诺能力已核验，允许空数组只表示原schema结构合法；存储/路由/实际采集仍未接入，未同步当前404缺口仍存在。

### 023独立身份读取/发布实现，真实集成尚未执行

主线分配023后已新增独立store/router及4张表：受信证据、当前头、只追加历史、按版本资源。证据冻结目标账户revision、META_BM来源ID/revision、完整原响应SHA256、实际observed_at、capability_version、complete/verified、撤销时刻、可空已知凭据到期及安全证据引用。没有生产registry写入器、浏览器写入口或自动verified行；任意传version字符串/伪造usable不能替代真实证据行，生产采集与权威registry未接入时只能503。

内部publisher以accounts.sync及当前账户范围、账户时钟→账户→证据→来源锁序，校验完整快照摘要/源版本/观察时间，按CAS版本只追加history/resources再移动head，同事务审计与outbox。晚到观察、旧CAS、超限/重复资源、缺证据/不完整/撤销/已知过期拒绝。GET原路径仅accounts.read，实时核ACTIVE/AUTHORIZED/未解绑、当前可见和证据/来源仍有效；只表示observed_at时完整观察，未来广告提交仍必须即时目标授权校验，不能拿GET当写授权。没有TTL字段依据，不自设5/15分钟有效期。

51项合同/证据边界纯测试通过（`.runtime/account-identities-unit.xml`），Ruff/格式通过。专属 `tools/account_identities_checks.py` 9组已准备未执行，需主线注册独立router并through023：真实会话/403/未同步503、无registry拒发布、严格原响应读回、撤销、来源和账户版本变化、已知到期、正文替换/迟到、真实审计触发器回滚、完整观察才允许真实空结果。fixture自己建独占账户、加密测试来源和SQL证据，不访问平台；这些证据仅验内部协议。denied_headers必须真实无accounts.read的会话，可复用020 import-only用户。原账户三视口中期待身份404的历史断言，注册路由后应更新为明确503未同步并复验；当前未改在测UI。
