-- 部署前人工执行：记录每条斗篷向项目代理线Google Sheet的回写结果。
ALTER TABLE biz_cloak
    ADD COLUMN sheet_writeback_status TINYINT NOT NULL DEFAULT 0
        COMMENT '表格回写状态：0未回写，1成功，2失败' AFTER status,
    ADD COLUMN sheet_writeback_message VARCHAR(1000) NULL
        COMMENT '表格回写结果或安全失败摘要' AFTER sheet_writeback_status,
    ADD COLUMN sheet_row_number INT UNSIGNED NULL
        COMMENT '成功匹配并写入的Google Sheet行号' AFTER sheet_writeback_message,
    ADD COLUMN sheet_writeback_at DATETIME(3) NULL
        COMMENT '最近一次表格回写完成时间' AFTER sheet_row_number,
    ADD KEY idx_cloak_sheet_writeback (
        batch_id, sheet_writeback_status, deleted_at
    ) COMMENT '按批次查询表格回写结果',
    ADD CONSTRAINT ck_cloak_sheet_writeback_status
        CHECK (sheet_writeback_status IN (0, 1, 2));
