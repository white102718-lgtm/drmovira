# Python最小引用资料与渠道交付记录

本文件属于实施文档第七节B线，不替代2342项严格台账。当前记录代码、专项验证范围和待验项；页面存在、单测和类型检查不等于模块验收通过。

## 首个闭环和入口

|入口|已实现操作|状态与限制|
|---|---|---|
|系统管理→字典与引用资料 `/orbit/system/dictionaries`|PRODUCT/BUSINESS_AGENT/VENDOR最小JSON模板下载；1—500行预检；逐行错误；当前变更前后差异；15分钟预览；显式原子提交；目录候选续页|需system菜单+维护动作+当前数据范围；不会恢复完整产品/总代/户商CRUD。当前14组业务HTTP+8组维护范围HTTP均已实际通过；合跑随后因账户专项失败未到浏览器，界面仍待复验|
|渠道管理 `/orbit/channels`|名称/渠道ID、产品、状态筛选；游标分页；新增、详情抽屉、编辑、分配、停用弹窗|原生Element Plus；保留渠道全部业务字段；真实全权限与容量验收尚需专项证据|

闭环顺序：先导入总代，再导入产品及允许总代集合，再为同团队有效拥有者创建渠道。无引用资料时提示导入；不得用自由文本替代product_id/agent_id。预检状态REJECTED不写目录，VALIDATED也不等于已提交；只有COMMITTED表示本地目录事务成功，不代表任何广告平台写入。

## 字段、状态和关键约束

- 引用资料包括kind、稳定UUID、名称、availability、owner_team_id、1—500名data_owner_user_ids、source_key；PRODUCT额外1—500个allowed_agent_ids。名称与来源键按Unicode NFC及文本长度校验，控制符拒绝。来源键同租户同类别唯一，已有UUID不能更换来源键，不能通过来源键将旧对象改绑新UUID。
- 产品关联总代必须已存在、同租户、同团队、AVAILABLE，且对全部产品拥有者可用。失效资料保留显示，禁止新选；不自动将本次导入未出现的资料置失效，不修改历史计划与事实快照。
- 渠道包含code、name、product_id、agent_id、type、media、url、status、ownership、业务UUID、revision、创建/更新UTC时间。code同租户唯一；链接必须HTTPS、无凭据、参数编码有效且字面地址非私网；允许合法HTTPS端口、公网IPv6和SPA片段，不照搬OIDC授权地址的443限制。保存链接不追加参数、不探测外网、不改写已有计划落地页。
- 渠道编辑/分配/停用必须If-Match、CSRF和Idempotency-Key。普通用户不能扩大拥有者集合；TEAM_ADMIN仅可写显式管理团队；所有拥有者必须同团队、启用且已激活。拥有者变化不能靠edit绕过channels.assign。历史包绑定通过product_locked保护产品变更，提示新建渠道；历史包迁移数据接入仍待完整迁移验收。
- 停用保留历史。已保存且没有更换/扩大归属的失效关联可继续解释与保留；新增关联及重新分配须重新核验。任务执行前复核渠道可用性由后续任务链路实施，当前不能宣称已完成。

## 服务端接口与事务

合同接口为GET `/reference-catalogs/{kind}`；POST `/reference-catalog-imports`；GET `/reference-catalog-imports/{id}`；POST `/{id}/commit`；渠道列表/创建/详情/编辑/owners/archive。

为实现界面增加的技术扩展：GET `/reference-catalog-imports/capabilities`提供维护CSRF与当前目录版本，GET `/{id}/differences`展示当前可审查差异；GET `/channels/capabilities`、`/channels/ownership-options`、`/{id}/edit-context`分别提供当前动作、可分配人员及历史绑定解释；GET `/channels/display-labels?ids=...`按当前可见渠道批量回显产品/总代/团队/拥有者名称，每次最多200个UUID，两次集合SQL，不按行请求。这些接口不替代原合同，均需当前会话、租户与动作门禁。

预览输入上限2MiB、最多500项，错误行按0开始的row保存、界面按1开始显示。预检读取真实目录，但不修改它。提交锁租户目录水位，重新校验目录版本、预览状态/版本/期限、当前角色和全部引用；目录、拥有者/产品总代关联、预览状态、版本、幂等结果、只追加事件与outbox在同一MySQL事务提交。任何事件写入失败整批回滚。两个基于相同目录版本的预览只能一个提交成功；数据库已回滚的死锁/锁等待最多重试整个事务3次，无外部副作用重试。

## 查询与容量设计

|访问路径|索引/分页及水位|仍需验证|
|---|---|---|
|产品/总代/户商候选|`(tenant_id,kind,id)`或`(tenant_id,kind,owner_team_id,id)`；拥有者关系覆盖索引`(tenant_id,user_id,reference_id)`；20/50/100/200键集分页；签名游标绑定actor/tenant/数据角色/团队/显式管理团队/筛选/kind/scope_version/catalog_revision|真实EXPLAIN ANALYZE、目录大规模分布与20并发P95；不能仅凭LIMIT判定性能通过|
|总代候选|必须product_id，产品先做可见性校验，再通过`(tenant_id,product_id,agent_id)`集合约束；owner_user_id叠加目标拥有者可用交集|全权限矩阵、失效产品与所有历史迁移案例|
|渠道列表|按tenant+UUID续页；状态、团队、产品分别有复合索引；拥有者关系`(tenant_id,user_id,channel_id)`；签名游标绑定目录scope及channel_revision|名称/渠道ID的INSTR包含匹配不是前缀索引检索，大量候选可能慢；需按真实查询分布测量，必要时单独搜索索引，不能声称已经优化通过|
|预检与提交|已存在资料、总代和拥有者去重批量查，每批最多500；资料executemany、集合删除、拥有者及总代关系每500条批量写入；不逐行无界读取|500行×500拥有者极限在2MiB下的有效组合、峰值内存、事务锁等待与失败恢复尚未容量实测|
|差异展示|单预览最多500行，当前目录版本变化时提交409；展示不隐式提交|500行大型差异的前端滚动/可访问性及内存验证待专项|
|拥有者候选|最多200项，按业务UUID续页，当前权限范围过滤|技术扩展after目前不表示冻结批量选择快照；不能将此候选游标当账户跨页范围冻结合同|

数据库迁移009中全部表/字段/索引有中文COMMENT。主事务数据与关系表分开，资料快照JSON有界；查询权限不扫描JSON数组。当前没有归档/清理任务调度，导入与幂等保留期、outbox消费者以及新租户初始化目录clock仍需统一生命周期方案后接入。没有执行真实50k/1m容量压测。

## 验证清单与证据边界

- [x] 60个纯合同单测：字段、Unicode、归属集合、批量上限、HTTPS、数据范围以及结构/类型400、字段值422与JSON Pointer；命令`.venv/Scripts/python.exe -m pytest python/tests/test_reference_channel_contract.py -q`，2026-11-08本地结果60 PASS。纯合同单测不能替代真实HTTP证据。
- [x] 独立Python文件及专项工具Ruff检查/格式通过。
- [x] 两API客户端、两页面及专属前端测试Prettier/vue-tsc通过；8个客户端单测通过，涵盖正文、CAS、幂等键、未知网络结果及错误语义。
- [x] `tools/reference_channel_checks.py`的12组真实HTTP/MySQL验证：预检不修改目录、原子提交/重放、来源绑定、候选、并发目录版本、到期及引用复验、审计失败回滚、渠道全字段、历史绑定、分配/停用、游标、即时撤权。2026-11-08 12:05:43北京时间开始的隔离运行整体161/161 PASS，包含B线12组；命令`.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 11`，当前主收据见[evidence/python-framework-integration.json](evidence/python-framework-integration.json)，历史归档由主任务维护。该结果不能替代下列完整验收。
- [x] `tests/e2e/orbit-python-channels.spec.ts`三视口真实界面闭环，覆盖重复行拒绝、修正预检、差异/提交、HTTP链接字段错误、创建/详情/编辑/分配/停用及弹窗边界。主任务独立复验26488结果为171后台组与1浏览器汇总组通过，三个视口3/3实际通过，无跳过、无重试；后续合同分类源码改动仍需相应真实HTTP复验，不继承为最新整模块验收。
- [x] 新增8组真实维护范围矩阵已在合跑通过：USER本人不扩集合、TEAM_ADMIN本人/明确团队、owner目标与产品交集、预览/差异/提交/重放撤范围、即时撤维护动作、拥有者移属/CAS、三身份另一租户对象不可见。该次总体合跑在后续素材断言失败、未到浏览器，不能将它称整体PASS。
- [ ] 全产品的两租户/两团队/普通用户/团队管理员/功能角色并集、全部跨模块操作矩阵。
- [x] 新增2组真实重启用/HTTPS保留片段及端口、渠道自身21项分页水位/名称回显专项已通过；对应本线共14+8=22组真实HTTP。在整体合跑中，B22和素材12均过，后续账户GET批次错误导致整体FAIL，浏览器未执行；不改变整体失败记录。
- [ ] 历史产品/总代/户商/包约束迁移、历史计划快照对账及跨模块账户/任务执行链路。
- [ ] 全容量、并发、归档与恢复验收；外部平台实测不在本闭环内。

## 原PRD尚待补齐的明确差异

|原要求/验收项|当前实现或证据|未覆盖部分|
|---|---|---|
|AT-CHN-01全字段与切产品联动|全字段写入/读取、同租户code唯一及格式有真实HTTP；前端切产品会清空总代。12:10:33前已修正表单type默认APP、列表/详情空name回退code，类型和相关单测通过，等待当前三视口实测|完整跨租户/未分配资料矩阵尚未执行；下游命名/报表展示回退依赖后续模块，未继承当前页面结果|
|AT-CHN-02目录连续性|候选不依赖已删products菜单；HTTP验证产品允许总代及product_locked拒绝变更|失效历史关联全组合和真实旧包约束迁移尚未完成；已补批量可读名称映射，真实HTTP验证当前可见21个渠道一次回显及不存在/重复ID边界；普通拥有者候选以200项有界读取，不能把未加载名称当资料不存在|
|AT-CHN-03停用与链接|HTTPS验证、停用保留链接/产品/归属已真实HTTP验证|DISABLED→ENABLED已补强制重新检查资料AVAILABLE与产品总代关系，真实专项已验证拒绝失效产品/已解除的总代关系，恢复合法关联后才可启用；未发送任务拦截、既有投放落地页比对及未知渠道统计依赖后续任务/报表模块，未完成|
|跨页列表|引用候选页20/50/100/200及变目录/筛选拒绝旧游标有真实HTTP|渠道自身21项多页无重复/遗漏、相同watermark及变更拒旧游标已实际通过；完整压力矩阵、候选500拥有者界面选择、多次加载后的编辑与失效竞态尚待专项|
|异常恢复|审计事件失败整批回滚、相同幂等键重放、同目录并发冲突已真实HTTP|浏览器网络未知结果重试、失效CSRF/会话/版本后的明确恢复入口须进一步测试；不能用客户端8单测替代真实断网|
|FR-SYS-引用目录维护|已去除额外SUPER门禁；增加USER本人不扩集合、TEAM_ADMIN本人/显式管理团队分支，预览/差异/提交/重放逐次复核，owner_user_id叠加产品与总代目标交集|新8组真实多身份矩阵已实际通过，新增字段/标签/分页2组也已通过，浏览器仍未实际走完；不可误记为完整合同通过|
|生命周期/大数据量|全部字段COMMENT、覆盖索引、批量查询与有界事务已写；显式迁移001—011已通过|新租户clock初始化、导入/幂等归档、outbox消费、执行计划、容量/并发指标、升级回退对账都未验证|

当前本模块仍为在制状态；22组HTTP和三视口浏览器通过不勾选整个模块验收，各项差异仍需继续修正。新增两组错误分类真实HTTP待主线队列验证。

## 下一批：维护权限与数据范围矩阵（8组真实专项已通过）

原覆盖合同未要求维护者必须SUPER_ADMIN。移除额外门禁前，必须同时增加下面的逐次复验，不能单独删除参数后声称权限正确。

|身份及条件|正例|反例|
|---|---|---|
|USER有system菜单与字典维护动作|本人团队、本人拥有者的新资料；当前可读旧资料保留原归属的更新|新增时加入他人或其他团队403；旧资料扩大拥有者403；没有维护动作拒绝；不可读预览/差异404|
|TEAM_ADMIN有维护动作并显式管理团队B|团队B内启用拥有者的最小资料批量导入、当前资料查询/差异/提交|只有数据角色但未授权团队B不得扩大范围；管理团队B不能写团队C；自己的个人范围与明确团队管理范围须分别处理|
|SUPER_ADMIN有维护动作|当前可信租户全部合法资料|其他租户对象仍不可见；不靠浏览器传tenant扩大范围；无维护动作即时拒绝|
|owner_user_id候选|指定本人，或显式管理同团队拥有者；返回调用者与目标拥有者可见交集|TEAM_ADMIN指定本人不应额外要求“管理自己”；选他人必须授权且有效。总代查询的product也必须对目标owner可用，不能只检验agent拥有者|
|预检后的撤权/移属|无变化的冻结输入正常提交，同键保持一次结果|撤维护动作403；撤管理团队或预览超当前范围404；拥有者移组/停用重新校验失败；相同幂等键也不能绕过当前范围|
|并发/CAS|当前版本一次提交|旧目录版本/旧预览版本409，无目录/审计/幂等部分提交；跨范围不能用CAS错误探测对象存在|

`readable()`只表示读取，不能直接作为更新/扩展拥有者授权；已拆出`assert_write_ownership()`提供严格写门禁。GET预览与差异、commit、预检重放/提交重放已对完整冻结输入的当前团队与拥有者范围检查；任意行不可见时不返回其他行的计数或差异。真实专项由`tools/reference_channel_scope_checks.py`提供8个固定场景，接入同一隔离队列；本节8组已通过，但不包含全模块全部字段/弹窗/外部环境和容量验收。

首次三视口浏览器专项在选择“类别”时全部失败：测试定位到Element Plus的readonly输入，placeholder覆盖该输入，未触发业务预检。已保留失败，由用例改点可见`.el-select__wrapper`（没有force/跳过断言/模拟成功）。后续合跑中desktop-1440与wide-1920已实际走完整个UI闭环并PASS；mobile-390在渠道页面标题定位时命中隐藏侧栏menu-title而失败，不能将两个桌面通过冒充三视口通过。已把两个页面标题限定到主内容卡片header，保持全部业务断言，等待独立channels三视口复验。原失败与桌面证据保留于主任务浏览器产物，不改写为整体PASS。

## 错误分类合同修复（源码和单测完成，真实HTTP待验证）

原API_SEMANTICS明确结构/类型400、字段边界422、未知字段400 UNKNOWN_FIELD，并用JSON Pointer。此前两个顶层Pydantic解析器错误地把部分类型错误变成422且缺少准确Pointer；现已由统一schema_error、整包行结构预检和嵌套归属检查修正，60个纯合同单测通过。下面登记实际修复口径，真实HTTP仍待主线验证。

|输入情况|应有响应|最小实现|
|---|---|---|
|非法JSON、重复JSON键、非对象根、字段缺失、对象/数组/标量类型不符|400 INVALID_STRUCTURE；不创建预览|保留严格JSON解析，统一将Pydantic结构/类型错误归400；首个错误loc转换成Pointer，不回显input/context|
|未知字段，包括嵌套归属及资料行未知属性|400 UNKNOWN_FIELD；不创建预览|精确指向如`/ownership/unexpected`或`/items/2/unexpected`；`~`与`/`按RFC6901转义|
|顶层kind非法、revision负数/越界、items数量0或501|422字段错误；不创建预览|边界与已知枚举错误区别于类型错误；bool不是int，false不能当版本0|
|资料行符合JSON结构，但UUID/长度/枚举值、重复ID/source、拥有者存在性、关联关系等不合法|201 REJECTED并逐行issues；目录不修改|先检整包结构，再做行值/业务预检。行issues保持合同row/code/message三字段，不擅自增加pointer破坏additionalProperties=false|
|资料行不是对象、name为数字、拥有者列表含数字等结构/类型错误|400对应`/items/{index}/...`；不创建预览|先在parse_import阶段验证ReferenceInput的对象结构与字段类型；不能将整个JSON结构错误藏进业务REJECTED|
|权限、可见范围、版本、过期|继续403/404/409/410，不受分类修复放宽|当前22组真实业务/范围专项保持断言，不能为通过而删除|

原首轮HTTP工具把行name=42作为REJECTED示例，按上述原合同应改为“字符串为空”等真正字段值行错误，并另增加name数字400及Pointer/无预览断言。该修正是纠正测试与实现的合同分类，不应减少原逐行错误、原子性和权限测试。

修改仅涉及B专属`reference_contract.py`、`channel_contract.py`及专属单测/HTTP工具；公共错误中间件已有`OrbitError.pointer → field_errors.path`能力，无需修改公共认证/中间件。已新增两组真实HTTP检查定义：`pythonReferenceChannelStructureTypesUnknownFieldsAndJsonPointers`验证顶层/嵌套类型与未知字段400及准确Pointer/无预览写入；`pythonReferenceRowValueIssuesRemainRejectedAndAtomic`验证合法结构批次多行值/重复/关联错误201 REJECTED且目录不变。固定专项清单由14增至16组，范围矩阵8组不变；当前源码已冻结交主线排队，尚未把这两组标为实际通过。

## 严格台账细项证据审查（建议，未改总台账）

已只读核对`progress.json`真实ID。下面仅为可独立结清的返回字段候选，建议主任务核对最新源码hash收据后回填开发DONE/测试PASS；验收状态仍由独立验收决定，不从字段通过推导整API/模块/容量通过。

|稳定ID|实现源码|具体真实case/实际断言|界限|
|---|---|---|---|
|`SCHEMA-ReferenceImportResult.state`|`reference_store.py` preview/get/commit|`pythonReferencePreviewRowIssuesAndNoCatalogMutation` REJECTED；`pythonReferenceAtomicCommitReplayAndSourceIdentity` VALIDATED→COMMITTED；`pythonReferenceExpiryAndCurrentOwnerRevalidation` GET EXPIRED；非法提交409、到期410真实断言|结清四状态返回及转换字段，不结清所有导入字段/500行容量|
|`SCHEMA-ReferenceImportResult.revision`|`reference_store.py` preview/commit|`pythonReferenceAtomicCommitReplayAndSourceIdentity` 预览1、同键重放不重复提交；`pythonReferenceOwnerTransferAndCasLeaveNoPartialWrites` 错版本99拒绝、当前版本成功；审计失败预览仍VALIDATED/1|仅正整数版本及CAS返回，不结清预检完整正文/错误分类|
|`SCHEMA-ReferencePage.next_cursor`|`reference_store.py` list，`directory_tokens.py`|`pythonReferenceAndChannelKeysetScopeAndWatermark` 真实20项首游标、后续页无重复，换kind/改目录拒旧游标；签名只含范围散列、版本及续页UUID|仅字符串/空值与当前专项续页，不算50k目录/权限全部组合|
|`SCHEMA-ChannelPage.next_cursor`|`channel_store.py` list|`pythonChannelOwnKeysetWatermarkAndBatchDisplayLabels` 21条真实渠道20+1、后页null、无重复遗漏、变筛选/实际修改拒旧游标|不把21条当容量压测|
|`SCHEMA-ChannelPage.data_as_of`|`reference_store.py` utc_text，`channel_store.py` list|同一真实21渠道续页case明确断言首/次页相同watermark；UTC时间由服务端生成并冻结进签名游标|仅列表水位字段，不代替统计事实as_of/业务日或容量验收|
|`SCHEMA-Channel.id`|`channel_store.py` save/public_channel，`channel_routes.py`|`pythonChannelCreateAllFieldsReplayUniqueAndHttps` 真实新建业务UUID、同键同对象、按ID GET与创建完整对象相等；三视口UI创建后详情使用同对象|不是外部Meta对象ID，无任何平台写入证明|
|`SCHEMA-Channel.revision`|`channel_store.py` save|`pythonChannelEditCasHistoricalBindingAndReferences` 1→2与旧CAS409；`pythonChannelAssignmentAndArchivePreserveHistory` 2→3→4及同键重放；审计失败保持原版本；重启用成功继续递增|只结清对象版本；不结清整个owners/archive权限矩阵|

以下保持IN_PROGRESS，不按“已实现页面”直接完成：`FR-CHN-01/02/03`、`CHN-01`至`CHN-09`、`FIELD-B-渠道.*`业务字段、全部十个`API-*Channel* / API-orbit*Reference*`入口、`SCHEMA-SharedOwnership.*`及ReferenceInput的1—500拥有者边界。理由包括完整逐字段边界/组合还未全部实测，来源/历史快照、任务执行前失效复验、不可见渠道详情/编辑/分配完整多租户矩阵、两端网络未知恢复、来源/历史UI、500拥有者界面、容量和生命周期仍有缺口。

`API-listChannel`尤其不能因21条分页通过即结清：所有page_size和日期/组合边界、无权用户及所有过滤组合仍需完整合同验收。`API-orbitPreviewReferenceImport`的400/422/行REJECTED与Pointer新两组须在真实HTTP通过后才可算该部分通过；60个纯单测不能代替该证据。技术扩展display-labels无原始稳定ID，需主任务登记扩展后追踪，不擅自塞入不存在的ID。


### 第七节渠道及引用目录容量（2026-11-09 02:44，北京时间）

显式真实容量组合41/41、68.46秒通过（原人员/目录/渠道37+新容量3+退出1）。SQL技术样本各装载50000渠道和VENDOR，真实关系表、原ChannelWrite/ReferenceRecord校验、中文长名称及同源产品/总代；装载23.88秒。渠道50000条/250页4.03秒，目录含既有25条共50025条/251页4.89秒，全页按原排序UUID逐项对账且水位不变，保留有序集合hash。四档20/50/100/200各端点200次、20并发，共1600次真实HTTP，P95渠道0.349/0.244/0.283/0.517秒，目录0.284/0.228/0.426/0.319秒，全部满足原一秒目标。实际EXPLAIN ANALYZE显示tenant/ID主键范围与拥有者覆盖索引；RSS前后257716224→274898944字节，仅采样不冒称峰值或泄漏证明。装载后缓存可能已热，没有生产冷启动结论。

证据evidence/python-reference-channel-capacity053-http.json及python-reference-channel-capacity053-report.json。保留首轮37通过/1失败/3未运行（工具把JSON字符串而非UTF8原请求字节传解析器）和第二轮38通过/1失败/2未运行（工具误把目录value.id当渠道顶层id）；分别修工具，原完整集合/四档/P95断言不删。工具护栏9项纯测通过，另一次首次collection缺模块导入已修为自含percentile。生产领域代码未因此修改，容量不是所有目录筛选组合、真实数据来源或整产品验收。

前一检查点已实际双仓推送：后端c56355e0，前端f90f711。3544固定纯测后仅删除hash链测试文件尾多余空行，原9项重新通过0.57秒；不把旧hash清单重写为新格式源码的重新全验。当前A真实空/5000身份库存排队、B结果构建、C扫描器/054 SQL工具继续，严格2342台账保持29开发/29测试/0验收。
