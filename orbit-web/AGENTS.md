# ORBIT 前端实施约定

先阅读后端仓库`../orbit-server/docs/orbit/IMPLEMENTATION_PLAN.md`、`MODULE_LOGIC.md`和`PROGRESS.md`。用户要求完整实现产品包的业务、字段、弹窗和二级页面，不能用页面骨架/模拟提示冒充完成。

- 官方若依Vue3、TypeScript、新页面使用`<script setup lang="ts">`与原生Element Plus；保留现有layout、菜单和功能，不引入React、Ant Design或Vben作为新UI。
- 新业务在`src/views/orbit/`与`src/api/orbit/`，路由`/orbit/*`通过新增后端菜单下发；既有动态菜单映射保持可用。子页/弹窗/抽屉逐个登记与验收。
- 复杂业务按账户、投放、监测、规则、素材、环境、渠道、系统八模块实现，不采用一个通用CRUD模板填充全部业务。
- 中文业务注释，准确类型，金额与外部ID保持字符串；明确loading/空/错误/无权限/部分未知、禁用原因与提交状态。
- 密钥只存在本次输入和提交内存，禁止放localStorage/sessionStorage、URL、日志或导出；不得复用默认请求拦截器的请求体缓存。当前系统配置独立客户端是参考。
- 默认本地18081代理本项目18080，不误连ad-mpower的8080/8081/5555服务，不启动/重启其他项目。
- 验证命令：`pnpm format:orbit`、`pnpm format:check:orbit`、`pnpm check:orbit`、`pnpm test:orbit`、`pnpm build:prod`。新增模块补充相应测试；组件mock不代替真实前后端Playwright验收。
- 每条业务同步后端进度台账；开发、测试、验收分别记录证据，未测试不打勾。不编辑生成报告伪造进度。
- 当前master分支继续，不创建新分支/worktree。私有`hesong0105-bit/orbit-web`已授权提交推送；origin是用户仓库，upstream是官方来源。
