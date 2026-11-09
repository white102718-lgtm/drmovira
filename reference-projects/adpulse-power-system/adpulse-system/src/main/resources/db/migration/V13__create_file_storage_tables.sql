CREATE TABLE IF NOT EXISTS sys_file_object (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '物理文件对象主键',
    content_hash CHAR(64) NOT NULL COMMENT '文件内容SHA-256小写十六进制值',
    hash_algorithm VARCHAR(16) NOT NULL DEFAULT 'SHA-256' COMMENT '哈希算法',
    file_size BIGINT UNSIGNED NOT NULL COMMENT '文件字节数',
    mime_type VARCHAR(128) NOT NULL COMMENT '服务端识别的MIME类型',
    storage_provider VARCHAR(32) NOT NULL DEFAULT 'LOCAL' COMMENT '存储提供方，当前为LOCAL',
    bucket_name VARCHAR(128) NULL COMMENT '对象存储桶，本地存储为NULL',
    object_key VARCHAR(512) NOT NULL COMMENT '相对存储根目录的对象键',
    storage_status VARCHAR(16) NOT NULL DEFAULT 'AVAILABLE' COMMENT '存储状态：AVAILABLE/DELETE_PENDING，清理任务负责状态转换',
    reference_count BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '有效文件记录引用数',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '更新用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间，0表示有效',
    PRIMARY KEY (id),
    UNIQUE KEY uk_sys_file_object_content (content_hash, file_size, deleted_at),
    UNIQUE KEY uk_sys_file_object_key (storage_provider, object_key, deleted_at),
    KEY idx_sys_file_object_cleanup (reference_count, storage_status, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='去重后的物理文件对象';

CREATE TABLE IF NOT EXISTS sys_file (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户文件记录主键',
    file_object_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联sys_file_object.id',
    original_name VARCHAR(255) NOT NULL COMMENT '用户上传时的原始文件名',
    extension VARCHAR(32) NULL COMMENT '标准化后的小写扩展名',
    uploader_id BIGINT UNSIGNED NOT NULL COMMENT '上传用户ID',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '更新用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '软删除时间，0表示有效',
    PRIMARY KEY (id),
    KEY idx_sys_file_object (file_object_id, deleted_at),
    KEY idx_sys_file_uploader (uploader_id, created_at, deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户文件元数据及物理对象引用';
