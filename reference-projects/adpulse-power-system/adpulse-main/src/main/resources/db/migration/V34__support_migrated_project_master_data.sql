-- 投放二组迁移前置结构调整；目标：新系统 adpulse_system，MySQL 8。
-- 由用户单独执行。本脚本不导入项目/代理线，不修改老生产库。
-- 作用：优化师允许 NULL、产品信息上限扩到2000字符、补充 KWAI 字典。
-- 注意：DDL 会隐式提交，不能通过 ROLLBACK 撤销。请先保存 SHOW CREATE TABLE 输出。
-- 仅数据库调整：后端/前端优化师校验、详情空值保护、产品长度及平台枚举须配套更新。
-- 不要在遇错后继续执行；若中断后过程残留，检查错误再删除该专用过程后重跑。

USE adpulse_system;
SET NAMES utf8mb4;

SELECT DATABASE() AS target_database, @@hostname AS target_hostname;
SHOW CREATE TABLE pm_project;
SHOW CREATE TABLE pm_agency_line;

DELIMITER $$
CREATE PROCEDURE mig_team160_prepare_20260907()
BEGIN
    DECLARE v_lock INT DEFAULT 0;
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_dict_id BIGINT UNSIGNED;
    DECLARE v_capacity BIGINT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        IF v_lock = 1 THEN
            DO RELEASE_LOCK('mig_team160_prepare_20260907');
        END IF;
        RESIGNAL;
    END;

    IF DATABASE() <> 'adpulse_system' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Wrong target database';
    END IF;
    SELECT GET_LOCK('mig_team160_prepare_20260907', 10) INTO v_lock;
    IF COALESCE(v_lock, 0) <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot acquire preparation lock';
    END IF;

    -- 先核查所有条件，再执行不可事务回滚的结构变更。
    SELECT COUNT(*) INTO v_count FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'pm_agency_line'
      AND column_name IN ('optimizer_id', 'optimizer_name');
    IF v_count <> 2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Agency line schema is unexpected';
    END IF;
    SELECT COUNT(*), MAX(character_maximum_length) INTO v_count, v_capacity
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'pm_project'
      AND column_name = 'product_info' AND data_type IN ('varchar', 'text', 'mediumtext', 'longtext');
    IF v_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Product info schema is unexpected';
    END IF;
    SELECT COUNT(*), MAX(id) INTO v_count, v_dict_id
    FROM sys_dict_type WHERE dict_code = 'AD_MEDIA' AND deleted_at = 0 AND status = 1;
    IF v_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'AD_MEDIA must be uniquely enabled';
    END IF;
    SELECT COUNT(*) INTO v_count FROM sys_dict_item
    WHERE dict_type_id = v_dict_id AND UPPER(TRIM(item_value)) = 'KWAI'
      AND deleted_at = 0;
    IF v_count > 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Duplicate KWAI dictionary values';
    END IF;
    IF EXISTS (
        SELECT 1 FROM sys_dict_item WHERE dict_type_id = v_dict_id
          AND UPPER(TRIM(item_value)) = 'KWAI' AND deleted_at = 0 AND status <> 1
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Existing KWAI is disabled; review first';
    END IF;

    SELECT COUNT(*) INTO v_count FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'pm_agency_line'
      AND column_name IN ('optimizer_id', 'optimizer_name') AND is_nullable = 'NO';
    IF v_count > 0 THEN
        ALTER TABLE pm_agency_line
            MODIFY COLUMN optimizer_id BIGINT UNSIGNED NULL COMMENT '优化师用户ID，未分配时为空',
            MODIFY COLUMN optimizer_name VARCHAR(100) NULL COMMENT '优化师姓名快照，未分配时为空';
    END IF;

    -- 已扩至更大长度的环境不降级、不截断。7003-N5555 原文986字符可完整保留。
    IF v_capacity < 2000 THEN
        ALTER TABLE pm_project
            MODIFY COLUMN product_info VARCHAR(2000) NOT NULL COMMENT '产品信息';
    END IF;

    START TRANSACTION;
    INSERT INTO sys_dict_item (dict_type_id, item_value, item_label, sort_order, status, remark)
    SELECT v_dict_id, 'KWAI', 'Kwai', 50, 1, '投放二组历史项目迁移：保留原有媒体'
    WHERE NOT EXISTS (
        SELECT 1 FROM sys_dict_item WHERE dict_type_id = v_dict_id
          AND UPPER(TRIM(item_value)) = 'KWAI' AND deleted_at = 0
    );
    COMMIT;
    DO RELEASE_LOCK('mig_team160_prepare_20260907');
    SET v_lock = 0;
END$$
DELIMITER ;

CALL mig_team160_prepare_20260907();
DROP PROCEDURE mig_team160_prepare_20260907;

-- 执行后验收：两个优化师字段应为 YES，产品信息长度应至少为2000，KWAI应只有一行且status=1。
SELECT table_name, column_name, column_type, is_nullable, character_maximum_length
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND ((table_name = 'pm_agency_line' AND column_name IN ('optimizer_id', 'optimizer_name'))
       OR (table_name = 'pm_project' AND column_name = 'product_info'));
SELECT item.item_value, item.item_label, item.status
FROM sys_dict_item item JOIN sys_dict_type type ON type.id = item.dict_type_id
WHERE type.dict_code = 'AD_MEDIA' AND type.deleted_at = 0 AND item.deleted_at = 0
  AND UPPER(TRIM(item.item_value)) = 'KWAI';
