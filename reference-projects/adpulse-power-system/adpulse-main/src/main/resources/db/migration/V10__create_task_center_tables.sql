CREATE TABLE biz_task (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    task_code VARCHAR(50) NOT NULL COMMENT '任务展示编号',
    task_type VARCHAR(20) NOT NULL COMMENT '任务类型：DELIVERY/MATERIAL',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '所属项目ID，逻辑关联pm_project.id',
    title VARCHAR(200) NOT NULL COMMENT '任务标题',
    description TEXT NULL COMMENT '任务说明',
    creator_id BIGINT UNSIGNED NOT NULL COMMENT '任务创建者用户ID，同时为默认验收人',
    creator_name VARCHAR(100) NOT NULL COMMENT '任务创建者姓名快照',
    owner_id BIGINT UNSIGNED NOT NULL COMMENT '任务总负责人用户ID',
    owner_name VARCHAR(100) NOT NULL COMMENT '任务总负责人姓名快照',
    priority VARCHAR(10) NOT NULL DEFAULT 'P2' COMMENT '任务优先级：P0/P1/P2/P3',
    status VARCHAR(30) NOT NULL COMMENT '任务状态：PENDING_CONFIRMATION/PROCESSING/PENDING_ACCEPTANCE/COMPLETED/WITHDRAWN',
    due_at DATETIME(3) NULL COMMENT '任务截止时间，UTC',
    accepted_at DATETIME(3) NULL COMMENT '负责人确认接收时间，UTC',
    completed_at DATETIME(3) NULL COMMENT '创建者验收通过时间，UTC',
    withdrawn_at DATETIME(3) NULL COMMENT '任务撤回时间，UTC',
    withdraw_reason VARCHAR(500) NULL COMMENT '任务撤回原因',
    version INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '乐观锁版本号',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建操作用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间，UTC',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间，UTC',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0表示有效，其他值为软删除Unix毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_biz_task_code_deleted (task_code, deleted_at),
    KEY idx_biz_task_owner_status (owner_id, status, deleted_at, updated_at),
    KEY idx_biz_task_creator_status (creator_id, status, deleted_at, updated_at),
    KEY idx_biz_task_project_type (project_id, task_type, deleted_at),
    KEY idx_biz_task_status_due (status, due_at, deleted_at),
    CONSTRAINT ck_biz_task_type CHECK (task_type IN ('DELIVERY', 'MATERIAL')),
    CONSTRAINT ck_biz_task_priority CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    CONSTRAINT ck_biz_task_status CHECK (status IN ('PENDING_CONFIRMATION', 'PROCESSING', 'PENDING_ACCEPTANCE', 'COMPLETED', 'WITHDRAWN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='任务公共主表';

CREATE TABLE biz_delivery_task (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '投放任务详情ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '任务ID，逻辑关联biz_task.id',
    product_url VARCHAR(1000) NOT NULL COMMENT '投放产品或落地页地址',
    region_value VARCHAR(100) NOT NULL COMMENT '投放地区字典值',
    target_description VARCHAR(1000) NOT NULL COMMENT '投放目标说明',
    planned_start_at DATETIME(3) NOT NULL COMMENT '计划开始投放时间，UTC',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_task_deleted (task_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投放任务专业详情';

CREATE TABLE biz_delivery_task_platform (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL COMMENT '投放任务ID',
    platform_value VARCHAR(100) NOT NULL COMMENT '投放平台字典值',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_task_platform_deleted (task_id, platform_value, deleted_at),
    KEY idx_delivery_platform_value (platform_value, task_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投放任务平台关系';

CREATE TABLE biz_delivery_task_allocation (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '团队线路分配ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '投放任务ID',
    team_code VARCHAR(30) NOT NULL COMMENT '参与团队编码：MP/MAD/MY/Firefly',
    team_owner_id BIGINT UNSIGNED NOT NULL COMMENT '团队负责人用户ID',
    team_owner_name VARCHAR(100) NOT NULL COMMENT '团队负责人姓名快照',
    pwa_line_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'PWA计划线路数',
    h5_line_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'H5计划线路数',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_task_team_deleted (task_id, team_code, deleted_at),
    KEY idx_delivery_allocation_owner (team_owner_id, deleted_at, task_id),
    CONSTRAINT ck_delivery_allocation_count CHECK (pwa_line_count + h5_line_count > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投放任务参与团队与线路数量分配';

CREATE TABLE biz_material_task (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '素材任务详情ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '任务ID，逻辑关联biz_task.id',
    demand_type VARCHAR(50) NOT NULL COMMENT '素材需求类型字典值',
    quantity INT UNSIGNED NOT NULL COMMENT '要求交付的素材总数',
    add_to_library TINYINT NOT NULL DEFAULT 1 COMMENT '验收通过后是否进入素材库：1是，0否',
    country_tags JSON NULL COMMENT '国家标签快照',
    theme_tags JSON NULL COMMENT '主题标签快照',
    gameplay_tags JSON NULL COMMENT '玩法标签快照',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_material_task_deleted (task_id, deleted_at),
    CONSTRAINT ck_material_task_quantity CHECK (quantity > 0),
    CONSTRAINT ck_material_task_library CHECK (add_to_library IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='素材任务专业详情';

CREATE TABLE biz_material_task_size (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id BIGINT UNSIGNED NOT NULL COMMENT '素材任务ID',
    size_value VARCHAR(100) NOT NULL COMMENT '素材尺寸或规格值',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_material_task_size_deleted (task_id, size_value, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='素材任务尺寸关系';

CREATE TABLE biz_material_task_reference (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '素材任务外部参考资料ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '素材任务ID',
    reference_name VARCHAR(255) NOT NULL COMMENT '外部参考资料名称',
    reference_url VARCHAR(2000) NOT NULL COMMENT '外部参考链接',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_material_reference_task (task_id, deleted_at, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='素材任务外部参考链接';

CREATE TABLE biz_delivery_task_submission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '投放交付ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '投放任务ID',
    version_no INT UNSIGNED NOT NULL COMMENT '任务内交付版本号',
    request_id VARCHAR(64) NOT NULL COMMENT '提交请求幂等键',
    submitted_by BIGINT UNSIGNED NOT NULL COMMENT '提交人用户ID',
    submitted_by_name VARCHAR(100) NOT NULL COMMENT '提交人姓名快照',
    platform_value VARCHAR(100) NOT NULL COMMENT '实际投放平台',
    ad_account_id VARCHAR(100) NOT NULL COMMENT '实际广告账户稳定ID',
    ad_account_name VARCHAR(255) NULL COMMENT '广告账户名称快照',
    actual_start_at DATETIME(3) NOT NULL COMMENT '实际开始投放时间，UTC',
    actual_budget DECIMAL(18, 4) NOT NULL COMMENT '实际投放预算',
    currency CHAR(3) NOT NULL COMMENT 'ISO 4217币种代码',
    campaign_count INT UNSIGNED NOT NULL COMMENT 'Campaign数量',
    adset_count INT UNSIGNED NOT NULL COMMENT 'Ad Set数量',
    ad_count INT UNSIGNED NOT NULL COMMENT 'Ad数量',
    delivery_status VARCHAR(20) NOT NULL COMMENT '投放状态：ACTIVE/PARTIAL/PAUSED/FAILED',
    exception_note VARCHAR(1000) NULL COMMENT '异常情况说明',
    submission_note TEXT NULL COMMENT '交付备注',
    submitted_at DATETIME(3) NOT NULL COMMENT '提交时间，UTC',
    review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '验收状态：PENDING/ACCEPTED/REJECTED',
    reviewer_id BIGINT UNSIGNED NULL COMMENT '验收人用户ID',
    reviewer_name VARCHAR(100) NULL COMMENT '验收人姓名快照',
    review_comment VARCHAR(1000) NULL COMMENT '验收意见或打回原因',
    reviewed_at DATETIME(3) NULL COMMENT '验收时间，UTC',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_submission_version_deleted (task_id, version_no, deleted_at),
    UNIQUE KEY uk_delivery_submission_request_deleted (request_id, deleted_at),
    KEY idx_delivery_submission_review (task_id, review_status, deleted_at),
    CONSTRAINT ck_delivery_submission_status CHECK (delivery_status IN ('ACTIVE', 'PARTIAL', 'PAUSED', 'FAILED')),
    CONSTRAINT ck_delivery_submission_review CHECK (review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT ck_delivery_submission_budget CHECK (actual_budget > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投放任务交付及验收记录';

CREATE TABLE biz_delivery_submission_object (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    submission_id BIGINT UNSIGNED NOT NULL COMMENT '投放交付ID',
    object_type VARCHAR(20) NOT NULL COMMENT '广告对象类型：CAMPAIGN/AD_SET/AD',
    object_id VARCHAR(200) NOT NULL COMMENT '平台广告对象ID',
    object_name VARCHAR(255) NULL COMMENT '对象名称快照',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_delivery_submission_object_deleted (submission_id, object_type, object_id, deleted_at),
    KEY idx_delivery_object_submission (submission_id, deleted_at, sort_order),
    CONSTRAINT ck_delivery_object_type CHECK (object_type IN ('CAMPAIGN', 'AD_SET', 'AD'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='投放交付关联的实际广告对象';

CREATE TABLE biz_material_task_submission (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '素材交付ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '素材任务ID',
    version_no INT UNSIGNED NOT NULL COMMENT '任务内交付版本号',
    request_id VARCHAR(64) NOT NULL COMMENT '提交请求幂等键',
    submitted_by BIGINT UNSIGNED NOT NULL COMMENT '提交人用户ID',
    submitted_by_name VARCHAR(100) NOT NULL COMMENT '提交人姓名快照',
    delivered_quantity INT UNSIGNED NOT NULL COMMENT '本次交付素材数量',
    submission_note TEXT NULL COMMENT '交付说明',
    submitted_at DATETIME(3) NOT NULL COMMENT '提交时间，UTC',
    review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' COMMENT '验收状态：PENDING/ACCEPTED/REJECTED',
    reviewer_id BIGINT UNSIGNED NULL COMMENT '验收人用户ID',
    reviewer_name VARCHAR(100) NULL COMMENT '验收人姓名快照',
    review_comment VARCHAR(1000) NULL COMMENT '验收意见或打回原因',
    reviewed_at DATETIME(3) NULL COMMENT '验收时间，UTC',
    library_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUIRED' COMMENT '素材入库状态：NOT_REQUIRED/PENDING/IMPORTED/FAILED',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_material_submission_version_deleted (task_id, version_no, deleted_at),
    UNIQUE KEY uk_material_submission_request_deleted (request_id, deleted_at),
    KEY idx_material_submission_review (task_id, review_status, deleted_at),
    CONSTRAINT ck_material_submission_quantity CHECK (delivered_quantity > 0),
    CONSTRAINT ck_material_submission_review CHECK (review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT ck_material_submission_library CHECK (library_status IN ('NOT_REQUIRED', 'PENDING', 'IMPORTED', 'FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='素材任务交付及验收记录';

CREATE TABLE biz_task_file_binding (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '任务领域文件绑定关系ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '所属任务ID',
    file_id BIGINT UNSIGNED NOT NULL COMMENT '通用文件ID，逻辑关联sys_file.id',
    target_type VARCHAR(40) NOT NULL COMMENT '绑定目标：DELIVERY_TASK/MATERIAL_TASK/DELIVERY_SUBMISSION/MATERIAL_SUBMISSION',
    target_id BIGINT UNSIGNED NOT NULL COMMENT '绑定目标记录ID',
    usage_type VARCHAR(30) NOT NULL COMMENT '文件用途：ATTACHMENT/REFERENCE/PROOF/DATA/MATERIAL',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '文件展示顺序',
    bound_by BIGINT UNSIGNED NOT NULL COMMENT '执行绑定的用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_file_binding_deleted (file_id, target_type, target_id, usage_type, deleted_at),
    KEY idx_task_file_binding_task (task_id, deleted_at),
    KEY idx_task_file_binding_target (target_type, target_id, deleted_at, sort_order),
    KEY idx_task_file_binding_file (file_id, deleted_at),
    CONSTRAINT ck_task_file_target CHECK (target_type IN ('DELIVERY_TASK', 'MATERIAL_TASK', 'DELIVERY_SUBMISSION', 'MATERIAL_SUBMISSION')),
    CONSTRAINT ck_task_file_usage CHECK (usage_type IN ('ATTACHMENT', 'REFERENCE', 'PROOF', 'DATA', 'MATERIAL'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='任务与通用文件记录的绑定关系';
