ALTER TABLE safeheron_team
    ADD COLUMN base_url VARCHAR(256) NOT NULL DEFAULT 'https://api.safeheron.vip'
        COMMENT 'Safeheron API地址' AFTER status,
    ADD COLUMN api_key VARCHAR(256) NULL COMMENT 'Safeheron接入标识' AFTER base_url,
    ADD COLUMN private_key_ciphertext TEXT NULL COMMENT 'API RSA私钥AES-GCM密文' AFTER api_key,
    ADD COLUMN safeheron_public_key TEXT NULL COMMENT 'Safeheron API RSA公钥' AFTER private_key_ciphertext,
    ADD COLUMN request_timeout BIGINT UNSIGNED NOT NULL DEFAULT 20000
        COMMENT '请求超时毫秒' AFTER safeheron_public_key;

ALTER TABLE safeheron_wallet
    ADD COLUMN customer_ref_id VARCHAR(128) NULL COMMENT '业务侧唯一引用ID，项目钱包使用项目编码'
        AFTER account_name,
    ADD UNIQUE KEY uk_safeheron_wallet_customer_ref_deleted (customer_ref_id, deleted_at);

ALTER TABLE safeheron_wallet_coin
    ADD COLUMN fee_unit VARCHAR(64) NULL COMMENT '链上手续费单位' AFTER coin_name,
    ADD COLUMN address_ciphertext TEXT NULL COMMENT '首个收款地址AES-GCM密文' AFTER fee_unit;
