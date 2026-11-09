# 原规则字段边界的真实HTTP补充

执行入口为 `--migration-through 62 --rules-only --include-rule-editor --include-rule-editor-scopes --include-rule-scope-consumer --include-rule-editor-definition --include-rule-schedule-preview --include-rule-definition-boundaries`，工具只接受本轮127.0.0.1:13306随机UUID库，并核实际数据库。原私有范围和Rule创建走真实HTTP；账户与指标配置为明确SQL技术样本，未调用simulate/enable或平台。

具名回执 `evidence/python-rule-definition062-boundaries-http.json` 实际 **69/69通过**：原62项加七组字段边界。新增创建15个真实DRAFT、19次严格拒绝；创建后GET与原15字段逐项一致，revision=1、next_run_at=null。每次拒绝前后比较八张规则表的完整原行摘要，不只核计数。

| 具名组 | 真实范围 |
| --- | --- |
| UnicodeName | 中文1/80码点成功；空/全空格/81码点拒绝，精确/name |
| TargetsAndWindows | CAMPAIGN/ADSET/AD、TODAY/YESTERDAY/LAST_3D/LAST_7D逐项成功；ACCOUNT/LAST_30D拒绝 |
| GroupsAndLeaves | 5组共20叶成功；6组、单组11叶、总21叶分别拒绝，精确原path |
| InclusiveDates | 2026-01-01至2027-01-01含首尾366天成功；延长一天367天拒绝 |
| Cooldown | 0/10080成功；-1/10081拒绝 |
| MaxDaily | 1/1000成功；0/1001拒绝 |
| StructureAndReadonly | 两数值字段bool拒绝400 INVALID_STRUCTURE；id/revision/state/next_run_at注入拒绝400 UNKNOWN_FIELD |

值/数量错误沿原422 FIELD_VALIDATION_FAILED，字段位置在原五字段Error的field_errors[0].path；未改变生产错误合同。首三次失败回执保留：主线工具误置parse_rule_response参数顺序、误用FIELD_INVALID、误把field_errors路径当顶层pointer，分别修工具而未改生产实现、删断言或放宽边界。第四档完整通过。

该专项不证明全部Unicode序列/全部AST算子/阈值、所有Schedule频率和DST、真实指标来源、模拟、启用、任务调度、运行记录或浏览器已经验收；不直接勾整个字段或模块。真实平台和容量均未测试。完整需求仍按总台账逐项追踪。
