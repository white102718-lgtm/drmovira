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
