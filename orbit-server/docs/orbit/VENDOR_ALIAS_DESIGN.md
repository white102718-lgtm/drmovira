# 户商代称独立扩展设计

状态：设计经主线批准，独立017及vendor_alias_*正在实现，尚未注册路由、执行迁移或宣称功能完成。既有引用目录、渠道及账户受测源码保持冻结。本文件明确供账户线接入的数据源，禁止以name、名称前30字符、source_key或任何Meta字段推测代称。

## 来源与兼容边界

原合同`data/ORBIT_Codex开发PRD/reference/03_原合同保留章节.md`要求：当前账户展示同步当前户商代称，历史日志保留快照。原Account.vendor_alias严格为null或1—30字符字符串；现有ReferenceInput/ReferenceValue的name上限255，且additionalProperties=false。故不能向原引用行/原value_json增加alias，也不能将两字段解释为同义。

本扩展不恢复户商一级菜单。维护入口复用系统引用目录页的VENDOR资料项，独立“维护代称”弹窗；业务资料导入的旧JSON、原响应及原路由保持兼容。户商完整名称继续由原name提供，代称另存。

唯一性证据核对：`contracts/字段逐项对照.json:1685`的alias项仅记“必填：是、约束：1至30字符、逻辑：账户所属户商动态显示该值”，没有租户唯一约束；`reference/03_原合同保留章节.md:32`要求当前关联/历史快照，`:441`说明内部来源，不要求唯一。`contracts/openapi-current.json:36297`仅定义Account.vendor_alias的null或1—30字符；对data目录md/html/json全文检索“代称…唯一/唯一…代称/户商…唯一”无命中。基于这些具体原始条目，不添加alias唯一索引；保持vendor_id唯一关联，并以真实专项验证两个VENDOR可保存相同代称。此结论不推导联系人、账号或其他字段是否唯一。

## 数据结构：017_vendor_alias.sql

新增`orbit_vendor_alias`，无历史数据推算或回填：

|字段|类型/约束|语义|
|---|---|---|
|tenant_id|CHAR(36)，复合主键|来自可信会话租户，不接受浏览器指定|
|vendor_id|CHAR(36)，复合主键；FK指向orbit_reference_record(tenant_id,id)|对应现有VENDOR稳定UUID，服务端再次检查kind|
|alias|VARCHAR(30) NULL|人工维护的真实代称；null表示尚未设置或显式清除，不使用空串|
|revision|BIGINT，2—9007199254740991|独立代称CAS版本，首次实际维护为2，此后递增|
|updated_at|DATETIME(3)|最后一次实际维护UTC时间|
|updated_by|BIGINT|实际操作者原若依ID，只用于审计，不向候选批量接口泄露|

全部表、字段、索引有中文COMMENT。复合主键同时支持当前账户页最多200个vendor_id的集合查询；不按alias全表搜索，不建立无需求的唯一约束（不同户商可使用相同代称）。FK不能独自约束kind，写事务必须核验当前VENDOR行。

没有alias物理行时，VENDOR仍是已存在的逻辑资源，GET返回`alias:null, revision:1, updated_at:null`，其中1明确为“未维护的基线版本”，不是伪造维护记录。首次PUT必须If-Match:"1"并写真实行revision2；锁住租户目录clock使并发首次写只能一个成功。显式清除保留物理行与递增版本，不能删行重置版本。此选择复用现有正整数If-Match合同，不为本扩展修改公共边界以允许版本0。

## 独立接口

|接口|门禁与输入|响应及约束|
|---|---|---|
|GET /api/v1/vendor-aliases/capabilities|当前system页+system.dictionaries.manage，或accounts.read；维护布尔值仍单独授权|csrf_token、can_manage；无全目录明文或凭据|
|GET /api/v1/vendor-aliases/{vendor_id}|accounts.read或维护分支，叠加当前VENDOR可见范围|`{vendor_id,alias,revision,updated_at,catalog_revision}`；别租户/不可见/非VENDOR统一404|
|GET /api/v1/vendor-aliases?ids=UUID,...|同上；1—200个不重复UUID；禁止未知/重复query参数|`{items:[{vendor_id,alias,revision,updated_at}],catalog_revision}`；仅返回当前可见VENDOR，缺alias的可见项明确null；不可见项省略，不泄露其是否存在|
|PUT /api/v1/vendor-aliases/{vendor_id}|system页+system.dictionaries.manage，并叠加VENDOR读取和严格写范围；CSRF、Idempotency-Key、If-Match必需|仅`{alias:string|null,reason:string}`，200返回同单项GET结构；不接受tenant/owner/name/source/Meta字段|

UUID和JSON结构类型400、未知字段400 UNKNOWN_FIELD、文本值/长度边界422、无动作403、不可见404、旧版本/幂等冲突409。alias字符串先NFC及首尾空白规范化，再按Unicode码点验证1—30；不截断、不接受空串或纯空白，不允许控制字符。null是显式清除。reason按既有1000字符中文理由边界处理，必需且非空。所有错误沿用准确JSON Pointer，不回显输入或Pydantic上下文。GET不返回updated_by。

维护授权不能仅检查可读：USER仅可维护完全属于本人的VENDOR（owner_team_id=本人当前团队，data_owner_user_ids恰为本人）；TEAM_ADMIN可维护明确管理团队或自己的上述个人VENDOR；SUPER_ADMIN仅当前可信租户。不能因为某资料包含本人而允许修改共享资料代称影响其他拥有者。复用`assert_write_ownership`时以previous=None检验此严格目标，不把原有共享集合作为普通用户保留写入的豁免。读范围继续按readable当前显式拥有者/管理团队。

## 写事务、版本与审计

1. 按当前会话授权维护动作与可信租户，验证CSRF；锁当前租户orbit_reference_clock，与原导入保持相同锁顺序。
2. 读取并锁VENDOR；复验当前kind、可见性、严格维护范围。停用VENDOR可维护历史展示代称，不因此恢复其导入/新引用能力。
3. 幂等意图hash包含独立资源类型VENDOR_ALIAS、vendor_id、expected alias revision、规范alias和reason；复用现有受控幂等表。命中成功键时仍先复验当前动作和VENDOR范围，不能用旧响应越权读取。
4. 锁独立alias行；缺行逻辑版本1。比对CAS。alias值没有变化时为明确no-op：包括null→null，不建alias行、不改版本/更新时间/目录水位、不伪造编辑事件；仅保存幂等响应，以便未知网络结果重放。实际变化先校验alias及目录版本上限，再写入revision+1。
5. 目录clock.revision递增，使现有引用候选游标/预检基线过期；channel_revision不变，渠道没有户商别名依赖。原ReferenceRecord.revision和value_json不修改。
6. 在同事务写`orbit_reference_event(resource_type=VENDOR_ALIAS,resource_id=vendor_id,revision=alias revision)`，含前后hash、操作者、原因、请求ID和catalog revision；幂等响应同时保存。事件/outbox失败整个事务回滚，包括别名、时钟与键。死锁沿用现有有界整事务重试，无外部平台副作用。

事件现有resource_type容量24足够VENDOR_ALIAS；新事件类型由主线确认扩展登记。原参考资料导入不会删除/改写alias行，但导入改变VENDOR范围后读写必须即时复核。无硬删除入口，避免孤立代称与历史引用丢失。

## 提供账户线的内部依赖

`vendor_alias_store.resolve_vendor_aliases(session, context, identifiers)`返回当前可见VENDOR UUID到真实alias（string或null）的映射；对不可见/不存在/类别不符项不返回。每批最多200，去重集合SQL，不允许每账户请求一次。context必须来自当前accounts.read或维护授权，不能调用者传造tenant/owner。账户页已有合法账户范围不能自动授予不可见VENDOR代称；不可见继续null，并沿现有缺失原因解释。

当前账户列表/详情在同请求事务内批量关联此表，不使用导入时别名快照充当当前值，不以账户行revision更改来同步名称。新别名变化使下一次账户请求展示新值；账户游标是否绑定catalog revision由账户线审查，若原游标不冻结展示字段，应明确该字段是实时标签，不能修改分页成员或历史数值。

账户导入提交、任务执行、操作日志的历史快照在实际业务事务点复制当时真实alias和可追溯alias_revision；未知保持null。历史快照独立字段由对应模块拥有者接入，不反向批量UPDATE旧审计/旧任务。不能在此独立扩展中擅改Account原响应增加alias_revision；如需要追溯，放现有内部快照结构或登记技术扩展。

## 实施与验收顺序

- 当前仅交付此设计；确认后新增017和独立vendor_alias_contract/store/routes，暂不注册，不改冻结reference_*。
- 纯测试：NFC前后30/31码点、空/纯空白/null、控制符/未知字段/类型/Pointer、严格维护范围。
- 主线排队真实MySQL/HTTP：未设置null基线、首次CAS并发一次成功、修改/清除/同值理由事件、旧CAS/同键异意图、撤动作/撤团队重放、两租户隐藏、USER共享资料不得维护、目录游标与预览失效、审计失败全回滚、200个集合读取无泄漏。
- 账户线随后接当前实时别名及历史冻结，验证变更后当前更新而旧日志不变；前端维护弹窗三视口另验。只完成独立别名接口不等于原户商代称字段验收，更不等于账户整模块通过。

## 当前实施证据与未结清字段

独立后端017、vendor_alias_contract/store/routes已经实现。主线回执`evidence/python-vendor-alias-http.json`记录22/22实际通过，其中8组为本扩展真实MySQL/HTTP：无状态GET和null no-op、NFC/CAS/幂等及目录水位、同值/清除/重复代称允许、结构/边界、审计失败全回滚、并发首次写仅一成功、USER共享只读/明确管理范围、撤权重放与真实另一租户VENDOR不可见。30纯测试不充当上述真实证据。

前端当前完整最小入口为`/orbit/system/dictionaries`选择“户商”，现有ReferenceCatalog仅条件嵌入独立`VendorAliases.vue`，新增当前代称表及“维护户商代称”弹窗。可见名称与真实代称分别显示，未知不从名称填充；维护支持NFC 1—30码点、原因、显式清除、错误/冲突后重新读取、未知网络结果冻结正文并以原键重试。后端动作限制不由页面猜测；无维护动作时仅显示当前读取。

7客户端测试与3个真实ElementPlus挂载测试通过，整体vue-tsc和专属Prettier检查通过。挂载专项首次发现alias输入显式disabled=false覆盖父form禁用，导致网络未知时仍可编辑；修复为叠加clear/busy/uncertain/conflict并复验。真实浏览器定义`orbit-python-vendor-alias.spec.ts`已交主线排队，尚不能勾选三视口通过。

`SCHEMA-Account.vendor_alias`以及`FIELD-*`中原账户“所属户商代称”仍不能仅因独立别名接口通过而结清：账户线还须接入每次请求批量实时读取，验证当前账户页刷新后变化、历史日志原快照不变、账户可见但VENDOR不可见时明确null，以及disabled VENDOR来源解释。原ReferenceInput/ReferenceValue无alias字段，不擅自增加原schema条目；独立扩展ID由主线统一登记。整个渠道/引用目录模块的容量、生命周期和跨模块任务失效复验缺口仍保留，不继承为本轮验收完成。
