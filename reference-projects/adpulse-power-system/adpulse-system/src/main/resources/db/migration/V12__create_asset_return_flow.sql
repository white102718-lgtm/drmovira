ALTER TABLE media_asset
    MODIFY COLUMN status VARCHAR(24) NOT NULL DEFAULT 'AVAILABLE'
        COMMENT '资产状态：AVAILABLE可用/ASSIGNED已分配/RETURN_PENDING待回收/DISABLED已停用';

CREATE TABLE IF NOT EXISTS media_asset_return (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '回收单内部主键',
    return_no VARCHAR(40) NOT NULL COMMENT '回收单号，用于页面检索和对账',
    asset_id BIGINT UNSIGNED NOT NULL COMMENT '被回收的媒介资产ID，逻辑关联media_asset.id',
    application_id BIGINT UNSIGNED NULL COMMENT '发起回收时的来源申请ID快照',
    asset_type VARCHAR(24) NOT NULL COMMENT '资产类型快照：PERSONAL/BM/PIXEL/TG',
    asset_name VARCHAR(128) NOT NULL COMMENT '发起回收时的资产名称快照',
    asset_code VARCHAR(191) NOT NULL COMMENT '发起回收时的资产唯一标识快照',
    project_id VARCHAR(64) NULL COMMENT '发起回收时的库存归属项目稳定标识快照',
    project_name VARCHAR(128) NULL COMMENT '发起回收时的库存归属项目名称快照',
    channel_id VARCHAR(64) NULL COMMENT '发起回收时的资产渠道稳定标识快照',
    channel_name VARCHAR(128) NULL COMMENT '发起回收时的资产渠道名称快照',
    assignee_id BIGINT UNSIGNED NULL COMMENT '发起回收时的使用人ID快照',
    assignee_name VARCHAR(64) NULL COMMENT '发起回收时的使用人名称快照',
    reason VARCHAR(1000) NOT NULL COMMENT '申请人填写的回收原因',
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING' COMMENT '回收单状态：PENDING待处理/COMPLETED已完成',
    outcome VARCHAR(24) NULL COMMENT '回收结果：AVAILABLE重新入库/DISABLED停用',
    requested_by_id BIGINT UNSIGNED NOT NULL COMMENT '发起回收的系统用户ID',
    requested_by_name VARCHAR(64) NOT NULL COMMENT '发起回收时的用户名称快照',
    completed_by_id BIGINT UNSIGNED NULL COMMENT '完成回收的资源管理员ID',
    completed_by_name VARCHAR(64) NULL COMMENT '完成回收时的管理员名称快照',
    completed_at DATETIME NULL COMMENT '回收完成时间，与服务器数据库时区一致',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建记录的系统用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后更新记录的系统用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '回收申请创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '回收申请最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间：0表示有效，其他值为Unix毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_media_asset_return_no (return_no, deleted_at),
    KEY idx_media_asset_return_asset (asset_id, status, deleted_at),
    KEY idx_media_asset_return_status (status, created_at, deleted_at),
    KEY idx_media_asset_return_requester (requested_by_id, created_at, deleted_at),
    KEY idx_media_asset_return_application (application_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='媒介资产回收单；保留分配快照、回收原因和处理轨迹，不级联删除原资产';

SET @return_menu_id = (
    SELECT id
    FROM sys_menu
    WHERE route_path = '/media-resources/returns' AND deleted_at = 0
    ORDER BY id
    LIMIT 1
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code, sort_order, status
)
SELECT COALESCE(@return_menu_id, 0), 3, 'MEDIA_RESOURCE_RETURN_MANAGE', '处理资产回收',
       'media:resource:return:manage', 10, 1
WHERE NOT EXISTS (
    SELECT 1
    FROM sys_menu
    WHERE menu_code = 'MEDIA_RESOURCE_RETURN_MANAGE' AND deleted_at = 0
);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT role.id, menu.id
FROM sys_role role
JOIN sys_menu menu
  ON menu.menu_code = 'MEDIA_RESOURCE_RETURN_MANAGE'
 AND menu.deleted_at = 0
WHERE role.role_code = 'ADMIN'
  AND role.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM sys_role_menu relation
      WHERE relation.role_id = role.id
        AND relation.menu_id = menu.id
        AND relation.deleted_at = 0
  );
