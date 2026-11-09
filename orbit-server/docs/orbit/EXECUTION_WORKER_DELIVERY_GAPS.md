# 执行发送 Worker 最小交付缺口

当前审计范围是原受理 202 到实际执行和核验的业务链，不把恢复扫描服务等同发送 Worker。没有新增或启用生产 authority，没有平台写入、CLI/应用接线或新迁移。

## 已有能力与证据边界

`launch_execution_contract.py`、`launch_execution_store.py` 和 039 持久准备支持原 validate/execute、source/head 分离、完整冻结 manifest、不可变命令、原 Task/Node 与审计 outbox 同事务受理。原 033/035/036 支持完整 DAG 和 Task/节点/SSE 读取。默认真实执行 authority 仍缺失；隔离 HTTP 202 是真实数据库协议验收，不是 Meta 或 AdsPower 可发送证明。

046 提供 attempt/runtime/不可变事实绑定及 fence；050 保存微秒事实；052 根据完整事实进行精确旧代际恢复、Task 聚合、事件与审计原子提交；054 scanner 和独立 service 已实际验证串行生命周期与清理。它们没有创建新的发送 claim、调用平台 transport、释放预算锁或制造发送成功。

## 原合同不可省略的边界

- `contracts/WORKFLOWS.md:66—68,73`：完整命令与 DAG 状态、父依赖、Task 聚合；已成功节点不能重建，取消节点不能因父重试复活。
- `WORKFLOWS.md:101—103,127`：原 source 唯一 Task、幂等稳定意图、完整 DAG 持久后才发送；不能逐页看见一部分节点便假定完整清单。
- `WORKFLOWS.md:111,117`：UNKNOWN 每五分钟只读对账，24 小时人工标记仍 UNKNOWN；确定未发送需原双人核准，不自动重新写。
- `WORKFLOWS.md:113,129,135`：三级 kill-switch，UNKNOWN 保留预算与对象锁，不自动切换 Meta/AdsPower 重发。
- `WORKFLOWS.md:137,139—141`：AdsPower 挑战、原设备证书和租约、WRITE_INTENT 云端确认、历史事件补传；机器登记或身份观测不授操作权限。

## 最小业务闭环顺序

|阶段|最小必需实现|当前缺口与验收要求|
|---|---|---|
|原 202 与完整来源|重读 COMPLETE Task、ACCEPTED preparation、冻结命令/hash、原 source/version 与幂等受理|已有内部协议；生产真实 provider、完整执行依赖的权威来源仍必须落实，不能用 ISOLATED_TEST 或 `TRUSTED` 字符串替代|
|DAG 就绪候选|有界原始 keyset、完整父依赖、取消/终态/执行意图、同租户范围、当前能力与持有者重验|尚无正式发送候选目录和领取入口；需要真实 SQL 并发与十万节点容量证据|
|安全 claim|事务内原 Task→preparation→命令/节点/runtime 顺序，原 attempt/fence 单调，预算/目标锁与三级 kill-switch 同步重验|046 表存在不代表已实现领取；当前租约恢复不能充当 claim。缺正式主体/租约 authority、预算账本和全部目标写方接入|
|发送前最终门禁|当前用户/团队/功能/账户/设备 scope、source/preview 时效、素材完整安全证明、精确 adapter/profile/identity、目标回读|身份目录观测不等于广告写授权；M2 原始观察不能当平台 capability。任何来源缺失 fail closed，无 transport 调用|
|WRITE_INTENT 与 transport|精确 attempt/fence/稳定操作键绑定，持久发送意图 ack 后才执行；受控 transport 只收冻结 typed instruction|缺真正 transport 协议及生产绑定；事务内不得网络 I/O。超时或不能证明未发送必须 UNKNOWN，不允许改 payload 复用键|
|回读与成功|持久真实 ACK/关联证据、逐级原对象ID与字段核验，ACCEPTED→VERIFYING→SUCCEEDED|无正式回读 provider 和独立核验代际。配置成功不宣称正在投放；无法读取不宣称删除/成功|
|未知与恢复|持久事实真实性、五分钟核验、24小时人工、双人裁决、旧 fence 事实留档不推进当前状态|052/054 只实现原事实恢复窄链；缺独立只读 reconciliation lease/worker、原人工业务闭环；不能借调度器自动新写|

## 建议下一窄交付

优先设计默认 unavailable 的发送前协议和可注入 typed transport 边界，先验证“无权威来源零 claim/零发送”以及完整 DAG/父依赖候选。正式 claim 的最小 DDL、预算与对象锁的参与表、统一锁序、attempt/fence 与发送意图原子范围必须先由主线审核；不直接复用账户导入命令 Worker 的状态或重试策略。

随后可在 UUID/13306 下以明确技术 authority 和本地不出网 transport 验证协议故障矩阵：发送前拒绝、意图前中断、意图后未知、ACK 后未知、晚到旧 fence、重复操作键、节点父失败/取消、审计 1644、两个 Worker 的唯一 claim。技术 transport 的本地成功只证明内部链路，不能标实际 Meta/AdsPower 验收。

首次正式外部交付需另有真实凭据/能力与用户明确允许的平台测试环境；本任务禁止真实广告写。当前已有恢复服务 20/20 不解除这些依赖，不升级整模块完成标记。
