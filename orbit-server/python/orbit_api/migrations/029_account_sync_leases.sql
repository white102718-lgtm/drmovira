-- 只读同步持久认领；028原始受理回执不变，不启用任何自动调度。
ALTER TABLE orbit_account_command
 ADD COLUMN attempt_count TINYINT UNSIGNED NOT NULL DEFAULT 0
   COMMENT '已开始只读尝试次数，首次加三次重试最多4，不是平台成功次数',
 ADD COLUMN claim_id CHAR(36) NULL COMMENT '单次认领UUID栅栏，旧执行者不得覆盖新认领',
 ADD COLUMN claimed_at DATETIME(3) NULL COMMENT '数据库真实认领UTC，120秒只读租约',
 ADD COLUMN next_attempt_at DATETIME(3) NULL COMMENT '30/60/120秒退避后的最早重读UTC',
 ADD COLUMN claimed_account_revision BIGINT NULL COMMENT '认领账户CAS版本，读取期间变化不得回写旧资料',
 ADD COLUMN claimed_auth_version BIGINT NULL COMMENT '认领时真实人员授权版本，每个HTTP和回写再核',
 ADD KEY idx_account_sync_queue(tenant_id,kind,state,next_attempt_at,created_at,id)
   COMMENT '有界读取待执行和退避到期命令，不深OFFSET',
 ADD KEY idx_account_sync_lease(tenant_id,kind,state,claimed_at,id)
   COMMENT '仅回收过期只读RUNNING；不重发广告写入UNKNOWN';
