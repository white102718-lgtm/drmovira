-- 原ReferenceInput/name严格合同保持不变；真实户商代称独立维护，不从名称推算。
CREATE TABLE orbit_vendor_alias (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID，禁止客户端指定',
 vendor_id CHAR(36) NOT NULL COMMENT '原引用目录VENDOR稳定UUID，写入另验类别与范围',
 alias VARCHAR(30) NULL COMMENT '人工维护真实代称，NFC后一至三十码点，未知或清除为NULL',
 revision BIGINT NOT NULL COMMENT '独立代称CAS版本，首次实际维护为2，缺行逻辑基线为1',
 updated_at DATETIME(3) NOT NULL COMMENT '最后实际维护UTC时间，逻辑空基线无更新时间',
 updated_by BIGINT NOT NULL COMMENT '实际维护者原若依用户ID，不向批量读取响应暴露',
 PRIMARY KEY (tenant_id,vendor_id),
 CONSTRAINT fk_vendor_alias_reference FOREIGN KEY (tenant_id,vendor_id)
 REFERENCES orbit_reference_record(tenant_id,id),
 CONSTRAINT ck_vendor_alias_revision CHECK (revision BETWEEN 2 AND 9007199254740991),
 CONSTRAINT ck_vendor_alias_length CHECK (alias IS NULL OR CHAR_LENGTH(alias) BETWEEN 1 AND 30)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs
COMMENT='独立真实户商代称，复合主键支持租户内二百项集合查询；无合同要求的代称唯一约束';
