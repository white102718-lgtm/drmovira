# 投放预检与执行SDK检查点

本检查点仅新增 `src/api/orbit/launch-validation.ts` 和专属transport替身测试。没有页面引用，没有新增后端路由，没有执行任何真实广告，也不能据此宣称预检、分配或提交已具备生产能力。原Task、投放页面及 `launch.ts` 不修改。

## 原接口与调用边界

| SDK函数      | 原接口                                                      | 权限           | 成功状态/正文                                       |
| ------------ | ----------------------------------------------------------- | -------------- | --------------------------------------------------- |
| reserveNames | POST `/api/v1/launch-plans/{id}/campaign-names`             | launch.edit    | 200 NameReservation；请求无正文，不能传空对象       |
| allocate     | POST `/api/v1/launch-plans/{id}/allocations`                | launch.edit    | 202 Allocation；仅表示受理，task_id可以null         |
| allocation   | GET `/api/v1/launch-plans/{id}/allocations/{allocation_id}` | launch.read    | 200 Allocation；只读取真实分配结果                  |
| validate     | POST `/api/v1/launch-plans/{id}/validate`                   | launch.edit    | 200 PlanValidation；valid=false也是须展示的业务结果 |
| execute      | POST `/api/v1/launch-plans/{id}/execute`                    | launch.execute | 202原Task；不接受Allocation/runtime UUID代替        |

启用还需要独立的 `launch.publish` 和二次确认，服务端仍须验证当前菜单、动作、双方资源范围与完整权威来源。SDK不因存在某个函数而赋予权限，也不实现生产provider。冻结素材安全证明、平台身份、能力与命令服务未就绪时，界面不能调用SDK伪装受理成功。

四个mutation均由调用方显式提供 `FrozenMutation`：`csrf_token`、`idempotency_key`、`if_match`。If-Match必须是已取得的带双引号安全正整数版本，SDK不会替调用方加一或用配置source_revision猜测状态head_revision。幂等键16—128可打印ASCII字符、CSRF为可安全放入HTTP header的16—255字符。UUID允许大小写的规范连字符形式，不接受裸32位、花括号或数值。不会改写调用方的正文或键。

复用 `orbitAuthHeaders` 和 `orbitCredentials`，认证仅在内存header/Cookie中，不放URL。若当前Cookie会话使原函数替换了冻结CSRF，SDK在请求前拒绝 `CSRF_CONTEXT_CHANGED`，要求确认原意图后重新取得上下文；不能偷偷换token。名称预留正文为空；预检仅两个UUID；执行仅小写64位十六进制hash和boolean activate_ack；分配仅原asset_ids、allow_repeat、seed、algorithm_version四字段。

## 响应解析

所有对象拒绝未知或缺失字段；整数拒绝不安全值。PlanValidation十字段全部保留：valid、hash、expires_at、errors、campaign_count、adset_count、ad_count、budget_totals、scope_version、total_dag_node_count。SDK不根据数量生成hash，不额外伪造服务端预检通过条件。

PlanValidation.errors最多1000条，每条原FieldError含path/code/message/constraint，成功正文constraint必须string；通用HTTP Error的既有nullable constraint兼容由独立 `PlanHttpFieldError` 处理，不放宽成功业务Schema。HTTP Error保留code、message、field_errors（最多100）、retryable、request_id及HTTP状态；正文错误不吞成空成功。

Money始终是amount原十进制字符串及三位大写currency。金额最多28字符、至多6位小数，不转Number，不接受指数、负数、前导零或千分位，不跨币种合计。budget_totals最多100项；三层计数及总DAG计数是0—2147483647整数，scope_version是安全正整数。

NameReservation保留id、配置plan_revision、真实naming_date和1—10000条items；sequence为最长30位数字字符串，保留前导零及超安全整数值。Allocation保留全部10字段，items最多10000、warnings最多100，每项素材版本为安全正整数，seed为0—2147483647；POST/GET结果须匹配当前plan_id，GET还核对allocation_id。QUEUED/RUNNING不能冒充SUCCEEDED；task_id=null不会被补成runtime UUID。

## 失败与后续页面接线

每次调用只发送一次请求，不自动重试。15秒客户端等待结束、已发送后取消、网络中断或成功HTTP正文/状态不符合合同均不可宣告写入成功；`unknown_result`标记不确定写结果，调用方须保留原正文、幂等键与CAS，显式重试同一意图。取消客户端等待不等于取消服务端任务。已取消且尚未发送则不发HTTP。禁止因超时切换执行通道或生成新键补发。

预检返回后，由未来调用方用原GET Plan重读当前head，不能从PlanValidation猜head+1，也不添加ETag合同。服务端hash绑定配置source、分配、命名、资源/能力/policy/scope及启用意图；15分钟有效期和上海跨日失效必须由服务端最终复验。页面还需错误JSON Pointer定位、冻结展开预览、按币种预算和提交确认，本SDK没有把这些缺失页面标记完成。execute合法202仅接既有真实Task查询，不显示平台创建/投放成功。

测试仅证明请求合同、严格解析和transport错误处理；不属于真实MySQL、预检provider、浏览器或平台验收证据。

## 父页面、逐账户身份与定位（2026-11-08）

计划列表新增投放预检入口，以服务端validation_available及当前编辑权限控制；当前正式权威Provider缺失时禁用，显示真实依赖。进入前重读计划和能力，成功预检后重新GET真实CAS头，未知写入保留原body/幂等键/If-Match，关闭、路由、切页及刷新均有保护。HTML网关502或畸形400无法确认是否受理时也保持原意图，GET读取错误不冒充写入未知。

逐账户主页、组身份、广告主页覆盖按当前账户/树分页编辑，未应用取消不改变原绑定，已应用进入原草稿恢复。accounts.read按当前权限独立控制，仅按需读取一个账户的真实身份观察；观察不是写授权，非空身份保存仍有后端依赖。孤立账户/组/广告绑定保留，删除须明确确认。

同一服务器revision的已知JSONPointer可定位实际树local_id、预算二级页及具体账户身份字段；陈旧版本或未知路径显示原路径，不假定位。原execute只接受实际202 Task并交既有TaskDetails，当前执行入口未因组件完成而开启。

统一纯测478/478、类型、生产构建、格式通过；原计划/模板真实三视口3/3、整档7/7、54.54秒通过，补充实际默认预检禁用与零相关写请求断言。该浏览器回执没有预检成功/Meta来源/完整execute验收；三预检弹窗成功与异常路径当前由组件测试覆盖。证据在后端docs/orbit/evidence/frontend-launch-validation-identity-checkpoint.json与python-launch-validation-identity-browser.json。
