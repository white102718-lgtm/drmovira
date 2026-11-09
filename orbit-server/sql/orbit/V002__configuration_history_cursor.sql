-- 配置每个版本仅生成一条审计，唯一约束保证版本游标不丢失记录。
-- 在V001之后执行；历史重复数据须先由管理员核查，不能静默删除。
ALTER TABLE orbit_configuration_audit
    ADD UNIQUE KEY uk_orbit_configuration_audit_revision (tenant_id, config_id, revision)
    COMMENT '租户配置版本唯一，支持变更历史稳定游标分页';
