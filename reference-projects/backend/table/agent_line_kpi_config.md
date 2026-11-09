# agent_line_kpi_config 集合

**数据库**：plat
**用途**：存储代理线的 KPI 目标和自动监控配置，用于广告投放效果自动评估。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `game_platform` | String | 游戏平台 |
| `agent_lines` | Array[String] | 关联代理线名称列表 |
| `target_purpose` | String | 目标用途 |
| `target_cost` | Float | 目标成本 |
| `target_lost_percent` | Float | 目标损失率 |
| `target_lifetime_hour` | Int | 目标生命周期（小时） |
| `max_target_cost` | Float | 最高目标成本 |
| `check_hourly` | String | 检查方式 |
| `event_name` | String | 追踪事件名称 |
| `event_field` | String | 事件字段 |
| `type` | String | 类型 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |
| `created_by` | String | 创建者用户名 |
| `updated_by` | String | 更新者用户名 |

## 软删除

删除时移入 `trash` 数据库。
