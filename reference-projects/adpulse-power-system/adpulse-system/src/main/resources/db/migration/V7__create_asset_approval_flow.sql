CREATE TABLE media_asset (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    asset_type VARCHAR(24) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    asset_code VARCHAR(191) NOT NULL,
    secret_data TEXT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'AVAILABLE',
    assignee_id BIGINT UNSIGNED NULL,
    assignee_name VARCHAR(64) NULL,
    application_id BIGINT UNSIGNED NULL,
    remark VARCHAR(500) NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    updated_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_media_asset_code (asset_type, asset_code, deleted_at),
    KEY idx_media_asset_status (asset_type, status, deleted_at),
    KEY idx_media_asset_assignee (assignee_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一媒介资产';

CREATE TABLE media_approval_config (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    asset_type VARCHAR(24) NOT NULL,
    approver_id BIGINT UNSIGNED NOT NULL,
    approver_name VARCHAR(64) NOT NULL,
    cc_user_ids VARCHAR(1000) NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    updated_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_media_approval_type (asset_type, deleted_at),
    KEY idx_media_approval_approver (approver_id, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='媒介资产审批配置';

CREATE TABLE media_asset_application (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    application_no VARCHAR(40) NOT NULL,
    asset_type VARCHAR(24) NOT NULL,
    title VARCHAR(128) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    requester_id BIGINT UNSIGNED NOT NULL,
    requester_name VARCHAR(64) NOT NULL,
    approver_id BIGINT UNSIGNED NOT NULL,
    approver_name VARCHAR(64) NOT NULL,
    decision_remark VARCHAR(1000) NULL,
    decided_at DATETIME NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    updated_by BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_media_application_no (application_no, deleted_at),
    KEY idx_media_application_requester (requester_id, status, deleted_at),
    KEY idx_media_application_approver (approver_id, status, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='媒介资产申请单';

CREATE TABLE media_asset_approval_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    application_id BIGINT UNSIGNED NOT NULL,
    action VARCHAR(24) NOT NULL,
    actor_id BIGINT UNSIGNED NOT NULL,
    actor_name VARCHAR(64) NOT NULL,
    remark VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_media_approval_log_application (application_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='媒介资产审批轨迹';
