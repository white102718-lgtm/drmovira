# 规则专属账户范围 SDK

新增 `src/api/orbit/rule-editor-scopes.ts`，独立测试与本文档；未修改原SDK、Form、List、权限、路由或公共配置。后端合同来自 `rule_editor_scope_contract.py` / `rule_editor_scope_routes.py`，selection继续原 `account_scope_contract.py`。规则范围不能借用投放或账户权限接口。

## 三个准确端点

```ts
ruleEditorScopesApi.accounts(
  { action: 'CREATE', owner_user_id, owner_team_id, q, page_size: 50 },
  signal,
)
ruleEditorScopesApi.accounts(
  { action: 'UPDATE', rule_id, owner_user_id, owner_team_id, cursor },
  signal,
)
ruleEditorScopesApi.members(snapshot_id, { q, page_size: 50, cursor }, signal)
const intent = freezeRuleEditorScopeIntent(body, auth)
await ruleEditorScopesApi.create(intent.body, intent.auth, signal)
```

| 方法     | HTTP                                             | 响应                      |
| -------- | ------------------------------------------------ | ------------------------- |
| accounts | GET `/rules/editor-accounts`                     | 原Member3 / Page4         |
| create   | POST `/rules/editor-scope-snapshots`，严格201    | 原Scope5，count为1..50000 |
| members  | GET `/rules/editor-scope-snapshots/{id}/members` | 原Member3 / Page4         |

请求统一位于 `/api/v1` 下。只复用 `launch-account-scopes` 的纯 `checkScopeRequest` / `parseScopeSnapshot` / `parseScopeMembers`，不调用其接口或要求 launch/accounts/monitor 等其它模块动作。

### GET查询

accounts需要 action及实际owner_user_id/owner_team_id；CREATE不传rule_id，UPDATE必须完整rule_id。可选原 q/status/auth_status/operator_user_id/vendor_id/page_size/cursor。status是ACTIVE/DISABLED/UNKNOWN；auth_status是AUTHORIZED/EXPIRED/REVOKED/UNKNOWN。未筛选时省略字段，不传null。没有日期、归因配置或任意扩展字段。

members仅 q/page_size/cursor，scope自身由服务端复核所属原动作与当前范围，不能通过新增action参数改变所有权。

四档20/50/100/200，cursor保留原串，不解码或按页号编造。q先拒控制/非法Unicode，再trim+NFC，最多100码点。accounts沿原账户short*text(required=false)，全空白可规范为空；members沿rule.\_text，原空串可用，但非空全空白拒绝。后端原成员搜索是ASCII数字或act*数字精确external_id，否则真实名称字面前缀；客户端不自加通配符、截断前导零或解释业务搜索。

参数和业务UUID必须来自父真实Context/候选，不提供手填UUID界面。

### POST四键与原selection

body四键必须齐全：action、rule_id、ownership、selection。CREATE的rule_id必须显式null，UPDATE必须UUID。ownership严格owner_user_id/owner_team_id两个UUID。

selection原三键mode/account_ids/filter：

- IDS：原始输入1..50000，filter=null；**数量先于去重校验**。规范UUID重复（含大小写变体）精确本地422 DUPLICATE_VALUE和原 `/account_ids/index` 指针，不静默去重、截断或沿Plan500限制。
- FILTER：account_ids必须空数组，filter完整五键q/status/auth_status/operator_user_id/vendor_id，可选项显式null。客户端只提交原筛选，由服务器原子冻结完整交集；不遍历可见页拼成“全选”，不发明排除差集。

复用原纯parser前，对q按实际后端规则规范，保留调用方对象不变。序列化正文不得超过原2,500,000 UTF8字节。IDS响应count必须完整匹配已提交IDs数量，不能静默丢成员。FILTER实际count仅由服务端返回，SDK不从当前页估算。

## 写入、CAS及未知恢复

auth包含真实EditorContext csrf_token、用户意图idempotency_key；UPDATE额外要求quoted正安全整数if_match（当前RuleRev），CREATE禁止携带该字段。没有额外取accounts或scope capabilities的请求。

`freezeRuleEditorScopeIntent`同步验证、复制并冻结四键body、selection及数组/filter、ownership、auth；不会生成随机键。调用方须在第一次发送前保存这个只在内存存在的intent。SDK发请求前同步序列化wire body，后续表单变化不能改在途请求。

网络中断、超时、已发送后取消、坏响应/非201、认证晚回可能无法确认已提交结果，错误 `unknown_result=true`。调用方只能手动复用同intent.body/intent.auth，不能改key/CAS/body重新提交，也不能把取消请求当作服务器取消成功。SDK不缓存意图、不自动重试或重新生成键，调用方必须保留跨弹窗生命周期的原回执。

真实服务器403/409/422/503等规范错误保留status/code/message/path/request_id/retryable，`unknown_result=false`，不全部包装成网络未知。Cookie现会话CSRF覆盖与旧intent不一致时，在fetch前409 CSRF_CONTEXT_CHANGED，未发送故unknown=false。已取消的首次请求也不发送。

未知/原意图含CSRF，只保留内存，禁止写日志、URL、DOM或持久存储。服务端仍复核原create/edit动作、双主体scope、CAS和幂等；签名或本地readonly不提供服务端授权。

## 响应与生命周期

Scope5严格解析id/count/scope_version/hash/created_at，count1..50000、hash64小写hex、真实UTC；Member3严格account_id/external_id/name，保留原外部ID前导零与名称，不添状态或货币假字段。Page4最多200且不能超过本次请求页大小，重复ID/无成员却仍有next_cursor拒绝。

沿当前orbitAuthHeaders/orbitCredentials、原PlanHttpFieldError与RuleApiError机制。对读取返回AbortError；已发送的写取消保留REQUEST_ABORTED unknown。认证前后指纹变化丢弃迟到值；父仍须认证epoch/contextKey处理相同凭据ABA并取消旧读取。

客户端15秒有界超时**只是客户端设置**，不能代替原后端10秒或容量标准。候选页最多200；流式UTF8响应预算16MiB兼容原最长名称，不截断合法长名。取消/失败移除listener、释放reader/timer，不透传任意异常正文。没有轮询或平台请求。

## 当前验证

- `pnpm exec vitest run --config vitest.config.ts tests/orbit/rule-editor-scopes-api.test.ts`：26/26 PASS，1.36秒，测试函数105毫秒。只有fetch/auth替身；没有DOM/DB/浏览器。
- 包括三个精确rules URL、四键201、UPDATE/CREATE头、重复与5万DTO边界、FILTER空IDs、冻结防变/手动同键重试、四档cursor、q差异/NFC100/101、严格参数、真实错误与未知区分、CSRF/取消/15秒。
- 首次23/24通过，路径断言测试错误地假设Vitest已加载/dev-api环境；补显式隔离stubEnv后保留三个严格URL断言通过。没有改变生产路径或放宽断言。
- 5万仅输入合同边界，不是5万成员真实SQL或容量验收。当前后端源仍在开发，不能根据纯测宣称冻结/资格来源已实测。
- 三文件格式检查随冻结记录；类型检查按主线采样限制尚未运行，后续释放后再查。禁止本次DOM/全量/build；原SDK/Form/List不变。
