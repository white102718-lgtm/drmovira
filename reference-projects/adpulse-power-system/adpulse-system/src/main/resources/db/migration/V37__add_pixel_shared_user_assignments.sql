CREATE TABLE media_asset_user_assignment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '像素共享使用关系主键',
    asset_id BIGINT UNSIGNED NOT NULL COMMENT '像素资产 ID，逻辑关联 media_asset.id',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '获授权使用人的系统用户 ID，逻辑关联 sys_user.id',
    user_name VARCHAR(100) NOT NULL COMMENT '授权时固化的使用人显示名称',
    assigned_by BIGINT UNSIGNED NOT NULL COMMENT '最后一次配置该关系的操作人 ID',
    assigned_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '关系创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '关系最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳，0 表示关系有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_media_asset_user_assignment_active (asset_id, user_id, deleted_at),
    KEY idx_media_asset_user_assignment_asset (asset_id, deleted_at),
    KEY idx_media_asset_user_assignment_user (user_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='像素资产共享使用关系；一条像素可授权给多个有效系统用户';
