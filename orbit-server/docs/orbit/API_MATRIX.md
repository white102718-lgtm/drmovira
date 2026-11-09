# ORBIT 接口逐项开发/测试/验收

更新时间：2026-11-09T09:30:10+08:00。原合同127条路径、156个HTTP操作。

新增系统配置接口在实现时另列版本化扩展合同；不修改原产品合同，也不因原合同没写而免除测试。

| 编号与条目 | 开发 | 测试 | 验收 | 逻辑/证据/阻断 |
| --- | --- | --- | --- | --- |
| `API-CFG-listSystemConfigurations` GET /api/v1/system-configurations | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-CFG-createSystemConfiguration` POST /api/v1/system-configurations | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-CFG-getSystemConfigurationMetadata` GET /api/v1/system-configurations/metadata | [x] 已开发 | [x] 通过 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。仅此元数据接口开发/测试完成，整体模块与验收未完成。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md, docs/orbit/evidence/python-configuration-metadata.json, python/orbit_api/configuration_routes.py |
| `API-CFG-getSystemConfiguration` GET /api/v1/system-configurations/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-CFG-updateSystemConfiguration` PUT /api/v1/system-configurations/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-CFG-testSystemConfigurationReadOnly` POST /api/v1/system-configurations/{id}/test | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。Python只读探测已实现，四类平台传输fixture/并发安全与浏览器专项通过，完整外部验收未完成。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-CFG-listSystemConfigurationHistory` GET /api/v1/system-configurations/{id}/history | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python配置检查点详见PYTHON_CONFIGURATION.md；旧Java测试不继承。<br>证据：docs/orbit/PYTHON_CONFIGURATION.md |
| `API-TEAM-getTeamCapabilities` GET /api/v1/teams/capabilities | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-ROLE-getRoleCapabilities` GET /api/v1/roles/capabilities | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-USER-getUserCapabilities` GET /api/v1/users/capabilities | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 本租户人员新增/编辑及原角色分配的业务版本、撤销、回滚/并发专项和人员三视口已通过；原读取/导入/删除全矩阵、团队禁用会话、受控跨租户、邀请/OIDC及容量仍待完整验收。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/native_user_changes.py, python/orbit_api/user_create_store.py, python/orbit_api/user_update_store.py |
| `API-USER-getUserReferenceOptions` GET /api/v1/users/reference-options | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 本租户人员新增/编辑及原角色分配的业务版本、撤销、回滚/并发专项和人员三视口已通过；原读取/导入/删除全矩阵、团队禁用会话、受控跨租户、邀请/OIDC及容量仍待完整验收。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/native_user_changes.py, python/orbit_api/user_create_store.py, python/orbit_api/user_update_store.py |
| `API-listChannel` GET /api/v1/channels | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createChannel` POST /api/v1/channels | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getChannel` GET /api/v1/channels/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateChannel` PUT /api/v1/channels/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listTemplate` GET /api/v1/templates | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createTemplate` POST /api/v1/templates | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getTemplate` GET /api/v1/templates/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateTemplate` PUT /api/v1/templates/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listRule` GET /api/v1/rules | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createRule` POST /api/v1/rules | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getRule` GET /api/v1/rules/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateRule` PUT /api/v1/rules/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listTag` GET /api/v1/tags | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createTag` POST /api/v1/tags | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getTag` GET /api/v1/tags/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateTag` PUT /api/v1/tags/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listCategory` GET /api/v1/categories | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createCategory` POST /api/v1/categories | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getCategory` GET /api/v1/categories/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateCategory` PUT /api/v1/categories/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-archiveTemplate` POST /api/v1/templates/{id}/archive | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-archiveRule` POST /api/v1/rules/{id}/archive | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-archiveTag` POST /api/v1/tags/{id}/archive | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-archiveCategory` POST /api/v1/categories/{id}/archive | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listAccounts` GET /api/v1/accounts | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAccount` GET /api/v1/accounts/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-assignAccount` PUT /api/v1/accounts/{id}/assignment | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-syncAccount` POST /api/v1/accounts/{id}/sync | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-unbindAccount` POST /api/v1/accounts/{id}/unbind | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAccountIdentities` GET /api/v1/accounts/{id}/identities | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createScopeSnapshot` POST /api/v1/scope-snapshots | [ ] 开发中 | [ ] 未运行 | [ ] 未运行 | 范围冻结页与成员弹窗已通过新增菜单接入，真实三视口覆盖冻结/游标前后页/搜索不改原集合/确认/清除/筛选变化失效；前端18项通过（含重试幂等、连点和取消迟到响应）。仍需完整账户列表跨页勾选、投手/户商名称选择器、server_scope跨租户正向授权及真实Meta目录，保持开发中/测试中/未验收。 当前范围菜单/动作按多个已分配且有效功能角色取并集；MySQL新增反例先复现403，再修复通过。真实非管理员登录证明权限合并不扩大USER数据范围，同Token角色停用/撤页立即403；仍非完整角色/跨租户/账户模块验收。 服务端操作租户目录前置已实现并复用于范围HTTP身份校验：SUPER读取系统内启用目标、其他角色仅当前租户；4项新真实MySQL预检通过，解析不创建业务快照。公开跨租户冻结/成员路由、home/target权限版本和actor+目标审计仍未完成，不增加整条完成或验收勾选。<br>内部home/target双版本前置校验新增3项MySQL测试，总89项通过。任一时钟变化、双上限及身份/角色/目标失效均已验证；未绑定公开快照/游标、目标事务及审计，跨租户业务仍未完成。<br>内部会话目标租户冻结、双版本绑定与锁顺序新增5项真实MySQL用例通过，总94项；重放/读取重新授权，旧快照不补版本，事务失败无残留。首轮record映射失败已修复并保留回执。公开跨租户HTTP、成员游标及actor+目标审计仍未实现，整项继续未验收。<br>内部会话目标成员分页及V2双版本游标新增6项MySQL专项通过，总100项；任一租户版本变化拒绝首/续页，游标绑定身份/角色/快照/筛选/页大小且与V1隔离。公开跨租户入口、actor+目标审计及前端目标选择仍待接入，整项继续未验收。<br>范围新冻结成功审计新增5项MySQL专项通过，总105项；记录actor/home/目标及双版本摘要，审计失败整笔回滚，幂等/并发仅一事件。测试已与运行中的预览端口/JAR隔离。公开跨租户入口、审计读取及全业务outbox仍待接入，不增加整项完成勾选。<br>受控公开跨租户范围POST及server_scope定位成员GET已接入；新增5项MySQL/2项真实HTTP用例通过，MySQL总110、应用7。保留V1/V2、双版本/CSRF/当前actor/菜单与原子审计。首轮容量连接超时保留，真实连接池复验全110通过。目标选择UI、审计读取和真实Meta未完成，整项不增加完成勾选。<br>用户最终确定RuoYi-FastAPI/Python+MySQL8+Redis，所有功能重新开发；此前Java证据仅历史核对，新架构尚未通过。 |
| `API-listPlans` GET /api/v1/launch-plans | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createPlan` POST /api/v1/launch-plans | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getPlan` GET /api/v1/launch-plans/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updatePlan` PUT /api/v1/launch-plans/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-allocationsPlan` POST /api/v1/launch-plans/{id}/allocations | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-campaignnamesPlan` POST /api/v1/launch-plans/{id}/campaign-names | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-validatePlan` POST /api/v1/launch-plans/{id}/validate | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-executePlan` POST /api/v1/launch-plans/{id}/execute | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAllocation` GET /api/v1/launch-plans/{id}/allocations/{allocation_id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-applyTemplate` POST /api/v1/templates/{id}/apply | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listTask` GET /api/v1/tasks | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getTask` GET /api/v1/tasks/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listOperation` GET /api/v1/operations | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getOperation` GET /api/v1/operations/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listSuggestion` GET /api/v1/suggestions | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getSuggestion` GET /api/v1/suggestions/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-editSuggestion` PATCH /api/v1/suggestions/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listAsset` GET /api/v1/assets | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAsset` GET /api/v1/assets/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateAsset` PUT /api/v1/assets/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listExport` GET /api/v1/exports | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createExport` POST /api/v1/exports | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getExport` GET /api/v1/exports/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listAlert` GET /api/v1/alerts | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAlert` GET /api/v1/alerts/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listImportBatch` GET /api/v1/account-imports | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getImportBatch` GET /api/v1/account-imports/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listReconcileCase` GET /api/v1/reconciliation-cases | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-openReconciliation` POST /api/v1/reconciliation-cases | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getReconcileCase` GET /api/v1/reconciliation-cases/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-cancelTask` POST /api/v1/tasks/{id}/cancel | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-retryTask` POST /api/v1/tasks/{id}/retry | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-taskEvents` GET /api/v1/tasks/{id}/events | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-simulateRule` POST /api/v1/rules/{id}/simulate | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-enableRule` POST /api/v1/rules/{id}/enable | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-pauseRule` POST /api/v1/rules/{id}/pause | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listRuleRuns` GET /api/v1/rules/{id}/runs | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-ignoreSuggestion` POST /api/v1/suggestions/{id}/ignore | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-previewOptimization` POST /api/v1/optimization-batches/preview | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-executeOptimization` POST /api/v1/optimization-batches/execute | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-queryMetrics` POST /api/v1/metrics/query | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-queryChannelReport` POST /api/v1/reports/channels/query | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-queryOperatorReport` POST /api/v1/reports/operators/query | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-queryLaunchStats` POST /api/v1/launch-stats/query | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAdoptionStats` GET /api/v1/adoption-stats | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createUpload` POST /api/v1/assets/upload-sessions | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-completeUpload` POST /api/v1/assets/upload-sessions/{id}/complete | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-bulkDeleteAssets` POST /api/v1/assets/bulk-delete | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-retryAccountImport` POST /api/v1/account-imports/{id}/retry | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-downloadExport` GET /api/v1/exports/{id}/download | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-ackAlert` POST /api/v1/alerts/{id}/ack | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-snoozeAlert` POST /api/v1/alerts/{id}/snooze | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-claimReconciliation` POST /api/v1/reconciliation-cases/{id}/claim | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-approveReconciliation` POST /api/v1/reconciliation-cases/{id}/decision | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listUser` GET /api/v1/users | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python团队/角色/人员基础读写及原目录桥接已有专项；原本人资料与完整编辑补齐空邮箱/控制字符拒绝、规范化和无操作，真实无部门Excel可导出。六页18项浏览器复验通过，业务邮箱必填/昵称可空。原引用/并发/删除导入、一次性邀请/OIDC及真实容量仍未完成，不计模块通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/user_routes.py, python/orbit_api/user_store.py |
| `API-createUser` POST /api/v1/users | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 本租户人员新增/编辑及原角色分配的业务版本、撤销、回滚/并发专项和人员三视口已通过；原读取/导入/删除全矩阵、团队禁用会话、受控跨租户、邀请/OIDC及容量仍待完整验收。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/native_user_changes.py, python/orbit_api/user_create_store.py, python/orbit_api/user_update_store.py |
| `API-getUser` GET /api/v1/users/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | Python团队/角色/人员基础读写及原目录桥接已有专项；原本人资料与完整编辑补齐空邮箱/控制字符拒绝、规范化和无操作，真实无部门Excel可导出。六页18项浏览器复验通过，业务邮箱必填/昵称可空。原引用/并发/删除导入、一次性邀请/OIDC及真实容量仍未完成，不计模块通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/user_routes.py, python/orbit_api/user_store.py |
| `API-updateUser` PUT /api/v1/users/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 本租户人员新增/编辑及原角色分配的业务版本、撤销、回滚/并发专项和人员三视口已通过；原读取/导入/删除全矩阵、团队禁用会话、受控跨租户、邀请/OIDC及容量仍待完整验收。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/native_user_changes.py, python/orbit_api/user_create_store.py, python/orbit_api/user_update_store.py |
| `API-listTeam` GET /api/v1/teams | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-createTeam` POST /api/v1/teams | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-getTeam` GET /api/v1/teams/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-updateTeam` PUT /api/v1/teams/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-listRole` GET /api/v1/roles | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-createRole` POST /api/v1/roles | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-getRole` GET /api/v1/roles/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-updateRole` PUT /api/v1/roles/{id} | [ ] 开发中 | [ ] 测试中 | [ ] 未运行 | 真实Python团队/角色本租户HTTP、独立菜单动作并集、CSRF、幂等/CAS、审计/outbox回滚及三视口页面专项已建立；跨租户、人员桥接、完整权限和容量尚未完成，不计API整体通过。<br>证据：docs/orbit/PYTHON_IDENTITY.md, python/orbit_api/role_store.py, python/orbit_api/team_routes.py, python/orbit_api/team_store.py |
| `API-listDictionaryItem` GET /api/v1/dictionaries/items | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createDictionaryItem` POST /api/v1/dictionaries/items | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getDictionaryItem` GET /api/v1/dictionaries/items/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateDictionaryItem` PUT /api/v1/dictionaries/items/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-inviteUser` POST /api/v1/users/{id}/invitation | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getSession` GET /api/v1/auth/session | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-logout` DELETE /api/v1/auth/session | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-startOIDC` POST /api/v1/auth/authorization-sessions | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-oidcCallback` GET /api/v1/auth/callback | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-startMetaOAuth` POST /api/v1/integrations/meta/authorization-sessions | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-metaCallback` GET /api/v1/integrations/meta/callback | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listIntegrations` GET /api/v1/integrations | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-revokeIntegration` POST /api/v1/integrations/{id}/revoke | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listCapabilities` GET /api/v1/capabilities | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listMetricProfiles` GET /api/v1/metric-profiles | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listTimezones` GET /api/v1/dictionaries/timezones | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-dictionaryOptions` GET /api/v1/dictionaries/options | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listAgent` GET /api/v1/execution-agents | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createAgent` POST /api/v1/execution-agents | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAgent` GET /api/v1/execution-agents/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateAgent` PUT /api/v1/execution-agents/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-revokeAgent` POST /api/v1/execution-agents/{id}/revoke | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-probeAgent` POST /api/v1/execution-agents/{id}/probe | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listAgentProfiles` GET /api/v1/execution-agents/{id}/profiles | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-agentHeartbeat` POST /api/v1/agent-api/heartbeats | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-auditEvents` GET /api/v1/audit-events | [ ] 开发中 | [ ] 未运行 | [ ] 未运行 | <br>补齐审计查询参数解析器并让内部分页复用同一字段规则：未知/身份注入字段400，重复或缺失参数400，不支持status/channel/profile/entity筛选422；验证页大小、游标长度、Unicode文本、历史操作者UUID和UTC日期，查询对象toString脱敏。新增7项单测及原OpenAPI参数清单核对通过，默认Java280、MySQL126、应用7、浏览器6、网络6和台账12通过。尚未接通公开审计控制器、跨租户合并及AuditPage旧未知字段适配，不是接口或页面验收，无整项新增完成勾选。<br>公开GET /api/v1/audit-events与新增审计菜单页已接通范围冻结事件：跨当前授权租户稳定合并、九字段详情、筛选与20/50/100/200分页；全部目标版本绑定游标，未知历史必填身份显式503而不伪造或隐藏。新增MySQL9/真实HTTP3/浏览器3项通过，总Java280、MySQL135、完整应用10、浏览器9、网络6、前端21、台账12；保留三次失败回执。其他事件源、历史身份补证及完整SYS08仍待完成，不增加整项完成或验收勾选。<br>用户最终确定RuoYi-FastAPI/Python+MySQL8+Redis，所有功能重新开发；此前Java证据仅历史核对，新架构尚未通过。 |
| `API-setKillSwitch` POST /api/v1/kill-switches | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-approveKillSwitchRelease` POST /api/v1/kill-switches/{id}/release-approval | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-proposeAttributionCorrection` POST /api/v1/attribution-corrections | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-approveAttributionCorrection` POST /api/v1/attribution-corrections/{id}/decision | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-scopeSnapshotMembers` GET /api/v1/scope-snapshots/{id}/members | [ ] 开发中 | [ ] 未运行 | [ ] 未运行 | 范围冻结页与成员弹窗已通过新增菜单接入，真实三视口覆盖冻结/游标前后页/搜索不改原集合/确认/清除/筛选变化失效；前端18项通过（含重试幂等、连点和取消迟到响应）。仍需完整账户列表跨页勾选、投手/户商名称选择器、server_scope跨租户正向授权及真实Meta目录，保持开发中/测试中/未验收。 当前范围菜单/动作按多个已分配且有效功能角色取并集；MySQL新增反例先复现403，再修复通过。真实非管理员登录证明权限合并不扩大USER数据范围，同Token角色停用/撤页立即403；仍非完整角色/跨租户/账户模块验收。 服务端操作租户目录前置已实现并复用于范围HTTP身份校验：SUPER读取系统内启用目标、其他角色仅当前租户；4项新真实MySQL预检通过，解析不创建业务快照。公开跨租户冻结/成员路由、home/target权限版本和actor+目标审计仍未完成，不增加整条完成或验收勾选。<br>内部home/target双版本前置校验新增3项MySQL测试，总89项通过。任一时钟变化、双上限及身份/角色/目标失效均已验证；未绑定公开快照/游标、目标事务及审计，跨租户业务仍未完成。<br>内部会话目标租户冻结、双版本绑定与锁顺序新增5项真实MySQL用例通过，总94项；重放/读取重新授权，旧快照不补版本，事务失败无残留。首轮record映射失败已修复并保留回执。公开跨租户HTTP、成员游标及actor+目标审计仍未实现，整项继续未验收。<br>内部会话目标成员分页及V2双版本游标新增6项MySQL专项通过，总100项；任一租户版本变化拒绝首/续页，游标绑定身份/角色/快照/筛选/页大小且与V1隔离。公开跨租户入口、actor+目标审计及前端目标选择仍待接入，整项继续未验收。<br>范围新冻结成功审计新增5项MySQL专项通过，总105项；记录actor/home/目标及双版本摘要，审计失败整笔回滚，幂等/并发仅一事件。测试已与运行中的预览端口/JAR隔离。公开跨租户入口、审计读取及全业务outbox仍待接入，不增加整项完成勾选。<br>受控公开跨租户范围POST及server_scope定位成员GET已接入；新增5项MySQL/2项真实HTTP用例通过，MySQL总110、应用7。保留V1/V2、双版本/CSRF/当前actor/菜单与原子审计。首轮容量连接超时保留，真实连接池复验全110通过。目标选择UI、审计读取和真实Meta未完成，整项不增加完成勾选。<br>用户最终确定RuoYi-FastAPI/Python+MySQL8+Redis，所有功能重新开发；此前Java证据仅历史核对，新架构尚未通过。 |
| `API-listTaskNodes` GET /api/v1/tasks/{id}/nodes | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listRuleHits` GET /api/v1/rule-hits | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getRuleHit` GET /api/v1/rule-hits/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getSuggestionEvidence` GET /api/v1/suggestions/{id}/evidence | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-previewManualOperation` POST /api/v1/manual-operations/preview | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-executeManualOperation` POST /api/v1/manual-operations/execute | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-assignChannelOwners` PUT /api/v1/channels/{id}/owners | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-archiveChannel` POST /api/v1/channels/{id}/archive | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-shareTemplate` POST /api/v1/templates/{id}/share | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getEntity` GET /api/v1/entities/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listEntities` GET /api/v1/entities | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listProfileBindings` GET /api/v1/profile-bindings | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createProfileBinding` POST /api/v1/profile-bindings | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getProfileBinding` GET /api/v1/profile-bindings/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-updateProfileBinding` PUT /api/v1/profile-bindings/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-listEnvironmentCapabilities` GET /api/v1/environment-capabilities | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-nextAgentLease` GET /api/v1/agent-api/leases/next | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-renewAgentLease` POST /api/v1/agent-api/leases/{id}/renew | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getAgentCommand` GET /api/v1/agent-api/leases/{id}/command | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-reportAgentEvents` POST /api/v1/agent-api/events | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-createAgentEvidenceUpload` POST /api/v1/agent-api/evidence-upload-sessions | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-resumeAfterHumanIntervention` POST /api/v1/tasks/{id}/resume | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-getExecutionManifest` GET /api/v1/agent-api/leases/{id}/manifest | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-downloadFrozenExecutionAsset` GET /api/v1/agent-api/leases/{id}/assets/{asset_id}/download | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-orbitListReferences` GET /api/v1/reference-catalogs/{kind} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-orbitPreviewReferenceImport` POST /api/v1/reference-catalog-imports | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-orbitGetReferenceImport` GET /api/v1/reference-catalog-imports/{id} | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
| `API-orbitCommitReferenceImport` POST /api/v1/reference-catalog-imports/{id}/commit | [ ] 未开发 | [ ] 未运行 | [ ] 未运行 |  |
