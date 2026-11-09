# 可信扫描profile、实例绑定与正式租户消费者

## 当前状态（2026-11-08）

030持久证明、真实runtime→Worker→统一CLEAN门禁已接入；034正式租户扫描配置消费者、候选及安全PNG测试、完整配置版本CAS、同事务来源绑定和配置UI也已接入。当前不是“只新增独立runtime、不修改Worker/配置”的阶段。

最新配置证据 `evidence/python-material-scanner-configuration-scope-browser.json` 为40/40 PASS（34.99秒），包含原10配置组、12新范围组、USER8/元数据/初始化/退出和新配置实际3视口；新影响提示已实测。旧配置原11类62字段 `evidence/python-configuration-existing-browser.json` 另7组及实际3视口PASS（151.31秒）。边界54项Python/21项前端纯测与实际固定中文HTTP/UI分开记录；完整解释及保留的首轮失败见 `MATERIAL_SCANNER_CONFIGURATION_DESIGN.md`。此前92/92六素材UI、69/69引用安全/存储Worker证据仍按各自源码快照保留，不能据此省略本次新增来源消费者实测。

正式受控launcher、多进程registry与生产profile发布仍未完成；每应用默认空registry，未受信发布时继续Unavailable。本轮引擎为显式本机隔离实例，并非生产部署、外部环境或实际daemon更换验收。配置之后停用/换代不暗加历史扫描读取TTL，已完成证明不回写；新在途任务按当前配置/来源失败关闭。

以下为按阶段保存的设计和实测沿革，历史“尚未执行/未接入”措辞只说明对应当时的阶段；当前状态以本节与最新具名回执为准。

## 信任来源与边界

唯一配置来源沿用 `config.orbit_runtime.private_values()`，由指定私有 `.env.local` 只读加载 `ORBIT_PYTHON_` 命名空间。新增 `ORBIT_PYTHON_MATERIAL_SCANNER_PROFILES` 为服务端JSON注册表；最多16个profile、总JSON最多256KiB、拒重复键及未知字段。租户系统配置只保存profile ID，不能提交host、端口、PID、路径、可信摘要、有效期或跳过扫描开关。

注册表必须由可信运维/受控启动器登记实例出生证明，不允许从当前端口、PID文件或VERSION自动生成“可信”记录。证明包含profile revision、随机instance ID、固定PID和进程创建微秒、exe/config/三病毒库SHA256、精确启动命令、loopback端口、证明签发/到期时间及来源摘要。证明最长24小时，签发前或到期后均拒绝。更新profile需要新revision，旧消费者不静默切换新端口或信任新进程。

启动证明的根可信来自只能由服务端管理员维护的私有配置。此runtime验证证明与实际进程/文件是否一致，不声称能抵抗已控制同一OS管理员/私有配置的攻击者，也不把文件mtime单独当成实际加载配置证明。受控启动器本身的发行、最小权限与部署属于主线后续接入，不由本模块安装系统服务。

## 每次扫描的验证顺序

1. 重新读取可信注册表，profile必须仍启用、revision/instance/来源完整等于构造时快照；未配置或来源过期返回受控UNVERIFIED。
2. 校验本机进程PID、创建时间、exe路径/指纹、精确唯一 `--config-file` 参数及仅固定loopback监听。文件路径必须是服务端固定绝对路径，逐级拒符号链接/Windows reparse point；有界流式复算固定exe/config/库摘要，不读任意用户路径。
3. 配置文件必须与证明摘要相同，禁止Include及关键选项重复；实际端口、数据库目录、MaxFileSize/MaxScanSize/StreamMaxLength/AlertExceedsMax必须符合ClamdPolicy，不以VERSION推断限额。
4. scanner专属runtime子类在每个真实TCP连接建立后，校验服务端已接受连接的反向四元组属于同一固定PID/进程代际。只看LISTEN前后快照不足以排除临时端口替换；有限接受等待不能超过核心绝对deadline，无法取得OS连接归属即失败，不回退为仅PING/VERSION。
5. 保留原核心真实流扫描、扫描前后VERSION及hash/size校验；完成后再次验证注册表、实例、文件与来源。任何变化把结果覆盖为UNVERIFIED，不保留CLEAN资格。

不缓存“曾经连接成功”作为可用证明。运行时证明/文件校验与扫描均在任务事务外完成；短事务仅登记结果，不持数据库锁进行文件/进程I/O。

实现使用ContextVar为每次调用绑定同一个150秒绝对预算，前后来源核验、有界文件哈希、每个连接的接受确认及核心流扫描共享剩余时间；迟到结果不能保持CLEAN。单次OS文件或进程观察调用若被内核阻塞，不能据此承诺线程可被强制终止；返回后仍复核绝对预算，Worker外层租约/调度资源约束在接线窗口单独验收。

## 030持久证据与接入门禁

独立追加表把原026 receipt精确关联到tenant/asset/receipt/claim，保存profile ID/revision、instance ID/证明摘要、exe/config摘要、来源摘要、实例创建时间、证明签发/到期、实际前后验证时间。禁止原对象路径、命令原文、连接凭据、扫描报告或全配置入库。原 `policy_sha256` 继续表示原配置证明，不能重解释为实例摘要。

030先为026追加唯一候选键 `(tenant_id,asset_id,id,claim_id)`，再用四列外键确保实例证明绑定同一收据的同轮claim；不能分别命中两条历史行。026原迁移文件不改，不回填旧证明。追加索引的实际DDL/约束回滚与EXPLAIN由接线窗口验证，目前尚未执行030。

新增runtime返回原ScanReceipt及独立RuntimeScanProof的显式结果对象；未接线前不能直接替代现scanner而丢失proof。主线窗口需要：Worker显式接受新结果、record_scan复核proof绑定本轮receipt/hash/claim并同事务写030、CLEAN消费者统一核030与对应026。旧receipt没有030不自动回填或获得新生产CLEAN资格；重新扫描需真实原文件与原有权限/版本/原因/幂等合同。

## 独立验证计划

纯测覆盖：可信配置缺失/重复键/未知字段/超长、租户输入不能扩端口路径、来源过期/未来、profile替换、PID重用/进程重启、exe/config/库变更、启动命令偏差、监听偏差、建立连接归属错误/未知、扫描后证据变化均fail-closed。连接/文件/时钟使用明确注入观察器的纯测不冒充真实OS验收。

真实验收须主线串行运行固定本机受控实例：先正常PNG、再真实停止/更换实例或配置的受控负例，证明重启旧profile不能通过；不得停止现预览或影响其他服务。正式生产配置/启动器接入前不勾选部署验收。

## 当前独立代码检查与待排工具

`python/tests/test_material_antivirus_runtime.py` 36项纯测实际通过，与原扫描协议30项联合66项通过；Ruff检查/格式通过。覆盖profile与实例/来源/文件/限额/建立连接归属门禁及统一绝对预算。以上包含明确注入的观察器与进程模型，不能计为真实OS或030数据库验收。

`tools/material_antivirus_runtime_checks.py::run_material_antivirus_runtime_checks(cases)` 已准备6组固定本机工具：actual PNG CLEAN、三个真实accepted连接固定PID、profile revision/PID出生时间/config期望摘要/证明过期负例与前后固定实例保持不变。工具只读主线固定fixture清单并显式provider，不读取任意ENV或路径，不修改实际配置/停止引擎；负例是profile期望漂移，不冒充真实停止替换进程或文件变更。由主线排队，当前尚未执行。

后续主线已真实执行，`evidence/python-material-antivirus-runtime.json` 6/6通过：真实PNG CLEAN，三次accepted连接逆四元组确认为固定PID所有，前后实例保持不变。profile版本/PID出生期望/配置摘要/到期负例均fail-closed；这不是实际重启或修改共享引擎，也不是030 SQL/Worker持久化/HTTP/生产启动器验收。psutil7.2.2由主线登记依赖；本轮源码继续冻结，下一共同窗口接030与Worker，不扩大独立扫描功能。

## 030独立持久层待真实SQL排队

`material_runtime_store.append_runtime_scan(session,claim,result,profile)` 要求调用方显式外层事务。身份授权复验后，按material clock→job→asset顺序锁定当前任务；复核claim、拥有者/团队、对象hash/size、SCANNING版本、物理LIVE和五分钟租约。profile与RuntimeScanProof的所有来源/实例/版本/摘要/时间字段必须一致，原receipt的policy_sha仍等于config SHA。用真实数据库UTC_TIMESTAMP(6)校验时间，并在锁等待后再次核对expiry，避免旧时间放行。

首次登记同事务追加026收据、030证明、包含实际reason/必要差异的审计与outbox，clock加一；方法不更新素材状态、不生成预览或授予READY。由后续Worker窗口负责状态迁移。receipt/event ID按tenant/asset/claim确定；相同完整结果重放不重复事件或水位，不同结果拒绝修改。现存026无030时拒绝补票，不能借新profile升格历史收据。收到过期/未知/字段不符数据仅拒绝，不把错误转换成CLEAN。

35项新纯测通过，与runtime36和原协议30联合101项通过；该证据不替代真实事务/FK验收。专属工具 `run_material_runtime_store_checks(admin,database,cases)` 准备11组真实SQL：实际PNG扫描后原子双表/审计/outbox、无READY提升、精确reason、重复与双事务并发幂等、冲突/claim/代际拒绝、过期租约、审计1644回滚及重试、旧无proof拒绝、同asset两条不同收据的claim交错四列FK1452，以及实际数据库UTC过期拒绝。构造第二条UNVERIFIED元数据仅作为FK反例，不称实际扫描成功；所有原引擎保持不变。当前工具冻结待主线through030排队，不自行启动共享服务。

主线已执行 `evidence/python-material-runtime-store-http.json`：新增11/11通过，含常规回归总184/184、113.32秒；101纯测另存通过。真实结果只覆盖独立持久层，未接Worker发布/HTTP消费者或生产profile设置；030与独立store检查点已随ccbb5594推送。

## 下一最小Worker接线方案（待共同窗口）

1. 保留 `MaterialWorker.record_scan(claim, result, *, profile=None)` 作为事务入口，新增显式RuntimeScanResult/profile分支；run_once在扫描及来源读取期间不持数据库锁，得到结果后将同次当前可信profile快照显式传入。不可把RuntimeScanResult强制解包成ScanReceipt而丢失proof。
2. 真实RuntimeScanResult有完整proof时，record_scan在同一已有外层事务调用append_runtime_scan；返回首写/重放身份后再以原claim/revision做SCANNING→PROCESSING或失败/隔离状态CAS及原事件。store不commit，任何状态/审计/outbox失败回滚026/030及状态；重放不能再次推进版本/发重复事件。
3. 默认Unavailable仍返回明确UNVERIFIED并持久失败，不要求伪造runtime proof。普通ScanReceipt的CLEAN与有缺陷proof的RuntimeScanResult不能再进入PROCESSING/READY；转为明确UNVERIFIED失败事件。真实INFECTED可以进入保守隔离，但没有完整运行proof不能获得可执行资格。外部真实故障收据仍可记录026失败，不能通过补票030升级旧结果。
4. 当前授权失效仍走原terminate逻辑，不借新helper改变身份锁序或恢复旧任务。profile/source读取在事务外；事务内只复验预先构造的可信快照及SQL当前UTC、claim/CAS。store需在最小窗口拆出“已锁claim”的内部复用点，避免状态CAS后重读SCANNING失败，也避免两次独立事务。
5. 026消费者统一收紧在shared clean_scan_predicate：同当前DONE claim、同原文件hash/size的CLEAN收据，必须有同tenant/asset/receipt/claim的030证明，配置SHA一致、扫描起止在证明有效窗口内。列表/详情/预览/编辑/去重/缓存重放/引用分配共用，不逐行查询030；旧026没有030显示待重新检查，不能静默回填。
6. 时间语义建议明确区分：可信来源过期禁止新的扫描/登记，030保存扫描当时完整证据。已完成且对象不变的历史扫描是否因profile随后到期/轮换就强制全库重扫，属于新的有效期策略，不能暗中用读取时now<expires让所有READY每天失效。当前建议读取核扫描当时有效性；如主线决定更严格的扫描结果TTL，需独立系统配置、状态提示、重扫任务及容量验收。

主线公共依赖：提供服务端当前profile registry快照读取器，以及租户启用/选择profile ID的配置消费者（可选ID来自服务端允许列表；不开放端口/路径/PID/摘要/跳过开关）。选择配置在扫描前后重验版本，禁止关停后再启用让旧扫描结果借新版本发布；SQL选择行锁顺序必须在material clock之前。若需把租户配置ID/revision持久化为独立来源维度，应另分迁移号追加，不能重解释030中的server profile_revision。

主线测试引导需把完整runtime fixture/profile明确注入当前素材HTTP/Worker/视频child/三视口；仅传ClamdPolicy不足以取得030资格。原实际杀毒证据仍保存为历史，但不继承为新强门禁通过。先跑独立record_scan原子性/重放/缺proof/撤权与状态审计回滚，再扩实际HTTP、引用、视频child及六视口。该方案确定时尚未改共享入口或生产Worker；后续实现阶段见下节。

## 最小核心已落盘，定向真实Worker待验

共同窗口已实现上述最小核心，未修改公共app/harness或生产配置。MaterialWorker增加同步/异步 `runtime_profile_provider(claim)`，扫描前后取得当前TrustedRuntimeProfile并与固定scanner.profile完全一致；缺失或变化不授予资格。record_scan显式支持RuntimeScanResult/profile，在同一事务追加026/030后进行状态CAS及事件；raw CLEAN或缺proof无法进入PROCESSING/READY。finish在发布前再次核当前claim的030资格，堵住旧PROCESSING无proof绕过。

统一SQL谓词迁入 `material_antivirus_sql.py`，原clean_scan_predicate委托新实现；列表/详情/预览/编辑/去重/重放/引用继续走同一集合门禁。030必须四列关联同026并匹配config SHA、扫描当时issued/verified/start/end/expiry窗口；不使用读取时当前时间作全库TTL。

素材全体292项纯测实际通过（2.59秒），定向135项通过；这些控制流/边界纯测不代替真实扫描接受验收。新 `run_material_runtime_worker_checks(admin,database,object_root,cases)` 七组工具使用固定真实runtime和安全PNG/真实Pillow，准备验证READY链、raw缺proof、无provider、profile后变、状态审计1644回滚、重放、旧无030拒绝finish。父runner需through030和本轮独占对象root，当前冻结待排。

原store11工具的历史反例改成“原对象已真实扫描、显式seed旧026/PROCESSING而不写030”，因为新Worker已经不能把raw CLEAN推进PROCESSING；保留所有11条断言。新工具源码须真实复验，不能继承旧184组结果。生产租户profile选择消费者与HTTP/视频/浏览器fixture升级仍待后续窗口。

主线已完成 `evidence/python-material-runtime-worker-http.json` 快速24/24通过，包含新版store11、真实Worker7及6组初始化/退出，11.53秒；scope明确不是完整后台回归。首轮183通过/1失败/7未跑属于主线未创建object root导致KeyError，Worker7当时未执行，失败attempt01保留；修复独占root后复验原18条业务断言全部通过。最小核心真实链已局部验证，旧素材HTTP/视频/浏览器和生产配置尚未升级复验。

## 旧素材/视频/浏览器工具已升级，尚未整包复验

九个C专属工具/fixture已在批准窗口升级：material_checks、material_browser_fixture、material_reference_checks、material_security_checks、material_security_scope_checks、material_antivirus_worker_checks、material_antivirus_memory_worker_checks、material_runtime_fixture、material_video_checks。所有Worker正路径显式选择当前bound scanner.profile，手动record_scan传profile；缺引擎/过期库等原raw负例与用例数量保留。感染标准串仍只在内存，额外核对030完整行不可变；审计1644同时核026/030均无残留。

引用真实扫描现增加BOUND事件，回滚前outbox严格为4，BOUND/PROCESSING/READY/REFERENCE_ADDED各1；不是忽略额外事件。视频接口唯一调整为 `run_material_video_checks(...,ffmpeg_bin,*,runtime_profile)`，由固定可信 `material_runtime_fixture_payload(bound_scanner)` 导出单profile JSON通过stdin注入，子进程构造ProcessBound与显式provider，不能再用裸policy回退。浏览器真实Worker线程复用相同显式provider，原六视口业务断言未修改。

Ruff九文件通过，视频子进程脚本实际compile通过；未自行运行共享引擎/数据库/浏览器。主线下一串行组装新bound scanner给所有Worker路径，raw scanner仅保留引擎协议3与独立容量2。旧90组与六视口、视频/安全等全部需在新门禁下真实复验，旧通过证据继续作历史，不能继承为本轮验收。


## 新门禁完整复验结果（2026-11-08 17:13，北京时间）

上述旧工具现已按030精确关联真实复验：`python-material-runtime-full-browser.json`92/92、134.22秒通过，包含真实PNG/MP4、协议3、runtime Worker、感染内存标准串、租约/回滚/恢复/竞争/分类/安全及六项浏览器流程，0skip/flaky。`python-material-runtime-reference-http.json`69/69、17.74秒通过，包含完整引用/安全范围及新版store11/Worker7，不继承旧90/51/六UI证据。另主线292项素材纯测2.62秒通过，全Python1329项31.51秒通过，均有固定源码回执。

这些结果结清当前显式注入固定runtime fixture的内部链路；生产租户profile选择配置消费者、受控启动器、真实进程替换负例、外部对象存储及完整500MiB HTTP/视频/RSS容量仍未验收。实际source/profile策略变化不得补造旧证明，生产默认缺配置继续fail-closed。新032分配不得以旧026或手写READY素材充作可执行证明。
