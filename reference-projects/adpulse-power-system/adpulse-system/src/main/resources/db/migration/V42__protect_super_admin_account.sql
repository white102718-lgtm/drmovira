-- 人工审核执行；先执行本脚本，再部署后端。DDL 不参与下方事务。
ALTER TABLE sys_user
    ADD COLUMN is_super_admin TINYINT NOT NULL DEFAULT 0 COMMENT '超级管理员，仅人工授予';

START TRANSACTION;
-- 只提升指定且未删除的本地账号，不根据昵称或手机号动态授予特权。
UPDATE sys_user
SET is_super_admin = 1,
    status = 1
WHERE username = 'admin-15666666666'
  AND source_type = 'LOCAL'
  AND deleted_at = 0;

-- 提交前核对结果必须恰好一行且 is_super_admin/status 都为 1；否则回滚并核对账号。
SELECT id, username, source_type, is_super_admin, status
FROM sys_user
WHERE username = 'admin-15666666666' AND deleted_at = 0;
COMMIT;
