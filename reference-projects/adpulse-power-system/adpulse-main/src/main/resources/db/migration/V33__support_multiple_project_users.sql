-- 项目 AM 多选关系；用户有效性由事务服务校验，不建立数据库外键。
CREATE TABLE pm_project_am (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '关系ID',
    project_id BIGINT UNSIGNED NOT NULL COMMENT '项目ID，逻辑关联pm_project.id',
    user_id BIGINT UNSIGNED NOT NULL COMMENT 'AM用户ID，逻辑关联sys_user.id',
    user_name VARCHAR(100) NOT NULL COMMENT 'AM姓名快照',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '页面展示顺序',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建人用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改人用户ID',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0表示有效，否则为软删除毫秒时间戳',
    PRIMARY KEY (id),
    UNIQUE KEY uk_project_am_user_deleted (project_id, user_id, deleted_at),
    KEY idx_project_am_user (user_id, project_id, deleted_at)
) COMMENT='项目AM多选关系';

CREATE TABLE pm_project_data_specialist LIKE pm_project_am;
ALTER TABLE pm_project_data_specialist
    MODIFY COLUMN user_id BIGINT UNSIGNED NOT NULL COMMENT '数据专员用户ID，逻辑关联sys_user.id',
    MODIFY COLUMN user_name VARCHAR(100) NOT NULL COMMENT '数据专员姓名快照',
    COMMENT = '项目数据专员多选关系';

CREATE TABLE biz_delivery_task_am LIKE pm_project_am;
ALTER TABLE biz_delivery_task_am
    CHANGE COLUMN project_id task_id BIGINT UNSIGNED NOT NULL COMMENT '投放任务ID，逻辑关联biz_task.id',
    MODIFY COLUMN user_id BIGINT UNSIGNED NOT NULL COMMENT '任务AM用户ID快照',
    MODIFY COLUMN user_name VARCHAR(100) NOT NULL COMMENT '任务AM姓名快照',
    COMMENT = '投放任务创建或重新提交时的项目AM快照';

INSERT INTO pm_project_am (project_id, user_id, user_name, sort_order, created_by, updated_by)
SELECT id, am_user_id, am_name, 0, created_by, updated_by
FROM pm_project WHERE deleted_at = 0 AND am_user_id IS NOT NULL;

INSERT INTO pm_project_data_specialist (project_id, user_id, user_name, sort_order, created_by, updated_by)
SELECT id, data_specialist_id, data_specialist, 0, created_by, updated_by
FROM pm_project WHERE deleted_at = 0 AND data_specialist_id IS NOT NULL;

INSERT INTO biz_delivery_task_am (task_id, user_id, user_name, sort_order, created_by, updated_by)
SELECT delivery.task_id, delivery.am_user_id, delivery.am_user_name, 0,
       task.created_by, task.updated_by
FROM biz_delivery_task delivery
INNER JOIN biz_task task ON task.id = delivery.task_id AND task.deleted_at = 0
WHERE delivery.deleted_at = 0 AND delivery.am_user_id IS NOT NULL;
