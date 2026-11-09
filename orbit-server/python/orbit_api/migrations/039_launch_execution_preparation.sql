-- 主线039：完整执行准备的私有持久表与不可变护栏；显式升级，不自动受理或发送。
-- 服务端MULTI_STATEMENTS可执行的复合触发器，无mysql客户端DELIMITER指令。
-- 默认无AuthorityProvider必须在创建任何隐藏Task/命令之前503。
ALTER TABLE orbit_task DROP CHECK ck_task_producer;
ALTER TABLE orbit_task ADD CONSTRAINT ck_task_producer
 CHECK(producer_kind IN ('ISOLATED_TEST','TRUSTED'));

CREATE TABLE orbit_launch_execution_preparation (
 tenant_id CHAR(36) NOT NULL COMMENT '可信当前租户，不来自客户端',
 id CHAR(36) NOT NULL COMMENT '内部准备UUID，不是公开Task或受理回执',
 task_id CHAR(36) NOT NULL COMMENT '预留真实Task，完整受理前始终BUILDING不可读',
 plan_id CHAR(36) NOT NULL COMMENT '真实计划UUID',
 source_revision BIGINT NOT NULL COMMENT '不可变配置版本，不随预检状态CAS增长',
 payload_hash CHAR(64) NOT NULL COMMENT '完整规范配置源SHA256',
 validation_id CHAR(36) NOT NULL COMMENT '当前完整成功的038预检记录',
 validated_head_revision BIGINT NOT NULL COMMENT '该038预检成功时的外部计划头',
 validation_hash CHAR(64) NOT NULL COMMENT '原schema1冻结预检hash',
 validation_expires_at DATETIME(3) NOT NULL COMMENT '真实预检完成后十五分钟到期',
 naming_date DATE NOT NULL COMMENT '冻结Asia/Shanghai命名日',
 actor_id BIGINT NOT NULL COMMENT '实际原生操作者，不能代替owner',
 subject_id CHAR(36) NOT NULL COMMENT '构建授权业务身份UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '真实源冻结投手UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '真实源冻结团队UUID',
 auth_version BIGINT NOT NULL COMMENT '准备时实际身份授权版本，final必须重验',
 authorization_fingerprint CHAR(64) NOT NULL COMMENT '当前角色团队与授权集合绑定摘要',
 intent_hash CHAR(64) NOT NULL COMMENT 'tenant计划source头及原execute两字段完整意图摘要',
 idempotency_key_hash CHAR(64) NOT NULL COMMENT '原幂等键SHA256，不保存明文',
 provider_kind VARCHAR(16) NOT NULL COMMENT 'TRUSTED或严格本轮UUID库ISOLATED_TEST，不等于写授权',
 provider_fingerprint CHAR(64) NOT NULL COMMENT '真实权威来源观察及版本绑定摘要',
 state VARCHAR(16) NOT NULL DEFAULT 'BUILDING' COMMENT '仅内部BUILDING/SEALING/SEALED/ACCEPTED/ABORTED',
 manifest_schema_version INT NOT NULL COMMENT '完整准备协议版本1',
 manifest_hash CHAR(64) NOT NULL COMMENT '完整字节清单SHA256，不是033块根',
 task_chunk_hash CHAR(64) NOT NULL COMMENT '033有序节点块ordinal数量hash根',
 graph_hash CHAR(64) NOT NULL COMMENT '完整真实DAG拓扑摘要',
 plan_input_hash CHAR(64) NOT NULL COMMENT '原配置树规范摘要',
 allocation_input_hash CHAR(64) NOT NULL COMMENT '真实分配来源摘要',
 expected_bytes BIGINT NOT NULL COMMENT '完整展开字节长度，无032旧块数限制',
 expected_byte_chunks INT UNSIGNED NOT NULL COMMENT '连续字节块总数',
 expected_node_count INT UNSIGNED NOT NULL COMMENT '实际DAG节点总数1至100000',
 expected_node_chunks INT UNSIGNED NOT NULL COMMENT '每块最多500节点，总块数最多200',
 expected_command_count INT UNSIGNED NOT NULL COMMENT '每真实DAG操作对应一份完整命令描述',
 expected_edge_count INT UNSIGNED NOT NULL COMMENT '实际拓扑父边总数',
 persisted_bytes BIGINT NOT NULL DEFAULT 0 COMMENT '同事务已落字节总数',
 persisted_byte_chunks INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已落连续字节块数即下一ordinal',
 persisted_node_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已落真实节点数',
 persisted_node_chunks INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已落连续节点块数即下一ordinal',
 persisted_command_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已落完整命令描述数',
 persisted_edge_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已落真实父边数',
 mutation_revision BIGINT NOT NULL DEFAULT 1 COMMENT '合法追加或控制转换递增，不能当成平台权威版本',
 sealed_revision BIGINT NULL COMMENT '实际完整流式核验后绑定的构建版本',
 sealed_at DATETIME(3) NULL COMMENT '实际完整校验完成UTC',
 accepted_head_revision BIGINT NULL COMMENT '成功SUBMITTED外部头，只允许final一次填',
 accepted_request_id CHAR(36) NULL COMMENT '真实原202受理关联请求UUID',
 accepted_at DATETIME(3) NULL COMMENT '真实原子受理UTC',
 created_at DATETIME(3) NOT NULL COMMENT '私有构建开始UTC，不是Task已受理时间',
 updated_at DATETIME(3) NOT NULL COMMENT '实际追加控制转换UTC',
 expires_at DATETIME(3) NOT NULL COMMENT '私有构建期限，不晚于预检期限且不得跨上海命名日',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_execution_task(tenant_id,task_id),
 UNIQUE KEY uq_execution_binding(tenant_id,id,task_id),
 KEY idx_execution_actor(tenant_id,actor_id,state,updated_at,id),
 KEY idx_execution_expiry(state,expires_at,tenant_id,id),
 KEY idx_execution_source(tenant_id,plan_id,source_revision,state,id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id),
 FOREIGN KEY(tenant_id,plan_id,source_revision)
 REFERENCES orbit_launch_plan_version(tenant_id,plan_id,revision),
 FOREIGN KEY(tenant_id,validation_id) REFERENCES orbit_launch_validation(tenant_id,id),
 FOREIGN KEY(tenant_id,subject_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CONSTRAINT ck_execution_hashes CHECK(REGEXP_LIKE(payload_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(validation_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(authorization_fingerprint,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(intent_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(idempotency_key_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(provider_fingerprint,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(manifest_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(task_chunk_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(graph_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(plan_input_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(allocation_input_hash,'^[a-f0-9]{64}$','c')),
 CONSTRAINT ck_execution_version CHECK(source_revision BETWEEN 1 AND 9007199254740991
 AND validated_head_revision>source_revision AND validated_head_revision<=9007199254740991
 AND auth_version BETWEEN 1 AND 9007199254740991
 AND mutation_revision BETWEEN 1 AND 9007199254740991 AND manifest_schema_version=1),
 CONSTRAINT ck_execution_state CHECK(state IN('BUILDING','SEALING','SEALED','ACCEPTED','ABORTED')),
 CONSTRAINT ck_execution_provider CHECK(provider_kind IN('TRUSTED','ISOLATED_TEST')),
 CONSTRAINT ck_execution_count CHECK(expected_bytes BETWEEN 1 AND 9007199254740991
 AND expected_byte_chunks BETWEEN 1 AND 9007199254740991
 AND expected_node_count BETWEEN 1 AND 100000
 AND expected_node_chunks=(expected_node_count+499) DIV 500
 AND expected_command_count=expected_node_count
 AND expected_edge_count<=expected_node_count*100
 AND persisted_bytes BETWEEN 0 AND expected_bytes
 AND persisted_byte_chunks<=expected_byte_chunks
 AND persisted_node_count<=expected_node_count
 AND persisted_node_chunks<=expected_node_chunks
 AND persisted_command_count<=expected_command_count
 AND persisted_edge_count<=expected_edge_count),
 CONSTRAINT ck_execution_complete CHECK(state NOT IN('SEALING','SEALED','ACCEPTED') OR
 (persisted_bytes=expected_bytes AND persisted_byte_chunks=expected_byte_chunks
 AND persisted_node_count=expected_node_count AND persisted_node_chunks=expected_node_chunks
 AND persisted_command_count=expected_command_count AND persisted_edge_count=expected_edge_count)),
 CONSTRAINT ck_execution_seal CHECK((state IN('BUILDING','SEALING') AND sealed_at IS NULL
 AND sealed_revision IS NULL) OR (state IN('SEALED','ACCEPTED') AND sealed_at IS NOT NULL
 AND sealed_revision IS NOT NULL AND sealed_revision BETWEEN 1 AND mutation_revision)
 OR (state='ABORTED' AND ((sealed_at IS NULL AND sealed_revision IS NULL)
 OR (sealed_at IS NOT NULL AND sealed_revision IS NOT NULL
 AND sealed_revision BETWEEN 1 AND mutation_revision)))),
 CONSTRAINT ck_execution_accept CHECK((state='ACCEPTED' AND accepted_at IS NOT NULL
 AND accepted_head_revision IS NOT NULL AND accepted_head_revision=validated_head_revision+1
 AND accepted_request_id IS NOT NULL)
 OR (state<>'ACCEPTED' AND accepted_at IS NULL AND accepted_head_revision IS NULL
 AND accepted_request_id IS NULL)),
 CONSTRAINT ck_execution_time CHECK(DATE(created_at+INTERVAL 8 HOUR) IS NOT NULL
 AND CAST(DATE(created_at+INTERVAL 8 HOUR)+INTERVAL 1 DAY AS DATETIME) IS NOT NULL
 AND created_at<=updated_at AND created_at<expires_at
 AND expires_at<=validation_expires_at AND DATE(created_at+INTERVAL 8 HOUR)=naming_date
 AND expires_at<=CAST(DATE(created_at+INTERVAL 8 HOUR)+INTERVAL 1 DAY AS DATETIME)-INTERVAL 8 HOUR)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='原execute私有完整构建头；无公开准备接口且不授平台写权';

CREATE TABLE orbit_launch_execution_byte_chunk (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 preparation_id CHAR(36) NOT NULL COMMENT '私有完整准备UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '连续字节块号，从零开始',
 byte_length INT UNSIGNED NOT NULL COMMENT '实际字节长度，不是字符长度',
 chunk_hash CHAR(64) NOT NULL COMMENT '实际字节SHA256',
 payload LONGBLOB NOT NULL COMMENT '完整JSON文档有界字节块，允许UTF8字符跨块',
 created_at DATETIME(3) NOT NULL COMMENT '实际持久UTC',
 PRIMARY KEY(tenant_id,preparation_id,ordinal),
 FOREIGN KEY(tenant_id,preparation_id) REFERENCES orbit_launch_execution_preparation(tenant_id,id),
 CONSTRAINT ck_execution_byte CHECK(REGEXP_LIKE(chunk_hash,'^[a-f0-9]{64}$','c')
 AND byte_length BETWEEN 1 AND 1048576
 AND OCTET_LENGTH(payload)=byte_length AND SHA2(payload,256)=chunk_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='完整执行文档逐字节持久；缺块不能密封';

CREATE TABLE orbit_launch_execution_command (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 preparation_id CHAR(36) NOT NULL COMMENT '同一完整构建UUID',
 task_id CHAR(36) NOT NULL COMMENT '真实Task，BUILDING阶段不公开不发送',
 node_id CHAR(36) NOT NULL COMMENT '真实DAG节点UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '真实稳定拓扑序号',
 node_key VARCHAR(512) NOT NULL COMMENT '原完整DAG稳定节点键',
 kind VARCHAR(16) NOT NULL COMMENT '原真实TaskNode类别',
 purpose VARCHAR(32) NOT NULL COMMENT '明确节点用途，不是自由平台命令',
 account_id CHAR(36) NOT NULL COMMENT '真实目标账户UUID',
 target_key VARCHAR(512) NOT NULL COMMENT '真实稳定目标键',
 resolved_configuration_json JSON NOT NULL COMMENT '完整最终名身份配置素材归因参数，无临时URL或凭据',
 resolved_configuration_hash CHAR(64) NOT NULL COMMENT '实际规范resolved配置SHA256，Store重算',
 observation_binding_hash CHAR(64) NOT NULL COMMENT '完整受信来源观察引用的绑定摘要',
 state VARCHAR(24) NOT NULL DEFAULT 'QUEUED' COMMENT '沿真实节点运行状态；存在不等于允许发出',
 attempt INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '实际执行次数；本阶段无Worker故恒零',
 updated_at DATETIME(3) NOT NULL COMMENT '实际运行或持久UTC',
 created_at DATETIME(3) NOT NULL COMMENT '私有命令描述持久UTC，不是WRITE_INTENT',
 PRIMARY KEY(tenant_id,task_id,node_id),
 UNIQUE KEY uq_execution_command_ordinal(tenant_id,task_id,ordinal),
 FOREIGN KEY(tenant_id,preparation_id,task_id)
 REFERENCES orbit_launch_execution_preparation(tenant_id,id,task_id),
 FOREIGN KEY(tenant_id,task_id,node_id) REFERENCES orbit_task_node(tenant_id,task_id,id),
 CONSTRAINT ck_execution_command_kind CHECK(kind IN('UPLOAD','CAMPAIGN','ADSET','CREATIVE',
 'AD','VERIFY','ENABLE','ALLOCATION')),
 CONSTRAINT ck_execution_command_state CHECK(state IN('DRAFT','VALIDATED','QUEUED','RUNNING',
 'ACCEPTED','VERIFYING','SUCCEEDED','FAILED','UNKNOWN','RETRY_WAIT','CANCELLED','EXPIRED',
 'BLOCKED_AUTH','BLOCKED_DEPENDENCY','NEEDS_HUMAN')),
 CONSTRAINT ck_execution_configuration CHECK(JSON_TYPE(resolved_configuration_json)='OBJECT'
 AND REGEXP_LIKE(resolved_configuration_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(observation_binding_hash,'^[a-f0-9]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='不可变完整命令意图及独立运行状态；本阶段不注册发送器';

CREATE TABLE orbit_launch_execution_acceptance (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 plan_id CHAR(36) NOT NULL COMMENT '真实计划UUID',
 source_revision BIGINT NOT NULL COMMENT '同源至多一次真实Task受理',
 task_id CHAR(36) NOT NULL COMMENT '公开原202真实Task UUID',
 preparation_id CHAR(36) NOT NULL COMMENT '实际密封的私有准备UUID',
 validation_id CHAR(36) NOT NULL COMMENT '实际通过并未过期的038记录',
 validated_head_revision BIGINT NOT NULL COMMENT '实际预检CAS头',
 submitted_head_revision BIGINT NOT NULL COMMENT '原子SUBMITTED后外部头',
 validation_hash CHAR(64) NOT NULL COMMENT '原预检hash',
 manifest_hash CHAR(64) NOT NULL COMMENT '完整已密封字节清单hash',
 intent_hash CHAR(64) NOT NULL COMMENT '原完整execute业务意图hash',
 accepted_request_id CHAR(36) NOT NULL COMMENT '真实原202请求关联UUID',
 accepted_by BIGINT NOT NULL COMMENT '实际受理操作者，不替代冻结owner',
 accepted_at DATETIME(3) NOT NULL COMMENT '真实原子受理UTC',
 PRIMARY KEY(tenant_id,plan_id,source_revision),
 UNIQUE KEY uq_execution_accept_task(tenant_id,task_id),
 UNIQUE KEY uq_execution_accept_preparation(tenant_id,preparation_id),
 FOREIGN KEY(tenant_id,plan_id,source_revision)
 REFERENCES orbit_launch_plan_version(tenant_id,plan_id,revision),
 FOREIGN KEY(tenant_id,preparation_id,task_id)
 REFERENCES orbit_launch_execution_preparation(tenant_id,id,task_id),
 FOREIGN KEY(tenant_id,validation_id) REFERENCES orbit_launch_validation(tenant_id,id),
 CONSTRAINT ck_execution_accepted_head CHECK(REGEXP_LIKE(validation_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(manifest_hash,'^[a-f0-9]{64}$','c')
 AND REGEXP_LIKE(intent_hash,'^[a-f0-9]{64}$','c') AND source_revision>=1
 AND validated_head_revision>source_revision AND submitted_head_revision=validated_head_revision+1
 AND submitted_head_revision<=9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='原202同source唯一真实受理事实，不是后台分配runtime';

-- 下列护栏当前锁读prep；合法顺序Task→prep→child。
-- seal只锁prep转SEALING，不同时等待Task/child；SQL非法倒序可能1213，整笔回滚。

CREATE TRIGGER guard_execution_byte_insert BEFORE INSERT ON orbit_launch_execution_byte_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.preparation_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_INSERT';
 END IF;
END;

CREATE TRIGGER guard_execution_byte_update BEFORE UPDATE ON orbit_launch_execution_byte_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND id=OLD.preparation_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_PAYLOAD';
 END IF;
END;

CREATE TRIGGER guard_execution_byte_delete BEFORE DELETE ON orbit_launch_execution_byte_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND id=OLD.preparation_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_DELETE';
 END IF;
END;

CREATE TRIGGER guard_execution_command_insert BEFORE INSERT ON orbit_launch_execution_command FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_INSERT';
 END IF;
 IF NEW.state<>'QUEUED' OR NEW.attempt<>0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_INITIAL_COMMAND_REQUIRED';
 END IF;
END;

CREATE TRIGGER guard_execution_command_update BEFORE UPDATE ON orbit_launch_execution_command FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL AND stage_state<>'ACCEPTED' AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_UNACCEPTED_UPDATE';
 END IF;
 IF stage_state IS NOT NULL AND (
   (NOT (OLD.tenant_id <=> NEW.tenant_id)) OR
   (NOT (OLD.preparation_id <=> NEW.preparation_id)) OR
   (NOT (OLD.task_id <=> NEW.task_id)) OR
   (NOT (OLD.node_id <=> NEW.node_id)) OR
   (NOT (OLD.ordinal <=> NEW.ordinal)) OR
   (NOT (OLD.node_key <=> NEW.node_key)) OR
   (NOT (OLD.kind <=> NEW.kind)) OR
   (NOT (OLD.purpose <=> NEW.purpose)) OR
   (NOT (OLD.account_id <=> NEW.account_id)) OR
   (NOT (OLD.target_key <=> NEW.target_key)) OR
   (NOT (BINARY CAST(OLD.resolved_configuration_json AS CHAR) <=> BINARY CAST(NEW.resolved_configuration_json AS CHAR))) OR
   (NOT (OLD.resolved_configuration_hash <=> NEW.resolved_configuration_hash)) OR
   (NOT (OLD.observation_binding_hash <=> NEW.observation_binding_hash)) OR
   (NOT (OLD.created_at <=> NEW.created_at))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_INTENT';
 END IF;
END;

CREATE TRIGGER guard_execution_command_delete BEFORE DELETE ON orbit_launch_execution_command FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_BINDING_REQUIRED'; END IF;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_DELETE';
 END IF;
END;

CREATE TRIGGER guard_execution_node_insert BEFORE INSERT ON orbit_task_node FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_INSERT';
 END IF;
END;

CREATE TRIGGER guard_execution_node_update BEFORE UPDATE ON orbit_task_node FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'ACCEPTED' AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_UNACCEPTED_UPDATE';
 END IF;
 IF stage_state IS NOT NULL AND (
   (NOT (OLD.tenant_id <=> NEW.tenant_id)) OR
   (NOT (OLD.task_id <=> NEW.task_id)) OR
   (NOT (OLD.id <=> NEW.id)) OR
   (NOT (OLD.ordinal <=> NEW.ordinal)) OR
   (NOT (OLD.node_key <=> NEW.node_key)) OR
   (NOT (OLD.kind <=> NEW.kind)) OR
   (NOT (BINARY CAST(OLD.initial_json AS CHAR) <=> BINARY CAST(NEW.initial_json AS CHAR)))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_INTENT';
 END IF;
END;

CREATE TRIGGER guard_execution_node_delete BEFORE DELETE ON orbit_task_node FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_DELETE';
 END IF;
END;

CREATE TRIGGER guard_execution_edge_insert BEFORE INSERT ON orbit_task_edge FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_INSERT';
 END IF;
END;

CREATE TRIGGER guard_execution_edge_update BEFORE UPDATE ON orbit_task_edge FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_PAYLOAD';
 END IF;
END;

CREATE TRIGGER guard_execution_edge_delete BEFORE DELETE ON orbit_task_edge FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_DELETE';
 END IF;
END;

CREATE TRIGGER guard_execution_chunk_insert BEFORE INSERT ON orbit_task_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=NEW.tenant_id AND task_id=NEW.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_INSERT';
 END IF;
END;

CREATE TRIGGER guard_execution_chunk_update BEFORE UPDATE ON orbit_task_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_PAYLOAD';
 END IF;
END;

CREATE TRIGGER guard_execution_chunk_delete BEFORE DELETE ON orbit_task_chunk FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.task_id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_DELETE';
 END IF;
END;

-- TRUSTED只允许先创建空计数的隐藏Task，再同事务建立prep，不能直接发布。
-- 035历史NULL头兼容仅留给旧ISOLATED_TEST；新TRUSTED必须完整严格typed header。
CREATE TRIGGER guard_execution_task_insert BEFORE INSERT ON orbit_task FOR EACH ROW
BEGIN
 IF NEW.producer_kind='TRUSTED' THEN
  IF NEW.manifest_phase<>'BUILDING' OR NEW.state<>'QUEUED' OR NEW.revision<>1
   OR NEW.node_count<>0 OR NEW.edge_count<>0 OR NEW.latest_sequence<>0
   OR NEW.latest_event_id IS NOT NULL OR NEW.needs_manual_reconciliation<>0
   OR NEW.expected_node_count NOT BETWEEN 1 AND 100000
   OR NEW.expected_chunk_count<>(NEW.expected_node_count+499) DIV 500
   OR NEW.dag_schema_version IS NULL OR NEW.dag_schema_version<>1
   OR NEW.plan_input_hash IS NULL OR NEW.allocation_input_hash IS NULL
   OR NOT REGEXP_LIKE(NEW.plan_input_hash,'^[a-f0-9]{64}$','c')
   OR NOT REGEXP_LIKE(NEW.allocation_input_hash,'^[a-f0-9]{64}$','c')
   OR NOT REGEXP_LIKE(NEW.source_hash,'^[a-f0-9]{64}$','c')
   OR NOT REGEXP_LIKE(NEW.graph_hash,'^[a-f0-9]{64}$','c')
   OR NOT REGEXP_LIKE(NEW.manifest_hash,'^[a-f0-9]{64}$','c') THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_TRUSTED_INITIAL_TASK_REQUIRED';
  END IF;
 END IF;
END;

CREATE TRIGGER guard_execution_task_update BEFORE UPDATE ON orbit_task FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE accepted_request CHAR(36) DEFAULT NULL;
 DECLARE accepted_time DATETIME(3) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state,accepted_request_id,accepted_at INTO stage_state,accepted_request,accepted_time
 FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.id FOR SHARE;
 IF stage_state IS NULL AND (OLD.producer_kind='TRUSTED' OR NEW.producer_kind='TRUSTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_TRUSTED_BINDING_REQUIRED';
 END IF;
 IF stage_state IS NOT NULL THEN
  IF (NOT (OLD.tenant_id <=> NEW.tenant_id)) OR
   (NOT (OLD.id <=> NEW.id)) OR
   (NOT (OLD.owner_user_id <=> NEW.owner_user_id)) OR
   (NOT (OLD.owner_team_id <=> NEW.owner_team_id)) OR
   (NOT (OLD.source_plan_id <=> NEW.source_plan_id)) OR
   (NOT (OLD.source_revision <=> NEW.source_revision)) OR
   (NOT (OLD.source_hash <=> NEW.source_hash)) OR
   (NOT (OLD.execution_mode <=> NEW.execution_mode)) OR
   (NOT (OLD.producer_kind <=> NEW.producer_kind)) OR
   (NOT (OLD.graph_hash <=> NEW.graph_hash)) OR
   (NOT (OLD.manifest_hash <=> NEW.manifest_hash)) OR
   (NOT (OLD.expected_node_count <=> NEW.expected_node_count)) OR
   (NOT (OLD.expected_chunk_count <=> NEW.expected_chunk_count)) OR
   (NOT (OLD.created_by <=> NEW.created_by)) OR
   (NOT (OLD.dag_schema_version <=> NEW.dag_schema_version)) OR
   (NOT (OLD.plan_input_hash <=> NEW.plan_input_hash)) OR
   (NOT (OLD.allocation_input_hash <=> NEW.allocation_input_hash)) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_TASK_SOURCE';
  END IF;
  IF stage_state IN('BUILDING','SEALING','SEALED') AND
   (NEW.state<>'QUEUED' OR NEW.revision<>1 OR NEW.latest_sequence<>0
    OR NEW.latest_event_id IS NOT NULL OR NEW.needs_manual_reconciliation<>0) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_UNACCEPTED_TASK_RUNTIME';
  END IF;
  IF stage_state='ABORTED' THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ABORTED_TASK_UPDATE';
  END IF;
  IF stage_state<>'BUILDING' AND (NOT (OLD.node_count <=> NEW.node_count)
   OR NOT (OLD.edge_count <=> NEW.edge_count)) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_TASK_COUNT';
  END IF;
  IF NOT (OLD.manifest_phase <=> NEW.manifest_phase) THEN
   IF NOT (OLD.manifest_phase='BUILDING' AND NEW.manifest_phase='COMPLETE'
    AND stage_state='ACCEPTED' AND accepted_request IS NOT NULL AND accepted_time IS NOT NULL
    AND NEW.accepted_request_id=accepted_request
    AND NEW.created_at=accepted_time AND NEW.state='QUEUED' AND NEW.revision=1
    AND NEW.latest_sequence=1 AND NEW.latest_event_id IS NOT NULL) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ACCEPTANCE_REQUIRED';
   END IF;
  ELSEIF NOT (OLD.accepted_request_id <=> NEW.accepted_request_id)
   OR NOT (OLD.created_at <=> NEW.created_at) THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_ACCEPTANCE';
  END IF;
 END IF;
END;

CREATE TRIGGER guard_execution_task_delete BEFORE DELETE ON orbit_task FOR EACH ROW
BEGIN
 DECLARE stage_state VARCHAR(16) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_state=NULL;
 SELECT state INTO stage_state FROM orbit_launch_execution_preparation
 WHERE tenant_id=OLD.tenant_id AND task_id=OLD.id FOR SHARE;
 IF stage_state IS NOT NULL AND stage_state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FROZEN_TASK_DELETE';
 END IF;
END;

CREATE TRIGGER guard_execution_preparation_update BEFORE UPDATE
 ON orbit_launch_execution_preparation FOR EACH ROW
BEGIN
 IF (NOT (OLD.tenant_id <=> NEW.tenant_id)) OR
   (NOT (OLD.id <=> NEW.id)) OR
   (NOT (OLD.task_id <=> NEW.task_id)) OR
   (NOT (OLD.plan_id <=> NEW.plan_id)) OR
   (NOT (OLD.source_revision <=> NEW.source_revision)) OR
   (NOT (OLD.payload_hash <=> NEW.payload_hash)) OR
   (NOT (OLD.validation_id <=> NEW.validation_id)) OR
   (NOT (OLD.validated_head_revision <=> NEW.validated_head_revision)) OR
   (NOT (OLD.validation_hash <=> NEW.validation_hash)) OR
   (NOT (OLD.validation_expires_at <=> NEW.validation_expires_at)) OR
   (NOT (OLD.naming_date <=> NEW.naming_date)) OR
   (NOT (OLD.actor_id <=> NEW.actor_id)) OR
   (NOT (OLD.subject_id <=> NEW.subject_id)) OR
   (NOT (OLD.owner_user_id <=> NEW.owner_user_id)) OR
   (NOT (OLD.owner_team_id <=> NEW.owner_team_id)) OR
   (NOT (OLD.auth_version <=> NEW.auth_version)) OR
   (NOT (OLD.authorization_fingerprint <=> NEW.authorization_fingerprint)) OR
   (NOT (OLD.intent_hash <=> NEW.intent_hash)) OR
   (NOT (OLD.idempotency_key_hash <=> NEW.idempotency_key_hash)) OR
   (NOT (OLD.provider_kind <=> NEW.provider_kind)) OR
   (NOT (OLD.provider_fingerprint <=> NEW.provider_fingerprint)) OR
   (NOT (OLD.manifest_schema_version <=> NEW.manifest_schema_version)) OR
   (NOT (OLD.manifest_hash <=> NEW.manifest_hash)) OR
   (NOT (OLD.task_chunk_hash <=> NEW.task_chunk_hash)) OR
   (NOT (OLD.graph_hash <=> NEW.graph_hash)) OR
   (NOT (OLD.plan_input_hash <=> NEW.plan_input_hash)) OR
   (NOT (OLD.allocation_input_hash <=> NEW.allocation_input_hash)) OR
   (NOT (OLD.expected_bytes <=> NEW.expected_bytes)) OR
   (NOT (OLD.expected_byte_chunks <=> NEW.expected_byte_chunks)) OR
   (NOT (OLD.expected_node_count <=> NEW.expected_node_count)) OR
   (NOT (OLD.expected_node_chunks <=> NEW.expected_node_chunks)) OR
   (NOT (OLD.expected_command_count <=> NEW.expected_command_count)) OR
   (NOT (OLD.expected_edge_count <=> NEW.expected_edge_count)) OR
   (NOT (OLD.created_at <=> NEW.created_at)) OR
   (NOT (OLD.expires_at <=> NEW.expires_at)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_BINDING';
 END IF;
 IF OLD.state IN('ACCEPTED','ABORTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_TERMINAL_PREPARATION';
 END IF;
 IF NOT ((OLD.state='BUILDING' AND NEW.state IN('BUILDING','SEALING','ABORTED'))
 OR (OLD.state='SEALING' AND NEW.state IN('SEALED','ABORTED'))
 OR (OLD.state='SEALED' AND NEW.state IN('ACCEPTED','ABORTED')))
 OR NEW.mutation_revision<>OLD.mutation_revision+1 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_PREPARATION_TRANSITION';
 END IF;
 IF OLD.state<>'BUILDING' AND (
(NOT (OLD.persisted_bytes <=> NEW.persisted_bytes)) OR
   (NOT (OLD.persisted_byte_chunks <=> NEW.persisted_byte_chunks)) OR
   (NOT (OLD.persisted_node_count <=> NEW.persisted_node_count)) OR
   (NOT (OLD.persisted_node_chunks <=> NEW.persisted_node_chunks)) OR
   (NOT (OLD.persisted_command_count <=> NEW.persisted_command_count)) OR
   (NOT (OLD.persisted_edge_count <=> NEW.persisted_edge_count))) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_SEALED_COUNT';
 END IF;
 IF NEW.state='SEALED' AND NEW.sealed_revision<>NEW.mutation_revision THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_SEAL_VERSION_REQUIRED';
 END IF;
 IF OLD.state='SEALED' AND (NOT (OLD.sealed_at <=> NEW.sealed_at)
 OR NOT (OLD.sealed_revision <=> NEW.sealed_revision)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_IMMUTABLE_SEAL';
 END IF;
 IF NEW.state='ACCEPTED' AND NOT EXISTS(SELECT 1 FROM orbit_launch_execution_acceptance a
 WHERE a.tenant_id=NEW.tenant_id AND a.preparation_id=NEW.id AND a.task_id=NEW.task_id
 AND a.plan_id=NEW.plan_id AND a.source_revision=NEW.source_revision
 AND a.validation_id=NEW.validation_id AND a.validated_head_revision=NEW.validated_head_revision
 AND a.submitted_head_revision=NEW.accepted_head_revision AND a.intent_hash=NEW.intent_hash
 AND a.validation_hash=NEW.validation_hash AND a.manifest_hash=NEW.manifest_hash
 AND a.accepted_request_id=NEW.accepted_request_id AND a.accepted_at=NEW.accepted_at) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ACCEPTANCE_BINDING_REQUIRED';
 END IF;
END;

CREATE TRIGGER guard_execution_preparation_delete BEFORE DELETE
 ON orbit_launch_execution_preparation FOR EACH ROW
BEGIN
 IF OLD.state<>'ABORTED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_PREPARATION_DELETE_FORBIDDEN';
 END IF;
END;

CREATE TRIGGER guard_execution_acceptance_update BEFORE UPDATE
 ON orbit_launch_execution_acceptance FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ACCEPTANCE_IMMUTABLE';
END;
CREATE TRIGGER guard_execution_acceptance_delete BEFORE DELETE
 ON orbit_launch_execution_acceptance FOR EACH ROW
BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ACCEPTANCE_IMMUTABLE';
END;

-- 必须从零计数BUILDING开始，禁止插入伪密封头直接套旧Task。
CREATE TRIGGER guard_execution_preparation_insert BEFORE INSERT
 ON orbit_launch_execution_preparation FOR EACH ROW
BEGIN
 DECLARE target_id CHAR(36) DEFAULT NULL;
 DECLARE validation_record CHAR(36) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND BEGIN
  SET target_id=NULL;
  SET validation_record=NULL;
 END;
 SELECT id INTO target_id FROM orbit_task
 WHERE tenant_id=NEW.tenant_id AND id=NEW.task_id AND manifest_phase='BUILDING'
 AND source_plan_id=NEW.plan_id AND source_revision=NEW.source_revision
 AND source_hash=NEW.payload_hash AND owner_user_id=NEW.owner_user_id
 AND owner_team_id=NEW.owner_team_id AND producer_kind=NEW.provider_kind
 AND graph_hash=NEW.graph_hash AND manifest_hash=NEW.task_chunk_hash
 AND plan_input_hash=NEW.plan_input_hash AND allocation_input_hash=NEW.allocation_input_hash
 AND expected_node_count=NEW.expected_node_count AND expected_chunk_count=NEW.expected_node_chunks
 AND node_count=0 AND edge_count=0 AND state='QUEUED' AND revision=1
 AND latest_sequence=0 AND latest_event_id IS NULL AND created_by=NEW.actor_id FOR SHARE;
 -- stage_begin先锁真实038来源，再Task→prep；这里重入同一共享锁。
 -- FK只证明validation UUID存在，不能替代同计划/源/头/hash/时效/命名日绑定。
 SELECT id INTO validation_record FROM orbit_launch_validation
 WHERE tenant_id=NEW.tenant_id AND id=NEW.validation_id AND plan_id=NEW.plan_id
 AND source_revision=NEW.source_revision AND payload_hash=NEW.payload_hash
 AND validated_head_revision=NEW.validated_head_revision AND validation_hash=NEW.validation_hash
 AND expires_at=NEW.validation_expires_at AND naming_date=NEW.naming_date FOR SHARE;
 IF target_id IS NULL OR validation_record IS NULL
 OR NEW.state<>'BUILDING' OR NEW.mutation_revision<>1
 OR NEW.persisted_bytes<>0 OR NEW.persisted_byte_chunks<>0 OR NEW.persisted_node_count<>0
 OR NEW.persisted_node_chunks<>0 OR NEW.persisted_command_count<>0 OR NEW.persisted_edge_count<>0
 OR NEW.sealed_revision IS NOT NULL OR NEW.sealed_at IS NOT NULL
 OR NEW.accepted_at IS NOT NULL OR NEW.accepted_head_revision IS NOT NULL
 OR NEW.accepted_request_id IS NOT NULL OR UTC_TIMESTAMP(3)>=NEW.expires_at THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_INITIAL_BINDING_REQUIRED';
 END IF;
END;

CREATE TRIGGER guard_execution_acceptance_insert BEFORE INSERT
 ON orbit_launch_execution_acceptance FOR EACH ROW
BEGIN
 DECLARE stage_id CHAR(36) DEFAULT NULL;
 DECLARE CONTINUE HANDLER FOR NOT FOUND SET stage_id=NULL;
 SELECT id INTO stage_id FROM orbit_launch_execution_preparation p
 WHERE p.tenant_id=NEW.tenant_id AND p.id=NEW.preparation_id AND p.task_id=NEW.task_id
 AND p.state='SEALED' AND p.plan_id=NEW.plan_id AND p.source_revision=NEW.source_revision
 AND p.validation_id=NEW.validation_id AND p.validated_head_revision=NEW.validated_head_revision
 AND p.intent_hash=NEW.intent_hash AND p.validation_hash=NEW.validation_hash
 AND p.manifest_hash=NEW.manifest_hash AND p.actor_id=NEW.accepted_by
 AND NEW.accepted_at<LEAST(p.expires_at,p.validation_expires_at)
 AND DATE(NEW.accepted_at+INTERVAL 8 HOUR)=p.naming_date FOR SHARE;
 IF stage_id IS NULL OR NEW.accepted_at>UTC_TIMESTAMP(3) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_SEALED_ACCEPTANCE_REQUIRED';
 END IF;
END;
