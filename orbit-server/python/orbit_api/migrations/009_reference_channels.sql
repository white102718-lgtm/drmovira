-- 最小引用资料和渠道闭环；不恢复产品、户商、总代完整CRUD，不改历史计划快照。
CREATE TABLE orbit_reference_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 revision BIGINT NOT NULL DEFAULT 0 COMMENT '全部引用资料原子导入的目录版本',
 channel_revision BIGINT NOT NULL DEFAULT 0 COMMENT '渠道任何写入后的列表水位',
 PRIMARY KEY (tenant_id),
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='租户引用资料和渠道写入短事务串行锁';
INSERT INTO orbit_reference_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_reference_record (
 tenant_id CHAR(36) NOT NULL COMMENT '资料所属可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '资料稳定业务UUID，沿用原始ID不按名称重建',
 kind VARCHAR(20) NOT NULL COMMENT 'PRODUCT、BUSINESS_AGENT或VENDOR',
 source_key VARCHAR(128) NOT NULL COMMENT '同租户及类别唯一来源键，不允许改绑业务UUID',
 name VARCHAR(255) NOT NULL COMMENT '当前资料名称；不回写历史快照',
 availability VARCHAR(16) NOT NULL COMMENT 'AVAILABLE允许新引用，UNAVAILABLE仅保留历史显示',
 owner_team_id CHAR(36) NOT NULL COMMENT '单一归属团队业务UUID',
 value_json JSON NOT NULL COMMENT '完整最小字段及有界拥有者集合，读取不从浏览器缓存恢复',
 revision BIGINT NOT NULL COMMENT '单条资料业务版本',
 catalog_revision BIGINT NOT NULL COMMENT '最近提交所在目录版本',
 updated_at DATETIME(3) NOT NULL COMMENT '资料修改UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_reference_source (tenant_id,kind,source_key) COMMENT '稳定来源键不得对应多个UUID',
 KEY idx_reference_kind (tenant_id,kind,id) COMMENT '类别内UUID键集分页',
 KEY idx_reference_team (tenant_id,kind,owner_team_id,id) COMMENT '团队范围及类别内有界分页',
 FOREIGN KEY (tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='最小产品总代户商资料，无硬删除';

CREATE TABLE orbit_reference_owner (
 tenant_id CHAR(36) NOT NULL COMMENT '资料所属可信租户UUID',
 reference_id CHAR(36) NOT NULL COMMENT '资料稳定UUID',
 user_id CHAR(36) NOT NULL COMMENT '同团队启用拥有者业务UUID',
 PRIMARY KEY (tenant_id,reference_id,user_id),
 KEY idx_reference_user (tenant_id,user_id,reference_id) COMMENT '普通用户按拥有者过滤，不扫描JSON',
 FOREIGN KEY (tenant_id,reference_id) REFERENCES orbit_reference_record(tenant_id,id),
 FOREIGN KEY (tenant_id,user_id) REFERENCES orbit_business_user(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用资料数据拥有者归属，不扩展功能权限';

CREATE TABLE orbit_reference_product_agent (
 tenant_id CHAR(36) NOT NULL COMMENT '产品与总代所属同一租户UUID',
 product_id CHAR(36) NOT NULL COMMENT 'PRODUCT资料UUID',
 agent_id CHAR(36) NOT NULL COMMENT 'BUSINESS_AGENT资料UUID',
 PRIMARY KEY (tenant_id,product_id,agent_id),
 KEY idx_reference_agent (tenant_id,agent_id,product_id) COMMENT '失效或归属修改时定位引用产品',
 FOREIGN KEY (tenant_id,product_id) REFERENCES orbit_reference_record(tenant_id,id),
 FOREIGN KEY (tenant_id,agent_id) REFERENCES orbit_reference_record(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='产品允许总代集合，保存渠道必须服务端复验';

CREATE TABLE orbit_reference_import (
 tenant_id CHAR(36) NOT NULL COMMENT '预览所属可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '导入预览UUID',
 actor_id BIGINT NOT NULL COMMENT '创建预览的原若依用户ID',
 team_ids_json JSON NOT NULL COMMENT '预览冻结的涉及团队集合，读取仍复验当前范围',
 input_json JSON NOT NULL COMMENT '最多500项、2MiB的受控导入业务输入',
 result_json JSON NOT NULL COMMENT '逐行问题、预计新增及更新数量，不代表已提交',
 state VARCHAR(16) NOT NULL COMMENT 'VALIDATED、REJECTED或COMMITTED；过期由读取计算',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '预览CAS版本，提交后递增',
 base_revision BIGINT NOT NULL COMMENT '预检依赖的原始目录版本',
 expires_at DATETIME(3) NOT NULL COMMENT '15分钟预览到期UTC时刻',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻',
 PRIMARY KEY (tenant_id,id),
 KEY idx_reference_import_expiry (tenant_id,expires_at,id) COMMENT '归档清理按到期游标有界读取'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用资料预检与原子提交状态；失败预检保留逐行问题';

CREATE TABLE orbit_channel (
 tenant_id CHAR(36) NOT NULL COMMENT '渠道所属可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '渠道稳定业务UUID',
 code VARCHAR(64) NOT NULL COMMENT '用户填写的渠道ID，同租户区分大小写唯一',
 name VARCHAR(100) NOT NULL COMMENT '渠道名称，可为空但不替代渠道ID',
 owner_team_id CHAR(36) NOT NULL COMMENT '渠道所属单一团队UUID',
 product_id CHAR(36) NOT NULL COMMENT '产品稳定引用UUID',
 agent_id CHAR(36) NOT NULL COMMENT '该产品允许的总代引用UUID',
 status VARCHAR(16) NOT NULL COMMENT 'ENABLED或DISABLED，停用保留历史',
 value_json JSON NOT NULL COMMENT '渠道类型媒体链接及完整归属，不保存目录名称快照冒充当前名称',
 product_locked TINYINT NOT NULL DEFAULT 0 COMMENT '历史马甲包约束产品不可修改，只能新建渠道',
 revision BIGINT NOT NULL COMMENT '渠道CAS业务版本',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻',
 updated_at DATETIME(3) NOT NULL COMMENT '修改UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_channel_code (tenant_id,code) COMMENT '同租户渠道ID唯一',
 KEY idx_channel_state (tenant_id,status,id) COMMENT '状态筛选和稳定UUID续页',
 KEY idx_channel_team (tenant_id,owner_team_id,id) COMMENT '团队范围键集分页',
 KEY idx_channel_product (tenant_id,product_id,id) COMMENT '产品筛选以及引用变更定位',
 FOREIGN KEY (tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 FOREIGN KEY (tenant_id,product_id) REFERENCES orbit_reference_record(tenant_id,id),
 FOREIGN KEY (tenant_id,agent_id) REFERENCES orbit_reference_record(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='渠道主数据，停用不硬删除，不覆写计划落地页';

CREATE TABLE orbit_channel_owner (
 tenant_id CHAR(36) NOT NULL COMMENT '渠道所属可信租户UUID',
 channel_id CHAR(36) NOT NULL COMMENT '渠道稳定UUID',
 user_id CHAR(36) NOT NULL COMMENT '同团队启用拥有者业务UUID',
 PRIMARY KEY (tenant_id,channel_id,user_id),
 KEY idx_channel_user (tenant_id,user_id,channel_id) COMMENT '普通用户按拥有者过滤渠道，不扫描JSON',
 FOREIGN KEY (tenant_id,channel_id) REFERENCES orbit_channel(tenant_id,id),
 FOREIGN KEY (tenant_id,user_id) REFERENCES orbit_business_user(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='渠道数据分配关系；分配不能提升功能角色权限';

CREATE TABLE orbit_reference_event (
 id CHAR(36) NOT NULL COMMENT '不可变事件及outbox去重UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 resource_type VARCHAR(24) NOT NULL COMMENT 'REFERENCE_IMPORT或CHANNEL',
 resource_id CHAR(36) NOT NULL COMMENT '导入预览或渠道UUID',
 revision BIGINT NOT NULL COMMENT '业务对象提交版本',
 actor_id BIGINT NOT NULL COMMENT '原若依操作人ID',
 request_id CHAR(36) NOT NULL COMMENT '服务端生成请求UUID',
 before_hash CHAR(64) NULL COMMENT '变更前规范业务hash，新建为空',
 after_hash CHAR(64) NOT NULL COMMENT '变更后规范业务hash',
 reason VARCHAR(1000) NOT NULL COMMENT '导入或分配及归档原因；常规保存记明确动作',
 details_json JSON NOT NULL COMMENT '来源键、目录版本及逐条前后hash等审计明细，不记录凭据',
 created_at DATETIME(3) NOT NULL COMMENT '与业务同事务UTC时刻',
 processed_at DATETIME(3) NULL COMMENT '消费者处理完成UTC时刻；NULL为待处理outbox',
 PRIMARY KEY (id),
 UNIQUE KEY uk_reference_event (tenant_id,resource_type,resource_id,revision) COMMENT '每业务版本唯一审计',
 KEY idx_reference_pending (tenant_id,processed_at,created_at,id) COMMENT '事件消费者有界读取及按事件UUID去重'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='业务只追加审计兼事务outbox，消费者不得修改审计内容';

CREATE TABLE orbit_reference_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '实际请求若依用户ID',
 request_key VARCHAR(128) NOT NULL COMMENT '16至128位ASCII幂等键',
 payload_hash CHAR(64) NOT NULL COMMENT '动作、对象、CAS版本及规范DTO摘要',
 response_json JSON NOT NULL COMMENT '与业务写入同事务保存的公开结果',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '创建UTC时刻',
 PRIMARY KEY (tenant_id,actor_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用资料与渠道专用幂等空间，提交前须重新授权';
