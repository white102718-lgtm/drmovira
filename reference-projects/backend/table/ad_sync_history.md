# ad_sync_history 集合

**数据库**：plat
**用途**：记录广告数据同步任务的执行历史，用于去重和追踪同步状态。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `date` | String | 同步日期，格式 `YYYY-MM-DD` 或 `YYYY-MM-DD HH` |
| `dev_id` | String | 开发者 ID |
| `ad_platform` | String | 广告平台：`facebook` / `google` |
| `agent_lines` | Array[String] | 代理线列表 |
| `placer_id` | String | 投手 ID |
| `run_status` | String | 执行状态：`running` / `success` / `failed` |
| `errors` | String | 错误信息 |
| `plat_map` | Object | 平台映射信息 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |

## 索引

- `(date DESC, agent_lines)`
