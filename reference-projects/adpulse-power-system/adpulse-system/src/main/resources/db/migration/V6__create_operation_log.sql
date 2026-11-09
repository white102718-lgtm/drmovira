CREATE TABLE sys_operation_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '操作日志ID',
    operator_user_id BIGINT UNSIGNED NULL COMMENT '操作人用户ID',
    operator_display_name VARCHAR(100) NULL COMMENT '操作人显示名称快照',
    module_code VARCHAR(32) NOT NULL COMMENT '业务模块编码',
    operation_type VARCHAR(32) NOT NULL COMMENT '操作类型',
    operation_name VARCHAR(100) NOT NULL COMMENT '操作名称',
    target_type VARCHAR(64) NOT NULL COMMENT '目标资源类型',
    target_id VARCHAR(64) NULL COMMENT '目标资源ID',
    request_method VARCHAR(10) NOT NULL COMMENT 'HTTP请求方法',
    request_path VARCHAR(255) NOT NULL COMMENT 'HTTP请求路径',
    client_ip VARCHAR(64) NOT NULL COMMENT '客户端IP',
    user_agent VARCHAR(500) NULL COMMENT '客户端User-Agent',
    operation_result TINYINT NOT NULL COMMENT '操作结果：0失败，1成功',
    failure_code INT NULL COMMENT '失败业务码',
    failure_reason VARCHAR(255) NULL COMMENT '失败原因',
    operated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '操作发生时间',
    PRIMARY KEY (id),
    KEY idx_operation_log_operator_time (operator_user_id, operated_at),
    KEY idx_operation_log_module_time (module_code, operated_at),
    KEY idx_operation_log_result_time (operation_result, operated_at),
    KEY idx_operation_log_target (target_type, target_id, operated_at),
    CONSTRAINT ck_operation_log_result CHECK (operation_result IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统操作审计日志';

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
    'SYSTEM_OPERATION_LOG_LIST',
    '查看操作日志',
    'system:operation-log:list',
    0,
    110,
    1,
    '操作日志分页查询权限'
);

SET @operation_log_permission_id = LAST_INSERT_ID();

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, @operation_log_permission_id
FROM sys_role r
WHERE r.role_code = 'ADMIN'
  AND r.deleted_at = 0;
