-- 052恢复决策候选；仅审阅，正式采用及真实SQL由主线执行。
-- 不领取、不发送、不释放预算；TaskEvent关联保留不可变快照，避免阻断原七天SSE清理。
CREATE TABLE orbit_execution_recovery_decision (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '本次实际恢复提交UUID，不代表广告尝试',
 task_id CHAR(36) NOT NULL COMMENT '原完整任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '被恢复原命令节点UUID',
 attempt_no INT UNSIGNED NOT NULL COMMENT '原广告尝试编号，恢复不得递增',
 fencing_token BIGINT NOT NULL COMMENT '原执行代际，不得借核验重新领取',
 claim_id CHAR(36) NOT NULL COMMENT '原领取UUID',
 worker_id CHAR(36) NOT NULL COMMENT '原拥有者实例UUID',
 before_runtime_revision BIGINT NOT NULL COMMENT '精确CAS旧运行版本',
 after_runtime_revision BIGINT NOT NULL COMMENT '本次单次运行更新版本，必须旧值加一',
 before_task_revision BIGINT NOT NULL COMMENT '本次提交前Task版本',
 after_task_revision BIGINT NOT NULL COMMENT '每条实际节点边或人工标记各递增一次的最终Task版本',
 before_task_sequence BIGINT NOT NULL COMMENT '本次提交前Task事件水位',
 after_task_sequence BIGINT NOT NULL COMMENT '本次提交最后事件水位',
 before_task_clock BIGINT NOT NULL COMMENT '租户任务目录提交前水位',
 after_task_clock BIGINT NOT NULL COMMENT '整次恢复只递增一次的任务目录水位',
 fact_count INT UNSIGNED NOT NULL COMMENT '本尝试完整验证事实总数，不是六类代表数量',
 fact_last_sequence INT UNSIGNED NOT NULL COMMENT '完整连续事实最后序号，无事实为零',
 fact_root_sha256 CHAR(64) NOT NULL COMMENT '有序完整事实域隔离链摘要，应用逐行重算，不存无限JSON',
 hash_schema_version INT NOT NULL COMMENT '固定有序事实规范摘要算法版本一',
 publication_phase VARCHAR(8) NOT NULL DEFAULT 'BUILDING' COMMENT '同事务构建后完整封存，未封存不能作为恢复结果',
 decision_code VARCHAR(40) NOT NULL COMMENT '受控原恢复决策代码，不含异常文本',
 state_path_json JSON NOT NULL COMMENT '最多三项原节点状态路径，应用严格校验每条原边',
 event_count INT UNSIGNED NOT NULL COMMENT '同事务实际状态边及人工标记事件数，一至三',
 actor_id BIGINT NOT NULL COMMENT '受控恢复主体真实原生ID',
 request_id CHAR(36) NOT NULL COMMENT '安全请求关联UUID，不替代业务幂等协议',
 decided_at DATETIME(6) NOT NULL COMMENT '可信SQL UTC完整决策时间',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_exec_recovery_revision(tenant_id,task_id,node_id,after_runtime_revision),
 UNIQUE KEY uq_exec_recovery_parent(tenant_id,task_id,node_id,id),
 KEY idx_exec_recovery_task(tenant_id,task_id,after_task_sequence,id),
 FOREIGN KEY(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id)
 REFERENCES orbit_execution_attempt(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id),
 CONSTRAINT ck_exec_recovery_versions CHECK(
 before_runtime_revision BETWEEN 1 AND 9007199254740990 AND after_runtime_revision=before_runtime_revision+1
 AND before_task_revision BETWEEN 1 AND 9007199254740988
 AND after_task_revision=before_task_revision+event_count
 AND before_task_sequence BETWEEN 0 AND 9007199254740988
 AND after_task_sequence=before_task_sequence+event_count
 AND before_task_clock BETWEEN 1 AND 9007199254740990 AND after_task_clock=before_task_clock+1),
 CONSTRAINT ck_exec_recovery_facts CHECK(fact_count=fact_last_sequence),
 CONSTRAINT ck_exec_recovery_root CHECK(CHAR_LENGTH(fact_root_sha256)=64
 AND NOT REGEXP_LIKE(fact_root_sha256,'[^0-9a-f]','c') AND hash_schema_version=1),
 CONSTRAINT ck_exec_recovery_events CHECK(event_count BETWEEN 1 AND 3),
 CONSTRAINT ck_exec_recovery_publication CHECK(publication_phase IN('BUILDING','SEALED')),
 CONSTRAINT ck_exec_recovery_actor CHECK(actor_id BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_exec_recovery_path CHECK(JSON_TYPE(state_path_json)='ARRAY'
 AND JSON_LENGTH(state_path_json) BETWEEN 1 AND 3),
 CONSTRAINT ck_exec_recovery_code CHECK(decision_code IN(
 'UNKNOWN_MANUAL_REQUIRED','UNKNOWN_READ_ONLY','ACCEPTED_REQUIRES_READBACK',
 'SEND_EVIDENCE_CONFLICT','ACK_REQUIRES_READBACK','PROVED_NOT_SENT','LEASE_OUTCOME_UNKNOWN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='不可变恢复决策证据根及精确运行绑定；无变化不插入';

CREATE TABLE orbit_execution_recovery_edge (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 task_id CHAR(36) NOT NULL COMMENT '原完整任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '恢复节点UUID，原TaskEvent同节点',
 decision_id CHAR(36) NOT NULL COMMENT '恢复决策UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '本次实际事件序号，一至三',
 event_id CHAR(36) NOT NULL COMMENT '同事务原TaskEvent UUID快照，事件七天清理不删除此关联',
 event_sequence BIGINT NOT NULL COMMENT '同事务原TaskEvent序号快照',
 task_revision BIGINT NOT NULL COMMENT '该边实际Task版本',
 node_before_state VARCHAR(40) NOT NULL COMMENT '该边前原节点状态，人工标志边为UNKNOWN',
 node_after_state VARCHAR(40) NOT NULL COMMENT '该边后原节点状态，不能用Task汇总替换',
 task_after_state VARCHAR(40) NOT NULL COMMENT '该边后按完整当前节点汇总的Task状态',
 edge_kind VARCHAR(16) NOT NULL COMMENT '原状态边STATE或人工标记MANUAL',
 audit_id CHAR(36) NOT NULL COMMENT '同事务安全审计UUID，不包含文件路径或凭据',
 PRIMARY KEY(tenant_id,decision_id,ordinal),
 UNIQUE KEY uq_exec_recovery_event(tenant_id,event_id),
 UNIQUE KEY uq_exec_recovery_audit(audit_id),
 FOREIGN KEY(tenant_id,task_id,node_id,decision_id)
 REFERENCES orbit_execution_recovery_decision(tenant_id,task_id,node_id,id),
 FOREIGN KEY(tenant_id,task_id,audit_id) REFERENCES orbit_task_audit(tenant_id,task_id,id),
 CONSTRAINT ck_exec_recovery_edge_number CHECK(ordinal BETWEEN 1 AND 3
 AND event_sequence BETWEEN 1 AND 9007199254740991 AND task_revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_exec_recovery_edge_kind CHECK(
 (edge_kind='MANUAL' AND node_before_state='UNKNOWN' AND node_after_state='UNKNOWN')
 OR (edge_kind='STATE' AND (
 (node_before_state='RUNNING' AND node_after_state IN('ACCEPTED','FAILED','UNKNOWN'))
 OR (node_before_state='ACCEPTED' AND node_after_state='VERIFYING')
 OR (node_before_state='VERIFYING' AND node_after_state='UNKNOWN')))),
 CONSTRAINT ck_exec_recovery_task_state CHECK(task_after_state IN(
 'QUEUED','RUNNING','VERIFYING','UNKNOWN','RETRY_WAIT','SUCCEEDED','PARTIAL_SUCCESS',
 'FAILED','CANCELLED','NEEDS_HUMAN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='恢复事件审计不可变关联快照；保持原SSE事件清理合同';

CREATE TRIGGER guard_exec_recovery_decision_insert BEFORE INSERT ON orbit_execution_recovery_decision FOR EACH ROW
BEGIN
 IF NEW.publication_phase<>'BUILDING' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_BUILD_REQUIRED';
 END IF;
END;
CREATE TRIGGER guard_exec_recovery_decision_update BEFORE UPDATE ON orbit_execution_recovery_decision FOR EACH ROW
BEGIN
 DECLARE actual_count INT;
 DECLARE valid_count INT;
 IF OLD.publication_phase<>'BUILDING' OR NEW.publication_phase<>'SEALED' OR NOT (NEW.tenant_id<=>OLD.tenant_id)
 OR NOT (NEW.id<=>OLD.id)
 OR NOT (NEW.task_id<=>OLD.task_id)
 OR NOT (NEW.node_id<=>OLD.node_id)
 OR NOT (NEW.attempt_no<=>OLD.attempt_no)
 OR NOT (NEW.fencing_token<=>OLD.fencing_token)
 OR NOT (NEW.claim_id<=>OLD.claim_id)
 OR NOT (NEW.worker_id<=>OLD.worker_id)
 OR NOT (NEW.before_runtime_revision<=>OLD.before_runtime_revision)
 OR NOT (NEW.after_runtime_revision<=>OLD.after_runtime_revision)
 OR NOT (NEW.before_task_revision<=>OLD.before_task_revision)
 OR NOT (NEW.after_task_revision<=>OLD.after_task_revision)
 OR NOT (NEW.before_task_sequence<=>OLD.before_task_sequence)
 OR NOT (NEW.after_task_sequence<=>OLD.after_task_sequence)
 OR NOT (NEW.before_task_clock<=>OLD.before_task_clock)
 OR NOT (NEW.after_task_clock<=>OLD.after_task_clock)
 OR NOT (NEW.fact_count<=>OLD.fact_count)
 OR NOT (NEW.fact_last_sequence<=>OLD.fact_last_sequence)
 OR NOT (NEW.fact_root_sha256<=>OLD.fact_root_sha256)
 OR NOT (NEW.hash_schema_version<=>OLD.hash_schema_version)
 OR NOT (NEW.decision_code<=>OLD.decision_code)
 OR NOT (NEW.state_path_json<=>OLD.state_path_json)
 OR NOT (NEW.event_count<=>OLD.event_count)
 OR NOT (NEW.actor_id<=>OLD.actor_id)
 OR NOT (NEW.request_id<=>OLD.request_id)
 OR NOT (NEW.decided_at<=>OLD.decided_at) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_IMMUTABLE';
 END IF;
 SELECT COUNT(*),COALESCE(SUM(ordinal BETWEEN 1 AND NEW.event_count
 AND event_sequence=NEW.before_task_sequence+ordinal
 AND task_revision=NEW.before_task_revision+ordinal),0)
 INTO actual_count,valid_count FROM orbit_execution_recovery_edge
 WHERE tenant_id=NEW.tenant_id AND decision_id=NEW.id;
 IF actual_count<>NEW.event_count OR valid_count<>NEW.event_count THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_INCOMPLETE';
 END IF;
END;
CREATE TRIGGER guard_exec_recovery_decision_delete BEFORE DELETE ON orbit_execution_recovery_decision FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_IMMUTABLE';
CREATE TRIGGER guard_exec_recovery_edge_insert BEFORE INSERT ON orbit_execution_recovery_edge FOR EACH ROW
BEGIN
 DECLARE parent_phase VARCHAR(8);
 DECLARE parent_count INT;
 SELECT publication_phase,event_count INTO parent_phase,parent_count
 FROM orbit_execution_recovery_decision WHERE tenant_id=NEW.tenant_id AND id=NEW.decision_id FOR UPDATE;
 IF parent_phase IS NULL OR parent_phase<>'BUILDING' OR NEW.ordinal>parent_count THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_EDGE_CLOSED';
 END IF;
END;
CREATE TRIGGER guard_exec_recovery_edge_update BEFORE UPDATE ON orbit_execution_recovery_edge FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_IMMUTABLE';
CREATE TRIGGER guard_exec_recovery_edge_delete BEFORE DELETE ON orbit_execution_recovery_edge FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RECOVERY_IMMUTABLE';
