# 列表身份摘要的同事务首次授权复用

本批只缩小 `AccountDetailsStore.list → IdentityPublicationSummary.prepare` 的重复授权。
原首次 `context(accounts.read)` 改由 `authorize_list` 执行，仍先完成实时菜单/动作、
业务主体和显式管理范围检查。私有票据仅同一摘要实例、session、根事务、actor、
accounts.read 和原 native/Cookie 上下文可用，不接收普通 BusinessContext。

票据为 frozen、eq=False、slots+weakref dataclass；对象身份哈希，不按字段相等。
WeakKeyDictionary 保存票据弱键和独立期望元组，不在登记值中引用票据本身；
登记值包含同session/事务/actor/action/context对象身份及原context五项primitive类型和值、managed和认证上下文身份。
即使用object.__setattr__强制改票据或原context字段，也在Cookie及来源SQL之前拒绝。
登记值持有session但不持有弱键，放弃的票据GC即撤登记并释放该引用；列表局部票据不会提前GC。消费先pop，
失败也不能复用，不回退其他鉴权。无跨请求缓存。签发/消费均拒绝活动nested事务，
已提交/回滚或换根事务拒绝；固定调用路径中间仅账户候选SELECT，不进入nested或DML。

消费时保留原 ensure_cookie_current 当前时间SQL，故退出、Cookie自然到期、OIDC配置
变化仍会失败关闭；await后再次核同事务/上下文。此处只省已持共享锁的业务scope和
角色菜单两次SQL读取，不删除Cookie检查。原resolve末段完整require_business_access、
account clock/到期分配投影检查、current_accounts及head/evidence/seal来源校验一字未改。
不能将prepare通过解释为返回授权；只有末段再次核验通过才返回最终数据。

普通prepare与accounts.sync发布路径保持原授权协议；没有可用Summary时列表仍原context。
来源锁顺序仍是首次授权→候选账户预读→Cookie重核→来源probe/config/release→account clock
→实际账户页→resolve末段重核。没有新增依赖、DDL、网络调用或跨请求缓存。

原account_details纯测试的Summary替身同步实现authorize_list/prepare_for_list，
保留原完整顺序和坏cursor不能来源probe的断言，不添加生产fallback。
新专属纯测覆盖伪造/复制/外实例/复用、actor/session/事务/nested/上下文改变、Cookie到期、
await中切换、弱键GC、普通prepare及sync隔离。这些不是MySQL锁或真实HTTP、容量证据。
原单worker 200行并发P95失败仍保留，节省SQL的实际收益由主线原数据/阈值复验。


## 实测检查点与本次加强边界

主线上一版同事务授权复用真实44/44通过146.04秒，回执
`evidence/python-account-scope060-auth-reuse-http.json`。四档20并发P95为
0.597/0.492/0.943/0.885秒，scope创建5.105秒、完整冻结与遍历31.747秒。
这是该版实际结果；主机波动存在，不能将全部改善归因于减少两条SQL。
本次追加独立登记元组与强制篡改拒绝，154项定向纯测通过，真实44项仍待主线重新验证。
