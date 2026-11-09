ALTER TABLE media_approval_config
    ADD COLUMN flow_name VARCHAR(100) NULL AFTER asset_type,
    ADD COLUMN form_schema JSON NULL AFTER cc_user_ids,
    ADD COLUMN nodes JSON NULL AFTER form_schema,
    ADD COLUMN enabled TINYINT NOT NULL DEFAULT 1 AFTER nodes;

ALTER TABLE media_asset_application
    ADD COLUMN form_data JSON NULL AFTER reason,
    ADD COLUMN form_schema_snapshot JSON NULL AFTER form_data,
    ADD COLUMN nodes_snapshot JSON NULL AFTER form_schema_snapshot,
    ADD COLUMN current_node_index INT NOT NULL DEFAULT 0 AFTER nodes_snapshot;

ALTER TABLE media_asset_approval_log
    ADD COLUMN node_index INT NULL AFTER remark,
    ADD COLUMN node_name VARCHAR(100) NULL AFTER node_index;

CREATE TABLE system_notification (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    content VARCHAR(500) NOT NULL,
    target_path VARCHAR(500) NOT NULL,
    business_type VARCHAR(40) NOT NULL,
    business_id BIGINT UNSIGNED NOT NULL,
    is_read TINYINT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_system_notification_user (user_id, is_read, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内消息';

UPDATE media_approval_config
SET flow_name = CONCAT(asset_type, ' 资源申请'),
    form_schema = JSON_ARRAY(
      JSON_OBJECT('key','quantity','label','申请数量','type','number','required',true),
      JSON_OBJECT('key','purpose','label','使用用途','type','textarea','required',true)
    ),
    nodes = JSON_ARRAY(JSON_OBJECT(
      'name','资源负责人审批','approverId',CAST(approver_id AS CHAR),'approverName',approver_name,
      'handlerId',CAST(approver_id AS CHAR),'handlerName',approver_name,'handlerIsApprover',true
    ))
WHERE form_schema IS NULL OR nodes IS NULL;

INSERT INTO media_approval_config
  (asset_type, flow_name, approver_id, approver_name, cc_user_ids, form_schema, nodes, enabled, created_by, updated_by)
SELECT seed.asset_type, seed.flow_name, u.id, u.display_name, '', seed.form_schema,
       JSON_ARRAY(
         JSON_OBJECT('name','业务负责人审批','approverId',CAST(u.id AS CHAR),'approverName',u.display_name,
                     'handlerId',CAST(u.id AS CHAR),'handlerName',u.display_name,'handlerIsApprover',true),
         JSON_OBJECT('name','资源交付处理','approverId',CAST(u.id AS CHAR),'approverName',u.display_name,
                     'handlerId',CAST(u.id AS CHAR),'handlerName',u.display_name,'handlerIsApprover',true)
       ), 1, u.id, u.id
FROM (
  SELECT 'PERSONAL' asset_type, '个号申请' flow_name,
    JSON_ARRAY(JSON_OBJECT('key','quantity','label','申请数量','type','number','required',true),
               JSON_OBJECT('key','country','label','注册国家/地区','type','text','required',true),
               JSON_OBJECT('key','purpose','label','使用用途','type','textarea','required',true)) form_schema
  UNION ALL SELECT 'BM', 'BM 申请',
    JSON_ARRAY(JSON_OBJECT('key','quantity','label','申请数量','type','number','required',true),
               JSON_OBJECT('key','bmLevel','label','BM 类型','type','select','required',true,'options',JSON_ARRAY('普通 BM','已验证 BM')),
               JSON_OBJECT('key','purpose','label','业务用途','type','textarea','required',true))
  UNION ALL SELECT 'PIXEL', '像素申请',
    JSON_ARRAY(JSON_OBJECT('key','website','label','网站或应用','type','text','required',true),
               JSON_OBJECT('key','events','label','需要事件','type','select','required',true,'options',JSON_ARRAY('Purchase','Lead','CompleteRegistration')),
               JSON_OBJECT('key','purpose','label','使用说明','type','textarea','required',true))
  UNION ALL SELECT 'TG', 'TG 申请',
    JSON_ARRAY(JSON_OBJECT('key','quantity','label','申请数量','type','number','required',true),
               JSON_OBJECT('key','accountType','label','账号类型','type','select','required',true,'options',JSON_ARRAY('个人号','群组','频道','Bot')),
               JSON_OBJECT('key','purpose','label','使用用途','type','textarea','required',true))
) seed
JOIN sys_user u ON u.phone='15666666666' AND u.status=1 AND u.deleted_at=0
ON DUPLICATE KEY UPDATE flow_name=VALUES(flow_name), form_schema=VALUES(form_schema), nodes=VALUES(nodes),
                        enabled=1, updated_by=VALUES(updated_by);

ALTER TABLE media_approval_config
    MODIFY flow_name VARCHAR(100) NOT NULL,
    MODIFY form_schema JSON NOT NULL,
    MODIFY nodes JSON NOT NULL;

