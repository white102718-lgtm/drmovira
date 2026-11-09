CREATE TABLE sys_department (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '部门ID',
    parent_id BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '父部门ID，根节点为0',
    dept_code VARCHAR(64) NOT NULL COMMENT '部门编码',
    dept_name VARCHAR(100) NOT NULL COMMENT '部门名称',
    path VARCHAR(1000) NOT NULL DEFAULT '/' COMMENT '部门层级路径',
    level TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '部门层级',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '同级显示顺序',
    leader_user_id BIGINT UNSIGNED NULL COMMENT '负责人用户ID',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_department_code_deleted (dept_code, deleted_at),
    UNIQUE KEY uk_department_parent_name_deleted (parent_id, dept_name, deleted_at),
    KEY idx_department_parent (parent_id, status, deleted_at, sort_order),
    KEY idx_department_path (path(255)),
    KEY idx_department_leader (leader_user_id),
    CONSTRAINT ck_department_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统组织部门表';

CREATE TABLE sys_user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username VARCHAR(64) NULL COMMENT '登录账号',
    phone VARCHAR(32) NOT NULL COMMENT '手机号',
    password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
    display_name VARCHAR(100) NOT NULL COMMENT '系统显示名称',
    english_nickname VARCHAR(64) NULL COMMENT '英文昵称',
    real_name VARCHAR(100) NULL COMMENT '真实姓名',
    primary_department_id BIGINT UNSIGNED NULL COMMENT '用户主部门ID',
    email VARCHAR(128) NULL COMMENT '邮箱',
    avatar_url VARCHAR(500) NULL COMMENT '头像地址',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    ip_access_mode TINYINT NOT NULL DEFAULT 0 COMMENT '0关闭规则，1允许全部，2白名单',
    mfa_enabled TINYINT NOT NULL DEFAULT 0 COMMENT '是否启用MFA',
    mfa_secret_ciphertext VARCHAR(1000) NULL COMMENT '加密后的MFA密钥',
    mfa_bound_at DATETIME(3) NULL COMMENT 'MFA绑定时间',
    password_changed_at DATETIME(3) NULL COMMENT '最后修改密码时间',
    login_failed_count INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '连续登录失败次数',
    locked_until DATETIME(3) NULL COMMENT '账号锁定截止时间',
    last_login_at DATETIME(3) NULL COMMENT '最后登录时间',
    last_login_ip VARCHAR(64) NULL COMMENT '最后登录IP',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_username_deleted (username, deleted_at),
    UNIQUE KEY uk_user_phone_deleted (phone, deleted_at),
    UNIQUE KEY uk_user_english_nickname_deleted (english_nickname, deleted_at),
    KEY idx_user_department (primary_department_id, status, deleted_at),
    KEY idx_user_display_name (display_name),
    KEY idx_user_real_name (real_name),
    KEY idx_user_status_deleted (status, deleted_at),
    CONSTRAINT ck_user_status CHECK (status IN (0, 1)),
    CONSTRAINT ck_user_ip_access_mode CHECK (ip_access_mode IN (0, 1, 2)),
    CONSTRAINT ck_user_mfa_enabled CHECK (mfa_enabled IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统用户表';

CREATE TABLE sys_role (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    role_code VARCHAR(64) NOT NULL COMMENT '角色编码',
    role_name VARCHAR(100) NOT NULL COMMENT '角色名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '显示顺序',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_code_deleted (role_code, deleted_at),
    UNIQUE KEY uk_role_name_deleted (role_name, deleted_at),
    KEY idx_role_status_deleted (status, deleted_at, sort_order),
    CONSTRAINT ck_role_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统角色表';

CREATE TABLE sys_menu (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '菜单ID',
    parent_id BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '父菜单ID，根节点为0',
    menu_type TINYINT NOT NULL COMMENT '类型：1目录，2菜单，3按钮',
    menu_code VARCHAR(100) NOT NULL COMMENT '菜单或权限编码',
    menu_name VARCHAR(100) NOT NULL COMMENT '菜单名称',
    route_path VARCHAR(255) NULL COMMENT '前端路由路径',
    component VARCHAR(255) NULL COMMENT '前端组件路径',
    icon VARCHAR(100) NULL COMMENT '菜单图标',
    permission_code VARCHAR(128) NULL COMMENT '权限标识',
    visible TINYINT NOT NULL DEFAULT 1 COMMENT '是否显示：1显示，0隐藏',
    cacheable TINYINT NOT NULL DEFAULT 0 COMMENT '是否缓存页面',
    external_link VARCHAR(500) NULL COMMENT '外部链接',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '同级显示顺序',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_menu_code_deleted (menu_code, deleted_at),
    UNIQUE KEY uk_menu_permission_deleted (permission_code, deleted_at),
    UNIQUE KEY uk_menu_parent_name_deleted (parent_id, menu_name, deleted_at),
    KEY idx_menu_parent (parent_id, status, deleted_at, sort_order),
    CONSTRAINT ck_menu_type CHECK (menu_type IN (1, 2, 3)),
    CONSTRAINT ck_menu_status CHECK (status IN (0, 1)),
    CONSTRAINT ck_menu_visible CHECK (visible IN (0, 1)),
    CONSTRAINT ck_menu_cacheable CHECK (cacheable IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统菜单权限表';

CREATE TABLE sys_user_role (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '关系ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    role_id BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
    created_by BIGINT UNSIGNED NULL COMMENT '分配人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_role_deleted (user_id, role_id, deleted_at),
    KEY idx_user_role_user (user_id, deleted_at),
    KEY idx_user_role_role (role_id, deleted_at, user_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户角色关联表';

CREATE TABLE sys_role_menu (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '关系ID',
    role_id BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
    menu_id BIGINT UNSIGNED NOT NULL COMMENT '菜单ID',
    created_by BIGINT UNSIGNED NULL COMMENT '分配人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_menu_deleted (role_id, menu_id, deleted_at),
    KEY idx_role_menu_role (role_id, deleted_at),
    KEY idx_role_menu_menu (menu_id, deleted_at, role_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '角色菜单关联表';

CREATE TABLE sys_user_department_scope (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '关系ID',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
    department_id BIGINT UNSIGNED NOT NULL COMMENT '授权部门ID',
    include_children TINYINT NOT NULL DEFAULT 1 COMMENT '是否包含子孙部门',
    created_by BIGINT UNSIGNED NULL COMMENT '授权人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_department_scope_deleted (user_id, department_id, deleted_at),
    KEY idx_scope_user (user_id, deleted_at),
    KEY idx_scope_department (department_id, deleted_at, user_id),
    CONSTRAINT ck_scope_include_children CHECK (include_children IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '用户部门数据权限范围';

CREATE TABLE sys_ip_rule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'IP规则ID',
    scope_type TINYINT NOT NULL COMMENT '范围：1通用，2用户专属',
    user_id BIGINT UNSIGNED NULL COMMENT '用户ID，通用规则为NULL',
    ip_cidr VARCHAR(64) NOT NULL COMMENT 'IP或CIDR',
    rule_name VARCHAR(100) NULL COMMENT '规则名称',
    status TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1启用，0停用',
    remark VARCHAR(500) NULL COMMENT '备注',
    created_by BIGINT UNSIGNED NULL COMMENT '创建人ID',
    updated_by BIGINT UNSIGNED NULL COMMENT '修改人ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，其他值为删除毫秒时间戳',
    normalized_user_id BIGINT UNSIGNED GENERATED ALWAYS AS (
        CASE WHEN scope_type = 1 THEN 0 ELSE user_id END
    ) STORED COMMENT '唯一约束辅助列',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ip_rule_scope_deleted (
        scope_type,
        normalized_user_id,
        ip_cidr,
        deleted_at
    ),
    KEY idx_ip_rule_user (user_id, status, deleted_at),
    KEY idx_ip_rule_common (scope_type, status, deleted_at),
    CONSTRAINT ck_ip_rule_scope_type CHECK (scope_type IN (1, 2)),
    CONSTRAINT ck_ip_rule_scope_user CHECK (
        (scope_type = 1 AND user_id IS NULL)
        OR (scope_type = 2 AND user_id IS NOT NULL)
    ),
    CONSTRAINT ck_ip_rule_status CHECK (status IN (0, 1))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci COMMENT = '系统IP访问规则';
