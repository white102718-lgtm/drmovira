-- 由用户审核后在部署前手工执行。项目通过钱包真实 customer_ref_id 建立一对一逻辑关联。
ALTER TABLE pm_project
    ADD COLUMN wallet_customer_ref_id VARCHAR(128) NULL
        COMMENT '关联Safeheron钱包业务引用；直连钱包为project_code，旧MPower钱包为旧task_id'
        AFTER project_code,
    ADD UNIQUE KEY uk_pm_project_wallet_ref_deleted (wallet_customer_ref_id, deleted_at);

-- 回填已经由新系统按项目编码创建的钱包；旧系统钱包在首次同步成功时再写入关联。
UPDATE pm_project project
INNER JOIN safeheron_wallet wallet
    ON wallet.customer_ref_id = project.project_code
    AND wallet.status = 1
    AND wallet.deleted_at = 0
SET project.wallet_customer_ref_id = wallet.customer_ref_id
WHERE project.deleted_at = 0
  AND project.wallet_customer_ref_id IS NULL;
