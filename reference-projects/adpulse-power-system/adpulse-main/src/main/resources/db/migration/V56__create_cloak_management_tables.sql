-- 部署前人工执行：保存GlobalPWA斗篷批量提交幂等状态和本地管理列表。
CREATE TABLE biz_cloak_batch (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '斗篷批次主键',
    request_id VARCHAR(64) NOT NULL COMMENT '一次用户提交意图的幂等键，重试必须复用',
    request_fingerprint CHAR(64) NOT NULL COMMENT '规范化请求SHA-256，用于拒绝同幂等键不同载荷',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID，逻辑关联pm_project.id',
    project_name VARCHAR(255) NOT NULL COMMENT '提交时项目名称快照，同时作为服务商应用名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '批次状态：1调用中，2成功，3明确失败，4结果待核对',
    total_count INT UNSIGNED NOT NULL COMMENT '本批斗篷数量，范围1至100',
    success_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已确认创建成功数量',
    provider_message VARCHAR(1000) NULL COMMENT '服务商返回的非敏感提示信息',
    error_message VARCHAR(1000) NULL COMMENT '安全错误摘要，不保存Token或完整响应',
    requested_by BIGINT UNSIGNED NOT NULL COMMENT '提交人用户ID',
    started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '本次开始调用时间',
    finished_at DATETIME(3) NULL COMMENT '本次完成时间',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_cloak_batch_request_deleted (request_id, deleted_at)
        COMMENT '保证一个有效幂等请求只有一个批次',
    KEY idx_cloak_batch_project_created (project_id, created_at, deleted_at)
        COMMENT '按项目查询最近提交批次',
    KEY idx_cloak_batch_status_updated (status, updated_at, deleted_at)
        COMMENT '定位调用中或待核对批次',
    CONSTRAINT ck_cloak_batch_status CHECK (status IN (1, 2, 3, 4))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='GlobalPWA斗篷批量提交幂等状态与执行结果';

CREATE TABLE biz_cloak (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地斗篷记录主键',
    batch_id BIGINT UNSIGNED NOT NULL COMMENT '所属批次ID，逻辑关联biz_cloak_batch.id',
    provider_cloak_id BIGINT UNSIGNED NULL COMMENT '服务商斗篷主键；批量接口不返回时暂为空，后续对账补齐',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID，逻辑关联pm_project.id',
    project_name VARCHAR(255) NOT NULL COMMENT '创建时项目名称快照',
    agency_line_id BIGINT UNSIGNED NOT NULL COMMENT '代理线ID，逻辑关联pm_agency_line.id',
    agency_line_name VARCHAR(255) NOT NULL COMMENT '创建时代理线名称快照',
    name VARCHAR(255) NOT NULL COMMENT '服务商应用名称，当前取项目名称',
    really_url VARCHAR(1000) NOT NULL COMMENT '真实投放链接，由代理线投放链接生成',
    virtual_url VARCHAR(1000) NOT NULL COMMENT '审核人员访问的审核链接',
    ad_url VARCHAR(100) NOT NULL COMMENT '推广链接前缀，仅小写字母和数字',
    gen_id VARCHAR(100) NOT NULL COMMENT '服务商域名ID',
    gen_domain VARCHAR(255) NOT NULL COMMENT '服务商根域名快照',
    promotion_url VARCHAR(1000) NOT NULL COMMENT '根据ad_url与gen_domain生成的完整推广链接',
    type TINYINT NOT NULL COMMENT '斗篷模式：0全关，1全开，2斗篷',
    country VARCHAR(500) NULL COMMENT '服务商投放地区代码，多个值以逗号分隔',
    country_label VARCHAR(255) NULL COMMENT '投放地区展示名称快照',
    lang_status TINYINT NOT NULL COMMENT '空语言请求：0禁止，1允许',
    pc_status TINYINT NOT NULL COMMENT 'PC端：0禁止，1允许',
    vpn_status TINYINT NOT NULL COMMENT 'VPN：0禁止，1允许',
    provider_link_id VARCHAR(128) NULL COMMENT '服务商推广链接ID，对账后补齐',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '本地状态：0待确认，1创建成功，2明确失败，3待核对',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后更新人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，软删除为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_cloak_batch_line_deleted (batch_id, agency_line_id, deleted_at)
        COMMENT '同一批次同一代理线只能创建一条斗篷',
    UNIQUE KEY uk_cloak_prefix_domain_deleted (ad_url, gen_id, deleted_at)
        COMMENT '同一服务商域名下的有效推广链接前缀不可重复',
    UNIQUE KEY uk_cloak_provider_deleted (provider_cloak_id, deleted_at)
        COMMENT '服务商斗篷主键补齐后不可重复',
    KEY idx_cloak_project_created (project_id, created_at, deleted_at)
        COMMENT '按项目筛选斗篷列表',
    KEY idx_cloak_batch_status (batch_id, status, deleted_at)
        COMMENT '按批次更新和核对斗篷结果',
    KEY idx_cloak_country_created (country, created_at, deleted_at)
        COMMENT '按投放地区筛选列表',
    CONSTRAINT ck_cloak_type CHECK (type IN (0, 1, 2)),
    CONSTRAINT ck_cloak_lang_status CHECK (lang_status IN (0, 1)),
    CONSTRAINT ck_cloak_pc_status CHECK (pc_status IN (0, 1)),
    CONSTRAINT ck_cloak_vpn_status CHECK (vpn_status IN (0, 1)),
    CONSTRAINT ck_cloak_status CHECK (status IN (0, 1, 2, 3))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    COMMENT='本地斗篷管理记录与GlobalPWA创建参数快照';
