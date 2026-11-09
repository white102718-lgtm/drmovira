# 首次原生 Windows owner 专项准备

## 当前状态与执行权限

`tools/material_scanner_owner_native_checks.py` 由主线人工读码后串行运行，首轮实际失败保留；修正夹具后真实25/25、31.34秒通过，证据`python-material-scanner-owner-native-http.json`。其中6组为真实Windows原生进程专项，13组为持久审计专项，其余为初始化/退出；不能将25组全部称为原生启停。工具没有修改产品、037或私有配置。

首次由主线授权的实际运行已保留 `python-material-scanner-owner-native-attempt-01.json`：19 PASS / 1 FAIL / 5 NOTRUN。新原生 Job 启动和 health 已通过，第二次 PNG scan 因测试内存对象缺少生产扫描器必需的 `mutation_guard` 协议而返回 UNVERIFIED；finally 已核对自有清理、19311释放、原7492/19310身份不变。本次仅修测试夹具，明确绑定同一规范 tenant/upload，immutable bytes使用nullcontext守卫；CLEAN/proof断言不变，并增加仅result/error_code/proof_present的脱敏诊断。整个原生链仍未验收通过。

## 入口和前置条件

```python
run_material_scanner_owner_native_checks(admin, database, cases, progress=None)
```

要求 Windows、本机 loopback 13306、数据库名 `orbit_py_it_<32位小写hex>` 且 DATABASE() 一致、037 三表存在。无需普通用户 HTTP 权限，无新增测试写端点。使用 `create_owner_audit_sink` 真实短事务，主线从已有明确私有配置创建 admin，工具不读取任何 env。

只读固定 `.runtime/tools/clamav-1.5.4/trusted-fixture-manifest.json`、已批准发行 zip、解压 exe 和三 CVD。实际复验固定 zip SHA、exe 与已批准归档成员、三数据库摘要、原配置及原始进程证明。manifest 与批准回执不作为任意第三方目录发现入口。

受保护实例必须仍是 PID **7492**、loopback **19310**，且来源、birth、原配置和监听始终一致。任一检查失败立即拒绝，只清理本轮自有 Job，不触碰原实例。

## 新文件与端口

首次原子 mkdir 固定 ROOT 直属 `owner-native-it-<UUID>`，exist_ok=False。仅在该新根创建 `clamd.conf` 和 `approved-source-fixture.json`；后者绑定原 manifest/归档/库摘要，明确是本轮 fixture 批准来源派生，**不是新增官方 GPG 验签**。此布局兼容冻结 owner 定义中“批准回执位于 installation_root 内”的要求。

数据库、官方程序及原配置只读复用。新配置使用 UUID 根为 TemporaryDirectory，不启文件日志/PID文件，不改系统 PATH，不安装服务。目标端口固定 **19311**；启动前占用即阻断，不扫描其他端口，也不终止占用者。端口抢占仍由 PID/birth/真实连接归属核验失败关闭。

## 资源与预算

- 启动第一轮和第二轮前都要求实际 available memory ≥ **6GiB**、固定磁盘 free ≥ **1GiB**；不足即阻断。
- 等待阶段每 10 秒输出安全 phase/elapsed；available 低于 **3GiB** 时取消本轮操作并进入自有清理。
- 工作总窗口 **360 秒**，finally 清理总窗口另 **30 秒**。
- 每次 owner startup **120 秒**，单次扫描 **30 秒**，外层等 scan **35 秒**，owner stop **10 秒**，SQL sink **5 秒**。先前引擎退出及端口释放后才允许第二轮，并再次检查资源。
- 新配置 MaxThreads=1、MaxQueue=2，标准流 DEVNULL；不宣称 CPU/RSS 硬限制或大文件容量通过。

默认 phase 输出只有阶段与累计秒数，不含 PID、路径、端口、连接、命令或凭据；主线也可提供 `progress(safe_dict)` 汇集。阶段包括来源检查、两轮真实启动、实际 PNG scan、Job close 与最终清理。长启动等待仍每 10 秒产生进度，不以调整断言超时或重试掩盖失败。

## 六组计划和真实范围

1. 真实资源/固定来源/原实例证明检查。
2. 原生挂起启动→自有 kill-on-close Job→恢复；真实 health PNG 通过后，持久 STARTED 提交才公开；再通过 ProcessBound scanner 实扫内存安全 PNG，验证 CLEAN、proof 和本轮 PID/birth。
3. 第一轮仍占用 19311 时，另一 owner 必须拒绝端口冲突，不新建进程、不新增 STARTING 审计。
4. 先 withdraw 再关闭自有 Job；确认原 PID/birth 已退出、19311释放、真实 STOPPED 和 outbox 一致，原 7492/19310 来源身份未变。
5. 第二轮真实启动、实际 health 通过后，对 STARTED 审计注入真实 MySQL 1644；不得 publish，原生自有进程须清理，只留下真实 STARTING 审计。触发器仅 UUID DB，finally 删除。
6. 所有自有 PID/birth 均结束，原引擎复核一致；只删除 UUID 根内两个已知文件并尝试空目录 rmdir，**不递归删除**。未知临时文件存在则保留并返回 cleanup_complete=False。

工具使用跟踪适配器记录所有本轮返回的原生句柄身份，但从不使用数值 PID terminate。异常、超时或 SQL 失败时，通过 owner 保留的 pending/自有 Job 执行清理；观察到不确定清理结果时不得勾完成或清目录，也不改为杀端口/名称/外部 PID。Windows 内核调用若硬挂起无法凭 Python 超时保证成功，必须由主线处理该明确阻断，不能输出假退出成功。

本阶段未接正式应用生命周期或多工作进程 registry，不自动续期、更新官方库或替生产运维做启动。实际运行后仍需区分失败回执、定点复验以及系统正式部署验收。
