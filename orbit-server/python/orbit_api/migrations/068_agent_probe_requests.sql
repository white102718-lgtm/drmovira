-- 主动只读探测；设备clock串行化同设备有效待办，不包含平台命令或凭据。
CREATE TABLE orbit_agent_probe_request (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID，所有访问显式限定',
 id CHAR(36) NOT NULL COMMENT '探测请求UUID，非广告命令ID',
 agent_id CHAR(36) NOT NULL COMMENT '目标设备UUID',
 actor_id BIGINT NOT NULL COMMENT '发起原生用户ID，派发及完成复验当前权限',
 agent_revision BIGINT NOT NULL COMMENT '创建时设备登记版本，变更后禁止执行',
 state VARCHAR(16) NOT NULL COMMENT 'QUEUED/COMPLETED/FAILED；EXPIRED按UTC到期派生',
 created_at DATETIME(6) NOT NULL COMMENT '服务端UTC创建时间',
 expires_at DATETIME(6) NOT NULL COMMENT '服务端UTC到期时间，创建后120秒',
 completed_at DATETIME(6) NULL COMMENT '服务端UTC终结时间',
 error_code VARCHAR(64) NULL COMMENT '固定安全错误码，不保存平台响应',
 completion_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原完成请求规范SHA256',
 completion_ack JSON NULL COMMENT '完成请求原Ack，丢响应可精确重放',
 PRIMARY KEY(tenant_id,id),
 KEY ix_probe_pending(tenant_id,agent_id,state,expires_at,created_at,id),
 FOREIGN KEY(tenant_id,agent_id) REFERENCES orbit_execution_agent(tenant_id,id),
 CHECK(state IN('QUEUED','COMPLETED','FAILED')),
 CHECK(agent_revision BETWEEN 1 AND 9007199254740991),
 CHECK(expires_at>created_at),
 CHECK((completion_hash IS NULL)=(completion_ack IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='设备主动只读观察请求；不授予任何广告操作能力';
