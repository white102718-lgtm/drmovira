-- 内部规则草稿版本存储；不增加菜单、授权、启用入口或调度器。
CREATE TABLE IF NOT EXISTS orbit_rule_draft (
    id CHAR(36) NOT NULL COMMENT '服务端规则UUID',
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID，所有读取显式限定',
    revision BIGINT NOT NULL COMMENT '正文或状态变化递增的乐观锁版本',
    state VARCHAR(24) NOT NULL COMMENT 'DRAFT草稿、ENABLED启用、PAUSED暂停、ARCHIVED归档；当前无启用入口',
    reference_status VARCHAR(32) NOT NULL DEFAULT 'PENDING_REFERENCES' COMMENT '固定待验证；owner、范围与profile授权链未接通，不可启用',
    body_json LONGTEXT NOT NULL COMMENT '完整RuleWrite规范JSON原串，版本不可反写',
    body_hash CHAR(64) NOT NULL COMMENT '规范正文UTF8 SHA256',
    current_simulation_id CHAR(36) NULL COMMENT '有效模拟UUID；任意正文或状态变更清空，模拟服务待接通',
    updated_at DATETIME(3) NOT NULL COMMENT '最近变更UTC时刻',
    PRIMARY KEY (tenant_id,id),
    CHECK (JSON_VALID(body_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='内部规则草稿头，不能代替授权规则读取模型';
CREATE TABLE IF NOT EXISTS orbit_rule_draft_version (
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
    rule_id CHAR(36) NOT NULL COMMENT '规则UUID',
    revision BIGINT NOT NULL COMMENT '不可变版本序号',
    state VARCHAR(24) NOT NULL COMMENT '该版本冻结状态',
    body_json LONGTEXT NOT NULL COMMENT '该版本规范RuleWrite JSON原串',
    body_hash CHAR(64) NOT NULL COMMENT '该版本正文UTF8 SHA256',
    created_at DATETIME(3) NOT NULL COMMENT '版本创建UTC时刻',
    PRIMARY KEY (tenant_id,rule_id,revision),
    FOREIGN KEY (tenant_id,rule_id) REFERENCES orbit_rule_draft(tenant_id,id),
    CHECK (JSON_VALID(body_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则正文及状态历史版本，只追加';
CREATE TABLE IF NOT EXISTS orbit_rule_draft_event (
    id CHAR(36) NOT NULL COMMENT '规则变更事件UUID',
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
    rule_id CHAR(36) NOT NULL COMMENT '规则UUID',
    revision BIGINT NOT NULL COMMENT '事件对应不可变规则版本',
    actor_id BIGINT NOT NULL COMMENT '服务端若依操作用户ID，不接受正文伪造',
    action VARCHAR(24) NOT NULL COMMENT 'SAVE保存、PAUSE暂停、ARCHIVE归档',
    reason VARCHAR(500) NOT NULL COMMENT '规范化人工原因，不保存平台响应或凭据',
    created_at DATETIME(3) NOT NULL COMMENT '事件UTC时刻，与规则更新同事务',
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id,rule_id,revision) REFERENCES orbit_rule_draft_version(tenant_id,rule_id,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则草稿及状态操作事件，审计失败回滚正文';
CREATE TABLE IF NOT EXISTS orbit_rule_draft_idempotency (
    tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
    actor_id BIGINT NOT NULL COMMENT '若依操作用户ID',
    idem_key CHAR(36) NOT NULL COMMENT '调用方幂等UUID，同租户用户范围唯一',
    request_hash CHAR(64) NOT NULL COMMENT '操作身份、期望版本、规范正文摘要和原因的SHA256',
    rule_id CHAR(36) NULL COMMENT '成功规则UUID，事务提交前才填入',
    revision BIGINT NULL COMMENT '首次成功结果版本，重放不读取可变当前头',
    PRIMARY KEY (tenant_id,actor_id,idem_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='内部规则操作幂等，失败事务不保留预占';
