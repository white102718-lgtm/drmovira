-- 冻结选择与当前账户目录分离；创建范围不提高账户目录版本，不伪造平台或执行授权。
CREATE TABLE orbit_account_scope_snapshot (
 tenant_id CHAR(36) NOT NULL COMMENT '当前可信租户UUID，跨租户上下文另行统一实现',
 id CHAR(36) NOT NULL COMMENT '不可猜测的范围快照UUID',
 actor_id BIGINT NOT NULL COMMENT '真实创建会话用户，不接受浏览器伪造',
 scope_version BIGINT NOT NULL COMMENT '真实身份授权版本，非账户名称或指标水位',
 auth_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '当前人员角色团队和显式管理团队权限指纹',
 request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '会话动作幂等键，不含凭据',
 request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原选择规范正文SHA256',
 request_json JSON NOT NULL COMMENT '原IDS或FILTER选择规范，非执行时权限凭据',
 member_count INT NOT NULL DEFAULT 0 COMMENT '完整冻结成员数量，最多50000，不截断',
 members_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '有序冻结成员快照SHA256，完整写入后才设置',
 ready BOOLEAN NOT NULL DEFAULT 0 COMMENT '只在所有成员与审计同事务成功后置真',
 created_at DATETIME(3) NOT NULL COMMENT '实际冻结UTC时刻，分页沿用而不重新生成',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uk_account_scope_request(tenant_id,actor_id,request_key),
 KEY idx_account_scope_actor(tenant_id,actor_id,created_at,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原账户跨页选择不可变快照，不是计划执行许可';

CREATE TABLE orbit_account_scope_member (
 tenant_id CHAR(36) NOT NULL COMMENT '范围所属可信租户UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '已授权范围UUID',
 account_id CHAR(36) NOT NULL COMMENT '冻结账户业务UUID',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '冻结平台数字ID，保留前导零',
 name LONGTEXT NOT NULL COMMENT '冻结完整账户名称，后续改名不改历史显示',
 name_prefix VARCHAR(191) NOT NULL COMMENT '冻结名称前缀索引，非原始值替代',
 account_revision BIGINT NOT NULL COMMENT '冻结对象版本仅供审计；改名不擅自令整个范围失效',
 owner_user_id CHAR(36) NOT NULL COMMENT '冻结投手，计划动作时重新核验',
 owner_team_id CHAR(36) NOT NULL COMMENT '冻结团队，计划动作时重新核验',
 currency CHAR(3) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '冻结币种，计划动作时重新核验',
 PRIMARY KEY(tenant_id,snapshot_id,account_id),
 KEY idx_account_scope_name(tenant_id,snapshot_id,name_prefix,account_id),
 FOREIGN KEY(tenant_id,snapshot_id) REFERENCES orbit_account_scope_snapshot(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='按UUID键集冻结成员，查询不依靠浏览器抓全量';

CREATE TABLE orbit_account_scope_event (
 id CHAR(36) NOT NULL COMMENT '不可变成功审计事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '业务租户UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '对应完整范围UUID',
 actor_id BIGINT NOT NULL COMMENT '真实原动作用户',
 request_id CHAR(36) NOT NULL COMMENT '服务端安全请求UUID',
 member_count INT NOT NULL COMMENT '完整冻结数量',
 members_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整成员摘要',
 created_at DATETIME(3) NOT NULL COMMENT '原子成功审计UTC时刻',
 PRIMARY KEY(id),
 UNIQUE KEY uk_account_scope_event(tenant_id,snapshot_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='范围冻结只追加审计，与成员及幂等状态同事务';

CREATE TABLE orbit_account_scope_outbox (
 event_id CHAR(36) NOT NULL COMMENT '关联成功审计事件UUID，消费者按此去重',
 tenant_id CHAR(36) NOT NULL COMMENT '业务租户UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '完整范围UUID',
 created_at DATETIME(3) NOT NULL COMMENT '同事务UTC创建时刻',
 processed_at DATETIME(3) NULL COMMENT '真实处理UTC时刻，未消费保持NULL',
 PRIMARY KEY(event_id),
 KEY idx_account_scope_pending(tenant_id,processed_at,created_at,event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户范围事务outbox，不自动声称下游已处理';
