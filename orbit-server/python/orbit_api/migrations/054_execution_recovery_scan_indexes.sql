-- 054 原执行代际恢复扫描索引；仅支持候选有界读取，不代表容量验收。
-- 不改变046/052历史状态、执行代际、租约含义、权限或Worker注册。
CREATE INDEX idx_exec_runtime_tenant_expiry
 ON orbit_execution_command_runtime(tenant_id,lease_expires_at,task_id,node_id)
 COMMENT '租户内原租约到期有界键集扫描，不授予发送权';
CREATE INDEX idx_exec_command_tenant_recovery
 ON orbit_launch_execution_command(tenant_id,state,task_id,node_id)
 COMMENT '租户内已受理命令原状态候选扫描';
CREATE INDEX idx_exec_runtime_tenant_manual
 ON orbit_execution_command_runtime(tenant_id,needs_manual_reconciliation,unknown_since,task_id,node_id)
 COMMENT '租户内未知结果二十四小时人工标记候选扫描';
