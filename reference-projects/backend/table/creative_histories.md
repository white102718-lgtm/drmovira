# creative_histories 集合

**数据库**：plat
**用途**：记录用户保存的创意广告历史，每个用户最多保留 100 条。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `username` | String | 操作用户名 |
| `real_name` | String | 操作用户姓名 |
| `creatives` | Array[Object] | 创意列表（广告素材配置） |
| `creatives_count` | Integer | 创意数量 |
| `created_at` | String | 创建时间（ISO 格式） |
