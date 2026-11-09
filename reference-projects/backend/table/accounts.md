# accounts 集合

**数据库**：plat
**用途**：存储广告平台开发者配置信息（Facebook / Google），供拉取广告数据、Facebook Login 等功能使用。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 对应 `fb_system_users._id`|
| `status` | Int | 状态：`1`=启用，`0`=停用，`2`=异常（系统判定开发者失效） |
| `ad_platform` | String | 平台：`facebook` / `google` |
| `description` | String | 备注描述 |
| `proxy` | String | 代理地址，供 API 请求使用 |
| `update_time` | DateTime | 更新时间 |

### Facebook 专属字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `app_id` | String | Facebook App ID |
| `app_secret` | String | Facebook App Secret（敏感） |
| `access_token` | String | 访问令牌（敏感） |
| `dev_id` | String | 开发者 ID |
| `config_id` | String | Facebook Login 配置 ID |
| `account_usage` | Object | 账号用途开关，嵌套对象，字段见下 |
| `account_usage.insights_pull` | Boolean | 是否启用广告数据（Insights）拉取 |
| `account_usage.facebook_login` | Boolean | 是否启用 Facebook Login 功能 |
| `account_usage.sync_personal` | Boolean | 是否同步个号 |
| `account_usage.sync_bm` | Boolean | 是否同步 BM |
| `account_usage.sync_pixels` | Boolean | 是否同步像素 |

### Google 专属字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `customer_id` | String | Google Ads 客户 ID |
| `login_customer_id` | String | 登录客户 ID（MCC） |
| `developer_token` | String | 开发者令牌（敏感） |
| `service_account_json` | String | 服务账号 JSON（敏感） |

## 常用查询条件

- `{"status": 1}` — 查询启用账户
- `{"account_usage.facebook_login": True, "status": 1}` — Facebook Login 可用账户
- `{"account_usage.insights_pull": True, "status": 1}` — 可拉取 Insights 的账户
- `{"account_usage.sync_personal": True, "status": 1}` — 同步个号的账户
- `{"account_usage.sync_bm": True, "status": 1}` — 同步 BM 的账户
- `{"account_usage.sync_pixels": True, "status": 1}` — 同步像素的账户
- `{"app_id": "xxx", "account_usage.facebook_login": True, "status": 1}` — 按 App ID 查询
