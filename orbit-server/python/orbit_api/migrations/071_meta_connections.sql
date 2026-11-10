-- Meta平台应用从受控服务端配置读取，租户连接只保存加密客户凭据。
CREATE TABLE orbit_meta_connection (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '连接UUID',
 actor_id BIGINT NOT NULL COMMENT '连接发起人若依用户ID',
 kind VARCHAR(8) NOT NULL COMMENT 'LOGIN登录授权或BM系统用户',
 principal_id VARCHAR(64) NOT NULL COMMENT 'Meta已验证主体ID',
 app_id VARCHAR(64) NOT NULL COMMENT '已验证平台应用ID',
 status VARCHAR(24) NOT NULL COMMENT 'ACTIVE/REAUTH_REQUIRED/DISCONNECTED',
 revision BIGINT NOT NULL COMMENT '凭据来源版本，更新或断开递增',
 token_envelope MEDIUMTEXT NULL COMMENT '租户及连接绑定AES-GCM密文，断开删除',
 scopes_json JSON NOT NULL COMMENT '已验证权限，不含Token',
 expires_at DATETIME(3) NULL COMMENT '凭据UTC到期，系统用户可无固定到期',
 data_access_expires_at DATETIME(3) NULL COMMENT '数据访问UTC到期',
 configuration_id CHAR(36) NULL COMMENT 'BM原配置UUID，登录连接为空',
 configuration_revision BIGINT NULL COMMENT 'BM原配置冻结版本',
 created_at DATETIME(3) NOT NULL COMMENT '登记UTC时间',
 updated_at DATETIME(3) NOT NULL COMMENT '最近状态变更UTC时间',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_meta_principal(tenant_id,actor_id,app_id,kind,principal_id),
 KEY ix_meta_expiry(tenant_id,status,expires_at),
 KEY ix_meta_principal(app_id,principal_id,tenant_id,id) COMMENT '签名回调按应用主体锁定受影响连接，避免扫描锁住其他租户主体',
 CONSTRAINT ck_meta_connection_kind CHECK(kind IN('LOGIN','BM')),
 CONSTRAINT ck_meta_connection_status CHECK(status IN('ACTIVE','REAUTH_REQUIRED','DISCONNECTED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='租户Meta读取连接，不授权广告写入';
CREATE TABLE orbit_meta_authorization_session (
 id CHAR(36) NOT NULL COMMENT '授权请求UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '发起租户UUID',
 actor_id BIGINT NOT NULL COMMENT '发起用户ID',
 browser_session_id CHAR(36) NOT NULL COMMENT '已验证浏览器会话UUID',
 state_digest BINARY(32) NOT NULL COMMENT '随机state的SHA256，不保存明文',
 state_envelope TEXT NOT NULL COMMENT '仅供原幂等重放的加密state',
 request_key VARCHAR(128) NOT NULL COMMENT '原发起会话幂等键',
 payload_hash CHAR(64) NOT NULL COMMENT '站内返回地址及重授权目标摘要',
 return_to VARCHAR(255) NOT NULL COMMENT '已验证站内返回路径',
 connection_id CHAR(36) NULL COMMENT '显式重新授权目标连接',
 connection_revision BIGINT NULL COMMENT '重新授权前冻结版本',
 app_id VARCHAR(64) NOT NULL COMMENT '发起时平台应用ID',
 status VARCHAR(16) NOT NULL COMMENT 'PENDING/EXCHANGING/COMPLETED/FAILED/CANCELLED',
 expires_at DATETIME(3) NOT NULL COMMENT '一次性state十分钟UTC截止',
 created_at DATETIME(3) NOT NULL COMMENT '发起UTC时间',
 PRIMARY KEY(id),
 UNIQUE KEY uq_meta_state(state_digest),
 UNIQUE KEY uq_meta_session_key(tenant_id,browser_session_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='Meta授权一次性浏览器绑定会话';
CREATE TABLE orbit_meta_account_source (
 tenant_id CHAR(36) NOT NULL COMMENT '账户租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '原业务账户UUID',
 connection_id CHAR(36) NOT NULL COMMENT '唯一当前读取连接',
 connection_revision BIGINT NOT NULL COMMENT '当前读取凭据版本，任务必须精确匹配',
 revision BIGINT NOT NULL COMMENT '来源关联版本',
 PRIMARY KEY(tenant_id,account_id),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES orbit_meta_connection(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户显式读取来源，禁止自动回退其他凭据';
CREATE TABLE orbit_meta_callback_receipt (
 id CHAR(36) NOT NULL COMMENT '回调处理UUID及确认码',
 app_id VARCHAR(64) NOT NULL COMMENT '验证签名的平台应用ID',
 principal_id VARCHAR(64) NOT NULL COMMENT '已验证Meta主体ID',
 kind VARCHAR(16) NOT NULL COMMENT 'DEAUTHORIZE或DELETE',
 request_hash CHAR(64) NOT NULL COMMENT '签名回调摘要用于幂等',
 status VARCHAR(16) NOT NULL COMMENT 'COMPLETED或PENDING',
 created_at DATETIME(3) NOT NULL COMMENT '处理UTC时间',
 PRIMARY KEY(id), UNIQUE KEY uq_meta_callback(request_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='Meta取消授权与删除请求脱敏回执';
CREATE TABLE orbit_meta_request_receipt (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '发起用户ID',
 request_key VARCHAR(128) NOT NULL COMMENT '写入幂等键',
 input_hash CHAR(64) NOT NULL COMMENT '无密钥请求规范摘要',
 result_json JSON NOT NULL COMMENT '无密钥结果回执',
 created_at DATETIME(3) NOT NULL COMMENT '处理UTC时间',
 PRIMARY KEY(tenant_id,actor_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='Meta业务写入幂等回执，与审计同事务';
-- 平台签名撤销与OAuth/BM发布共用主体互斥；跨租户回调先锁主体再按租户顺序锁账户clock。
CREATE TABLE orbit_meta_principal_lock (
 app_id VARCHAR(64) NOT NULL COMMENT '平台应用ID，主体空间隔离',
 principal_id VARCHAR(64) NOT NULL COMMENT '已验证Meta主体ID',
 last_revoked_at DATETIME(6) NULL COMMENT '最近签名撤销UTC时刻，阻止迟到凭据发布复活',
 PRIMARY KEY(app_id,principal_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='Meta主体发布撤销互斥与撤销时间，不保存凭据';
