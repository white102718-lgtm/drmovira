-- 部署前人工执行：投放日报属于 main 业务服务，附件复用 system 的通用文件。
CREATE TABLE IF NOT EXISTS biz_delivery_report (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '日报主键',
    report_date DATE NOT NULL COMMENT 'Doris date 对应的业务日期，不另行转换时区',
    reporter_id BIGINT UNSIGNED NOT NULL COMMENT '当前会话用户ID，历史归属不随英文名变更',
    reporter_english_name VARCHAR(64) NOT NULL COMMENT '保存时用于匹配placer_id的英文名',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联pm_project，由服务层校验',
    project_name VARCHAR(255) NOT NULL COMMENT '保存时项目名称',
    agency_line_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联pm_agency_line，由服务层校验所属项目',
    agency_line_name VARCHAR(255) NOT NULL COMMENT '保存时代理线名称',
    platform VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '媒体平台分组值',
    metrics_json JSON NOT NULL COMMENT '固定人工指标；金额为USD，不含平台实际消耗',
    account_ids_json JSON NOT NULL COMMENT '去重的来源账户ID数组',
    campaign_ids_json JSON NOT NULL COMMENT '去重的来源campaign ID数组',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '首次保存时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最近保存时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_owner_day_line (reporter_id, report_date, project_id, agency_line_id, platform, deleted_at) COMMENT '防止自动行、补录行和重复保存造成重复计入',
    KEY idx_delivery_project (project_id, report_date) COMMENT '项目维度查询',
    KEY idx_delivery_line (agency_line_id, report_date) COMMENT '代理线维度查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投放日报本人记录，无审批、无平台金额快照';

CREATE TABLE IF NOT EXISTS biz_delivery_report_attachment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '附件关联主键',
    report_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联biz_delivery_report',
    file_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联sys_file；须为本人上传图片',
    sort_order INT NOT NULL COMMENT '截图展示顺序，每行最多5张',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '绑定时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    KEY idx_delivery_attachment_report (report_id, deleted_at, sort_order) COMMENT '按日报读取截图',
    KEY idx_delivery_attachment_file (file_id, deleted_at) COMMENT '检查文件引用'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投放日报截图关联；服务层限制本人、图片类型及5张上限';
