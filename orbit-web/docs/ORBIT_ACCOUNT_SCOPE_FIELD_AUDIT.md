# 账户范围字段与HTTP操作验收候选

本文件只读对照原合同、Python源码和已保存的具名真实回执，不修改2342项总台账。当前新投放选择器/父编辑器仍由主线执行浏览器复验；本文件不预判其结果。45项新SDK/选择器纯测、15项Draft纯测和全前端546项均不是数据库或平台验收。

审计取 `orbit-server/docs/orbit/progress.json.items`，不取重复的 `history[].previous`。当前共有2342项；下列20个Scope/Filter schema字段仍为NOT_STARTED/NOT_RUN/NOT_RUN，两个原API为IN_PROGRESS/NOT_RUN/NOT_RUN。本轮不直接改状态。

## 原合同与真实HTTP入口

依据 `data/ORBIT_Codex开发PRD/contracts/openapi-current.json`、`contracts/WORKFLOWS.md:125`、`contracts/PERMISSIONS.md:57`：

| 精确台账ID                 | 原入口/操作                                                      | 已有实现和证据                                                                         | 不能一并结清的内容                                                                               |
| -------------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `API-createScopeSnapshot`  | POST `/api/v1/scope-snapshots`，201，`accounts.read`             | `account_scope_routes.py:create` → `AccountScopeStore.create`；A40/容量44/B102具名回执 | 原受控SUPER `X-Target-Tenant`跨租户正例尚不支持；不能直接将整API验收标通过                       |
| `API-scopeSnapshotMembers` | GET `/api/v1/scope-snapshots/{id}/members`，200，`accounts.read` | `AccountScopeStore.members`；20/200分页、真实250页、游标换查询409、权限变更拒绝        | 原操作还声明7个通用查询参数，但当前白名单只支持q/page_size/cursor；完整参数合同待裁决与实现/验收 |
| 无原operationId            | GET `/api/v1/scope-snapshots/capabilities`，200                  | Python技术扩展；真实只读角色无需accounts.import即可取得冻结上下文                      | 不创造第三个原API台账ID；不把capabilities当快照HEAD或身份写授权                                  |

原OpenAPI只有上述两个Scope操作。若“3操作”指冻结、分页成员、读取capabilities，其第三项必须明确是技术扩展。若指投放使用快照，则对应原Plan创建/更新接口与 `SCHEMA-PlanWrite.account_scope_snapshot_id`，也不能改称第三个Scope原操作。

## 具名真实证据索引

以下均为当前Python版本隔离本机MySQL/Redis/真实HTTP，不外发广告。回执位于 `orbit-server/docs/orbit/evidence/`。

| 代号  | 回执与实际结果                                                | 最相关具名检查                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A40   | `python-account-scopes-http.json`，40/40 PASS                 | `pythonAccountScopeFilterFreezesAllMembersWithStrictOriginalResponse`；`pythonAccountScopeIdsReplayIsSetCanonicalAndHashStable`；`pythonAccountScopeUnknownInvisibleAndInvalidSelectionsFailWithoutPartialCommit`；`pythonAccountScopeKeysetMembersStayFrozenAcrossOrdinaryRename`；`pythonAccountScopePlanLimitRejects521WithoutTruncation`；`pythonAccountScopePlanRechecksOwnerTeamCurrencyButNotNameRevision`；`pythonAccountScopeIdempotencyRejectsDifferentSelection`；`pythonAccountScopeMemberAndAuditFailuresRollBackWholeCommand`；`pythonAccountScopeReadOnlyWithoutImportCanGetCsrfAndFreeze`；`pythonAccountScopeForeignSnapshotsAndRevokedReadOrMemberScopeFailClosed`                                                                                                              |
| A44   | `python-account-scope-capacity-http.json`，44/44 PASS         | `pythonAccountScopeCapacityActuallyFreezesFiftyThousandAndReadsAll250Pages`：实际50000个成员、250页、零遗漏/重复、按完整冻结值复算hash相等。附 `python-account-scope-capacity-metrics.json`：创建3.697秒；创建及逐页复核177.592秒。不是每次GET都在1秒内或真实冷启动的证明                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| AV14  | `python-account-scope-visibility-plans-http.json`，14/14 PASS | `pythonScopeVisibilityActualFiftyThousandAccountsAndThreeRoleSnapshots`；SUPER/TEAM/USER各自 `EquivalentPlansMeasured`、`NoClockMutationStillDenied`。不等于全接口或全部多租户权限验收                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| B102  | `python-launch-scope-consumption-http.json`，102/102 PASS     | `pythonLaunchScopePersistsActualIdsAndImmutableProvenanceWithEditableOriginalPlan`；`pythonLaunchScopeOriginalIntentReplayDistinguishesDifferentSnapshotsSameIds`；`pythonLaunchScopeFiveHundredAcceptedFiveHundredOneAndExpandedOverflowAtomic`；`pythonLaunchScopeOrdinaryRenameKeepsFrozenSelectionAndReadsCurrentRevision`；`pythonLaunchScopeOwnerTeamCurrencyAndUnbindDriftRejectWholePlan`；`pythonLaunchScopeForeignCreatorTenantAndListCursorCannotBeConsumed`；`pythonLaunchScopeCurrentAccountsAndLaunchRevocationBlockOriginalKeyWithoutEmptyDraftExpansion`；`pythonLaunchScopeAuditRollbackAndUnknownIdentityRemainFailClosed`；`pythonLaunchScopeActualDeadlockRetryRetainsOriginalRequestAndFrozenSelection`；`pythonLaunchScopeActualTargetOwnerMustAlsoHaveCurrentAccountsRead` |
| A41UI | `python-account-scopes-browser.json`，41/41 PASS              | `pythonBrowserScopesThreeViewports` 是原独立账户范围页的三视口，不继承为本轮投放草稿新选择器通过                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

对应检查实现为 `tools/account_scope_checks.py`、`tools/account_capacity_checks.py`、`tools/account_scope_visibility_plan_checks.py`、`tools/launch_scope_consumption_checks.py`。不使用Java历史 `account-scope-core.json`、`scope-http-transactions.json` 等当Python证据。

## 精确schema字段候选

表中“强候选”表示有直接真实值/集合/协议行为断言，可供主线独立核对开发/测试阶段；不自动推导整模块验收通过。“补边界”表示当前具名HTTP没有独立覆盖全部原字段边界，不能只凭SDK纯测把原字段完整验收结清。

| 精确字段ID                                       | 源码与原义                                                       | 直接真实证据                                                         | 候选强度与剩余项                                                                                                  |
| ------------------------------------------------ | ---------------------------------------------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `SCHEMA-ScopeSnapshot.id`                        | `AccountScopeStore.create/public`：服务端UUID，创建者/租户内访问 | A40重放同id、外人404；B102真实Plan provenance保留同scope_id          | 强候选；本轮新UI须显示/提交真实id，不以普通cursor代替                                                             |
| `SCHEMA-ScopeSnapshot.count`                     | 实际冻结成员数，整数0..2147483647，业务上限50000                 | A40=521；A44=50000且全成员对账；B102=500接受、501拒绝计划且不截断    | 强候选的实际计数/业务上限；空FILTER的真实count=0正例尚无此具名专项独立断言                                        |
| `SCHEMA-ScopeSnapshot.scope_version`             | 公开权限版本，非account clock/revision                           | A40真实撤权/成员范围变更拒绝；AV14三角色无时钟变动也拒绝             | 补边界：需明确断言返回版本范围、成员页同版本、权限改变后的旧游标/重放；安全整数顶值仅纯测不能冒真实授权时钟验收   |
| `SCHEMA-ScopeSnapshot.hash`                      | 64字符；当前服务端对完整有序冻结值计算SHA256                     | A44逐50000条复算完整hash相等；A40同集合倒序重放hash稳定              | 强候选，可独立结清冻结集合hash真实计算；不是凭hash即可执行                                                        |
| `SCHEMA-ScopeSnapshot.created_at`                | 服务端UTC date-time，原冻结时间                                  | A40真实201含严格5字段；重放返回原响应                                | 补边界：现具名检查未单独断言时间格式/稳定值与成员data_as_of一致，不能仅“字段存在”判完整验收                       |
| `SCHEMA-ScopeMember.account_id`                  | 原账户UUID，完整冻结顺序，不使用外部数字ID充当UUID               | A44将250页50000个ID逐项与原集合排序对账；B102真实消费同集合          | 强候选，真实完整ID与无重漏已直接断言                                                                              |
| `SCHEMA-ScopeMember.external_id`                 | 1..64位数字字符串，保留前导零                                    | A40 `startswith('00')`，A44输出严格3字段                             | 补边界：64位端点/类型拒绝主要是新SDK纯测，现专项真实值约24—31位，不声称64位SQL回读已实测                          |
| `SCHEMA-ScopeMember.name`                        | 1..10000字符；冻结名称，不跟随当前账户重命名                     | A40改名后成员items原值不变；B102普通改名不使选择失效                 | 可结清“冻结名称”子行为；10000码点/Unicode边界尚非此真实专项，不把小名称夹具当完整字段边界                         |
| `SCHEMA-ScopeMemberPage.items`                   | 0..200成员数组，严格3字段项                                      | A40实际20条且相邻页无交集；A44实际250页每页≤200并全量对账            | 强候选；空搜索结果0条与20/50/100/200全部大小的真实组合仍应补专项/新UI证据                                         |
| `SCHEMA-ScopeMemberPage.next_cursor`             | opaque签名游标或null；绑定snapshot/权限/q/page_size              | A40换q重放409；A44每页游标不重复且尾页null                           | 强候选；MAC篡改/同q换page_size失效尚须对应具名断言，不能把SDK URL保留测试当签名验证                               |
| `SCHEMA-ScopeMemberPage.data_as_of`              | `members`返回原snapshot.created_at                               | A40严格4字段响应                                                     | 补边界：源逻辑已实现，但具名实际检查未显式将其与created_at比对，不依字段存在结清                                  |
| `SCHEMA-ScopeMemberPage.scope_version`           | 当前受授权快照版本，读取前全成员复验                             | A40当前读取/撤权/成员移交拒绝；AV14角色矩阵                          | 补边界：新UI解析严格值并拒版本漂移是纯测试；需真实稳定版本值和变化后失败的逐字段证据                              |
| `SCHEMA-ScopeRequest.mode`                       | IDS/FILTER严格互斥，三个字段恰好出现                             | A40实际两模式；空IDS/重复拒绝；B102scope+显式IDs互斥及普通cursor拒绝 | 已有真实正反，候选开发/测试；非法枚举、各互斥组合的完整HTTP矩阵尚需补，不能仅继承Python解析纯测                   |
| `SCHEMA-ScopeRequest.account_ids`                | UUID数组≤50000；IDS非空；重复拒绝，排序规范化                    | A40两ID倒序重放、重复422；A44 FILTER产生50000；B102500/501消费       | 补边界：A44不是“HTTP IDS提交50000”的证明，真实输入50001/UUID变体/混合外域原子拒绝需逐项保留                       |
| `SCHEMA-ScopeRequest.filter`                     | FILTER完整五字段，IDS=null，冻结当前权限交集                     | A40实际非空FILTER且IDS=null；AV14不同数据角色完整可见性复验          | 已有模式正反候选；非空vendor、空FILTER范围与所有原枚举组合仍需明示真实覆盖                                        |
| `SCHEMA-AccountSelectionFilter.q`                | NFC/首尾规范化≤100码点；原账户名包含匹配或完整数字ID             | A40以唯一marker实际冻结521；A44 marker50000                          | 补边界：100/101 Unicode、控制字符、字面%/\_/!、数字64位/前导零查询需真实专项；成员q是冻结名称前缀，勿混作相同语义 |
| `SCHEMA-AccountSelectionFilter.status`           | ACTIVE/DISABLED/UNKNOWN/null                                     | A40真实UNKNOWN，A44=null                                             | 补边界：ACTIVE/DISABLED过滤正反不能由账户列表或SDK纯测间接冒认                                                    |
| `SCHEMA-AccountSelectionFilter.auth_status`      | AUTHORIZED/EXPIRED/REVOKED/UNKNOWN/null                          | A40真实UNKNOWN，A44=null，B消费账户AUTHORIZED                        | 补边界：B消费状态不是FILTER逐枚举过滤的证明                                                                       |
| `SCHEMA-AccountSelectionFilter.operator_user_id` | 业务用户UUID或null，与实时数据范围求交集                         | A40真实指定owner；A44=null；AV14三角色可见性                         | 补边界：具体filter指定本人/普通peer/明确管理团队/外域的HTTP结果需与三角色内部可见性矩阵区分                       |
| `SCHEMA-AccountSelectionFilter.vendor_id`        | UUID或null，按真实账户vendor过滤                                 | A40/A44只用null                                                      | 保留未完成；非空vendor真实正反与外域/被停用已绑定历史口径没有上述专项证明                                         |

最稳妥先核对的细项：`SCHEMA-ScopeSnapshot.id`、`SCHEMA-ScopeSnapshot.hash`、`SCHEMA-ScopeMember.account_id`，再按实际断言范围核对 `SCHEMA-ScopeSnapshot.count`、`SCHEMA-ScopeMemberPage.items`、`SCHEMA-ScopeMemberPage.next_cursor`。不能把表中强候选解释为已经自动打勾。

## HTTP参数与剩余合同差异

可独立比对的精确ID：

- `PARAM-createScopeSnapshot.header.Idempotency-Key`：A40同集合规范重放、不同payload409；B102不同snapshot即使同IDs也不是同意图。长度16/128及可见ASCII两端、重复header的真实HTTP边界尚需有具名断言。
- `PARAM-createScopeSnapshot.header.X-CSRF-Token`：A40错误csrf403、只读USER可取得真实上下文；缺失/多值/16..255原声明长度与Cookie会话重认证恢复仍需专项。新SDK的会话不偷换及未知锁仅纯证据。
- `PARAM-createScopeSnapshot.header.X-Target-Tenant`：原声明SUPER可控跨租户写，当前 `_read_boundary`统一403。非SUPER拒绝是安全正例，SUPER受控正例缺实现/证据，不能标完整通过。
- `PARAM-scopeSnapshotMembers.path.id`：A40他人快照404，B102同创建者/租户/普通cursor不能消费；格式非UUID、大小写归一化、缺失ID仍应严格独立验证。
- `PARAM-scopeSnapshotMembers.query.q`：A40换q旧cursor409；当前名此前缀/数字精确搜索，仍缺字面转义/边界与正向结果的完备真实矩阵。
- `PARAM-scopeSnapshotMembers.query.cursor`：A44完整250页、尾null，A40换q409；其MAC/用途/租户/actor/page_size绑定不能只以页数代替全部安全验收。
- `PARAM-scopeSnapshotMembers.query.page_size`：源码支持20/50/100/200，A40=20与A44=200有真实证明；本轮UI拟补20+1及切换，50/100实际HTTP和非法51/201仍应明确核验。

以下七个精确ID存在原声明与现边界差异，不可结清：

`PARAM-scopeSnapshotMembers.query.status`、`PARAM-scopeSnapshotMembers.query.date_from`、`PARAM-scopeSnapshotMembers.query.date_to`、`PARAM-scopeSnapshotMembers.query.operator_user_id`、`PARAM-scopeSnapshotMembers.query.channel_id`、`PARAM-scopeSnapshotMembers.query.metric_profile_id`、`PARAM-scopeSnapshotMembers.query.entity_type`。

当前 `account_scope_routes.members` 仅将q/page_size/cursor传给 `_read_boundary`，其余被当未知字段400。原ScopeMember本身也没有日期/渠道/profile/entity等维度，不能前端猜映射或静默忽略。需要产品/主线明确这些通用参数在冻结成员中的语义，或正式维护合同裁决；本轮选择器不显示伪筛选。

`GEN-08` 还包含撤权、筛选变化、取消、所谓快照过期。原ScopeSnapshot无expires_at，现也无HEAD/DELETE/取消HTTP；取消本地使用不能冒称服务端删除，权限/成员变更失效不能被改称TTL到期。保留该整体行为未完整验收，待本轮三视口与明确的剩余语义核对。

## 本轮必须实际重验的前端路径

1. 原layout/菜单 → 投放 → 新草稿 → 选择账户；账户入口实际使用当前accounts.read和非敏感登录/权限上下文，资产/渠道仍原入口。
2. 手动20+1跨页勾选、回退及取消明确ID；不全量拉取、无静默全选、最多500；负责人/团队和币种不能靠名称推断。
3. FILTER真实501范围展示501且禁用应用，不截断500；更换条件后重新冻结真实21；成员20+1、上一页、查询只改变成员视图，不改变原快照。
4. 真实scope五字段经严格SDK解析和UI显示；POST原Plan只发`account_ids=[]`加真实scope id；服务端返回实际21IDs/null，Draft以该来源回编、显示21，随后PUT不得继续发旧scope或只读字段。
5. 保存结果未知同body/key恢复、scope POST未知同key/csrf恢复、换登录上下文阻断跨身份重放、关闭/route/刷新保护。当前只纯测试，不能借主线成功路径冒认真实网络故障验收。
6. 清除账户必须确认；孤立身份完整保留；恢复草稿只有scope id时数量显示未知，身份等保存返回实际ID后才可编辑。不伪造hash/count/资源身份。
7. 真实撤权/账户改归属时当前snapshot/member/Plan消费均失效。已有后台具名证据有效，但新UI清旧观察、禁用应用及重试恢复还应按风险单独实测。

本轮root正在跑的新投放三视口回执尚未在本审计中计为PASS。平台账户采集授权、权威身份/能力、真实广告预检/执行、跨租户受控SUPER写入均不因范围选择器完成而自动通过。
