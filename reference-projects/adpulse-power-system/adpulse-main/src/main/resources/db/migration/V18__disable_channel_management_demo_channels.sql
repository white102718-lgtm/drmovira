-- 联调渠道曾被误导入共享环境。它们会被“系统渠道”下拉当成真实渠道读取，
-- 因此仅按固定测试 ID 与渠道编码双重匹配停用，避免影响用户自行创建的渠道。
UPDATE media_channel
SET status = 0,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE deleted_at = 0
  AND status = 1
  AND (
      (id = 9900101 AND channel_code = 'METASG')
      OR (id = 9900102 AND channel_code = 'METAEU')
      OR (id = 9900103 AND channel_code = 'METAUL')
      OR (id = 9900104 AND channel_code = 'TTASIA')
  );
