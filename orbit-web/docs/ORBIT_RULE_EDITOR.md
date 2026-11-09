# 规则受控编辑容器

`RuleEditor.vue`整合已冻结原11字段Form、规则专属Context/Owner/Profile候选、ScopeSelector及原create/update SDK；只作为父页容器，不注册路由或菜单。

## 父接口

props为`ruleId:string|null`、实际认证生命周期`contextKey`、当前`permissionCodes`、可选真实业务`defaults{timezone,start_date,end_date}`/`timezones`、父回传的`pendingIntent`。事件为`saved(Rule)`、`close`、`pendingIntent(record|null)`。父页须保存pending记录并回传，才能跨关闭/卸载恢复；组件不使用持久存储记录敏感业务正文。

CREATE仅取真实CREATE Context。UPDATE并行读取UPDATE Context与专属edit-definition，并核id/revision/ownership/profile绑定一致；版本漂移明确409重新加载。只用rules.create/edit，不借rules.read、accounts、monitor、system权限。ENABLED/ARCHIVED只读；启用规则须先通过原暂停流程。

## 完整字段与真实候选

原RuleWrite11字段完整交给Form：name、ownership、target_level、scope_snapshot_id、logic、groups、window、metric_profile_id、schedule7、cooldown_minutes、max_daily。归属候选原OWNER label前缀，profile候选原UUID精确定位；四档20/50/100/200及游标前后页，保存已经真实加载项避免分页覆盖尚未保存的选择。指标展示source/version/完整ID，没有伪造profile.name。历史版本单独展示，当前不可用不能提交。

沿原模块4/FIELDS既有Form默认：新建规则、AD、AND、spend GTE未填阈值、LAST_3D、INTERVAL30、cooldown60、max_daily5。时区和起止日期不取浏览器/UTC默认；由父实际业务上下文传入或用户明确选择合法IANA。金额仍逐账户自身币种解释，不换汇、不跨币聚合。

原sealed范围显示真实count及“已保存范围，保存时重新校验权限”，不构造Scope5、hash或时刻，不要求访问其他creator私有snapshot。原owner保持时允许交给save完整复核；owner变化必须新scope。新scope只由真实规则专属Selector取得，不把当前可见页拼成全量。

## 失败与恢复

新写入在发送前冻结完整原body/key/quoted IfMatch并通知父。网络/未知回执保留意图，手动恢复保持三项不变，仅传输认证换当前真实CSRF。当前head变化不阻原成功键恢复；actor/rule不同不能重发。恢复前刷新当前Context，当前动作/服务器再次授权，不自动请求恢复。首次明确422等拒绝清pending，恢复遇403等仍不推断原未知请求从未成功。

关闭中断本地等待但不抹进行中意图；迟到结果不会覆盖当前上下文。Scope未确认记录独立传父，恢复后只按原owner绑定，不自动转移；旧head scope成员可读不代表可应用（由Selector原head规则阻断）。401/403清敏感规则、候选和成员视图，保留未确认意图供当前动作下明确确认。普通503显示真实来源错误，保留本地修改但禁止保存。

## 验证范围

挂载使用原ElementPlus与真实Form，SDK为受控替身；Selector通过组件协议替身核容器接线，其内部32项独立挂载已有证据。此批不等于真实候选HTTP、页面菜单、跨浏览器或后端规则整体验收。主线后续接真实父页并统一三视口验证；Simulation/Run来源及正向ENABLE仍沿真实后端状态，不在容器伪造。

本轮专属容器20项与definition SDK8项共28项定向通过；类型与格式另行核对。未运行共享DB、服务或浏览器。

## 后五次预览接力

Form可选schedule-preview槽传当前Schedule副本，Editor接只读RuleSchedulePreview，读取原UPDATE当前版本或CREATE空版本与当前CSRF。修改Schedule/owner/上下文清旧预览，源加载/保存或范围未知期间禁读；预览401/403触发同Editor敏感数据清理，pending SAVE/SCOPE不被清除。不会更改原保存正文或产生Simulation资格。原UI协议仍需主线真实浏览器验收。

## 当前同主体恢复接线

原业务正文、幂等键及版本不变；首次写前实际读取原六动作恢复身份，手动恢复须再次同actor/tenant核验。新标签页登录和父页只读身份复核不自动发送写请求。完整约束与实际测试见 [ORBIT_RULE_RECOVERY.md](ORBIT_RULE_RECOVERY.md)。此节点仍需主线真实HTTP/浏览器验收，不继承旧UI证据。
