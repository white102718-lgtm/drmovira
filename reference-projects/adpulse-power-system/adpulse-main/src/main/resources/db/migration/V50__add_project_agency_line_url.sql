-- 项目保存单值代理线业务链接；由用户审核后在部署前手工执行。
ALTER TABLE pm_project
    ADD COLUMN agency_line_url VARCHAR(1000) NULL
        COMMENT '项目代理线链接，支持HTTP或HTTPS地址'
        AFTER customer_daily_report_url;
