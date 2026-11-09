-- 仅内部成功可见性证明；不改变原ScopeSnapshot/Member响应、hash或幂等合同。
ALTER TABLE orbit_account_scope_snapshot
 ADD COLUMN cleanup_requested BOOLEAN NOT NULL DEFAULT 0
 COMMENT '内部原子清理标记；置真后所有新读取失败关闭，不是公开删除接口' AFTER ready,
 ADD CONSTRAINT chk_scope_cleanup_boolean CHECK(cleanup_requested IN (0,1)),
 ADD CONSTRAINT chk_scope_ready_boolean CHECK(ready IN (0,1));

CREATE TABLE orbit_scope_access_verdict (
 tenant_id CHAR(36) NOT NULL COMMENT '当前可信租户UUID，随同快照外键约束',
 snapshot_id CHAR(36) NOT NULL COMMENT '已ready且未清理的不可变范围UUID',
 actor_id BIGINT NOT NULL COMMENT '原创建人当前真实原生用户ID，不能由浏览器指定证明',
 auth_version BIGINT NOT NULL COMMENT '本次完整验证的实时身份授权版本',
 auth_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '当前主体角色团队及显式管理范围SHA256',
 account_version BIGINT NOT NULL COMMENT '共享锁保护的账户时钟版本，任意账户写入后失效',
 members_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原不可变完整成员摘要，不重写历史hash',
 member_count INT NOT NULL COMMENT '原完整成员数，允许合法空范围，不截断50000上限',
 predicate_version BIGINT NOT NULL COMMENT '当前可见性谓词实现版本，升级后旧证明不复用',
 verified_at DATETIME(3) NOT NULL COMMENT '最近一次实际完整校验成功UTC时刻，不作TTL许可',
 PRIMARY KEY(tenant_id,snapshot_id,actor_id) COMMENT '按租户快照创建人唯一定位，不随访问次数追加',
 CONSTRAINT fk_scope_verdict_snapshot FOREIGN KEY(tenant_id,snapshot_id)
  REFERENCES orbit_account_scope_snapshot(tenant_id,id),
 CONSTRAINT chk_scope_verdict_actor CHECK(actor_id>0),
 CONSTRAINT chk_scope_verdict_versions CHECK(auth_version BETWEEN 1 AND 9007199254740991
  AND account_version BETWEEN 1 AND 9007199254740991
  AND predicate_version BETWEEN 1 AND 9007199254740991),
 CONSTRAINT chk_scope_verdict_count CHECK(member_count BETWEEN 0 AND 50000),
 CONSTRAINT chk_scope_verdict_hashes CHECK(auth_digest REGEXP '^[0-9a-f]{64}$'
  AND members_hash REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='每快照创建人最多一行正向可见性证明，不是授权缓存或执行许可';

CREATE TRIGGER scope_snapshot_insert_guard BEFORE INSERT ON orbit_account_scope_snapshot
FOR EACH ROW BEGIN
 IF NEW.ready<>0 OR NEW.cleanup_requested<>0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_CREATION_MUST_START_UNREADY';
 END IF;
END;

CREATE TRIGGER scope_snapshot_update_guard BEFORE UPDATE ON orbit_account_scope_snapshot
FOR EACH ROW BEGIN
 IF OLD.ready=1 AND (
  NOT (NEW.tenant_id <=> OLD.tenant_id) OR NOT (NEW.id <=> OLD.id) OR
  NOT (NEW.actor_id <=> OLD.actor_id) OR NOT (NEW.scope_version <=> OLD.scope_version) OR
  NOT (NEW.auth_fingerprint <=> OLD.auth_fingerprint) OR
  NOT (NEW.request_key <=> OLD.request_key) OR NOT (NEW.request_hash <=> OLD.request_hash) OR
  NOT (NEW.request_json <=> OLD.request_json) OR NOT (NEW.member_count <=> OLD.member_count) OR
  NOT (NEW.members_hash <=> OLD.members_hash) OR NOT (NEW.ready <=> OLD.ready) OR
  NOT (NEW.created_at <=> OLD.created_at)
 ) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_SNAPSHOT_IMMUTABLE';
 END IF;
 IF (OLD.cleanup_requested=1 AND NEW.cleanup_requested<>1) OR
    (OLD.ready=0 AND NEW.cleanup_requested<>0) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_CLEANUP_TRANSITION_INVALID';
 END IF;
 IF NEW.ready=1 AND (NEW.members_hash IS NULL OR NEW.member_count NOT BETWEEN 0 AND 50000
  OR NEW.members_hash NOT REGEXP '^[0-9a-f]{64}$') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_METADATA_INVALID';
 END IF;
END;

CREATE TRIGGER scope_snapshot_delete_guard BEFORE DELETE ON orbit_account_scope_snapshot
FOR EACH ROW BEGIN
 IF OLD.ready=1 AND OLD.cleanup_requested=0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_CLEANUP_REQUIRED';
 END IF;
END;

CREATE TRIGGER scope_member_insert_guard BEFORE INSERT ON orbit_account_scope_member
FOR EACH ROW BEGIN
 DECLARE parent_ready BOOLEAN DEFAULT NULL;
 SELECT ready INTO parent_ready FROM orbit_account_scope_snapshot
  WHERE tenant_id=NEW.tenant_id AND id=NEW.snapshot_id FOR SHARE;
 IF parent_ready IS NULL OR parent_ready<>0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_MEMBERS_IMMUTABLE';
 END IF;
END;

CREATE TRIGGER scope_member_update_guard BEFORE UPDATE ON orbit_account_scope_member
FOR EACH ROW BEGIN
 DECLARE parent_ready BOOLEAN DEFAULT NULL;
 SELECT ready INTO parent_ready FROM orbit_account_scope_snapshot
  WHERE tenant_id=OLD.tenant_id AND id=OLD.snapshot_id FOR SHARE;
 IF parent_ready IS NULL OR parent_ready<>0 THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_MEMBERS_IMMUTABLE';
 END IF;
 IF NOT (NEW.tenant_id <=> OLD.tenant_id) OR NOT (NEW.snapshot_id <=> OLD.snapshot_id) THEN
  SET parent_ready=NULL;
  SELECT ready INTO parent_ready FROM orbit_account_scope_snapshot
   WHERE tenant_id=NEW.tenant_id AND id=NEW.snapshot_id FOR SHARE;
  IF parent_ready IS NULL OR parent_ready<>0 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_MEMBERS_IMMUTABLE';
  END IF;
 END IF;
END;

CREATE TRIGGER scope_member_delete_guard BEFORE DELETE ON orbit_account_scope_member
FOR EACH ROW BEGIN
 DECLARE parent_ready BOOLEAN DEFAULT NULL;
 DECLARE parent_cleanup BOOLEAN DEFAULT NULL;
 SELECT ready,cleanup_requested INTO parent_ready,parent_cleanup
  FROM orbit_account_scope_snapshot
  WHERE tenant_id=OLD.tenant_id AND id=OLD.snapshot_id FOR SHARE;
 IF parent_ready IS NULL OR (parent_ready=1 AND parent_cleanup<>1) THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='SCOPE_READY_MEMBERS_IMMUTABLE';
 END IF;
END;
