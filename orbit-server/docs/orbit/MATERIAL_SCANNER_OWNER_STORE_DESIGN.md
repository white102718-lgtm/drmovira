# 037 扫描所有者持久审计协议

## 当前交付边界

本阶段新增 `material_scanner_owner_store.py`、独立037迁移、专属纯测和真实工具。主线实际19/19、9.06秒通过，证据`python-material-scanner-owner-store-http.json`；审计/outbox两处1644全回滚、并发幂等、FK及真实EXPLAIN均通过。查询分别使用`uq_scanner_owner_sequence`、`idx_scanner_owner_outbox_pending`。owner原38与store42项注入纯测已通过，全Python1610项检查点另有具名回执。真实Windows Job启停、正式私有loader与应用生命周期仍待验证；本轮没有启动或停止任何真实进程，不读写私有env。

这是服务端运维来源，不属于任意租户，也不新建 ORBIT 菜单、用户角色或 HTTP 写路由。`tasks.read`、`assets.*`、租户超级管理员等业务权限均不赋予调用此 store 的运维权限；只有主线显式构造的可信 owner 能注入本 sink。Python 内部调用边界不是对恶意进程代码的沙箱。

## 精确事件形状与来源

消费现有 owner `_audit` 的精确十字段：

| 字段 | 规则 |
|---|---|
| event_id | 固定规范 UUID，同一事件重试必须复用 |
| profile_id | 服务端候选标识，1—40 个小写字母、数字、下划线或连字符 |
| definition_revision | 正整数，最大 JS 安全整数；不借用租户配置 revision |
| instance_id | 本轮随机 UUID；全局唯一，不跨 profile 或定义版本复用 |
| action | STARTING / STARTED / STOPPED / INVALIDATED |
| source_sha256 | 固定发行、配置和库等来源的不可变摘要 |
| executable_sha256 | 批准程序字节摘要 |
| config_sha256 | 批准配置字节摘要 |
| release_receipt_sha256 | 批准发行回执摘要；不声称本次重新执行官方验签 |
| occurred_at | 带 UTC offset 的发生时间，完整保留微秒；拒无时区和非 UTC |

未知字段一律拒绝，不能通过扩展字段持久化 PID、地址、端口、路径、命令、配置正文、凭据或原请求。规范化时间为 UTC 后计算十字段 `payload_sha256`，`Z` 与 `+00:00` 的同一时间语义一致。MySQL 登记时间使用 UTC_TIMESTAMP(6)，输入最多容许比实际数据库时钟领先 5 秒；实例时间不能倒退。此 5 秒为技术时钟容差，不是来源或病毒库有效期的重新定义。

## 三表与幂等

`orbit_scanner_owner_instance` 主键为 `(profile_id, definition_revision, instance_id)`，另外对 instance_id 全局唯一。批准来源四个摘要在第一次 STARTING 写入后不可由 store 更改，只允许更新阶段和顺序。

阶段严格为 `STARTING(1) → STARTED(2) → STOPPED(3) 或 INVALIDATED(3)`，末态互斥。没有成功完成的启动可以停在 STARTING，不能为了补齐流程伪造 STARTED/STOPPED。此阶段记录的是已提交审计阶段，不能单凭行仍为 STARTED 推断当前 OS 进程仍活着。崩溃后的协调和失败事件扩展需另行明确；本迁移不擅自扩大 owner 既有事件枚举。

`orbit_scanner_owner_audit` 仅追加，事件 ID 全局唯一，实例动作和实例 sequence 各自唯一。相同 event_id 及完全相同规范摘要精确重放时返回 `replayed=True`，不新增审计/outbox、不改变阶段；不同 payload 或用新 event_id 重复同实例动作明确冲突。历史 STARTING 的精确重放可在终态后返回原结果，但不能回退阶段或换绑来源。

`orbit_scanner_owner_outbox` 与审计共享 event_id 并有外键约束。没有外部消费器时 processed_at 保持 NULL，不返回“已外部投递”的模拟成功。消费者未来必须按 event_id 去重。

## 事务、锁与失败关闭

```python
# 用于其他显式短事务，提交仍由调用方管理
async with sessions() as session, session.begin():
    await append_owner_event(session, safe_event)

# 给现有 owner 显式注入；此 sink 在 commit 完成后才返回
sink = create_owner_audit_sink(sessions, timeout_seconds=5)
```

锁顺序固定为实例唯一键创建/锁定 → 精确事件/动作查询 → 审计追加 → outbox 追加 → 阶段更新。同一外层事务提交，任何审计、outbox、约束或 commit 错误均不得返回成功。sink 将数据库细节转换为固定安全 503；取消继续传播，超时触发事务回滚。事务内没有进程启动、关闭、文件 hash、网络、健康 probe、scanner provider 或等待外部事件。

已有 owner 在 STARTED sink 返回后才 publish；因此此 sink 的 SQL 失败会进入 owner 的自有进程清理路径，不能发布公共候选。真实数据库工具另用注入的进程/health 替身验证此集成门禁，仅 SQL 为真实组件，不冒充真实 Windows 启动或杀毒。

## 列表和索引

`read_owner_events` 只供可信内部调用，按完整实例键和 `sequence_no > after_sequence` 读，limit 1—200，实例天然最多三条。使用 `uq_scanner_owner_sequence`，无 OFFSET、无全局搜索或任意用户查询入口。

待处理 outbox 预期按 `(processed_at IS NULL, created_at, event_id)` 使用 `idx_scanner_owner_outbox_pending` 有界读取。037 专项对两条查询执行真实 EXPLAIN；在实际运行前不能标索引验证或容量验收通过。当前没有实现外部投递、删除/清理策略或全局大容量压测。

## 主线接入与真实专项

导出 `MATERIAL_SCANNER_OWNER_STORE_CASES`，共 **13 组**，入口：

```python
run_material_scanner_owner_store_checks(admin, database, cases)
```

只要求迁移已执行到 037，无 tenant/user/material/ClamD manifest/object_root/HTTP 夹具依赖。拒绝非 loopback、非 13306 或非 `orbit_py_it_<32位小写hex>`；另读取实际 DATABASE() 精确匹配。工具只在该隔离库内创建临时 1644 触发器并 finally 删除，未自行连接或启动测试服务。

13 组计划：真实首次原子写；完整阶段与有界分页；精确重放；event_id payload 冲突；自然动作去重；来源换绑拒绝；乱序/倒退/双末态；audit 1644 全回滚；outbox 1644 全回滚后重试；真实并发重复；outbox 外键与全局实例 UUID；真实 EXPLAIN；真实审计失败结合注入进程不得 publish。只返回安全 case_count/索引名称与 `actual_process_start_tested=False`，不输出数据库连接信息或进程基础设施字段。

后续正式接线仍由主线审核：可信定义 loader、发行回执来源核验、生命周期与周期监督、真实 Windows Job 启停、退出协调。此模块不接管现有守护进程、不自动更新生产配置，也不把先前素材/配置消费者验收继承到新的运维启动链。
