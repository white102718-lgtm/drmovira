# Codex 开发任务与启动说明

## 可直接交给 Codex 的任务提示

> 请先阅读PRD-ORBIT.md、CONTRACT_OVERRIDES.md和contracts/openapi-current.json，按本文件阶段实现ORBIT。仅八个一级模块，保留全部原字段和信息。使用真实React/Ant Design，自动化投放六区单列上下。先检查现有仓库和约束，建立可复验开发计划；每阶段交付源码、测试和未完成项。原型仅视觉/业务参考，禁止把隐藏iframe/DOM桥部署为生产，也禁止把模拟结果宣称真实投放成功。原包和历史合同中的被删流程不实施；遇到冲突按覆盖表处理。无需重新讨论已确认名称、布局和模块范围。

## 阶段与完成门槛

### DEV-01 工程骨架与合同

依赖：无。

交付：建立八模块路由、Ant Design token、DTO客户端、真实组件、fixture身份和适配接口；保留全部字段；不要复用旧DOM桥。

需求：FR-GEN-01, FR-GEN-03, FR-GEN-05, FR-UI-01, FR-UI-02, FR-UI-03。

阶段验证：AT-GEN-01, AT-GEN-03, AT-GEN-05, AT-UI-01, AT-UI-02, AT-UI-03；未通过不得标记阶段完成。

### DEV-02 认证、权限与审计

依赖：DEV-01。

交付：OIDC/session、角色和数据范围、RLS、scope撤销、secret_ref、审计/outbox、kill switch。

需求：FR-GEN-02, FR-SYS-01, FR-SYS-02。

阶段验证：AT-GEN-02, AT-SYS-01, AT-SYS-02；未通过不得标记阶段完成。

### DEV-03 引用目录与渠道

依赖：DEV-02。

交付：实现4个新目录路径、完整渠道表单及历史约束，按覆盖表修正旧产品权限依赖。

需求：FR-CHN-01, FR-CHN-02, FR-CHN-03, FR-SYS-03。

阶段验证：AT-CHN-01, AT-CHN-02, AT-CHN-03, AT-SYS-03；未通过不得标记阶段完成。

### DEV-04 账户管理与导入

依赖：DEV-03。

交付：18列、详情、OAuth、分配历史、同步、本地解绑、带户商的导入和逐项结果。

需求：FR-ACC-01, FR-ACC-02, FR-ACC-03。

阶段验证：AT-ACC-01, AT-ACC-02, AT-ACC-03；未通过不得标记阶段完成。

### DEV-05 素材与标签

依赖：DEV-02。

交付：安全上传、指标/分类/标签筛选、归并标签页、引用追溯及原子批删。

需求：FR-AST-01, FR-AST-02, FR-AST-03。

阶段验证：AT-AST-01, AT-AST-02, AT-AST-03；未通过不得标记阶段完成。

### DEV-06 计划配置与模板

依赖：DEV-04、DEV-05。

交付：六区上下表单、差异树、预检、命名和分配冻结、草稿/模板/共享。

需求：FR-LCH-01, FR-LCH-02, FR-LCH-03, FR-LCH-04。

阶段验证：AT-LCH-01, AT-LCH-02, AT-LCH-03, AT-LCH-04；未通过不得标记阶段完成。

### DEV-07 统一命令与任务执行

依赖：DEV-06。

交付：CAS、幂等、风险账本、DAG、outbox、任务SSE、重试取消、回读及UNKNOWN只读对账；先用确定性fake Adapter验证。

需求：FR-GEN-04, FR-LCH-05。

阶段验证：AT-GEN-04, AT-LCH-05；未通过不得标记阶段完成。

### DEV-08 环境与双通道Adapter

依赖：DEV-07。

交付：设备绑定、心跳、租约fencing、动作能力证据、AdsPower Adapter和Meta Adapter、挑战恢复。

需求：FR-ENV-01, FR-ENV-02, FR-ENV-03。

阶段验证：AT-ENV-01, AT-ENV-02, AT-ENV-03；未通过不得标记阶段完成。

### DEV-09 指标与建议操作

依赖：DEV-07。

交付：指标发布快照、七Tab、导出、冻结建议依据、编辑/忽略/提交和采纳统计；先fixture，后真实采集。

需求：FR-MON-01, FR-MON-02, FR-MON-03, FR-MON-04。

阶段验证：AT-MON-01, AT-MON-02, AT-MON-03, AT-MON-04；未通过不得标记阶段完成。

### DEV-10 规则与AI闭环

依赖：DEV-09。

交付：条件AST、调度slot、模拟、命中、冷却/额度、模型schema验证与人工确认执行。

需求：FR-RUL-01, FR-RUL-02, FR-RUL-03。

阶段验证：AT-RUL-01, AT-RUL-02, AT-RUL-03；未通过不得标记阶段完成。

### DEV-11 迁移与端到端发布门禁

依赖：DEV-08、DEV-10。

交付：空库/升级迁移、引用对账、存档、真实连接器能力验证、端到端回归和回退演练。

需求：FR-MIG-01。

阶段验证：AT-MIG-01；未通过不得标记阶段完成。

## 实施习惯

1. 先运行 `python3 validation/validate_prd.py` 验证需求包完整性。确定语言、框架与存储的ADR，优先遵从实际仓库约束，不能凭原型猜已有后端。
2. 从OpenAPI生成或校验DTO，表单schema逐项映射FIELDS.md。建立fixture，包括未知值、多币种、失效引用、部分失败、UNKNOWN与NEEDS_HUMAN。
3. 单元/服务测试覆盖预算账本、状态转换、命名分配、权限；契约测试验证结构及条件限制；E2E验证关键用户路径，不能只测组件存在。
4. 阶段报告包含变更文件、所覆盖FR、实际执行命令、通过/失败/阻断、外部能力证据；模拟测试与真实联调分别记录。
5. 外部凭据和发布环境缺失时继续完成独立模块与mock测试，把对应生产动作维持禁用，并明确阻断原因。不得自行部署、迁移生产数据或执行真实广告写入；交付具体变更和验证结果后再按用户授权范围推进。
