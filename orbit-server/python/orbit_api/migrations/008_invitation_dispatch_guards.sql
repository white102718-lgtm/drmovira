-- 已发布迁移不回写；旧邀请缺少发起者安全版本时不可直接发送，需管理员明确重发。
ALTER TABLE orbit_user_invitation
 ADD COLUMN revision BIGINT NOT NULL DEFAULT 1
  COMMENT '邀请状态内部版本；创建1，撤销或消费递增，不替代人员版本',
 ADD COLUMN created_by_auth_version BIGINT NULL
  COMMENT '发起者安全版本快照；历史未知为NULL，不猜测并禁止旧队列发送',
 ADD COLUMN active_user_id BIGINT GENERATED ALWAYS AS
  (CASE WHEN status='ACTIVE' THEN user_id ELSE NULL END) STORED
  COMMENT '仅有效邀请参与人员唯一约束，已撤销或消费历史保留',
 ADD UNIQUE KEY uk_invitation_active_user(tenant_id,active_user_id)
  COMMENT '每租户人员最多一个有效邀请，重发先撤销旧凭据';
ALTER TABLE orbit_invitation_delivery
 ADD KEY idx_invitation_delivery_sending(status,claimed_at,id)
  COMMENT '发送中进程中断按认领时间小批转UNKNOWN，不盲目再次投递';
ALTER TABLE orbit_auth_idempotency
 MODIFY COLUMN request_key VARBINARY(128) NOT NULL
  COMMENT '退出幂等键按ASCII原始字节比较，不能因旧ascii_bin补空格规则混同不同键';
