-- 重建审批目录前，仅清理审批域数据；媒介资产库存、用户、部门、项目和渠道均保留。
ALTER TABLE media_approval_config
    ADD COLUMN description VARCHAR(255) NOT NULL DEFAULT '' AFTER flow_name,
    ADD COLUMN group_name VARCHAR(64) NOT NULL DEFAULT '其他审批' AFTER description,
    ADD COLUMN icon VARCHAR(64) NOT NULL DEFAULT 'lucide:workflow' AFTER group_name,
    ADD COLUMN visibility VARCHAR(16) NOT NULL DEFAULT 'all' AFTER icon,
    ADD COLUMN settings JSON NULL AFTER visibility,
    ADD COLUMN sort_order INT NOT NULL DEFAULT 0 AFTER settings;

DELETE FROM media_asset_approval_log;

DELETE FROM system_notification
WHERE business_type IN ('APPLICATION', 'APPROVAL', 'CC', 'PROCESSING');

DELETE FROM media_asset_application;

UPDATE media_approval_config
SET enabled = 0,
    deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED) + id
WHERE deleted_at = 0;

-- 优先使用首个启用的系统管理员；若未分配管理员角色，则回退到首个启用用户。
INSERT INTO media_approval_config
    (asset_type, category, flow_name, description, group_name, icon, visibility, settings,
     sort_order, approver_id, approver_name, cc_user_ids, form_schema, nodes, enabled,
     created_by, updated_by)
SELECT catalog.asset_type,
       catalog.category,
       catalog.flow_name,
       catalog.description,
       catalog.group_name,
       catalog.icon,
       'all',
       JSON_OBJECT('approvalType', 'manual'),
       catalog.sort_order,
       initial_user.id,
       initial_user.display_name,
       '',
       catalog.form_schema,
       JSON_ARRAY(JSON_OBJECT(
           'id', CONCAT(catalog.asset_type, '-approval'),
           'kind', 'approval',
           'name', '业务负责人审批',
           'assigneeMode', 'member',
           'approverType', 'USERS',
           'approverId', CAST(initial_user.id AS CHAR),
           'approverName', initial_user.display_name,
           'approverIds', JSON_ARRAY(CAST(initial_user.id AS CHAR)),
           'approverNames', JSON_ARRAY(initial_user.display_name),
           'handlerId', CAST(initial_user.id AS CHAR),
           'handlerName', initial_user.display_name
       )),
       1,
       initial_user.id,
       initial_user.id
FROM (
    SELECT 'PERSONAL' asset_type,
           'advertising' category,
           '个号申请' flow_name,
           '沿用 MPower 个号申请字段，并支持配置地区选项。' description,
           '媒介与资源' group_name,
           'lucide:user-round' icon,
           10 sort_order,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full','helpText','资源库存按渠道隔离，请先明确本次申请的渠道归属。'),
               JSON_OBJECT('key','channelId','label','所属渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择系统渠道','helpText','资源库存按渠道隔离，审批通过后仅能分配该渠道下的资产。'),
               JSON_OBJECT('key','sectionDetails','label','申请详情','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
               JSON_OBJECT('key','purpose','label','说明','type','textarea','required',false,'width','full','placeholder','请输入申请说明','maxLength',200)
           ) form_schema
    UNION ALL SELECT 'BM','advertising','BM 申请','沿用 MPower BM 申请字段，并支持配置地区选项。','媒介与资源','lucide:briefcase-business',20,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full','helpText','资源库存按渠道隔离，请先明确本次申请的渠道归属。'),
               JSON_OBJECT('key','channelId','label','所属渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择系统渠道','helpText','资源库存按渠道隔离，审批通过后仅能分配该渠道下的资产。'),
               JSON_OBJECT('key','sectionDetails','label','申请详情','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
               JSON_OBJECT('key','purpose','label','说明','type','textarea','required',false,'width','full','placeholder','请输入申请说明','maxLength',200)
           )
    UNION ALL SELECT 'PIXEL','advertising','像素申请','沿用 MPower 像素、BM 和授权账户字段。','媒介与资源','lucide:scan-line',30,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full','helpText','资源库存按渠道隔离，请先明确本次申请的渠道归属。'),
               JSON_OBJECT('key','channelId','label','所属渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择系统渠道','helpText','资源库存按渠道隔离，审批通过后仅能分配该渠道下的资产。'),
               JSON_OBJECT('key','sectionDetails','label','像素信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','pixelNames','label','像素','type','textarea','required',true,'width','full','placeholder','请输入“像素名称:像素ID”，多个像素以“;”分隔','validationRule','pixel-list'),
               JSON_OBJECT('key','bms','label','BM ID','type','text','required',true,'width','half','placeholder','请输入 BM ID，多个以“;”分隔','validationRule','digit-list'),
               JSON_OBJECT('key','accountIds','label','授权账户 ID','type','textarea','required',true,'width','full','placeholder','请输入授权账户 ID，多个以“;”分隔','validationRule','digit-list')
           )
    UNION ALL SELECT 'TG','advertising','社交资产申请','沿用 MPower 社交资产申请字段，并支持配置地区选项。','媒介与资源','lucide:send',40,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full','helpText','资源库存按渠道隔离，请先明确本次申请的渠道归属。'),
               JSON_OBJECT('key','channelId','label','所属渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择系统渠道','helpText','资源库存按渠道隔离，审批通过后仅能分配该渠道下的资产。'),
               JSON_OBJECT('key','sectionDetails','label','申请详情','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','region','label','地区','type','select','required',false,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
               JSON_OBJECT('key','purpose','label','说明','type','textarea','required',false,'width','full','placeholder','请输入申请说明','maxLength',200)
           )
    UNION ALL SELECT 'BUNDLE','advertising','绑包申请','沿用 MPower 账户 ID 与绑定应用链接字段。','媒介与资源','lucide:package-check',50,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionDetails','label','绑包信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','accountIds','label','账户 ID','type','textarea','required',true,'width','full','placeholder','请输入账户 ID，多个以“;”分隔','validationRule','digit-list'),
               JSON_OBJECT('key','bindAppLink','label','绑定应用链接','type','text','required',true,'width','full','placeholder','请输入绑定应用链接','validationRule','url')
           )
    UNION ALL SELECT 'PAGE','advertising','主页申请','沿用 MPower 地区、主页数量和授权 BM 字段。','媒介与资源','lucide:panels-top-left',60,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionDetails','label','主页信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','region','label','地区','type','select','required',true,'width','half','optionSource','custom','placeholder','请选择地区','options',JSON_ARRAY('新加坡','马来西亚','泰国','越南','印度尼西亚','菲律宾','印度','美国','日本','香港')),
               JSON_OBJECT('key','pageCount','label','主页数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','authBm','label','授权 BM','type','text','required',true,'width','half','placeholder','请输入授权 BM','validationRule','digit-list')
           )
    UNION ALL SELECT 'COMPUTER','office','电脑申请','按新原型补充系统部门、人员和项目选择。','行政与资产','lucide:laptop',70,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
               JSON_OBJECT('key','departmentId','label','所属部门','type','select','required',true,'width','half','optionSource','departments','placeholder','请选择系统部门'),
               JSON_OBJECT('key','assigneeId','label','使用人','type','select','required',true,'width','half','optionSource','users','placeholder','请选择系统人员'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','sectionDetails','label','电脑信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','purpose','label','用途说明','type','textarea','required',true,'width','full','placeholder','请说明电脑用途及配置要求','maxLength',200)
           )
    UNION ALL SELECT 'MOBILE','office','手机申请','按新原型补充系统部门、人员和项目选择。','行政与资产','lucide:smartphone',80,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
               JSON_OBJECT('key','departmentId','label','所属部门','type','select','required',true,'width','half','optionSource','departments','placeholder','请选择系统部门'),
               JSON_OBJECT('key','assigneeId','label','使用人','type','select','required',true,'width','half','optionSource','users','placeholder','请选择系统人员'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','sectionDetails','label','手机信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','purpose','label','用途说明','type','textarea','required',true,'width','full','placeholder','请说明手机用途及配置要求','maxLength',200)
           )
    UNION ALL SELECT 'STATIC_IP','office','静态 IP 申请','按新原型补充系统部门、人员和项目选择。','行政与资产','lucide:network',90,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
               JSON_OBJECT('key','departmentId','label','所属部门','type','select','required',true,'width','half','optionSource','departments','placeholder','请选择系统部门'),
               JSON_OBJECT('key','assigneeId','label','使用人','type','select','required',true,'width','half','optionSource','users','placeholder','请选择系统人员'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','sectionDetails','label','静态 IP 信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','purpose','label','用途说明','type','textarea','required',true,'width','full','placeholder','请说明静态 IP 用途及配置要求','maxLength',200)
           )
    UNION ALL SELECT 'EMAIL','office','邮箱申请','按新原型补充系统部门、人员和项目选择。','行政与资产','lucide:mail',100,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
               JSON_OBJECT('key','departmentId','label','所属部门','type','select','required',true,'width','half','optionSource','departments','placeholder','请选择系统部门'),
               JSON_OBJECT('key','assigneeId','label','使用人','type','select','required',true,'width','half','optionSource','users','placeholder','请选择系统人员'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','sectionDetails','label','邮箱信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','quantity','label','数量','type','number','required',true,'minValue',1,'width','half'),
               JSON_OBJECT('key','purpose','label','用途说明','type','textarea','required',true,'width','full','placeholder','请说明邮箱用途及配置要求','maxLength',200)
           )
    UNION ALL SELECT 'PAYMENT','finance','打款申请','沿用 MPower 渠道、备款金额和备注字段，并增加项目选择。','财务管理','lucide:badge-dollar-sign',110,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOwnership','label','申请归属','type','section','required',false,'width','full'),
               JSON_OBJECT('key','channelId','label','渠道','type','select','required',true,'width','half','optionSource','channels','placeholder','请选择渠道'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',false,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','sectionPayment','label','付款信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','amount','label','备款金额','type','number','required',true,'minValue',0.01,'width','half','validationRule','positive-money'),
               JSON_OBJECT('key','remark','label','备注','type','textarea','required',false,'width','full','placeholder','请输入备注','maxLength',50)
           )
    UNION ALL SELECT 'ACCOUNT_OPERATION','finance','广告账户操作申请','统一充值、扣款、清零、回收、解绑和换绑，按操作类型显示对应字段。','财务管理','lucide:wallet-cards',120,
           JSON_ARRAY(
               JSON_OBJECT('key','sectionOperation','label','操作信息','type','section','required',false,'width','full'),
               JSON_OBJECT('key','operationType','label','操作类型','type','select','required',true,'width','half','optionSource','custom','options',JSON_ARRAY('充值','扣款','活跃清零','活跃清零回收','回收','解绑','换绑')),
               JSON_OBJECT('key','accountIds','label','广告账户 ID','type','textarea','required',true,'width','full','placeholder','请输入广告账户 ID，多个以“;”分隔','validationRule','digit-list'),
               JSON_OBJECT('key','projectId','label','所属项目','type','select','required',true,'width','half','optionSource','projects','placeholder','请选择系统项目'),
               JSON_OBJECT('key','amount','label','金额','type','number','required',false,'minValue',0.01,'width','half','validationRule','positive-money',
                   'visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('充值','扣款')),
                   'requiredWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('充值','扣款'))),
               JSON_OBJECT('key','applyReason','label','申请原因','type','select','required',false,'width','half','optionSource','custom','options',JSON_ARRAY('账户停用','余额处理','业务调整','风控处理','其它'),
                   'visibleWhen',JSON_OBJECT('fieldKey','operationType','operator','in','value',JSON_ARRAY('活跃清零','活跃清零回收','回收'))),
               JSON_OBJECT('key','remark','label','备注','type','textarea','required',true,'width','full','placeholder','请输入操作说明','maxLength',100)
           )
) catalog
JOIN (
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
) initial_user;
