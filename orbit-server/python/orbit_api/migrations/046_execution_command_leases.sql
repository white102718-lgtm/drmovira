-- 046候选，尚未执行；不注册Worker、不发送、不改变033/039公开状态。
-- 新尝试先插入、运行头后指向该精确尝试；同一外层事务避免不可延迟FK环。
CREATE TABLE orbit_execution_attempt (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 task_id CHAR(36) NOT NULL COMMENT '原完整受理任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '原命令及节点UUID',
 preparation_id CHAR(36) NOT NULL COMMENT '039冻结执行准备UUID',
 attempt_no INT UNSIGNED NOT NULL COMMENT '实际尝试从一开始，保留所有历史尝试',
 fencing_token BIGINT NOT NULL COMMENT '该命令单调代际，不得复用旧代际推进状态',
 claim_id CHAR(36) NOT NULL COMMENT '服务端本次领取唯一UUID',
 worker_id CHAR(36) NOT NULL COMMENT '本次明确拥有者实例UUID，不是设备授权',
 execution_mode VARCHAR(16) NOT NULL COMMENT '原冻结META_API或ADSPOWER_UI，不允许未知时换通道',
 command_hash CHAR(64) NOT NULL COMMENT '039冻结完整解析命令规范摘要，应用重算',
 manifest_hash CHAR(64) NOT NULL COMMENT '039完整清单摘要，不是块根',
 source_hash CHAR(64) NOT NULL COMMENT '冻结来源配置及依赖摘要，应用重算',
 authority_hash CHAR(64) NOT NULL COMMENT '真实领取权威证明摘要，不能以类型标签替代授权',
 authorization_hash CHAR(64) NOT NULL COMMENT '发起人当前动作及拥有者范围核验摘要',
 actor_id BIGINT NOT NULL COMMENT '领取时原生发起人ID，不是后台系统账号替代',
 subject_id CHAR(36) NOT NULL COMMENT '领取时实际业务身份UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '冻结任务实际拥有者UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '冻结任务实际拥有团队UUID',
 auth_version BIGINT NOT NULL COMMENT '领取时当前身份授权版本，发送前仍须再次核验',
 created_at DATETIME(3) NOT NULL COMMENT '可信SQL UTC领取时间',
 PRIMARY KEY(tenant_id,task_id,node_id,attempt_no),
 UNIQUE KEY uq_exec_attempt_fence(tenant_id,task_id,node_id,fencing_token),
 UNIQUE KEY uq_exec_attempt_claim(tenant_id,claim_id),
 UNIQUE KEY uq_exec_attempt_binding(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id),
 FOREIGN KEY(tenant_id,task_id,node_id)
 REFERENCES orbit_launch_execution_command(tenant_id,task_id,node_id),
 FOREIGN KEY(tenant_id,preparation_id,task_id)
 REFERENCES orbit_launch_execution_preparation(tenant_id,id,task_id),
 FOREIGN KEY(tenant_id,subject_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CONSTRAINT ck_exec_attempt_number CHECK(attempt_no>=1 AND fencing_token BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_exec_attempt_actor CHECK(actor_id BETWEEN 1 AND 9007199254740991
 AND auth_version BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_exec_attempt_mode CHECK(execution_mode IN('META_API','ADSPOWER_UI')),
 CONSTRAINT ck_exec_attempt_hash CHECK(
 CHAR_LENGTH(command_hash)=64 AND NOT REGEXP_LIKE(command_hash,'[^0-9a-f]','c')
 AND CHAR_LENGTH(manifest_hash)=64 AND NOT REGEXP_LIKE(manifest_hash,'[^0-9a-f]','c')
 AND CHAR_LENGTH(source_hash)=64 AND NOT REGEXP_LIKE(source_hash,'[^0-9a-f]','c')
 AND CHAR_LENGTH(authority_hash)=64 AND NOT REGEXP_LIKE(authority_hash,'[^0-9a-f]','c')
 AND CHAR_LENGTH(authorization_hash)=64 AND NOT REGEXP_LIKE(authorization_hash,'[^0-9a-f]','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='不可变执行尝试；存在不代表已发送或正式发送权限';

CREATE TABLE orbit_execution_command_runtime (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 task_id CHAR(36) NOT NULL COMMENT '完整受理任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '原命令UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '内部运行CAS水位，状态写入仍须原任务及节点同步CAS',
 active_attempt INT UNSIGNED NULL COMMENT '当前精确尝试；初始未领取为空',
 fencing_token BIGINT NOT NULL DEFAULT 0 COMMENT '单调代际，初始未领取为零',
 claim_id CHAR(36) NULL COMMENT '当前尝试领取UUID；清租约不能清掉该绑定',
 worker_id CHAR(36) NULL COMMENT '当前尝试所属实例UUID',
 lease_expires_at DATETIME(3) NULL COMMENT '租约SQL UTC有效期，不授广告写权限',
 unknown_since DATETIME(3) NULL COMMENT '当前未知开始UTC，不因每次核验重置二十四小时',
 last_reconciled_at DATETIME(3) NULL COMMENT '实际只读核验完成UTC，不是新写发送',
 next_reconcile_at DATETIME(3) NULL COMMENT '未知五分钟只读核验水位，人工处理后可为空',
 needs_manual_reconciliation BOOLEAN NOT NULL DEFAULT FALSE COMMENT '二十四小时后人工标识，不改变UNKNOWN',
 created_at DATETIME(3) NOT NULL COMMENT '可信SQL UTC建立时间',
 updated_at DATETIME(3) NOT NULL COMMENT '可信SQL UTC实际运行变更时间',
 PRIMARY KEY(tenant_id,task_id,node_id),
 KEY idx_exec_runtime_expiry(lease_expires_at,tenant_id,task_id,node_id),
 KEY idx_exec_runtime_reconcile(next_reconcile_at,tenant_id,task_id,node_id),
 FOREIGN KEY(tenant_id,task_id,node_id)
 REFERENCES orbit_launch_execution_command(tenant_id,task_id,node_id),
 FOREIGN KEY(tenant_id,task_id,node_id,active_attempt,fencing_token,claim_id,worker_id)
 REFERENCES orbit_execution_attempt(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id),
 CONSTRAINT ck_exec_runtime_revision CHECK(revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_exec_runtime_binding CHECK(
 (active_attempt IS NULL AND fencing_token=0 AND claim_id IS NULL AND worker_id IS NULL
 AND lease_expires_at IS NULL AND unknown_since IS NULL AND last_reconciled_at IS NULL
 AND next_reconcile_at IS NULL AND needs_manual_reconciliation=FALSE)
 OR (active_attempt IS NOT NULL AND active_attempt>=1 AND fencing_token BETWEEN 1 AND 9007199254740991
 AND claim_id IS NOT NULL AND worker_id IS NOT NULL)),
 CONSTRAINT ck_exec_runtime_time CHECK(created_at<=updated_at
 AND (lease_expires_at IS NULL OR lease_expires_at>created_at)
 AND (unknown_since IS NULL OR unknown_since<=updated_at)
 AND (last_reconciled_at IS NULL OR (unknown_since IS NOT NULL AND last_reconciled_at>=unknown_since
 AND last_reconciled_at<=updated_at))
 AND (next_reconcile_at IS NULL OR (unknown_since IS NOT NULL AND next_reconcile_at>=unknown_since))
 AND (needs_manual_reconciliation=FALSE OR (unknown_since IS NOT NULL
 AND updated_at>=unknown_since+INTERVAL 24 HOUR))),
 CONSTRAINT ck_exec_runtime_boolean CHECK(needs_manual_reconciliation IN(0,1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='命令当前租约及核验头；不重复存公开状态，状态仍取039命令及033节点';

CREATE TABLE orbit_execution_attempt_fact (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 task_id CHAR(36) NOT NULL COMMENT '原任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '原命令UUID',
 attempt_no INT UNSIGNED NOT NULL COMMENT '事实发生所属尝试，晚到不得改绑当前尝试',
 fencing_token BIGINT NOT NULL COMMENT '事实发生时真实代际',
 claim_id CHAR(36) NOT NULL COMMENT '事实发生时领取UUID',
 worker_id CHAR(36) NOT NULL COMMENT '事实发生时来源实例UUID',
 event_id CHAR(36) NOT NULL COMMENT '来源稳定事件UUID，同键异内容必须拒绝',
 sequence_no INT UNSIGNED NOT NULL COMMENT '该尝试事实连续序号，从一开始且受事务CAS保护',
 fact_kind VARCHAR(32) NOT NULL COMMENT '私有事实类型，不是TaskNode或command状态',
 send_phase VARCHAR(24) NOT NULL COMMENT '事实对应真实发送阶段，不凭无意图行推断未发送',
 evidence_source VARCHAR(32) NOT NULL COMMENT '经Store核验的来源类别，字符串本身不是信任证明',
 evidence_sha256 CHAR(64) NOT NULL COMMENT '必要脱敏证据规范摘要，不存Token或整份平台响应',
 external_id VARCHAR(64) NULL COMMENT '原平台唯一数字对象ID，成功读回必须具备',
 occurred_at DATETIME(3) NOT NULL COMMENT '事实真实发生UTC，来源时钟须核验',
 recorded_at DATETIME(3) NOT NULL COMMENT '可信SQL实际入库UTC，晚到事实仍保留',
 PRIMARY KEY(tenant_id,event_id),
 UNIQUE KEY uq_exec_fact_sequence(tenant_id,task_id,node_id,attempt_no,sequence_no),
 KEY idx_exec_fact_attempt(tenant_id,task_id,node_id,attempt_no,occurred_at,event_id),
 FOREIGN KEY(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id)
 REFERENCES orbit_execution_attempt(tenant_id,task_id,node_id,attempt_no,fencing_token,claim_id,worker_id),
 CONSTRAINT ck_exec_fact_seq CHECK(sequence_no>=1),
 CONSTRAINT ck_exec_fact_hash CHECK(CHAR_LENGTH(evidence_sha256)=64
 AND NOT REGEXP_LIKE(evidence_sha256,'[^0-9a-f]','c')),
 CONSTRAINT ck_exec_fact_external CHECK(external_id IS NULL OR (CHAR_LENGTH(external_id) BETWEEN 1 AND 64
 AND NOT REGEXP_LIKE(external_id,'[^0-9]','c'))),
 CONSTRAINT ck_exec_fact_time CHECK(occurred_at<=recorded_at),
 CONSTRAINT ck_exec_fact_phase CHECK(
 (fact_kind='WRITE_INTENT' AND send_phase='BEFORE_DISPATCH' AND evidence_source='LOCAL_INTENT')
 OR (fact_kind='PROVED_NOT_SENT' AND send_phase='BEFORE_DISPATCH' AND evidence_source='TRANSPORT_PROVEN_NO_SEND')
 OR (fact_kind='ACCEPTED' AND send_phase='ACKNOWLEDGED' AND evidence_source='PLATFORM_ACK')
 OR (fact_kind IN('READBACK_SUCCEEDED','READBACK_REJECTED','READBACK_INCONCLUSIVE')
 AND send_phase='READBACK' AND evidence_source='PLATFORM_READBACK')),
 CONSTRAINT ck_exec_fact_success CHECK(fact_kind<>'READBACK_SUCCEEDED' OR external_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='不可变历史事实，旧代际可留档但不能推进当前命令';

CREATE TRIGGER guard_exec_attempt_update BEFORE UPDATE ON orbit_execution_attempt FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ATTEMPT_IMMUTABLE';
CREATE TRIGGER guard_exec_attempt_delete BEFORE DELETE ON orbit_execution_attempt FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_ATTEMPT_IMMUTABLE';
CREATE TRIGGER guard_exec_fact_update BEFORE UPDATE ON orbit_execution_attempt_fact FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FACT_IMMUTABLE';
CREATE TRIGGER guard_exec_fact_delete BEFORE DELETE ON orbit_execution_attempt_fact FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_FACT_IMMUTABLE';
CREATE TRIGGER guard_exec_runtime_delete BEFORE DELETE ON orbit_execution_command_runtime FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RUNTIME_DELETE_FORBIDDEN';
CREATE TRIGGER guard_exec_runtime_update BEFORE UPDATE ON orbit_execution_command_runtime FOR EACH ROW
BEGIN
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.task_id<>OLD.task_id OR NEW.node_id<>OLD.node_id
 OR NEW.created_at<>OLD.created_at OR OLD.revision>=9007199254740991 OR NEW.revision<>OLD.revision+1
 OR NEW.updated_at<OLD.updated_at OR NEW.fencing_token<OLD.fencing_token
 OR NOT ((NEW.active_attempt<=>OLD.active_attempt) AND NEW.fencing_token=OLD.fencing_token
 AND (NEW.claim_id<=>OLD.claim_id) AND (NEW.worker_id<=>OLD.worker_id)
 OR (NEW.active_attempt=COALESCE(OLD.active_attempt,0)+1
 AND NEW.fencing_token=OLD.fencing_token+1)) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='EXECUTION_RUNTIME_CAS_INVALID';
 END IF;
END;
