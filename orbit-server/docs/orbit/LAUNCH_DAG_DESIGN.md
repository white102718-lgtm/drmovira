# PY06 独立完整DAG展开检查

## 本节点边界与原合同

本节点仅新增`python/orbit_api/launch_dag.py`、`python/tests/test_launch_dag.py`和本文。未注册HTTP、创建Task、写SQL、运行共享MySQL/浏览器或发送平台请求。原范围消费文件仍冻结。TeamAI检索未命中ORBIT的DAG口径，依据原PRD与本次主线确认实施。

原依据：`contracts/WORKFLOWS.md`第2节完整slot分配，第8节canonical输入/十五分钟有效期及同计划版本任务唯一，第127行全部DAG节点上限100000和manifest完整才可发送；`reference/03_原合同保留章节.md`步骤6说明上传→系列→组→创意→广告→回读，并允许独立分支并发。原OpenAPI TaskNode.kind包含UPLOAD/CAMPAIGN/ADSET/CREATIVE/AD/VERIFY/ENABLE/ALLOCATION，父依赖最多100，node_key最多512。本文不擅改原公开Task schema。

`build_launch_dag(plan, *, plan_revision, allocation, compatibility, material_revisions)`是内部纯函数。先复用原严格PlanWrite解析、UUID/大小/层级上限，再要求非空实际账户与完整三层树。空草稿可以保存，但不能生成空成功DAG。缺完整AllocationSolution或可信CompatibilityEvidence返回503；缺边/未核验/不完整能力证据不能被当作兼容、计数零或valid=true。映射缺项、重复slot、外域素材、实际不兼容边、错误usage等拒绝整图，素材/算法/能力/输入版本漂移409。

返回不可变DagManifest及内部DagNode，明确`execution_authorized=False`，不包含task_id、平台external_id、状态或预检hash。内部graph_hash不是原PlanValidation.hash。结构完整并不证明身份、政策、来源当前权限、杀毒或平台能力可执行；这些仍须真实预检事务与provider分别核验。

## 实际节点、去重与依赖

- UPLOAD按实际使用的(account_id,asset_id)唯一生成，素材revision固定。相同素材在同账户重复使用只上传一次，不跨账户、跨asset ID或按内容hash合并；未被完整分配实际采用的池成员不产生上传操作。每项UPLOAD都有真实目标VERIFY，不能拿到平台ID就当处理可用。
- 每个展开系列有CAMPAIGN与对应VERIFY，每个展开组有ADSET与对应VERIFY。ADSET依赖所属系列回读成功。所有系列、组和广告创建目的明确为CREATE_PAUSED。
- 每个广告slot保留独立CREATIVE与VERIFY，不凭相同文案/素材猜测可复用。CREATIVE同时依赖所属组VERIFY及本账户所用素材UPLOAD的VERIFY。AD依赖组VERIFY和其CREATIVE的VERIFY，之后有自身VERIFY。
- UPLOAD与初始PAUSED系列可以独立并行，创意是实际汇合点。没有让系列依赖500个上传的截断列表，也没有串行500项上传；原文未定义必须整个池全上传完才创建任一系列，主线明确批准采用真实对象最小依赖。未来若能力包规定额外真实先决条件，需要版本化图规则，不能忽略其计数。
- activate=false完全没有ENABLE。activate=true对每个系列、组、广告分别产生真实ENABLE及其VERIFY，不对UPLOAD/CREATIVE启用。组启用依赖父系列启用回读，广告启用依赖父组启用回读。所有ENABLE还依赖整批广告配置回读门禁；这不代替launch.publish、二次确认、当前policy或发送前授权。

全部VERIFY指向实际操作对象。ALLOCATION在本图生成前已是独立完整结果，不增加一个未落库的假ALLOCATION任务节点。已有上传映射、平台幂等回读、AdsPower执行语义将来必须由可信版本化执行适配器确定；当前图按每个实际账户素材对安排真实上传/核验，不会凭缓存存在就减少节点或宣称no_op。

## 启用门禁最多100父依赖的证明

采用主线批准的现有真实广告VERIFY每99项分组方案，不增加额外广告回读或无对象屏障。

每组前98个广告VERIFY只依赖各自AD，保持并行；组尾真实广告VERIFY依赖自身AD、同组前98个VERIFY、前组尾VERIFY。首组不含前组尾，因此父边最多99；后续完整组最多100。最后不足99的组按实际数量收缩，末尾仍是对应最后一条真实广告的原VERIFY，并包含前组尾。只有组尾的实际广告回读需要等待该组及之前所有回读成功。

稳定拓扑中这些父节点都已经生成，因此不存在回边。归纳可得第k组尾的祖先包含前k组全部广告配置回读；最终门禁覆盖整批全部广告。完整树每个系列/组至少一广告，因此其素材、创意及父级创建/回读也是某个广告回读的祖先。所有ENABLE依赖最终门禁，没有截断到前100条，也不重复读取N条广告。

失败传播边界：非组尾独立分支仍可完成原创建与回读；某组失败会阻止本组尾及后续组尾/所有激活，后续组的其他98条回读仍独立。这是整批激活前全配置成功的保守门禁，不把已创建PAUSED对象伪报成功激活。未知结果及安全重试由后续真实命令模块处理，本纯函数不转换状态。

## 排序、指纹、局部错误与完整计数

账户、三层local_id、各自数值副本序号决定稳定key和拓扑。错误source_pointer保留调用原树数组位置，即使UUID排序后也仍定位正确的`/campaigns/i/adsets/j/ads/k`。不截断名称或node_key。上限错误指向`/campaigns`；空层指向实际空数组；映射问题指向`/allocation_id`；版本和重复开关错误指向原字段。

plan_input_hash规范排序账户/素材/profile集合及按账户/组/ad映射的身份集合，保留配置树兄弟顺序、金额字符串和其他原字段；原请求不变。每节点configuration_hash绑定schema版本、计划revision、完整计划指纹、完整分配input_hash、kind/key、父key、素材ID/revision。graph_hash包括真实完整节点及分配输入；仅诊断source_pointer不参与语义图hash，以免素材集合换序改变语义指纹。

设U为实际使用的账户素材对数量、C/S/A为展开系列/组/广告数：

| 模式 | 完整节点公式 |
| --- | --- |
| 全部初始PAUSED | 2U + 2C + 2S + 4A |
| 完整启用分支 | 2U + 4C + 4S + 6A |

构造节点前先按完整映射预计算总数，超过100000立即422 PLAN_NODE_LIMIT，避免先构造被拒绝的大图；构造中再次保护，结束断言预测数与真实节点数完全一致。不能只返回广告数当DAG总数。已有每层/广告10000保护先于展开。

复杂度：不含已完成兼容图/分配求解，排序O(A log A + 配置排序)，节点和父边O(V+E)，每广告回读额外依赖均摊O(1)，全图E为线性量级且单节点最多100。内存O(V+E+原计划)，graph_hash当前使用规范JSON会有额外瞬时对象/字节峰值；100000纯fixture通过不是生产容量证明，正式任务应使用分块manifest和流式规范摘要，不在HTTP返回十万节点。

## 信任边界及下一步

兼容证据的verified/complete是内部provider对象，绝不能从浏览器body映射为认证标志。既有纯兼容图机械绑定slot字段/素材版本，其source_hash还必须由未来可信provider绑定完整账户能力、身份映射、URL、素材尺寸/格式/时长/hash及要求；DAG的完整计划hash只冻结本次内容，不能代替provider重新证明该内容。未建立生产能力证据采集器时真实接口继续503，不可将本地fixture用于生产成功。

真实预检还须实时caller+实际owner读权限交集、当前账户身份/能力、C CLEAN证据、当前allocation/命名、预算minor-unit/minimum/policy、账户时区与日期/时间校验、激活确认。原十五分钟hash、上海跨日失效、即时发送前重核及同计划revision任务唯一仍是后续节点，本文件不签发任何凭证。

真实任务最终需要有界首200节点/游标、100000节点完整manifest、分块原子发布/恢复、逐操作命令与核验。不能把DagManifest dataclass当Task表，也不能为了返回202制造空Task。分配持久化最小DDL提案见`LAUNCH_ALLOCATION_PERSISTENCE_DESIGN.md`，032仅预留，未经主线批准不写迁移。

## 实际证据

定向DAG首轮31纯测4.03秒通过；新增配置指纹与真实不兼容映射等后，DAG36+原分配27共63项纯测PASS（8.38秒）。最终加入未使用池成员不上传检查：DAG37+原分配27共64项纯测PASS（8.28秒），源码与测试Ruff PASS。此为最终冻结检查点。

覆盖单广告10真实节点、账户内上传去重/跨账户不合并、真实副本及独立兄弟展开、全部ENABLE祖先完整性、99组边界1/98/99/100/197/198/199/500、全节点拓扑/真实目标/父上限、原字段指针、完整配置与分配变化指纹、无provider503、部分/外域/不兼容/旧版本拒绝、恰好100000节点及超限拒绝。纯测没有SQL、真实平台、真实provider、Task/预检或性能验收，不勾选整投放模块。

032实际容量联测后新增精确配置边界修复：内部二次json.dumps原先默认空格使合法原5MiB配置膨胀，现使用规范紧凑separators，原严格PlanWrite与5MiB限制不变。新增精确5242880字节合法配置→5000广告/20006真实节点，原配置name仅多1字节→413原错误码；最终DAG38项实际PASS（5.77秒）。032最终20/20真实SQL又验证10000广告/500素材的精确5MiB源完整通过DAG及全部items原子发布，范围见LAUNCH_ALLOCATION_RUNTIME_DELIVERY，仍不代表生产平台能力或Task执行已完成。
