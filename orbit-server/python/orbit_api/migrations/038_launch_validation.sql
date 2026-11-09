-- 原validate的成功冻结记录；只记录实际完整预检，不开放execute或广告写入。
-- 配置源仍指向021不可变版本，Plan.revision独立作为内容/状态CAS头。
CREATE TABLE orbit_launch_validation (
 tenant_id CHAR(36) NOT NULL COMMENT '当前授权上下文租户UUID，外键均带租户',
 id CHAR(36) NOT NULL COMMENT '本次成功冻结记录UUID，不是Task或分配运行时ID',
 plan_id CHAR(36) NOT NULL COMMENT '真实投放计划UUID',
 source_revision BIGINT NOT NULL COMMENT '021最新不可变配置版本，纯状态变化不重绑名称或分配',
 validated_head_revision BIGINT NOT NULL COMMENT '本次预检成功CAS后的外部Plan.revision',
 payload_hash CHAR(64) NOT NULL COMMENT '对应配置源的规范完整JSON摘要，不代替预检hash',
 validation_hash CHAR(64) NOT NULL COMMENT '原schema1完整展开树及来源版本的SHA256',
 validated_at DATETIME(3) NOT NULL COMMENT '完成真实预检的UTC毫秒时刻，不用客户端时钟',
 expires_at DATETIME(3) NOT NULL COMMENT '验证完成后十五分钟UTC时刻，上海跨日另外即时失效',
 naming_date DATE NOT NULL COMMENT '冻结名称的Asia/Shanghai业务日，重试不改名',
 scope_version BIGINT NOT NULL COMMENT '当前已验证目录范围版本，提交前仍重新核权限',
 allocation_id CHAR(36) NOT NULL COMMENT '同配置源且完整SUCCEEDED的实际素材分配UUID',
 name_reservation_id CHAR(36) NOT NULL COMMENT '同配置源和上海命名日的实际名称保留UUID',
 provider_kind VARCHAR(16) NOT NULL COMMENT 'TRUSTED正式来源或仅专属测试库ISOLATED_TEST',
 provider_fingerprint CHAR(64) NOT NULL COMMENT '权威观察引用及版本的完整来源摘要，不接受自报verified',
 summary_json JSON NOT NULL COMMENT '严格十字段成功PlanValidation；不保存平台Token或任意来源正文',
 observation_refs_json JSON NOT NULL COMMENT '仅kind、业务UUID和版本的受信观察引用，最多四千项一MiB',
 created_by BIGINT NOT NULL COMMENT '实际执行本次预检的若依用户ID，仅审计不替代冻结拥有者',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '成功事务记录创建UTC毫秒时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_launch_validation_head(tenant_id,plan_id,validated_head_revision)
 COMMENT '同计划一次成功CAS头只能对应一条不可变预检记录',
 KEY idx_launch_validation_source(tenant_id,plan_id,source_revision,validated_at,id)
 COMMENT '同配置源预检历史按时间与UUID有界续页',
 KEY idx_launch_validation_expiry(tenant_id,expires_at,id)
 COMMENT '过期观察有界定位；存在执行历史引用时不得物理删除',
 FOREIGN KEY(tenant_id,plan_id,source_revision)
 REFERENCES orbit_launch_plan_version(tenant_id,plan_id,revision),
 FOREIGN KEY(tenant_id,allocation_id) REFERENCES orbit_launch_allocation(tenant_id,id),
 FOREIGN KEY(tenant_id,name_reservation_id) REFERENCES orbit_launch_name_reservation(tenant_id,id),
 CONSTRAINT ck_launch_validation_source CHECK(source_revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_launch_validation_head CHECK(validated_head_revision>source_revision
 AND validated_head_revision<=9007199254740991),
 CONSTRAINT ck_launch_validation_scope CHECK(scope_version BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_launch_validation_provider CHECK(provider_kind IN('TRUSTED','ISOLATED_TEST')),
 CONSTRAINT ck_launch_validation_ttl CHECK(
 TIMESTAMPDIFF(MICROSECOND,validated_at,expires_at)=900000000),
 CONSTRAINT ck_launch_validation_day CHECK(naming_date=DATE(validated_at+INTERVAL 8 HOUR)),
 CONSTRAINT ck_launch_validation_summary CHECK(JSON_TYPE(summary_json)='OBJECT'
 AND JSON_LENGTH(summary_json)=10 AND OCTET_LENGTH(summary_json)<=131072
 AND JSON_CONTAINS_PATH(summary_json,'all','$.valid','$.hash','$.expires_at','$.errors',
 '$.campaign_count','$.adset_count','$.ad_count','$.budget_totals','$.scope_version',
 '$.total_dag_node_count')=1
 AND JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.valid'))='true'
 AND JSON_UNQUOTE(JSON_EXTRACT(summary_json,'$.hash'))=validation_hash
 AND JSON_TYPE(JSON_EXTRACT(summary_json,'$.errors'))='ARRAY'
 AND JSON_LENGTH(JSON_EXTRACT(summary_json,'$.errors'))=0),
 CONSTRAINT ck_launch_validation_observations CHECK(JSON_TYPE(observation_refs_json)='ARRAY'
 AND JSON_LENGTH(observation_refs_json)<=4000 AND OCTET_LENGTH(observation_refs_json)<=1048576)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
COMMENT='原预检完整成功的不可变冻结记录；不授予命令发送或平台创建许可';
