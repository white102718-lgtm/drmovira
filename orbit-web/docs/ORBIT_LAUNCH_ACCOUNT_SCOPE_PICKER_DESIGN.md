# 投放账户范围选择器：独立实施设计

日期：2026-11-08。仅设计，不接入正在复验的投放父页面，不修改 A 的范围合同、服务或现有账户页面。

## 1. 原需求与实际接口

原文精确位置：

- `data/ORBIT_Codex开发PRD/PRD-ORBIT.md:64`：跨页全选必须用 scope-snapshot，不由浏览器抓全量 ID 猜测。
- `PRD-ORBIT.md:344`：保留账户选择、搜索、仅看已选、跨页快照、计划负责人等。
- `contracts/WORKFLOWS.md:125`：IDS 必须非空 account_ids 且 filter=null；FILTER 必须空 account_ids 且 filter 非空；服务端一致性读取求权限交集，返回 hash/count/scope_version；成员分页读取；计划使用 snapshot 时 account_ids=[]；范围上限 50000、计划上限 500，不截断；执行仍须实时撤权校验。
- `contracts/PERMISSIONS.md`：账户引用须当前调用者与实际计划拥有者双方可读，且同租户/团队/投手/币种。

当前已存在的接口如下，不新增同义别名接口：

| 方法与路径                                 | 真实行为                                                                                           | 客户端边界                                                                 |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| GET `/api/v1/accounts`                     | 原账户目录与真实数据范围，支持名称/外部 ID、状态、授权状态、投手、户商及不透明游标                 | 手动选择候选；每次只读一页。不能自动循环读取成员来拼全选。                 |
| GET `/api/v1/scope-snapshots/capabilities` | 需要 accounts.read；返回 csrf_token、max_members=50000、max_plan_accounts=500                      | 只取得来源读取/冻结的上下文，不借 accounts.import 或 system.users。        |
| POST `/api/v1/scope-snapshots`             | 原 ScopeRequest，真实 201；CSRF + Idempotency-Key；同事务完整成员/审计/outbox                      | 无 If-Match/ETag 合同，不凭空加 scope revision。未知写结果保留原正文和键。 |
| GET `/api/v1/scope-snapshots/{id}/members` | q/page_size/cursor；20/50/100/200；当前人员、租户、授权版本和全体成员可见性即时重验                | 只查看已冻结成员；q 不改变该快照的选择集合。                               |
| 原 POST/PUT `/api/v1/launch-plans[/{id}]`  | 已真实接 AccountScopeStore.resolve_for_plan；解析实际 IDs，复核目标归属/单币种和双方读取，再写计划 | 不是向成员第一页拿到几个 ID 就当已全部验证。                               |

`src/api/orbit/scopes.ts` 已有原 SDK 类型/请求，`accounts/scopes/ScopeMembers.vue` 已有只读成员二级页。当前这些 SDK 返回值主要为 TypeScript 断言；新投放选择器的严格解析与写入结果分类应放在独立适配文件，先不修改 A 文件或把其页面改成投放页面。

## 2. 明确不新增的行为

### 2.1 手动勾选、单账户与取消勾选

手动模式维护用户明确勾选的有界本地集合，最多 500。单账户即大小为 1 的同一模式，不另造接口。

- 按账户系统 UUID 关联，外部数字 ID 始终为字符串。
- 跨页保留明确勾选的 ID；取消勾选只移除用户明确选择的那一项。
- “选择本页”只针对当前已读取且明确显示的可选行，不等于“所有筛选结果”。
- “仅看已选”展示这个本地明确集合。旧草稿中的尚未加载账户用原 UUID 标明未知名称，不伪造姓名、授权、币种或当前可用性。
- 原显式 ID 提交可以继续沿用 `account_ids=[...]`，无需为了选一个账户强制先创建 scope。若另行选择冻结这些显式 IDs，使用原 IDS POST；不能混成 FILTER 请求。

### 2.2 FILTER 全选不是可变的本地集合

FILTER 的原 schema 只有 `mode/account_ids/filter`，并且 additionalProperties=false。没有 excluded_account_ids、差集、PATCH 成员或派生快照接口。

本次核对的原文没有明确“FILTER 全选后排除若干项”的接口语义。因此本批：

- FILTER 成员二级页为只读，不画可用的排除勾选框。
- 切换到手动选择时明确说明需要逐项勾选，不自动抓全量成员转换成 IDS；原快照仍实际存在。
- 只允许手动模式本地取消勾选，不擅自改变 FILTER 的服务端集合。
- 不为我们内部讨论中提到的“排除”新增后端合同。若后续用户明确新增需求，另提受控服务端差集技术扩展，保持原 ScopeRequest 不变，由主线分配后端所有权。

### 2.3 没有 HEAD、TTL 或取消/删除接口

- 当前 scope 只有 capabilities/POST/members，没有 HTTP HEAD、GET 单个元数据、DELETE、cancel 路由。
- 025 表没有 expires_at 或 TTL；不能套用预检 15 分钟时效到账户范围。
- 当前快照能否继续使用取决于真实创建人员、租户、auth_version/指纹、完整成员可见性以及计划消费时归属/币种等规则。
- 用户在 201 后取消选择，含义是“不把这个快照用于本地草稿”；不发送不存在的删除请求，不宣称服务端已取消或清理快照。

## 3. 选择状态与数据结构

建议组件输出一个只在前端使用的判别联合，写计划时才映射原字段：

```ts
type PlanAccountSelection =
  | { kind: 'IDS'; account_ids: string[]; snapshot: null }
  | { kind: 'SNAPSHOT'; account_ids: []; snapshot: ScopeSnapshot }
```

不得把 `ScopeSnapshot.id` 放到 account_ids，不能把列表 cursor 放到 snapshot.id，也不能让 snapshot 与非空 IDs 同时进入 PlanWrite。

状态机：

| 状态             | 可执行动作                                     | 不能做的动作                               |
| ---------------- | ---------------------------------------------- | ------------------------------------------ |
| BROWSING_IDS     | 分页候选、搜索、明确勾选/取消、≤500 项本地确认 | 自动抓全量；把未读取名称当已验证           |
| BROWSING_FILTER  | 编辑原 ScopeFilter、查看当前候选、发起一次冻结 | 本地拼出 FILTER 全集合                     |
| READING          | 中止这一次 GET、明确重试、取消弹窗             | 迟到响应覆盖新筛选/新拥有者                |
| FREEZING         | 等待本次原 POST                                | 换模式/换 key/改正文/丢弃意图              |
| UNKNOWN_WRITE    | 同 key/同正文/同冻结上下文重试；保留原意图     | 假取消、另建新范围、自动重试或偷偷换会话头 |
| SNAPSHOT_READY   | 分页查看成员、确认使用或取消本地使用           | 将一页结果当整个集合、FILTER 排除          |
| SNAPSHOT_INVALID | 展示明确失效原因；用户重新选择/冻结            | 沿用旧 cursor 或把旧范围默默缩小           |

创建请求的 key 只在明确新意图时生成一次；当前请求规范正文、key、冻结 CSRF 和 actor/ownership 上下文留在内存。未知结果期间通过 `locked` 事件让未来父页面保留原组件、禁止路由/标签页离开，并使用原浏览器离开保护。此设计不发明未应用弹窗数据的新持久缓存协议，也不把 Token/CSRF 写入草稿缓存。

## 4. 筛选与候选来源

原 ScopeFilter exact 字段：q、status、auth_status、operator_user_id、vendor_id，全部必须存在，未使用项是 null。

- q 按原规则 NFC/trim、最多 100 码点；账户名称和完整外部数字 ID 搜索语义由真实账户 API 决定。
- status/auth_status 使用原枚举，不把 UNKNOWN 或 DISABLED 自动改成 ACTIVE。
- 投放选择器的 operator_user_id 默认绑定当前计划 owner_user_id，并清楚显示该负责人范围。单个计划不能跨投手。owner_team_id 不是 ScopeFilter 的字段，不能向原请求偷偷追加；团队及最终双方权限由计划消费严格复核。
- vendor_id 默认 null；如未来从父页面传入已授权的户商过滤，必须沿用原 UUID，不借维护引用目录权限，也不凭本地拼昵称生成候选。独立组件首批不创造新的户商候选接口。
- 日期只影响账户消耗查询，不属于原 ScopeFilter，不加入冻结成员条件。
- 成员查看的 q/page_size 与候选筛选分开保存。搜索冻结成员只改变显示，不令快照重新生成。

手动模式的数据来源显示账户真实 owner/team/currency/auth/account 状态；只是可读资料。未知或不符合当前计划归属的项说明原因，不伪造授权成功。原草稿允许部分业务字段暂缺，最终保存/预检的实时检查仍不可被客户端“可选”标签替代。

## 5. 快照创建、核对和失效

### 5.1 原 POST 与结果

FILTER 请求示例，字段保持 exact：

```json
{
  "mode": "FILTER",
  "account_ids": [],
  "filter": {
    "q": "用户实际输入",
    "status": null,
    "auth_status": null,
    "operator_user_id": "当前计划真实拥有者UUID",
    "vendor_id": null
  }
}
```

示例是结构说明，不是可用业务数据。服务端 201 才保存真实 id/count/hash/scope_version/created_at。count=0 是合法空范围，但不能确认用于至少一账户的计划；count>500 显示真实数量并拒绝用于计划，允许查看成员和缩小筛选，不截断到 500。不能把“原范围允许 50000”解释为“计划允许 50000”。

### 5.2 成员查看二级页

- 原 GET 每次一页，20/50/100/200；不透明 cursor 与查看 q/page_size、snapshot 和权限绑定。
- 上页保存实际旧 cursor；查看筛选/size 改变后只从首游标读取，不跨条件重放。
- `scope_version` 必须匹配已取得快照。401/403/404/409 清除旧成员显示并禁用确认；只保留说明失效所必需的元数据，不在撤权后继续展示旧成员名称。
- 网络失败保留当前已知选择意图，给出显式重试；不把失败转换成零账户或授权通过。
- 原成员 name 允许 1—10000 码点，external_id 为 1—64 位数字字符串；显示可使用 CSS 收起和完整查看，不在数据层截断名称或转 Number。

### 5.3 何时失效、何时不失效

- 候选过滤、actor/计划拥有者上下文变化后，旧选择不能静默变成新目标的选择；保留原资料并明确重新选择，未知写请求除外，须先确认原结果。
- 服务端 snapshot() 逐次检查创建人员、租户、auth_version/指纹与全体成员当前可见性；一项越权整份拒绝，不返回“剩余可见部分”。
- 当前账户仅改名并不会自动让整个快照失效，成员页面保留冻结名称。不能拿账户名称普通 revision 推导范围失效。
- `resolve_for_plan` 额外检查冻结及当前 owner/team/currency 一致、目标归属、1—500、单币种；后续 validate_sources 再检查双方可读和本地仍绑定。成员 GET 成功不等于这些检查已经全部通过，更不等于身份/执行授权。

## 6. Plan HEAD、保存与真实快照存续

这里的“当前 head”指父页面原 GET Plan，不是新增 HTTP HEAD。

- 新建草稿无服务器 Plan ID，不做伪 head 请求。
- 编辑既有草稿时，选择器不覆盖原 form。未来父接线在采用新来源前可按原 GET 读取当前版本；与原编辑基线不一致时提示陈旧，保留本地未保存配置，不自动替换整个草稿。
- IDS 输出映射原 account_ids；SNAPSHOT 输出映射 account_ids=[]、account_scope_snapshot_id=真实 id。保存继续使用原草稿冻结 key/body/引号 CAS，不能因为 UI 翻页或成员刷新换写入意图。
- 真实后端消费会将工作副本解析为实际 ID 并把公开 account_scope_snapshot_id 清为 null；不可变版本依赖另外保存 scope_id/hash/授权水位和 resolved_ids_hash。公开 Plan 编辑回读不能再同时带非空 IDs 与旧 scope。
- 因此保存后按服务器返回的实际 account_ids 回显，并说明已冻结实际账户；不把本地旧 snapshot ID 冒充公开 Plan 仍有效的授权字段。
- 使用 snapshot 尚未解析为实际 IDs 时，树展开计数可以用真实 snapshot.count 作明确标注的本地估算，但服务端消费后仍重新检查 10000 上限。逐账户身份编辑应等待真实账户 IDs，不能循环抓 scope 全体成员来拼身份表。
- 取消窗口或替换本地选择，不会删除已创建的不可变快照；当前也没有客户端可声明的服务端过期时刻。

## 7. 建议精确文件所有权

独立批可以先实现并冻结这些新文件，不接 parent：

| 文件                                                | B 责任                                                                                                                                                |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/api/orbit/launch-account-scopes.ts`            | 原 scope API 的严格投放适配：Exact DTO、201/200、UUID/安全整数/原字符串界限、同 actor 的冻结头、GET Abort 与 mutation 未知结果分类；不更改原 schema。 |
| `src/views/orbit/launch/PlanAccountScopePicker.vue` | 手动 IDS 与 FILTER 冻结状态机、受控原 POST、只读分页成员和明确确认/取消；暂不作为父表单来源。                                                         |
| `tests/orbit/launch-account-scopes.test.ts`         | 严格 DTO 与请求边界、同键、不泄露 URL 凭证、读取/写入未知分类。                                                                                       |
| `tests/orbit/plan-account-scope-picker.test.ts`     | 真实 ElementPlus + 明确网络替身，仅内部组件证据。                                                                                                     |
| 本设计文档                                          | 记录实现/纯测/真实验收各自证据，不混记。                                                                                                              |

暂不改：A 的 scopes.ts、accounts/scopes/\*_、account*scope*_；受测 index.vue、TemplatesPanel.vue、SourcePicker.vue、DraftEditor.vue；共享权限/路由/凭据/runner/E2E 配置；任何后端表和合同。

父接线另由主线释放最小所有权后实施：将原账户选择入口接判别联合、恢复/未知锁、旧身份孤立提示和实际保存返回处理。root 统一配置真实浏览器 fixture，不由组件创建假业务 endpoint。

## 8. 开发、测试、验收拆分

首批内部测试至少覆盖：

1. 一个账户与跨页明确勾选/取消；本地 ≤500；不因新候选页覆盖旧勾选；仅看已选。
2. FILTER 原五字段完整/IDS 互斥；不接受 excluded_ids 或 cursor 作为 snapshot。
3. 真实 201 元数据；0、500、501 的计划确认边界；不把 count 收缩或复制为部分 IDs。
4. 同 key/正文/冻结上下文的未知重试；标准明确失败与网关/无响应分开；无自动重试。
5. 读取消/关闭/切上下文/卸载迟到保护；未知 POST 不假取消或强制卸载。
6. 成员四档分页/查看搜索/上页历史；搜索不改范围；权限或授权版本改变整份失效。
7. 名称最大长度和 64 位外部 ID 字符串；500 行本地勾选上限；无自动循环抓全量。
8. 原 API 没有 HEAD/TTL/DELETE，组件不得发送这些请求或宣称它们成功。

随后真实验收必须单独证明：同租户 USER/TEAM/根角色的合法范围与撤权/目标拥有者交集、跨页快照、501 拒绝而不截断、改名不重写快照、未知请求重放、保存返回实际 IDs 与依赖快照、三个视口确认/取消/仅看已选与成员二级页。纯组件替身、静态设计和列表构建都不计为这些真实验收。
