# 规则调度校验与时间计算

## 输入字段和边界

`RuleSchedule`是Java内部无副作用组件，没有HTTP入口、数据库写入、定时线程或模型调用。输入严格对应产品OpenAPI的Schedule七字段，未知字段和缺失字段均拒绝；互斥不用的字段必须显式为null，不把字符串数字、小数或空值转成有效整数。错误只返回固定文案，不带被拒绝值。

| 字段 | 校验及逻辑 |
| --- | --- |
| frequency | 仅INTERVAL、DAILY、WEEKLY |
| interval_minutes | INTERVAL必填整数15—1440；其他频次必须null |
| time_of_day | DAILY/WEEKLY必填HH:mm，00:00—23:59；INTERVAL必须null |
| weekday | WEEKLY必填ISO星期1—7，周一1、周日7；其他频次必须null |
| timezone | 使用本机Java TZDB注册的区域ID及UTC，最长64字符；拒绝自行拼接的固定偏移量、无效名称和两端空白 |
| start_date | 严格四位年YYYY-MM-DD，真实日历日期，含生效日 |
| end_date | 不早于生效日，起止日均包含且最多366个当地日；支持闰年，拒绝非法日期 |

公开Definition构造器也校验同一组语义约束，防止内部调用绕过JSON校验；解析结果使用不可变Java时间类型，后续修改原JSON不会改变结果。

## 预览与未来运行共用规则

INTERVAL从生效日当地首个有效时刻开始，按实际经过分钟递增，不在每个午夜重置锚点。纽约春季切换日按小时运行有23个slot，秋季有25个；当地墙钟重复但UTC时刻和slot不同。午夜本身不存在时，按Java的atStartOfDay选择该日首个有效时刻。

DAILY/WEEKLY按当地墙钟解析。缺失墙钟不平移执行，单列skippedLocalTimes供后续审计；重复墙钟只选第一次，即较早UTC时刻。该选择在preview和latestDue中一致。星期使用当地日期，不能按UTC日期判断。

preview返回严格晚于afterExclusive的位置，最多50条。latestDue只在启用且当前仍在生效区间时选择最近一个有效位置，同时返回遗漏有效位置数及缺失墙钟列表，不补发一串过期执行。截止日后不补建任务。lastEvaluatedExclusive只是调用方提供的计算水位，尚无数据库租约、持久化水位或唯一约束，调用者不能据此声称运行已去重。

Java行为依据：[ZoneRules.getValidOffsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html#getValidOffsets(java.time.LocalDateTime))、[LocalDate.atStartOfDay](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#atStartOfDay(java.time.ZoneId))。结果依赖部署JDK的TZDB；各运行节点须使用一致版本，升级时复跑时区回归。

## 测试与未完成项

38项专项涵盖三频次、所有字段互斥、显式null、整数上下界与类型、真实日期及366日边界、IANA区域、ISO星期、起止包含、UTC跨日、纽约缺失/重复、Lord Howe半小时切换、Apia整日缺失、间隔不重置、停机合并、启停/超期、秒与纳秒临界、不变性及结果上限。见`evidence/rule-schedule-core.json`，测试使用确定时间，不连接平台或数据库。

完整规则结构、条件evaluator与内部草稿版本已补齐，见[RULE_DRAFTS.md](RULE_DRAFTS.md)；可启用的规则读写闭环、scope/profile授权与可用性、模拟有效期、状态转换、运行租约/调度水位/slot去重/遗漏日志落库、规则编辑和预览页面、真实命中分发均未完成。RUL-03整体不勾选，测试阶段保持进行中；没有以本核心替代完整功能验收。
