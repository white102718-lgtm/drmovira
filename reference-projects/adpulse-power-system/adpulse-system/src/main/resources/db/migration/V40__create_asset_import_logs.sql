-- 人工审核后部署前执行；导入记录用于当前操作人回溯，不允许跨用户查询。
CREATE TABLE media_asset_import_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '资产导入记录主键',
    asset_subtype VARCHAR(32) NOT NULL COMMENT '导入时选择的资产子类型，如 tg、wechat、computer',
    file_name VARCHAR(255) NOT NULL COMMENT '用户上传的原始文件名，仅用于历史列表展示',
    total_count INT UNSIGNED NOT NULL COMMENT '服务端识别的有效数据行总数',
    success_count INT UNSIGNED NOT NULL COMMENT '成功写入资产库存的数据行数',
    failure_count INT UNSIGNED NOT NULL COMMENT '导入失败的数据行数',
    failure_details JSON NOT NULL COMMENT '失败行号及原因数组，不保存原始单元格敏感信息',
    failed_file_ciphertext MEDIUMTEXT NULL COMMENT '失败工作簿 Base64 的 AES-GCM 密文，仅所属操作人下载时解密',
    operator_id BIGINT UNSIGNED NOT NULL COMMENT '导入操作人系统用户 ID，逻辑关联 sys_user.id',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '导入记录创建时间（UTC）',
    PRIMARY KEY (id),
    KEY idx_media_asset_import_log_operator_created (operator_id, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='资产 Excel 批量导入的追加审计记录；失败工作簿加密保存并按操作人隔离';
