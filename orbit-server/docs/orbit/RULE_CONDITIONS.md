# 规则条件校验与三值计算

## 当前实现

`RuleConditions`是供后续模拟和调度共用的Java内部组件，无HTTP入口、数据库访问或外部动作。parse接收从RuleWrite投影出来的logic/groups子对象，不是完整RuleWrite请求校验器。只接受根logic/groups、组logic/conditions和条件metric/operator/threshold，拒绝未知属性、第三层AST、空组和错误类型。

| 字段 | 规则 |
| --- | --- |
| 根logic、组logic | 仅AND/OR；两层逻辑独立计算，不互相覆盖 |
| groups | 1—5组，每组1—10条件，所有组总计最多20条件 |
| metric | spend、impressions、clicks、registrations、purchases、purchase_value、roas、cpm、ctr、cpc、cpa；不接受任意指标名或表达式 |
| operator | 仅GT、GTE、LT、LTE、EQ、NEQ，不执行用户脚本或拼接SQL |
| threshold | 必须为非负十进制字符串，最长28字符、最多6位小数；无正负号、科学计数、千位分隔、两端空白或前导零；缺失/空值不能转0 |
| 计数阈值 | impressions/clicks/registrations/purchases必须为整数值；1.000000与1值相同，1.000001拒绝 |
| 金额阈值 | spend/purchase_value/cpm/cpc/cpa不超过1000000000 |
| 比率阈值 | roas不超过1000000；ctr不超过100，使用百分数单位，1代表1% |

解析后的条件、分组和定义均不可变，公开构造器重复校验约束。数值始终使用BigDecimal，EQ按数值比较，不按小数尾零或浮点近似比较，28位计数不转JavaScript Number或long。

## 三值逻辑和明细

AND有FALSE即FALSE，否则有UNKNOWN为UNKNOWN，其余TRUE。OR有TRUE即TRUE，否则有UNKNOWN为UNKNOWN，其余FALSE。该规则同时用于组内和组间。所有叶子均计算以保留完整模拟明细，不因短路而丢失后续缺失原因。

观察值缺字段返回MISSING，显式null返回NULL_VALUE；非法十进制、超长/过精度和计数非整数返回INVALID_VALUE，结果均为UNKNOWN。无效原始串不写入结果，只保留固定原因，不把无效值当零。合法观察值保留BigDecimal；不把阈值上限当作实际指标上限来截断数据。真实值的一致性和质量仍须指标发布器及质量门槛校验。

null NEQ 0为UNKNOWN，不能产生候选。只有最终TRUE使candidate为true，但这只是条件候选；OR中一个真实分支为TRUE也不代表缺失关键指标已经被豁免。范围授权、完整coverage、新鲜度、观察期和归因成熟度仍必须由后续链路独立检查。

结果含每组及每个条件的metric/operator/threshold/observed/result/reason，供后续接口按产品模拟合同映射；尚未暴露为接口。toString不打印数值，非法输入异常只有固定文案。该组件不验证调用者提供的Map是否来自可信快照。

## 验证及未完成项

83项专项覆盖AND/OR的完整三值表（组内与组间均核对）、六比较符的低于/等于/高于、11指标、金额/CTR/ROAS及计数边界、超过2^53的计数、六位小数、空/缺失/非法值原因、未知字段/脚本/嵌套拒绝、组数量/每组条件/总20条件、构造器及不可变性。见`evidence/rule-conditions-core.json`。两项测试工具回归另外证明旧Surefire报告不能冒充当前执行证据，当前汇总只采集本次新生成报告。

完整RuleWrite结构和内部草稿版本已补齐，见[RULE_DRAFTS.md](RULE_DRAFTS.md)；owner内部数据授权见[RULE_OWNERSHIP.md](RULE_OWNERSHIP.md)，scope/profile可用性、可启用的规则存储闭环、模拟真实扫描及15分钟有效期、启停/归档状态机、运行调度去重和可信命中分发、逐条件明细页面均未完成。RUL-02及相关字段整体不勾选，所有真实业务验收仍未通过。本核心不产生模拟命中列表、AI建议或广告写入。
