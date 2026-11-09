CREATE TABLE sys_dict_type (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '字典类型ID',
    dict_code VARCHAR(64) NOT NULL COMMENT '稳定的业务字典编码',
    dict_name VARCHAR(100) NOT NULL COMMENT '字典名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dict_type_code_deleted (dict_code, deleted_at),
    KEY idx_dict_type_status (status, deleted_at),
    CONSTRAINT ck_dict_type_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统字典类型表';

CREATE TABLE sys_dict_item (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '字典项ID',
    dict_type_id BIGINT UNSIGNED NOT NULL COMMENT '字典类型ID',
    item_value VARCHAR(100) NOT NULL COMMENT '供程序使用的字典值',
    item_label VARCHAR(100) NOT NULL COMMENT '供用户展示的字典标签',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '显示顺序',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dict_item_value_deleted (dict_type_id, item_value, deleted_at),
    KEY idx_dict_item_type (dict_type_id, status, deleted_at, sort_order),
    CONSTRAINT ck_dict_item_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统字典项表';

INSERT INTO sys_dict_type (dict_code, dict_name, status, remark)
VALUES ('AD_MEDIA', '投放媒体', 1, '广告投放平台选项');

SET @ad_media_type_id = LAST_INSERT_ID();

INSERT INTO sys_dict_item (dict_type_id, item_value, item_label, sort_order, status)
VALUES
    (@ad_media_type_id, 'FACEBOOK', 'Facebook', 10, 1),
    (@ad_media_type_id, 'GOOGLE', 'Google', 20, 1),
    (@ad_media_type_id, 'TIKTOK', 'TikTok', 30, 1);

SET @system_menu_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'SYSTEM' AND deleted_at = 0
);

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, route_path, component,
    permission_code, sort_order, status
) VALUES (
    @system_menu_id, 2, 'SYSTEM_DICTIONARY', '字典管理', '/system/dictionary',
    'system/dictionary/list', 'system:dictionary:list', 50, 1
);

SET @dictionary_menu_id = LAST_INSERT_ID();

INSERT INTO sys_menu (
    parent_id, menu_type, menu_code, menu_name, permission_code, sort_order, status
) VALUES
    (@dictionary_menu_id, 3, 'SYSTEM_DICTIONARY_CREATE', '新增字典',
        'system:dictionary:create', 10, 1),
    (@dictionary_menu_id, 3, 'SYSTEM_DICTIONARY_UPDATE', '修改字典',
        'system:dictionary:update', 20, 1),
    (@dictionary_menu_id, 3, 'SYSTEM_DICTIONARY_DELETE', '删除字典',
        'system:dictionary:delete', 30, 1);

INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, m.id
FROM sys_role r
CROSS JOIN sys_menu m
WHERE r.role_code = 'ADMIN'
  AND r.deleted_at = 0
  AND m.menu_code IN (
      'SYSTEM_DICTIONARY',
      'SYSTEM_DICTIONARY_CREATE',
      'SYSTEM_DICTIONARY_UPDATE',
      'SYSTEM_DICTIONARY_DELETE'
  )
  AND m.deleted_at = 0;
