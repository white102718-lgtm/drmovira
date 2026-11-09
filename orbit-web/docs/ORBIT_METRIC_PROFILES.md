# 指标配置只读目录交付边界

本批仅新增独立SDK、目录组件和专属纯测，不注册路由/菜单、不修改投放父页面、不新增指标发布或执行入口。原合同来源为 `contracts/openapi-current.json` 的 `MetricProfile`、`MetricProfilePage`、`GET /api/v1/metric-profiles`。

## 原字段与页面

组件 `src/views/orbit/monitor/MetricProfiles.vue` 直接使用当前若依会话的 `monitor.read` 或通配权限，不借 `launch.read`。默认可作为独立子页面；若父监测页按tab挂载，可传 `active` 和不含凭据的 `contextKey` 登录/权限代次。身份、角色、权限或context变化清空已读目录/详情并从当前上下文重读；隐藏或卸载取消当前GET。没有轮询或自动重试。

列表展示真实id、version、source、verified、maturity_days，查看详情展示原12字段：

- `id`：完整UUID；不猜名称。
- `version`：原字符串版本，不转整数。
- `source`：META/FIXTURE；FIXTURE明确标测试配置。
- `register_action_type`、`purchase_action_type`、`value_action_type`：null显示未知且未映射，不填默认事件。
- `attribution_windows`：完整1至10项数组，不截断或从文本猜执行参数。
- `action_report_time`：原字符串。
- `timezone_policy`：ACCOUNT_LOCAL，账户当地时区。
- `breakdown`：TOTAL。
- `maturity_days`：1至90整数，账户当地日。
- `verified`：原boolean声明；目录和声明均不构成当前广告执行许可。

不增加Ownership、状态、发布时间或发布者投手字段；不提供创建/编辑/执行按钮。META来源也明确不代替当前账户、能力、政策及执行授权核验。

## 请求与分页

SDK `src/api/orbit/metric-profiles.ts` 只调用真实GET `/api/v1/metric-profiles`，复用 `orbitAuthHeaders`/`orbitCredentials` 内存认证，no-store；没有凭据URL、写操作或幂等键生成。

本批按主线明确的最小查询语义，仅发送：

| 参数              | 行为                                                   |
| ----------------- | ------------------------------------------------------ |
| q                 | 空代表全部；非空完整UUID，精确指标ID搜索，大小写归一化 |
| metric_profile_id | null不发送；非空完整UUID精确匹配，与q求交集            |
| cursor            | 不透明原游标，不解MAC、不构造offset                    |
| page_size         | 20/50/100/200，默认50                                  |

原通用status/date/operator/channel/entity_type业务语义未定义，不显示伪筛选，不吞参数。SDK运行时也拒绝额外参数。输入ID改变立即取消旧请求并清旧页，显式查询后读取；页大小改变回首。上一页保存真实游标历史；字节预算短页仍按服务端next_cursor提供下一页，不按items.length猜末页。成功页展示真实data_as_of/scope_version。

响应只接受原200与严格4字段Page，配置严格12字段，数组上限/nullable/boolean/枚举/安全整数/日期格式均校验。非200不伪装成功。原错误体的field_errors、nullable constraint、retryable及request_id保留。

403/401清旧配置和详情，409清旧游标并提供首页恢复，503明确服务/权威来源未就绪；只有实际成功的空数组才显示“当前筛选没有指标配置”。网络失败只提供显式重试，重试保留原查询和游标；换条件后不再恢复旧意图。Abort及epoch保护使迟到结果不能覆盖新筛选或新身份。

## 验证与待接入

专属命令：

`pnpm exec vitest run --config vitest.config.ts tests/orbit/metric-profiles.test.ts tests/orbit/metric-profiles-page.test.ts`

首轮实际61/61 PASS：SDK44、真实ElementPlus挂载17，耗时4.89秒。SDK测试采用transport替身，组件采用API替身；这些结果不是真实SQL/HTTP/平台验收。

主线后续统一接菜单/路由和真实目录API，执行三视口：当前monitor.read正反、META/FIXTURE/nullable与全12字段、四档前后页/短页游标、q与id交集、403/409/503、上下文失效和响应式详情。不得因本批组件能挂载而将完整监测模块或指标权威来源标完成。

## 独立真实浏览器用例（已准备，尚未执行）

专属 `tests/e2e/orbit-python-metric-profiles.spec.ts` 包含3个独立测试，每个原60秒、零重试，交主线按三个视口运行，共9项：

1. `Python指标配置21条四档分页历史及十二字段详情真实闭环`：实际21条首50；切20后20+1、上一页原集合；50/100/200回首；详情12字段、null、窗口数组、boolean及FIXTURE边界说明，水平响应式。
2. `Python指标配置UUID双筛选交集无结果及游标重置真实闭环`：使用真实GET中的完整UUID；q大小写规范化、profile_id单筛、相同ID交集、不同ID空集；清空条件恢复原20+1，旧页游标不复用。
3. `Python指标配置真实刷新重进及空搜索恢复`：同一有效登录实际刷新、离开目录后重新进入；重新取得真实getInfo与列表；空结果后清空搜索恢复21项，重新查看实际详情。

前置由主线单独seed21条严格FIXTURE SQL样本：version为observed-v001至observed-v021；register/value action type为null，purchase action type与窗口来自样本，verified可为true但页面仍不得解释为Meta生产验证。独立浏览器档应仅seed该21条，不能先跑会增加其他registry记录的checker后仍断言总数21。样本不是Meta权威来源或受控发布验收。

只使用既有 `ORBIT_E2E_FIXTURE_PASSWORD` 的主线隔离登录上下文，每测试登录一次；没有新登录限流豁免。读取等待仅剥离已知`/dev-api/`前缀一次后严格匹配完整GET路径与实际查询参数。选择页大小点击真实可见ElementPlus wrapper，不强制点击隐藏input。每次整页重载按真实getInfo密码提示分支取消原安全提示，不修改安全配置或密码状态。诊断复用安全网络工具，不采集Token、请求体或完整trace。

403/409没有安全服务端驱动前不模拟，第三测试也不冒称撤权/目录变更已验证；这些错误目前只有61项纯测中的边界证据。路由/菜单/真实API、runner与C样本发布均由主线统一安排。本批只完成TS类型和格式静态检查，尚无9项真实浏览器PASS证据。
