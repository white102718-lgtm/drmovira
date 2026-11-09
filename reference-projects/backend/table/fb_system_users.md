# fb_system_users 集合

**数据库**：plat
**用途**：存储 Facebook 系统用户（System User）的资源列表，用于映射广告账户与开发者应用凭据。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 主键（Facebook App ID） |
| `accounts` | Array[Object] | 关联的广告账户列表 |
| `accounts[].id` | String | 广告账户 ID（不含 `act_` 前缀） |
| `accounts[].name` | String | 广告账户名称 |
| `pages` | Array[Object] | 关联的 Facebook 主页列表 |
| `pages[].id` | String | 主页 ID |
| `pages[].name` | String | 主页名称 |
| `updated_at` | DateTime | 更新时间（UTC） |

## 索引

| 索引字段 | 说明 |
|----------|------|
| `{accounts.id: 1}` | 按广告账户 ID 查询 |
| `{pages.id: 1}` | 按主页 ID 查询 |
