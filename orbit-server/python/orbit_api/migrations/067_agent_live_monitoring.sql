-- 067候选：真实mTLS设备监测；不签发广告写权限、浏览器凭据或租约。
CREATE TABLE orbit_agent_certificate (
 fingerprint_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '真实DER证书SHA256',
 tenant_id CHAR(36) NOT NULL COMMENT '证书SAN绑定租户', agent_id CHAR(36) NOT NULL COMMENT '证书CN绑定设备',
 not_before DATETIME(6) NOT NULL COMMENT '证书UTC生效', not_after DATETIME(6) NOT NULL COMMENT '证书UTC到期',
 revoked_at DATETIME(6) NULL COMMENT '运维撤销UTC时刻', created_at DATETIME(6) NOT NULL COMMENT '注册UTC时间',
 PRIMARY KEY(fingerprint_sha256), KEY ix_agent_certificate(tenant_id,agent_id),
 FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id),
 CHECK(not_after>not_before)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='受控运维登记设备叶证书；无私钥';
CREATE TABLE orbit_agent_monitor_head (
 tenant_id CHAR(36) NOT NULL COMMENT '租户', agent_id CHAR(36) NOT NULL COMMENT '设备',
 boot_id CHAR(36) NOT NULL COMMENT '当前启动UUID', last_seq BIGINT NOT NULL COMMENT '最新已接收序号',
 recovery_streak INT NOT NULL COMMENT '连续新seq恢复计数1至2', revision BIGINT NOT NULL COMMENT '监测独立CAS水位',
 received_at DATETIME(6) NOT NULL COMMENT '心跳服务端接收UTC时刻',
 diagnostic_seq BIGINT NULL COMMENT '当前诊断所属已接收seq', diagnostic_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '诊断幂等摘要',
 diagnostic_json JSON NULL COMMENT '精确安全诊断DTO', diagnostic_ack JSON NULL COMMENT '诊断原回执',
 diagnostic_received_at DATETIME(6) NULL COMMENT '诊断服务端接收UTC时刻',
 PRIMARY KEY(tenant_id,agent_id),FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id),
 CHECK(last_seq BETWEEN 1 AND 9007199254740991),CHECK(revision BETWEEN 1 AND 9007199254740991),CHECK(recovery_streak BETWEEN 1 AND 2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备当前启动和监测状态，不改变设备登记revision';
CREATE TABLE orbit_agent_boot (
 tenant_id CHAR(36) NOT NULL COMMENT '租户',agent_id CHAR(36) NOT NULL COMMENT '设备',boot_id CHAR(36) NOT NULL COMMENT '启动UUID',
 created_at DATETIME(6) NOT NULL COMMENT '首心跳接收UTC时刻',retired_at DATETIME(6) NULL COMMENT '退役UTC时刻，永久拒绝该boot',
 PRIMARY KEY(tenant_id,agent_id,boot_id),FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备启动永久账本';
CREATE TABLE orbit_agent_heartbeat_receipt (
 tenant_id CHAR(36) NOT NULL COMMENT '租户',agent_id CHAR(36) NOT NULL COMMENT '设备',boot_id CHAR(36) NOT NULL COMMENT '启动UUID',seq BIGINT NOT NULL COMMENT '原心跳序号',
 payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '规范原请求摘要',ack_json JSON NOT NULL COMMENT '原Ack',received_at DATETIME(6) NOT NULL COMMENT '首次接收UTC时刻',
 PRIMARY KEY(tenant_id,agent_id,boot_id,seq),FOREIGN KEY(tenant_id,agent_id,boot_id) REFERENCES orbit_agent_boot(tenant_id,agent_id,boot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='心跳去重回执；重复不刷新在线时间';
CREATE TABLE orbit_agent_profile_observation (
 tenant_id CHAR(36) NOT NULL COMMENT '租户',agent_id CHAR(36) NOT NULL COMMENT '设备',id CHAR(36) NOT NULL COMMENT '设备和Profile稳定uuid5',
 external_profile_id VARCHAR(128) COLLATE utf8mb4_bin NOT NULL COMMENT '设备本地Profile标识',boot_id CHAR(36) NOT NULL COMMENT '观察所属boot',
 seq BIGINT NOT NULL COMMENT '观察所属心跳seq',process_state VARCHAR(16) NOT NULL COMMENT 'ACTIVE/INACTIVE/UNKNOWN，非登录证明',
 observed_at DATETIME(6) NOT NULL COMMENT '客户端观察UTC证据时刻',received_at DATETIME(6) NOT NULL COMMENT '服务端接收UTC时刻',
 PRIMARY KEY(tenant_id,agent_id,external_profile_id),UNIQUE KEY uq_agent_profile_uuid(tenant_id,agent_id,id),
 FOREIGN KEY(tenant_id,agent_id,boot_id,seq) REFERENCES orbit_agent_heartbeat_receipt(tenant_id,agent_id,boot_id,seq),
 CHECK(process_state IN('ACTIVE','INACTIVE','UNKNOWN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='最近已观察Profile；不是完整库存声明';
CREATE TABLE orbit_agent_identity_report (
 tenant_id CHAR(36) NOT NULL COMMENT '租户',agent_id CHAR(36) NOT NULL COMMENT '设备',event_id CHAR(36) NOT NULL COMMENT '本机持久事件UUID',
 boot_id CHAR(36) NOT NULL COMMENT '当前启动',seq BIGINT NOT NULL COMMENT '已接受心跳序号',binding_id CHAR(36) NOT NULL COMMENT '当前绑定',binding_revision BIGINT NOT NULL COMMENT '精确绑定版本',
 profile_external_id VARCHAR(128) COLLATE utf8mb4_bin NOT NULL COMMENT 'Profile标识',external_account_id VARCHAR(64) NULL COMMENT '实际观察平台账户ID，不由期望值回填',currency CHAR(3) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '实际观察币种',
 identity_state VARCHAR(24) NOT NULL COMMENT 'VALID/LOGIN_REQUIRED/CHALLENGE/IDENTITY_MISMATCH/UNKNOWN',adapter_version VARCHAR(64) NOT NULL COMMENT '服务端允许的只读适配器版本',
 evidence_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '本机安全观察摘要，不存DOM/Cookie/Token',fingerprint_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际连接叶证书指纹',
 observed_at DATETIME(6) NOT NULL COMMENT '观察UTC时刻',received_at DATETIME(6) NOT NULL COMMENT '服务端UTC接收时刻',payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '事件规范请求摘要',ack_json JSON NOT NULL COMMENT '原Ack',
 PRIMARY KEY(tenant_id,agent_id,event_id),KEY ix_agent_identity_binding(tenant_id,binding_id,received_at,event_id),
 FOREIGN KEY(tenant_id,binding_id) REFERENCES orbit_profile_binding(tenant_id,id),
 FOREIGN KEY(tenant_id,agent_id,boot_id,seq) REFERENCES orbit_agent_heartbeat_receipt(tenant_id,agent_id,boot_id,seq),
 FOREIGN KEY(fingerprint_sha256) REFERENCES orbit_agent_certificate(fingerprint_sha256),
 CHECK(identity_state IN('VALID','LOGIN_REQUIRED','CHALLENGE','IDENTITY_MISMATCH','UNKNOWN')),
 CHECK(identity_state<>'VALID' OR (external_account_id IS NOT NULL AND currency IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='有界只读身份报告；不授予广告发送能力';
CREATE TABLE orbit_agent_identity_head (
 tenant_id CHAR(36) NOT NULL COMMENT '租户',binding_id CHAR(36) NOT NULL COMMENT '绑定UUID',agent_id CHAR(36) NOT NULL COMMENT '报告设备',event_id CHAR(36) NOT NULL COMMENT '最近接受报告，避免同微秒排序猜测',
 PRIMARY KEY(tenant_id,binding_id),FOREIGN KEY(tenant_id,binding_id) REFERENCES orbit_profile_binding(tenant_id,id),
 FOREIGN KEY(tenant_id,agent_id,event_id) REFERENCES orbit_agent_identity_report(tenant_id,agent_id,event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='绑定最新身份报告精确指针';
