# ORBIT 开发与验收入口

当前按用户要求改为 **RuoYi-FastAPI/Python + MySQL8 + Redis，全部功能重新开发**。先读[现行实施方案](IMPLEMENTATION_PLAN.md)和[框架替换及性能边界](PYTHON_BACKEND_MIGRATION.md)，再查看[新架构进度总览](PROGRESS.md)。旧Java专项文档/回执仅历史参考，不算Python验收。

- [全部模块逻辑、页面和弹窗](MODULE_LOGIC.md)：逐条业务行为及测试关注点，包含新增系统配置。
- [模块/页面交付表与实际并行分工](DELIVERY_BOARD.md)：前端、后端、联调、验收、缺口和证据分列，不以测试数量代替业务交付。
- [逐字段逻辑](FIELD_MATRIX.md)：原基础/扩展字段、正文补充与OpenAPI Schema属性，分别跟踪开发、测试、验收。
- [接口操作清单](API_MATRIX.md)：原127路径的156个HTTP操作，逐条跟踪。
- [实施方案与覆盖项](IMPLEMENTATION_PLAN.md)：若依选型、技术覆盖、开发顺序和交付标准。
- [数据库设计与性能台账](DATABASE_DESIGN.md)：当前实际表、逐模块查询索引计划及容量验收目标。
- [系统配置与凭据安全](SYSTEM_CONFIGURATION.md)：新增页面、GPT/Claude/Meta配置、加密与当前未验收边界。
- [Python人员、团队与角色](PYTHON_IDENTITY.md)：团队/角色及人员本租户读写检查点，含完整字段表单、版本冲突、回滚、会话撤销和三视口；邀请、OIDC、旧入口全矩阵、跨租户及完整验收仍未完成。
- [完整应用浏览器专项](BROWSER_INTEGRATION.md)：真实登录/动态菜单与配置弹窗的视口测试及未验收边界。
- [AI分析输入校验核心](ANALYSIS_INPUT.md)：产品Schema运行时修正、严格限制合并与尚未接通的消费链路。
- [产品原始需求](baseline/README.md)：原文快照，不因实施选择改写。
- [机器台账](progress.json)：状态唯一来源。报告由工具生成，不手工伪造勾选。

业务进度与“文档整理已完成”分开统计。最初所有业务开发、测试、验收均未完成。任何真实外部连接、实机执行和模型人工评估未验证的事项，都必须保持可见。

- [分析任务内部入队](ANALYSIS_JOBS.md)：冻结版本、并发幂等、当地日额度和未完成边界。

- [规则调度核心](RULE_SCHEDULE.md)：字段校验、当地墙钟、夏令时与停机合并，以及未接通的持久化/页面。

- [规则条件核心](RULE_CONDITIONS.md)：指标阈值、完整三值逻辑、逐条件缺失原因及未完成边界。

- [完整规则校验与内部版本存储](RULE_DRAFTS.md)：幂等/并发/状态/事件事务和未接通授权的明确边界。

- [规则拥有者与团队授权](RULE_OWNERSHIP.md)：显式身份映射、实时数据角色、撤权后幂等复核与未完成边界。

- [指标归因口径版本目录](METRIC_PROFILES.md)：完整定义、未知映射、不可变版本与不冒充真实验证的边界。

- [内部账户范围冻结](ACCOUNT_SCOPES.md)：模式校验、权限交集、不可变成员、50000容量与尚未接通的真实来源/公开接口。

[账户范围公开HTTP、CSRF与幂等逻辑](SCOPE_HTTP.md)。
