-- 独立不可变业务时点快照；当前alias变更不回填历史，不修改原Account响应schema。
CREATE TABLE orbit_account_vendor_alias_snapshot (
 tenant_id CHAR(36) NOT NULL COMMENT '由原业务动作可信上下文确定的租户UUID',
 resource_type VARCHAR(24) NOT NULL COMMENT 'IMPORT受理、ACCOUNT_BINDING绑定、IMPORT_ASSIGNMENT初始归属或ASSIGNMENT分配',
 resource_id CHAR(36) NOT NULL COMMENT '对应导入批次、账户或归属区间UUID',
 resource_revision BIGINT NOT NULL COMMENT '发生业务事务时的对象版本，不允许覆盖同版本快照',
 vendor_id CHAR(36) NOT NULL COMMENT '已通过原动作归属范围验证的户商UUID',
 vendor_revision BIGINT NOT NULL COMMENT '当时最小引用资料版本，不能以后用最新版本回填',
 vendor_name_snapshot VARCHAR(255) NOT NULL COMMENT '当时完整资料名称，与真实代称严格分离',
 alias VARCHAR(30) NULL COMMENT '当时真实代称；未设置或清空保留NULL，不从name推断',
 alias_revision BIGINT NOT NULL COMMENT '当时真实alias版本；未建记录时按源助手的明确UNSET版本',
 alias_source VARCHAR(16) NOT NULL COMMENT 'VENDOR_ALIAS真实源或UNSET尚未设置，历史缺行另表明未采集',
 request_id CHAR(36) NOT NULL COMMENT '同事务审计关联请求UUID，不包含凭据',
 captured_at DATETIME(3) NOT NULL COMMENT '实际业务事务捕获UTC时刻；不伪造旧历史观测',
 PRIMARY KEY(tenant_id,resource_type,resource_id,resource_revision),
 KEY idx_account_alias_vendor(tenant_id,vendor_id,captured_at,resource_id)
   COMMENT '户商业务快照按UTC时刻与UUID稳定检索'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='账户业务时点真实户商代称只追加快照，不自动回填既有对象';
