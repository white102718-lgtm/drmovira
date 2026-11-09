# Rule指标发行头只读桥：窄交付

当前只有`rule_metric_publication_access.py`及专属纯测；不注册simulate、Metrics路由、issuer或Task，没有新迁移、事实读取、库存或READY发布。原publication与来源配置仍须由独立领域实际发行；provider默认None在任何SQL前503 `RULE_PUBLICATION_SOURCE_UNAVAILABLE`。kind标签/配置READ_VERIFIED/非空hash都不能代替独立证据。

## 已实现接口和实际来源

- `RuleMetricPublicationAccess(access_facade, calendar, authority=None)`：父必须是当前Rule授权facade和日历实例，不接monitor上下文，不增加monitor/accounts/launch动作。
- `await open(session, rule_ticket, calendar_summary) -> PublicationReadTicket`：先核默认来源门禁，再calendar.assert_summary和access.verified_profile(session,ticket,summary._parent_summary)。只有父真实EOF、精确发行对象及原同一实际SessionTransaction才可能读SQL。
- `await verify_heads(session, publication_ticket, publication_ids: tuple[UUID,...]) -> VerifiedPublicationBatch`：严格1..200、去重不能静默、规范UUID；内部实际SELECT完整原头，不允许调用者传头行/数字cutoff/完成布尔。
- `assert_batch(session,ticket,batch)`核发行实例与原真实对象身份；dataclasses.replace或跨session/事务不可复用。所有结果为深不可变tuple，没有可修改头dict冒来源证明。

主线新增的`RuleSimulationAccessFacade.verified_profile`返回原open已经取得并保存的不可变RuleProfileBinding，先核真实父summary，不重新SELECT当前配置、不换latest版本、不补锁。实际Rule ticket只有profile_version/profile_hash，profile_id来自已冻结rule_json；本reader对三者再核一致，不猜缺失source ID/rev。

**本窄阶段仅支持META且非空真实source_config_id/正安全source_config_revision。** 原FIXTURE桥只fixture_boundary而没有锁配置，不能称“已锁来源”；FIXTURE即便有authority也503。ISOLATED_TEST authority仍须13306/本轮UUID库guard，且profile同样必须是已锁META/非空source，不能以测试需要放开来源。专属纯测替换父profile lock返回实际类型META binding，仅验证内部接力协议，不证明真的锁过Meta配置或真实Meta发行。

## 锁序和cutoff

承接父既定auth/owner→精确profile source→metric clock/profile→account clock→Rule/完整成员→父EOF与calendar summary；到本模块时**不再读取/锁新的system configuration**。authority接口仅允许DB核验同一已锁来源的独立登记，不得在此首次补source锁或持锁网络。未来若生产authority还需另一source/登记域锁，必须先解决联合预锁接口，不能在本接口悄悄完成。

open按tenant+精确profile id/version/hash，取PUBLISHED generation最大头`LIMIT 1 FOR SHARE`。之后才核同exact source ID/rev，故坏的最新头不会因WHERE过滤而悄悄退回旧合法头。没有新生成或更新fact_clock。取得锚点generation/capture_sequence_max后固定，后续每个实际头都不得超过这两者；可读取更早头，不能将更早头ID替换成anchor。没有“最新事实/实体”选择逻辑，不能拿该cutoff声称已完成cell选择。

## 每头完整独立receipt

复用`metrics_query_store.publication_validation_binding`的23字段规范化：tenant/id/generation/profile id/version/hash/authority kind/source id/rev/source_proof_hash/state、expected/captured cell根/count/fact_count/capture_sequence_max/manifest根、publisher/request、oldest/created/published原UTC时间。额外严格核与真实Rule/已锁source绑定逐类型相等，计数/根/时间等保留原helper完整边界。

`RulePublicationAuthority.verify_publications(session,binding,heads)`为服务内ABC，返回tuple[PublicationValidationReceipt]；只收到最多200个只读头，必须从**独立已登记证据**实际核验，不能收到头后现算hash echo授信。reader比较receipt准确类型、完整23字段类型和值、ID全集、数量与不重复；拒绝遗漏坏头/部分成功、bool冒整数及自报hash。binding带真实Rule/manifest/member根、calendar根/共同evaluated_at、profile精确根/原profile proof hash和source ID/rev；它本身不是可外传的授权票据。

authorities尚无生产实现；本模块只约束输入输出，无法仅凭ABC保证某个未来实现真的独立验过来源。未来生产实现/工具注册必须单独审查来源登记和撤销路径。本纯测用提前登记tuple的明确纯替身，不注入生产、无来源网络。

## 受控验证和未做项

当前37项专属纯测使用真实父facade/calendar发行对象、SQLAlchemy RowMapping与AsyncSessionTransaction；底层authorize/SQL、原profile锁、独立receipt登记仍受控替身。覆盖：默认None零SQL、伪造父票据/summary/跨facade、META非空source限制、真实23字段tuple、两个cutoff/原source、最新坏头不退回、独立登记遗漏/重复/非tuple/字段与type不一致、请求0/201/重复/非tuple、实际200头有界读取、缺头、跨事务/replace拒绝。首轮31通过/1失败为专属test误读OrbitError.status_code（实际字段status），已保留first-failed日志，未改产品错误合同。

当前纯测结果37/37（1.62秒）证明协议；最终格式/静态复验由同轮专属日志记录。没有实际MySQL/HTTP/Meta或生产authority验收，没有50k容量结论。calendar_complete只指日历可解，UNRESOLVED summary不会被改为source complete；本模块不发行任何来源完整、EMPTY合法0、独立membership、coverage、Simulation READY或enable资格。

下一窄阶段应由主线排真实UUID SQL/原META配置和精确profile技术登记、独立receipt表：锚点与早头核验、坏源/撤销/漏头、200边界、source锁序和事务失效。事实cell/facts/父链及独立预期仍下一任务，未有源时继续503，不借旧monitor权限或工具ExpectedUnitProvider伪造Rule窗口来源。
