-- 070：持久派单仍需可信上游；租约不代替真实能力验证或平台写入授权。
CREATE TABLE orbit_agent_dispatch (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '稳定内部派单UUID',
 task_id CHAR(36) NOT NULL COMMENT '已完整受理任务UUID',
 node_id CHAR(36) NOT NULL COMMENT '真实冻结命令节点UUID',
 operation_id CHAR(36) NOT NULL COMMENT '原业务操作UUID',
 agent_id CHAR(36) NOT NULL COMMENT '固定执行设备UUID',
 profile_binding_id CHAR(36) NOT NULL COMMENT '固定账户Profile关联UUID',
 binding_revision BIGINT NOT NULL COMMENT '冻结关联版本',
 actor_id BIGINT NOT NULL COMMENT '原执行授权操作者',
 entity_type VARCHAR(16) NOT NULL COMMENT 'CAMPAIGN/ADSET/AD能力对象层级',
 versions_json JSON NOT NULL COMMENT '工作流页面适配器客户端内核语言精确版本',
 instruction_json JSON NOT NULL COMMENT '冻结指令稳定字段，不含密钥或临时租约字段',
 command_hash CHAR(64) NOT NULL COMMENT '稳定规范指令SHA256',
 state VARCHAR(16) NOT NULL DEFAULT 'QUEUED' COMMENT 'QUEUED/LEASED/UNKNOWN/COMPLETED；UNKNOWN绝不重派',
 created_at DATETIME(6) NOT NULL COMMENT 'SQL实际入队UTC',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_agent_dispatch_node(tenant_id,task_id,node_id),
 KEY ix_agent_dispatch_queue(tenant_id,agent_id,state,created_at,id),
 FOREIGN KEY(tenant_id,task_id,node_id) REFERENCES orbit_launch_execution_command(tenant_id,task_id,node_id),
 FOREIGN KEY(tenant_id,profile_binding_id) REFERENCES orbit_profile_binding(tenant_id,id),
 CONSTRAINT ck_agent_dispatch_state CHECK(state IN('QUEUED','LEASED','UNKNOWN','COMPLETED')),
 CONSTRAINT ck_agent_dispatch_revision CHECK(binding_revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='受控服务内部冻结派单；无任意HTTP派单入口';
CREATE TABLE orbit_agent_profile_fence (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 agent_id CHAR(36) NOT NULL COMMENT '设备UUID',
 profile_external_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '区分大小写的Profile标识',
 fencing_token BIGINT NOT NULL DEFAULT 0 COMMENT '每次合法新租约单调递增，永不回退',
 PRIMARY KEY(tenant_id,agent_id,profile_external_id),
 FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id),
 CONSTRAINT ck_agent_profile_fence CHECK(fencing_token BETWEEN 0 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备Profile全历史防旧代际栅栏';
CREATE TABLE orbit_agent_execution_lease (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '租约UUID',
 dispatch_id CHAR(36) NOT NULL COMMENT '冻结派单UUID',
 agent_id CHAR(36) NOT NULL COMMENT '领取设备UUID',
 boot_id CHAR(36) NOT NULL COMMENT '领取时当前启动UUID',
 profile_external_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '真实独占Profile',
 attempt_id CHAR(36) NOT NULL COMMENT '本次不可混用的执行尝试UUID',
 fencing_token BIGINT NOT NULL COMMENT 'Profile全历史单调代际',
 command_received_at DATETIME(6) NULL COMMENT '指令首次领取确认UTC；重放与下一Profile分配分离',
 expires_at DATETIME(6) NOT NULL COMMENT '服务端租约截止UTC，默认120秒',
 created_at DATETIME(6) NOT NULL COMMENT '服务端领取UTC',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_agent_lease_dispatch(tenant_id,dispatch_id),
 KEY ix_agent_lease_active(tenant_id,agent_id,expires_at),
 FOREIGN KEY(tenant_id,dispatch_id) REFERENCES orbit_agent_dispatch(tenant_id,id),
 CONSTRAINT ck_agent_lease_expiry CHECK(expires_at>created_at),
 CONSTRAINT ck_agent_lease_fence CHECK(fencing_token BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实任务命令绑定租约，过期不自动重派';
ALTER TABLE orbit_agent_execution_lease ADD COLUMN last_sequence BIGINT NOT NULL DEFAULT 0 COMMENT '本租约已接收连续事件序号，不跨尝试共用';
CREATE TABLE orbit_agent_execution_event (
 tenant_id CHAR(36) NOT NULL COMMENT '可信证书租户UUID',
 event_id CHAR(36) NOT NULL COMMENT '本地持久事件UUID，重试保持不变',
 lease_id CHAR(36) NOT NULL COMMENT '原不可混用租约UUID',
 sequence_no BIGINT NOT NULL COMMENT '该租约连续事件序号',
 input_hash CHAR(64) NOT NULL COMMENT '规范事件全字段摘要，异内容重放拒绝',
 event_json JSON NOT NULL COMMENT '精确安全事件及证据引用，无凭据',
 historical BOOLEAN NOT NULL COMMENT '接收时是否仅历史记录，不授权新写',
 created_at DATETIME(6) NOT NULL COMMENT '真实服务端接收UTC',
 PRIMARY KEY(tenant_id,event_id),
 UNIQUE KEY uq_agent_execution_event_sequence(tenant_id,lease_id,sequence_no),
 FOREIGN KEY(tenant_id,lease_id) REFERENCES orbit_agent_execution_lease(tenant_id,id),
 CONSTRAINT ck_agent_execution_event_sequence CHECK(sequence_no BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备事件接收事实；成功状态仍须可信证据适配器';
CREATE TRIGGER guard_agent_execution_event_update BEFORE UPDATE ON orbit_agent_execution_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='AGENT_EXECUTION_EVENT_IMMUTABLE';
CREATE TRIGGER guard_agent_execution_event_delete BEFORE DELETE ON orbit_agent_execution_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='AGENT_EXECUTION_EVENT_IMMUTABLE';
