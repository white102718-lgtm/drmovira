-- 授权回调原子入队；账户读取/创建沿用已有批次和逐项结果。
ALTER TABLE orbit_meta_authorization_session
 ADD COLUMN owner_user_id CHAR(36) NULL COMMENT '发起授权时冻结的真实平台业务用户UUID，旧会话须重新授权',
 ADD COLUMN owner_team_id CHAR(36) NULL COMMENT '发起授权时冻结的团队UUID';
ALTER TABLE orbit_account_import
 MODIFY vendor_id CHAR(36) NULL COMMENT '可后续补充的户商UUID，无户商不阻止导入',
 MODIFY vendor_revision BIGINT NULL COMMENT '有户商时冻结的版本，否则NULL',
 MODIFY input_ref CHAR(36) NULL COMMENT '人工导入原始对象UUID，自动发现原文在auto_import_batch';
CREATE TABLE orbit_meta_auto_import (
 tenant_id CHAR(36) NOT NULL COMMENT '授权state冻结的可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '一次性授权会话UUID，也是任务幂等键',
 connection_id CHAR(36) NOT NULL COMMENT '授权成功的连接UUID',
 connection_revision BIGINT NOT NULL COMMENT '授权成功时冻结的连接版本',
 actor_id BIGINT NOT NULL COMMENT '发起授权的原生平台用户ID',
 owner_user_id CHAR(36) NOT NULL COMMENT '发起授权的业务用户UUID，即新账户投放师',
 owner_team_id CHAR(36) NOT NULL COMMENT '发起授权时冻结的团队UUID',
 actor_auth_version BIGINT NOT NULL COMMENT '冻结发起人权限版本，逐页复验',
 scope_version BIGINT NOT NULL COMMENT '冻结目录权限版本，逐页复验',
 request_id CHAR(36) NOT NULL COMMENT '原始回调请求追溯UUID',
 state VARCHAR(20) NOT NULL COMMENT 'QUEUED/DISCOVERING/IMPORTING/FAILED，导入终态从原批次派生',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '事务审计版本与租约领取栅栏',
 checkpoint_json JSON NULL COMMENT '已完整提交页的内部续页检查点，不对浏览器返回',
 page_number INT NOT NULL DEFAULT 0 COMMENT '已完整提交页数，不足全量时禁止完成状态',
 attempts INT NOT NULL DEFAULT 0 COMMENT '当前页领取次数，成功提交后归零，最多4次',
 claim_id CHAR(36) NULL COMMENT '当前读取租约UUID，迟到结果不得发布',
 claimed_at DATETIME(3) NULL COMMENT '租约领取UTC时刻，120秒后可恢复',
 next_attempt_at DATETIME(3) NOT NULL COMMENT '下一次允许读取UTC时刻',
 error_code VARCHAR(80) NULL COMMENT '固定安全错误码，不保存平台原始异常',
 created_at DATETIME(3) NOT NULL COMMENT '授权成功入队UTC时刻',
 updated_at DATETIME(3) NOT NULL COMMENT '任务最近变化UTC时刻',
 PRIMARY KEY(tenant_id,id),
 KEY idx_auto_import_claim(state,next_attempt_at,claimed_at),
 KEY idx_auto_import_connection(tenant_id,connection_id,created_at,id),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES orbit_meta_connection(tenant_id,id),
 CHECK(state IN ('QUEUED','DISCOVERING','IMPORTING','FAILED')),
 CHECK(page_number BETWEEN 0 AND 250),
 CHECK(attempts BETWEEN 0 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='Meta授权全量账户自动发现的可恢复持久任务';
CREATE TABLE orbit_meta_auto_import_batch (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 task_id CHAR(36) NOT NULL COMMENT '自动发现任务UUID',
 batch_id CHAR(36) NOT NULL COMMENT '既有账户导入批次UUID，全部结果复用原表',
 page_number INT NOT NULL COMMENT '对应已提交平台页号，从1开始',
 input_text TEXT NOT NULL COMMENT '该页账户ID原文，仅服务端保存，不含凭据',
 PRIMARY KEY(tenant_id,task_id,page_number),
 UNIQUE KEY uk_auto_import_batch(tenant_id,batch_id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_meta_auto_import(tenant_id,id),
 FOREIGN KEY(tenant_id,batch_id) REFERENCES orbit_account_import(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='发现检查点与原导入批次同事务关联及输入追溯';
ALTER TABLE orbit_meta_import_source
 ADD COLUMN discovery_task_id CHAR(36) NULL COMMENT '服务端自动发现任务UUID，已持久发现后直接复验账户读取权限',
 ADD FOREIGN KEY(tenant_id,discovery_task_id) REFERENCES orbit_meta_auto_import(tenant_id,id);
