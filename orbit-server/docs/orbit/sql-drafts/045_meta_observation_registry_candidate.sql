-- M2候选：只存原始Meta观察，不写023、不改变账户，不授权执行；主线审阅后才可采用。
-- ledger先完整预留，故有意不设ledger→head FK；方法同外层事务写全，重放核真实head。
CREATE TABLE orbit_meta_raw_head (
 tenant_id CHAR(36) NOT NULL COMMENT '服务端当前业务租户UUID',
 id CHAR(36) NOT NULL COMMENT '原始观察登记UUID，非Task',
 actor_id BIGINT NOT NULL COMMENT '原accounts.sync实际调用方原生用户ID',
 subject_id CHAR(36) NOT NULL COMMENT '捕获时业务主体UUID',
 auth_version BIGINT NOT NULL COMMENT '新登记通过最终CAS的捕获授权版本',
 account_clock BIGINT NOT NULL COMMENT '新登记通过最终CAS的账户水位，不因登记更新',
 source_config_id CHAR(36) NOT NULL COMMENT '明确META_BM来源配置UUID',
 source_config_revision BIGINT NOT NULL COMMENT '最终当前核验来源版本，不含Token',
 business_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际BM数字文本，保留前导零',
 graph_version VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '明确配置graphVersion，不猜默认版本',
 captured_at DATETIME(6) NOT NULL COMMENT 'M1账户与配置捕获UTC微秒原精度',
 started_at DATETIME(6) NOT NULL COMMENT '事务外网络观察开始UTC微秒原精度',
 observed_at DATETIME(6) NOT NULL COMMENT '完整分页结束UTC微秒原精度，非能力有效期',
 source_binding_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'M1业务主体与账户来源绑定根，不含凭据',
 observation_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整原观察规范正文SHA256',
 bound_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '绑定根和观察根的组合SHA256',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整准备根含计数及全部行hash',
 account_count INT NOT NULL COMMENT '完整账户数量1至500',
 resource_count INT NOT NULL COMMENT '全部账户原始资源数量，未知不补资源',
 request_count INT NOT NULL COMMENT '本轮实际Graph GET数，非平台写入数',
 response_bytes INT NOT NULL COMMENT '本轮实际响应字节数，上限32MiB',
 stored_bytes INT NOT NULL COMMENT '登记小行规范计费字节数，上限32MiB',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '数据库登记UTC微秒原精度',
 PRIMARY KEY(tenant_id,id),
 KEY idx_meta_raw_source(tenant_id,source_config_id,source_config_revision,observed_at,id),
 KEY idx_meta_raw_observed(tenant_id,observed_at,id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(actor_id) REFERENCES sys_user(user_id),
 CONSTRAINT ck_meta_raw_revisions CHECK(auth_version BETWEEN 1 AND 9007199254740991 AND account_clock BETWEEN 1 AND 9007199254740991 AND source_config_revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_meta_raw_window CHECK(captured_at<=started_at AND started_at<=observed_at),
 CONSTRAINT ck_meta_raw_counts CHECK(account_count BETWEEN 1 AND 500 AND resource_count BETWEEN 0 AND 2500000 AND request_count BETWEEN 1 AND 2500 AND response_bytes BETWEEN 1 AND 33554432 AND stored_bytes BETWEEN 1 AND 33554432),
 CONSTRAINT ck_meta_raw_hashes CHECK(source_binding_sha256 REGEXP '^[a-f0-9]{64}$' AND observation_sha256 REGEXP '^[a-f0-9]{64}$' AND bound_sha256 REGEXP '^[a-f0-9]{64}$' AND intent_hash REGEXP '^[a-f0-9]{64}$'),
 CONSTRAINT ck_meta_raw_source_text CHECK(business_id REGEXP '^[0-9]{1,64}$' AND graph_version REGEXP '^v[0-9]{1,3}\\.[0-9]{1,2}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原始只读Meta观察，非身份能力或执行授权';

CREATE TABLE orbit_meta_raw_account (
 tenant_id CHAR(36) NOT NULL COMMENT '同租户原始观察范围',
 registry_id CHAR(36) NOT NULL COMMENT '所属完整观察登记UUID',
 account_id CHAR(36) NOT NULL COMMENT '内部账户UUID，不拿平台ID代替',
 account_revision BIGINT NOT NULL COMMENT '新登记最终核验的账户版本',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '平台数字ID原文，不转整数',
 owner_user_id CHAR(36) NOT NULL COMMENT '捕获并最终CAS核验的投手归属',
 owner_team_id CHAR(36) NOT NULL COMMENT '捕获并最终CAS核验的团队归属',
 metadata_json JSON NOT NULL COMMENT '明确原始六字段，缺失保留null，未映射内部状态',
 bm_edges_json JSON NOT NULL COMMENT '实际观察到的owned/client边来源',
 unknown_json JSON NOT NULL COMMENT '原始未知字段原因集合，不伪造可用性',
 resource_count INT NOT NULL COMMENT '该账户完整资源数0至5000',
 row_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '本账户全部小行字段规范SHA256',
 PRIMARY KEY(tenant_id,registry_id,account_id),
 KEY idx_meta_raw_account_history(tenant_id,account_id,registry_id),
 FOREIGN KEY(tenant_id,registry_id) REFERENCES orbit_meta_raw_head(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 CONSTRAINT ck_meta_raw_account_values CHECK(account_revision BETWEEN 1 AND 9007199254740991 AND resource_count BETWEEN 0 AND 5000 AND external_id REGEXP '^[0-9]{1,64}$' AND row_hash REGEXP '^[a-f0-9]{64}$'),
 CONSTRAINT ck_meta_raw_account_json CHECK(JSON_TYPE(metadata_json)='OBJECT' AND JSON_TYPE(bm_edges_json)='ARRAY' AND JSON_LENGTH(bm_edges_json) BETWEEN 1 AND 2 AND JSON_TYPE(unknown_json)='ARRAY')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户原始观察小行，不更新账户现态';

CREATE TABLE orbit_meta_raw_resource (
 tenant_id CHAR(36) NOT NULL COMMENT '同租户原始资源范围',
 registry_id CHAR(36) NOT NULL COMMENT '所属完整登记UUID',
 account_id CHAR(36) NOT NULL COMMENT '逐账户资源观察绑定UUID',
 kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'PAGE、PIXEL或APPLICATION原始种类',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '平台资源数字ID原文',
 name VARCHAR(4096) NULL COMMENT '原平台名称原文，未知为NULL，禁止255截断',
 row_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '账户与资源原字段规范SHA256',
 PRIMARY KEY(tenant_id,registry_id,account_id,kind,external_id),
 FOREIGN KEY(tenant_id,registry_id,account_id) REFERENCES orbit_meta_raw_account(tenant_id,registry_id,account_id),
 CONSTRAINT ck_meta_raw_resource_values CHECK(kind IN('PAGE','PIXEL','APPLICATION') AND external_id REGEXP '^[0-9]{1,64}$' AND row_hash REGEXP '^[a-f0-9]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原始身份资源清单，无usable或能力版本';

CREATE TABLE orbit_meta_raw_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '当前租户边界',
 actor_id BIGINT NOT NULL COMMENT '原accounts.sync调用主体',
 operation VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '固定META_RAW_REGISTER_V1',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原16至128ASCII幂等键SHA256，不存明文',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整准备意图根',
 registry_id CHAR(36) NOT NULL COMMENT '预生成完整登记UUID；前向FK故意省略，重放须核head真实存在',
 receipt_json JSON NOT NULL COMMENT '完整确定回执，同事务成功前不可见，不含可提交NULL状态',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '数据库预留UTC微秒原精度',
 PRIMARY KEY(tenant_id,actor_id,operation,key_hash),
 UNIQUE KEY uk_meta_raw_ledger_registry(tenant_id,registry_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(actor_id) REFERENCES sys_user(user_id),
 CONSTRAINT ck_meta_raw_ledger_values CHECK(operation='META_RAW_REGISTER_V1' AND key_hash REGEXP '^[a-f0-9]{64}$' AND intent_hash REGEXP '^[a-f0-9]{64}$' AND JSON_TYPE(receipt_json)='OBJECT' AND JSON_LENGTH(receipt_json)=6),
 CONSTRAINT ck_meta_raw_ledger_receipt CHECK(
 JSON_CONTAINS_PATH(receipt_json,'all','$.registry_id','$.binding_sha256','$.observed_at','$.account_count','$.resource_count','$.execution_authorized')=1
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.registry_id'))='STRING' AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.registry_id'))=registry_id
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.binding_sha256'))='STRING' AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.binding_sha256')) REGEXP '^[a-f0-9]{64}$'
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.observed_at'))='STRING'
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.account_count'))='INTEGER' AND JSON_EXTRACT(receipt_json,'$.account_count') BETWEEN 1 AND 500
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.resource_count'))='INTEGER' AND JSON_EXTRACT(receipt_json,'$.resource_count') BETWEEN 0 AND 2500000
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='BOOLEAN' AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='false')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='按key行锁完整预留，失败整体事务回滚';

CREATE TABLE orbit_meta_raw_audit (
 tenant_id CHAR(36) NOT NULL COMMENT '当前业务租户',
 id CHAR(36) NOT NULL COMMENT '原始观察审计事件UUID',
 registry_id CHAR(36) NOT NULL COMMENT '完整登记UUID',
 actor_id BIGINT NOT NULL COMMENT '实际调用原生用户ID',
 request_id CHAR(36) NOT NULL COMMENT '原始请求关联UUID，不代替幂等键',
 details_json JSON NOT NULL COMMENT '仅安全回执与计数，不含Token或平台错误正文',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '同事务审计UTC微秒原精度',
 PRIMARY KEY(tenant_id,id),
 KEY idx_meta_raw_audit_registry(tenant_id,registry_id,id),
 FOREIGN KEY(tenant_id,registry_id) REFERENCES orbit_meta_raw_head(tenant_id,id),
 FOREIGN KEY(actor_id) REFERENCES sys_user(user_id),
 CONSTRAINT ck_meta_raw_audit_json CHECK(JSON_TYPE(details_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='独立原始观察审计，不调用账户event或增加账户水位';

CREATE TABLE orbit_meta_raw_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '同租户事件边界',
 event_id CHAR(36) NOT NULL COMMENT '真实已写入审计事件UUID',
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '仅持久PENDING事件，不自动外发',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '同事务outbox创建UTC微秒原精度',
 PRIMARY KEY(tenant_id,event_id),
 KEY idx_meta_raw_outbox_state(tenant_id,state,created_at,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_meta_raw_audit(tenant_id,id),
 CONSTRAINT ck_meta_raw_outbox_state CHECK(state IN('PENDING','DONE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原始观察同事务事件，未启动发送器';

-- 原始证据只追加；保留/清理须未来显式迁移设计，本阶段不开放业务回填。
CREATE TRIGGER guard_meta_raw_head_update BEFORE UPDATE ON orbit_meta_raw_head FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_HEAD_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_head_delete BEFORE DELETE ON orbit_meta_raw_head FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_HEAD_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_account_update BEFORE UPDATE ON orbit_meta_raw_account FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_ACCOUNT_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_account_delete BEFORE DELETE ON orbit_meta_raw_account FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_ACCOUNT_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_resource_update BEFORE UPDATE ON orbit_meta_raw_resource FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_RESOURCE_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_resource_delete BEFORE DELETE ON orbit_meta_raw_resource FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_RESOURCE_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_audit_update BEFORE UPDATE ON orbit_meta_raw_audit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_AUDIT_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_audit_delete BEFORE DELETE ON orbit_meta_raw_audit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_AUDIT_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_idempotency_delete BEFORE DELETE ON orbit_meta_raw_idempotency FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_IDEMPOTENCY_IMMUTABLE';
CREATE TRIGGER guard_meta_raw_idempotency_update BEFORE UPDATE ON orbit_meta_raw_idempotency FOR EACH ROW
BEGIN
 IF NOT ((NEW.tenant_id<=>OLD.tenant_id) AND (NEW.actor_id<=>OLD.actor_id)
 AND (NEW.operation<=>OLD.operation) AND (NEW.key_hash<=>OLD.key_hash)
 AND (NEW.intent_hash<=>OLD.intent_hash) AND (NEW.registry_id<=>OLD.registry_id)
 AND (NEW.receipt_json<=>OLD.receipt_json) AND (NEW.created_at<=>OLD.created_at)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_IDEMPOTENCY_IMMUTABLE';
 END IF;
END;
CREATE TRIGGER guard_meta_raw_outbox_delete BEFORE DELETE ON orbit_meta_raw_outbox FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_OUTBOX_DELETE_FORBIDDEN';
CREATE TRIGGER guard_meta_raw_outbox_update BEFORE UPDATE ON orbit_meta_raw_outbox FOR EACH ROW
BEGIN
 IF NOT ((NEW.tenant_id<=>OLD.tenant_id) AND (NEW.event_id<=>OLD.event_id)
 AND (NEW.created_at<=>OLD.created_at)
 AND ((NEW.state<=>OLD.state) OR (OLD.state='PENDING' AND NEW.state='DONE'))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RAW_OUTBOX_TRANSITION_INVALID';
 END IF;
END;
