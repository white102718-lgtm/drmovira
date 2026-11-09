-- 人工审核后在新应用部署前执行；不重置历史任务，重置脚本位于 scripts/dev。
-- 明细包含访问令牌，按有序的类型化明细列表加密保存，不用于 SQL 条件查询。
ALTER TABLE biz_delivery_task
    ADD COLUMN items_ciphertext LONGTEXT NULL COMMENT '投放明细列表AES-GCM密文，包含类型、像素、令牌、测试代码、渠道、链接和投手ID';

-- 原表继续承担按投手交付及验收的执行状态；旧线路数只保留历史兼容，不再参与新业务。
ALTER TABLE biz_delivery_task_allocation
    DROP CHECK ck_delivery_allocation_count,
    MODIFY team_code VARCHAR(30) NOT NULL DEFAULT '' COMMENT '历史团队编码，新流程不再填写',
    MODIFY pwa_line_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已废弃，仅保留历史PWA线路数',
    MODIFY h5_line_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已废弃，仅保留历史H5线路数';
