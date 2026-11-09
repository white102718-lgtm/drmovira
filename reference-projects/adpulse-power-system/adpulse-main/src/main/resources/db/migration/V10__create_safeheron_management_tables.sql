CREATE TABLE safeheron_wallet (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '钱包本地ID',
    account_key VARCHAR(128) NOT NULL COMMENT 'Safeheron钱包稳定标识，不存储私钥或助记词',
    account_name VARCHAR(255) NOT NULL COMMENT '钱包展示名称',
    team_id VARCHAR(64) NULL COMMENT '所属Safeheron团队标识，逻辑关联safeheron_team.team_id',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '钱包状态：1可用，0停用',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_safeheron_wallet_key_deleted (account_key, deleted_at),
    KEY idx_safeheron_wallet_team_status (team_id, status, deleted_at),
    CONSTRAINT ck_safeheron_wallet_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Safeheron钱包目录；仅保存业务标识和展示信息，不保存密钥材料';

CREATE TABLE safeheron_wallet_coin (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '钱包币种本地ID',
    account_key VARCHAR(128) NOT NULL COMMENT '钱包稳定标识，逻辑关联safeheron_wallet.account_key',
    coin_key VARCHAR(64) NOT NULL COMMENT 'Safeheron币种及网络标识，例如USDT_TRC20',
    coin_name VARCHAR(100) NOT NULL COMMENT '币种及网络展示名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '币种状态：1可用，0停用',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_safeheron_wallet_coin_deleted (account_key, coin_key, deleted_at),
    KEY idx_safeheron_coin_account_status (account_key, status, deleted_at),
    CONSTRAINT ck_safeheron_wallet_coin_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Safeheron钱包支持币种目录；地址等敏感信息不在此表保存';

CREATE TABLE safeheron_team (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '团队配置本地ID',
    team_id VARCHAR(64) NOT NULL COMMENT 'Safeheron团队稳定标识',
    team_name VARCHAR(100) NOT NULL COMMENT '团队展示名称',
    approver_id BIGINT UNSIGNED NULL COMMENT '归集审批人用户ID，逻辑关联sys_user.id',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '团队配置状态：1启用，0停用',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_safeheron_team_deleted (team_id, deleted_at),
    KEY idx_safeheron_team_approver (approver_id, status, deleted_at),
    CONSTRAINT ck_safeheron_team_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Safeheron团队与归集审批人配置';

CREATE TABLE safeheron_collection_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '归集规则ID',
    department_id BIGINT UNSIGNED NOT NULL COMMENT '所属部门ID，逻辑关联sys_department.id',
    collect_account_key VARCHAR(128) NOT NULL COMMENT '归集目标钱包标识，逻辑关联safeheron_wallet.account_key',
    collect_account_name VARCHAR(255) NOT NULL COMMENT '目标钱包名称快照',
    coin_key VARCHAR(64) NOT NULL COMMENT '归集币种及网络标识',
    threshold_usd DECIMAL(24, 8) NOT NULL COMMENT '触发归集的美元估值阈值',
    frequency_minutes INT UNSIGNED NOT NULL COMMENT '归集检查频率，单位分钟',
    gas_station_enabled TINYINT NOT NULL DEFAULT 1 COMMENT '是否允许Gas加油：1允许，0禁止',
    reserve_gas DECIMAL(24, 8) NULL COMMENT '源钱包保留Gas数量，按链上币种计量',
    max_tx_fee DECIMAL(24, 8) NULL COMMENT '单笔最大链上手续费，按网络原生币计量',
    signer VARCHAR(255) NULL COMMENT '签名策略或签名人标识，不保存私钥',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '规则状态：1启用，0停用',
    effective_status TINYINT NOT NULL DEFAULT 1 COMMENT '生效状态：0关闭，1生效，2异常',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_safeheron_rule_scope_deleted
        (department_id, collect_account_key, coin_key, deleted_at),
    KEY idx_safeheron_rule_status (status, effective_status, deleted_at),
    KEY idx_safeheron_rule_wallet (collect_account_key, deleted_at),
    CONSTRAINT ck_safeheron_rule_status CHECK (status IN (0, 1)),
    CONSTRAINT ck_safeheron_rule_effective CHECK (effective_status IN (0, 1, 2)),
    CONSTRAINT ck_safeheron_rule_gas_station CHECK (gas_station_enabled IN (0, 1)),
    CONSTRAINT ck_safeheron_rule_threshold CHECK (threshold_usd >= 0),
    CONSTRAINT ck_safeheron_rule_frequency CHECK (frequency_minutes > 0)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Safeheron部门级自动归集规则；执行器按启用规则读取，不保存任何签名密钥';

CREATE TABLE safeheron_collection_record (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '归集记录ID',
    team_id VARCHAR(64) NULL COMMENT '所属Safeheron团队标识',
    department_id BIGINT UNSIGNED NULL COMMENT '所属部门ID，逻辑关联sys_department.id',
    task_id VARCHAR(64) NULL COMMENT '关联投放任务稳定ID',
    source_account_key VARCHAR(128) NULL COMMENT '被归集钱包稳定标识',
    source_account_name VARCHAR(255) NULL COMMENT '被归集钱包名称快照',
    dest_account_key VARCHAR(128) NULL COMMENT '目标钱包稳定标识',
    dest_account_name VARCHAR(255) NULL COMMENT '目标钱包名称快照',
    coin_key VARCHAR(64) NOT NULL COMMENT '币种及网络标识',
    coin_name VARCHAR(100) NOT NULL COMMENT '币种及网络展示名称快照',
    amount DECIMAL(36, 18) NOT NULL COMMENT '链上归集数量',
    amount_usd DECIMAL(24, 8) NULL COMMENT '发起归集时的美元估值',
    gas_fee DECIMAL(36, 18) NULL COMMENT '链上实际Gas费用',
    status TINYINT NOT NULL COMMENT '执行状态：0进行中，1成功，2失败',
    transaction_type VARCHAR(32) NOT NULL COMMENT '交易类型：NORMAL/AUTO_SWEEP/AUTO_FUEL',
    approver_id BIGINT UNSIGNED NULL COMMENT '审批人用户ID，逻辑关联sys_user.id',
    approver_name VARCHAR(100) NULL COMMENT '审批人名称快照',
    approve_result TINYINT NULL COMMENT '审批结果：0拒绝，1通过，2审批中',
    tx_hash VARCHAR(255) NULL COMMENT '链上交易哈希',
    remark VARCHAR(500) NULL COMMENT '失败原因或人工备注，不记录密钥和完整签名请求',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '归集发起时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    KEY idx_safeheron_record_team_time (team_id, created_at, deleted_at),
    KEY idx_safeheron_record_department_time (department_id, created_at, deleted_at),
    KEY idx_safeheron_record_task_time (task_id, created_at, deleted_at),
    KEY idx_safeheron_record_status_time (status, created_at, deleted_at),
    CONSTRAINT ck_safeheron_record_status CHECK (status IN (0, 1, 2)),
    CONSTRAINT ck_safeheron_record_approve CHECK
        (approve_result IS NULL OR approve_result IN (0, 1, 2))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'Safeheron归集执行与审批结果记录；业务审计长期保留并支持软删除';
