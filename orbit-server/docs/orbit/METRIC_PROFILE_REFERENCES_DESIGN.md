# 原PlanWrite指标引用冻结

本阶段新增 `metric_profile_references.py`，只实现真实目录依赖读取/冻结接口；原公共LaunchStore/Template/Naming入口由主线统一接入。此前query真实26/26和指标三视口9/9已通过；本阶段references只有纯测，未连接数据库，不继承旧证据为新业务验收。

## 原合同与接口

原PlanWrite仅在campaigns/adsets内提供可空`metric_profile_id` UUID，没有profile version或adapter映射字段。`collect_metric_profile_ids(campaigns)`从该原字段收集并去重排序，沿原MAX_NODES预算，不新增前端字段或500等自造profile数量上限。

`resolve_metric_profile_dependencies(session,current,owner_actor,ownership,profile_ids,*,permission,isolated_fixture=False)`由外层真实写事务调用，permission必须显式为launch.create、launch.edit、templates.create或templates.edit。四个原动作均注册在launch菜单，逐项原样核验，不用模板动作推导或叠加计划动作。函数重验当前caller原动作、BusinessContext完全一致，并核目标owner当前原生用户、identity、scope、租户、业务用户/团队启用且非invited，实际subject/team与原ownership一致。owner_actor须来自服务端已有归属核验，不接受前端原生ID。目标不额外要求launch.read/monitor.read，caller也不增加这些读动作。

函数不代替原`launch_access.owner`对当前操作人可变更归属的范围规则。空引用正常返回`{metric_profiles:{}}`且不查来源/菜单；显式隔离开关仍先guard，不能用空集合绕过fixture生产保护。所有非空引用完整通过后才返回，缺失/撤销/跨租户不能部分成功。

## 全局锁顺序

1. 无锁预读当前ENABLED head→明确current_version的source/config元数据，仅定位来源。即使调用者事务有旧RR快照也不能把此数据直接当最终版本。
2. META配置ID去重、全局UUID排序，200批`FOR SHARE`；来源必须当前META_BM、enabled、精确source_config_revision。不可用409。
3. tenant metric clock共享锁，读取SQL UTC_TIMESTAMP(3)作为统一验证时刻。
4. profile UUID排序分200批，用head PRIMARY驱动、STRAIGHT_JOIN版本PRIMARY，FOR SHARE最终读取；不JOIN configuration，避免变化来源在clock后被隐式补锁。current_version/source/config pair与预读不同立即409，绝不在clock后尝试锁新来源。
5. 最终原profile通过复用`validated_public_profile`的schema、规范hash、严格proof/source独立列和MySQL毫秒观察值/非未来验证。未知坏行503，不吞掉。之后调用方才获取launch clock/head CAS。

200是有界SQL批次，不是原业务字段最大数。全局顺序跨批保持；500纯测验证200/200/100分批不等于真实容量或EXPLAIN证明。新helper不创建事务/commit、不执行I/O来源探测、不写Plan或幂等记录。

## 返回与来源冻结

返回`metric_profiles`以profile UUID为key，值为version（原字符串）、head_revision、profile_hash、source_sha256、source_config_id、source_config_revision；另有捕获时metric_profile_clock。无adapter_version、AttributionSpec、latest或默认v1。原不可变040版本保留完整profile与proof，调用者将这些精确依赖放入既有PlanVersion.dependency_json即可，不需扩展原响应或新增SQL。

metric_profile_clock是捕获水位，计划“资料变更”指纹宜比较metric_profiles真实依赖，避免无关目录变化单独制造配置新版本；最终由主线Store实现决定并验收。执行另用已冻结明确version/hash及Plan实际adapter_version调用lock_exact，不能再次选择新的activehead或latest adapter。

正式isolated_fixture默认False，FIXTURE行不可用；显式True从开始验证真实127.0.0.1:13306/UUID库。TRUSTED行仍需040已发布来源及当前配置/证明真实一致；本阶段不建立Meta Authority、不把该字符串当外部已连接或写授权。

## 主线接入待办与验收

- validate_sources需传真实create/edit动作，先解析指标来源再锁业务来源clock及launch head；模板、复制、命名重绑按各自原动作合同审查，不能默认edit。
- 保存新键且payload相同、active profile实际依赖变化时，旧Store单靠payload提前返回会丢弃新依赖；主线需按原plan CAS创建真实新配置版本。原键重放保留原已提交依赖，不重绑当前head，仍应复核当前权限及该旧版本可用性。
- 新module不改冻结Store/query/040/041、公共launch_references、模板或命名入口。
- 真实SQL需覆盖META配置有序锁/换来源409无反锁、重复profile去重、create/edit不额外read、目标身份停用/跨租户、坏proof/observed、资料换版新PlanVersion/旧键来源不复活、1644全回滚；主线排队执行后才记录业务测试完成。


## 模板原动作与成功重放语义修订

按原API_SEMANTICS.md接口约定，成功key先匹配原结果，再判新业务/If-Match；同key异payload仍409。helper没有幂等key接口，调用方在成功重放路径不得调用它。旧保存响应只是读，不创建新执行；当前profile停用/换head不改变原成功结果。仍需原会话有效和当前Plan/Template读范围，不能直接凭幂等行泄露旧响应。Template apply成功重放还需目标Plan当前可见性，不重新解析模板当前资料或重新应用。

模板save原create/edit动作现获精确支持：只调用require_business_access(session, actor, 'launch', 原templates.create/edit)，不增加launch.create/edit/read或monitor.read。templates.share/archive/read没有加入helper；仅共享/归档不能因此新要求模板编辑/计划创建动作。apply产生新Plan时沿原launch.create，源模板read由原Store自身负责。

只读核对021及TemplateStore：当前模板head只有config_json/hash/bytes，模板version只有value_json及创建信息，均没有独立dependency_json。TemplateStore.save仅保存campaign UUID引用，现版本快照不保留metric版本/hash/来源依赖；不能把现有value_json当已含这类证明。

推荐主线最小追加迁移：在orbit_launch_template和orbit_launch_template_version各增加可空dependency_json JSON列（中文COMMENT说明精确来源冻结/历史未知）；不要DEFAULT '{}'或把旧NULL回填成“已核验空依赖”。head用于有界当前比较，version保存真实逐版依赖；新create/edit同事务写两列。成功旧key仍先原结果，不能因新列NULL或当前资料变化失败。share/archive新版本可沿用原dependency（含历史NULL）而不重新调用create/edit helper；新apply必须按原动作重新核验当前资料，冻结到新PlanVersion，不把历史NULL解释为执行许可。021没有找到模板version更新/删除禁止触发器，主线可同时评估追加整行只追加guard，避免新依赖被历史改写；本阶段没有修改DDL或Store。

是否需要新模板配置版本，由主线比较真实metric_profiles内容决定；metric_profile_clock仅捕获水位不计无关目录噪声。此迁移/公共接线仍待主线分配和真实SQL验收，当前权限扩展纯测只证明helper原样传递动作及失败关闭。
