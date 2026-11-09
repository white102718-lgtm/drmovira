# platform_config 集合

**数据库**：plat
**用途**：存储游戏平台的全局配置信息，关联代理线、区域、素材分类等。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 游戏平台名称（主键） |
| `attribution_platform` | String | 归因平台 |
| `agent_lines` | Array[String] | 关联的代理线名称列表 |
| `enabled` | Boolean | 是否启用 |
| `visible` | Boolean | 是否对前端可见 |
| `total_budget` | Float | 总预算 |
| `target_region` | Array[String] | 目标投放区域列表 |
| `material_category_ids` | Array[String] | 关联素材分类 ID 列表 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |
| `created_by` | String | 创建者用户名 |
| `updated_by` | String | 更新者用户名 |

## 软删除

删除时移入 `trash` 数据库。
