# 063候选SQL护栏专项

当前：主线原62+候选8实际70/70 PASS（22.85秒），证据见文末。14/14工具纯护栏测试通过（0.35秒），两个文件Ruff/format通过；063仍candidate，无模拟API或来源authority验收。S2a原42项独立，不把工具纯测或主线5322全量纯测称模拟业务完成。

入口：`run_rule_simulation_schema_checks(client, admin, headers, password, cache, database, cases)`，常量`RULE_SIMULATION_SCHEMA_CASES`固定8组。无新依赖。仅由主线显式`--rules-only --include-rule-simulation-schema`、through062且同原Rule隔离fixture开关的本轮UUID库运行。工具不注册runner、不启动DB/进程、不加载env或建立新连接，不调用simulate/enable、模型或平台。

## 前置与候选应用

admin必须实际host127.0.0.1、整数port13306、orbit_py_it_加32位小写hex，SELECT DATABASE精确相等，session必须STRICT_TRANS_TABLES及foreign_key_checks=1，并具有runner显式MULTI_STATEMENTS连接能力。先确认八张候选表均不存在及062菜单存在；任一候选表已存在即拒绝，不DROP/重新应用，不关闭FK/trigger。

只读固定docs/orbit/sql-drafts/063_rule_simulation_candidate.sql，显式执行并drain每个nextset；不复制到正式migrations或添加迁移记录。DDL是MySQL隐式提交、不能承诺异常整批回滚；root若DDL失败必须保留安全errno/失败点并明确残余表由本轮UUID生命周期处理，不能把半schema重跑算成功。metrics返回候选SHA256与8表/24trigger实际元数据，不返回SQL/参数/连接或凭据。

## 完整外键图与限制

复用`MetricFactSqlFixture(admin,database)`提供原真实账户及048不可变实体链，`seed_metric_reference_profile(...,index=963)`提供严格040版本与hash；原scope能力/POST及Rule能力/POST建立025完整私有范围和057同Rule manifest、RuleVersion/head。目标AD、TODAY、一账户/实体、两个原条件以便验证叶序，原API真实返回201且首revision1。原scope/Rule的隔离fixture开关由主线启用，绝不通过HTTP参数打开。

048 publication由既有技术fixture先BUILDING再完整SQL形状PUBLISHED、零cell、明确ISOLATED_TEST/source_proof.SQL_ONLY_NOT_PLATFORM，作为复合FK探针；该行不证明真实来源issuer或完整预期。063的MISSING单元、UNKNOWN实体/叶、根同样是标注SQL_ONLY的约束数据，并未通过实际source/evaluator/publisher。因此即使SQL READY探针通过，也不能称业务Simulation READY、实际指标成功发行或原模拟API完成。没有绕FK、DROP trigger或伪造源资格。

## 八组固定计划

1. 八表/24trigger实际元数据，SQL mode及连接护栏。
2. 同Rule精确version/manifest/profile/publication复合FK完整建图，真实账户/实体维度及两叶。
3. 原Simulation13不同JSON空白的raw语义一致正例，原bytes/hash准确读取，三方receipt绑定；sealed头/叶/成功request自赋值UPDATE也精确1644拒绝。
4. 另一份合法Simulation13 raw及其正确自身SHA，与正确storedJSON不一致，精确1644拒绝。
5. raw正确但storedJSON的业务hash不同，精确1644拒绝。
6. 两个合法条件叶交换顺序而集合相同，精确1644拒绝，不用JSON_CONTAINS替代有序比较。
7. 原raw前置非法UTF8字节，精确1644拒绝，不记录原bytes或错误正文。
8. 每个负例都在显式admin.begin后先写audit/outbox并更新READY头，再request失败；finally rollback后八表全部原行逐值不变，最终BUILDING/PENDING且rawNULL。不能因admin autocommit=True只回滚最后statement。

每组仅完成全部断言才append；异常不转成功/skip。MySQL拒绝仅捕获pymysql.MySQLError并要求当前预期errno1644；若实际CAST/strict字符处理返回另一errno，保留失败让主线逐条核真实语义，不能宽泛接受任意数据库错误。原数据、raw、token、username/password与SQL参数不输出。只输出固定scope/phase/整数errno。

纯测试只验证目标/实际DATABASE/strict/FK/multi/existingtable前置、固定候选路径/八组及raw语义的数组有序与严格UTF8/重复键拒绝；并不执行24trigger或证明SQL采用性。


## 主线真实限定回执

主线已串行执行原62组加本工具8组：70/70 PASS，22.85秒，证据`evidence/python-rule-simulation063-candidate-sql.json`。八表24trigger实际采用、正常JSON空白与原bytes保存、四类精确1644拒绝及八表原行回滚均通过，无首轮失败。063仍仅候选，未复制为正式迁移，未实现或调用simulate链路；SQL_ONLY形状样本不代表source发行权威。14项工具纯测和S2a42项纯测仍各自独立范围。

本工具实际调用的辅助文件（供主线source清单）：`tools/metric_fact_schema_checks.py`、`tools/metric_profile_reference_checks.py`、该seed直接调用的`tools/metric_profile_query_checks.py`、`tools/rule_definition_checks.py`、`tools/rule_editor_checks.py`。生产纯验证依赖`python/orbit_api/rule_contract.py`、`rule_simulation_contract.py`、`configuration.py`、`directory_tokens.py`；SQL候选与工具自身也须摘要纳入。HTTP实际应用源码仍由主线按本轮公共清单记录，不能只记录上述辅助文件代替全部路由/Store来源。
