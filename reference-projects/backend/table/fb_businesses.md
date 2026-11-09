# fb_businesses 集合

**数据库**：plat
**用途**：存储 Facebook Business Manager 信息，由 fb_business_sync 同步写入。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 复合 ID，格式：`{facebook_id}_{business_id}` |
| `facebook_id` | String | 来源个号的 Facebook ID |
| `business_id` | String | Business Manager ID |
| `business_name` | String | BM 名称 |
| `accounts` | Array[String] | BM 下的广告账户 ID 列表 |
| `pages` | Array[String] | BM 下的主页 ID 列表 |
| `pixels` | Array[String] | BM 下的像素 ID 列表 |
| `updated_at` | DateTime | 更新时间 |

## 关联说明

- `facebook_id` 关联 `personal_accounts._id`
- `accounts` 内容对应 `fb_ad_accounts._id`
