-- 计划替换/取消按真实业务引用键反查；保留既有素材方向索引供归档和保留期检查。
ALTER TABLE orbit_material_reference
 ADD KEY idx_material_reference_resource(tenant_id,kind,resource_id,active,asset_id,id)
 COMMENT '租户业务键活跃引用有界定位与素材UUID顺序扫描';
