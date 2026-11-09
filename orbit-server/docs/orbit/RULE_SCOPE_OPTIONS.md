# 规则作用账户的操作者/户商筛选候选

本技术扩展经主线批准，生产路由/签名用途注册及真实执行由主线统筹。它不扩充原Rule15、RuleWrite11、Scope5或Member3，不授人员、账户分配、户商导入或模拟能力。

## 已冻结公开合同

`GET /api/v1/rules/editor-scope-options`

|参数|准确语义|
|---|---|
|kind|必需，OPERATOR或VENDOR|
|action|原CREATE或UPDATE，分别只要求rules.create或rules.edit|
|rule_id|CREATE省略；UPDATE当前规则UUID必需，与当前head和状态重新核验|
|owner_user_id|目标规则拥有者business UUID必需|
|owner_team_id|目标规则团队business UUID必需；没有team_id同义参数|
|q|可选空，最多100码点；候选真实label字面前缀；完整带连字符UUID时只精确id；不是账户名称过滤q|
|page_size|20/50/100/200，默认50|
|cursor|不透明签名键集游标，不超过2048字符|

未知/重复参数400；参数值422，精确字段pointer。此入口不接status/auth_status/operator_user_id/vendor_id/account_q等其它过滤参数，传入直接拒绝，不静默忽略。候选基于**完整当前caller与目标owner双范围可读账户交集**，不随Selector其它已选过滤器收缩；最终Scope创建仍原五filters完整查询/原子冻结。这样两个下拉不因自己的已选值锁成单一候选，也不让一个q承担两个搜索域。

返回严格Page4：`{items,next_cursor,data_as_of,scope_version}`，scope_version沿原caller auth_version安全正整数；data_as_of原UTC date-time。UUID排序键集、四档、首末/上一页由客户端历史游标完成；不是全量候选清单。

OPERATOR item严格5字段：`{id,name,team_id,team_name,active}`。

- id为 `orbit_business_user.id`，不是sys_user原生整数、created_by、平台system user或账户external_id。
- name按当前 `COALESCE(NULLIF(display_name,''),NULLIF(sys_user.nick_name,''),sys_user.user_name)`；team_id/team_name为真实当前业务团队。不会把UUID当人名或同名当同一身份；UI可拼真实名字/团队/完整id消歧。
- active严格boolean，按现owner_active的人员、邀请、原生停用/删除、团队与scope启用状态计算。仍拥有可读账户的失效操作者保留active=false供历史过滤；这不是新指派人员候选，不授账户分配或规则owner新指派。

VENDOR item严格4字段：`{id,name,alias,availability}`。

- id为当前同tenant kind=VENDOR的 `orbit_reference_record.id`；name是真实资料名，不作为alias默认值。
- alias仅来自独立 `orbit_vendor_alias.alias`，未知/未设置严格null，不从name截断或猜代称。name字符串、alias字符串或null，分别保留；同alias不同id不合并。
- availability为AVAILABLE/UNAVAILABLE；只要历史绑定账户当前确实在双范围中，可筛UNAVAILABLE，不因此允许新导入/新绑定。
- 资料本身的姓名/代称还必须满足caller与目标owner的reference数据范围（无额外模块动作）；foreign或不可见资料不能借label泄露。已失效旧选择由前端保留原值作说明/清除，不把缺候选伪成有效新选项。

## 明确一致性方案：独占READ COMMITTED

新route使用现 `read_committed_session(DataSourceRegistry)` 自有连接，再开启外层session.begin。Store入口必须核实实际bind为AsyncConnection，已配置READ COMMITTED且有真实外层事务；不接受仅session.info字符串旗标。**不依赖外层FOR SHARE使嵌套EXISTS在RR下变当前读**；本方案选择独占RC+完整clock/末重核，避免原_rule预读建立RR旧readview后与新clock拼接。

原authorize_rule与owner_scope/_begin读取当前动作、明确管理团队、目标owner及原指派边界；不借accounts.read/users/monitor/profile。来源锁序为现授权/无锁Rule预读→reference_clock（含alias维护的revision）→directory_clock→account_clock→有界label/alias当前行→Ruleclock/head及双方末重核。所有正式来源写方遵循对应clock；结果最后核Rule当前version/ownership/state及双方当前授权。CREATE无head，不为它发明占位revision；UPDATE只接受原可重新选账户状态。

cursor purpose预留 `RULE_SCOPE_OPTIONS_CURSOR_V1`，主线统一注册。绑定session/actor/tenant、双方完整scope指纹、kind/action/目标owner_team_id/user_id、UPDATE当前head/revision/payload、q/page_size、reference/directory/account水位、after和asof。alias维护已增加reference_clock.revision，不新造alias clock。当前动作撤销403；Rule越域404；当前head/scope/来源水位漂移409；MAC错误沿原token错误；持久label/schema不完整503整页拒绝，不删掉坏行凑成功页。

## SQL与容量边界

OPERATOR按business_user `(tenant,id)>after` 驱动，EXISTS当前双范围账户 `a.owner_user_id=b.id`；VENDOR按reference `(tenant,kind,id)>after` 驱动，EXISTS双范围账户 `a.vendor_id=r.id`。源目录每候选一行，无应用拉全accountIDs、无OFFSET、无应用层全量distinct；page_size+1并有界批量读alias/label。

复用012 idx_account_owner/team/vendor，009 reference_kind/team/reference_owner覆盖索引，017 alias复合主键；不提出新DDL。label表达式与alias搜索缺专门索引，因此LIMIT不等于容量通过；真实执行计划与大目录需要另证。无未来源候选补零/假全选。

## 当前阶段

公开contract与后续Store/routes/tests/tools为独立文件，尚未注册公共路由、执行SQL/HTTP/浏览器或容量验收；采样期仅编辑和轻量静态检查，完整测试等主线窗口。teamai recall未找到ORBIT此候选的更具体约定，以原PRD、当前已确认规则Scope与本次批准的技术扩展为准。

## 当前开发冻结与有限证据

新增 contract/store/routes 三个模块、两份专属纯测及 `tools/rule_scope_options_checks.py` 已形成固定检查点。定向纯测66项通过（0.84秒），六文件 Ruff check 与 format --check 通过。此前首轮纯测暴露显式q=null未先类型检查，已修为422；第二次新增clock测试的局部变量拼接位置错误已修。它们均不代表SQL/HTTP或容量通过。

主线已统一注册 `RULE_SCOPE_OPTIONS_CURSOR_V1`，原跨用途纯回归34项通过。新router入口为 `orbit_api.rule_scope_options_routes.router`，须在 `/rules/{rule_id}` 动态路由前显式注册。原app、权限、凭据和公共runner没有由B修改。

真实工具入口为 `run_rule_scope_options_checks(client,admin,headers,password,cache,database,cases)`，固定 `RULE_SCOPE_OPTIONS_CASES` 八组；新档基线6加本8预计14，实际以主线回执为准。工具仅允许127.0.0.1:13306且实际SELECT DATABASE()等于精确UUID库。本工具独立固定原生用户990631—990653；实际新API角色仅rules.create/edit。SQL样本23个人员/23个户商与UNKNOWN账户、一条真实代称、一个明确管理团队，均SQL_ONLY，不是平台权威或导入成功。新fixture留在本轮独立UUID库，由主线整库生命周期清理；不恢复其它工具的既有人物/角色，不混用同档已有固定用户。

八组实际待跑断言依次是：不借accounts动作；操作者四档完整集合/真实UUID/停用历史；户商四字段四档/未知代称/不可用历史；USER本人和TEAM明确管理/同team peer排除/管理员caller不得扩大目标USER；双方reference范围与中文字面%_!前缀；kind/size/q/session和三来源clock绑定；当前动作撤回403与不存在UPDATE规则404；未知重复参数/GET正文/非法值和规则业务表零写。当前工具并未证明现存UPDATE规则head漂移、真实跨tenant对象、并发撤权锁竞争、EXPLAIN或大容量；这些留为后续明确专项，不以不存在UUID冒称跨租户通过。

Store只接受真实bind为READ COMMITTED的AsyncConnection和已开启外层事务；其它会话在授权/来源SQL前拒绝。纯测证明此入口护栏/SQL结构和末段错误传播，真正RC嵌套EXISTS行为仍待主线真实队列。没有新增DDL，候选label表达式及alias前缀不声称现有索引可覆盖整个搜索，尚无容量结论。

## 首轮真实结果与新增两组（等待复验）

主线回报原62加本8共70/70真实PASS，22.47秒，归档名 `python-rule-scope-options062-http.json`。这项证据仅覆盖当轮原八组，不能继承为新增case通过。

现工具保留原八个CASE名称和断言，追加两组：

1. `pythonRuleScopeOptionsExistingUpdateHeadCasAndArchivedStateInvalidatesCursor`：经原Scope POST、原Rule POST得到真实revision1 DRAFT；UPDATE上下文20+3分页完整23人；经原Rule PUT真实推进revision2，旧cursor409、新首屏正常；经原archive POST真实归档revision3后UPDATE无论有无cursor均409。不由SQL写Rule head/version/state。
2. `pythonRuleScopeOptionsRealForeignTenantOwnerVendorAccountIsolation`：独立真实外tenant/team/owner/native身份/VENDOR/alias/account完整关联，并用SQL JOIN先核这条关系存在；当前root及规则专属USER按真实foreign operator/vendor UUID或外域名称前缀查询均空items，不泄label/alias。foreign owner沿原root OWNER_UNAVAILABLE422、USER OWNERSHIP_DENIED403，不为新接口改错误语义。真实外域account经原editor-scope IDS路径拒404；集合空页不伪造404，也不以随机不存在对象冒充跨tenant。

新增foreign原生用户990654；独立mode固定范围更新为990631—990654，其余随机实体仍留本轮UUID库由主线整库清理。公开route和全部生产源码保持首轮通过版本未变。本轮定向纯测67/67 PASS0.76秒、修改的tool/test Ruff/format PASS；新增两组尚未真实运行。主线下一组合为原62+候选10，预计72，实际以真实回执为准。

## 新增两组真实复验及有限内置浏览器

主线已完成原62+候选10+字段边界7的共同父档 **79/79 PASS**，耗时578.85秒（含手动等待）。父回执为 `evidence/python-rule-scope-options062-browser-parent.json`；本工具追加的真实UPDATE head/归档及实际跨tenant两组均已真实通过，前节“等待复验”属于此前历史状态。原八组仍在本次重验中，未削弱其断言。SQL UNKNOWN账户、资料和profile依旧仅隔离技术样本，非平台权威。

同档内置浏览器有限12项实际PASS，证据 `evidence/python-rule-scope-options062-browser-partial.json`：真实登录与原菜单、创建二级页、操作者真实名称/停用历史、20+3与已选保留和23唯一人、户商23项/22个未知代称/不可用历史、原五filter和真实范围冻结/回执、1440/1920/390布局及最终重载占位文案。其明确限制仍保留：100/200仅选项可见而非独立UI翻页，UI撤权/网络/DST/完整新Rule保存未本轮实测；损坏head造成SUPER列表503未被删除或称通过；最初错路由404与原登录429自然恢复也未掩盖。没有新Rule保存、Simulation/启用或广告平台写入。最后两处placeholder变更后仅复载检查，因此不宣称12项全程属于同一冻结源码，不标整页/模块完整验收。
