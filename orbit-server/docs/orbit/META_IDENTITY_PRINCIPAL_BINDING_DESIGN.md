# M3b：真实配置主体与/me精确绑定

本阶段新增`meta_identity_principal_binding.py`及独立纯测，不改冻结M1/M2/M3观察器、原配置schema、023、公共入口或Provider。不执行真实Meta请求，不启动数据库或定时器。它解决“配置中的主体是谁、实际读请求返回谁”的绑定，不能回答“该主体可对这些资源投广告吗”。

## 已确认的接口

```python
source = await capture_identity_principal(sessions, actor, bound)
match = await observe_identity_principal(
    source, selected, transport=None, limits=None,
)
```

`bound`为真实M1产生的`BoundMetaObservation`；纯校验复用冻结M2 `prepare_rows`检查完整issuer/原始观察/绑定根与集合。`sessions`必须创建独立无事务session；在接管context之前拒绝已有事务，避免close隐式回滚调用者事务。`actor`必须等于原捕获主体，不接浏览器传tenant/source/expected_id。

`configuration.py:185`的META_BM可选`systemUserId`已存在，本阶段从真实配置`settings_json`读取它，不新增配置字段。M1原配置没有携带该字段，因此执行第二个完整短事务：不是只查配置，更不能用M3事实包实际/me反过来填“期望主体”。缺失、空、非法或非文本ID均503 `META_PRINCIPAL_SOURCE_UNAVAILABLE`，保持M1原始读取接口可兼容。

## 第二短事务完整当前授权与CAS

固定顺序：

1. 原`accounts`菜单与`accounts.sync`动作当前授权，当前actor/tenant核对；当前auth_version行FOR SHARE。
2. 当前租户所有启用且READ_VERIFIED的META_BM配置按全局UUID顺序共享锁读，要求恰好一个；该标签只允许尝试读取，不是Meta授权或能力发行。
3. 配置ID/revision精确等于原Bound；businessId/graphVersion精确相同；accessToken密文仍存在；systemUserId为1至64位数字文本，前导零不强转、不裁剪。此层不解密新Token，不记录密文/Token。
4. account clock共享锁及原dueguard；显式`managed_teams`当前锁读，避免旧RRview nested EXISTS范围。
5. 原Bound全部账户按UUID当前共享锁集合读取，最多500账户；准确数量/ID集合、tenant、当前本人或显式可管理团队范围，以及每账户revision/external ID/owner/team/未解绑均重新核对。
6. 当前subject/team/data_role/auth_version/accountclock与原捕获一致。配置/版本或原账户绑定漂移409 `META_PRINCIPAL_SOURCE_CHANGED`；当前不可见404，当前动作失效403，dueguard原503不绕过。

账户数由原Bound限制；M3“1至500条所选资源”是另一维度，不会据此漏核未选资源所在账户。事务读取原Bound的所有账户，即使随后网络只选择其中一个PAGE，也必须完整核对。

当前M1为clock→账户→配置共享读，新绑定为配置→clock→账户共享读；本阶段没有账户UPDATE升级，但不宣称系统整体无死锁。合法入口必须从自有无锁事务开始，不在launch head之后首次调用。真实并发及非法倒序1213仍需主线专项；不能用纯锁序断言冒充真实MySQL证明。

SQL事务和session全部退出后才生成不可变`PrincipalBindingSource`。新source根包含原Bound根、配置ID/revision/BM/API版本、实际配置systemUserId、当前managed集合及UTC原精度捕获时刻。没有session/factory、调用方expected ID或任何新Token字段。该对象仍引用M1隐藏凭据，仅供内存读取；repr隐藏，禁止将整个对象asdict后落库/日志。

## 事务外实际主体匹配

`observe_identity_principal`先验新source私有issuer与根，再复用冻结M3 `observe_identity_facts`。它先GET `/me?fields=id`，随后只读所选raw集合内的PAGE/PIXEL/iOS事实；host/path/分页/预算/脱敏沿M3，不开新自由查询入口。

事实包必须与source的原Bound根、配置ID/revision、Graph版本、BM精确一致。缺实际/me返回503 `META_PRINCIPAL_NOT_OBSERVED`，实际ID与配置systemUserId逐字不同返回503 `META_PRINCIPAL_MISMATCH`；不回显任一ID/响应/Token。字符串`42`和`00042`不被数字转换成“相同”。

`BoundPrincipalMatch`绑定新source根、完整M3事实根、实际主体ID和匹配结果；只声明`principal_matches=true`。固定`principal_type_verified=false`、`publication_revalidated=false`、`durable=false`、`execution_authorized=false`、capability/policy版本null；不提供usable或verified字段。嵌套原M3事实的`principal_binding=CONFIG_PRINCIPAL_NOT_BOUND`保持历史语义，不改原包伪装它当时已经匹配。新的匹配对象仅补上此独立关系。

匹配不证明主体类型确为system user。配置名称叫systemUserId、官方SDK有SystemUser类、AssignedUser.user_type返回字符串、资源枚举非空，都不能代替独立类型及权限证明。捕获后配置/账户变化不会在纯网络步骤被自动发现，因此明确没有“最终CAS已通过”标志。

## 官方版本化权限核对结果与尚缺的最小证据

本轮已读官方SDK固定`25.0.0` tag，改善此前只有main声明的问题，但SDK代码仍仅证明声明存在，不等于配置Graph v25.0端点权限承诺：

- [SystemUser 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/systemuser.py)：87—115行GET assigned_ad_accounts，146—175行GET assigned_pages。可以作为后续“实际绑定主体所分配资源”的只读候选入口；返回ID不能推导任务权限。
- [User 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/user.py)：1642—1673行GET permissions；[Permission定义](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/permission.py)声明permission/status以及granted/declined/expired。尚未证实此入口对当前system user类型/配置权限的适用性，不自动按用户Token模型解释system user Token。
- [AssignedUser 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/assigneduser.py)：无tasks字段。不能从create_assigned_user的POST枚举推断GET task响应或当前主体获权。
- [AdAccount 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/adaccount.py)：有user_tasks字段及任务枚举；[Page 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/page.py)有任务枚举。这些声明不能单独证明“某任务足以创建某目标广告”。

官方权限页面核验受限：[system-user permissions](https://developers.facebook.com/docs/marketing-api/system-users/guides/permissions/)、v25 user/assigned_pages、v25 page/assigned_users在网页工具不可读，debug_token页面限流。内部浏览器不可用，现有Chrome连接器新建页也发生内部错误，已停止重复同阻点。未绕登录/权限/访问控制；未使用第三方转载作为技术授权依据。

为最终接023及真实预检，只需要补齐下列必要证据，不继续无限扩raw字段：

| 必要结论 | 最小来源与当前状态 |
| --- | --- |
| 配置主体等于实际请求主体 | 本模块真实配置读取+事务外/me逐字匹配；尚待主线真实SQL与受控HTTP组合验证 |
| Token对正确版本/API具有实际授予范围、未明确撤销/过期 | 候选官方permissions/安全内省机制需先核system user适用性和敏感参数传输规则；不把Token放URL，不凭READ_VERIFIED、已读取字段或可选到期null声称有效 |
| 目标账户与所选PAGE/PIXEL/APP实际被该主体授权，且满足目标动作/事件/OS | 需官方版本化资产任务/权限语义及实际GET证据；M3分配主体列表、可读边、can_post与ADVERTISE枚举不足；不擅自硬编码“某scope+某任务=usable” |
| 合法capability/policy版本及目标组合规则 | 需独立受信、可撤销的发行包，引用明确官方版本规则及实际观察根；不能将raw hash或当前日期当能力版本 |
| 归因profile/placement/goal/平台映射 | 使用对应权威registry与精确适配器证据，不由user_tasks或资源ID猜参数；现缺生产producer的分支仍503 |
| 023完整正文与发布期当前账户/源一致 | 仍须严格名称边界、完整观察/证据正文hash、source/account CAS，和实际capability版本；缺权威不能靠全部false或假空数组绕过 |

上表中的候选权限入口只有读源设计，不在本轮实现；没有依据的能力保持unknown且不发行usable。本模块是必要主体绑定，并不承诺只靠上述已实现事实就足以开放生产预检。

## 发布期必须重新CAS

未来publisher在同事务重新当前动作/actor/tenant/所有目标账户可见性、配置唯一启用/ID/revision/businessId/graphVersion/systemUserId、auth_version、dueguard/clock、每账户revision/owner/team/external/未解绑，并核source/facts/匹配根和实际能力发行/撤销。随后才可能原子写受信023 evidence+history+resources+审计/outbox。若用于launch，调用者与plan owner的实际引用权限仍需沿原契约额外核对；不能沿用accounts.sync匹配回执冒充launch.execute授权。

已有023 publisher取锁方向不能在launch head后首次取得来源/账户锁；最终桥须按明确来源→clock→账户→head预锁或经审阅重构。此阶段不创建迁移、不实现publisher、不更改默认None AuthorityProvider。

## 验证清单

- [x] 新专属44项纯协议与既有M3观察/工具76项合跑120/120通过（1.13秒），Ruff/格式通过。覆盖完整第二事务CAS、配置主体缺失/非法、范围与当前managed、dueguard/撤权、外层事务不接管、源/事实根错绑、实际ID逐字匹配、网络只在session关闭后、双账户全量CAS及不冒生产权限。
- [ ] 真实SQL第二捕获+受控/me匹配/错配/当前撤权、旧RRview及零写专项：待主线统一接入，不自行运行。
- [ ] 真实Meta主体/权限/资源任务、生产023发行及预检：未验证、未接通，不计验收。

## 待主线串行运行的真实组合工具

工具继续复用`run_meta_observation_registry_checks(..., cipher=..., include_identity_facts=True)`，不新增公共入口或第二组固定身份。原14个M2与5个M3a用例保留；新6组独立导出`IDENTITY_PRINCIPAL_BINDING_CASES`，依次验证：缺配置systemUserId固定503、真实配置二次捕获与/me精确匹配、实际错/me固定拒绝、配置/账户/clock/auth代际漂移、动作撤回/转属/旧RRview撤团队管理、网络期间无SQL且无新增持久事实。

复用同轮真实加密配置，配置systemUserId仍为API创建的7；仅新的受控`principal_match`模式返回/me=7，旧M3a返回17的观察及所有断言不变。缺ID和代际漂移由本轮隔离库SQL技术变更触发并finally恢复；实际/me来自httpx MockTransport，不填造匹配回执。另用M1真实捕获TEAM_ADMIN原包，在新捕获事务先建立旧RRview，再由另一已提交连接删除团队管理关系，必须404，最后恢复管理行。该场景不以修改accountclock掩盖旧RR风险。

新主体匹配/错配共6次受控Graph GET，沿用现自有AsyncEngine网络期间SQL事件禁止、前后checkedout=0和SQL计数不变检查；预计全档100次受控GET（包括原50、新M3a原始包10、M3a collector24、新主体collector6、管理身份M1包10），真实Meta请求0。只有主线实际metrics可据此记录结果。每组均比较原始六表计数、账户clock/正文/revision和023 evidence/head，要求无新增持久事实；不把技术fixture恢复写计作生产采集功能。

6初始化+原14+M3a5+M3b6预计31组。此前M3a25/25回执仅对应旧检查点，不能继承为本6组已通过。新增工具安全/响应协议17项、绑定44项与原观察60项合跑121/121通过（1.09秒），Ruff/格式通过；真实组合仍待主线执行。默认`include_identity_facts=False`不运行新增M3a/M3b分支，原045默认行为不变。

主线后续实际组合31/31通过（10.16秒），回执`evidence/python-meta-principal045-http.json`；100次受控Graph GET、自有引擎30次网络期间无SQL/连接归还检查，真实Meta请求0。上述待测章节是交付时的历史计划，现由此有限结果补齐；不能继承为真实Meta主体类型、OAuth范围、资产任务、023可投证据或生产预检验收。

该原回执同时观察到045旧CHECK使用JSON BETWEEN的1235警告，不能因31组通过掩盖。主线另分配051增量数值CHECK修正与独立矩阵；31回执保留原貌，不更改或覆盖，也不将其表述成“无警告”。
