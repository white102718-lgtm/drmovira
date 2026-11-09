-- 012已冻结；补充只读Worker来源与认领审计，不改变既有批次输入或静默猜测来源。
ALTER TABLE orbit_account_import
 ADD COLUMN source_config_id CHAR(36) NULL COMMENT '首次受控认领冻结的唯一已只读验证META_BM配置UUID，NULL尚未决定来源',
 ADD COLUMN source_config_revision BIGINT NULL COMMENT '冻结META_BM版本，每次读取与回写均重新核验',
 ADD COLUMN actor_auth_version BIGINT NULL COMMENT '首次受控认领冻结发起人身份安全版本；冻结前目录版本变化拒绝',
 ADD COLUMN request_id CHAR(36) NULL COMMENT '稳定Worker批次关联请求UUID，不包含秘密';
ALTER TABLE orbit_account_import_row
 ADD COLUMN claim_request_id CHAR(36) NULL COMMENT '本次认领固定请求UUID，与revision共同防迟到覆盖',
 MODIFY COLUMN attempts INT NOT NULL DEFAULT 0 COMMENT '实际只读尝试次数：首次加最多3次重试，共最多4次；退避30/60/120秒加至多10秒抖动';
