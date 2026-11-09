# Task只读界面合同核对与Error小闭环

## 范围与证据口径

本轮仅补原Task读取错误五字段及中文只读详情。原Task列表、详情、节点分页、Task-only入口与SSE仍沿用既有实现。新单元测试使用HTTP/observer替身和真实Element Plus组件挂载，不替代真实API、三视口或平台验收；本轮尚未执行数据库与浏览器。上个指标选择器检查点为前端`5fb2196`，与本轮Task错误改动证据分别记录。

原合同依据：`data/ORBIT_Codex开发PRD/contracts/openapi-current.json`的`Error`、`FieldError`、`Task`、`TaskNode`、`TaskEvent`与`/api/v1/tasks`各路径；`WORKFLOWS.md`的UNKNOWN核验、Task分页与SSE约束。当前Python仅有Task列表/详情/节点和SSE读取，没有cancel/retry/resume/reconcile写路由。

## 确认的缺口与此次修正

原HTTP Error严格只有五字段：`code`（1—64码点）、`message`（1—1000）、`field_errors`（0—100条）、`retryable`（布尔）、`request_id`（UUID）。每条FieldError严格只有`path`（1—255）、`code`（1—64）、`message`（1—1000）、`constraint`（0—500字符串，不能null）。之前Task GET错误只取code/message，SSE错误也丢失原请求编号与字段详情。

`src/api/orbit/tasks.ts`现在导出严格解析器与`taskHttpError`，拒绝额外/缺失/类型及长度不符的字段。`TaskApiError`仍兼容原三参数构造，新增`source`明确server/local。本地网络、超时、坏body错误的`request_id=null`仅是本地对象状态，绝非放宽原服务端Error合同。坏body不显示任意原message、HTML或响应正文，保留实际HTTP状态，以保证401/403/404仍清除旧数据。

`src/api/orbit/task-events.ts`复用同一解析，保留握手与快照读取的原五字段。HTTP错误读取限制为2MiB，覆盖原100条最大FieldError的最坏JSON转义；SSE帧原有大小与增量解析限制不变。授权失败即使body格式错误也终止，不转为重连继续持有旧权限。

`TaskReadError.vue`安全文本显示错误说明、代码、请求编号、读取重试标记及全部字段路径/代码/说明/约束；字段详情使用可展开列表，无HTML执行、Storage写入或新操作按钮。`retryable`明确仅解释读取请求，不成为UNKNOWN广告重发许可。

`TaskPanel.vue`、`TaskDetails.vue`保存结构化错误。`index.vue`复用既有不含Token的真实actor/权限/会话代次context，传递到两层Task组件。上下文变化会中断GET/SSE、清空旧任务与错误，原epoch防止旧请求和事件晚到覆盖新身份。详情已有403/404清空、409游标恢复、关闭/隐藏取消观察与Task-only逻辑保留。

## 原页面覆盖与仍未接入的能力

Task原10必需字段及可选execution_mode、TaskNode原13必需字段及可选execution_mode/no_op已有只读展示；父ID完整保留，跨页父ID不会被裁断。后端未提供可选no_op时显示未提供，不猜false。配置核验、任务处理与投放状态分别显示，SUCCEEDED不推断为正在投放。

列表nodes为空是原稀疏投影，node_count来自服务端。详情首200与其后20/50/100/200节点分页不从当前页猜整体完成率。原不支持的日期/channel/entity/metric筛选不制造UI查询；节点q仅node_key前缀。

TaskEvent九字段已严格解析、用于合并触发真实GET，但本轮不新增事件记录视图。未来可设计当前订阅的有界观察记录，不能冒充完整历史日志。原Task/TaskNode没有operation_id、每次尝试证据引用、全局状态计数或对账case字段，不能拿task/node UUID推定operation_id，不能从前200节点推定全局进度。

cancel/retry/resume/reconcile弹窗和按钮依赖真正的后端动作、权限、CAS/幂等/审计与核验流程。当前不新增这些入口。UNKNOWN仍不是FAILED_RETRYABLE，读取错误retryable=true也不改变任务或节点状态。SSE异常恢复仍使用原checkpoint/410快照与有界读取，不宣称平台执行成功。

## 本轮定向验证计划

`task-read-errors.test.ts`：原五字段/四字段严格正反边界、最大Unicode与100条错误、GET/SSE原错误保留、坏JSON授权终止与本地无虚构编号。

`task-read-error-view.test.ts`：中文字段完整、安全HTML文本、无操作按钮、本地提示、同tasks.read的actor切换及旧GET拒绝晚到。

`task-events-components.test.ts`新增两项：同权限actor切换时旧observer/GET不污染新Task；真实结构化SSE撤权错误透传与旧数据清空。原列表、全部节点分页、UNKNOWN、关闭停止读取与SSE合并断流恢复测试保留。

真实Task三视口和受控HTTP坏body验收由主线串行安排。本文件不据纯测试将整个Task模块或原写操作标为完成。

当前定向结果：7个测试文件143/143通过，17.00秒；`pnpm check:orbit`通过，列明改动文件Prettier检查与`git diff --check`通过。首轮134项中133通过，新增未attach的组件测试点击submit未触发表单默认行为，改为原form submit事件并断言实际请求次数后复验通过；未改生产行为、未削弱原断言。原SDK/observer测试的旧简化错误夹具补齐必需的五字段，保留原状态码与恢复断言。
