-- 本地人员创建与重置密码的敏感幂等摘要使用独立密钥，轮换后仍可验证旧请求。
ALTER TABLE orbit_directory_idempotency ADD COLUMN digest_key_id VARCHAR(40) NULL COMMENT '密码写请求HMAC密钥版本；其他目录请求为NULL';
-- 原生登录账号不可重复，防止跨租户并发创建同名账号。部署前核对历史重名。
ALTER TABLE sys_user ADD UNIQUE KEY uk_orbit_local_login_name(user_name);
-- 邀请流程退役，已发出的旧邀请不能再激活人员。
UPDATE orbit_user_invitation SET status='REVOKED',revision=revision+1,revoked_at=UTC_TIMESTAMP(3) WHERE status='ACTIVE';
