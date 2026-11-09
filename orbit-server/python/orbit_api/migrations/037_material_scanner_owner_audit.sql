-- 服务端显式扫描所有者的运维来源；无租户菜单或公开写入口，不接管已有进程。
CREATE TABLE orbit_scanner_owner_instance (
 profile_id VARCHAR(40) NOT NULL COMMENT '服务端固定扫描候选标识，不含连接地址',
 definition_revision BIGINT NOT NULL COMMENT '已批准所有者定义版本',
 instance_id CHAR(36) NOT NULL COMMENT '本轮显式启动随机实例UUID',
 source_sha256 CHAR(64) NOT NULL COMMENT '固定发行配置数据库来源摘要，不存路径原文',
 executable_sha256 CHAR(64) NOT NULL COMMENT '批准可执行文件摘要',
 config_sha256 CHAR(64) NOT NULL COMMENT '批准配置文件摘要',
 release_receipt_sha256 CHAR(64) NOT NULL COMMENT '服务端批准发行回执摘要，不冒充重新验签',
 state VARCHAR(16) NOT NULL COMMENT '实际审计阶段STARTING、STARTED、STOPPED或INVALIDATED',
 sequence_no INT NOT NULL COMMENT '本实例已提交事件顺序，从1递增，最多3',
 last_occurred_at DATETIME(6) NOT NULL COMMENT '本实例最近事件发生UTC时间，禁止时间倒退',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '首次登记UTC时间',
 PRIMARY KEY(profile_id,definition_revision,instance_id),
 UNIQUE KEY uq_scanner_owner_instance_uuid(instance_id) COMMENT '启动UUID全局唯一，禁止跨候选借用同一实例',
 KEY idx_scanner_owner_instance_time(created_at,profile_id,definition_revision,instance_id)
 COMMENT '全局运维实例按UTC与唯一键有界续页',
 CONSTRAINT ck_scanner_owner_definition CHECK(definition_revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_scanner_owner_stage CHECK((state='STARTING' AND sequence_no=1)
 OR (state='STARTED' AND sequence_no=2)
 OR (state IN ('STOPPED','INVALIDATED') AND sequence_no=3))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
COMMENT='显式扫描所有者运维实例；只更新阶段，不覆盖批准来源';

CREATE TABLE orbit_scanner_owner_audit (
 event_id CHAR(36) NOT NULL COMMENT '调用方固定事件UUID，精确重试去重',
 profile_id VARCHAR(40) NOT NULL COMMENT '可信扫描候选标识',
 definition_revision BIGINT NOT NULL COMMENT '绑定同轮批准定义版本',
 instance_id CHAR(36) NOT NULL COMMENT '绑定同轮启动实例UUID',
 sequence_no INT NOT NULL COMMENT '实例内严格事件顺序',
 action VARCHAR(16) NOT NULL COMMENT '实际STARTING、STARTED、STOPPED或INVALIDATED动作',
 source_sha256 CHAR(64) NOT NULL COMMENT '本事件不可变来源摘要',
 executable_sha256 CHAR(64) NOT NULL COMMENT '本事件批准程序摘要',
 config_sha256 CHAR(64) NOT NULL COMMENT '本事件批准配置摘要',
 release_receipt_sha256 CHAR(64) NOT NULL COMMENT '本事件发行批准回执摘要',
 payload_sha256 CHAR(64) NOT NULL COMMENT '十个安全输入字段规范化摘要，用于重放一致性',
 occurred_at DATETIME(6) NOT NULL COMMENT '所有者提供的实际发生UTC时间，保留微秒',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '事务登记UTC时间',
 PRIMARY KEY(event_id),
 UNIQUE KEY uq_scanner_owner_action(profile_id,definition_revision,instance_id,action)
 COMMENT '同实例同动作仅一条，不用不同事件ID覆盖原动作',
 UNIQUE KEY uq_scanner_owner_sequence(profile_id,definition_revision,instance_id,sequence_no)
 COMMENT '实例内顺序读取与并发去重',
 KEY idx_scanner_owner_audit_time(created_at,event_id) COMMENT '全局安全审计有界续页',
 CONSTRAINT fk_scanner_owner_audit_instance FOREIGN KEY(profile_id,definition_revision,instance_id)
 REFERENCES orbit_scanner_owner_instance(profile_id,definition_revision,instance_id),
 CONSTRAINT ck_scanner_owner_audit_stage CHECK((action='STARTING' AND sequence_no=1)
 OR (action='STARTED' AND sequence_no=2)
 OR (action IN ('STOPPED','INVALIDATED') AND sequence_no=3))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
COMMENT='服务端扫描运维只追加安全审计；不含PID端口路径凭据或原配置';

CREATE TABLE orbit_scanner_owner_outbox (
 event_id CHAR(36) NOT NULL COMMENT '与审计同一个事件UUID，消费者据此去重',
 created_at DATETIME(6) NOT NULL DEFAULT (UTC_TIMESTAMP(6)) COMMENT '同事务入箱UTC时间',
 processed_at DATETIME(6) NULL COMMENT '未来消费者实际完成UTC时间，未投递保持NULL',
 PRIMARY KEY(event_id),
 KEY idx_scanner_owner_outbox_pending(processed_at,created_at,event_id)
 COMMENT '未处理事件按时间及UUID有界续页，禁止深OFFSET',
 CONSTRAINT fk_scanner_owner_outbox_audit FOREIGN KEY(event_id)
 REFERENCES orbit_scanner_owner_audit(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
COMMENT='全局扫描运维事务outbox；无外部投递成功占位';
