# 060账户列表首屏诊断分析（非正式容量结论）

读取806个安全报告，未执行SQL或浏览器。按page_size/items_count及execute_calls=27
技术形状识别容量样本：800个暖首屏，另1个最初200行首读（list48.108ms），
5个其他基线首屏排除。200行最初首读按文件写入顺序早于第一批20行暖读识别；
没有借业务q/ID分类。完整聚合在`.runtime/account-list-query-analysis-800368f9920648d5bad0a95b521bbc93.json`。

|页尺寸|样本|list均值/P95 ms|execute均值/P95 ms|非execute均值/P95 ms|
|---|---:|---:|---:|---:|
|20|200|228.666 / 274.983|223.008 / 269.311|5.658 / 6.381|
|50|200|248.017 / 311.188|241.064 / 302.939|6.952 / 8.713|
|100|200|270.315 / 307.166|260.270 / 292.611|10.045 / 10.613|
|200|200|351.730 / 502.893|335.866 / 486.826|15.864 / 15.614|

每个容量样本恰好27次execute，成功且恢复execute；seal计数全部0。
这批没有身份已发布资源，不能用它推断百万身份摘要seal性能。
非execute是墙钟差值，不是CPU；list不包括路由前鉴权、提交、JSON编码/gzip与网络。
同档instrumented HTTP P95分别733.729/787.951/850.662/1020.475ms。
不能相减不同请求的P95称为阶段耗时，但list P95与HTTP P95量级差表明仅list诊断不足以
解释HTTP尾部。记录本身有落盘/分类开销，诊断失败不等同原未加诊断容量结论。

## 固定标签访问次数及200行耗时

每请求：BUSINESS_AUTH6；ACCOUNT_PAGE3；MANAGED_TEAMS3；OTHER3；IDENTITY_HEAD2；
ACCOUNT_CLOCK2；SERVER_TIME2；SPEND_AGGREGATE1；SOURCE_CONFIGURATION1；
DETAILS_OBSERVATION1；OWNER_DISPLAY1；REFERENCE_CLOCK1；DETAILS_CLOCK1，共27。

200行标签每请求均值（约ms，精确分位与最大单次见聚合JSON）：
BUSINESS_AUTH77.0、SPEND_AGGREGATE37.6、ACCOUNT_PAGE35.2、IDENTITY_HEAD32.3、
OTHER29.3、MANAGED_TEAMS28.6、SERVER_TIME26.7、ACCOUNT_CLOCK17.2、OWNER_DISPLAY13.2、
DETAILS_OBSERVATION11.1、REFERENCE_CLOCK9.6、DETAILS_CLOCK9.5、SOURCE_CONFIGURATION8.7。

静态源码解释：三次ACCOUNT_PAGE分别是摘要预读、clock后实际页、resolve当前账户复核。
三次MANAGED_TEAMS对应首次context、空户商visible_vendors、resolve.current_accounts。
六次BUSINESS_AUTH对应首次context、resolve_vendor_alias_snapshots重新授权、resolve末段，
各两条。OTHER三次可由目录clock及两次account clock附带的到期分配command门禁解释；
这是固定源码核对，不是从报告中读取SQL正文。现工具没有单独区分它们。

execute墙钟包含数据库、驱动解码、事件循环等待，不能视为服务端SQL耗时或锁等待。
200行多个不同标签最大单次同时达到约180–233ms，并非只有某一表；目前无证据证明
单一索引、某个共享锁或某个聚合独占导致串行。SPEND按页增大时均值上升，值得捕获实际
EXPLAIN/服务端计时，但不能把它直接判为唯一瓶颈。实际首屏SELECT与简化EXPLAIN差异
另见ACCOUNT_DETAILS_CAPACITY_PATH_AUDIT.md。

## 下一最小可验证优化建议（尚未实施）

优先在AccountDetailsStore.enrich中，records返回的vendors为空时跳过
resolve_vendor_alias_snapshots，直接aliases={}。当前容量每页无户商，helper仍重新执行
accounts.read两条SQL及visible_vendors的managed查询，最终必返空字典；此项可有界去掉
3条无输出工作，而非缓存/弱化现有helper协议。首次list授权和resolve末段完整授权仍在，
有真实户商时原helper及权限路径全保留。须纯测空/非空/不可见户商与原DTO完全一致，
再真实HTTP/原四档20并发复验，不承诺必然消除HTTP尾部。

其后再补路由前鉴权、事务提交、响应压缩/发送阶段的技术计时及事件循环延迟；
已有profile不能证明这些阶段的具体占比，不以加worker或放宽阈值代替实测。
不优先删resolve当前账户/到期投影重核、合并当前时间检查，避免用性能改变失效语义。
