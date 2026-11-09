-- 066：设备登记与未验证账户/Profile关联；不发行证书、不标记心跳在线或平台身份有效。
CREATE TABLE orbit_execution_agent_clock (
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '设备和绑定共享目录水位',
 PRIMARY KEY (tenant_id),
 CONSTRAINT fk_environment_clock_tenant FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CONSTRAINT ck_execution_agent_clock CHECK(revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB COMMENT='执行机及Profile绑定事务水位';

CREATE TABLE orbit_execution_agent (
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '设备登记UUID，运维证书须绑定此ID',
 name VARCHAR(80) NOT NULL COMMENT '机器名称',
 endpoint VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '仅执行机本地读取的Local API地址，云端不连接',
 probe_interval INT NOT NULL COMMENT '计划探测周期秒，非已启动任务',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '设备CAS版本',
 state VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'OFFLINE' COMMENT 'READY/SUSPECT/OFFLINE/REVOKED；登记初始OFFLINE',
 last_heartbeat DATETIME(6) NULL COMMENT '可信心跳服务端接收UTC时刻；未接通为NULL',
 created_at DATETIME(6) NOT NULL COMMENT '登记UTC时刻，按北京时间日界筛选',
 updated_at DATETIME(6) NOT NULL COMMENT '最后变更UTC时刻',
 PRIMARY KEY(tenant_id,id),
 KEY ix_execution_agent_created(tenant_id,created_at,id),
 KEY ix_execution_agent_state(tenant_id,state,id),
 CONSTRAINT fk_execution_agent_tenant FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CONSTRAINT ck_execution_agent_revision CHECK(revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_execution_agent_probe CHECK(probe_interval BETWEEN 10 AND 300),
 CONSTRAINT ck_execution_agent_state CHECK(state IN('READY','SUSPECT','OFFLINE','REVOKED')),
 CONSTRAINT ck_execution_agent_live CHECK(state NOT IN('READY','SUSPECT') OR last_heartbeat IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='超级管理员统一登记的执行机器，不存密钥或证书私钥';

CREATE TABLE orbit_profile_binding (
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '绑定UUID',
 account_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '内部广告账户UUID',
 agent_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '执行机登记UUID',
 profile_external_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '执行机本地Profile标识，区分大小写',
 owner_user_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '绑定时冻结账户投手UUID',
 owner_team_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '绑定时冻结账户团队UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '绑定CAS版本',
 identity_state VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'UNKNOWN' COMMENT '身份状态；人工登记不验证身份',
 verified_at DATETIME(6) NULL COMMENT '可信身份核验UTC时间；登记为NULL',
 unbound_at DATETIME(6) NULL COMMENT '解绑UTC时间；非空关联失效',
 active_key TINYINT GENERATED ALWAYS AS (IF(unbound_at IS NULL,1,NULL)) STORED COMMENT '仅有效关联参与唯一性',
 created_at DATETIME(6) NOT NULL COMMENT '创建UTC时刻',
 updated_at DATETIME(6) NOT NULL COMMENT '变更UTC时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_profile_binding_active(tenant_id,agent_id,profile_external_id,account_id,active_key),
 KEY ix_profile_binding_account(tenant_id,account_id,id),
 KEY ix_profile_binding_agent(tenant_id,agent_id,id),
 CONSTRAINT fk_profile_binding_agent FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id),
 CONSTRAINT fk_profile_binding_account FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 CONSTRAINT ck_profile_binding_revision CHECK(revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_profile_binding_identity CHECK(identity_state IN('VALID','LOGIN_REQUIRED','CHALLENGE','IDENTITY_MISMATCH','UNKNOWN')),
 CONSTRAINT ck_profile_binding_verified CHECK((identity_state<>'VALID' OR verified_at IS NOT NULL) AND (identity_state<>'UNKNOWN' OR verified_at IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户与执行机Profile显式关联；绑定不授予登录或执行能力';

CREATE TABLE orbit_execution_agent_idempotency (
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 actor_id BIGINT NOT NULL COMMENT '原生用户ID',
 operation VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '设备或绑定操作类型',
 key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原幂等键SHA256',
 input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原规范请求SHA256',
 result_json JSON NOT NULL COMMENT '原成功回执，不含凭据',
 created_at DATETIME(6) NOT NULL COMMENT '受理UTC时刻',
 PRIMARY KEY(tenant_id,actor_id,operation,key_hash)
) ENGINE=InnoDB COMMENT='设备和绑定同事务成功幂等回执';

CREATE TABLE orbit_execution_agent_event (
 id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '事件UUID',
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 resource_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'EXECUTION_AGENT或PROFILE_BINDING',
 resource_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '设备或绑定UUID',
 revision BIGINT NOT NULL COMMENT '变更后CAS版本',
 actor_id BIGINT NOT NULL COMMENT '原生操作者ID',
 request_id VARCHAR(128) NOT NULL COMMENT '安全请求关联标识',
 action VARCHAR(64) NOT NULL COMMENT '实际操作类型',
 details_json JSON NOT NULL COMMENT '安全审计说明及变化哈希，不含Key或Cookie',
 created_at DATETIME(6) NOT NULL COMMENT '发生UTC时刻',
 PRIMARY KEY(id), UNIQUE KEY uq_execution_agent_event_tenant(tenant_id,id),
 KEY ix_execution_agent_event_resource(tenant_id,resource_type,resource_id,revision),
 CONSTRAINT ck_environment_event_revision CHECK(revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_environment_event_type CHECK(resource_type IN('EXECUTION_AGENT','PROFILE_BINDING')),
 CONSTRAINT ck_environment_event_action CHECK(CHAR_LENGTH(action) BETWEEN 1 AND 64),
 CONSTRAINT fk_environment_event_tenant FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备和绑定不可变更业务审计';

CREATE TABLE orbit_execution_agent_outbox (
 event_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '同事务审计事件UUID',
 tenant_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '租户UUID',
 resource_type VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '设备或绑定类型',
 resource_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs NOT NULL COMMENT '设备或绑定UUID',
 created_at DATETIME(6) NOT NULL COMMENT '入队UTC时刻',
 PRIMARY KEY(event_id),KEY ix_execution_agent_outbox_tenant(tenant_id,created_at,event_id),
 CONSTRAINT ck_environment_outbox_type CHECK(resource_type IN('EXECUTION_AGENT','PROFILE_BINDING')),
 CONSTRAINT fk_environment_outbox_event FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_execution_agent_event(tenant_id,id)
) ENGINE=InnoDB COMMENT='设备和绑定审计事务outbox；不是执行机命令或证书签发';

INSERT INTO orbit_execution_agent_clock(tenant_id,revision) SELECT id,1 FROM orbit_tenant;

CREATE TRIGGER orbit_execution_agent_event_no_update BEFORE UPDATE ON orbit_execution_agent_event FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='environment audit is immutable'; END;
CREATE TRIGGER orbit_execution_agent_event_no_delete BEFORE DELETE ON orbit_execution_agent_event FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='environment audit is immutable'; END;
CREATE TRIGGER orbit_execution_agent_receipt_no_update BEFORE UPDATE ON orbit_execution_agent_idempotency FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='environment receipt is immutable'; END;
CREATE TRIGGER orbit_execution_agent_receipt_no_delete BEFORE DELETE ON orbit_execution_agent_idempotency FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='environment receipt is immutable'; END;

-- 设备由超管统一管理；只编译已有菜单和动作，不给旧角色附送权限。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(31060,'AdsPower监测',31000,6,'environments','orbit/environments/index',1,1,'C','0','0','','monitor','admin',NOW(),'设备统一管理及当前账户环境；登记不代表已验证'),
(31061,'查看账户环境',31060,1,'#','',1,1,'F','0','0','environments.read','#','admin',NOW(),'仅当前账户范围'),
(31062,'登记设备与绑定',31060,2,'#','',1,1,'F','0','0','environments.enroll','#','admin',NOW(),'服务端另校验超级管理员'),
(31063,'撤销设备',31060,3,'#','',1,1,'F','0','0','environments.revoke','#','admin',NOW(),'服务端另校验超级管理员'),
(31064,'探测设备',31060,4,'#','',1,1,'F','0','0','environments.probe','#','admin',NOW(),'可信执行机链路未接通时明确不可用');
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,31060 FROM orbit_business_role br
 JOIN orbit_business_role_menu m ON m.tenant_id=br.tenant_id AND m.role_id=br.id
 WHERE m.menu_code='environments' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
 WHERE rm.role_id=br.native_role_id AND rm.menu_id=31060);
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,m.menu_id FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 JOIN sys_menu m ON m.perms=a.permission_code AND m.parent_id=31060
 WHERE NOT EXISTS(SELECT 1 FROM sys_role_menu rm
 WHERE rm.role_id=br.native_role_id AND rm.menu_id=m.menu_id);
