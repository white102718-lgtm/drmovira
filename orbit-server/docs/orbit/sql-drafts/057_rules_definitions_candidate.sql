-- 057候选：原规则定义闭环，尚未正式采用/执行。root审核后才复制到migrations。
-- 名称唯一原文：FIELDS.md:572、reference/03_原合同保留章节.md:198，租户内未归档名称唯一。
-- 无模拟成功/启用资格/AI/广告写入；原Rule11配置与Rule15响应不加公开字段。
CREATE TABLE orbit_rule_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '当前真实租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '规则定义变化目录水位，不是授权或事实版本',
 PRIMARY KEY(tenant_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CHECK(revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则定义键集分页及短事务写锁';
INSERT INTO orbit_rule_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_rule_scope_manifest (
 tenant_id CHAR(36) NOT NULL COMMENT '规则所属可信租户',
 id CHAR(36) NOT NULL COMMENT '规则专属范围manifest UUID，不是原scope接口的替代ID',
 rule_id CHAR(36) NOT NULL COMMENT '只允许本规则各版本引用，不可借其它规则manifest',
 source_snapshot_id CHAR(36) NOT NULL COMMENT '最初caller私有原账户快照，后续不放宽其接口',
 source_snapshot_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原完整成员含显示字段的审计根',
 member_ids_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整排序成员ID根，显示名不改变选择身份',
 member_count INT NOT NULL COMMENT '完整冻结1至50000，不截断',
 created_by BIGINT NOT NULL COMMENT '最初经原rules动作授权的原生操作者',
 creator_auth_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '最初caller授权代际审计根，不作永久授权',
 owner_user_id CHAR(36) NOT NULL COMMENT '首次冻结时规则owner，后续转属仍须重新核完整交集',
 owner_team_id CHAR(36) NOT NULL COMMENT '首次冻结时规则团队，仅历史审计',
 owner_auth_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '首次owner当前完整数据范围根',
 sealed BOOLEAN NOT NULL DEFAULT 0 COMMENT '仅外层完整写入后单调封存，不是能力发行',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '实际冻结UTC毫秒时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_manifest_owner(tenant_id,rule_id,id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(tenant_id,source_snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CHECK(member_count BETWEEN 1 AND 50000),
 CHECK(sealed IN(0,1)),
 CHECK(REGEXP_LIKE(source_snapshot_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(member_ids_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(creator_auth_fingerprint,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(owner_auth_fingerprint,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='同规则版本可复用的不可变账户成员选择，不授予历史scope';

CREATE TABLE orbit_rule_scope_member (
 tenant_id CHAR(36) NOT NULL COMMENT 'manifest可信租户',
 manifest_id CHAR(36) NOT NULL COMMENT '同事务尚未封存的规则manifest',
 account_id CHAR(36) NOT NULL COMMENT '完整冻结账户业务UUID，不是Meta外部ID',
 frozen_owner_user_id CHAR(36) NOT NULL COMMENT '首次冻结账户归属审计，不代替当前权限',
 frozen_owner_team_id CHAR(36) NOT NULL COMMENT '首次冻结账户团队审计',
 frozen_currency CHAR(3) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '首次真实币种；未知null不补USD',
 frozen_revision BIGINT NOT NULL COMMENT '首次账户版本审计；改名不改变选择身份',
 PRIMARY KEY(tenant_id,manifest_id,account_id),
 FOREIGN KEY(tenant_id,manifest_id) REFERENCES orbit_rule_scope_manifest(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 CHECK(frozen_revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='最多50000完整成员，分批写入不复制每个状态版本';

CREATE TABLE orbit_rule_event (
 tenant_id CHAR(36) NOT NULL COMMENT '真实规则租户',
 id CHAR(36) NOT NULL COMMENT '只追加事件UUID',
 rule_id CHAR(36) NOT NULL COMMENT '规则稳定业务UUID，先事件再版本避免外键环',
 revision BIGINT NOT NULL COMMENT '本次真实版本，不是旧CAS或平台版本',
 actor_id BIGINT NOT NULL COMMENT '当前原动作授权的原生操作者',
 request_id CHAR(36) NOT NULL COMMENT '本次请求UUID，不写入公开Rule正文',
 action VARCHAR(16) NOT NULL COMMENT 'CREATE/UPDATE/PAUSE/ARCHIVE/ENABLE原规则动作',
 reason VARCHAR(1000) NULL COMMENT '原Reason人工原因；无Reason动作保持null',
 details_json JSON NOT NULL COMMENT '前后版本/状态/配置根，不含凭据',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实审计UTC毫秒',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_event_version(tenant_id,rule_id,revision,id),
 KEY idx_rule_event_history(tenant_id,rule_id,created_at,id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CHECK(revision BETWEEN 1 AND 9007199254740991),
 CHECK(action IN('CREATE','UPDATE','PAUSE','ARCHIVE','ENABLE')),
 CHECK(JSON_TYPE(details_json)='OBJECT')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则定义只追加审计，不伪装RuleRun或AI分析';

CREATE TABLE orbit_rule_version (
 tenant_id CHAR(36) NOT NULL COMMENT '规则真实租户',
 rule_id CHAR(36) NOT NULL COMMENT '规则稳定UUID',
 revision BIGINT NOT NULL COMMENT '每次配置或状态CAS产生的不可变版本',
 payload_json JSON NOT NULL COMMENT '严格原RuleWrite11字段完整规范正文，不含状态技术字段',
 payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原11字段canonical SHA256',
 name VARCHAR(80) NOT NULL COMMENT 'NFC/trim后的原名称，as_cs不偷改大小写口径',
 owner_user_id CHAR(36) NOT NULL COMMENT '本版本规则拥有者UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '本版本规则团队UUID',
 target_level VARCHAR(16) NOT NULL COMMENT '原CAMPAIGN/ADSET/AD',
 state VARCHAR(16) NOT NULL COMMENT '原四状态；无真实模拟时Store不得写ENABLED',
 manifest_id CHAR(36) NOT NULL COMMENT '严格同rule完整封存manifest',
 metric_profile_id CHAR(36) NOT NULL COMMENT '原profile UUID，不伪造投放adapter',
 metric_profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '原精确字符串version，不是内部CAS',
 metric_profile_hash CHAR(64) NOT NULL COMMENT '已核原profile规范根，绑定现040复合外键',
 profile_proof_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '已核来源证明根，状态变更保持旧引用不重绑',
 event_id CHAR(36) NOT NULL COMMENT '同规则同版本真实事件，先写事件再写版本',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '本版本实际UTC毫秒，不是规则首次创建时间',
 PRIMARY KEY(tenant_id,rule_id,revision),
 FOREIGN KEY(tenant_id,rule_id,manifest_id) REFERENCES orbit_rule_scope_manifest(tenant_id,rule_id,id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 FOREIGN KEY(tenant_id,metric_profile_id,metric_profile_version,metric_profile_hash)
 REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 FOREIGN KEY(tenant_id,rule_id,revision,event_id) REFERENCES orbit_rule_event(tenant_id,rule_id,revision,id),
 CHECK(revision BETWEEN 1 AND 9007199254740991),
 CHECK(CHAR_LENGTH(name) BETWEEN 1 AND 80),
 CHECK(target_level IN('CAMPAIGN','ADSET','AD')),
 CHECK(state IN('DRAFT','ENABLED','PAUSED','ARCHIVED')),
 CHECK(REGEXP_LIKE(payload_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(profile_proof_hash,'^[0-9a-f]{64}$','c')),
 CHECK(JSON_TYPE(payload_json)='OBJECT' AND JSON_LENGTH(payload_json)=11 AND
 JSON_CONTAINS_PATH(payload_json,'all','$.name','$.ownership','$.target_level','$.scope_snapshot_id',
 '$.logic','$.groups','$.window','$.metric_profile_id','$.schedule','$.cooldown_minutes','$.max_daily'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则完整配置/状态历史；数据库来源绑定不是生产模拟资格';

CREATE TABLE orbit_rule_head (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '原Rule稳定UUID',
 revision BIGINT NOT NULL COMMENT '当前真实CAS版本，引用完整不可变版本',
 name VARCHAR(80) NOT NULL COMMENT '当前NFC名称，字面contains查询',
 active_name VARCHAR(80) GENERATED ALWAYS AS (CASE WHEN state<>'ARCHIVED' THEN name ELSE NULL END) STORED COMMENT '原PRD租户未归档名称唯一，归档释放',
 owner_user_id CHAR(36) NOT NULL COMMENT '当前规则owner，列表operator按此不按creator',
 owner_team_id CHAR(36) NOT NULL COMMENT '当前规则团队',
 target_level VARCHAR(16) NOT NULL COMMENT '当前原目标层级',
 metric_profile_id CHAR(36) NOT NULL COMMENT '当前原profile ID列表过滤',
 manifest_id CHAR(36) NOT NULL COMMENT '当前版本同rule封存manifest',
 state VARCHAR(16) NOT NULL COMMENT '当前原四状态',
 next_run_at DATETIME(3) NULL COMMENT '真实未来slot；未接调度或非ENABLED为null，不伪造',
 created_by BIGINT NOT NULL COMMENT '首次创建原生操作者，仅审计不是拥有者',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '首次真实创建UTC，不随编辑变化',
 updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '最近真实版本变化UTC',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_active_name(tenant_id,active_name),
 KEY idx_rule_owner_page(tenant_id,owner_user_id,state,created_at,id),
 KEY idx_rule_team_page(tenant_id,owner_team_id,state,created_at,id),
 KEY idx_rule_profile_page(tenant_id,metric_profile_id,state,created_at,id),
 KEY idx_rule_target_page(tenant_id,target_level,state,created_at,id),
 FOREIGN KEY(tenant_id,id,revision) REFERENCES orbit_rule_version(tenant_id,rule_id,revision),
 CHECK(state IN('DRAFT','ENABLED','PAUSED','ARCHIVED')),
 CHECK(state='ENABLED' OR next_run_at IS NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则目录当前投影；原未归档名称唯一';

CREATE TABLE orbit_rule_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '当前真实租户',
 actor_id BIGINT NOT NULL COMMENT '原生请求主体，不能由浏览器提供',
 operation VARCHAR(16) NOT NULL COMMENT '原定义动作，simulate另有未来独立收据',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原幂等键不可逆摘要',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '全部规范正文/原因/原CAS/目标动作完整根',
 rule_id CHAR(36) NOT NULL COMMENT '原已成功业务ID，重放核当前该规则对象范围',
 response_json JSON NOT NULL COMMENT '完整原Rule15成功收据，首次INSERT即完整无NULL占位',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '本键实际成功UTC时刻',
 PRIMARY KEY(tenant_id,actor_id,operation,key_hash),
 FOREIGN KEY(tenant_id,rule_id) REFERENCES orbit_rule_head(tenant_id,id),
 CHECK(operation IN('CREATE','UPDATE','PAUSE','ARCHIVE','ENABLE')),
 CHECK(REGEXP_LIKE(key_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(intent_hash,'^[0-9a-f]{64}$','c')),
 CHECK(JSON_TYPE(response_json)='OBJECT' AND JSON_LENGTH(response_json)=15 AND
 JSON_CONTAINS_PATH(response_json,'all','$.id','$.revision','$.state','$.next_run_at',
 '$.name','$.ownership','$.target_level','$.scope_snapshot_id','$.logic','$.groups','$.window',
 '$.metric_profile_id','$.schedule','$.cooldown_minutes','$.max_daily'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原操作成功键优先，同意图重放不重绑变化来源';

CREATE TABLE orbit_rule_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '真实事件租户',
 event_id CHAR(36) NOT NULL COMMENT '唯一只追加规则事件',
 state VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING或DONE，仅未来dispatcher确认',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '同事务实际UTC毫秒',
 PRIMARY KEY(tenant_id,event_id),
 KEY idx_rule_outbox_pending(state,created_at,tenant_id,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_rule_event(tenant_id,id),
 CHECK(state IN('PENDING','DONE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则定义原子事件投递，未启发送器';

CREATE TRIGGER rule_manifest_insert BEFORE INSERT ON orbit_rule_scope_manifest FOR EACH ROW BEGIN
 IF NEW.sealed<>0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_UNSEALED_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_manifest_update BEFORE UPDATE ON orbit_rule_scope_manifest FOR EACH ROW BEGIN
 IF OLD.sealed<>0 OR NEW.sealed<>1 OR NOT(NEW.tenant_id<=>OLD.tenant_id)
 OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.rule_id<=>OLD.rule_id)
 OR NOT(NEW.source_snapshot_id<=>OLD.source_snapshot_id)
 OR NOT(NEW.source_snapshot_hash<=>OLD.source_snapshot_hash)
 OR NOT(NEW.member_ids_hash<=>OLD.member_ids_hash) OR NOT(NEW.member_count<=>OLD.member_count)
 OR NOT(NEW.created_by<=>OLD.created_by)
 OR NOT(NEW.creator_auth_fingerprint<=>OLD.creator_auth_fingerprint)
 OR NOT(NEW.owner_user_id<=>OLD.owner_user_id) OR NOT(NEW.owner_team_id<=>OLD.owner_team_id)
 OR NOT(NEW.owner_auth_fingerprint<=>OLD.owner_auth_fingerprint) OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_IMMUTABLE'; END IF;
 IF NEW.member_count<>(SELECT COUNT(*) FROM orbit_rule_scope_member
 WHERE tenant_id=OLD.tenant_id AND manifest_id=OLD.id)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_COUNT_MISMATCH'; END IF;
END;
CREATE TRIGGER rule_manifest_delete BEFORE DELETE ON orbit_rule_scope_manifest FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_IMMUTABLE';
CREATE TRIGGER rule_member_insert BEFORE INSERT ON orbit_rule_scope_member FOR EACH ROW BEGIN
 DECLARE frozen INT DEFAULT NULL;
 SELECT sealed INTO frozen FROM orbit_rule_scope_manifest
 WHERE tenant_id=NEW.tenant_id AND id=NEW.manifest_id FOR SHARE;
 IF frozen IS NULL OR frozen<>0
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MEMBER_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_member_update BEFORE UPDATE ON orbit_rule_scope_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MEMBER_IMMUTABLE';
CREATE TRIGGER rule_member_delete BEFORE DELETE ON orbit_rule_scope_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MEMBER_IMMUTABLE';
CREATE TRIGGER rule_version_insert BEFORE INSERT ON orbit_rule_version FOR EACH ROW BEGIN
 DECLARE frozen INT DEFAULT NULL;
 SELECT sealed INTO frozen FROM orbit_rule_scope_manifest
 WHERE tenant_id=NEW.tenant_id AND rule_id=NEW.rule_id AND id=NEW.manifest_id FOR SHARE;
 IF frozen IS NULL OR frozen<>1
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_version_update BEFORE UPDATE ON orbit_rule_version FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_VERSION_IMMUTABLE';
CREATE TRIGGER rule_version_delete BEFORE DELETE ON orbit_rule_version FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_VERSION_IMMUTABLE';

CREATE TRIGGER rule_head_insert BEFORE INSERT ON orbit_rule_head FOR EACH ROW BEGIN
 DECLARE v_revision BIGINT DEFAULT NULL;
 DECLARE v_name VARCHAR(80); DECLARE v_owner CHAR(36); DECLARE v_team CHAR(36);
 DECLARE v_target VARCHAR(16); DECLARE v_profile CHAR(36); DECLARE v_manifest CHAR(36);
 DECLARE v_state VARCHAR(16);
 SELECT revision,name,owner_user_id,owner_team_id,target_level,metric_profile_id,manifest_id,state
 INTO v_revision,v_name,v_owner,v_team,v_target,v_profile,v_manifest,v_state
 FROM orbit_rule_version WHERE tenant_id=NEW.tenant_id AND rule_id=NEW.id
 AND revision=NEW.revision FOR SHARE;
 IF NEW.revision<>1 OR v_revision IS NULL OR NOT(NEW.name<=>v_name)
 OR NOT(NEW.owner_user_id<=>v_owner) OR NOT(NEW.owner_team_id<=>v_team)
 OR NOT(NEW.target_level<=>v_target) OR NOT(NEW.metric_profile_id<=>v_profile)
 OR NOT(NEW.manifest_id<=>v_manifest) OR NOT(NEW.state<=>v_state)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_HEAD_VERSION_MISMATCH'; END IF;
END;
CREATE TRIGGER rule_head_update BEFORE UPDATE ON orbit_rule_head FOR EACH ROW BEGIN
 DECLARE v_revision BIGINT DEFAULT NULL;
 DECLARE v_name VARCHAR(80); DECLARE v_owner CHAR(36); DECLARE v_team CHAR(36);
 DECLARE v_target VARCHAR(16); DECLARE v_profile CHAR(36); DECLARE v_manifest CHAR(36);
 DECLARE v_state VARCHAR(16);
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.id<=>OLD.id)
 OR NOT(NEW.created_by<=>OLD.created_by) OR NOT(NEW.created_at<=>OLD.created_at)
 OR NEW.revision<>OLD.revision+1 OR OLD.state='ARCHIVED'
 OR (OLD.state='ENABLED' AND NEW.state<>'PAUSED')
 OR (OLD.state='DRAFT' AND NEW.state NOT IN('DRAFT','ENABLED','ARCHIVED'))
 OR (OLD.state='PAUSED' AND NEW.state NOT IN('PAUSED','ENABLED','ARCHIVED'))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_HEAD_TRANSITION_INVALID'; END IF;
 SELECT revision,name,owner_user_id,owner_team_id,target_level,metric_profile_id,manifest_id,state
 INTO v_revision,v_name,v_owner,v_team,v_target,v_profile,v_manifest,v_state
 FROM orbit_rule_version WHERE tenant_id=NEW.tenant_id AND rule_id=NEW.id
 AND revision=NEW.revision FOR SHARE;
 IF v_revision IS NULL OR NOT(NEW.name<=>v_name)
 OR NOT(NEW.owner_user_id<=>v_owner) OR NOT(NEW.owner_team_id<=>v_team)
 OR NOT(NEW.target_level<=>v_target) OR NOT(NEW.metric_profile_id<=>v_profile)
 OR NOT(NEW.manifest_id<=>v_manifest) OR NOT(NEW.state<=>v_state)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_HEAD_VERSION_MISMATCH'; END IF;
END;
CREATE TRIGGER rule_head_delete BEFORE DELETE ON orbit_rule_head FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_ARCHIVE_ONLY';
CREATE TRIGGER rule_event_update BEFORE UPDATE ON orbit_rule_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EVENT_IMMUTABLE';
CREATE TRIGGER rule_event_delete BEFORE DELETE ON orbit_rule_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EVENT_IMMUTABLE';
CREATE TRIGGER rule_receipt_update BEFORE UPDATE ON orbit_rule_idempotency FOR EACH ROW BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.actor_id<=>OLD.actor_id)
 OR NOT(NEW.operation<=>OLD.operation) OR NOT(NEW.key_hash<=>OLD.key_hash)
 OR NOT(NEW.intent_hash<=>OLD.intent_hash) OR NOT(NEW.rule_id<=>OLD.rule_id)
 OR NOT(NEW.response_json<=>OLD.response_json) OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_RECEIPT_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_receipt_delete BEFORE DELETE ON orbit_rule_idempotency FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_RECEIPT_IMMUTABLE';
CREATE TRIGGER rule_outbox_update BEFORE UPDATE ON orbit_rule_outbox FOR EACH ROW BEGIN
 IF NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.event_id<=>OLD.event_id)
 OR NOT(NEW.created_at<=>OLD.created_at)
 OR NOT(NEW.state=OLD.state OR (OLD.state='PENDING' AND NEW.state='DONE'))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_OUTBOX_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_outbox_delete BEFORE DELETE ON orbit_rule_outbox FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_OUTBOX_IMMUTABLE';
