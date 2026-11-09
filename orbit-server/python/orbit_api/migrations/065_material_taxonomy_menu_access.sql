-- 素材库入口仅负责导航；读取素材和标签分类仍由独立动作授权。
-- 保留原页面、所有动作叶节点及若依菜单，不为旧角色增补权限。
UPDATE sys_menu SET perms=''
WHERE menu_id=31050 AND parent_id=31000 AND path='assets';
