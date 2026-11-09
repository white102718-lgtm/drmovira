# 正式租户扫描配置与受控启动器

## 当前状态（2026-11-08）

第一阶段正式租户配置消费者已经接入：`MATERIAL_SCANNER/profileId`、034租户单例与030来源外键、受控候选、实际安全PNG只读测试、配置版本前后CAS、正式ConfiguredMaterialWorker同事务来源绑定，以及前端选择器/影响提示均已有实现。原11类62字段保留，新增后为12类63字段。

| 真实证据 | 本轮实际结果 | 可据此说明的范围 |
| --- | --- | --- |
| `evidence/python-material-scanner-configuration-scope-browser.json` | 40/40 PASS，34.99秒 | 原10配置组、12新范围组、USER8及元数据/初始化/退出、浏览器汇总全部通过；实际新配置3视口通过，包含当前影响文案 |
| `evidence/python-material-scanner-configuration-http.json`（主线原19组回执） | 19/19 PASS，10.45秒 | 原10组配置HTTP/SQL/实际PNG/正式Worker、FK/成对NULL、审计1644回滚及精确重试 |
| `evidence/python-configuration-existing-browser.json` | 7/7 PASS，151.31秒；实际3视口 | 原11类62字段、凭据保持/替换、已提交响应丢失后同键重试、历史及迟到读取竞态保留通过 |

最新40组范围包含TEAM与SUPER+动作、同Token动作撤权403、身份停用401 SESSION_REQUIRED、真实跨租户配置隔离/FK、无配置/停用/空registry实际Worker失败关闭、真实扫描后withdraw/republish、A→B→A完整revision拒旧结果、停用配置后既有CLEAN历史证明不回写。finally的SQL身份还原只是夹具清理，不代表正式停启身份生命周期可让旧Token复活。

**尚未完成：受控启动器、生产正式profile发布、多进程registry架构及生产外部验收。** 每应用默认空registry，没有服务器明确发布的可信实例时仍Unavailable。本轮显式隔离registry指向同一已核验本机引擎；内存publish换代和第二别名不代表实际daemon替换，更不是部署或正式环境验收。

边界纯测另计：配置/范围专属54项PASS（0.75秒）、SDK/候选21项PASS（3.91秒），证明80个Unicode码点/NFC/控制符及availability严格类型边界。实际HTTP/三视口使用固定中文标签，不声称80emoji或非法字符真实UI验收。首轮3819驱动分类、旧user_fixture初始化和scope身份401预期错误的失败回执保留；未删断言、未放宽错误码集合或测试时限。

以下保留初始设计及逐阶段记录。其中“建议/尚未/待运行”等是对应历史阶段的状态，以本节当前结果和具名回执为准，不再表示本文件仍为只读提案或034尚待分配。

## 初始设计记录：可复用位置

| 位置 | 已核对行为 | 本阶段复用与边界 |
| --- | --- | --- |
| `python/orbit_api/contracts/configuration-fields.json` | 系统配置section/字段白名单、类型、默认值、options、中文说明 | 增加一个技术扩展section；不开放infra字段 |
| `configuration.py` 的 ConfigurationWrite/parse_write/metadata | strict、extra禁止、未知section/字段拒绝；enabled为严格bool；settings仅str/int；reason必填 | 保留原请求结构与错误语义，不另造宽松扫描配置API |
| `configuration_routes.py` | 原若依认证；拒客户端指定tenant；If-Match、幂等、限额、原请求审计关联 | 增加受控profile候选读取；不得复用用户输入端口进行探测 |
| `authorization.py:require_configuration_access` | 31081/system.integrations.manage，且当前数据角色必须SUPER_ADMIN | 配置读取/修改/候选列表继续此门禁，不放宽给TEAM_ADMIN；素材操作者仍只需原assets动作 |
| `configuration_store.py` | 同租户行锁、CAS、幂等、审计/outbox同事务；修改重置UNTESTED；验证也递增revision | 配置版本作为扫描前后CAS输入；不能把verificationStatus当实时引擎证明 |
| `001_identity_configuration.sql` | 配置UUID主键，唯一(tenant,section,name)，允许同section多个配置 | 新扫描section必须显式解决唯一选择，不能随便取第一个enabled |
| 前端 `src/views/orbit/system/configuration/ConfigurationDialog.vue`、`validation.ts`、SDK | 元数据驱动字段及统一写入结构；当前select仅静态options | 为profileId增加受控候选选择，保留name/enabled/reason/If-Match；不展示路径/PID/摘要 |
| `config/orbit_runtime.py:private_values` | 只读固定`.env.local`，仅ORBIT_PYTHON_，禁dotenv插值、禁通用ENV回退 | 保持只读，不由启动器或配置页面写入/更新此文件 |
| MaterialWorker/runtime/store/030 | 显式provider、前后profile一致、真实进程/连接证明、同事务收据/proof/状态 | 新增租户选择上下文，不重解释server profile_revision或config SHA |

现有通用只读`/test`主要通过ModelConnectionProbe运行模型探测，不应把新增scanner section交给模型HTTP连接器。scanner探测需单独受控分支：当前配置/registry状态检查，加安全内存PNG实际扫描；释放数据库锁后做OS/引擎I/O，再按配置版本CAS写结果。只读验证不上传用户素材，不启动/重启进程，不代表广告执行能力。

## 租户可写schema

现已新增技术section `MATERIAL_SCANNER`，复用原ConfigurationWrite：

```json
{
  "section": "MATERIAL_SCANNER",
  "name": "素材安全扫描",
  "enabled": false,
  "settings": {"profileId": ""},
  "secrets": {},
  "reason": "配置变更的实际原因"
}
```

- `enabled`沿用顶层严格bool，不在settings重复定义。
- `profileId`为空或`[a-z0-9_-]{1,40}`；启用时必填，并须属于服务端当前允许列表。停用时可保留原ID便于审计，但不能消费失效/移除的ID。启用未知ID或请求包含host/port/path/pid/skip/token等字段明确422/400，不忽略。
- 无secret槽位；用户此前要求的GPT/Claude/FB等token继续在各自原section加密，本section不接收扫描引擎连接token或运维凭据。
- 该section每tenant只允许一条配置（包括停用行）；通过编辑profileId切换，不以可变name作为选择键。建议独立迁移增加只对该section生效的generated tenant列+唯一索引。其他BM/模型section仍可多条，不能全表添加(tenant,section)唯一约束。
- 若迁移前已经存在同tenant该section多行，检测并失败，禁止删行、按时间猜选或合并审计。

候选接口建议位于现`/api/v1/system-configurations`下的固定路径、注册在`/{config_id}`之前，返回`{items:[{id,label,availability}]}`。availability仅READY/UNAVAILABLE及受控原因，不含PID/路径/端口/命令/库文件/配置摘要。候选来自服务器允许定义和当前registry，不来自远程URL或客户端。获取候选不等于获得素材权限，也不自动启动进程。

现metadata的静态select options不能准确表示动态registry。最小兼容方案是profileId保留text字段合同，前端专门渲染受控候选选择器，后端语法+registry成员校验；无需修改所有ConfigField.type枚举。若新增动态option类型，须由主线统一SDK/metadata严格schema与旧字段兼容测试，不能只改前端。

## 唯一选择及版本来源的必要SQL

已落实 `034_material_scanner_configuration.sql`，包含：

1. 系统配置表增加上述scanner-only singleton约束及中文说明；索引可按tenant+section定位唯一行，禁`ORDER BY updated_at LIMIT 1`。
2. 030表追加可空`configuration_id`与`configuration_revision`，只为新扫描写入，旧行保留NULL不回填。约束两者同空/同非空，revision>0。
3. 配置表增加候选唯一键(tenant_id,id)，030用(tenant_id,configuration_id)外键防跨租户绑定。不能把configuration_revision外键指向可变的当前revision，否则正常修改会破坏历史不可变扫描证据。
4. 独立consumer在同事务核对配置行当前enabled/profileId/revision，再登记来源ID/revision。030的profile_revision继续表示服务器profile定义版本；两种版本不得混用。

新的正式消费者资格若要求配置来源证明，需由主线显式升级统一SQL门禁、对应旧030状态提示和完整fixture；旧030缺来源不能补一个当前配置ID就升格。当前固定测试provider证据也不能伪称有正式租户配置来源。

## 消费流程和锁序

1. Worker认领仍复用原素材任务授权快照。扫描前在短事务读取该真实tenant唯一配置，要求启用、当前版本有效；没有配置/停用/多行/未知profile/无可用registry均Unavailable，不能改用默认profile或上一租户结果。
2. 释放事务后，服务器selector从内存registry取对应bound scanner，形成不可变`SelectionSnapshot(tenant_id,configuration_id,configuration_revision,profile_id,profile_revision,instance_id,profile_sha256)`。snapshot不是请求DTO，不接受前端构造。
3. 锁外真实扫描。前后重读配置选择版本及registry/profile；切换、停用再启用产生的新revision、实例重启/来源过期都使旧结果无法发布。不仅比较profileId，避免A→B→A复活。
   现通用只读验证也递增configuration.revision，因此第一阶段采用该版本时，验证或仅改展示名同样会保守拒绝已在途结果，UI应说明需要重试。若需避免这种额外取消，应由主线另设只在enabled/profileId变化时递增的selection_generation并实测，不能暗中忽略已有revision变化。
4. 正式record_scan事务内顺序为：当前身份/素材任务授权共享锁→该配置行共享锁及版本CAS→material clock→job→asset→026/030→状态与事件。配置行锁必须在material clock前；不得通过现`ConfigurationStore.get/_row`不加区分地拿FOR UPDATE并在之后做引擎I/O。
5. 配置写入维持身份→配置幂等→配置行；配置写方不反向锁素材clock/job。回收/引用等素材写方不读取扫描选择配置，避免形成配置行↔素材clock环。
6. 事务内只读取当前SQL行及已构造的可信registry快照，不持锁读`.env.local`、校验大文件、启动进程或联网。registry实现需提供内存generation的无I/O复验；发生原子替换时让未提交的旧snapshot失败。
7. 状态/审计/outbox/新来源字段保持同一外层事务；配置行或审计失败整笔回滚。重复scan claim沿用原精确重放规则，不能借重放将旧来源替换成新配置版本。

范围保持已批准时间语义：来源必须在扫描和登记当时有效；配置以后停用或profile轮换，不自动改写已完成、同文件对象的历史扫描。新扫描/重扫受当前选择限制。若要“停用立即禁止所有已有素材预览/分配”或扫描结果TTL，属于额外业务策略，应明确实现及压测，不能暗中加读取时now<expires造成全库失效。

## 受控启动器：只读定义、内存登记

第一阶段明确单一服务端所有者，不把启动权放到租户接口：

- 定义只来自指定私有文件的ORBIT命名空间或主线显式测试provider。建议另用`ORBIT_PYTHON_MATERIAL_SCANNER_DEFINITIONS`区分固定启动定义与带PID的短期运行profile；若私有文件没有定义就Unavailable，代码不写文件、不修改通用ENV、不把本机fixture路径当生产默认。
- 启动定义固定profile ID、官方已核验发行来源/exe/config/库摘要、根目录、loopback端口、限额及并发上界；不包含用户可插值的shell命令。动态PID/create_time/instance_id/有效期由真实受控启动产生，不要求写回`.env.local`。
- 受控launcher只在显式本地生命周期入口运行，用固定参数shell=False启动自有子进程，Windows隐藏窗口；不安装系统服务、不接管/停止现有预览或任意同端口进程。端口已被未知进程占用即拒绝；没有“按VERSION相同就收养”路径。
- 先核固定目录/链接边界、发行/配置/三库指纹及有效期，再启动；有界健康等待核真实PID出生、精确启动参数、实际监听/accepted连接、VERSION与安全内存PNG扫描。全部成功后才原子发布内存registry新generation。
- registry记录不可变TrustedRuntimeProfile与来源摘要；发布/撤销/替换由launcher所有者控制，provider只读。当前runtime构造器接受显式values_provider，直接使用该内存注册表，不需要改私有文件。
- 进程退出、健康/来源失效、配置或库切换时先撤销registry，旧scanner前后检查必须失败；重启必须新instance_id与generation。只回收launcher持有且PID/create_time仍匹配的自有进程句柄，不能按端口或文件名杀进程。

第一阶段内存registry只在同一明确所有者进程有效，不能宣称已支持多个API/任务进程共享或跨主机。多进程部署需主线选择受控本机IPC/独立launcher或带认证的共享registry；不能让每个API worker抢同一端口，也不能仅因Redis有一条PID记录就信任。当前loopback+OS PID证明不适用于远程扫描地址，远程架构另行设计。

运行来源审计最小记录：profile/definition版本、instance ID、启动/到期、exe/config/库摘要、来源摘要及受控启动/退出原因；无环境、路径、原始命令或用户文件。可先由主线分配受控启动审计存储；内存来源丢失后不能凭旧030摘要恢复一个“当前可用”进程。

## 实施归属（初始分工记录，第一阶段已落实）

| 责任 | 最小变更 |
| --- | --- |
| 公共配置/严格合同 | 新section/profileId字段、singleton冲突码、受控候选与scanner只读测试分支；SDK/系统配置页专用选择器 |
| SQL编号 | singleton/generated索引、配置tenant候选键、030来源字段/外键/中文说明；必要启动来源审计 |
| 配置selector | 新内部SelectionSnapshot读取/版本锁/CAS，不借上传用户的system.integrations.manage权限执行后台读取 |
| launcher/registry入口 | 服务端显式生命周期与内存provider注入；不默认启动，不更新私有文件 |
| C素材核心 | 新选择snapshot参数、同事务来源绑定和统一资格门禁；不修改原policy_sha/profile_revision语义 |
| harness | 真实配置API保存选项、受控测试registry、配置切换/停启/审计回滚/隔离/跨租户与原全素材回归 |

## 最小验收顺序

先严格schema、未知字段/ID拒绝、SUPER_ADMIN+原动作、CSRF/If-Match/幂等与singleton并发；再真实配置消费者无配置/停用Unavailable、同租户选择、profile切换/停用再启用旧结果拒绝、锁等待跨expiry、来源字段与状态审计全回滚。随后验证受控自有子进程的真实启动/退出/代际变化，不停止当前共享ClamD做破坏性试验。最后跑实际PNG/MP4/引用/安全/内存感染/六UI并明确多进程与生产环境未实测项。

大数据性能沿用keyset/集合安全查询，扫描选择每任务只查一个tenant唯一配置，禁止每素材列表行读取registry或哈希病毒库。现runtime逐次真实hash的成本必须测量后优化；若未来引入不可变发行身份缓存，必须保留文件身份变更检测、受控切换撤销与真实连接PID检查，不能以缓存可用标志跳过安全证明。

## 第一阶段实施记录（历史阶段保留，当前结果见文首）

- 已实现 `MATERIAL_SCANNER` section，唯一公开字段 `settings.profileId`，无secret、路径、端口或PID输入。旧11类62字段保持逐项原合同；现在12类63字段。034通过生成列唯一键约束每租户一条扫描配置，停用行同样占用单例；重复现有行导致迁移失败，不能删数据自动合并。
- `MaterialScannerRegistry` 只接收服务端显式发布的 `ProcessBoundMaterialScanner`，每次发布产生新内存generation。候选接口为 `GET /api/v1/system-configurations/material-scanner-profiles`，仅返回 `items[{id,label,availability}]`，复用当前SUPER_ADMIN系统配置权限、拒绝指定租户/未知查询。缺省每应用空registry，未接正式启动器时不能伪造可用候选。
- 系统配置 `/test` 对扫描section执行实际固定安全PNG内存扫描，不创建磁盘测试文件；需完整RuntimeScanResult/proof、完整绑定校验、前后同一registry来源才可READ_VERIFIED。单registry最多一个探测，取消HTTP请求不提前释放仍运行的实际扫描线程槽位。失败不回显底层连接信息。完成复验沿用原权限/CAS/审计/outbox，并使完整配置revision递增。
- 正式 `ConfiguredMaterialWorker(session_factory,objects,*,registry=...)` 逐个任务按真实tenant选择单例，扫描前后比较configuration UUID/完整revision及registry generation。新快照在收据事务内锁同租户配置 `FOR SHARE`，再按原clock/job/asset顺序落026/030；034新增的configuration_id/revision与原收据、证明、状态、审计/outbox同事务。030旧来源NULL保持历史fixture含义，不补正式来源；正式Worker缺快照不得调用旧fixture模式。
- 媒体完成前复核配置版本、启用与实例generation，处理中变更不能发布READY。这里不检查“当前时间小于扫描proof到期”来为历史对象增加TTL，原有效期语义保持扫描/登记当时有效。配置以后变化不回写已完成历史证据。
- 锁内复验明确 `registry.verify(binding,source=False)`，仅内存实例代际和已经构造的profile，不读取私有文件、不做OS/网络/大文件检查；真实provider检查在SQL context退出后的扫描前后执行。纯测及真实工具均设置provider锁内调用即失败的guard。
- 前端系统配置弹窗新增候选选择器，无自由输入传输配置；候选未知/过期不可新选，读取失败保留已有选择，可显式刷新，有空态/失败态及响应epoch防组件卸载后的迟到覆盖。SDK对白名单与未知字段严格拒绝，不保存基础设施返回。

本阶段静态/纯测：素材与系统配置合计365项PASS（2.79秒）；前端相关4文件20项PASS；Vue类型、Ruff与定点格式检查通过。22项新增配置纯测证明边界行为，不是实际引擎或MySQL验收。

真实专项交主线排队：`tools/material_scanner_configuration_checks.py`，固定10个具名case，入口 `run_material_scanner_configuration_checks(client,admin,headers,database,object_root,cases,*,registry)`。要求独占本机UUID数据库、through034、实际可信引擎、父工具registry与HTTP应用registry显式发布相同固定profile；不需要HTTP测试修改端点。覆盖真实安全PNG探测、singleton、正式Worker来源、三处版本漂移、FK/成对NULL、审计1644全回滚与精确重试。真实SQL/HTTP结果尚未取得，不标已验收。

公共入口由主线接线：每应用 `app.state.material_scanner_registry`；实际后台运行明确使用ConfiguredMaterialWorker。受控launcher、多进程registry架构、生产正式配置、系统配置候选浏览器交互、HTTP500MiB/峰值容量仍未验收；当前不能把隔离fixture的显式registry发布称为生产启动器完成。

真实首轮 `python-material-scanner-configuration-attempt-01.json` 为16通过/1失败/2未跑：前三项元数据及前8组新增功能实际通过；第9组MySQL CHECK正确返回3819，但驱动映射为OperationalError，工具原捕获IntegrityError未覆盖。修复仅将捕获改为DBAPIError，并分别严格断言FK错误1452与CHECK错误3819，原持久化前后相等断言保持；第10审计回滚与最终退出未在首轮执行，不提前标通过。主线排原19计划复验，产品代码未因该工具问题修改。

主线原19计划复验19/19实际PASS（10.45秒），第9约束保持原数据、第10正式配置来源随审计1644全回滚/同收据重试不重复事件均真实通过。事务内provider调用即抛的真实record/finish guard同时通过；本结果仅覆盖本机显式registry、MySQL和配置HTTP消费者，非正式启动器或多进程registry部署验收。

浏览器专项已准备待主线执行：`tests/e2e/orbit-python-scanner-configuration.spec.ts`，一用例三视口，读取现有正式单例当前revision，实际候选、取消不写、同profile保存、真实PNG测试、历史与窄屏边界；不开network mock，不改变60秒/零重试。旧配置E2E保留原11类62字段循环及凭据重试/历史/竞态断言，显式新12类中独立检查扫描profile字段；扫描单例交新专项编辑，不在旧循环创建。当前仅类型/格式通过，尚无浏览器通过证据。

主线新配置浏览器实测 `python-material-scanner-configuration-browser.json` 为20/20 PASS（33.48秒），实际3视口全部通过，unexpected/skipped/flaky均0。首轮harness在用户夹具未准备时引用user_fixture产生UnboundLocalError，产品浏览器用例尚未运行；保留attempt01，修复只限制相应旧假设条件，产品断言、60秒及零重试未改。本结果证明新增扫描单例编辑与实际安全PNG测试UI，不能代替旧11类全字段浏览器复验；旧spec源码已保留并明确选择GPT默认类型，等待主线联跑。

另新增独立12组范围专项 `tools/material_scanner_configuration_scope_checks.py` 待真实运行；需原10组及真实USER8夹具，不新造人员目录初始化。计划实际检验TEAM/SUPER+动作、同Token撤权/业务停用、真实异租户SUPER不可读其他配置、异租户无配置Worker、停用/空registryWorker、扫描后withdraw/republish、A→B→A完整revision、真实异租户configuration FK与历史CLEAN来源不回写。负例全程不调用媒体processor；同固定引擎的内存registry换代不称实际daemon替换。工具执行边界13项纯测PASS（0.31秒），本12组业务范围尚未实测，不计验收通过。

范围首轮 `python-material-scanner-configuration-scope-attempt-01.json`：36通过/1失败/3未跑，前10组新范围负例均真实通过。第11组把整个业务身份scope停用错误地预期成动作撤权403；源码审计确认 `native_session._version` 先因scope.enabled=0拒绝原登录身份，`http_boundary.authentication_error` 对ORBIT接口明确返回401 SESSION_REQUIRED。只修工具为严格401/SESSION_REQUIRED、错误体仅code/message/request_id且无业务数据，诊断只输出(status,code)；原角色动作撤权403保持。18项范围工具纯测PASS（0.34秒），没有放宽401/403集合或修改产品。测试finally以SQL还原夹具身份不代表正式业务“停用后再启用旧Token可复活”，原身份生命周期版本逻辑及既有验收继续保留。第12组与新文案三视口待复验，不先标通过。

扫描配置弹窗另增加业务影响提示“保存或测试会更新扫描配置版本，正在处理的素材可能需要重新检查”，仅MATERIAL_SCANNER出现，其他配置不变；局部12项纯测及类型/格式通过。此前20/20浏览器仍绑定旧文案版本，需主线与范围12组一起重新运行三视口，不以旧截图覆盖新文案。

候选标签边界另已定点统一：服务端复用原short_text，NFC/trim后按80个Unicode码点计数，拒Cc/Cf/Cs（含DEL、双向格式控制、孤立surrogate）及行分隔符，原路径分隔符拒绝保留；SDK采用同一NFC/trim与码点计数，并显式要求availability是字符串枚举，不能通过String转换把`['READY']`冒充READY。配置/范围专属54项纯测PASS（0.75秒），SDK/候选21项PASS（3.91秒），类型/Ruff/格式通过。合法80emoji及非法控制字符是纯测边界，实际HTTP/浏览器仍使用固定中文受控标签，不能将二者混称“emoji真实UI验收”。新文案/边界与scope12组交主线同轮复验，其他产品逻辑、旧原始负例、引擎及SQL未改。
