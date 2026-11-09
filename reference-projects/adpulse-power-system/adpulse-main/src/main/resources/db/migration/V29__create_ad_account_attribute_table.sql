CREATE TABLE ad_account_attribute (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '账户属性配置 ID',
    account_attribute VARCHAR(15) NOT NULL COMMENT '广告账户可选属性名称，存入广告账户资产信息主表',
    account_attribute_code VARCHAR(10) NOT NULL COMMENT '账户属性配置编码，仅用于配置识别',
    created_by BIGINT UNSIGNED NULL COMMENT '创建该属性配置的用户 ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '记录创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '记录最后修改时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间戳；0 表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ad_account_attribute_name_deleted (account_attribute, deleted_at),
    UNIQUE KEY uk_ad_account_attribute_code_deleted (account_attribute_code, deleted_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
    COMMENT = '广告账户属性配置；供账户台账编辑与批量导入选择，不建立数据库外键';
