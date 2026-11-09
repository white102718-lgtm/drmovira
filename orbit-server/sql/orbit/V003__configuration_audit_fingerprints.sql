-- 审计旧新状态摘要；在V001、V002之后执行，禁止凭空回填无法还原的历史快照。
ALTER TABLE orbit_configuration_audit
    ADD COLUMN before_revision BIGINT NULL COMMENT '操作前版本；新建为0；迁移前历史未知为NULL' AFTER revision,
    ADD COLUMN before_hash CHAR(64) NULL COMMENT '旧配置规范状态SHA256；新建及迁移前历史为NULL；凭据使用密文信封参与摘要' AFTER before_revision,
    ADD COLUMN after_hash CHAR(64) NULL COMMENT '新配置规范状态SHA256；迁移前历史为NULL；不存Token明文摘要' AFTER before_hash,
    ADD COLUMN hash_algorithm VARCHAR(32) NULL COMMENT '摘要格式版本：SHA256_STATE_V1；迁移前历史未知为NULL' AFTER after_hash;
