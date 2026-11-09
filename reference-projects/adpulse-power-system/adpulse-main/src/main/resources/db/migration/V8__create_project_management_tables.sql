CREATE TABLE pm_project (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '项目ID',
    project_code VARCHAR(50) NOT NULL COMMENT '全局唯一项目编码',
    project_name VARCHAR(100) NOT NULL COMMENT '项目名称',
    responsible_team VARCHAR(100) NOT NULL COMMENT '负责团队字典值',
    am_user_id BIGINT UNSIGNED NULL COMMENT 'AM用户ID',
    am_name VARCHAR(100) NULL COMMENT 'AM姓名快照',
    delivery_leader_id BIGINT UNSIGNED NULL COMMENT '投放负责人用户ID',
    delivery_leader_name VARCHAR(100) NULL COMMENT '投放负责人姓名快照',
    is_outsourced TINYINT NOT NULL DEFAULT 0 COMMENT '是否外包：1是，0否',
    priority VARCHAR(20) NOT NULL COMMENT '优先级字典值',
    service_fee_percent DECIMAL(5, 2) NOT NULL COMMENT '服务费百分比',
    status VARCHAR(20) NOT NULL COMMENT '项目状态字典值',
    product_info VARCHAR(500) NOT NULL COMMENT '产品信息',
    customer_daily_report_url VARCHAR(1000) NULL COMMENT '客户日报链接',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_project_code_deleted (project_code, deleted_at),
    UNIQUE KEY uk_pm_project_name_deleted (project_name, deleted_at),
    KEY idx_pm_project_status (status, deleted_at),
    KEY idx_pm_project_am_user (am_user_id, deleted_at),
    KEY idx_pm_project_delivery_leader (delivery_leader_id, deleted_at),
    CONSTRAINT ck_pm_project_outsourced CHECK (is_outsourced IN (0, 1)),
    CONSTRAINT ck_pm_project_service_fee CHECK (
        service_fee_percent >= 0 AND service_fee_percent <= 100
    )
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目表';

CREATE TABLE pm_project_platform (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID',
    platform_value VARCHAR(100) NOT NULL COMMENT '投放平台字典值',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_project_platform_deleted (project_id, platform_value, deleted_at),
    KEY idx_pm_project_platform_value (platform_value, project_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目投放平台关系表';

CREATE TABLE pm_project_region (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID',
    region_value VARCHAR(100) NOT NULL COMMENT '地区字典值',
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_project_region_deleted (project_id, region_value, deleted_at),
    KEY idx_pm_project_region_value (region_value, project_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目投放地区关系表';

CREATE TABLE pm_project_kpi (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID',
    metric_value VARCHAR(100) NOT NULL COMMENT 'KPI指标字典值',
    comparator VARCHAR(4) NOT NULL COMMENT '比较符',
    target_value DECIMAL(18, 4) NOT NULL COMMENT '目标值',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_pm_project_kpi_project (project_id, deleted_at, sort_order),
    CONSTRAINT ck_pm_project_kpi_comparator CHECK (comparator IN ('>=', '<=', '=')),
    CONSTRAINT ck_pm_project_kpi_target CHECK (target_value >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目KPI要求表';

CREATE TABLE pm_agency_line (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '代理线ID',
    project_id BIGINT UNSIGNED NULL COMMENT '所属项目ID',
    request_id VARCHAR(200) NULL COMMENT '创建幂等键',
    line_name VARCHAR(80) NOT NULL COMMENT '代理线名称',
    platform_value VARCHAR(100) NOT NULL COMMENT '投放平台字典值',
    delivery_url VARCHAR(1000) NULL COMMENT '投放链接',
    page_id VARCHAR(255) NULL COMMENT '广告平台主页ID',
    pixel_name VARCHAR(255) NULL COMMENT '像素名称',
    optimizer_id BIGINT UNSIGNED NOT NULL COMMENT '优化师用户ID',
    optimizer_name VARCHAR(100) NOT NULL COMMENT '优化师姓名快照',
    created_by BIGINT UNSIGNED NULL,
    updated_by BIGINT UNSIGNED NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pm_agency_line_name_deleted (line_name, deleted_at),
    UNIQUE KEY uk_pm_agency_line_request_deleted (request_id, deleted_at),
    KEY idx_pm_agency_line_project (project_id, deleted_at),
    KEY idx_pm_agency_line_platform (platform_value, deleted_at),
    KEY idx_pm_agency_line_optimizer (optimizer_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '项目代理线表';

INSERT INTO sys_dict_type (dict_code, dict_name, status, remark)
SELECT 'PROJECT_REGION', '项目投放地区', 1, '项目管理投放地区选项'
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_type WHERE dict_code = 'PROJECT_REGION' AND deleted_at = 0
);

SET @project_region_type_id = (
    SELECT id FROM sys_dict_type
    WHERE dict_code = 'PROJECT_REGION' AND deleted_at = 0
    ORDER BY id DESC LIMIT 1
);

INSERT INTO sys_dict_item (dict_type_id, item_value, item_label, sort_order, status)
SELECT @project_region_type_id, seed.item_value, seed.item_label, seed.sort_order, 1
FROM (
    SELECT 'US' AS item_value, '美国' AS item_label, 10 AS sort_order
    UNION ALL SELECT 'JP', '日本', 20
    UNION ALL SELECT 'GB', '英国', 30
    UNION ALL SELECT 'DE', '德国', 40
    UNION ALL SELECT 'SG', '新加坡', 50
) seed
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_item item
    WHERE item.dict_type_id = @project_region_type_id
      AND item.item_value = seed.item_value
      AND item.deleted_at = 0
);
