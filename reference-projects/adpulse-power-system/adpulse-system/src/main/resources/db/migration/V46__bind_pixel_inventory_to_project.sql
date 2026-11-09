-- 像素不再关联使用人；分配时记录项目与申请人所属团队的快照，结项后释放并清空这些字段。
ALTER TABLE media_asset
    ADD COLUMN usage_team VARCHAR(128) NULL COMMENT '像素分配时的申请人所属团队快照；项目结项释放时清空' AFTER assignee_name;

-- 历史像素的“已分配”状态以项目关联为准；没有项目的像素恢复为可用库存。
UPDATE media_asset
SET status = CASE WHEN project_id IS NULL OR project_id = '' THEN 'AVAILABLE' ELSE 'ASSIGNED' END,
    assignee_id = NULL,
    assignee_name = NULL,
    usage_team = NULL
WHERE asset_type = 'PIXEL'
  AND deleted_at = 0;

-- 像素不再维护使用人关系；保留历史记录以便审计，但不参与当前资产展示和分配。
UPDATE media_asset_user_assignment
SET deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED) + id,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE deleted_at = 0
  AND asset_id IN (
      SELECT id FROM media_asset WHERE asset_type = 'PIXEL' AND deleted_at = 0
  );
