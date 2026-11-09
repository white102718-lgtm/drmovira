# RuleScopeSelector 账户范围选择器

本组件只使用规则专属 Scope SDK。新增 `src/views/orbit/rules/RuleScopeSelector.vue`、专属挂载测试与本文档；不注册主页面/菜单/路由，不修改 SDK、父页、公共布局或后端。

依据 `data/ORBIT_Codex开发PRD/PRD-ORBIT.md:54,58,64,236,362`：原动作与双方当前范围、带引号CAS/幂等、20/50/100/200游标、跨页快照而非浏览器拉全量ID、规则只定义条件/范围/调度。实际技术合同沿 `rule_editor_scope_contract.py` 三端点、原Scope5/Member3/Page4，不沿投放Plan500限制。

## 父组件受控接口

| prop                          | 必需来源                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------- |
| modelValue                    | 真实打开/关闭状态                                                                     |
| action                        | 原CREATE或UPDATE                                                                      |
| ruleId                        | CREATE显式null；UPDATE实际规则UUID                                                    |
| ownership                     | 当前已选owner_user_id/owner_team_id，不由组件猜测                                     |
| currentRuleRevision           | CREATE null；UPDATE当前正安全整数RuleRev                                              |
| csrfToken                     | 当前真实EditorContext返回值                                                           |
| permissionCodes/contextKey    | 当前原动作及认证生命周期；相同凭据重新登录也须变化contextKey                          |
| disabled                      | 父编辑器整体禁用态，不能借此绕权限                                                    |
| operatorOptions/vendorOptions | 可选真实{id,label}筛选候选；无来源则对应控件明确禁用，不加载其它菜单/动作             |
| pendingIntent                 | 可选父已接管的 `{intent: FrozenRuleEditorScopeIntent, context: string}`；只能内存保留 |

事件：

- `update:modelValue(false)`：关闭本地Dialog；不代表取消服务器冻结。
- `choose(Scope5)`：真实POST成功并经过当前成员读取核对后，用户点击“应用真实范围”才回传；不自动改RuleWrite。
- `pending-intent(record|null)`：第一次发送前发完整冻结记录；明确成功或首次明确拒绝后发null。父必须内存接管，若组件卸载后需恢复，重新挂载时传回pendingIntent。不接回时只承诺原实例内存恢复，不能声称自带持久恢复。
- `locked(boolean)`：有在途或未确认意图时为true。即使弹窗已关闭，父仍须阻止新scope写；不能把关闭或卸载当成结果已确认。

pending含会话CSRF与请求键，仅内存保留，不能写日志、DOM、URL或浏览器持久存储。

## 选择和冻结

原五filter齐全：q、status、auth_status、operator_user_id、vendor_id。名称/平台ID输入不填UUID；操作者/户商只接受父真实候选。没有来源时不提供假选项或默认业务ID。

候选每页20/50/100/200，保存前/后原cursor。点击查询时冻结已提交filter和page_size，尚未提交的输入不污染翻页。有效空页明确零匹配；未查询、加载失败或0匹配时不能以FILTER冻结。

- IDS：只有用户明确勾选的Member3加入Map，跨页保留；原1..50000上限，不自动勾选首行或把当前页当全部。已选核对每组渲染50项并可移除，不一次渲染5万行。
- FILTER：selection.account_ids始终[]，提交已查询的完整原filter。真正全量数量来自服务端Scope5，不能从当前页估算。没有差集合同，不提供FILTER逐个排除。
- 所有方式都真实POST后得到Scope5，再读原members核对。显示真实id/count/scope_version/hash/UTC。没有Scope0或未落库假成功。
- 成员独立q、四档和cursor历史；搜索只查看冻结成员，不改变快照。成员失败403/404/409/503等明确显示、旧快照不可应用；成功读取才能重新解除本地不可用标记。关闭后再打开已有回执会重新读成员，不能直接沿用旧资格。
- 最终保存仍由服务器当前原动作、owner交集、scope与CAS复核。本地回执不提供永久授权。

## 并发、未知与恢复

第一次发送前同步固定四键body、key及原quoted If-Match。CREATE无版本头；UPDATE使用原currentRuleRevision。没有自动重试或新键接管。

未知时允许显式“关闭并保留待确认请求”，不会困住用户。若正在发写，关闭取消本地等待并保守标未知、保留原pending；晚响应不自动应用。已关闭但仍有pending时，不能另发新scope冻结。

稳定恢复绑定是actor生命周期contextKey + action/rule/owner/team。读取和选择还绑定当前RuleRev/权限代际：改变时取消旧读并清空旧选择/回执。未知恢复不要求后来的head或无关权限数组逐字等于原值，仍必须当前原动作有效，并发送原body/key/If-Match，由服务器先重放/再CAS。不同actor、owner或rule绝不重发旧意图。

恢复成功只确认原Scope结果，不能直接当当前可应用。组件从原frozen If-Match单独记录snapshotBoundRevision，不拿当前head给旧回执重新盖资格。head3未知后当前head4，原If-Match3恢复201、成员即使真实返回200，也只显示原回执供历史核对、明确不可应用，须重新冻结；不能用mock409遮蔽该情形。恢复后来遇403/CSRF等失败也不抹掉第一笔未知，避免伪称原请求未提交。

经主线裁决，同actor生命周期、原action/rule/owner/team绑定下，**仅用户手动恢复**可用当前真实csrfToken重建本次传输认证；原pending、业务body、幂等key、原If-Match逐字不变。认证是当前请求门禁，不是原幂等业务payload。没有自动刷新/重发，不需要修改冻结SDK。

401/403候选或成员响应会立即清除旧候选、已选名称、旧快照/成员及游标，独立accessDenied阻断新冻结和应用，不依赖父props权限及时刷新。页面提供显式“重新验证当前访问”，必须重新取得当前候选；普通网络503仅显示错误，保留本地明确选择供重试。pending原意图不因此丢失，恢复仍须当前原动作与服务端授权。

## Modal和验证范围

使用原ElementPlus Dialog焦点圈；打开聚焦实际搜索输入，关闭/卸载归还仍连接的触发器。写入/未知期间不使用Escape或遮罩偷偷关闭，但提供显式关闭保留意图。认证变化隐藏旧候选/快照和不属于当前恢复上下文的对象数据。

最终专属实际ElementPlus挂载32/32 PASS15.75秒（测试函数12.94秒），全局check:orbit PASS，三文件Prettier与当前机械检查另随冻结记录。全部SDK调用是替身。覆盖原动作、无额外账户读取、IDS跨页、FILTER完整五字段、四档cursor、zero/503、回执后choose、当前CAS、未知同键恢复、父接管跨卸载、原head与members200历史回执、CSRF手动更新、401/403即时清数据和锁新写、网络保留选择、不同actor/owner/rule、晚回/取消、上下文旧游标清理、再打开复核及Dialog焦点hook。

交叉只读审查发现最初24项范围不足：head漂移只测了members409、未测允许读取历史成员的200；候选/成员403仅显示错误，旧选择仍可能在本地可见。已修原head独立资格绑定与即时accessDenied清理，并增加上述正反负例；未放宽原断言或更改成员API制造409。

焦点测试触发真实Dialog的opened/closed生命周期事件验证输入focus/触发器恢复；并非已运行三视口或自然浏览器Tab/焦点圈验收。没有DB、真实HTTP、容量或平台调用；真实后端scope资格仍由主线专项与后续页面联调验证。

## 当前同主体恢复接线

原业务正文、幂等键及版本不变；首次写前实际读取原六动作恢复身份，手动恢复须再次同actor/tenant核验。新标签页登录和父页只读身份复核不自动发送写请求。完整约束与实际测试见 [ORBIT_RULE_RECOVERY.md](ORBIT_RULE_RECOVERY.md)。此节点仍需主线真实HTTP/浏览器验收，不继承旧UI证据。
