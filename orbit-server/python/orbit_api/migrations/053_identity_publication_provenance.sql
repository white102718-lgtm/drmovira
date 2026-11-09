-- 053 身份发布来源追溯。原023历史及接口不重写；本DDL不植入任何能力发行。
CREATE TABLE orbit_identity_capability_release (
 tenant_id CHAR(36) NOT NULL COMMENT '发行仅适用的真实业务租户',
 id CHAR(36) NOT NULL COMMENT '独立受控发行UUID，不由身份publish顺便创建',
 revision BIGINT NOT NULL COMMENT '发行源精确正安全整数版本',
 capability_version VARCHAR(64) NOT NULL COMMENT '原AccountIdentities能力版本字符串，不冒充Agent或策略版本',
 issuer VARCHAR(128) NOT NULL COMMENT '受控实际发行者标识，非调用者verified布尔',
 source_kind VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'META_AUTHORITY或仅隔离协议ISOLATED_PROTOCOL',
 source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整权威来源证据规范SHA256，不包含凭据',
 source_config_id CHAR(36) NOT NULL COMMENT '绑定原META_BM配置UUID',
 source_config_revision BIGINT NOT NULL COMMENT '绑定配置精确版本',
 business_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '发行适用BM数字文本，不改变前导零',
 graph_version VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '明确适用Graph版本，非SDK猜测',
 action_scope VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '仅ACCOUNT_IDENTITIES_READ，绝不授广告写权',
 revoked_at DATETIME(6) NULL COMMENT '当前已知发行撤销UTC微秒；只允许NULL到非NULL且不可恢复',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '受控发行登记UTC微秒',
 PRIMARY KEY(tenant_id,id),
 KEY idx_identity_release_source(tenant_id,source_config_id,source_config_revision,id),
 CONSTRAINT ck_identity_release_values CHECK (
  revision BETWEEN 1 AND 9007199254740991 AND source_config_revision BETWEEN 1 AND 9007199254740991
  AND CHAR_LENGTH(capability_version) BETWEEN 1 AND 64 AND CHAR_LENGTH(issuer) BETWEEN 1 AND 128
  AND source_kind IN ('META_AUTHORITY','ISOLATED_PROTOCOL') AND source_hash REGEXP '^[0-9a-f]{64}$'
  AND business_id REGEXP '^[0-9]{1,64}$' AND graph_version REGEXP '^v[0-9]{1,3}\\.[0-9]{1,2}$'
  AND action_scope='ACCOUNT_IDENTITIES_READ'
 )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='身份只读能力独立受控发行；当前无生产发行器，空表不能被publish自授';

CREATE TABLE orbit_identity_publication_provenance (
 tenant_id CHAR(36) NOT NULL COMMENT '原023同租户',
 evidence_id CHAR(36) NOT NULL COMMENT '唯一原023证据UUID',
 account_id CHAR(36) NOT NULL COMMENT '完整库存目标账户UUID',
 identity_revision BIGINT NOT NULL COMMENT '同事务发布的原023历史版本',
 registry_id CHAR(36) NOT NULL COMMENT '已登记045完整原始库存UUID',
 release_id CHAR(36) NOT NULL COMMENT '独立能力发行UUID，不接受自由版本自授',
 release_revision BIGINT NOT NULL COMMENT '冻结的发行源精确版本',
 release_source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '冻结权威发行来源根',
 raw_observed_at DATETIME(6) NOT NULL COMMENT '完整资格实际观察UTC微秒，原精度不截断',
 raw_credential_expires_at DATETIME(6) NULL COMMENT '权威已知凭据到期UTC微秒；NULL不发明TTL',
 bound_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '045完整原始来源与库存组合根',
 principal_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际me与配置主体精确匹配根，不代表主体类型或写权',
 facts_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'M3实际资源观察完整事实根，不单独授可投',
 principal_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '来源配置实际systemUserId与me匹配值',
 projection_version VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '显式UTC_FLOOR_MS_V1，原023毫秒仅向下投影',
 payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原严格四字段及完整五字段资源规范根',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '全部来源、期望版本、微秒及完整资格正文根',
 authority_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'TRUSTED或严格UUID库ISOLATED_TEST，标签自身不是权限',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '真实同事务登记UTC微秒',
 PRIMARY KEY(tenant_id,evidence_id),
 UNIQUE KEY uk_identity_provenance_version(tenant_id,account_id,identity_revision),
 KEY idx_identity_provenance_raw(tenant_id,registry_id,evidence_id),
 CONSTRAINT fk_identity_proof_evidence FOREIGN KEY(tenant_id,evidence_id) REFERENCES orbit_account_identity_evidence(tenant_id,id),
 CONSTRAINT fk_identity_proof_history FOREIGN KEY(tenant_id,account_id,identity_revision) REFERENCES orbit_account_identity_history(tenant_id,account_id,revision),
 CONSTRAINT fk_identity_proof_raw FOREIGN KEY(tenant_id,registry_id) REFERENCES orbit_meta_raw_head(tenant_id,id),
 CONSTRAINT fk_identity_proof_release FOREIGN KEY(tenant_id,release_id) REFERENCES orbit_identity_capability_release(tenant_id,id),
 CONSTRAINT ck_identity_proof_values CHECK (
  identity_revision BETWEEN 1 AND 9007199254740991 AND release_revision BETWEEN 1 AND 9007199254740991
  AND projection_version='UTC_FLOOR_MS_V1' AND authority_kind IN ('TRUSTED','ISOLATED_TEST')
  AND principal_id REGEXP '^[0-9]{1,64}$'
  AND release_source_hash REGEXP '^[0-9a-f]{64}$' AND bound_sha256 REGEXP '^[0-9a-f]{64}$'
  AND principal_sha256 REGEXP '^[0-9a-f]{64}$' AND facts_sha256 REGEXP '^[0-9a-f]{64}$'
  AND payload_hash REGEXP '^[0-9a-f]{64}$' AND intent_hash REGEXP '^[0-9a-f]{64}$'
  AND (raw_credential_expires_at IS NULL OR raw_credential_expires_at>raw_observed_at)
 )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='原023完整身份发布旁证；保留微秒与完整根，绝不回填猜测旧verified证据';

-- 完整receipt先reserve再写证据，故ledger不设前向evidence FK；失败外层事务整体回滚。
CREATE TABLE orbit_identity_publication_ledger (
 tenant_id CHAR(36) NOT NULL COMMENT '当前业务租户',
 actor_id BIGINT NOT NULL COMMENT '实际accounts.sync调用者原生ID',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '同actor幂等键SHA256，无原键正文',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '冻结完整发布意图根',
 evidence_id CHAR(36) NOT NULL COMMENT '预生成实际证据UUID，无NULL或BUILDING占位',
 receipt_json JSON NOT NULL COMMENT '完整历史元数据回执，不返回旧资源、不授执行权',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '本次事务预留UTC微秒',
 PRIMARY KEY(tenant_id,actor_id,key_hash),
 UNIQUE KEY uk_identity_ledger_evidence(tenant_id,evidence_id),
 CONSTRAINT ck_identity_ledger_values CHECK (
  actor_id>0 AND key_hash REGEXP '^[0-9a-f]{64}$' AND intent_hash REGEXP '^[0-9a-f]{64}$'
  AND (JSON_TYPE(receipt_json)='OBJECT' AND JSON_LENGTH(receipt_json)=6
   AND JSON_CONTAINS_PATH(receipt_json,'all','$.account_id','$.evidence_id','$.revision','$.payload_hash','$.observed_at','$.execution_authorized')
   AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.account_id'))='STRING'
   AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.evidence_id'))='STRING'
   AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.evidence_id'))=evidence_id
   AND CASE WHEN JSON_TYPE(JSON_EXTRACT(receipt_json,'$.revision'))='INTEGER'
    THEN CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.revision')) AS DECIMAL(65,0)) BETWEEN 1 AND 9007199254740991 ELSE FALSE END
   AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.payload_hash'))='STRING'
   AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.payload_hash')) REGEXP '^[0-9a-f]{64}$'
   AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.observed_at'))='STRING'
   AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='BOOLEAN'
   AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='false') IS TRUE
 )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='完整身份发布成功回执；旧成功仍先核当前动作与账户范围';

CREATE TRIGGER trg_identity_release_bu BEFORE UPDATE ON orbit_identity_capability_release FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id AND NEW.id<=>OLD.id AND NEW.revision<=>OLD.revision
  AND NEW.capability_version<=>OLD.capability_version AND NEW.issuer<=>OLD.issuer
  AND NEW.source_kind<=>OLD.source_kind AND NEW.source_hash<=>OLD.source_hash
  AND NEW.source_config_id<=>OLD.source_config_id AND NEW.source_config_revision<=>OLD.source_config_revision
  AND NEW.business_id<=>OLD.business_id AND NEW.graph_version<=>OLD.graph_version
  AND NEW.action_scope<=>OLD.action_scope AND NEW.created_at<=>OLD.created_at
  AND ((NEW.revoked_at<=>OLD.revoked_at) OR (OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL)))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RELEASE_IMMUTABLE'; END IF;
END;
CREATE TRIGGER trg_identity_release_bd BEFORE DELETE ON orbit_identity_capability_release FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RELEASE_IMMUTABLE';
CREATE TRIGGER trg_identity_proof_bu BEFORE UPDATE ON orbit_identity_publication_provenance FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_PROVENANCE_IMMUTABLE';
CREATE TRIGGER trg_identity_proof_bd BEFORE DELETE ON orbit_identity_publication_provenance FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_PROVENANCE_IMMUTABLE';
CREATE TRIGGER trg_identity_ledger_bu BEFORE UPDATE ON orbit_identity_publication_ledger FOR EACH ROW
BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id AND NEW.actor_id<=>OLD.actor_id AND NEW.key_hash<=>OLD.key_hash
  AND NEW.intent_hash<=>OLD.intent_hash AND NEW.evidence_id<=>OLD.evidence_id
  AND NEW.receipt_json<=>OLD.receipt_json AND NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_LEDGER_IMMUTABLE'; END IF;
END;
CREATE TRIGGER trg_identity_ledger_bd BEFORE DELETE ON orbit_identity_publication_ledger FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_LEDGER_IMMUTABLE';
