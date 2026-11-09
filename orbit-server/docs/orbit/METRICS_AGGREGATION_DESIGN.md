# 指标分子与比率计算

本模块为`python/orbit_api/metrics_aggregation.py`，仅实现授权后完整单元内的计算，不发行来源、质量、覆盖率或可执行建议。没有新增路由、采集器和页面，后续Query Store仍须复核权限、选择最新完整cell、处理完整预期集合及迟到版本。

已按teamai-recall检索金额与指标约定，无相关命中；口径依据baseline/reference/03_原合同保留章节.md第14—23行和baseline/contracts/WORKFLOWS.md第29行。币种和指标版本不能混合，原历史归属在聚合前过滤，不在计算函数中猜测。

## 原业务口径和算法版本

`MetricGroup`精确包含tenant、currency、profile_id、profile_version。不同分组输入一律503，不能把美元与欧元、不同租户或归因口径相加。`MetricAccumulator`仅接收六项可加分子：spend、impressions、clicks、registrations、purchases、purchase_value；不接收预计算比率。

ROAS=总价值/总消耗，CPM=总消耗/总展示×1000，CTR=总点击/总展示×100，CPC=总消耗/总点击。原合同的CPA为指定转化，首期conversions=purchases，因此CPA=总消耗/总购买。不能照搬参考项目的注册CPA，也不能平均各行ROAS。

版本`orbit-metric-sum-purchases-ratio6-half-up-v1`采用最后一步保留六位小数、ROUND_HALF_UP；这是原文未规定舍入细节处的显式实现选择，未来变化必须换algorithm_version并保留旧查询快照。源值超过六位不偷偷舍入；原28字符上限同时作用于结果，溢出整包503，不科学计数、不截断。使用局部Decimal精度80，进程全局精度变化不影响结果。

## 未知、质量与原子性

任一参与行某分子为null，则该汇总列为null；零是有效数值。没有行时全部未知，不能生成零。可信完整空结果若确有零，必须由独立来源明确提供零分子，计算函数不做来源推断。分母零返回null。调用方必须显式传入ratios_allowed；无质量许可或任一关键五指标不完整，所有比率为null。

每行先完整校验再更新六个分子，非法末字段和溢出不留下半行累计。输入只接受原规范十进制字符串/null，拒绝float、bool、指数、负数和原始比率。函数只保留六个Decimal及缺失位，可流式消费；没有声称已达到真实查询容量目标。usage始终null，等待真实ad→creative→asset映射的跨日distinct计算，不拿行数或广告数代替。

## 验证范围

31项定向测试通过，包括加权比率、购买CPA、未知传播、空集合、显式质量许可、四维分组冲突、非法输入原子性、全局低精度下的大金额、总和/比率溢出、HALF_UP边界、一万行流式精确累计与重复读取。首轮29通过/2失败证据保留：测试错误使用七位源小数，修为合法分子分母产生七位比率，没有放宽源输入合同。

与严格合同、范围消费合并的固定源码检查为280项；真实SQL范围仍独立13项。详见具名evidence回执；这些均不能勾选完整监测功能或容量验收。
