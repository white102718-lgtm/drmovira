ALTER TABLE sys_user
    DROP CHECK ck_user_mfa_enabled,
    DROP COLUMN mfa_enabled;
