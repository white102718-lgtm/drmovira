ALTER TABLE sys_login_log
    DROP CHECK ck_login_log_auth_stage;

ALTER TABLE sys_login_log
    MODIFY auth_stage TINYINT NOT NULL
        COMMENT '认证阶段：1密码，2绑定MFA，3验证MFA，4飞书扫码';

ALTER TABLE sys_login_log
    ADD CONSTRAINT ck_login_log_auth_stage CHECK (auth_stage IN (1, 2, 3, 4));
