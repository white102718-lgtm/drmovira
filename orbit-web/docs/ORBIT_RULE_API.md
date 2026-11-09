# 原规则API客户端

`src/api/orbit/rules.ts`独立接Python原九接口及专属capabilities，不包含页面、菜单、调度、AI或模拟来源。后端定义专项已由主线真实22/22通过（13.83秒），证据在server的`docs/orbit/evidence/python-rules060-definition-http.json`；该结果不是本客户端联调或整个Rule验收。

| 方法         | HTTP                                    | 正常状态/正文                  |
| ------------ | --------------------------------------- | ------------------------------ |
| list         | GET /api/v1/rules                       | 200 RulePage                   |
| create       | POST /api/v1/rules                      | 201 Rule                       |
| get          | GET /api/v1/rules/{id}                  | 200 Rule                       |
| update       | PUT /api/v1/rules/{id}                  | 200 Rule                       |
| archive      | POST /api/v1/rules/{id}/archive         | 200 Rule；原Reason             |
| simulate     | POST /api/v1/rules/{id}/simulate        | 原200 Simulation；严格不发正文 |
| enable       | POST /api/v1/rules/{id}/enable          | 原200 Rule；仅simulation_id    |
| pause        | POST /api/v1/rules/{id}/pause           | 原200 Rule；原Reason           |
| runs         | GET /api/v1/rules/{id}/runs             | 原200 RuleRunPage              |
| capabilities | GET /api/v1/rules/capabilities?action=… | 200，仅csrf_token              |

capabilities六动作固定为CREATE、UPDATE、ENABLE、PAUSE、ARCHIVE、SIMULATE，最后一个沿rules.read；不借accounts/monitor/launch授权。后端simulate、enable、runs仍缺真实来源，当前503必须原样呈现，不能转空数组或已启用。

## 字段与边界

- RuleWrite完整11键，Rule完整15键；RuleSimulation13、ConditionResult5、RuleRun8、列表页4键严格核对。未知或缺失字段失败；不兼容若依`{code:200,data:…}`包裹成功。
- 条件为Rule逻辑→1至5组→每组1至10叶，合计最多20叶，不接受更深递归。阈值和观察值保持Decimal文本/原null，大于JS精度的计数不转number。阈值只用临时BigInt定点比较计数整数及CTR/ROAS/金额上限，返回及请求仍为原字符串；UNKNOWN不补0。
- Schedule七键始终必需，互斥字段显式null；日期含首尾最多366天，按真实日历核验。INTERVAL15—1440分钟，DAILY/WEEKLY原HH:mm、weekday分支；IANA合法性依当前浏览器Intl支持检查，后端ZoneInfo和调度仍为权威。SDK不自行计算DST槽位或next_run_at。
- 名称先拒控制/非法Unicode，再NFC+trim并按码点核80上限；Reason上限1000，不能套配置表单500。UUID保持字符串；安全版本整数不转换浮点文本；原UTC响应保持原字符串。
- list/runs均保留原十查询字段：q/cursor/page_size/status/date_from/date_to/operator_user_id/channel_id/metric_profile_id/entity_type。q先NFC且不修改调用方原对象，允许空串、最多100码点；字面contains及case/accent语义由后端决定，客户端不改前缀查询。页大小20/50/100/200，游标只传原opaque值。
- 后端list对非空date/channel语义尚未实现，明确422；runs合法原参数当前仍503，客户端不会悄悄丢参数来换取成功。模拟续页原有next_cursor但尚无获批续页入口，SDK不发明接口或在原simulate添加正文。

## 单次意图与会话

写入调用者提供`{csrf_token,idempotency_key}`；更新/动作另传原带引号`if_match`字符串。SDK不生成新key、不自动重试、不把请求体写入URL/Storage。发出时立即序列化已验证完整正文，调用方随后修改表单不会改该次请求。网络、超时、错误成功体或会话变化导致写结果无法确认时`RuleApiError.unknown_result=true`，调用方必须保留原body/key/CAS进行恢复，不宣称已取消。

沿原`orbitAuthHeaders`/`orbitCredentials`切换Cookie或Bearer，会话CSRF替换后不匹配冻结CSRF则发出前409。每次响应比较发出前后的认证头/credentials快照，变化时丢弃迟到结果。公共authentication私有epoch没有读取接口，本SDK不冒称订阅了它；未来页面仍须用自己的请求代次和AbortController防关闭/切换/相同凭据ABA的旧响应覆盖。SDK不改变公共认证状态。

单次fetch有15秒有界超时，并尊重调用方AbortSignal；已取消读取不发出，已发出的写取消不等于服务端未受理。沿ReferenceApiError基类和原HTTP FieldError解析保留服务端code/field_errors/retryable/request_id；已有通用错误constraint=null兼容单独保留，不放宽成功Rule/Simulation DTO。无效HTML/包裹响应仅显示安全本地错误。

## 验证范围

独占`tests/orbit/rules-api.test.ts`首版30/30纯测通过；随后补q分解组合100/101边界与原对象不变，实际31/31通过（1.21秒；测试函数内69毫秒）。fetch/认证为替身，包括原字段数量、Decimal与null、366日期/互斥键、20叶、Unicode、10000模拟明细、全部原请求形状、精确201、原错误503、未知写、会话变化、Cookie CSRF、超时不重发及Storage零写。类型和格式检查另由本次命令确认。

这不是页面/真实Cookie退出/真实HTTP/真实模拟、50k规则范围容量或整模块验收。旧Java证据不继承；实际ENABLED暂停、Simulation同版本15分钟、RuleRun持久调度和生产事实来源仍需后续真实闭环。
