-- 074：原指标profile允许真实OAuth/BM连接作为唯一来源，保留旧配置来源和不可变记录。
-- chk_4名称已由040实际MySQL8 schema核对；原config成对空值和revision约束保留。
ALTER TABLE orbit_metric_profile_version
 ADD COLUMN source_connection_id CHAR(36) NULL COMMENT '真实Meta连接UUID；与旧config来源恰选一项',
 ADD COLUMN source_connection_revision BIGINT NULL COMMENT '真实账户读取时冻结的连接版本，撤销或重授权即失效',
 ADD KEY idx_metric_connection_source(tenant_id,source_connection_id,source_connection_revision,profile_id),
 ADD CONSTRAINT fk_metric_source_connection FOREIGN KEY(tenant_id,source_connection_id) REFERENCES orbit_meta_connection(tenant_id,id),
 DROP CHECK orbit_metric_profile_version_chk_4,
 ADD CONSTRAINT ck_metric_connection_pair CHECK((source_connection_id IS NULL)=(source_connection_revision IS NULL)),
 ADD CONSTRAINT ck_metric_connection_revision CHECK(source_connection_revision IS NULL OR source_connection_revision BETWEEN 1 AND 9007199254740991),
 ADD CONSTRAINT ck_metric_exact_source CHECK(
  (source='META' AND authority_kind='TRUSTED' AND ((source_config_id IS NOT NULL AND source_connection_id IS NULL) OR (source_config_id IS NULL AND source_connection_id IS NOT NULL)))
  OR (source='FIXTURE' AND authority_kind='ISOLATED_TEST' AND source_connection_id IS NULL)
 );

CREATE TABLE orbit_meta_profile_request (
 tenant_id CHAR(36) NOT NULL COMMENT '当前授权租户UUID',
 actor_id BIGINT NOT NULL COMMENT '真实发布操作者用户ID',
 request_key VARCHAR(128) COLLATE utf8mb4_bin NOT NULL COMMENT '只读验证加原子发布的客户端幂等标识',
 payload_hash CHAR(64) NOT NULL COMMENT '公开配置选择规范JSON摘要，不含Token',
 response_json JSON NOT NULL COMMENT '已提交的原指标发行回执，不含私有来源证明',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实发行事务提交UTC时刻',
 PRIMARY KEY(tenant_id,actor_id,request_key),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CHECK(CHAR_LENGTH(request_key) BETWEEN 1 AND 128),
 CHECK(CHAR_LENGTH(payload_hash)=64 AND NOT REGEXP_LIKE(payload_hash,'[^0-9a-f]','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实Meta指标发行幂等结果，与profile审计及outbox同事务';

-- 连接版本或撤销改变有效目录，使既有分页游标不能拼接两个来源快照。
CREATE TRIGGER metric_connection_update AFTER UPDATE ON orbit_meta_connection
 FOR EACH ROW BEGIN
 IF NOT (NEW.revision<=>OLD.revision) OR NOT (NEW.status<=>OLD.status)
 OR NOT (NEW.expires_at<=>OLD.expires_at) OR NOT (NEW.data_access_expires_at<=>OLD.data_access_expires_at) THEN
 UPDATE orbit_metric_profile_clock SET revision=revision+1
 WHERE tenant_id=NEW.tenant_id AND revision<9007199254740991;
 IF ROW_COUNT()<>1 THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PROFILE_CLOCK_EXHAUSTED';
 END IF;
 END IF;
 END;
