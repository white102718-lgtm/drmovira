# personal_accounts 集合

**数据库**：plat
**用途**：存储绑定的 Facebook 个人账户信息，用于 Facebook Business 数据同步（个号路径）。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | Facebook ID（作为主键，无独立 `facebook_id` 字段） |
| `name` | String | Facebook 账户名称 |
| `email` | String | 邮箱 |
| `app_id` | String | 关联的 Facebook App ID（对应 accounts 集合） |
| `app_secret` | String | App Secret（敏感，可从 accounts 补充） |
| `access_token` | String | 用户访问令牌（敏感） |
| `expires_in` | Int | 令牌有效期（秒） |
| `created_at` | String | 令牌创建时间，格式 `YYYY-MM-DD HH:MM:SS`（注意是字符串，非 DateTime） |
| `user_name` | String | 绑定的投放师标识，值对应 `user` 集合的 `real_name`（如 `Sha`），非登录名 `username`，也非中文名 |
| `status` | Boolean | 账户状态：`True`=启用，`False`=停用 |
| `accounts` | Array[String] | 关联的广告账户 ID 列表 |
| `business` | Array[String] | 关联的 Business Manager ID 列表 |
| `pages` | Array[String] | 关联的 Facebook 主页 ID 列表 |
| `updated_at` | DateTime | 更新时间 |

## 常用查询条件

- `{"status": True}` — 查询启用的个人号（注意：此集合用 Boolean，非 Int）
- `{"_id": facebook_id}` — 按 Facebook ID 查询

## 关联说明

- 通过 `app_id` 关联 `accounts` 集合，补充 `proxy`、`app_secret`
- 通过 `user_name` 关联 `user` 集合的 `real_name`，取该用户 `full_name` 作为「投放师」显示名（鉴权失效告警用此链路）：`user.find_one({"real_name": user_name}).full_name`。`user_name` 查不到对应 user 时，投放师为空
- 同步任务推送时，`token_type` 为 `personal`，`sync_flags` 为 `{"sync_personal": True}`
