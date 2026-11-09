-- 049：有界查询快照与稳定分页，由显式升级工具执行。
-- 原POST仍只200 Metrics，无新202；BUILDING不可读，同key重放不得创建第二份结果。
CREATE TABLE orbit_metric_query_snapshot (
 tenant_id CHAR(36) NOT NULL COMMENT '当前真实目标租户UUID',
 id CHAR(36) NOT NULL COMMENT '完整查询快照UUID，原query_snapshot_id',
 actor_id BIGINT NOT NULL COMMENT '真实调用者原生用户ID',
 subject_id CHAR(36) NOT NULL COMMENT '当前业务身份UUID',
 auth_version BIGINT NOT NULL COMMENT '真实授权版本，原scope_version来源',
 auth_fingerprint CHAR(64) NOT NULL COMMENT 'actor角色团队与显式管理范围指纹',
 query_hash CHAR(64) NOT NULL COMMENT '全部规范筛选排序和page_size摘要，不包含cursor',
 query_json JSON NOT NULL COMMENT '原13字段规范查询小对象，首次cursor为null，最大16KiB',
 account_scope_snapshot_id CHAR(36) NULL COMMENT '原跨页选择快照ID，空scope不强加50000上限',
 account_scope_hash CHAR(64) NULL COMMENT '复核过的完整不可变成员摘要',
 account_scope_count BIGINT NULL COMMENT '原scope实际成员数量，null不伪造0',
 source_publication_id CHAR(36) NOT NULL COMMENT '同profile版本截至水位锚点UUID，原snapshot_id，不声称包含全部事实',
 source_generation BIGINT NOT NULL COMMENT '全局generation截止水位；事实可来自同profile版本此前各完整publication',
 profile_id CHAR(36) NOT NULL COMMENT '原查询profile UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '冻结完整原profile版本',
 profile_hash CHAR(64) NOT NULL COMMENT '冻结原profile配置摘要',
 algorithm_version VARCHAR(64) NOT NULL COMMENT '明确Decimal与聚合版本，不猜latest',
 state VARCHAR(16) NOT NULL DEFAULT 'BUILDING' COMMENT 'BUILDING、READY、FAILED或EXPIRED；只有READY可读',
 build_generation BIGINT NOT NULL DEFAULT 1 COMMENT '构建claim栅栏代次，旧builder不能发布或清理新代',
 build_token_hash CHAR(64) NOT NULL COMMENT '本次内部构建claim摘要，不存会话Token',
 lease_until DATETIME(3) NOT NULL COMMENT '构建租约UTC时刻，仅用于恢复，不是查询有效期',
 row_count BIGINT NOT NULL DEFAULT 0 COMMENT '完整排序结果行数，不是当前页数',
 row_bytes BIGINT NOT NULL DEFAULT 0 COMMENT '完整排序结果已冻结字节数，供内部预算审计',
 totals_count INT NOT NULL DEFAULT 0 COMMENT '完整分币种profile汇总数量，最大1000',
 expected_account_count BIGINT NOT NULL DEFAULT 0 COMMENT '服务端冻结预期账户基数，不依赖事实返回行数',
 expected_cell_count BIGINT NOT NULL DEFAULT 0 COMMENT '冻结预期account/day/profile单元数',
 missing_count INT NOT NULL DEFAULT 0 COMMENT '完整授权范围缺失单元数量，原非负int范围',
 rows_hash CHAR(64) NULL COMMENT '有序全部rowkey/ordinal/payload摘要根，READY前必须完成',
 totals_hash CHAR(64) NULL COMMENT '完整全范围totals摘要，不能按当前页计算',
 data_as_of DATETIME(3) NOT NULL COMMENT '本查询冻结的实际UTC数据时刻，不自动刷新原结果',
 created_at DATETIME(3) NOT NULL COMMENT '准备查询UTC时刻',
 sealed_at DATETIME(3) NULL COMMENT '完整原子发布排序行和totals的UTC时刻',
 failure_code VARCHAR(64) NULL COMMENT '固定脱敏构建失败/资源预算代码，不回显SQL',
 cleanup_requested BOOLEAN NOT NULL DEFAULT 0 COMMENT '内部回收闸门，设1后新读404；保留幂等墓碑',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_metric_query_actor(tenant_id,id,actor_id),
 UNIQUE KEY uq_metric_query_generation(tenant_id,id,build_generation),
 UNIQUE KEY uq_metric_query_profile(tenant_id,id,profile_id),
 KEY idx_metric_query_reuse(tenant_id,actor_id,query_hash,source_generation,state,id),
 KEY idx_metric_query_lease(state,lease_until,tenant_id,id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(tenant_id,account_scope_snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id),
 FOREIGN KEY(tenant_id,source_publication_id,source_generation,profile_id,profile_version)
  REFERENCES orbit_metric_publication(tenant_id,id,generation,profile_id,profile_version),
 FOREIGN KEY(tenant_id,profile_id,profile_version,profile_hash)
  REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 CHECK(auth_version BETWEEN 1 AND 9007199254740991),
 CHECK(source_generation BETWEEN 1 AND 9007199254740991),
 CHECK(build_generation BETWEEN 1 AND 9007199254740991),
 CHECK(state IN ('BUILDING','READY','FAILED','EXPIRED')),
 CHECK(row_count>=0 AND row_bytes>=0 AND expected_account_count>=0 AND expected_cell_count>=0),
 CHECK(totals_count BETWEEN 0 AND 1000),
 CHECK(missing_count BETWEEN 0 AND 2147483647),
 CHECK((account_scope_snapshot_id IS NULL)=(account_scope_hash IS NULL)),
 CHECK((account_scope_snapshot_id IS NULL)=(account_scope_count IS NULL)),
 CHECK(account_scope_count IS NULL OR account_scope_count BETWEEN 0 AND 50000),
 CHECK(state<>'READY' OR (sealed_at IS NOT NULL AND rows_hash IS NOT NULL AND totals_hash IS NOT NULL)),
 CHECK(JSON_TYPE(query_json)='OBJECT' AND JSON_STORAGE_SIZE(query_json)<=16384),
 CHECK(REGEXP_LIKE(auth_fingerprint,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(query_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(build_token_hash,'^[0-9a-f]{64}$','c')),
 CHECK(account_scope_hash IS NULL OR REGEXP_LIKE(account_scope_hash,'^[0-9a-f]{64}$','c')),
 CHECK(rows_hash IS NULL OR REGEXP_LIKE(rows_hash,'^[0-9a-f]{64}$','c')),
 CHECK(totals_hash IS NULL OR REGEXP_LIKE(totals_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='冻结查询完整manifest候选，claim和预算边界不改变原API';

CREATE TABLE orbit_metric_query_expected_account (
 tenant_id CHAR(36) NOT NULL COMMENT '冻结租户UUID',
 query_id CHAR(36) NOT NULL COMMENT '真实查询快照UUID',
 build_generation BIGINT NOT NULL COMMENT '所属构建代次，旧claim写入或清理必须绑定该代',
 account_id CHAR(36) NOT NULL COMMENT '服务端授权后冻结的完整预期账户ID，不靠客户端拉全量',
 timezone_name VARCHAR(64) NOT NULL COMMENT '查询冻结的IANA账户时区，供逐账户未来日/DST检查',
 expectation_hash CHAR(64) NOT NULL COMMENT '权威预期集合及历史归属检查绑定，不从返回行数生成',
 PRIMARY KEY(tenant_id,query_id,account_id),
 FOREIGN KEY(tenant_id,query_id,build_generation) REFERENCES orbit_metric_query_snapshot(tenant_id,id,build_generation),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 CHECK(REGEXP_LIKE(expectation_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整预期账户集合候选；历史冻结owner仍另行过滤';

CREATE TABLE orbit_metric_query_sorted_row (
 tenant_id CHAR(36) NOT NULL COMMENT '当前可信租户UUID',
 query_id CHAR(36) NOT NULL COMMENT '所属完整查询UUID',
 build_generation BIGINT NOT NULL COMMENT '同一claim构建代次，防迟到旧builder写入当前结果',
 ordinal BIGINT NOT NULL COMMENT '初次已冻结排序的稳定键；续页用大于此键，不用OFFSET',
 row_key_hash CHAR(64) NOT NULL COMMENT 'dataset实体/currency/日期等完整稳定分组键摘要',
 payload_json JSON NOT NULL COMMENT '单条严格原MetricRow15字段，最大16KiB，绝非无限items数组',
 payload_hash CHAR(64) NOT NULL COMMENT '该单条规范JSON摘要，参与有序根对账',
 payload_bytes INT NOT NULL COMMENT '规范UTF8实际字节数，不以字符数代替',
 PRIMARY KEY(tenant_id,query_id,ordinal),
 UNIQUE KEY uq_metric_query_row_key(tenant_id,query_id,row_key_hash),
 FOREIGN KEY(tenant_id,query_id,build_generation) REFERENCES orbit_metric_query_snapshot(tenant_id,id,build_generation),
 CHECK(ordinal BETWEEN 1 AND 9007199254740991),
 CHECK(payload_bytes BETWEEN 1 AND 16384),
 CHECK(JSON_TYPE(payload_json)='OBJECT' AND JSON_STORAGE_SIZE(payload_json)<=16384),
 CHECK(REGEXP_LIKE(row_key_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(payload_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='按原排序一次性冻结的独立结果行候选；后续四档只键集读';

CREATE TABLE orbit_metric_query_total (
 tenant_id CHAR(36) NOT NULL COMMENT '真实tenant分组',
 query_id CHAR(36) NOT NULL COMMENT '完整查询UUID',
 build_generation BIGINT NOT NULL COMMENT '汇总所属claim代次，和排序行一次原子发布',
 currency CHAR(3) NOT NULL COMMENT '独立币种，禁止换汇或跨币种求和',
 profile_id CHAR(36) NOT NULL COMMENT '独立精确profile分组',
 payload_json JSON NOT NULL COMMENT '单条原MetricTotal8字段，最大16KiB，完整筛选全范围汇总',
 payload_hash CHAR(64) NOT NULL COMMENT '规范汇总摘要，参与完整totals根',
 PRIMARY KEY(tenant_id,query_id,currency,profile_id),
 FOREIGN KEY(tenant_id,query_id,build_generation) REFERENCES orbit_metric_query_snapshot(tenant_id,id,build_generation),
 FOREIGN KEY(tenant_id,query_id,profile_id) REFERENCES orbit_metric_query_snapshot(tenant_id,id,profile_id),
 CHECK(JSON_TYPE(payload_json)='OBJECT' AND JSON_STORAGE_SIZE(payload_json)<=16384),
 CHECK(REGEXP_LIKE(payload_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='全量授权totals只构建一次，不随当前页重算';

CREATE TABLE orbit_metric_query_request (
 tenant_id CHAR(36) NOT NULL COMMENT '原请求目标租户',
 actor_id BIGINT NOT NULL COMMENT '真实操作者，每次重放仍重新授权',
 key_hash CHAR(64) NOT NULL COMMENT 'ASCII幂等键SHA256，不保存认证或CSRF',
 request_hash CHAR(64) NOT NULL COMMENT '原完整13字段含cursor的规范正文及动作摘要',
 query_id CHAR(36) NOT NULL COMMENT '首次已固定的查询UUID，失败或过期不重建其他结果',
 after_ordinal BIGINT NOT NULL COMMENT '本次页的原始键，首次0，不用SQL OFFSET',
 page_size INT NOT NULL COMMENT '本次请求固定20/50/100/200，与cursor绑定',
 request_id CHAR(36) NOT NULL COMMENT '本次受控读取请求UUID，重放编号不作为业务版本',
 created_at DATETIME(3) NOT NULL COMMENT '原始意图登记UTC时刻',
 PRIMARY KEY(tenant_id,actor_id,key_hash),
 FOREIGN KEY(tenant_id,query_id,actor_id) REFERENCES orbit_metric_query_snapshot(tenant_id,id,actor_id),
 CHECK(after_ordinal BETWEEN 0 AND 9007199254740991),
 CHECK(page_size IN (20,50,100,200)),
 CHECK(REGEXP_LIKE(key_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(request_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='查询幂等意图及页边界候选，不存巨大response JSON或复制整包';

-- READY只有技术cleanup0->1可变，冻结结果不得靠refresh/超时改写。
-- 请求身份/输入/授权/来源从创建起就不可变，BUILDING也不得换payload复用同一query_id。
CREATE TRIGGER metric_query_identity_guard BEFORE UPDATE ON orbit_metric_query_snapshot
 FOR EACH ROW BEGIN
 IF NOT (NEW.tenant_id<=>OLD.tenant_id) OR NOT (NEW.id<=>OLD.id)
  OR NOT (NEW.actor_id<=>OLD.actor_id) OR NOT (NEW.subject_id<=>OLD.subject_id)
  OR NOT (NEW.auth_version<=>OLD.auth_version) OR NOT (NEW.auth_fingerprint<=>OLD.auth_fingerprint)
  OR NOT (NEW.query_hash<=>OLD.query_hash) OR NOT (NEW.query_json<=>OLD.query_json)
  OR NOT (NEW.account_scope_snapshot_id<=>OLD.account_scope_snapshot_id)
  OR NOT (NEW.account_scope_hash<=>OLD.account_scope_hash) OR NOT (NEW.account_scope_count<=>OLD.account_scope_count)
  OR NOT (NEW.source_publication_id<=>OLD.source_publication_id) OR NOT (NEW.source_generation<=>OLD.source_generation)
  OR NOT (NEW.profile_id<=>OLD.profile_id) OR NOT (NEW.profile_version<=>OLD.profile_version)
  OR NOT (NEW.profile_hash<=>OLD.profile_hash) OR NOT (NEW.algorithm_version<=>OLD.algorithm_version)
  OR NOT (NEW.data_as_of<=>OLD.data_as_of) OR NOT (NEW.created_at<=>OLD.created_at)
  OR NEW.build_generation<OLD.build_generation OR NEW.cleanup_requested<OLD.cleanup_requested
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_INTENT_IMMUTABLE';
 END IF;
 END;
CREATE TRIGGER metric_query_ready_guard BEFORE UPDATE ON orbit_metric_query_snapshot
 FOR EACH ROW BEGIN
 IF OLD.state='READY' AND (
  NOT (NEW.tenant_id<=>OLD.tenant_id) OR NOT (NEW.id<=>OLD.id) OR NOT (NEW.actor_id<=>OLD.actor_id)
  OR NOT (NEW.subject_id<=>OLD.subject_id) OR NOT (NEW.auth_version<=>OLD.auth_version)
  OR NOT (NEW.auth_fingerprint<=>OLD.auth_fingerprint) OR NOT (NEW.query_hash<=>OLD.query_hash)
  OR NOT (NEW.query_json<=>OLD.query_json)
  OR NOT (NEW.account_scope_snapshot_id<=>OLD.account_scope_snapshot_id)
  OR NOT (NEW.account_scope_hash<=>OLD.account_scope_hash) OR NOT (NEW.account_scope_count<=>OLD.account_scope_count)
  OR NOT (NEW.source_publication_id<=>OLD.source_publication_id) OR NOT (NEW.source_generation<=>OLD.source_generation)
  OR NOT (NEW.profile_id<=>OLD.profile_id) OR NOT (NEW.profile_version<=>OLD.profile_version)
  OR NOT (NEW.profile_hash<=>OLD.profile_hash) OR NOT (NEW.algorithm_version<=>OLD.algorithm_version)
  OR NOT (NEW.state<=>OLD.state) OR NOT (NEW.build_generation<=>OLD.build_generation)
  OR NOT (NEW.build_token_hash<=>OLD.build_token_hash) OR NOT (NEW.lease_until<=>OLD.lease_until)
  OR NOT (NEW.row_count<=>OLD.row_count) OR NOT (NEW.row_bytes<=>OLD.row_bytes)
  OR NOT (NEW.totals_count<=>OLD.totals_count) OR NOT (NEW.expected_account_count<=>OLD.expected_account_count)
  OR NOT (NEW.expected_cell_count<=>OLD.expected_cell_count) OR NOT (NEW.missing_count<=>OLD.missing_count)
  OR NOT (NEW.rows_hash<=>OLD.rows_hash) OR NOT (NEW.totals_hash<=>OLD.totals_hash)
  OR NOT (NEW.data_as_of<=>OLD.data_as_of) OR NOT (NEW.created_at<=>OLD.created_at)
  OR NOT (NEW.sealed_at<=>OLD.sealed_at) OR NOT (NEW.failure_code<=>OLD.failure_code)
  OR NEW.cleanup_requested<OLD.cleanup_requested
 ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_READY_IMMUTABLE';
 END IF;
 END;
CREATE TRIGGER metric_query_parent_delete_guard BEFORE DELETE ON orbit_metric_query_snapshot
 FOR EACH ROW BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_IDEMPOTENCY_TOMBSTONE_REQUIRED';
 END;
CREATE TRIGGER metric_query_request_update_guard BEFORE UPDATE ON orbit_metric_query_request
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_REQUEST_IMMUTABLE';
CREATE TRIGGER metric_query_request_delete_guard BEFORE DELETE ON orbit_metric_query_request
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_REQUEST_TOMBSTONE_REQUIRED';

CREATE TRIGGER metric_query_account_insert_guard BEFORE INSERT ON orbit_metric_query_expected_account
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=NEW.tenant_id AND id=NEW.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_account_update_guard BEFORE UPDATE ON orbit_metric_query_expected_account
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.query_id<>OLD.query_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_account_delete_guard BEFORE DELETE ON orbit_metric_query_expected_account
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state NOT IN ('BUILDING','FAILED','EXPIRED') AND NOT query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_row_insert_guard BEFORE INSERT ON orbit_metric_query_sorted_row
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=NEW.tenant_id AND id=NEW.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_row_update_guard BEFORE UPDATE ON orbit_metric_query_sorted_row
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.query_id<>OLD.query_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_row_delete_guard BEFORE DELETE ON orbit_metric_query_sorted_row
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state NOT IN ('BUILDING','FAILED','EXPIRED') AND NOT query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_total_insert_guard BEFORE INSERT ON orbit_metric_query_total
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=NEW.tenant_id AND id=NEW.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_total_update_guard BEFORE UPDATE ON orbit_metric_query_total
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state<>'BUILDING' OR query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.query_id<>OLD.query_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_query_total_delete_guard BEFORE DELETE ON orbit_metric_query_total
 FOR EACH ROW BEGIN
 DECLARE query_state VARCHAR(16) DEFAULT NULL;
 DECLARE query_cleanup BOOLEAN DEFAULT FALSE;
 SELECT state,cleanup_requested INTO query_state,query_cleanup FROM orbit_metric_query_snapshot
 WHERE tenant_id=OLD.tenant_id AND id=OLD.query_id FOR SHARE;
 IF query_state IS NULL OR (query_state NOT IN ('BUILDING','FAILED','EXPIRED') AND NOT query_cleanup) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_QUERY_CHILD_IMMUTABLE';
 END IF;
 END;
