-- 显式选择的Meta连接与当前渠道；只在原导入批次同事务登记，不自动迁移旧账户来源。
CREATE TABLE orbit_meta_import_source (
 tenant_id CHAR(36) NOT NULL COMMENT '原导入批次可信租户UUID',
 batch_id CHAR(36) NOT NULL COMMENT '原账户导入批次UUID，选择后不可静默更换',
 connection_id CHAR(36) NOT NULL COMMENT '明确选择的Meta连接UUID',
 connection_revision BIGINT NOT NULL COMMENT '选择时连接版本，每次读取和回写精确复验',
 channel_id CHAR(36) NULL COMMENT '仅新建账户关联的当前渠道UUID，原账户不覆盖',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '冻结来源关联版本，不随批次进度变化',
 PRIMARY KEY(tenant_id,batch_id),
 FOREIGN KEY(tenant_id,batch_id) REFERENCES orbit_account_import(tenant_id,id),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES orbit_meta_connection(tenant_id,id),
 FOREIGN KEY(tenant_id,channel_id) REFERENCES orbit_channel(tenant_id,id),
 CHECK(connection_revision BETWEEN 1 AND 9007199254740991),
 CHECK(revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户导入显式Meta来源与渠道，失效不得回退其他凭据';
