-- AdPulse 管理员路由菜单重建脚本（MySQL 8+）
-- 菜单来源：D:\progress\aiAdpluse-yuanxing\plat\src\router\menu-schema.ts
-- 适用后端：D:\progress\adpulse-power-system
--
-- 说明：
-- 1. 按后端数据规范软删除全部旧菜单及角色菜单关系，不物理删除历史数据。
-- 2. 重建原型管理员全部可见菜单，仅保留能从现有页面入口打开的隐藏路由。
-- 3. 本脚本仅处理目录和页面路由，不创建 menu_type=3 的按钮权限。
-- 4. 仅给有效的 ADMIN 角色授予全部新路由；其他角色需在角色管理中重新授权。

START TRANSACTION;

SET @deleted_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED);

UPDATE sys_role_menu
SET deleted_at = @deleted_at
WHERE deleted_at = 0;

UPDATE sys_menu
SET status = 0,
    deleted_at = @deleted_at,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE deleted_at = 0;

-- 根路由、一级目录及根级隐藏路由。
INSERT INTO sys_menu (
    parent_id,
    menu_type,
    menu_code,
    menu_name,
    route_path,
    component,
    icon,
    permission_code,
    visible,
    cacheable,
    sort_order,
    status,
    remark
) VALUES
    (0, 2, 'Home', '首页', '/home', '/home/index', 'ion:home-outline', NULL, 1, 1, -999, 1, '原型运行时首页'),

    (0, 1, 'BusinessCenter', '业务中心', '/business-center', 'BasicLayout', 'lucide:briefcase-business', NULL, 1, 0, -900, 1, 'redirect=/fusion/projects'),
    (0, 1, 'WorkbenchCenter', '工作台', '/workbench', 'BasicLayout', 'lucide:panels-top-left', NULL, 1, 0, -850, 1, 'redirect=/workbench/tasks'),

    (0, 1, 'MaterialCenter', '素材中心', '/material-center', 'BasicLayout', 'lucide:folders', NULL, 1, 0, -800, 1, 'redirect=/creative/canvas'),
    (0, 2, 'RequirementPool', '素材任务池', '/requirement/pool', '/requirement/pool', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/material-center'),
    (0, 2, 'RequirementProduction', '我的素材任务', '/requirement/myTask', '/requirement/myTask', NULL, NULL, 0, 1, 0, 1, '隐藏路由；activePath=/material-center'),

    (0, 1, 'DeliveryCenter', '投放中心', '/delivery-center', 'BasicLayout', 'lucide:rocket', NULL, 1, 0, -700, 1, 'redirect=/fusion/ads/create'),
    (0, 1, 'DataGrowthCenter', '数据复盘', '/data-growth', 'BasicLayout', 'lucide:chart-no-axes-combined', NULL, 1, 0, -650, 1, 'redirect=/data-report'),
    (0, 1, 'FinanceCenter', '财务中心', '/finance', 'BasicLayout', 'lucide:landmark', NULL, 1, 0, -600, 1, 'redirect=/finance/project-profit'),
    (0, 1, 'MediaResourceCenter', '媒介资源中心', '/media-resources', 'BasicLayout', 'lucide:warehouse', NULL, 1, 0, -500, 1, 'redirect=/media-resources/accounts'),
    (0, 1, 'PlatformConfigurationCenter', '平台技术配置', '/platform-configuration', 'BasicLayout', 'lucide:settings-2', NULL, 1, 0, -400, 1, 'redirect=/management/developers'),
    (0, 1, 'SystemManagement', '系统管理', '/system-management', 'BasicLayout', 'lucide:shield-check', NULL, 1, 0, -300, 1, 'redirect=/system-management/users'),

    (0, 2, 'RequirementPitcher', '投手需求工作台', '/requirement/pitcher', '/requirement/pitcher', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/workbench/tasks'),
    (0, 2, 'WorkbenchMaterialTaskCreate', '新建素材任务', '/workbench/tasks/create-material', '/requirement/create', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/workbench/tasks'),
    (0, 2, 'WorkbenchDeliveryTaskCreate', '新建投放任务', '/workbench/tasks/create-delivery', '/workbench/delivery-task-create', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/workbench/tasks'),
    (0, 2, 'FusionProductKnowledge', '产品与创意知识库', '/fusion/product-knowledge', '/fusion/product-knowledge/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/fusion/projects'),
    (0, 2, 'FusionAiStudio', 'AI创意工作台', '/fusion/ai-studio', '/fusion/capability-workbench/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/creative/canvas'),
    (0, 2, 'FusionAdgenLibrary', '历史、模板与存储', '/fusion/adgen-library', '/fusion/adgen-library/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/creative/canvas'),
    (0, 2, 'FusionAiTasks', '全局任务中心', '/fusion/ai-tasks', '/fusion/ai-tasks/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/workbench/tasks'),

    -- 原型 access.ts 自动补充的隐藏路由，改由后端完整下发。
    (0, 2, 'Profile', '个人信息', '/profile', '/profile/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由'),
    (0, 2, 'AutomatedRuleConfig', '规则配置', '/createAdvertisement/automated-rule-config', '/createAdvertisement/AutomatedRuleConfig', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/AutomatedRules'),
    (0, 2, 'Drilldown', '下钻分析', '/data-report/drilldown', '/dataReport/Drilldown', NULL, NULL, 0, 0, 0, 1, '隐藏路由'),
    (0, 2, 'TaskDetail', '任务详情', '/requirement/detail', '/requirement/detail', NULL, NULL, 0, 0, 0, 1, '隐藏路由'),
    (0, 2, 'CreateRequirement', '新建需求', '/requirement/create', '/requirement/create', NULL, NULL, 0, 0, 0, 1, '隐藏路由'),
    (0, 2, 'CreativeCanvasEditor', 'AI创意画布编辑器', '/creative/canvas/:id', '/creative/canvas/editor', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/creative/canvas');

SET @business_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'BusinessCenter' AND deleted_at = 0
);
SET @workbench_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'WorkbenchCenter' AND deleted_at = 0
);
SET @material_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'MaterialCenter' AND deleted_at = 0
);
SET @delivery_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'DeliveryCenter' AND deleted_at = 0
);
SET @data_growth_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'DataGrowthCenter' AND deleted_at = 0
);
SET @finance_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'FinanceCenter' AND deleted_at = 0
);
SET @media_resource_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'MediaResourceCenter' AND deleted_at = 0
);
SET @platform_configuration_center_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'PlatformConfigurationCenter' AND deleted_at = 0
);
SET @system_management_id = (
    SELECT id FROM sys_menu WHERE menu_code = 'SystemManagement' AND deleted_at = 0
);

-- 一级目录下的页面路由；隐藏页面仍保留路由，只是不显示在侧边栏。
INSERT INTO sys_menu (
    parent_id,
    menu_type,
    menu_code,
    menu_name,
    route_path,
    component,
    icon,
    permission_code,
    visible,
    cacheable,
    sort_order,
    status,
    remark
) VALUES
    (@business_center_id, 2, 'FusionProjects', '项目管理', '/fusion/projects', '/fusion/projects/index', 'lucide:briefcase-business', NULL, 1, 0, 20, 1, NULL),

    (@workbench_center_id, 2, 'WorkbenchTasks', '任务中心', '/workbench/tasks', '/workbench/tasks', 'lucide:list-todo', NULL, 1, 0, 10, 1, NULL),
    (@workbench_center_id, 2, 'WorkbenchApplications', '资源申请', '/workbench/applications', '/workbench/applications', 'lucide:file-plus-2', NULL, 1, 0, 20, 1, NULL),
    (@workbench_center_id, 2, 'WorkbenchApprovals', '审批中心', '/workbench/approvals', '/workbench/approvals', 'lucide:clipboard-check', NULL, 1, 0, 30, 1, NULL),
    (@workbench_center_id, 2, 'MyMediaAssets', '我的资产', '/media-assets/my-assets', '/media-resources/accounts', 'lucide:boxes', NULL, 1, 0, 40, 1, NULL),

    (@material_center_id, 2, 'CreativeCanvas', 'AI创意画布', '/creative/canvas', '/creative/canvas/index', 'lucide:panels-top-left', NULL, 1, 0, 10, 1, NULL),
    (@material_center_id, 2, 'OriginalMaterialLibrary', '素材库', '/materials/material-library', '/materials/material-library', 'lucide:folder-search', NULL, 1, 0, 30, 1, NULL),

    (@delivery_center_id, 2, 'FusionCreateAd', '多平台广告发布', '/fusion/ads/create', '/fusion/ads/create/index', 'lucide:send', NULL, 1, 0, 10, 1, NULL),
    (@delivery_center_id, 2, 'AdPulseCreateAd', 'AdPulse高级创建', '/createAdvertisement', '/createAdvertisement/index', 'lucide:badge-plus', NULL, 1, 0, 20, 1, NULL),
    (@delivery_center_id, 2, 'PersonnelData', '人员数据', '/dashboard/personnel-data', '/dashboard/personnel-data', 'lucide:users-round', NULL, 1, 0, 56, 1, NULL),
    (@delivery_center_id, 2, 'AutomatedRules', '自动化规则', '/AutomatedRules', '/createAdvertisement/AutomatedRuleLibrary', 'lucide:workflow', NULL, 1, 0, 60, 1, NULL),
    (@delivery_center_id, 2, 'AdAlertRules', '投放预警', '/delivery/alert-rules', '/createAdvertisement/AlertRule', 'lucide:bell-ring', NULL, 1, 0, 70, 1, NULL),
    (@delivery_center_id, 2, 'AdConfiguration', '广告配置', '/delivery/ad-config', '/management/ad-config/index', 'lucide:settings-2', NULL, 1, 0, 80, 1, NULL),

    (@data_growth_center_id, 2, 'DataReport', '经营与投放报表', '/data-report', '/dataReport/Index', 'lucide:chart-spline', NULL, 1, 0, 10, 1, NULL),
    (@data_growth_center_id, 2, 'ProjectComparison', '项目环比分析', '/analytics/project-comparison', '/analytics/project-comparison/index', 'lucide:chart-no-axes-column-increasing', NULL, 1, 0, 15, 1, NULL),
    (@data_growth_center_id, 2, 'AdManager', '广告面板', '/dashboard/ad-manager', '/dashboard/ad-manager', 'lucide:megaphone', NULL, 1, 0, 20, 1, NULL),
    (@data_growth_center_id, 2, 'MaterialInsights', '素材效果与看板', '/materials/material-insights', '/materials/material-insights', 'lucide:chart-column-big', NULL, 1, 0, 30, 1, NULL),
    (@data_growth_center_id, 2, 'ReviewExperiments', '复盘与实验', '/fusion/review-experiments', '/fusion/review-experiments/index', NULL, NULL, 0, 0, 0, 1, '隐藏路由；activePath=/data-report'),

    (@finance_center_id, 2, 'FinanceServiceFees', '服务费管理', '/finance/service-fees', '/finance/overview', 'lucide:receipt-text', NULL, 1, 0, 10, 1, NULL),
    (@finance_center_id, 2, 'FinanceCosts', '成本管理', '/finance/costs', '/finance/overview', 'lucide:wallet-cards', NULL, 1, 0, 20, 1, NULL),
    (@finance_center_id, 2, 'FinanceProjectProfit', '项目利润', '/finance/project-profit', '/finance/overview', 'lucide:badge-dollar-sign', NULL, 1, 0, 30, 1, NULL),
    (@finance_center_id, 2, 'FinanceReconciliation', '对账', '/finance/reconciliation', '/finance/overview', 'lucide:scale', NULL, 1, 0, 40, 1, NULL),

    (@media_resource_center_id, 2, 'MediaResourceAccounts', '资产管理', '/media-resources/accounts', '/media-resources/accounts', 'lucide:boxes', NULL, 1, 0, 10, 1, NULL),
    (@media_resource_center_id, 2, 'MediaResourceChannels', '渠道管理', '/media-resources/channels', '/media-resources/channels', 'lucide:radio-tower', NULL, 1, 0, 22, 1, NULL),
    (@media_resource_center_id, 2, 'MediaResourceAccountManagement', '账号管理', '/media-resources/account-management', '/media-resources/account-management', 'lucide:badge-dollar-sign', NULL, 1, 0, 25, 1, NULL),
    (@media_resource_center_id, 2, 'MediaResourceReturns', '资源回收', '/media-resources/returns', '/media-resources/returns', 'lucide:package-open', NULL, 1, 0, 40, 1, NULL),
    (@media_resource_center_id, 2, 'MediaResourceAudit', '操作记录', '/media-resources/audit', '/media-resources/audit', 'lucide:scroll-text', NULL, 1, 0, 50, 1, NULL),
    (@media_resource_center_id, 2, 'MediaResourceApprovalConfig', '审批配置', '/media-resources/approval-config', '/media-resources/approval-config', 'lucide:workflow', NULL, 1, 0, 60, 1, NULL),

    (@platform_configuration_center_id, 2, 'PlatformDevelopers', '开发者与授权', '/management/developers', '/management/developers/index', 'lucide:code-xml', NULL, 1, 0, 10, 1, NULL),
    (@platform_configuration_center_id, 2, 'PlatformResources', '平台资源同步', '/management/platform-resources', '/management/fb-resource/index', 'lucide:refresh-cw', NULL, 1, 0, 20, 1, NULL),
    (@platform_configuration_center_id, 2, 'PlatformConfiguration', '平台与代理线', '/management/platform-config', '/management/platform-config/index', 'lucide:settings', NULL, 1, 0, 30, 1, NULL),
    (@platform_configuration_center_id, 2, 'ManagementTasks', '同步任务', '/management/tasks', '/management/tasks/index', 'lucide:list-restart', NULL, 1, 0, 40, 1, NULL),

    (@system_management_id, 2, 'SystemUsers', '用户管理', '/system-management/users', '/system/user/list', 'lucide:users', 'system:user:list', 1, 0, 10, 1, NULL),
    (@system_management_id, 2, 'SystemDepartments', '部门管理', '/system-management/departments', '/system/department/list', 'lucide:building-2', 'system:department:list', 1, 0, 20, 1, NULL),
    (@system_management_id, 2, 'SystemRoles', '角色权限', '/system-management/roles', '/system/role/list', 'lucide:user-cog', 'system:role:list', 1, 0, 30, 1, NULL),
    (@system_management_id, 2, 'SystemMenus', '菜单管理', '/system-management/menus', '/system/menu/list', 'lucide:panel-left', 'system:menu:list', 1, 0, 40, 1, NULL),
    (@system_management_id, 2, 'AdgenOperations', 'AdGen模型与运维', '/fusion/adgen-operations', '/fusion/operations-center/index', 'lucide:server-cog', NULL, 1, 0, 50, 1, NULL);

-- 管理员拥有全部新路由。
INSERT INTO sys_role_menu (role_id, menu_id)
SELECT r.id, m.id
FROM sys_role r
CROSS JOIN sys_menu m
WHERE r.role_code = 'ADMIN'
  AND r.status = 1
  AND r.deleted_at = 0
  AND m.status = 1
  AND m.deleted_at = 0;

COMMIT;

-- 执行后校验：预期 64 个路由节点、0 个按钮权限、64 条 ADMIN 授权。
SELECT
    SUM(menu_type IN (1, 2)) AS route_menu_count,
    SUM(menu_type = 3) AS button_permission_count,
    SUM(menu_type IN (1, 2) AND visible = 1) AS visible_route_count,
    SUM(menu_type IN (1, 2) AND visible = 0) AS hidden_route_count
FROM sys_menu
WHERE status = 1
  AND deleted_at = 0;

SELECT COUNT(*) AS admin_relation_count
FROM sys_role_menu rm
INNER JOIN sys_role r
    ON r.id = rm.role_id
   AND r.role_code = 'ADMIN'
   AND r.status = 1
   AND r.deleted_at = 0
INNER JOIN sys_menu m
    ON m.id = rm.menu_id
   AND m.status = 1
   AND m.deleted_at = 0
WHERE rm.deleted_at = 0;
