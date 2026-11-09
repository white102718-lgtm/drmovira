-- 主页资产不再归属渠道；同步清除旧渠道字段及其兼容项目镜像，
-- 不触及审批单、回收单等历史快照表，保留审计链路。
UPDATE media_asset
SET channel_id = NULL,
    channel_name = NULL,
    project_id = NULL,
    project_name = NULL
WHERE asset_type = 'PAGE'
  AND (channel_id IS NOT NULL
       OR channel_name IS NOT NULL
       OR project_id IS NOT NULL
       OR project_name IS NOT NULL);
