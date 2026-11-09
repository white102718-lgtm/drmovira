-- 063候选：规则模拟完整输入/结果暂存与原成功收据。未采用、未执行、无正式来源issuer。
-- root单独审核后落正式迁移；READY是完整计算，不是enable/AI/广告许可。
CREATE TABLE orbit_rule_simulation (
 tenant_id CHAR(36) NOT NULL COMMENT '当前授权租户UUID',
 id CHAR(36) NOT NULL COMMENT '原Simulation稳定UUID，每次构建独立身份',
 snapshot_id CHAR(36) NOT NULL COMMENT '同物理头真实持久输入快照独立UUID，不借scope/publication',
 actor_id BIGINT NOT NULL COMMENT '原rules.read当前原生操作者',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原幂等键不可逆摘要',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原SIMULATE动作/规则/IfMatch规范意图根',
 rule_id CHAR(36) NOT NULL COMMENT '原同tenant规则UUID',
 rule_revision BIGINT NOT NULL COMMENT '被模拟的不可变原Rule版本',
 manifest_id CHAR(36) NOT NULL COMMENT '精确同Rule已封存范围，不放宽私有scope',
 scope_snapshot_id CHAR(36) NOT NULL COMMENT '原Rule配置中的范围来源UUID，仅审计',
 profile_id CHAR(36) NOT NULL COMMENT '原精确MetricProfile UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '精确原字符串版本，不是最新推断',
 profile_hash CHAR(64) NOT NULL COMMENT '精确040规范根，字符集匹配原复合FK',
 source_publication_id CHAR(36) NOT NULL COMMENT '048真实已发行cutoff锚点，不覆盖各cell实际批次',
 source_generation BIGINT NOT NULL COMMENT '精确锚点发行代际',
 input_json JSON NOT NULL COMMENT '有界完整输入声明/根/算法/授权/质量摘要，不存全量实体',
 input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '应用canonical输入摘要，不能用SQL JSON CAST替代',
 expected_account_count INT NOT NULL COMMENT '真实冻结1至50000账户',
 expected_unit_count INT NOT NULL COMMENT '真实独立预期账户业务日单元数，最多350000',
 expected_entity_count BIGINT NOT NULL COMMENT '独立完整授权实体数，不由返回事实COUNT推断',
 leaf_count INT NOT NULL COMMENT '原编译AST每实体条件数1至20',
 build_epoch BIGINT NOT NULL COMMENT '原请求ledger单调构建代次，不是Rule revision',
 build_token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '只存当前构建nonce摘要，不作授权',
 state VARCHAR(16) NOT NULL DEFAULT 'BUILDING' COMMENT '内部BUILDING/READY/FAILED/CANCELLED，非原Rule状态',
 evaluated_at DATETIME(6) NOT NULL COMMENT '统一SQL UTC评估参考时刻',
 lease_until DATETIME(6) NOT NULL COMMENT '当前构建资源租约，不是模拟确认有效期',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '真实准备UTC微秒',
 sealed_at DATETIME(6) NULL COMMENT '完整发布SQL UTC，不伪装来源观察时间',
 expires_at DATETIME(6) NULL COMMENT 'seal加15分钟，仅用于确认，不自动删除历史',
 scanned_count BIGINT NULL COMMENT '完整实体数，BUILDING未知不补0',
 hit_count BIGINT NULL COMMENT '实体TRUE数量，不是条件叶子数量',
 unknown_count BIGINT NULL COMMENT '实体UNKNOWN数量，允许完整READY',
 false_count BIGINT NULL COMMENT '实体FALSE数量',
 condition_count BIGINT NULL COMMENT '完整实体数乘固定原条件数',
 entity_ids_root CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '真实EOF后重读SQL的完整实体身份根',
 results_root CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '重读SQL全部实体叶子的有序完整根',
 business_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原Simulation.hash，绑定输入根及计算结果根',
 failure_code VARCHAR(64) NULL COMMENT '固定安全失败码，不存SQL/异常全文',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_sim_snapshot(tenant_id,snapshot_id),
 UNIQUE KEY uq_rule_sim_manifest(tenant_id,id,manifest_id),
 UNIQUE KEY uq_rule_sim_profile(tenant_id,id,profile_id,profile_version),
 UNIQUE KEY uq_rule_sim_intent(tenant_id,id,actor_id,key_hash,intent_hash,build_epoch),
 KEY idx_rule_sim_lease(state,lease_until,tenant_id,id) COMMENT '仅构建巡检候选，不启动自动重试',
 FOREIGN KEY(tenant_id,rule_id,rule_revision) REFERENCES orbit_rule_version(tenant_id,rule_id,revision),
 FOREIGN KEY(tenant_id,rule_id,manifest_id) REFERENCES orbit_rule_scope_manifest(tenant_id,rule_id,id),
 FOREIGN KEY(tenant_id,profile_id,profile_version,profile_hash)
 REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 FOREIGN KEY(tenant_id,source_publication_id,source_generation,profile_id,profile_version)
 REFERENCES orbit_metric_publication(tenant_id,id,generation,profile_id,profile_version),
 CHECK(snapshot_id<>id AND snapshot_id<>manifest_id AND snapshot_id<>scope_snapshot_id AND snapshot_id<>source_publication_id),
 CHECK(rule_revision BETWEEN 1 AND 9007199254740991 AND build_epoch BETWEEN 1 AND 9007199254740991),
 CHECK(actor_id BETWEEN 1 AND 9007199254740991),
 CHECK(source_generation BETWEEN 1 AND 9007199254740991),
 CHECK(expected_account_count BETWEEN 1 AND 50000 AND expected_unit_count BETWEEN expected_account_count AND 350000),
 CHECK(expected_entity_count BETWEEN 0 AND 2147483647 AND leaf_count BETWEEN 1 AND 20),
 CHECK(state IN('BUILDING','READY','FAILED','CANCELLED')),
 CHECK(JSON_TYPE(input_json)='OBJECT' AND JSON_STORAGE_SIZE(input_json)<=32768),
 CHECK(REGEXP_LIKE(key_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(intent_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(input_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(profile_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(build_token_hash,'^[0-9a-f]{64}$','c')),
 CHECK(entity_ids_root IS NULL OR REGEXP_LIKE(entity_ids_root,'^[0-9a-f]{64}$','c')),
 CHECK(results_root IS NULL OR REGEXP_LIKE(results_root,'^[0-9a-f]{64}$','c')),
 CHECK(business_hash IS NULL OR REGEXP_LIKE(business_hash,'^[0-9a-f]{64}$','c')),
 CHECK(state<>'READY' OR (sealed_at IS NOT NULL AND expires_at IS NOT NULL
 AND scanned_count IS NOT NULL AND hit_count IS NOT NULL AND unknown_count IS NOT NULL AND false_count IS NOT NULL
 AND condition_count IS NOT NULL AND entity_ids_root IS NOT NULL AND results_root IS NOT NULL AND business_hash IS NOT NULL
 AND scanned_count=expected_entity_count AND scanned_count=hit_count+unknown_count+false_count
 AND hit_count>=0 AND unknown_count>=0 AND false_count>=0
 AND condition_count=scanned_count*leaf_count AND sealed_at>=evaluated_at
 AND expires_at=sealed_at+INTERVAL 15 MINUTE AND failure_code IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则模拟真实快照及完整计算头，不是执行许可';

CREATE TABLE orbit_rule_simulation_account (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 simulation_id CHAR(36) NOT NULL COMMENT '所属独立构建UUID',
 manifest_id CHAR(36) NOT NULL COMMENT '精确同Rule成员来源',
 account_id CHAR(36) NOT NULL COMMENT '完整授权真实账户UUID',
 timezone_name VARCHAR(64) NOT NULL COMMENT '账户真实IANA时区，不用调度时区覆盖',
 currency CHAR(3) NULL COMMENT '真实账户币种，未知保持NULL不补USD',
 owner_user_id CHAR(36) NOT NULL COMMENT '捕获时经双方当前范围复核的投手',
 owner_team_id CHAR(36) NOT NULL COMMENT '捕获时实际团队',
 date_from DATE NOT NULL COMMENT '统一evaluated_at解析的包含起始业务日',
 date_to DATE NOT NULL COMMENT '包含结束业务日，最多7日',
 expected_units_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '独立预期单元有序根',
 PRIMARY KEY(tenant_id,simulation_id,account_id),
 FOREIGN KEY(tenant_id,simulation_id,manifest_id) REFERENCES orbit_rule_simulation(tenant_id,id,manifest_id),
 FOREIGN KEY(tenant_id,manifest_id,account_id) REFERENCES orbit_rule_scope_member(tenant_id,manifest_id,account_id),
 CHECK(date_to>=date_from AND DATEDIFF(date_to,date_from)<=6),
 CHECK(REGEXP_LIKE(expected_units_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='最多50000真实账户窗口，不存巨型账户JSON';

CREATE TABLE orbit_rule_simulation_unit (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 simulation_id CHAR(36) NOT NULL COMMENT '所属构建UUID',
 account_id CHAR(36) NOT NULL COMMENT '明确预期账户UUID',
 business_date DATE NOT NULL COMMENT '账户业务日标签，不统一上海切日',
 profile_id CHAR(36) NOT NULL COMMENT '同模拟精确原profile',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '同模拟原字符串版本',
 status VARCHAR(16) NOT NULL COMMENT 'SELECTED或已证明缺失MISSING，不推断合法零',
 cell_id CHAR(36) NULL COMMENT '048真实完整捕获单元UUID；MISSING没有假UUID',
 account_snapshot_id CHAR(36) NULL COMMENT '原cell精确账户维度快照',
 capture_sequence BIGINT NULL COMMENT '原cell冻结采集序号，不改成anchor generation',
 breakdown_key VARCHAR(16) NOT NULL DEFAULT 'TOTAL' COMMENT '原首期固定完整单元粒度',
 expectation_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '独立发行预期与归属证明根',
 selected_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际选择或明确缺失声明规范根',
 PRIMARY KEY(tenant_id,simulation_id,account_id,business_date),
 FOREIGN KEY(tenant_id,simulation_id,account_id) REFERENCES orbit_rule_simulation_account(tenant_id,simulation_id,account_id),
 FOREIGN KEY(tenant_id,simulation_id,profile_id,profile_version) REFERENCES orbit_rule_simulation(tenant_id,id,profile_id,profile_version),
 FOREIGN KEY(tenant_id,cell_id,account_id,account_snapshot_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence)
 REFERENCES orbit_metric_capture_cell(tenant_id,id,account_id,account_snapshot_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence),
 CHECK(status IN('SELECTED','MISSING') AND breakdown_key='TOTAL'),
 CHECK((status='MISSING' AND cell_id IS NULL AND account_snapshot_id IS NULL AND capture_sequence IS NULL)
 OR (status='SELECTED' AND cell_id IS NOT NULL AND account_snapshot_id IS NOT NULL AND capture_sequence IS NOT NULL
 AND capture_sequence BETWEEN 1 AND 9007199254740991)),
 CHECK(REGEXP_LIKE(expectation_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(selected_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整独立预期及实际单元选择，不借返回facts构造分母';

CREATE TABLE orbit_rule_simulation_entity (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 simulation_id CHAR(36) NOT NULL COMMENT '所属构建UUID',
 entity_id CHAR(36) NOT NULL COMMENT '原真实内部CAMPAIGN/ADSET/AD UUID',
 account_id CHAR(36) NOT NULL COMMENT '该实体所属真实账户',
 source_snapshot_id CHAR(36) NOT NULL COMMENT '048不可变实际实体维度快照UUID',
 entity_kind VARCHAR(16) NOT NULL COMMENT '与原规则target_level一致',
 currency CHAR(3) NULL COMMENT '同实体账户币种，不跨币求和',
 truth VARCHAR(16) NOT NULL COMMENT '实体TRUE/FALSE/UNKNOWN，非叶子统计',
 entity_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整元数据/真值/叶子有序根',
 PRIMARY KEY(tenant_id,simulation_id,entity_id),
 FOREIGN KEY(tenant_id,simulation_id,account_id) REFERENCES orbit_rule_simulation_account(tenant_id,simulation_id,account_id),
 FOREIGN KEY(tenant_id,account_id,source_snapshot_id,entity_kind) REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind),
 CHECK(entity_kind IN('CAMPAIGN','ADSET','AD') AND truth IN('TRUE','FALSE','UNKNOWN')),
 CHECK(REGEXP_LIKE(entity_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='有界实体结果行，全局规范UUID排序不在Python攒全集';

CREATE TABLE orbit_rule_simulation_condition (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 simulation_id CHAR(36) NOT NULL COMMENT '所属独立构建UUID',
 entity_id CHAR(36) NOT NULL COMMENT '原ConditionResult真实entity_id',
 condition_index INT NOT NULL COMMENT '原编译AST稳定0基索引，不是分页ordinal',
 `value` VARCHAR(28) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原Decimal文本；未知NULL不补0',
 result VARCHAR(16) NOT NULL COMMENT '原三值TRUE/FALSE/UNKNOWN',
 reason_code VARCHAR(64) NULL COMMENT '原未知原因，非错误全文',
 PRIMARY KEY(tenant_id,simulation_id,entity_id,condition_index),
 FOREIGN KEY(tenant_id,simulation_id,entity_id) REFERENCES orbit_rule_simulation_entity(tenant_id,simulation_id,entity_id),
 CHECK(condition_index BETWEEN 0 AND 19 AND result IN('TRUE','FALSE','UNKNOWN')),
 CHECK(`value` IS NULL OR REGEXP_LIKE(`value`,'^(0|[1-9][0-9]*)([.][0-9]{1,6})?$','c')),
 CHECK(reason_code IS NULL OR CHAR_LENGTH(reason_code) BETWEEN 1 AND 64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整原五字段叶子投影与真实复合keyset索引';

CREATE TABLE orbit_rule_simulation_request (
 tenant_id CHAR(36) NOT NULL COMMENT '当前真实租户UUID',
 actor_id BIGINT NOT NULL COMMENT '原当前请求主体',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原幂等键摘要',
 intent_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '动作/Rule/IfMatch完整意图',
 simulation_id CHAR(36) NOT NULL COMMENT '当前构建或原已成功结果',
 build_epoch BIGINT NOT NULL COMMENT '精确当前构建代际，旧构建不能发布新回执',
 state VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT '内部PENDING/FAILED/COMPLETED',
 response_json JSON NULL COMMENT '原成功Simulation13字节语义固定，不更新旧session cursor',
 response_bytes MEDIUMBLOB NULL COMMENT '原成功JSON精确UTF8字节，重放不经MySQL JSON重排',
 response_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原响应字节SHA256，不是Simulation业务根',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '原键第一次准备UTC',
 PRIMARY KEY(tenant_id,actor_id,key_hash),
 FOREIGN KEY(tenant_id,simulation_id,actor_id,key_hash,intent_hash,build_epoch)
 REFERENCES orbit_rule_simulation(tenant_id,id,actor_id,key_hash,intent_hash,build_epoch),
 CHECK(state IN('PENDING','FAILED','COMPLETED')),
 CHECK(build_epoch BETWEEN 1 AND 9007199254740991),
 CHECK(REGEXP_LIKE(key_hash,'^[0-9a-f]{64}$','c') AND REGEXP_LIKE(intent_hash,'^[0-9a-f]{64}$','c')),
 CHECK((state='COMPLETED' AND response_json IS NOT NULL AND response_bytes IS NOT NULL AND response_hash IS NOT NULL
 AND JSON_TYPE(response_json)='OBJECT' AND JSON_LENGTH(response_json)=13 AND JSON_STORAGE_SIZE(response_json)<=1048576
 AND JSON_CONTAINS_PATH(response_json,'all','$.id','$.rule_id','$.revision','$.snapshot_id','$.hash',
 '$.account_count','$.scanned_count','$.hit_count','$.unknown_count','$.false_count','$.conditions','$.expires_at','$.next_cursor')
 AND OCTET_LENGTH(response_bytes)<=1048576 AND REGEXP_LIKE(response_hash,'^[0-9a-f]{64}$','c')
 AND SHA2(response_bytes,256)=response_hash
 -- 原字节单独验hash不等于同一响应；JSON比较保留数组顺序，绝不用双向JSON_CONTAINS。
 AND JSON_VALID(CONVERT(response_bytes USING utf8mb4))
 AND CAST(CONVERT(response_bytes USING utf8mb4) AS JSON)=response_json)
 OR (state<>'COMPLETED' AND response_json IS NULL AND response_bytes IS NULL AND response_hash IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='模拟独立成功幂等，不借原Rule15收据表';

CREATE TABLE orbit_rule_simulation_audit (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 id CHAR(36) NOT NULL COMMENT '只追加模拟事件UUID',
 simulation_id CHAR(36) NOT NULL COMMENT '精确构建UUID',
 actor_id BIGINT NOT NULL COMMENT '当前原read动作主体',
 request_id CHAR(36) NOT NULL COMMENT '实际请求审计UUID',
 action VARCHAR(16) NOT NULL COMMENT 'READY/FAILED/CANCELLED内部模拟事件，不变更Rule状态',
 details_json JSON NOT NULL COMMENT '有界输入根/结果根/原因/统计，不存凭据或全部叶子',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '实际审计UTC微秒',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_sim_audit(tenant_id,simulation_id,action),
 FOREIGN KEY(tenant_id,simulation_id) REFERENCES orbit_rule_simulation(tenant_id,id),
 CHECK(action IN('READY','FAILED','CANCELLED')),
 CHECK(JSON_TYPE(details_json)='OBJECT' AND JSON_STORAGE_SIZE(details_json)<=16384)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='模拟完整发布或失败只追加审计，不伪装RuleRun/Hit';

CREATE TABLE orbit_rule_simulation_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 event_id CHAR(36) NOT NULL COMMENT '精确模拟审计事件UUID',
 state VARCHAR(16) NOT NULL DEFAULT 'PENDING' COMMENT '仅PENDING到DONE受控确认，未接dispatcher',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '真实原子写入UTC微秒',
 PRIMARY KEY(tenant_id,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_rule_simulation_audit(tenant_id,id),
 CHECK(state IN('PENDING','DONE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='与模拟封存收据同事务的事件投递意图';

-- 以下guards不计算canonical SHA256：完整SQL流重算由Store负责，严禁用JSON CAST代替。
CREATE TRIGGER rule_sim_insert BEFORE INSERT ON orbit_rule_simulation FOR EACH ROW BEGIN
 IF NEW.state<>'BUILDING' OR NEW.sealed_at IS NOT NULL OR NEW.expires_at IS NOT NULL
 OR NEW.scanned_count IS NOT NULL OR NEW.hit_count IS NOT NULL OR NEW.unknown_count IS NOT NULL
 OR NEW.false_count IS NOT NULL OR NEW.condition_count IS NOT NULL OR NEW.entity_ids_root IS NOT NULL
 OR NEW.results_root IS NOT NULL OR NEW.business_hash IS NOT NULL OR NEW.failure_code IS NOT NULL
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_BUILDING_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_sim_update BEFORE UPDATE ON orbit_rule_simulation FOR EACH ROW BEGIN
 IF OLD.state<>'BUILDING' OR NEW.state NOT IN('READY','FAILED','CANCELLED')
 OR NOT(JSON_ARRAY(NEW.tenant_id,NEW.id,NEW.snapshot_id,NEW.actor_id,NEW.key_hash,NEW.intent_hash,
 NEW.rule_id,NEW.rule_revision,NEW.manifest_id,NEW.scope_snapshot_id,NEW.profile_id,NEW.profile_version,
 NEW.profile_hash,NEW.source_publication_id,NEW.source_generation,NEW.input_json,NEW.input_hash,
 NEW.expected_account_count,NEW.expected_unit_count,NEW.expected_entity_count,NEW.leaf_count,
 NEW.build_epoch,NEW.build_token_hash,NEW.evaluated_at,NEW.lease_until,NEW.created_at)
 <=>JSON_ARRAY(OLD.tenant_id,OLD.id,OLD.snapshot_id,OLD.actor_id,OLD.key_hash,OLD.intent_hash,
 OLD.rule_id,OLD.rule_revision,OLD.manifest_id,OLD.scope_snapshot_id,OLD.profile_id,OLD.profile_version,
 OLD.profile_hash,OLD.source_publication_id,OLD.source_generation,OLD.input_json,OLD.input_hash,
 OLD.expected_account_count,OLD.expected_unit_count,OLD.expected_entity_count,OLD.leaf_count,
 OLD.build_epoch,OLD.build_token_hash,OLD.evaluated_at,OLD.lease_until,OLD.created_at))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_IMMUTABLE'; END IF;
 IF NEW.state='READY' AND (
 NEW.expected_account_count<>(SELECT COUNT(*) FROM orbit_rule_simulation_account WHERE tenant_id=OLD.tenant_id AND simulation_id=OLD.id)
 OR NEW.expected_unit_count<>(SELECT COUNT(*) FROM orbit_rule_simulation_unit WHERE tenant_id=OLD.tenant_id AND simulation_id=OLD.id)
 OR NEW.expected_entity_count<>(SELECT COUNT(*) FROM orbit_rule_simulation_entity WHERE tenant_id=OLD.tenant_id AND simulation_id=OLD.id)
 OR NEW.expected_entity_count*NEW.leaf_count<>(SELECT COUNT(*) FROM orbit_rule_simulation_condition WHERE tenant_id=OLD.tenant_id AND simulation_id=OLD.id))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_INCOMPLETE'; END IF;
 IF NEW.state='READY' AND (
 NOT EXISTS(SELECT 1 FROM orbit_rule_simulation_audit a JOIN orbit_rule_simulation_outbox o
 ON o.tenant_id=a.tenant_id AND o.event_id=a.id WHERE a.tenant_id=OLD.tenant_id
 AND a.simulation_id=OLD.id AND a.action='READY')
 OR NOT EXISTS(SELECT 1 FROM orbit_rule_simulation_request r WHERE r.tenant_id=OLD.tenant_id
 AND r.simulation_id=OLD.id AND r.actor_id=OLD.actor_id AND r.key_hash=OLD.key_hash
 AND r.intent_hash=OLD.intent_hash AND r.build_epoch=OLD.build_epoch AND r.state='PENDING'))
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_ATOMIC_RECEIPT_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_sim_delete BEFORE DELETE ON orbit_rule_simulation FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_IMMUTABLE';
CREATE TRIGGER rule_sim_account_insert BEFORE INSERT ON orbit_rule_simulation_account FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16); DECLARE leaf_total INT;

 SELECT state,leaf_count INTO parent_state,leaf_total FROM orbit_rule_simulation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.simulation_id FOR SHARE;
 IF parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_FROZEN'; END IF;

END;
CREATE TRIGGER rule_sim_account_update BEFORE UPDATE ON orbit_rule_simulation_account FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_account_delete BEFORE DELETE ON orbit_rule_simulation_account FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_unit_insert BEFORE INSERT ON orbit_rule_simulation_unit FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16); DECLARE leaf_total INT;
 DECLARE begin_day DATE; DECLARE end_day DATE;
 SELECT state,leaf_count INTO parent_state,leaf_total FROM orbit_rule_simulation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.simulation_id FOR SHARE;
 IF parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_FROZEN'; END IF;
 SELECT date_from,date_to INTO begin_day,end_day FROM orbit_rule_simulation_account
 WHERE tenant_id=NEW.tenant_id AND simulation_id=NEW.simulation_id AND account_id=NEW.account_id FOR SHARE;
 IF begin_day IS NULL OR NEW.business_date<begin_day OR NEW.business_date>end_day
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_UNIT_OUTSIDE_WINDOW'; END IF;
END;
CREATE TRIGGER rule_sim_unit_update BEFORE UPDATE ON orbit_rule_simulation_unit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_unit_delete BEFORE DELETE ON orbit_rule_simulation_unit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_entity_insert BEFORE INSERT ON orbit_rule_simulation_entity FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16); DECLARE leaf_total INT;
 DECLARE actual_entity CHAR(36); DECLARE actual_currency CHAR(3);
 SELECT state,leaf_count INTO parent_state,leaf_total FROM orbit_rule_simulation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.simulation_id FOR SHARE;
 IF parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_FROZEN'; END IF;
 SELECT entity_id INTO actual_entity FROM orbit_metric_entity_snapshot WHERE tenant_id=NEW.tenant_id
 AND account_id=NEW.account_id AND id=NEW.source_snapshot_id AND entity_kind=NEW.entity_kind FOR SHARE;
 SELECT currency INTO actual_currency FROM orbit_rule_simulation_account WHERE tenant_id=NEW.tenant_id
 AND simulation_id=NEW.simulation_id AND account_id=NEW.account_id FOR SHARE;
 IF actual_entity IS NULL OR actual_entity<>NEW.entity_id OR NOT(actual_currency<=>NEW.currency)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_ENTITY_BINDING_INVALID'; END IF;
END;
CREATE TRIGGER rule_sim_entity_update BEFORE UPDATE ON orbit_rule_simulation_entity FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_entity_delete BEFORE DELETE ON orbit_rule_simulation_entity FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_condition_insert BEFORE INSERT ON orbit_rule_simulation_condition FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16); DECLARE leaf_total INT;

 SELECT state,leaf_count INTO parent_state,leaf_total FROM orbit_rule_simulation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.simulation_id FOR SHARE;
 IF parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_FROZEN'; END IF;
 IF NEW.condition_index>=leaf_total
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CONDITION_INDEX_INVALID'; END IF;
END;
CREATE TRIGGER rule_sim_condition_update BEFORE UPDATE ON orbit_rule_simulation_condition FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_condition_delete BEFORE DELETE ON orbit_rule_simulation_condition FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_CHILD_IMMUTABLE';
CREATE TRIGGER rule_sim_request_insert BEFORE INSERT ON orbit_rule_simulation_request FOR EACH ROW BEGIN
 IF NEW.state<>'PENDING' OR NEW.response_json IS NOT NULL OR NEW.response_bytes IS NOT NULL
 OR NEW.response_hash IS NOT NULL OR NEW.build_epoch<>1
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_REQUEST_PENDING_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_sim_request_update BEFORE UPDATE ON orbit_rule_simulation_request FOR EACH ROW BEGIN
 DECLARE published INT DEFAULT 0;
 IF OLD.state='COMPLETED'
 OR NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.actor_id<=>OLD.actor_id)
 OR NOT(NEW.key_hash<=>OLD.key_hash) OR NOT(NEW.intent_hash<=>OLD.intent_hash)
 OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_REQUEST_IMMUTABLE'; END IF;
 IF NEW.state='PENDING' THEN
  IF OLD.state<>'FAILED' OR NEW.build_epoch<>OLD.build_epoch+1 OR NEW.simulation_id=OLD.simulation_id
  THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_REQUEST_RETRY_INVALID'; END IF;
 ELSE
  IF OLD.state<>'PENDING' OR NEW.build_epoch<>OLD.build_epoch OR NEW.simulation_id<>OLD.simulation_id
  THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_REQUEST_TRANSITION_INVALID'; END IF;
 END IF;
 IF NEW.state='COMPLETED' THEN
  IF NOT JSON_VALID(CONVERT(NEW.response_bytes USING utf8mb4)) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_RESPONSE_BYTES_INVALID';
  END IF;
  IF NOT(CAST(CONVERT(NEW.response_bytes USING utf8mb4) AS JSON)<=>NEW.response_json) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_RESPONSE_BYTES_MISMATCH';
  END IF;
  SELECT COUNT(*) INTO published FROM orbit_rule_simulation s
  WHERE s.tenant_id=NEW.tenant_id AND s.id=NEW.simulation_id AND s.state='READY'
  AND JSON_UNQUOTE(JSON_EXTRACT(NEW.response_json,'$.id'))=s.id
  AND JSON_UNQUOTE(JSON_EXTRACT(NEW.response_json,'$.rule_id'))=s.rule_id
  AND JSON_EXTRACT(NEW.response_json,'$.revision')=s.rule_revision
  AND JSON_UNQUOTE(JSON_EXTRACT(NEW.response_json,'$.snapshot_id'))=s.snapshot_id
  AND JSON_UNQUOTE(JSON_EXTRACT(NEW.response_json,'$.hash'))=s.business_hash
  AND JSON_EXTRACT(NEW.response_json,'$.account_count')=s.expected_account_count
  AND JSON_EXTRACT(NEW.response_json,'$.scanned_count')=s.scanned_count
  AND JSON_EXTRACT(NEW.response_json,'$.hit_count')=s.hit_count
  AND JSON_EXTRACT(NEW.response_json,'$.unknown_count')=s.unknown_count
  AND JSON_EXTRACT(NEW.response_json,'$.false_count')=s.false_count
  AND JSON_UNQUOTE(JSON_EXTRACT(NEW.response_json,'$.expires_at'))=DATE_FORMAT(s.expires_at,'%Y-%m-%dT%H:%i:%s.%fZ')
  AND JSON_TYPE(JSON_EXTRACT(NEW.response_json,'$.conditions'))='ARRAY'
  AND JSON_LENGTH(JSON_EXTRACT(NEW.response_json,'$.conditions'))<=200;
  IF published<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_RESPONSE_BINDING_INVALID'; END IF;
 END IF;
END;
CREATE TRIGGER rule_sim_request_delete BEFORE DELETE ON orbit_rule_simulation_request FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_REQUEST_IMMUTABLE';
CREATE TRIGGER rule_sim_audit_insert BEFORE INSERT ON orbit_rule_simulation_audit FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16);
 SELECT state INTO parent_state FROM orbit_rule_simulation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.simulation_id FOR SHARE;
 IF parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_AUDIT_BEFORE_SEAL_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_sim_audit_update BEFORE UPDATE ON orbit_rule_simulation_audit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_AUDIT_IMMUTABLE';
CREATE TRIGGER rule_sim_audit_delete BEFORE DELETE ON orbit_rule_simulation_audit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_AUDIT_IMMUTABLE';
CREATE TRIGGER rule_sim_outbox_update BEFORE UPDATE ON orbit_rule_simulation_outbox FOR EACH ROW BEGIN
 IF OLD.state<>'PENDING' OR NEW.state<>'DONE' OR NOT(NEW.tenant_id<=>OLD.tenant_id)
 OR NOT(NEW.event_id<=>OLD.event_id) OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_OUTBOX_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_sim_outbox_delete BEFORE DELETE ON orbit_rule_simulation_outbox FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_OUTBOX_IMMUTABLE';
CREATE TRIGGER rule_sim_outbox_insert BEFORE INSERT ON orbit_rule_simulation_outbox FOR EACH ROW BEGIN
 DECLARE parent_state VARCHAR(16);
 SELECT s.state INTO parent_state FROM orbit_rule_simulation_audit a JOIN orbit_rule_simulation s
 ON s.tenant_id=a.tenant_id AND s.id=a.simulation_id WHERE a.tenant_id=NEW.tenant_id AND a.id=NEW.event_id FOR SHARE;
 IF NEW.state<>'PENDING' OR parent_state IS NULL OR parent_state<>'BUILDING'
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_SIM_OUTBOX_BEFORE_SEAL_REQUIRED'; END IF;
END;
