# RuleRuns 运行记录分页组件

独立文件 `src/views/orbit/rules/RuleRuns.vue`，原生 Vue3 / Element Plus；通过 RuleList 详情内“运行记录”入口挂载。没有新增路由、HTTP API、权限、UUID输入或运行来源。

## 原合同与范围

- `data/ORBIT_Codex开发PRD/PRD-ORBIT.md:24,242,362,364` 规则范围保留触发记录，命中走分析/建议流程；不得用列表空值冒充来源已就绪。
- 原 `contracts/openapi-current.json`：`GET /rules/{id}/runs`，RuleRun8 与 Page4。请求与响应继续由冻结 `src/api/orbit/rules.ts` 的 `rulesApi.runs(id, query, signal)` 校验。
- 八字段完整显示：id、rule_id、rule_revision、schedule_slot、snapshot_id、state、hit_count、reason_code。UTC原值显示，不以浏览器时区重解释；0只来自真实 hit_count，reason_code=null 显示“未提供”。不会生成运行ID、调度时刻或假成功。

## 父组件协议

| prop              | 说明                                                                                                                        |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `ruleId`          | 真实已选规则ID，不提供UUID手填框。空值不发请求。                                                                            |
| `permissionCodes` | 当前原动作列表；仅rules.read或原超级权限可读，不借create/edit/accounts/monitor。                                            |
| `contextKey`      | 真实认证生命周期标识；包括同凭据重新登录。父必须在主体/登录生命周期变化时更新。                                             |
| `filters`         | 父受控其余原查询参数 q/operator_user_id/channel_id/metric_profile_id/entity_type。组件不伪造人员/渠道候选，也不修改此对象。 |

组件本地提供原状态 RUNNING/SUCCEEDED/SKIPPED/UNKNOWN/FAILED、原 date_from/date_to 的YYYY-MM-DD输入和20/50/100/200条分页。日期不默认今天，不猜日期窗口的时区语义。当前后端运行来源尚未接通，原合法请求仍可503；不因此显示空记录或声称筛选已完成业务验收。

“查询记录”时冻结完整已提交 query 并清空cursor栈；未提交的状态/日期输入不会污染下一页游标。清空日期后省略参数，不发送null。下一页只使用原next_cursor；上一页回到已保存的原cursor。页大小、父过滤条件变化回首页。409不偷偷换游标：清除旧页、明确显示错误，用户重新查询时从首页读取。

## 生命周期与失败

- 每次新读取消上次AbortSignal，递增本组件epoch；规则/认证/权限切换立即清除原数据，原响应晚到不得覆盖当前页。
- 从SDK返回后仍核每条rule_id属于本次规则，错对象有效结构也502 INVALID_RESPONSE。无额外写动作或执行授权。
- 关闭RuleList详情会卸载RuleRuns并取消在途请求；组件卸载后不写回页状态。
- 只有真实有效items=[]页显示“当前页无运行记录”。loading、403、503、409、网络错误、字段错误均不变为空页；显示原code/message/path/request_id。没有自动重试或后台轮询。
- 原模拟详情的next_cursor续页接口仍缺，未用运行记录接口替代或伪造实现。

## 当前有限证据

首次定向挂载已完成：`pnpm exec vitest run --config vitest.config.ts tests/orbit/rule-runs.test.ts tests/orbit/rule-list.test.ts` **38/38 PASS**（Runs19 + 原List18及新增接线1），8.01秒。挂载使用真实Element Plus、替身SDK；不是SQL、HTTP、三视口或真实规则运行验收。

覆盖八字段/真实空页、四档参数、next/previous、状态与日期冻结、null清空、父原参数保真、403/503/409、旧cursor重新查询、无权限/空规则不读取、规则与认证切换取消、晚成功/晚失败不覆盖、卸载以及错对象拒绝。原List模拟503与取消/未知写入断言保持通过。

主线容量采样释放后，补关闭详情取消子组件断言，定向再次38/38 PASS（7.60秒）；类型检查、六文件Prettier均PASS，RuleRuns机械检查[]。没有启动服务/DB/浏览器或平台调用。

## 业务闭环名称收口

RuleRuns展示原`GET /rules/{id}/runs`返回的RuleRun8字段，本轮统一标题、aria-label、loading/empty与错误文案为“运行记录”，入口在RuleList同名按钮。原PRD全局`/rule-hits`触发明细仍是独立缺口，不能由本组件替代；未新增来源或将503显示为空。只改可见名称与对应精确断言，原分页、当前认证/取消、日期过滤和8字段协议不变。实际单测日志见`.runtime/rule-runs-business-*`，组件替身不计真实运行来源通过。
