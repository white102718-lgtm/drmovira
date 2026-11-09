-- 原TaskEvent正文七天；UUID4游标身份保存至Task生命周期结束，不能用floor猜旧UUID。
CREATE TABLE orbit_task_event_cursor (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实任务，不提供跨任务查找',
 event_id CHAR(36) NOT NULL COMMENT '真实事件UUID，正文删除后仍可判定410',
 sequence BIGINT NOT NULL COMMENT '真实每任务递增序号',
 occurred_at DATETIME(3) NOT NULL COMMENT '原持久事件UTC',
 expires_at DATETIME(3) NOT NULL COMMENT '原事件UTC加七天，逻辑过期独立物理清理',
 PRIMARY KEY(tenant_id,task_id,event_id),
 UNIQUE KEY uk_task_cursor_sequence(tenant_id,task_id,sequence),
 UNIQUE KEY uk_task_cursor_event(tenant_id,event_id),
 KEY idx_task_cursor_expiry(tenant_id,task_id,expires_at,sequence),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
 COMMENT='事件UUID4最小身份目录；不按七天删除，不存事件正文';
CREATE TABLE orbit_task_event_retention (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户',
 task_id CHAR(36) NOT NULL COMMENT '真实任务',
 purged_through_sequence BIGINT NOT NULL DEFAULT 0 COMMENT '物理裁剪已触及序号，仅辅助水位不替代UUID目录',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '真实清理版本',
 PRIMARY KEY(tenant_id,task_id),
 FOREIGN KEY(tenant_id,task_id) REFERENCES orbit_task(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='事件正文分批清理水位';
-- 迁移时尚无生产事件写方；只从实际存量回填，不能捏造已丢失的事件身份。
INSERT INTO orbit_task_event_cursor(tenant_id,task_id,event_id,sequence,occurred_at,expires_at)
 SELECT tenant_id,task_id,event_id,sequence,occurred_at,DATE_ADD(occurred_at,INTERVAL 7 DAY)
 FROM orbit_task_event;
INSERT INTO orbit_task_event_retention(tenant_id,task_id)
 SELECT tenant_id,task_id FROM orbit_task_event GROUP BY tenant_id,task_id;
-- 同事务目录保障也覆盖冻结的T1初始发布；触发器失败整个原事件写事务回滚。
CREATE TRIGGER orbit_task_event_cursor_insert AFTER INSERT ON orbit_task_event
 FOR EACH ROW
  INSERT INTO orbit_task_event_cursor(tenant_id,task_id,event_id,sequence,occurred_at,expires_at)
   VALUES(NEW.tenant_id,NEW.task_id,NEW.event_id,NEW.sequence,NEW.occurred_at,
    DATE_ADD(NEW.occurred_at,INTERVAL 7 DAY));
