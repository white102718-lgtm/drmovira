-- 账户18列观测与消耗日事实；仅受控采集器写入，未采集不生成0或伪造观测时间。
CREATE TABLE orbit_account_details_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 revision BIGINT NOT NULL DEFAULT 0 COMMENT '附加观测与消费事实发布水位，游标绑定版本',
 snapshot_id CHAR(36) NULL COMMENT '最近原子发布UUID，NULL表示从未发布',
 PRIMARY KEY(tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户详情观测发布时钟';
INSERT INTO orbit_account_details_clock(tenant_id) SELECT id FROM orbit_tenant;
CREATE TABLE orbit_account_details_current (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '内部账户UUID',
 revision BIGINT NOT NULL COMMENT '本条观测版本',
 value_json JSON NOT NULL COMMENT '严格白名单字段和逐字段来源/观测时刻，无凭据',
 snapshot_id CHAR(36) NOT NULL COMMENT '本次原子发布UUID',
 updated_at DATETIME(3) NOT NULL COMMENT '本地接收UTC时间，不替代平台观测时间',
 PRIMARY KEY(tenant_id,account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户18列当前附加观测';
CREATE TABLE orbit_account_details_history (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '内部账户UUID',
 revision BIGINT NOT NULL COMMENT '该账户不可变观测版本',
 value_json JSON NOT NULL COMMENT '已发布字段白名单快照',
 snapshot_id CHAR(36) NOT NULL COMMENT '原子发布UUID',
 received_at DATETIME(3) NOT NULL COMMENT '接收UTC时间',
 PRIMARY KEY(tenant_id,account_id,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户附加观测只追加历史';
CREATE TABLE orbit_account_spend_day (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '账户UUID',
 business_date DATE NOT NULL COMMENT '账户IANA时区当地业务日',
 currency CHAR(3) NOT NULL COMMENT '账户币种，禁止跨币种混加',
 amount DECIMAL(27,6) NULL COMMENT '权威消费；未知NULL，完整观测才允许0',
 coverage VARCHAR(16) NOT NULL COMMENT 'COMPLETE完整或PARTIAL缺失',
 owner_user_id CHAR(36) NULL COMMENT '业务日冻结投手，NULL未归属',
 owner_team_id CHAR(36) NULL COMMENT '业务日冻结团队，NULL未归属',
 source VARCHAR(100) NOT NULL COMMENT '受控来源标识，不含Token',
 observed_at DATETIME(3) NOT NULL COMMENT '来源观测UTC时刻',
 revision BIGINT NOT NULL COMMENT '同账户同业务日递增版本',
 snapshot_id CHAR(36) NOT NULL COMMENT '最后更新发布UUID',
 PRIMARY KEY(tenant_id,account_id,business_date),
 KEY idx_account_spend_team(tenant_id,owner_team_id,business_date,account_id) COMMENT '历史团队授权范围后聚合',
 KEY idx_account_spend_owner(tenant_id,owner_user_id,business_date,account_id) COMMENT '历史本人归属范围后聚合'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户当地日消费当前权威观测';
CREATE TABLE orbit_account_spend_day_history LIKE orbit_account_spend_day;
ALTER TABLE orbit_account_spend_day_history
 DROP PRIMARY KEY, ADD PRIMARY KEY(tenant_id,account_id,business_date,revision),
 COMMENT='账户当地日消费不可变版本历史';
