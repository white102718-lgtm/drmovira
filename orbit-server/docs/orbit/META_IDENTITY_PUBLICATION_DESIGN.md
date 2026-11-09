# M3c：原身份快照的持久发布与实际消费闭环草案

本文件只设计，不修改冻结M1/M2/M3源码、公共入口、工具或迁移。目标是让已有`GET /api/v1/accounts/{id}/identities`返回有来源的原合同快照，并让现有页面实际消费；不再增加一个只会保存更多raw字段的旁路。配置主体匹配只是必要关系，不能被改名为资源授权、system user类型、能力版本或生产执行权。

## 当前已有证据与未交付边界

- M2、M3a、M3b组合31/31真实通过，10.16秒；`evidence/python-meta-principal045-http.json`。100次受控Graph GET、30次自有引擎网络无SQL/连接归还检查，真实Meta请求0。该原回执保留当时045 JSON BETWEEN的1235警告，不覆盖历史证据。
- 主线采用正式051单ALTER后，原31加051矩阵3组共34/34真实通过，10.46秒；`evidence/python-meta-receipt051-http.json`。4个有效边界、40个精确3819负例、SHOW WARNINGS无1235/转换警告、六表不变，原M2/M3重新验证。
- 上述只证明内部捕获、范围、CAS、绑定、持久事务与数据库边界，不证明真实Meta主体类型、Token scope、资产任务、资源可投或生产预检。023生产可信发行器仍未接。

## 原合同与现有消费者必须保持

原OpenAPI `AccountIdentities`恰四字段：`account_id`、`resources`、`capability_version`、`observed_at`。每资源恰五字段：`external_id`、`name`、`kind`、`usable`、`reason_code`；ID为1至64位数字文本，name为0至255字符，kind只有PAGE/PIXEL/APPLICATION，usable严格bool，reason为null或1至64字符。最多5000资源。不得添加principal/type/verified/policy/raw状态字段改变原DTO。

`account_identities_contract.py`校结构；`account_identities_store.py:40—70`核023 evidence的verified/complete/revoked、目标账户与配置revision、凭据已知到期、正文hash与观察时刻；`:187—272`发布历史、明细、head及账户审计/outbox。当前没有提供可信权威生产写入器，也没有浏览器可提交verified的接口。

现消费者已经存在：

| 消费者 | 当前行为 | 有可信完整快照之后 |
| --- | --- | --- |
| `accounts/AccountDetailsDrawer.vue:24—46` | 请求原GET，显示能力版本/观察时间、资源及可用原因；503明确错误 | 同路径真实200即可显示，不需要新菜单或假成功API |
| `launch/PlanIdentityBindings.vue:425—426、570—607` | 读取原身份API；usable=false禁选，保存前按kind/id/usable核对 | 可选择真实快照的可用PAGE/PIXEL/APP；不因可选就获得广告写权 |
| `account_details_store.py:406—409` | extended的identity_status/count/observed_at仍固定UNSYNCED/null | 需要独立批量真实读模型接线；不能仅发布023后声称18列已一致 |
| `launch_references.py:60—66` | 非空identity_bindings或profile_binding_ids统一503 | 必须分拆身份资源与Agent/profile依赖；有证据的非空身份可逐账户双方核验，未接profile仍503 |
| 原validate/execute AuthorityProvider | 正式来源尚不足，默认None失败关闭 | 另需目标组合/归因/策略/即时权限；不能以身份GET快照解除默认503 |

## 不同结论不能混为一个verified

1. M2登记证明原始读取包未错绑；M3b证明真实配置systemUserId与当次/me数字文本一致。都不证明其类型或资产任务。
2. 原身份快照的usable应来自“该目标账户在观察窗口中对该资源的基础可用性”受信判定。未知的权限、任务、字段语义或不支持版本必须503；不能把unknown压成false，或因资源存在、分配主体非空、can_post、ADVERTISE枚举出现便给true。
3. `capability_version`必须引用独立受控能力发行包，具有明确适用Graph版本、来源、发布/撤销和原始证据引用。不能填raw hash、配置revision、当前日期、Agent版本或自由字符串冒充。
4. `policy_version`不是原四字段的一部分。不能为了身份GET额外硬要求整个投放策略/指标模块完成，也不能在身份发布时伪造它。真实预检的policy、归因profile/精确attribution映射、placement/目标组合和执行能力由各自来源另行提供；缺失时对应validate/execute仍503。
5. 即便身份快照200、部分资源usable=true，它仍是观察结果；实际execute及每次外部发送必须另作当前caller/plan owner、目标账户资源和动作即时授权。主体匹配不能取代其中任何一项。

官方v25 SDK已核对的端点/类型见`META_IDENTITY_PRINCIPAL_BINDING_DESIGN.md`。权限页面/内部浏览器受阻只影响对应外部语义核验；没有出处的部分保持unknown。它不阻止下面完整内部发布协议、原DTO读取、RR/并发/回滚和UI真实联调的开发与隔离验证。

## 本阶段最小交付：直接实现发布存储，不再停在纯模块

建议下一次授权直接交付一个“单账户完整身份快照→023原GET→现页面”的有界闭环，先默认无Authority明确503，再通过严格隔离发行器验证真实SQL与HTTP；正式发行器需要的外部证据不足仅阻断正式生产正例。

拟接口是内部技术补充，不是原PRD新增公开写API：

```python
publisher = IdentityPublicationStore(authority=None)
prepared = await publisher.prepare(account_id, raw_registry_id, principal_match)
receipt = await publisher.publish(
    session, actor, prepared,
    expected_identity_revision=revision, key=key, request_id=request_id,
)
```

`prepare`没有数据库session/网络长事务，要求受控ABC `IdentityCapabilityAuthority`而不是caller的verified布尔：

- `capture(...)`事务外获取完整能力判定与实际来源证明，只返回白名单不可变对象；不把M3 facts直接改成Decision。
- `revalidate(session, current, prepared)`只锁/读实际发行源、撤销与版本，不在数据库事务中发送网络请求；必须先于账户/身份head最终锁。
- 正式TRUSTED必须有具体生产来源发行器、适用版本及可验证的源记录；不能仅设置kind字符串。默认None或缺权威版本返回503，023/审计/outbox/幂等均零写。
- ISOLATED_TEST只允许主线13306与UUID隔离库，并明确协议专用，不为真实Meta能力背书。该发行器输出的正例只验证本地完整协议，不注册到正式预览。

首闭环使用单账户原Bound，降低锁/网络范围；内部发布接受原合同最多5000资源，后续批量只能按账户拆任务，不改变单账户完整性。M3 collector单次选择上限500是资源选择数，不能被误解成500账户/完整5000库存已采集。生产读入若超过当前整体网络预算/完整采集能力，明确503，不截取前500后标complete；完整5000的真实容量需单独档，不用5000条DTO纯测冒充。

### 完整性、名称和时间是发布前置

- `resources`必须与绑定账户在完整raw库存中的(kind,id)集合精确相等。M3只查所选子集的结果不能覆盖head；未知或未核条目不得省略，空数组只能在该账户三种边完整且确实为空、能力发行器也确认完整时发布。
- 若provider分批捕获，必须有整体有界预算、完整集合/重复一致性与观察窗口；不同请求不是平台原子快照。每批配置/主体绑定不等于整个任务完成；中途失败不发布部分头。
- 每项name必须来自该实际资源可审计的合法值，null或超过255则该账户发布503；不将ID当名称、不截断、不从另一个账户同名猜测。原M3a/b4096/null测试资产应继续不能直接发布023。
- raw和事实原始时间为微秒，而023 evidence/history为DATETIME(3)，现`timestamp()/iso()`规范到毫秒。建议新增旁证保留原微秒与完整hash，另明确定义`UTC_FLOOR_MS_V1`投影用于023 evidence/history/body三者同一精确毫秒；这是待主线批准的内部投影规则，不改原proof，也不依靠MySQL四舍五入。`.123499/.123500/.999999`及跨秒须实际验证。若主线决定升级023时间列则另迁移并保持原响应兼容，不能两个口径混用。
- known credential expiry只有真实凭据来源证明才能填；PIXEL.user_access_expire_time不自动是Token统一到期。未知到期继续null，不发明身份快照5/15分钟TTL；原预检15分钟是另一合同。

### 最小持久证据与迁移需求（编号待主线）

建议只增加发布旁证和幂等ledger，继续使用023历史/资源/head及原账户事件，不再建一套“看似身份但原GET不读”的孤立raw仓库：

| 对象 | 必要字段/约束 |
| --- | --- |
| 发布旁证 | tenant/evidence UUID、account ID/revision、M2 raw_registry FK及账户/库存根、M3 source/facts/principal-match根、真实配置systemUserId/版本、能力发行源ID/version/hash/种类、原微秒窗口、023毫秒投影/正文hash、完整资源数、实际issuer来源引用、创建时间。只安全字段，无Token/任意URL/平台错误正文 |
| 发布ledger | tenant+actor+operation+key hash；完整intent hash、evidence ID、确定metadata receipt及原request_id。完整一次reserve/no NULL状态；不先对missing key SELECT FOR UPDATE形成共享gap竞争 |
| 023与读取补强 | 原字段/schema不变；新旁证与023 evidence/history同事务。原GET增加真实来源/撤销/旁证一致性校验；旧仅verified=true但没有新来源证明的记录不得回填猜测，需刷新/明确未核 |

实际能力发行表/发行维护权限与可验证FK仍需主线明确具体来源，不能先建一个任意JSON“authority”列让调用者自报。正式生产来源未定时TRUSTED路径保持503；隔离协议可验证明确标记的发行记录和全套外键/回滚。

旁证/正文只追加且有不可变护栏；撤销状态与当前head允许严格受控状态推进，不改原观察内容。每批≤100行及明确参数字节预算，按account/revision/kind/external_id覆盖索引读取5000明细；不能每资源N+1。保留、配额、清理需独立决定，不启动无限自动采集。

## 锁序、当前范围、重放与事务

建议统一合法发布方向：当前auth/auth_version→能力/配置来源全局UUID锁→accountclock **直接UPDATE锁**及dueguard→当前managed显式锁→目标账户UPDATE锁→幂等已存在行/完整reserve→023 evidence/identity head→有界资源/历史/旁证/审计/outbox。

该完整方向适用于新写入。早期成功probe可在auth后先作普通非锁ledger读取，但不得在当前对象范围核验前比较异intent或返回任何结果；命中走当前clock/managed/账户范围读取后历史metadata重放。miss走上述新写方向，不先持SHARE clock后再补来源或升级UPDATE。等待同key并发者时，应先取得规定来源锁但把来源版本/是否可新发行的判定推迟到完整reserve确认“本次新赢家”后；已成功者仍先当前动作/范围和原intent核对，不能被旧CAS或失效旧配置抢先屏蔽。整个路径需像M2已验证的双首probe反例实测，不依靠事务自动重试1062。

不先拿clock SHARE再升级UPDATE；现023 `publish(...write=True)`会取clock UPDATE，未来桥必须预先拿同模式避免升级死锁。现publisher随后重入账户/配置锁可以复用，但不得在head之后首次取得未持来源锁。实际最终锁图需主线与共享配置/指标源更新者统一后实测，不用注释冒充无死锁证明。

最终CAS必须覆盖：当前accounts.sync与目标账户范围、actor/tenant、启用身份与当前auth_version、真实唯一配置ID/revision/BM/API/systemUserId、已知来源撤销/凭据到期、accountclock和dueguard、目标account revision/owner/team/external/未解绑、能力发行版本/撤销、原raw/M3/正文所有根、expected identity revision。当前managed必须内层显式锁读，不能依赖在普通probe建立旧RRview之后的nested EXISTS。

现023 event会增加global accountclock。捕获clock是发布前CAS，不是发布后GET长期有效凭据；否则自己发布就立即失效。GET长期使用单账户revision、真实来源/能力版本、当前授权和已知撤销检查；不因无关账户event永久失效，也不漏当前转属范围。clock增加、023 head/历史/旁证/ledger/审计/outbox必须同事务回滚。

成功键重放建议先当前原动作与对象范围，再核完整原intent并返回原metadata receipt，优先于旧CAS；该receipt只表示历史发布已提交，不带旧resources/usable作为当前结果，不调用网络、不重新发行能力。当前GET单独按最新来源核验；配置失效后的历史receipt不能当现在可用。samekey异intent409；新key才重新完整来源CAS。此为待主线确认的内部技术幂等口径，不冒充原PRD已定义身份写API。

入口必须在必要时先探测成功重放，再调用可能无provider/网络不可用的prepare；未知提交结果需保留原Prepared与key，不能因重新prepare失败掩盖已提交结果。无成功记录时，缺Authority仍503且零写。此入口属于后续内部CLI/调用编排，不新增HTTP写后门。

并发miss使用完整ledger INSERT ON DUP key=key后现有行FOR UPDATE；多赢家只有一组完整快照，当前动作/范围在fallback仍重验。当前不可见404、撤权403、未知能力或来源503、CAS409均不写半成品。未知提交结果保留原key/prepared重查，不让Worker改key冒新成功。

## 从实际发布到页面消费的有限节点

| 节点 | 可以实现和真实验证 | 页面/动作的明确结果 |
| --- | --- | --- |
| C1 完整内部发布 | 明确Authority协议、单账户完整5000上限、实际SQL CAS/回滚/并发/原GET，无provider零写，隔离issuer完整正例 | UUID库可真实200并跑现Drawer/选择器；正式仍503，不称生产可投 |
| C2 最小正式资源来源 | 找到适用Graph版本的真实Token/资产任务证据，发行受控capability版本，至少一户库存全部能判定；真实凭据缺失只阻此生产正例 | 满足原四/五字段后现GET可真实200，Drawer与PlanIdentityBindings无需新菜单即可消费；unknown仍503，usable=false按明确原因禁选 |
| C3 引用与18列一致 | 共享身份readmodel批量当前校验、current caller+实际plan owner交集、保存原identity绑定引用/版本；更新extended真实计数 | 身份草稿引用不再固定503；Agent/profile_binding_ids未接仍单独503。不能为草稿额外强加execute权限或全部执行必填字段 |
| C4 正式预检/提交 | 分别接目标组合/MetricProfile真实归因/策略/作用域/完整物料证明及执行权威，冻结原完整树 | validate仅在所有实际来源齐全后200；execute保留原launch.execute/必要publish+ack，缺来源仍503，identity快照本身不打开执行 |

这四个节点有明确停止扩raw的界限。C1应直接落完整存储+原HTTP读取和页面联调，不再只交一个canonical纯函数；C2的真实权限页面/凭据阻断不能让C1的事务、读取、RR、回滚停工。C2也不能用ISOLATED_TEST值、全false或假capability版本来宣称完成。

## 建议文件所有权与主线依赖

- A新增：`identity_publication_store.py`（含最小Authority协议与发布流程）、`identity_publication_readmodel.py`（完整batch/来源验证），对应专属tests与`tools/identity_publication_checks.py`。避免先拆出更多只有纯函数的层。
- A经主线窗口解冻：`account_identities_store.py`仅接真实旁证/当前范围与安全读取；`account_details_store.py`仅接批量真实身份投影；现M1/M2/M3保持兼容冻结。
- B或主线：独立`launch_identity_references.py`与既有`launch_references.py`最小接线，复用当前caller/owner双主体规则；B前端选择器只做真实响应/错误呈现，不路由替身。
- 主线：分配新迁移编号、实际能力发行源/FK与维护权限决定、公共app/runner/发行Provider注入、隔离测试排队和正式缺省None。未经分工不修改共享文件或自行占迁移。

## 必须通过的开发/测试/验收清单

- [ ] 开发：完整原DTO+旁证/发行/主体/库存的不可变关系；无provider/未知任务503；单账户完整发布、稳定intent/receipt及原GET消费；列明所有原始未知。
- [ ] 真实SQL：当前撤权/配置userid变更/发行撤销/账户转属或解绑/clock与revision漂移；旧RRview撤管理；两首probe并发；expected revision竞争；actual1644审计/outbox失败全回滚；发布后自身clock+1仍可正常GET；源变更后旧GET失败而历史receipt语义不伪当前可用。
- [ ] 字段：完整空库存与selected子集严格区分、5000资源、长名/null拒绝、外部ID前导零、严格bool/DB非0或1值不靠bool()归真、完整正文hash与明细数量/来源一致；三个微秒边界精确投影与原proof不变。
- [ ] HTTP/页面：原GET严格四/五字段；无读权限403、跨范围404、无权威/未同步503；现Drawer及选择器实际三视口，无route.fulfill/SQL假名截断；usable=false禁选且原因可见，后台错不清旧来源提示。
- [ ] 引用：每账户/每广告组/主页覆盖local_id映射；caller与plan owner双方可读；capability版本变化要求重新核验，不把Agent/profile版本与资源能力混用；原launch动作权限不扩张。
- [ ] 容量：5000完整资源有界写/读与精确遍历、500账户批量读取无N+1、锁/内存/延迟实际量测；未跑不能标大容量通过。
- [ ] 生产有限验收：真实配置版本/Token/资产任务与适用能力发行证据齐全；外部凭据/官方页面受阻单列，不能因此声称所有功能或真实环境已验收。

## C1实际实现检查点（053主档已有限真实验证）

上述建议已由主线批准进入C1实现，技术幂等口径、三个必要表与显式向下毫秒投影已确认，不再作为待裁决的当前结论。原023及公开DTO不重写，旧手工`verified=true`且没有053旁证的历史行不自动升级为可信证据。

新增`identity_publication_store.py`与`identity_publication_readmodel.py`，默认Authority=None。Authority必须实现独立ABC的`capture(match,account_id)`和仅数据库来源锁的`revalidate(session,current,prepared)`；kind标签自身不构成权威。`capture`在`prepare`中执行，禁止调用方把正在持锁session传进去。正式当前没有生产Authority/发行器，因此仍503且零新证据；隔离Authority必须同时通过URL+SELECT DATABASE的本机13306/本轮UUID库护栏，且只能引用`ISOLATED_PROTOCOL`发行，不能被TRUSTED读取路径继承。原始Graph空capabilities、空assigned_users不影响隔离协议可测试性，也绝不被用于推导真实usable。

候选`053_identity_publication_provenance_candidate.sql`包含3表/6个DB护栏，主线已采用为正式053并通过真实DDL/主档：

- `orbit_identity_capability_release`：独立受控发行，明确issuer、source_kind/hash、tenant、META_BM ID/revision、BM、Graph版本、原capability字符串和只读action scope。publish不插入此表。正文不可变，只允许一次NULL→已撤销，不能恢复或删除发行。
- `orbit_identity_publication_provenance`：FK连接真实023证据/历史、045完整原始登记与独立发行；冻结raw µ秒/原bound及facts/principal完整根、配置主体值、正文根/完整intent根、`UTC_FLOOR_MS_V1`。禁止更新/删除。原raw库存不额外复制另一套档案。
- `orbit_identity_publication_ledger`：tenant+actor+keyhash唯一，预生成evidence UUID和完整六字段metadata receipt一次reserve，无NULL/BUILDING。仅全列完全一致noop，禁止删除；预留、023证据/历史/head/资源、旁证、原account_event/outbox和clock+1均在调用方一个事务。

Store公开调用：

```python
store = IdentityPublicationStore(authority=None)  # 正式缺省，不能自授
old = await store.successful_replay(session, actor, key=key, intent_hash=intent_hash)
# 旧成功probe只返回历史metadata，不返回旧resources；必须先当前sync/全部原账户范围。
prepared = await configured_store.prepare(match, account_id,
    registry_id=registered_raw_id, expected_revision=expected_identity_revision)
receipt = await configured_store.register(session, actor, prepared,
    key=key, request_id=request_id)  # 调用方commit后才可外显持久化
value = await IdentityPublicationReadmodel().get(session, actor, account_id)
```

`Prepared`重新核原M1/M3 issuer及完整事实正文根，不信保留hash；资格必须精确覆盖目标账户raw全部(kind,id)，不能把M3 selected≤500子集当完整库存，也不能把500选择限额偷换成原5000库存上限。完整库存中NULL或>255名称返回明确503，不截断、不用ID冒名。所有资源逐条资格由独立Authority捕获，不把非空ID/匹配/me字段映射成可投。

合法新写锁序为当前auth→全配置UUID/独立发行及provider来源锁→clock直接UPDATE/dueguard→当前managed显式锁→全部原账户UPDATE→完整ledger reserve及当前行锁→真实raw明细核验→023 head与完整版本→旁证/审计/outbox。来源版本错误在确认本次reserve为新赢家后才拒绝，以保持并发成功键优先。旧成功当前范围优先，源失效/旧clock不重新绑定历史回执。`successful_replay`允许进程重启后在无Authority时恢复metadata，但调用方必须保存原key和完整intent根；不同根409，不以新key掩盖未知结果。

当前GET先作不外显的来源探测。有probe则来源锁先于clock；随后当前授权范围、账户状态及current head优先，最后才判来源/发行是否有效。无probe不取空来源锁，直接clock→当前managed/账户，未知/越域404、授权但无head503 UNSYNCED、只有旧裸头503 SOURCE_RETRY。头并发切换到不同来源时拒503并在新短事务重试，绝不在持clock后首次补来源锁。严格验证完整资源数/原DTO/hash，DB usable=2在bool转换前拒绝，发行撤销、配置变版、主体不符、账户revision变化及已知到期立即失败。发布前clock不是GET永久版本，自己的发布clock+1不能使自己失效。

定向纯测当前55/55通过，Ruff通过。覆盖纯合同/发行隔离、完整库存与selected差异、原四/五字段、.123499/.123500/.999999向下投影、当前读来源重试/未知账户404、零Authority、当前动作优先、工具数据库护栏。它们本身不计真实SQL/Meta/浏览器验收。

### 主线真实队列接线

工具`run_identity_publication_checks(client,admin,headers,password,cache,database,cases,*,cipher=None)`，常量`IDENTITY_PUBLICATION_CASES`为12组。真实角色/配置加密API；SQL账户和READ_VERIFIED仅本轮技术fixture；Graph使用httpx MockTransport，独立能力发行SQL行明确ISOLATED_PROTOCOL。工具复用`prepare_plan_identities`的990360/990361，因此单独互斥档运行，不能同轮重复创建同一原helper。只主线已有13306/UUID库，工具不启服务、不读取其他环境、不发送平台写。

实际逐组范围：默认无Authority零写、完整原GET/原子旁证、三个µ边界实际SQL回读、旧成功源/clock/auth变更与重启probe、新keyCAS回滚、当前sync撤回/外owner404、actual1644审计和outbox全回滚、双首probe miss同key只有一组完整版本、未知/foreign/unsynced原GET、旧RR撤管理、不可变表与损坏usable精确拒绝、独立发行撤销后原GET503而旧metadata仍历史重放。主线实际18/18（12专属+初始化）PASS、10.94秒，证据`python-identity-publication053-http.json`，显式through46+051+053，已无旧045 JSON BETWEEN警告。仅本隔离协议原GET闭环，不勾选生产Meta/所有身份或容量/三视口。

首轮实际6PASS/1FAIL/11未运行保留`python-identity-publication053-first-failed.json`：真实RowMapping不能执行dict的`|`，故在调用validate_evidence实参构造前TypeError；定点改为`dict(config)|...`，对应纯fixture改成只有Mapping协议的锁读行，未放宽断言。该首失败使用through46+053未带051，旧警告作为历史事实保留；后续通过档明确加入051，不改045原迁移。

主线公共改动只需原`account_identities_routes.py` GET内部改调用新readmodel，不新增写路由，不给浏览器任意Authority/verified入口；无需在app注册新router。旧023协议夹具无053旁证应保持失败关闭，不能添加兼容放行。工具HTTPGET严格比较原完整正文，测试数据为完整C1协议来源。当前反向发行撤销后旧GET应503；若仍走旧readmodel返回200，专项必须真实失败而非放宽。

### 现有页面三视口的下一实际步骤

053 SQL+原GET主档已通过。工具新增可选`prepare_browser_fixture=False`，默认原12组不变；True在全部撤销负例后另写独立未撤销ISOLATED_PROTOCOL release与`isolated-identity-browser-v2`，实际新head revision6并原GET200，返回`browser_fixture={account_id,external_id,expected}`。仅该本轮UUID库浏览器窗口保留有效来源，最终由主线drop库；不能恢复已撤销旧release。新专属spec为前端`tests/e2e/orbit-python-identity-publication.spec.ts`（实际不存在tools/browser，沿现有命名），环境`ORBIT_E2E_IDENTITY_PUBLICATION_FIXTURE`传该公开DTO JSON，不包含Token。

spec沿真实登录/账户页，按完整外部ID筛唯一行，原18列保留；“详情→读取身份资源”精确同account原GET，核完整四/五字段、PAGE/PIXEL/APPLICATION、前导零、name、真实bool/原因、capability_version/观测时间；第二次刷新同DTO、关闭后原行innerText逐字不变。账户写请求与浏览器Meta请求为零，无route.fulfill。仅新spec Prettier/TS noEmit通过，三视口尚待主线串行。PlanIdentityBindings在真实引用窗口接好前不算选择器已验。列表extended仍UNSYNCED为明确未接缺口，Drawer显式读取成功不冒充列表同步完成。

旧`tools/account_identities_checks.py`9组是裸023 evidence与旧Store发布夹具，与新权威GET冲突；through46没有053时也不应返回旧伪权威200。三视口后需把原领域Store测试保留为明确历史内部协议、HTTP成功接力完整053 fixture并重新完整回归。此为内部待办，不是凭据外部阻断，不能通过兼容降级GET或删断言掩盖。

extended列表身份summary留独立批量接口：一次当前auth/managed+排序来源批量锁，按当前可读账户集合批量head/evidence/provenance/resource计数及根核验，不能200行循环get。未知来源对应UNKNOWN/UNSYNCED，不能把未接字段宣称SYNCED/0。该列表、caller/planowner双主体引用和生产权限producer仍未接，不因C1原GET通过而标全部身份功能完成。

已有051+M3组合有限证据为`python-meta-receipt051-http.json`实际34/34、10.46秒；4有效边界/40精确3819拒绝、无1235/转换warning、六表不变，原M2/M3重验。该证据未包含053，不改写045历史，也不证明生产能力或真实Meta权限。

### C1原GET与三视口后续实测回执

主线已执行`python-identity-publication053-three-viewports.json`：19/19通过，含原18组与三视口汇总1组，实际Playwright宽1920/桌面1440/手机390三项3/3通过；浏览器15.19秒，总86.67秒包括原登录限流窗口自然冷却59.62秒，没有清理限流键或提高阈值。上文“待主线串行”是当时准备状态，目前该有限Drawer专项已完成。

真实SQL保留原独立release撤销负例，随后另建未撤销的ISOLATED_PROTOCOL发行和真实revision6。原账户登录/18列过滤/详情Drawer/原GET四字段及逐资源五字段、版本/观测时间、可用bool与不可用原因、相同GET刷新、关闭原行不变、零账户写请求/零浏览器Meta请求均实际通过。它是完整内部发布→原HTTP→现Drawer读取的有限闭环；不包含生产Meta权限、真正第三方能力发行器、计划identity引用、列表summary或5000/500账户容量。原019以前的Java验收不复用，原023裸证据不自动继承。

当前053工具/spec与C1生产源冻结供检查点；后续先补完整空库存与5000明细边界的实际资格/SQL/HTTP，再迁移旧9领域/HTTP回归。原未完成清单仍保留，不把这次三视口提升为整个身份模块或投放执行验收。

### 完整库存边界实际结果与旧领域接力

主线已实际执行新增显式`include_inventory_boundaries=True`档，`python-identity-publication053-inventory-boundaries.json`20/20 PASS、12.45秒（原18+新增2，不把两组重复计为全功能验收）。常量`IDENTITY_INVENTORY_BOUNDARY_CASES`独立导出，默认原12不变；未改生产Store或扩大M3 selected上限。

同来源、同当前owner的独立anchor账户只提供/me配置主体核对的一项PAGE观察；目标账户实际全分页库存为0或5000，独立资格覆盖目标完整集合，明确断言anchor的ID009不进入目标资源。实际空库存原GET200严格四字段、resources=[]，HTTP163字节、13.6ms。实际5000目标PAGE由25个有界受控GET页获得，045原始登记与023/053完整发布/原GET逐项精确集合一致，响应544052字节；capture及原始登记1.044秒、身份发布0.729秒、HTTP83.1ms。以上各为本隔离SQL协议的一次实测，不称冷缓存、P95、生产Meta或500账户容量。

5001目标确实读到第26个受控页后由原采集限额`META_RECORD_BUDGET_EXCEEDED`拒绝，8个发布相关表、6个raw表、独立发行和clock全不变，零部分登记/发布；原已发布5000正文仍可读取。本档124个受控GET均通过自有引擎零SQL连接/事务检查，真实Meta请求0。不是用纯DTO长度测试代替完整采集/持久化边界。

旧`tools/account_identities_checks.py`迁移现已实现但待主线真实合跑：签名原10参不变，原9组领域get/publish的完整正文、撤销、来源/账户变版、凭据到期、tamper/late、审计全回滚、完整空集断言保留；领域读取改显式旧Store.get，不构造HTTP Response替身。HTTP无认证/权限/query/UUID/unknown/无head边界仍走原新reader；新增第10组`pythonAccountIdentitiesBareLegacyHeadCannotBypassPublicationProvenance`在裸023 publish后精确断言HTTP503 SOURCE_RETRY。审计异常仅接受实际DBAPI errno1644。首写之前要求053三表真实存在，不能在旧through46降级裸head权威200。

新原HTTP200成功语义由053原12+库存边界2完整fixture接力，主线完整A档只调用一次`prepare_plan_identities`，不覆盖既有native用户。主线要求023+051+053及原alias/worker依赖；当前旧工具专属9项护栏与C1共74/74定向纯测PASS1.02秒、Ruff通过，尚不是该完整A档实际验收。此回归接力为内部工作，不能归因缺真实Meta凭据而搁置。

主线随后实际完成through054联合A档67/67 PASS，回执`python-account-identities054-combined-http.json`，原领域/边界10与完整053/库存14均运行。上段“尚非完整A档”是准备时状态，现已有限实证；不将旧裸领域协议提升为生产authority。旧工具、053工具及测试当前冻结供后续固定回归。

### 下一摘要交付：速度与完整性方案对比（055尚未采用）

下一可见缺口为extended身份摘要原来硬编码UNSYNCED；单户C1及Drawer已真实通过不意味着列表、计划双主体引用已完成。主线拥有公共details/routes接线，A仅设计新`identity_publication_summary.py`/测试及055候选，不改冻结生产源。

A方案在当前页≤200个账户用一条PRIMARY范围流式资源SELECT、≤1000行缓冲逐账户重算原canonical SHA，校验source/proof/完整数量后才SYNCED。它避免200次get/N+1和客户端百万行载入，但最坏200×5000仍扫描百万行并长持来源/clock锁，不适合每次前台列表。保留用于原显式完整GET、后台完整验真或历史seal回填，不采用作列表默认捷径。

B方案以已完整验证并冻结的发布旁证为seal，只对既有provenance对应版本阻止023资源后插入/U/D，并保存独立有界摘要。必须同时解决：

- 每个资源写方先锁已存在history行，冻结状态在该行单调维护；不能对missing proof做逐资源FOR SHARE gap探测，避免不同合法账户/租户先共享同gap再各自插proof而出现升级死锁。合法新publish已有history→resources→head→proof顺序，history新行X锁贯穿外层事务；最终proof建立时设置内部冻结位，资源后写不可成功。旧bare历史保持领域兼容，存在历史proof仅先freeze，不自动认作已核seal。
- 冻结版本history/evidence不可改正文，已知撤销保持单调；protected head不可回退或删除，下一完整/裸新版本如何处理必须按当前provenance存在与否分类，不能把裸next head当SYNCED。055候选不能改已受测023/053原迁移文件。
- 独立seal表精确FK绑定原proof/history，DB current BI核真实资源COUNT≤5000、history/evidence/proof字段一致并禁止sealU/D。仅此COUNT不足重证损坏历史正文，原裸history.count不得直接复制为已验；新发布用已完整核验的Prepared根/数量，历史回填必须history锁下原完整GET SHA重验，坏行不发seal。
- 为识别直接SQL伪造seal，提议独立完整性MAC用途`IDENTITY_SUMMARY_SEAL_V1`绑定tenant/account/revision/evidence/proof root/count/source refs。它只证明完整性验真，不是Meta资格或新的业务权限；DB只存MAC，key仍主线ORBIT keyring，不写库/日志。缺key/坏MAC/撤销source/release均UNKNOWN/null。若不采用MAC，必须明确依赖“仅受控publisher可INSERTseal”的数据库权限约束，不能夸大为任意SQL伪seal也能识别。此处为初稿方案记录；主线后续已批准MAC及055候选，见下方实施状态。

前台目标为≤200来源/头/旁证/seal有界批量查询及MAC核验，不扫描完整resources，也不200次get；0只允许完整空库存seal，缺headUNSYNCED/null，缺证/坏seal/来源撤销UNKNOWN/null。观察时间仍UTC原身份时刻，不能套账户消耗日期/时区过滤。

公共锁序接点：主线专用list/details owned AsyncConnection在任何SQL前设置READ COMMITTED并绑定原session/Redis上下文，退出恢复隔离或invalidate；不SET SESSION污染池。auth后同selection/已验MAC的after预选前200候选，不外显；prepare普通head/proof probe→当前META_BM唯一来源与有序release锁→原account clock/reference clock/details watermark→最终当前范围页→resolve批量当前head/seal。票据绑定同session真实事务与actor/tenant。最终新页/新head引用未锁release时仅UNKNOWN/null或整页重试（主线决定），绝不持clock后补首次source锁。原RR普通probe可能建立旧readview，不能只给账户SELECT加锁而让金额/观测依然读旧快照；公共RC接线需并发观测与旧RR撤管理反例重验。

原无055路径的损坏usable真实负例仍必须503；055后同一后写变成精确1644、全状态不变而非删除负例；纯坏行读取验证继续保留。新摘要/055在初稿时尚未实施；当前独立实现及候选状态见下方，不受C1的67组结果覆盖。


### 055当前独立实现（候选，尚无真实SQL/列表接线验收）

主线已批准B方案及`IDENTITY_SUMMARY_SEAL_V1`独立MAC用途。当前新模块`identity_publication_summary.py`和专属纯测、新候选`sql-drafts/055_identity_inventory_summary_candidate.sql`已落盘；原023/053、C1 Store/readmodel/工具不改，正式迁移及公共RC接线由主线审核。当前只可称独立实现与纯协议验证，不是发布或列表功能完成。

接口：`IdentityPublicationSummary(cipher=None)`，`prepare(session,actor,candidate_ids)`、`resolve(session,actor,page,ticket)`用于同事务≤200列表；`prepare_publication(session,actor,prepared)`、`seal_published(session,actor,prepared,receipt,ticket)`预留后台同发布外层事务。prepare当前auth→有界头probe→唯一启用READ_VERIFIED配置UUID顺序锁→精确release UUID排序锁；不先拿clock。resolve重新当前read授权/显式managed及账户范围，原clock守卫不跳过，批量只读头/历史、证据、旁证、seal、raw头五类元数据，不读取resources，不对200账户逐个GET。新头或新页引用未提前锁的release仅UNKNOWN/null，不晚补来源锁。无head为UNSYNCED/null；只有完整空库存有效seal可显示0。

票据绑定模块issuer、实际session、真实外层transaction、actor、tenant/current context、动作和不可变捕获来源；不能跨事务/actor复用。当前source/release撤销、账户revision/状态/解绑、credential expiry、完整roots、原观察µ秒/毫秒映射均重验。当前clock只是串行稳定性与dueguard，不当作永久来源版本或代替每页授权。当前读取有锁而无长资源扫描；最坏百万资源的成本只可出现在后台显式完整验真，不能进入列表热路径。

后台接线须先调用原`successful_replay`，命中原成功直接返回历史metadata，不因新source版本强行重新封印。未命中才`prepare_publication`（只有accounts.sync，不借read）→原C1 `register`→`seal_published`→外层commit。该方法只允许本次当前head/完整Prepared根/回执版本相符，E→精确一个H锁后调用原完整`verify_history`核正文与资源根，再签seal。原发行/来源失效不生成成功摘要；无cipher默认不发seal，调用方不得把False视为已封印。当前尚未修改C1接入此wrapper，因此默认原publish只建冻结旁证、没有seal，列表保持UNKNOWN。

seal使用25个严格typed业务字段（含key_id）及schema_version1规范MAC，绑定tenant/account/revision/evidence/registry、source ID/rev、account revision、release ID/rev/root、原capability字符串、完整count、payload/intent/bound/principal/facts根、principal实际ID、authority_kind、UTC_FLOOR_MS_V1及原µ秒/毫秒/expiry。DB存key_id与MAC，不存密钥、不打印凭据。验证显式使用存量key_id：保留旧key可验证，未知或退役key只UNKNOWN/null，绝不按当前active key静默重签旧seal。该MAC只证明本系统曾完整核验并封印这些数据，不证明Meta拥有权、可投、policy/capability或写授权。

055候选为一张27列seal表（25业务MAC字段、MAC和created_at）、history内部单调freeze位、13个触发器：资源I/U/D锁已存在H并拒冻结后写；history拒冻结正文变更/解冻/删除；evidence冻结正文不可改，仅已知revoked_at从NULL到非NULL；protected head禁止回退/删；proof BI当前E SHARE→H UPDATE精确绑定并置freeze；seal BI按当前锁读精确P/E/H绑定并以PRIMARY资源游标逐行计数（≤5000），不以RR旧view的普通COUNT作保证；seal U/D拒绝。DB计数/FK/typed checks不能代替MAC或后台完整hash。旧proof维护回填仅freeze，绝不INSERTseal；已损坏旧正文不会凭history.count自动变可信。

合法发布均在原account write clock下，原C1在资源写入前已新建H并持X，proof最后只重入E/H锁。显式历史封印先E后H，避免与已知撤销E→H形成合法倒序。非法直接SQL可能先持资源行锁再等待触发器H，与封印H→资源冲突仍可实际1213整笔回滚；不声称所有SQL无死锁。候选DDL及backfill含隐式提交，必须维护窗口/应用启动前执行，不能假定在线部署无保护间隙。只读核现生产C1 register及旧AccountIdentitiesStore.publish均走account write clock；本轮未发现这两条正式发布入口绕clock，外部原生SQL不据此视为可信writer。

当前定向纯测65项（MAC全部字段防替换、µ秒投影、旧key轮换/退役、票据、当前动作/范围、来源撤销、新头未知、固定五批无resources、候选结构）通过；Ruff通过。纯替身不算SQL/Meta/容量。下一实际主线顺序：审候选并执行055→guard正负及并发/精确1644零变→同事务wrapper封印及原GET/摘要一致→公共RC列表/详情接线→旧RR撤管理和并发新obs反例→真实200×5000摘要容量。原无055损坏usable503回归保留；055后后写负例必须精确1644且全状态不变，不能删断言。生产issuer仍默认未接，真实Meta与计划双主体身份引用仍独立缺口。
