-- 010历史保持不变：标签/分类名称须租户内同类型唯一，分组不改变名称唯一性。
-- 首先原子创建正确唯一索引：MySQL会扫描并验证全部已有行。
-- 若同租户同类型存在重名（即使分组不同），此语句以1062失败，原表数据和旧索引保持；
-- 运维必须先确认冲突归属，禁止本迁移自动删除、改名或合并关联。
ALTER TABLE orbit_material_taxonomy
 ADD UNIQUE KEY uq_material_taxonomy_kind_name(tenant_id,kind,name) COMMENT '租户内同类名称唯一；分组不允许绕过',
 ADD KEY idx_material_taxonomy_kind_page(tenant_id,kind,id) COMMENT '无状态筛选时按UUID键集分页，避免state中间列阻碍顺序';

-- 仅在正确唯一索引创建成功后，移除010错误的分组唯一约束。
ALTER TABLE orbit_material_taxonomy DROP INDEX uq_material_taxonomy_name;
