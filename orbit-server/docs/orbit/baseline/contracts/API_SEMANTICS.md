# 本版范围适用说明

本文为原合同详细语义基线。已删除的独立模块流程不再实施，适用边界以01_修订需求与删除边界.md为准；保留页面的字段、AI闭环、预算、状态与双通道规则不因此删除。

# API 服务语义与条件校验

OpenAPI 3.1的所有业务对象additionalProperties=false。JSON结构通过不等于业务合法；按本文件及fields执行服务校验。未知字段400 UNKNOWN_FIELD，结构/类型错误400 INVALID_STRUCTURE，字段边界及条件必填422 FIELD_VALIDATION_FAILED，错误路径用JSON Pointer。版本要求If-Match为带引号十进制revision；缺少返回400 REVISION_REQUIRED，过期409 REVISION_CONFLICT。用户输入全部NFC规范化，短文本trim且拒换行/控制符，正文保留LF；按code point计长度。

## 接口约定

OpenAPI为实际路由清单；PRD第13章只作流程说明，不再实现其中同义旧路由。更新资源采用PUT全量可编辑字段；PATCH仅用于建议编辑。列表分页20/50/100/200，游标绑定筛选、排序、scope及快照；排序null在末尾，ID作为第二键。跨页全选只走scope-snapshots。用户提交所有权时服务器校验其指派权限；一般用户不能靠修改owner获取别人数据。

mutation必须Idempotency-Key和CSRF；回调及mTLS心跳走独立认证，不要求Cookie/CSRF。相同key+同payload返回原HTTP成功码和相同业务ID/结果；同key不同payload409 IDEMPOTENCY_CONFLICT。对已成功但随后版本变化的重放，先匹配原幂等结果再判If-Match，避免正确重试变成版本冲突。没有命中幂等记录才执行业务授权/版本校验；但已撤销用户/权限仍不可读取旧响应数据，先校验会话及当前读范围。

202仅表示已受理。响应中id/task_id/operation_ids用于查询；不能展示“平台执行成功”。业务模型不统一包data，使用OpenAPI指定结构；request_id统一放X-Request-ID响应头，错误体也包含request_id。分页响应有data_as_of和scope_version。所有list的status过滤只接受该领域枚举，未知422；不支持的组合过滤422而不是静默忽略。q仅用于该资源名称/代码，外部ID精确匹配。日期端点包含，读指标1—93业务日，长范围通过导出异步；不得含未来业务日。

查询型POST /metrics/query及reports/query使用冻结查询语义，不创建业务写命令，但仍验证CSRF和幂等键便于query_snapshot复用。GET字典/options返回当前菜单可用的公共配置，不暴露业务总代列表；总代走/business-agents且按产品菜单+数据范围授权。

## 关键服务校验表

|对象/操作|必须额外执行的校验|
|---|---|
|Plan草稿|允许缺业务必填；所有local_id计划内唯一，树层级合法，总配置大小≤5MiB；类型、长度、tenant、引用已有时权限和最大数量始终有效|
|Plan预检/执行|展开所有必填；同投手/团队/租户/币种；campaign目标能力已验证；每预算拥有者恰一预算，AD不得budget；daily/lifetime不能同时；每个adset开始≥发送时刻未来5分钟；lifetime必填end_time且≤366天；特殊广告类别用户确认；未知能力组合不能选|
|投放身份|网站目标要求pixel+conversion_event，app目标要求application+商店HTTPS URL；平台资产逐账户可用；不混用网站像素与app配置；page必填；override必须匹配该计划广告local_id|
|广告及素材|title/body/cta按首期必填；网站URL为HTTPS且无凭据；服务端探测阻止私网/环回/链路本地/元数据地址及重定向绕过；素材兼容锁定能力版本；上传JPEG/PNG≤20MiB、MP4≤500MiB；枚举以能力包白名单交集|
|规则|总条件≤20；计数指标threshold整数，CTR≤100，比率≤1000000，金额≤1000000000；AST仅两层；INTERVAL有15—1440分钟且time/weekday=null；DAILY有time且interval/weekday=null；WEEKLY有time+weekday且interval=null；日期≤366天；scope/profile可用|
|建议/手工预算|BUDGET_SET before/after/owner均必填，amount>0及币种精度；非预算after=null；DELETE要delete_ack=true和delete权限；OBSERVE不能提交；原AI输出不可变；编辑需reason；风险账本见WORKFLOWS|
|申请|RECHARGE恰一account、amount>0且≤1000000、quantity/timezone/product=null；OPEN_ACCOUNT无account且quantity1—1000、product/timezone必填、amount=null；UNBIND/RECOVER至少一account且quantity/timezone/product=null，UNBIND amount=null、RECOVER可选amount；vendor/currency均必填|
|审批履约|只能合法状态，职责分离；所有回执账号属于目标租户/户商及请求范围（下户新增账号需授权核验）；供应商回执hash冲突409；COMPLETE要求数量/金额/币种/账号均吻合；ACCEPT_PARTIAL只在DISCREPANCY|
|主数据|中文表单值转换为OpenAPI大写代码；费率字符串0—100最多2位，空不能转0；regions引用ENABLED地区字典；product_agents至少1；channel.agent属于product；包渠道同产品；停用对象不能新增引用；被引用删除拒绝，历史快照不改|
|导入|输入≤20000codepoint，原始非空token≤500；数字ID≤32位；错误分行但总体上限错误整批拒绝；无权限不泄露已有归属；ALREADY_EXISTS不重新绑定|
|共享拥有者|同团队至少一有效成员，普通创建者只能指派本人；TEAM模板recipient必须同team；模板更新不扩大已存在计划权限|
|报表|query.dataset与路由匹配；channel路由必须CHANNEL，operator路由OPERATOR，launch路由LAUNCH；所有汇总先权限过滤；granularity必填；totals为全范围而非页合计|
|全局角色|角色/团队/权限修改仅具system动作的SUPER_ADMIN；不能自行给自己提权；至少保留一名启用SUPER_ADMIN；审批禁止自审不因SUPER_ADMIN绕过|
|OAuth|一次性state十分钟、绑定会话/发起人/return_to；回调受信issuer/redirect、服务端交换；redirect只能站内；错误重定向不含token；Meta回调仅关联原发起人有权配置的租户|
|Agent|Agent.endpoint仅localhost/127.0.0.1端口；设备证书CN绑定agent_id，heartbeat observed_at仅作证据、在线判断用服务端收到时间；boot_id换代后旧boot心跳拒绝，seq重复忽略|

## 首期状态修改和管理补充

主数据状态由PUT更新，字段状态即归档/停用入口，不提供硬删除；产品无status字段，已使用产品只能编辑合法字段，首期不提供停用按钮。客户TERMINATED不能新投放；渠道DISABLED、户商DISABLED禁止新选择。团队/用户停用立即撤权；既有记录不删除。规则编辑时ENABLED必须先pause，服务端不隐式继续调度旧版本。

GET /tasks包含原型正在执行和历史记录两个视图，由状态过滤派生；GET /tasks/{id}返回首200节点，GET /tasks/{id}/nodes分页。GET /rule-hits展示分析尚未完成/失败，GET /suggestions只返回已经生成建议对象。SSE和任务查询使用同一持久化版本，不以浏览器时间推进状态。

## 错误码补充

|错误码|HTTP|重试语义|
|---|---|---|
|STALE_PREVIEW / REVISION_CONFLICT / IDEMPOTENCY_CONFLICT|409|新预览或修正请求，不能直接重发旧写|
|ALLOCATION_NO_MATCH / PLAN_ACCOUNT_LIMIT / PLAN_NODE_LIMIT|422|修改计划；分配求解未完成为202而不是假失败|
|BUDGET_ROLLING_LIMIT / LIFETIME_BELOW_SPEND / ATTRIBUTION_IMMATURE|422|不执行，重新满足条件后预览|
|TARGET_HAS_UNKNOWN_COMMAND / BUDGET_BASELINE_UNKNOWN|409|先对账，不能自动重发|
|LIFETIME_SPEND_STALE / SNAPSHOT_EXPIRED|409|刷新数据重新预览|
|SELF_APPROVAL_FORBIDDEN / DUTY_CONFLICT|403|换合格人员，不回退权限|
|IMPORT_TOO_MANY_TOKENS / VENDOR_DISABLED|422|用户修正；无后台任务|
|EVENT_CURSOR_EXPIRED|410|GET任务快照后续传|
|UNKNOWN_EVIDENCE / OUTPUT_POLICY_REJECTED|任务错误|模型任务失败或按策略有限重试；不可执行|
|AUTH_REVOKED / DEPENDENCY_FAILED / PLATFORM_RATE_LIMITED|任务错误|分别阻断、等待依赖、按限流重排；保留原命令|

## 评审和合同变更

每项修改先更新decision/PRD语义，再更新Schema和fixtures，生成客户端后跑契约测试。含财务、权限、归属、幂等变更必须升级policy/schema版本；旧任务仍绑定旧快照，但发送前当前安全限制更严格时拒绝执行并提示重新预览，不自动弱化保护。

## 所有权与共享动作的额外防提权规则

所有权调整使用/{resource}/{id}/owners，要求该主数据的assign权限；普通PUT即使包含ownership，也必须与当前值相同，否则409 OWNERSHIP_CHANGE_REQUIRES_ASSIGN。新建记录默认本人；替他人创建须create+assign以及数据范围。模板visibility或recipient集合改变必须templates.share（独立/share入口），不能借templates.edit扩展共享。归档主数据通过/archive设置停用状态，客户为TERMINATED，其余为DISABLED；PUT直接把状态改为停用也必须archive权限。产品无停用状态，不实现产品/archive；菜单不能显示未实现动作。

计划拥有者变更仅草稿可用，需launch.edit且调用者为管理目标团队的TEAM_ADMIN或SUPER_ADMIN；新拥有者须同时拥有全部引用资源，变更使占号/预览/分配失效。普通用户不能指派他人。所有权限校验均在服务端执行。

## 实体读取与长范围导出

手工操作前通过GET /entities/{id}取得内部ID、revision、账户、层级、父级、预算拥有者和配置/有效状态；数据按账户当前所有权过滤。entity_revision仅用于发现本地观察过期，服务端预览仍须重新读平台并冻结实际配置，发送前再复验；不能以本地版本假装平台CAS。列表/监测行的entity_id可用于详情请求，未映射内部实体不得执行手工动作。

ExportRequest.source=SNAPSHOT时query_snapshot_id必填且query=null；source=QUERY时query必填且query_snapshot_id=null。QUERY允许1—730个账户业务日，query.cursor必须null，page_size只控制内部取数页大小，不限制输出总行；只读指标交互接口仍限制93天。服务端受理时冻结授权范围、过滤器及已发布数据快照，后台异步执行长范围查询。历史超出保留或缺失明确标coverage/missing_count，不能补零。两种模式都不接受任意SQL。导出状态通过GET /exports/{id}读取；下载时复验数据和菜单权限。角色撤权直接REVOKED，不返回旧文件。
