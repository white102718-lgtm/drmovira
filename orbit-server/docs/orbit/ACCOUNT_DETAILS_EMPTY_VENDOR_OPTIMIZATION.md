# 账户详情空户商引用短路

只改AccountDetailsStore.enrich：records返回vendors={}时aliases={}，不调用
resolve_vendor_alias_snapshots。该helper原空输入仍做reference_context的accounts.read
两条SQL及visible_vendors的managed查询，最后必返{}。没有可显示代称数据时移除这三项
空工作，不改变共享helper本身的授权合同。

有真实vendors时原helper照常执行，当前撤权/来源错误原样传播，不部分返回；代称未知
保持NULL，不以户商name替代。原首次list授权/私有票据/Cookie校验/resolve末段授权及
当前账户校验、catalog/account时钟均不改。引用目录records调用仍保留，未缓存。

6项新纯测覆盖无vendor、找不到目录vendor、真实代称、未知NULL、非空撤权传播及空账户页。
连原列表/摘要/票据回归160/160通过1.10秒，Ruff通过。这不证明真实SQL从27降24或容量达标。
主线将按原50k/百万事实/四档20并发及同安全diagnostic重验；上一批失败与诊断开销限定保留。
实际P95受路由/提交/压缩/网络/事件循环等影响，不承诺省三条SQL即可解决尾部延迟。
