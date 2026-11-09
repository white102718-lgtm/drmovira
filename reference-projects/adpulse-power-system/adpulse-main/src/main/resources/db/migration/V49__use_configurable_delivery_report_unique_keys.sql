-- 部署前人工执行：将Google日报更新依据从固定记录ID改为模板配置的联合唯一键。
ALTER TABLE biz_delivery_report_google_push_item
    ADD COLUMN unique_key_columns JSON NULL
        COMMENT '用于匹配更新目标行的联合唯一列字母数组'
        AFTER target_headers;

UPDATE biz_delivery_report_google_push_item
SET unique_key_columns = JSON_ARRAY(report_id_column)
WHERE unique_key_columns IS NULL
  AND report_id_column IS NOT NULL;

ALTER TABLE biz_delivery_report_google_push_item
    MODIFY unique_key_columns JSON NOT NULL
        COMMENT '用于匹配更新目标行的联合唯一列字母数组',
    MODIFY report_id_column VARCHAR(8) NULL
        COMMENT '历史记录ID目标列；联合唯一键模式不再写入';
