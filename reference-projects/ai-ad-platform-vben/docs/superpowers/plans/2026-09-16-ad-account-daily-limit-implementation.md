# 资产管理广告户账户日限额展示实施方案

## 1. 需求目标

在“资产管理 > 广告户”中增加“账户日限额”信息，并在以下位置保持一致展示：

- 广告户列表；
- 广告户 Excel 导出；
- “编辑广告账户”抽屉。

账户日限额只读，数据唯一来源为 MongoDB `fb_ad_accounts.account_dsl`。本次不增加编辑、批量修改、筛选、导入能力，也不修改现有账户保存行为。

## 2. 数据链路

```text
MongoDB fb_ad_accounts.account_dsl
  -> adpulse-main AdAccountAssetService
  -> AdAccountAssetViews.Account.accountDailyLimit
  -> 前端 AdAccountAsset.accountDailyLimit
  -> 列表 / Excel 导出 / 编辑抽屉只读展示
```

### 字段契约

| 层级 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- |
| MongoDB | `account_dsl` | 数值或空值 | Facebook 广告账户单日限额 |
| Java API | `accountDailyLimit` | `BigDecimal`，可空 | 保留金额精度，不写入 MySQL 资产台账 |
| TypeScript | `accountDailyLimit?: number \| null` | 可空数值 | 仅供展示和导出 |

兼容 Mongo 历史数据可能出现的 `Double`、`Decimal128` 或数值字符串。无法解析或字段不存在时返回 `null`，前端统一显示 `—`。

## 3. 后端实施

仓库：`D:\progress\adpulse-power-system`，模块：`adpulse-main`。

### 3.1 扩展响应模型

修改：

- `adpulse-main/src/main/java/com/adpulse/main/adaccountasset/AdAccountAssetViews.java`

在 `AdAccountAssetViews.Account` 中新增可空字段 `BigDecimal accountDailyLimit`。只扩展返回结构，不修改请求 DTO、数据库表或 MyBatis Mapper。

### 3.2 从 Mongo 快照映射日限额

修改：

- `adpulse-main/src/main/java/com/adpulse/main/adaccountasset/AdAccountAssetService.java`

在统一账户视图组装逻辑中读取 `platformAccount.account_dsl`：

- 有 Mongo 账户快照时，解析并返回日限额；
- Mongo 无对应账户或字段为空时返回 `null`；
- 不从 MySQL `ad_account_asset` 回退，避免形成第二数据源；
- 不把日限额写入账户编辑、批量修改或导入流程。

由于资产列表、按 ID 批量查询、我的广告户、按渠道查询和生命周期详情共用该账户视图，接口响应会保持一致，但本次前端只在需求指定的列表、导出和编辑抽屉展示。

### 3.3 后端测试调整

修改：

- `adpulse-main/src/test/java/com/adpulse/main/adaccountasset/AdAccountAssetServiceTest.java`
- 如响应 record 构造器受影响，同步调整 `adpulse-main/src/test/java/com/adpulse/main/channel/service/ChannelServiceTest.java`

覆盖：

- 从 Mongo 数值正确映射 `accountDailyLimit`；
- `account_dsl` 缺失时返回空值；
- 现有 Mongo 名称、平台状态优先级不变；
- 既有测试构造器参数保持可编译。

## 4. 前端实施

仓库：`D:\progress\ai-ad-platform-vben`，应用：`plat`。

### 4.1 API 类型与只读边界

修改：

- `plat/src/api/main/ad-account-assets.ts`

在 `AdAccountAsset` 增加 `accountDailyLimit?: number | null`。在单条账户更新请求组装时显式剔除该字段，保证即使编辑表单持有该值，也不会提交到后端。

### 4.2 广告户列表

修改：

- `plat/src/views/media-resources/components/AdAccountAssetTable.vue`

新增“账户日限额”列，放在“平台状态”之后：

- 数值右对齐；
- 使用千分位，最多保留 2 位小数；
- 空值显示 `—`；
- 同步加入表格框选复制映射；
- 增加表格横向滚动宽度，避免新增列挤压现有内容。

本列只加入资产管理广告户表格，不修改共享列定义，避免无意改变渠道详情页的列结构。

### 4.3 Excel 导出

修改同一表格组件的导出列与行映射：

- 新增“账户日限额”列；
- 导出原始数值，保留 Excel 排序、求和能力；
- 空值保持为空，不导出占位符字符串；
- 继续复用当前筛选、分页拉取和“导出所选”逻辑。

### 4.4 编辑抽屉

在“编辑广告账户”抽屉中增加“账户日限额”字段：

- 放在账户 ID、账户名称等基础信息附近；
- 使用禁用输入框展示，与现有只读账户名称视觉一致；
- 文案明确该值由 Facebook 账户数据同步，不允许修改；
- 不进入保存请求、批量编辑字段或导入模板。

## 5. 旧“是否限额”字段清理

- 前端删除 `isLimited` 类型、筛选、列表、编辑、批量修改、导入导出以及共享广告户视图；
- Java `adpulse-main` 删除对应的 API 契约、业务模型、Mapper 和飞书同步读取逻辑；
- 新增迁移删除 MySQL `ad_account_asset.is_limited`，保留已经执行的历史迁移文件；
- 不修改 MongoDB、Python `schedulers` 或 Python `backend`；
- `accountDailyLimit` 继续保持只读，不增加筛选、排序、批量修改或导入能力；
- 不启动或重启本地前后端服务，不执行生产发布。

## 6. 验证计划

按当前仓库约定只执行与改动范围匹配的静态检查：

### 前端

```powershell
pnpm exec prettier --check plat/src/api/main/ad-account-assets.ts plat/src/views/media-resources/components/AdAccountAssetTable.vue
pnpm exec eslint plat/src/api/main/ad-account-assets.ts plat/src/views/media-resources/components/AdAccountAssetTable.vue
pnpm --filter @vben/plat typecheck
git diff --check
```

### 后端

```powershell
mvn -pl adpulse-main spotless:check
mvn -pl adpulse-main -am test-compile -DskipTests
git diff --check
```

不默认运行单元测试、全量构建、浏览器交互或视觉回归；如实施阶段明确要求，再补充定向测试或页面验证。

## 7. 验收标准

- Mongo 有 `account_dsl` 时，列表、导出和编辑抽屉展示同一数值；
- Mongo 字段为空或账户快照不存在时，列表和抽屉显示 `—`，导出单元格为空；
- 编辑抽屉无法修改账户日限额，保存请求不包含该字段；
- 除废弃的“是否限额”外，原有账户编辑、分配、批量修改、筛选、导入和导出行为不变；
- MySQL 迁移删除旧字段，MongoDB 和 Python 服务无修改，且无凭据或 Mongo 原始文档写入日志；
- 目标文件通过格式、类型、编译和 `git diff --check` 静态检查。

## 8. 风险与处理

- **Mongo 数值类型不一致**：后端集中兼容常见数值表示，并以 `BigDecimal` 输出。
- **空值被误认为 0**：缺失值保持 `null`，不使用 0 兜底。
- **只读字段误提交**：前端请求组装显式剔除，后端请求模型不新增对应字段。
- **共享页面遗留旧字段**：同步清理公共列工厂、渠道详情和“我的资产”的 `isLimited` 映射。
