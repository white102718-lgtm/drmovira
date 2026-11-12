-- 产品/总代已退出业务流程；旧关联仅作历史保留，不删除审计或来源记录。
-- 先执行迁移，再部署不再写入这两个引用的应用。
ALTER TABLE orbit_channel
 MODIFY product_id CHAR(36) NULL COMMENT '已退役产品引用，仅保留历史兼容',
 MODIFY agent_id CHAR(36) NULL COMMENT '已退役总代引用，仅保留历史兼容';
