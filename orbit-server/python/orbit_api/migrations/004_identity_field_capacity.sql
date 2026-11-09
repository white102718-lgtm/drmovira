-- 人员/角色业务桥接前显式扩大原若依字段；只升级独立Python库，不迁移Java预览。
-- 字符串容量按Unicode字符计，不按UTF-16截断；手机号是联系方式，不等于认证证明。
ALTER TABLE sys_user
 MODIFY COLUMN nick_name VARCHAR(50) NOT NULL COMMENT '用户昵称；兼容ORBIT最多50个Unicode字符',
 MODIFY COLUMN email VARCHAR(254) NULL DEFAULT '' COMMENT '规范邮箱联系方式；最多254字符，不自动重绑认证身份',
 MODIFY COLUMN phonenumber VARCHAR(32) NULL DEFAULT '' COMMENT '手机号联系方式；兼容国际区号与分隔写法，最多32字符';
ALTER TABLE sys_role
 MODIFY COLUMN role_name VARCHAR(50) NOT NULL COMMENT '功能角色名称；兼容ORBIT最多50个Unicode字符';
