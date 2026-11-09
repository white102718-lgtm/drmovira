# PY06 A025账户范围消费闭环

## 合同与输入/持久化

原WORKFLOWS125允许`account_scope_snapshot_id`与空`account_ids`表示真正跨页冻结集合；两者不可同时非空。范围最大50000，计划1..500且单投手/团队/租户/币种，超过422 PLAN_ACCOUNT_LIMIT，不得截断；普通列表cursor不是范围ID。

本节点复用已真实验收的`AccountScopeStore.resolve_for_plan(session,current,snapshot_id,owner_user_id=...,owner_team_id=...)`，不直读表代替权限解析。该helper以当前actor/tenant、真实auth_version和显式管理团队fingerprint校验原创建者、全体成员可读性与owner/team/currency冻结值，不因普通name/revision变化自动改写选择。真实目标owner的accounts.read仍由原launch引用交集逻辑另外复核，SUPER调用者不能替代实际owner读权。

原请求先按规范JSON固定幂等hash（保留原scope ID），再deepcopy工作副本。消费到实际IDs后再次做展开层/广告10000上限，规范配置也再次受5MiB保护；原输入不变，数据库死锁重试不复用已消费的可变value。不同snapshot即使成员相同，也不是同一原幂等意图。

工作副本写入真实有序账户IDs，已消费`account_scope_snapshot_id=null`，GET后的原PlanWrite可直接编辑，不产生“非空scope+IDs”自相矛盾。原scope_id/members_hash/auth_fingerprint/scope_version/实际IDs hash/count保存于不可变plan_version.dependency_json.account_scope_snapshot，元数据只在resolver已授权并持共享锁后按同tenant/actor/ready/id精确读取；不把权限指纹当执行许可。

无scope的空来源草稿不调用resolver、不新增accounts权限；显式IDs仍走旧来源权限路径。未接真实身份/profile/metric能力时仍503，不因范围成功就签发validate/execute成功。普通改名保留冻结成员显示，保存计划引用当前真实账户版本；后续账户归属、币种、解绑与双方权限变化全部实时拒绝整批。

## 源码与界限

修改仅`launch_references.py`、获批最小`LaunchStore.save`配合；原D1工具仅把不存在scope UUID过时的503改为真实404，保留结构/未知字段覆盖。新`test_launch_scope_consumption.py`、`tools/launch_scope_consumption_checks.py`。不改前端、公共app、A025 store、命名、角色桥接、迁移或主runner，不运行共享服务/真实广告。

## 检验入口

13项新增纯测PASS，覆盖原helper调用、provenance、空来源不扩权限、互斥、403/404/409不改原请求、0/501不截断、消费后展开上限、元数据数量错配、原意图重试/同IDs不同snapshot、最终5MiB保护。相关原合同/命名/边界110项检查点通过后新增最终大小保护，最新最终组合回执以主线/本轮记录为准；纯测不等于真实SQL。

真实专项签名`run_launch_scope_consumption_checks(client, admin, headers, fixture, cases)`，固定`LAUNCH_SCOPE_CONSUMPTION_CASES`10组。需原人员fixture与迁移001—025，不依赖真实平台/Token，不新增公共入口。仅允许`orbit_py_it_[a-f0-9]{32}`孤立库。

冻结送验时的10组固定清单（最新实测结果见文末）：
1. 原HTTP消费2IDs落库/版本依赖/GET原body继续编辑；
2. 原键重放与不同snapshot/显式同IDs意图冲突；
3. 500成功、501拒绝、消费后12000展开拒绝及互斥；
4. 账户普通改名不改冻结成员、计划引用当前revision；
5. owner/team/currency/解绑漂移及预算币种不一致原子拒绝；
6. 实际外租户/其他创建者scope、随机不存在scope及成员列表cursor拒绝；
7. 即时accounts/launch.create撤销阻断成功原键，无scope空草稿不扩大读取依赖；
8. audit故障全回滚、原键恢复，profile身份未知仍503；
9. 测试专属MEMORY计数夹具首个事件发真实MySQL1213，外层transaction重试原scope请求，最终只有1版本且后续原键可重放；
10. 真实目标owner去掉功能角色后，SUPER caller不能代替其accounts.read；角色与账户归属finally完整恢复。

所有临时trigger/Memory表均测试专属并清理；账户SQL仅创建无平台副作用的fixture，plan动作走真实HTTP。送验阶段未执行时不记PASS；本清单的最新实际执行结果见文末，不把有工具当真实通过。

冻结前最终定向组合：新增13 + 原launch_contract_expansion / launch_store_boundaries / launch_naming共111项PASS（0.88秒），全部本节点源码/工具Ruff PASS。该111是纯单元/边界组合，不是10组真实HTTP回执。

## 最新真实SQL/HTTP验收证据

主线`python-launch-scope-consumption-http.json`：through030共102/102实际PASS（84.77秒），原B92+本节点10全部具名通过。实际覆盖消费/原schema回编、幂等意图区别、500/501与展开超限、改名/归属币种解绑漂移、跨租户/创建者/普通cursor、当前双方读权和动作撤销、审计原子回滚、真实MySQL1213重试原请求与最终5MiB纯边界。原命名/模板等断言未删减。主线另复验定向纯测111/111 PASS（0.88秒）。

该证据只结清内部计划范围消费后台节点；不是新范围选择UI、真实平台账户授权、能力预检、任务执行或整投放模块验收。既有投放浏览器三视口PASS发生在本节点之前，仅按其原有范围引用，不将后台新消费等同新增浏览器通过。production源码冻结交主线提交。
