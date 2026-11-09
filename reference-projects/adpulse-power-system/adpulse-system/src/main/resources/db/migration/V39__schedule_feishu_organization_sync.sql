-- 人工审核后部署前执行；不由应用启动自动迁移。无外键，逻辑引用由事务服务维护。
CREATE TABLE sys_feishu_org_schedule (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '单组织计划，固定使用 ID 1',
    enabled TINYINT NOT NULL DEFAULT 0 COMMENT '自动同步开关：0关闭，1开启',
    interval_minutes INT NOT NULL DEFAULT 60 COMMENT '间隔分钟：15、30、60；0表示每天指定时间',
    daily_time CHAR(5) NOT NULL DEFAULT '02:00' COMMENT '每日执行时间 HH:mm，北京时间',
    missing_count_limit INT NOT NULL DEFAULT 10 COMMENT '任一类别缺失停用数量达到此值时拦截',
    missing_percent_limit INT NOT NULL DEFAULT 20 COMMENT '任一类别缺失占现有启用记录百分比达到此值时拦截',
    verified_app_hash CHAR(64) NULL COMMENT '已预览应用配置的 SHA-256 摘要，不存储明文凭据',
    next_run_at DATETIME(3) NULL COMMENT '下次调度时间 UTC；停用时为空',
    updated_by BIGINT UNSIGNED NULL COMMENT '配置人，逻辑关联 sys_user.id',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后修改时间',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0有效，否则为软删除毫秒时间戳',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='飞书组织自动同步配置及跨实例事务互斥入口';

INSERT INTO sys_feishu_org_schedule (id) VALUES (1);

-- 部署需先停止旧版本同步入口；历史未完成日志不能占用新版本唯一活动槽。
UPDATE sys_feishu_org_sync_log
SET status = 'FAILED', ended_at = CURRENT_TIMESTAMP(3), error_message = '版本升级中断，请重新预览后同步'
WHERE status = 'RUNNING' AND deleted_at = 0;

ALTER TABLE sys_feishu_org_sync_log
    MODIFY started_by BIGINT UNSIGNED NULL COMMENT '人工操作用户ID；系统调度为空',
    MODIFY trigger_type VARCHAR(16) NOT NULL COMMENT 'PREVIEW预览、MANUAL手动、SCHEDULED定时',
    MODIFY status VARCHAR(16) NOT NULL COMMENT 'PENDING待执行、RUNNING执行中、SUCCESS成功、FAILED失败、REVIEW待确认、SKIPPED跳过',
    ADD snapshot_hash CHAR(64) NULL COMMENT '人工预览快照及本地组织基线摘要',
    ADD app_hash CHAR(64) NULL COMMENT '任务绑定的应用配置摘要',
    ADD accept_missing TINYINT NOT NULL DEFAULT 0 COMMENT '是否人工确认本次预览中的超限缺失停用',
    ADD attempts INT NOT NULL DEFAULT 0 COMMENT '执行次数，同时作为过期工作线程的隔离版本',
    ADD available_at DATETIME(3) NULL COMMENT '最早认领时间 UTC，用于有限退避重试',
    ADD lease_until DATETIME(3) NULL COMMENT '任务执行租约截止 UTC，超时后禁止写入',
    ADD active_slot TINYINT GENERATED ALWAYS AS
        (CASE WHEN deleted_at = 0 AND trigger_type <> 'PREVIEW' AND status IN ('PENDING','RUNNING') THEN 1 ELSE NULL END) STORED
        COMMENT '唯一活动槽；数据库保证手动与定时合计最多一个活动任务',
    ADD UNIQUE KEY uk_feishu_org_active_slot (active_slot),
    ADD KEY idx_feishu_org_pending (status, available_at, deleted_at);
