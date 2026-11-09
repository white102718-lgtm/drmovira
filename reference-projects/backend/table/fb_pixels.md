# fb_pixels 集合

**数据库**：plat
**用途**：存储 Facebook 追踪像素信息，由 fb_business_sync 同步写入。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | Facebook 像素 ID |
| `name` | String | 像素名称 |
| `facebook_id` | String | 来源个号的 Facebook ID |
| `updated_at` | DateTime | 更新时间 |
