# TaskEvent存量防线：独立模块与先失败后接线验收

主线先运行未接防线的真实基线：20通过、1失败、6未运行，存量schema_version=2确实被错误放行；回执`python-task-event-integrity-baseline-attempt-01.json`保留。随后在store读取整批后接入task_event_validation，原合同、033/036及写方保持。新增7组与原14组、Cookie5组、Boundary7组联合真实39/39、17.41秒通过（`python-task-event-complete-http.json`）；独立新增档27/27通过。

## 严格原合同

原OpenAPI TaskEvent固定9字段：event_id、sequence、schema_version、task_id、task_revision、node_id、state、occurred_at、request_id。schema_version是整数1；sequence/task_revision为正安全整数；UUID/null与UTC时间照原合同。state原Schema是UTF8 string、1..40码点，**不是Task/TaskNode枚举**。FUTURE_STATE、PAUSED、40个汉字、40个emoji在纯测中明确接受，不按node_id增加未定义语义。

新模块整批验证：当前已授权Task的tenant/id与正安全header版本/序号；事件字段存在、类型和边界；事件tenant/task必须匹配该可信Task，event revision/sequence不得高于header；时间为数据库UTC DATETIME(3)或明确UTC aware毫秒时间。未知来源格式、损坏行统一503 TASK_EVENT_STATE_UNAVAILABLE，不返回原值、SQL或异常正文。公共投影仍由原public_event严格选9字段，新增模块不扩DTO。

目录按整批event_id一次IN集合查询，最多200；校tenant/task/event_id/sequence/occurred_at精确一致，expires_at必须真实occurred_at+7天。整批先结构检查，后一次目录检查，再允许返回任何行；空批不额外查目录，201行先503而非发送或N+1。没有全Task扫描或新授权缓存。

查询边界外坏sequence（如0或大于header.latest_sequence）不会出现在原SELECT中，既有连续性逻辑以503 TASK_EVENT_SEQUENCE_UNAVAILABLE失败关闭。主线已明确保留此精确码和旧14负例，不为定位任意孤立坏行扫描全Task，也不把它伪装为已返回行的字段错误。纯测仍严格验证所有返回行的0/max/bool边界。

## 主线最小接线补丁

主线完成当前32检查点后，先**不接validator**运行新工具，保存实际baseline FAIL及精确恢复证据。随后仅在task_event_store.py导入`validate_persisted_batch`，在batch取得events后、原连续性检查及return前插入：

```python
await validate_persisted_batch(session, row, events)
```

原start已经调用首batch，故首批错误可在HTTP200之前503；后续每批同样整批先校。不能只在public_event编码单行时检查，否则可能已发送本批前一行或已开200。原事件/迁移/生产publisher不因此放开；没有任意写HTTP，不增加菜单或MAC用途。

## 新工具7组

入口`run_task_event_integrity_checks(client,admin,headers,database,cases)`，导出`TASK_EVENT_INTEGRITY_CASES`7项。严格13306当前UUID库，自建真实非空Task/PLAN版本，使用root现有权限；不创建额外用户/角色、不借外部凭据、不发平台请求。

1. 合法未来state字符串仍可200并按原TaskEvent输出，防止为修损坏行而错误收紧原Schema。
2. 存量schema_version=2，首次SSE必须HTTP200前精确503 STATE_UNAVAILABLE；这是未接防线时的预期首个实际失败，不用模拟失败回执。
3. task_revision=0/高于header/超过安全整数、sequence=0/超header/超安全整数、event_id/request_id非UUID。可返回坏字段精确STATE码；被原SQL排除的坏seq精确原SEQUENCE码。
4. 空state被拒；不拿合法未来字符串当错误，不为注入41码点去改VARCHAR(40)。超长/无效UTF8由纯测和数据库自身约束覆盖，未称真实库已接受这些非法值。
5. 目录event_id/sequence/occurred_at/expires_at分离，每次503并逐字段恢复，不改变033/036已受测迁移。
6. 两行批次第二行损坏，第一行合法，整批HTTP200前拒绝；不允许先输出第一帧再报错。
7. 在途流先真实心跳；另一事务受控publisher生成event2并在同事务注入version2后提交，避免合法event2先可见的竞态。首流有界关闭且不发业务/伪控制帧，下次同原cursor精确503；最后恢复event2并核对完整真实行快照。

所有注入只改独占一行，用另一未改唯一键定位finally恢复，全字段读取比较确保恢复原状。状态断言失败也必须恢复；错误诊断仅numeric actual/expected，不打印损坏原值。并发publisher在此只是ISOLATED_TEST事务协议，不是实际平台执行来源。

## 当前证据与未完成

47项专属纯测通过，Ruff/格式/编译通过。当前防线接线后的三视口真实浏览器6/6通过，整档24/24、109.24秒（`python-task-event-current-integrity-browser.json`），包含真实事件提交、详情刷新、撤权停流及权限恢复复核。真实UTC不同时区、额外历史数据迁移修复、生产来源完整状态机、自然OS慢TCP与observer大容量仍依各自证据，不能从本7组推导全部完成。
