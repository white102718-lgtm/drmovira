-- 本人命令诊断：非唯一关联索引不改变旧幂等键、状态或Task模型。
-- 读取最多两条，关联重复时明确失败，不任选/删除旧命令。
ALTER TABLE orbit_account_command
 ADD KEY idx_account_command_diagnostic
 (tenant_id,actor_id,actor_subject_id,account_id,kind,request_id)
 COMMENT '当前本人动作与账户范围校验后按原受理请求关联读取';
