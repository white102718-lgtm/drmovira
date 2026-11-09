# Rule Editor 只读 SDK

本次仅新增 `src/api/orbit/rule-editor.ts`、对应合同测试与本文档，没有修改原 RuleWrite11、Rule15、MetricProfile12 或既有 rules SDK。两个技术 GET 的权威来源是后端冻结的 `rule_editor_contract.py`、`rule_editor_store.py`、`rule_editor_routes.py`；原字段合同继续沿用 `data/ORBIT_Codex开发PRD/contracts/openapi-current.json`。

## 调用协议

```ts
ruleEditorApi.context({ action: 'CREATE' }, signal)
ruleEditorApi.context({ action: 'UPDATE', rule_id }, signal)
ruleEditorApi.options({ action: 'CREATE', kind: 'OWNER', q, page_size, cursor }, signal)
ruleEditorApi.options(
  {
    action: 'UPDATE',
    rule_id,
    kind: 'PROFILE',
    owner_user_id,
    owner_team_id,
    q,
    page_size,
    cursor,
  },
  signal,
)
```

- `GET /api/v1/rules/edit-context`：仅 action/rule_id；CREATE 禁止 rule_id，UPDATE 必须完整 UUID。
- `GET /api/v1/rules/editor-options`：在 target 上增加 OWNER 或 PROFILE。OWNER 禁止 owner 两字段；PROFILE 必须 owner_user_id、owner_team_id。参数只能从当前真实上下文/候选传入，不意味着页面应让用户手填 UUID。
- OWNER `q` 是人员显示 label 的**字面前缀**，不是规则列表名称包含筛选。SDK 不插入 `%`，不自行解释 `%/_/!`；服务器负责 literal LIKE 转义。PROFILE `q` 仅完整指标 UUID，不能用 version 当名称搜索。
- q 先拒控制字符/非法 Unicode，再 trim+NFC、按码点最多100；原空串可查询，非空但全空白拒绝。UUID 规范为小写，不修改调用方对象。
- page_size 20/50/100/200，未传由服务器默认50；cursor 是不可解释的原字符串，最多2048码点。筛选、owner、page_size、规则版本、当前权限或来源变化都可能使游标409；父组件必须清空旧游标并从首页重读，SDK不静默修复或重试。
- 所有请求无 body、无写入幂等键。未知参数和不合法组合在 fetch 前本地422 `FIELD_INVALID`，保留字段 path。真实服务器400/403/409/422/503及原 code/path/request_id 不改写。

## 精确响应

Context **8字段**：action、rule_id、rule_revision、editable、csrf_token、default_ownership、selected_owner、selected_profile。

- CREATE 的 rule_id/revision/selected_profile 均 null，editable=true；UPDATE rule_id 必须匹配当前请求，revision 是正安全整数。
- default_ownership 只有 owner_user_id/owner_team_id。
- selected_owner 只有 item/can_keep，item 是 null 或 OwnerOption **4字段** id/team_id/name/team_name。item 存在不代表可提交；can_keep=false 必须由 UI 明确处理。缺 item 不允许 can_keep=true，item 的 owner/team 必须与 default_ownership 一致。
- selected_profile 是 null 或 **4字段** id/bound_version/current/status；current 是 null 或复用既有 `parseMetricProfile` 的原12字段。CURRENT 要当前版本等于原绑定版本，CHANGED 必须不相等，UNAVAILABLE 仅 current=null。不能从版本字符串、非空ID、verified 或候选存在推断执行能力。
- 原 MetricProfile 没有 name；父 Form 的 label 必须从真实 source/version/id 派生，并保留完整 ID 区分同 version。

OWNER/PROFILE Page **4字段**：items、next_cursor、data_as_of、scope_version。每页最多200并不得超过本次请求页大小，ID不得重复；data_as_of 是真实有效UTC时间，scope_version 正安全整数。PROFILE 精确UUID q 返回其他ID拒绝。空页必须 next_cursor=null，不伪造剩余游标。Owner显示文本保留原值、不裁剪；4096码点仅SDK异常响应预算，不是新增业务字段限制。

SDK 的 strict parser 公开为 `parseRuleEditorContext`、`parseRuleOwnerOption`、`parseRuleOwnerPage`、`parseRuleProfilePage`，以及对应类型。返回的 csrf_token 是真实当前编辑辅助会话值，不由客户端生成。

## 传输和错误

复用 `orbitAuthHeaders`、`orbitCredentials`、`parsePlanHttpFieldError` 与原 `RuleApiError` 的错误字段；本 SDK 导出 `RuleEditorApiError extends RuleApiError`。父组件可按同一错误呈现机制处理。

GET 仅接受200，cache=no-store；HTTP201、错误对象、错误字段或错对象响应不会被化为空候选。原错误 envelope 五字段严格解析，保留 retryable/request_id/source='server'，不回显额外响应正文。

每次读取15秒预算，支持已取消/在途/正文流取消；外部取消抛 AbortError，超时 READ_TIMEOUT，网络中断 NETWORK_UNAVAILABLE。UTF8致命解码及2MiB流式技术预算防无界候选响应；正常候选上限200。失败/取消均移除监听并释放 reader/timer；清理失败不覆盖原错误。没有自动重试。

请求前后捕获原 auth headers/credentials 指纹；认证变化返回409 SESSION_CONTEXT_CHANGED并丢弃迟到值。SDK不能观察同凭据退出再登录的私有 epoch；父页面仍必须用真实认证生命周期 contextKey 和 AbortController 阻断 ABA/关闭后晚响应，不能只依赖此指纹。

## 验证范围

- 专属 Vitest **24/24 PASS**，最近一次1.19秒（测试函数31毫秒）。覆盖严格 DTO、两 action/kind、四档 cursor、NFC100/101、调用方不变、当前/失效 owner与profile、原503/409、Cookie/Bearer变化、abort/15秒超时/流取消与清理、UTF8/2MiB预算、请求页大小与精确UUID过滤。
- `pnpm check:orbit` PASS；三文件 Prettier 检查另随最终冻结确认。
- fetch/认证均为受控替身，只证明 SDK 合同与协议，不是后端 SQL、真实 HTTP、权限来源或三视口验收。没有 DB、服务、平台请求、路由或菜单修改。
- 原 Form/List 未接此客户端；下一步由父页面读取真实 Context、分页 Owner/Profile 候选并接实际 rules 专属 scope helper。缺来源503、候选变化409必须显示并重新读取，不能填默认 UUID 或借账户/监测/系统人员动作。
