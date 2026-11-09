# 手动任务与飞书广告账户使用人同步实施文档

## 1. 背景与目标

资产管理中的广告账户使用人当前来自 `ad_account_asset_assignment`，定时读取
`feishu_account_used_record` 的任务只同步账户业务资料，不同步 `user_name`。

本次新增“手动任务”能力：

- 在“系统管理”菜单下提供可重复触发的“手动任务”页面。
- 首期接入“同步飞书广告户使用人”任务，后续可继续注册其他人工触发任务。
- 每次点击生成独立触发事件，记录触发人、触发时间、执行状态及完整长文本日志。
- 飞书使用人只作为共同使用人增量补充，不覆盖、不删除现有申请、人工、导入或历史关系。
- 相同系统用户按 `sys_user.id` 去重，重复触发保持幂等。

不在本次范围内：

- 不修改现有账户业务资料的小时定时同步。
- 不把现有组织同步、卡台同步等入口迁入新页面。
- 不根据飞书名单解除任何已有使用人。
- 不建立逐条异常明细表或逐条结构化执行结果表。

## 2. 已确认的业务规则

### 2.1 同步范围

- 每次任务全量扫描 MongoDB `feishu_account_used_record` 集合中的全部记录，不按
  `in_use` 或同步时间过滤。
- `account_id` 去除可选的 `act_` 前缀后与 `ad_account_asset.account_id` 匹配。
- 不接受前端传入账户范围，避免筛选状态造成同步范围不明确。

### 2.2 使用人解析与匹配

- 来源字段为 `user_name`，允许包含多人。
- 分隔符统一支持英文逗号、中文逗号、`/`、`、`、英文/中文分号及换行。
- 去除首尾空白并忽略空名字，同一条记录中的重复名字只处理一次。
- 仅要求 `sys_user.deleted_at = 0`；不限制 `status`，允许匹配未启用但尚未删除的系统用户。
- 先按 `real_name` 精确匹配；无结果时再按 `display_name` 精确匹配。
- 同一名字最终只对应一个用户 ID 时视为成功；对应多个不同用户 ID 时视为重名并跳过。
- 多个名字解析到同一个用户 ID 时，最终按用户 ID 去重。

禁止按模糊姓名、部门或昵称猜测用户关系。飞书源记录目前没有稳定人员 ID，因此无法唯一匹配时必须跳过。

### 2.3 关系写入

- 已存在 `(ad_account_asset_id, user_id)` 有效关系时不重复插入。
- 已有关系的 `assignment_source`、`application_id`、`is_primary` 和 `assigned_at` 均保持不变。
- 新增关系的 `assignment_source` 固定为 `FEISHU_MANUAL_SYNC`，`application_id` 为空。
- 账户没有任何有效使用人时，第一个新增人员设为主使用人；其余新增人员为共同使用人。
- 账户已有使用人时，飞书新增人员全部作为共同使用人，不改变原主使用人。
- 至少新增一名使用人后，将账户库存状态更新为 `ASSIGNED`。
- 飞书记录以后下线、姓名留空或删除人员时，不释放既有关系；解除关系继续使用现有人工流程。

### 2.4 容错规则

以下属于数据级跳过，不中断整个任务：

- 广告账户不存在。
- `user_name` 为空。
- 姓名找不到未删除的系统用户。
- 姓名对应多个未删除的系统用户。
- 账户与用户关系已经存在。

MongoDB 不可访问、MySQL 不可访问、任务框架异常等系统级错误将本次任务标记为 `FAILED`。
单个账户写入失败时记录错误并继续其他账户；任务最终仍为 `SUCCESS`，日志末尾必须包含失败账户数量。

## 3. 总体架构

```text
系统管理 / 手动任务页面
        │
        │ POST /manual-tasks/{taskCode}/executions
        ▼
adpulse-main 手动任务服务
        │
        ├─ 创建 PENDING 触发事件
        ├─ 后台 Worker 原子领取任务
        ├─ 调用任务注册表中的具体执行器
        │      └─ 飞书广告账户使用人同步执行器
        └─ 更新状态、时间与 LONGTEXT 日志

数据源：MongoDB feishu_account_used_record
业务写入：MySQL ad_account_asset_assignment / ad_account_asset
菜单权限：adpulse-system sys_menu / sys_role_menu
```

职责边界：

- `adpulse-main`：手动任务框架、执行记录、MongoDB 读取、广告账户使用人业务写入。
- `adpulse-system`：新增菜单及按钮权限数据，不复制广告账户同步逻辑。
- 前端 `plat`：任务展示、触发确认、状态轮询、历史记录和日志抽屉。

## 4. 数据库设计

### 4.1 手动任务执行表

在 `adpulse-main` 增加人工审核并执行的迁移脚本
`V47__create_manual_task_execution.sql`：

```sql
CREATE TABLE manual_task_execution (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '手动任务执行记录 ID',
    task_code VARCHAR(64) NOT NULL COMMENT '稳定任务编码，如 SYNC_FEISHU_AD_ACCOUNT_USERS',
    task_name VARCHAR(128) NOT NULL COMMENT '触发时的任务名称快照',
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING'
        COMMENT '执行状态：PENDING 待执行、RUNNING 执行中、SUCCESS 成功、FAILED 失败',
    triggered_by BIGINT UNSIGNED NOT NULL COMMENT '触发人 ID，逻辑关联 sys_user.id',
    triggered_by_name VARCHAR(100) NOT NULL COMMENT '触发人名称快照',
    triggered_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        COMMENT '管理员触发时间（UTC）',
    started_at DATETIME(3) NULL COMMENT '后台开始执行时间（UTC）',
    finished_at DATETIME(3) NULL COMMENT '执行结束时间（UTC）',
    heartbeat_at DATETIME(3) NULL COMMENT '运行中心跳时间，用于识别服务异常遗留任务（UTC）',
    log_content LONGTEXT NULL COMMENT '本次触发的完整文本日志，不得包含令牌、密钥或数据库凭据',
    active_task_code VARCHAR(64)
        GENERATED ALWAYS AS (
            CASE
                WHEN deleted_at = 0 AND status IN ('PENDING', 'RUNNING') THEN task_code
                ELSE NULL
            END
        ) STORED COMMENT '限制同一任务同时只有一个待执行或执行中实例',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间（UTC）',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最后更新时间（UTC）',
    deleted_at BIGINT UNSIGNED NOT NULL DEFAULT 0
        COMMENT '软删除时间戳；0 表示有效，非 0 表示已删除',
    PRIMARY KEY (id),
    UNIQUE KEY uk_manual_task_active (active_task_code),
    KEY idx_manual_task_code_time (task_code, triggered_at, deleted_at),
    KEY idx_manual_task_status_time (status, triggered_at, deleted_at),
    KEY idx_manual_task_triggered_by (triggered_by, triggered_at, deleted_at),
    CONSTRAINT ck_manual_task_status
        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED'))
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_0900_ai_ci
  COMMENT = '管理员手动触发任务的执行事件、状态与长文本日志';
```

不新增外键。列表查询不得返回 `log_content`，仅在查询单条执行详情时加载长文本。

### 4.2 使用人来源枚举

`ad_account_asset_assignment.assignment_source` 为字符串字段，无需修改表结构。同步新增关系使用
`FEISHU_MANUAL_SYNC`；同步修改文档和中文注释，补充该来源的含义。

### 4.3 菜单与权限脚本

在 `adpulse-system` 增加人工审核并执行的脚本
`V49__add_manual_task_menu.sql`：

- 在现有“系统管理”目录下新增菜单 `SYSTEM_MANUAL_TASK`。
- 路由：`/system/manual-tasks`。
- 组件：`/system/manual-tasks`。
- 页面权限：`system:manual-task:list`。
- 新增按钮节点 `SYSTEM_MANUAL_TASK_EXECUTE`，权限为 `system:manual-task:execute`。
- 将页面与按钮权限默认分配给有效的 `ADMIN` 角色。
- 脚本使用 `NOT EXISTS`，重复审核或补执行时保持幂等。

## 5. 后端实现

### 5.1 通用手动任务框架

在 `adpulse-main` 新建 `manualtask` 领域，包含：

- `ManualTaskDefinition`：任务编码、名称、说明及执行入口。
- `ManualTaskRegistry`：启动时收集所有定义，校验任务编码唯一，并按编码查找执行器。
- `ManualTaskService`：返回任务目录、创建触发事件、分页查询历史、查询单条日志。
- `ManualTaskWorker`：定时原子领取 `PENDING` 记录并执行。
- `ManualTaskMapper` 与 XML：只负责执行记录持久化和原子状态流转。
- DTO/视图类型：不直接向 Controller 暴露持久化模型。

任务状态只能按以下方向变化：

```text
PENDING -> RUNNING -> SUCCESS
                   -> FAILED
```

Worker 每 2 秒最多领取 5 条任务。领取使用带状态条件的更新：只有
`WHERE id = ? AND status = 'PENDING'` 更新成功的实例才能执行，避免多实例重复消费。

`RUNNING` 期间每完成一个处理批次更新 `heartbeat_at`。Worker 每分钟将心跳超过 30 分钟的
`RUNNING` 记录标记为 `FAILED`，日志追加“服务中断或执行超时”；释放唯一活动槽后允许管理员重新触发。

### 5.2 日志写入

提供任务级 `ManualTaskLogger`，统一生成：

```text
[yyyy-MM-dd HH:mm:ss.SSS] [INFO] 日志内容
[yyyy-MM-dd HH:mm:ss.SSS] [WARN] 日志内容
[yyyy-MM-dd HH:mm:ss.SSS] [ERROR] 日志内容
```

- 展示时间按 `Asia/Shanghai` 格式化，并在页面说明为北京时间。
- 内存中按批次缓存日志，每 100 行或累计 64 KiB 时追加到 `log_content`，任务结束前强制刷新。
- SQL 使用 `CONCAT(COALESCE(log_content, ''), #{content})` 原子追加，禁止先读后写覆盖并发内容。
- 每条被跳过的账户/人员写入一行日志；正常新增和“已存在”也写入日志，满足完整触发日志要求。
- 捕获异常时写入执行阶段、异常类型和安全错误信息。完整服务端堆栈仍写应用日志；数据库日志不得包含凭据、Token、请求头、Mongo URI 或 SQL 连接串。

日志开头记录触发人和任务 ID，结尾记录以下统计：

- 扫描飞书记录数。
- 解析人员数。
- 新增关系数。
- 已存在关系数。
- 账户不存在数。
- 空姓名数。
- 用户未匹配数。
- 用户重名数。
- 单账户写入失败数。
- 总耗时。

### 5.3 飞书使用人任务

新增任务编码常量：

```text
SYNC_FEISHU_AD_ACCOUNT_USERS
```

实现流程：

1. 一次性读取 MongoDB `feishu_account_used_record` 集合中全部记录的 `account_id`、
   `user_name`，不按 `in_use` 或同步时间过滤，也不读取其他无关字段。
2. 规范化账户 ID，并按账户 ID 合并重复记录中的姓名，保持首次出现顺序。
3. 批量收集全部唯一姓名，查询所有 `deleted_at = 0` 的系统用户，不限制 `status`，
   建立“姓名 -> 用户候选集合”。
4. 对每个账户完成姓名解析；无法唯一匹配的人员记录日志并跳过。
5. 查询账户资产及其当前有效使用人 ID。
6. 对新增用户调用独立的事务写入服务，每个账户一个事务：
   - 再次查询/锁定目标资产，防止并发人工修改导致重复判断。
   - 计算当前有效关系，按用户 ID 二次去重。
   - 使用专用 Mapper 插入缺失关系；`ON DUPLICATE KEY UPDATE` 只能刷新人员名称快照和
     `updated_by/updated_at`，不得覆盖既有关系来源、申请 ID、主使用人和分配时间。
   - 根据写入前是否已有有效关系决定第一个新增人员的 `is_primary`。
   - 实际新增后更新库存状态为 `ASSIGNED`。
7. 刷新日志和心跳，继续下一个批次。
8. 输出统计并完成任务。

不能直接复用当前会覆盖 `assignment_source` 的通用 `upsert` SQL；应新增飞书手动同步专用插入方法。

### 5.4 API

统一前缀：`/manual-tasks`。

#### 查询任务目录

```http
GET /manual-tasks
Permission: system:manual-task:list
```

返回字段：`taskCode`、`taskName`、`description`、`running`、`latestExecution`。

#### 触发任务

```http
POST /manual-tasks/{taskCode}/executions
Permission: system:manual-task:execute
Body: none
```

服务端从认证会话读取触发人，禁止前端提交操作人。任务不存在返回业务校验错误；已有活动实例返回冲突错误并携带当前任务 ID。

#### 查询触发记录

```http
GET /manual-tasks/executions?taskCode=&status=&page=1&pageSize=20
Permission: system:manual-task:list
```

列表不返回 `logContent`。ID 按字符串返回。

#### 查询执行详情与日志

```http
GET /manual-tasks/executions/{id}
Permission: system:manual-task:list
```

返回触发事件全部展示字段及 `logContent`。正在执行时允许前端重复查询。

所有接口继续使用统一 `ApiResponse`，Controller 只做 HTTP 适配；权限和状态约束位于 Service。

## 6. 前端实现

### 6.1 页面结构

在前端 `plat/src/views/system/manual-tasks.vue` 新增页面，使用现有系统管理页面和浅色主题基线：

```text
页面标题：手动任务
说明：由管理员按需触发后台任务，并查看每次执行记录与完整日志

任务卡片
└─ 同步飞书广告户使用人
   ├─ 行为说明：只增加共同使用人，不删除或覆盖现有关系
   ├─ 最近执行状态与时间
   └─ 立即触发

触发记录表格
├─ 任务名称
├─ 状态
├─ 触发人
├─ 触发时间
├─ 开始时间
├─ 完成时间
├─ 执行耗时
└─ 查看日志
```

### 6.2 触发交互

- 仅拥有 `system:manual-task:execute` 时显示“立即触发”。
- 点击后弹出确认框，明确提示：全量扫描飞书记录，只新增共同使用人，不解除现有关系。
- 提交期间按钮显示 loading，已有同类活动任务时按钮禁用并显示“执行中”。
- 创建成功后显示短成功提示，将新记录插入列表顶部并开始轮询。
- 存在 `PENDING/RUNNING` 记录时每 3 秒刷新任务目录和当前页记录；全部结束后停止轮询。
- 页面销毁时清理定时器，避免后台请求泄漏。

### 6.3 日志抽屉

- 点击“查看日志”打开抽屉，按需请求单条详情。
- 使用等宽字体、`white-space: pre-wrap` 和可滚动容器保留长文本换行。
- 提供“复制全部”和“刷新日志”按钮；图标带文字或可访问名称。
- 运行中日志顶部显示状态和加载反馈，刷新不关闭抽屉、不重置滚动位置。
- 日志为空时显示明确空状态，不展示 `undefined` 或空白抽屉。
- 不把日志内容渲染为 HTML，按纯文本展示，避免日志注入。

API 类型与调用放入独立的 `plat/src/api/main/manual-tasks.ts`，通过 `mainBackendClient` 请求
`adpulse-main`。

## 7. 权限与安全

- Controller/Service 使用 `@PreAuthorize` 校验页面和执行权限。
- 前端权限只控制可见性，不能替代后端鉴权。
- 触发人只能来自 `CurrentUser`，同时保存 ID 和名称快照。
- 日志禁止保存请求头、JWT、Redis 会话、MongoDB URI、数据库凭据及其他密钥。
- 日志内容按纯文本返回和展示，不支持富文本。
- 新增关系使用系统用户稳定 ID；姓名仅用于本次解析和展示快照。
- 任务查询只允许已认证且拥有页面权限的用户访问。

## 8. 测试方案

### 8.1 后端单元测试

- 支持全部约定分隔符及混合分隔符。
- 空白、重复姓名正确清理。
- `real_name` 唯一匹配成功；无结果后可回退 `display_name`。
- 重名匹配多个用户时跳过并记录日志。
- 多个名字映射到同一用户时只新增一次。
- `act_` 前缀规范化正确。
- 已存在 `APPLICATION`、`MANUAL`、`IMPORT` 或 `MIGRATION` 关系时不覆盖来源和主使用人。
- 无使用人账户的首位新增人员成为主使用人；已有关系时新增人员均为共同使用人。
- 重复执行不产生重复关系。
- 飞书不再包含某人时不会解除关系。
- 至少新增一人后库存状态为 `ASSIGNED`。
- 数据级异常不终止其他账户；系统级异常标记任务失败。
- 日志按批追加，包含触发信息、过程、错误和最终统计。
- 同一任务并发触发只有一个成功创建。
- 多实例 Worker 只有一个能领取同一执行记录。
- 超时 `RUNNING` 记录能被标记失败并释放活动槽。
- 无权限用户不能查看或触发任务。

### 8.2 Mapper 契约测试

- 列表 SQL 不读取 `LONGTEXT log_content`。
- 详情 SQL 返回完整日志。
- 飞书专用插入 SQL 不覆盖既有 `assignment_source`、`application_id`、`is_primary` 和
  `assigned_at`。
- 任务领取 SQL 包含 `status = 'PENDING'` 条件。
- 日志 SQL 使用数据库原子追加。

### 8.3 前端验证

- 页面权限和执行按钮权限分别生效。
- 确认框文案准确说明“只增不减”。
- 触发中、成功、失败、空记录均有明确反馈。
- 轮询只在存在活动任务时运行并在页面卸载时停止。
- 长日志保留换行、可滚动、可复制、按纯文本渲染。
- 窄屏下任务卡和操作区换行，不产生页面级横向滚动。
- 执行静态类型检查、针对性 ESLint 和 `git diff --check`。

## 9. 上线步骤与验收

1. 审核并手工执行 `adpulse-main` 的执行记录表脚本。
2. 审核并手工执行 `adpulse-system` 的菜单和权限脚本。
3. 部署 `adpulse-main`，确认 Worker 启动且 MongoDB/MySQL 配置沿用现有安全配置。
4. 部署 `adpulse-system`，确认登录响应包含新增权限码。
5. 部署前端，管理员重新登录以刷新 Redis 会话中的权限。
6. 首次触发前只读核对 Mongo 集合总记录数、非空 `user_name` 数和待匹配系统用户数。
7. 管理员触发任务，核对执行记录、触发人、时间、状态与完整日志。
8. 抽样验证新增人员成为共同使用人，原有人员及关系来源未发生变化。
9. 再次触发，确认新增数为零或仅包含期间新增数据，且不存在重复有效关系。

验收标准：

- 系统管理下可访问“手动任务”页面。
- 非执行权限用户不能触发任务。
- 每次触发都有独立、可追溯的事件记录和长文本日志。
- 同一任务不能并发执行。
- 飞书人员能按系统用户 ID 增量加入广告账户。
- 原有使用人永不因本任务被覆盖或解除。
- 重复触发幂等，错误可在日志中定位且不泄露敏感配置。
