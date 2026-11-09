# fb_ad_accounts 集合

**数据库**：plat
**用途**：存储 Facebook 广告账户信息，由 fb_business_sync 同步写入。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 广告账户 ID（纯数字，无 act_ 前缀） |
| `account_id` | String | 广告账户号 |
| `name` | String | 账户名称 |
| `account_status` | Int | 账户状态码（Facebook 定义） |
| `age` | Float | 账户创建天数 |
| `amount_spent` | String | 累计花费金额 |
| `currency` | String | 货币代码（如 `USD`） |
| `disable_reason` | Int | 禁用原因码 |
| `is_prepay_account` | Boolean | 是否预付款账户 |
| `owner` | String | 账户所有者 ID |
| `spend_cap` | String | 支出上限 |
| `tax_id_status` | Int | 税务 ID 状态 |
| `timezone_name` | String | 时区名称 |
| `pixels` | Array[String] | 关联的像素 ID 列表 |
| `facebook_id` | String | 来源个号的 Facebook ID |
| `account_dsl` | Float | 账户单日限额 |
| `updated_at` | DateTime | 更新时间 |
