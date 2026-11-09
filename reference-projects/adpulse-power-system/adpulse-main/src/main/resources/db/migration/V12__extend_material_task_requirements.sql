ALTER TABLE biz_task
    MODIFY owner_id BIGINT UNSIGNED NULL COMMENT '任务总负责人用户ID，待分配时为空',
    MODIFY owner_name VARCHAR(100) NULL COMMENT '任务总负责人姓名快照，待分配时为空';

ALTER TABLE biz_task DROP CHECK ck_biz_task_status;
ALTER TABLE biz_task
    ADD CONSTRAINT ck_biz_task_status CHECK (
        status IN (
            'PENDING_ASSIGNMENT', 'PENDING_CONFIRMATION', 'PROCESSING',
            'PENDING_ACCEPTANCE', 'COMPLETED', 'WITHDRAWN'
        )
    );

ALTER TABLE biz_material_task
    ADD COLUMN language_code VARCHAR(100) NULL COMMENT '素材语言字典值' AFTER demand_type,
    ADD COLUMN green_material TINYINT NOT NULL DEFAULT 0 COMMENT '是否按绿通素材要求产出' AFTER language_code,
    ADD COLUMN department_id BIGINT UNSIGNED NULL COMMENT '创建者所属部门ID快照' AFTER green_material,
    ADD COLUMN department_name VARCHAR(100) NULL COMMENT '创建者所属部门名称快照' AFTER department_id,
    ADD COLUMN product_sub_name VARCHAR(200) NULL COMMENT '用户填写的官方产品子名称' AFTER department_name,
    ADD CONSTRAINT ck_material_task_green CHECK (green_material IN (0, 1));

ALTER TABLE biz_material_task
    ALTER COLUMN add_to_library SET DEFAULT 0;

CREATE TABLE biz_material_task_requirement (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '素材需求描述ID',
    task_id BIGINT UNSIGNED NOT NULL COMMENT '逻辑关联biz_task.id',
    sort_order INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '展示顺序',
    description VARCHAR(2000) NOT NULL COMMENT '需求描述',
    duration_text VARCHAR(50) NULL COMMENT '时长自由文本',
    quantity INT UNSIGNED NOT NULL COMMENT '本项交付数量',
    related_link VARCHAR(2000) NULL COMMENT '相关链接',
    remark VARCHAR(2000) NULL COMMENT '备注',
    compliance_requirement VARCHAR(2000) NULL COMMENT '合规要求',
    created_by BIGINT UNSIGNED NOT NULL COMMENT '创建操作用户ID',
    updated_by BIGINT UNSIGNED NOT NULL COMMENT '最后修改用户ID',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_material_requirement_order_deleted (task_id, sort_order, deleted_at),
    KEY idx_material_requirement_task (task_id, deleted_at, sort_order),
    CONSTRAINT ck_material_requirement_quantity CHECK (quantity > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='素材任务需求描述明细';

ALTER TABLE biz_task_file_binding DROP CHECK ck_task_file_target;
ALTER TABLE biz_task_file_binding
    ADD CONSTRAINT ck_task_file_target CHECK (
        target_type IN (
            'DELIVERY_TASK', 'MATERIAL_TASK', 'MATERIAL_REQUIREMENT',
            'DELIVERY_SUBMISSION', 'MATERIAL_SUBMISSION'
        )
    );
