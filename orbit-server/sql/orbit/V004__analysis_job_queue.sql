-- 内部可信规则命中入队基础；本迁移不启动Worker或调用模型。
CREATE TABLE IF NOT EXISTS orbit_analysis_gate (
 tenant_id CHAR(36) NOT NULL COMMENT '服务端可信租户UUID',
 rule_id CHAR(36) NOT NULL COMMENT '已鉴权规则UUID，上游规则分发器待接通',
 entity_id CHAR(36) NOT NULL COMMENT '冻结的分析对象UUID',
 generation BIGINT NOT NULL DEFAULT 0 COMMENT '规则对象分析代次，跨规则改版保持递增',
 last_admitted_at DATETIME(3) NULL COMMENT '最近成功入队UTC时刻，用于真实经过时间冷却',
 PRIMARY KEY (tenant_id,rule_id,entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则对象入队串行化门闩，不代表对象授权来源';
CREATE TABLE IF NOT EXISTS orbit_analysis_daily_quota (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 rule_id CHAR(36) NOT NULL COMMENT '规则UUID，不按规则revision重置额度',
 entity_id CHAR(36) NOT NULL COMMENT '分析对象UUID，不按页面人数统计',
 business_date DATE NOT NULL COMMENT '实际入队时刻按冻结规则IANA时区计算的当地日',
 admitted_count INT NOT NULL DEFAULT 0 COMMENT '当地日成功入队次数，与任务和审计同事务',
 PRIMARY KEY (tenant_id,rule_id,entity_id,business_date),
 FOREIGN KEY (tenant_id,rule_id,entity_id) REFERENCES orbit_analysis_gate(tenant_id,rule_id,entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则对象当地日额度，失败事务不扣次数';
CREATE TABLE IF NOT EXISTS orbit_analysis_job (
 id CHAR(36) NOT NULL COMMENT '内部分析任务UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID，所有读写须带租户',
 rule_id CHAR(36) NOT NULL COMMENT '冻结规则UUID',
 rule_revision BIGINT NOT NULL COMMENT '冻结规则版本',
 entity_id CHAR(36) NOT NULL COMMENT '冻结分析对象UUID',
 hit_id CHAR(36) NOT NULL COMMENT '可信规则命中UUID，上游持久化待接通',
 schedule_slot VARCHAR(100) NOT NULL COMMENT '冻结调度slot，不接受人工开始分析入口',
 schedule_zone VARCHAR(64) NOT NULL COMMENT '冻结规则IANA时区',
 business_date DATE NOT NULL COMMENT '实际入队对应的规则当地日',
 generation BIGINT NOT NULL COMMENT '规则对象分析代次，用于防晚到覆盖',
 state VARCHAR(24) NOT NULL COMMENT '当前仅实现QUEUED与SUPERSEDED；消费状态机待接通',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '任务状态乐观锁版本',
 dedupe_hash CHAR(64) NOT NULL COMMENT 'tenant/hit/事实hash/提供商与策略版本的SHA256幂等摘要',
 input_hash CHAR(64) NOT NULL COMMENT '冻结输入JSON的UTF8 SHA256',
 input_json LONGTEXT NOT NULL COMMENT '冻结事实包原始规范JSON，无凭据；保持字节内容用于hash复核',
 policy_id CHAR(36) NOT NULL COMMENT '冻结AI建议策略配置UUID',
 policy_revision BIGINT NOT NULL COMMENT '冻结策略配置版本',
 provider_id CHAR(36) NOT NULL COMMENT '冻结GPT或Claude配置UUID，不保存密钥副本',
 provider_revision BIGINT NOT NULL COMMENT '冻结提供商版本，派发前仍需核对撤权与版本',
 settings_json JSON NOT NULL COMMENT '冻结策略及提供商公开参数，不含密文或明文凭据',
 created_at DATETIME(3) NOT NULL COMMENT '入队UTC时刻',
 PRIMARY KEY (id),
 UNIQUE KEY uk_analysis_job_tenant_id (tenant_id,id),
 UNIQUE KEY uk_analysis_job_dedupe (tenant_id,dedupe_hash),
 KEY idx_analysis_job_queue (tenant_id,state,created_at,id),
 FOREIGN KEY (tenant_id,rule_id,entity_id) REFERENCES orbit_analysis_gate(tenant_id,rule_id,entity_id),
 CHECK (JSON_VALID(input_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='持久化分析待办队列，仅内部可信分发器可调用，尚无模型Worker';
CREATE TABLE IF NOT EXISTS orbit_analysis_job_event (
 id CHAR(36) NOT NULL COMMENT '不可变任务事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '事件所属可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '分析任务UUID',
 from_state VARCHAR(24) NULL COMMENT '旧状态，首次入队为NULL',
 to_state VARCHAR(24) NOT NULL COMMENT '新状态：QUEUED或SUPERSEDED',
 reason_code VARCHAR(64) NOT NULL COMMENT '固定原因码，不记录输入或平台原始响应',
 created_at DATETIME(3) NOT NULL COMMENT '事件UTC时刻，与任务状态同事务',
 PRIMARY KEY (id),
 KEY idx_analysis_event_job (tenant_id,job_id,created_at,id),
 FOREIGN KEY (tenant_id,job_id) REFERENCES orbit_analysis_job(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='分析入队和替代事件审计，不替代未来模型费用账本';
