# fb_pages 集合

**数据库**：plat
**用途**：存储 Facebook 主页信息，由 fb_business_sync 同步写入。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | Facebook 主页 ID |
| `name` | String | 主页名称 |
| `category` | String | 主页分类 |
| `facebook_id` | String | 来源个号的 Facebook ID |
| `updated_at` | DateTime | 更新时间 |
