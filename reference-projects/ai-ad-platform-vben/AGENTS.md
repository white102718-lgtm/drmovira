# AdPulse 广告平台 AI 项目入口

本文件只维护项目入口、任务路由和必须加载的规范。详细规则按主题存放在 `.ai-context/`，同一规则只保留一个权威来源。

## 1. 项目定位

- Vue 3 + TypeScript + Vben Admin 5.x monorepo，业务应用为 `plat/`（`@vben/plat`）。`apps/*`、`playground` 和 `docs` 是上游演示包，除非任务明确要求，否则不修改。
- 主 UI 栈：Ant Design Vue 4、VXE Table、VbenForm；状态使用 Pinia，部分服务端状态使用 `@tanstack/vue-query`。
- 构建使用 Vite + Turbo；包管理器固定为 pnpm（Node >= 20.10）。主分支 `master`，开发分支 `dev`，提交信息采用 conventional + 中文说明。

## 2. 必须阅读的规范

| 任务类型 | 必读文件 |
| --- | --- |
| 任何代码生成、修改、重构、评审或数据库设计 | [.ai-context/ai-coding-guidelines.md](.ai-context/ai-coding-guidelines.md) |
| 前端 UI 新建、修改、修复、审查或视觉验收 | [.ai-context/ui-guidelines.md](.ai-context/ui-guidelines.md) |
| 跨仓定位、本地启动/联调、验证、发布或远程变更 | [.ai-context/engineering-workflow.md](.ai-context/engineering-workflow.md) |
| 页面定位、动态菜单或路由变更 | [.ai-context/routes.md](.ai-context/routes.md) |

- 按任务读取相关专题文件；不得在本文件或其他文档复制专题细则。
- 冲突优先级：用户当前明确要求 → 本文件的项目边界 → 对应专题规范 → 仓库工具配置 → 相邻稳定实现。

## 3. 项目关键路径

```text
plat/src/
├── api/         # 业务接口
├── views/       # 业务页面及共享业务组件
├── adapter/     # Vben 表单、表格、组件适配
├── router/      # 路由、守卫、动态菜单
├── store/       # Pinia 业务状态
├── constants/   # 共享常量与页面尺寸
├── styles/      # 全局主题与 UX 基线
└── utils/       # 业务工具
```

- 正式菜单由后端 `/menus/` 下发；`plat/src/router/access.ts` 通过 `import.meta.glob('../views/**/*.vue')` 映射页面。`/dashboard/ad-manager` 对应 `plat/src/views/dashboard/ad-manager.vue`。
- 隐藏页在 `plat/src/router/routes/access.ts` 补充；核心静态路由位于 `router/routes/core.ts`。
- 共享业务组件优先从 `plat/src/views/components/` 复用；模块私有组件放页面目录的 `components/`。

## 4. API 与通用实现基线

- `plat/src/api/request.ts` 封装请求客户端；业务主力为 `backendClient`（`/backend`）。拦截器负责 Bearer token、成功解包、401 登录跳转、通用错误提示及大整数处理，页面不得重复判断状态码。
- 列表优先 `useVbenVxeGrid`，表单优先 `useVbenForm`，弹窗/抽屉优先 `useVbenModal` / `useVbenDrawer`。
- 接口参数与表单字段同名时直接传递；大整数 ID 按字符串处理；正式文案使用 `$t()`。
- `#/` 映射 `plat/src/`；登录路径使用 `@vben/constants` 的 `LOGIN_PATH`，不得整页跳转旧 OAuth 站点。

## 5. 常用命令

| 操作 | 根目录命令 |
| --- | --- |
| 安装依赖 | `pnpm install` |
| 启动普通前端 | `pnpm dev:plat` |
| 启动本地后端联调前端 | `pnpm local:plat` |
| 同时启动本地前端、system、main | `pnpm local:all` |
| 构建业务应用 | `pnpm build:plat` |
| 类型检查 | `pnpm check:type` |
| Lint / 格式化 | `pnpm lint` / `pnpm format` |
| 提交 | `pnpm commit` |

启动方式、私有环境、验证范围和远程发布边界以 `engineering-workflow.md` 为准。

<!-- [teamai:culture:start] -->
<!-- DO NOT EDIT: This section is auto-managed by teamai -->

## Team Culture (teamai)

## Company: 无界

**Mission:** 用同一套 Agent 上下文，让团队知识跟着代码走

## Team: 无界技术

**Mission:** 每个人的 Agent 都能读到同事已推送的实现和约定 **Goals:**

- 口头约定必须落进本仓或业务代码
- 读要宽，写要窄
- 少维护文档，多检索、多写回

## 工作原则

- 约定从已推送的代码里长出来，不靠会议纪要。
- 本仓只存代码写不清的东西：单位、时区语义、禁止混用、新旧接口谁说了算。
- 字段长什么样，以业务仓的类型和实现为准。
- 谁第一次确认一条口径，谁就在当次任务里写回 `learnings/`。
- 同一主题不要并存两套说法。产品逻辑听产品经理；已上线实现听已推送代码。

## 协作

- Cursor 和 Codex 用同一套 skills / rules / recall，不要各维护一份。
- 跨模块只读对齐；改别人的域必须等人确认。
- 分享经验用中文，写短、可执行，不要写成日记。

<!-- [teamai:culture:end] -->
