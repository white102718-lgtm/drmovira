CREATE TABLE ad_account_asset (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '广告账户资产信息记录 ID',
    account_id VARCHAR(100) NOT NULL COMMENT '广告平台账户 ID；逻辑关联 MongoDB fb_ad_accounts._id，不建立数据库外键',
    account_name VARCHAR(255) NULL COMMENT '人工维护或 Excel 导入的账户展示名称',
    account_type VARCHAR(100) NULL COMMENT '广告账户业务类型',
    account_attribute VARCHAR(100) NULL COMMENT '广告账户属性；取值来自有效的 ad_account_attribute 配置或历史保留值',
    managed_bm VARCHAR(500) NULL COMMENT '管理 BM 展示名称',
    managed_bm_id VARCHAR(100) NULL COMMENT '管理 BM 的平台标识',
    backup_managed_bm VARCHAR(500) NULL COMMENT '备用管理 BM 展示名称',
    backup_managed_bm_id VARCHAR(100) NULL COMMENT '备用管理 BM 的平台标识',
    timezone VARCHAR(100) NULL COMMENT '广告账户时区名称或 UTC 偏移',
    card_station VARCHAR(100) NULL COMMENT '广告账户绑定的卡台名称',
    card_number VARCHAR(100) NULL COMMENT '广告账户绑定的卡号；按业务原值保存，接口和日志不得额外输出',
    is_limited VARCHAR(10) NULL COMMENT '是否限额：YES 表示限额，NO 表示不限额，NULL 表示未维护',
    update_source VARCHAR(20) NOT NULL COMMENT '最近维护来源：MANUAL_EDIT 或 EXCEL_IMPORT',
    created_by BIGINT UNSIGNED NULL COMMENT '首次创建该资产信息的用户 ID；逻辑关联 sys_user.id',
    updated_by BIGINT UNSIGNED NULL COMMENT '最近更新该资产信息的用户 ID；逻辑关联 sys_user.id',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳；0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ad_account_asset_account_deleted (account_id, deleted_at),
    KEY idx_ad_account_asset_updated (updated_at, id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '广告账户资产信息主表；存在有效记录时优先于飞书历史账户使用记录';

ALTER TABLE ad_account_attribute
    MODIFY account_attribute VARCHAR(15) NOT NULL
        COMMENT '广告账户可选属性名称，存入广告账户资产信息主表';
