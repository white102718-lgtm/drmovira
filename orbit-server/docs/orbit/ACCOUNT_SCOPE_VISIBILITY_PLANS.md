# 五万范围成员可见性查询：真实计划结论与代次方案评估

当前结论：保留生产LEFT JOIN全体可见性复核，不替换NOT EXISTS、不添加生产覆盖索引、不按旧account_clock跳查。数据库强制visibility_generation仅为未采用的设计评估，未写代码或迁移，不阻塞其他模块。

## 已执行证据

- 主线命令：`.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 31 --account-scope-visibility-plan-only`。
- [真实回执](evidence/python-account-scope-visibility-plans-http.json)：14/14通过，总169.48秒；其中初始化/框架6组和本专项8组，不把14组全称为性能场景。
- [实际计划与计时](evidence/python-account-scope-visibility-plans-metrics.json)：MySQL 8.4.13，50,000独占账户、三份各50,000成员的SQL快照，共150,000成员；0条日事实。装载12.5614秒，finally清理验证PASS。
- SUPER使用原真实身份；TEAM_ADMIN、USER以真实角色API授accounts.read、实际登录，TEAM显式管理USER所属团队。该项验证身份前置，主体是SQL微基准，不冒充完整HTTP分页/撤权或实际平台采集。
- 每个角色/状态/变体实际执行3次，保存原样本和中位数；另执行EXPLAIN FORMAT=JSON及EXPLAIN ANALYZE。冷缓存未测，没有并发性能结论。

## 全部可见时中位耗时（秒）

|真实数据角色|生产原LEFT JOIN|生产等价NOT EXISTS|影子覆盖LEFT JOIN|影子覆盖NOT EXISTS|
|---|---:|---:|---:|---:|
|SUPER_ADMIN|0.7411|1.1305|0.6841|1.6358|
|TEAM_ADMIN|1.0580|1.9474|1.0506|1.9146|
|USER|0.7798|1.6806|0.8122|1.6917|

生产LEFT的成员m使用PRIMARY的tenant_id/snapshot_id前缀，实际读取50,000行；账户a用PRIMARY等值查找，实际loops=50,000。TEAM还执行真实团队管理范围判定。估算成员行数出现75,000或73,511，不能把估算当实际行数。NOT EXISTS出现物化子查询及auto_distinct_key，本机本次各角色均慢于原LEFT；不能仅凭SQL写法推断更快。

候选索引只建立在同连接TEMPORARY同宽影子表，索引为tenant_id/id/owner_user_id/owner_team_id，候选显式FORCE INDEX以测其路径；源生产表没有ALTER或hint。影子表人口、统计、物理布局、缓存与生产表不同；SUPER略低、TEAM接近、USER更高，不能归因为生产覆盖索引会改善，更不能据此推荐上线。

无旧clock bump负例中，TEAM/USER直接改变最后一条成员账户owner/team；SUPER用同一独占账户缺失。四种SQL都实际识别不可见，工具核旧account_clock未变。它们是故障注入，非业务转属或真实日历跨日验收。原SQL和原工具断言均未放宽。

现有约178秒/250成员页是另一份真实容量回执的数据，不能以本次单次SQL中位数替换该总耗时或推算已优化后的工期。尤其TEAM原全量SQL本次超过1秒，不可拿此前单owner账户列表P95目标的通过结果来掩盖此处独立瓶颈。

## 为什么旧account_clock不能作安全缓存

正式账户受理/导入/到期投影/同步均可追到clock锁与event同事务推进；但直接SQL和维护操作并无数据库约束必须推进该clock。现有tools/account_scope_checks.py包含直接UPDATE owner/team且不bump的撤权断言。若只在带MAC旧cursor的后续页跳查，这一反例必须新增为“先取cursor，再改尚未翻到成员，下一页立即409”，不能改工具补bump掩盖。

每页真实authorize、scope creator、auth_version和权限指纹仍不可省：租户/用户/当前团队停用、角色/动作撤销、USER所属团队变化、TEAM显式managed集合变化均不能用账户代次取代。原snapshot成员及历史名称也必须保持不可变；仅账户代次没有覆盖直接篡改snapshot/member的问题。

## 独立visibility_generation候选：必须先证明的协议

候选表按tenant保存不可复用epoch UUID、单调generation、ready和schema/protocol版本；不复用account_clock。由账户INSERT/DELETE及owner_user_id/owner_team_id/tenant_id/id相关UPDATE触发器在同一InnoDB事务推进，跨租户移动必须使旧/新两侧失效。普通rename只改name/name_prefix不改变可见性，不能无依据让合法冻结选择失效；auth_status/unbound_at当前不是scope.visible_clause条件，但若将来筛选语义扩大，必须同步升级触发条件和协议版本，而非默认遗漏。

候选MAC payload须绑定tenant/actor/subject/snapshot UUID、snapshot hash/不可变成员版本、auth_version/指纹、query/page_size/after，以及epoch/generation/protocol。新快照或旧cursor不带受信代次时执行完整复核后才签当前代次；MAC错形/用途错误继续拒绝。代次变更本身不等同SCOPE_CHANGED：应完整复核，仍全可见则保留冻结成员与历史名称并签新代次；真越权/成员缺失才409。找不到generation、ready=false、版本未知或schema不匹配只允许完整安全路径或明确503，绝不默认“代次0相同”跳查。

这些是必要条件，并不是已证明可安全采用的实现。当前存在以下阻断。

### 锁序与读视图阻断

当前账户写遵循clock→account→command/审计；触发器再写generation会增加account→generation锁边。若成员页持generation共享锁后执行需要账户锁的完整检查，会与直接SQL持account锁后等待generation形成反向等待。即使快路径只读冻结member不锁账户，也不能忽略慢路径及共用authorize里的clock锁。

更直接的现存反例：一事务直接UPDATE account（触发器持generation写锁），随后像现有工具一样bump account_clock；另一请求已持clock共享锁再等generation共享锁，形成generation→clock与clock→generation环。不能为躲此问题把旧测试改成先bumpclock，或把死锁不断重试当作已消除锁序问题。统一数据库写过程/权限约束或重新设计scope读事务后才能继续评估，均超出“只添触发器”范围。

不持generation锁的两次读也不是自动正确：必须证明两次读是当前已提交代次，且完整反连接的MVCC读视图不早于被签代次；在REPEATABLE READ旧read view里两次普通SELECT相同不能证明无新提交。并发作者可能在账户变更后、generation提交前阻塞；正确的线性化点需明确，不能按墙钟或固定TTL猜。候选READ COMMITTED、乐观复核/重启事务等都需单独证明和真实并发测试，不能偷偷改变共享事务隔离级别。

### 首次回填与生命周期阻断

应先禁用所有快路径，建立generation表/epoch并安装全部触发器；触发器必须让新租户/缺行初始化为不可跳查，不能靠应用恰好预建。多个CREATE TRIGGER并非与所有账户写一次原子上线：中间窗口不能发受信cursor。最保守方案是在明确维护写屏障下核表/触发器定义、建立新epoch、设置ready，再由首个完整复核发新cursor；无此屏障及并发回填证明，不启用优化。首次代次无需重算历史账户哈希，但不能把旧cursor已有的全量复核当作新epoch证据。

应用账号不能直接写generation/ready/epoch、DROP/ALTER/TRUNCATE源表或删除触发器。恢复备份、回滚旧应用、换库、DDL维护和触发器变更必须关闭快路径/轮换epoch并重新完整复核，防止旧epoch ABA复用；generation溢出不能回绕。所有相关表必须InnoDB；触发器或事件失败整笔失败，不能吞错后提交账户而丢代次。

仅DML触发器并不能覆盖TRUNCATE/DROP，也不能覆盖外键级联；必须对这些路径明确定义禁止或维护epoch轮换。否则SUPER只靠“generation不变”会漏掉全表删除。官方说明见[CREATE TRIGGER](https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html)、[TRUNCATE TABLE](https://dev.mysql.com/doc/refman/8.4/en/truncate-table.html)、[外键级联](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)。

### 冻结成员与租户假设阻断

ready snapshot的成员增删、snapshot_id/tenant_id重写、owner/hash/count/auth_fingerprint篡改不能被账户触发器捕获。当前表的“不可变”主要由应用协议保证，不是全面数据库强制。候选必须额外证明这些表不可在ready后改写，或用独立成员epoch/dirty状态使任何改变都拒绝继续；不能发现成员变化后仍按旧hash签“全量已验证”。需要允许合法清理而不允许改写在用快照，清理与服务并发也要有明确协议。

三角色的每页当前菜单/动作/用户与租户启用、creator、auth_version/指纹、TEAM显式管理集合照旧实时复核，不能把它们缓存到generation。已到期未追平分配仍执行既有guard503；时刻到达并不一定有账户UPDATE，不能因generation未变跳过guard。计划执行期owner/team/currency、身份/能力验证继续逐对象执行，不能借“分页验证过”成为写授权。

## 采用前强制矩阵（全部未运行）

1. 三角色先取cursor；直接SQL改未翻到成员owner/team且不bump旧clock，新generation必须自动变；下一页立即409。删除、同ID删除后重插、跨租户移动同样覆盖，不能只测第一页。
2. INSERT/DELETE/相关UPDATE批量、多租户交叉顺序、两个并发写方与读者；记录实际锁序、等待、deadlock/rollback及重试边界。故意构造account→generation→clock旧工具写法，不能只测顺序良好的应用写方。
3. 事务回滚/审计失败/trigger SIGNAL、generation缺行/满值/ready=false、缺触发器/旧schema/旧epoch；回滚不误发布代次证据，缺保障必须失败关闭或完整复核。
4. rename在冻结快照中保留旧name，cursor不因普通显示变化无故失效；真实owner变更后仍可见则完整复核续页，不静默重算历史成员。
5. creator/actor/subject、角色/动作撤销、租户/本人或本人团队停用、managed team移除，均在相同generation下即时拒绝；过期/改签/跨query或跨snapshot cursor拒绝。
6. 就绪成员篡改、清理并发、备份恢复/重新建表、TRUNCATE/级联/触发器DDL权限边界、跨午夜到期guard与恢复器无自锁。触发器不能证明的路径明确禁用快路径。
7. 重新真实50k/250页、三角色和并发读写测量；完整成员hash零漏重、撤权即时性不变，并记录写侧吞吐/锁等待。单租户每账户一行的触发器可能把50k批量导入集中到同一代次行，写放大未测，不能只汇报读快了。

当前决定仍为不采用该优化。以上锁序、读视图、成员不可变及维护屏障没有完整证明，不能用“有触发器”替代完整安全性；生产原SQL与索引保持原样。

官方依据的适用边界：[事务表中触发器失败随语句回滚](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html)；[InnoDB死锁处理建议](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks-handling.html)。本文具体锁环与候选协议是结合本仓库路径的设计推论，尚未作为数据库行为实测结果。
