# M2原始Meta观察登记设计

本阶段只登记原始观察，不发布023身份、不产生capability/policy/workflow版本、不更新账户、不授权执行。主线已采用正式045迁移并完成下述隔离真实专项；M1、M2与原observer源码保持冻结。开发者未读私密变量、未调用真实Meta、未自行启动数据库或定时器。

## 已实现的内部接口（未接公共入口；已做隔离真实SQL验证）

```python
registry = MetaObservationRegistry()
prepared = registry.prepare(bound)  # 无SQL、无网络，有界验证与小行规范化
receipt = await registry.register(
    session, actor, prepared, key=key, request_id=request_id,
)  # 调用方外层事务；不commit、不执行网络
```

`prepare`仅接M1产生的BoundMetaObservation，不接HTTP任意verified字段、Token或来源ID覆盖。核M1私有issuer、原binding_sha256、原observer完整evidence_sha256、二者combined hash。hash是内容一致性，不是外部来源权威。逐项核固定类型、UUID、版本正安全整数、UTC原始时间精度、captured≤started≤observed、500账户上限与每账户5000资源上限；metadata、资源和unknown原因均按原observer字段验证，名字null/4096原文保留。最终DB时刻不得早于观察结束，不自造观察TTL。

045新内部头的捕获、开始、完成和创建时间均采用DATETIME(6)，读取按UTC原微秒精度比较，最终参考时刻为UTC_TIMESTAMP(6)。receipt按原时刻isoformat输出，不强制截毫秒；canonical/hash不裁剪时间。不改M1或原observer，也不依赖其当前utc_now是否碰巧归整毫秒。`.123499`、`.123500`、`.999999`必须精确往返，不能让DATETIME(3)四舍五入改变原proof。

准备结果只引用不可变绑定和逐账户/资源小行；按原canonical排序流式重算观察根，不将全观察转成32MiB单JSON或巨量deepcopy。每次SQL集合≤100行且规范参数字节≤256KiB，总规范持久参数预算≤32MiB；小头/ledger/audit/outbox预留64KiB，明细按完整tenant/registry/行hash参数字节精确累计，小头写入时也检查不超过预留。特殊名称引号/反斜线可能扩大编码，不以“4096字符必定16KiB”替代实际字节计算。实际JSON/驱动开销须在真实045专项量测；超限明确拒绝，不截断/返回部分成功。原网络32MiB预算与SQL规范字节预算不同，不假称二者天然相等。

回执只含原始登记UUID、来源绑定根、观察时间、账户与资源计数及固定execution_authorized=false；它不是Task、usable或生产Provider就绪标志。Token仅留M1隐藏内存配置，所有SQL参数/持久包/回执/日志不含Token，禁止对M1包直接asdict后存储。

## 最终当前授权与CAS

1. 调用者必须持显式外层事务。按actor原accounts.sync菜单和动作当前授权，actor/tenant始终与原包一致。新key/未成功才比较捕获subject/team/data_role/auth_version；历史成功重放按当前身份与当前范围，不要求旧auth_version或旧配置继续有效。
2. 全部当前启用且READ_VERIFIED的META_BM来源按全局UUID顺序当前共享锁读取，核唯一来源恰为捕获ID/revision，businessId/graphVersion精确相同且密钥密文仍存在；不解密、不因READ_VERIFIED标签产能力权威。
3. account clock共享锁并执行原dueguard；新登记才要求等于捕获clock。M1捕获和M2登记均已改为当前managed_teams显式FOR SHARE锁读及应用层逐账户交集，不再依赖nested EXISTS在旧RRview里的结果。历史重放仍执行dueguard，不能拿未来转属尚未追平时的旧owner当当前范围。
4. 全部捕获账户按UUID当前共享锁集合读取；租户、revision、owner/team、external ID、未解绑精确一致；应用层用当前本人/显式managed team/SUPER规则逐项重核范围，不由客户端冻结owner决定权限。
5. 此阶段唯一合法动作是accounts.sync；不叠加read，也不扩大到launch.edit/execute。未来launch双方读取链必须单独确认。

M2锁序为auth→配置globalUUID→account clock→managed当前集合→排序账户→原始registry幂等/明细。M1捕获与现SYNC仍为auth→account clock→账户→配置，尚未统一。M2只持共享源/账户锁且不升级账户锁，但不能由此宣称整个未来系统无死锁；不得将M2嵌入已先持账户UPDATE/launch head的未知外层事务。合法调用起点及与现SYNC/config更新的真实并发必须在主线045专项证明；非法倒序1213由外层整笔回滚，不能部分成功。

## 主线已确认的6表与幂等合同

拟6表：原始头、逐账户、逐资源、独立审计、outbox、幂等ledger。头保存tenant/主体与auth/scope来源、配置ID/revision/BM/API版本、捕获/观察窗口、三个内容根、请求数/字节数及账户/资源计数；账户保存revision/归属/external ID与完整小metadata/unknown/bm_edges；资源保存kind/external ID/name及行hash。索引按tenant/account/observed_at/registry定位最新观察，不维护“最新身份能力”投影。

幂等绑定tenant+actor+operation+key_sha256，intent为同一Prepared规范根。旧成功键始终先当前accounts.sync及全部原账户当前可见性，不因source disabled/newrevision、账户revision/clock或捕获auth_version变化而重绑历史raw证据；该回执不授任何能力或执行权。只有新key/未成功请求才完整核source/account版本CAS。samekey异根在当前原账户范围后返回409；不能借换成一组可见账户查询原不可见成功意图。并发fallback遵同一动作/范围规则，不因普通早期probe建立旧RRview而错失已提交成功者。

公共事务只重试1205/1213，不自动处理1062。采用主线确认的完整ledger预留：预生成registry UUID与确定receipt，当前动作与范围核验后、版本CAS之前INSERT ON DUPLICATE KEY UPDATE仅key=key，再SELECT FOR UPDATE比根/registry_id；该时key必定存在。已删除missing key的提前locking read，避免两首登记者都持共享gap后竞争插入。普通早期probe命中时仍可直接当前范围复核后重放；probe miss后upsert锁等待最终读到成功者也走同一历史重放。本次新UUID才要求来源/账户/授权版本CAS并写完整head/details/audit/outbox。没有NULL/BUILDING可提交状态，没有全租户registry clock。为避免前向插入循环，ledger不建registry→head FK；其余明细/audit/outbox有同租户FK。方法错误必须由调用方回滚整个外层事务，不能捕获异常后提交孤立预留。真实双事务竞争仍须主线验证，纯顺序测试不是“无死锁”证据。

重放不只检查头：实际账户集合必须与Prepared精确相等；读取MySQL JSON后重新规范化，核每账户全部字段与row_hash；资源按PRIMARY键集每200行当前读，逐项重算正文hash、比完整预期集合/数量及总规范字节，不抽样、不只信保留的旧row_hash。原observed根在prepare时完整流式重算；结合逐项精确比对可以发现头不变但明细缺失/篡改。JSON展示空白不影响规范比较。201资源纯例证明第二页最后一项也被检查，但不冒充实际SQL索引或容量验收。

候选045增加12个DB guards：head/account/resource/audit任何UPDATE/DELETE拒绝；ledger DELETE拒绝、UPDATE仅全列NULL-safe一致noop；outbox DELETE拒绝，UPDATE仅同tenant/event/created且PENDING→DONE或同state。保留未来dispatcher正常ack，但本阶段无发送器。测试库的损坏注入如需移除单个guard，必须明确记录且finally恢复；不能把业务修改原始证据视为合法路径。

审计/outbox独立，不调用account_access.event，不能递增账户clock让刚登记的CAS立即失效。原始头/全部小行/ledger/审计/outbox同事务成功，任一1644或约束失败整笔回滚。未知持久化结果须保留同key/原Prepared重查，不能改key猜成功。

## 验证与交付清单

- [x] 主线确认完整ledger预留、历史成功原回执优先与6字段安全回执。
- [x] 已实现独立Registry；主线采用正式045六表/12guard迁移，真实DDL与本节限定的业务专项通过。
- [x] M2专属47项、M1专属34项与原observer65项合跑146/146通过（1.21秒），Ruff与格式通过。覆盖issuer/三个根、无Token、名长null/4096、UTC微秒和计数、批次字节边界、来源/归属漂移、当前managed、历史重放及并发miss后成功协议、动作撤销、dueguard、完整预留后才locking read、明细缺失/损坏和全量键集；包括上述3种微秒值新登记及历史回读共6例。session/SQL/授权均为替身，不是实际RR/原子性/容量证明。
- [x] 主线真实045首档20/20通过，10.21秒，其中14项为本模块专属，其余为初始化。回执为`evidence/python-meta-observation045-http.json`。覆盖完整六表写入、源/账户/clock版本CAS、历史成功当前授权与范围、同key异根、审计与outbox的真实1644全回滚、双首probe实际并发同key唯一结果、原微秒精确回读、12guard及合法outbox确认、M1旧RRview下撤管理、受控单guard移除后的损坏failclosed/恢复、无账户clock或023写入。
- [ ] 源与SYNC等所有合法/非法锁序的系统性并发矩阵、500账户/大量资源容量尚未完整实测。双首probe实际并发通过只证明该用例，不证明所有路径无死锁。
- [ ] 独立真实Meta连接：仅获得对应权限/设备后验证；未测不阻断上述内部协议开发，不冒充内部fixture为真实平台能力。

保留期限、配额/租户容量和受控清理尚需决定。本阶段无自动定时采集、无后台无限留存循环；即使045内部协议验收通过也不能开放生产预检或广告执行。

真实专项的来源边界：两个账户由隔离UUID库SQL技术fixture建立，READ_VERIFIED为受控测试SQL状态；配置经真实API加密，M1执行真实SQL捕获，网络使用MockTransport完成50次受控Graph GET，真实Meta平台请求数为0。以上结果不证明Meta令牌权限、BM业务归属、资源可投、生产能力发行或执行权威。
