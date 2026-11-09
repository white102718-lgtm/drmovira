-- 保存项目代理线 Google Sheet 同步批次和逐行失败原因；由用户审核后手工执行。
CREATE TABLE pm_agency_line_sync_batch (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '代理线同步批次ID',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID，逻辑关联pm_project.id',
    trigger_type VARCHAR(20) NOT NULL COMMENT '触发方式：manual手动、scheduled每小时自动',
    status VARCHAR(20) NOT NULL COMMENT '批次状态：running/success/partial/failed',
    link_snapshot VARCHAR(1000) NOT NULL COMMENT '本批读取的项目代理线链接快照',
    spreadsheet_id VARCHAR(255) NULL COMMENT 'Google Spreadsheet稳定ID',
    sheet_gid VARCHAR(50) NULL COMMENT '链接中指定的Google Sheet gid',
    sheet_title VARCHAR(255) NULL COMMENT '同步时解析到的Google Sheet页签名称',
    total_rows INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '参与校验的非空数据行数',
    success_rows INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '成功新增或更新的行数',
    failed_rows INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '校验或写入失败的行数',
    error_message VARCHAR(1000) NULL COMMENT '批次级失败原因，不保存凭据或Token',
    triggered_by BIGINT UNSIGNED NULL COMMENT '手动触发用户ID；定时同步为空',
    triggered_by_name VARCHAR(100) NULL COMMENT '手动触发用户姓名快照；定时同步为系统',
    started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '批次开始时间',
    finished_at DATETIME(3) NULL COMMENT '批次结束时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0表示有效，其他值为软删除Unix毫秒时间戳',
    PRIMARY KEY (id),
    KEY idx_agency_line_sync_project (project_id, started_at, deleted_at),
    KEY idx_agency_line_sync_status (status, started_at, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '项目代理线Google Sheet同步批次历史';

CREATE TABLE pm_agency_line_sync_failure (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '代理线同步失败明细ID',
    batch_id BIGINT UNSIGNED NOT NULL COMMENT '同步批次ID，逻辑关联pm_agency_line_sync_batch.id',
    sheet_row_number INT UNSIGNED NOT NULL COMMENT 'Google Sheet中的一基行号',
    agency_line_name VARCHAR(80) NULL COMMENT '可识别时保存代理线名称，不保存其他原始单元格',
    failure_reason VARCHAR(1000) NOT NULL COMMENT '脱敏后的失败原因，不保存凭据或Token',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '失败记录创建时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0表示有效，其他值为软删除Unix毫秒时间戳',
    PRIMARY KEY (id),
    KEY idx_agency_line_sync_failure_batch (batch_id, sheet_row_number, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '项目代理线Google Sheet同步逐行失败明细';
