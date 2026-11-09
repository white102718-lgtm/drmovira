# 061新RULE来源消费专项

当前只完成工具和护栏纯测，尚未实际SQL/HTTP，不刷新任何历史验收。原40档与本专项分开；原scope10组完整保留。无Meta能力/模拟资格/广告写，数据库为root本轮13306 UUID隔离库。

入口`tools/rule_scope_consumer_checks.py`导出`RULE_SCOPE_CONSUMER_CASES`8个具名组，函数`run_rule_scope_consumer_checks(client,admin,headers,password,cache,database,cases)`。由root显式`--include-rule-scope-consumer`附rules-only/editor/editor-scopes、through061并统一串行；本工具无启动入口、不改app/迁移/Git。无需scanner/object-root额外kwargs。必须已有登录no-store修复、原角色/规则/阶段1、阶段2scope路由及20用途注册；FIXTURE指标只沿明确rules-only引导，不是生产Meta来源。

独立构造真实用户990612、990613，角色仅rules.create/edit，无accounts.read/users/monitor借权。后者技术SQL配置为当前TEAM_ADMIN和显式manager同team，用来测试当前协作编辑边界，不代表完整角色生命周期已验。账户四个，原真实scope接口冻结；来源MetricProfile为独立明确FIXTURE样本，无平台请求。

|组|精确可执行范围|
|---|---|
|1|真实CREATE scope→原Rule POST201、原15字段/GET、独立RuleVersion原body、sealed manifest source_kind RULE/sourceid/目标Rule/count/原来源hash/成员ID根全部对账|
|2|真实UPDATE scope冻结Rule1，原PUT IfMatch1→Rule2，manifest准确新源；scope冻结revision仍1，不改写历史|
|3|新UPDATE scope指向RuleA却用RuleB当前CAS保存409；新scope冻结A2后正常编辑到A3，再用scope2+当前CAS3保存409；两个失败均原八表counts/Rule clock无变化|
|4|已消费CREATE scope移给另一新Rule409；独立新scope第一次Rule outbox1644后八表/clock全回滚且无source绑定，删本轮自有失败trigger后原key可完整成功，不遗留占用|
|5|两真实HTTP线程Barrier同时不同name/key使用同CREATE scope，无重试；精确1×201+1×409，唯一Rule绑定，八表delta[0,1,2,1,1,1,1,1]及clock仅+1；并非大容量/多机竞争证明|
|6|原CREATE成功键在Rule已更新且指标停用后仍原receipt，异body409，当前原create撤权403；不重新消费来源或增版本|
|7|当前协作者无accounts/users权限，私有scope成员404，但沿原rules.edit编辑同Rule公开manifest成功；manifest不复制/不借scope creator身份|
|8|两源同UUID409且八表/clock不变；技术隔离DB注入：从原账户scope API真实完整样本，派生新UUID的四表完整构建0→成员→ready1→audit/outbox，显式BEGIN/COMMIT/失败ROLLBACK；新UUID故意等于未消费RULE scope。原源不改、无guard/FK关闭、无SQL返回替换。这不是正常HTTP可制造UUID碰撞的证明|

工具失败沿原checked只打印固定安全expected/actual/code，绝不正文/token/密码/SQL参数。新role密码hash取本轮原root验证数据，密码仅已有内存参数，经原登录签发会话。所有SQL数据库guard在首个查询/fixture import之前，之后SELECT DATABASE再次精确核对。碰撞别名保留本轮隔离库，由root原整体fixture清理处理，不擅删不可变历史或其他服务。

主线实际结果：through061原40+上述8组完整48/48 PASS、17.58秒，证据`evidence/python-rule-scope-consumer061-http.json`。真实SQL/HTTP执行了首次绑定、原字段、回滚与双请求并发，不仅是工具纯测。未覆盖50k scope/跨机worker/正式角色issuer/Meta来源，初次并发通过也不能称10万DAG或全模块验收。061带RuleVersion完整历史升级仍是另一项独立待办，不能由本八组新数据代替。

冻结交接时工具护栏`python/tests/test_rule_scope_consumer_tool.py`10/10 PASS0.16s；Ruff/format PASS。SQL参数数目及碰撞五步同事务AST检查、双线程/barrier结构属于纯证据；实际8组由上段主线回执单独证明，不提升为完整业务验收。正式源/旧40组工具均未修改。
