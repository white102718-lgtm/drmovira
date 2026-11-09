# MongoDB 表结构文档

## 数据库概览

| 数据库 | 说明 |
|--------|------|
| `plat` | 主业务数据库 |
| `user` | 用户与权限数据库 |
| `trash` | 软删除回收站（各集合均有对应副本） |

---

## plat 数据库

### 广告平台账户

| 集合 | 文件 | 说明 |
|------|------|------|
| `accounts` | [accounts.md](./accounts.md) | 广告平台开发者配置（Facebook/Google） |
| `personal_accounts` | [personal_accounts.md](./personal_accounts.md) | Facebook 个人账户（绑定个号） |
| `fb_ad_accounts` | [fb_ad_accounts.md](./fb_ad_accounts.md) | Facebook 广告账户（同步自 FB） |
| `fb_businesses` | [fb_businesses.md](./fb_businesses.md) | Facebook Business Manager |
| `fb_pages` | [fb_pages.md](./fb_pages.md) | Facebook 主页 |
| `fb_pixels` | [fb_pixels.md](./fb_pixels.md) | Facebook 追踪像素 |

### 广告投放配置

| 集合 | 文件 | 说明 |
|------|------|------|
| `platform_config` | [platform_config.md](./platform_config.md) | 游戏平台配置 |
| `agent_line_config` | [agent_line_config.md](./agent_line_config.md) | 代理线配置 |
| `agent_line_kpi_config` | [agent_line_kpi_config.md](./agent_line_kpi_config.md) | 代理线 KPI 配置 |
| `ad_create_templates` | [ad_create_templates.md](./ad_create_templates.md) | 广告创建配置模板 |
| `ad_operations` | [ad_operations.md](./ad_operations.md) | 广告操作记录 |
| `ad_sync_history` | [ad_sync_history.md](./ad_sync_history.md) | 广告数据同步历史 |

### 素材管理

| 集合 | 文件 | 说明 |
|------|------|------|
| `materials` | [materials.md](./materials.md) | 广告素材文件 |
| `material_commons` | [material_commons.md](./material_commons.md) | 公共素材库（独立集合 + 独立桶） |
| `material_folders` | [material_folders.md](./material_folders.md) | 素材个人文件夹（最多三级） |
| `material_folder_links` | [material_folder_links.md](./material_folder_links.md) | 素材↔个人文件夹归属（多对多） |
| `material_folder_shares` | [material_folder_shares.md](./material_folder_shares.md) | 个人文件夹分享（只读授权） |
| `ad_creatives` | [ad_creatives.md](./ad_creatives.md) | 已审核广告创意素材 |
| `material_groups` | [material_groups.md](./material_groups.md) | 素材组 |
| `material_group_histories` | [material_group_histories.md](./material_group_histories.md) | 素材组应用历史 |
| `material_category` | [material_category.md](./material_category.md) | 素材分类树 |
| `material_templates` | — | 素材模板（标题/正文） |
| `creative_materials` | [creative_materials.md](./creative_materials.md) | 创意生成视频素材 |
| `creative_materials_img` | [creative_materials.md](./creative_materials.md) | 创意生成图片素材 |
| `creative_tasks` | [creative_tasks.md](./creative_tasks.md) | AI 创意视频生成任务 |
| `creative_tasks_img` | [creative_tasks.md](./creative_tasks.md) | AI 创意图片生成任务 |
| `creative_run_tasks_img` | [creative_tasks.md](./creative_tasks.md) | 创意运行图片任务 |

### 标签系统

| 集合 | 文件 | 说明 |
|------|------|------|
| `tag_configs` | [tag_configs.md](./tag_configs.md) | 标签系统配置 |
| `fact_tags` | [tag_configs.md](./tag_configs.md) | 事实类标签 |
| `inference_tags` | [tag_configs.md](./tag_configs.md) | 推理类标签 |
| `tree_tags` | — | 树形分类标签 |

### 其他业务

| 集合 | 文件 | 说明 |
|------|------|------|
| `tasks` | [tasks.md](./tasks.md) | 系统任务管理 |
| `department_config` | [department_config.md](./department_config.md) | 部门组织结构 |
| `telegram_config` | [telegram_config.md](./telegram_config.md) | Telegram 通知配置 |

---

## user 数据库

| 集合 | 文件 | 说明 |
|------|------|------|
| `user` | [user.md](./user.md) | 系统用户账号 |
| `role` | [role.md](./role.md) | 角色与权限 |
| `menu` | [menu.md](./menu.md) | 菜单树结构 |

---

## trash 数据库

软删除回收站，包含以下集合的副本，均额外携带 `delete_time`、`deleted_by` 字段：

`accounts` / `ad_create_templates` / `material_templates` / `department_config` /
`platform_config` / `material_category` / `agent_line_config` / `agent_line_kpi_config` /
`tag_configs` / `telegram_config`

`materials` 是例外：素材是硬删（MinIO 对象一并删掉），副本只作删除留痕、**不可还原**，
字段为 `deleted_at` / `deleted_by` / `deleted_by_real_name` / `deleted_department` / `source`，
见 [materials.md](./materials.md#删除留痕trashmaterials)。

---

## 设计约定

- **时间字段**：统一使用 CST（UTC+8）
- **status 字段**：`plat` 库中整型（`1`/`0`），`personal_accounts` 中为 Boolean（`True`/`False`）
- **软删除**：数据移入 `trash` 库，不物理删除
- **敏感字段**：`app_secret`、`access_token`、`hashed_password`、`bot_token`、`service_account_json` 等不在 API 响应中返回
