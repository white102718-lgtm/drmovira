# Rule模拟专属事实与独立预期桥提案

当前只读设计。Access实际原62+8共70/70（23.31秒）证明1001账户读取与事务能力，063候选70/70（22.85秒）证明约束技术形状，二者都没有发行指标来源或完成simulate。本文不修改MetricsQueryStore、RuleStore、facade、SQL或公共入口，不调用平台/DB。原44采样期间不运行重型测试。

## 1. 权限与输入：复用真实Rule票据，不造旧Context

桥只接新RuleSimulationAccessFacade发行的当前实际事务票据、同实例真实完整manifest summary及精确profile绑定，规则动作为原rules.read；不额外要求monitor.read/accounts.read/launch动作。不把public Rule payload/UUID/count或TRUSTED字符串当权限。不伪造MetricsReadContext、ExpectedUnitManifest的旧query/025 scope身份，也不调用旧monitor公开入口获得账户范围。

新计算与成功历史读取分开：本期facade沿原lock_rule_profile(expected原RuleVersion版本)检查当前head匹配，换head明确409内部限制，不能静默latest；历史receipt按原当前read与冻结范围读取，不调用新计算桥、不续期或改原bytes。未来支持旧精确profile新计算需主线单独裁决，不由桥猜测。

## 2. 来源锁序的先决裁决

现facade.open已经按profile源配置→metric clock/profile→account clock→Rule clock/head取得锁；后接来源authority若首次锁另一个配置，就可能与配置→clock写方形成反序。因此桥不得在account/Rule锁之后补第一次source锁。

主线优先采用联合前置，而非在现open后再拼接：先从Rule冻结精确profile_version的immutable版本行定位来源，再按固定cutoff预定位全部可能被选择的publication来源；source lock-plan包含profile来源与候选实际来源，按配置UUID全局固定顺序取得当前锁，复核后才进入metric/account/Rule。读取精确profile的不可变来源投影需明确新内部接口，不跨模块偷取facade私有状态或凭public DTO猜值。fixture仅在显式UUID guard下用独立技术登记证明，不能由生产空provider自动选择。

全部候选预定位必须有界：从Rule immutable manifest按账户keyset读取并依据当时账户窗口构造候选，或扫描同tenant/精确profile/cutoff的严格来源超集；预读的账户/时区/范围只用于定位，不授最终权限。若来源集合大，使用本轮受控staging表或有界有序来源流构造lock-plan，不在Python积攒全量publication/head。最终锁下重算实际窗口、每个被选cell及publication，必须证明其来源在原锁集合中且版本/证据一致；任何新source/发生变化直接409，不补锁、不继续部分结果。超集扫描成本与持锁规模必须实测，不称已有容量能力。source自身其他登记行/clock锁顺序也需与未来实际publisher统一核定，不能擅造一个顺序。

如先做单来源缩减实现，所有publication source必须与profile已锁source同id/revision、否则503，只能标内部支持限制，不代表所有来源支持或真实合同完整。

现lock_rule_profile的expected_version仅在最终current row处比较，初始probe若已换head可能先锁了新版本的config。建议主线给共享helper增加早期probe.current_version==expected检查，仍保留最终当前row复核；这不改变本期head匹配语义，只阻止错误新cfg进入来源锁阶段。由root单独修改共享helper，本proposal不改其代码。最终头若变则拒绝，不把新head的source悄悄加入已锁集合；历史receipt路径独立，不能借此增加重算/续期门禁。

## 3. 必要SQL字段与验证职责

### 当前Rule/账户与窗口

原RuleVersion精确rule_id/revision/payload_hash/manifest_id/metric_profile_id/metric_profile_version/metric_profile_hash/profile_proof_hash；原manifest完整member_count/member_ids_hash及sealed、同Rule/source_kind身份；新当前账户流给account_id、当前owner/team、真实currency/timezone。共同SQL UTC_TIMESTAMP(6)冻结evaluated_at，所有批次沿同一参考时刻使用rule_metric_windows.resolve_rule_metric_windows，按每账户IANA展开TODAY/YESTERDAY/LAST_3D/LAST_7D，不能用规则调度时区或统一上海业务日替代。

完整账户集合×对应日历窗口可由已授权范围和纯日期核心明确生成expected unit keys，不从返回cell数量推分母；最多50k×7日。缺时区无法生成对应业务日，明确不可计算/缺来源门禁，不造UTC或缺失日期MISSING行。NULL币种当前表NOTNULL，不造实际NULL样本；若未来可信输入允许NULL，Money条件保持UNKNOWN、不补USD或跨币合并。

### 048发行头（anchor和每个实际cell所属头都要核）

SELECT tenant_id,id,generation,profile_id,profile_version,profile_hash,authority_kind,source_config_id,source_config_revision,source_proof_json,state,expected_cell_count,expected_cells_hash,captured_cells_hash,cell_count,fact_count,capture_sequence_max,manifest_hash,publisher_actor_id,request_id,oldest_observed_at,created_at,published_at。

复用publication_validation_binding做完整结构/时间/根规范化，仍必须实际调用独立发行证据验证接口，不以state=PUBLISHED、kind=TRUSTED或hash存在推权威。验证返回的每个精确binding必须与所选原头逐字段、逐类型相等，数量/ID全集一致，不能遗漏坏头并继续部分数据。anchor冻结可用cutoff generation与capture_sequence_max；每个被选cell的实际publication可以更早，但须同tenant/profile精确version/hash、PUBLISHED、代际不超cutoff且逐头验证。不能把早批次id改成anchor.id。

### 048捕获单元

SELECT id,publication_id,account_id,account_snapshot_id,account_snapshot_kind,business_date,profile_id,profile_version,breakdown_key,capture_sequence,timezone_name,currency,owner_user_id,owner_team_id,attribution_version,expected_page_count,received_page_count,expected_entity_count,fact_count,empty_result,empty_field_mask,critical_complete,inventory_hash,source_hash,oldest_observed_at及tenant。

对于真实窗口unit key，在已授权账户及明确日期内、同profile/version/TOTAL、PUBLISHED代际cutoff约束下选capture_sequence最大的完整单元。先确定最大逻辑版本，再考虑墓碑/当前过滤；迟到110不能覆盖120，也不能因最新版本空/删或字段缺失退回旧值。现unique key及原SQL选择规则可参考，但桥不复制旧monitor scope过滤：必须同时核当前Rule双方账户范围和来源历史owner/team归属策略，不把当前可见自动当历史广告事实可见。

每个预期unit必须得到SELECTED或有独立声明的MISSING，后者不等合法0。必须核实际页数、原计数、完整关键字段mask及inventory/source根。完整cell的存在本身不证明每个metric字段有值；registrations等NULL继续传播。empty_result仅在独立entity roster/count=0、完整页面/根齐全且发行field mask明确该指标完整零时才可贡献0，否则未知。

### 048事实与实体/父链

逐选定cell按(cell_id,fact_id)有界keyset读取原AD事实，核tenant、account_id、account_snapshot_id、business_date、profile_id/version、breakdown_key、capture_sequence与cell一一对应；需要id、is_deleted、ad_id/adset_id/campaign_id、四级*_snapshot_id/*_snapshot_kind、channel_id/product_name_snapshot、parent_mapping_hash、asset/launch映射状态与根、spend/impressions/clicks/registrations/purchases/purchase_value、observed_at/fact_hash。

构建完整raw事实根时包含墓碑；原单元完整版本选择完成后，活动聚合才排is_deleted=1，不能先过滤墓碑再回退旧版本。若相应来源合同只提供整cell完整快照，就以该完整cell为原单位，不另创每广告跨cell“最新”规则。

实体维度读取tenant,id,account_id,entity_kind,entity_id,external_id,name,parent_snapshot_id,parent_kind,content_hash，逐级ACCOUNT→CAMPAIGN→ADSET→AD精确验证父映射，不仅验证叶子外键存在。目标CAMPAIGN/ADSET/AD的当前预期身份必须来自独立完整成员清单；同target UUID对应两个账户/币种或冲突父链拒绝，不用set去重掩盖冲突，也不生成假UUID填缺实体。

048已提供PUBLISHED头及子行追加/修改/删除拒绝、实体维度U/D拒绝；这些能支持持久引用后重读，但只有在完整成员/事实根、真实发行证明也验证后，才是可重建输入。相同来源UUID/count不等完整原始数值根。

## 4. 独立预期：现056不等Rule发行表

056只给原metric_query_snapshot添加expected_unit_hash/membership_hash/count/version及不可变更新guard。它不直接提供Rule专属独立来源，不应把任意SQL query头当预期issuer。现ExpectedUnitManifest还绑定旧统一date_from/date_to、query_hash、scope身份；Rule按账户业务日的多窗口不能造一个旧query后借用其票据。

新RuleExpectedManifest需绑定tenant/actor/当前subject-auth范围指纹、Rule/revision/manifest/member根、精确profile/version/hash/proof、evaluated_at、source anchor/cutoff、算法域/version、unit_count/root与独立target membership_count/root。membership必须独立于已返回facts：来源应证明完整平台/采集库存分页或原登记清单，缺采集页/未知实体全集时503，不能将实际facts COUNT或孤立entity_snapshot集合当预期。

每个unit的ExpectedUnitReceipt字段原则可复用（account/date/profile、历史归属/currency/timezone、账户快照、归因版本、entity_count/root），但必须新Rule授权绑定。目标membership明确account/date/entity_id/entity_snapshot_id/target_kind、name capture_sequence/observed，并在所有窗口日归并到全局canonical target UUID有序全集。跨日同实体只算一个scanned；其各unit贡献分别验证。合法完整空集合要独立根为0个实体，而不是查询没有返回行。

## 5. 最小新接口稿（未实施/待主线冻结）

- RuleMetricSourceAuthority.verify_publications(session, rule_binding, heads<=200) -> tuple[PublicationValidationReceipt]：实际可信来源登记核验，缺省None在连接/任务/BUILDING前503。rule_binding由新联合facade签发并绑定真实事务及当前Rule范围/精确profile/已锁来源，不接受请求构造。现旧Receipt结构可复用，权限与实际验证实现不可继承其kind字符串。
- RuleExpectedInventoryProvider.prepare(session, rule_binding, account_windows) -> RuleExpectedManifest；iter_unit_batches与iter_membership_batches、revalidate。account_windows为新facade当前批次和共同SQL时间生成的已验证窗口，不能接任意HTTP列表/SQL片段。provider不能持锁网络，不允许缺项skip；生产issuer尚未实现，技术fixture明确独立本轮登记证据。
- RuleFactExpectationBridge.capture_anchor(session, verified_manifest, expected_profile) -> RuleFactTicket：先完成已批准source锁序，再固定完整anchor/预期绑定。票据同实例/session/actual transaction，无成功Simulation/eligible字段。
- iter_units(session,ticket,after,limit<=200) -> VerifiedRuleUnitBatch：完整预期驱动选择，不从cell反推全集；每批保留选中cell、真实publication、预期证明及字段完整mask。数据坏/来源拒绝整批失败，不输出部分成功。
- iter_entity_inputs(session,ticket,unit_batch,...) -> VerifiedRuleEntityInputBatch：从精确cell/事实/独立membership重建目标实体原始指标及quality，以可审计输入根绑定每个实体/account/currency；新typed batch由bridge私有issuer签发。每批200，全局目标UUID顺序必须有SQL staging/keyset支持，不能用Python全图排序或每页重扫全部数据掩盖容量。
- resume/revalidate(session,persisted_input)必须每批当前授权/完整scope/来源证明后新发票据，不复用上事务实例能力、不重新latest。最终seal独立重读SQL输入与结果根；参数里没有caller supplied facts_complete或expectedroot通行证。

必须由主线先分配联合来源/预期/授权facade协作接口和必要的有界staging字段，才实现上述桥；现默认空生产authority不被自动补成fixture。不会改共享MetricsQueryStore，也不让有界授权summary充当来源发行证明。

## 6. 有限纯聚合复用与质量

复用rule_metric_windows的账户业务日纯函数、MetricAccumulator/MetricGroup的六分子严格Decimal和五ratio、原S1解释器稳定condition_index与三值。按同tenant/account/target实体/currency/profile/version分别累积；CAMPAIGN/ADSET要先从完整独立AD membership验证成员，再汇总，不用部分AD当完整父对象。CTR/ROAS等按分子总和后计算，不能平均比率。未知/缺一个贡献污染对应字段，分母0返回NULL；合法空cell零的许可须实际独立证明，不把SQL空SUM COALESCE0当完整零。

MetricAccumulator.finish(ratios_allowed=...)参数不等执行/建议许可：由字段完整性定义是否该ratio可计算，原quality进一步记录missing/stale/immature/sparse。Money跨币拒绝、NULL保持UNKNOWN。完整授权READY允许UNKNOWN/稀疏；15分钟同版本确认与后续可执行建议的coverage/归因成熟/最旧observed质量约束分开，不发明enable全TRUE门槛。桥不写RuleHit/Run/建议或发AI/广告。

## 7. 待真实验收

正式issuer缺失默认零新构建；本轮技术来源必须显式guard及真实登记证据逐项确验，不能只复读hash。小型真实SQL链需覆盖两个账户不同时区/币种与跨日、cutoff120/迟到110、来源头/源config/预期不匹配、最新空/墓碑不回退、完整0与未知NULL区分、父对象缺一个AD/member时UNKNOWN或缺清单503、坏hash/外来实体拒绝、每批撤权与跨事务失效、全局实体顺序跨200分页、final EOF根重算和来源配置锁序真实并发。全部尚未执行；无50k/350k单元或10万实体容量结论。
