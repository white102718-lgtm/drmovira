CREATE TABLE card_station_limit_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '卡台限额规则ID',
    scope_key VARCHAR(32) NOT NULL DEFAULT 'global'
        COMMENT '规则作用域；当前固定为global，PhotonPay与ArrivalX共用',
    daily_period SMALLINT UNSIGNED NOT NULL
        COMMENT '历史消耗统计周期，单位：天，取值1至365',
    adjust_amount DECIMAL(24, 8) NOT NULL
        COMMENT '加权额度，单位：USD；新日限额在历史最高消耗基础上增加的金额',
    min_amount DECIMAL(24, 8) NOT NULL DEFAULT 0
        COMMENT '自动调整后的最低日限额，单位：USD',
    auto_adjust_enabled TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否自动调整日限额：1开启，0关闭',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '软删除时间戳：0表示有效，否则为Unix毫秒',
    PRIMARY KEY (id),
    UNIQUE KEY uk_card_station_limit_rule_scope_deleted (scope_key, deleted_at),
    KEY idx_card_station_limit_rule_updated_by (updated_by, deleted_at),
    CONSTRAINT ck_card_station_limit_rule_period
        CHECK (daily_period BETWEEN 1 AND 365),
    CONSTRAINT ck_card_station_limit_rule_amount
        CHECK (adjust_amount >= 0 AND min_amount >= 0),
    CONSTRAINT ck_card_station_limit_rule_enabled
        CHECK (auto_adjust_enabled IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = 'PhotonPay与ArrivalX共用的卡日授权额度自动调整规则';
