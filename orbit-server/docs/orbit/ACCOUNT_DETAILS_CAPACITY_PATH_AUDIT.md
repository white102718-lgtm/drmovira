# 账户详情容量访问路径只读审计

本审计未改查询、索引、阈值、并发或数据，也未自行运行数据库。
依据 `evidence/python-account-scope060-profile-first-report.json`，五万账户/百万日事实
完整250页无重复遗漏，首读HTTP80.8ms，200行20并发P95为1.141秒，原失败保留。

报告的账户首屏EXPLAIN ANALYZE走PRIMARY，实际扫描201行约0.303ms，无filesort。
但它是简化SELECT id，含unbound_at IS NULL；实际AccountDetailsStore._page为SELECT a.*，
还含完整数据范围及筛选。因此只能证明该简化首屏，不是实际整条读取链已优化的证据。

消费汇总当前JSON_TABLE按本页账户驱动STRAIGHT_JOIN并FORCE PRIMARY，避免旧反向扫全租户。
此报告没有该实际查询的EXPLAIN；应验证200账户×20日约4000事实的预期访问路径，不能拿
账户首屏0.303ms代替聚合SQL计划。摘要head/evidence/proof/seal/raw查询有界批量，
现资料不能证明它们所有实际SQL的服务端耗时、连接池等待或锁等待。

200行暖读吞吐23.87请求/秒、P50 0.785秒；20行49.41请求/秒。随rows增长可能同时增加
原事实聚合、摘要核验、DTO、压缩、网络与事件循环排队，尚未定位单一瓶颈。
cProfile异步coroutine恢复次数不是请求数或查询数；不能凭共享锁存在推断串行。

后续可验证顺序：记录实际固定标签SQL次数/耗时/返回行数；对实际page、消费聚合和
五组摘要读取做EXPLAIN ANALYZE；分别计连接池、SQL、逐行核验、JSONResponse、gzip与
发送时间，并观察事件循环延迟。禁止输出SQL参数/业务值/凭据。原20并发/四档不变。
当前fixture名称全匹配且并发反复首屏，是暖热点专项，不等于深页、稀疏名称和TEAM范围容量。
多worker如另测须明确生产配置、Redis一致性、连接/内存预算，不能覆盖本单worker历史失败。
