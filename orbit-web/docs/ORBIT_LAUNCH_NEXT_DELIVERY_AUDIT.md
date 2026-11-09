# 投放计划与模板下一批最小交付核对

核对日期：2026-11-08。本文只读比对原 PRD、OpenAPI 与当前源码，不修改受测产品代码、不勾选总台账。

主线最新已通知：前端 478/478、类型/构建/格式通过；原投放页面三视口 3/3、整档 7/7，通过了默认预检禁用与相关写请求为零的断言。这证明本次已接入页面的真实行为，不能证明生产预检、身份保存、素材分配或 execute 已可用。

## 1. 第一批实施回填：真实列表分页和模板详情元数据

本批已获主线授权并实现：计划与模板四档每页数量、游标历史回退、换条件禁止旧游标、目录失效显式回首、网络失败保留原成功页、异步迟到结果隔离；模板 UTC 创建日期过滤及原详情元数据。新增 `tests/orbit/launch-pagination.test.ts` 16/16 纯测通过，包含短页仍有下一游标、确认保存后刷新与 busy 转场、未知写入不丢原意图。主线现已在through039独立库执行6/6真实三视口（整档7/7、71.84秒），覆盖原草稿模板流程与本批分页日期/详情。固定51文件494项、类型检查通过；排除在制账户范围组件。失败回执保留：原测试只填日期未完成面板编辑，移动端日历会挡住查询；最终真实Enter确认后点击面板外关闭，不使用force/自动重试/加超时。曾捕获一次ERR_NO_BUFFER_SPACE，最终三视口无网络失败，仍不宣称已根治浏览器底层资源错误。未做本批容量验收。

这是不依赖外部平台、不需要占位接口、可独立完成开发/测试/浏览器验收的一批。

### 1.1 计划、模板列表的分页选项与错误恢复

- 原依据：PRD-ORBIT.md 第 64 行通用列表 20/50/100/200；原 GET `/api/v1/launch-plans`、`/api/v1/templates` 均定义 `page_size` 四档。
- 审计时：`src/views/orbit/launch/index.vue`、`TemplatesPanel.vue` 请求固定 `page_size=20`；页面只有向后游标，缺少每页数量选择和可回到已读上页的游标历史。本批已补四档与游标历史。
- 下一完整闭环：四档每页数量；筛选/每页数量改变后从首游标重新读取；下一页使用服务端不透明游标；上一页使用保存的原游标；快照/权限变化明确回首，不能拼接旧数据或复用换筛选后的游标；请求迟到和取消不能覆盖新筛选。
- 容量约束：后端 `bounded_page` 会按响应字节预算收缩实际页长，不能断言 200 档必定返回 200 个 5MiB 计划，也不能把返回少于 page_size 当成末页；以 `next_cursor` 为准。不通过浏览器抓全目录伪造页码或总数。
- 必要真实检查：21 条以上两个相邻游标页；四档参数准确；查询保持筛选；换筛选后旧游标不重放；403 清除旧数据；409 重读首游标；编辑/预检未知锁继续阻止翻页和离开；三个视口可操作。

### 1.2 已支持但页面缺少的真实过滤条件

- 当前后端 `launch_routes.collection_filters` 支持计划：q/status/date_from/date_to/operator_user_id/channel_id；模板支持 q/status/date_from/date_to/operator_user_id。
- 当前页面：计划有 q/status/日期，没有负责人/渠道过滤；模板只有 q/status，没有日期/拥有者过滤。
- 本批已接模板日期，服务端已经支持，不需要新接口。负责人/渠道完整候选需另核只读权限来源，不借 create/edit 的 owner-options，不因列表过滤强加 accounts/system 菜单。也可提供明确“仅看此行真实拥有者/渠道”的有限操作，但不能冒充完整候选器。
- 原 OpenAPI 两列表还共列 metric_profile_id/entity_type，以及模板 channel_id。现后端 `_read_boundary` 不接受这些参数。不能直接画可用筛选框然后静默忽略；应单独明确其在计划/无外部绑定模板上的真实匹配语义，补后端查询及严格合同测试后再开放。

### 1.3 模板详情缺失的原返回字段

- 原 `Template` 除配置还要求 id/revision/ownership/state。当前列表展示 revision/state，但详情弹窗主要展示名称、说明、可见范围、接收者与配置树，没有独立完整元数据区域。
- 下一完整闭环：在真实 GET 详情中展示完整模板 ID、revision、state、owner_user_id、owner_team_id；没有权威名称时显示原 UUID 与“名称未读取”，不假定当前创建者就是所有者。私有/共享、接收者集合和只读权限与现有流程保持一致。
- 不添加原 DTO 没有的创建/修改时间、分享历史或“最后执行成功”等假字段，不创造无后端支撑的历史二级页。

## 2. 紧随其后：投放账户跨页快照消费 UI

- 原依据：PRD-ORBIT.md 第 344 行账户搜索/仅看已选/跨页快照；WORKFLOWS 原文允许 `account_scope_snapshot_id` 与空 `account_ids`，服务端冻结实际 ID，二者不得同时非空。
- 当前：`SourcePicker.vue` 只有逐页显式 ID 选择，未调用快照 API；`DraftEditor.vue` 仅解释既有 snapshot 字段。后端范围消费已接真实 `AccountScopeStore.resolve_for_plan`，不是“仍无后端实现”。
- 已有可复用客户端：`src/api/orbit/scopes.ts` 的 createScope/getScopeCsrf/getScopeMembers；已有范围成员只读二级页 `accounts/scopes/ScopeMembers.vue`。复用前核对其权限、可中止读取及严格响应校验，不修改 A 的既有组件来凑接口。
- 一个完整交付应包含：当前筛选冻结确认、显式选择与筛选快照两种模式、真实 count/hash/创建时间、成员分页查看、超 500 账户拒绝进入计划而非截断到前 500、不同拥有者/团队/币种拒绝、同意图重试和取消处理、来源变动失效提示。
- 提交快照请求时 account_ids 必须为空；保存响应已解析为实际 IDs 后，以服务端真实返回为准，不能继续把旧 snapshot 当当前可用授权；旧身份绑定的孤立处理保持显式确认。
- 禁止：用列表 cursor 充当 snapshot；前端循环抓全量 IDs 假全选；把快照当永久权限；不展示超量原因而静默缩小选择。

## 3. 尚缺字段，但必须先补真实资料/能力依赖

| 原字段/流程                            | 当前真实状态                                                                                                          | 下一步边界                                                                                                                                                               |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 广告组归因设置 `metric_profile_id`     | 原 AdSetConfig 有字段，CampaignTree 无编辑/只读说明；`launch_references.require_config_dependencies` 对非空值返回 503 | 原 FIELDS attribution_spec 是服务器 profile 引用，不能加任意 JSON 或手填 UUID。先实现当前租户/调用者及目标拥有者交集的权威 profile 候选与消费，再做选择/详情/版本/失效。 |
| `profile_binding_ids`                  | DraftEditor 未提供逐账户环境绑定编辑或完整只读回显；非空仍受身份/环境依赖 503                                         | ADSPOWER_UI 必须逐账户有效绑定；META_API 为空。复用未来真实环境绑定和能力回执，不添加假 Profile 数据或绕过账户交集。                                                     |
| `workflow_version` / `adapter_version` | Plan DTO 可保存/恢复原值，页面未配置或展示真实能力版本                                                                | 由经验证能力包给出，不能编辑任意“v1”字符串冒充已验证；权威来源未就绪时保持不可执行并清楚展示未知。                                                                       |
| CTA、优化目标、计费事件、特殊广告类别  | 当前部分是可输入草稿字符串，特殊类别 allow-create；没有生产能力枚举交集                                               | FIELDS 要求能力枚举与目标相关白名单。不能把 LEARN_MORE、PURCHASE 等候选硬编码为已验证；当前草稿值和最终验证状态明确区分。                                                |
| 优化事件、商店 URL                     | 新身份组件可编辑草稿值，观察仅含 PAGE/PIXEL/APPLICATION，无事件枚举或域名许可                                         | 最终预检缺权威能力应继续拒绝；不能由 observed usable 推导平台写授权或商店域名已许可。                                                                                    |
| 目标变更和特殊广告类别确认             | 当前会保留旧身份并展示冲突；目标下的组/创意关联约束与特殊类别适用性尚无完整用户确认流程                               | 明确列出受影响原配置；用户确认后才能清理/替换，取消保留原输入；不能用静默删除达成“互斥”，更不能只加确认框便称能力通过。                                                  |

这些是原字段/流程差距，不能由“结构 DTO 已存在”“SDK 已通过”“构建通过”结清。

## 4. 原任务/预检主链路仍未完成的边界

- 生产 validation provider 未配置时入口正确关闭；具备合法原接口与隔离 fixture 不等于生产授权可用。
- 生产 allocation provider、逐账户即时身份验证、完整 capability 证据、最终 execute 原 202 Task 桥接仍需完整真实接线。runtime UUID 不能代替 Task。
- 预检结果、冻结展开、执行确认已接组件与父保护，但没有生产 provider 的三视口只能验“默认关闭、零相关写入”，不能验真实成功预检/广告执行。
- 原 FR-LCH-05 的任务重试、取消、只读对账、统计、提醒仍需原后端状态/命令能力支撑。本批继续计划/模板，不靠新增占位按钮或跳转去其他半成品模块冒充完成。

## 5. 原文与源码核对位置

- 原资料：`D:/progress/orbit/data/ORBIT_Codex开发PRD/PRD-ORBIT.md` 第 64、174—204、344—346 行；`FIELDS.md` attribution_spec、CTA、identity_bindings/profile_binding_ids/workflow_version/adapter_version；`contracts/WORKFLOWS.md` 第 2 节；`contracts/API_SEMANTICS.md` 关键服务校验表。
- 原合同：`contracts/openapi-current.json` 的 Plan/Template/CampaignConfig/AdSetConfig/AdConfig，以及两列表 GET、scope-snapshots、validate/execute。
- 当前页面：`src/views/orbit/launch/index.vue`、DraftEditor、CampaignTree、SourcePicker、TemplatesPanel、PlanIdentityBindings、PlanValidationDialog、PlanExpansionPreview、PlanExecuteConfirm。
- 当前后端：`orbit-server/python/orbit_api/launch_routes.py` 的 collection_filters；launch_store/template_store.list；launch_references 的范围消费及依赖拒绝；launch_validation_store 的 provider 门禁。

第 1 批完成真实验收后，再由主线安排第 2 批或其他明确缺口；每批仍按开发、专项测试、真实验收分别登记，不因此标整个投放模块完成。
