-- 050候选：保留事实原UTC微秒，不重写旧毫秒值、不修改已发布046。
-- 原FK/CHECK/触发器及非NULL保持；旧DATETIME(3)自然扩展为末三位000。
ALTER TABLE orbit_execution_attempt_fact
 MODIFY COLUMN occurred_at DATETIME(6) NOT NULL COMMENT '事实真实发生UTC微秒，来源时钟须核验',
 MODIFY COLUMN recorded_at DATETIME(6) NOT NULL COMMENT '可信SQL实际入库UTC微秒，晚到事实仍保留';
