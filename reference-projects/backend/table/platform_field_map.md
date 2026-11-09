# platform_field_map 集合

**数据库**：plat
**用途**：存储广告平台的字段映射配置，支持按代理线设置特殊映射规则。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 主键（平台 ID） |
| `default_field_mappings` | Object | 默认字段映射（源字段 → 目标字段） |
| `description` | String | 配置描述 |
| `is_active` | Boolean | 是否启用 |
| `special_agent_mappings` | Array[Object] | 特殊代理线映射列表 |
| `special_agent_mappings[].agent_line` | String | 代理线名称 |
| `special_agent_mappings[].field_mappings` | Object | 该代理线的字段映射 |
| `special_agent_mappings[].description` | String | 说明 |
| `special_agent_mappings[].is_active` | Boolean | 是否启用 |
| `created_at` | String | 创建时间 |
| `updated_at` | String | 更新时间 |
| `created_by` | String | 创建者用户名 |
| `updated_by` | String | 更新者用户名 |
