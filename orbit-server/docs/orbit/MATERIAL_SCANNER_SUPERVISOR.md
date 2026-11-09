# 正式单 Worker 扫描生命周期：独立模块

## 当前状态

loader/supervisor 独立模块已完成真实隔离生命周期验证；现在新增 `material_worker_service.py`、`tools/run_material_worker.py` 和专属纯测作为显式一次/常驻入口，不挂 API，也不修改既有 owner/store/registry/Worker 或私有配置。构造没有读取 env、访问SQL或创建进程；所有生命周期动作都要由可信单 Worker 入口显式调用。

原生 owner 25/25 实际通过并已在 `6e8aa0ed` 推送，037 19/19 已证明持久协议。随后 loader/supervisor 实际通过24/24、20.85秒，证据 `python-material-scanner-supervisor-native-http.json`：原生19311 owner、真实037 sink、正式租户配置、实际PNG任务经ConfiguredMaterialWorker到READY及receipt/proof/source、停用后的拒领和自有清理全部验证，cleanup_complete=True；既有7492/19310/18080/18081不变。这些不继承为新CLI/常驻driver验收；新入口目前只有注入纯测，尚未执行或部署。

## 唯一私有加载入口

仅在显式调用 `load_owner_configuration()` 时导入并调用既有 `config.orbit_runtime.private_values`。继续只读指定 `D:/progress/adpulse-power-system/.env.local` 的 ORBIT_PYTHON 命名空间，禁用通用 ENV、第三方目录、数据库 STARTED 记录或请求体回退，不写入任何配置。

消费两个字段：

- `ORBIT_PYTHON_MATERIAL_SCANNER_OWNER_ENABLED`：缺省 `false`，只接受精确字符串 `true` / `false`。关闭时不解析 artifact 定义、不启动进程。
- `ORBIT_PYTHON_MATERIAL_SCANNER_OWNER_DEFINITIONS`：启用时必需，最多256KiB JSON、严格重复键拒绝，映射必须恰好 **一个 profile**。不默默截断多个候选。

映射键是唯一 profile_id，值必须精确覆盖现 `ScannerOwnerDefinition` 除 profile_id 外的全部字段：revision/label、六个绝对本地路径、exe/config/批准回执摘要、三CVD摘要映射、issued_at/expires_at、完整 ClamdPolicy、proof_ttl_seconds/startup_seconds/shutdown_seconds。policy 也要求完整既有字段，不能缺限额后采用宽松默认。拒未知 pid/端口连接扩展、相对路径、UNC、非UTC或无时区日期；名称/哈希/版本/源有效期委托既有定义校验，实际逐级reparse/文件hash仍在 owner 启动和监控中核验。

规范DTO按稳定数据库名称顺序、UTC、Paths计算来源快照摘要；只涉及这两个字段。无关JWT/其他租户配置变化不会使 scanner 失效。定义 revision 是服务端批准版本，不借用租户 MATERIAL_SCANNER 配置 revision；正式 Worker 仍由既有 selector 精确绑定租户配置完整 revision。

## 显式生命周期接口

```python
# 可信入口提供已有sessions/objects，不在模块内新建连接或发现路径。
supervisor = MaterialScannerSupervisor(
    registry=worker_local_registry,
    sessions=sessions,
    objects=objects,
    snapshot_provider=load_owner_configuration,
)
await supervisor.start()
try:
    # 单入口负责周期monitor与有界轮询；不得并发run_once。
    await supervisor.monitor_once()
    await supervisor.run_once()  # 固定一个任务
finally:
    await supervisor.shutdown()
```

未传 snapshot_provider 时使用纯内存 disabled DTO，**不会隐式读取私有文件或启用服务**。模块没有自动挂接API lifespan或默认后台调度；下节新增CLI是显式bootstrap，仍须主线审阅后独立真实验证，当前不是已运行的常驻服务。

## 新独立Worker服务与CLI

```text
python tools/run_material_worker.py --once
python tools/run_material_worker.py --serve --interval 1
python tools/run_material_worker.py --serve --interval 1 --cycles 2
```

以上仅接口说明，本轮没有执行命令。`--once` / `--serve` 必须显式二选一；interval 1—3600秒，cycles仅serve 1—1000，省略cycles的serve为显式常驻。拒服务器、DB、Token、凭据、对象或程序路径参数；参数错误只输出固定code，不回显误传的秘密argv。

CLI首先只读指定private_values并校验owner enabled。关闭时直接返回DISABLED、0计数、cleanup_complete=True，不初始化DataSourceRegistry、对象适配器、进程锁或信号。启用后仅用同一私有命名空间的MATERIAL_OBJECT_ROOT，LocalMaterialObjects验证已有目录、不自动创建任意对象根；然后使用固定 backend/.runtime/material-worker.lock、DataSourceRegistry.initialize(log_enabled=False)、session(log_sql=False)、同registry supervisor。

正式main在整个asyncio.run及其后台线程收尾期间持有固定本地进程锁，不删除锁文件；拒锁路径上的链接/reparse。一次和常驻共用该锁，不借用API leader、进程名或端口查找已有owner。SIGINT/SIGTERM只设置stop事件，退出时还原原信号处理器。

`run_material_worker_service` 保持一个run_once任务，同时用**独立monitor Task**默认每15秒复核；scan/process耗时时也能发现来源失效。停用、期限/来源变化、monitor异常、未处理异常或未知返回立即停止领取并以失败码退出，不吞错误再轮询，不自动重启/续签。停止信号只排空当前单任务，不能领取下一条；排空后该任务的READY/失败计数仍纳入最终安全统计。

正常返回的READY、QUARANTINED、UPLOAD_FAILED、PROCESSING_FAILED和STALE是已处理的单素材结果。serve会继续领取下一条，不重试同一个失败素材；累计failed计数不能让后续循环停机，防止坏素材导致全租户消费者停止。ready只统计READY，failed统计其余已处理结果（含并发过期的STALE）；这些都不会伪标素材可用。once处理这类终态后返回COMPLETED并保留ready/failed计数，代表本次操作完成，不代表素材成功。未知状态、缺字段、返回多于一项等协议异常仍失败退出。

服务保存精确monitor/active/shutdown及supervisor内部清理Tasks。退出先停止领取，结束monitor，再用supervisor有界shutdown排空/关闭；未结束、被取消或异常的Task/自有句柄残留不会报告cleanup_complete=True。清理不确定保持FAILED，保留Task引用，不dispose仍可能有在途SQL的registry；CLI返回非0，不将其改为正常STOPPED。monitor退出等待上界为source_seconds+120，shutdown等待上界为drain_seconds+2×cleanup_seconds+5；这些是保留后台动作的等待预算，不能保证OS硬挂起可强制取消。

正常IDLE/COMPLETED/STOPPED/DISABLED且确认清理返回0；失败或未知清理返回1；解释器中断/取消返回130。终端仅固定result/code、cycles/processed/ready/failed计数与cleanup_complete，不输出素材ID、路径、PID、网络地址、配置、数据库异常或凭据。只有确认清理完成才dispose DataSourceRegistry，之后才离开最外层本机进程锁。

启动顺序：读取DTO → 默认037持久sink → 同一显式registry构造owner → owner真实health/审计后publish → 再读DTO防启动期间换配置 → 构造同registry的 `ConfiguredMaterialWorker` → 允许领取。无 objects、来源变化、SQL/health/源错误均失败关闭，不构造可用Worker。

单个 supervisor 仅允许一次 start；重复start、运行后重启或失败自动复活一律拒绝。受控重启需要外层明确关闭并构造新生命周期实例，不自动续签proof/定义、采用别的端口或接管已有进程。

## 任务、监控和关闭

`run_once` 固定 limit=1，单实例并发调用立即拒绝，不排队覆盖 `ConfiguredMaterialWorker` 的租户快照。每次领取前重读相关私有来源摘要并验证当前binding时间/代际。取消等待方不取消正在执行的任务：用 shield 保留 `_inflight`，供退出路径等待；实际scan和媒体操作继续由原有来源/权限/租约门禁保护。

可信 driver 必须独立周期调用 `monitor_once`；该方法复验相关私有来源与既有 owner 的 OS/文件/期限。变化、进程失效、来源到期或异常立即停止领取、withdraw再关闭自有scanner。proof到期不自动延期，不把已有扫描历史CLEAN改成全库TTL；新任务保持Unavailable，直到明确新来源和受控重启。

正常 shutdown 先停止新领取，有界等待在途，再withdraw与关闭owner。默认排空180秒（可显式1—300）、单次清理30秒（1—60）、私有DTO读取5秒（1—30）；实际 owner stop 还受既有定义约束。超时不取消后台 scan/process，也不声称已清理：保留任务并报告 INFLIGHT_PENDING。owner.stop 本身用独立精确Task加shield，超时/取消仍保留原任务，避免其 to_thread 原生Job操作被取消后遗忘；后续shutdown等待同一任务，不按数值PID找进程。

状态为 NEW、STARTING、DISABLED、RUNNING、STOPPING、STOPPED、FAILED。失败锁存；即使后续句柄全部关闭也只返回 False，不把先前失败或审计丢失改为正常退出。owner stop 的审计失败可能留下历史 STARTED 阶段，该行不能证明进程仍在运行；当前不自动补造终态/补票，仍需明确运维协调。不会因为A→B→A私有定义还原就自动恢复。

关闭被取消时立即停止领取/withdraw，并保留明确后台清理Task。调用者必须在进程生命周期 finally 中持续处理其失败状态；本模块不承诺操作系统硬挂起能被Python取消强制解决，也不以kill进程名/端口代替自有Job。

## 进程边界

这是单进程单 Worker owner。API 的 `app.state.material_scanner_registry` 仍独立空；SQL STARTED、相同profileId、静态私有PROFILES或其他进程声称健康都不能复建API本地binding。API在没有明确远程消费者合同前仍候选空、probe Unavailable；不能宣称本阶段已完成跨进程UI候选与测试。

不自动挂若依 application_leader/Redis启动锁。该锁用于框架初始化，不等同于本地registry共享或扫描实例所有权。未来多进程部署需要另行设计安全候选目录/probe transport、来源绑定与实例代际测试；本模块既不实现RPC也不伪造共享内存。

## 验证边界与后续真实专项

专属纯测覆盖严格DTO/重复键/单profile/UTC/版本摘要、默认关闭零启动、owner审计后同registry构造Worker、重复start、并发run_once、取消保留在途、正常排空、排空超时、清理取消与精确stopTask保留、配置换代/停用/到期不复活、Worker错误、SQL审计失败、API另registry为空等。

前述独立真实链已由主线通过24/24；下一专项仅验证新的CLI/常驻driver：disabled零依赖、一次执行和serve有限轮次、耗时处理期间周期monitor、信号停止排空、锁竞争、失败/不确定清理退出码。仍要求固定UUID对象/配置目录、独占端口、13306 UUID库，保护既有7492/19310；不写私有env。新driver当前只有专属纯测，Windows原生、数据库、真实信号及多进程锁竞争必须另列证据，不能以此前supervisor通过替代。

## 新CLI实际专项工具（准备完成，尚未执行）

`tools/material_worker_cli_checks.py` 导出5个 `MATERIAL_WORKER_CLI_CASES`，入口 `run_material_worker_cli_checks(admin, database, object_root, fixture_values, cases)`。fixture_values必须是本轮ORBIT测试map，严格13306 UUID库和16379/15缓存；对象根为backend/.runtime/integration-objects/run-<32hex>/materials且初始为空。主线注册共享flag后人工审阅再串行执行，本子任务不自行启动真实子进程。

子进程固定Python `-c` wrapper，实际调用真实 `run_material_worker.main`。秘密及CLI参数只通过有大小上限的内存stdin传输，不写磁盘、不放argv或环境变量；wrapper代码本身固定。每个Python以hidden/suspended方式创建并先加入父工具自有kill-on-close Job再恢复；其中ClamD仍由产品owner创建自己的Job。本轮原官方包/manifest/三CVD只读，只有UUID配置/批准来源fixture目录新建；不冒充新增GPG验证。

五组实际计划：缺少OWNER配置的默认disabled（DB模块未导入、子孙进程0）；错误argv固定安全JSON且不回显惰性Token哨兵；真实once PNG→READY/030/034/037+outbox精确来源；serve持固定material-worker.lock时第二Python拒绝、未初始化DB/未创建第二引擎；serve有限两轮自然结束、自有Job/出生身份结束、原7492/19310不变。此处只测有限serve自然关闭，不发送Windows外部SIGTERM，也不称已验证graceful console/systemd停止；先前signal纯测也不替代外部验收。

stdout/stderr各最多64KiB，只接受固定code/字段/类型的安全JSON；未知日志不回显原文，直接失败。父工具每10秒输出安全phase/elapsed，工作总预算360秒、finally自有Job清理30秒；启动前要求6GiB可用内存和1GiB磁盘，运行低于3GiB停止本轮。只用保留的Popen/Job原生句柄清理本轮进程及子孙，不按端口/名称/外部PID终止；不确定时保留精确handle和UUID对象/数据库，只有实际确认后返回cleanup_complete=True。


## CLI最新真实回执（2026-11-08）

主线第六轮真实CLI专项24/24通过，耗时65.99秒（原owner持久层18组及本工具5组、退出检查）。先前五轮失败回执全部保留；最新通过不抹去失败历史。实际覆盖默认disabled无DB导入/无新增Worker后代，错误argv不回显，真实once PNG经ConfiguredMaterialWorker写入READY及030/034/037来源，固定本地锁阻止第二引擎，serve有限轮次自然关闭。所有自有Job、Python和引擎身份均实际清理，19311空闲，原7492/19310保护不变。

Windows启动Python时已有console host。实际PROBE保留descendant_count，不把1改为0：仅允许配置加载前baseline全为conhost.exe，main结束后完整PID+birth/running集合严格一致且无新增后代；Job关闭后再证明相同身份均结束。新增conhost、同PID换birth、baseline含Python、结束后残留ClamD均拒绝。此前“子孙进程0”准备目标据此细化为“零新增Worker后代、Windows既有console基线精确围栏”。

此回执只证明本机固定UUID夹具、指定原生发行来源及19311的CLI链路，不证明外部Windows控制台信号、跨机共享registry、正式服务安装或生产部署。有限serve自然退出与纯测信号处理不可称外部SIGTERM已优雅排空。
