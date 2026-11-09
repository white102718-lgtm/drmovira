# PY06 投放计划、草稿、模板内部闭环

状态：原合同已核对，设计与接口依赖对齐中。渠道500人UI首轮失败优先修复，当前新launch实际产品源码尚未实施，不继承渠道/Java证据为PY06完成。所有新增实现限launch_*/template_*、021专属迁移及前端launch目录；公共022菜单、注册与purpose由主线负责。

## 原合同与完整交付边界

权威来源：PRD-ORBIT FR-LCH与模板章节；reference/03_原合同保留章节第4.2、4.9及投放/模板字段表；contracts/WORKFLOWS第2、3、5、8节；PERMISSIONS与API_SEMANTICS；openapi-current.json PlanWrite/Plan/PlanPage、CampaignConfig/AdSetConfig/AdConfig/Budget、IdentityBinding/GroupIdentity/AdIdentityOverride、Allocation*、NameReservation/NameItem、Template*。原技术栈被覆盖，其余字段/状态/权限/异常没有删减。

|六区与附属页面/弹窗|必须保留的原功能|首个闭环与后续依赖|
|---|---|---|
|1 账户、负责人、渠道、计划|账户搜索/仅看已选/跨页范围；单投手团队租户币种1—500；管理员明确owner；渠道产品/总代当前可见；计划名称草稿可空|先支持原真实直接account_ids；scope_snapshot真实接口缺失时503，不能用cursor冒充；账户选择弹窗必须随后接入|
|2 系列配置|objective、buying_type、special_ad_categories、budget、bid_strategy、copies与每份差异；自动系列命名只读|草稿允许缺业务必填，已有结构/枚举/引用/数量仍严格；未知能力不能在可执行预检中放行|
|3 广告组配置|name/copies/budget/countries/age/locales/placements/optimization/billing/profile/start/end/ads|同一预算拥有者恰一预算、网站/应用互斥，时间条件在真实预检/发送时重验；先存合法草稿配置，不假验身份/能力|
|4 广告配置与树|name/title/body/description/url/url_tags/cta/asset_type/copies；复制/克隆新local_id，层级和全计划唯一|正文保留LF并转义展示；链接不能自动覆盖为渠道URL。不可只用JSON文本框替代最终树编辑与字段表单|
|5 素材池与分配|筛选/分类/标签、READY、图片/视频限制、allow_repeat、seed、完整slot路径、重新分配确认/取消、素材使用差异|素材≤500、广告≤10000；allocation-v1全局可行匹配及seed稳定，能力包不全明确未就绪；C供安全批量素材/活跃引用，allocator归B|
|6 预检与提交|展开数量/真实预算拥有者/币种/身份/能力/命名/素材差异/风险/15分钟TTL；创建默认PAUSED；启用独立publish确认|身份、命令、真实能力模块缺失时原路由失败关闭，不能返回valid:true、假hash/task或实际外发广告|
|草稿二级页与恢复|服务器草稿为准，列表/编辑/保存/失败未保存/未保存离开提示；切页不丢配置|5MiB上限；保存失败不更新时间；本地仅无凭证恢复缓存，不能用localStorage当唯一落库|
|模板二级页及保存/编辑/加载/共享/归档弹窗|名称说明、PRIVATE/TEAM、明确接收人冻结、重名冲突；非所有者不可编辑；加载后重选账户/身份/渠道|原7个模板路由完整；不能让新团队成员自动获得旧TEAM模板或通过加载反向获得数据权限|
|任务与统计二级页|节点/attempt/失败/证据/UNKNOWN核验/安全重试/取消、SSE恢复、汇总/趋势|后续命令/任务及报表阶段；本节点不做假任务列表或假平台成功|

## 原API和字段逐项落点

- GET/POST `/api/v1/launch-plans`、GET/PUT `/{id}`为计划和草稿原入口，不另造同义plans API。原PlanWrite保留name、ownership、account_ids、可空channel_id、campaigns、identity_bindings、asset_ids、allow_repeat、activate_after_create、execution_mode，以及可选account_scope_snapshot_id/profile_binding_ids/workflow_version/adapter_version。Plan响应必须包含原required和id/revision/state/created_at/updated_at，禁止额外包装data或随意加字段。
- 原`/{id}/allocations` POST202与`/{id}/allocations/{allocation_id}` GET为真实求解状态；`/{id}/campaign-names` POST200无业务正文，受控占号；`/{id}/validate`接原allocation_id+name_reservation_id；`/{id}/execute`仅原hash+activate_ack。缺依赖时保持原请求严格结构/会话/对象范围校验后503依赖错误，不受理假任务。
- 原模板GET/POST `/api/v1/templates`、GET/PUT `/{id}`、POST `/{id}/archive`、`/{id}/share`、`/{id}/apply`不改。TemplateWrite仅name/description/visibility/recipient_user_ids/campaigns；Template响应加入id/revision/ownership/state，不能夹带账户/租约/平台执行ID/credentials。
- CampaignConfig：local_id/copies/adsets必需，objective/buying_type/special_ad_categories/budget/bid_strategy已出现就严格校验。AdSetConfig：local_id/copies/ads必需，其余name/budget/country_codes/age_min/max/locales/placements/optimization_goal/billing_event/metric_profile_id/start_time/end_time全部保留。AdConfig：local_id/copies必需，其余name/title/body/description/url/url_tags/cta/asset_type全部保留。每层copies1—50整数，不允许bool当1，不新增AD budget。
- IdentityBinding逐account_id保存page_id、groups和ad_overrides；GroupIdentity完整保留adset_local_id、pixel_id/conversion_event或application_id/object_store_url；AdIdentityOverride保存ad_local_id/page_id。不接受自由未知字段或跨层local_id。结构合法不代表外部资源对账户真实有权；未有权威身份来源不得保存为已验证。
- Budget金额为严格十进制字符串（最多28字符、6位原合同小数），业务用Decimal、>0/≤1000000、币种真实精度校验；spend_cap可null，不把0当清除。campaign budget.owner须CAMPAIGN，adset须ADSET，二者不可并存；预算汇总按预算拥有者复制倍数，而非按广告重复累加。动态平台最小预算、20%/24h账本、lifetime消费证据由后续真实能力/风控提供，不由草稿“通过”代替。

技术扩展仅拟增加专属capabilities、负责人/引用候选、draft-readiness等明确路径，供原页面使用且由主线登记。不得恢复删除的产品/户商/包一级菜单。原Plan没有对外archive路由，state=ARCHIVED不等于可随意新增launch.archive权限；后续确有草稿归档需求再登记独立扩展。

## 分期与首个真实内部交付

1. D1 原严格草稿/模板落库：全部嵌套DTO与结构/字段/大小；真实引用交集；create/get/list/update/CAS/幂等/不可变版本/审计outbox。模板创建、修改、共享/撤共享、归档、apply生成新草稿；所有弹窗和空/错/无权/未知结果恢复。此阶段既有账户/素材/渠道全部走真实资料，不使用占位默认ID。
2. D2 内部树展开、预算总额、命名：精确复制公式与局部克隆，展开上限；真实目录/昵称回退、上海业务日、序号原子占用及幂等；修改/午夜/引用版本变化导致原预览失效。名称预留是内部成功，不表示平台已创建。
3. D3 allocation-v1：C安全素材批量接口+019物理LIVE/READY/当前版本+目标owner交集；完整兼容图全局匹配，无重复容量1，重复最小化Σusage²并用seed稳定平局。≤60秒求解，否则真实持久异步任务（每计划最多1个），不以202假受理。缺真实capability_version/目标格式尺寸时明确503或阻断，不按类型单条件冒充全部兼容。
4. D4 身份/预检/命令接口：真实账户资源、锁定能力包、预算policy/kill-switch/租约、15分钟hash和任务manifest，实际发送前再核验，UNKNOWN保留锁。外部写仍不在本地授权范围，内部Adapter测试不能声称真实广告验证。

D1/D2可逐个完成真实HTTP/三视口后勾细项，不等待外部凭据；D3/D4未就绪不影响空引用草稿和纯配置模板，但绝不声称整个PY06完成。

## 数据库021与性能/锁设计

|专属表|关键内容、唯一约束和访问索引|
|---|---|
|orbit_launch_clock|每tenant launch/template独立revision；列表水位，不与目录scope_version混同|
|orbit_launch_plan|tenant+id主键；owner_user/team、state、name、payload_json≤5MiB、revision、UTC时间；索引tenant/owner/id、tenant/team/id、tenant/state/id、tenant/updated_at/id|
|orbit_launch_plan_version|tenant+plan+revision唯一；不可变完整输入+hash、owner/目录/账户/能力版本，旧版本供审计/任务引用，不回写|
|orbit_launch_plan_account / asset / node|关联tenant+plan+UUID，成员有序/去重；节点local_id唯一、parent与ordinal；不在大列表扫描JSON判断权限/COUNT所有事实；原始JSON完整保留表单语义|
|orbit_launch_template / version / recipient|模板name NFC trim后按tenant+owner规范化唯一；版本追加，recipient明确冻结UUID；recipient按tenant/user/template覆盖索引；新成员不自动加入|
|orbit_launch_name_sequence / reservation / item|tenant+channel+owner+Shanghai day唯一counter；tenant+plan+revision+expanded_key唯一预留；序号只增不回收，规范命名≤200，至少4位自然扩展|
|orbit_launch_allocation / item|plan+revision+input_hash+seed+algorithm去重；完整slot映射与素材版本、capability_version；处理中有界状态/租约，active allocation引用素材019|
|orbit_launch_idempotency / event / outbox|主体+意图+原成功响应，历史至少2年；事件只追加，唯一资源版本；业务/版本/审计/outbox/幂等同事务，失败整批回滚|

全部字段/索引中文COMMENT，复合tenant FK不允许跨租户关系。前端列表20/50/100/200 keyset，purpose LAUNCH_CURSOR_V1/TEMPLATE_CURSOR_V1绑定actor/可信tenant/角色/显式管理团队/scope_version/筛选/排序/列表水位，不使用OFFSET或把列表cursor冒充账户全选快照。name包含搜索仍有索引风险，需真实EXPLAIN和容量证据，不凭LIMIT通过。

多资源写锁顺序已与主线/C约定：授权/人员边界→账户clock与排序账户→素材clock→全量UUID先排序、≤200分块的排序素材→引用目录clock/渠道快照→launch clock/plan行CAS；不能先锁plan再调用素材helper。plan可先无锁预读，需要资源集在获取规定锁后CAS重验，任何漂移409重读，不按旧集合继续。模板apply剥离全部素材/分配，不调用素材引用注册。事务内不等待模型/平台/对象存储网络。

5MiB草稿仅为原始配置上限，不允许展开超过每层10000及广告10000；DAG节点100000是后续任务保护值。列表只读索引化概要，get才读单个payload；版本保留/归档有界批次，不在API同步扫描历史。真实50k/1m/20并发性能检查另立证据，不以本闭环代替。

## 当前实际跨模块依赖

- A：可复用account_access.visible_clause/parameters及account clock，真实账户SELECT固定tenant、≤500 IDs、ORDER BY id FOR SHARE。目标owner/team必须匹配账户当前归属，当前投手单币种，不靠caller可读推断目标也可读。scope-snapshots和identities目前无Python权威读接口，必须失败关闭；待A提供接口后接。
- C：新material_references.py单批≤200，actor与目标owner的assets.read及数据交集、READY/revision/hash、019 physical LIVE，活跃引用同事务；全池≤500先全量排序再分块。它不提供allocator、capability包或假可执行结果；算法由B实现。
- 来源菜单：主线已确认非空账户/渠道/素材引用必须同时检查caller与实际目标owner的accounts.read/channels.read/assets.read及当前数据范围交集，launch.create/edit不能替代来源read。空引用草稿不额外要求来源菜单。目标owner不会因管理员caller可读而自动得到对象权限。
- 主线：公共launch/templates动作与022菜单，DirectoryTokens目的白名单；app/router/公共credentials不由B并发改。无权403、不可见404、结构400/未知UNKNOWN_FIELD、字段/引用422、版本/并发409保持原语义。

本轮teamai-recall已执行命名时区/金额/模板归属检索，未命中相关learnings，故以上以本次原PRD为准。当前命名默认Asia/Shanghai，不混成账户当地业务日；未来若项目配置允许命名时区变化，预留必须冻结其配置版本并使旧预览失效。原账户币种白名单目前只有币种合法性，不提供货币最小单位/平台最小预算或国家能力字典；D1存储结构边界与D2内部Decimal汇总不能冒充真实精度/能力预检已通过，缺权威版本时D4明确阻断。

## 模板与命名必须保留的非CRUD语义

模板name同租户同owner NFC唯一，TEAM需share动作。TEAM接收者必须同team启用成员，明确冻结集合；默认分享当前启用团队成员也要真正生成名单，超过500明确拒绝而不截断。PRIVATE recipients必须空。接收者只读/使用，非所有者不能修改/归档/扩大共享。apply另需launch.create及目标owner范围，复制配置并生成新local_id，剥账户/渠道/identity/素材池/旧allocation/租约/外部ID/执行结果，activate_after_create=false；素材类型要求保留。旧计划不因模板更新改写。

命名格式原样为“渠道名或code_昵称或姓名_YYYYMMDD_自动编号”，日期按Asia/Shanghai，不用浏览器日。按目标owner冻结昵称（不把操作管理员替代计划负责投手），账户和展开系列的每份分别独立序号；至少4位，9999之后自然增长。预留唯一plan+revision+expanded_key，同revision重试返回原号且允许跳号不回收。CHANNEL DISABLED、角色撤权、频道/昵称版本或日变动在真正预检/提交前复验；旧任务已有冻结名不回写。

## 验证与待结清

先纯测完整DTO/5MiB/Unicode/LF/日期/Decimal/树展开/模板剥离/确定性匹配，再主线真实MySQL/HTTP验证双租户/三身份/多角色并集、CAS/并发/审计失败/幂等撤权/候选版本/名称占号/素材活跃引用；最后真实三视口六区、树编辑、草稿恢复/离开提示、账户/身份/素材池/分配结果/模板所有弹窗。

LCH-01—21、FR-LCH、Template/API/Schema全部逐项保留未验，模板保存和空草稿不替代缺失的身份、预检、预算风控、命令、任务或统计。外部缺设备/Token仅阻断对应平台验证，内部可安全完成的部分继续推进。

## D1首轮真实联调固定检查点（尚未真实SQL验收）

- 新源：`launch_contract.py`/`launch_countries.py`、`launch_expansion.py`、`launch_access.py`、`launch_references.py`、`launch_store.py`/`launch_routes.py`、`template_contract.py`/`template_store.py`/`template_routes.py`；新021迁移。现有渠道/别名与其他线源码未改。
- 首个HTTP入口：`launch_routes.router`及`template_routes.router`，由主线在022菜单窗口显式注册。模板使用launch菜单的templates.*动作，不要求额外launch.read。计划原create/get/list/update、模板原create/get/list/update/share/archive/apply均已写真实事务，尚待真实回执；命名、分配、validate/execute未接，不冒充完成。
- 新68项纯回归已通过（合同/展开/Decimal预算/上海午夜/模板克隆，以及范围/8MiB分页/依赖失败关闭/预读CAS竞态），Ruff通过。纯测不是HTTP或MySQL验收。
- 工具：`run_launch_draft_template_checks(client, admin, headers, fixture, password, cache, cases)`；固定`LAUNCH_DRAFT_TEMPLATE_CASES`14组。必须专属`orbit_py_it_[0-9a-f]{32}`数据库，读取既有人员fixture；临时功能角色通过真实API创建，仅临时替换四名人员sys_user_role并在finally恢复，不改共享作用域。默认团队共享冻结后的新入团队员404，非所有者403，混入外租户接收者整批拒绝；并发CAS、审计trigger故障、幂等恢复、分页水位均由真实请求断言。没有自起服务/数据库。
- 原Page.items要求完整Plan/Template，因此没有用摘要破坏原API。先按payload_bytes/config_bytes的小元数据选ID，8MiB软上限至少一条，随后一次有界集合读JSON，人数集合一次批量读；未达到page_size也必须给next_cursor。界面概览后续可用明确summary技术扩展，不能假称原Page不含大配置。
- 预算此阶段确认严格Decimal语法及拥有者/复制公式、所选账户真实币种一致；真正币种minor unit、平台最小值、预算policy版本仍未接，不可将DRAFT视为有效预检。国家使用249项ISO快照并保留原始源/hash，不靠二字母正则接受ZZ；运行时不联网。
- 非空账户引用实时caller+target accounts.read与当前own/显式managed scope交集、唯一真实owner/team/币种；非空素材走C新的有界双权限READY/LIVE/revision/hash接口，安全扫描状态仍不能代表整个计划可执行；非空渠道走双方channels.read、拥有者交集、启用状态及当前产品/总代AVAILABLE关系。空草稿不强加来源菜单。
- 原WORKFLOWS125规定snapshot与显式account_ids不可同时非空，已严格422；snapshot单独输入在A025未接时503，不以普通cursor替代。身份/环境绑定及metric_profile资料源未接时明确503，绝不把未知租户UUID当已验证资料落库。
- 模板TEAM空接收者按原PERMISSIONS冻结当前启用成员（最多500，超过须明确选择，不能截断）。变更/撤回共享须templates.share；保留相同共享集合编辑文字不额外强加share；归档不因历史接收者已停用而被阻塞。非所有者维护一律拒绝。应用需templates.read+launch.create，既验预读版本又验锁后CAS，避免未来If-Match复制旧树；深复制新local_id，剥所有来源选择。
- 命名DDL唯一键包含plan/revision/项目日期/真实来源hash，相同完整输入沿用，日期或姓名来源变化允许重新预留，旧记录不覆写。实际占号/旧预览失效/提交尚未实施和实测。
- 容量限制不是容量验收：q包含搜索仍有scope范围扫描风险；索引/EXPLAIN/真实大分布压力与恢复排主线后续队列，当前不标PASS。

D1候选补充固定检查点：经主线允许在首轮未开始前补两capabilities的actor_user_id/actor_team_id/actor_label和`GET /launch-plans/ownership-options`。候选只需launch.create或launch.edit之一，数据范围始终本人OR显式管理团队（SUPER当前租户），不隐含system.users/accounts/channels权限；返回仅id/name/team_id/team_name，200项上限及actor/tenant/team/数据角色/显式范围/目录版本/page_size签名游标。临时角色撤两写动作403；演员换team后本人候选和caps即时反映；USER同team peer不能候选。新增`launch_options.py`及4项纯回归，总72纯测PASS；真实HTTP工具固定清单扩至16组（原14+拥有者范围、撤权/换team两组），尚待真实回执。前一段14组/68项属于第一次冻结历史，实际待测版本以本段16/72为准。

A025后台/三视口完成后经主线解冻，UUID输入已收紧为原规范短横线形式（允许大写归一化，拒花括号/裸32位/URN）；四项新纯回归及D1结构组真实待测断言已补。现D1+recipient共80项纯测PASS，Ruff PASS，真实工具16+4组待主线串行。新增recipient是templates.share单动作独立候选，不依赖launch写或templates.read；返会话CSRF供只分享动作的真实写入，限定本人当前team或明确可维护的本人旧模板team，源JSON不接受任意team_id。静态recipient router须先于模板动态ID路由注册。此检查点全B新后端与工具重新冻结，前端独立继续。

## D1真实后端与前端送验检查点（2026-11-08，北京时间）

本段更新前面历史“待测”状态：主线`python-launch-template-channel-attempt-01.json`中D1固定16组全部实际通过；该父轮整体失败是recipient新夹具sys_user.user_name超过原表30字符，不能把父轮改写为PASS。夹具改为29字符随机唯一值后，`python-template-recipients-http.json`独立21/21实际通过（含4个新recipient业务组），原字段长度与断言保持。没有重复跑未改D1或47组旧渠道。

前端新增`src/views/orbit/launch/{index,DraftEditor,CampaignTree,SourcePicker,TemplatesPanel}.vue`，API专属`launch.ts/templates.ts/launch-form.ts/launch-recovery.ts/launch-countries.ts`。可打开022原投放菜单，操作三层树的新增/复制/编辑、预算弹窗、负责人/账户/渠道/素材候选、服务器草稿保存/详情，以及模板保存/详情/修改/分享/加载新草稿/归档。模板加载剥来源并新建local_id；不提供手填拥有者UUID。网络结果未知时冻结原业务体和幂等键，当前账号sessionStorage只存恢复业务意图，不存CSRF或凭据；刷新后使用当前会话凭据重试原键，撤权不会被当作原请求确定失败。

前端6文件27项纯/组件测试PASS，完整vue-tsc PASS。最后修改涉及模板错误展示/首次加载、只读标题和来源弹窗关闭竞态，分别复验组件12+4项PASS；首次草稿保存后E2E重定位“编辑投放草稿”，不依赖已变更的旧抽屉名称。源码准备冻结由主线完整构建并串行浏览器验证。

真实浏览器入口`tests/e2e/orbit-python-launch.spec.ts`，单test按三视口执行：真实登录→101码点拒绝→三个来源候选GET/取消→三层树/预算/100emoji标题/广告复制→POST草稿→保存模板→共享明确成员→应用新草稿→PUT改名→归档模板→已应用草稿详情保持原配置。没有route.fulfill、UI代写数据库或真实广告外发。此时尚未跑浏览器，不能记UI验收通过。素材列表依赖主线迁移026；该首轮只测试候选读取/取消，不宣称非空来源选择完整验证。

仍未完成：账户scope解析接入、逐账户身份、权威能力/币种minor-unit/预算policy、真实命名占号、全局素材分配、validate/execute命令与任务、每一原字段弹窗异常与真实容量验收。来源候选和模板搜索目前手动提交；筛选变化后旧游标需重读首页，进一步交互/大数据性能仍待专项。D1真实落库或三层草稿不等同PY06整模块完成。

主线最新真实后台回执`python-channel-launch-naming-http.json`：through029共92/92实际PASS（83.22秒），原D1 16、recipient4及命名8均覆盖当前冻结版本。UI首轮三视口在成功apply后ElTabs内部状态与父modelValue分离，已修为确定成功内部切页先nextTick再开editor，真实ElementPlus组件2组PASS。UI第02轮三视口分享中文原因原生/模型状态尚待定位（提交前原因校验阻止，未发POST）；现加入候选ready及原生值/模型计数断言和异步候选真实组件专项，不能把这些断言称产品修复或浏览器通过。后台PASS与UI失败分开保留。

UI诊断03—05进一步区分了问题：05受控事件附件仅固定枚举/长度/布尔，确认DOM标签正确、无重复ID，focus由ACTION_REASON被仍打开的多选弹层接回SELECT_INPUT，9码点全部写入其搜索框；不是原因模型/校验逻辑丢字。spec改为真实点击原因框触发clickoutside，并断言成员框aria-expanded=false、原因框获焦后原fill，保留原生值/模型9码点/后端响应断言，未改逐字输入或强制点击。临时事件诊断及document listener均已移除。06单桌面实际通过分享/应用/改名/归档/详情业务链，最终响应式边界在抽屉右侧滑入动画的初始几何处失败；最新spec用原默认5秒expect.poll等待真实left/right入视口，再执行完全相同的边界与scrollWidth断言，没有固定sleep/放宽边界。仍等待后续实际PASS回执，不把06父FAIL改成通过。

原投放UI最终主线`python-launch-browser.json`已真实三视口全PASS（宏7/7，browser expected3，0 failed/skipped/flaky，53.27秒），范围限定为草稿三层预算/100emoji/来源GET与取消、模板保存/分享/apply/archive、详情及响应式。单桌面07此前7/7、27.46秒在`python-launch-desktop-diagnostic.json`，不与三视口重复计验收。01—06父FAIL和05安全焦点诊断仍单独保留，不改写历史。账户scope当前实际消费接入另见LAUNCH_SCOPE_DELIVERY.md，此新后台消费节点未包含在上述UI通过证据；身份/能力/分配/执行仍不由这轮UI冒充通过。

A025→launch实际消费后台已由主线`python-launch-scope-consumption-http.json`验证：through030完整102/102 PASS（84.77秒，原92+新10）；111项定向纯测也再次PASS。真实范围包括原请求不变/真实MySQL1213重试、不同scope同IDs幂等冲突、500实际ID落库/501及展开超限拒绝、GET原body回编、immutable来源依赖、权限/归属币种漂移与审计全回滚。详见LAUNCH_SCOPE_DELIVERY。本次没有新增scope消费前端浏览器验收，预检/身份/profile/能力/分配持久化/任务执行仍未完成，不把102后台PASS扩写成整PY06通过。


## 指标依赖接力与当前授权（节点 2026-11-09 00:14，北京时间）

原计划新保存按实际create/edit动作解析原adset.metric_profile_id，冻结精确profile版本、head revision、正文与来源摘要及配置版本。无monitor.read也可按已知UUID保存；目录读取仍另需原monitor.read。相同正文配新键且绑定来源换版时建立新PlanVersion，无关metric clock变化不制造新配置版本。成功旧键先匹配原意图，再校验当前原read权限与对象范围返回原结果；不再因来源停用/最新CAS/已提交状态重新绑定。并发首次探测均miss后的fallback同样核read，真实两个clock等待者最终一份201写入、另一份403读拒绝。

044为模板head和只追加version增加可空dependency_json；旧NULL仍表示历史未知。新create/edit精确冻结，share/archive只沿用已存依赖含NULL，apply的新键则在新Plan中重新绑定当前资料；不回填旧模板。历史version的UPDATE/DELETE数据库拒绝。原API响应未增加内部字段。

实际证据：`python-plan-template-metric044-http.json`35/35，`python-launch-scope-current044-http.json`43/43，`python-template-current-scope-concurrent044-http.json`18/18。模板旧RR范围基线先真实失败后修复：嵌套管理/收件人关系及当前收件人列表均显式锁定读取，避免普通成功键探测先建立旧视图后仍读到撤销关系；首轮失败完整保留。

另修复状态head不等于配置source的内部边界：保存先capture_plan_source核完整性，再读取实际source_revision依赖，不能猜预检状态head存在PlanVersion。这个边界有固定纯协议回归；目前真实validate成功夹具含未接生产的identity引用，不能据纯测宣称整个“正式预检后编辑”HTTP闭环已验收，身份来源桥仍须开发。

固定ORBIT Python2582项67.94秒通过，全部受测源码前后摘要一致；前端638项及类型、指定目录格式、构建通过。新共享字段组件的桌面真实3/3通过；完整三视口首轮手机导航侧栏遮挡正在定位，尚未全通过。生产Meta绑定M1仅临时只读观察，未持久发布或授予执行权；隔离SQL资料、纯测、构建和上述有限专项均不代表完整模块/平台验收。严格台账仍29开发/29测试/0验收。


### 指标字段完整浏览器复验（2026-11-09 00:24，北京时间）

新计划/模板共享指标输入和选择器完整三视口9/9、整档7/7通过，实际浏览器54.30秒；前端638项、类型/格式/构建通过，已提交推送5fb2196。首轮浏览器6通过/3手机失败保留，确认原移动侧栏尚展开后，使用原遮罩正常收起；手机3/3后完整9/9重新执行，不增加60秒/零重试，不修改布局或绕过点击。三个实际操作：目录全部12字段与隔离来源提示→选择UUID保存重读；清空后PUT及响应均不含可选属性；无monitor.read原角色手填保存、目录GET始终零。没有发送命名/分配/预检/广告执行请求。

后续源代码当前复验：Plan/Template指标原HTTP35/35、旧RR当前授权与真实并发重放18/18、原三角色五万SQL计划和独占清理17/17均通过。原identity正式来源尚未接，纯协议验证不能升级为正式预检后编辑验收。固定Python2582项源码前后不变，严格台账29开发/29测试/0验收。当前接力为A的M2原始观察登记（候选045未接入/未验收）、任务worker与任务UI缺口审查；本节点提交推送后继续，非产品最终完成。


### 第七节接力与交叉审查（2026-11-09 00:50，北京时间）

任务GET/SSE客户端保留原Error全部五字段，页面提供中文只读错误详情，切换当前身份及权限上下文时清理旧请求、事件和错误；本地错误不虚构服务端请求编号。固定前端688/688、类型/格式/生产构建通过，受测源码前后相同，见frontend-task-read-errors-current.json。原Task三视口6/6、整档23/23，事件流三视口6/6、整档24/24真实通过，见python-task-read-error044-three-viewports.json和python-task-read-error044-events-three-viewports.json。首轮事件流3通过/3失败及父档21通过/1失败/2未运行保留：完整撤权文案恢复后，原隐藏详情/零行/真实403/停止观察断言原样复验；未放宽超时或更改原布局。

A/B/C继续按文件所有权接力：A修复原始观察登记missing-key锁风险、重放明细完整性及捕获当前团队授权；C修复未发送证明与读回事实冲突时误判可重试的问题，121项纯测通过，仍待046真实SQL；B接本次订阅观察记录九字段只读展示。045/046尚未真实集成通过，不将纯测或候选DDL计为业务验收。原18080/18081/19310预览进程保持，严格台账仍29开发/29测试/0验收，全部内部功能尚未完成。


### 第七节真实数据库接力（2026-11-09 01:04，北京时间）

045原始观察登记实际20/20、10.21秒通过，14组专属覆盖：六表原子登记、当前范围及动作、旧成功回执/新键CAS、同key异根、审计/outbox1644整笔回滚、双首probe真实并发、UTC微秒三个边界、12个不可变护栏、旧RR团队撤回及受控损坏失败关闭。实际50次受控Graph GET、0真实Meta请求，账户/READ_VERIFIED均为SQL技术fixture；原始观察不能充当023身份能力或广告执行授权。

046租约SQL护栏真实16/16、9.39秒通过：原validate200/execute202完整来源、3表6触发器、精确FK/单调fence、旧尝试事实隔离与1644整体回滚。首轮14通过/1失败/1未运行保留：测试管理连接autocommit=True漏显式begin，修正后完整原断言复验。纯恢复合同121项含“未发送证明与任意读回冲突不可重试”，尚无claim/send/Worker或事故恢复验收。

TaskEvent九字段只读观察记录真实三视口6/6、整档24/24、101.82秒通过；依据真实提交request_id逐字段对账，保留旧撤权/隐藏/清空/403/停止订阅断言。内存仅最近200条，四档本地分页，不冒充完整历史；前端702项及类型/格式/构建通过，已推送83c886c。固定ORBIT Python2768/2768、68.08秒且源码前后相同；首次快照误纳在制Store导致SOURCE_CHANGED的失败另保留，重跑明确排除其源码/新测试。所有具名回执位于evidence，不把有限专项提升为产品验收。

三线继续：A凭据主体与身份资源额外事实观察、B任务拥有者精确筛选、C有界流式事实和可信恢复读取。新窄Store当前仅55纯测，未纳2768或真实046护栏验收；正式来源、状态写/后台任务、预算与锁等仍待完成。严格总台账29开发/29测试/0验收，原18080/18081/19310预览保持。


### 任务冻结拥有者查询（2026-11-09 01:11，北京时间）

任务列表新增冻结任务拥有者UUID精确筛选，沿原operator_user_id GET参数与当前授权范围交集；空值移除参数、查询重置游标、上下文/撤权清理、非法UUID本地拒绝、原行内筛选保留，无人员目录依赖或额外权限。实际Task三视口6/6、整档23/23通过，浏览器77.91秒；原详情/关闭停流/角色范围断言保留，追加按真实owner查询及清除参数的实际GET对账。固定前端713项、类型/格式/构建通过，源码前后相同。见python-task-owner-filter046-three-viewports.json与frontend-task-owner-filter046-final.json。

TaskNode字段审查确认原13必需及2可选均有可达显示，缺失no_op不猜false；此次只补原列表查询入口，不把未实现Worker、任务控制或完整2342项提升为已验收。严格台账仍29开发/29测试/0验收，后端恢复读取和额外Meta事实观察继续。


### 第七节持续接力：监测范围消费（2026-11-09 01:41，北京时间）

三条开发线继续分别推进身份来源绑定、监测事实/查询设计、执行事实追加；公共路由、迁移编号、共享真实验证、台账和Git仍由主线统一。监测合同和范围消费固定源码249项纯测试、Ruff检查及格式检查通过，源码前后不变；真实MySQL/HTTP范围专项13/13通过，证据为`evidence/python-metrics-scope046-http.json`及`evidence/python-metrics-contract-scope-unit.json`。

本轮验证monitor.read消费原501账户冻结范围、无accounts.read、空快照、撤权、不同主体与归属漂移；未实现Metrics路由、指标采集、聚合或新增容量验收，不从旧spend表伪造完整指标。严格总台账保持2342项、29开发/29测试/0验收。050事实微秒迁移已审核采用，追加SQL/并发/回滚仍待新专项，不能据迁移文件存在勾选。原预览不变，继续开发。


### 第七节真实验证与接力（2026-11-09 01:59，北京时间）

- 身份观察/真实配置主体绑定与051回执边界组合34/34、10.46秒通过；4个合法边界、40个非法回执均精确3819、无原1235兼容性或转换警告，六表无探针残留。全档100次受控Graph GET、30次网络期间零SQL检查、0次真实Meta调用。旧31档及原警告记录保留；仍非023权威能力/平台验收。
- 执行事实追加完整27/27、10.05秒通过，含原只读7组、微秒三边界、跨SQL秒重放原回执、旧fence全current字段不变、真实1644整笔回滚重试及两连接同event唯一fact/audit/outbox。两轮22通过/1失败/4未运行均保留：SET后换连接与AsyncConnection类型适配已修，原断言未删。尚无恢复状态提交、Worker或广告发送。
- 监测合同/范围/分子比率固定280项通过，范围真实13/13；048/049仅数据库初始化及原范围13项回归成功，新的父树FK/发布不可变/最新完整cell选择仍待专属工具，不能据建表勾选功能。名称快照已设计为独立维度，避免日事实重复四级长文本；完整Metrics API、发行来源和容量未完成。
- 固定已就绪ORBIT Python清单3289/3289、70.43秒通过，源码前后hash一致；明确排除B在制schema工具/QueryStore。前端沿用实际713项及拥有者筛选三视口6/6证据，本轮无前端源码变更，不重复冒称重新验过。

三线继续A身份完整库存/发布设计、B监测SQL专属工具后只读查询、C恢复CAS与052完整决策追溯。主线统一公共接口、迁移与串行真实验证、台账和Git。严格2342项仍29开发/29测试/0验收，原预览不变，不部署或真实广告写入；本检查点不是整个产品完成。


### 第七节监测SQL护栏接力（2026-11-09 02:05，北京时间）

048/049正式迁移与专属真实SQL20/20、10.53秒通过（旧范围13+新7）；工具护栏纯测25/25及格式/静态检查通过。新7组实际验证12表/32触发器、完整同账户父树和publication/generation/profile组合FK、发布后逐表I/U/D拒绝、READY快照/旧构建代次保护、最新120完整空/省略结果不回填100广告以及迟到110不覆盖120、原包含搜索和前导零ID。原旧VALUES语法的MySQL弃用警告保留，未当作正确性失败；不删原断言。

所有来源与manifest为明确SQL_ONLY_NOT_PLATFORM技术样本；该工具未验证生产发行权威、同token并发构建、名称hash碰撞校验实现、完整Metrics接口或容量，不据DDL专项勾选业务验收。具名回执`evidence/python-metric-facts048-query049-sql.json`，初始化回执独立保留。三线继续身份完整发布、只读QueryStore和恢复CAS/决策追溯；主线仍串行队列和Git，未部署，严格29开发/29测试/0验收不变。

048/049正式SQL注释与文件尾格式整理后，原20组按最终源码完整复验通过，未删场景；最终回执为evidence/python-metric-facts048-query049-final-sql.json，初轮回执继续保留。


### 第七节恢复提交与身份发布接力（2026-11-09 02:29，北京时间）

052完整恢复组合真实40/40、12.72秒通过：原执行受理/租约/事实27组与新恢复13组；包含原Task/节点/SSE读取、ACK两条中间边、289条尾页冲突、五分钟/24小时UNKNOWN、其他节点人工标记、五项CAS、两连接仅一提交、1644全表回滚重试、不可变决策及原七日事件清理。固定恢复六测试文件241/241、1.60秒且源码前后一致。首轮26通过/1失败/13未运行保留，根因为工具元数据LIKE的驱动参数格式，改为绑定参数后保留2表6trigger断言完整重跑。证据evidence/python-execution-recovery052-http.json及python-execution-recovery052-unit.json。没有正式恢复调度、claim/send、平台来源或事故恢复验收。

053身份完整发布及原GET真实18/18、10.94秒通过，显式选择through046+051+053：完整库存/独立发行来源、微秒floor投影、当前权限先于幂等重放、旧来源CAS、双首probe并发、1644整笔回滚、旧RR撤回及发行撤销。首轮6通过/1失败/11未运行保留，实际SQLAlchemy RowMapping不支持dict合并运算，改为显式dict并增加Mapping替身回归。证据evidence/python-identity-publication053-http.json。来源仍为隔离协议发行，正式Meta发行、列表摘要/计划引用接线和新三视口尚待后续，不据有限实测宣布整个账户模块完成。

A继续独立身份三视口，B继续指标窄读取专属真实工具，C转正式恢复扫描调度设计；公共入口、迁移、共享真实队列、台账及Git由主线负责。2342项严格台账仍29开发/29测试/0验收；原预览未变，无部署或真实广告写入。
