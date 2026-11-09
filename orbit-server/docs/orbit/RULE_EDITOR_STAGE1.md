# R1规则编辑辅助第一阶段

仅新增技术扩展GET：`/api/v1/rules/edit-context`、`/api/v1/rules/editor-options`。原Rule11写入/15响应、原MetricProfile12字段不变，无scope创建/选择引擎、模拟/启用成功、调度或平台写入。主线负责将`rule_editor_routes.router`先于原动态`/{rule_id}`注册，配置`RULE_EDITOR_CURSOR_V1`签名用途与隔离runner；本阶段不改公共auth/app/credentials/迁移。

## 已冻结HTTP形状

context query严格`action=CREATE|UPDATE`；CREATE禁止rule_id，UPDATE必须规范rule_id。response精确八字段：action、rule_id(null/UUID)、rule_revision(null/正整数)、editable(bool)、csrf_token、default_ownership原双UUID、selected_owner、selected_profile。

selected_owner为`{item:null|{id,team_id,name,team_name},can_keep:bool}`，标签来自真实业务用户/原生昵称/用户名及团队名称，仅返回此关联最小信息，不暴露人员目录、邮箱或系统角色。CREATE默认实际本人；UPDATE由当前可见规则原归属获取。当前owner不存在/停用/团队已变时can_keep=false，不猜新团队合法归属。可见旧owner不代表可任意新指派；新候选仅USER本人、TEAM本人或显式managed目标、SUPER同tenant有效用户，均排除邀请、停用/删除/无效scope/team。

selected_profile在CREATE为null；UPDATE为`{id,bound_version,current:null|原MetricProfile12,status:CURRENT|CHANGED|UNAVAILABLE}`。bound_version来自当前规则版本的冻结依赖；current仅真实当前启用head和合法来源。旧head不存在/停用或owner不可用显示UNAVAILABLE，不擅自重绑旧规则；当前可用字符串version改变则CHANGED。原MetricProfile没有name，UI应组合version/source/windows显示，不能新增持久name或要求用户手输UUID。

options query严格`{action,rule_id?,kind:OWNER|PROFILE,owner_user_id?,owner_team_id?,q?,page_size?,cursor?}`。OWNER禁止ownerpair，q为真实label字面前缀、转义LIKE通配符；PROFILE必须ownerpair，非空q仅exactUUID，不把版本文本猜成搜索语义。四档20/50/100/200，cursor长度1..2048。response严格`{items,next_cursor,data_as_of,scope_version}`；OWNER item为四字段，PROFILE item直接原12字段。GET拒正文、重复/未知query以及X-Target-Tenant。

## 授权、来源与事务

每条入口独立使用rules.create或rules.edit；不借rules.read、accounts.read、system.users或monitor.read。UPDATE必须当前规则对象可见，原ENABLED/ARCHIVED可展示引用但editable=false不授PUT。原规则写入仍自行严格校当前动作、原If-Match/幂等和所有依赖，候选不是永久许可。

共享复用点为现`authorize_rule/revalidate_access/owner_scope/revalidate_owner`、`assert_write_ownership`、公开纯`RuleStore.public`（原11字段hash和head投影）、公开`validated_public_profile`（严格原12字段、来源proof/独立列/SQL UTC、MySQL毫秒round含秒进位）。不调用强制rules.read的RuleStore.get、不借私有_row、不复制原Store写逻辑、不调用monitor目录接口。

调用顺序：当前caller/owner身份与managed当前锁；UPDATE普通probe只定位当前引用；目录clock共享水位；PROFILE集合probe定位来源→config全局UUID当前共享锁→metricclock/SQL UTC→集合head/version当前共享锁；最后ruleclock→当前head/version锁核revision/完整payload/hash/归属与probe一致，再以该锁定previous完成指派复核。新PROFILE选择先用当前新指派门禁拒绝无权owner，不能先读profile再由错误差异泄露。保留原owner由context独立展示，最终保存由原Store判断，不把context当新指派授权。

最终profile校验使用前置已锁的config投影，不在metricclock之后依赖RR旧一致读的配置JOIN。原proof微秒不改写，独立observed_at按既有MySQL毫秒归一并与实际SQL UTC比较。source/head漂移409，坏hash/proof/verified=false或未初始化503，整页拒绝不逐条catch跳过。当前enabled head引用已停用/变版配置也明确409，不能伪空成功；完全无启用head可返回真实空页。context无选中head返回UNAVAILABLE；存在但坏来源仍503/409，不掩盖损坏。

只有可信`app.state.rule_editor_fixture`显式bool才允许FIXTURE；默认False，True每次（含空context/页）仍检查真实13306/UUID边界。FIXTURE及技术SQL META形状都不证明真实Meta发布/投放能力。普通HTTP没有切换此state/指定配置路径或来源的参数。

游标独立MACpurpose，绑定domain、session/actor/tenant、caller完整auth/managed、action/kind/rule_id及当前revision、目标owner及完整auth/managed、filter/page_size、目录水位和对应metric/owner水位。每页重新授权和当前来源复验；篡改/跨会话/字段切换拒绝，水位变化409，不把游标当幂等或永久范围。

## 验证范围

原九API/16真实证据继续独立。新`RULE_EDITOR_CASES`八组仅由主线串行实际运行：真正非root仅create/edit的context且其他菜单403；USER与TEAM显式managed及SUPER的真实标签候选；21+严格profile/原12字段/keyset；session/kind/filter/size/clock游标失效；UPDATE保留有效旧owner和冻结/当前版本差异；停用headUNAVAILABLE与技术坏proof整页503；当前动作撤回/外规则404；GET边界和八张业务表零写。

纯测使用真实公共profile校验/SQLAlchemy RowMapping和内存会话替身，覆盖SQL源锁次序、坏页拒绝、微秒边界、旧RR配置、精确动作、无权owner先拒、空fixture边界、当前锁定previous、cursor绑定。尚无真实MySQL/HTTP或前端验收；不把这些纯测当候选业务验收。账户候选、scope冻结/完整成员读取仍为明确下一阶段，前端暂不能据本阶段声称Rule完整编辑已交付。

本轮定向纯测47/47 PASS（0.90秒）：编辑合同/Store40项、工具护栏7项。Ruff与格式检查通过。source与工具冻结供主线原22+新8真实专项；该计划尚未执行，不能提前记PASS。
