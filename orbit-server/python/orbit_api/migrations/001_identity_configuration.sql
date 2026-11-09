-- Python底座独立空库的ORBIT业务表；仅显式迁移工具执行，不在应用启动时自动执行。
-- 已按Python合同重新审核字段、租户索引、唯一性与UTC语义；不修改用户Java预览库。


-- ORBIT新增业务表，适用于MySQL 8。先执行若依原始建库SQL，再审核执行本脚本。
-- 不连接或修改ad-mpower现有数据库。时间字段全部保存UTC，应用负责账户业务日转换。
-- 凭据只保存AES-GCM密文，独立主密钥不进入数据库。关联由事务服务验证，不创建外键。

CREATE TABLE IF NOT EXISTS orbit_tenant (
    id CHAR(36) NOT NULL COMMENT '租户内部UUID，与外部BM或广告账户ID无关',
    name VARCHAR(100) NOT NULL COMMENT '租户展示名称，不作为授权关联键',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '租户启用标志：1允许当前授权访问，0禁用并阻断新操作',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '可变对象版本，从1递增，用于并发校验',
    created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '记录创建UTC时刻，毫秒精度',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='ORBIT租户基础信息，授权范围由服务端解析';

CREATE TABLE IF NOT EXISTS orbit_user_scope (
    user_id BIGINT NOT NULL COMMENT '关联若依sys_user.user_id，每个用户一个当前租户上下文',
    tenant_id CHAR(36) NOT NULL COMMENT '当前授权租户UUID，禁止由浏览器请求参数覆盖',
    data_role VARCHAR(20) NOT NULL COMMENT '数据角色：USER本人、TEAM_ADMIN明确管理团队、SUPER_ADMIN授予范围',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '授权启用：1有效，0立即阻断业务访问',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '授权范围版本，变更时使旧缓存或快照失效',
    PRIMARY KEY (user_id),
    KEY idx_orbit_scope_tenant (tenant_id) COMMENT '按租户核对用户授权与成员范围'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='若依身份与ORBIT当前租户授权映射，不接受客户端伪造';

CREATE TABLE IF NOT EXISTS orbit_system_configuration (
    id CHAR(36) NOT NULL COMMENT '系统配置内部UUID，同时参与密文AAD对象绑定',
    tenant_id CHAR(36) NOT NULL COMMENT '配置所属租户UUID，所有读写必须带服务端租户条件',
    section VARCHAR(40) NOT NULL COMMENT '配置类型：AI_GPT/AI_CLAUDE/AI_SUGGESTIONS/META_APP/META_BM/ADSPOWER/OIDC/STORAGE/METRICS/NOTIFICATIONS/RISK',
    name VARCHAR(100) NOT NULL COMMENT '同租户同类型唯一的配置展示名，可区分多个BM或模型',
    enabled TINYINT NOT NULL DEFAULT 0 COMMENT '启用标志：仅代表配置可被业务选择，不代表连接或写能力验证通过',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '乐观锁版本，修改或验证后递增，旧If-Match拒绝',
    settings_json JSON NOT NULL COMMENT '严格白名单公开参数JSON，不得保存API Key/Token/App Secret',
    secrets_json JSON NOT NULL COMMENT '字段名到AES-256-GCM密文信封的JSON；信封含版本/key_id/nonce/tag，明文不落库',
    verification_status VARCHAR(24) NOT NULL DEFAULT 'UNTESTED' COMMENT '只读验证状态：UNTESTED未测、READ_VERIFIED只读通过、FAILED失败、BLOCKED待连接器实测',
    verified_at DATETIME(3) NULL COMMENT '最近只读探测完成UTC时刻；修改配置后清空',
    created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '创建UTC时刻，毫秒精度',
    updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '最近配置或验证更新UTC时刻，毫秒精度',
    PRIMARY KEY (id),
    UNIQUE KEY uk_orbit_configuration_name (tenant_id, section, name) COMMENT '禁止同租户同类型配置名称重复',
    KEY idx_orbit_configuration_tenant (tenant_id, section, id) COMMENT '租户内配置分组与稳定查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='系统业务配置与独立加密凭据，不复用若依明文sys_config';

CREATE TABLE IF NOT EXISTS orbit_configuration_audit (
    id CHAR(36) NOT NULL COMMENT '只追加配置审计UUID',
    tenant_id CHAR(36) NOT NULL COMMENT '审计所属租户UUID，审计查询同样按租户授权',
    config_id CHAR(36) NOT NULL COMMENT '变更配置UUID，禁止以可变名称作为引用',
    actor_id BIGINT NOT NULL COMMENT '从当前有效会话获取的若依用户ID，不接受客户端自报',
    action VARCHAR(24) NOT NULL COMMENT '配置审计动作：CREATE创建、UPDATE修改、READ_TEST只读测试',
    revision BIGINT NOT NULL COMMENT '操作后配置版本，与配置写入同事务',
    changed_fields_json JSON NOT NULL COMMENT '仅记录变更字段名及密钥替换/清除动作，不包含明文或密文值',
    reason VARCHAR(500) NOT NULL COMMENT '操作者填写的变更原因或系统只读测试结果说明',
    created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '审计事件UTC时刻，毫秒精度，只追加不覆盖',
    PRIMARY KEY (id),
    KEY idx_orbit_configuration_audit (tenant_id, config_id, created_at, id) COMMENT '租户内按配置追溯变更历史'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='脱敏配置审计，不保存敏感请求体或第三方原始响应';

-- 新空库默认租户仅供本项目初始化；现有库迁移需显式审核用户映射。
CREATE TABLE IF NOT EXISTS orbit_configuration_idempotency (
    tenant_id CHAR(36) NOT NULL COMMENT '从当前会话解析的租户UUID，幂等记录不能跨租户复用',
    actor_id BIGINT NOT NULL COMMENT '发起操作用户ID，重放前重新校验当前权限与对象范围',
    request_key VARCHAR(128) NOT NULL COMMENT '客户端随机Idempotency-Key，同键请求通过行锁串行化',
    payload_hash CHAR(64) NOT NULL COMMENT '请求路径、版本与规范化输入SHA256，只存hash不存密钥请求体',
    response_json JSON NULL COMMENT '事务内保存的脱敏业务响应；不得保存明文或加密凭据',
    created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '幂等记录创建UTC时刻，保留策略不得短于合同要求',
    PRIMARY KEY (tenant_id, actor_id, request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='配置写入幂等记录，与配置、审计同事务成功或回滚';

INSERT IGNORE INTO orbit_tenant (id, name) VALUES ('00000000-0000-0000-0000-000000000001', 'ORBIT默认租户');
INSERT IGNORE INTO orbit_user_scope (user_id, tenant_id, data_role)
SELECT user_id, '00000000-0000-0000-0000-000000000001', 'SUPER_ADMIN'
FROM sys_user WHERE user_id = 1 AND status = '0' AND del_flag = '0';

-- 只新增ORBIT菜单，不删除、覆盖或改写若依现有系统管理/监控/工具菜单。
INSERT IGNORE INTO sys_menu (menu_id, menu_name, parent_id, order_num, path, component, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, remark) VALUES
(31000, 'ORBIT工作台', 0, 10, 'orbit', NULL, 1, 0, 'M', '0', '0', '', 'dashboard', 'admin', NOW(), 'ORBIT八业务模块根目录；保留所有若依原菜单'),
(31080, 'ORBIT系统管理', 31000, 8, 'system', 'ParentView', 1, 0, 'M', '0', '0', 'system.read', 'system', 'admin', NOW(), 'ORBIT业务系统管理，不覆盖若依原系统管理'),
(31081, '系统配置', 31080, 1, 'configuration', 'orbit/system/configuration/index', 1, 1, 'C', '0', '0', 'system.integrations.manage', 'edit', 'admin', NOW(), 'AI、Meta/BM和其他业务集成配置，密钥只写不读');


-- 配置每个版本仅生成一条审计，唯一约束保证版本游标不丢失记录。
-- 在V001之后执行；历史重复数据须先由管理员核查，不能静默删除。
ALTER TABLE orbit_configuration_audit
    ADD UNIQUE KEY uk_orbit_configuration_audit_revision (tenant_id, config_id, revision)
    COMMENT '租户配置版本唯一，支持变更历史稳定游标分页';


-- 审计旧新状态摘要；在V001、V002之后执行，禁止凭空回填无法还原的历史快照。
ALTER TABLE orbit_configuration_audit
    ADD COLUMN before_revision BIGINT NULL COMMENT '操作前版本；新建为0；迁移前历史未知为NULL' AFTER revision,
    ADD COLUMN before_hash CHAR(64) NULL COMMENT '旧配置规范状态SHA256；新建及迁移前历史为NULL；凭据使用密文信封参与摘要' AFTER before_revision,
    ADD COLUMN after_hash CHAR(64) NULL COMMENT '新配置规范状态SHA256；迁移前历史为NULL；不存Token明文摘要' AFTER before_hash,
    ADD COLUMN hash_algorithm VARCHAR(32) NULL COMMENT '摘要格式版本：SHA256_STATE_V1；迁移前历史未知为NULL' AFTER after_hash;


-- 若依数字用户ID与产品UUID显式映射；若依部门层级不自动授予业务团队管理范围。
CREATE TABLE IF NOT EXISTS orbit_business_team (
    tenant_id CHAR(36) NOT NULL COMMENT '所属租户UUID',
    id CHAR(36) NOT NULL COMMENT '业务团队UUID，不复用若依dept_id',
    name VARCHAR(100) NOT NULL COMMENT '团队名称',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '1启用、0停用，停用立即阻止成员新写入',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '团队信息与状态版本',
    PRIMARY KEY (tenant_id,id),
    FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='ORBIT业务团队目录；管理UI及受控维护入口待接通';
CREATE TABLE IF NOT EXISTS orbit_business_user (
    tenant_id CHAR(36) NOT NULL COMMENT '所属租户UUID',
    id CHAR(36) NOT NULL COMMENT '产品用户UUID，与若依user_id独立',
    user_id BIGINT NOT NULL COMMENT '关联若依sys_user.user_id，停用和删除实时复核',
    team_id CHAR(36) NOT NULL COMMENT '当前业务团队UUID，不改写历史资源冻结归属',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '1启用、0撤销该业务身份',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '业务身份与成员关系版本',
    PRIMARY KEY (tenant_id,id),
    UNIQUE KEY uk_business_user_login (tenant_id,user_id),
    FOREIGN KEY (tenant_id,team_id) REFERENCES orbit_business_team(tenant_id,id),
    FOREIGN KEY (user_id) REFERENCES sys_user(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='业务UUID与若依登录用户映射，按租户唯一';
CREATE TABLE IF NOT EXISTS orbit_business_team_manager (
    tenant_id CHAR(36) NOT NULL COMMENT '授权所属租户UUID',
    manager_user_id BIGINT NOT NULL COMMENT '被授权管理团队的若依用户ID',
    team_id CHAR(36) NOT NULL COMMENT '显式可管理业务团队UUID',
    enabled TINYINT NOT NULL DEFAULT 1 COMMENT '1授权、0撤销，写入及重放重新读取',
    revision BIGINT NOT NULL DEFAULT 1 COMMENT '管理授权版本',
    PRIMARY KEY (tenant_id,manager_user_id,team_id),
    FOREIGN KEY (tenant_id,manager_user_id) REFERENCES orbit_business_user(tenant_id,user_id),
    FOREIGN KEY (tenant_id,team_id) REFERENCES orbit_business_team(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='团队管理显式授权，TEAM_ADMIN不隐含全部团队';

-- 只承接V001已显式映射的默认租户用户1；不会批量授予其他若依管理员或自动推断部门。
INSERT IGNORE INTO orbit_business_team(tenant_id,id,name)
SELECT s.tenant_id,'00000000-0000-0000-0000-000000000001','ORBIT默认团队'
FROM orbit_user_scope s JOIN sys_user u ON u.user_id=s.user_id AND u.status='0' AND u.del_flag='0'
JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1
WHERE s.user_id=1 AND s.tenant_id='00000000-0000-0000-0000-000000000001' AND s.data_role='SUPER_ADMIN' AND s.enabled=1;
INSERT IGNORE INTO orbit_business_user(tenant_id,id,user_id,team_id)
SELECT s.tenant_id,'00000000-0000-0000-0000-000000000001',1,'00000000-0000-0000-0000-000000000001'
FROM orbit_user_scope s JOIN sys_user u ON u.user_id=s.user_id AND u.status='0' AND u.del_flag='0'
JOIN orbit_business_team t ON t.tenant_id=s.tenant_id AND t.id='00000000-0000-0000-0000-000000000001'
WHERE s.user_id=1 AND s.tenant_id='00000000-0000-0000-0000-000000000001' AND s.data_role='SUPER_ADMIN' AND s.enabled=1;


-- Python新实现的幂等摘要密钥版本；旧密钥保留期间可验证相同请求，不存Token的无密钥摘要。
ALTER TABLE orbit_configuration_idempotency ADD COLUMN payload_key_id VARCHAR(40) NULL COMMENT 'HKDF派生HMAC使用的主密钥版本；无敏感替换请求可为NULL';
CREATE TABLE orbit_configuration_outbox (
 event_id CHAR(36) NOT NULL COMMENT '配置审计事件UUID，消费者幂等去重键',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 config_id CHAR(36) NOT NULL COMMENT '配置UUID',
 revision BIGINT NOT NULL COMMENT '对应配置版本',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '同事务创建UTC时刻',
 PRIMARY KEY(event_id),
 KEY idx_config_outbox_tenant (tenant_id,created_at,event_id) COMMENT '租户内稳定批量消费'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='配置变更outbox，与业务和审计同事务；不触发真实广告写入';

-- 从Python第一笔写入起冻结真实审计身份和请求UUID，避免将来通用审计页缺失必填证据。
ALTER TABLE orbit_configuration_audit
 ADD COLUMN actor_subject_id CHAR(36) NOT NULL COMMENT '写入时真实业务操作者UUID，后续调队不反写',
 ADD COLUMN actor_team_id CHAR(36) NOT NULL COMMENT '写入时操作者团队UUID，历史授权依据',
 ADD COLUMN request_id CHAR(36) NOT NULL COMMENT '服务端本次HTTP请求UUID，不接受客户端冒充';
