# RuleList 独立组件交付

本组件尚未注册为业务页面，不代表规则模块整体验收。它沿现有 Vue3 / Element Plus 布局，复用冻结的 `src/api/orbit/rules.ts`；没有修改 SDK、Form、菜单、路由或后端。

## 原始依据与接口

- `D:/progress/orbit/data/ORBIT_Codex开发PRD/PRD-ORBIT.md:24`：rules 菜单范围包括列表、条件编辑、调度、模拟、启停和触发记录。
- 同文件第 242、362、364 行：启用规则先暂停再编辑；完整条件/频次/时区保留；命中进入 AI 分析流程，不能新增直接平台动作或“开始分析”。
- `contracts/openapi-current.json` 原 Rule / RuleSchedule / Simulation / ConditionResult / RuleRun 与九接口；公开响应由原 SDK 解析，不新增 DTO 字段。
- 原 Rule15 没有创建人、创建时间。列表明确显示“原接口尚未提供”，不使用 ownership 冒充创建人，也不从当前时间补数据。这两个保留展示字段仍需后续合同扩展及真实来源。

## 父组件协议

`RuleList.vue` props：

| 参数                        | 来源与约束                                                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `permissionCodes: string[]` | 当前真实原动作权限；默认空。支持原超级权限 `*:*:*`，不按角色猜权限。                                                       |
| `contextKey: string`        | 父必须传当前认证生命周期标识；登录/退出/主体变化以及同凭据重新登录都须变化。组件请求 epoch 与原 SDK 认证检查共同防晚回包。 |
| `filters`                   | 父受控原日期、投放师、渠道、归因配置筛选；只传原 RuleQuery 字段，不在本组件要求用户手输 UUID。                             |

组件拥有名称字面包含、状态、对象层级及 20/50/100/200 条分页输入。查询提交时冻结过滤条件；未提交的输入不污染已有游标。下一页/上一页保存原游标，重新查询、父筛选或页大小变化回首页。原日期/渠道语义未实现时，服务器 422 原样展示，不忽略参数制造成功。

事件：

- `create({csrf_token})`：先核本地 `rules.create`，再读 CREATE capabilities。父接真实候选与 Form，实际创建须自行保留原 key/body。
- `edit(rule, {csrf_token})`：先核 `rules.edit`、真实详情 DRAFT/PAUSED，再取 UPDATE capabilities；传完整独立 Rule 副本，不能伪造候选或 scope。父仍须当前 CAS 提交。

不会请求缺少动作的 capabilities。SIMULATE 使用原 `rules.read`；没有借 accounts、monitor、launch 或系统人员权限。创建专属角色不被额外要求 rules.read。

## 列表、详情与动作

详情一定独立 GET，读取中不沿用列表行伪装已取得详情。覆盖原 15 字段：ID、revision、state、name、ownership 双字段、target_level、scope_snapshot_id、logic、groups 全叶及 Decimal 原文本、window、metric_profile_id、Schedule 全七键、cooldown_minutes、max_daily、next_run_at。ID/UTC/未知 null 如实显示，scope 只有只读展示。

暂停和归档有原因确认弹窗。只有 ENABLED 可暂停，只有 DRAFT/PAUSED 可归档/编辑。确认后才请求对应 action capabilities；第一次实际发送时冻结 rule ID/revision、带引号 If-Match、CSRF、原正文及随机 idempotency key。

- 明确服务端拒绝展示原 code/message/field_errors.path，保留可修改原因并重新确认。
- 网络/响应异常的未知写入锁定原因与原意图，不自动重试，不重新取 cap 或生成新 key；手动“使用原请求重试”复用完整原 body/key/CAS。
- 未知结果期间不允许创建新动作或切换详情。认证变化会立即撤下含旧对象信息的弹窗 DOM、清空列表/详情并取消在途读取；原意图仅留组件内存。恢复原上下文后才可原请求重试。父若卸载组件，不能将此等同确认取消；当前没有跨卸载持久恢复服务，需后续父流程保留组件生命周期/回执。
- 本地原权限仅决定入口展示，真实授权、CAS、幂等始终由服务器复核。

模拟没有请求体，仅使用真实响应。Simulation13 原字段有 `expires_at`，没有 `created_at`；本组件不新增字段，也不根据客户端时间制造有效模拟。只允许同 rule_id/revision 且服务端 expires_at 尚未过期的真实模拟解锁启用入口；每秒仅刷新本地保守提示、不轮询请求，最终服务器仍是期限/资格权威。错误对象/版本响应按未知结果处理，不能生成启用资格。实际 503 可见，不返回假模拟。

模拟条件明细每组最多渲染 50 条，保留 null/UNKNOWN 与 reason_code。若原响应 next_cursor 非空，明确后续未加载；原模拟续页接口仍缺，不能声称完整明细已展示。触发记录通过独立 RuleRuns 组件调用原 GET /rules/{id}/runs，503 明确显示，不伪空数组。已补原状态/日期筛选、20/50/100/200 四档与前后游标页；打开详情后点击“触发记录”才加载，关闭详情卸载并取消子组件读取。具体交付及有限纯测范围见 ORBIT_RULE_RUNS.md。

## 验证与边界

- `pnpm exec vitest run --config vitest.config.ts tests/orbit/rule-list.test.ts`：18/18 PASS，最终一次 6.59 秒，其中测试函数 3.90 秒。
- `pnpm check:orbit`：PASS。
- 仅本文件/专属测试/本文档 Prettier 校验；机械 UI 检查结果另记最终节点。
- 使用真实 Element Plus 挂载、替身 rules SDK。验证调用参数/当前 CAS/未知同键恢复/取消无写入/服务端错误呈现/认证晚回防护，不属于真实 HTTP、浏览器、Rule Simulation/执行来源验收。
- 首次新增认证负例 17/18 PASS、1 FAIL：仅 `model-value=false` 使 Element Plus 隐藏弹窗但旧文字仍留 DOM。已用上下文条件卸载整个弹窗内容修复，保留原旧文字不可见断言后 18/18 PASS；没有放宽断言或延长超时。
- 未启动服务、共享数据库、浏览器或真实平台调用。主线后续接真实 helper/Form/路由后再进行原接口及三个视口验证。

## 运行记录后续页接力

原冻结18项挂载断言保留，并新增真实子组件下一页调用断言，当前List19项与Runs19项合计38/38通过（8.01秒，仅SDK替身）。没有修改原SDK、模拟响应或新增HTTP接口；模拟next_cursor原续页接口缺口仍明确保留。

## 业务闭环优先修复（2026-11-09）

当前已有真接口链：列表/四档keyset→Rule15详情Drawer→创建/编辑二级页→真实owner/profile→原11字段/条件/调度→五filters范围Dialog/服务器freeze→原保存→原GET/返回刷新；暂停/归档独立原因确认Dialog及原CAS/幂等键。字段、二级页、未知请求与权限最终以主线真实内置浏览器逐步验收，组件替身不等业务验收。

本窄修改只修两处确证缺口：列表详情的原RuleRun入口改名“运行记录”，展开后明确范围，不把它冒充全局RuleHit；原列表/详情GET收到401/403即时清旧page/detail/simulation、关闭Drawer并中止未完成读取/入口/动作等待，不等permission props刷新。已经发出的未知动作保留原body/key/quoted CAS，隐藏旧对象名称和原因；手动原请求恢复仍沿原动作权限和服务端范围复核，不新增rules.read作为原动作重放门禁。当前源409和普通503不能被当撤权；仍显示错误和已授权详情。

本轮仍需补的原UI元数据：列表创建人/创建时间目前原Rule15未提供，ownership显示UUID而非真实姓名/团队标签；必须由专属真实metadata投影补齐，不能用浏览器时间/当前登录者/额外目录权限猜值。其余范围容量、完整未知网络/撤权浏览器、正向启用/模拟/调度、全局触发不因此标完成。暂停正向夹具技术ENABLED不等生产enable来源。

定向测试使用原生ElementPlus、SDK受控替身，保留原List所有断言，新增read401/403/旧未知意图保留、409/503不误清理；没有数据库、平台、Git操作。最终命令/数量见本轮.runtime/rule-list-business-\*，主线真实浏览器随后执行。

## ACTION意图父接管与成功回列表（当前业务修复）

RuleList新增pendingAction prop与pending-action事件，专属冻结动作对象包含原Rule/原因或simulation_id、原CSRF/key/quoted IfMatch、actor生命周期context。只有实际准备发送才emit，打开原因确认Dialog不产生pending。未知后的403/409不能证明先前未受理，继续保留原意图；手动恢复仅原POST，不自动换键或正文、不增status端点。成功先emit null清父，再refresh回首屏保留appliedQuery（不能写后沿旧目录cursor导致409）。

规则父页持ACTION envelope，与Editor SAVE/SCOPE严格分支；认证:key真正重挂载后把原ACTION交新List，跨身份只泛化显示且不重发；原生命周期同上下文才可手动恢复。ACTION时List自身禁新写而保留原确认，Editor pending仍用父inert。明确读撤权/权限变化隐藏原名称/原因，后台原动作仍当前重验，不额外借read/edit权。

SPA onBeforeRouteLeave在存在未确认意图时阻止离开并提示，成功确认清父后才可离开。未发确认不阻离；同页List/Editor切换仍保留原pending。未承诺硬刷新/浏览器重启恢复，没有把业务事实写入Storage。原父测试改用真实RouterView挂载，实证实际路由record的leave guard；首轮直挂Page的68/69假注入失败日志保留，未放宽阻离断言。

当前另接独立显示metadata SDK，完整说明见ORBIT_RULE_DISPLAY_METADATA.md；后台真实API及内置浏览器将另验，组件替身不继承旧保存v1/v2/归档v3的真实通过。

## 当前同主体恢复接线

原业务正文、幂等键及版本不变；首次写前实际读取原六动作恢复身份，手动恢复须再次同actor/tenant核验。新标签页登录和父页只读身份复核不自动发送写请求。完整约束与实际测试见 [ORBIT_RULE_RECOVERY.md](ORBIT_RULE_RECOVERY.md)。此节点仍需主线真实HTTP/浏览器验收，不继承旧UI证据。

## 具体执行频次与名称查询边界

当前列表按原Schedule展示每N分钟、每天当地HH:mm、每周指定ISO星期及当地HH:mm；保持原IANA时区，不把当地时刻猜成UTC，不显示裸频次枚举代替具体调度。

名称查询先NFC，按Unicode码点最多100，超限在本地明确 `/q` 错误，不发请求且不改变已提交查询、cursor/history；空串沿原SDK无q筛选。输入框不设原生UTF16 maxlength100，否则100emoji被错误截断为50；也不设会截断合法NFC压缩输入的200硬限制。提示明确最多100字符。页面不偷偷trim/改变未提交原输入，SDK和后端仍各自严格验证。

本轮只改List、专属测试及本文档；不改已真实验过的未知恢复流程。两个只读筛选候选等专属rules.read新接口，不借CREATE/UPDATE编辑候选或目录/monitor权限。定向替身测试不等于新的浏览器验收。
