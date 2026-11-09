UPDATE media_asset
SET channel_id = project_id,
    channel_name = project_name
WHERE deleted_at = 0
  AND (channel_id IS NULL OR channel_id = '')
  AND project_id IS NOT NULL
  AND project_id <> '';
