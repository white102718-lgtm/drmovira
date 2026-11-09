# RuleSimulationAccessFacade真实专项工具

当前：主线原62+新access8首轮真实70/70 PASS（23.31秒），回执`evidence/python-rule-simulation062-access-http.json`。11/11专属工具纯护栏通过；生产+工具39纯测主线另验PASS（1.15秒），Ruff/format通过。生产facade28纯测及候选063 SQL70/70均为其他范围，不能替代本工具真实队列结果。

入口`run_rule_simulation_access_checks(client,admin,headers,password,cache,database,cases)`，固定`RULE_SIMULATION_ACCESS_CASES`8组。native990670经rg确认与既有tools/tests无占用，避开scope-options的990631—990654。只创建当前UUID库真实SQL账户/身份和原HTTP角色/scope/Rule，不调用simulate/enable/指标发行或平台。与scope-options工具组合时仍保留其原用例/权限，不复用其人物夹具。

## 护栏和依赖

admin exact host127.0.0.1、整数port13306、orbit_py_it_加32位小写hex、SELECT DATABASE精确匹配，否则任何写/HTTP/engine前拒绝。异步engine只从admin同连接内存user/password及固定host/port/database构造，echoFalse/hide_parametersTrue、pool_size2/max_overflow0，首次实际异步SELECT DATABASE再核，finally dispose。不读取env、无需新的配置/第三方依赖或生产issuer。Windows模型复用既有install_windows_asyncmy_compat，不改变事件循环/SQL含义。schema/SQL权限/全局设置不改。

root需启用与rules-only一致的真实隔离profile入口，原Rule写可接ISOLATED_TEST profile；异步profile桥自身还会fixture_boundary核实际UUID13306。原Role仅rules.read，USER本人才是1001账户owner；用真实native登录/getInfo证明无create/edit/monitor/accounts/users/launch借权。scope与Rule创建由root真实原API完成。密码只用于fixture_login内存，不输出/写文件或命令。

辅助source文件：tools/fixture_login.py、metric_profile_reference_checks.py、其直接seed调用metric_profile_query_checks.py、rule_definition_checks.py、rule_editor_checks.py；生产新facade、rule_access/rule_profile_references/rule_editor_definition/rule_store/原授权与账户profile依赖均须由主线真实回执范围记录，不能只hash本工具。原Rule/scope公开Store及隔离应用配置由主线统一接入。

## 八组精确范围

1. 原角色rules.read-only、native USER登录与getInfo、1001真实账户、原scope201/Rule201；无事实/平台样本。
2. facade实际200/1000分页全ID有序无重漏，原canonical([IDs])根和count1001、每个账户真实当前USD/EUR及IANA时区逐项对账，八Rule表读前后逐值不变。
3. 012当前currency/timezone_id均NOTNULL，实际NULL写精确1048+rollback后原行不变；另本轮可变账户时区SQL技术值not/a-zone实际返回TIMEZONE_INVALID及原字符串，不补UTC。缺timezone/NULLcurrency分支只能标此前纯测通过，不能冒充当前schema可达；不ALTER/关闭CHECK/改SQLmode。
4. 实际facade实例与SessionTransaction的未EOF finish、replace假batch、重复iterator、另一Session、提交再begin旧ticket均拒绝；对已实际SQL读取的generator抛CancelledError并验证取消不被吞/不能finish。不声称阻塞SQL/服务端取消或P_S清理已测。
5. 本轮账户普通改名/revision1→2，完整成员ID根不变；历史冻结revision不是当前必须相等条件，八Rule表不变。
6. 删除本人物理原生role grant后facade精确403 PERMISSION_DENIED（finally还原仅测试清理）；最后账户转属root，使root caller可读但Rule owner USER不可读，root与USER facade都409 RULE_ACCOUNT_SCOPE_CHANGED。还原账户，仅这些测试技术可变身份/账户字段改变，八Rule表读取零写。不把SQL还原等同正式撤权再启用会话生命周期。
7. 先真实AsyncSession建立旧RR头快照，另原HTTP PUT合法name更新并创建RuleVersion2，未DROP或改sealed版本；旧RR facade最终当前头精确409 RULE_SOURCE_CHANGED，新事务旧expected精确409 REVISION_CONFLICT。不声称在当前SHARE头锁持有期间并发写已成功或已测锁等待。
8. 同原profile合法技术seed追加不可变新版本、切head，原Rule保持绑定旧version，facade409 METRIC_PROFILE_VERSION_CHANGED且不重绑Rule。该行为是当前内部支持局限，不宣称原合同全面满足，也不测试/影响历史成功receipt读取。

每组完成才append，无skip/retry或错误吞成空结果。除真实预期精确1048、原权限/状态错误外，未知SQL/业务错误原样失败给主线定位；没有宽泛多码集合。SQL记录/参数、URL凭据、Token或异常正文不输出。实际8组已按上述回执首轮全部通过；11纯测本身仍只证明工具前置护栏和URL固定内存来源，不代替真实SQL/锁/权限。1001不等50k容量、NOTNULL拒绝不等实际NULL分支已验、generator取消不等阻塞SQL取消；均无source issuer或simulate成功。
