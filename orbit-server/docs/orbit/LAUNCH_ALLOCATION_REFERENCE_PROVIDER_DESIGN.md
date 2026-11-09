# 分配真实素材Provider桥：限定交付

当前仅独立实现launch_allocation_reference_provider.py与27项纯测；未自动注册生产应用、未提供真实平台权威适配器、未跑真实SQL/HTTP/浏览器。kind=TRUSTED标记受控代码路径，不是“平台可用”或验收证明。默认authority=None，立即503 ALLOCATION_AUTHORITY_UNAVAILABLE，不猜兼容、不新建Task。

## 原接口和缺失权威

复用AllocationProvider.capture(session,current,plan,request)、prepare_publication(session,current,packet,previous_id)、publish_references(...ticket...)。冻结runtime不变，原POST返回Allocation而非Task，Task ID可null。原WORKFLOWS的READY/版本/平台格式能力完整匹配、当前双方范围、完整引用与任何输入变化失效仍成立。

真实外部账户授权、逐账户身份、能力包、策略、素材目标/版位格式限制及相关权限版本必须由未来显式AllocationReferenceAuthority提供。本阶段只有ABC，不能拿ISOLATED_TEST的evaluate=True或verified布尔进入生产。其lock_sources必须只用预先可信取得的能力包及DB来源锁，按账户/身份/渠道等既有顺序先锁来源，不锁launch、不在事务中做网络I/O；返回LockedAllocationAuthority绑定精确transaction、BusinessContext、plan hash、source/authority摘要及capability版本。compatibility是同步无SQL/无网络的完整图计算，必须含所有真实媒体版本并匹配锁定来源。

## 真实SQL依赖与锁序

无需新迁移。依赖已有010素材、019物理生命周期LIVE、024精确引用逆查索引、026扫描收据、030 runtime proof及034来源绑定；这些都由C既有接口负责复验，不在本文件另写SQL或放宽门禁。

capture重新核当前launch.edit上下文，然后authority来源锁→require_allocation_assets：pool最多500、UUID全局排序、分成<=200批；每批既有C核caller及目标owner的assets.read、双方对象范围、目标team、READY/LIVE及版本/散列。桥额外严格要求antivirus_status==CLEAN且execution_eligible is True，不能把旧媒体READY、truthy数值或UNVERIFIED当可执行。安全元数据只保留revision/sha256/kind/mime/size/宽高/时长，不返回对象路径、预览token或ClamD基础设施。

publication先authority来源锁；有旧allocation时，调用lock_active_material_reference_set(kind=ALLOCATION,resource_id=真实旧allocation,additional_asset_ids=新pool)，旧真实引用与新池union按全局UUID排序加锁，然后批量读新素材。不能先锁新素材再补更小UUID旧素材。无旧allocation时只按新池排序读；不能拿plan_id当引用业务键。

prepare返回本Provider生成、session.info登记、绑定同一transaction/context/旧resource/plan hash/不可变metadata的MaterialPublicationTicket。runtime随后按既有顺序锁launch clock/head并完成source、guard、claim及previous allocation/input_hash CAS。只有成功后才调用发布回调；桥不授予计划权限、不提供HTTP入口。

发布验证原票据对象身份、当前事务和Provider实例、旧allocation及原元数据相等，并核完整slot集合、原input_hash/algorithm/seed/capability。释放只消费C的旧ALLOCATION精确票据，保留历史行；然后只对solution实际用到的素材按<=200批登记新ALLOCATION活跃引用。不会给整个500素材池全部建立引用，不动EXECUTION或HISTORICAL_EVIDENCE。所有动作复用调用方同一外层事务；任何引用/审计故障由外层回滚旧active、新items、引用及outbox，不在桥commit或吞异常。

## 验证与下一实际窗口

27项纯测0.97秒及Ruff通过。覆盖500素材升序200/200/100、默认缺权威关闭、当前授权漂移、媒体READY但无扫描拒绝、缺项整体失败、authority来源/版本/txn绑定、旧新union锁序、只登记实际使用子集、精确票据单次消费/跨实例跨事务拒绝、部分slot与改metadata拒绝、来源版本漂移、C权限/范围错误原样传播、释放失败不登记新引用。依赖均显式桩，不冒充真实权限或CLEAN/SQL验收。

下一主线需分配新独立真实工具：用真实C已扫描素材/多身份与现runtime短事务验证bridge的200+分批、旧新引用精确释放、1644审计全回滚、撤权/同actor跨tenant/旧READY无030证明拒绝，以及实际索引/并发。真实平台authority仍需单独实现与验收；可用只用于隔离SQL的authority桩测试桥协议，但回执必须明确不证明平台兼容性。公共app/route/harness、冻结runtime与当前HTTPfixture本次均未修改。


## 待排队真实工具

已准备tools/launch_allocation_reference_checks.py，导出LAUNCH_ALLOCATION_REFERENCE_CASES共8组，入口run_launch_allocation_reference_checks(client,admin,headers,database,cases,*,object_root,registry,user_fixture)。主线需through038、USER8夹具及既有034同profile的子进程/父registry显式注入；没有cipher/password/cache参数。对象根只接受本backend/.runtime/integration-objects/run-*/materials且逐级拒绝链接/reparse；本工具不创建服务、实例、额外对象根或自动清理主线资源。

工具先经现系统配置HTTP创建/更新MATERIAL_SCANNER（只选受控profile），对USER同团队两人以公开角色API建本轮素材/launch动作角色，再仅在本轮SQL夹具绑定。三份安全PNG用typed对象分片/assemble、SCANNING+真实actor授权快照入队，由ConfiguredMaterialWorker实际扫描处理，读取030/034配置来源与真实CLEAN收据，工具没有INSERT CLEAN/receipt/proof。

8组：真实三PNG配置扫描证明；安全metadata与真实版本捕获；同团队不同USER不可见及当前assets.read撤权；实际asset散列与原真实收据不符时拒绝（只在回滚事务临时改asset，不篡改不可变收据）；source1<head3完整runtime发布实际ALLOCATION引用；旧新池替换中MATERIAL_REFERENCE_ADDED审计触发1644使引用/items/active/头/双clock/audit/outbox完整回滚；重试释放旧精确ALLOCATION并登记新used素材、保留显式历史种类fixture行；原键重放与旧claim均不重复引用审计。

本轮平台authority明示ISOLATED-SQL-CAPABILITY-NOT-META，自身精确guard实际URL127.0.0.1:13306及同UUID库。账户/身份/兼容图不证明Meta；历史引用行仅用于保留种类协议测试，不冒充真实广告历史证据。工具6项护栏纯测0.37秒及Ruff通过；8真实组未运行，需主线串行排队后才有实际结论。


## 最新真实限定结果（2026-11-08）

主线已实际执行32/32 PASS，13.00秒，回执evidence/python-allocation-reference-bridge-http.json（2026-11-08T13:55:02.895841Z）。其中配置扫描10组、USER8组、桥8组及初始化/退出6组。桥8原具名断言均实际完成：三份PNG经正式配置消费者真实扫描形成030/034来源；当前双方权限/USER隔离、收据与asset散列不符拒绝、source<head运行时接力、真实活跃引用、1644替换审计回滚、精确释放/只登记used、历史种类fixture保留与重放无重复审计。

该回执不证明Meta真实兼容图/账户写授权或生产Authority已实现；本轮IsolatedSqlAuthority只为本机UUID库提供协议能力。没有平台写入、没有自动注册生产Provider。27纯测/6工具护栏与32真实链为不同证据层，均不代表整个投放/素材模块验收完成。现生产源和工具继续冻结供主线提交。
