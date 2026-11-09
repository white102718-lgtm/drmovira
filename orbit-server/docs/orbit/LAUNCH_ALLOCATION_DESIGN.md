# PY06 分配算法独立节点：allocation-v1

## 原合同与当前边界

依据原WORKFLOWS第2节：先按账户/三层local_id/各自数字copy_no元组生成稳定slot，素材按内部UUID排序。每广告恰好1素材。不重复时池大小必须等于广告数（池<=500意味着该模式广告<=500）；重复时池1..min(500,广告数)，每层及广告<=10000。完整图必须核READY/版本/类型/锁定能力包的格式、尺寸、时长，未知不能猜true，均匀不能替代兼容。

本节点只新增`python/orbit_api/launch_allocation.py`及`python/tests/test_launch_allocation.py`，没有HTTP注册、SQL写入、假202、假task、真实平台写入。原D1/命名/前端与共享入口均保持冻结。缺权威适配器时503 CAPABILITY_COMPATIBILITY_UNAVAILABLE；本地纯测能力包明确为isolated fixture，不把verified布尔值当真实 registry 验收。

## 完整兼容证据

`build_compatibility_evidence(slots, asset_ids, *, capability_version, source_hash, verified, complete, evaluate, material_revisions, ..., work_budget=None)`逐slot×asset读取已冻结本地能力证据；evaluate必须返回真正bool，None或其他类型立即503，不把未知当不兼容/兼容。不得在每条边联网。完整图使用每slot的兼容bitset和已求值bitset，必须每一条边均已明确求值。

不可变CompatibilityEvidence绑定规范排序slot keys、完整slot字段hash（包括asset_type）、规范素材ID集合、素材revision集合、能力版本及权威source_hash。source_hash必须由未来可信适配器冻结完整账户能力、素材格式尺寸时长/hash以及计划对应要求；浏览器不可提交此类verified标志取得权限。相同slot key但要求改变不能重用旧图，素材版本漂移409，缺边/集合/version错配503。

`solve_allocation(..., allow_repeat, seed, material_revisions, ..., work_budget=None)`生成包含algorithm/seed/slot字段/素材版本/能力来源/全部兼容边的input_hash，输出完整不可变Assignment/usage/Σusage²/warnings；不输出部分映射。真正API store还须在同事务附当前asset_revision、scope、plan_revision、租约/任务状态并按原公开schema返回，纯结果不冒充ALLOCATION_SUCCEEDED存储证据。

## 最大匹配与全局凸费用

先做真实容量残量增广可行性：source→slot容量1，slot→兼容asset容量1，asset→sink不重复容量1/重复容量slot_count。任一slot不能增广即422 ALLOCATION_NO_MATCH，全批拒绝。

重复模式再从空流计算最小费用完整匹配。asset→sink第k份流的费用为2k-1，总费用1+3+...+(2u-1)=u²；slot↔asset正反残量边费用均0。因此每次在全部可达asset终点中选最小边际费用2*usage+1的残量增广路，而非只在当前slot直接候选中选较少使用者。路径可以把早先slot迁至另一素材，全程保留真实兼容边。原最小费用流无负环，加下一个slot后沿最短残量路增广，归纳得到当前完整前缀全局最优；全部slot完成后为Σusage²全局最优。反向费用sink→asset不会出现在终止于sink的最短简单增广路径中，不能据此省略内部已有匹配反向边。

为控制10000slot图的对象数量，用`members[a] & compatible_column[b]`找出a上可迁给b的真实已匹配slot见证，把搜索压缩为至多500资产节点；位交不为0才存在残量路径，并保存具体slot，回溯时逐个验证其确实匹配到前驱asset。seed用SHA256(allocation-v1,NUL,seed,NUL,asset_id)确定稳定边优先级，slot固定原元组顺序、见证取最低slot序；seed只在相同边际费用平局决定路径，不添加会压过主目标的权重。同输入/版本/seed固定结果，改变seed可以不同但主目标不变。

反例已测试：首slot兼容A/B，第二slot只能seed优先的A；固定贪心会失败（不重复）或usage=2/0、成本4（重复），残量增广迁移首slot到B得到完整1/1、成本2。约束3个只能A、1个A/B时最优3/1成本10，成功并显示差异警告，不宣称次数差<=1。

## 规模、复杂度、时限与真实任务约束

N<=10000，M<=500，完整边最多500万。图表示为兼容行/兼容列/匹配成员bitset加O(N+M)数组；原始信息量约3NM bit，Python对象及slot字符串额外计，不把该估计当真实内存压测。评估器建图N*M次，转列位运算上界O(N*M*L)，残量搜索保守上界O(N*M²*L)，L为容纳N位的机器字数；直达全局最低usage的常见图可以很早结束搜索，但最坏图仍须超时保护，不能靠典型快图声称所有容量通过。

Budget使用真实monotonic deadline，范围(0,60]秒。建图与可行性/凸费用两阶段必须传同一个work_budget，不能建图60秒再求解60秒。每slot/每64候选均检查；单调时钟超时抛AllocationTimeout，只携带阶段/source_hash/完整图完成时的input_hash，不带partial assignments或task_id。此为协作式CPU时限，阻塞的错误evaluate不能被纯Python中断；未来Worker必须只用本地非阻塞包并有独立进程硬限保护，不能在数据库事务持锁期间求解。

原POST allocations固定202并允许QUEUED/RUNNING/SUCCEEDED/FAILED、task_id可null，不意味着未建立队列就返回202。本节点不注册该接口。下一store/Worker必须先真实持久记录冻结输入、只允许每计划一个求解任务、claim/lease/heartbeat/超时恢复/幂等；同步尝试超时才能真实切入已落库异步任务，并沿相同冻结输入hash继续。发布成功映射前重新取得来源锁（素材clock/全量sorted素材在launch之前）、实际plan CAS、caller+target读权限、当前C CLEAN/revision/hash及能力版本，任何漂移整批拒绝。取消/替换沿C提供的引用ticket和同事务deactivate/register，不伪造活跃引用，不动历史证据。

## 证据与未验

27纯测PASS，Ruff PASS。512个3×3图与独立穷举注入匹配oracle比较可行性；2401个4×3非空图与穷举全部候选的usage²最优值逐一比较；覆盖贪心反例、seed确定性/仅平局、集合排列同hash、不可避免差异、缺权威/未知边/不完整图、旧素材版本/旧slot类型拒绝、typed超时/共享60秒deadline。纯最大边界含10000slot×500素材完全兼容图，整套测试27项4.53秒；这只是纯算法fixture，不是权威能力、SQL、真实数据分布或端到端容量验收。

原分配接口、持久异步任务、真实能力包适配器、C引用注册联调、预检/执行、用户重新分配seed+1确认/取消保留及完整UI均仍未实现/未真实验收，不打整模块勾选。
