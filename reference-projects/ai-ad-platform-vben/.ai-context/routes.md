# AdPulse 路由与页面索引

> 数据来源：2026-09-29 当前环境 `/menus/` 动态菜单响应。
> 页面文件核对范围：`plat/src/views/**/*.vue`。
> 路由最终行为还会经过 `plat/src/router/access.ts` 的迁移、补充和下线处理；本文已单独列出这些差异。

## 1. 使用方法

用户用中文名称描述页面时，按以下顺序定位：

1. 先在本文搜索完整中文标题或标题中的关键词；
2. 使用“页面文件”直接定位 Vue 页面；
3. 同名页面或共用组件通过“访问路径”区分；
4. 标记为“重定向”“前端移除”或“运行时补充”的项目，以 `plat/src/router/access.ts` 为准；
5. 如果当前环境菜单再次调整，应重新获取 `/menus/` 响应并更新本文，不能只凭本文推断最新权限菜单。

组件字符串按以下规则映射：

```text
/dashboard/ad-manager
→ plat/src/views/dashboard/ad-manager.vue
```

`BasicLayout` 和 `IFrameView` 是布局组件，不对应业务页面文件。

## 2. 顶级菜单与目录

| 中文名称 | 访问路径 | 类型 |
| --- | --- | --- |
| 首页 | `/home` | 页面 |
| Mpower AI | `/home/ai-chat` | 页面 |
| 业务中心 | `/business-center` | 目录 |
| 工作台 | `/workbench` | 目录 |
| 素材中心 | `/material-center` | 目录 |
| 投放中心 | `/delivery-center` | 目录 |
| 数据复盘 | `/data-growth` | 目录 |
| 财务中心 | `/finance` | 目录 |
| 媒介资源中心 | `/media-resources` | 目录 |
| 平台技术配置 | `/platform-configuration` | 目录 |
| 系统管理 | `/system-management` | 目录 |
| 个人信息 | `/profile` | 隐藏页面 |
| 需求建议反馈 | `/feedback` | 页面 |

## 3. 中文页面名索引

### 独立页面

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| 首页 | `/home` | `plat/src/views/home/index.vue` | 菜单可见 |
| Mpower AI | `/home/ai-chat` | `plat/src/views/home/ai-chat.vue` | 菜单可见 |
| 个人信息 | `/profile` | `plat/src/views/profile/index.vue` | 隐藏 |
| 需求建议反馈 | `/feedback` | `plat/src/views/feedback/index.vue` | 菜单可见 |

### 业务中心

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| 项目管理 | `/fusion/projects` | `plat/src/views/fusion/projects/index.vue` | 菜单可见 |
| 产品与创意知识库 | `/fusion/product-knowledge` | `plat/src/views/fusion/product-knowledge/index.vue` | 隐藏，归属项目管理 |

### 工作台

| 中文名称 | 访问路径 | 页面文件 | 可见性 / 说明 |
| --- | --- | --- | --- |
| 任务中心 | `/workbench/tasks` | `plat/src/views/workbench/tasks.vue` | 菜单可见 |
| 素材任务池 | `/requirement/pool` | `plat/src/views/requirement/pool.vue` | 隐藏，归属任务中心 |
| 我的素材任务 | `/requirement/myTask` | `plat/src/views/requirement/myTask.vue` | 隐藏，归属任务中心 |
| 投手需求工作台 | `/requirement/pitcher` | `plat/src/views/workbench/tasks.vue` | 旧地址；运行时重定向到任务中心 |
| 新建素材任务 | `/workbench/tasks/create-material` | `plat/src/views/requirement/create.vue` | 隐藏，归属任务中心 |
| 新建投放任务 | `/workbench/tasks/create-delivery` | `plat/src/views/workbench/delivery-task-create.vue` | 隐藏，归属任务中心 |
| 全局任务中心 | `/fusion/ai-tasks` | `plat/src/views/fusion/ai-tasks/index.vue` | 隐藏，归属任务中心 |
| 任务详情 / 素材任务详情 | `/requirement/detail` | `plat/src/views/workbench/tasks.vue` | 旧地址；运行时携带任务 ID 重定向到任务中心 |
| 新建需求 | `/requirement/create` | `plat/src/views/requirement/create.vue` | 隐藏，归属任务中心 |
| 日报 | `/workbench/daily-reports` | `plat/src/views/workbench/daily-reports.vue` | 菜单可见 |
| 投放日报申请 | `/workbench/delivery-daily-report` | `plat/src/views/workbench/daily-report-application.vue` | 隐藏，归属日报 |
| 日报填写 | `/workbench/daily-report-application` | `plat/src/views/workbench/daily-report-application.vue` | 隐藏，旧入口 |
| 素材师月报 | `/workbench/material-designer-monthly-report` | `plat/src/views/workbench/material-designer-monthly-report.vue` | 隐藏，归属日报 |
| 斗篷管理 | `/workbench/cloaks` | `plat/src/views/workbench/cloak-management/index.vue` | 菜单可见（以后端角色授权结果为准） |
| 资源申请 | `/workbench/applications` | `plat/src/views/workbench/applications.vue` | 菜单可见 |
| 审批中心 | `/workbench/approvals` | `plat/src/views/workbench/approvals.vue` | 菜单可见 |
| 我的资产 | `/media-assets/my-assets` | `plat/src/views/workbench/my-assets.vue` | 菜单可见 |

### 素材中心

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| AI创意画布 | `/creative/canvas` | `plat/src/views/creative/canvas/index.vue` | 菜单可见 |
| AI创意工作台 | `/fusion/ai-studio` | `plat/src/views/fusion/capability-workbench/index.vue` | 隐藏，归属 AI创意画布 |
| 历史、模板与存储 | `/fusion/adgen-library` | `plat/src/views/fusion/adgen-library/index.vue` | 隐藏，归属 AI创意画布 |
| AI创意画布编辑器 | `/creative/canvas/:id` | `plat/src/views/creative/canvas/editor.vue` | 隐藏，归属 AI创意画布 |
| 素材库 | `/materials/material-library` | `plat/src/views/materials/material-library.vue` | 菜单可见 |

### 投放中心

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| 多平台广告发布 | `/fusion/ads/create` | `plat/src/views/fusion/ads/create/index.vue` | 菜单可见 |
| AdPulse高级创建 | `/createAdvertisement` | `plat/src/views/createAdvertisement/index.vue` | 菜单可见 |
| 自动化规则 | `/AutomatedRules` | `plat/src/views/createAdvertisement/AutomatedRuleLibrary.vue` | 菜单可见 |
| 规则配置 | `/createAdvertisement/automated-rule-config` | `plat/src/views/createAdvertisement/AutomatedRuleConfig.vue` | 隐藏，归属自动化规则 |
| 投放预警 | `/delivery/alert-rules` | `plat/src/views/createAdvertisement/AlertRule.vue` | 菜单可见 |
| 广告配置 | `/delivery/ad-config` | `plat/src/views/management/ad-config/index.vue` | 菜单可见 |

### 数据复盘

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| 复盘与实验 | `/fusion/review-experiments` | `plat/src/views/fusion/review-experiments/index.vue` | 隐藏 |
| 我的看板 | `/data-growth/my-dashboard` | `plat/src/views/data-growth/my-dashboard.vue` | 菜单可见 |
| 经营与投放报表 | `/data-report` | `plat/src/views/dataReport/Index.vue` | 菜单可见 |
| 下钻分析 | `/data-report/drilldown` | `plat/src/views/dataReport/Drilldown.vue` | 隐藏，归属经营与投放报表 |
| 项目运营面板 | `/dashboard/project-daily-report` | `plat/src/views/dashboard/project-daily-report.vue` | 菜单可见 |
| 项目环比分析 | `/analytics/project-comparison` | `plat/src/views/analytics/project-comparison/index.vue` | 菜单可见 |
| 人员数据 | `/dashboard/personnel-data` | `plat/src/views/dashboard/personnel-data.vue` | 菜单可见 |
| 广告面板 | `/dashboard/ad-manager` | `plat/src/views/dashboard/ad-manager.vue` | 菜单可见 |
| 素材效果与看板 | `/materials/material-insights` | `plat/src/views/materials/material-insights.vue` | 菜单可见 |

### 财务中心

财务中心的四个入口共用同一个页面组件，由路由路径区分当前业务页签或状态。

| 中文名称 | 访问路径 | 页面文件 | 可见性 |
| --- | --- | --- | --- |
| 服务费管理 | `/finance/service-fees` | `plat/src/views/finance/overview.vue` | 菜单可见 |
| 成本管理 | `/finance/costs` | `plat/src/views/finance/overview.vue` | 菜单可见 |
| 项目利润 | `/finance/project-profit` | `plat/src/views/finance/overview.vue` | 菜单可见 |
| 对账 | `/finance/reconciliation` | `plat/src/views/finance/overview.vue` | 菜单可见 |

### 媒介资源中心

| 中文名称 | 访问路径 | 页面文件 | 可见性 / 说明 |
| --- | --- | --- | --- |
| 资产管理 | `/media-resources/accounts` | `plat/src/views/media-resources/accounts.vue` | 菜单可见 |
| 渠道管理 | `/media-resources/channels` | `plat/src/views/media-resources/channels.vue` | 菜单可见 |
| 资源回收 | `/media-resources/returns` | `plat/src/views/media-resources/returns.vue` | 菜单可见 |
| 操作记录 | `/media-resources/audit` | `plat/src/views/media-resources/audit.vue` | 菜单可见 |
| 审批配置 | `/media-resources/approval-config` | `plat/src/views/media-resources/approval-config.vue` | 运行时迁移到系统管理的新路径 |
| 预警通知 | `/media-resources/alert-notifications` | `plat/src/views/media-resources/alert-notifications/index.vue` | 菜单可见 |

### 平台技术配置

| 中文名称 | 访问路径 | 页面文件 | 可见性 / 说明 |
| --- | --- | --- | --- |
| 开发者与授权 | `/management/developers` | `plat/src/views/management/developers/index.vue` | 菜单可见；默认 `tab=facebook` |
| 平台资源同步 | `/management/platform-resources` | `plat/src/views/management/fb-resource/index.vue` | 菜单可见；默认 `tab=personal` |
| 平台与代理线 | `/management/platform-config` | `plat/src/views/management/platform-config/index.vue` | 接口仍返回，但运行时前端移除 |
| 同步任务 | `/management/tasks` | `plat/src/views/management/tasks/index.vue` | 菜单可见 |

### 系统管理

| 中文名称 | 访问路径 | 页面文件 | 可见性 / 说明 |
| --- | --- | --- | --- |
| 用户管理 | `/system-management/users` | `plat/src/views/system/user/list.vue` | 菜单可见 |
| 部门管理 | `/system-management/departments` | `plat/src/views/system/department/list.vue` | 菜单可见 |
| 角色权限 | `/system-management/roles` | `plat/src/views/system/role/list.vue` | 菜单可见 |
| 申请管理 | `/system-management/applications` | `plat/src/views/system/application/list.vue` | 菜单可见 |
| 菜单管理 | `/system-management/menus` | `plat/src/views/system/menu/list.vue` | 菜单可见 |
| Google数据集成 | `/system-management/data-integration` | `plat/src/views/media-resources/data-integration.vue` | 菜单可见 |
| 组织架构同步 | `/system-management/feishu-data-integration/organization-sync` | `plat/src/views/system/feishu-organization-sync.vue` | 菜单可见，归属飞书数据集成 |
| 文档同步 | `/system-management/feishu-data-integration/document-sync` | `plat/src/views/media-resources/account-feishu-sync.vue` | 菜单可见，归属飞书数据集成 |
| AdGen模型与运维 | `/fusion/adgen-operations` | `plat/src/views/fusion/operations-center/index.vue` | 菜单可见 |
| 字典管理 | `/system/dictionary` | `plat/src/views/system/dictionary/list.vue` | 菜单可见 |
| 登录日志 | `/system-management/logs/login` | `plat/src/views/system/log-management/login.vue` | 菜单可见 |
| 需求反馈搜集 | `/system-management/feedback-collection` | `plat/src/views/feedback/list.vue` | 菜单可见 |
| 操作日志 | `/system-management/logs/operation` | `plat/src/views/system/log-management/operation.vue` | 菜单可见 |
| 日报配置 | `/system-management/daily-report-config` | `plat/src/views/system/daily-report-config.vue` | 菜单可见 |
| 手动任务 | `/system/manual-tasks` | `plat/src/views/system/manual-tasks.vue` | 菜单可见 |

## 4. 前端运行时补充与迁移路由

以下路由不能只从 `/menus/` 原始响应判断，`plat/src/router/access.ts` 会在注册前动态处理。

| 中文名称 | 最终访问路径 | 页面文件 / 行为 | 来源 |
| --- | --- | --- | --- |
| 投手需求工作台 | `/requirement/pitcher` | 重定向 `/workbench/tasks` | 旧入口迁移 |
| 素材任务详情 | `/requirement/detail` | 将旧 `id` 转为 `materialOrderId` 后重定向 `/workbench/tasks` | 旧入口迁移 |
| 审批办理 | `/workbench/approvals/:id` | `plat/src/views/workbench/approval-handle.vue` | 前端补充 |
| 填写资源申请 | `/workbench/applications/create` | `plat/src/views/workbench/applications-create.vue` | 前端补充 |
| 批量创建斗篷 | `/workbench/cloaks/batch-create` | `plat/src/views/workbench/cloak-management/batch-create.vue` | 前端补充的隐藏页 |
| 数据同步记录 | `/management/developers/sync-history` | `plat/src/views/management/developers/sync-history.vue` | 前端补充 |
| 审批配置 | `/system-management/approval-config` | `plat/src/views/media-resources/approval-config.vue` | 从媒介资源中心迁移到系统管理 |
| 集成数据 | `/system-management/data-integration/:id/data` | `plat/src/views/media-resources/data-integration-data.vue` | 前端补充 |
| 角色成员 | `/system-management/roles/:roleId/members` | `plat/src/views/system/role/members.vue` | 前端补充 |
| 添加渠道 | `/media-resources/channels/create` | `plat/src/views/media-resources/channel-management/ChannelEditor.vue` | 前端补充 |
| 编辑渠道 | `/media-resources/channels/:id/edit` | `plat/src/views/media-resources/channel-management/ChannelEditor.vue` | 前端补充 |
| 渠道详情 | `/media-resources/channels/:id` | `plat/src/views/media-resources/channel-management/ChannelDetail.vue` | 前端补充 |
| AI创意画布编辑器 | `/creative/canvas/:id` | `plat/src/views/creative/canvas/editor.vue` | 前端强制注册为根级隐藏页 |
| 登录日志（兼容入口） | `/system/login-log` | `plat/src/views/system/login-log/list.vue` | 非演示环境按权限补充 |
| 操作日志（兼容入口） | `/system/operation-log` | `plat/src/views/system/operation-log/list.vue` | 非演示环境按权限补充 |

运行时还会执行以下下线或兼容处理：

- 移除 `/management/platform-config`（平台与代理线）；
- 移除旧媒介资源看板和分配页；
- 将旧审批配置入口迁移至 `/system-management/approval-config`，旧地址仅作为隐藏兼容入口；
- 保留旧飞书文档同步地址作为隐藏兼容入口；
- 当后端未返回个人信息、规则配置、下钻分析、新建需求等必要隐藏页时，由前端补充。

## 5. 维护规则

- 本文是定位辅助索引，不替代后端菜单权限和 `plat/src/router/access.ts` 的真实行为。
- 更新菜单数据时，应同时核对中文标题、访问路径、组件字符串、隐藏状态和页面文件是否存在。
- 组件字符串存在但页面文件不存在时，先检查 `access.ts` 是否将其改写为重定向或下线入口，不要直接创建同名空页面。
- 新增或迁移页面后，同步更新本索引；若同一个组件服务多个访问路径，必须逐项列出并说明区分方式。
