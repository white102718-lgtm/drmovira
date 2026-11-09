-- 账户当前渠道独立扩展；不改变原Account DTO、历史归属或计划渠道快照。
CREATE TABLE orbit_account_current_channel (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '当前账户内部UUID；一账户至多一条当前关联',
 channel_id CHAR(36) NULL COMMENT '当前渠道UUID；NULL表示明确清空，无记录亦视为未关联',
 updated_at DATETIME(3) NOT NULL COMMENT '当前关联最后提交UTC时刻',
 PRIMARY KEY (tenant_id,account_id),
 KEY idx_account_channel (tenant_id,channel_id,account_id) COMMENT '当前渠道到规则范围账户的有界查询',
 FOREIGN KEY (tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 FOREIGN KEY (tenant_id,channel_id) REFERENCES orbit_channel(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户当前渠道；应用写入必须同事务推进账户revision和clock及审计outbox';

CREATE TABLE orbit_account_channel_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '实际请求原生用户ID',
 request_key VARCHAR(128) NOT NULL COMMENT '账户渠道独立幂等键空间',
 payload_hash CHAR(64) NOT NULL COMMENT '账户UUID、CAS和完整规范正文摘要',
 response_json JSON NOT NULL COMMENT '已提交结果；重放必须重新授权',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '提交UTC时刻',
 PRIMARY KEY (tenant_id,actor_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户当前渠道写入与回执同事务，不以客户端重试产生重复审计';
