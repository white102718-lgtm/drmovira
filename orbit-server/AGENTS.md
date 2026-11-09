# ORBIT 后端实施约定

本项目是完整产品开发任务。首先阅读`docs/orbit/IMPLEMENTATION_PLAN.md`、`MODULE_LOGIC.md`、`PROGRESS.md`及`SYSTEM_CONFIGURATION.md`，按依赖顺序继续未完成项。不要将初始检查点或已通过单测误读为八模块已完成。

## 技术与范围

- 用户2026-11-07最新决定：RuoYi-FastAPI后端、MySQL8和Redis；覆盖此前Java/MySQL要求。前端仍官方RuoYi-Vue3/Element Plus。既有Java/MySQL源码和证据保留作迁移核对，不能当作Python/MySQL实现或验收。
- 用户覆盖产品包技术框架要求，业务字段、条件、权限、状态、任务、双通道、弹窗和二级页等要求继续严格执行。
- 保留若依原菜单/功能；ORBIT业务新增菜单路由。不恢复旧申请、审批、履约和完整客户/产品/户商等退役模块。
- 当前分支继续开发，不创建/切换额外分支或worktree，保留已有未提交改动。

## 代码与安全

- Python路由薄、Service业务规则、Repository显式租户查询；Pydantic精确DTO。使用SQLAlchemy异步MySQL事务，幂等、审计、outbox与业务同事务；禁止无事务降级假装成功。
- 公共类型、业务方法和金额/时区/权限/版本/并发等边界用中文注释；SQL表与字段有有效中文COMMENT，说明枚举、单位、时间和关联。
- 金额Decimal、MySQL DECIMAL和接口十进制字符串，外部ID/业务UUID字符串，未知不补零；权限必须服务端复验，不能靠隐藏按钮。
- 凭据AES-GCM与独立主密钥、只写不读、不日志、不导出，不复用JWT密钥；不可使用会缓存含密钥请求体的默认审计或防重复机制。
- 后端私有变量只从`D:/progress/adpulse-power-system/.env.local`受控加载。ORBIT只读取自己的`ORBIT_`变量，不回退复用参考项目的数据库、Redis或平台凭据。
- Python本地启动与验收使用独立端口和独立MySQL/Redis实例；在Python等价迁移通过前不停止或修改现有18080/18081 Java预览。不得自动迁移/部署或执行真实广告写入。

## 验证与进度

- 产品原文在`docs/orbit/baseline/`，保持字节不变；校验脚本需UTF-8模式并在临时副本执行，避免修改原结果文件。
- Python使用Ruff格式和检查、pytest业务测试、真实MySQL/Redis事务及Playwright前后端验证。Java历史回执与Python新回执分开，旧PASS不继承为新版本通过。
- `python tools/orbit_progress.py check`检查覆盖和证据；`render`生成可读报告；规则新增/变化用`sync`合并。初始化脚本`record_initial_checkpoint.py`只能运行一次，禁止重置后续进度。
- 每条开发/测试/验收分开打勾。测试证据要有实际命令、时间、环境、结果、条目ID和受测源码hash；外部阻断列出解除条件，不标PASS。
- 本地镜像报告位于`D:/progress/orbit/docs/`；仓库内`docs/orbit/progress.json`为状态源。源代码变化使旧证据失效时重新验证，不改断言或跳过测试冒充完成。
- GitHub私有`hesong0105-bit/orbit-server`已授权提交推送；上游remote为`upstream`，目标为`origin`。每次提交前检查状态和`git diff --check`，不得泄露凭据。
