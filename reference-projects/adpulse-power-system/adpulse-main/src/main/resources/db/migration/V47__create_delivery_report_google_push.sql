-- 部署前人工执行：为每个项目配置唯一的Google日报模板，并记录可重试的推送批次。
CREATE TABLE biz_delivery_report_google_template (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Google日报模板主键',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '适用项目ID，逻辑关联pm_project，由服务层校验',
    template_name VARCHAR(255) NOT NULL COMMENT '模板展示名称',
    google_account_id BIGINT UNSIGNED NULL COMMENT '历史OAuth账号ID；服务账户模式不再写入',
    spreadsheet_id VARCHAR(255) NOT NULL COMMENT 'Google Spreadsheet稳定标识',
    spreadsheet_name VARCHAR(500) NOT NULL COMMENT 'Google Spreadsheet展示名称快照',
    sheet_id VARCHAR(64) NOT NULL COMMENT '目标Sheet稳定标识',
    sheet_title VARCHAR(255) NOT NULL COMMENT '目标Sheet页签名称快照',
    header_row INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '目标表头所在行，从1开始',
    field_mappings JSON NOT NULL COMMENT '系统字段到目标列字母、表头和必填规则的映射数组',
    enable_flag TINYINT NOT NULL DEFAULT 1 COMMENT '模板状态：1启用，0停用',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_google_template_project (project_id, deleted_at)
        COMMENT '一个有效项目只能配置一个Google日报模板',
    KEY idx_delivery_google_template_account (google_account_id, enable_flag, deleted_at)
        COMMENT '按Google授权账号检查有效模板'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    COMMENT='投放日报到项目Google Sheet的一对一写入模板';

CREATE TABLE biz_delivery_report_google_push_batch (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '推送批次主键',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '批次状态：0待执行，1执行中，2成功，3部分失败，4失败',
    total_count INT UNSIGNED NOT NULL COMMENT '批次日报总数',
    success_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '成功写入数量',
    failed_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '写入失败数量',
    requested_by BIGINT UNSIGNED NOT NULL COMMENT '发起推送的用户ID',
    error_message VARCHAR(1000) NULL COMMENT '批次级安全错误摘要，不保存令牌或完整表格数据',
    started_at DATETIME(3) NULL COMMENT '开始执行时间',
    finished_at DATETIME(3) NULL COMMENT '完成执行时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间',
    PRIMARY KEY (id),
    KEY idx_delivery_google_batch_status (status, created_at)
        COMMENT '后台任务按状态和创建时间领取批次',
    KEY idx_delivery_google_batch_user (requested_by, created_at)
        COMMENT '查询当前用户最近推送结果'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    COMMENT='投放日报Google推送批次日志，保留用于查询与失败重试';

CREATE TABLE biz_delivery_report_google_push_item (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '推送明细主键',
    batch_id BIGINT UNSIGNED NOT NULL COMMENT '推送批次ID，逻辑关联推送批次',
    report_id BIGINT UNSIGNED NOT NULL COMMENT '投放日报ID，作为Google端幂等标识',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '日报项目ID快照',
    template_id BIGINT UNSIGNED NOT NULL COMMENT '推送时使用的模板ID快照',
    google_account_id BIGINT UNSIGNED NULL COMMENT '历史OAuth账号ID；服务账户模式不再写入',
    spreadsheet_id VARCHAR(255) NOT NULL COMMENT '目标Spreadsheet稳定标识快照',
    sheet_id VARCHAR(64) NOT NULL COMMENT '目标Sheet稳定标识快照，用于页签改名后重新定位',
    sheet_title VARCHAR(255) NOT NULL COMMENT '目标Sheet页签名称快照',
    header_row INT UNSIGNED NOT NULL COMMENT '推送时校验的目标表头行号',
    field_values JSON NOT NULL COMMENT '按Google列字母保存的待写入值快照',
    target_headers JSON NOT NULL COMMENT '按Google列字母保存的目标表头快照，防止列移动后写错',
    unique_key_columns JSON NOT NULL COMMENT '用于匹配更新目标行的联合唯一列字母数组',
    report_id_column VARCHAR(8) NULL COMMENT '历史记录ID目标列；联合唯一键模式不再写入',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '明细状态：0待执行，1执行中，2成功，3失败',
    target_row INT UNSIGNED NULL COMMENT '成功写入或更新的Google行号',
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已执行尝试次数',
    error_message VARCHAR(1000) NULL COMMENT '单条安全错误摘要',
    started_at DATETIME(3) NULL COMMENT '本次开始执行时间',
    finished_at DATETIME(3) NULL COMMENT '本次完成执行时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_google_batch_report (batch_id, report_id)
        COMMENT '同一批次内一条日报只能出现一次',
    KEY idx_delivery_google_item_batch_status (batch_id, status, id)
        COMMENT '按批次读取和执行推送明细',
    KEY idx_delivery_google_item_report (report_id, status, created_at)
        COMMENT '追踪单条日报的历史推送结果'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    COMMENT='投放日报Google推送明细与不可变写入快照';
