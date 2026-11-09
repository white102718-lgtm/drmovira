# 原execute真实C素材桥

本阶段只实现内部桥和纯协调协议测试，尚未注册生产Provider、执行真实SQL或声称素材跨execute业务验收。原Store、公共C模块、旧分配Provider及039迁移均未修改。前一隔离原execute38/38成功只证明SQL样本协议；当前桥用于补真实C来源，不把这两者混为同一验收。

## 独占文件及接口

`python/orbit_api/launch_execution_material_bridge.py`：

- `ExecutionMaterialBridge.capture_materials(session,current,source) -> ExecutionMaterialCapture`。调用方开启短事务；先当前launch.execute，无额外launch.edit/read/Task动作；非空素材池复用C双方assets.read及当前范围。返回不可变完整真实描述字节，不保存用户可变dict。网络采集须在此事务关闭之后。
- `lock_for_accept(session,current,source,capture,prepared) -> ExecutionMaterialTicket`。放在Provider.revalidate来源阶段：权威账户/身份等来源锁之后、launch clock/head之前；全池排序、最多500、200分批重取C锁，逐字段核冻结描述。纯PreparedExecution实际DAG used集合必须精确等于material描述集合，used必须在全池内；真实名称不作为素材元数据。返回绑定本Bridge实例、本事务、tenant/actor/current、配置source hash/revision、owner/team、完整manifest hash及used集合的票据。
- `publish(session,current,source,prepared,ticket,task_id,request_id)`。只接受session.info实际登记的同对象票据；跨事务、复制票据、租户/actor/owner/来源/used/manifest变化都拒绝，且在任何C发布调用之前失败。按used升序200分批调用真实`register_active_material_references(...,'EXECUTION',...)`，结果必须完整。C会重入已有锁、核真实资格，实际引用/素材审计/outbox与原accept外事务同笔提交；成功消费票据，不能重放票据。

空池仍要求原launch.execute，但不调用C上下文或强制assets.read。它不是原execute业务可用性的承诺；原纯清单/能力规则仍决定计划是否允许无素材。

## 真实来源与锁顺序

复用 `material_references.py:83` 的caller与计划owner双方启用身份、同租户/团队、assets.read交集；`:116`完整素材读取持material clock及升序资产行锁，核READY/LIVE、真实版本/SHA及当前030 receipt与034 runtime proof。`material_security.py:13`与`material_antivirus_sql.py:8`绑定DONE job、claim、对象SHA/大小、CLEAN及完整扫描时证明链；没有自行增加“读取时全局TTL”。桥不填零、不把READY或verified布尔当CLEAN。

不能直接复用 `ReferenceBackedAllocationProvider._capture`，因为该分配入口明确需要launch.edit。也不能复用它裁剪后的material_metadata，因为execute描述需要id/owner/原字段名与实际尺寸/时长。桥仅做规范Decimal时长处理，保留完整执行描述及资格字段；原素材名字不进入描述。

合法调用链为：当前原execute授权 → authority来源锁 → 本桥全部C锁及票据 → launch clock/head → 038/allocation/name → Task/prep → 本桥publish重入C锁 → acceptance/审计/outbox/幂等。桥本身不通过数据库锁表“猜测”调用者是否先锁了head；保证来自受控Provider.revalidate钩子的固定调用顺序及C登记接口同事务锁票据要求。实际组合Provider和并发SQL必须专项验证，不能仅凭注释宣布全局锁序已实测。

## 验证与缺口

独立21/21纯协调测试通过（0.97秒），Ruff与格式通过。包含完整描述、同事务登记与单次消费、租户/actor/owner/source hash/revision/used/manifest/Bridge/事务/登记身份绑定、素材变更、READY但无完整C资格、空池、500项全局升序200/200/100分批及动作上下文变化。C读取/发布均为替身，所以不计030/034真实来源或双方权限已验。

下一真实SQL桥至少需要：真实C扫描流水与proof生成的READY/LIVE素材；caller可读但owner不可读、两方撤权、旧READY无receipt、receipt/proof缺失或版本/SHA/尺寸变化；超过200项排序；跨事务票据；无预持C锁不可晚补；EXECUTION引用与C审计/outbox1644令原accept全回滚；成功后引用阻止错误归档。由主线统一构造和串行运行，不自行开服务。

本桥没有账户即时授权、identity capability、真实META政策/能力、指标registry与source hash、实时SSRF验证或平台执行器。未来受控ExecutionAuthorityProvider必须组合这些权威来源，不能因C桥实现就把正式None改成可执行成功，更不能复用隔离FIXTURE资料成为生产authority。

## 专属真实工具准备（未运行）

新增 `tools/launch_execution_material_bridge_checks.py`，导出`EXECUTION_MATERIAL_BRIDGE_CASES`六组及`run_launch_execution_material_bridge_checks(client,admin,headers,database,cases,*,object_root,registry,user_fixture)`。child类`IsolatedMaterialExecutionProvider(session_factory,control_dir=None)`仅ISOLATED_TEST，先真实13306/UUID检查，capture用本桥完整C描述、当前版本与实际SHA；revalidate在Store取得launch head前登记同事务票据，publish实际调用C写引用、素材审计/outbox。搭配专属`IsolatedExecutionValidationProvider`在首次validate冻结网站来源；不改冻结旧工具。

真实前置沿既有C桥方法：实际PNG字节写LocalMaterialObjects分片并assemble，真实SCANNING/job经ConfiguredMaterialWorker处理，明确核030/034完整CLEAN资格，再真实HTTP validate→execute。它不声称HTTP上传页面已验。Worker有界处理最多20个队列条目，必须实际找到本组对象并READY，不假设原租户队列为空。对象根必须主线当前隔离run根、禁止链接，最终清理由主线完成。

六组计划分别是：真实扫描证明；原HTTP202完整Task、真实EXECUTION引用及source1/validated head2/submitted head3；caller(root)可读但plan owner不可读的交集拒绝；owner实际assets.read撤销/精确恢复；当前034 runtime proof hash损坏/精确恢复拒绝并零Task；真实素材outbox1644使引用/计划CAS/acceptance同笔回滚。不是500真实扫描容量，500分批仅原21条纯协调测试范围。

工具guard六条纯测试通过（1.39秒），包含目标库拒绝与真实FRAMEWORK cwd/plain module导入，Ruff/格式通过。真实SQL/HTTP尚未运行、没有六组成功回执，不标跨execute C桥验收。正式AuthorityProvider仍None。

首真实档启动前主线批准第4组补caller自身撤权：从其真实assets/capabilities取得会话CSRF，保留launch.execute但删除全部assets.read映射，caller请求须403且零Task；root代读同计划须因owner无read返回404且零Task，finally精确恢复映射。不借launch.read/edit，不增加具名组数。定点后guard6/6通过（1.94秒），Ruff/格式通过，工具再次冻结待主线30档。

## 最新真实检查点

主线已串行完成首真实30/30（12.73秒），回执`evidence/python-execution-material-bridge-http.json`。六个新增组实际通过：真实030/034 PNG证明→原HTTP202完整Task及实际EXECUTION引用/source<head；双方素材范围交集；caller与owner assets.read即时撤权/恢复；真实runtime proof损坏拒绝；素材outbox1644令原accept整体回滚。既有隔离Meta能力/身份/FIXTURE归因仍未成为真实平台authority。

生产Bridge和专属工具继续冻结。500项排序/200分批及跨事务票据拒绝仍仅纯协调测试范围，不抬成500文件扫描容量或跨进程实测。未进行真实Meta能力/政策/身份授权核验、指标真实来源采集、SSRF生产预检或任何平台广告写入，生产默认None/发送缺口保持明确。
