-- 将有效用户的中国大陆手机号统一为带 +86 国家码的 E.164 格式。
-- 如果同一号码同时存在 11 位和 +86 两种有效记录，唯一索引会阻止更新；
-- 执行前先查看下方查询结果，并人工合并冲突用户。

SELECT CONCAT('+86', local_user.phone) AS normalized_phone,
       local_user.id AS local_user_id,
       international_user.id AS international_user_id
FROM sys_user AS local_user
INNER JOIN sys_user AS international_user
  ON international_user.phone = CONCAT('+86', local_user.phone)
 AND international_user.deleted_at = 0
WHERE local_user.phone REGEXP '^1[3-9][0-9]{9}$'
  AND local_user.deleted_at = 0;

START TRANSACTION;

UPDATE sys_user
SET phone = CONCAT('+86', phone)
WHERE phone REGEXP '^1[3-9][0-9]{9}$'
  AND deleted_at = 0;

COMMIT;

ALTER TABLE sys_user
    MODIFY COLUMN phone VARCHAR(32) NULL
        COMMENT '手机号，统一使用E.164格式；飞书用户在无权限时可为空';
