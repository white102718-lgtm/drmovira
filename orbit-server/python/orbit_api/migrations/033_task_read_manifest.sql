-- 原Task独立持久读模型；不开放生产execute，不自动启动任何发送Worker。
CREATE TABLE orbit_task_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '任务可信租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '完整发布或实际状态迁移列表水位',
 PRIMARY KEY(tenant_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='任务列表版本，不作为权限缓存';
INSERT INTO orbit_task_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_task (
 tenant_id CHAR(36) NOT NULL COMMENT '来源计划可信租户',
 id CHAR(36) NOT NULL COMMENT '真实任务UUID，不复用账户/命令/request UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '实际任务状态与事件版本',
 owner_user_id CHAR(36) NOT NULL COMMENT '真实计划版本冻结拥有者，不是Worker',
 owner_team_id CHAR(36) NOT NULL COMMENT '真实计划版本冻结团队',
 source_plan_id CHAR(36) NOT NULL COMMENT 'T1仅支持实际存在的PLAN来源',
 source_revision BIGINT NOT NULL COMMENT '来源不可变计划版本',
 source_hash CHAR(64) NOT NULL COMMENT '来源实际规范payload摘要，不是预检授权hash',
 execution_mode VARCHAR(16) NOT NULL COMMENT '真实计划META_API或ADSPOWER_UI',
 state VARCHAR(20) NOT NULL DEFAULT 'QUEUED' COMMENT '原Task状态枚举；BUILDING不作为Task状态',
 manifest_phase VARCHAR(16) NOT NULL DEFAULT 'BUILDING' COMMENT '内部BUILDING/COMPLETE，未完整不公开/不发送',
 producer_kind VARCHAR(16) NOT NULL COMMENT 'T1仅隔离库ISOLATED_TEST，生产provider缺失503',
 graph_hash CHAR(64) NOT NULL COMMENT '实际完整拓扑摘要',
 manifest_hash CHAR(64) NOT NULL COMMENT '有序块ordinal/count/hash摘要',
 expected_node_count INT UNSIGNED NOT NULL COMMENT '完整真实节点数量1至100000',
 expected_chunk_count INT UNSIGNED NOT NULL COMMENT '每块最多500真实节点',
 node_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已持久节点实际总数，COMPLETE后等于预期',
 edge_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '实际父边总数',
 needs_manual_reconciliation BOOLEAN NOT NULL DEFAULT 0 COMMENT '只由真实UNKNOWN对账流程推进',
 latest_event_id CHAR(36) NULL COMMENT '最新实际提交事件UUID',
 latest_sequence BIGINT NOT NULL DEFAULT 0 COMMENT '每任务持久事件递增序号',
 accepted_request_id CHAR(36) NOT NULL COMMENT '原构建关联请求，不作为读取凭据',
 created_by BIGINT NOT NULL COMMENT '真实构建操作者原生ID',
 created_at DATETIME(3) NOT NULL COMMENT '真实持久构建UTC',
 updated_at DATETIME(3) NOT NULL COMMENT '实际完整发布/状态变化UTC',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uk_task_plan_revision(tenant_id,source_plan_id,source_revision),
 KEY idx_task_owner(tenant_id,owner_user_id,manifest_phase,created_at,id),
 KEY idx_task_team(tenant_id,owner_team_id,manifest_phase,created_at,id),
 KEY idx_task_state(tenant_id,manifest_phase,state,created_at,id),
 FOREIGN KEY(tenant_id,source_plan_id,source_revision)
 REFERENCES orbit_launch_plan_version(tenant_id,plan_id,revision),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CONSTRAINT ck_task_count CHECK(expected_node_count BETWEEN 1 AND 100000),
 CONSTRAINT ck_task_revision CHECK(revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_task_state CHECK(state IN('QUEUED','RUNNING','VERIFYING','UNKNOWN','RETRY_WAIT',
 'SUCCEEDED','PARTIAL_SUCCESS','FAILED','CANCELLED','NEEDS_HUMAN')),
 CONSTRAINT ck_task_phase CHECK(manifest_phase IN('BUILDING','COMPLETE')),
 CONSTRAINT ck_task_mode CHECK(execution_mode IN('META_API','ADSPOWER_UI')),
 CONSTRAINT ck_task_producer CHECK(producer_kind='ISOLATED_TEST')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原Task完整持久核心；无平台执行授权';

CREATE TABLE orbit_task_chunk (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实Task UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '连续块序号从0开始',
 expected_count INT UNSIGNED NOT NULL COMMENT '块真实节点数1至500',
 expected_hash CHAR(64) NOT NULL COMMENT '开始构建时冻结的规范块摘要',
 persisted BOOLEAN NOT NULL DEFAULT 0 COMMENT '节点与父边整块成功后置真',
 PRIMARY KEY(tenant_id,task_id,ordinal),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id),
 CONSTRAINT ck_task_chunk_count CHECK(expected_count BETWEEN 1 AND 500)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='后台有界事务块；缺块不能发布';

CREATE TABLE orbit_task_node (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '所属真实Task',
 id CHAR(36) NOT NULL COMMENT '按Task namespace和稳定node_key生成UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '稳定拓扑序号从0开始',
 node_key VARCHAR(512) NOT NULL COMMENT '原真实DAG稳定节点键',
 kind VARCHAR(16) NOT NULL COMMENT '原TaskNode八种节点类别',
 state VARCHAR(24) NOT NULL DEFAULT 'QUEUED' COMMENT '原TaskNode状态，不推测平台成功',
 initial_json JSON NOT NULL COMMENT '原真实DagNode冻结结构，不含Token/平台响应',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '真实平台ID，未发为NULL',
 attempt INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '真实执行尝试，未发为0',
 error_code VARCHAR(64) NULL COMMENT '受控错误分类',
 error_message VARCHAR(1000) NULL COMMENT '受控脱敏中文分类，不存原异常',
 retryable BOOLEAN NOT NULL DEFAULT 0 COMMENT '仅证据确定安全失败可重试',
 configuration_state VARCHAR(16) NOT NULL DEFAULT 'UNVERIFIED' COMMENT '配置核验，不等于投放状态',
 delivery_state VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN' COMMENT '真实投放状态，未观察为UNKNOWN',
 updated_at DATETIME(3) NOT NULL COMMENT '实际持久UTC',
 PRIMARY KEY(tenant_id,task_id,id),
 UNIQUE KEY uk_task_node_key(tenant_id,task_id,node_key),
 UNIQUE KEY uk_task_node_ordinal(tenant_id,task_id,ordinal),
 KEY idx_task_node_state(tenant_id,task_id,state,ordinal),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id),
 CONSTRAINT ck_task_node_kind CHECK(kind IN('UPLOAD','CAMPAIGN','ADSET','CREATIVE','AD','VERIFY','ENABLE','ALLOCATION')),
 CONSTRAINT ck_task_node_state CHECK(state IN('DRAFT','VALIDATED','QUEUED','RUNNING','ACCEPTED',
 'VERIFYING','SUCCEEDED','FAILED','UNKNOWN','RETRY_WAIT','CANCELLED','EXPIRED','BLOCKED_AUTH',
 'BLOCKED_DEPENDENCY','NEEDS_HUMAN')),
 CONSTRAINT ck_task_configuration CHECK(configuration_state IN('UNVERIFIED','VERIFIED','MISMATCH','UNKNOWN')),
 CONSTRAINT ck_task_delivery CHECK(delivery_state IN('UNKNOWN','ACTIVE','PAUSED','REVIEWING','BLOCKED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实非空DAG节点；后台分块写，manifest完整才公开';

CREATE TABLE orbit_task_edge (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '父子只能同Task',
 child_id CHAR(36) NOT NULL COMMENT '真实子节点UUID',
 parent_id CHAR(36) NOT NULL COMMENT '真实父节点UUID',
 PRIMARY KEY(tenant_id,task_id,child_id,parent_id),
 FOREIGN KEY(tenant_id,task_id,child_id) REFERENCES orbit_task_node(tenant_id,task_id,id),
 FOREIGN KEY(tenant_id,task_id,parent_id) REFERENCES orbit_task_node(tenant_id,task_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整真实父依赖，禁止跨任务引用';

CREATE TABLE orbit_task_event (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实Task',
 event_id CHAR(36) NOT NULL COMMENT '原TaskEvent UUID',
 sequence BIGINT NOT NULL COMMENT '每Task递增且唯一，非浏览器计时器',
 schema_version INT NOT NULL DEFAULT 1 COMMENT '原事件版本1',
 task_revision BIGINT NOT NULL COMMENT '同事务任务实际版本',
 node_id CHAR(36) NULL COMMENT '任务级事件为NULL',
 state VARCHAR(40) NOT NULL COMMENT '真实持久事件状态',
 occurred_at DATETIME(3) NOT NULL COMMENT '数据库真实UTC时间',
 request_id CHAR(36) NOT NULL COMMENT '原安全关联请求UUID',
 PRIMARY KEY(tenant_id,task_id,sequence),
 UNIQUE KEY uk_task_event_id(tenant_id,event_id),
 KEY idx_task_event_expiry(occurred_at,tenant_id,task_id,sequence),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id),
 FOREIGN KEY(tenant_id,task_id,node_id) REFERENCES orbit_task_node(tenant_id,task_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='持久TaskEvent，T2实现7天SSE续传/清理';

CREATE TABLE orbit_task_audit (
 id CHAR(36) NOT NULL COMMENT '不可变成功审计UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实Task',
 actor_id BIGINT NOT NULL COMMENT '真实操作者，不改变任务拥有者',
 request_id CHAR(36) NOT NULL COMMENT '安全关联请求',
 action VARCHAR(40) NOT NULL COMMENT '实际完整发布动作',
 created_at DATETIME(3) NOT NULL COMMENT '数据库UTC',
 PRIMARY KEY(id),
 UNIQUE KEY uk_task_audit_tenant(tenant_id,task_id,id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='任务发布成功审计，失败整笔回滚';

CREATE TABLE orbit_task_outbox (
 audit_id CHAR(36) NOT NULL COMMENT '关联不可变审计UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实Task',
 created_at DATETIME(3) NOT NULL COMMENT '数据库UTC',
 PRIMARY KEY(audit_id),
 FOREIGN KEY(tenant_id,task_id,audit_id) REFERENCES orbit_task_audit(tenant_id,task_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整发布同事务outbox，不自动调度发送';

-- 主线授权：任务仍归原launch子功能，仅编译已有tasks.read，不自动授新动作。
INSERT INTO sys_menu(menu_id,menu_name,parent_id,order_num,path,component,is_frame,is_cache,
 menu_type,visible,status,perms,icon,create_by,create_time,remark) VALUES
(310206,'读取执行任务动作',31020,26,'#','',1,1,'F','0','0','tasks.read','#','admin',NOW(),
 '读取冻结归属范围内真实完整Task与节点，不开放执行/取消/重试');
INSERT INTO sys_role_menu(role_id,menu_id)
 SELECT DISTINCT br.native_role_id,310206 FROM orbit_business_role br
 JOIN orbit_business_role_action a ON a.tenant_id=br.tenant_id AND a.role_id=br.id
 WHERE a.permission_code='tasks.read' AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm
 WHERE rm.role_id=br.native_role_id AND rm.menu_id=310206);
