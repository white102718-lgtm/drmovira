-- Python组织目录事务基础；只由显式迁移工具执行，应用启动不得自动执行本文件。
-- 已有团队缺少原始时间，不回填伪造历史；后续新建/修改服务显式写UTC。
ALTER TABLE orbit_business_team
 ADD COLUMN created_at DATETIME(3) NULL COMMENT '创建UTC时刻；迁移前未采集的记录为NULL',
 ADD COLUMN updated_at DATETIME(3) NULL COMMENT '修改UTC时刻；迁移前未采集的记录为NULL',
 ADD KEY idx_business_team_state (tenant_id,enabled,id) COMMENT '租户及状态过滤后按业务UUID稳定续页';
ALTER TABLE orbit_business_user
 ADD KEY idx_business_user_native (user_id,tenant_id) COMMENT '原若依身份事件按数字用户ID定位关联租户';

CREATE TABLE orbit_directory_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '当前组织目录所属可信租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '用户、团队及角色目录变更版本；写事务递增',
 updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '目录变更UTC时刻',
 PRIMARY KEY (tenant_id),
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='组织目录版本及并发管理事务锁；不代表广告事实数据水位';
INSERT INTO orbit_directory_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_directory_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '本次单租户事务的可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '当前若依会话用户ID',
 request_key VARCHAR(128) NOT NULL COMMENT '客户端操作幂等键，区分大小写；不得放密码或Token',
 payload_hash CHAR(64) NOT NULL COMMENT '资源种类、目标、版本及无秘密业务DTO的规范摘要',
 response_json JSON NULL COMMENT '同事务的公开响应；不含密码或凭据',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '幂等记录创建UTC时刻',
 PRIMARY KEY (tenant_id,actor_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='组织目录写入幂等结果，与目录、版本及审计同事务';

CREATE TABLE orbit_directory_audit (
 id CHAR(36) NOT NULL COMMENT '不可变审计事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '对象所属可信租户UUID',
 resource_type VARCHAR(16) NOT NULL COMMENT '目录资源类型：USER、TEAM、ROLE',
 resource_id CHAR(36) NOT NULL COMMENT '稳定业务UUID，不使用名称猜测关联',
 action VARCHAR(20) NOT NULL COMMENT '实际动作：CREATE、UPDATE、INVITE等',
 revision BIGINT NOT NULL COMMENT '操作后业务版本',
 before_revision BIGINT NOT NULL COMMENT '操作前版本，新建为0',
 before_hash CHAR(64) NULL COMMENT '操作前公开业务状态摘要，新建为NULL；不保存密码',
 after_hash CHAR(64) NOT NULL COMMENT '操作后公开业务状态摘要，不含认证秘密',
 changed_fields_json JSON NOT NULL COMMENT '已变更字段名；不记录完整请求体或联系方式原值',
 actor_id BIGINT NOT NULL COMMENT '首次请求的真实若依会话用户ID',
 actor_subject_id CHAR(36) NOT NULL COMMENT '首次请求冻结的业务用户UUID',
 actor_team_id CHAR(36) NOT NULL COMMENT '首次请求冻结的业务团队UUID',
 request_id CHAR(36) NOT NULL COMMENT '服务端生成的首次请求关联UUID',
 created_at DATETIME(3) NOT NULL COMMENT '审计与业务提交的UTC时刻',
 PRIMARY KEY (id),
 UNIQUE KEY uk_directory_audit_version (tenant_id,resource_type,resource_id,revision)
   COMMENT '每个目录业务版本只追加一条审计',
 KEY idx_directory_audit_time (tenant_id,created_at,id) COMMENT '租户内时间及UUID稳定游标查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='人员团队角色只追加审计；应用不得覆盖历史';

CREATE TABLE orbit_directory_outbox (
 event_id CHAR(36) NOT NULL COMMENT '关联审计事件UUID，消费者按此去重',
 tenant_id CHAR(36) NOT NULL COMMENT '目录所属可信租户UUID',
 resource_type VARCHAR(16) NOT NULL COMMENT '资源类型：USER、TEAM、ROLE',
 resource_id CHAR(36) NOT NULL COMMENT '目录对象业务UUID',
 revision BIGINT NOT NULL COMMENT '产生事件的业务版本',
 created_at DATETIME(3) NOT NULL COMMENT '与业务同事务的UTC创建时刻',
 processed_at DATETIME(3) NULL COMMENT '消费者实际处理完成UTC时刻，未完成为NULL',
 PRIMARY KEY (event_id),
 KEY idx_directory_outbox_pending (tenant_id,processed_at,created_at,event_id)
   COMMENT '租户内未处理事件有界批量读取，不使用深OFFSET'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='组织目录事件事务outbox；尚未接入邀请或其他外部投递消费者';
