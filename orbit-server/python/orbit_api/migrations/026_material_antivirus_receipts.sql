-- 不继承旧READY为扫描通过；新证据必须绑定本轮claim和真实对象摘要。
CREATE TABLE orbit_material_scan_receipt (
 tenant_id CHAR(36) NOT NULL COMMENT '真实任务租户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '原素材UUID，历史元数据保留',
 claim_id CHAR(36) NOT NULL COMMENT '本轮任务认领UUID，迟到证据不能跨claim复用',
 id CHAR(36) NOT NULL COMMENT '扫描证据UUID',
 result VARCHAR(12) NOT NULL COMMENT 'CLEAN完整扫描/INFECTED感染/UNVERIFIED未知或失败',
 sha256 CHAR(64) NOT NULL COMMENT '绑定原对象SHA256；成功仅在实际流式复算一致后写入',
 byte_size BIGINT NOT NULL COMMENT '绑定实际原对象字节数',
 engine_version VARCHAR(32) NULL COMMENT '实际匹配的引擎版本，未连接时不代表已运行',
 database_version BIGINT NULL COMMENT '匹配的官方daily库版本，未知不通过',
 database_built_at DATETIME(3) NULL COMMENT '可信官方病毒库构建UTC时间，不能使用文件mtime',
 policy_sha256 CHAR(64) NULL COMMENT '主线校验的实际扫描配置证明摘要',
 started_at DATETIME(3) NOT NULL COMMENT '本轮扫描开始UTC时间',
 completed_at DATETIME(3) NOT NULL COMMENT '本轮扫描结束UTC时间',
 error_code VARCHAR(48) NULL COMMENT '安全结果码，不存原始病毒报告或路径',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '证据登记UTC时间',
 PRIMARY KEY(tenant_id,asset_id,id),
 UNIQUE KEY uq_material_scan_claim(tenant_id,asset_id,claim_id) COMMENT '同一任务认领只登记一次证据',
 KEY idx_material_scan_current(tenant_id,asset_id,result,sha256,byte_size,completed_at)
 COMMENT '引用和READY核对当前对象的完整扫描证据'
) COMMENT='不可变素材病毒扫描证据，不以媒体READY或模拟输出代替真实扫描';
