# A线：通知任务交付计划

本阶段遵循实施文档第七节。人员邀请、OIDC与Cookie浏览器闭环已有检查点，不重复重写。当前阶段仅补齐通知任务执行入口和受控周期运行，不能以调度单测替代真实邮件送达验收。

## 最小范围与接口依赖

- 复用 `InvitationDeliveryWorker` 的单条认领、短事务、真实HTTPS、版本回执与超时UNKNOWN恢复；本阶段不修改该类、不增加迁移。
- 生产入口仍只读取指定 `.env.local` 的 `ORBIT_PYTHON_` 命名空间，不增加连接串、密钥或测试模式参数。
- `--send` 和 `--recover` 必须明确选择；默认只执行一轮。显式 `--serve` 才启动常驻循环；没有将任务加入Web应用启动或现有调度器。
- 每轮先保守恢复超时SENDING，再按上限逐条认领。UNKNOWN不会重新入队；只在管理员明确重发新邀请后产生新投递。
- 同机一次性和常驻运行共享操作系统文件锁；第二实例不能同时启动。不同机器仍由MySQL `SKIP LOCKED` 和持久化状态保护认领。
- SIGINT/SIGTERM只标记停止：当前单条完成后不再认领下一条，等待间隔可立即退出。强制杀进程没有成功回执保证，仍按SENDING→UNKNOWN恢复。
- 周期之间默认等待30秒，可设5至3600秒；单轮1至100条。连续三轮异常后退出1，错误只输出固定类别。没有自动外发重试。
- `--serve --cycles N` 限定1至1000轮，仅用于受控验收；省略轮数时为显式常驻。长期无人值守的进程托管/报警仍需后续环境部署，不声称已启用。

## 分阶段勾选与证据

| 阶段 | 实现 | 测试 | 验收 | 说明 |
| --- | --- | --- | --- | --- |
| 调度循环、停止边界、脱敏失败 | 已写入 | 专项单测已通过 | 对应CLI子项通过 | 单测使用Worker替身，只证明任务控制逻辑；实际运行另见149组回执 |
| 本机互斥与退出释放 | 已写入 | 真实子进程争锁测试已通过 | 对应互斥子项通过 | 不启动共享服务；不等于跨机器长期运维验收 |
| 实际CLI启动及隔离TLS投递 | 已实现 | 真实子进程/MySQL/TLS通过 | 内部子项通过 | 由主任务串行集成，源码与回执可追溯 |
| 两轮有限自动恢复与UNKNOWN不重发 | 已写入 | 实际两轮CLI通过 | 内部子项通过 | 不注册Web应用启动任务，不声称常驻托管已启用 |
| 真实外部通知渠道/邮件送达 | 待外部条件 | 未运行 | 未通过 | 受控TLS回执不是邮件送达证据 |

专用单测：`python -m pytest python/tests/test_invitation_job.py tools/tests/test_invitation_worker_cli.py tools/tests/test_invitation_worker_lock.py tools/tests/test_invitation_worker_cli_checks.py`。回执暂存 `.runtime/invitation-job-unit.xml`，主任务归档时需登记当时源码指纹。静态检查与格式仅限本线文件，由主任务统一运行全局回归与总台账更新。

## 主任务集成接入点

新工具 `tools/invitation_worker_cli_checks.py` 提供 `run_invitation_worker_cli_checks(values, idp, queued, state, cases)`。可在现有投递专项末尾、通知配置与发起人快照仍有效时调用；`values`使用主runner内存中的隔离配置，`queued/state`复用现有投递专项局部函数。需要主任务在该专项函数增加显式values参数并统一注册 `CLI_CASES`，本线不改公共runner。

子进程从stdin接收隔离配置，经已有 `configure_isolated_fixture` 验证；真实执行生产CLI的 `__main__`、实际数据库初始化、任务方法和清理。只有测试引导把网络目标限定为本机TLS夹具并验证夹具CA，不伪造成功响应。配置不写入命令行、环境变量或磁盘。验收顺序：恢复不能发送QUEUED→真实签名HTTPS接受→两轮受控恢复且无新请求→两轮发送遇断连仅产生一次请求且保留UNKNOWN→启动失败固定错误且无私密输出。

主任务已完成真实CLI集成：`evidence/python-framework-integration.json` 执行于 `2026-11-08T03:54:16.819635+00:00`，149/149组通过，其中5组CLI新增专项全部通过；日志在后端工作区 `.runtime/invitation-cli-integration.log`。使用显式001—008迁移范围，不包含其他并行模块未完成迁移。该回执证明本机隔离环境实际启动生产CLI、数据库初始化、TLS回执与有限周期；不增加整模块验收勾选。真实容量、外部渠道及无人值守托管验收独立保留。

## 原始合同逐项核对（只读审计，2026-11-08）

依据为原PRD `FIELDS.md` 系统字段、`PRD-ORBIT.md` FR-SYS-01及第380行补充、`contracts/PERMISSIONS.md` 认证条款、`contracts/openapi-current.json` 的UserWrite/User/Session/AuthorizationStart/AuthorizationSession以及AT-SYS-01。以下区分“已有实现”“已有证据”“尚未覆盖”；不以源码审阅等同业务验收。CLI执行结果引用主任务上述149组实测回执，不由审计推测。

### 人员字段与弹窗

| 字段/逻辑 | 当前Python及界面实现 | 剩余核对或证据缺口 |
| --- | --- | --- |
| id、revision | 只读业务UUID、最大安全整数版本；详情显示，更新携带If-Match | 原User严格十字段与补充字段扩展需保持分别登记，不能把原additionalProperties=false悄悄放宽 |
| display_name | 1至50码点、NFC/trim、拒绝控制字符；新增/编辑/列表/详情 | 改名后全部未来业务模块的历史操作姓名快照尚需跨模块证明，不能仅用人员保存测试代替 |
| nickname | 0至50码点，与姓名分离，四个界面位置保留 | 逐字段边界已有解析及人员专项；全部界面字段清单仍需绑定实际截图/用例 |
| email | 规范邮箱与长度校验；邀请只绑定规范化邮箱，未经IdP核验不启用 | 浏览器尚缺“邮箱不匹配/未验证”的失败流程；后台已有首次激活拒绝专项 |
| phone | 0至32码点的补充联系方式字段，可编辑；原PRD第380行明确要求保留 | 作为补充字段登记，不属于原八字段UserWrite；手机号不应被误称认证凭据 |
| team_id | UUID、同租户启用团队引用、远程选择；调队增加安全版本 | 详情当前显示团队UUID而非名称；原型可读名称/失效历史名称应补齐；真实Cookie调队后界面重新登录尚缺专项 |
| role_ids | 1至20个合法UUID、不重复、同租户有效引用，远程多选 | FIELDS中“默认只读”与当前新增空选项需补充明确映射：当前要求操作者主动选择，不会擅自授予角色；详情只显示UUID，需名称回显 |
| data_role | USER/TEAM_ADMIN/SUPER_ADMIN；普通用户不能附带管理团队；超级管理员专属变更 | 真实Cookie账号修改角色后旧页写入、菜单刷新、重新登录需浏览器专项；现有数据库/HTTP证据不可冒充这些UI验收 |
| managed_team_ids | 0至500个合法UUID、不重复、同租户；TEAM_ADMIN显示多选控件 | 500项远程回显、停用/失效团队与切换数据角色清空集合需单独三视口边界证据 |
| status | INVITED/ENABLED/DISABLED；未经验证不得直接ENABLED；最后管理员保护 | 停用后旧Cookie访问必须401已有服务逻辑；真实Cookie浏览器正在操作时的失效提示/路由恢复待验 |
| identity_status | 只读LOCAL_ACCOUNT/UNVERIFIED/OIDC_VERIFIED；既有口令与已验证OIDC区分 | 首次邀请成功后三视口已验证OIDC_VERIFIED；每种状态下新增/编辑/邀请按钮矩阵尚未全覆盖 |
| 新增/编辑弹窗 | 全字段、取消、授权变更确认、版本冲突重读、同意图幂等重试 | 应补齐重读取消保留草稿、保存期间关闭、全部403/401/409/422/503提示的组件/真实HTTP联合矩阵；不宣称每一异常弹窗都已验收 |
| 人员详情抽屉/列表 | 四种文本字段、角色/状态、游标/日期/每页数量保留 | 名称回显及全字段长值/大集合、空值与读失败重试需要独立验收记录 |

当前对应源码：`python/orbit_api/identity_contract.py`、`user_create_store.py`、`user_update_store.py`、`user_store.py`；前端 `src/views/orbit/system/users/{index,CreateUser,ReferenceSelect}.vue`。已有证据索引在 `PYTHON_IDENTITY.md` 与 `evidence/python-browser-users.json`；旧检查点不能证明新增缺口已完成。

### 登录、会话及退出合同

| 合同字段/状态 | 当前实现与已有证明 | 明确未覆盖/下一动作 |
| --- | --- | --- |
| AuthorizationStart.return_to | 原接口只接受单一字段；255码点站内路径，嵌套编码/双斜线/反斜线拒绝；前端保守回退index | 成功返回原目标已有单测，真实浏览器非index返回、带query/hash目标待专项 |
| AuthorizationSession.authorize_url、expires_at | 后端返回两字段并使用固定提供者、PKCE S256、五分钟授权状态；前端只跳HTTPS443 | 前端没有校验expires_at；过期服务响应/浏览器滞留超过五分钟时的显示与重新发起未形成真实链路证据 |
| callback.state、code | 唯一两参数；浏览器绑定、一用即认领；实际HTTPS/RSA/nonce验证及同邮箱不自动合并身份已有HTTP专项 | IdP用户取消常见error/error_description回调目前归为参数无效，缺少取消的明确指引与真实浏览器场景；不应重试原码 |
| Session.user | 使用本地人员及角色，不能由IdP角色/邮箱自行授予 | 全部公开字段严格类型由后端保证；前端remember仅做基本形状校验，尚未逐字段覆盖无效响应处理 |
| Session.scope_version | 读取本租户目录时钟；角色/团队变更触发即时失效 | 当前tab不主动订阅权限变化；界面主动刷新/401恢复未形成完整验收矩阵 |
| Session.menu_codes、permission_codes | 有效本地功能角色取并集；未知注册代码拒绝；原layout及原菜单保留 | 多功能角色并集与空菜单真实Cookie三视口未逐项验收；本字段还需与主任务正在统一的公共授权变更一起回归 |
| Session.csrf_token | 独立用途MAC、内存持有、不写Storage；Cookie写请求同源+CSRF | 已有Cookie HTTP越源/缺CSRF拒绝；真实浏览器失效CSRF提示及重读恢复尚缺，限流Redis不可用时503/失败关闭仍需专项 |
| Session.expires_at | 闲置30分钟/绝对12小时，数据库时钟；续期不突破绝对上限 | 数据库到期/续期专项已覆盖，浏览器闲置到期、绝对到期、重新登录指引待补 |
| Secure/HttpOnly/Lax/Path=/无Domain | 受控IdP真实浏览器三视口已读属性、刷新恢复、退出401及再次登录 | 生产证书/域名/反向代理尚未验证；自签名夹具不代表生产TLS验收 |
| DELETE session无正文、CSRF、幂等Ack | 原会话归属、同键重放、审计回滚已有数据库/HTTP；客户端网络失败保留退出键 | 多tab退出、退出与probe竞态、丢响应重试前探测会话的行为未有真实浏览器证明 |
| 无提供者/多个提供者/429/503 | 页面有配置缺失、重读、手选提供者及错误信息；接口有限流 | 新增6项专用组件替身检查已通过；尚不等同后台真实429/503、真实IdP失败UI验收 |
| 发起授权期间离开页面 | callback等待结果有generation保护，但start函数等待授权URL后没有相同保护 | 只读发现可疑竞态：页面卸载后迟到start结果仍执行location.assign；需主任务分配公共页面修改并补导航替身测试，再决定修复。当前六项新测试未覆盖此成功跳转竞态 |
| 身份提供者受信恢复入口 | 没有新增自建密码恢复流程，保留原若依口令登录入口 | 当前企业登录页尚无受信IdP账号恢复入口；需在明确提供者配置后补，不接受浏览器任意恢复URL |

现有证据：`evidence/python-authentication-storage.json`、`python-oidc-callback.json`、`python-browser-system-authentication.json`，以及实际Session/Cookie HTTP专项。成功浏览器闭环不能替代本表列出的异常与并发路径。

### 邀请、通知状态及运维缺口

| 对象 | 已有实现/证据 | 尚未覆盖 |
| --- | --- | --- |
| POST人员邀请 | 无正文、If-Match、CSRF、同键幂等；24小时、唯一有效邀请、重发撤销旧凭据；后台6组排队与5组激活检查 | Cookie管理员实际发邀请并由通知接收方打开链接的完整浏览器链路尚缺；当前首次链接从隔离加密队列取出 |
| ACTIVE/CONSUMED/REVOKED/EXPIRED | 状态接口按数据库时钟派生EXPIRED；弹窗四种中文标签 | 尚无四状态逐个组件与三视口证据，过期重发/撤销旧链接的真实浏览器失败流程需补 |
| QUEUED/SENDING/ACCEPTED/FAILED/UNKNOWN | 弹窗五标签；明确ACCEPTED仅渠道接受；实际Webhook、断连UNKNOWN与恢复已有后台5组 | 尚无五状态逐个界面验收；failure_code后端返回但弹窗未展示具体类别，支持排错仍不足 |
| blocked_reason/can_invite | 服务端核对超级管理员、人员状态、唯一OIDC与Webhook配置；弹窗禁用原因 | 多OIDC提供者/多通知配置、禁用配置、站内通知不能投递未登录人的界面矩阵尚缺；当前唯一提供者是明确产品约束说明，不静默随机挑选 |
| 邀请响应丢失/重发确认 | 组件保留版本+幂等键；刷新不制造新意图；重发需确认；已有4项组件测试 | 关闭重开后原待确认意图、多人员各自未知意图、401/403/422/503恢复需补专用测试；429是否保持原键也需验证 |
| CLI与受控循环 | 本阶段实现；27项控制/边界单测通过；主任务149组回执包含5组真实CLI验收通过 | 没有把常驻任务自动注册/启动，没有进程托管、监控告警或任务管理页面验收；正常停止信号生命周期仍以控制逻辑单测为证，尚未声称生产操作系统运维验收 |
| 到期数据清理/容量 | 有索引和小批认领，认证到期按读取时校验 | 尚无生产会话/授权/邀请/幂等历史的有界保留清理任务；测试库清理不算实现。需定义审计留存与FK顺序后实现；5万账户/100万事实总容量仍未运行 |
| 外部渠道与提供者 | 本机TLS及IdP夹具验证真实协议交换，不调用外部渠道 | 真实IdP、Webhook运营方签名验证/去重及实际邮件送达、生产TLS、限流/可用性与告警均未验收 |

### 下一最小闭环与测试边界

1. 已由主任务完成已冻结的5组CLI集成并登记149组真实结果；只对本机隔离MySQL/TLS运行。后续归档与总台账由主任务维护。
2. 独立新增 `orbit-web/tests/orbit/authentication-errors.test.ts`，不改任何认证实现，覆盖无提供者、提供者故障重读、多提供者未选、重复点击/限流、回调拒绝不重放且不清除旧账号、一次性参数丢失六场景。6项已通过；回执为工作区 `.runtime/authentication-errors-unit.json`。本文件通过服务替身验证页面交互，不能计为真实IdP或真实429验收。
3. 下一业务闭环建议为“同一真实Cookie管理员发邀请→受控通知渠道实际收到→浏览器打开→过期/撤销拒绝→重发新邀请成功→旧邀请保持无效”。需主任务分配专用浏览器异常fixture与源文件所有权，并串行排队；不在本次审计擅改共享runner或公共认证代码。
4. 随后单独补邀请状态/失败类别组件矩阵、人员详情名称回显与权限变更后UI恢复。清理/容量及外部条件保持独立待办，不能挡住引用目录/素材等并行开发，也不能由本表存在冒充已完成。
