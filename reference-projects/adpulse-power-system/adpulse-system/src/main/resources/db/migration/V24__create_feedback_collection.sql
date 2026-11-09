CREATE TABLE sys_feedback (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '反馈记录稳定主键',
    category VARCHAR(20) NOT NULL COMMENT '反馈类型：FEATURE功能需求、BUG问题反馈、EXPERIENCE体验建议',
    title VARCHAR(100) NOT NULL COMMENT '反馈标题，便于列表检索和快速分流',
    content TEXT NOT NULL COMMENT '用户填写的完整反馈描述，不包含客户端诊断信息',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '处理状态：PENDING待处理、PROCESSING处理中、RESOLVED已解决、CLOSED已关闭',
    submitted_by_id BIGINT UNSIGNED NOT NULL COMMENT '提交账号ID快照来源，逻辑关联sys_user.id',
    submitted_by_name VARCHAR(100) NOT NULL COMMENT '提交时的账号显示名称快照',
    submitted_by_username VARCHAR(64) NULL COMMENT '提交时的登录账号快照',
    client_ip VARCHAR(64) NOT NULL COMMENT '服务端解析的提交端IP，不信任前端传值',
    user_agent VARCHAR(500) NULL COMMENT 'HTTP User-Agent快照，用于浏览器和设备分析',
    device_type VARCHAR(20) NULL COMMENT '客户端推断设备类型：desktop/tablet/mobile/unknown',
    page_url VARCHAR(1000) NULL COMMENT '反馈发生页面地址，不包含Cookie或认证信息',
    diagnostic_json JSON NULL COMMENT '受控客户端诊断快照：浏览器、系统、屏幕、网络和脱敏控制台记录',
    admin_reply TEXT NULL COMMENT '处理人员给提交人的处理说明或结论',
    processed_by_id BIGINT UNSIGNED NULL COMMENT '最后处理人ID，逻辑关联sys_user.id',
    processed_by_name VARCHAR(100) NULL COMMENT '最后处理人显示名称快照',
    processed_at DATETIME(3) NULL COMMENT '最后一次更新处理状态的时间',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建用户ID，与submitted_by_id一致',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后更新用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '反馈提交时间（服务端时区）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '反馈最后更新时间（服务端时区）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间：0有效，其他值为Unix毫秒时间戳',
    PRIMARY KEY (id),
    KEY idx_feedback_status_time (status, created_at, deleted_at),
    KEY idx_feedback_category_time (category, created_at, deleted_at),
    KEY idx_feedback_submitter_time (submitted_by_id, created_at, deleted_at),
    CONSTRAINT ck_feedback_category CHECK (category IN ('FEATURE', 'BUG', 'EXPERIENCE')),
    CONSTRAINT ck_feedback_status CHECK (status IN ('PENDING', 'PROCESSING', 'RESOLVED', 'CLOSED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='产品需求、缺陷和体验建议反馈；保留提交时账号及诊断快照供问题分析';

CREATE TABLE sys_feedback_file_binding (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '反馈附件绑定主键',
    feedback_id BIGINT UNSIGNED NOT NULL COMMENT '反馈ID，逻辑关联sys_feedback.id',
    file_id BIGINT UNSIGNED NOT NULL COMMENT '文件ID，逻辑关联sys_file.id',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '附件在反馈详情中的展示顺序',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建绑定的用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '绑定创建时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间：0有效，其他值为Unix毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_feedback_file_deleted (feedback_id, file_id, deleted_at),
    KEY idx_feedback_file_feedback (feedback_id, deleted_at, sort_order),
    KEY idx_feedback_file_file (file_id, deleted_at, feedback_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='反馈与通用文件的逻辑绑定；不使用数据库外键，由反馈服务事务校验引用';

SET @system_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE menu_code = 'SystemManagement'
      AND deleted_at = 0
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
) VALUES (
    @system_menu_id, 2, 'SystemFeedbackCollection', '需求反馈搜集',
    '/system-management/feedback-collection', '/feedback/list',
    'lucide:messages-square', 'system:feedback:manage', 1, 0, 60, 1,
    '反馈信息列表、详情与处理入口'
);

SET @feedback_manage_menu_id = LAST_INSERT_ID();

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, @feedback_manage_menu_id
FROM sys_role role
WHERE role.role_code = 'ADMIN'
  AND role.deleted_at = 0;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    icon, permission_code, visible, cacheable, sort_order, status, remark
) VALUES (
    0, 2, 'RequirementFeedback', '需求建议反馈', '/feedback', '/feedback/index',
    'lucide:message-square-plus', NULL, 1, 0, 900, 1,
    '全体登录用户提交产品需求、问题和体验建议的入口'
);

SET @feedback_submit_menu_id = LAST_INSERT_ID();

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, @feedback_submit_menu_id
FROM sys_role role
WHERE role.status = 1
  AND role.deleted_at = 0;
