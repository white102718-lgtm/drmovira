-- 033已经受测，新增类型化DAG头；历史NULL不猜测回填，不改变已有只读投影。
ALTER TABLE orbit_task
 ADD COLUMN dag_schema_version INT UNSIGNED NULL
 COMMENT '真实DagManifest编码版本，新begin必须1；历史未记录保留NULL',
 ADD COLUMN plan_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL
 COMMENT 'B集合规范计划摘要，不等于payload_hash或预检hash；历史缺失不猜',
 ADD COLUMN allocation_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL
 COMMENT 'B实际分配输入摘要，参与graph_hash；不冒充平台授权',
 ADD CONSTRAINT ck_task_dag_header CHECK (
  (dag_schema_version IS NULL AND plan_input_hash IS NULL AND allocation_input_hash IS NULL)
  OR (dag_schema_version IS NOT NULL AND dag_schema_version=1
   AND plan_input_hash IS NOT NULL AND allocation_input_hash IS NOT NULL
   AND REGEXP_LIKE(plan_input_hash,'^[a-f0-9]{64}$','c')
   AND REGEXP_LIKE(allocation_input_hash,'^[a-f0-9]{64}$','c'))
 );
