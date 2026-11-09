-- ORBIT作为外部OIDC客户端；不把上游OIDC服务端的JWT会话当作产品Cookie会话。
-- 所有时间为UTC，凭据只留用途摘要或AES-GCM信封；由显式迁移工具执行，启动不建表。
CREATE TABLE orbit_external_identity (
 id CHAR(36) NOT NULL COMMENT '稳定身份绑定UUID，不替换若依内部subject UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '业务身份所属可信租户UUID',
 user_id BIGINT NOT NULL COMMENT '绑定的原若依用户ID，不能通过邮箱自动合并',
 issuer VARCHAR(500) NOT NULL COMMENT '已验证OIDC issuer原文，按标准精确比较',
 issuer_digest BINARY(32) NOT NULL COMMENT 'issuer UTF8 SHA256，供有界索引定位，命中后仍比较原文',
 subject VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '外部issuer下的原始sub，大小写敏感，不trim或改写',
 subject_digest BINARY(32) NOT NULL COMMENT '原始sub SHA256，避免长组合索引',
 provider_id CHAR(36) NOT NULL COMMENT '完成首次验证的系统OIDC配置UUID',
 verified_email VARCHAR(254) NOT NULL COMMENT '邀请绑定时身份提供者证明已验证的邮箱快照，不作为唯一身份',
 verified_at DATETIME(3) NOT NULL COMMENT '外部身份完成验证的UTC时刻',
 PRIMARY KEY(id),
 UNIQUE KEY uk_oidc_issuer_subject(issuer_digest,subject_digest) COMMENT '一个稳定外部身份只能绑定一个本地用户',
 UNIQUE KEY uk_oidc_user(user_id) COMMENT '首期一个业务用户一个稳定外部身份，不隐式改绑',
 KEY idx_oidc_identity_tenant(tenant_id,user_id) COMMENT '本租户身份核对和成员定位',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(user_id) REFERENCES sys_user(user_id),
 FOREIGN KEY(provider_id) REFERENCES orbit_system_configuration(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='经过签名与邀请验证的OIDC身份绑定，不存ID Token或访问Token';

CREATE TABLE orbit_user_invitation (
 id CHAR(36) NOT NULL COMMENT '邀请业务UUID，不是登录凭据',
 tenant_id CHAR(36) NOT NULL COMMENT '目标人员所在可信租户UUID',
 user_id BIGINT NOT NULL COMMENT '被邀请的原若依用户ID',
 user_revision BIGINT NOT NULL COMMENT '发送后人员版本，后续资料或权限变更使旧邀请失效',
 auth_version BIGINT NOT NULL COMMENT '发送时身份安全版本，停用后启用也不复活旧邀请',
 recipient_email VARCHAR(254) NOT NULL COMMENT '本次邀请邮箱快照，回调需匹配已验证邮箱',
 provider_id CHAR(36) NOT NULL COMMENT '本次绑定使用的受信OIDC配置UUID',
 provider_revision BIGINT NOT NULL COMMENT '发起时OIDC配置版本，不能静默换用新issuer或客户端',
 token_digest BINARY(32) NOT NULL COMMENT '256位随机邀请凭据的分用途SHA256，24小时一次性',
 status VARCHAR(16) NOT NULL COMMENT 'ACTIVE有效、CONSUMED已使用、REVOKED撤销、EXPIRED过期',
 expires_at DATETIME(3) NOT NULL COMMENT '邀请创建后24小时的UTC截止，不因投递重试延长',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻',
 consumed_at DATETIME(3) NULL COMMENT '成功绑定时UTC时刻，未使用为NULL',
 revoked_at DATETIME(3) NULL COMMENT '撤销UTC时刻，未撤销为NULL',
 created_by BIGINT NOT NULL COMMENT '发起邀请的原若依操作者ID',
 PRIMARY KEY(id),
 UNIQUE KEY uk_invitation_digest(token_digest) COMMENT '凭据摘要唯一定位，禁止记录原文',
 KEY idx_invitation_person(tenant_id,user_id,created_at,id) COMMENT '人员当前邀请和有界历史查询',
 KEY idx_invitation_expiry(status,expires_at,id) COMMENT '到期任务按游标小批处理，不做深OFFSET',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(user_id) REFERENCES sys_user(user_id),
 FOREIGN KEY(provider_id) REFERENCES orbit_system_configuration(id),
 FOREIGN KEY(created_by) REFERENCES sys_user(user_id),
 CHECK(status IN ('ACTIVE','CONSUMED','REVOKED','EXPIRED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='一次性24小时人员邀请，重发在同事务撤销旧凭据';

CREATE TABLE orbit_oidc_authorization (
 id CHAR(36) NOT NULL COMMENT '授权事务UUID，不暴露PKCE verifier',
 tenant_id CHAR(36) NOT NULL COMMENT '受信OIDC配置所属租户UUID',
 provider_id CHAR(36) NOT NULL COMMENT '受信系统OIDC配置UUID',
 provider_revision BIGINT NOT NULL COMMENT '授权开始时配置版本，外部返回后重新比较',
 state_digest BINARY(32) NOT NULL COMMENT '随机state的分用途SHA256，原子一次性消费',
 binding_digest BINARY(32) NOT NULL COMMENT 'HttpOnly主机绑定Cookie摘要，防止跨浏览器回调置换',
 protected_json JSON NOT NULL COMMENT 'verifier、nonce和返回地址的AES-GCM信封，不存授权码',
 invitation_id CHAR(36) NULL COMMENT '邀请授权的目标邀请UUID，普通再次登录为NULL',
 status VARCHAR(16) NOT NULL COMMENT 'PENDING待交换、EXCHANGING已认领、CONSUMED成功、FAILED失败',
 expires_at DATETIME(3) NOT NULL COMMENT '授权开始后5分钟UTC截止',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻',
 claimed_at DATETIME(3) NULL COMMENT '外部交换前原子认领UTC时刻',
 finished_at DATETIME(3) NULL COMMENT '完成或失败UTC时刻',
 failure_code VARCHAR(64) NULL COMMENT '白名单失败类别，不记录授权码、Token或提供者原响应',
 PRIMARY KEY(id),
 UNIQUE KEY uk_oidc_state_digest(state_digest) COMMENT 'state摘要唯一查找和并发认领',
 KEY idx_oidc_auth_expiry(status,expires_at,id) COMMENT '过期授权小批清理游标',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(provider_id) REFERENCES orbit_system_configuration(id),
 FOREIGN KEY(invitation_id) REFERENCES orbit_user_invitation(id),
 CHECK(status IN ('PENDING','EXCHANGING','CONSUMED','FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='授权码加PKCE事务，网络交换不占用业务数据库事务';

CREATE TABLE orbit_browser_session (
 id CHAR(36) NOT NULL COMMENT '会话内部UUID，不是浏览器登录凭据',
 tenant_id CHAR(36) NOT NULL COMMENT '当前登录主体的可信租户UUID',
 user_id BIGINT NOT NULL COMMENT '原若依用户ID，角色和数据范围每次从当前目录复核',
 auth_version BIGINT NOT NULL COMMENT '发放时身份安全版本，撤权后旧会话永久失效',
 provider_id CHAR(36) NOT NULL COMMENT '完成登录的受信OIDC配置UUID',
 provider_revision BIGINT NOT NULL COMMENT '登录时OIDC配置版本，配置变化需要重新认证',
 token_digest BINARY(32) NOT NULL COMMENT '随机会话Cookie分用途SHA256，不存Cookie原文',
 binding_digest BINARY(32) NOT NULL COMMENT '配套HttpOnly主机绑定Cookie摘要，防止Cookie注入固定会话',
 csrf_key_id VARCHAR(40) NOT NULL COMMENT 'CSRF用途MAC主密钥版本，不存密钥原文',
 status VARCHAR(16) NOT NULL COMMENT 'ACTIVE有效、REVOKED已撤销、EXPIRED已过期',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '会话退出等状态变更版本，不因触摸活跃时间虚增',
 created_at DATETIME(3) NOT NULL COMMENT '发放UTC时刻',
 last_seen_at DATETIME(3) NOT NULL COMMENT '上次有效请求UTC时刻，最多按分钟合并更新',
 idle_expires_at DATETIME(3) NOT NULL COMMENT '闲置30分钟截止，永不超过绝对截止',
 absolute_expires_at DATETIME(3) NOT NULL COMMENT '首次发放后12小时绝对UTC截止，不续期',
 revoked_at DATETIME(3) NULL COMMENT '显式退出或替换的UTC时刻',
 PRIMARY KEY(id),
 UNIQUE KEY uk_browser_session_digest(token_digest) COMMENT '每次认证按凭据摘要单点读取',
 KEY idx_browser_session_user(tenant_id,user_id,status,id) COMMENT '本用户会话撤销与核对',
 KEY idx_browser_session_expiry(absolute_expires_at,id) COMMENT '到期任务游标索引，避免扫描所有会话',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(user_id) REFERENCES sys_user(user_id),
 FOREIGN KEY(provider_id) REFERENCES orbit_system_configuration(id),
 CHECK(status IN ('ACTIVE','REVOKED','EXPIRED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='ORBIT HttpOnly Secure SameSite=Lax不透明会话，独立于原Bearer兼容入口';

CREATE TABLE orbit_invitation_delivery (
 id CHAR(36) NOT NULL COMMENT '稳定投递UUID，同时作为通知通道幂等标识',
 tenant_id CHAR(36) NOT NULL COMMENT '邀请所属可信租户UUID',
 invitation_id CHAR(36) NOT NULL COMMENT '一次性邀请UUID，一个邀请只对应一个投递意图',
 notification_id CHAR(36) NOT NULL COMMENT '受信Webhook通知配置UUID',
 notification_revision BIGINT NOT NULL COMMENT '排队时通知配置版本，不静默把旧邀请发到新地址',
 protected_json JSON NOT NULL COMMENT '收件邮箱与邀请凭据的AES-GCM信封，审计和API不回显',
 status VARCHAR(16) NOT NULL COMMENT 'QUEUED排队、SENDING发送中、ACCEPTED通道接受、FAILED失败、UNKNOWN结果未知',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '投递状态版本，用于认领与防旧结果覆盖',
 created_at DATETIME(3) NOT NULL COMMENT '与邀请同事务写入的UTC时刻',
 claimed_at DATETIME(3) NULL COMMENT '发送前认领UTC时刻',
 completed_at DATETIME(3) NULL COMMENT '收到通道回执或确认失败UTC时刻',
 failure_code VARCHAR(64) NULL COMMENT '脱敏错误类别，不保存远端原始响应',
 PRIMARY KEY(id),
 UNIQUE KEY uk_invitation_delivery(invitation_id) COMMENT '防止同邀请制造多个投递意图',
 KEY idx_invitation_delivery_claim(status,created_at,id) COMMENT 'Worker按稳定游标有界认领',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(invitation_id) REFERENCES orbit_user_invitation(id),
 FOREIGN KEY(notification_id) REFERENCES orbit_system_configuration(id),
 CHECK(status IN ('QUEUED','SENDING','ACCEPTED','FAILED','UNKNOWN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='邀请事务outbox；通道接受不冒充邮件已送达，未知结果不盲目重发';

CREATE TABLE orbit_auth_audit (
 id CHAR(36) NOT NULL COMMENT '认证审计事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '事件所处可信租户UUID',
 user_id BIGINT NULL COMMENT '已确认的主体ID，匿名失败为NULL，不猜测用户',
 resource_type VARCHAR(24) NOT NULL COMMENT 'AUTHORIZATION、SESSION、INVITATION或DELIVERY',
 resource_id CHAR(36) NOT NULL COMMENT '对应内部业务UUID，不保存凭据摘要以外的秘密',
 action VARCHAR(48) NOT NULL COMMENT '白名单动作类别，不来自提供者自由文本',
 revision BIGINT NOT NULL COMMENT '该状态操作后的内部版本',
 request_id CHAR(36) NOT NULL COMMENT '服务端生成请求UUID，便于安全关联排查',
 created_at DATETIME(3) NOT NULL COMMENT '审计写入UTC时刻',
 PRIMARY KEY(id),
 KEY idx_auth_audit_tenant(tenant_id,created_at,id) COMMENT '租户审计键集分页与保留清理',
 KEY idx_auth_audit_resource(tenant_id,resource_type,resource_id,created_at,id) COMMENT '有界查询当前认证资源事件',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(user_id) REFERENCES sys_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='认证最小审计，不存JWT、授权码、邀请链接、Cookie、密码或密钥';

CREATE TABLE orbit_auth_idempotency (
 session_id CHAR(36) NOT NULL COMMENT '退出请求所对应内部会话UUID，不是登录凭据',
 request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '客户端退出幂等键，作用域限定该会话',
 payload_hash BINARY(32) NOT NULL COMMENT '退出语义SHA256，不保存请求凭据',
 response_json JSON NOT NULL COMMENT '原Ack结果，不包含User资料或Cookie原文',
 created_at DATETIME(3) NOT NULL COMMENT '提交UTC时刻，清理需遵循认证与审计保留约定',
 PRIMARY KEY(session_id,request_key),
 KEY idx_auth_idempotency_retention(created_at,session_id) COMMENT '有界保留清理游标，不扫描主体业务表'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='会话退出幂等回执；重放仍验证原会话归属及CSRF，不恢复会话';
