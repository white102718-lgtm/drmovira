# 正式身份能力来源的最小接力方案

核对日期：2026-11-09，北京时间。本文件只给下一实施边界，没有新增生产发行器、配置、迁移、路由或Meta请求。055摘要只证明本系统曾完整封印数据，不能作为本方案的外部资格来源。当前正式Authority仍缺来源时503。

## 1. 原合同要证明什么

原`data/ORBIT_Codex开发PRD/contracts/WORKFLOWS.md:19`要求每账户保存主页及广告组像素/转化事件或应用/商店URL，最终逐账户预检。保留03第166—167行要求已授权外部ID，不能向所有账户套同一主页；第165行的归因profile和目标能力是另一来源，不能用资产任务代替。

原AccountIdentities保持PAGE/PIXEL/APPLICATION三类和原四/五字段。AD_ACCOUNT只是目标账户的内部前置证据，不新增为resources.kind。`usable`需要完整、明确的资源用途资格；未知不能批量写false冒充完整否定，也不能非空ID就true。接口结构合法、清单完整、主体已匹配、来源已验证和能力已发行是不同结论。

至少分开三种来源：

| 来源 | 实际回答的问题 | 单独不能回答的问题 |
|---|---|---|
| 资产库存 | 此BM/目标账户返回了哪些资源，全部页是否读完 | 哪个主体获什么任务；该资源能否用于本次目标 |
| 配置主体及资产任务 | 同一真实主体、BM、Graph版本在具体资产上的分配和明确任务 | 该主页/像素/应用与特定目标账户、目标/目的地/产品是否兼容 |
| 逐目标用途兼容证据 | 指定账户+资源+用途组合的受信兼容性及已知限制 | 用户在ORBIT内的launch.execute/publish、策略、预算和最终发送许可 |

这三种证据不能相互循环自证：库存不发行自身资格，055 MAC不证明Meta任务，独立capability_release也不能只引用库存hash然后把source_kind改成META_AUTHORITY。

## 2. 本轮实际确认的官方入口和未确认字段

主线已用内部浏览器读取[账户指南](https://developers.facebook.com/docs/business-management-apis/business-asset-management/guides/ad-accounts)、[主页指南](https://developers.facebook.com/docs/business-management-apis/business-asset-management/guides/pages)及[系统用户权限指南](https://developers.facebook.com/docs/business-management-apis/system-users/guides/permissions)，正文结论保存在`META_AUTHORITY_DOC_FINDINGS.md`。本代理网页抓取仍throttled，自己的iab不可用、Chrome建页API失败，已停止重复；本轮额外真实读取了Meta官方固定25.0.0 SDK，下面区分两种证据层级，不称API实测。

| 入口/字段 | 已确认到的精确范围 | 接入限制 |
|---|---|---|
| `/{BUSINESS_SCOPED_USER_ID}/assigned_pages`、`/{PAGE_ID}/assigned_users?business={BUSINESS_ID}` | 官方主页正文给出这些GET例子 | 正文没有GET tasks字段/响应shape；不能填猜测的tasks数组 |
| `/{BUSINESS_SCOPED_USER_ID}/assigned_ad_accounts`、`/act_{AD_ACCOUNT_ID}/assigned_users` | 官方账户正文给出这些GET例子 | 分配关系与拥有库存不同；未展示GET tasks shape |
| `/{APP_SCOPED_SYSTEM_USER_ID}?fields=email,assigned_ad_accounts,assigned_pages` | 官方系统用户权限正文有该GET示例 | 不读取email作为业务必要字段；APP_SCOPED与BUSINESS_SCOPED命名不可静默混同 |
| SystemUser两条assigned边 | 固定[25.0.0 SystemUser SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/systemuser.py#L87)分别返回AdAccount和Page | SDK声明接口，不承诺当前配置Graph版本支持或凭据有权；assigned_pages的可选pages参数不是授权证明 |
| `business`过滤及AssignedUser | [AdAccount SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/adaccount.py#L1909)、[Page SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/page.py#L992)的GET assigned_users接受business；[AssignedUser SDK](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/assigneduser.py#L25)声明id/business/name/user_type | AssignedUser没有tasks声明；只能读取已明确白名单字段，不从POST tasks枚举构造GET事实 |
| 账户`user_tasks` | 固定AdAccount SDK声明这个字段；现M1已原样读取 | 字段存在不等于已确认“任意指定主体”的任务含义或目标创建许可。还需版本化GET语义及同主体绑定证据 |
| BM的system_users | [Business SDK 25.0.0](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/25.0.0/facebook_business/adobjects/business.py#L4418)有GET边，返回SystemUser；后者声明id/system_user_id | 可作下一只读绑定候选，但两ID的namespace映射、实际返回及所需权限仍须确认，不从数字相等推断类型/映射 |

官方页面任务角色表与SDK的POST tasks枚举是配置操作的说明，不是已获当前任务的GET响应。当前没有足够证据定义`assigned_users.tasks`或Page的GET `tasks`字段；禁止为跑通测试添加这个伪合同。下一步若官方版本参考或实际只读响应证实新字段，必须独立记录其来源/版本/真实目标与任务语义，随后才启用解析器，旧版本保持未知。

## 3. 可先实施的窄闭环

第一步只补“已绑定主体的资产分配关系”，不直接发行usable。拟独立`meta_principal_asset_access.py`及专属tests/tool，不改冻结M1/M2/M3或C1。输入现模块生成且重算校验通过的配置主体Match、完整Bound、明确所选目标账户/主页集合；不接受caller expected_user_id、任意URL或verified布尔。只读已确认assigned边与对象关系，输出完整有界的事实包：source/config/BM/Graph、原主体ID及明确namespace、目标账户/主页ID、assigned关系、原样已确认字段、complete/unknown原因、观察时刻、规范hash。**tasks字段没有证据时就是unknown，不生成资格。**

最小接口候选：`observe_principal_asset_access(match, selections, *, version_contract, transport=None) -> PrincipalAssetAccessFacts`。`version_contract`来自本系统受控、不可任意构造的接口合同注册，绑定官方出处及所支持字段，不是自由版本字符串。网络仍仅GET、固定Graph host/配置版本、Authorization头、同源分页after重建、总页/请求/字节/记录预算；不得取Page.access_token或发送授权分配操作。全程无SQL会话，缺页/403/版本不支持不会变成已完整无任务。

同主体业务绑定至少交叉核现配置systemUserId与真实/me，主体assigned目标与目标assigned用户（business过滤有证据的入口）及BM标识。主体验证只使用已确认namespace；若同一个字段在不同入口的namespace关系未确认，保留明确未核状态，不做字符串替换或自动ID转换。当前M3b的匹配结论不会自动升级为“系统用户类型已证实”。

第二步补精确任务读取合同，优先Page和AD_ACCOUNT。需要官方适用版本的字段/完整响应与语义，及真实只读凭据能读取的证明。先写协议完整性/撤销/分页/同主体反例，再由主线批准只读外测。任务不足只有在完整、权威响应确认后才能作为明确不可用原因；未知字段/权限不足/不完整分页应阻断正式资格发布。当前已读文档未解决这一点，不能承诺第一步就能发行Page true。

第三步引入独立的目标用途兼容来源，显式输入`(account_id,resource_kind,resource_id,intended_use,objective,destination)`，返回版本化、可撤销的明确决策及proof；先Page与实际目标账户。Pixel/App仍需其自己的账户访问、事件/目标、应用平台及商店URL等语义，不能借用Page任务规则。缺来源直接503，不把原observed restrictions空值当允许。

## 4. 正式发行与现有发布的接点

现`identity_publication_store.py:81`的IdentityCapabilityAuthority有capture/revalidate边界，原Qualification携独立release ID/revision/source_hash及逐资源决策。正式实现应只适配已经齐全的库存+主体任务+目标用途证据。生产构造入口默认None；ISOLATED_PROTOCOL、READ_VERIFIED、raw登记及主体Match不能被工厂转换成生产Authority。

正式独立release必须冻结issuer、精确来源合同版本、配置ID/rev、BM/Graph、适用tenant及ACCOUNT_IDENTITIES_READ动作范围、完整来源根、能力版本字符串；发行内容immutable，当前撤销单调。source_hash绑定三类事实与判定规则，不用日期/随机UUID/原raw hash冒充能力版本。不能由身份publish顺便INSERT release自授；缺任务或兼容性不生成release。当前发行表已存在，但真实受控发行器/版本合同尚未接，不新增任意HTTP发行backdoor。

网络capture仍在事务外。最终短事务按当前auth/完整来源配置全局UUID顺序→独立release及来源proof→账户clock→排序账户（含当前managed锁读）→身份版本/ledger→发布/封印/审计outbox。CAS核tenant/actor/auth_version、唯一当前来源ID/rev/BM/Graph/principal、所有账户rev/owner/team/external/解绑、完整根及发行撤销，避免旧RR view复用已撤权限。publish和seal仍同外层事务；旧成功key返回原历史metadata前先当前动作/全部原对象范围，不因新配置版本重绑旧回执。

该发行仅为账户身份读取快照。接计划草稿时还要当前caller和plan owner双主体可读；validate还需现指标profile、归因适配、policy/capability/scope等独立来源；execute及每次外部发送另外即时复验原launch.execute、必要publish+ack和当前资源授权。任务GET/身份快照/055 SYNCED均不变成未来广告写权。

## 5. 最小分工及验收界限

| 步骤 | 独立所有权建议（待主线授权） | 可真实验证 | 明确未完成 |
|---|---|---|---|
| P1 主体资产分配关系 | 一个新collector+测试+独立工具；不改旧模块 | M1真实SQL捕获、受控GET/完整性/同主体与namespace反例、网络零SQL、最终CAS漂移 | 不是tasks或usable发行；没有真实Meta凭据仅阻真实API读 |
| P2 精确任务来源 | 同collector的受控版本合同与正式任务适配 | 官方字段shape、缺字段/未知枚举、两侧关系不一致/撤销；实际只读来源 | 只有fixture PASS不能打开生产adapter |
| P3 Page逐账户用途兼容 | 独立兼容provider与production Authority实现；主线接发行流程 | 独立proof/完整库存决策、发行/发布原子回滚、撤销后原GET及摘要UNKNOWN | Pixel/App未确认保持503；不得全false凑完整 |
| P4 原页面与计划消费 | 主线/B共享引用接线；A的C1/055接口不改DTO | 已有原GET/Drawer、列表三字段、caller+owner引用交集 | 预检与执行所有其他来源仍各自核验 |

当前可以安全继续P1完整只读组合实现，不能宣称精确tasks字段或Page资格已有生产依据。若需要尽快真实发行，优先补P2/P3证据而不是再增加无用途raw字段。该设计未执行任何Meta请求，未读生产Token，未迁移或修改生产来源代码。
