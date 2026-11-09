# 规则定义与展示元数据真实闭环专项

当前工具已编写，尚未执行真实SQL或HTTP；纯测只覆盖隔离护栏，不冒充业务验收。入口为 `run_rules_definition_flow_checks(client, admin, headers, password, cache, database, cases)`，常量 `RULES_DEFINITION_FLOW_CASES` 固定8组。由主线 `--rules-only --rules-definition-flow --include-rule-display-metadata` 显式调度，禁止工具自行加载env或建立服务。

本轮严格限定127.0.0.1:13306、随机UUID库并核SELECT DATABASE()。新原生身份990680/990681分别具有真实本租户/外租户业务角色及仅rules.read权限，均走原登录与会话链；密码仅内存。角色、账户和profile为隔离技术夹具，不能证明外部指标发行或平台权限。

## 8组实际计划

1. 原HTTP创建DRAFT、详情回读及过滤列表；严格保留Rule15/Page4。
2. 两条Rule一次批量展示元数据，输入顺序、真实拥有者和团队名称、原native创建人及SQL UTC毫秒逐项对账。
3. OR两组、decimal阈值、冷却0、每日上限8编辑到revision2，原成功key/旧CAS重放及回读。
4. DRAFT暂停严格409（仅负向）；原归档到revision3、列表/详情回读，原创建人/时间不变。ENABLED暂停正向由主线另行标记的技术状态夹具检验，不在本工具范围。
5. 仅rules.read用户读取自己的原详情和元数据，创建能力403；不借directory/accounts/monitor/launch权限。
6. 可见与不可见Rule混合整请求404，真实外租户会话访问已知Rule整404且不返回items。
7. 同Token撤回read即时403，finally恢复仅为夹具清理；空/重复ID、重复query、未知query、GET正文和targettenant各按固定错误拒绝。
8. 在业务写入和夹具初始化完成后，对原规则八表全行快照；元数据及拒绝读取之后逐表完全相等。

不调用simulate/enable/scheduler/真实广告写；不声称启用或正向暂停完成。元数据真实MySQL UNION/collation/CAST仍待主线串行专项，不由纯测推断。

## 受测依赖

工具依赖 `tools/fixture_login.py`、`tools/rule_simulation_access_checks.py`（仅guard）、`tools/metric_fact_schema_checks.py`、`tools/metric_profile_reference_checks.py`（及其query seed依赖）、`tools/rule_definition_checks.py`、`tools/rule_editor_checks.py`，以及原规则合同和新展示元数据合同/Store/路由。主线需将这些辅助源码纳入相应证据source清单。无额外迁移或生产配置要求。


## 前两轮真实失败记录与精确修正

主线第一轮6PASS/1FAIL/8未运行，停在夹具getInfo精确权限假设；metadata尚未执行。第二轮安全诊断明确status200、非空权限仅rules.read、结构空权限3项、未知权限0。原若依LoginService直接保留三层目录perms=''，不代表新增业务权限。工具修为所有权限项必须str、非空权限集合严格等于{rules.read}；只允许空字符串目录项，None/未知或任何额外动作均拒绝。生产getInfo、菜单与权限逻辑未改。两份父失败回执保留，新工具修正后实际15档仍待主线复验，不预记通过。


## 第五轮真实闭环结果

主线原15/15全部PASS，11.15秒，原Rule15/Page4、真实中文名称/原native创建人/UTC毫秒、跨租户与混不可见整404、仅read权限及即时撤销、原规则八表只读全行不变均实际通过。本结果覆盖前三节待实际MySQL说明；具名主线回执与BUSINESS_FLOW保留完整限定范围。

前四轮失败不改写：第一、二轮分别停在getInfo错误的精确空权限假设，安全诊断证明status200且仅rules.read和3个结构空字符串，工具随后仅允许这些空项；第三、四轮元数据首请求503，第四轮实证DBAPIError1271，属于UNION collation冲突，随后九投影显式同utf8mb4/utf8mb4_0900_as_cs修复。第五轮才实际通过。未调用simulate/enable，不把DRAFT暂停409负向当ENABLED暂停正向；后者由主线独立技术状态夹具负责，不在本8组通过范围。
