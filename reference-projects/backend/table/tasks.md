# tasks 集合

**数据库**：plat
**用途**：系统任务管理，记录跨部门协作任务的生命周期。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `task_type` | String | 任务类型 |
| `description` | String | 任务描述 |
| `game_platform` | String | 关联游戏平台 |
| `related_users` | Array[String] | 相关用户列表 |
| `status` | String | 任务状态：`initiated` / `in_progress` / `completed` |
| `deadline` | DateTime | 截止日期 |
| `is_deleted` | Boolean | 是否已删除（软删除标志） |
| `delete_time` | DateTime | 删除时间 |
| `deleted_by` | String | 删除者用户名 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |
| `created_by` | String | 创建者用户名 |
| `updated_by` | String | 更新者用户名 |
