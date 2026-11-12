-- 已核对现有 ORBIT 叶菜单，不创建或删除权限。仅更改显示名。
UPDATE sys_menu SET menu_name='创建广告'
WHERE menu_id=31020 AND component='orbit/launch/index' AND menu_name='投放管理';
