-- 人工审核后部署前执行；导入记录只允许所属操作人查询和下载。
CREATE TABLE ad_account_asset_import_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '广告账户导入记录主键',
    file_name VARCHAR(255) NOT NULL COMMENT '用户上传的原始文件名，仅用于历史列表展示',
    total_count INT UNSIGNED NOT NULL COMMENT '服务端识别的有效数据行总数',
    success_count INT UNSIGNED NOT NULL COMMENT '成功新增或更新广告账户的数据行数',
    failure_count INT UNSIGNED NOT NULL COMMENT '导入失败的数据行数',
    failure_details JSON NOT NULL COMMENT '失败行号、账户 ID 与原因数组，不保存原始单元格内容',
    failed_file_ciphertext MEDIUMTEXT NULL COMMENT '失败工作簿 Base64 的 AES-GCM 密文，仅所属操作人下载时解密',
    operator_id BIGINT UNSIGNED NOT NULL COMMENT '导入操作人系统用户 ID，逻辑关联 sys_user.id，不建立外键',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '导入记录创建时间（UTC）',
    PRIMARY KEY (id),
    KEY idx_ad_account_import_operator_created (operator_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='广告账户文件批量导入的追加记录；失败工作簿加密保存并按操作人隔离';
