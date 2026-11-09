ALTER TABLE sys_user
    ADD COLUMN mfa_status TINYINT NOT NULL DEFAULT 0
        COMMENT '-1不启用，0待绑定，1已绑定' AFTER mfa_enabled,
    ADD COLUMN mfa_last_used_counter BIGINT NULL
        COMMENT '最近一次成功使用的TOTP时间计数器' AFTER mfa_bound_at;

UPDATE sys_user
SET mfa_status = CASE WHEN mfa_enabled = 1 THEN 1 ELSE 0 END;
