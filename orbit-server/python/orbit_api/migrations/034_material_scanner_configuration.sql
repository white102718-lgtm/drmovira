-- 正式素材扫描配置为租户单例；不改变多BM/模型等既有多配置语义。
-- 已有同租户重复扫描配置将使唯一索引建立失败，保留原数据，由运维显式处理。
ALTER TABLE orbit_system_configuration
 ADD scanner_singleton_tenant CHAR(36) GENERATED ALWAYS AS
 (CASE WHEN section='MATERIAL_SCANNER' THEN tenant_id ELSE NULL END) STORED
 COMMENT '素材扫描配置单例键；其他section为NULL允许多条',
 ADD UNIQUE KEY uq_material_scanner_singleton(scanner_singleton_tenant),
 ADD UNIQUE KEY uq_configuration_tenant_identity(tenant_id,id);

-- 旧显式隔离fixture证明保持NULL来源，不补造正式租户配置来源。
ALTER TABLE orbit_material_scan_runtime_proof
 ADD configuration_id CHAR(36) NULL COMMENT '正式消费者实际锁定的本租户扫描配置UUID；历史fixture为空',
 ADD configuration_revision BIGINT NULL COMMENT '扫描前后复核的完整配置版本，非profile版本',
 ADD CONSTRAINT ck_material_runtime_configuration CHECK
 ((configuration_id IS NULL AND configuration_revision IS NULL) OR
  (configuration_id IS NOT NULL AND configuration_revision IS NOT NULL AND configuration_revision>0)),
 ADD CONSTRAINT fk_material_runtime_configuration FOREIGN KEY(tenant_id,configuration_id)
 REFERENCES orbit_system_configuration(tenant_id,id);
