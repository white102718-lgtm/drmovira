-- 061正式：规则编辑私有范围与manifest双来源；保留原025四表及其权限，验收范围见具名回执。
-- MySQL8.4: https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html
-- FK: https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html
-- COPY: https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html
-- atomic != transactional: https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html
-- 维护窗口：新增STORED列需要ALGORITHM=COPY，需测空间/MDL/复制延迟，不能称无阻塞升级。
-- 每条DDL原子，不代表本文件多DDL可事务整体回滚。应用写方须停在维护边界。
-- 前置精确核057原FK名orbit_rule_scope_manifest_ibfk_2确指(tenant_id,source_snapshot_id)
-- ->orbit_account_scope_snapshot(tenant_id,id)，其余FK/trigger的SHOW CREATE摘要必须保存并匹配。
-- 原057未显式命名该FK；该名由第二条FOREIGN KEY自动生成，只按核对后精确名drop，不模糊匹配。

CREATE TABLE orbit_rule_editor_scope_snapshot (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID，不接受跨租户上下文',
 id CHAR(36) NOT NULL COMMENT '规则编辑私有范围UUID，不属于原账户scope API',
 actor_id BIGINT NOT NULL COMMENT '经原rules.create或rules.edit授权的真实创建者',
 action VARCHAR(6) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原规则CREATE或UPDATE动作',
 rule_id CHAR(36) NULL COMMENT 'UPDATE真实锁定规则UUID；CREATE为空，不授历史规则读取权',
 rule_revision BIGINT NULL COMMENT 'UPDATE创建时真实规则版本，CREATE为空',
 owner_user_id CHAR(36) NOT NULL COMMENT '目标业务拥有者UUID，须双方当前账户范围交集',
 owner_team_id CHAR(36) NOT NULL COMMENT '目标拥有者当前团队UUID',
 scope_version BIGINT NOT NULL COMMENT '创建者真实身份授权版本，非账户目录水位',
 auth_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '创建者动作和当前数据范围指纹',
 owner_auth_fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '目标拥有者当前有效身份及数据范围指纹',
 account_clock_revision BIGINT NOT NULL COMMENT '冻结时真实账户目录水位，仅审计不作为永久授权',
 request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '规则范围专属幂等键，与原账户scope完全隔离',
 request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '动作规则owner和规范选择正文的SHA256',
 request_json JSON NOT NULL COMMENT '动作归属与原IDS或FILTER规范选择，不含凭据或权限票据',
 member_count INT NOT NULL DEFAULT 0 COMMENT '完整成员数量1至50000，构建时为零，不截断',
 members_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '完整七列排序成员规范SHA256，构建时为空',
 ready BOOLEAN NOT NULL DEFAULT 0 COMMENT '仅完整成员及同事务审计写入时发布，不是平台授权',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实冻结UTC毫秒时刻，重放不改写',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_editor_scope_request(tenant_id,actor_id,request_key),
 KEY idx_rule_editor_scope_actor(tenant_id,actor_id,created_at,id) COMMENT '创建者私有历史有界键集',
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY(tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CHECK((action='CREATE' AND rule_id IS NULL AND rule_revision IS NULL)
    OR (action='UPDATE' AND rule_id IS NOT NULL AND rule_revision IS NOT NULL
        AND rule_revision BETWEEN 1 AND 9007199254740991)),
 CHECK(scope_version BETWEEN 1 AND 9007199254740991),
 CHECK(account_clock_revision BETWEEN 1 AND 9007199254740991),
 CHECK(REGEXP_LIKE(auth_fingerprint,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(owner_auth_fingerprint,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(request_hash,'^[0-9a-f]{64}$','c')),
 CHECK(JSON_TYPE(request_json)='OBJECT'),
 CHECK(ready IN(0,1)),
 CHECK((ready=0 AND member_count=0 AND members_hash IS NULL)
    OR (ready=1 AND member_count BETWEEN 1 AND 50000 AND members_hash IS NOT NULL
        AND REGEXP_LIKE(members_hash,'^[0-9a-f]{64}$','c')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='原规则动作私有冻结选择，与账户scope隔离';

CREATE TABLE orbit_rule_editor_scope_member (
 tenant_id CHAR(36) NOT NULL COMMENT '范围真实租户UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '本规则编辑私有范围UUID',
 account_id CHAR(36) NOT NULL COMMENT '真实账户业务UUID，不是平台外部ID',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '冻结平台数字ID，保留前导零',
 name LONGTEXT NOT NULL COMMENT '冻结完整名称，改名不重写历史',
 name_prefix VARCHAR(191) NOT NULL COMMENT '冻结名称前缀检索列，不替代完整名称',
 account_revision BIGINT NOT NULL COMMENT '冻结账户版本审计字段，消费时重验真实成员权限',
 owner_user_id CHAR(36) NOT NULL COMMENT '冻结时账户拥有者',
 owner_team_id CHAR(36) NOT NULL COMMENT '冻结时账户团队',
 currency CHAR(3) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原账户币种可未知，不猜USD或强制同币种',
 PRIMARY KEY(tenant_id,snapshot_id,account_id),
 KEY idx_rule_editor_scope_name(tenant_id,snapshot_id,name_prefix,account_id) COMMENT '私有成员名称前缀及UUID键集',
 FOREIGN KEY(tenant_id,snapshot_id) REFERENCES orbit_rule_editor_scope_snapshot(tenant_id,id),
 CHECK(account_revision BETWEEN 1 AND 9007199254740991),
 CHECK(currency IS NULL OR REGEXP_LIKE(currency,'^[A-Z]{3}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则编辑完整冻结成员，不复制实时广告事实';

CREATE TABLE orbit_rule_editor_scope_event (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 id CHAR(36) NOT NULL COMMENT '不可变成功事件UUID',
 snapshot_id CHAR(36) NOT NULL COMMENT '本次完整发布私有范围UUID',
 actor_id BIGINT NOT NULL COMMENT '真实创建会话操作者',
 request_id CHAR(36) NOT NULL COMMENT '服务端安全请求UUID，不含正文或凭据',
 member_count INT NOT NULL COMMENT '完整发布成员数量',
 members_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整有序七列快照摘要',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '真实成功UTC毫秒时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_rule_editor_scope_event(tenant_id,snapshot_id),
 UNIQUE KEY uq_rule_editor_scope_event_bind(tenant_id,id,snapshot_id),
 FOREIGN KEY(tenant_id,snapshot_id) REFERENCES orbit_rule_editor_scope_snapshot(tenant_id,id),
 CHECK(member_count BETWEEN 1 AND 50000),
 CHECK(REGEXP_LIKE(members_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则范围只追加成功审计，与成员及幂等结果同事务';

CREATE TABLE orbit_rule_editor_scope_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 event_id CHAR(36) NOT NULL COMMENT '精确关联成功事件UUID，消费者按此去重',
 snapshot_id CHAR(36) NOT NULL COMMENT '与成功事件精确相同的范围UUID',
 state VARCHAR(7) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'PENDING' COMMENT '仅PENDING到DONE单调完成，不等于已执行广告',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '原子发布UTC毫秒时刻',
 PRIMARY KEY(tenant_id,event_id),
 KEY idx_rule_editor_scope_pending(state,created_at,tenant_id,event_id) COMMENT '事务outbox有界待投递键集',
 FOREIGN KEY(tenant_id,event_id,snapshot_id) REFERENCES orbit_rule_editor_scope_event(tenant_id,id,snapshot_id),
 CHECK(state IN('PENDING','DONE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='规则范围成功审计事务outbox，未自动注册消费者';

-- 单条COPY ALTER使原单源FK到双源FK替换本身原子；不删旧trigger，不做旧行UPDATE回填。
-- 两生成列显式同原字符集/排序规则，ACCOUNT旧行通过DEFAULT计算原ID，hash/正文完全保留。
-- 省略ON UPDATE/DELETE以使用默认RESTRICT，避免CHECK列的显式referential-action限制。
ALTER TABLE orbit_rule_scope_manifest
 DROP FOREIGN KEY orbit_rule_scope_manifest_ibfk_2,
 ADD COLUMN source_kind VARCHAR(7) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'ACCOUNT'
   COMMENT '真实范围来源ACCOUNT原私有快照或RULE规则编辑私有快照，封存后不可切换',
 ADD COLUMN account_source_snapshot_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs
   GENERATED ALWAYS AS (CASE WHEN source_kind='ACCOUNT' THEN source_snapshot_id ELSE NULL END) STORED
   COMMENT 'ACCOUNT来源精确外键生成列，不由请求赋值',
 ADD COLUMN rule_source_snapshot_id CHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs
   GENERATED ALWAYS AS (CASE WHEN source_kind='RULE' THEN source_snapshot_id ELSE NULL END) STORED
   COMMENT 'RULE来源精确外键生成列，不由请求赋值',
 ADD KEY idx_rule_manifest_account_source(tenant_id,account_source_snapshot_id) COMMENT '原快照来源精确外键及逆查',
 ADD KEY idx_rule_manifest_editor_source(tenant_id,rule_source_snapshot_id,rule_id) COMMENT '规则编辑快照来源精确外键及跨规则绑定逆查',
 ADD CONSTRAINT ck_rule_manifest_source_kind CHECK(source_kind IN('ACCOUNT','RULE')),
 ADD CONSTRAINT ck_rule_manifest_source_xor CHECK(
   (source_kind='ACCOUNT' AND account_source_snapshot_id IS NOT NULL AND rule_source_snapshot_id IS NULL)
   OR (source_kind='RULE' AND account_source_snapshot_id IS NULL AND rule_source_snapshot_id IS NOT NULL)),
 ADD CONSTRAINT fk_rule_manifest_account_source FOREIGN KEY(tenant_id,account_source_snapshot_id)
   REFERENCES orbit_account_scope_snapshot(tenant_id,id),
 ADD CONSTRAINT fk_rule_manifest_editor_source FOREIGN KEY(tenant_id,rule_source_snapshot_id)
   REFERENCES orbit_rule_editor_scope_snapshot(tenant_id,id),
 ALGORITHM=COPY;

-- 旧manifest trigger仍精确控制source_snapshot_id/hash/sealed；不在trigger引用任何生成列。
CREATE TRIGGER rule_manifest_source_kind_update BEFORE UPDATE ON orbit_rule_scope_manifest FOR EACH ROW BEGIN
 IF NOT(NEW.source_kind<=>OLD.source_kind)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_MANIFEST_SOURCE_IMMUTABLE'; END IF;
END;

CREATE TRIGGER rule_editor_scope_insert BEFORE INSERT ON orbit_rule_editor_scope_snapshot FOR EACH ROW BEGIN
 IF NEW.ready<>0 OR NEW.member_count<>0 OR NEW.members_hash IS NOT NULL
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_BUILDING_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_editor_scope_update BEFORE UPDATE ON orbit_rule_editor_scope_snapshot FOR EACH ROW BEGIN
 IF OLD.ready<>0 OR NEW.ready<>1 OR NOT(NEW.tenant_id<=>OLD.tenant_id)
 OR NOT(NEW.id<=>OLD.id) OR NOT(NEW.actor_id<=>OLD.actor_id)
 OR NOT(NEW.action<=>OLD.action) OR NOT(NEW.rule_id<=>OLD.rule_id)
 OR NOT(NEW.rule_revision<=>OLD.rule_revision)
 OR NOT(NEW.owner_user_id<=>OLD.owner_user_id) OR NOT(NEW.owner_team_id<=>OLD.owner_team_id)
 OR NOT(NEW.scope_version<=>OLD.scope_version)
 OR NOT(NEW.auth_fingerprint<=>OLD.auth_fingerprint)
 OR NOT(NEW.owner_auth_fingerprint<=>OLD.owner_auth_fingerprint)
 OR NOT(NEW.account_clock_revision<=>OLD.account_clock_revision)
 OR NOT(NEW.request_key<=>OLD.request_key) OR NOT(NEW.request_hash<=>OLD.request_hash)
 OR NOT(NEW.request_json<=>OLD.request_json) OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_IMMUTABLE'; END IF;
 IF NEW.member_count<>(SELECT COUNT(*) FROM orbit_rule_editor_scope_member
 WHERE tenant_id=OLD.tenant_id AND snapshot_id=OLD.id)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_COUNT_MISMATCH'; END IF;
END;
CREATE TRIGGER rule_editor_scope_delete BEFORE DELETE ON orbit_rule_editor_scope_snapshot FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_IMMUTABLE';
CREATE TRIGGER rule_editor_scope_member_insert BEFORE INSERT ON orbit_rule_editor_scope_member FOR EACH ROW BEGIN
 DECLARE published INT DEFAULT NULL;
 SELECT ready INTO published FROM orbit_rule_editor_scope_snapshot
 WHERE tenant_id=NEW.tenant_id AND id=NEW.snapshot_id FOR SHARE;
 IF published IS NULL OR published<>0
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_MEMBER_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_editor_scope_member_update BEFORE UPDATE ON orbit_rule_editor_scope_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_MEMBER_IMMUTABLE';
CREATE TRIGGER rule_editor_scope_member_delete BEFORE DELETE ON orbit_rule_editor_scope_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_MEMBER_IMMUTABLE';
CREATE TRIGGER rule_editor_scope_event_insert BEFORE INSERT ON orbit_rule_editor_scope_event FOR EACH ROW BEGIN
 DECLARE published INT DEFAULT NULL; DECLARE actual_actor BIGINT DEFAULT NULL;
 DECLARE actual_count INT DEFAULT NULL; DECLARE actual_hash CHAR(64) DEFAULT NULL;
 SELECT ready,actor_id,member_count,members_hash INTO published,actual_actor,actual_count,actual_hash
 FROM orbit_rule_editor_scope_snapshot WHERE tenant_id=NEW.tenant_id AND id=NEW.snapshot_id FOR SHARE;
 IF published IS NULL OR published<>1 OR actual_actor IS NULL OR actual_count IS NULL OR actual_hash IS NULL
 OR NEW.actor_id<>actual_actor OR NEW.member_count<>actual_count OR NOT(NEW.members_hash<=>actual_hash)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_COMPLETE_EVENT_REQUIRED'; END IF;
END;
CREATE TRIGGER rule_editor_scope_event_update BEFORE UPDATE ON orbit_rule_editor_scope_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_EVENT_IMMUTABLE';
CREATE TRIGGER rule_editor_scope_event_delete BEFORE DELETE ON orbit_rule_editor_scope_event FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_EVENT_IMMUTABLE';
CREATE TRIGGER rule_editor_scope_outbox_update BEFORE UPDATE ON orbit_rule_editor_scope_outbox FOR EACH ROW BEGIN
 IF OLD.state<>'PENDING' OR NEW.state<>'DONE'
 OR NOT(NEW.tenant_id<=>OLD.tenant_id) OR NOT(NEW.event_id<=>OLD.event_id)
 OR NOT(NEW.snapshot_id<=>OLD.snapshot_id) OR NOT(NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_OUTBOX_IMMUTABLE'; END IF;
END;
CREATE TRIGGER rule_editor_scope_outbox_delete BEFORE DELETE ON orbit_rule_editor_scope_outbox FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='RULE_EDITOR_SCOPE_OUTBOX_IMMUTABLE';
