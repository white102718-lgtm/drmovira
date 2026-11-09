# AdPulse 工程执行与环境规范

本文件是 AdPulse 跨仓定位、本地联调、验证和交付安全的唯一权威来源。它不重复代码风格或 UI 细则；编码规则见 `ai-coding-guidelines.md`，UI 规则见 `ui-guidelines.md`。

## 1. 任务定位与改动范围

- 先根据前端请求客户端、代理路径、接口地址或运行证据确认实际落点，再进入对应仓库；不得仅凭业务名称遍历所有服务。
- 小范围任务按“定位实际调用路径 → 修改直接相关代码 → 针对性静态校验 → 交付”执行。没有直接证据时，不扩展为全仓审计、全链路重构或无关问题治理。
- 修改必须保留既有 API、字段、权限、路由、数据转换和业务流程，除非当前需求明确要求改变。
- 用户提供反例或纠正信息时，使用稳定 ID、明确查询条件、权威数据源或可复现代码路径独立核验；结论应区分已验证事实、合理推断和待确认事项。
- 不得把未核实的矛盾归因于编码、缓存、环境、数据延迟或工具异常。发生误判时，说明原结论、复核证据、正确结论和误判原因。
- 不重复读取本次任务中已完整读取且未变化的规范、文件或诊断输出；中间进度只报告影响判断的新发现、假设、阻塞和验证结果。

## 2. 后端职责与调用链

| 子系统 | 源码目录 | 前端入口 / 调用关系 | 主要职责 |
| --- | --- | --- | --- |
| `system` | `D:\progress\adpulse-power-system\adpulse-system` | `backendClient`；开发环境 `/backend/*`；本地端口 `8080` | 用户、组织、角色、权限、菜单及关联配置 |
| `main` | `D:\progress\adpulse-power-system\adpulse-main` | `mainBackendClient` 或 `/backend/project/*`；本地端口 `8081` | 广告投放、项目、素材、报表等主营业务 |
| 广告数据 API | `D:\progress\backend` | `adpulseClient`；`/adpulse-api/*`；默认端口 `8000` | 广告面板查询与聚合等 FastAPI 接口 |
| 数据调度与同步 | `D:\progress\schedulers` | 前端不直接调用 | 广告数据拉取、清洗、同步、调度及异步消费 |

- 广告面板核心链路：外部广告平台 → `schedulers` → Doris/Mongo 等存储 → `backend` FastAPI → 前端 `adpulseClient`。
- `schedulers` 包含多个可独立部署的 scheduler、dispatcher、consumer 和 worker，不是单一 HTTP 服务。
- 组织、用户、角色、权限和菜单属于 `system`；广告平台主营业务属于 `main`；广告面板查询属于 `backend`；采集、定时同步和异步消费属于 `schedulers`。
- 多服务协作必须沿用既有接口、消息或明确契约，不复制业务逻辑。

## 3. 特殊代码边界

- `plat/src/embedded/twitcanva/**` 是只读历史参考，不得新增、修改、删除或接入新功能。
- 当前正式画布实现位于 `plat/src/embedded/adgen-canvas/**`；画布需求默认修改这里，除非用户明确指定其他实现。

## 4. 本地前后端联调

- 同时启动或重启前端、`system` 和 `main` 时，在前端仓库根目录执行 `pnpm local:all`。若为重启，只停止本项目已识别的相关进程，不影响其他项目或本机进程。
- 单独启动或重启本地后端时，必须使用 `D:\progress\adpulse-power-system\scripts\dev\start-local-services.ps1`；不得直接运行 Maven、手工注入环境变量或复用来源不明的 Java 进程。
- 后端环境变量只能从 `D:\progress\adpulse-power-system\.env.local` 及启动脚本支持的私有覆盖文件加载。不得把凭据写入命令、仓库、日志、测试输出或回复。
- 私有环境至少提供 `FEISHU_OAUTH_REDIRECT_URI`、`DB_URL`、`REDIS_HOST`、`REDIS_PASSWORD`、`DORIS_URL`、`MONGODB_URI`、`MINIO_ACCESS_KEY` 和 `MINIO_SECRET_KEY`；这里只记录变量名，不记录值。
- 需要联调本地后端时，前端使用根目录 `pnpm local:plat`，不得使用 `pnpm dev:plat`。其代理应将 `/backend/*` 指向本机 `system:8080`，将 `/backend/project/*` 指向本机 `main:8081`。
- 启动后验证 `http://127.0.0.1:5555/`、`/backend/menus/` 和 `/backend/project/projects`，并确认代理响应来自对应本机服务。验证输出不得包含环境变量值、令牌或其他敏感信息。
- 已运行的前端服务默认依赖 Vite 热更新；只有配置、环境变量、依赖变化、热更新失效或用户明确要求时才重启。不得仅为普通验证主动启动服务。

## 5. 验证策略

- 默认只执行与改动范围匹配的格式、语法、类型、针对性 Lint 和 `git diff --check`；不得默认执行全量构建、单元测试、集成测试、端到端测试或浏览器测试。
- 用户明确指定命令或测试范围时，以当前任务要求为准。
- 浏览器交互、视觉状态和端到端验收仅在用户明确要求，或 `ui-guidelines.md` 将具体高风险 UI 问题列为阻断验收时执行；所有此类测试统一使用 Playwright 驱动真实浏览器。
- 执行浏览器验证时记录实际操作路径、关键断言和可复现证据；不得仅凭源码、DOM 推断、构建结果或截图目测宣称通过。
- 不得为了提高完成感而自行追加服务重启、全量构建、全量测试、浏览器测试或重复验证。

## 6. 临时产物与 Git

- 构建、测试、诊断或 AI 辅助产生的临时文件，确认不属于源码、运行必需资源或测试基线后，必须加入根目录 `.gitignore`，使用尽可能精确的规则，并通过 `git check-ignore -v <路径>` 验证。
- 保留用户已有工作树变更，不覆盖或回退无关修改。

## 7. 发布与远程变更边界

- 测试、正式及其他远程环境的前后端代码均由用户手动发布。AI 不得上传部署包、替换或清理部署文件、切换版本、重启远程容器/服务，也不得触发或修改 Jenkins/CI/CD 发布任务。
- AI 可以修改代码、执行本地校验、分析 Jenkins 日志并提供发布说明。
- 唯一允许的远程环境变更是用户在当前任务中明确授权的远程 SQL。执行前必须确认目标环境、SQL 内容和影响范围；授权不得沿用到后续任务，也不得扩展为发布或服务重启。
- 用户手动发布前端时采用直接覆盖流程：归档新包到 `/opt/docker/frontend/adpulse/packages/`；清空但不删除 `/opt/docker/frontend/adpulse/current/`；解压新包到 `current`；重启 `adpulse-frontend-test`；按时间或版本仅保留最新 5 个归档包。
- 发布过程不得清理未明确指定的其他文件；完成后应核对部署版本、容器结果和归档数量。若仓库没有发布脚本或流水线配置，只提供实施说明，不得用业务代码代替运维配置。
