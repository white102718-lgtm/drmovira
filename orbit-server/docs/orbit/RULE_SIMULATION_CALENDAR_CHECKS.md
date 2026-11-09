# 规则日历预期真实工具

当前仅工具准备完成，12/12纯护栏测试PASS（补接点后0.84秒），工具/测试Ruff与format通过；未运行SQL/HTTP。实际7组统一交root队列。原expected_units21纯测、access1001账户70/70及063候选70/70均不是本工具已通过证据。

固定入口`run_rule_simulation_calendar_checks(client,admin,headers,password,cache,database,cases)`，常量`RULE_SIMULATION_CALENDAR_CASES` tuple7组。native990671已rg确认无既有占用，区别access990670及scope-options990631—990654。仅新tool/test/doc，不修改旧access工具、calendar生产模块、runner/迁移或私有配置。

## 初始化和安全边界

复用`rule_simulation_access_checks.guard_target/engine_url`，固定127.0.0.1:13306、随机UUID库、SELECT DATABASE严格相等；无env/新服务/外呼。异步engine从同admin内存连接值构造，echoFalse/hide_parametersTrue/pool_size2/max_overflow0，首次异步actual DATABASE复核，finally dispose。密码仅本轮fixture_login内存使用，不输出/写文件/argv。

原真实Role只rules.read，USER为1001账户真实owner；通过native登录/getInfo证明无其它业务动作。root沿原HTTP scope/Rule创建一份1001成员scope及TODAY/YESTERDAY/LAST_3D/LAST_7D四条原规则，技术profile通过既有合法seed建立。root需与rules-only一致profile隔离flag；生产正常配置不自动fixture。

账户币种USD/EUR与真实IANA America/Los_Angeles、Asia/Shanghai、Pacific/Kiritimati、Europe/Berlin轮转，零指标事实。原八Rule表全行不变baseline在全部初始化写入结束后取，不能把4条Rule/scope新建算进只读边界。全程不调用simulate/enable或source provider，不造READY，也不把日历完整当采集/实体清单完整。

## 固定7组

1. read-only角色/native/1001真实账户、root原scope及四Rule201完整图。
2. 同一个实际SessionTransaction与同calendar实例依次计算四窗口，各窗口每次使用新Rule父票据，分别以200/1000父批次完整消费；calendar输出始终最多200。每个unit的account/date/IANA/currency/window/status/reason与独立ZoneInfo业务日计算逐项对账；同Rule两分组完整根相同，所有summary同SQL参考时刻。仅当前Session.execute局部包装计固定`SELECT UTC_TIMESTAMP(6) AS evaluated_at`，本事务实际一次；不计参数、不输出SQL/正文，finally恢复原bound method，无全局hook/连接池修改。
3. 本轮可变账户坏IANA技术值not/a-zone，finally精确还原；真实UNRESOLVED_WINDOW sentinel保留首账户且无日期/不补UTC，account_count1001、resolved1000/unresolved1/calendar_completeFalse，完整ID不漏。不是source MISSING或合法零。
4. 原currency/timezone NOTNULL，真实NULL写精确1048、显式rollback及原两列不变，不ALTER或关闭护栏。NULL/缺字段正常分支仍只有纯测，不能声称实际可写。
5. 三个独立真实事务验证early close、CancelledError和并发calendar重复迭代；然后原父facade继续真实EOF取得完整父summary，calendar仍因部分消费拒绝finish，避免仅靠无父summary伪造负例。取消仅generator级，不冒充阻塞SQL/server取消/P_S清理实测。
6. 伪父batch在SQL时钟前拒绝（计数0）、replace伪unit批次、foreignSession、提交后新事务旧ticket均拒绝；生产发行对象/实际事务能力不跨批复制。
7. 全阶段结束原八Rule表全行逐值仍等于初始化后baseline，候选Simulation表数量未增加。不调用模拟路径/无来源发行；现有其它candidate技术表若主线同时预置，不能把其存在归本工具新建。

每组完整断言后才append；未知SQL/业务错误原样交主线，不退空/skip/retry。当前所有实际用例待跑，11纯测试只检隔离guard/actualDB先行、固定语句局部计数和成功/取消/异常恢复、native/窗口/组数，不证明真实窗口/SQL结果。

source辅助清单：旧tools/rule_simulation_access_checks.py（guard/engine_url）、fixture_login.py、metric_profile_reference_checks.py及其metric_profile_query_checks.py seed、rule_definition_checks.py、rule_editor_checks.py。生产新rule_simulation_expected_units.py、rule_simulation_access.py、rule_metric_windows.py及其原授权/profile/Rule/账户公开依赖须由root纳入实际回执源码清单；不以本工具hash替代整条API/SQL来源。


补主线verified_profile接点：第2/3组完整父EOF后调用实际`access.verified_profile(session,ticket,parent_summary)`，要求真实RuleProfileBinding且id/version/hash精确等于fixture初始化后从原RuleVersion读取的冻结三列；独立当前Session.execute调用级计数必须仍0，finally恢复原方法，不返回/输出proof。不增加CASE数，不在account/Rule锁后补SQL或其它source锁。新工具pure合计12项；此接点实际SQL仍随主线102档验证。


## 主线真实102档限定结果（后续实测覆盖上述待跑计划）

主线组合102/102 PASS，84.93秒，新7组calendar均实际通过；证据 `docs/orbit/evidence/python-rules062-options-simulation-calendar102.json`。实际范围为1001账户（不是50k）、四IANA与四窗口、200/1000父批次完整日历根一致、SQL UTC6同一事务一次、坏IANA sentinel不漏账户及NULL写精确1048拒绝。完整EOF后的verified_profile真实返回冻结RuleProfileBinding，id/version/hash与原Rule版本相符，调用未增加SQL。

这是授权账户业务日日历与只读权限证据，不证明事实来源发行、独立实体清单、采集coverage或Simulation READY；无simulate/enable/source成功。取消证明生成器/事务票据语义，不扩大为服务端SQL等待取消。上文“待真实”保留为当时计划，实际范围以本节和具名回执为准。按最新第七节先交付规则定义闭环，不继续扩展模拟内部组件。
