-- 资源可用性证据由真实只读采集/权威registry提供；本迁移不植入默认有效证据。
CREATE TABLE orbit_account_identity_evidence (
 tenant_id CHAR(36) NOT NULL COMMENT '可信采集租户UUID',
 id CHAR(36) NOT NULL COMMENT '不可猜测的独立证据UUID',
 account_id CHAR(36) NOT NULL COMMENT '证据核验的目标账户业务UUID',
 account_revision BIGINT NOT NULL COMMENT '核验时账户授权与绑定版本，变化后不得沿用',
 source_config_id CHAR(36) NOT NULL COMMENT '已验证META_BM来源配置UUID，不含Token',
 source_config_revision BIGINT NOT NULL COMMENT '核验时来源版本，配置变化使旧证据失效',
 capability_version VARCHAR(64) NOT NULL COMMENT '资源能力权威核验版本，不等于Agent版本或随意字符串',
 payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '规范原AccountIdentities正文SHA256，防替换资源或usable',
 observed_at DATETIME(3) NOT NULL COMMENT '实际完整只读观察UTC时刻，不以当前时间填补',
 complete BOOLEAN NOT NULL DEFAULT 0 COMMENT '全部分页与目标账户资源核验完整，缺页不得为真',
 verified BOOLEAN NOT NULL DEFAULT 0 COMMENT '权威采集证据已验证；没有生产registry时保持假',
 revoked_at DATETIME(3) NULL COMMENT '已知能力撤销UTC时刻，非NULL立即阻断旧true',
 credential_expires_at DATETIME(3) NULL COMMENT '已知凭据到期UTC；NULL不发明默认TTL',
 evidence_ref VARCHAR(255) NOT NULL COMMENT '不含凭据的受控审计证据引用',
 created_at DATETIME(3) NOT NULL COMMENT '真实证据登记UTC时刻',
 PRIMARY KEY(tenant_id,id),
 KEY idx_identity_evidence_account(tenant_id,account_id,observed_at,id),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='账户身份只读能力可信证据，尚无生产registry写入器，不开放手工假验证接口';

CREATE TABLE orbit_account_identity_history (
 tenant_id CHAR(36) NOT NULL COMMENT '身份快照租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '目标账户业务UUID',
 revision BIGINT NOT NULL COMMENT '只追加身份快照版本',
 evidence_id CHAR(36) NOT NULL COMMENT '同租户可信采集证据UUID',
 capability_version VARCHAR(64) NOT NULL COMMENT '原响应能力版本的冻结值',
 observed_at DATETIME(3) NOT NULL COMMENT '实际观察UTC时刻',
 resource_count INT NOT NULL COMMENT '完整资源条数，0只允许完整成功观察',
 request_id CHAR(36) NOT NULL COMMENT '原子审计关联请求UUID',
 created_at DATETIME(3) NOT NULL COMMENT '本地发布UTC时刻，不冒充观察时间',
 PRIMARY KEY(tenant_id,account_id,revision),
 FOREIGN KEY(tenant_id,evidence_id) REFERENCES orbit_account_identity_evidence(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='身份观察只追加版本，不回写旧历史';

CREATE TABLE orbit_account_identity_head (
 tenant_id CHAR(36) NOT NULL COMMENT '当前身份快照租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '当前目标账户UUID',
 revision BIGINT NOT NULL COMMENT '已原子发布的当前历史版本',
 PRIMARY KEY(tenant_id,account_id),
 FOREIGN KEY(tenant_id,account_id,revision)
 REFERENCES orbit_account_identity_history(tenant_id,account_id,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='身份观察当前头，未建行即未同步';

CREATE TABLE orbit_account_identity_resource (
 tenant_id CHAR(36) NOT NULL COMMENT '资源观察所属租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '已核验可用性的目标账户UUID',
 revision BIGINT NOT NULL COMMENT '只追加观察版本',
 kind VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'PAGE、PIXEL或APPLICATION，BM不伪装成资源',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '平台ASCII数字ID，保留前导零',
 name VARCHAR(255) NOT NULL COMMENT '原始资源名称，允许空名但不得截断',
 usable BOOLEAN NOT NULL COMMENT '仅表示该观察时刻目标账户可用性，不是未来写授权',
 reason_code VARCHAR(64) NULL COMMENT '不可用/限制原因；没有说明保持NULL',
 PRIMARY KEY(tenant_id,account_id,revision,kind,external_id),
 FOREIGN KEY(tenant_id,account_id,revision)
 REFERENCES orbit_account_identity_history(tenant_id,account_id,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='按观察版本批量读取资源，禁止每资源N加一查询';
