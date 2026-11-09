CREATE TABLE sys_login_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '登录日志ID',
    user_id BIGINT UNSIGNED NULL COMMENT '匹配到的用户ID',
    login_identifier VARCHAR(128) NULL COMMENT '用户提交的登录标识',
    username VARCHAR(64) NULL COMMENT '登录账号快照',
    display_name VARCHAR(100) NULL COMMENT '用户显示名称快照',
    auth_stage TINYINT NOT NULL COMMENT '认证阶段：1密码，2绑定MFA，3验证MFA',
    login_result TINYINT NOT NULL COMMENT '登录结果：0失败，1成功',
    failure_code INT NULL COMMENT '失败业务码',
    failure_reason VARCHAR(255) NULL COMMENT '失败原因',
    client_ip VARCHAR(64) NOT NULL COMMENT '客户端IP',
    user_agent VARCHAR(500) NULL COMMENT '客户端User-Agent',
    login_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '登录发生时间',
    PRIMARY KEY (id),
    KEY idx_login_log_user_time (user_id, login_at),
    KEY idx_login_log_result_time (login_result, login_at),
    KEY idx_login_log_ip_time (client_ip, login_at),
    KEY idx_login_log_identifier_time (login_identifier, login_at),
    CONSTRAINT ck_login_log_auth_stage CHECK (auth_stage IN (1, 2, 3)),
    CONSTRAINT ck_login_log_result CHECK (login_result IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统登录审计日志';

SET @system_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SYSTEM'
      AND deleted_at = 0
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id,
    menu_type,
    menu_code,
    menu_name,
    permission_code,
    visible,
    sort_order,
    status,
    remark
) VALUES (
    @system_menu_id,
    3,
    'SYSTEM_LOGIN_LOG_LIST',
    '查看登录日志',
    'system:login-log:list',
    0,
    100,
    1,
    '登录日志分页查询权限'
);

SET @login_log_permission_id = LAST_INSERT_ID();

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, @login_log_permission_id
FROM sys_role r
WHERE r.role_code = 'ADMIN'
  AND r.deleted_at = 0;
