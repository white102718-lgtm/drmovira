-- 申请入口从审批配置中独立出来；表单仍暂存在审批配置中，多条申请可关联同一审批配置。
CREATE TABLE media_application_definition (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '申请入口 ID',
    application_code VARCHAR(64) NOT NULL COMMENT '稳定申请编码，创建后不可修改',
    application_name VARCHAR(100) NOT NULL COMMENT '申请名称',
    category VARCHAR(24) NOT NULL COMMENT '分类：advertising/finance/office/social',
    description VARCHAR(255) NOT NULL DEFAULT '' COMMENT '申请入口说明',
    icon VARCHAR(64) NOT NULL DEFAULT 'lucide:file-plus-2' COMMENT 'Iconify 图标',
    approval_config_id BIGINT UNSIGNED NOT NULL COMMENT '关联审批配置 ID，逻辑关联 media_approval_config.id',
    operation_type VARCHAR(32) NULL COMMENT '提交时预设的操作类型；普通申请为空',
    visibility VARCHAR(16) NOT NULL DEFAULT 'all' COMMENT '可见范围：all/admins',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '展示顺序，数值越小越靠前',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户 ID，逻辑关联 sys_user.id',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户 ID，逻辑关联 sys_user.id',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除毫秒时间戳；0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_application_code_deleted (application_code, deleted_at),
    KEY idx_application_list (status, visibility, category, sort_order, deleted_at),
    KEY idx_application_approval_config (approval_config_id, deleted_at),
    CONSTRAINT ck_application_status CHECK (status IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申请入口定义；表单由关联审批配置维护';

INSERT INTO media_application_definition
    (application_code, application_name, category, description, icon,
     approval_config_id, operation_type, visibility, sort_order, status, created_by, updated_by)
SELECT config.asset_type, config.flow_name, config.category, config.description, config.icon,
       config.id, NULL, config.visibility, config.sort_order, config.enabled,
       config.created_by, config.updated_by
FROM media_approval_config config
WHERE config.deleted_at = 0 AND config.asset_type != 'ACCOUNT_OPERATION';

-- 广告账户七种操作是七个独立申请入口，但共用一个审批配置和表单。
INSERT INTO media_application_definition
    (application_code, application_name, category, description, icon,
     approval_config_id, operation_type, visibility, sort_order, status, created_by, updated_by)
SELECT operation.application_code, operation.application_name, config.category,
       operation.description, operation.icon, config.id, operation.operation_type,
       config.visibility, config.sort_order + operation.sort_offset, config.enabled,
       config.created_by, config.updated_by
FROM media_approval_config config
CROSS JOIN (
    SELECT 'ACCOUNT_RECHARGE' application_code, '广告账户充值申请' application_name,
           '充值' operation_type, '向广告账户充值。' description, 'lucide:badge-plus' icon, 0 sort_offset
    UNION ALL SELECT 'ACCOUNT_DEDUCTION', '广告账户扣款申请', '扣款', '从广告账户扣减余额。', 'lucide:badge-minus', 1
    UNION ALL SELECT 'ACCOUNT_ACTIVE_CLEAR', '广告账户活跃清零申请', '活跃清零', '将广告账户活跃余额清零。', 'lucide:eraser', 2
    UNION ALL SELECT 'ACCOUNT_ACTIVE_CLEAR_RECYCLE', '广告账户活跃清零回收申请', '活跃清零回收', '活跃清零后回收广告账户。', 'lucide:archive-restore', 3
    UNION ALL SELECT 'ACCOUNT_RECYCLE', '广告账户回收申请', '回收', '回收广告账户及其归属关系。', 'lucide:archive', 4
    UNION ALL SELECT 'ACCOUNT_UNBIND', '广告账户解绑申请', '解绑', '解除广告账户当前绑定关系。', 'lucide:unlink', 5
    UNION ALL SELECT 'ACCOUNT_REBIND', '广告账户换绑申请', '换绑', '变更广告账户绑定关系。', 'lucide:refresh-cw', 6
) operation
WHERE config.asset_type = 'ACCOUNT_OPERATION' AND config.deleted_at = 0;

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component, icon,
    permission_code, sort_order, status, remark
)
SELECT parent.id, 2, 'SYSTEM_APPLICATION', '申请管理',
       '/system-management/applications', 'system/application/list', 'lucide:file-stack',
       'system:application:list', 35, 1, '管理申请入口及其审批配置关联'
FROM sys_menu parent
WHERE parent.menu_code = 'SYSTEM' AND parent.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_menu existing
      WHERE existing.menu_code = 'SYSTEM_APPLICATION' AND existing.deleted_at = 0
  );

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
JOIN sys_menu menu ON menu.menu_code = 'SYSTEM_APPLICATION' AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN' AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_role_menu relation
      WHERE relation.role_id = role.id AND relation.menu_id = menu.id AND relation.deleted_at = 0
  );
