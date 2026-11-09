# 规则模拟S1纯流式解释器

当前独立纯层已实现并冻结：专属57项纯测PASS（0.70s），Ruff/format通过。没有SQL/模拟provider/Simulation13成功响应/READY或执行资格，不创建迁移，不改原解释器。正式模拟持久化编号由主线另分配，062留规则页面菜单。

## 纯输入与结果边界

异步入口：`evaluate_simulation_entities(rule, expected, batches, sink) -> EvaluationSummary`，位于`python/orbit_api/rule_simulation_evaluator.py`。

- rule为原RuleWrite（也允许原Rule子类仅提取11配置字段再严格解析），冻结规范配置；复用`compile_conditions`和`evaluate_conditions`，稳定flatten condition_index、不短路。
- ExpectedEntityStream为明确entity_count及expected entity_ids_root。0..2147483647沿原scanned_count范围，不假设账户1..50000就是实体数；实体可能多于账户。它只是技术完整性输入，不是权限或独立预期发行证明。
- EntityObservation为冻结entity_id/account_id/currency/observations。ID均规范UUID，currency为账户自身ISO三字符或未知None；原规则11种指标为Decimal、原小数字符串或None，拒float/bool/int等非合同类型与usage未知字段。缺指标/类型内非法数值沿现解释器UNKNOWN，不补0。输入dict先复制再MappingProxyType，key/value仅不可变类型；slots+frozen DTO不保留调用方可变映射，输出叶子tuple亦深不可变，public()只返回新投影。
- batches为异步tuple批次，每批1..200；200是本纯层内存协议，不新增PRD业务上限。全局entity_id规范排序严格递增、不得重复，同一个实体不可拆批。禁止全实体list/set，常数根/统计与当前批次内存。
- 每实体输出不可变EntityEvaluation，保留该实体三值与完整叶子。每叶public投影严格原ConditionResult五键entity_id/condition_index/value/result/reason_code；数值用原Decimal文本规范，不输出float或实体真值额外字段到原ConditionResult。
- sink为明确异步消费当前已计算批次的受控内部接口，不通过公开请求接收回调/SQL，未来Store自行实现BUILDING写入。成功ack必须恰为None；False或其它返回不能当成功。sink任一异常/取消不返回最终summary；已经消费的前缀不得当完整模拟结果发布。

## 值与覆盖口径

本纯层不发行来源/coverage、账户窗口、实体全量集合、quality、权限/租约/执行资格。ExpectedEntityStream和EntityObservation不含TRUSTED字符串，不将其当可信issuer。未来adapter必须独立核当前双方权限、全部(account,business_date,profile)预期、完整分页/成员根、最旧观察时刻、成熟与稀疏、真实内部实体UUID和账户归属。

不跨实体求和/不跨币汇率。每实体保持其自身账户币种和原阈值；币种未知不能猜USD。确需跨该实体多行汇总时由adapter复用`MetricAccumulator/MetricGroup`在同租户/币种/profile下先汇总分子再计算比率；不平均ROAS/CTR。分母0、coverage未许可或缺字段按现汇总器产None，再由条件解释器得UNKNOWN。S1不从几个非NULL值反推coverage完整。

currency=None时依原`rule_contract.MONEY_METRICS`集合将spend/purchase_value/cpm/cpc/cpa观测视作None进入现三值解释器；不清除独立计数/CTR和已由adapter正确供给的无币单位ROAS。该规则不授予ROAS来源完整性，未来adapter仍须核其同一实体分子/分母。

hit/false/unknown为实体根真值计数，与叶子计数区分；scanned=三者之和。FALSE/TRUE根仍输出全部UNKNOWN叶子，不因短路删除条件。输出NULL原因沿现`METRIC_MISSING/METRIC_INVALID`，更详细来源质量原因需未来adapter/独立技术合同，不改本次既有解释器。

## 完整流与根协议V1

SHA256采用固定版本domain和UTF8 canonical JSON，各frame前置无符号8字节big-endian长度，拒绝连接歧义。identity根对实际严格排序实体ID逐帧更新；必须与expected数量及root精确一致。

固定identity序列：frame({domain:"ORBIT_RULE_SIMULATION_ENTITY_IDS_V1",version:1}) → 每个frame(规范entity_id字符串) → frame({count:实际数量})。纯`entity_ids_root(iterable)`复用同协议、排序与INT32数量校验；它不是可信预期发行器。

结果根另独立domain，包含原RuleWrite规范配置根、expected数量/identity根、每实体account/currency/entity真值及全部原五键叶子（condition_index严格编译顺序）、最终统计。独立domain区分identity/root，批次边界不进入业务根，因此同一有序实体流按20或200批处理结果根相同。不同Rule配置/实体身份或上下文/叶子/顺序不能重用根。

固定result序列：frame({domain:"ORBIT_RULE_SIMULATION_RESULTS_V1",version:1}) → frame({algorithm:"orbit-rule-simulation-evaluator-v1",rule_hash,expected_count,entity_ids_root}) → 每实体frame({entity_id,account_id,currency,result,conditions:[全部原五键叶子]}) → frame({summary:{scanned_count,hit_count,unknown_count,false_count,condition_count}})。rule_hash为原11字段严格规范RuleWrite canonical UTF8 SHA256。批次边界、未经条件使用的多余观测不改变结果；来源原始值/完整覆盖另由未来snapshot根绑定。

只能在异步迭代器真实EOF、数量/identity全部一致、所有sink await成功后返回最终EvaluationSummary。缺尾/额外/重复/乱序/中途source异常/sink异常/取消均无最终返回根；未来持久Store不得把中间hash复制为最终证明。显式expected0+标准空identity根才接受空流；空流本身不证明0个预期实体或完整空指标。

每批消费后及EOF后显式异步让出一次，adapter/sink即使不主动挂起也可响应取消；取消在EOF前已提出时不能因马上计算摘要而返回成功。无finally吞错/假回滚，无独立后台任务。未来来源按staging主键有界排序读，不得为了本协议排序在Python累积海量全实体。

统计和完整根是内部计算结果，不等于Simulation.hash最终业务定义（后者还须绑定Rule revision/manifest/profile/来源快照/算法和实际15分钟租约）；不得直接拿本层summary充当Simulation13。

## 验证清单

独立纯测试：原条件稳定索引/全叶五键/所有实体计数；NULL≠0、无效Decimal与计数、真实先分子后ratio/0分母、USD/EUR分别判断；批次分割根恒等、改Rule/实体/account/currency/叶子根改变；0流显式预期与错误root；少尾/超量/重复/乱序/非法UUID/大小批次拒绝；sink/源失败与取消均无summary；源失败不被吞为正常EOF；只持当前批次无全局实体集合。

纯层通过只证明计算协议，不证明MySQL、实际账户来源、平台、模拟15分钟有效性、前端全部条件分页或启用/运行调度。真实来源与持久化由后续明确阶段推进。
