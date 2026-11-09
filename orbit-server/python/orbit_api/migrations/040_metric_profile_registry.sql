-- 040：指标来源不可变版本及显式参数映射；由显式升级工具执行。
-- 先版本再头；version→tenant、head/binding→exact version，避免不可延迟外键环。
CREATE TABLE orbit_metric_profile_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '指标目录及适配变化分页水位，不是原profile字符串version',
 PRIMARY KEY(tenant_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CHECK(revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标来源租户短事务锁与有界分页水位';
INSERT INTO orbit_metric_profile_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_metric_profile_version (
 tenant_id CHAR(36) NOT NULL COMMENT '真实来源所属租户',
 profile_id CHAR(36) NOT NULL COMMENT '原MetricProfile稳定UUID',
 version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '原字符串版本精确值，不是CAS头revision',
 payload_json JSON NOT NULL COMMENT '原MetricProfile完整不可变JSON，不添加内部技术字段',
 payload_hash CHAR(64) NOT NULL COMMENT '原profile规范JSON SHA256',
 source VARCHAR(16) NOT NULL COMMENT '原META或FIXTURE来源',
 authority_kind VARCHAR(16) NOT NULL COMMENT 'TRUSTED真实来源或ISOLATED_TEST本机独立库',
 source_config_id CHAR(36) NULL COMMENT '实际META_BM来源配置UUID，fixture可空',
 source_config_revision BIGINT NULL COMMENT '核验时真实配置版本，不能填当前时间代替',
 observed_at DATETIME(3) NOT NULL COMMENT '实际映射及来源观察UTC时刻',
 evidence_ref VARCHAR(255) NOT NULL COMMENT '受控证据标识，不含URL凭据或路径',
 source_sha256 CHAR(64) NOT NULL COMMENT '权威来源完整不可变摘要',
 source_proof_json JSON NOT NULL COMMENT '严格最小来源证明，与独立列共同核验',
 created_by BIGINT NOT NULL COMMENT '当前有release.manage的实际原生操作者',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实内部登记UTC时刻',
 PRIMARY KEY(tenant_id,profile_id,version),
 UNIQUE KEY uq_metric_version_hash(tenant_id,profile_id,version,payload_hash),
 KEY idx_metric_source(tenant_id,source_config_id,source_config_revision,profile_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(tenant_id,source_config_id) REFERENCES orbit_system_configuration(tenant_id,id),
 CHECK(CHAR_LENGTH(version) BETWEEN 1 AND 64),
 CONSTRAINT ck_metric_payload_hash CHECK(CHAR_LENGTH(payload_hash)=64 AND NOT REGEXP_LIKE(payload_hash,'[^0-9a-f]','c')),
 CONSTRAINT ck_metric_source_hash CHECK(CHAR_LENGTH(source_sha256)=64 AND NOT REGEXP_LIKE(source_sha256,'[^0-9a-f]','c')),
 CONSTRAINT ck_metric_evidence CHECK(CHAR_LENGTH(evidence_ref) BETWEEN 1 AND 255 AND NOT REGEXP_LIKE(evidence_ref,'[^A-Za-z0-9._:-]','c')),
 CHECK((source_config_id IS NULL)=(source_config_revision IS NULL)),
 CHECK(source_config_revision IS NULL OR source_config_revision BETWEEN 1 AND 9007199254740991),
 CHECK((source='META' AND authority_kind='TRUSTED' AND source_config_id IS NOT NULL)
    OR (source='FIXTURE' AND authority_kind='ISOLATED_TEST'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标配置不可变原版本，内部未有有效头的行不可公开读取';

CREATE TABLE orbit_metric_profile_head (
 tenant_id CHAR(36) NOT NULL COMMENT '当前配置租户UUID',
 id CHAR(36) NOT NULL COMMENT '稳定profile UUID',
 current_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '指向真实存在的原字符串版本',
 revision BIGINT NOT NULL COMMENT '内部发布停用CAS头，不写入原MetricProfile响应',
 state VARCHAR(16) NOT NULL COMMENT 'ENABLED或DISABLED；停用不改旧快照',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '第一次正式发布UTC时刻',
 updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '最后实际发布停用UTC时刻',
 PRIMARY KEY(tenant_id,id),
 KEY idx_metric_head_state(tenant_id,state,id),
 FOREIGN KEY(tenant_id,id,current_version) REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version),
 CHECK(revision BETWEEN 1 AND 9007199254740991),
 CHECK(state IN ('ENABLED','DISABLED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='仅有明确实际版本的指标配置可见头';

CREATE TABLE orbit_metric_profile_adapter (
 tenant_id CHAR(36) NOT NULL COMMENT '同一租户UUID',
 profile_id CHAR(36) NOT NULL COMMENT '精确指标配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '映射绑定的原profile字符串版本',
 adapter_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '明确参数适配器发行版本，不推测latest',
 registry_revision BIGINT NOT NULL COMMENT '首次发布时真实目录水位，之后不可变',
 profile_hash CHAR(64) NOT NULL COMMENT '严格绑定同版本profile原JSON摘要',
 mapping_json JSON NOT NULL COMMENT '显式AttributionSpec数组，不能从窗口文本自动推导',
 mapping_hash CHAR(64) NOT NULL COMMENT '参数映射规范JSON SHA256',
 source_proof_json JSON NOT NULL COMMENT '与原profile版本一致的来源证明',
 revoked_at DATETIME(3) NULL COMMENT '仅允许从空变为真实撤销UTC时刻，不允许复活',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实发布UTC时刻',
 PRIMARY KEY(tenant_id,profile_id,profile_version,adapter_version),
 KEY idx_metric_adapter_active(tenant_id,profile_id,revoked_at,adapter_version),
 FOREIGN KEY(tenant_id,profile_id,profile_version,profile_hash)
 REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 CHECK(registry_revision BETWEEN 1 AND 9007199254740991),
 CHECK(CHAR_LENGTH(adapter_version) BETWEEN 1 AND 64),
 CONSTRAINT ck_metric_adapter_profile_hash CHECK(CHAR_LENGTH(profile_hash)=64 AND NOT REGEXP_LIKE(profile_hash,'[^0-9a-f]','c')),
 CONSTRAINT ck_metric_adapter_mapping_hash CHECK(CHAR_LENGTH(mapping_hash)=64 AND NOT REGEXP_LIKE(mapping_hash,'[^0-9a-f]','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原指标版本与目标参数的精确不可变映射及单向撤销';

CREATE TABLE orbit_metric_profile_audit (
 tenant_id CHAR(36) NOT NULL COMMENT '当前租户UUID',
 id CHAR(36) NOT NULL COMMENT '单次真实变化事件UUID',
 actor_id BIGINT NOT NULL COMMENT '服务端当前授权操作者',
 profile_id CHAR(36) NOT NULL COMMENT '实际配置UUID',
 revision BIGINT NOT NULL COMMENT '实际变化后的内部头版本',
 action VARCHAR(64) NOT NULL COMMENT '受控发布、整配置停用或精确适配撤销动作',
 request_id CHAR(36) NOT NULL COMMENT '当前请求或内部操作UUID',
 details_json JSON NOT NULL COMMENT '版本及摘要或必要状态差异，不含凭据/完整请求',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实审计UTC时刻',
 PRIMARY KEY(tenant_id,id),
 KEY idx_metric_audit_profile(tenant_id,profile_id,created_at,id),
 FOREIGN KEY(tenant_id,profile_id) REFERENCES orbit_metric_profile_head(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标发行只追加审计，与版本头及outbox同事务';

CREATE TABLE orbit_metric_profile_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '事件所属租户',
 event_id CHAR(36) NOT NULL COMMENT '真实审计事件UUID，同事件不得重复入队',
 state VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING或DELIVERED投递状态',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实入队UTC时刻',
 PRIMARY KEY(tenant_id,event_id),
 KEY idx_metric_outbox_delivery(state,created_at,tenant_id,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_metric_profile_audit(tenant_id,id),
 CHECK(state IN ('PENDING','DELIVERED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标变化可恢复投递，不以提交后内存消息代替';

CREATE TRIGGER metric_version_immutable_update BEFORE UPDATE ON orbit_metric_profile_version
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_VERSION_IMMUTABLE';
CREATE TRIGGER metric_version_immutable_delete BEFORE DELETE ON orbit_metric_profile_version
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_VERSION_IMMUTABLE';
CREATE TRIGGER metric_adapter_immutable_delete BEFORE DELETE ON orbit_metric_profile_adapter
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_ADAPTER_IMMUTABLE';
CREATE TRIGGER metric_adapter_immutable_update BEFORE UPDATE ON orbit_metric_profile_adapter
 FOR EACH ROW BEGIN
 IF NOT (NEW.tenant_id<=>OLD.tenant_id) OR NOT (NEW.profile_id<=>OLD.profile_id)
 OR NOT (NEW.profile_version<=>OLD.profile_version) OR NOT (NEW.adapter_version<=>OLD.adapter_version)
 OR NOT (NEW.registry_revision<=>OLD.registry_revision) OR NOT (NEW.profile_hash<=>OLD.profile_hash)
 OR NOT (NEW.mapping_json<=>OLD.mapping_json) OR NOT (NEW.mapping_hash<=>OLD.mapping_hash)
 OR NOT (NEW.source_proof_json<=>OLD.source_proof_json) OR NOT (NEW.created_at<=>OLD.created_at)
 OR (OLD.revoked_at IS NOT NULL AND NOT (NEW.revoked_at<=>OLD.revoked_at)) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_ADAPTER_IMMUTABLE';
 END IF;
 END;
CREATE TRIGGER metric_audit_immutable_update BEFORE UPDATE ON orbit_metric_profile_audit
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_AUDIT_IMMUTABLE';
CREATE TRIGGER metric_audit_immutable_delete BEFORE DELETE ON orbit_metric_profile_audit
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_AUDIT_IMMUTABLE';
