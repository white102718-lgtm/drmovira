# 060同请求ASGI与list诊断分析

读取运行目录4bc4a41d69a447fea03daf9617910635的809份安全文件；schema2共808份、
schema1共1份。容量形状24execute且items_count=page_size共801，排除早于暖20的首次200
首读1份，四档暖样本各200。其他8份（4无list、4其他基础list）不混入暖分位数。
同trace严格检查HTTP/list trace一致，所有阶段都先在同一请求内计算差值，才汇总分布；
每请求从入口到app_end的七段相加与app_total误差<1e-8秒，不做不同样本P95相减。
安全聚合和当前7个源码SHA256位于
`.runtime/account-list-asgi-analysis-4bc4a41d69a447fea03daf9617910635.json`。

## 已证实的变化

800暖请求均24execute：相对上一诊断27，BUSINESS_AUTH从6降4、MANAGED_TEAMS从3降2，
其余标签次数保持；因此空vendor短路确实消除三条SQL。seal调用仍全部0，不能拿这批证明
百万身份资源的seal性能。并发/硬件/诊断不同，耗时改善不全部归因三条SQL。

|页尺寸|before_list均值/P95 ms|service均值/P95 ms|execute均值/P95 ms|非execute均值/P95 ms|
|---|---:|---:|---:|---:|
|20|194.766 / 304.319|194.664 / 252.423|189.776 / 246.633|4.891 / 5.794|
|50|229.628 / 313.049|236.087 / 296.028|228.432 / 287.094|7.658 / 8.327|
|100|236.961 / 306.545|251.800 / 279.932|242.651 / 268.743|9.151 / 10.459|
|200|307.616 / 471.457|337.782 / 510.739|323.016 / 495.492|14.768 / 15.382|

|页尺寸|list后→response.start均值/P95 ms|start后→最后body前均值/P95 ms|全部body send均值/P95 ms|末body后→app_end均值/P95 ms|app_total均值/P95 ms|
|---|---:|---:|---:|---:|---:|
|20|76.016 / 102.473|13.601 / 20.275|0.097 / 0.120|50.764 / 67.666|529.897 / 711.176|
|50|78.397 / 103.792|16.166 / 22.604|0.103 / 0.140|61.988 / 85.401|622.357 / 794.313|
|100|70.219 / 131.236|15.483 / 21.941|0.093 / 0.124|57.970 / 73.500|632.514 / 770.764|
|200|130.649 / 206.578|23.550 / 37.428|0.108 / 0.139|68.345 / 99.911|868.032 / 1050.992|

每请求app_total减该请求list_wrapper再聚合：200行均值530.236ms/P95709.719ms，
这才是同请求list外开销，非“HTTP P95减list P95”。
200行真实server app P95位置的单个trace `d2c9f652503f476081bc617907e4b217`：
before_list326.561ms、list_wrapper343.101ms、list后到start275.907ms、start send0.074ms、
start后到末body17.581ms、末bodysend0.015ms、末body后87.753ms，共1050.992ms。
这一实际请求execute330.910ms、非execute12.182ms，不能把其他请求的SQL P95塞进该分解。

原HTTP容量报告P95为659.268/763.959/727.938/1017.432ms。客户端样本没有技术trace，
因此只并列记录，不能与某个服务端请求强行一对一；客户端可在app最终清理结束前已收到响应。
同请求阶段证明list外存在显著开销，但不证明它是哪一条SQL、CPU或锁导致。

## 固定源码边界与下一步

account_details_routes.extended在list前完成CurrentUserDependency及read_committed_session
连接获取/READ COMMITTED设置；这些都在before_list内。get_current_user可读Redis/身份和
用户快照；缓存命中未必持query_db连接，不能直接声称每请求同时占两条连接造成池耗尽。
需实际checkout等待/同时checkedout数及命中状态才能证实。

list后至response.start包含JSONResponse构建、外层session.begin提交、RC连接关闭及默认
隔离级别恢复、框架/中间件路径。read_sessions.py确实使用独占AsyncConnection并通过
SQLAlchemy在归还时复原隔离级别，但这份诊断没有各子阶段计时，不能先删提交/隔离恢复。
末body后的app_end包含框架/依赖清理；最后send返回不等于客户端网络接收完成。

下一最小可证实步骤是只在诊断中加原依赖解析、RC checkout/设置、commit/close、
JSONResponse render几个固定时间段及pool当前计数，沿同trace而非继续堆SQL缓存。
不吞权限、不复用跨请求事务、不跳到期核验；未定位前不修改隔离语义、阈值或并发。
原固定SQL标签24次完整分布已在聚合JSON，execute墙钟也含事件循环/驱动，不冒充服务端耗时。

ASGI最终合并落盘发生在app_end之后，未计入service/list_wrapper/app_total；同步落盘会扰动
其他请求事件循环。此诊断档失败保留，不是正式容量合格或生产性能结论。未执行DB/Git。
