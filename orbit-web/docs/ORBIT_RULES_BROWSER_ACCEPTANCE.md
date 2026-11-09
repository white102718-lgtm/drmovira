# 规则完整页面真实浏览器验收步骤（待执行）

本文件是主线执行清单，不是成功回执。本轮仅只读核对已冻结DOM/合同，没有启动服务、浏览器、DB或构造Playwright结果。原依据：`data/ORBIT_Codex开发PRD/PRD-ORBIT.md`模块4、`FIELDS.md:567—744`规则字段、`contracts/WORKFLOWS.md:63`原状态边与15分钟同版本模拟、`:125`冻结范围语义；实际字段以原Rule15/RuleWrite11/RuleSchedule7合同为准。

## 0. 实际前置与证据边界

1. 使用主线独占UUID测试库、已实际应用057/060/062及此前依赖迁移。记录UI/API origin、后端提交/工作树fingerprint、前端fingerprint、浏览器和三个实际viewport；不记录Cookie、CSRF、Bearer、平台Token或原私有env。
2. 通过真实登录、原菜单和实际HTTP建立会话。不得使用route.fulfill、注入组件state或替换SDK结果。截图可见当前用户与菜单但不得含凭据。
3. 为列表准备至少201条真实Rule，包含可识别名称、DRAFT/PAUSED/ENABLED/ARCHIVED及至少两个owner/团队；范围准备至少521个当前caller与目标owner均可见的真实账户，另有不可见样本。不可把列表API返回的fixture名称当生产资料。
4. 通过主线现有技术fixture准备真实规则可引用profile证明、已sealed Rule manifest以及原scope5。这些仅覆盖隔离协议；不能把ISOLATED/FIXTURE、READ_VERIFIED或非空ID变成生产能力。没有合法来源时，503必须呈现为失败/未就绪，不能为了UI成功改变权限/资格合同。
5. 至少分别准备rules.read+create+edit、仅create、仅edit、无动作身份。每个API仍由服务端核范围；浏览器不依赖前端按钮隐藏证明授权。
6. 每步保存：真实方法/path/安全query、HTTP状态与固定error code、field_errors.path、业务revision/计数/成员hash等公开证据，关键截图。写请求正文和密钥头只在受控内存比较，不写通用日志。HTTP匹配只去除已知`/dev-api`代理前缀再严格匹配路径/对象，不能泛化任意前缀。

## 1. 语义定位速查

| 区域     | 实际定位/可见文字                                                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 页面     | h1“智能规则”；父section aria-label“规则列表区域”，原List aria-label“规则列表”                                                                                                         |
| 列表查询 | aria-label“规则名称”“规则状态”“对象层级”“每页条数”；按钮“查询”“上一页”“下一页”“创建规则”                                                                                              |
| 详情     | dialog/Drawer标题“规则详情”；所在目标行按钮“详情”；内部“编辑规则”“模拟”“启用”“暂停”“归档”“触发记录”                                                                                   |
| 二级编辑 | section aria-label“规则编辑容器”，h2“创建规则”或“编辑规则”；“返回规则列表”“关闭编辑器”                                                                                                |
| 未确认   | “关闭并保留未确认请求”“恢复原未确认请求”“刷新恢复会话”“使用原保存请求恢复”“打开原范围请求”                                                                                            |
| 原Form   | 规则名称/作用对象/所属投放师/所属团队/归因指标配置/观察窗口/组间关系/运行方式/间隔分钟/执行时刻/执行星期/调度时区/开始日期/截止日期/分析冷却分钟/每日最多分析次数，均有对应aria-label |
| 条件     | “添加条件组”“第1组添加条件”“删除条件组 1”，aria-label“第1组关系”“第1组第1条指标”“第1组第1条比较符”“第1组第1条阈值”                                                                    |
| 候选     | “规则归属姓名前缀”“归属每页条数”“指标每页条数”；“加载归属候选”“下一页归属”“上一页归属”“加载指标候选”“定位已保存配置”“下一页指标”“上一页指标”                                          |
| 范围     | dialog“选择规则账户范围”；aria-label“范围选择方式”“规则账户搜索”“规则账户状态”“规则账户授权状态”“规则账户操作者”“规则账户户商”“候选每页条数”                                          |
| 范围成员 | “查询账户”“上一页账户”“下一页账户”“冻结所选范围”“应用真实范围”；aria-label“规则快照成员搜索”“成员每页条数”；“查询冻结成员”“上一页成员”“下一页成员”                                    |
| 调度预览 | section aria-label“未来五次运行预览”；按钮“预览运行时间”“取消预览”；表头“本地运行时间（含偏移）”“对应UTC时间”                                                                         |

ElementPlus下拉先点击可见combobox/带aria-label容器，再选当前可见option的精确文字；存在同名列表/表单输入时先限定区域。Checkbox点击可见label/`.el-checkbox`，随后检查内部input checked；不对隐藏input调用check/uncheck，不force、不靠增加60秒超时掩盖定位错误。Drawer关闭按钮用当前可见dialog内aria-label“Close this dialog”或实际DOM公开名，先核DOM，不选择全局第一个关闭按钮。

## 2. 菜单、列表、游标

- [ ] 从若依原菜单进入“智能规则”，原layout/导航保留，真实GET `/api/v1/rules`响应200后列表才显示。若062菜单未出现，记录菜单/权限阻断，不URL直达冒充菜单通过。
- [ ] 名称填写字面contains（含`%`/`_`测试值），点击“查询”；核请求q符合实际原查询，不把它改成前缀。状态与对象层级选择后点击查询。缺乏原date/channel/profile筛选语义的参数不得由UI伪造，明确登记未覆盖。
- [ ] “每页条数”依次20/50/100/200，每次回第一页、实际请求page_size正确，响应条数不超过该档。201+fixture使next_cursor真实存在；下一页携原cursor，上一页回真实历史cursor，当前筛选/排序下无重复或遗漏。不以只看按钮亮灭代替HTTP。
- [ ] 修改名称输入但不查询，翻页仍使用旧已提交q；创建/编辑保存后显式refresh回首屏且保留旧appliedQuery和未提交输入。新revision改变clock后不发送旧cursor。
- [ ] 列表原字段与响应对账：名称、状态、对象、ownership、window、revision、next_run_at和调度。创建人/创建时间现原API未提供，UI明确“原接口尚未提供”，此项记缺口，不伪造当前用户/当前时间。

## 3. 详情→编辑二级页与只读

- [ ] 在精确Rule行点击“详情”，真实GET `/rules/{id}`200；逐项对原Rule15，Schedule7含null“不适用”，Decimal阈值原字符串保留。
- [ ] DRAFT/PAUSED点击“编辑规则”，先真实capabilities UPDATE成功，然后原Drawer model关闭/不再覆盖编辑页面；query严格`mode=edit&rule_id=<id>`。专属GET `/rules/{id}/edit-definition`和`/rules/edit-context`真实200且同revision/owner/profile绑定。
- [ ] edit-definition的stored_scope只有4键、真实521 count，并与rule.scope_snapshot_id/ownership一致。Form显示“已保存范围，保存时重新校验权限”；不为旧协作manifest访问另creator的私有snapshot成员，不出现伪hash/created_at。
- [ ] ENABLED/ARCHIVED定义完整可读但不可保存；ENABLED先走原暂停，ARCHIVED终态。无模拟来源时真实503，不把预览时间当Simulation。
- [ ] 仅edit身份从真实授权入口/二级地址读取时不借rules.read，不先探通用GET；仅create身份可开CREATE而不挂读列表。两者需实际服务端成功/403证据，不仅前端按钮。
- [ ] 返回列表后原List实例筛选保留；再次编辑为当前真实revision。非法/重复rule_id或CREATE夹rule_id明确地址错误，不发伪对象请求。

## 4. 原完整11字段与真实来源

- [ ] 编辑器名称、target_level三级、owner/team、scope、logic、groups、window四种、profile、schedule、cooldown、max_daily完整填写。POST/PUT只有11键；Schedule7键与互斥null完整，不增加浏览器默认字段。
- [ ] 创建默认仅原PRD已有非日期值。没有父真实日期/时区上下文时保持空；用“补充IANA时区”“加入时区候选”明确输入合法区，再在“调度时区”选择，不伪造平台当地时区。
- [ ] OWNER真实候选前缀和PROFILE当前source/version/完整ID，四档分页、前后页；改候选页不会重置未保存名称/阈值。相同version不同ID不混淆；当前停用profile保留历史标签但不能伪装当前有效。
- [ ] 改owner清原范围，按新owner/team重新读PROFILE和账户候选；不能借管理员caller范围转授owner不可读账户。来源403清旧敏感字段；503显示明确来源不可用，不以空候选成功代替。
- [ ] 条件根AND/OR、组内AND/OR；至多5组、每组10、合计20叶，至少1组1叶；原11指标/6比较符、阈值Decimal字符串及nullable语义不变。超过边界原前后端拒绝，不能截断提交。
- [ ] INTERVAL/DAILY/WEEKLY切换清不适用项：interval、time_of_day、weekday互斥null；366含首尾可用、367明确拒绝。cooldown=0有明确意义，空值不能补0。

## 5. 真实范围、跨页与freeze

- [ ] “选择账户范围”打开真实dialog，焦点落“规则账户搜索”；明确勾选IDS与全选过滤FILTER可切换。默认操作者/户商无真实候选则禁用并明确“尚无真实候选”，不能借accounts/roles/launch权限查候选。
- [ ] 原5filters严格对应q/status/auth_status/operator_user_id/vendor_id；四档候选页20/50/100/200，真实规则专属GET `/rules/editor-accounts`，无额外账户菜单请求。
- [ ] IDS跨两页显式勾选，当前计数准确；折叠“核对已选账户（每组50个，可移除）”核真实名称/ID并移除一项。零匹配不能冻结。
- [ ] FILTER查询得到521+完整结果；“冻结所选范围”POST `/rules/editor-scope-snapshots`：严格4键action/rule_id/ownership/selection，FILTER account_ids=[]，发送完整filter而非当前页IDs。UPDATE使用原quoted If-Match和原key，CREATE不带If-Match。
- [ ] 201真实Scope5显示count/hash/scope_version/created_at；成员页读取`/rules/editor-scope-snapshots/{id}/members`，四档/前后页，不通过name改当前成员集合。完成核对后“应用真实范围”才把真实scope id/count回Form。
- [ ] 取消本地选择不会删除已冻结服务端snapshot。完整50000/50001上限属于独立容量与API专项，浏览器521样本不能冒称五万验收。
- [ ] 关闭/取消焦点返回原触发器；移动端对话框不横向溢出视口，宽ID/hash可以换行或在表容器内部滚动。

## 6. 保存、CAS、幂等与未知结果

- [ ] 正常CREATE用原POST `/rules`201，UPDATE用PUT `/rules/{id}`200+当前quoted If-Match；实际审计/version/member manifest可由主线隔离SQL证据核对。保存成功回列表，显式首屏refresh保留筛选。
- [ ] 同正文no-op允许原revision/state，不要求凭空+1；变正文产生实际新revision/旧Simulation失效。另一会话先改revision，旧CAS真实409，表单保留明确错误，不自动覆盖。
- [ ] 默认不制造未知结果。若主线具“真实服务器已提交后丢响应”的受控网络fault，在严格隔离下执行：保存已发但响应断开→UI未确认；核后台一次实际写入，再关闭回列表，禁止新写，恢复原请求。没有该fault设施则记NOT_RUN，不注入SDK异常或route.fulfill充当真实未知。
- [ ] 恢复请求业务body、idempotency key和原If-Match逐字一致，只有真实当前会话CSRF可更新；原成功应返回同一回执，无新version/audit重复。第一次明确422不应永久占未确认；未知恢复遇403不应声称原写已取消。
- [ ] Scope未知同理：“关闭并保留待确认请求”→父“恢复原未确认请求”→“打开原范围请求”→子“使用原请求恢复”。旧head3回执在当前head4，即使members200仍历史不可应用，必须重新冻结，不能悄悄重新盖当前head。
- [ ] 真实撤销规则动作/管理团队/owner范围后下一请求401/403：旧定义/候选/成员不再可见，禁新写；原未知意图保持但不自动重发。切另一actor只显示泛化警告、不显示原body或Rule内容；本步骤必须实际会话/权限变更，不仅手改前端props。

## 7. 已接slot未来五次预览

- [ ] 在未保存Form调度中改“间隔分钟”后点击“预览运行时间”，实际POST `/rules/editor-schedule-preview`4键携当前草稿Schedule与原currentRuleRevision；只有当前CSRF，无If-Match/Idempotency-Key。不得创建Rule/Simulation/Task或增加audit写回执。
- [ ] 200显示真实reference_at UTC6、IANA、0—5条local offset+对应UTC6，不默认凑满5条。请求后修改Schedule/版本/owner/会话，旧结果立即清，迟到包不能当当前；保存/来源加载/SAVE或SCOPE未知时预览禁用。
- [ ] 真实空：选择结束日期已早于服务器reference的合法日区间，slots=[]，显示“当前起止日期与参考时间之后没有可运行时刻”，不是503空伪成功。
- [ ] DST：需主线实际服务端参考时间落到受测IANA下一缺失墙钟之前，或隔离SQL时钟真实后端测试明确注入（不能前端改Date/伪响应）。DAILY选择缺失02:30，查看skipped_local_times墙钟与中文原因，下一有效slot含正确offset；重复墙钟只运行一次。没有这样的参考时刻时浏览器该子项NOT_RUN，既有后端SQL时钟证据单列，不能伪自然等待。
- [ ] 403预览导致整个Editor敏感Form清理，原SAVE/SCOPE意图不被误删；503/409显示真实code，不产生enable资格。点击“取消预览”取消当前只读等待，页面不再显示该迟到结果。

## 8. 三视口与最终记录

在主线现行wide/tablet/mobile三个真实project分别执行，不自行另定仅桌面为全通过。每个记录viewport尺寸、菜单可用、列表宽表内部滚动、固定操作列、详情Drawer、ScopeDialog/下拉浮层、完整Form、预览UTC长字符串、错误与按钮加载/禁用、键盘Tab和焦点返回。禁止仅截图占位页或把所有请求503的壳页面当功能通过。

最终逐组记开发/测试/验收，不以整组标题打勾替代原字段：正常真实HTTP；隔离技术fixture来源；故障注入网络；时钟注入；生产凭据未测。每项给实际执行时间、请求/公开字段对账、截图/日志路径及失败保留。当前仍未完成的`/rule-hits`、Simulation续页、正向启用/调度/AI建议/执行权威来源等继续列清；RuleRuns不能代替全局触发记录。
