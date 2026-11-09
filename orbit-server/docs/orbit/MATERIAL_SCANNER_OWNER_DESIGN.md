# 扫描实例受控所有者：独立实现与待接入边界

## 当前状态

本轮仅新增三个服务端模块及两份注入纯测，未改已冻结的租户扫描配置、034、registry、Worker、应用入口或主集成工具。未启动、停止、迁移或接管任何真实进程。现有独立 ClamD 实例保持原状。

- [x] 独立单所有者状态机、固定文件定义校验、Windows Job 适配器源码。
- [x] 38 项注入纯测通过；Ruff check 与 format 通过。
- [ ] 真实 Windows Job、挂起进程归属、真实引擎启动/健康/停止验收。
- [ ] 指定私有配置加载、生命周期入口、持久化审计适配、退出钩子与周期监督接线。
- [ ] 生产运维部署、多工作进程统一 registry、容量与资源峰值验收。

纯测替换了全部 Popen、Win32、socket 和扫描健康行为。正向用例的 READ_VERIFIED 是显式注入的测试结果，不是实际杀毒或进程启动证据。固定伪 executable/数据库/批准回执仅是临时目录内的普通测试字节，绝不执行。

## 文件与最小接口

`material_scanner_owner_definition.py` 提供 `ScannerOwnerDefinition` 和 `verify_owner_files(definition, deadline)`。定义由服务端显式提供，候选租户仍只选择 profileId。定义包含固定安装目录、自有临时目录、exe/config/三 CVD/发行批准回执 SHA256、版本有效期和有界启动/退出时间。所有路径必须绝对本地路径，逐级拒绝 symlink/reparse、UNC、非普通文件和超限文件。

目前仅预留 `ORBIT_PYTHON_MATERIAL_SCANNER_OWNER_DEFINITIONS` 名称，没有读取系统环境或私有文件的自动回退。后续必须由主线从唯一指定 `.env.local` 只读 ORBIT 命名空间解析并显式构造，不能新增通用 ENV、租户路径或端口输入。

发行回执的当前含义是“可信供应流程已批准、服务端固定其摘要的文件”。本模块复验回执本身与相关 artifact 哈希，并不重新执行官方 GPG 验签，也不能把任意本地 JSON 视为官方证明。正式批准回执的解析/签发来源必须在接线时补齐。

配置只允许受控指令白名单；必须固定 loopback、端口、数据库、自有 TemporaryDirectory、Foreground、扫描限制、AlertExceedsMax 和有界线程/队列。拒绝 Include、LogFile、PidFile、重复和未知指令。程序不生成配置、不创建目录、不写入私有 env，也不更新病毒库。

`material_scanner_owner_process.py` 提供 `WindowsOwnerProcessAdapter`。所有原生操作延迟到显式调用，导入无进程副作用。Windows Job 使用 KILL_ON_JOB_CLOSE；创建失败不降级启动。Popen 固定两参数且 shell=False，先 CREATE_SUSPENDED，再将原生进程句柄加入自建 Job，最后用同一原生句柄恢复。stdin/stdout/stderr 为 DEVNULL，避免无界捕获子进程输出。无 PID 文件、端口扫描接管、按进程名终止或数值 PID terminate。

`material_scanner_owner.py` 提供：

```python
owner = MaterialScannerOwner(registry, audit_sink=async_persistent_audit)
await owner.start(explicit_server_definition)
await owner.monitor_once()
await owner.stop()
```

`audit_sink` 必须显式、可等待，持久化完成后才能返回。缺失或失败时拒绝发布。当前无默认数据库实现，主线需接入安全持久审计；内存测试 sink 不等价于持久审计验收。

## 状态与顺序

1. 单实例 asyncio 锁拒绝并行/重复启动；已有同 ID 公共候选也拒绝，绝不采用已有进程。
2. 校验定义、Job 支持、固定文件来源和端口预检，记录 STARTING 后才创建挂起子进程。
3. 保存 PID 与出生时间，Job 归属完成后恢复，校验仍存活。
4. 在**私有 registry** 内执行安全 PNG 的现有真实 probe。进程加载数据库期间，在同一个有界启动窗口内等待，只有真实 READ_VERIFIED 才继续；未公开任何候选。
5. 复验固定文件来源、PID/出生时间及定义有效期；持久 STARTED 审计完成后才发布公共 registry binding。
6. 停止、来源变化、实例代际变化或 proof 到期时，先 withdraw 自有 binding，再关闭自己持有的 Job 和原生进程句柄。

port bind 预检不是端口所有权证明。即使预检后发生抢占，后续既有 ProcessBoundMaterialScanner 的 PID/出生时间、命令行、监听归属和实际 TCP 连接检查仍须通过，不能仅凭端口打开就发布。

所有者在等待 spawn 被取消或超时时不会遗忘后台线程：保留 pending 清理任务；迟到的自有进程立即关闭，不得发布。清理结果未知时保留句柄并阻止后续启动。Job close 后 wait 超时不标已退出，重试只等待原始进程句柄，不重复关闭已释放 Job。适配器在 spawn 尚未返回时的失败句柄也会保留，显式 stop 可继续清理。

本轮仅提供 `monitor_once`，没有后台调度或自动重启。接入者必须安排有界周期调用和 finally/退出钩子。proof 有效期仍遵循既有 runtime profile 时间语义；本实现不自动续签、不偷偷延长历史收据或更新扫描配置版本。

## 并发、审计与资源限制

所有权只属于一个显式应用进程中的 owner 对象。注册表仍是本进程内存对象，未提供跨进程目录、接管、共享守护进程或分布式选主保证。进程崩溃时由 Windows Job 最后句柄关闭机制处理自有子进程，真实行为待隔离原生验收。

审计事件仅含事件/实例/profile 标识、定义 revision、来源/批准文件摘要、动作和时间；不含 PID、路径、端口、命令行、配置内容或凭据。STARTING/STARTED 不是每个失败分支完整运维审计；失败事件持久化与应用告警接线仍待主线统一。

哈希分块上限 1MiB，文件大小与启动/关闭窗口均有界。SQL 事务不参与进程启动、哈希或健康扫描。本实现不宣称 Windows CPU/RSS、系统调用硬挂起或磁盘 I/O 的硬资源隔离；Job 当前只保证 kill-on-close 配置，非内存限制证明。线程超时后采用迟到清理而非假称 OS 调用已被强行取消。

## 本轮纯测证据与后续接线

运行命令：

```text
.venv/Scripts/python.exe -m pytest python/tests/test_material_scanner_owner.py python/tests/test_material_scanner_owner_process.py -q
.venv/Scripts/python.exe -m ruff check [以上三个 owner 模块和两份测试]
```

38 项覆盖：发布前 health/审计/来源双重校验、缺 Job/端口冲突、假 health 拒绝、代际与有效期变化、取消后迟到清理、清理失败保留句柄、固定来源变更、危险配置拒绝、挂起→Job→恢复顺序、固定 argv/DEVNULL、赋 Job/恢复失败原生句柄清理、PID 重用/观察权限不足、关闭 wait 超时重试、适配器内部未知清理阻止新启动等。

待主线安排：显式私有定义 DTO 解析与批准发行回执来源、持久审计 sink、独立 owner 对象生命周期注入、周期 monitor、关闭钩子；之后使用全新独占目录/端口/可信官方包执行真实启动和退出专项。不得以现有 034 配置、真实既有 ClamD、历史 Worker/UI 通过证据继承本模块验收，也不得碰现有预览或守护进程来凑成功。
