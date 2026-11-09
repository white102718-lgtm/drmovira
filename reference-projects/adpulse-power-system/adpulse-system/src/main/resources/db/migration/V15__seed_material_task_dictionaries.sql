INSERT INTO sys_dict_type (dict_code, dict_name, status, remark)
SELECT seed.dict_code, seed.dict_name, 1, seed.remark
FROM (
    SELECT 'MATERIAL_DEMAND_TYPE' dict_code, '素材需求类型' dict_name, '素材任务创建选项' remark
    UNION ALL SELECT 'MATERIAL_SIZE', '素材尺寸', '素材任务支持多选'
    UNION ALL SELECT 'TASK_PRIORITY', '任务优先级', '任务中心通用优先级'
    UNION ALL SELECT 'MATERIAL_LANGUAGE', '素材语言', '素材申请原型语言列表'
) seed
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_type type
    WHERE type.dict_code = seed.dict_code AND type.deleted_at = 0
);

INSERT INTO sys_dict_item (dict_type_id, item_value, item_label, sort_order, status)
SELECT type.id, seed.item_value, seed.item_label, seed.sort_order, 1
FROM sys_dict_type type
JOIN (
    SELECT 'MATERIAL_DEMAND_TYPE' dict_code, 'VIDEO' item_value, '视频' item_label, 10 sort_order
    UNION ALL SELECT 'MATERIAL_DEMAND_TYPE', 'IMAGE', '图片', 20
    UNION ALL SELECT 'MATERIAL_SIZE', '9x16', '9*16（竖屏）', 10
    UNION ALL SELECT 'MATERIAL_SIZE', '16x9', '16*9（横屏）', 20
    UNION ALL SELECT 'MATERIAL_SIZE', '1x1', '1x1', 30
    UNION ALL SELECT 'MATERIAL_SIZE', 'OTHER', '其他', 40
    UNION ALL SELECT 'TASK_PRIORITY', 'P0', 'P0 突发紧急', 10
    UNION ALL SELECT 'TASK_PRIORITY', 'P1', 'P1 常规/迭代', 20
    UNION ALL SELECT 'TASK_PRIORITY', 'P2', 'P2 素材储备', 30
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'en', '英语', 10
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'hi', '印地语', 20
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'pt', '葡萄牙语', 30
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'id', '印尼语', 40
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'bn', '孟加拉语', 50
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'es', '西班牙语', 60
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'vi', '越南语', 70
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'ms', '马来语', 80
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'th', '泰语', 90
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'ur', '乌尔都语', 100
    UNION ALL SELECT 'MATERIAL_LANGUAGE', 'fil', '菲律宾语', 110
) seed ON seed.dict_code = type.dict_code
WHERE type.deleted_at = 0
  AND NOT EXISTS (
      SELECT 1 FROM sys_dict_item item
      WHERE item.dict_type_id = type.id
        AND item.item_value = seed.item_value
        AND item.deleted_at = 0
  );
