# Dashboard 数据看板需求文档

## 1. 业务背景

这是一个 **Facebook/Meta 广告投放数据看板**，供内部运营团队查看各维度的投放数据和效果指标。

- 数据从 Facebook Marketing API 同步到 Doris (兼容 MySQL 协议) 数据库
- 部分业务字段（部门、游戏平台、代理线、投手）通过广告的 `landing_url` 匹配规则自动归类
- 渠道信息存储在 ERP 系统中，通过 account_id 关联

### 核心文件

| 文件 | 职责 |
|------|------|
| `dashboard.py` | 汇总、填充提交、BI 历史等接口，SQL 构建函数仅供内部复用 |
| `dashboard_detail.py` | **唯一的维度明细接口** (`GET /dashboard/detail/{dimension}`)，使用 Builder 模式 + `DetailQueryHandler` 类 |

`dashboard.py` 中的 `get_detail_by_dimension` 已删除，所有维度明细查询统一走 `dashboard_detail.py`。

---

## 2. 维度层级结构

维度从上到下，形成层级关系，上层维度可以作为下层的筛选条件：

```
department (部门)
  └─ game_platform (游戏平台)
       └─ ad_platform (广告平台)
            └─ agent_line (代理线)
                 └─ placer_id (投手)
                      └─ channel (渠道) ← 独立逻辑，来自 ERP
                           └─ account_id (账户)
                                └─ campaign_id (系列)
                                     └─ ad_set_id (广告组)
                                          └─ ad_id (广告)
```

定义在 `DimensionType` 枚举中，顺序即上面的顺序。

### `newest_dim` 概念

前 7 个维度（department ~ account_id）属于 `newest_dim`，它们与 campaign_id/ad_set_id/ad_id 在显示列上有差异：
- `newest_dim` 内：无状态列、无创建时间列、无频次列、无去重链接点击数（account_id 例外：有状态列）
- `newest_dim` 外：有状态列、有创建时间列、有频次(3d/5d/7d)列、有去重链接点击数/去重点击成本

### `subset` 概念

每个维度的 `subset` 是它前面的所有维度集合，用于：
1. 前端传入上层维度的筛选值
2. 代理线维度的填充数据中展示上层维度列（部门、游戏平台、广告平台）

例如 `agent_line` 的 `subset = {"department", "game_platform", "ad_platform"}`

---

## 3. 数据源

### 3.1 数据表

| 表名 | 用途 | 粒度 | 说明 |
|------|------|------|------|
| `ad_hourly_detail` | 最新数据（is_newest=True） | 小时级，有 `level` 字段 | 包含 campaign/adset/ad 各级别数据 |
| `ad_daily_detail` | 最新数据按天（dashboard_detail.py 使用） | 天级，有 `level` 字段 | 同上，但是天级别聚合 |
| `ad_hourly_summary` | 填充数据（is_newest=False） | 小时级，按 platform+agent_line+department 聚合 | 包含 bi 字段 |

`level` 字段值：`'campaign'` / `'adset'` / `'ad'` / `'account'`

### 3.2 ERP 数据库

用于获取：
- 渠道 → 账户 ID 的映射关系 (`get_channel_account_mapping`)
- 渠道名称 (`get_channel_names`)
- 系列维度的渠道列（Python 层补充）

---

## 4. 查询参数

### 4.1 请求参数 (`DashboardQueryParams`)

| 参数 | 类型 | 说明 |
|------|------|------|
| `date` | str | 日期范围，逗号分隔。按天: `"2024-01-01,2024-01-07"`；按小时: `"2024-01-01 00,2024-01-01 23"` |
| `is_newest` | bool | `True` = 最新数据（ad_hourly_detail），`False` = 填充数据（ad_hourly_summary） |
| `show_1d` | bool | 是否显示 1d 归因指标列 |
| `sort_by` | str | 排序字段（中文名，如 "花费金额"） |
| `sort_order` | str | `asc` / `desc` |
| `page` / `page_size` | int | 分页 |
| `status` | str | 状态过滤，逗号分隔（如 "ACTIVE,PAUSED"） |
| `name` | str | 按名称前缀搜索 |
| `tab_order` | str | 自定义维度排序（影响 subset 计算） |
| 各维度字段 | str | 筛选条件，如 `department=部门A`，多个值逗号分隔 |

### 4.2 `is_hour` 判断

通过 `date` 参数长度判断：长度 13（如 `"2024-01-01 00"`）为小时模式，否则为天模式。

小时模式的差异：
- GROUP BY 多加 `date`
- SELECT 多加 `DATE_FORMAT(date, '%m-%d %H:%i') AS 时间`

### 4.3 `show_1d` 差异

开启时在对应指标后插入 1d 归因版本：
- `安装数` → `1d安装数` (app_installs_1dclick)
- `注册数` → `1d注册数` (register_1dclick)
- `注册成本` → `1d注册成本`
- `订阅数/成本/价值` → `1d订阅数/成本/价值`
- `购物数/成本/价值/roas` → `1d购物数/成本/价值/roas`

仅影响 SELECT 字段，不影响 FROM/WHERE/GROUP BY。

---

## 5. 核心查询机制

### 5.1 `from_ad_level` 机制

某些维度（部门、游戏平台、广告平台、代理线、投手）的数据源自广告级别的 `landing_url` 匹配，因此必须从 `level='ad'` 向上聚合。

在 `dashboard_detail.py` 中，`from_ad_level` 是 `DimensionQueryBuilder` 基类的 property，通过维度类型自动推导，不需要手动设置：

```python
_OWN_LEVEL_DIMS = {"campaign_id", "ad_set_id", "ad_id", "account_id"}

@property
def from_ad_level(self) -> bool:
    return self.dimension not in self._OWN_LEVEL_DIMS
```

当 `from_ad_level=True` 时：
- 查询使用 `level='ad'` 而非维度自身的 level
- **不会走**单行小时明细路径（即使 is_hour=True 也走 CTE 聚合）

### 5.2 `ad_level_filters` 机制

当查询 campaign_id / ad_set_id / ad_id 维度时，所有 subset 过滤条件（如 department、game_platform）不直接加到 WHERE，而是收集到 `ad_level_filters` 字典中。

这是因为 department/agent_line 等字段在 ad 级别通过 landing_url 匹配得到，**可能与 campaign/adset 级别的值不同**（ad 级别会覆盖）。直接在 campaign/adset 级别用这些字段过滤会导致查不到数据。

#### 5.2.1 ID 字段 vs 维度字段的区别

`ad_level_filters` 中的字段分两类，处理方式不同：

| 类型 | 字段 | 处理方式 |
|------|------|---------|
| **ID 字段** | campaign_id, ad_set_id, ad_id, account_id | 各级别都存在且值一致，**直接加到 WHERE** |
| **维度字段** | department, agent_line, game_platform 等 | 仅 ad 级别准确，需先从 ad 级别查出对应实体 ID（`get_entity_ids_from_ad_level`） |

例如查询 ad_set_id 时传入 `department=技术部&campaign_id=xxx`：
1. `campaign_id` 是 ID 字段 → 直接加 `AND campaign_id IN (...)`
2. `department` 是维度字段 → 从 ad 级别查出满足条件的 ad_set_id 列表 → 再加 `AND ad_set_id IN (...)`

#### 5.2.2 IS NULL 条件的特殊处理（`ad_level_null_filters`）

当筛选值为 `"null"` 时（如 `department=null`），表示"该字段在上层为空"。对于 campaign_id / ad_set_id / ad_id 维度，这类 IS NULL 条件存入 `ad_level_null_filters`，**不直接加到 where_sql**。

原因：ad 级别的 department/agent_line 会被 landing_url 覆盖为非 NULL 值，即使 campaign 级别为 NULL。如果在 ad 级别加 `AND department IS NULL`，查不到数据。

处理逻辑按维度分三种情况：
- **ad_id 维度**：查询本身就在 `level='ad'`，department 等字段直接存在于查询表中，IS NULL 条件和维度字段筛选都**直接拼到 where_sql**，不走子查询。这避免了大量 ad_id 塞入 `IN (...)` 导致 Doris 表达式树超限（10000）的问题。
- **campaign_id / ad_set_id 维度**：若有维度字段筛选（`ad_only_filters` 非空）或 null 筛选，IS NULL 条件合并到 ad 级别子查询中，查出对应实体 ID 列表后再 `IN (...)`
- 若只有 **ID 字段筛选**且无 null 筛选：无需额外处理

### 5.3 下钻筛选机制

当查询 channel / account_id 等"上层"维度时，URL 中可能携带"下层"维度的筛选条件（如 `campaign_id`、`ad_set_id`），这些条件不在 subset 中（subset 只包含当前维度之前的维度）。

为支持从下层维度向上钻取查看的场景，非 ad_level_dim 维度会额外应用 `campaign_id`、`ad_set_id`、`ad_id` 的下钻筛选：

```python
_drill_down_dims = {"campaign_id", "ad_set_id", "ad_id"}
```

这些筛选直接加到 WHERE 条件中，因为这些 ID 字段在各级别的数据表中都存在。

### 5.4 系列/广告组/广告维度的查询流程

campaign_id / ad_set_id / ad_id 的 `_apply_ad_level_filters` 完整流程：

1. 将 `ad_level_filters` 拆分为 `direct_filters`（ID 字段）和 `ad_only_filters`（维度字段）
2. 直接应用 `direct_filters` 到 WHERE
3. **ad_id 维度**（本身查 `level='ad'`）：维度字段和 IS NULL 条件直接拼到 WHERE，无需子查询
4. **campaign_id / ad_set_id 维度**：若有 `ad_only_filters` 或 `ad_level_null_filters`：
   - 合并 IS NULL 条件
   - 从 ad 级别查出满足条件的实体 ID 列表（`get_entity_ids_from_ad_level`）
   - 将实体 ID 列表加到 WHERE
5. 主查询回到自身级别（campaign/adset/ad）执行

---

## 6. SQL 构建路径（dashboard_detail.py）

### 6.1 三种路径

| 方法 | 适用条件 | 数据源 | 特点 |
|------|---------|--------|------|
| `build_filled_sql` | `is_newest=False` 且 `len(subset) <= index("agent_line")` | `ad_hourly_summary` | 含 bi 字段，按最新日期取数 |
| `build_hourly_sql` | `is_hour=True` | `ad_hourly_detail` | 非 from_ad_level 走单行明细；from_ad_level 走 CTE 聚合 |
| `build_daily_sql` | 其余情况（按天） | `ad_daily_detail` | **直接聚合，无 ROW_NUMBER 去重** |

### 6.2 `build_daily_sql` 关键设计

`ad_daily_detail` 每天已存储最新一条数据，**不需要 ROW_NUMBER 去重**，直接 GROUP BY 聚合：
- 单天查询：每个实体一条，SUM 等于本身
- 多天查询：每天各一条，SUM 跨天累加

仅当子类定义了窗口列（`_daily_window_columns` 或 `_extra_rn_columns`）时使用 CTE，否则直接查询。

### 6.3 dashboard.py 中的遗留 SQL 构建函数

`construct_newest_sql` / `construct_filled_sql` / `construct_hour_detail_sql` / `query_channel_dimension_data` 等旧构建函数已删除，维度查询统一走 dashboard_detail.py。dashboard.py 只保留 `SORTABLE_FIELDS` / `validate_and_build_order_clause` / `generate_dimension_subset` / `get_channel_account_mapping` 等被 dashboard_detail.py 复用的公共部分。

---

## 7. 去重逻辑

### 7.1 hourly 路径：grouping_date + rn（仅 ad_hourly_detail）

0 点的数据归前一天：

```sql
CASE
  WHEN EXTRACT(HOUR FROM date) = 0
       THEN CAST(date - INTERVAL '1' DAY AS DATE)
  ELSE CAST(date AS DATE)
END AS grouping_date
```

```sql
ROW_NUMBER() OVER (
    PARTITION BY {dimension}, ad_id, grouping_date
    ORDER BY
        CASE WHEN EXTRACT(HOUR FROM date) = 0 THEN 0 ELSE 1 END,
        date DESC
) AS rn
```

最终 `WHERE rn = 1` 保留每组最新一条。

### 7.2 daily 路径：无 rn 去重（ad_daily_detail）

`ad_daily_detail` 每天已是最新一条，不需要 ROW_NUMBER 去重，直接聚合。

### 7.3 在跑预算去重（`_enrich_running_budget`，Python 层）

`from_ad_level` 维度（department / game_platform / ad_platform / agent_line）的在跑预算通过 `DetailQueryHandler._enrich_running_budget` 方法在 Python 层单独查询补充，不在主 SQL 中处理。只统计投放中（ACTIVE/IN_PROCESS 且账户正常）的系列，已暂停不计。

原因：ad 级别数据没有 budget 字段，campaign 级别数据没有维度字段（department 等），无法在一条 SQL 中同时获取。

查询使用 JOIN：
```sql
SELECT t_ad.{dim}, SUM(t_camp.budget)/100 AS total_budget
FROM (
    -- ad 级别: 取维度→campaign_id 映射（不限日期，映射关系稳定）
    SELECT DISTINCT {dim}, campaign_id
    FROM {table}
    WHERE level = 'ad' {where_sql}
) t_ad
JOIN (
    -- campaign 级别: 取每个 campaign 最新预算（按日期过滤）
    SELECT campaign_id, budget, delivery_str, account_status,
        ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY date DESC) AS rn
    FROM {table}
    WHERE level = 'campaign' AND {date_sql}
) t_camp ON t_ad.campaign_id = t_camp.campaign_id
WHERE t_camp.rn = 1 AND t_camp.delivery_str IN ('ACTIVE','IN_PROCESS') AND t_camp.account_status IN (1,8,9)
GROUP BY t_ad.{dim}
```

关键点：
- ad 映射子查询**不加日期过滤**：campaign 的 agent_line 由 landing_url 决定，不随日期变化；加日期会遗漏当天无 ad 数据的 campaign
- campaign 子查询**加日期过滤**：取查询日期范围内最新的预算值
- 结果通过 `budget_map` 按维度值匹配写入 `result` 列表，并在 `columns` 中插入到"花费金额"之后（在跑预算与花费金额都固定在左侧，固定列必须连续，否则前端错位）

---

## 8. 预算/消耗拆分计算规则

聚合维度不再展示"预算"列，改为在"花费金额"后展示三列：**在跑预算、已关停消耗、在跑消耗**（在跑预算紧跟花费金额，两列都固定在左侧）。

- 在跑判定：`delivery_str IN ('ACTIVE','IN_PROCESS') AND account_status IN (1,8,9)`（`_RUNNING_COND`），已暂停/已删除/账户停用均算已关停
- 已关停消耗 / 在跑消耗：主 SQL 中按行状态 `CASE` 拆分 `amount_spent`，两列之和等于花费金额；多天查询时按每天快照的状态归属
- 在跑预算：只统计在跑系列的预算

| 维度范围 | 计算方式 | 说明 |
|---------|---------|------|
| department ~ agent_line / placer_id | 消耗拆分在主 SQL（ad 级别行）；在跑预算走 `_enrich_running_budget` Python 层 JOIN 查询 | ad 级别取维度→campaign_id 映射，campaign 级别取最新预算 |
| campaign_id / ad_set_id | 预算 = `ANY_VALUE(latest_budget) / 100` | 自身预算，保留"预算"列，无消耗拆分 |
| account_id / ad_id | 不展示预算 | — |
| channel | 三列均在主 SQL（campaign 级别行）；在跑预算 = `SUM(CASE WHEN rn = 1 AND 在跑 THEN budget END) / 100` | 预算是时点值，只取 rn=1 快照 |
| filled 路径 | 无预算列，在跑预算由 `_enrich_running_budget` 补充 | summary 表无状态字段，无消耗拆分 |

预算单位为分，显示时除以 100。

**注意：** `from_ad_level` 维度的在跑预算不能在主查询 SQL 中直接计算，因为 ad 级别没有 budget 字段，campaign 级别没有维度字段（department/agent_line 等）。必须通过 `_enrich_running_budget` 单独查询后合并到结果中。

---

## 9. 各维度配置一览

`from_ad_level` 由基类 property 自动推导：`dimension not in {"campaign_id", "ad_set_id", "ad_id", "account_id"}` 即为 True。

| 维度 | level | from_ad_level | 额外列 |
|------|-------|---------------|--------|
| department | campaign | True (→ ad) | 已关停/在跑消耗、在跑预算（`_enrich_running_budget` Python 层补充） |
| game_platform | campaign | True (→ ad) | 已关停/在跑消耗、在跑预算（`_enrich_running_budget` Python 层补充） |
| ad_platform | campaign | True (→ ad) | 已关停/在跑消耗、在跑预算（`_enrich_running_budget` Python 层补充） |
| agent_line | campaign | True (→ ad) | 已关停/在跑消耗、在跑预算（`_enrich_running_budget` Python 层补充）；filled 时展示 subset 列 |
| placer_id | campaign | True (→ ad) | 已关停/在跑消耗、在跑预算（`_enrich_running_budget` Python 层补充） |
| channel | campaign | N/A（独立逻辑） | Python 层聚合，数据来自 ERP |
| account_id | account | False | 状态、户余额、户限额、单日限额；先从 campaign 级别查出 account_id 列表 |
| campaign_id | campaign | False（先查 ID 再回来） | 状态、创建时间、频次、账户名、账户 ID、渠道（ERP 补充） |
| ad_set_id | adset | False | 状态、创建时间、频次 |
| ad_id | ad | False | 状态、创建时间、频次、unique_name、主页 ID、帖子 ID、投放链接 |

---

## 10. 渠道维度特殊逻辑

渠道维度完全独立，不走通用 SQL 构建，流程如下：

1. **`_apply_account_filter` 预处理**：先从 `level='ad'` 查出满足 department/agent_line 等筛选条件的 account_id 列表，将 where_sql 替换为 `AND account_id IN (...)`
2. 从 ERP 获取 `channel_id → account_id[]` 映射
3. 从 `ad_daily_detail`/`ad_hourly_detail`（level='campaign'）查账户级别数据，WHERE 条件中只有 `account_id IN (...)`（不分页，需全量）
4. Python 层按 `channel_id` 聚合各账户数据
5. 从 ERP 获取渠道名称
6. Python 层重新计算派生字段（百分比、比率、成本）
7. Python 层排序 + 分页

**关键点**：渠道和账户共用 `_apply_account_filter` 预处理逻辑。department/agent_line 等字段在 campaign 级别可能与 ad 级别不一致（ad 级别通过 landing_url 覆盖），因此必须从 ad 级别查找匹配的 account_id，而非直接在 campaign 级别过滤。

---

## 11. 账户维度特殊逻辑

账户维度预处理：先通过 **ad 级别**查出满足 where_sql 的 account_id 列表，再用 `account_id IN (...)` 查 account 级别数据。

从 ad 级别查找是因为 department/agent_line 等字段在 ad 级别最准确（ad 级别通过 landing_url 匹配可能覆盖 campaign 级别的值）。account 级别数据本身没有这些筛选字段，需要先从 ad 级别确定符合条件的账户。

额外列：
- 户余额：`FIRST_VALUE(balance) OVER (...) / 100`
- 户限额：`FIRST_VALUE(spend_cap) OVER (...) / 100`
- 单日限额：`FIRST_VALUE(account_dsl) OVER (...)`

---

## 12. 指标列定义

### 基础指标（所有维度共有）

| 显示名 | SQL 表达式（聚合模式） | 字段名 |
|--------|----------------------|--------|
| 花费金额 | `ROUND(SUM(amount_spent), 2)` | amount_spent |
| 覆盖人数 | `SUM(reach)` | reach |
| 展示次数 | `SUM(impressions)` | impressions |
| 点击数 | `SUM(clicks_all)` | clicks_all |
| 点击率 | `SUM(clicks_all)*100.0/SUM(impressions)` | 计算字段 |
| 点击成本 | `SUM(amount_spent)/SUM(clicks_all)` | 计算字段 |
| 链接点击数 | `SUM(inline_link_clicks)` | inline_link_clicks |
| 安装数 | `SUM(app_installs)` | app_installs |
| 注册数 | `SUM(complete_registration)` | complete_registration |
| 注册转化率 | `SUM(complete_registration)/SUM(clicks_all)*100` | 计算字段 |
| 注册成本 | `SUM(amount_spent)/SUM(complete_registration)` | 计算字段 |
| 订阅数 | `SUM(subscribe_website)` | subscribe_website |
| 订阅率 | `SUM(subscribe_website)/SUM(complete_registration)*100` | 计算字段 |
| 订阅成本 | `SUM(amount_spent)/SUM(subscribe_website)` | 计算字段 |
| 订阅价值 | `SUM(subscribe_website_values)` | subscribe_website_values |
| 购物数 | `SUM(purchases)` | purchases |
| 购物率 | `SUM(purchases)/SUM(complete_registration)*100` | 计算字段 |
| 购物成本 | `SUM(amount_spent)/SUM(purchases)` | 计算字段 |
| 购物价值 | `SUM(purchases_value)` | purchases_value |
| 购物roas | `SUM(purchases_value)/SUM(amount_spent)` | 计算字段 |
| 对话数 | `SUM(messaging_conversation_started)` | messaging_conversation_started |
| 对话成本 | `SUM(amount_spent)/SUM(messaging_conversation_started)` | 计算字段 |

### 非 newest_dim 专有（campaign_id / ad_set_id / ad_id）

| 显示名 | SQL 表达式 |
|--------|-----------|
| 千展 | `SUM(amount_spent)/SUM(impressions)*1000` |
| 去重链接点击数 | `SUM(unique_inline_link_clicks)` |
| 去重点击成本 | `SUM(amount_spent)/SUM(unique_inline_link_clicks)` |
| 频次 | `AVG(frequency)` |
| 3d频次 | `AVG(frequency_3d)` |
| 5d频次 | `AVG(frequency_5d)` |
| 7d频次 | `AVG(frequency_7d)` |

### BI 指标（仅 filled 路径 / ad_hourly_summary）

| 显示名 | SQL 表达式 | 字段名 |
|--------|-----------|--------|
| bi注册数 | `SUM(bi_registrations)` | bi_registrations |
| bi首充人数 | `SUM(bi_first_recharge_users)` | bi_first_recharge_users |
| bi首充金额 | `SUM(bi_first_recharge_amount)` | bi_first_recharge_amount |
| bi首充成本 | `SUM(amount_spent)/SUM(bi_first_recharge_users)` | 计算字段 |
| bi首次roas | `SUM(bi_first_recharge_amount)/16000/SUM(amount_spent)` | 计算字段（16000 为汇率） |
| bi首次arppu | `SUM(bi_first_recharge_amount)/16000/SUM(bi_first_recharge_users)` | 计算字段 |
| bi注册成本 | `SUM(amount_spent)/SUM(bi_registrations)` | 计算字段 |

---

## 13. dashboard_detail.py 代码架构

### 13.1 `DetailQueryHandler` 类

路由函数只有两行，所有逻辑封装在 `DetailQueryHandler` 中：

```python
@router.get("/detail/{dimension}")
async def get_detail_by_dimension_v2(...):
    handler = DetailQueryHandler(dimension, query_params, db, erp_db, current_user)
    return await handler.execute()
```

Handler 持有全部状态（`self.where_sql`、`self.params`、`self.date_sql` 等），Builder 方法直接接收 handler 作为 `ctx` 参数访问这些属性。

**注意事项：**
- 无独立的 `QueryContext` 类，handler 本身就是上下文
- handler 提供 `offset` property 和 `order_clause()` 方法供 builder 使用
- `is_newest` 和 `show_1d` 是 property，从 `q_params` 实时读取

### 13.2 Builder 单例

`DIMENSION_BUILDERS` 字典中的 builder 是模块级单例，不能存储请求级别的状态。所有请求相关数据通过 `ctx`（即 handler）传递。

### 13.3 `_build_daily_columns` / `_build_hourly_columns` 的设计约束

每个 builder 需要分别定义 daily 和 hourly 的列，因为 SQL 表达式不同（`SUM(x)` vs `x`）。目前无法合并到 `__init__`，因为：
1. Builder 是单例，不能存请求级状态（`show_1d` 每次请求可能不同）
2. daily/hourly 的 SQL 表达式根本不同

---

## 14. 筛选条件构建流程

```
1. 解析 DashboardQueryParams → q_params (split 处理逗号)
2. 计算 subset = 当前维度之前的所有维度
3. 提取 subset_params = q_params 中属于 subset 的字段

4. 遍历 subset_params:
   ├─ "null" 值处理:
   │    ├─ ad_level_dim 且非 ID 字段 → 存入 ad_level_null_filters
   │    └─ 其他 → 直接加 WHERE ... IS NULL
   ├─ channel → 暂存 channel_filter_ids，后续转换
   ├─ account_id → 补 act_ 前缀
   ├─ campaign/adset/ad 维度 → 收集到 ad_level_filters（不直接加 WHERE）
   └─ 其他 → 直接加 WHERE ... IN (...)

5. 下钻筛选（非 ad_level_dim 维度）:
   campaign_id/ad_set_id/ad_id 若在 URL 中但不在 subset 中 → 直接加 WHERE

6. channel_filter_ids → ERP 查映射 → account_id IN (...)
7. account_id/channel 维度 → 从 ad 级别查 account_id 列表，替换 where_sql
8. channel 维度 → 额外筛选条件处理
9. status 过滤 → account 维度: account_status IN (...); 其他维度: status IN (...)

10. _apply_ad_level_filters:
    ├─ ID 字段(campaign_id 等) → 直接加 WHERE
    ├─ ad_id 维度 → 维度字段和 IS NULL 条件直接加 WHERE（本身就查 ad level）
    ├─ campaign_id/ad_set_id 维度 → 维度字段从 ad 级别查实体 ID 列表
    └─ ad_level_null_filters → 合并到 ad 级别子查询（仅 campaign/adset）
```

---

## 15. 排序机制

- 排序字段使用中文名（如 "花费金额"），通过 `SORTABLE_FIELDS` 白名单映射到 SQL 表达式
- 有 `aggregated`（聚合模式）和 `hourly`（小时明细模式）两套白名单
- 默认排序：花费金额降序
- 所有排序加 `NULLS LAST`

---

## 16. 权限控制

- 用户的 `departments` 列表限制可见数据范围：`AND department IN (...)`
- 非 operator/developer/test/admin 角色的用户只能查看 `newest_dim` 范围内的维度
