# 独立五万范围创建专项

当前仅工具已实现，尚未运行真实数据库或HTTP。入口 `run_scope_create_profile_checks(client,admin,headers,password,cache,database,cases,*,diagnostic_dir)`，导出 `SCOPE_CREATE_PROFILE_CASES` 固定三项，不复用原44项容量名称、不刷新原字段证据。

主线以新互斥诊断mode显式调用，并在child安装既有scope create诊断器。仍只允许127.0.0.1:13306、本轮UUID数据库和实际SELECT DATABASE()一致；目录沿 `.runtime/account-scope-capacity-profile/<32hex>/`。client原read timeout必须等于10秒，工具不覆盖timeout、不重试创建。

第一组从当前真实bootstrap1业务映射取得tenant/owner/team，校启用和真实原生用户；不依赖其他工具全局fixture。只建立50000个有序UUID synthetic账户，使用原capacity的15列账户形状、USD/EUR混合、原真实授权/状态字段、唯一marker、原初始revision1；500行一事务，无日事实INSERT。装载后核实际50000行全七列及日事实为0，更新当前账户clock。此组不代表全账户/百万事实/平台容量。

第二组真实读取原capabilities，再POST原ScopeRequest FILTER。要求201、原五字段精确shape、count50000、UUID、有效scope_version、UTC毫秒created_at，以及所有实际原冻结七列 `[id,external_id,name,revision,owner,team,currency]` 的完整canonical SHA256。ReadTimeout时调用安全timeout collector，collector失败只固定标collected=false，原ReadTimeout对象原样抛出；报告及首失败保留，不能加时或跳过创建。

第三组使用原members GET及其真实游标，固定200行×250页。逐页原四字段shape/data_as_of/scope_version稳定，每成员原三字段精确对账，游标不循环，完整有序ID与50000个真实夹具完全相等、零重漏，并用成员三字段+已验证冻结元数据重算完整七列根与POST hash相等。不拉取或修改浏览器，不发送广告。

与原账户容量档隔离：本档不运行前置20并发P95门禁，只定位scope自己的装载、创建及成员读取阶段。先前原200行20并发P95=1.141秒仍是未达1秒的独立失败；不能因本档成功覆盖原失败或推断前端构建干扰。

护栏纯测13/13 PASS（0.37秒），含目标/实际库/10秒不变、三组新case名称、seed仅占位符批量账户且无spend INSERT、全七列哈希、ReadTimeout诊断成功/失败均原异常/单次POST、无敏感报告。纯超时用例仅500个内存替身，不是实际50000成功证据。与诊断器33项纯测分开记录，实际三组由主线串行执行后再补结果。
