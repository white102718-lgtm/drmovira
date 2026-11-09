# Rule编辑账户选择与私有冻结：阶段2设计

当前已有独立生产候选模块及纯测、061 SQL候选和待执行真实工具；尚未接公共app/RuleStore/双来源reader、未执行迁移/SQL/HTTP、没有账户选择UI或容量验收。阶段1context/OWNER/PROFILE沿用已冻结合同；本阶段不借用accounts.read、system.users或monitor.read，不改原Rule/MetricProfile/ScopeSnapshot五字段及Member三字段DTO。不是执行、模拟资格或Meta授权。

## 约束与现代码核对

- 原025账户scope四表、`AccountScopeStore.authorize(accounts.read)`、creator私有、原幂等唯一键及原接口全部保留。不为了Rule改025的唯一键或放宽reader。
- 原`account_scope_contract.parse_scope`负责IDS/FILTER、重复UUID拒绝、50000上限、规范JSON；`account_selection.selection_sql`仅固定别名a筛选SQL，不授予权限，可直接复用纯函数。现`AccountScopeStore.create`混合授权/DB/审计，不可整体冒充通用engine。
- 原`rule_access.authorize_rule`/`owner_scope`/`revalidate_owner`负责原rules动作、当前caller与owner身份/团队。`readable`可复用双方账户交集判断。原UPDATE previous只能由当前锁定Rule得出。
- 原`rule_scope_references.capture_rule_scope`从025读完整原七列hash并重验双方成员，现057 `orbit_rule_scope_manifest.source_snapshot_id`永久FK原025。仅新增reader而不改FK不可行。
- scope成员不继承Plan500。原Rule范围是1–50000。FILTER超过上限拒绝而非截断；IDS先核原输入数量再拒重复/越权/缺失，不静默去重。
- 当前纯选择与分批封装需显式公用模块提案，root审核后再分配旧Store改动。首次生产实现可直接复用现有parser及固定selection_sql，用小型通用batch/hash helper，禁止复制整段Store然后称共享。

## 技术扩展API与精确对象

以下为新增技术扩展，尚待root统一路由注册/MAC用途，不改变原九Rule API。

1. `GET /api/v1/rules/editor-accounts`：action CREATE/UPDATE、rule_id配对规则同阶段1；owner_user_id/owner_team_id必填；原账户五筛选q/status/auth_status/operator_user_id/vendor_id；page_size四档20/50/100/200，cursor有界非空。返回原成员三字段`{account_id,external_id,name}`列表及`next_cursor/data_as_of/scope_version`，仅当前caller和目标owner交集。这里不返回日事实，不需要metrics/monitor动作；如果UI确需额外字段须另明示扩展而非偷偷增加原Member schema。
2. `POST /api/v1/rules/editor-scope-snapshots`：严格正文`{action,rule_id,ownership,selection}`；selection原三字段`{mode,account_ids,filter}`。CREATE的rule_id=null；UPDATE真实UUID，服务器核当前Rule/可编辑状态并只读生成previous，不接受HTTP previous。原rules.create/edit分别独立，原会话CSRF+Idempotency-Key+request_id；UPDATE需If-Match当前Rule revision以免owner/范围上下文漂移。返回原Scope五字段`{id,count,scope_version,hash,created_at}`；原RuleWrite仍只传这个UUID。
3. `GET /api/v1/rules/editor-scope-snapshots/{id}/members`：scope仅creator可读，依已存CREATE/UPDATE动作重验原rules权限；不得拿rules.read或任意owner身份读取他人的私有scope。UPDATE还需当前Rule可见，整个原成员集合当前双方可读才允许任一页，不能只核本页。返回原Member三字段及原ScopeMembers页字段；q仅冻结external_id/name_prefix原语义，page_size四档。
4. caps建议复用阶段1上下文CSRF，只新增显式`max_rule_accounts=50000`扩展时须新DTO；不复用账户caps的`max_plan_accounts=500`。接口参数未知/重复/跨tenant/GET body一律沿既有严格边界拒绝。

cursor绑定session、actor、tenant、subject、auth_version/data_role/team/managed、原action、rule_id/revision、owner身份与完整scope指纹、规范filters、page_size、account clock与首个data_as_of；members另绑定snapshot id/hash/count与双方当前授权。上下文变化409，非法MAC/参数按既有边界；用途由root分配，不复用ACCOUNT_SCOPE_CURSOR签名。

CREATE新分配使用完整fresh owner边界；UPDATE允许保存有效旧owner仅在original previous与当前锁定Rule一致时。owner保留不能绕过每个新账户同时处于双方当前交集。历史成功幂等原结果重放先核当前会话/creator及当前完整成员可读，不能重新冻结或重新绑定当前owner；同键异正文409。命名空间独立表`(tenant,actor,request_key)`，原账户相同raw key完全不冲突。

## SQL四表及双来源

候选：`sql-drafts/061_rule_editor_scopes_candidate.sql`，4 CREATE TABLE、1 ALTER TABLE、12新增trigger。没有修改025或drop任何旧trigger。

- `orbit_rule_editor_scope_snapshot`：原创建者、动作/UPDATE rule+revision、目标owner/team、双授权指纹、account水位、规范请求+hash、唯一幂等键、BUILDING ready0到完整ready1、count/hash、原UTC3。ready0仅count0/hashNULL；ready1严格1..50000/hash64小写十六进制。
- `..._member`：原七列规范hash所需冻结列+name_prefix，PK(tenant,snapshot,account)，前缀键集索引。currency保留未知NULL，不猜值。成员只允许未ready时追加，发布后不可插改删。
- `..._event`：精确snapshot/actor/count/hash；同snapshot唯一成功事件、永久不可变；插入核已ready及真实metadata匹配。
- `..._outbox`：精确(tenant,event,snapshot)组合FK、PENDING→DONE单调；内容/created不可改、不可删除。尚未注册consumer。

应用必须同一外层事务插入snapshot→完整分块成员→校验完整hash/count→ready1→event→outbox，且再次复核权限/owner/currentRule。任何失败整笔回滚，不能先commit ready后补票。DDL计数trigger只证明完整数量，不能代替应用对规范七列hash重算或身份授权；直接技术SQL不是发布authority。

057迁移：原文件第二条匿名FK预期为`orbit_rule_scope_manifest_ibfk_2`，精确指向原(tenant,source_snapshot_id)→025(tenant,id)。正式迁移前必须实际SHOW CREATE与INFORMATION_SCHEMA核该名称、列序、目标和默认RESTRICT；不得靠名字猜测或按like批量drop。既有其它FK/索引/trigger定义摘要须留存。

采用source_kind NOT NULL DEFAULT ACCOUNT；两列同utf8mb4_0900_as_cs的STORED生成列：ACCOUNT才投影原source_snapshot_id，RULE才投影原source_snapshot_id。单条COPY ALTER中drop精确旧FK，增加两索引/两新精确FK、枚举CHECK和显式IS NULL/IS NOT NULL XOR CHECK。默认RESTRICT，不写CASCADE/SET NULL；CHECK用IS NULL保证不落入SQL UNKNOWN放行。源ID原NOT NULL，所以合法kind一定仅一投影非空。原历史行自动生成ACCOUNT投影，不执行UPDATE回填；原source_snapshot_id、payload/hash、created/sealed、成员和Rule版本字节不改。

新增独立BEFORE UPDATE trigger仅保护source_kind不变；原057 sourceid/hash/sealed/版本/成员所有trigger保留。MySQL禁止trigger的OLD/NEW访问generated列，本候选完全不这样做。API双表查到同UUID必须409，不能隐式偏好旧源；FK本身按source_kind精确核存在/同tenant，但不能证明调用者creator私有或阻止两源偶然同UUID，因此应用还须明确消歧和当前权限。

RuleStore后续显式带source_kind写内部manifest。公开Rule/RuleVersion payload仍原scope_snapshot_id，不添加类型字段；旧manifest读取明确ACCOUNT，RULE只走新可信reader。share/archive不重新冻结；新apply/编辑引用重走原动作与实际当前范围。执行/模拟未来仍重验不可变manifest所有账户，不能以scope receipt当资格。

## 锁序与性能

沿原Rule写路径统一：真实caller/session与目标owner身份/团队当前锁→已有profile/source config→metric clock→account clock→来源snapshot→按UUID批次member/account→rule clock/head/version最终CAS。不要因Rule scope UPDATE引入ruleclock→accountclock反序。UPDATE头可先非锁预读，最后现读重验revision/owner/state，漂移则回滚，不持ruleclock做50k扫描。创建过程两次授权/currentOwner复核，任意批次发现不完整或越权整笔失败。

新候选SELECT直接固定a别名+纯selection_sql，与caller/owner两个独立命名空间的可见性谓词AND组合；不能把targetowner替换current去冒用accounts.read或复用含同名参数导致覆盖。Member全体校验按1000UUID/keyset批次，无N+1；页最多200。新selection/hash engine只收规范行迭代器或有界batch，不自动授权/commit、不动态表名、不得改原API SQL作为未证明优化。

私有成员GET若每页重验50k，250页会重复大量扫描，不能声称50k性能已经达标。可另评审专属visibility proof缓存，必须绑定新scope/actor与owner当前完整范围/accountclock，不能借043仅caller证明跳过owner交集。初版没有可靠证明前保守全量复核，性能待真实250页/并发测量。索引仅候选，不等EXPLAIN或容量通过。

## 维护、原子性与回退

官方依据：

- [MySQL8.4 generated columns](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html)：STORED可索引/FK；限制引用动作；trigger不能OLD/NEW引用生成列。
- [Foreign keys](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)：组合键/NULL/默认RESTRICT，字符集/排序规则匹配。
- [Online DDL operations](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html)：ADD STORED需COPY；不能标INSTANT或LOCK NONE支持。
- [CHECK](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)：生成列可参与CHECK；NULL不等FALSE，显式referential actions与CHECK有限制，候选省略actions采用默认RESTRICT，须真实DDL确认。
- [Atomic DDL](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)：每条支持DDL原子，DDL隐式提交，不是多语句事务升级。

需维护窗口/暂停相关写方，评估COPY临时空间(旧表+新表+索引/日志)、MDL等待、持有长事务、复制延迟、恢复备份和实际耗时。这个候选没有执行部署授权，不能擅自停现预览。应用新写方必须迁移与trigger全部成功后才开启；多条CREATE/ALTER/TRIGGER间中断会留下部分schema，不能盲目重跑或靠ROLLBACK消除。root迁移器需按实际清单确定已完成阶段并核结构，不用IF NOT EXISTS吞掉不匹配结构。

单条ALTER失败时旧FK与旧表应完整保留；前面已成功的新四表仍存在。ALTER成功后trigger创建失败应保持新写方关闭，由维护恢复精确缺项；旧规则是否继续服务须先核完整兼容，不能自动宣告成功。down不提供可自动执行脚本：若存在任何RULE manifest/新scope历史数据，不允许删表或把RULE改ACCOUNT；必须前滚修复或备份恢复。仅在确认新表全空且所有manifest ACCOUNT、原snapshot引用完整、相关写方停用时，可评审反向COPY ALTER(恢复精确旧FK、删新FK/生成列/sourcekind/check/index)、再drop新增保护trigger/四表；多DDL仍非整体原子，原025及057历史字节摘要必须对账。不能把应用代码回滚等同schema已降级。

## 拟独占文件与主线接点（未授权生产修改）

新增`rule_editor_scope_contract.py/store.py/routes.py`及专属tests/tools；小型纯`scope_selection_engine.py`需root分配并审原AccountScopeStore适配，不先占用公共修改。`rule_scope_references.py`的双来源解析、`RuleStore._freeze`内部sourcekind、正式061/应用注册/新MAC/前端由root统一分配。原Rule/MetricProfile DTO与原025store/router不改。

## 真实迁移/业务验证矩阵（全部待执行）

|组|真实准备与断言|边界|
|---|---|---|
|DDL1|带sealed旧ACCOUNT manifest/RuleVersion/成员/历史hash→061；generated投影准确，旧字节摘要全不变、旧trigger定义全保留|核实际旧FK名/列序，非只查表存在|
|DDL2|空表与有数据两种COPY，四表/两生成列/双FK/两索引/XOR/12trigger精确metadata|记录MDL/COPY成本，不宣在线|
|DDL3|ACCOUNT/RULE同tenant存在成功；不存在/跨tenant/坏kind/NULL kind/显式generated非DEFAULT均拒；原sourceid/hash与sourcekind更新拒|新kind保护与原sealed trigger同时生效|
|DDL4|旧ACCOUNT仍保护原snapshot删除，新RULE保护新snapshot；默认RESTRICT；两源同UUID由应用409|不关闭FK或降权限|
|DDL5|错count、非法hash、ready绕过、晚插/改/删成员、event错actor/hash、outbox错snapshot及内容篡改拒|应用hash重算另实测，SQLcount不充当hash证明|
|DDL6|升级途中精确DDL失败/ALTER失败原FK仍在；成功阶段不误称整体回滚；受控无新数据down演练及有RULE数据拒降级|root一次性UUID库，不碰原预览|
|AUTH1|只有rules.create或edit、无accounts/users/monitor，仍真实可用；无原动作403|scope creator-private，另actor及foreign404|
|AUTH2|USER/TEAM_ADMIN显式managed/SUPER+targetowner当前交集；旧owner可留但新增账户越界拒|同Token撤权/停用/团队/目标scope变更立即拒|
|DATA1|IDS1/50000、FILTER含混币种/NULL、50001/重复/缺失/越权拒；完整七列hash/250页全集|不继承Plan500、不截断|
|DATA2|同key同正文旧receipt重放、异body409、同rawkey原账户与Rule各自独立；并发唯一发布|当前读边界保留，不重绑新owner|
|READ1|四档游标绑定session/action/owner/filters/rule版本/clock，成员q与原三字段/五字段保持|全体成员撤权即整页拒，不能只核当前页|
|TX1|outbox1644后snapshot/member/event/outbox+Rule manifest全回滚；成功整笔commit|无广告发送/模拟/平台授权|
|REG1|原025账户4表+权限/creator/原幂等/原规则九API+阶段1八case全部复验|不以新scope通过刷新原容量失败证据|

TeamAI recall本轮查询无命中；以上来自现有代码和官方MySQL8.4手册，不从相似项目推导授权。


## 独立源码冻结检查点（未接公共入口）

- 新`rule_editor_scope_contract.py`的DTO和三个路径已按root批准固定：ScopeContext/ScopeQuery/ScopeWrite，原Scope5/Member3/Page4。`ScopeWrite.canonical`固定HTTP四键规范正文；发布时完整intent额外冻结真实rule_revision。旧成功键匹配原四键正文、校独立列/完整intent hash后重放旧receipt，不拿新If-Match重绑原结果。
- 新`rule_editor_scope_store.py`包含真实SQL候选/IDS与FILTER完整冻结/creator私有成员读取；没有commit、平台调用、账户scope权限回退或HTTP previous。新`scope_selection_engine.py`是七列hash与计数的纯工具，直接沿原MAX_MEMBERS50000，无SQL/callback；原AccountScopeStore尚未迁移使用，不声称共享重构完成。
- UPDATE新key必须当前可编辑状态和当前If-Match。成功scope重放及成员历史读取允许Rule单纯改版或状态变化；仍须当前原动作、Rule可见性、目标owner适用性和双方法定全部成员范围。scope.rule_revision永久保留创建时值仅审计，不能充当当前Rule CAS/模拟/执行许可。cursor绑定当前Rule revision，变版后旧cursor409，重新加载可合法读取。当前目标owner不再可指派时不能借历史previous强行保留。
- scope发布唯一键竞争不对已ready行做no-op UPDATE(会触发不可变guard)，也不预锁不存在unique gap；初探非锁读，INSERT1062仅按精确errno走当前FOR SHARE旧receipt重验，其他DB异常原样传播。实际并发行为仍待主线真实专项，纯测试不替代MySQL锁证明。
- 新router导出`rule_editor_scope_routes.router`，prefix `/api/v1/rules`，须由root先于动态Rule router注册。无需新fixture state（账户来源始终真实SQL/原rules动作）；工具在UPDATE历史用例用既有原Rule的FIXTURE指标样本，因此runner仍须原rules-only显式profile fixture引导，不能生产默认开。
- 新MAC用途固定`RULE_EDITOR_SCOPE_CURSOR_V1`，候选domain RULE_EDITOR_ACCOUNTS_V1与私有成员domain RULE_EDITOR_SCOPE_MEMBERS_V1；root登记凭据白名单。CSRF沿原DIRECTORY_CSRF_V1，不新造登录/会话通道。
- 专属纯测69/69通过0.95s，含真实SQLAlchemy RowMapping、严格输入/四档、1000+1分批、规范七列hash、独立projection/完整intent、当前权限零业务SQL、第二批成员撤权、幂等1062当前读、异常不假成功、游标分域；工具护栏已包含，非实际SQL/HTTP/50k验收。Ruff/format检查通过。最终具体重跑数值以交付消息为准。

真实工具：`tools/rule_editor_scope_checks.py`，导出`RULE_EDITOR_SCOPE_CASES`10个具名case，入口
`run_rule_editor_scope_checks(client,admin,headers,password,cache,database,cases)`；无需新增scanner/cipher/object-root注入。必须当前13306/UUID库、已采用061、原登录/角色/规则/阶段1context静态路由、原rules-only明确指标fixture flag。工具自建原native用户990611、rules.create/edit-only角色、205本人+1foreign真实账户，不依赖Stage1用户/规则。实际包括生成FK/旧trigger元数据、原动作无accounts.read、四档完整205键集、IDS201七列hash、FILTER205全体、SUPER非creator404、游标domain/filter/size/clock、同actor同rawkey与025独立发布、原Rule revision1→2后UPDATE scope原receipt重放/历史读取、末成员撤权拒第一页、CSRF/foreign/1644四表回滚、即时原动作撤销与严格边界。没有测试控制后门/网络mock/平台写；10case不代表完整Rule scope integration或50k容量。

root实际FK验证建议：迁移前按实际057 SHOW CREATE保存旧FK与全部trigger定义/旧manifest及版本/成员hash；核第二匿名FK的列序和目标，非只核约定名字；061后KCU精确核两个生成列的同tenant复合FK、COLUMNS的STORED+表达式和字符集/排序、两个索引列序及默认RESTRICT，并核旧sourceid/hash/payload/成员字节全部不变。必须另有真实DML负例(坏kind/跨tenant/缺源、sourcekind update、显式写generated、FK阻止源删除)及部分DDL失败/维护窗口验证。现10工具仅带精确元数据检查，不冒称这些迁移负例全部已实现或通过。

## 061主线已有有限迁移证据

主线已采用正式061并完成空schema实际DDL；实际精确核对旧057 `orbit_rule_scope_manifest_ibfk_2` 与旧三个manifest trigger。另独立自建SQL历史探针`tools/rule_scope_schema_probe.py --with-history`已PASS，证据`evidence/python-rule-scope061-sealed-manifest.json`：原025 snapshot/member与057 sealed manifest/member四表的原列逐项未变，ACCOUNT生成列映射准确，旧sealed修改/删除三次均精确1644。该样本没有RuleVersion历史，不代表所有历史升级/维护窗口/容量/回退全部通过；新API/新RULE源消费实际验证另排。

## 双来源Rule消费独立源码检查点

已在owned `rule_scope_references.py` 与`rule_store.py`接内部双来源，不改原公开Rule15字段。新save在同一事务先生成实际CREATE RuleID，传给capture与最终persist，防止预检查绑定ID和写入manifest ID漂移。capture固定ACCOUNT→RULE当前读，碰撞409；RULE snapshot FOR UPDATE串行首次绑定，在同snapshot锁下用精确来源索引查其它Rule/当前Rule manifest。

- ACCOUNT新source沿原creator/授权代际/七列完整hash/双方全部账户范围；不扩大025原读取权限。
- RULE新source须creator、原action、实际目标owner/team、双当前授权指纹、完整冻结intent规范hash和独立列一致、原七列根与所有成员当前双方交集。CREATE未绑定scope只可新建一次Rule；已绑定到其它Rule即409。未绑定CREATE scope不能拿来编辑一个现存Rule。
- UPDATE首次消费必须source.action UPDATE、scope.rule_id精确当前Rule，scope.rule_revision等于本次save expected（拒bool/缺失）。source已属于同Rule后原revision仅历史，保存仍当前CAS与完整范围，不把旧scope revision当当前Rule版本。
- 同Rule已公开manifest协作复用不要求当前editor等于原scope creator，也不返回私有scope正文；沿原公开Rule权限与完整当前双方成员重验，只增加双来源消歧/source_kind/精确Rule绑定/原来源hash核对。原私有scope API仍creator-only。
- 成功原Rule幂等回执仍在新source核验之前按原动作/当前Rule可见性返回；不因后来source变化而重新绑定。新body/新key保存不能借同scope复用分支绕过UUID碰撞。
- 原锁序保留：caller/owner→profile config/metric clock→account clock→来源snapshot→manifest/member/account→rule clock/head最终CAS；不是新引入ruleclock→accountclock反序。

定向纯测`test_rule_access_references.py`+`test_rule_store.py`111/111 PASS2.78s，Ruff/format PASS。这些是协议/内存SQL替身，不是实际双连接竞争或新RULE保存验收。主线原40档即便通过（其UPDATE业务源仍ACCOUNT）也不能替代新RULE source→原POST/PUT→manifest完整实际链。后续需实际首次CREATE绑定双连接、跨Rule拒绝、首次UPDATE revision/target负例、同Rule协作复用、全体权限撤回与outbox1644整事务回滚。

主线已将061逆查索引延伸为(tenant,rule_source_snapshot_id,rule_id)，保留外键前缀并支持按来源/目标排除其它Rule；正式061与草案字节一致，有限sealed历史探针已按最终SQL复验。该索引仍没有大历史EXPLAIN或容量证据，不冒称大历史性能已通过。

主线through061原40组实际SQL/HTTP已PASS，证据`evidence/python-rule-editor-scopes061-http.json`：原22、编辑候选8、新scope10均完整执行，含只授原rules动作、四档完整205账户、IDS/FILTER七列根、当前权限/末成员撤权、跨actor私有读取、原键与不同If-Match、1644四表整笔回滚。仍不是新RULE source原保存、五万新scope容量或全编辑页浏览器验收；新consumer八组在制，不把该40结果抬为整模块完成。
