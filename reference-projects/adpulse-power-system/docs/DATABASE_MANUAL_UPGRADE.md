# 数据库手工升级说明

应用不会自动执行数据库结构变更。每次部署新版应用前，数据库管理员必须按版本号审核并手工执行尚未执行的 SQL 脚本。

## V4：删除旧版 MFA 开关

当前认证逻辑只使用 `mfa_status`：

- `-1`：不要求 MFA，密码验证通过后直接登录。
- `0`：要求 MFA，用户尚未绑定。
- `1`：已绑定 MFA，登录时验证动态码。

旧字段 `mfa_enabled` 已不被 Java、Mapper 或接口使用。执行 V3 后，旧字段的数据已经转换到 `mfa_status`，因此可以删除。

### 执行前检查

```sql
SHOW COLUMNS FROM sys_user LIKE 'mfa_status';

SELECT mfa_status, COUNT(*) AS user_count
FROM sys_user
GROUP BY mfa_status
ORDER BY mfa_status;
```

第一条查询必须返回 `mfa_status` 字段，第二条查询中的状态只能是 `-1`、`0`、`1`。建议执行前备份 `sys_user` 表。

### 执行升级

在项目目录执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V4__drop_legacy_mfa_enabled.sql
```

V4 脚本的实际内容是：

```sql
ALTER TABLE sys_user
    DROP CHECK ck_user_mfa_enabled,
    DROP COLUMN mfa_enabled;
```

该脚本只执行一次。已经完成 V1、V2、V3 的现有数据库只需要执行 V4，不要重复执行旧脚本。

### 执行后验证

```sql
SHOW COLUMNS FROM sys_user LIKE 'mfa_enabled';
SHOW COLUMNS FROM sys_user LIKE 'mfa_status';
SHOW CREATE TABLE sys_user;
```

预期结果：第一条查询返回空，第二条返回 `mfa_status`，建表语句中不再出现 `ck_user_mfa_enabled`。

执行完成并验证无误后，再启动或更新 Java 服务。由于当前后端不读取 `mfa_enabled`，删除字段不需要额外修改接口参数。

## V5：增加登录审计日志

执行以下脚本创建 `sys_login_log`、增加 `system:login-log:list` 权限并授权给有效的 `ADMIN` 角色：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V5__create_login_log.sql
```

执行后验证：

```sql
SHOW CREATE TABLE sys_login_log;

SELECT id, menu_code, permission_code
FROM sys_menu
WHERE menu_code = 'SYSTEM_LOGIN_LOG_LIST'
  AND deleted_at = 0;
```

V5 只执行一次。部署新版 Java 服务后，管理员需要重新登录，使 Redis 会话权限快照包含 `system:login-log:list`。接口字段和查询方式见 `LOGIN_LOG_API.md`。

## V6：增加操作审计日志

部署新版 Java 服务前执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V6__create_operation_log.sql
```

执行后验证：

```sql
SHOW CREATE TABLE sys_operation_log;

SELECT id, menu_code, permission_code
FROM sys_menu
WHERE menu_code = 'SYSTEM_OPERATION_LOG_LIST'
  AND deleted_at = 0;
```

V6 只执行一次。该脚本创建操作审计表、增加 `system:operation-log:list` 权限并授权给有效的 `ADMIN` 角色。执行后管理员需要重新登录。接口说明见 `OPERATION_LOG_API.md`。

## V7：增加字典配置

部署新版 Java 服务前执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V7__create_dictionary_tables.sql
```

执行后验证：

```sql
SHOW CREATE TABLE sys_dict_type;
SHOW CREATE TABLE sys_dict_item;

SELECT dict_code, dict_name, status
FROM sys_dict_type
WHERE dict_code = 'AD_MEDIA' AND deleted_at = 0;

SELECT menu_code, permission_code
FROM sys_menu
WHERE menu_code = 'SYSTEM_DICTIONARY' AND deleted_at = 0;
```

V7 只执行一次。脚本创建字典类型和字典项表，初始化投放媒体示例字典，增加字典管理菜单并授权给有效的 `ADMIN` 角色。执行后管理员需要重新登录，使 Redis 会话权限快照包含 `system:dictionary:list`。接口说明见 `DICTIONARY_API.md`。

## V7：增加资产申请审批流程

部署包含资产管理功能的新版服务前执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V7__create_asset_approval_flow.sql
```

执行后验证：

```sql
SHOW CREATE TABLE media_asset;
SHOW CREATE TABLE media_approval_config;
SHOW CREATE TABLE media_asset_application;
SHOW CREATE TABLE media_asset_approval_log;
```

V7 只执行一次。脚本建立个号、BM、像素、TG 的统一库存、审批配置、申请单和审批轨迹。应用不会自动执行迁移；未手工执行该脚本时 `/asset-flow/**` 接口不可用。

## V8：增加项目管理与代理线

部署主业务服务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V8__create_project_management_tables.sql
```

执行后验证：

```sql
SHOW CREATE TABLE pm_project;
SHOW CREATE TABLE pm_agency_line;
SHOW CREATE TABLE pm_project_platform;
SHOW CREATE TABLE pm_project_region;
SHOW CREATE TABLE pm_project_kpi;

SELECT item_value, item_label
FROM sys_dict_item
WHERE dict_type_id = (
    SELECT id FROM sys_dict_type
    WHERE dict_code = 'PROJECT_REGION' AND deleted_at = 0
)
AND deleted_at = 0
ORDER BY sort_order;
```

V8 只执行一次。脚本不创建数据库外键；项目、用户、字典和代理线引用均由事务服务校验。启动 `adpulse-main-server` 后，项目管理接口位于 `/api/main/fusion/**`。

## V9：增加渠道管理

部署主业务服务前，审核并手工执行表结构脚本：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V9__create_channel_management_tables.sql
```

需要在测试环境初始化联调数据时，再执行演示数据脚本：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/seed/channel_management_demo_data.sql
```

执行后验证：

```sql
SHOW CREATE TABLE media_channel;
SHOW CREATE TABLE media_channel_rate;
SHOW CREATE TABLE media_channel_account_type;
SHOW CREATE TABLE media_channel_account;
SHOW CREATE TABLE media_channel_goods;
SHOW CREATE TABLE media_channel_campaign_spend;

SELECT COUNT(*) FROM media_channel WHERE deleted_at = 0;
SELECT COUNT(*) FROM media_channel_account WHERE deleted_at = 0;
```

V9 只执行一次，不创建数据库外键。演示数据脚本使用 `990xxxx`、`7900xxxx` 等固定测试 ID，可重复执行。启动 `adpulse-main-server` 后，渠道管理接口位于 `/api/main/channels/**`、`/api/main/channel-accounts/**`。

演示数据脚本仅允许在隔离测试环境执行，不得用于共享测试、预发布或生产环境。若历史环境已误执行，部署前审核并手工执行 V18，将四条固定联调渠道停用，避免它们进入“系统渠道”下拉：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V18__disable_channel_management_demo_channels.sql
```

执行后验证：

```sql
SELECT id, channel_name, channel_code, status
FROM media_channel
WHERE id IN (9900101, 9900102, 9900103, 9900104)
ORDER BY id;
```

四条记录的 `status` 应为 `0`；用户在渠道管理中创建的正常渠道不受影响。

## V19：增加 Google Sheets 同步结果表

部署包含 Google 同步 worker 的主业务服务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V19__create_google_sync_data.sql
```

执行后验证：

```sql
SHOW CREATE TABLE google_sync_data;

SELECT status, COUNT(*)
FROM external_sync_job
WHERE provider = 'google' AND deleted_at = 0
GROUP BY status;
```

V19 只执行一次。读取方向的 Google Sheets 映射会按映射、日期、项目名称和任务线名称幂等写入该表；首次、编辑和手动同步为全量同步，自动任务按映射日期范围同步。

## V20：限制未删除项目名称唯一

部署项目名称唯一性校验前，先确认存量未删除项目没有重名，再审核并手工执行：

```sql
SELECT project_name, COUNT(*) AS duplicate_count
FROM pm_project
WHERE deleted_at = 0
GROUP BY project_name
HAVING COUNT(*) > 1;
```

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V20__add_active_project_name_unique_key.sql
```

该索引包含 `deleted_at`：未删除项目名称必须唯一，软删除后可重新使用原名称。

## V22：增加项目类型和产品链接

部署新项目表单前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V22__add_project_type_and_product_links.sql
```

V22 为项目增加 `project_type`，并创建可保存多个链接的 `pm_project_product_link` 子表；不创建数据库外键。

## V23：增加项目外包团队

部署“有外包”项目可多选外包团队功能前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V23__create_project_outsourcing_team.sql
```

V23 创建 `pm_project_outsourcing_team` 子表，用于保存项目选择的多个外包团队；不创建数据库外键。

## V24：升级项目投放地区与国家数据

部署项目“投放地区 / 国家”级联选择前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V24__upgrade_project_region_country.sql
```

V24 创建统一的地区国家主数据，并将 `pm_project_region` 扩展为地区编码、地区名称、国家编码和国家名称四列。现有 `US`、`JP`、`GB`、`DE`、`SG` 等国家代码会自动回填中文名称和所属地区；无法识别的历史值会保留并归入“未分类”，避免丢失项目数据。该脚本不创建数据库外键。

执行后验证：

```sql
SELECT region_code, region_name, country_code, country_name
FROM pm_project_region
WHERE deleted_at = 0
ORDER BY project_id, id;

SELECT region_code, COUNT(*) AS country_count
FROM pm_region_country
WHERE status = 1 AND deleted_at = 0
GROUP BY region_code
ORDER BY region_code;
```

## V25：增加代理线主页 ID

部署支持代理线主页 ID 的主业务服务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V25__add_agency_line_page_id.sql
```

V25 为 `pm_agency_line` 增加可选的 `page_id` 字段，用于保存广告平台主页 ID。

执行后验证：

```sql
SHOW COLUMNS FROM pm_agency_line LIKE 'page_id';
```

## V26：代理线像素改为选填

部署支持代理线像素留空的主业务服务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V26__make_agency_line_pixel_optional.sql
```

V26 将 `pm_agency_line.pixel_name` 调整为可空字段，已有像素数据不受影响。

执行后验证：

```sql
SHOW COLUMNS FROM pm_agency_line LIKE 'pixel_name';
```

## V27：扩展项目 KPI 判断方式

部署项目 KPI 完整比较规则前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V27__extend_project_kpi_comparators.sql
```

V27 为项目 KPI 增加区间上限字段，并支持大于、小于、等于、大于等于、
小于等于和闭区间判断。已有 KPI 数据保持不变。

执行后验证：

```sql
SHOW CREATE TABLE pm_project_kpi;
SELECT metric_value, comparator, target_value, target_max_value
FROM pm_project_kpi
WHERE deleted_at = 0
ORDER BY project_id, sort_order;
```

## V28：接入项目Safeheron钱包

部署项目钱包创建功能前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V28__enable_project_safeheron_wallets.sql
```

V28 为Safeheron团队补充数据库凭证字段，为钱包增加项目业务幂等引用，
并以AES-GCM密文保存ETH与USDT-TRC20的首个收款地址。不要把明文私钥或地址写入脚本、日志或版本库。
默认团队 `team_id = '1'` 必须启用并配置完整凭证。测试环境设置
`SAFEHERON_TEST_MASTER_KEY`，生产环境设置 `SAFEHERON_PROD_MASTER_KEY`，两者均为
Base64编码的32字节密钥且不得混用。设置与对应旧环境相同的主密钥后，可以直接迁移
旧系统的 `ak`、`pvk`、`spk`、`base_url` 和 `request_timeout`；其中 `pvk`
对应 `private_key_ciphertext`。

执行后验证：

```sql
SHOW COLUMNS FROM safeheron_team;
SHOW CREATE TABLE safeheron_wallet;
SHOW COLUMNS FROM safeheron_wallet_coin;
SELECT team_id, team_name, base_url, request_timeout, status,
       api_key IS NOT NULL AS has_api_key,
       private_key_ciphertext IS NOT NULL AS has_private_key,
       safeheron_public_key IS NOT NULL AS has_platform_public_key
FROM safeheron_team
WHERE deleted_at = 0;
```

## V29：创建广告账户属性配置

部署广告账户台账的属性配置功能前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V29__create_ad_account_attribute_table.sql
```

V29 创建 `ad_account_attribute` 配置表，用于维护广告账户的可选属性名称与编码。

执行后验证：

```sql
SHOW CREATE TABLE ad_account_attribute;
```

## V40：创建广告账户资产信息主表

部署广告账户资产信息主表读写逻辑前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V40__create_ad_account_asset_table.sql
```

V40 创建初始版本的 `ad_account_asset`。部署 Main V41 后，账户清单改为 MongoDB
`fb_ad_accounts` 与本表的并集，飞书记录也由定时任务写入本表，不再作为列表实时回退来源。
本表不建立数据库外键，`account_id` 与 `fb_ad_accounts._id` 保持逻辑关联。

执行后验证：

```sql
SHOW CREATE TABLE ad_account_asset;

SELECT update_source, COUNT(*) AS account_count
FROM ad_account_asset
WHERE deleted_at = 0
GROUP BY update_source;
```

## Main V41：统一广告账户资产和使用人关系

部署广告账户并集查询、飞书小时同步、渠道导入和新使用人关系前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V41__unify_ad_account_asset_ledger.sql
```

V41 扩展 `ad_account_asset`，以 `(account_id, account_name)` 作为有效账户业务唯一键，
新增平台状态、渠道归属、人工锁定和来源同步时间；同时创建
`ad_account_asset_assignment` 保存广告账户与使用人的多对多关系。脚本会从
`media_channel_account` 和 `media_channel_account_assignment` 回填历史数据，但不会删除旧表，
旧表中的财务字段继续供灰度期及 Doris 查询使用。

执行后验证：

```sql
SHOW CREATE TABLE ad_account_asset;
SHOW CREATE TABLE ad_account_asset_assignment;

SELECT account_id, account_name, COUNT(*) AS duplicate_count
FROM ad_account_asset
WHERE deleted_at = 0
GROUP BY account_id, account_name
HAVING COUNT(*) > 1;

SELECT COUNT(*) AS active_assignment_count
FROM ad_account_asset_assignment
WHERE assignment_status = 'ACTIVE' AND deleted_at = 0;
```

## Main V42：恢复广告账户库存状态

部署库存状态展示、编辑和申请办理联动前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V42__restore_ad_account_inventory_status.sql
```

V42 在 `ad_account_asset` 增加 `inventory_status`，从旧 `media_asset` 回填已有状态，并以
`ad_account_asset_assignment` 的有效关系校正“已分配”状态。迁移后广告账户库存状态不再由页面实时关联旧表获得。

执行后验证：

```sql
SHOW COLUMNS FROM ad_account_asset LIKE 'inventory_status';

SELECT inventory_status, COUNT(*) AS account_count
FROM ad_account_asset
WHERE deleted_at = 0
GROUP BY inventory_status;

SELECT COUNT(*) AS inconsistent_assignment_count
FROM ad_account_asset asset
WHERE asset.deleted_at = 0
  AND asset.inventory_status != 'ASSIGNED'
  AND EXISTS (
      SELECT 1
      FROM ad_account_asset_assignment assignment
      WHERE assignment.ad_account_asset_id = asset.id
        AND assignment.assignment_status = 'ACTIVE'
        AND assignment.deleted_at = 0
  );
```

## Main V43：按账户 ID 合并广告账户资产

部署账户开户办理前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V43__deduplicate_ad_account_assets_by_account_id.sql
```

V43 将同一有效 `account_id` 的多条资产记录合并为一条：优先保留人工维护、已归属渠道、名称完整且更新时间较新的记录；使用人分配关系迁移到保留记录后删除重复资产。随后将有效账户唯一键恢复为 `(account_id, deleted_at)`，账户名称变更不再创建新的资产记录。

执行后验证：

```sql
SELECT account_id, COUNT(*) AS active_count
FROM ad_account_asset
WHERE deleted_at = 0
GROUP BY account_id
HAVING COUNT(*) > 1;

SHOW INDEX FROM ad_account_asset
WHERE Key_name = 'uk_ad_account_asset_account_deleted';

SELECT COUNT(*) AS orphaned_assignment_count
FROM ad_account_asset_assignment assignment
LEFT JOIN ad_account_asset asset ON asset.id = assignment.ad_account_asset_id
WHERE asset.id IS NULL;
```

## Main V44：飞书广告账户资料同步字典开关

部署飞书广告账户资料同步开关前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V44__seed_ad_account_asset_feishu_sync_switch.sql
```

V44 新增系统字典 `AD_ACCOUNT_ASSET_FEISHU_SYNC`，默认启用项值为 `1`，继续按小时将
`feishu_account_used_record` 的业务资料同步到 `ad_account_asset`。需要暂停时，在系统配置的字典页面
将该字典项值修改为 `0`；仅启用且未删除的 `0` 会暂停飞书资料同步，字典缺失、禁用或删除时均保持默认同步。
该开关不影响 `fb_ad_accounts` 的账户名称和平台状态同步。

执行后验证：

```sql
SELECT type.dict_code, type.status AS type_status,
       item.item_value, item.item_label, item.status AS item_status
FROM sys_dict_type type
LEFT JOIN sys_dict_item item
  ON item.dict_type_id = type.id
 AND item.deleted_at = 0
WHERE type.dict_code = 'AD_ACCOUNT_ASSET_FEISHU_SYNC'
  AND type.deleted_at = 0;
```

## V43：像素申请办理不再分配库存资产

部署该流程调整前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V43__disable_pixel_inventory_assignment.sql
```

该脚本仅更新像素申请的办理节点配置：办理人不再选择库存资产，只填写办理结果；历史申请仍由服务端兼容，不会再分配像素资产。

## Main V46：代理线补齐投放明细字段和链接历史

部署代理线字段同步与投放链接历史功能前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V46__align_agency_line_delivery_fields.sql
```

V46 为 `pm_agency_line` 增加类型、像素 ID、Token 密文、测试代码和斗篷链接，
并将投放链接长度统一为 2000。Token 只保存 AES-GCM 密文。
脚本同时创建 `pm_agency_line_delivery_url_history`，并把现有非空投放链接回填为第 1 版；
不创建数据库外键。

执行后验证：

```sql
SHOW COLUMNS FROM pm_agency_line;
SHOW CREATE TABLE pm_agency_line_delivery_url_history;

SELECT COUNT(*) AS encrypted_token_count
FROM pm_agency_line
WHERE token_ciphertext IS NOT NULL;
```

## Main V47：投放日报写入项目Google Sheet

部署投放日报Google模板和推送任务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V47__create_delivery_report_google_push.sql
```

V47 创建项目唯一模板、推送批次和推送明细三张表，不创建数据库外键。
推送明细保存目标位置与字段值快照，用于跨项目部分失败后的查询和重试；
Google访问令牌继续只保存在既有授权账号表的密文字段中。

执行后验证：

```sql
SHOW CREATE TABLE biz_delivery_report_google_template;
SHOW CREATE TABLE biz_delivery_report_google_push_batch;
SHOW CREATE TABLE biz_delivery_report_google_push_item;
```

## Main V50：增加项目代理线链接

部署支持项目代理线链接的主业务服务前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V50__add_project_agency_line_url.sql
```

V50 为 `pm_project` 增加可选的 `agency_line_url` 字段，用于保存项目级代理线链接；
链接只允许 HTTP 或 HTTPS 地址，应用创建和修改项目时使用相同校验口径。

执行后验证：

```sql
SHOW COLUMNS FROM pm_project LIKE 'agency_line_url';
```

## Main V51：增加项目代理线 Google Sheet 同步历史

部署项目代理线链接自动同步功能前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V51__create_agency_line_sheet_sync_history.sql
```

V51 创建同步批次与逐行失败明细表。批次记录项目、触发方式、Google 页签快照和成功失败数量；
失败明细只保存 Sheet 行号、可识别的代理线名称及脱敏原因，不保存 Token、服务账户凭据或整行原文。
两张表均不创建数据库外键，项目和批次引用由服务层校验。

执行后验证：

```sql
SHOW CREATE TABLE pm_agency_line_sync_batch;
SHOW CREATE TABLE pm_agency_line_sync_failure;
```

## Main V52-V53：项目钱包业务引用与创建方式

部署旧MPower钱包兼容逻辑前，按顺序审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V52__link_project_wallet_by_customer_reference.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V53__clarify_project_wallet_provider_switch.sql
```

V52 为项目增加 `wallet_customer_ref_id`，并回填此前按 `project_code` 直连创建的钱包。
V53 将字典 `PROJECT_CREATE_WALLET` 明确为创建方式：`0` 表示旧MPower代理创建，
`1` 表示新系统直连Safeheron。每个环境必须且只能启用一个有效值。

选择 `0` 时，还需在新系统私有配置中设置 `adpulse.mpower-wallet.base-url`、
`secret`，并保留 `asset-migration` 的 `ASSET_MIGRATION_SOURCE_URL`、用户名和密码。
该来源账号需额外具有老库 `sys_dept`、`sys_user` 的 `SELECT` 权限，不需要任何写权限。
新系统按负责团队名称精确查询旧 `sys_dept`，按人员姓名精确查询旧 `sys_user`；
地区直接使用新系统国家配置中的国家名称。Redis只作为查询结果缓存，
正常命中默认缓存24小时，回退默认值的结果缓存30分钟；Redis关闭或异常时直接查老库。
旧库无唯一匹配时使用默认值：部门 `100`、地区“美国”、AM和数据专员 `1`、项目状态 `0`。
签名密钥必须与旧MPower的 `open.api.secret` 一致，不得写入仓库。

执行后验证：

```sql
SHOW COLUMNS FROM pm_project LIKE 'wallet_customer_ref_id';
SHOW INDEX FROM pm_project WHERE Key_name = 'uk_pm_project_wallet_ref_deleted';
SELECT type.dict_code, item.item_value, item.item_label, item.status
FROM sys_dict_type type
JOIN sys_dict_item item ON item.dict_type_id = type.id AND item.deleted_at = 0
WHERE type.dict_code = 'PROJECT_CREATE_WALLET' AND type.deleted_at = 0;
```

## Main V56-V58：斗篷管理、Google Sheet回写与失败重试

部署斗篷批量创建、管理和代理线表格回写功能前，按顺序审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V56__create_cloak_management_tables.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V57__add_cloak_sheet_writeback_result.sql
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-main/src/main/resources/db/migration/V58__release_failed_cloak_prefix.sql
```

V56 创建服务商批量提交幂等批次和本地斗篷明细，不创建数据库外键。
V57 在斗篷明细中增加逐条Google Sheet回写状态、结果摘要、目标行号和完成时间；
单条回写失败不会回滚已成功创建的斗篷或同批其他回写结果。
V58 保留明确失败记录用于审计，但释放其推广链接前缀；待确认、成功和结果待核对记录
仍参与唯一性约束，避免并发提交或未知远端结果产生重复斗篷。

执行后验证：

```sql
SHOW CREATE TABLE biz_cloak_batch;
SHOW CREATE TABLE biz_cloak;
SHOW COLUMNS FROM biz_cloak LIKE 'sheet_writeback_status';
SHOW COLUMNS FROM biz_cloak LIKE 'prefix_occupancy';
SHOW INDEX FROM biz_cloak WHERE Key_name = 'uk_cloak_prefix_domain_active';
```

## System V51：投放日报项目推送权限

部署投放日报项目Google日报推送权限控制前，审核并手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V51__add_delivery_report_google_push_permission.sql
```

V51 在“工作台-日报”下增加按钮权限`workbench:daily:report:push`，并默认授予管理员角色；
其他需要配置模板、查看推送记录或执行推送的角色，需在菜单管理中显式授权。

执行后验证：

```sql
SELECT menu_code, menu_name, permission_code, status
FROM sys_menu
WHERE menu_code = 'WORKBENCH_DAILY_REPORT_PUSH'
  AND deleted_at = 0;
```
