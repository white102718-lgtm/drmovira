-- 部署前人工执行：数据专员可为空；通过服务校验有效用户，不建立外键。
ALTER TABLE pm_project
    ADD COLUMN data_specialist_id BIGINT UNSIGNED NULL COMMENT '数据专员用户ID，逻辑关联sys_user.id' AFTER delivery_leader_name,
    ADD COLUMN data_specialist VARCHAR(100) NULL COMMENT '数据专员姓名快照，未指定时为空' AFTER data_specialist_id,
    ADD INDEX idx_pm_project_data_specialist (data_specialist_id) COMMENT '数据专员用户关联查询';
