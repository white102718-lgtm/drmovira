# 广告投放数据查询页面：当前内部交付边界

本批在原monitor模块下补齐查询SDK和原生Element Plus查询页面，不新增一级菜单或平行演示入口，不修改既有指标配置目录。已接Python原monitor子路由/orbit/monitor/data和专属查询上下文；公开技术来源及三视口实际通过，真实生产指标来源仍待实现；当前文件存在、纯测或类型通过均不等于业务验收。

## 原合同与页面对应

依据server的`docs/orbit/baseline/contracts/openapi-current.json`、`WORKFLOWS.md:49/123`、`PRD-ORBIT.md:353`和`reference/03_原合同保留章节.md:7/60`。

页面七Tab原顺序为监测与规则优化、投放师、渠道、广告账户、广告系列、广告组、广告。监测与规则优化明确说明规则命中、依据、记录、采纳等服务未接入，不绘制模拟风险金额或AI卡。投放师/渠道保留原数据维度和查询字段，映射服务缺失时必须真实失败；首四实体维度使用ACCOUNT/CAMPAIGN/ADSET/AD。ASSET/LAUNCH原枚举保留在严格SDK中，其入口属于原素材/投放模块，不新添monitor主Tab。

原POST `/api/v1/metrics/query`只接受完整13字段：

| 字段                | 当前页面行为                                                   |
| ------------------- | -------------------------------------------------------------- |
| date_from / date_to | 真实ISO日期，首尾均包含、1至93日；不以浏览器时区假判断未来日期 |
| dataset             | 与原Tab绑定，SDK保留原八枚举                                   |
| metric_profile_id   | 从真实目录候选选择版本/来源，发送该项真实UUID，不要求手填ID    |
| scope_snapshot_id   | 当前显示全部当前可见账户并发送null，不凭空创造快照UUID         |
| channel_id          | 可选1至64码点原ID，空值null                                    |
| operator_user_id    | 可选真实投放师UUID，空值null                                   |
| q                   | 名称包含匹配或完整平台ID，最多100码点；不拿它伪造账户/父树过滤 |
| sort / direction    | 原七排序字段及ASC/DESC                                         |
| cursor              | 父页面保存原签名游标；不解码或捏造                             |
| page_size           | 20/50/100/200；改条件重新从首页查询                            |
| granularity         | SUMMARY实体汇总或DAY账户当地同名业务日                         |

指标配置复用原GET `/api/v1/metric-profiles`严格SDK，以50项分页读取、签名游标上一页/更多配置。版本文本仅筛当前已加载页，只有完整UUID才使用原q精确远程查询，不能把版本关键字发成新q语义。选项显示真实version/source/verified状态，FIXTURE显著标测试样本；当前页加至多一个已选项，不无界拉全目录。目录403明确错误并清选中引用，409提示重新读取，context变化abort旧读取和清候选。投放师UUID及渠道ID仍为原过滤字段，不借用户目录或其他菜单强加读取权限。产品、父实体及真正账户下钻未出现在本13字段合同中，不能擅发未知参数或把名称q当作等价下钻，仍属待补业务缺口。

成功响应严格八字段全部可见：items、next_cursor（以真实下一页按钮体现）、scope_version、snapshot_id、data_as_of、missing_count、query_snapshot_id、totals。表格展示全部12个MetricValues，行的原15字段可在只读实体详情完整读取。原币种汇总保留服务端8字段，包含全范围account_count/ad_count/missing_count/coverage及12值；绝不在前端累加当前页或混合币种。长金额/比率全程字符串，不经Number、toFixed或浏览器重算；null显示未知，来源未就绪不显示空成功。

## 权限、写入意图与恢复

页面仅根据真实monitor.read或既有超级通配权限开放；身份、角色、权限及contextKey变化会abort旧网络并清旧数据、错误、游标和本页意图，旧epoch响应不得覆盖新主体。收到401/403也清结果和恢复键。现有layout/menu/MetricProfiles均保留。

原POST需要当前CSRF和Idempotency-Key。SDK必须由调用方显式提供两者，不自造CSRF、不自动换键或重试。页面优先真实csrfToken prop，其次当前cookieCsrf()；两者都无时自动读取技术扩展GET `/api/v1/metrics/capabilities`严格单字段`{csrf_token:string}`，仅原monitor.read门禁，不借账户或投放capabilities。准备中/失败时禁查询，可显式重试；上下文请求独立epoch/abort，旧主体CSRF不得晚到覆盖新主体。原生会话不再停在只有prop才能使用的状态，公开HTTP及三视口仍由主线验证。

显式查询生成一次冻结意图；翻页为新POST意图，原条件/页大小保留。失败重试保留原body、CSRF和幂等键。网络中断、坏HTTP body或坏200结构不能证明服务端未建立快照，标记结果未知；这时禁编辑筛选，切Tab/离开须明确确认放弃本页恢复。确认不表示取消服务端快照，也不产生广告操作。所有恢复仅本页内存，无Storage、URL Token或自动重发。

503显示未就绪错误、原request_id及字段错误，保留原查询；409提示范围/快照变化，明确确认后重新查询首页；空筛选成功、未查询、加载、来源失败与无权限为独立状态。Error原五字段及FieldError原四字段完整展示，纯文本转义，无v-html；本地错误request_id=null明确为未收到可核验的服务端ID，不冒充原Error响应。

## 文件与当前验证

新增SDK为`src/api/orbit/metrics.ts`，页面为`src/views/orbit/monitor/index.vue`，子组件为`MetricQueryForm.vue`、`MetricRows.vue`、`MetricRowDetails.vue`。没有更改公共路由、菜单、后端Store或既有SDK。

初始查询阶段曾实际105/105通过（6.79秒）；后续新增上下文和真实目录选择专属测试，本批最终计数以固定源码回归为准。SDK使用fetch替身，组件为真实Element Plus挂载，均只算纯结构/交互证据，不算HTTP、可信发行、浏览器或容量验收。相关文件Prettier与类型检查另见本批最终固定检查。Impeccable机械检测初始四个Vue文件返回空问题数组，不代替后续真实三视口检查。

上下文及目录接线固定源码后，五文件实际118/118通过（8.22秒）：API95、表单7、结果2、详情1、父页面13；`pnpm check:orbit`和本批11文件Prettier检查通过。包括真实目录分页SDK调用、已加载版本筛选、原完整UUID远程q、403/迟到候选隔离，native自动上下文、显式/cookie优先、上下文503/403和旧主体CSRF晚到拒绝；仍未计为公开HTTP或浏览器通过。

待主线验证：monitor路由和写入上下文、原POST真实503/恢复、真实有数据四实体查询与分页、撤权、三视口详情/横向表格/日期控件。生产PublicationValidationProvider和独立ExpectedUnitProvider尚缺，不使用SQL_ONLY_NOT_PLATFORM夹具宣称已完成生产指标采集。其他原监测功能（规则建议、依据、操作记录、采纳统计、提醒、导出、产品/父树下钻）未由本批查询页面替代，必须各自后续闭环。

## 本轮实际验证

主线公开查询与三视口父档19/19通过，三个视口9/9、46.15秒，无跳过或重试；原完整范围四dataset/四档分页、DAY44、分币种汇总、字面搜索及只读详情已逐项核对。首次版本同名导致选择不明确，现显示完整真实配置ID并按id精确选择，失败回执保留。搜索无匹配的完整单元coverage曾错误降为0，后端已按完整采集证明修复；字段有效零需独立零成员及逐字段完整事实证明，缺失注册及GBP未采集仍NULL。证据见server docs/orbit/evidence/python-metrics-public060-three-viewports.json。

固定前端当前872项、类型、17文件格式和构建通过，源码前后hash相同（frontend-checkpoint060-checkpoint.json）。原7Tab中投放师/渠道映射、分析规则建议、账户快照选择、生产发行及容量仍有待办；本有限联测不计全模块验收。
