# ad_create_templates 集合

**数据库**：plat
**用途**：存储用户保存的广告创建配置模板，供快速复用投放设置。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 模板名称（同一用户下唯一） |
| `real_name` | String | 创建者姓名 |
| `description` | String | 模板描述 |
| `settings` | Object | 完整配置（见子字段） |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |

### settings.series（广告系列设置）

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `purchaseType` | String | `竞拍` | 购买类型 |
| `seriesType` | String | `销量` | 系列类型 |
| `objectiveType` | String | `广告系列预算` | 目标类型 |
| `budgetType` | String | `单日预算` | 预算类型 |
| `budget` | Float | — | 预算金额 |
| `currency` | String | `USD` | 货币 |
| `targetPrice` | String | `最高数量或价值` | 目标出价方式 |
| `optimizationMethod` | String | `标准` | 优化方式 |
| `flowOptimization` | String | `不限` | 流量优化 |
| `flowOptimizationAmount` | Float | — | 流量优化金额 |

### settings.adGroup（广告组设置）

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `conversionLocation` | String | `WEBSITE` | 转化位置 |
| `performanceGoal` | String | `OFFSITE_CONVERSIONS` | 成效目标 |
| `conversionEvent` | String | `PURCHASE` | 转化事件 |
| `schedule_start_time` | String | — | 排期开始时间 |
| `schedule_end_time` | String | — | 排期结束时间 |

### settings.regionGroup（地区组定向设置）

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `deliveryPosition` | String | `网站` | 投放位置 |
| `billingEvent` | String | `IMPRESSIONS` | 计费事件 |
| `conversionGoal` | String | `PURCHASE` | 转化目标 |
| `country` | String | — | 国家代码 |
| `language` | String | — | 语言 |
| `ageRangeStart` | Int | `18` | 年龄起始 |
| `ageRangeEnd` | Int | `65` | 年龄结束 |
| `gender` | String | `""` | 性别：空=不限 / `1`=男 / `2`=女 |
| `publisher_platforms` | Array[String] | — | 发布平台（facebook/instagram 等） |
| `device_platforms` | Array[String] | — | 设备平台（mobile/desktop） |
| `user_os` | Array[String] | — | 用户操作系统 |
| `isNewModelEnabled` | Boolean | `false` | 是否启用新模型 |

## 索引

- `(real_name, name)`（唯一）
- `real_name`
- `create_time DESC`

## 软删除

删除时移入 `trash` 数据库，追加 `delete_time`、`deleted_by` 字段。
