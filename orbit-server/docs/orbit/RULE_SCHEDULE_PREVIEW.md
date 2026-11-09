# 规则未来五次运行预览

当前新独立接口/工具待主线真实队列，专属36纯测与definition导航工具8纯测合跑44/44 PASS1.20s，Ruff/format通过；不是正式调度器、模拟或启用资格。没有迁移、不写Rule/版本/clock、不改原Schedule核心/原七字段合同。

POST `/api/v1/rules/editor-schedule-preview`，router为`orbit_api.rule_schedule_preview_routes.router`，主线须静态路由先于原`/{rule_id}`注册。构造`RuleSchedulePreviewStore(DirectoryTokens(credential_cipher()))`，无需新state/MAC目的。单外层事务。

严格四键正文：`{action:CREATE|UPDATE,rule_id:null|UUID,rule_revision:null|安全整数,schedule:原Schedule七键}`。CREATE两字段null；UPDATE要求当前可见Rule及精确当前revision。正文revision是本技术端点唯一CAS，拒If-Match和Idempotency-Key，无query/指定tenant，重复JSON键/多余字段拒绝。单个当前X-CSRF-Token使用既有DIRECTORY_CSRF_V1，按真实会话/actor/tenant绑定；不能用另一个会话的有效token。16KiB仅内部请求内存预算。

严格四键响应：

```
{reference_at: SQL实际UTC6+Z,
 timezone: schedule.timezone,
 slots: [{local_time: 带offset RFC3339, utc_time: UTC6+Z}],
 skipped_local_times:[{local_time: 不存在的无offset当地墙钟,
                       reason_code:DST_NONEXISTENT_LOCAL_TIME}]}
```

slots最多5，三列分别显示local_time/顶层timezone/utc_time；不将服务器本地时区或浏览器Host猜成调度时区。DST缺失墙钟没有对应UTC，明确跳过；重叠沿原preview_schedule选择较早UTC且仅一次。end_date已过或合法范围不足5时返回真实0..5，不能伪造未来运行。skipped最多原366日范围，非无限扫描。

授权：CREATE只rules.create；UPDATE只rules.edit+原Rule当前可见与body CAS，不借rules.read/monitor/accounts/users动作，不核profile READY/完整scope成员以免阻止修正定义。非DRAFT状态仍只是计算指定候选schedule，不授予该状态下保存资格。末段同事务授权指纹复核。错误CSRF403早于业务clock；foreign对象404；旧版本409；缺version、已存在Rule却缺clock或坏clock/存储定义503 RULE_SCHEDULE_PREVIEW_UNAVAILABLE。

时间/锁：原授权SHARE→rule clock SHARE取UTC_TIMESTAMP(6)→UPDATE head/version SHARE（当前锁读，原serializer核定义）→纯preview_schedule(limit5)→末授权。CREATE新tenant尚无ruleclock时只另SELECT UTC_TIMESTAMP(6)，不创建水位、不填revision0；UPDATE先可见性，再区分缺clock损坏，不能让原不存在对象变成误导503。

源码`rule_schedule_preview.py`/`rule_schedule_preview_routes.py`；原schema/核心无改动。取消异常原样传播，外层事务管理清理；本轮纯取消测试不冒充MySQL锁等待取消已实测。

## 真实工具计划

`RULE_SCHEDULE_PREVIEW_CASES`七组；`run_rule_schedule_preview_checks(client,admin,headers,password,cache,database,cases)`无kwargs。仅本轮127.0.0.1:13306/UUID+SELECTDATABASE。需through061+正常rules fixtureprofile。工具原生ID990616/990617，独立SQL技术tenant/team/业务身份/真实native menu动作/真实POST login会话；不伪造header或维护issuer。新tenant不插入规则clock；原已有tenant原API创建一份Rule作为UPDATE基础。

1. 新独立tenant create-only首次预览，SQL前后UTC6夹取、实际5次15分钟、clock始终不存在，原八表值不变。
2. edit当前CAS、独立create撤回仍可edit、无read权限403、失效profile不挡时间计算；原规则API创建fixture不计预览零写。
3. SQL当前时间之后的实际NewYork DST gap/fold与过去范围0次，全部同一真实HTTP核心计算，不设置MySQL时钟。
4. 错误/跨会话/缺失/重复CSRF403。
5. 四键/重复JSON/query/body超限/指定tenant/双CAS头拒绝。
6. 同Token edit撤回403、恢复后正常；新tenant授原edit动作后请求真实另一tenant已存Rule404。
7. 正常create/update后原八张规则表所有原列、原行值逐项不变（含clock、version、audit、outbox），工具自身fixture初始化在baseline之前。

实际MySQL等待期间取消/服务端P_S与trx退出尚未测试，本轮仅纯CancelledError/零DML。真实启动调度、slot持久去重、启用/运行记录和触发/分析仍独立待办。

## 已执行专项

正式062导航下整档62/62真实MySQL/Redis/HTTP通过，包含七组时间预览、新独立租户首次无clock及真实跨租户对象404；证据`evidence/python-rules062-schedule-preview-http.json`。新导航初次因后端仍要求旧父权限而403，两个失败回执保留，修正目录授权注册后完整复跑，不恢复隐含read动作。

主线内置浏览器实际完成局部接线与原生预览弹窗三个视口（1440/1920/390）、五次结果/过期零次、手机表格内部横滚及关闭焦点；另真实保存、521范围冻结与成员翻页。证据`evidence/python-rules062-browser-partial.json`及截图。并非所有视口重复全流程、UI DST/网络故障/撤权或全模块验收，不以HTTP专项代替这些缺口。
