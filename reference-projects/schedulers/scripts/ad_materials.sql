CREATE TABLE ad_materials (
  unique_name VARCHAR(200) NOT NULL COMMENT "唯一名称",
  tags ARRAY<VARCHAR(65533)> COMMENT "标签数组(JSON存储)"
) ENGINE=OLAP
UNIQUE KEY(`unique_name`)
DISTRIBUTED BY HASH(`unique_name`) BUCKETS AUTO
PROPERTIES ( "replication_num" = "1" );
