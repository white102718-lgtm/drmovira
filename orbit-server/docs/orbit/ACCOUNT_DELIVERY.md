# 广告账户交付：首个可独立验证的导入闭环

遵循实施文档第七节A线接力。Python重新实现，原Java账户范围页面与证据不继承为本模块完成；参考仓库只读。当前处于开发中。主任务已在独立MySQL中迁移到013并接入真实HTTP专项；首次账户GET失败已修复，账户受理四组实际通过，不标整模块通过。

## 合同与最小范围

原FR-ACC-01保留账户18列、详情与来源；FR-ACC-02保留授权、同步、分配和本地解绑；FR-ACC-03保留批量导入。首阶段为“有效户商/投手选择→原始数字ID预检→持久化202受理→批次及逐token结果续页”。合法项在只读平台元数据处理前保持WAITING，不能展示绑定成功，也不能凭测试返回值预置生产账户。

随后接力受控只读元数据适配器→真实本地绑定→账户列表/详情；消费失败单独标FAILED/UNSYNCED，不撤销成功绑定。分配历史、OAuth、重试租约和完整18列扩展后续逐项实现，不把通用CRUD替代这些业务流程。

原始 `contracts/openapi.json` 与 `openapi-current.json` 的账户导入均只有GET `/api/v1/account-imports`、GET `/{id}`、POST `/{id}/retry`，没有可受理新批次的POST；两份合同没有可复用的户商导入创建接口。因此独立登记技术扩展，保持原ImportRequest不变：

- POST `/api/v1/account-imports`：仅四个必填属性 `vendor_id` UUID、`account_ids_text` 原始字符串1—20000码点、`owner_user_id` UUID、`owner_team_id` UUID；禁止actor/tenant/额外属性。CSRF与16—128可见ASCII幂等键必填。202返回原ImportBatch，不表示平台成功。
- GET `/api/v1/account-imports/capabilities`：会话CSRF及当前拥有者默认值；不泄露Token。
- GET `/api/v1/account-imports/owner-options?q&cursor`：当前可管理、已激活人员及团队名称，50项键集续页，不借用system人员管理权限。
- 原GET `/api/v1/account-imports/{id}` 增加cursor查询技术扩展：每次最多200行；原ImportBatch正文的十属性保持不变。
- 原GET `/api/v1/accounts` 与 `/{id}` 已编写只读目录服务，原Account/Page正文保持；暂不宣称18列补充字段均接通。当前筛选只接受实现了的参数，不静默吞掉日期等未实现筛选。

原ImportRequest仍只有 `account_ids_text/owner_user_id/owner_team_id`；不直接改其additionalProperties规则。前端保留原始文本；仅提示项数/字符数，逐项结果以Python服务端为准。

## 字段与状态约束

1. 先数原始非空token，包含重复项，上限500；文本总码点上限20000。分隔符为空白、换行、中英文逗号和分号。只去小写 `act_` 前缀，不把数字转Number、不去前导零、不做全角数字转换。
2. 导入入口严格1—32位ASCII数字；已同步账户存储允许1—64位，两者分别验收。每个token保留0基索引、1基行/列，CRLF按一行；raw_display最多128码点，完整原始输入保存在不可覆盖对象中并记录SHA256引用。
3. 首个有效token若索引0，重复项仍正确指向0。非法项INVALID不调用平台，重复项DUPLICATE不再次调用。DUPLICATE不计失败，ALREADY_EXISTS算成功但不重绑。尚有未终态时不能显示SUCCEEDED。
4. 元数据校验固定外部账户ID、原始名称、服务端币种白名单、有效IANA时区、账户/授权状态及有时区的观测时刻。账户UTC偏移按参考时刻计算夏令时。原账户名称原文留存；显示截断不能丢存储值。
5. 未知余额/消费为null，不以充值或其他金额推算、不补0。只读适配器未配置时固定503 `ACCOUNT_CONNECTOR_UNVERIFIED`，不虚构平台成功。当前尚未接通生产Meta读取。
6. VENDOR只复用最小引用目录；AVAILABLE、同租户同团队、调用者可读、目标owner在分配集合中必须同时满足。持久化批次冻结户商版本、actor、owner、scope和原始输入hash。新Worker已编写每次外部读取前及完成回写前复核，真实MySQL联合验收尚待执行。

## 数据与性能设计

012仅新建账户业务表，不修改公共组织或菜单表。当前账户唯一键 `(tenant_id,external_id)`；内部UUID与外部ID分离。普通用户 `(tenant_id,owner_user_id,id)`、团队 `(tenant_id,owner_team_id,id)`、户商/状态/名称前缀/登记时间各有索引。默认每页50，可选20/50/100/200，UUID keyset，不使用深OFFSET或把全表装入内存后过滤。

批次按owner/team/actor及状态建索引；行唯一 `(tenant_id,batch_id,token_index)`，每批最多500行，用executemany批量写入；读取201行判断是否还有下一页。认领按 `(state,next_attempt_at,tenant_id,id)`，120秒恢复索引独立。认领Worker已有实现待联合验收，索引存在不算恢复或性能验收。

账户游标签名绑定actor/租户/角色/团队/筛选/目录权限版本及账户水位；导入行游标绑定actor/租户/批次/权限版本，候选游标单独绑定OWNER用途与搜索词。任何旧范围不能借游标取回撤权对象。

短写事务锁定租户账户时钟，批次/行/幂等/审计/outbox原子提交。原始对象不可覆盖，在数据库提交前落盘；事务失败可能留下未引用对象，不能留下假成功业务记录。生产对象根只从指定私有 `.env.local` 的 `ORBIT_PYTHON_ACCOUNT_IMPORT_OBJECT_ROOT` 读取，必须事先存在且不含链接/重解析点。当前仅本机对象适配器，生产对象存储与未引用对象保留清理仍待实现。

账户归属历史采用 `[starts_at,ends_at)`，转移从账户当地下一业务日00:00生效，禁止重叠；同起点唯一约束不能代替锁定账户后的重叠校验。原参考项目使用重叠区间重复累计的口径，与本PRD不同，因此不复用该语义。本阶段仅建历史表，不声称分配流程已实现。

5万账户、100万事实真实容量尚未运行，不杜撰吞吐/延迟承诺。当前账户目录不读取广告事实表，后续消费汇总、覆盖率及来源需独立汇总表和真实执行计划/容量证据。

## 开发、测试、验收分列

| 子项 | 开发 | 测试 | 验收 | 证据/限制 |
| --- | --- | --- | --- | --- |
| 原始导入解析、状态汇总、只读元数据验证 | 已实现 | 专项纯逻辑通过 | 仅对应纯逻辑 | 不代表平台或数据库通过 |
| 原始输入本机对象完整性/不可覆盖 | 已实现 | 临时目录实际文件读写通过 | 仅对应对象子项 | 不代表生产对象存储通过 |
| 012业务表 | 已写入 | 主任务独立库已迁移至013 | 未整体验收 | 不包含014，迁移成功不等于业务通过 |
| 受理/幂等/范围/批次查询 | 已实现、实际缺陷已修 | 4组真实HTTP/MySQL通过 | 仅受理子流程通过 | `evidence/python-account-import-http.json`，不是平台绑定或完整模块验收 |
| 人员/户商选择与导入/结果弹窗 | 已实现待联调 | 类型检查及4项组件测试通过 | 未通过真实联调 | 服务替身只验证交互，不称全部账户页面完成 |
| 元数据Worker与本地绑定 | 已实现 | 6组真实MySQL/本机TLS通过 | 仅受控内部子流程通过 | evidence/python-account-worker-http.json；无真实Meta证明，非整模块 |
| 账户完整18列/详情/筛选 | 未完成 | 未运行 | 未通过 | 原Account只读目录代码不能替代补充字段与来源验收 |
| OAuth/同步/分配/解绑/重试恢复 | 未完成 | 未运行 | 未通过 | 不执行平台广告写入，本地解绑也需独立事务/确认 |
| 容量与外部Meta | 待实施/外部条件 | 未运行 | 未通过 | 原Java证据不继承 |

当前33项专项（合同27+真实本机对象6）通过，回执 `.runtime/account-foundation-unit.xml`；Ruff与格式通过，前端类型检查通过。4项导入组件专项通过，回执在工作区 `.runtime/accounts-import-ui-unit.json`：目标拥有者限定户商查询、原始文本/前导零提交、501重复项仍超限、未知结果保留意图/幂等键及无候选指引。首轮一项断言误把“当前不代表账户绑定成功”的警告文本判为宣称成功，保留 `accounts-import-ui-unit-attempt-01.json` 后改为直接核对“状态：已排队”，没有删除业务断言或模拟平台成功。主任务归档前应对最终源码重新登记指纹。

## 主任务接入与下一步

公共权限已由主任务登记accounts及ACCOUNT_CURSOR_V1/ACCOUNT_IMPORT_CURSOR_V1。013菜单、`account_routes.router` 与 `account_routes.accounts_router` 已由主任务注册，并使用隔离对象临时目录真实受测；未迁移旧Java预览。014与Worker已另轮真实验证，不属于迁移至013的受理回执范围。

新菜单视图入口 `orbit/accounts/index` 已有原Account只读字段的列表、筛选、游标分页、详情抽屉和导入入口。它尚未补齐原18列、日期/投手筛选、列设置和同步/分配/解绑等专门流程，必须继续开发；不能把当前入口可打开视为整个账户模块交付。

`run_account_import_checks(client,admin,headers,owner_user_id,owner_team_id,vendor_id,cases)` 由主任务串行执行，前置为B线提供当前可读且对目标owner已分配的AVAILABLE户商。覆盖真实持久化四种逐项结果、同键重放/不同意图冲突、500行三页/501原始项拒绝、审计注入失败时批次/行/幂等/事件/outbox全回滚。当前合法行保持WAITING，测试不会把入队当作绑定成功。

首次主任务session90629：POST202字段、原始行状态、duplicate_of=0及未知金额null已通过，随后GET批次未返回原响应。根因为公共 `_uuid(value,pointer)` 调用缺pointer导致TypeError/503，已统一修正账户入口、筛选及游标的调用；加入批次/账户/投手/户商无效ID必须422的真实HTTP检查。保留失败证据、不弱化原GET断言。修复复验后主任务已归档 `evidence/python-account-import-http.json`：2026-11-08T04:38:39.301126Z 四组实际全部通过。父整轮仍因渠道390px标题定位失败而FAIL，不能把账户分项通过表述为全回归通过；B独立复验由主任务负责。

## 第二阶段：唯一来源只读Worker（六组内部专项通过）

新增 `account_worker.py`、`account_platform.py`、014迁移、`tools/account_worker_checks.py`。未自动注册任务或启动无人值守调度，不触碰原预览，不调用平台写方法。根源协议依据官方SDK的 [Business只读账户边](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/business.py)、[AdAccount元数据字段](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adaccount.py) 和 [Graph异常结构](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/exceptions.py)；SDK信息不替代真实生产授权测试。

来源仅限当前租户唯一启用且READ_VERIFIED的META_BM。零个为SOURCE_REQUIRED、多个为SOURCE_AMBIGUOUS，不轮流猜Token；首次认领冻结source UUID/revision、actor auth版本、稳定批次request UUID，每次HTTP与回写实时复核。候选读取只允许官方HTTPS443，完整核验BM owned/client边授权后读取账户元数据，分页重建固定主机URL，不跟随带Token的nextURL。单请求15秒、BM预检总30秒、响应64KB、每边至多50000条、每批目标至多500项。平台只读异常不存原始响应和Token。

| 类别 | 后续动作 |
| --- | --- |
| 网络中断/超时、HTTP5xx、Graph瞬时1/2/is_transient、429或Graph限流4/17/32/613/80004 | 首次+最多3次重读，30/60/120秒加0—10秒抖动；第4次失败终态，不伪造成功 |
| 401/403、Graph10/190/200、BM不含目标 | 终态拒绝，不重试其他Token |
| 来源/户商/身份版本变化、撤权、元数据缺字段/错ID/无效时区币种、非HTTPS跳转/坏JSON | 终态失败，禁止本地绑定 |
| 已有同户商账户 | 仍校验本地权限及户商状态；ALREADY_EXISTS，不平台读取、不重分配 |
| 其他户商或已有归属冲突 | 冲突终态，不覆盖当前拥有者或历史 |
| FETCHING超过120秒 | revision+claim UUID栅栏撤销旧认领；有剩余次数才延迟重读，否则失败；不放宽任何广告写入UNKNOWN规则 |

完成事务遵循账户时钟→批次→行锁序；新账户唯一键、初始归属历史、行结果、批次汇总、审计/outbox原子提交。初始归属从账户当地绑定日00:00开始；后续分配仍须单独实现“下一业务日”规则。长原名完整保存，ImportRow仅截取255码点展示；无金额保持null，不将缺失元数据补0。现有无户商分支仅增加户商绑定，禁止转移归属，元数据冲突终止。

专用测试回执 `.runtime/account-worker-network-unit.xml`：本机真实TLS覆盖BM owned/client、固定主机分页、缺授权不探测账户、HTTP400限流/瞬时分类、失败不泄密、不重试内联、错误ID/缺字段/坏Unicode、长原名及读取前实时守卫。控制单测覆盖三档退避、限制值和已有绑定不绕过户商校验；会话替身不计数据库权限/锁验收。最终数目以该回执为准。

主任务串行调用 `run_account_worker_checks(client,admin,headers,cipher,owner_user_id,owner_team_id,vendor_id,database,cases)`；需新独立库迁移至014、真实AVAILABLE且已分配户商、独立导入对象根。六组计划为零/多来源无请求、真实本机TLS+MySQL原子绑定/初始历史、已有绑定不读平台不转移、读取后来源变化拒绝回写、审计回滚+租约恢复、首次加3次有限重试。夹具READ_VERIFIED仅人工创建的受控协议前提，不算真实Meta验证。工具限制loopback13306及本轮独立库，最终清理独占触发器并恢复原测试来源启用状态。六组已由主任务于2026-11-08T04:50:14.796206Z真实执行PASS，回执 `evidence/python-account-worker-http.json`。父整轮素材编译失败仍保留FAIL，不扩大六组分项范围；真实Meta及无人值守任务未测/未启用。

多来源后续技术扩展提案（未实现）：独立GET `/api/v1/account-imports/source-options`，以accounts.import鉴权，返回可读已验证来源id/name/revision，不返回secret；独立创建schema增加显式source_id/revision并冻结，不改变原ImportRequest，不静默切换既有批次。需主任务确认接口和UI后单独闭环。

014六组内部专项通过后，继续账户18列、日期/投手筛选、同步/分配/解绑、OAuth及三视口页面验收；真实Meta与容量仍未测，不因本机协议通过而打勾。

## 原18列与详情的下一闭环设计（未实现）

已核对原 `openapi-current.json`：`Account`仅14属性且additionalProperties=false；GET `/accounts/{id}`只能保持该正文。原 `/accounts/{id}/identities` 已有AccountIdentities合同，身份资源必须复用该路径，不能用空数组加当前时间伪造已观测。原合同未提供AccountDetails或 `/details`，故缺列需独立补充技术schema，由主任务裁决接入；下表仅为覆盖设计，不算已开发。

| 原列 | 现有可用来源 | 下一步缺口/未知语义 |
| --- | --- | --- |
| 投放师 | ownership.owner_user_id | 显示当前可读人员名称；历史日期与事实归属分开 |
| 名称/ID | name/external_id | 完整原名可查看，不把截断展示当原始值 |
| 户商 | vendor_id/vendor_alias | 冻结导入别名与当前引用变化策略明确，不额外越权查详情 |
| 个号名称 | 无 | 平台来源未观测保持null，不用BM配置名称代替 |
| 所属主体 | 无 | 平台业务主体观测与名称/ID分别保留 |
| 账户状态 | account_status | 只读状态来源/时间及异常码分开 |
| 授权状态 | auth_status | AUTHORIZED须授权范围核验，不等同Token存在 |
| 付费类型 | 无 | 原始平台枚举与显示映射；未知null |
| 余额 | balance | Observation含币种、状态、来源、时间，未知amount=null |
| 应付账单 | 无 | 独立Observation，不从余额/充值推算 |
| 总花费 | 无 | 平台累计值与查询窗口消费分开，禁止相互替代 |
| 付费方式 | 无 | 只保留业务需要的非敏感摘要，不持久银行卡凭据 |
| 消耗 | spend | 后续事实汇总/覆盖率独立，不以账户metadata补0 |
| 消耗时间 | spend.observed_at/business_date | 统计业务日、拉取观测时刻分别展示 |
| BM/主页/像素 | 原AccountIdentities接口尚未实现 | 真实分页资源快照，不用来源BM配置冒充全部身份资产 |
| 时区 | timezone | IANA持久化、参考时刻计算夏令时 |
| 封禁原因 | 无 | 原始平台code+说明+观测时刻；无信息未提供 |
| 操作 | 当前仅导入入口 | OAuth/同步/分配/本地解绑逐项动作权限和确认弹窗 |

详情额外保留授权时间、本地解绑时间、封禁观测时间、最近同步、备注、各金额来源/更新时间。字段应按观测存储而非在GET中实时并发请求平台；每次只取当前页<=200个账户的索引观测，禁止每行N+1查引用/平台。金额未提供和过期分开，历史观测保留水位，不覆盖为0。新增观测表/索引需后续主任务分配迁移编号。

日期已通过原型明确：`ORBIT原型.html:806—807/812/974—980` 按每账户IANA当地业务日筛消耗，默认各账户当地今天；账单/累计总花费不受窗口影响，不因无消费排除账户。不能按created_at/synced_at过滤。当前户商代称还须遵照 `reference/03_原合同保留章节.md:32` 批量实时关联，导入/审计继续冻结历史快照。投手筛选已有operator_user_id实现，前端选择器和当前范围交集需接入；18列与列设置、详情、原identities接口、事实索引/快照/游标及三视口的详细下一闭环见 [ACCOUNT_DETAILS_DESIGN.md](ACCOUNT_DETAILS_DESIGN.md)。该文档为设计，不算功能完成。


## 第三阶段：18列独立扩展实施中

新增 `account_details_contract.py/account_details_store.py/account_details_routes.py` 与015迁移；新router未注册到application，未修改冻结的既有账户代码和前端。原Account14字段/AccountIdentities不变。新extended/details读模型按当前账户范围分页，日消费再按冻结事实归属求权限交集；日期窗口不影响无消费账户成员或账单/累计值。JSON_TABLE一次关联当前页各账户窗口，发布以至多1000个精确日键关联归属历史，批量读取旧版本及executemany写当前/历史，不逐日N+1或加载账户全历史。目录、账户、观测、权限与参考时刻共同绑定独立游标。

015的日事实与附加字段只能经内部 `AccountDetailsStore.publish` 显式事务、accounts.sync、CAS水位发布，无浏览器手工金额接口。来源/观测时间校验、迟到拒绝、半开区间归属派生、审计/outbox与当前/历史同事务；完整覆盖才返回真实零，部分/未采集保持null，Decimal合计超原金额合同拒绝而不四舍五入。

参考目录仅name<=255，没有明确定义的alias；新details.vendor_display显示可读当前完整name及REFERENCE_CATALOG来源，原vendor_alias保持null并给ALIAS_NOT_MAPPED，不能按name长度推断代称或截断原名。真正代称数据源仍为明确缺口，不计原“户商代称”验收完成。身份资源、生产事实采集、授权时间、备注编辑等也仍待后续真实来源接通；不把null结构当采集完成。

专用40项（合同34+读模型控制6）PASS，`.runtime/account-details-unit.xml`，Ruff/格式通过；首次控制测试替身漏actor_id导致1失败，保留attempt-01后修正替身字段，原游标失效断言完整。`tools/account_details_checks.py` 已准备8组真实MySQL/HTTP工具，尚未运行：原14字段/未知、日汇总真实零与缺失、日期不改账单/成员、游标/发布失效、实时引用名但不伪造alias、迟到拒绝、审计全回滚、非法日期/不可见ID。待主任务登记新MAC用途并接路由、迁移015后串行执行；当前不计数据库或页面验收。

后续实际结果补记（不覆盖上述历史）：015初轮JSON_TABLE归属锁出现errno3569，修为仅物理表 `FOR SHARE OF h`/`FOR UPDATE OF f` 后主任务86455快速14/14通过。该回执不覆盖异常日内或迟到归属；零点猜归属缺陷另经合同核对纠正到018，不能因原8组PASS冒充该边界验收。

## 第四阶段：018归属冻结、旧接口一致性与18列前端

WORKFLOWS:13、PERMISSIONS:18、DOMAIN:31/35明确历史冻结及独立双人更正。主任务已裁决：新日事实仅唯一assignment覆盖整个有效日窗口（当天截至观测时刻、完整历史日截至当地次日00）才归属，否则UNASSIGNED；已有日补采复制原owner/team/attribution_version，不能按变化后的区间重算。018增加冻结版本/原因，不改015；DST窗口按IANA的23/25小时计算。初次绑定Worker本来已按当地绑定日00，不改成精确now。

原Account列表/详情现已共用扩展观测读模型，仍严格14属性，列表日期同窗口消费语义；主任务真实018首轮中原core与extended一致性组已通过。新增read-only owner-options不借import/system.users权限，但首次真实bootstrap display_name=NULL被LIKE'%'排除；依既有user_store合同修为实名→原昵称→原用户名回退，新候选与批量owner_display共用表达式，await主线复验。没有把该错误猜成500或删除断言。

账户相关85项（含12项归属边界）纯逻辑通过；真实专属工具现13组，018异常归属/迟到冻结/DST末尾组尚待主线执行结果。当前A专属后端与工具已冻结，不自行启动测试库或共享服务。

前端18列、日期/取消确认、列设置、详情、原身份只读入口已落盘；仅列ID偏好持久化，未知金额不补0，读取失败不假装空资源。最终同一冻结源码全前端111/111通过（`.runtime/account-details-full-current.json`），其中新详情7项+导入4项；类型与格式通过。首次主线110/111时报告结束比最终未知提示文案修正早约12秒，保留失败回执，最终全套重新执行而非拿单测替代全套。

`tests/e2e/orbit-python-accounts.spec.ts`已准备真实三视口，使用可见Element Plus label点击并断言隐藏input状态，无force或放宽超时；尚未运行。原身份后端、生产事实采集、OAuth/同步/分配/备注/解绑、容量以及真实代称源接入均还有未完成项；017真实alias已由B完成，下一后端解冻后接入，不把name或null占位当完整代称需求。

后续实际复验：`evidence/python-account-attribution-http.json` 于2026-11-08T05:49:01.422624Z记录27/27真实通过，含13详情组、真实初始化及登出等准备组，覆盖NULL姓名回退、core同窗一致、异常日内UNASSIGNED、迟到冻结与DST。主任务随后报告24029全量253/253（252后台+账户三视口汇总1、3个实际Playwright测试）通过；当前<=018和该前端继续冻结等待主线提交。该阶段没有完成原身份采集、业务写动作或所有外测，整模块仍不勾验收。020仅新增未接入文件/设计/独立工具，不能把其10纯测合并成020真实通过。

## 第五阶段：020真实代称接线已就绪，真实专项排队

主任务已提交推送前阶段 server `9b1409b7` / web `8378c3d`。上一节“尚未运行”的三视口及A27已由后续回执覆盖：253/253全量含3个账户实际Playwright视口通过；该证据不覆盖020新修改，也不代表原身份资源或全部账户动作已完成。

020现在已接真实业务调用点：受理事务在IMPORT_ACCEPTED前冻结IMPORT；Worker在实际本地绑定事务内冻结ACCOUNT_BINDING和IMPORT_ASSIGNMENT（初始归属沿用accounts.import，不追加accounts.assign）。原幂等回放直接返回保存响应，不重新捕获；已有同户商ALREADY_EXISTS不重分配。所有快照与原业务、审计和outbox同事务，仅INSERT、不回填旧对象。B原动作冻结助手实时复核身份、租户、VENDOR资料指纹及范围；import-only不调用accounts.read显示resolver。

当前列表/详情每页批量读取真实alias，原Account仍14字段；当前完整资料name独立保留，不推断或截断为代称。扩展vendor_display给alias_source/revision，未知null分别说明UNSET、NOT_VISIBLE，历史缺行仍为“当时未采集”。reference_clock改变使原与扩展游标409。

当前纯逻辑118/118通过（`.runtime/account-alias-integration-unit.xml`，含A10及B21）；前端详情与导入11/11通过（web `.runtime/account-alias-ui-unit.json`），类型/格式/Ruff通过。这些替身结果不计真实020权限或事务验收。

`tools/account_alias_snapshot_checks.py::run_account_alias_snapshot_checks(client,admin,headers,import_identity,vendor_id,database,cases)`已冻结交主线串行，6组尚未执行：从未设置NULL+UNSET、改代称不改历史、幂等重放、无read的import-only、快照写与审计写故障整笔回滚并同键重试、core/extended一致及两种旧游标失效。需要through020、独占从未设置alias的VENDOR、同团队root与import-only两拥有者、至少21可见账户。工具守卫本轮UUID独立库及loopback13306，无外网平台调用；仅用无效token受理以避免把伪平台资料计成功。旧Worker6组另增加绑定/初始归属快照及审计回滚断言，也需through020重新执行。

下一个有界闭环为原GET `/accounts/{id}/identities`：目前后端404，前端明确失败只证明错误呈现，不算功能。应保留原AccountIdentities严格schema，以真实观察快照读取、accounts.read与当前账户范围、原ResourceCapability为边界；未同步返回明确503，不补空资源加当前时间冒充已同步。原身份生产采集、OAuth/同步/分配/备注/解绑、容量与外部真实Meta依然未完成。

## 第六阶段：023身份只读闭环已准备，未计真实验收

新增独立身份合同、store/router、023受信证据/当前头/历史/资源表和9组真实协议工具。51纯测通过，Ruff/格式通过；尚未注册router或执行真实MySQL/HTTP专项。核心边界是原四字段返回、accounts.read与当前账户范围、未同步503、真实证据摘要/账户授权版本/来源版本、已知撤销或到期失败关闭。没有默认TTL或随意version即可信的发布途径，生产采集/权威registry未接入保持明确缺口。详见ACCOUNT_DETAILS_DESIGN第十一节；020仍先等主线六组真实专项，二者不混记通过。

后续真实回执：主线 `evidence/python-account-identities-http.json` 已实际52/52通过（020+023组合，非真实Meta）；`python-account-identities-browser.json` 后续A56通过：55后台/初始化+三视口聚合1，含3个实际Playwright视口。旧“尚未注册/未执行”保留为阶段历史，不再代表当前状态。账户页面真实UNKNOWN夹具精确返回503 ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE（没有修改事实凑UNSYNCED），原身份9组独立ACTIVE/AUTHORIZED夹具另证未同步503 ACCOUNT_IDENTITIES_UNSYNCED。浏览器等待实际响应并断言code，保留错误呈现、无假空结果、按钮可重试；首轮主线harness夹具变量未绑定失败已保留，修复后复验，不属于产品成功记录。生产身份collector、权威registry与即时写授权核验仍未接入，不标整体验收。

## 第七阶段：025原跨页范围独立实现，真实集成排队

按原WORKFLOWS:125实现IDS/FILTER互斥，原ScopeSnapshot五字段与ScopeMember三字段保持；IDS原始最多50000且非空，FILTER必须完整五项筛选。解析拒绝重复键/重复ID/错误类型，复用原账户filters与新唯一account_selection SQLbuilder；原目录读取已在获准窗口改用同一builder，名称/数字/act_、转义前缀、status/auth/operator/vendor语义保持一致，不另写筛选体系。

025新增范围头/成员/成功审计/outbox。创建持有当前业务授权及账户时钟共享锁，在一个事务中按UUID每块最多1000取原账户与写入成员，用流式SHA冻结完整成员；IDS每块只发当块1000ID，FILTER遇到第50001明确422且全部回滚，不截断或一次把5万长名加载进内存。创建范围不修改账户目录时钟，避免共享锁升级；范围有独立同事务审计/outbox。原动作幂等与同actor键绑定，重放也重新核权限与完整冻结可见性，故障不能留ready或虚假审计成功。

scope_version使用真实sys_identity_subject.auth_version，另绑定当前人员/租户/角色/团队/显式管理团队指纹。账户改名或指标/账户目录时钟变化不自行令冻结IDs失效，也不改原冻结名称；权限变化和任一成员越权整份409。成员20/50/100/200键集分页，游标签筛选/人员/快照/页大小，名称和外部ID查询冻结值。内部resolve_for_plan重核当前accounts.read、原创建者与授权、1至500、不截断、冻结owner/team/currency与当前及目标交集；普通name/revision变化不当作新的失效规则。计划的snapshot与非空account_ids互斥由原launch合同先校验，不能把相等ID同时提交作为例外。草稿展开不等于资源预检或广告写授权。

获主线确认的技术辅助GET /scope-snapshots/capabilities只回csrf_token/max_members/max_plan_accounts，严格accounts.read，不借import；全局ORBIT边界提供no-store与request_id，静态路径优先注册。原POST仍201、CSRF和幂等头必填；真正跨租户SUPER X-Target-Tenant目前共享上下文未实现，本闭环明确403并登记缺口，不绕过统一授权。成员接口原OpenAPI沿用了channel/date/metric/entity等通用参数，但没有冻结账户成员上的对应语义，当前仅q/page_size/cursor，其余明确UNKNOWN_FIELD，不默默接受假筛选，待统一补齐或裁决。

28项范围纯测试通过（`.runtime/account-scope-unit.xml`）：含原DTO实际构造50000、原始50001拒绝、1001流式块与摘要、不可见无ready、FILTER第50001控制、计划上限/归属币种/改名边界。首次4失败为会话替身漏data_role，保留attempt-01后补正确上下文，不删除断言。原详情/归属与新解析相关68纯测通过（`.runtime/account-scope-selection-unit.xml`）。这都不是5万真实容量验收。

真实tools/account_scope_checks.py十组已准备未执行，521受控SQL账户，不与主线50k/1m容量工具重复：原FILTER完整冻结、IDS规范幂等、非法/不可见不部分成功、改名续页保留冻结值、521计划限制、计划归属/币种动作重核、不同正文幂等冲突、成员及审计触发器整笔回滚、read-only无import取得本接口CSRF并POST、foreign/撤read/成员转属失败关闭。readonly_identity须独占单角色USER且只有accounts.read；迁移025/router由主线串行接入，当前未计真实通过。account_details_store及account_selection已按真实容量窗口冻结，独立025文件不注册共享应用。

025前端后续接线：主线已把旧范围API与两个页面交由A维护，改为Python /capabilities；原重试幂等、取消、迟到与权限失效保护保留。IDS大小写等价重复明确DUPLICATE_VALUE/422提示，不静默Set去重。原账户页增加router.push('/orbit/account-scopes')入口；主线使用027的隐藏二级菜单31016，不复用已是读取动作的31011，也不新增第九个一级业务菜单。成员弹窗以唯一局部类限制到视口内，body滚动而页脚仍可操作。

相关前端20/20纯测试通过（web `.runtime/python-scope-ui-unit.json`，含旧范围、账户18列/导入回归及新增接线/重复/入口断言），类型与最终Prettier通过。新Python scopes三视口spec已交主线未执行：真实账户入口→521 FILTER→成员分页/搜索→取消不选/确认→变更条件清除→重复ID无POST→单ID真实冻结→清除，并检查弹窗几何与截图。025未受测专属工具中的普通改名已按主线同意保留marker前缀，仅改变名称内容/revision，继续断言历史name不改；不修改真实筛选事实凑数量。共享路由/layout/playwright配置未由A修改，全部后台及前端现在冻结等待主线串行实际验收。

025排队期间主线容量专项已实际完成，回执evidence/python-account-capacity-http.json及python-account-capacity-metrics.json：50,000账户/1,000,000日事实、250页完整遍历无漏重、20并发200HTTP样本、P95约0.542秒（原目标≤1秒）、错误0、原13详情组通过。仅当前机器上的单owner首读/暖读场景，装载后缓存可能已热，没有真实冷缓存、所有报表/范围冻结/任务或全部多租户容量的结论；保留首次attempt记录，不据此勾全部容量验收。新增028守卫尚未接旧读模型，不属于该容量源码验收范围。

## 第八阶段：028分配、只读同步任务、本地解绑首检查点

原Assignment严格operator_user_id/owner_team_id/vendor_id可null/effective_from/reason，原同步和解绑仅Reason；三动作都要求CSRF、If-Match、幂等及对应当前权限/账户范围。批准独立技术GET actions/capabilities按指定原动作授权，固定csrf_token/revision/next_effective_from，不借accounts.read/import。服务端每次提交重新计算IANA下一当地日零点；不信旧caps时刻/客户端时区。额外微秒不截成零点，DST23/25小时按IANA；不存在的墙钟午夜明确拒绝，不猜UTC偏移。

主线已裁决未来归属方案：受理同事务结束当前区间到未来边界并建立未来区间与SCHEDULED命令，当前owner投影在边界前保留旧值。新独立Worker到期重核原actor当前动作/源账户范围、目标启用人员/团队/AVAILABLE户商交集、原owner/vendor及冻结时区/币种、未来区间一致性，别名接受与激活分别冻结版本1/2。只改当前投影，不改历史日事实；权限/来源/区间漂移进入BLOCKED并保留active_kind，必须显式恢复。原幂等Ack是原受理回执，不是实时任务状态；阶段源码没有无人值守托管。

保护链路必须后续接到每个账户读取、scope、计划来源、采集前：到期未追平则503，绝不沿旧owner过滤放行或漏掉应转入账户。新单对象require_projection_current和租户保守require_tenant_projections_current已准备但尚未接共享入口；后者通过未完成分配到期索引查存在性，不让每个GET升级全租户写锁串行20并发。真实保护链路、到期多时区/异常恢复属于下一必做闭环，不把SCHEDULED首检查点当分配完整验收。

同步当前只持久WAITING_EXECUTOR命令，冻结唯一启用READ_VERIFIED来源ID/版本；0或多来源、坏结构/缺密文Token明确503，不猜Token。未执行不修改synced_at/spend/余额或伪造SYNCED。真实只读执行器尚未接入，last_error_code明确ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED，仍是未完成项。解绑只记本地时间、结束当前区间、终止未执行SYNC、保留平台状态/历史/事实/全局凭据，不发广告删除；存在未来分配时冲突拒绝，不静默撤销调度。普通改名不阻断到期，时区/币种或业务归属漂移必须阻断。

33项原字段/头/时间/控制纯测试通过（.runtime/account-actions-unit.xml），Ruff/格式通过。首次Worker一失败为测试审计参数下标取成request_id，保留attempt-01后修替身，业务断言未删。独立tools/account_actions_checks.py十二组真实MySQL/HTTP工具已准备未执行：future受理旧owner保留、Ack/CAS/幂等、非边界拒绝、受控时钟推进与alias双快照、actions-only无read/import、撤权BLOCKED显式恢复、受理/激活审计触发器回滚、来源0/2拒绝、持久同步不假成功、本地解绑保留历史。需主线准备真实actions-only TEAM_ADMIN显式管理团队，以及AVAILABLE且对root/目标投手可读的VENDOR；不访问真实Graph，受控未来时间不等于真实日历跨日。新028 router/迁移尚未接主线，真实测试/验收均未勾选。

## 第九阶段：029真实只读同步持久执行协议（独立未集成）

028已按主线要求冻结，新增029仅扩展只读SYNC认领/尝试/租约字段与索引，不修改原受理回执或启动任何调度。独立AccountSyncWorker每轮必须显式指定真实租户，有界1至100条；默认实际MetaAccountPlatform，固定官方HTTPS、真实BM owned/client账户范围预检及目标元数据读取。短事务认领后才释放锁发送HTTP，每个实际HTTP与最终回写重新核原发起人当前accounts.sync、同身份/租户、真实授权版本、当前账户可见/未解绑、冻结归属、到期投影守卫、来源ID/版本/READ_VERIFIED/密文Token；不是信任认领时缓存的授权。

单次claim UUID+命令版本+账户CAS版本防止旧执行者落库。首次加3次只读重试，30/60/120秒三档，第四次失败终态，限流/瞬时网络只读错误才允许有界重读；来源/授权/归属/账户版本漂移及无效资料终态拒绝。120秒过期只读租约回收先转退避，再由后续明确调用执行，不在关闭/取消时立刻重发。这里没有真实广告写入UNKNOWN重发逻辑。成功元数据、命令终态、账户审计/outbox/水位同事务；审计失败整笔回滚。生产无人值守托管、公共任务当前状态页及启动入口尚未接通。

只更新实际返回且验证的名称、平台状态、授权状态、来源/observed_at与账户版本，不写金额零值，不改已有日事实/冻结归属/余额观测。主线已裁决实际币种或IANA时区变化失败关闭ACCOUNT_METADATA_RECONCILIATION_REQUIRED；尚无专门元数据更正合同，需人工核对并后续明确更正流程，不能为同步成功偷改历史日窗口/未来分配边界。未来或迟到observed_at拒绝，原Ack幂等重放仍保持原受理含义，不冒充当前任务状态。

新增36项同步专用纯测试PASS（.runtime/account-actions-sync-unit.xml），Ruff/格式通过：重试预算、同租户同账户claim栅栏、终态/过期拒绝、每HTTP授权/当前范围/源/版本检查、撤权压过可重试网络失败、金额/历史不回写、取消不重发、资料更正/观测时刻边界。会话与平台替身仅证明控制协议，不替代真实MySQL/HTTPS验证。

tools/account_actions_sync_checks.py九组真实MySQL+HTTP+本机TLS工具已准备、尚未执行：实际元数据与原core/extended一致、四次限流与三档退避、来源在发送/回写前变化、账户版本栅栏、租约恢复与旧claim失效、actions-only原人员停用阻断HTTP、在途读取不能复活本地解绑、真实审计触发器回滚及受控恢复、时区更正拒绝。调用run_account_sync_checks(client,admin,headers,cipher,owner_user_id,owner_team_id,action_identity,database,cases)，沿本轮UUID测试库与独占TLS夹具，来源只用加密测试Token并恢复原启用标志，不访问生产Meta。由主线串行迁移029并运行；028十二组与029九组不得混算为已通过。

tools/account_action_fixture.py已提供唯一actions-only TEAM_ADMIN真实身份准备函数：真实roles API只授assign/sync/unbind，独占nativeID990102须未占用，显式管理传入同租户启用团队；正常登录后证明extended/import均403。主线统一调用，不由本线启动共享服务或测试库。

主线后续实际范围容量44/44PASS：5万范围冻结3.697秒、250成员页总177.59秒，完整成员hash一致且零漏重；同轮账户20并发暖读P95约0.427秒。回执evidence/python-account-scope-capacity-http.json及python-account-scope-capacity-metrics.json。当前每页重核全体5万成员可见性保持正确但代价高；仅只读提出未来游标绑定account_clock、仍实时核授权指纹的优化，未修改本轮冻结025源码或以性能跳过实时撤权。

独立前端src/api/orbit/account-actions.ts和AccountActionDialog.vue实现SYNC/UNBIND原Reason弹窗、对应动作capabilities、CSRF/CAS/幂等、明确原受理Ack与本地解绑边界。网络/5xx/坏回执不确定时锁正文和原key，关闭重开同账户同动作仍保留内存中的原意图，不刷新caps偷换版本；成功才清意图并发accepted。初次确定4xx不发成功事件，允许重新读取权限/版本。NFC后按Unicode码点1至1000，末尾换行/隐藏格式/控制字符拒绝，不用trim悄悄吞掉；未知金额/生产执行不伪成功。新组件尚未挂到冻结account/index，无真实浏览器验收。

专属前端9/9替身测试PASS（web .runtime/account-actions-ui-unit.json），类型与格式通过；范围含原路径/头/Reason字段、严格4字段与状态回执、取消、明确受理文案、Unicode边界、能力失败与403、网络原意图关闭重开重试、迟到能力不能覆盖新账户/动作。父页面真实按钮接线/动作权限展示/三视口待后续主线窗口。

主线批准独立分配候选GET /accounts/{id}/assignment-options及ACCOUNT_ASSIGNMENT_OPTIONS_CURSOR_V1用途。kind严格OWNER或VENDOR；VENDOR必须明确owner_user_id，团队只从真实目标人员查，OWNER禁止owner参数；q最多100码点、20/50/100/200页、UUID键集。先accounts.assign+当前源账户范围/到期守卫，OWNER仅同租户启用/激活人员、本人或显式可管理团队；VENDOR进一步要求同目标团队、AVAILABLE、同时对当前actor与目标owner可读，批量真实alias来源不回退name。候选仅当前最小资料，不承诺稍后仍可执行；提交仍独立CAS/权限/归属重验。

新独立account_assignment_options.py和_routes.py已完成16项纯测PASS（.runtime/account-assignment-options-unit.xml），Ruff/格式通过。游标绑定原账户/版本、真实auth_version/人员角色团队/显式管理团队、目录与引用时钟、kind/target/q/pageSize；既有sharedclock守卫接通后，到期投影未追平须503。新router尚未注册、真实HTTP专项未运行；028/029本轮不可据此增加已验收数量。当前VENDOR类别/目标团队/owner覆盖索引与键集复用真实引用结构，名称前缀需后续多户商容量EXPLAIN核对，不能把有界返回数量称作无界扫描已解决。

tools/account_assignment_options_checks.py另备5组真实专项未执行，独占native990200至990221均先验证未占用，创建本轮21同管理团队启用人员及1外团队人员，真实20+1分页、当前停用排除、VENDOR目标交集与真实alias、外源/外owner404、重复/未知参数及游标签q/源账户版本。A新增同步36+候选16合并52纯测再次通过（.runtime/account-sync-options-unit.xml），未启动任何共享数据库或浏览器。

全局到期守卫接线前的只读审查已回报主线：正式core/extended/owner候选、观测publish、identities、scope、launch账户源都经account_access.clock；旧导入Worker的lock_batch自取账户clock、preflight完全不取clock，需单独接保护。preflight须先clock共享锁/到期保护再batch/row，不能在已锁batch后补clock反转complete锁序。真正assignment恢复只用自身clock SQL和B alias/auth helper，不经过公共clock，因此不会被自己的全局guard阻断；029同步另有目标账户到期保护。此处是待主线实现/真实复验的审查结论，不虚标完成。

主线随后已接shared account_access.clock到期门禁。本线按开放窗口补旧导入Worker：lock_batch持clockX后全租户dueguard；preflight最先clock SHARE与同可信aware UTC门禁，然后batch/row，保护认领、回写及每个实际HTTP，且不反转锁序。029解密Orbit503也定点改为SOURCE_UNAVAILABLE，未把来源缺失误报授权变更；到期专用码仍保留。最新37同步+2新锁序控制+8旧Worker控制共47纯测PASS（.runtime/account-projection-sync-unit.xml），代码再次freeze等待真实专项。

独立tools/account_projection_checks.py新增6真实组准备未执行：原/扩展/详情/投手/identities读、scope新冻结与已冻成员、launch账户源及受控观测发布、import受理和旧Worker发送前都应503，随后独立assignment恢复器可推进而不自锁，旧owner立即404/旧scope409。夹具在隔离库明确预置合法NY历史昨天至今天零点的归属与持久SCHEDULED命令，不改服务器时钟、不调用生产Graph，不把预置历史冒充真实跨日或原受理HTTP验收；受理合同另由028十二组证明。函数所需020 target、025只读身份由主线复用，source全保持本轮隔离。尚未真实运行，不勾完整归属验收。

## 第十阶段：分配弹窗、真实回归失败留痕与后续任务边界

主线A首轮92计划中63PASS/1FAIL/28未跑，回执python-account-actions-sync-projection-attempt-01.json；失败为028专项两个META_BM受控来源同name撞001的uk_orbit_configuration_name(tenant_id,section,name)。仅工具改为参数化名称加自身source UUID，未改唯一约束或业务断言。第02轮66PASS/1FAIL/25未跑，主线确认028十二真实组全部通过；029首目标命令未成SUCCEEDED，仍未知具体错误码，不能因processed=1推断目标成功或假设一定旧队列。

029工具已加固定安全诊断processed/initial_pending_count/target_state/attempt_count/last_error_code/graph_request_count，不打印Token、SQL参数或externalID。先读取本轮真实旧可执行队列，经同一Worker有界按原序处理，并核旧任务明确失败关闭且无HTTP；不跳过队列、不改生产Worker优先级、不提前未到期重试。028末自身SYNC已unbind取消，因此旧队列仅是需取证的可能性，不当作已确认根因。新增工具修订freeze等待主线复验，029/到期保护目前仍未PASS。

独立前端account-assignment.ts及AccountAssignmentDialog.vue完成原五字段分配：OWNER/AVAILABLE VENDOR候选联动、真实最小团队名、明确选户商或null；生效时刻只读采用服务器返回并按账户IANA显示。换投手即清旧户商，迟到候选不串投手；固定UTC时刻、团队、人员、户商、原因与CAS/幂等同意图，网络未知关闭重开仍重试原意图。SCHEDULED只报未来受理，不把当前owner提前变更；明确409可重新取权限/服务端时刻，不偷偷换旧重试。NFC/Unicode1000码点、控制字符、无选择、无变化、取消、坏回执均不伪成功。

专属分配UI/SDK9项替身测试PASS（web .runtime/account-assignment-ui-unit.json），类型/格式通过；尚未挂冻结父页面或真实浏览器。加上前一SYNC/UNBIND9项只代表独立组件协议，不把总18项当原全部动作已验收。

主线已裁决FIELDS“仅管理员分配operator”与PERMISSIONS功能模板可调整的具体解释：保留显式accounts.assign+数据范围，不额外硬编码数据角色；USER被明确授动作时仍只能本人，无法分给别人，只有TEAM/SUPER可管理他人；本人可用户商变更仍需原动作/范围。此解释记录，不临时修改受测权限逻辑。

统一任务只读合同核对：原/api/v1/tasks及详情/nodes/events要求tasks.read；cancel要求tasks.cancel，retry/resume要求tasks.retry。任务继承计划/建议owner/team，不能以Worker或“知道request_id”扩大范围；request_id是响应头/错误/事件关联，不等于TaskID或查询授权。原Task.state无SCHEDULED/WAITING_EXECUTOR、TaskNode.kind无SYNC/ASSIGNMENT，不能直接伪装原Task；Ack.id当前为账户UUID的已受测语义也不能偷改。账户独立异步命令无原唯一任务归属映射，需单独明确脱敏诊断DTO/归属权限及command→task关联；未批准前未写新status端点，原Task能力仍待完整实施。广告写UNKNOWN双人tasks.reconcile核验也不移作只读lease重试。

后续主线真实复验最终92/92PASS，15.54秒，回执evidence/python-account-actions-sync-projection-http.json，包含原账户/身份/范围/元数据回归和028动作12、029同步9、到期保护6。四轮失败回执全部保留：第01轮配置名称夹具冲突；第02轮首同步组断言失败未有目标诊断，旧队列仅当时假设；第03轮实际目标SUCCEEDED/attempt1/error=null/graph2/initial_pending=0，已排除旧队列；第04轮core/details均200，定位两个独立GET完整JSON等值误把timezone.reference_at要求同刻。最终工具固定differing_keys证明只有该时间字段差异，原14字段及timezone4字段严格，其他业务值逐字段精确相等；每次reference独立落本次DB UTC窗口并验证IANA偏移/标签/TODAY日窗口。不改生产时钟/返回值或放宽其他字段来凑通过。

该92只证明受控本地MySQL/HTTP/TLS协议、未来分配区间/投影守卫/恢复与真实读取事务；不证明生产Meta凭据可用、无人值守托管、真实日历跨日或整个账户模块验收。前文“待执行”保留为阶段历史，以上回执为当前该专项结果；options5、账户动作真实前端三视口、OAuth、备注、历史展示/统一任务及外部实测等仍未完成。

账户父页面动作入口已接独立两个弹窗，原18列/日期/列设置/分页/范围/导入/详情保留。操作列140px用原生ElementPlus下拉，按当前若依明确permissions分别显示assign/sync/unbind，并在command回调复查；不靠角色名授权，不逐行发权限N+1。打开和提交仍由Python实时动作/对象范围校验。accepted只刷新当前读取，不提前改owner或金额；未知关闭重开因组件保持挂载而沿原key/CAS/正文恢复。

相关账户前端35/35纯测PASS（web .runtime/account-actions-page-unit.json），包括旧18列/详情/导入、两个动作组件及SDK、实际父页动作权限入口/撤权/受理刷新/未知恢复；vue-tsc和Prettier通过。首轮34/35的新断言把UNSYNCED fixture误期望“未提供/未知”，保留attempt-01后改为真实“未同步”且明确无0 USD，不删除业务检查。当前前端freeze交主线接真实浏览器；这些替身测不计浏览器或平台验收。


### 第七节身份页面与指标窄读取（2026-11-09 02:34，北京时间）

身份原GET与独立有效发行fixture接现有Drawer，实际19/19组合通过，三视口3/3、15.19秒；总86.67秒含原限流自然冷却59.62秒，未清空或放宽限流。按完整外部ID筛选、原18列、详情读取/刷新四或五字段精确DTO、资源可用性/原因/时刻、关闭原行不变、零账户写/零浏览器Meta请求。原列表UNSYNCED摘要缺口继续保留，未假改状态。证据evidence/python-identity-publication053-three-viewports.json。仅新增专属spec/测试配置，页面源码未改；两文件Prettier和前端类型检查通过，旧713纯测沿原冻结证据不冒称重验。

指标窄QueryStore独立16/16、10.63秒通过（基础6+READ10，未重复旧scope13）：真实501冻结范围且无accounts.read、历史USER/TEAM/SUPER隔离、120完整空/省略和迟到110不回填100、所有历史来源逐个预登记23字段回执、中文/字面百分号下划线/前导零ID、nullable Decimal、私有句柄同事务绑定、当前profile/scope/config撤回。证据evidence/python-metrics-query-read049-http.json。旧VALUES弃用警告留存，非正确性失败；独立来源表为SQL_ONLY_NOT_PLATFORM，不是完整MetricsAPI、发行、预期coverage分母或容量验收。

全部已审核正式迁移through053下，人员/目录/渠道和配置元数据原41组回归通过，证据evidence/python-reference-channel053-regression.json。旧身份9组裸023夹具与新权威GET存在已知内部冲突，须迁移测试并补完整空库存/5000资源边界后再计完整回归；不得降级路由或假作外部阻断。下一继续指标结果构建与恢复扫描器，严格总台账仍29开发/29测试/0验收。


### 身份库存边界与旧协议联合回归（2026-11-09 02:47，北京时间）

053原12+新增库存2+基础6真实20/20、12.45秒通过。完整空库存原DTO163字节；目标5000条实际25页来源、完整544052字节HTTP响应，capture/raw登记1.044秒、发布0.729秒、GET0.083秒，全部资源ID集合和原字段逐项一致。另1条独立anchor仅用于/me主体核对，不混入目标库存；原M3 selected<=500限制不改。5001实际26页触发META_RECORD_BUDGET_EXCEEDED，所有原始/发布表和clock均无部分写。全档124次受控Graph GET均核网络期间零SQL，真实Meta请求0。证据evidence/python-identity-publication053-inventory-boundaries.json；不是500账户或真实平台容量。

旧023领域Store的原撤销/到期/漂移/晚到/审计/完整空集断言全部保留，领域读取改为显式内部Store；新原HTTP裸head精确503 SOURCE_RETRY，不兼容降级。原HTTP正向由同一档完整05314组接力。through054账户导入/Worker/详情/代称/旧领域10/权威14组合实际67/67通过，证据evidence/python-account-identities054-combined-http.json；旧重复键与VALUES警告如实留存，不据warning推断业务失败。此前旧9夹具内部冲突已在本有限组合解决，后续更宽跨模块仍分别重验。054三个只读扫描索引已实际初始化，扫描器自身10组仍待专属真实档。
