# Meta生产只读来源接入：最小实际链与后续任务

## 当前结论与证据范围

2026-11-08只读核对当前源码。本次只新增本文档，没有读取私密环境变量、请求Meta、操作数据库、修改现有Store/路由或赋予生产权威。`meta_launch_observation.py`的65项transport受控纯测证明协议边界，不能代替真实app/token、API版本和资源权限验收。既有C→execute真实30组只证明真实素材链与隔离执行协议；Meta、资源执行能力和归因来源仍不因此成立。

M1临时绑定现已实现于独立`meta_bound_observation.py`：仅原accounts.sync路径、自有短事务捕获后事务外观察，没有持久登记。下一项是对来源与账户重新授权/CAS后的原始只读观察登记，随后才是独立能力核验与身份发布；不应把原始观察直接塞进023的`verified`或向Authority默认注入一个`TRUSTED`标签。

源码定位：

- `meta_launch_observation.py:74、238、398`：来源配置、不可变观察包、网络采集；输入没有tenant或业务账户revision，结果`execution_authorized=False`，policy/workflow固定未知。
- `account_actions_sync.py:123—221`：现有同步在每次发送前和回写时核原`accounts.sync`、subject/auth_version、当前账户范围、归属、revision与固定来源，并在内存解密Token；`:362—443`回写元数据、审计及outbox，币种/时区变化拒绝自动覆盖。
- `account_identities_store.py:40—70、187—212`及迁移023：身份发布需要真实registry证据，绑定内部账户revision、配置revision、capability_version、完整原正文hash；当前没有生产registry写入器。
- `launch_validation_store.py:118—138、461—485、513—576`：capture无session、网络在事务外；final revalidate仅DB来源锁，先于launch clock/head；无Provider默认503。原十字段响应和原TTL/CAS不扩写。
- `metric_profile_store.py:30—39、191—222`：MetricProfileAuthority独立capture/revalidate；正式source必须META，发行需原system.release.manage，不能让launch.validate顺便取得配置发行权限。
- `metric_profile_contract.py:25—89`：原profile版本是字符串；显式adapter_version、attribution_spec和独立来源proof均必需。`metric_profile_query.py:89—140`同时核proof与独立typed observed_at、源版本和当前配置，不应绕过此读取器。

## 观察能证明什么

| 实际读取 | 可登记的事实 | 不能推出的事实 |
| --- | --- | --- |
| BM owned_ad_accounts与client_ad_accounts完整枚举的并集 | 指定配置/BM/token在本次窗口能从对应边观察到该external account ID，并保留实际边来源 | 业务账户属于当前投手、可跨租户读取、具ads_management、可以发布广告 |
| act_ID的id/account_id | 该返回与请求外部ID精确匹配，前导零不被转换 | 内部UUID对应关系、内部账户当前revision和授权状态 |
| name/currency/timezone_name/account_status | 平台原始值或明确unknown，真实0保留；开始/完成时间范围 | 系统支持的币种/IANA时区、原内部状态枚举、冻结历史归属可被覆盖 |
| promote_pages/adspixels/advertisable_applications全部分页的id/name | 该账户这次可观察的PAGE/PIXEL/APPLICATION清单，完整空清单合法 | 每个资源可写/可执行、Page身份任务完整、pixel事件兼容、APP目标/操作系统/优化目标兼容 |
| capabilities/user_tasks原始文本集合 | 原样白名单字段的只读观察，缺失为unknown | ORBIT capability_version、每资源usable=true、policy/workflow版本、Agent版本或平台写授权 |
| 完整观察SHA256 | 同一规范数据、配置ID/revision、版本和窗口的内容身份，可检测替换 | 签发者可信、凭据有效至某时刻、来源在最终提交时仍当前 |

以上多个Graph GET没有平台原子快照保证；`complete`仅表示全部要求的分页在预算内结束。观察窗口内也可能发生平台授权变化，执行前须再作目标账户/资源即时校验。

已查官方SDK边与字段的链接、权限页NotLoggedIn/429限制见`META_LAUNCH_OBSERVATION_DESIGN.md`第一节。business_management/ads_read仍只是待官方页面与实际app核验的候选，不能在实施说明中宣称最小权限已经验证。

## 第一闭环：当前配置与账户绑定的原始证据

现M1内部接口已落独立模块`meta_bound_observation.py`；没有公开HTTP。未来持久登记建议独立Store；现observer、原SYNC响应和原身份DTO保持不变。

```python
async def capture_meta_source(sessions, actor, account_ids, *, cipher, permission="accounts.sync") -> MetaSourceSnapshot: ...
async def observe_meta_source(snapshot, *, transport=None) -> BoundMetaObservation: ...
# 下行仅后续M2设计，未实现、未授权公开HTTP：
async def persist_meta_observation(session, actor, snapshot, observation, request_id) -> ObservationReceipt: ...
```

1. `capture_meta_source`目前仅允许accounts.sync；accounts.read、launch.edit和launch.execute等分支在打开session前明确拒绝，不叠加read权限。它自行取得独立无事务session并结束短事务和session后才返回包，拒绝工厂复用已有事务。先核当前原同步主体和账户数据范围、到期归属投影，明确同租户内部UUID→external ID→唯一当前来源映射；0或多个来源拒绝，不能猜任意Token。未来launch预检沿现Store的launch.edit（launch_validation_store.py:466、535），execute沿launch.execute；其完整双主体账户读取/来源锁接口尚需单独实现核对，不拿BM并集替代本地范围，也不把未来分支强加accounts.sync。
2. 锁当前明确的META_BM配置ID/revision、enabled/READ_VERIFIED、settings.businessId/settings.graphVersion和加密accessToken；现命名参考`account_actions_sync.py:174—208`，不是其他section的apiVersion。仅在内存用既有Cipher解密，冻结租户、actor/subject、auth版本、原动作、owner/team、账户UUID/revision/external ID及配置版本；结束事务才传给observer。每批1—500账户、最多一个明确来源配置；不同来源拆批，不任意混合。
3. 网络阶段没有session或数据库锁，只调用现GET observer。Token不进持久JSON、回执、repr或日志。超预算/缺页失败不给完整证据；不能把前几个账户成功作为整批完成。
4. `persist_meta_observation`外层事务中，重新核当前动作与对象范围、subject/auth_version、当前来源revision及账户revision/归属/外部ID，任何漂移拒绝旧包，不能自动换源后继续沿旧观察。来源配置按UUID排序锁，再账户clock与排序账户；之后如接launch，才允许其clock/head。固定锁序在真实工具中验证，与既有SYNC的账户→配置顺序不能盲目合成同一长事务；如共享同表出现交叉顺序，先统一合法入口或以独立短事务证明无跨链锁，不能只靠注释宣称安全。
5. 同事务只追加原始观察、原动作审计与outbox。source/account CAS、正文hash与计数校验失败全部回滚；重放仍先核当前动作与当前对象范围。回执仅证据UUID、hash、观察窗口和计数，不返回secret或充当Task/可执行性响应。

原始观察阶段不自动更新原账户元数据：现SYNC有完整状态映射、币种白名单与币种/时区纠错阻断，首闭环先保存事实，不建立第二套覆盖规则。以后如需组合，必须重用同一metadata转换及CAS，并解决更新账户revision后身份绑定应使用的新revision，不能让刚发布的证据立即自失效。

### 最小迁移需求（尚未申请编号或编写DDL）

建议独立原始证据头与逐账户明细两表，复用既有业务审计/outbox机制，避免改023历史语义。

- 头：tenant/id、source_config_id/revision、business_id、graph_version、actor/subject、原动作、request_id、started_at/observed_at、evidence_sha256、request_count/response_bytes、account_count、规范schema_version；无Token、任意URL、错误正文或手工verified位。
- 明细：tenant/evidence_id/account_id、captured_account_revision、external_id、owner/team快照、canonical账户观察JSON、单行hash/resource_count；联合主键tenant/evidence/account，FK指向同租户证据和账户。
- 约束：UUID/正安全整数/UTC毫秒、观察结束不早于开始、账户1—500、资源每账户≤5000、单行与整批字节预算、ID/revision不空、hash固定64hex；头正文根按明细稳定排序重算，不接受self-reported hash代替验证。
- 索引：tenant/account_id/observed_at/id用于最近观察；tenant/source_config_id/source_config_revision；重放唯一约束按明确operation/actor/request key定义，不能单凭相同hash吞掉不同主体请求。原JSON总32MiB上限不是随意加大SQL包；须采用有界明细写入、明确driver包预算和原子提交实际量测。
- 撤销状态/保留期限和清理策略须单独定技术合同；不能照搬7天Task事件TTL。缺这个裁决时只实现有限测试数据，不启动无人值守无限增长采集。

## 第二闭环：身份registry，而非把raw转成usable

023原AccountIdentities要求resources每项name为string≤255、usable为bool、reason_code为null或string，整体必需capability_version。当前observer允许name=null或最长4096，因此不能无损直接发布；禁止null改空串、长名截断、hash当capability_version。

应新增受信`IdentityCapabilityResolver`技术适配器，输入绑定账户的原始证据、明确选中的资源、目标组合及当前能力发行证明，输出逐资源实际可用判定、合法展示名、原因及独立capability版本/来源证据。它需有真实平台权限/资源任务和目标兼容依据；现GET边不足的字段先登记未知，缺必要来源503。仅确认资源不可用时可按既有正文发布usable=false及明确原因；整个能力版本无权威来源时，不以“全false”规避023完整可信证据要求。

真实registry签发后才写023 evidence并调用原`AccountIdentitiesStore.publish`；二者须同一事务且snapshot hash、最终account_revision、source revision、资源正文完全一致。原publish内部先账户后配置锁，集成必须先读清既有顺序并统一来源锁策略，不能直接在launch head后首次调用它。GET只展示观察，不是execute写授权。已知revoked_at、凭据过期、源修订、解绑、转属或账户revision变化仍立即阻断；未知到期不自造5/15分钟TTL。

## 第三闭环：指标/归因、策略与生产预检分开补齐

1. MetricProfile不是Graph账户capabilities。真实META profile需要原完整profile的字符串version、source_sha256/observed_at/evidence_ref/配置ID与revision，以及明确版本的attribution_spec目标映射。不能从“7天点击”等窗口字符串猜Meta数组。沿`MetricProfileAuthority.capture/revalidate`→`MetricProfileStore.publish`→现query/references的不可变profile与adapter精确读取；发行权限保持原system.release.manage，不与预检调用者权限混淆。
2. policy/workflow版本需要独立受控发行源：产品/渠道、币种/预算/时区、目标与特殊类别、URL/SSRF、平台约束、身份与profile兼容矩阵均须有可重验版本来源。raw capabilities/user_tasks不是这个来源；将observer SHA当policy_version不成立。原完整计划树、素材、scope、allocation/name冻结也不能因Meta观察完成而跳过。
3. 生产ValidationAuthorityProvider.capture可组合数据库来源短事务、事务外Meta观察、真实profile/身份/策略证据；revalidate只能按来源→各clock/排序资源→launch clock/head前重验版本与双主体权限，不作网络或发行写入。观察refs只用白名单kind/id/revision，不塞完整Graph正文/secret进038。
4. execute仍需要独立ExecutionAuthority、真实C素材same-transaction ticket、最新账户/身份资源与能力证明、原launch.execute及activate时publish/ack。即使只读预检真实通过，也不能默认注入生产执行Provider或开放命令发送。完整命令持久发送/lease/UNKNOWN/VERIFY是后续链，不能由本文件的read-only链代替。

## 可独立开工与验收清单

| 次序 | 狭窄交付 | 开发/测试应证明 | 当前状态 |
| --- | --- | --- | --- |
| M1 | 只读配置/账户快照适配器，内存BoundMetaObservation | 正确businessId/graphVersion、唯一来源、原accounts.sync范围、外部ID前导零、Token不泄漏、自有事务结束后网络 | 已实现；32专属纯测通过，尚无真实SQL/Meta验收 |
| M2 | 原始观察两表+CAS登记/审计/outbox | 真实UUID测试库重放、撤权、配置/账户变化、1644全回滚、500账户字节/锁预算；不写023 verified | 需先批准DDL及锁序；外部Meta凭据可独立阻断 |
| M3 | 实际Meta只读连接验收 | 管理员确认API版本/app权限；真实BM两边及三资源边完整、缺scope/被撤权/限流，日志无凭据 | 未测；不在聊天/日志索取Token |
| M4 | 身份能力适配器与023受信publisher | 真实权威资源任务/目标组合证据、完整名称边界、能力版本/撤销、最终revision一致；不猜usable | 关键来源接口缺失，不能先填true |
| M5 | 真实MetricProfileAuthority及策略发行包 | META来源与精确attribution映射、独立版本/来源hash/撤销，与原profile读取一致 | registry协议已有，生产producer仍缺 |
| M6 | 组合原validate生产Provider | 默认503零写、成功真实counts/完整树/15分钟、source/head CAS、双主体与所有refs实时重验 | 依赖M4/M5，不用隔离成功冒充 |

### M1当前实现与证据限定

`MetaSourceSnapshot`冻结当前tenant/actor/subject/team/data_role/auth_version、原accounts.sync、账户clock、排序账户UUID/revision/external ID/owner/team、明确配置ID/revision/businessId/graphVersion及捕获时间。Token仅作为repr隐藏的内存配置传给GET observer，不进binding摘要、回执或持久存储；包不保存session。`BoundMetaObservation`组合绑定hash与实际观察hash，durable/publication_revalidated/execution_authorized全部固定False。hash用于检测误绑定，不是来源签名或生产authority。

捕获锁序严格沿现SYNC：授权行→auth_version→account clock及dueguard→一次有界排序账户查询（最多500）→唯一READ_VERIFIED配置。未改为指标来源的配置→clock方向，二者尚未统一；未来publisher不得拿此快照声称最终CAS通过。来源READ_VERIFIED只允许尝试读取，不产身份能力版本或usable。原始账户状态不被改写，已解绑拒绝，其他状态沿原SYNC允许重读恢复，不擅加ACTIVE/AUTHORIZED前置。

`test_meta_bound_observation.py`32项纯测及原observer65项合跑97/97通过（1.07秒），Ruff/格式通过。覆盖事务和session退出后才有网络、当前同步授权/到期guard拒绝、0/多来源、租户/账户/配置revision误绑定、原字段graphVersion不回退apiVersion、密钥异常脱敏、前导零、原名与4096资源名称不裁剪、500账户一次集合读取，以及内部UUID排序与平台ID排序不混淆。SQLsession/授权和HTTPtransport均为受控替身；500集合形状不是500真实数据库扫描容量验收。没有外呼Meta或数据库实测。

下一窄任务为M2迁移与真实CAS登记工具；需先核跨链锁序与保留策略。M1完成只意味着临时只读来源绑定，不宣称持久发布、生产接通、所有投放功能或正式环境验收完成。
