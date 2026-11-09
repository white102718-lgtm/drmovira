# material_templates 集合

**数据库**：plat
**用途**：存储素材模板配置，同一用户下模板名称唯一，删除时移入 trash 数据库。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 模板名称（同一用户下唯一） |
| `real_name` | String | 创建者姓名 |
| `description` | String | 模板描述 |
| `batchTitle` | String | 批量广告标题 |
| `batchDescription` | String | 批量广告正文 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |

## 索引

| 索引字段 | 说明 |
|----------|------|
| `{real_name: 1, name: 1}` | 唯一复合索引 |
| `{create_time: -1}` | 时间倒序排列 |

## 软删除

删除时文档移入 `trash.material_templates`，追加以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `delete_time` | DateTime | 删除时间 |
| `deleted_by` | String | 删除者用户名 |
