# M3a：身份事实只读观察

本阶段为独立`meta_identity_facts_observation.py`，不修改冻结M1/M2/原observer，不接023、公共路由、生产Provider或定时器，不写数据库、不做广告写入。测试只使用受控transport。原始观察、READ_VERIFIED、SQL fixture、非空资源ID都不能产生生产执行权。

## 内部接口与可信边界

```python
selected = [IdentityFactSelection(account_id, kind, external_id)]
facts = await observe_identity_facts(bound, selected, transport=None, limits=None)
```

`bound`必须是M1的`BoundMetaObservation`。复用冻结M2 `prepare_rows`的纯校验核issuer、来源与完整原始观察根、绑定集合和预算；不调用登记或SQL。此处依赖当前固定内部校验接口，不因此继承M2持久登记或权威地位。

明确选择1至500个唯一`(internal account UUID, kind, external ID)`；必须在该账户原始raw集合出现。不同账户拥有相同外部资源时仍保留逐账户绑定；不接受任意source/token/Graph版本/expected principal/verified/usable输入。外部ID保留前导零，来源、配置revision与配置Graph版本只从Bound取值。

配置契约`configuration.py:185`确有可选`systemUserId`，但冻结M1配置/绑定没有携带该字段。故本模块先执行GET `/me?fields=id`，只观察实际主体；结果固定`principal_binding=CONFIG_PRINCIPAL_NOT_BOUND`，不能拿businessId或调用者参数冒充可信systemUserId。未来要核主体，必须独立捕获真实配置字段并纳入来源根及最终CAS，不能在此处偷偷加参数。

## 官方声明与字段白名单

以下链接本次已通过官方primary源核对。SDK main字段声明不证明某个已配置Graph版本支持这些字段，也不证明所用令牌的OAuth授权、system user任务或平台可投；目前没有经真实Meta验证的最小权限集合。400/权限拒绝只记录未核状态，不猜测“资源不存在”或自动降级为可用。

| 读取 | 本阶段固定字段 | 观察的意义与限制 |
| --- | --- | --- |
| `/me` | id | 实际响应主体，未与配置systemUserId匹配 |
| `/{page}` | id,name,business,can_post | 返回资源/业务关系和发帖标记；can_post不等于投广告权限 |
| `/{pixel}` | id,name,owner_business,owner_ad_account,is_unavailable,is_restricted_use,user_access_expire_time | 返回归属关系及限制；到期原始文本不冒作全局Token到期，不推出目标/转化事件兼容 |
| `/{application}` | id,name,business,ios_bundle_id,iphone_app_store_id,ipad_app_store_id | iOS相关原始事实；bundle ID是有界字符串数组，不猜Android包名，不拼接商店URL冒作已验证来源 |
| `/{page或pixel}/assigned_users?business=绑定BM` | id,business,user_type | 仅观察完整已分配主体；不等于当前主体实际获投放权 |

官方来源：

- [Page SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/page.py)：Field.business/can_post与GET assigned_users（939—968行）。明确不请求access_token。
- [AdsPixel SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adspixel.py)：44—58行的归属/限制字段，322—351行的GET assigned_users；`user_access_expire_time`官方类型datetime，保留原文本，不发明时间语义。
- [Application SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/application.py)：业务/iOS字段；2202行`ios_bundle_id`为list<string>，2208—2209行商店ID为string。
- [AssignedUser SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/assigneduser.py)：25—35行仅声明business/id/name/user_type；没有tasks字段，因此不猜GET tasks，也不将另一对象的ADVERTISE枚举当当前授权证据。
- [User SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/user.py)：Field.id与节点GET。

原要求来自WORKFLOWS第19行逐账户page、组级pixel+conversion_event或application+storeURL；第101行独立capability/policy/scope版本；保留03第166—169、435—437行的资源可用、APP平台匹配及能力包。上述只读白名单不足以单独满足它们。

## 不推断的字段与未核状态

业务展示name保留原null/0至4096字符，不截成023的255；嵌套业务/账户只留数字文本id，忽略自由扩展字段。缺失字段输出null并加入unknown_fields；bool严格为bool，外部ID不接受数字强转，文本拒绝NUL、无效UTF8和已知令牌回显。iOS数组保留语义顺序，不压成单个bundle。AssignedUser字段缺失仍为null，不将返回某主体推为当前Token主体。

403或已识别权限错误记录`META_READ_FORBIDDEN`；400通用字段/版本等未支持结果记录`META_READ_REJECTED`，不解析自由错误正文猜具体原因。后者可能有多种平台原因，不能宣称已准确诊断为“不支持版本”。已返回对象id与请求不符、非法字段、分页/预算异常、临时故障、重定向或断网则拒绝整个结果，不给部分成功包。APPLICATION不读取未明确的分配边，状态明确为`NOT_REQUESTED_FOR_APPLICATION`。

输出不可变的绑定根、配置ID/revision/API版本、UTC原始观察窗口、实际主体和逐资源小JSON事实/原因、真实请求数/响应字节及内容SHA256。固定`api_version_compatibility_verified=false`、`durable=false`、`execution_authorized=false`、`capability_version=null`、`policy_version=null`。不提供usable或verified字段。

## 网络与预算

默认网络层独立暴露GET，固定HTTPS graph.facebook.com、配置Graph版本与上述路径/精确fields，禁止任意查询、Token查询参数、userinfo、fragment和重定向。Token只在Authorization头，源包和结果repr隐藏；异常不带URL、headers或平台正文。测试transport复用相同响应契约，不等于真实网络验证。

复用原`MetaObservationLimits`及`_ReadBudget`的字节/请求/错误解析；这是冻结内部接口依赖。每页最多200，最多250页/边、50000分配主体/边、2500请求、单响应256KiB、总响应及结果32MiB、总体60秒；默认单GET15秒。分页next只校验同host/同版本/同资源路径，丢弃其查询/Token；必须有合法不透明after，再自行重建fields/business/limit/after。重复cursor/重复主体、next无after、超限不能变成完整枚举。调用者可减少预算，不能增加硬上限。没有网络期间数据库事务或锁。

## 下一桥接与尚缺来源

下一步应先补可证明的主体绑定/字段版本支持，再建立独立受信IdentityCapabilityResolver，核逐账户/目标/资源任务、限制、APP OS/storeURL与真实能力发行/撤销。能力版本不能用raw hash替代；policy/workflow/归因参数不能从capabilities/user_tasks、can_post或资源分配主体推断。名称null/超255与原023严格正文不相容，必须明确未就绪，不允许裁剪以换取成功。

未来最终登记/发布必须重新当前授权和CAS：auth与当前managed显式锁→全部来源配置globalUUID→accountclock/dueguard→排序账户→能力发行证据→023 head。原023 publisher现有取锁方向需要先预锁再重入或明确重构；不在launch head之后首次取得来源锁。最终资源证据与023正文/版本/观察时刻一致，整事务审计/outbox；执行仍另作caller与plan owner即时授权，GET不是写授权。本阶段不创建迁移、不实现这条发布链。

## 验证清单

- [x] 新专属受控transport纯测最终60/60通过（0.73秒），Ruff及格式通过；覆盖完整白名单、issuer/根篡改、选择交集、缺据/403/400、原始长名/null、iOS数组、注入/脱敏、分页完整性、预算、独立完整JSON根对照、顺序稳定与取消。另替身HTTP连接池证明默认transport只发GET、流式字节上限和目标校验先于网络；不等于真实TCP/Meta测试。
- [x] 主线真实Bound SQL捕获与受控HTTP组合25/25通过（11.13秒），其中原14组、新5组及初始化；回执`evidence/python-meta-identity-facts045-http.json`。此处的HTTP为MockTransport，不是Meta实网。
- [ ] 真实Meta配置版本/权限/资源字段测试：无真实外呼，不计通过。
- [ ] 023受信发布及生产能力Provider：未接，不计功能验收。

## 主线待排的045组合专项

扩展`tools/meta_observation_registry_checks.py`的原7参数及`cipher`不变，仅增加关键字`include_identity_facts=False`。原`META_OBSERVATION_REGISTRY_CASES`14组和默认路径/原断言全部保留；新5组独立导出`IDENTITY_FACT_OBSERVATION_CASES`，不能把旧045成功回执算作新模块通过。

True时只在原14组完成后，复用同轮真实角色、API加密配置及2个SQL技术账户，再执行一次真实M1 SQL捕获。仅该次raw的受控APPLICATION边增加007空名称；新包不register，原14组的4资源数据与断言不变。新组分别核完整白名单/iOS数组/长名/null及未绑定主体、选择交集网络前拒绝、完整分页及缺游标失败、403和缺字段明确未知、全程无额外持久写入。配置systemUserId=7而受控/me返回17，必须仍明确未绑定，不能虚构配置匹配。

网络与SQL观察针对同一真实AsyncEngine：捕获后连接池checkedout为0；每次新采集GET前后均核为0，GET期间SQLAlchemy before_cursor_execute若发生任何SQL即失败，前后SQL计数相同；不以普通空连接数代替事务观察。此证明仅限本次自有捕获/引擎，不能声称已审计全应用所有连接。每组前后比较六张raw表计数、账户clock/账户正文/revision及023 evidence/head，要求零额外写入。新collector24次受控GET逐一检查；加原14组50次和额外raw捕获10次，预计本档84次受控GET、0真实Meta请求（以主线实际metrics为证，当前尚未运行）。

新增工具安全/响应协议16项与原collector60项合跑76/76通过（0.98秒），Ruff/格式通过。工具未自行运行SQL；下一步由主线串行使用隔离13306 UUID库，新增5组的实际结果仍待回执，不提前标验收。

主线最新实际结果：组合档25/25通过，11.13秒，回执`evidence/python-meta-identity-facts045-http.json`。84次受控Graph GET中新增collector24次，24次自有引擎网络期间无SQL/连接归还检查通过；真实Meta请求0，无023或额外持久写入。所用账户、READ_VERIFIED、/me与资源响应仍为本轮显式技术fixture；结果不证明真实令牌主体、配置版本权限、资产任务、可投能力或生产预检。上述“待回执”是工具交付时的历史状态，现由本段实际回执补齐；源码/工具继续冻结。
