-- 部署前人工审核执行；不由应用启动自动迁移。
-- 状态仅标记项目代理线业务进度，不暂停媒体广告、不改变自动投放配置。
-- 历史代理线默认进行中。回滚应用可保留此列，不需要删除历史状态数据。
ALTER TABLE pm_agency_line
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'
        COMMENT '代理线业务状态：active进行中，stopped已停投' AFTER line_name,
    ADD CONSTRAINT chk_pm_agency_line_status CHECK (status IN ('active', 'stopped'));
