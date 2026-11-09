CREATE TABLE card_station_card (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '卡片本地ID',
    platform VARCHAR(32) NOT NULL COMMENT '卡台平台：photonpay或arrivalx',
    external_card_id VARCHAR(128) NOT NULL COMMENT '第三方卡片稳定标识',
    card_name VARCHAR(255) NULL COMMENT '卡片名称',
    masked_pan VARCHAR(64) NULL COMMENT '脱敏卡号，禁止保存完整卡号',
    card_status VARCHAR(32) NOT NULL COMMENT '第三方卡片状态',
    balance DECIMAL(24, 8) NOT NULL DEFAULT 0 COMMENT '卡片可用余额',
    currency VARCHAR(16) NOT NULL DEFAULT 'USD' COMMENT '余额币种',
    advertisement_account_id VARCHAR(128) NULL COMMENT '关联广告账户稳定标识',
    company_entity VARCHAR(255) NULL COMMENT '公司主体',
    daily_limit DECIMAL(24, 8) NULL COMMENT '日限额',
    monthly_limit DECIMAL(24, 8) NULL COMMENT '月限额',
    transaction_min_amount DECIMAL(24, 8) NULL COMMENT '单笔最低消费限制',
    transaction_max_amount DECIMAL(24, 8) NULL COMMENT '单笔最高消费限制',
    utilization_limit_amount DECIMAL(24, 8) NULL COMMENT '卡台周期限额',
    utilization_limit_preset VARCHAR(32) NULL COMMENT '卡台限额周期',
    period_max_consume_amount DECIMAL(24, 8) NULL COMMENT '周期内日最高消耗',
    provider_payload JSON NULL COMMENT '第三方非敏感扩展字段快照，不保存完整卡号或密钥',
    provider_created_at DATETIME(3) NULL COMMENT '第三方卡片创建时间（UTC）',
    provider_updated_at DATETIME(3) NULL COMMENT '第三方卡片最后更新时间（UTC）',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_card_station_platform_external_deleted
        (platform, external_card_id, deleted_at),
    KEY idx_card_station_platform_status (platform, card_status, deleted_at),
    KEY idx_card_station_ad_account (advertisement_account_id, deleted_at),
    CONSTRAINT ck_card_station_platform CHECK (platform IN ('photonpay', 'arrivalx')),
    CONSTRAINT ck_card_station_balance CHECK (balance >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '卡台卡片本地目录；仅保存脱敏卡号和业务字段';

CREATE TABLE card_station_balance (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '卡台余额ID',
    platform VARCHAR(32) NOT NULL COMMENT '卡台平台',
    product_code VARCHAR(64) NOT NULL COMMENT '卡产品编码',
    currency VARCHAR(16) NOT NULL COMMENT '币种',
    balance DECIMAL(24, 8) NOT NULL DEFAULT 0 COMMENT '可用余额',
    frozen_balance DECIMAL(24, 8) NOT NULL DEFAULT 0 COMMENT '冻结余额',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后同步时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_card_station_balance_scope_deleted
        (platform, product_code, currency, deleted_at),
    CONSTRAINT ck_card_station_balance_amount CHECK (balance >= 0 AND frozen_balance >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '卡台账户余额快照';

CREATE TABLE card_station_limit_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '限额调整记录ID',
    platform VARCHAR(32) NOT NULL COMMENT '卡台平台',
    external_card_id VARCHAR(128) NOT NULL COMMENT '第三方卡片稳定标识',
    old_amount DECIMAL(24, 8) NULL COMMENT '调整前限额',
    new_amount DECIMAL(24, 8) NOT NULL COMMENT '调整后限额',
    preset VARCHAR(32) NULL COMMENT '限额周期',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '执行状态：0待执行，1成功，2失败',
    error_message VARCHAR(500) NULL COMMENT '失败原因，不记录第三方密钥',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '操作人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '操作时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    KEY idx_card_limit_card_time (platform, external_card_id, created_at, deleted_at),
    CONSTRAINT ck_card_limit_status CHECK (status IN (0, 1, 2)),
    CONSTRAINT ck_card_limit_amount CHECK (new_amount >= 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '卡台限额调整任务与结果记录';

CREATE TABLE external_sync_job (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '第三方同步任务ID',
    provider VARCHAR(32) NOT NULL COMMENT '提供方：photonpay、arrivalx、feishu或google',
    job_type VARCHAR(32) NOT NULL COMMENT '任务类型：FULL_SYNC、MAPPING_SYNC等',
    business_id VARCHAR(128) NULL COMMENT '关联业务稳定标识',
    request_payload JSON NULL COMMENT '同步请求非敏感参数',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '任务状态：0待执行，1执行中，2成功，3失败',
    error_message VARCHAR(1000) NULL COMMENT '失败原因，不记录令牌或密钥',
    requested_by BIGINT UNSIGNED NOT NULL COMMENT '发起人用户ID',
    started_at DATETIME(3) NULL COMMENT '开始时间（UTC）',
    finished_at DATETIME(3) NULL COMMENT '结束时间（UTC）',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    KEY idx_external_sync_provider_status (provider, status, created_at, deleted_at),
    KEY idx_external_sync_business (provider, business_id, created_at, deleted_at),
    CONSTRAINT ck_external_sync_status CHECK (status IN (0, 1, 2, 3))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '第三方集成异步任务队列和执行审计';

CREATE TABLE feishu_app_config (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '飞书应用配置ID',
    app_name VARCHAR(100) NOT NULL COMMENT '飞书应用展示名称',
    app_id VARCHAR(100) NOT NULL COMMENT '飞书应用App ID',
    app_secret_ciphertext TEXT NOT NULL COMMENT 'AES-GCM加密后的App Secret',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_feishu_app_id_deleted (app_id, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '飞书开放平台应用配置；密钥仅密文保存且接口不回显';

CREATE TABLE feishu_sync_task (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '飞书同步任务ID',
    task_name VARCHAR(255) NOT NULL COMMENT '同步任务名称',
    app_id VARCHAR(100) NOT NULL COMMENT '关联飞书应用App ID',
    app_token VARCHAR(128) NOT NULL COMMENT '多维表格或电子表格App Token',
    table_id VARCHAR(128) NOT NULL COMMENT '飞书子表稳定标识',
    table_name VARCHAR(255) NULL COMMENT '飞书子表名称',
    target_table_name VARCHAR(128) NOT NULL COMMENT '目标系统数据表名称',
    task_type TINYINT NOT NULL DEFAULT 0 COMMENT '任务类型：0多维表格，1电子表格',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '任务状态：1启用，0停用',
    last_sync_time DATETIME(3) NULL COMMENT '最后成功同步时间（UTC）',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_feishu_task_source_deleted (app_token, table_id, deleted_at),
    KEY idx_feishu_task_status (status, deleted_at),
    CONSTRAINT ck_feishu_task_status CHECK (status IN (0, 1)),
    CONSTRAINT ck_feishu_task_type CHECK (task_type IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '飞书到AdPulse系统表的数据同步任务';

CREATE TABLE feishu_field_mapping (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '字段映射ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '同步任务ID，逻辑关联feishu_sync_task.id',
    system_field_name VARCHAR(128) NOT NULL COMMENT '系统字段名',
    feishu_field_name VARCHAR(255) NOT NULL COMMENT '飞书字段名',
    column_comment VARCHAR(255) NULL COMMENT '系统字段说明',
    data_type VARCHAR(64) NULL COMMENT '系统字段类型',
    is_required TINYINT NOT NULL DEFAULT 0 COMMENT '是否必填：1是，0否',
    is_split TINYINT NOT NULL DEFAULT 0 COMMENT '是否拆分飞书字段：1是，0否',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_feishu_mapping_task_field_deleted
        (task_id, system_field_name, deleted_at),
    CONSTRAINT ck_feishu_mapping_required CHECK (is_required IN (0, 1)),
    CONSTRAINT ck_feishu_mapping_split CHECK (is_split IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '飞书字段到系统字段映射';

CREATE TABLE feishu_sync_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '同步日志ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '同步任务ID',
    status TINYINT NOT NULL COMMENT '执行状态：0执行中，1成功，2失败',
    total_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '读取记录数',
    success_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '成功记录数',
    fail_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '失败记录数',
    error_message VARCHAR(1000) NULL COMMENT '失败摘要，不记录飞书令牌',
    started_at DATETIME(3) NOT NULL COMMENT '开始时间（UTC）',
    ended_at DATETIME(3) NULL COMMENT '结束时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    KEY idx_feishu_log_task_time (task_id, started_at, deleted_at),
    CONSTRAINT ck_feishu_log_status CHECK (status IN (0, 1, 2))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '飞书同步执行结果日志';

CREATE TABLE google_integration_account (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Google授权账号ID',
    google_subject VARCHAR(128) NOT NULL COMMENT 'Google用户稳定标识sub',
    email VARCHAR(255) NOT NULL COMMENT 'Google账号邮箱',
    picture VARCHAR(1000) NULL COMMENT 'Google头像地址',
    access_token_ciphertext TEXT NULL COMMENT 'AES-GCM加密后的Access Token',
    refresh_token_ciphertext TEXT NULL COMMENT 'AES-GCM加密后的Refresh Token',
    token_expires_at DATETIME(3) NULL COMMENT 'Access Token失效时间（UTC）',
    auth_status TINYINT NOT NULL DEFAULT 1 COMMENT '授权状态：1有效，0已断开，2已过期',
    authorized_at DATETIME(3) NOT NULL COMMENT '最近授权时间（UTC）',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '授权发起人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_google_subject_deleted (google_subject, deleted_at),
    KEY idx_google_email_status (email, auth_status, deleted_at),
    CONSTRAINT ck_google_auth_status CHECK (auth_status IN (0, 1, 2))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Google OAuth账号；令牌仅密文保存且接口不回显';

CREATE TABLE google_integration_mapping (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Google Sheets映射ID',
    google_account_id BIGINT UNSIGNED NOT NULL COMMENT 'Google账号ID，逻辑关联google_integration_account.id',
    name VARCHAR(255) NOT NULL COMMENT '映射配置名称',
    report_type TINYINT NOT NULL COMMENT '系统报表类型',
    spreadsheet_id VARCHAR(255) NOT NULL COMMENT 'Google Spreadsheet稳定标识',
    spreadsheet_name VARCHAR(500) NOT NULL COMMENT 'Google Spreadsheet名称快照',
    spreadsheet_modified_time VARCHAR(64) NULL COMMENT '表格最后修改时间快照',
    sheet_names JSON NOT NULL COMMENT '参与同步的Sheet名称数组',
    field_mappings JSON NOT NULL COMMENT '按Sheet分组的字段映射',
    sync_direction TINYINT NOT NULL COMMENT '同步方向：1读取，2写入，3双向',
    conflict_strategy TINYINT NOT NULL COMMENT '冲突策略：1系统优先，2Sheets优先，3最新优先',
    date_range_type TINYINT NOT NULL COMMENT '日期范围类型：1自定义，2最近N天，3本月',
    date_range_config JSON NOT NULL COMMENT '日期范围配置',
    sync_frequency TINYINT NOT NULL COMMENT '同步频率：1手动，2每天，3每小时',
    sync_time VARCHAR(8) NULL COMMENT '每日同步时间，HH:mm',
    enable_flag TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用：1启用，0停用',
    last_sync_time DATETIME(3) NULL COMMENT '最后成功同步时间（UTC）',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_google_mapping_scope_deleted
        (google_account_id, spreadsheet_id, name, deleted_at),
    KEY idx_google_mapping_account_status (google_account_id, enable_flag, deleted_at),
    CONSTRAINT ck_google_mapping_direction CHECK (sync_direction IN (1, 2, 3)),
    CONSTRAINT ck_google_mapping_conflict CHECK (conflict_strategy IN (1, 2, 3)),
    CONSTRAINT ck_google_mapping_date_range CHECK (date_range_type IN (1, 2, 3)),
    CONSTRAINT ck_google_mapping_frequency CHECK (sync_frequency IN (1, 2, 3)),
    CONSTRAINT ck_google_mapping_enable CHECK (enable_flag IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'AdPulse系统报表与Google Sheets的同步映射配置';
