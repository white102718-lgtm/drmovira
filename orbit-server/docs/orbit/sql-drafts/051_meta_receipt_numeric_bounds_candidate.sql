-- 候选051：仅修复045原始观察回执JSON数值比较；由主线审核后采用，不在此执行。
-- MySQL JSON不支持直接BETWEEN；CASE先严格区分INTEGER，再用原生DECIMAL比较。
-- 保留原6键、类型与范围语义；IS TRUE显式拒绝整体UNKNOWN，不回填或更改旧证据。
ALTER TABLE orbit_meta_raw_idempotency
 DROP CHECK ck_meta_raw_ledger_receipt,
 ADD CONSTRAINT ck_meta_raw_ledger_receipt CHECK((
 JSON_CONTAINS_PATH(receipt_json,'all','$.registry_id','$.binding_sha256','$.observed_at','$.account_count','$.resource_count','$.execution_authorized')=1
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.registry_id'))='STRING'
 AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.registry_id'))=registry_id
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.binding_sha256'))='STRING'
 AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.binding_sha256')) REGEXP '^[a-f0-9]{64}$'
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.observed_at'))='STRING'
 AND CASE WHEN JSON_TYPE(JSON_EXTRACT(receipt_json,'$.account_count'))='INTEGER'
   THEN CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.account_count')) AS DECIMAL(65,0)) BETWEEN 1 AND 500
   ELSE FALSE END
 AND CASE WHEN JSON_TYPE(JSON_EXTRACT(receipt_json,'$.resource_count'))='INTEGER'
   THEN CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.resource_count')) AS DECIMAL(65,0)) BETWEEN 0 AND 2500000
   ELSE FALSE END
 AND JSON_TYPE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='BOOLEAN'
 AND JSON_UNQUOTE(JSON_EXTRACT(receipt_json,'$.execution_authorized'))='false'
 ) IS TRUE);
