-- 人员目录补充；仅显式隔离迁移，旧记录未知登记时间保持NULL。
ALTER TABLE orbit_business_user
 ADD COLUMN display_name VARCHAR(50) NULL COMMENT '人员展示姓名；旧记录未知时只展示原昵称，不伪造实名验证',
 ADD COLUMN invited TINYINT NOT NULL DEFAULT 0 COMMENT '1待邀请验证、0原本地账号；不代表OIDC身份已验证',
 ADD COLUMN created_at DATETIME(3) NULL COMMENT '业务人员登记UTC时刻，迁移前未采集为NULL',
 ADD COLUMN updated_at DATETIME(3) NULL COMMENT '业务人员最后修改UTC时刻，迁移前未采集为NULL',
 ADD KEY idx_business_user_team (tenant_id,team_id,id) COMMENT '租户内按团队过滤并按UUID稳定续页';

-- 已有受控人员动作升级为实际目录页面，不改写若依原用户管理菜单。
UPDATE sys_menu SET menu_name='人员管理',path='users',component='orbit/system/users/index',
 menu_type='C',visible='0',status='0',icon='user',is_cache=1,order_num=2
WHERE menu_id=31082 AND parent_id=31080;
