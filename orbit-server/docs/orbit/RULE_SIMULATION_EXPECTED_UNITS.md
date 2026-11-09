# Rule模拟：授权账户业务日日历预期

当前交付仅新`rule_simulation_expected_units.py`、专属纯测及本文；21/21定向纯测PASS（1.34秒），两个Python文件Ruff/format通过，无实际SQL/HTTP、无issuer或模拟READY。已有access真实1001账户回执和063候选约束回执不自动覆盖本模块。

## 输入与固定时刻

`RuleSimulationExpectedUnits(access_facade)`要求真实RuleSimulationAccessFacade实例，不接受None/TRUSTED标签或任意callback。`iter_units(session, rule_ticket, authorized_batch)`首先调用该父实例assert_batch，必须精确真实发行对象、同AsyncSession和实际SessionTransaction；假batch/换ticket在SQL时钟前拒绝。没有caller时间、expected_count或任意账户列表入参。

首次真实批次在该calendar实例+实际SessionTransaction执行一次`SELECT UTC_TIMESTAMP(6) AS evaluated_at`，SQL返回naive UTC附UTC标记，保留微秒；后续所有授权批次及同事务另一Rule流均复用同一时刻。SQL失败/取消/异常值将该事务时钟标失败，不再重新取时假装同一次计算；首次并发查询拒绝，不起后台任务。跨事务必须先取得新真实父票据，旧票据/结果不复用。

Rule window来自父票据深不可变原Rule15，复用`rule_metric_windows.resolve_rule_metric_window`；不接手工window覆盖。TODAY、YESTERDAY、LAST_3D、LAST_7D按各账户真实IANA及共同SQL时刻得到包含两端的日期标签，不用规则调度时区/UTC/上海统一日期替换，也不声称已证明对应UTC采集区间。

## 有界输出与未知窗口

输入父batch可有200或1000账户；逐账户仅临时最多7天，输出`CalendarUnitBatch.units`每批1..200条，不积攒50k或350k全集。记录`CalendarExpectedUnit`固定account_id/business_date/timezone_name/currency/window/status/reason_code，全局按父账户UUID及该账户日期递增输出。父batch必须在下一父batch推进前完整消费本iterator；提前推进、重复/并发输入、关闭/取消/异常都不能产生完整summary。

有效时区输出每个实际日历日一条RESOLVED记录。缺失/坏时区或日期溢出输出该账户唯一`UNRESOLVED_WINDOW` sentinel：business_date=None，原timezone及currency原样保留，reason_code为TIMEZONE_INVALID或WINDOW_DATE_OVERFLOW。它计account_count及unresolved_account_count，不计resolved_unit_count，不跳过账户、不补UTC/零、不称MISSING事实。

sentinel不是063非NULL日期unit的可写行，也不代表独立实体预期或采集缺失；后续持久化/来源桥必须明确保留诊断或阻止完整发布，不把它变成一份正常完整指标。原current账户表NOTNULL，因此实际NULL分支此阶段仍只有纯测，不宣称正常SQL写可达。

`finish(session, rule_ticket, verified_manifest_summary)`是同步纯校验，不查询新的时刻或数据。首先assert_summary验证真实父完整EOF结果，再核本模块所有账户实际消费完、ID根/count严格等父summary，才发行ExpectedCalendarSummary。字段为evaluated_at/account_count/resolved_unit_count/unresolved_account_count/calendar_root/calendar_complete。未解析账户仍计完整授权account_count；calendar_complete只表示日历可全部解析，绝不是来源完整、coverage=1、Simulation READY或enable/建议执行许可。

批次和summary是深不可变的私有发行对象，`assert_batch/assert_summary`同时核实际对象身份，dataclasses.replace复制issuer字段不能换值伪造能力。批次仅在原父batch尚当前时可用；summary只在原实际事务有效。弱票据索引及结果弱引用不反向永久持有所有页。方法不创建任务、不commit或持久化，不声称回滚外层已提交前缀。

## 根格式

账户身份根逐UUID canonical字符串、逗号、左右方括号SHA256，与原Rule manifest canonical([ids])严格一致。finish只接受实际流累计根，不接受传入完成布尔或数量。

日历根固定域`ORBIT_RULE_CALENDAR_UNITS_V1`加NUL前缀；每段UTF8 canonical JSON前置8字节大端长度。头数组包含域版本、tenant、Rule UUID/revision、manifest UUID/成员根/完整数量、共同evaluated_at UTC ISO微秒含+00:00、原window。每条记录为account UUID、ISO日期或null、原timezone、原currency、window、status、reason_code；尾段为EOF/account_count/resolved_unit_count/unresolved_account_count。对象键序/字符串拼接不存在隐式边界，NULL和缺值不与日期混比较。不同批次分组不得改变根，币种/时区/业务日变化必须改变根。

这个calendar_root仅证明授权账户日历声明；不包含publication/fact值、独立实体membership、captured pages或完整指标根。不能把它放进既有source字段冒充source_selection_root，不复用旧MetricsReadContext/056 issuer，不调用monitor权限。

## 纯测与待真实范围

21项使用真实父Facade发行批次、SQLAlchemy RowMapping及AsyncSessionTransaction；授权/SQL结果仍是明确纯测替身，没有实际DB。覆盖四窗口/美洲与上海跨日、1001账户1000→200再拆、同事务两个父票据仅一次时钟、分批根一致、未解析保留账户/NULL不补USD、跳批/重复/并发/提前close/cancel/父流抢先EOF、替换伪batch/summary、时钟失败/取消不换时、跨事务失效、metadata入根和缺父实例拒绝。

下一真实专项需由root统一排队：沿原HTTP图/真实facade取实际SQL UTC6并证明相同事务只取一次、1001多时区窗口与有界输出完整对账、坏IANA sentinel真实覆盖及NULL1048边界、旧事务结果不可复用/取消未EOF无summary。事实来源/独立实体清单仍按另一proposal后接，默认无生产issuer不创建成功Simulation，不因日历统计通过就发READY。


## 主线真实102档限定结果（后续实测覆盖上述待跑计划）

主线组合102/102 PASS，84.93秒，新7组calendar均实际通过；证据 `docs/orbit/evidence/python-rules062-options-simulation-calendar102.json`。实际范围为1001账户（不是50k）、四IANA与四窗口、200/1000父批次完整日历根一致、SQL UTC6同一事务一次、坏IANA sentinel不漏账户及NULL写精确1048拒绝。完整EOF后的verified_profile真实返回冻结RuleProfileBinding，id/version/hash与原Rule版本相符，调用未增加SQL。

这是授权账户业务日日历与只读权限证据，不证明事实来源发行、独立实体清单、采集coverage或Simulation READY；无simulate/enable/source成功。取消证明生成器/事务票据语义，不扩大为服务端SQL等待取消。上文“待真实”保留为当时计划，实际范围以本节和具名回执为准。按最新第七节先交付规则定义闭环，不继续扩展模拟内部组件。
