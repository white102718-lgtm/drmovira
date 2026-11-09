-- 隐藏页面仍保留独立权限与可直达路由；仅调整父级以整理菜单管理树。
-- 不改 visible/status，避免这些二级页面进入侧边导航或改变既有授权结果。

UPDATE sys_menu AS child
INNER JOIN sys_menu AS parent
    ON parent.menu_code = 'WorkbenchTasks'
   AND parent.deleted_at = 0
SET child.parent_id = parent.id
WHERE child.deleted_at = 0
  AND child.menu_code IN (
    'RequirementPitcher',
    'WorkbenchMaterialTaskCreate',
    'WorkbenchDeliveryTaskCreate',
    'FusionAiTasks',
    'TaskDetail',
    'CreateRequirement',
    'RequirementPool',
    'RequirementProduction'
  );

UPDATE sys_menu AS child
INNER JOIN sys_menu AS parent
    ON parent.menu_code = 'FusionProjects'
   AND parent.deleted_at = 0
SET child.parent_id = parent.id
WHERE child.deleted_at = 0
  AND child.menu_code = 'FusionProductKnowledge';

UPDATE sys_menu AS child
INNER JOIN sys_menu AS parent
    ON parent.menu_code = 'CreativeCanvas'
   AND parent.deleted_at = 0
SET child.parent_id = parent.id
WHERE child.deleted_at = 0
  AND child.menu_code IN (
    'FusionAiStudio',
    'FusionAdgenLibrary',
    'CreativeCanvasEditor'
  );

UPDATE sys_menu AS child
INNER JOIN sys_menu AS parent
    ON parent.menu_code = 'AutomatedRules'
   AND parent.deleted_at = 0
SET child.parent_id = parent.id
WHERE child.deleted_at = 0
  AND child.menu_code = 'AutomatedRuleConfig';

UPDATE sys_menu AS child
INNER JOIN sys_menu AS parent
    ON parent.menu_code = 'DataReport'
   AND parent.deleted_at = 0
SET child.parent_id = parent.id
WHERE child.deleted_at = 0
  AND child.menu_code = 'Drilldown';
