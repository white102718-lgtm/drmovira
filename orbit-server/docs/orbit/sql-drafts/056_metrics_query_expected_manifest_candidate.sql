-- 056候选：须主线审阅/采用/显式升级，不能由查询GET或工具自行执行。
-- 旧行兼容NULL，但不能作为新结果构建或READY重放依据。
ALTER TABLE orbit_metric_query_snapshot
 ADD COLUMN expected_unit_hash CHAR(64) NULL COMMENT 'T1独立受信预期单元有序规范根，非实际返回cell根',
 ADD COLUMN expected_membership_hash CHAR(64) NULL COMMENT 'T1完整预期实体成员有序规范根，不能从已有事实推算',
 ADD COLUMN expected_membership_count BIGINT NULL COMMENT '完整独立预期实体成员数量，重建必须精确对账',
 ADD COLUMN expected_manifest_version VARCHAR(64) COLLATE utf8mb4_bin NULL COMMENT '完整预期流规范算法版本，T1后不得改写',
 ADD CONSTRAINT ck_metric_query_expected_manifest CHECK ((
  (expected_unit_hash IS NULL AND expected_membership_hash IS NULL
   AND expected_membership_count IS NULL AND expected_manifest_version IS NULL)
  OR (expected_unit_hash IS NOT NULL AND expected_membership_hash IS NOT NULL
   AND expected_membership_count IS NOT NULL
   AND expected_membership_count BETWEEN 0 AND 9007199254740991
   AND expected_manifest_version IS NOT NULL AND CHAR_LENGTH(expected_manifest_version) BETWEEN 1 AND 64
   AND REGEXP_LIKE(expected_unit_hash,'^[0-9a-f]{64}$','c')
   AND REGEXP_LIKE(expected_membership_hash,'^[0-9a-f]{64}$','c'))
 ) IS TRUE),
 ADD CONSTRAINT ck_metric_query_expected_safe_count CHECK (
  expected_account_count BETWEEN 0 AND 9007199254740991
  AND expected_cell_count BETWEEN 0 AND 9007199254740991
 );

CREATE TRIGGER metric_query_expected_manifest_guard BEFORE UPDATE ON orbit_metric_query_snapshot
 FOR EACH ROW BEGIN
 IF NOT (NEW.expected_unit_hash<=>OLD.expected_unit_hash)
  OR NOT (NEW.expected_membership_hash<=>OLD.expected_membership_hash)
  OR NOT (NEW.expected_membership_count<=>OLD.expected_membership_count)
  OR NOT (NEW.expected_manifest_version<=>OLD.expected_manifest_version)
  OR NOT (NEW.expected_cell_count<=>OLD.expected_cell_count)
  OR NOT (NEW.expected_account_count<=>OLD.expected_account_count)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_EXPECTATION_IMMUTABLE';
 END IF;
 END;
