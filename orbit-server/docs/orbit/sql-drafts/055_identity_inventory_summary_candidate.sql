-- 055候选：仅系统完整性封印，绝不是Meta能力发行；主线审阅采用后才执行。
-- 维护窗口/应用启动前执行DDL及存量冻结回填；DDL隐式提交，不承诺在线无保护间隙。
-- 合法发布顺序：E -> H -> resources -> head -> provenance(BI冻结H) -> seal。
-- 旧provenance只冻结，不自动生成MAC；无seal的旧证据列表保持UNKNOWN。
ALTER TABLE orbit_account_identity_history
 ADD COLUMN provenance_frozen BOOLEAN NOT NULL DEFAULT 0 COMMENT '内部单调完整性冻结位，不是verified或平台权威',
 ADD CONSTRAINT ck_identity_history_freeze CHECK(provenance_frozen IN (0,1));

CREATE TABLE orbit_identity_inventory_seal (
 tenant_id CHAR(36) NOT NULL COMMENT '同租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '完整库存账户UUID',
 revision BIGINT NOT NULL COMMENT '冻结身份快照正安全整数版本',
 evidence_id CHAR(36) NOT NULL COMMENT '原023证据UUID',
 registry_id CHAR(36) NOT NULL COMMENT '045原始库存UUID',
 release_id CHAR(36) NOT NULL COMMENT '独立能力发行UUID',
 release_revision BIGINT NOT NULL COMMENT '原发行精确版本',
 release_source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整发行来源根',
 source_config_id CHAR(36) NOT NULL COMMENT '原META_BM配置UUID',
 source_config_revision BIGINT NOT NULL COMMENT '原META_BM精确配置版本',
 account_revision BIGINT NOT NULL COMMENT '观察发布绑定的账户版本',
 capability_version VARCHAR(64) NOT NULL COMMENT '原DTO能力版本；MAC不发行能力',
 resource_count INT NOT NULL COMMENT '完整资源条数；0仅完整空库存',
 observed_at DATETIME(3) NOT NULL COMMENT '原DTO UTC毫秒向下投影',
 raw_observed_at DATETIME(6) NOT NULL COMMENT '保留来源UTC微秒，不以数据库舍入替代',
 raw_credential_expires_at DATETIME(6) NULL COMMENT '原已知到期微秒；NULL不猜TTL',
 bound_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整原始库存根',
 principal_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '配置主体匹配根',
 facts_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整事实根',
 principal_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '配置主体实际数字ID，不证明主体类型',
 projection_version VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '固定UTC_FLOOR_MS_V1',
 payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整原DTO与资源规范根',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整发布意图根',
 authority_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原来源类别；标签不是授权',
 key_id VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际MAC密钥ID；未知或退役只UNKNOWN',
 mac CHAR(43) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'IDENTITY_SUMMARY_SEAL_V1系统完整性MAC，不含密钥',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '真实登记UTC微秒，不进入来源MAC',
 PRIMARY KEY(tenant_id,evidence_id),
 UNIQUE KEY uk_identity_seal_version(tenant_id,account_id,revision),
 CONSTRAINT fk_identity_seal_proof FOREIGN KEY(tenant_id,evidence_id)
 REFERENCES orbit_identity_publication_provenance(tenant_id,evidence_id),
 CONSTRAINT fk_identity_seal_history FOREIGN KEY(tenant_id,account_id,revision)
 REFERENCES orbit_account_identity_history(tenant_id,account_id,revision),
 CONSTRAINT ck_identity_inventory_seal CHECK((
 revision BETWEEN 1 AND 9007199254740991
 AND release_revision BETWEEN 1 AND 9007199254740991
 AND source_config_revision BETWEEN 1 AND 9007199254740991
 AND account_revision BETWEEN 1 AND 9007199254740991
 AND resource_count BETWEEN 0 AND 5000
 AND CHAR_LENGTH(capability_version) BETWEEN 1 AND 64
 AND principal_id REGEXP '^[0-9]{1,64}$'
 AND projection_version='UTC_FLOOR_MS_V1'
 AND authority_kind IN ('TRUSTED','ISOLATED_TEST')
 AND key_id REGEXP '^[A-Za-z0-9_-]{1,40}$'
 AND mac REGEXP '^[A-Za-z0-9_-]{43}$'
 AND observed_at=TIMESTAMPADD(MICROSECOND,-MOD(MICROSECOND(raw_observed_at),1000),raw_observed_at)
 AND (raw_credential_expires_at IS NULL OR raw_credential_expires_at>raw_observed_at)
 AND release_source_hash REGEXP '^[0-9a-f]{64}$'
 AND bound_sha256 REGEXP '^[0-9a-f]{64}$'
 AND principal_sha256 REGEXP '^[0-9a-f]{64}$'
 AND facts_sha256 REGEXP '^[0-9a-f]{64}$'
 AND payload_hash REGEXP '^[0-9a-f]{64}$'
 AND intent_hash REGEXP '^[0-9a-f]{64}$') IS TRUE)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='有界列表完整性封印；只有后台完整重算可发行MAC，不是平台授权';

CREATE TRIGGER trg_identity_history_freeze_bu BEFORE UPDATE ON orbit_account_identity_history FOR EACH ROW
BEGIN
 IF (OLD.provenance_frozen=1 OR NEW.provenance_frozen=1)
  AND NOT(NEW.tenant_id<=>OLD.tenant_id AND
   NEW.account_id<=>OLD.account_id AND
   NEW.revision<=>OLD.revision AND
   NEW.evidence_id<=>OLD.evidence_id AND
   NEW.capability_version<=>OLD.capability_version AND
   NEW.observed_at<=>OLD.observed_at AND
   NEW.resource_count<=>OLD.resource_count AND
   NEW.request_id<=>OLD.request_id AND
   NEW.created_at<=>OLD.created_at AND NEW.provenance_frozen>=OLD.provenance_frozen)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_HISTORY_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_history_freeze_bd BEFORE DELETE ON orbit_account_identity_history FOR EACH ROW
BEGIN
 IF OLD.provenance_frozen=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_HISTORY_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_resource_freeze_bi BEFORE INSERT ON orbit_account_identity_resource FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id AND revision=NEW.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_resource_freeze_bd BEFORE DELETE ON orbit_account_identity_resource FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=OLD.tenant_id AND account_id=OLD.account_id AND revision=OLD.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_resource_freeze_bu BEFORE UPDATE ON orbit_account_identity_resource FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 -- 最多两个真实父行，按复合PK排序；直接SQL已持resource锁仍可1213，整笔必须回滚。
 IF (OLD.tenant_id,OLD.account_id,OLD.revision)<=(NEW.tenant_id,NEW.account_id,NEW.revision) THEN
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=OLD.tenant_id AND account_id=OLD.account_id AND revision=OLD.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id AND revision=NEW.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
 ELSE
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id AND revision=NEW.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=OLD.tenant_id AND account_id=OLD.account_id AND revision=OLD.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_RESOURCE_FROZEN'; END IF;
 END IF;
END;

CREATE TRIGGER trg_identity_evidence_freeze_bu BEFORE UPDATE ON orbit_account_identity_evidence FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 DECLARE item_value INT;
 DECLARE ended BOOLEAN DEFAULT FALSE;
 DECLARE protected_rows CURSOR FOR SELECT provenance_frozen FROM orbit_account_identity_history
  WHERE tenant_id=OLD.tenant_id AND evidence_id=OLD.id ORDER BY account_id,revision FOR SHARE;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET ended=TRUE;
 OPEN protected_rows;
 evidence_loop: LOOP
  FETCH protected_rows INTO item_value;
  IF ended THEN LEAVE evidence_loop; END IF;
  IF item_value=1 THEN SET frozen_value=1; END IF;
 END LOOP;
 CLOSE protected_rows;
 IF frozen_value=1 AND NOT(NEW.tenant_id<=>OLD.tenant_id AND
   NEW.id<=>OLD.id AND
   NEW.account_id<=>OLD.account_id AND
   NEW.account_revision<=>OLD.account_revision AND
   NEW.source_config_id<=>OLD.source_config_id AND
   NEW.source_config_revision<=>OLD.source_config_revision AND
   NEW.capability_version<=>OLD.capability_version AND
   NEW.payload_hash<=>OLD.payload_hash AND
   NEW.observed_at<=>OLD.observed_at AND
   NEW.complete<=>OLD.complete AND
   NEW.verified<=>OLD.verified AND
   NEW.credential_expires_at<=>OLD.credential_expires_at AND
   NEW.evidence_ref<=>OLD.evidence_ref AND
   NEW.created_at<=>OLD.created_at AND
  ((NEW.revoked_at<=>OLD.revoked_at) OR (OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL)))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_EVIDENCE_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_evidence_freeze_bd BEFORE DELETE ON orbit_account_identity_evidence FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 DECLARE item_value INT;
 DECLARE ended BOOLEAN DEFAULT FALSE;
 DECLARE protected_rows CURSOR FOR SELECT provenance_frozen FROM orbit_account_identity_history
  WHERE tenant_id=OLD.tenant_id AND evidence_id=OLD.id ORDER BY account_id,revision FOR SHARE;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET ended=TRUE;
 OPEN protected_rows;
 evidence_loop: LOOP
  FETCH protected_rows INTO item_value;
  IF ended THEN LEAVE evidence_loop; END IF;
  IF item_value=1 THEN SET frozen_value=1; END IF;
 END LOOP;
 CLOSE protected_rows;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_EVIDENCE_FROZEN'; END IF;
END;

CREATE TRIGGER trg_identity_head_freeze_bu BEFORE UPDATE ON orbit_account_identity_head FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=OLD.tenant_id AND account_id=OLD.account_id AND revision=OLD.revision FOR SHARE;
 IF frozen_value=1 AND NOT(NEW.tenant_id<=>OLD.tenant_id AND NEW.account_id<=>OLD.account_id
  AND NEW.revision>=OLD.revision) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_HEAD_ROLLBACK'; END IF;
END;

CREATE TRIGGER trg_identity_head_freeze_bd BEFORE DELETE ON orbit_account_identity_head FOR EACH ROW
BEGIN
 DECLARE frozen_value INT DEFAULT 0;
 SELECT provenance_frozen INTO frozen_value FROM orbit_account_identity_history
 WHERE tenant_id=OLD.tenant_id AND account_id=OLD.account_id AND revision=OLD.revision FOR SHARE;
 IF frozen_value=1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_HEAD_ROLLBACK'; END IF;
END;

CREATE TRIGGER trg_identity_proof_freeze_bi BEFORE INSERT ON orbit_identity_publication_provenance FOR EACH ROW
BEGIN
 DECLARE evidence_account CHAR(36);
 DECLARE evidence_hash CHAR(64);
 DECLARE evidence_observed DATETIME(3);
 DECLARE history_evidence CHAR(36);
 DECLARE history_observed DATETIME(3);
 DECLARE history_count INT;
 SELECT account_id,payload_hash,observed_at INTO evidence_account,evidence_hash,evidence_observed
 FROM orbit_account_identity_evidence WHERE tenant_id=NEW.tenant_id AND id=NEW.evidence_id FOR SHARE;
 SELECT evidence_id,observed_at,resource_count INTO history_evidence,history_observed,history_count
 FROM orbit_account_identity_history WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id
 AND revision=NEW.identity_revision FOR UPDATE;
 IF evidence_account IS NULL OR history_evidence IS NULL OR NOT(evidence_account<=>NEW.account_id)
  OR NOT(history_evidence<=>NEW.evidence_id) OR NOT(evidence_hash<=>NEW.payload_hash)
  OR NOT(evidence_observed<=>history_observed)
  OR NOT(evidence_observed<=>TIMESTAMPADD(MICROSECOND,-MOD(MICROSECOND(NEW.raw_observed_at),1000),NEW.raw_observed_at))
  OR history_count IS NULL OR history_count<0 OR history_count>5000
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_PROVENANCE_BINDING'; END IF;
 UPDATE orbit_account_identity_history SET provenance_frozen=1
 WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id AND revision=NEW.identity_revision;
END;

CREATE TRIGGER trg_identity_inventory_seal_bi BEFORE INSERT ON orbit_identity_inventory_seal FOR EACH ROW
BEGIN
 DECLARE actual_tenant_id CHAR(36);
 DECLARE actual_account_id CHAR(36);
 DECLARE actual_revision BIGINT;
 DECLARE actual_evidence_id CHAR(36);
 DECLARE actual_registry_id CHAR(36);
 DECLARE actual_release_id CHAR(36);
 DECLARE actual_release_revision BIGINT;
 DECLARE actual_release_source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_source_config_id CHAR(36);
 DECLARE actual_source_config_revision BIGINT;
 DECLARE actual_account_revision BIGINT;
 DECLARE actual_capability_version VARCHAR(64);
 DECLARE actual_resource_count INT;
 DECLARE actual_observed_at DATETIME(3);
 DECLARE actual_raw_observed_at DATETIME(6);
 DECLARE actual_raw_credential_expires_at DATETIME(6);
 DECLARE actual_bound_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_principal_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_facts_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_principal_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_projection_version VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE actual_authority_kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin;
 DECLARE evidence_frozen INT;
 DECLARE found_kind VARCHAR(16);
 DECLARE found_external VARCHAR(64);
 DECLARE actual_count INT DEFAULT 0;
 DECLARE ended BOOLEAN DEFAULT FALSE;
 DECLARE resource_rows CURSOR FOR SELECT kind,external_id FROM orbit_account_identity_resource
  FORCE INDEX(PRIMARY) WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id
  AND revision=NEW.revision ORDER BY kind,external_id FOR SHARE;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET ended=TRUE;
 -- E -> H -> P，与发布/撤销的当前锁方向一致；current读不能使用RR旧view。
 SELECT id INTO actual_evidence_id FROM orbit_account_identity_evidence
 WHERE tenant_id=NEW.tenant_id AND id=NEW.evidence_id FOR SHARE;
 SELECT provenance_frozen INTO evidence_frozen FROM orbit_account_identity_history
 WHERE tenant_id=NEW.tenant_id AND account_id=NEW.account_id AND revision=NEW.revision FOR SHARE;
 SELECT p.tenant_id, p.account_id, p.identity_revision, p.evidence_id, p.registry_id, p.release_id, p.release_revision, p.release_source_hash, e.source_config_id, e.source_config_revision, e.account_revision, h.capability_version, h.resource_count, h.observed_at, p.raw_observed_at, p.raw_credential_expires_at, p.bound_sha256, p.principal_sha256, p.facts_sha256, p.principal_id, p.projection_version, p.payload_hash, p.intent_hash, p.authority_kind INTO actual_tenant_id, actual_account_id, actual_revision, actual_evidence_id, actual_registry_id, actual_release_id, actual_release_revision, actual_release_source_hash, actual_source_config_id, actual_source_config_revision, actual_account_revision, actual_capability_version, actual_resource_count, actual_observed_at, actual_raw_observed_at, actual_raw_credential_expires_at, actual_bound_sha256, actual_principal_sha256, actual_facts_sha256, actual_principal_id, actual_projection_version, actual_payload_hash, actual_intent_hash, actual_authority_kind
 FROM orbit_identity_publication_provenance p
 JOIN orbit_account_identity_evidence e ON e.tenant_id=p.tenant_id AND e.id=p.evidence_id
 JOIN orbit_account_identity_history h ON h.tenant_id=p.tenant_id AND h.account_id=p.account_id
  AND h.revision=p.identity_revision
 WHERE p.tenant_id=NEW.tenant_id AND p.evidence_id=NEW.evidence_id FOR SHARE OF p,e,h;
 IF ended OR evidence_frozen IS NULL OR evidence_frozen<>1 OR NOT(NEW.tenant_id<=>actual_tenant_id) OR
  NOT(NEW.account_id<=>actual_account_id) OR
  NOT(NEW.revision<=>actual_revision) OR
  NOT(NEW.evidence_id<=>actual_evidence_id) OR
  NOT(NEW.registry_id<=>actual_registry_id) OR
  NOT(NEW.release_id<=>actual_release_id) OR
  NOT(NEW.release_revision<=>actual_release_revision) OR
  NOT(NEW.release_source_hash<=>actual_release_source_hash) OR
  NOT(NEW.source_config_id<=>actual_source_config_id) OR
  NOT(NEW.source_config_revision<=>actual_source_config_revision) OR
  NOT(NEW.account_revision<=>actual_account_revision) OR
  NOT(NEW.capability_version<=>actual_capability_version) OR
  NOT(NEW.resource_count<=>actual_resource_count) OR
  NOT(NEW.observed_at<=>actual_observed_at) OR
  NOT(NEW.raw_observed_at<=>actual_raw_observed_at) OR
  NOT(NEW.raw_credential_expires_at<=>actual_raw_credential_expires_at) OR
  NOT(NEW.bound_sha256<=>actual_bound_sha256) OR
  NOT(NEW.principal_sha256<=>actual_principal_sha256) OR
  NOT(NEW.facts_sha256<=>actual_facts_sha256) OR
  NOT(NEW.principal_id<=>actual_principal_id) OR
  NOT(NEW.projection_version<=>actual_projection_version) OR
  NOT(NEW.payload_hash<=>actual_payload_hash) OR
  NOT(NEW.intent_hash<=>actual_intent_hash) OR
  NOT(NEW.authority_kind<=>actual_authority_kind)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_SEAL_BINDING'; END IF;
 SET ended=FALSE;
 OPEN resource_rows;
 resource_loop: LOOP
  FETCH resource_rows INTO found_kind,found_external;
  IF ended THEN LEAVE resource_loop; END IF;
  SET actual_count=actual_count+1;
  IF actual_count>5000 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_SEAL_COUNT'; END IF;
 END LOOP;
 CLOSE resource_rows;
 IF actual_count<>NEW.resource_count THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_SEAL_COUNT'; END IF;
 -- DB只证明绑定/计数；完整资源SHA与MAC由backend先核，密钥从不进入SQL。

END;

CREATE TRIGGER trg_identity_inventory_seal_bu BEFORE UPDATE ON orbit_identity_inventory_seal FOR EACH ROW
BEGIN
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_SEAL_IMMUTABLE';
END;

CREATE TRIGGER trg_identity_inventory_seal_bd BEFORE DELETE ON orbit_identity_inventory_seal FOR EACH ROW
BEGIN
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='IDENTITY_SEAL_IMMUTABLE';
END;

-- 维护窗口回填仅冻结原真实proof对应历史，不猜测旧行有效，更不自动补seal。
UPDATE orbit_account_identity_history h JOIN orbit_identity_publication_provenance p
 ON p.tenant_id=h.tenant_id AND p.account_id=h.account_id AND p.identity_revision=h.revision
 SET h.provenance_frozen=1;
