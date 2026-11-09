-- 申请类型是资源申请中心的一级导航；审批配置不再承担分组职责。
CREATE TABLE media_application_type (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '资源申请类型稳定 ID',
    type_name VARCHAR(64) NOT NULL COMMENT '资源申请中心左侧展示的类型名称',
    category VARCHAR(24) NOT NULL COMMENT '类型默认业务分类：advertising/finance/office/social',
    description VARCHAR(255) NOT NULL DEFAULT '' COMMENT '类型在资源申请中心的辅助说明',
    icon VARCHAR(64) NOT NULL DEFAULT 'lucide:folder-open' COMMENT '类型展示使用的 Iconify 图标',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '资源申请中心左侧展示顺序，数值越小越靠前',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1 启用，0 停用；停用类型不可新增申请',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户 ID，逻辑关联 sys_user.id',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户 ID，逻辑关联 sys_user.id',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除毫秒时间戳，0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_application_type_name_deleted (type_name, deleted_at),
    KEY idx_application_type_list (deleted_at, status, sort_order, id),
    CONSTRAINT ck_application_type_status CHECK (status IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资源申请类型主数据；申请入口按类型分组展示';

SET @application_type_operator_id = COALESCE(
    (SELECT id FROM sys_user WHERE status = 1 AND deleted_at = 0 ORDER BY id LIMIT 1),
    (SELECT id FROM sys_user WHERE deleted_at = 0 ORDER BY id LIMIT 1),
    0
);

-- 按资源申请页面已有的四个类型初始化主数据，名称、说明、图标和排序可后续在申请管理中维护。
INSERT INTO media_application_type
    (type_name, category, description, icon, sort_order, status, created_by, updated_by)
VALUES
    ('社交资产', 'social', 'TG号、微信号、Facebook 账号', 'lucide:messages-square', 10, 1, @application_type_operator_id, @application_type_operator_id),
    ('广告资产', 'advertising', '广告账户、像素、BM 与主页', 'lucide:badge-dollar-sign', 20, 1, @application_type_operator_id, @application_type_operator_id),
    ('办公资产', 'office', '电脑、手机、邮箱与静态 IP', 'lucide:laptop', 30, 1, @application_type_operator_id, @application_type_operator_id),
    ('财务申请', 'finance', '项目充值与付款', 'lucide:wallet-cards', 40, 1, @application_type_operator_id, @application_type_operator_id);

ALTER TABLE media_application_definition
    ADD COLUMN application_type_id BIGINT UNSIGNED NULL COMMENT '所属资源申请类型 ID，逻辑关联 media_application_type.id' AFTER application_name,
    ADD KEY idx_application_definition_type (application_type_id, deleted_at, sort_order);

-- 已有申请入口按原业务分类回填到同分类的初始化类型，保持现有申请和审批关系不变。
UPDATE media_application_definition definition
JOIN media_application_type type
  ON type.category = definition.category
 AND type.deleted_at = 0
SET definition.application_type_id = type.id
WHERE definition.deleted_at = 0;

ALTER TABLE media_application_definition
    MODIFY COLUMN application_type_id BIGINT UNSIGNED NOT NULL COMMENT '所属资源申请类型 ID，逻辑关联 media_application_type.id';

-- 先移除审批配置对旧分组的引用，再删除不再使用的分组表；不删除任何审批配置或申请记录。
ALTER TABLE media_approval_config
    DROP INDEX idx_approval_config_group,
    DROP COLUMN group_id,
    DROP COLUMN group_name;

DROP TABLE media_approval_group;
