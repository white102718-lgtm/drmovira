# material_group_histories 集合

**数据库**：plat
**用途**：记录素材组的应用历史，每个用户保留最近 100 条。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `group_id` | String | 关联素材组 ID |
| `group_name` | String | 素材组名称快照 |
| `materials_count` | Int | 素材数量 |
| `materials` | Array[Object] | 素材配置快照 |
| `applied_at` | DateTime | 应用时间 |
| `username` | String | 操作用户名 |
| `user_id` | String | 用户 ID |
| `real_name` | String | 用户姓名 |
| `apply_mode` | String | 应用方式：`replace`=替换 / `append`=追加 |

## 索引

- `(username, applied_at DESC)`
- `group_id`
