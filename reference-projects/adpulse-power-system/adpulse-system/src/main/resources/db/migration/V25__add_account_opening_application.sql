-- 补齐 MPower 广告户申请：申请人填写开户信息，审批通过后由办理人登记广告账户与 BM 链接。
INSERT INTO media_approval_config
    (asset_type, category, flow_name, description, group_id, group_name, icon, visibility,
     settings, sort_order, approver_id, approver_name, cc_user_ids, form_schema, nodes,
     enabled, created_by, updated_by)
SELECT 'ACCOUNT_OPENING',
       'advertising',
       '广告户申请',
       '沿用 MPower 账户名称、开户数量、授权方式、充值金额、时区与备注字段。',
       approval_group.id,
       approval_group.group_name,
       'lucide:badge-plus',
       'all',
       JSON_OBJECT(
           'approvalType', 'manual',
           'handlerAction', JSON_OBJECT(
               'formSchema', JSON_ARRAY(
                   JSON_OBJECT(
                       'key','openedAccountIds','label','已开户广告账户','type','textarea',
                       'required',true,'width','full','maxLength',1000,
                       'placeholder','请输入广告账户 ID，每行一个或用分号分隔',
                       'validationRule','digit-list'
                   ),
                   JSON_OBJECT(
                       'key','bmLink','label','BM 链接','type','textarea','required',false,
                       'width','full','maxLength',400,
                       'placeholder','请输入 BM 链接（最多 400 字）'
                   )
               )
           )
       ),
       5,
       initial_user.id,
       initial_user.display_name,
       '',
       JSON_ARRAY(
           JSON_OBJECT('key','sectionDetails','label','广告户信息','type','section','required',false,'width','full'),
           JSON_OBJECT(
               'key','accountName','label','账户名称','type','text','required',false,
               'width','half','maxLength',50,'placeholder','请输入账户名称'
           ),
           JSON_OBJECT(
               'key','quantity','label','开户数量','type','number','required',true,
               'width','half','minValue',1,'placeholder','请输入开户数量，最少 1 个'
           ),
           JSON_OBJECT(
               'key','authType','label','授权类型','type','select','required',true,
               'width','half','optionSource','custom','defaultValue','邮箱',
               'options',JSON_ARRAY('邮箱','BM','邮箱和 BM'),'placeholder','请选择授权类型'
           ),
           JSON_OBJECT(
               'key','authAccount','label','授权邮箱/BM','type','text','required',true,
               'width','half','placeholder','请输入授权邮箱/BM'
           ),
           JSON_OBJECT(
               'key','rechargeAmount','label','充值金额','type','number','required',false,
               'width','half','minValue',200,'validationRule','positive-money',
               'placeholder','请输入充值金额，最低 $200'
           ),
           JSON_OBJECT(
               'key','amountType','label','币种','type','select','required',true,
               'width','half','optionSource','custom','defaultValue','USD',
               'options',JSON_ARRAY('USD','EUR'),'placeholder','请选择币种'
           ),
           JSON_OBJECT(
               'key','timezone','label','时区','type','select','required',true,
               'width','half','optionSource','custom',
               'options',JSON_ARRAY('UTC-8','UTC-5','UTC+0','UTC+1','UTC+7','UTC+8','UTC+9'),
               'placeholder','请选择时区'
           ),
           JSON_OBJECT(
               'key','remark','label','备注','type','textarea','required',false,
               'width','full','maxLength',500,'placeholder','请输入备注'
           )
       ),
       JSON_ARRAY(
           JSON_OBJECT(
               'id','ACCOUNT_OPENING-approval','kind','approval','name','业务负责人审批',
               'assigneeMode','member','approverType','USERS',
               'approverId',CAST(initial_user.id AS CHAR),
               'approverName',initial_user.display_name,
               'approverIds',JSON_ARRAY(CAST(initial_user.id AS CHAR)),
               'approverNames',JSON_ARRAY(initial_user.display_name),
               'handlerId',CAST(initial_user.id AS CHAR),
               'handlerName',initial_user.display_name,
               'handlerAction',JSON_OBJECT(
                   'formSchema',JSON_ARRAY(
                       JSON_OBJECT(
                           'key','openedAccountIds','label','已开户广告账户','type','textarea',
                           'required',true,'width','full','maxLength',1000,
                           'placeholder','请输入广告账户 ID，每行一个或用分号分隔',
                           'validationRule','digit-list'
                       ),
                       JSON_OBJECT(
                           'key','bmLink','label','BM 链接','type','textarea',
                           'required',false,'width','full','maxLength',400,
                           'placeholder','请输入 BM 链接（最多 400 字）'
                       )
                   )
               )
           )
       ),
       1,
       initial_user.id,
       initial_user.id
FROM media_approval_group approval_group
CROSS JOIN (
    SELECT system_user.id,
           system_user.display_name
    FROM sys_user system_user
    LEFT JOIN sys_user_role user_role
      ON user_role.user_id = system_user.id
     AND user_role.deleted_at = 0
    LEFT JOIN sys_role role
      ON role.id = user_role.role_id
     AND role.deleted_at = 0
     AND role.status = 1
    WHERE system_user.status = 1
      AND system_user.deleted_at = 0
    GROUP BY system_user.id, system_user.display_name
    ORDER BY MAX(role.role_code = 'ADMIN') DESC, system_user.id
    LIMIT 1
) initial_user
WHERE approval_group.group_name = '媒介与资源'
  AND approval_group.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM media_approval_config existing
      WHERE existing.asset_type = 'ACCOUNT_OPENING'
        AND existing.deleted_at = 0
  )
ORDER BY approval_group.id
LIMIT 1;

-- 申请定义与审批配置使用稳定 ID 逻辑关联，不创建跨领域外键。
INSERT INTO media_application_definition
    (application_code, application_name, category, description, icon,
     approval_config_id, operation_type, visibility, sort_order, status,
     created_by, updated_by)
SELECT 'ACCOUNT_OPENING',
       '广告户申请',
       'advertising',
       '申请广告户并填写授权方式、开户数量、首充与时区。',
       'lucide:badge-plus',
       config.id,
       NULL,
       config.visibility,
       config.sort_order,
       config.enabled,
       config.created_by,
       config.updated_by
FROM media_approval_config config
WHERE config.asset_type = 'ACCOUNT_OPENING'
  AND config.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1
      FROM media_application_definition existing
      WHERE existing.application_code = 'ACCOUNT_OPENING'
        AND existing.deleted_at = 0
  );
