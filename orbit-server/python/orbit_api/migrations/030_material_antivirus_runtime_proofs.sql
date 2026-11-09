-- 仅追加运行实例证明；旧026收据不回填，也不改policy_sha256配置摘要含义。
-- 为四列外键增加明确候选键；不改旧026迁移，也不允许跨收据借用其他claim。
ALTER TABLE orbit_material_scan_receipt
 ADD UNIQUE KEY uq_material_receipt_claim_identity(tenant_id,asset_id,id,claim_id)
 COMMENT '实例证明精确绑定同一收据和认领，不能分别命中两条历史行';

CREATE TABLE orbit_material_scan_runtime_proof (
 tenant_id CHAR(36) NOT NULL COMMENT '真实扫描任务租户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '绑定素材UUID，不重分配历史拥有者',
 receipt_id CHAR(36) NOT NULL COMMENT '绑定026不可变扫描收据UUID',
 claim_id CHAR(36) NOT NULL COMMENT '绑定同轮任务认领UUID',
 profile_id VARCHAR(40) NOT NULL COMMENT '服务端可信profile标识，租户不能自填端口或路径',
 profile_revision BIGINT NOT NULL COMMENT '私有注册表profile版本，变化后旧消费者拒绝',
 instance_id CHAR(36) NOT NULL COMMENT '受控启动登记的随机实例UUID，不随端口重用',
 profile_sha256 CHAR(64) NOT NULL COMMENT '完整可信profile规范JSON摘要',
 source_sha256 CHAR(64) NOT NULL COMMENT '可信启动来源证明摘要，不含命令或环境原文',
 executable_sha256 CHAR(64) NOT NULL COMMENT '实际核验固定可执行文件SHA256',
 config_sha256 CHAR(64) NOT NULL COMMENT '实际核验启动配置SHA256，不能代替进程证明',
 process_created_at_us BIGINT NOT NULL COMMENT '实例创建UTC Unix微秒，阻止PID重用',
 issued_at DATETIME(3) NOT NULL COMMENT '可信来源证明签发UTC时间',
 expires_at DATETIME(3) NOT NULL COMMENT '可信来源证明到期UTC时间，不能无限期续信',
 verified_before DATETIME(3) NOT NULL COMMENT '真实扫描前实例与来源核验UTC时间',
 verified_after DATETIME(3) NOT NULL COMMENT '真实扫描后实例与来源复验UTC时间',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '不可变证据登记UTC时间',
 PRIMARY KEY(tenant_id,asset_id,receipt_id),
 UNIQUE KEY uq_material_runtime_claim(tenant_id,asset_id,claim_id)
 COMMENT '同一认领的实例证明只登记一次',
 KEY idx_material_runtime_instance(profile_id,profile_revision,instance_id,expires_at)
 COMMENT '按可信profile和实例定位证明，不按全表回扫',
 CONSTRAINT fk_material_runtime_receipt FOREIGN KEY(tenant_id,asset_id,receipt_id,claim_id)
 REFERENCES orbit_material_scan_receipt(tenant_id,asset_id,id,claim_id),
 CONSTRAINT ck_material_runtime_revision CHECK(profile_revision>0),
 CONSTRAINT ck_material_runtime_time CHECK(issued_at<=verified_before
 AND verified_before<=verified_after AND verified_after<expires_at)
) COMMENT='追加不可变扫描运行实例证明，不回填旧收据或泄露本机路径';
