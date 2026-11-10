CREATE TABLE orbit_meta_sync_policy (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 profile_id CHAR(36) NOT NULL COMMENT '显式选择原指标配置UUID',
 adapter_version VARCHAR(64) NOT NULL COMMENT '已验证指标映射版本',
 scheduler_enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT '租户明确开启自动采集，默认关闭',
 actor_id BIGINT NOT NULL COMMENT '启用者，调度每次复核实际权限',
 revision BIGINT NOT NULL COMMENT '配置CAS版本',
 last_fast_slot BIGINT NULL COMMENT '已创建最近7日任务的UTC十五分钟槽',
 last_daily_date DATE NULL COMMENT '已创建90日归因修正的UTC日期',
 updated_at DATETIME(6) NOT NULL COMMENT '最后配置变更UTC',
 PRIMARY KEY(tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='租户Meta采集口径与默认关闭的自动调度';

CREATE TABLE orbit_meta_connection_sync_policy (
 tenant_id CHAR(36) NOT NULL COMMENT '当前连接所属租户UUID',
 connection_id CHAR(36) NOT NULL COMMENT '明确独立Meta连接UUID，不继承其他客户策略',
 profile_id CHAR(36) NOT NULL COMMENT '仅当前连接已验证的指标口径UUID',
 adapter_version VARCHAR(64) NOT NULL COMMENT '受控指标映射版本',
 scheduler_enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT '连接级自动采集明确开关，默认关闭',
 actor_id BIGINT NOT NULL COMMENT '真实设置者，调度逐次复核权限',
 revision BIGINT NOT NULL COMMENT '连接级配置CAS版本',
 last_fast_slot BIGINT NULL COMMENT '已创建最近7日任务的UTC十五分钟槽',
 last_daily_date DATE NULL COMMENT '已创建90日归因修正任务的UTC日期',
 updated_at DATETIME(6) NOT NULL COMMENT '连接策略最后变更UTC时刻',
 PRIMARY KEY(tenant_id,connection_id),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES orbit_meta_connection(tenant_id,id),
 FOREIGN KEY(tenant_id,profile_id) REFERENCES orbit_metric_profile_head(tenant_id,id),
 CHECK(revision BETWEEN 1 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='独立连接采集策略，存在时覆盖兼容租户默认策略';
