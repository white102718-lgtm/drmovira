-- 最小引用目录，不恢复产品、总代、户商独立CRUD；所有业务变更经预览原子提交。
CREATE TABLE IF NOT EXISTS orbit_reference_catalog_version (
 tenant_id CHAR(36) NOT NULL COMMENT '服务端可信租户UUID',
 revision BIGINT NOT NULL DEFAULT 0 COMMENT '当前目录版本，整批提交递增一次',
 PRIMARY KEY(tenant_id), CHECK(revision BETWEEN 0 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='租户引用目录并发时钟';
INSERT IGNORE INTO orbit_reference_catalog_version(tenant_id) SELECT id FROM orbit_tenant;
CREATE TRIGGER IF NOT EXISTS orbit_reference_tenant_i AFTER INSERT ON orbit_tenant FOR EACH ROW
 INSERT IGNORE INTO orbit_reference_catalog_version(tenant_id) VALUES(NEW.id);

CREATE TABLE IF NOT EXISTS orbit_reference_record (
 id CHAR(36) NOT NULL COMMENT '保留的原引用UUID，禁止跨租户重用覆盖',
 tenant_id CHAR(36) NOT NULL COMMENT '所属可信租户UUID',
 kind VARCHAR(24) NOT NULL COMMENT 'PRODUCT产品、BUSINESS_AGENT总代、VENDOR户商',
 source_key VARCHAR(128) NOT NULL COMMENT '同租户同类型稳定来源键，不按名称匹配',
 owner_team_id CHAR(36) NOT NULL COMMENT '单一归属团队UUID',
 availability VARCHAR(16) NOT NULL COMMENT 'AVAILABLE允许新增引用，UNAVAILABLE仅保留历史解释',
 value_json LONGTEXT NOT NULL COMMENT '规范化ReferenceInput，包含当前名称及共享拥有者',
 value_hash CHAR(64) NOT NULL COMMENT '规范正文SHA256，审计仅记录摘要',
 revision BIGINT NOT NULL COMMENT '该记录每次成功更新递增的版本',
 catalog_revision BIGINT NOT NULL COMMENT '最近更新所属目录版本',
 updated_at DATETIME(3) NOT NULL COMMENT '最近更新UTC时刻',
 PRIMARY KEY(id), UNIQUE KEY reference_source(tenant_id,kind,source_key),
 KEY reference_tenant_kind(tenant_id,kind,id), CHECK(JSON_VALID(value_json)),
 CHECK(revision BETWEEN 1 AND 9007199254740991), CHECK(catalog_revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='保留稳定UUID的最小引用资料，无硬删除接口';
CREATE TABLE IF NOT EXISTS orbit_reference_product_agent (
 tenant_id CHAR(36) NOT NULL COMMENT '所属租户UUID',
 product_id CHAR(36) NOT NULL COMMENT '产品稳定引用UUID',
 agent_id CHAR(36) NOT NULL COMMENT '允许关联的总代稳定引用UUID',
 PRIMARY KEY(tenant_id,product_id,agent_id),
 FOREIGN KEY(product_id) REFERENCES orbit_reference_record(id),
 FOREIGN KEY(agent_id) REFERENCES orbit_reference_record(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='产品与总代白名单，同租户同团队及当前可见性由事务复验';
CREATE TABLE IF NOT EXISTS orbit_reference_import (
 id CHAR(36) NOT NULL COMMENT '导入预览UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '所属可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '创建预览的若依用户ID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '预览版本，成功提交加一',
 state VARCHAR(16) NOT NULL COMMENT 'VALIDATED、REJECTED或COMMITTED；过期读取投影EXPIRED',
 base_catalog_revision BIGINT NOT NULL COMMENT '预检针对的目录版本',
 body_json LONGTEXT NOT NULL COMMENT '规范完整导入正文，仅授权维护读取内部使用',
 body_hash CHAR(64) NOT NULL COMMENT '规范导入正文SHA256',
 issues_json LONGTEXT NOT NULL COMMENT '从0开始的逐行错误数组，不回显不可见对象名称',
 created_count INT NOT NULL COMMENT '预检预计新增数量',
 updated_count INT NOT NULL COMMENT '预检预计更新数量',
 expires_at DATETIME(3) NOT NULL COMMENT '数据库UTC时间起15分钟过期',
 created_at DATETIME(3) NOT NULL COMMENT '数据库UTC创建时刻',
 PRIMARY KEY(tenant_id,id), CHECK(JSON_VALID(body_json)), CHECK(JSON_VALID(issues_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用目录预览，预览不修改实际目录';
CREATE TABLE IF NOT EXISTS orbit_reference_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '当前若依操作用户ID',
 idem_key CHAR(36) NOT NULL COMMENT '调用方幂等UUID，预览及提交共享键空间',
 request_hash CHAR(64) NOT NULL COMMENT '动作、预览ID、期望版本及正文指纹',
 import_id CHAR(36) NULL COMMENT '首次成功返回的预览UUID',
 response_json LONGTEXT NULL COMMENT '首次成功的不可变合同结果，当前权限仍须复核',
 PRIMARY KEY(tenant_id,actor_id,idem_key), CHECK(response_json IS NULL OR JSON_VALID(response_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用导入幂等响应，与业务事务一起提交或回滚';
CREATE TABLE IF NOT EXISTS orbit_reference_event (
 id CHAR(36) NOT NULL COMMENT '服务端审计及outbox共用事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '目标租户UUID',
 import_id CHAR(36) NOT NULL COMMENT '提交的预览UUID',
 actor_id BIGINT NOT NULL COMMENT '若依操作用户ID',
 actor_subject_id CHAR(36) NOT NULL COMMENT '当前可信业务操作者UUID',
 request_id CHAR(36) NULL COMMENT '真实请求UUID，内部调用未知时不伪造',
 action_code VARCHAR(64) NOT NULL COMMENT 'REFERENCE_IMPORT_COMMITTED',
 source VARCHAR(255) NOT NULL COMMENT '规范化导入来源',
 reason VARCHAR(1000) NOT NULL COMMENT '规范化提交原因',
 before_catalog_revision BIGINT NOT NULL COMMENT '提交前目录版本',
 after_catalog_revision BIGINT NOT NULL COMMENT '提交后目录版本',
 changes_json LONGTEXT NOT NULL COMMENT '逐记录ID及前后SHA256，不含完整原始正文',
 created_at DATETIME(3) NOT NULL COMMENT '审计UTC时刻',
 PRIMARY KEY(id), UNIQUE KEY reference_event_import(tenant_id,import_id), CHECK(JSON_VALID(changes_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用导入审计，任何写入失败回滚整批';
CREATE TABLE IF NOT EXISTS orbit_reference_outbox (
 event_id CHAR(36) NOT NULL COMMENT '事件UUID，消费者以此幂等去重',
 tenant_id CHAR(36) NOT NULL COMMENT '可信目标租户UUID',
 import_id CHAR(36) NOT NULL COMMENT '提交的预览UUID',
 catalog_revision BIGINT NOT NULL COMMENT '本次提交的目录版本',
 created_at DATETIME(3) NOT NULL COMMENT '同事务数据库UTC时刻',
 PRIMARY KEY(event_id), FOREIGN KEY(event_id) REFERENCES orbit_reference_event(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='引用目录变更outbox，只追加；当前不执行外部广告操作';
