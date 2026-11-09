-- 审批分组独立持久化后，空分组、分组顺序和删除状态不再依赖审批配置记录推导。
CREATE TABLE media_approval_group (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '审批分组稳定 ID',
    group_name VARCHAR(64) NOT NULL COMMENT '审批配置页展示的分组名称',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '分组展示顺序，数值越小越靠前',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户 ID，逻辑关联 sys_user.id',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户 ID，逻辑关联 sys_user.id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳（毫秒）；0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_approval_group_name_deleted (group_name, deleted_at),
    KEY idx_approval_group_sort (deleted_at, sort_order, id)
) COMMENT='审批配置分组；保存空分组、排序及删除生命周期';

-- 迁移现有审批配置中的分组，保留每个分组下最小审批顺序作为初始分组顺序。
INSERT INTO media_approval_group
    (group_name, sort_order, created_by, updated_by)
SELECT group_name,
       MIN(sort_order),
       MIN(created_by),
       MIN(updated_by)
FROM media_approval_config
WHERE deleted_at = 0
GROUP BY group_name
ORDER BY MIN(sort_order), MIN(id);

ALTER TABLE media_approval_config
    ADD COLUMN group_id BIGINT UNSIGNED NULL COMMENT '所属审批分组 ID，逻辑关联 media_approval_group.id；迁移前已删除的历史配置可为空' AFTER description,
    ADD KEY idx_approval_config_group (group_id, deleted_at, sort_order);

UPDATE media_approval_config config
JOIN media_approval_group approval_group
  ON approval_group.group_name = config.group_name
 AND approval_group.deleted_at = 0
SET config.group_id = approval_group.id
WHERE config.deleted_at = 0;
