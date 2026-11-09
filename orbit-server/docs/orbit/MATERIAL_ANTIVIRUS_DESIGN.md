# 素材真实病毒扫描接入方案与分阶段证据

## 原始语义与当前缺口

原合同 `data/ORBIT_Codex开发PRD/contracts/WORKFLOWS.md:27` 要求顺序 `INITIATED→UPLOADING→SCANNING→PROCESSING→READY`；`reference/03_原合同保留章节.md:74` 明确上传后先病毒与媒体校验，再处理至可用。

此前Worker在claim时直接推进PROCESSING，媒体处理成功即READY，没有真实病毒扫描。旧媒体/权限/租约/浏览器证据不覆盖完整READY。现已实施下面的扫描阶段与证据代码，真实Worker/SQL专项待主线排队，不能只据单测结清缺口。

## 定点集成改动清单

1. 新 `material_antivirus.py`：固定可信本机ClamD适配器，流式扫描、严格协议/限额/证据校验；不从请求接收地址、端口、路径或跳过参数。不安装服务、不修改系统PATH。
2. 新独立迁移（编号待主线分配）：不可变扫描证据表，记录tenant/asset/claim、原文件SHA256及字节数、引擎版本、实际加载病毒库版本/时间、扫描起止UTC、结果CLEAN/INFECTED/UNVERIFIED、受控错误码和配置证明摘要；不存原文件、原始扫描输出或服务器路径。成功证据必须绑定当前原对象hash/size及本轮claim，不能借旧对象/旧任务结果进入READY。
3. `material_worker.py`：claim只将job置RUNNING，asset仍SCANNING。锁外真实扫描；只有完整CLEAN证据落库且claim/asset revision/hash/当前身份复验成功，短事务推进PROCESSING，再媒体处理，最后复验后READY。INFECTED进入QUARANTINED；超限、超时、过期病毒库、不可用、未知/截断协议明确UNVERIFIED并失败，禁止预览发布/READY。限额类启发式FOUND视为未完成扫描，不能冒充真实感染或CLEAN。
4. recover覆盖SCANNING和PROCESSING的RUNNING租约，旧claim扫描/处理结果不得复活。重试必须新claim并重新扫描；撤权、停用或归档时不继续发布。原对象保留和审计策略继续生效。
5. `material_references.py`：不再硬编码未扫描，而是核对绑定当前原对象的完整扫描证据。证据无效即拒绝新分配/执行；释放旧引用不受新扫描门禁阻止。媒体/能力/权限仍分别验证。
6. 主线负责公共可信配置、fixture ClamD注入与runner；产品默认无扫描器配置即fail-closed。既有HTTP/视频/浏览器工具必须明确注入真实测试扫描器，不能加“测试默认CLEAN”绕过。

## I/O、协议及时间边界

只在可信对象resolver与同对象mutation guard下打开原文件；1MiB有界读取、累计hash/size复核，扫描使用流式INSTREAM，不把本机路径传给ClamD。单连接单对象，无无界并发或IDSESSION队列；扫描前版本检查与扫描后的版本/证据匹配不能省略。数据块及错误响应都不进入日志。

协议使用NUL分隔命令，块长为网络字节序4字节，最后空块结束。只接受完整唯一成功记录；ERROR、超限、未知、缺终止符、额外结果、响应超长、提前EOF全部失败。响应限额建议8KiB，连接超时2s，单socket操作最多10s且服从总monotonic绝对deadline150s；不能通过少量持续回包无限延长。扫描+媒体处理上界应低于现5min任务租约；媒体现有最长60s，仍需整轮总耗时测试。超过绝对deadline立即关闭连接，不等待无限后台线程完成。

ClamD配置不能只从VERSION推断：必须由主线管理、校验实际配置和进程来源，证明StreamMaxLength与MaxFileSize至少覆盖524288000字节，MaxScanSize有界且不会把合法原对象静默跳过，AlertExceedsMax开启。数据库年龄须按实际加载库时间检查，不以下载文件mtime或TCP健康代替。健康失败/配置未知/旧库不应继续SCANNING→PROCESSING。

## 验收顺序

- [x] 官方二进制来源、签名与病毒库来源由主线核验，固定隔离fixture manifest记录三库SHA和官方GPG指纹；不是生产配置。
- [x] 协议纯测试30项通过；Worker事务控制纯测15项通过，refs含新门禁56项通过；合计当前素材独立纯测202项。回执 `.runtime/material-antivirus-unit.xml`。
- [x] 真实adapter内存3项：PNG为CLEAN、官方无害标准测试串为INFECTED、冻结hash失配为UNVERIFIED，`evidence/python-material-antivirus-engine-adapter.json`。测试串未写入本机对象或文件。
- [x] 真实500MiB有界INSTREAM与超限1字节拒绝，独立容量复验2/2通过；仅协议流范围，首轮未知失败保留，不能替代HTTP/视频/磁盘吞吐或整进程峰值验收。
- [x] 真实Worker6组局部通过：SCANNING保持到真实CLEAN再PROCESSING/READY、未配扫描器及过期库失败、双阶段过期租约拒旧回写/恢复、真实1644审计拒绝时证据与状态一起回滚。来源为整轮失败回执 `evidence/python-material-antivirus-security-attempt-01.json`，不能称整轮通过。
- [ ] 实际文件感染端到端隔离（当前感染检测只在内存实际引擎证明，Worker隔离分支纯测）；更多归档竞争与容量仍另验。
- [ ] 既有素材13新引用专项/生命周期66套餐与三视口重新验收；旧媒体证据只作历史，不继承扫描通过。

## 当前实现与排队边界

026新增不可变扫描证据表；Worker显式接收scanner，未配置时Unavailable，不存在本地/测试默认CLEAN。claim时保持SCANNING，扫描证据短事务持久化并复验当前claim、对象hash/size、revision、身份后，才推进PROCESSING。record_scan与finish都拒绝已超过5min租约的回写，恢复覆盖SCANNING/PROCESSING且更换claim。refs读取同对象、当前DONE job同claim的完整CLEAN证明；旧READY没有证明时返回UNVERIFIED，登记活跃引用409；合法释放不依赖扫描状态。

专属真实工具已升级显式注入scanner；视频child仅接收JSON安全可信policy字段。新 `material_antivirus_worker_checks.py` 的6组实际SQL/对象/Worker专项已局部通过，尚未完成整个C套餐回归；测试作业created_at明确设为2000以优先处理本轮安全对象，不把它称为队列公平性证明。原refs fixture也升级为实际安全PNG对象与真实扫描Worker，另保留legacy READY拒登记分支；升级后13组局部通过，原27/27只代表更早权限合同，不能直接继承为扫描证明。

### 实际回归失败与修复记录

首轮refs-only缺独占对象root为主线fixture初始化失败；第二轮真实AV3与Worker6局部通过后，refs回滚组仍断言旧元数据fixture的outbox基线1，升级真实扫描后实际应为3（PROCESSING、READY、REFERENCE_ADDED各一）。修复为严格基线3并核对实际audit动作各1，回滚后outbox必须精确不变，不移除回滚断言。

后续C47实际44项通过/1失败/2未跑，AV3、Worker6、refs13、legacy前6组均局部通过。失败为错误CSRF预期403，原通用签名Token解析返回400 TOKEN_INVALID；仅素材适配器新增统一verify_csrf把该确切错误转403 CSRF_INVALID，其他403/503原样保留，上传snapshot和所有素材写操作复用，不修改公共Token类。新增4项纯测通过；当前素材217项纯测、前端20项及vue-tsc通过。真实403与后续引用/归档/回收/RUNNING及集合隔离仍待整轮复验。

legacy消费者门禁已统一到 `material_security.py`：旧READY不生成preview_url、预览与编辑拒绝、同hash不允许无证据去重，缓存READY/dedup重放复核当前安全状态。独立security集合最多200规范CSV，详情读取、重扫{reason}+If-Match/幂等/CSRF/assets.upload+scope为登记的技术扩展，不污染原Asset结构。新UI一次集合读取安全状态、旧READY显示待复核，编辑关闭、详情可申请重新检查。权限扩展4组独立工具已准备，未执行。

### C51真实回归通过（不代表整项目完成）

`evidence/python-material-antivirus-security-scope-http.json` 实际51/51通过，含AV真实内存3、实际Worker6、引用13、legacy消费者8、安全scope4及主线初始化/人员/配置夹具。此前错误CSRF403失败已复验；真实list与get的旧READY preview_url均为null，直接预览/编辑拒绝，同hash新上传真实扫描，三个缓存重放路径拒绝，重扫原因/原文件hash/版本/CSRF/活跃引用/归档/物理回收/RUNNING门禁、同团队普通用户范围及队列后撤upload均实际验证。

该51项不替代新AV下原完整素材/视频/生命周期套餐与浏览器；大对象500MiB、实际感染磁盘原文件、正式扫描器配置与进程代际证明仍未验。当前217项素材纯测、前端20项及vue-tsc通过。详情已补刷新安全状态并用epoch阻止迟到回写，新独立安全浏览器三视口和legacy fixture已准备，尚未执行。

正式配置不能把policy SHA字符串当作ClamD有效限额的协议证明。受控进程管理需绑定真实启动配置、进程/实例代际与可信策略；同端口重启成同版本病毒库但不同限额必须识别为未验证。现隔离fixture记录不是生产配置验收。

### C92整轮失败与安全浏览器定点修复

`evidence/python-material-all-security-browser-attempt-01.json` 保留整轮失败：90项后台实际通过，原素材浏览器三视口全部通过；新增安全浏览器三视口均停在重扫响应等待，退出检查未执行，整轮不能记为通过。真实开发代理请求包含 `/dev-api`，新增用例的裸 `/api/v1` 路径谓词没有捕获已经发出的请求。

这90项已包括两组真实ClamD+MySQL内存感染Worker专项：`pythonMaterialActualEngineMemoryWorkerInfectedQuarantinesWithoutCallingProcessor` 与 `pythonMaterialActualEngineMemoryWorkerReceiptCannotBeReplayedOrBecomeReferenceable`。实际处理器没有被调用，状态持久为QUARANTINED、没有预览/CLEAN资格，旧claim回写与分配均拒绝且原收据保持不变；无害标准测试串只在内存，不证明HTTP上传或磁盘感染文件流程。500MiB实际INSTREAM两组不属于这90项。

定点修复仅更新新增浏览器用例的响应匹配：必须为 `https://app.fixture.example` 同源POST，路径精确匹配 `/api/v1/assets/{id}/rescan` 或 `/dev-api/api/v1/assets/{id}/rescan`。独立匹配器9项纯测覆盖正确代理/直达路径及错误方法、来源、协议、前后缀、ID与非法URL；素材前端合计29项纯测及vue-tsc通过。POST202、真实CLEAN、安全预览、角色权限断言及默认60秒/零重试保持不变。新安全三视口定点真实重验待主线执行；本次纯测不能替代浏览器验收。

第二次真实定点回执 `evidence/python-material-security-browser-attempt-02.json` 仍失败，已走过真实POST202。刷新每轮清空详情，测试点击后立即读取，导致20秒轮询持续只看到抽屉标题；同时页面刷新缺少明确加载提示。已定点补独立刷新路径：保留已有元数据，显示加载提示和禁重复按钮，递增epoch并释放旧预览，防止迟到响应覆盖；测试每轮等待同一素材真实安全GET200及界面加载结束，再核对CLEAN。原CLEAN/预览/权限断言和超时均保留。当前38项前端纯测与vue-tsc通过，第三轮真实新三视口待主线执行；前两次失败回执保留，不能合并抹去。

### 500MiB独立容量首次失败

`evidence/python-material-antivirus-capacity-attempt-01.json` 首次实际500MiB流专项结果0/2通过，AssertionError；第一次回执只保存异常类型，尚不能定位为扫描耗时、协议或工具断言问题。随后仅在专属容量工具补固定字段诊断：结果、受控错误码、耗时、源打开次数、实际已读字节与最大单次读取，不输出流内容/连接/路径/凭据。产品扫描超时和断言均未更改。

后续 `evidence/python-material-antivirus-capacity.json` 诊断复验实际2/2通过：完整524288000字节INSTREAM，最大源读取1MiB、1.273秒返回CLEAN；超限1字节在客户端拒绝且未打开源，固定本机进程PID/配置/exe前后保持一致。首次失败已另存attempt01；扫描器源码没有改变，首次原因尚未重现，不能称已修复根因。通过范围仅本机真实ClamD的有界虚拟流，不扩展为500MiB视频上传、媒体解码、磁盘感染流程或整进程峰值内存验收。

### 联合浏览器attempt03失败

`evidence/python-material-six-browser-attempt-03.json` 中旧素材三视口实际通过，新安全三视口未通过。desktop/mobile已经过真实202与CLEAN刷新，预览尺寸断言的浏览器evaluate误用了Node闭包fixture，现改为显式传入宽高。wide在素材挂载前失败，现有快照仅img、没有足够网络诊断，不能声称已证实权限或组件根因；新用例补登录后真实壳与菜单挂载同步，再保留整页导航与原5秒标题断言，并增加仅路径/状态/资源类型/错误类型的失败证据。待主线真实联合六视口复验，不以这些测试修正声明功能通过。

### 联合六视口最终限定通过

attempt04中新增安全三视口已通过，旧素材wide/mobile通过，旧desktop在登录资源加载阶段60秒失败；该父轮失败仍保留。随后主线定位并修复测试HTTPS网关在accept线程握手导致闲置预连接阻塞资源接收的问题，增加两组真实TLS空闲连接回归；未延长用例超时或增加重试。

`evidence/python-material-six-browser.json` 最终实际六视口全部通过：原上传/处理/分类标签/编辑/归档三视口与新增历史READY→真实重扫202→CLEAN→实际预览尺寸/编辑恢复三视口；宏7/7，51.97秒，browser unexpected/skipped/flaky均0。attempt01至04失败继续保存，后台90组证据仍引用原父轮而不伪称本轮重新执行。正式生产runtime/030尚未接入验收，500MiB HTTP视频/磁盘吞吐及整进程RSS仍未验。

## 直接依据

[ClamD协议](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)说明流式块编码、结果记录及流总限额；[扫描文档](https://docs.clamav.net/manual/Usage/Scanning.html)提醒TCP无认证，并区分客户端与守护进程的配置职责。限额/过期库等实际默认值以本机已校验1.5.4包的 `conf_examples/clamd.conf.sample` 为准，不能仅沿用网站或旧版本默认值。
