-- 素材生命周期队列：只登记与恢复，不自动启动调度、清理对象或访问云。
ALTER TABLE orbit_material_asset
 ADD COLUMN physical_cleanup_state VARCHAR(12) NOT NULL DEFAULT 'LIVE' COMMENT 'LIVE可引用/CLEANING已冻结新引用/PURGED已物理回收；不改变逻辑归档状态',
 ADD COLUMN physical_deleted_at DATETIME(3) NULL COMMENT '物理对象回收成功UTC时刻；资产和历史审计不删除',
 ADD KEY idx_material_retention_due(state,physical_cleanup_state,archived_at,tenant_id,id) COMMENT '归档满30日的有界保留清理候选';

ALTER TABLE orbit_material_reference
 ADD KEY idx_material_reference_active(tenant_id,asset_id,active,id) COMMENT '活跃引用阻止逻辑和物理回收的有界存在性检查';

CREATE TABLE orbit_material_lifecycle_job (
 tenant_id CHAR(36) NOT NULL COMMENT '来自数据库素材的租户UUID，不接受请求指定',
 id CHAR(36) NOT NULL COMMENT '生命周期任务UUID',
 asset_id CHAR(36) NOT NULL COMMENT '保留的资产元数据UUID',
 upload_id CHAR(36) NOT NULL COMMENT '本任务唯一允许回收的对象上传UUID，不能替换为其他素材对象',
 kind VARCHAR(24) NOT NULL COMMENT 'UPLOAD_EXPIRY未完成上传过期或ARCHIVE_RETENTION归档保留清理',
 state VARCHAR(8) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING待领/RUNNING租约中/RETRY等待重试/DONE已回收',
 generation BIGINT NOT NULL DEFAULT 1 COMMENT '每次认领递增的fencing版本，迟到回写不能覆盖',
 claim_token CHAR(36) NULL COMMENT '当前认领UUID，不含路径或秘密',
 lease_until DATETIME(3) NULL COMMENT '当前租约截止UTC时刻，过期可恢复',
 due_at DATETIME(3) NOT NULL COMMENT '最早重试UTC时刻；保留期与引用检查不能绕过',
 attempts INT NOT NULL DEFAULT 0 COMMENT '实际领取次数，不代表文件全部删除',
 last_error_code VARCHAR(48) NULL COMMENT '安全失败分类，不含文件路径/凭据/原始异常',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '登记UTC时刻',
 updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '最近状态变化UTC时刻，服务显式更新',
 completed_at DATETIME(3) NULL COMMENT '物理回收及元数据提交完成UTC时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_material_lifecycle_object(tenant_id,kind,upload_id) COMMENT '同类同对象唯一任务，幂等重复扫描不复制',
 KEY idx_material_lifecycle_due(state,due_at,tenant_id,id) COMMENT '有界待执行及失败退避队列',
 KEY idx_material_lifecycle_lease(state,lease_until,tenant_id,id) COMMENT '有界崩溃租约恢复候选'
) COMMENT='素材过期及归档保留生命周期任务，物理操作在短事务之外';
