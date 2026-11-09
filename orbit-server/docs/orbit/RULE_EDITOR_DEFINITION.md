# 规则编辑定义技术读取

当前原definition源码已由主线完成through061实际55/55（48原档+7新增）通过，证据`evidence/python-rule-edit-definition061-http.json`；原首次父档亦保留。当前仅工具新增062规则页面导航断言待真实重验，不将旧55证据继承为新导航已通过。原Context8、Rule15、Scope5、原六动作及所有已通过061消费不改。

GET `/api/v1/rules/{rule_id}/edit-definition` 仅要求当前 `rules.edit` 和原规则对象可见性。无查询/正文、不接受指定租户。router为 `orbit_api.rule_editor_definition_routes.router`，主线注册；不需要新DDL、MAC用途、fixture开关或凭据。严格两键：

```
{rule: 原Rule15,
 stored_scope: {id: rule.scope_snapshot_id,
                count: 该Rule当前版本已sealed manifest.member_count,
                owner_user_id: rule.ownership.owner_user_id,
                owner_team_id: rule.ownership.owner_team_id}}
```

stored_scope是历史定义元数据，不是Scope5（不伪造hash/scope_version/created_at），不是私有快照成员读取权，也不宣称完整当前账户交集已核验。count必须为实际非NULL整数1..50000；未知不能补0。owner取当前Rule，manifest首次冻结owner只作内部历史审计。ACCOUNT/RULE两种源均可读已绑定manifest，不要求原creator。

调用方应将本响应Rule.revision和独立Context的rule_revision对账；两次请求之间有真实修改则重新读取，不能拼接不同版本或用本接口证明Context仍可编辑。ARCHIVED等状态可加载旧定义，不因此授予保存/启用资格。

单外层事务：当前rules.edit/范围→rule clock FOR SHARE→head FOR SHARE→精确不可变version FOR SHARE→同tenant/同Rule/当前manifest FOR SHARE→原Rule严格serializer与独立投影核验→末段同动作/同事务授权重验。缺版本/manifest、payload根与独立字段不一致、未sealed、sourceid不等原scope_snapshot_id、count/根/061生成映射损坏，均503 RULE_DEFINITION_UNAVAILABLE。foreign或跨tenant对象404，当前动作撤回403。

本端点不读profile head/来源、不扫描scope member，不要求accounts.read/system.users/monitor.read/rules.read；失效profile仍允许修正定义。成员全集当前授权由真正保存/模拟/执行各自原流程核验，不通过本元数据endpoint代替。仅四条有界业务查询（另原授权查询），无N+1。共享锁直到事务结束与原写方clock/heads顺序一致。

## 专属真实工具

`RULE_EDITOR_DEFINITION_CASES`七组，入口 `run_rule_editor_definition_checks(client,admin,headers,password,cache,database,cases)`。无额外kwargs；要求root原rules-only/editor through061正常隔离启动并明确fixtureprofile消费开关。只13306+127.0.0.1+本轮UUID+SELECT DATABASE一致。工具自行创建edit-only用户990614、managed协作者990615、真实原API范围和Rule。

1. edit-only加载原15+scope4、原read/accounts/users/monitor仍403，原八表全部行值不变。

   后续062兼容分支仅当sys_menu确有31047：真实getRouters递归核`orbit/rules/index`组件存在、getInfo permissions含rules.edit且无rules.read/全权限；不新增case、不替代原read403。through061没有该菜单时保持原七组兼容。
2. managed协作者可加载同Rule，私有原账户snapshot成员入口仍403；不新增creator限制。
3. DRAFT原API创建；ENABLED由独立SQL技术事件→版本→head→outbox原子构造，再实际原pause/archive API到PAUSED/ARCHIVED，定义均可读；profile停用仍可读。该ENABLED只证明历史读取，不证明正式模拟/enable成功或调度运行。
4. 合法SQL技术新版本转移当前Rule owner，保留首次manifest owner，返回当前ownership，完整原FK/trigger保持。
5. 同Token动作即时撤回403、不同owner/不存在对象404，恢复只为测试finally清理。
6. 独立SQL技术版本保持完整事件/FK/trigger链，分别payload hash坏、nullable数字、声明scope与manifest source不同；真实endpoint精确503且只读。无DROP/关闭guard，不冒充正常HTTP写可达或正式来源。
7. query/body/指定租户/非法UUID严格拒绝，最终正常读取，原八表原列/值全量对账不变（包括clock、revision、event、version、outbox）。

跨tenant隔离由绑定当前授权tenant SQL及纯可见性检查保证；真实工具的跨tenant请求头403与foreign owner404分别记录，不将不存在UUID假称第二租户真实对象验收。实际第二tenant已存Rule的404边界仍可由主线补专属fixture。

纯测试覆盖真实SQLAlchemy RowMapping、原serializer、八种状态/源组合、NULL/0/bool/超限拒绝、独立投影/根/生成列不一致、末段撤权；实际路由在隔离框架依赖下执行严格GET与单外层事务。纯适配合同不代替真实授权/SQL/HTTP验收。

## 已执行证据

through061真实MySQL、Redis与Python HTTP整档55/55通过，包含上述七组专属用例；最终回执为`evidence/python-rule-edit-definition061-http.json`。首轮业务断言通过但公共入口导入排序未通过，保留首轮回执，修正排序后完整重跑55组，未减少断言。当前渠道/元数据整档64/64另经真实复验，回执`evidence/python-reference-channel061-definition-policy.json`。这些是限定接口专项，不能替代编辑整页浏览器、真实第二租户已存规则边界或规则完整业务验收。
