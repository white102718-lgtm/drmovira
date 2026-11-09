# ORBIT 实施约定与分阶段交付

日期：2026-11-07（Asia/Shanghai）。本文件落实本聊天已确认的方案，不代表实现完成。

## 已确认范围

1. 用户最新技术覆盖：Vue3 + Element Plus，Python FastAPI后端、MySQL8与Redis。采用insistence/RuoYi-FastAPI作为相似Python后台改造依据，使用其原生异步MySQL事务，所有功能重新开发；保留现有前端、layout和菜单。详见PYTHON_BACKEND_MIGRATION.md，Java历史证据不继承为Python通过。
2. 八业务模块新增到ORBIT工作台，路由`/orbit/*`；业务字段/权限/状态/弹窗/二级页面完整实现。需求包指定的React/Ant Design/PostgreSQL/RLS/ClickHouse等技术栈不作为强制约束；数据库隔离、快照、精度、归属等业务语义仍需实现。
3. GPT API与Claude API；系统管理新增系统配置页，业务密钥认证加密、只写不读、租户隔离、脱敏审计，保存不自动解锁平台写能力。
4. 参考`D:/progress/ai-ad-platform-vben`、`D:/progress/adpulse-power-system`、`D:/progress/backend`、`D:/progress/schedulers`等ad-mpower实际调用链。只读参考，不把原项目的旧审批/履约业务带进ORBIT。
5. 当前目录无原Git仓库，前后端放独立子目录；使用克隆后的默认分支，不额外切分支或创建worktree。GitHub个人账号`hesong0105-bit`下私有`orbit-web`与`orbit-server`，已获创建、提交和推送授权。
6. 本地开发验收；不部署、不迁移现有环境，不执行真实广告写。缺凭据/设备的真实集成列外部阻断，不能声称全量验收通过。

## 上游固定版本

| 仓库 | 分支 | 初始提交 |
| --- | --- | --- |
| yangzongzhuan/RuoYi-Vue3 | master | 838965c5a18d2c61b73ec30c6e288057aaa08b63 |
| yangzongzhuan/RuoYi-Vue | springboot3 | a51a838b71b446ea27256900efe7ed2faa2a02fd |

上游MIT许可证和来源信息保留。原始需求完整快照在`baseline/`；用户覆盖项在本文件和模块逻辑文档单独登记，不改产品原文。

## 开发顺序

| 原阶段 | 当前交付内容 | 依赖 |
| --- | --- | --- |
| DEV-01 | 底座、八模块路由/菜单、契约、字段映射、覆盖台账、格式与测试工具 | 无 |
| DEV-02 | 用户/租户/团队、动作与数据权限、会话撤销、审计/outbox、系统配置及加密 | DEV-01 |
| DEV-03 | 引用目录原子导入、渠道全流程与权限 | DEV-02 |
| DEV-04 | 账户18列、详情、OAuth、归属、同步、解绑、批量添加和逐项结果 | DEV-03 |
| DEV-05 | 素材安全上传/处理、筛选、标签分类、引用、批删 | DEV-02 |
| DEV-06 | 六区计划、差异树、身份/预算、全局素材分配、命名、草稿/模板共享 | DEV-04、DEV-05 |
| DEV-07 | 统一命令、DAG、预算预占、幂等、回读、重试取消、SSE、UNKNOWN | DEV-06 |
| DEV-08 | Agent、Meta和AdsPower双通道、能力矩阵、租约、挑战恢复 | DEV-07 |
| DEV-09 | Python采集与指标快照、七Tab、建议/日志/统计/导出/提醒 | DEV-07 |
| DEV-10 | 规则条件/模拟/调度、GPT与Claude分析、评估与人工确认闭环 | DEV-09 |
| DEV-11 | 空库/升级/回退、跨模块E2E、外部验证清单、证据归档与双仓推送 | DEV-08、DEV-10 |

阶段按开发、测试、验收分别计数。代码构建、文档覆盖、假数据交互都不能替代功能验收。新增系统配置编号为CFG-01至CFG-16，纳入system模块；不把新增要求强塞进旧36项验收而漏测。

## 质量与测试标准

- 所有业务字段、原型信息、Schema属性与接口操作分别建立矩阵；API合同不等同于实际业务实现。
- 单元测试覆盖纯业务与安全边界；真实MySQL/Redis集成覆盖隔离、事务、锁、幂等和并发；Playwright覆盖真实前后端所有页面/弹窗和关键流程。
- 字段测试包括正常、空值、缺失、边界、非法类型/枚举、联动、条件必填、权限、存储与展示一致性；只读字段验证来源/时间/未知。
- 前端ESLint/Prettier/TypeScript，Java Spotless/Google Java Format；中文业务注释；SQL表和字段中文COMMENT包含单位、枚举和时间语义。
- 记录实际命令、时间、环境、退出码和脱敏证据；无用例或未运行均不能勾选。外部集成、模型质量人工评估、实机动作能力单独记录。
- 修复后重跑受影响测试；不以删用例、改断言、跳过模块降低完成标准。若依原功能和八业务模块均需回归。

## 进度与监督

`progress.json`为状态源；`PROGRESS.md`为按模块勾选总览，`FIELD_MATRIX.md`与`API_MATRIX.md`为逐项报告。使用`python tools/orbit_progress.py render`生成报告，`check`验证覆盖与证据。原需求变化或新增模块逻辑后执行`sync`，按稳定ID合并，不清空历史状态。

当前聊天已创建10分钟心跳监督（automationId：orbit-10）；每10分钟检查实际工作状态；工作已停则立即恢复下一项，存在运行中的开发则避免重复并发。持续推进授权开发，不以心跳、一次测试或一次提交作为停工点；仅在有意义的完成、失败或需要用户处理时通知，不作逐轮例行汇报。不得用心跳次数冒充工作量或验收通过。没有运行中的工作进程时如实说明；任务全部内部验收和推送完成后停止监督，外部阻断仍明确列出。

## 接入文档依据

- [OpenAI API认证](https://developers.openai.com/api/reference/overview)：凭据仅服务端使用。
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)：输出遵守支持的JSON Schema子集，应用仍验证业务语义。
- Claude协议在实现其Adapter前按Anthropic官方文档核对；不使用Claude Code CLI登录态或订阅凭据替代API Key。

## 内部分析入队检查点

当前只推进DEV-10的内部队列核心：可信命中接口、公开配置版本冻结、原子冷却/当地日额度、幂等及generation事件。真实规则分发、指标来源、任务页面、模型Worker和建议闭环仍未完成；本检查点不能替代DEV-09或DEV-10完成验收。具体逻辑与逐项测试边界见[ANALYSIS_JOBS.md](ANALYSIS_JOBS.md)。

规则持久化前置：已实现共用Schedule校验/预览/最近到期slot计算，详见[RULE_SCHEDULE.md](RULE_SCHEDULE.md)；规则存储、条件计算、调度唯一和可信命中链路继续待开发。

规则持久化前置进一步补齐logic/groups投影校验和三值evaluator，详见[RULE_CONDITIONS.md](RULE_CONDITIONS.md)。完整RuleWrite结构及内部版本事务已补齐，见[RULE_DRAFTS.md](RULE_DRAFTS.md)。owner身份映射及内部数据授权已补齐，见[RULE_OWNERSHIP.md](RULE_OWNERSHIP.md)。profile未验证定义目录已补齐，见[METRIC_PROFILES.md](METRIC_PROFILES.md)。内部账户范围请求及冻结事务已补齐，见[ACCOUNT_SCOPES.md](ACCOUNT_SCOPES.md)。内部目录CAS发布事务已补齐；下一步接真实Meta目录采集、未来模块权限版本、跨租户公开授权与规则引用，并继续真实口径验证及模拟；内部存储不替代规则页面或可启用闭环。

当前已实现授权输入的单调权限时钟与范围冻结权限版本已补齐，详见[账户范围逻辑](ACCOUNT_SCOPES.md)。当前范围HTTP动作复核和加密游标已接入；未来模块授权源、缓存/SSE/导出撤销尚未完成，不增加整体完成勾选。

冻结范围成员分页核心已补齐：整份范围实时权限复核、UUID keyset、冻结字段、AEAD游标绑定及11项新增MySQL专项与5万250页容量验证，详见[账户范围逻辑](ACCOUNT_SCOPES.md)。公开创建/成员接口以及会话/菜单动作/CSRF/幂等链路已接入；账户列表跨页选择、跨租户正向授权与字段HTTP覆盖仍需补齐，保留未完成勾选。

范围公开POST/成员GET及会话绑定CSRF扩展已接入，真实若依登录/HTTP/MySQL/Redis链路见[SCOPE_HTTP.md](SCOPE_HTTP.md)。当前仍需受控跨租户正向授权、剩余字段边界/角色HTTP组合及完整账户列表选择器，保留未完成勾选。

范围逐字段HTTP专项已扩展为3个聚合用例，覆盖缺失/类型/非法值/超限不落库及筛选、IDS规范化重放、四种页大小和长ID字符串；完整覆盖表见[SCOPE_HTTP.md](SCOPE_HTTP.md)。本轮补测试和证据，不增加整体开发或验收勾选。

账户范围冻结页及成员弹窗已通过新增V012菜单接入，含筛选变化立即使旧选择失效、幂等重试、查询取消和分页核对；配置/范围各3个真实浏览器视口通过。完整账户列表跨页勾选、投手/户商名称目录与跨租户正向授权仍待开发，参见[SCOPE_HTTP.md](SCOPE_HTTP.md)，保持逐阶段未完成勾选。

范围授权已按PERMISSIONS.md修复多功能角色并集，保持当前菜单/动作交集与数据角色隔离；MySQL82及真实非管理员HTTP（完整应用5项、浏览器仍6项）通过。原误拒绝403失败回执保留，不增加完整模块验收勾选，见SCOPE_HTTP.md多角色小节。

服务端操作租户目录前置已实现，当前身份解析接入范围HTTP；新增4项内部目录/目标预检真实MySQL用例，总86项通过。公开跨租户写入、home/target权限版本联动及actor+目标审计仍未实现，继续未验收，详见SCOPE_HTTP.md服务端租户目录小节。


内部home/target双版本前置校验新增3项MySQL测试，总89项通过。任一时钟变化、双上限及身份/角色/目标失效均已验证；未绑定公开快照/游标、目标事务及审计，跨租户业务仍未完成。 默认Java273、完整应用5及浏览器6项通过；具体逻辑见[SCOPE_HTTP.md](SCOPE_HTTP.md)双租户权限版本小节。


内部会话目标租户冻结、双版本绑定与锁顺序新增5项真实MySQL用例通过，总94项；重放/读取重新授权，旧快照不补版本，事务失败无残留。首轮record映射失败已修复并保留回执。公开跨租户HTTP、成员游标及actor+目标审计仍未实现，整项继续未验收。 默认Java273、应用5、浏览器6及网络6项回归通过；当前边界见[SCOPE_HTTP.md](SCOPE_HTTP.md)会话目标冻结小节。


内部会话目标成员分页及V2双版本游标新增6项MySQL专项通过，总100项；任一租户版本变化拒绝首/续页，游标绑定身份/角色/快照/筛选/页大小且与V1隔离。公开跨租户入口、actor+目标审计及前端目标选择仍待接入，整项继续未验收。 Java273、应用5、浏览器6及网络6项回归通过；详见[SCOPE_HTTP.md](SCOPE_HTTP.md)内部会话目标分页小节。


本地前后端已按用户要求启动供查看，运行边界与自动测试端口冲突见[LOCAL_PREVIEW.md](LOCAL_PREVIEW.md)。不得停止预览实例；下次浏览器回归须先隔离18081端口。此启动不新增业务开发/测试/验收勾选，actor+目标审计仍待继续。


范围新冻结成功审计新增5项MySQL专项通过，总105项；记录actor/home/目标及双版本摘要，审计失败整笔回滚，幂等/并发仅一事件。测试已与运行中的预览端口/JAR隔离。公开跨租户入口、审计读取及全业务outbox仍待接入，不增加整项完成勾选。 Java273、应用5、浏览器6及网络6项回归通过；详见[SCOPE_HTTP.md](SCOPE_HTTP.md)范围成功审计与预览隔离小节。


受控公开跨租户范围POST及server_scope定位成员GET已接入；新增5项MySQL/2项真实HTTP用例通过，MySQL总110、应用7。保留V1/V2、双版本/CSRF/当前actor/菜单与原子审计。首轮容量连接超时保留，真实连接池复验全110通过。目标选择UI、审计读取和真实Meta未完成，整项不增加完成勾选。 Java273、浏览器6、网络6及台账12回归通过；详见[SCOPE_HTTP.md](SCOPE_HTTP.md)公开跨租户范围小节。


新增范围冻结审计内部读取门禁及V016历史身份字段：新事件保存操作者业务UUID/团队UUID，旧事件NULL不猜测；当前菜单角色授权并集与本人/显式管理团队/当前启用租户数据范围共同约束，调队不改历史，撤管及资源不可见立即拒绝。新增6项MySQL专项通过，总116；Java273、应用7、浏览器6、网络6和台账12通过。完整AuditPage API、request_id采集、查询分页与审计页面仍待开发，本轮不增加整项完成勾选。 详见[SCOPE_HTTP.md](SCOPE_HTTP.md)审计历史身份与内部读取门禁小节。


范围冻结成功审计接通真实HTTP请求UUID：服务端生成并返回X-Request-ID，同事务保存；客户端同名头不能冒充，重试返回新请求ID但事件保留首个成功ID；旧事件和内部调用NULL不伪造。新增3项MySQL专项并强化2项真实TCP用例，总MySQL119、Java273、应用7、浏览器6、网络6与台账12通过。首轮编译失败及随后HTTP错误头/体UUID不一致（7项中5失败）均已修复，原断言全量复验，另修正浏览器未等待关闭/刷新版本的步骤，三次失败回执保留。完整审计API/查询分页/页面及其他业务审计仍待开发，不增加整项完成勾选。 详见[SCOPE_HTTP.md](SCOPE_HTTP.md)冻结成功审计的真实HTTP请求关联小节。


恢复停留在失败的审计查询开发：修复不可见404跨事务代理导致外层rollback-only，纠正字面下划线测试预期并保留失败证据。内部单目标审计批次支持动作字面查询、历史操作者UUID、UTC包含端点、稳定时间/UUID排序及首批截止；最多扫描200候选，空批仍可续扫；AEAD游标绑定身份/目标/筛选/大小/双版本，任一时钟变化或目标停用均拒绝。新增7项MySQL专项，总126通过，Java273、应用7、浏览器6、网络6及台账12通过。通用AuditPage跨租户合并、公开接口与审计页面未实现，无整项完成或验收新增勾选。 详见[AUDIT_QUERY.md](AUDIT_QUERY.md)。


补齐审计查询参数解析器并让内部分页复用同一字段规则：未知/身份注入字段400，重复或缺失参数400，不支持status/channel/profile/entity筛选422；验证页大小、游标长度、Unicode文本、历史操作者UUID和UTC日期，查询对象toString脱敏。新增7项单测及原OpenAPI参数清单核对通过，默认Java280、MySQL126、应用7、浏览器6、网络6和台账12通过。尚未接通公开审计控制器、跨租户合并及AuditPage旧未知字段适配，不是接口或页面验收，无整项新增完成勾选。 详见[AUDIT_QUERY.md](AUDIT_QUERY.md)参数解析小节。


公开GET /api/v1/audit-events与新增审计菜单页已接通范围冻结事件：跨当前授权租户稳定合并、九字段详情、筛选与20/50/100/200分页；全部目标版本绑定游标，未知历史必填身份显式503而不伪造或隐藏。新增MySQL9/真实HTTP3/浏览器3项通过，总Java280、MySQL135、完整应用10、浏览器9、网络6、前端21、台账12；保留三次失败回执。其他事件源、历史身份补证及完整SYS08仍待完成，不增加整项完成或验收勾选。 详见[AUDIT_QUERY.md](AUDIT_QUERY.md)公开接口与页面小节。
