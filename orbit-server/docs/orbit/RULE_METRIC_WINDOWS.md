# 规则指标账户当地窗口纯规范

依据原baseline/reference/03_原合同保留章节.md:139（账户IANA时区）、:206
（TODAY/YESTERDAY/LAST_3D/LAST_7D，LAST含今天）和:211（schedule.timezone不是数据业务日）。
teamai recall没有ORBIT精确窗口结论，不以其他项目巴西业务日替换本需求。

已有rule_conditions处理三值条件；rule_schedule处理调度slot/DST及执行日历，二者不负责
每账户指标日窗口。account_details_contract.window的LAST7等枚举不同，未改动或硬套。

新纯接口：AccountMetricTimezone(account_id,timezone_name)；
resolve_rule_metric_window(evaluated_at,window,account)返回ResolvedRuleMetricWindow；
resolve_rule_metric_windows(evaluated_at,window,accounts)每批0至200账户，保序、拒重复，
不消费无限迭代器。大范围由来源适配器分批，所有批必须复用同一次可信UTC evaluated_at。

输入时刻须aware且UTC offset为0；非UTC输入不自动猜测转换。未知/缺失IANA不回退UTC，
固定offset字符串不能代替IANA。函数不读取系统now或Schedule。输出每账户ID、IANA、
同评估时刻、原window、local_today及包含首尾的date_from/date_to。
TODAY=[today,today]；YESTERDAY=[today-1,today-1]；LAST_3D=[today-2,today]；
LAST_7D=[today-6,today]。日期按当地日历减天，不减UTC固定24小时。

DST折叠/跳时采用真实UTC instant转换当地date，无需构造不存在墙钟时刻。
国际日期变更导致消失的当地日期仍是所选日历标签，实际是否存在完整单元由来源判断；
纯函数不补零、不伪造expected/cell，不推断READY/Simulation/权限或启用资格。
Python日期可表示范围内原值保留；转换/减日超界明确异常。未来SQL来源仍须额外验证
其DATE存储范围，不得把纯日期结果当作已合法持久化。

38项专属纯测通过，覆盖原四窗口、同instant多当地日期、DST两种情况、闰年/跨年、
国际日期线、上下界、非法IANA/非UTC、200/201、空批/重复与UUID规范。
此结果不是SQL、来源权威、规则simulate/enable或浏览器验收；未改HTTP字段和既有公共模块。
