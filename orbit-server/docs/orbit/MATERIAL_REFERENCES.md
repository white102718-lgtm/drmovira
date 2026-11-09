# 素材内部引用合同与验收台账

本阶段仅新增内部服务接口，不注册HTTP、不授予计划权限，不实现分配算法。
历史证据仍由既有引用表阻止物理回收；写入历史证据需要未来任务服务的不可变manifest、原拥有者和证据身份合同。

## 调用顺序

1. 计划服务校验当前原业务动作、可见计划；从服务端DB无锁预读旧分配业务键及revision/input_hash。
2. 开启同一外层事务，调用 `lock_active_material_reference_set(session, context, kind, resource_id, additional_asset_ids=new_pool)`。
3. 此接口锁素材clock，从真实引用表读旧活跃引用，按旧新素材并集UUID升序锁素材，再锁精确引用。旧池最多500、新池最多500；禁止传前端伪造旧引用集合。
4. 新池按全局UUID排序，以不超过200项分块调用 `require_allocation_assets`。这是双方当前assets.read、租户、拥有者/显式管理团队交集及READY/LIVE、版本、摘要复核；预锁新池本身不授予读取权限。
5. 计划服务再锁launch clock/plan/旧allocation，CAS原revision/input_hash并复核真实能力包。失败必须回滚整事务。
6. 成功后使用本事务精确票据 `deactivate_locked_material_references` 释放旧ALLOCATION/EXECUTION，再 `register_active_material_references` 登记新引用，最后由计划服务提交。

只取消时无需新池，无需旧素材仍READY、旧拥有者仍有素材权限。取消保留历史行并置active=0，不触碰HISTORICAL_EVIDENCE。票据绑定实际事务对象、actor、tenant、kind、resource以及精确ref/asset集合；复制或跨事务复用拒绝。

所有引用变更审计实际before/after，写outbox和素材clock同事务，不在内部commit；登记已活跃的同业务键引用幂等，不生成重复审计。

## 安全元数据和未闭合项

返回id、revision、名称、归属、kind/state、sha256/mime/size、宽高、十进制定点字符串duration或null、物理状态。无对象路径、上传对象ID、凭据、签名URL。

原PRD的READY要求完整可用；旧媒体处理直出READY尚缺真实杀毒证明。026接入后，接口仅在当前DONE job同claim、对象hash/size及完整CLEAN扫描证据匹配时返回素材侧 `antivirus_status=CLEAN`、`execution_eligible=true`；旧READY无证据仍UNVERIFIED/false，登记活跃引用409。素材侧门禁不替代计划动作、真实账户能力包约束和全局分配可行性验证，不能据此声称整个计划可执行。新真实Worker/SQL回归尚待主线排队。

024仅增加 `(tenant_id,kind,resource_id,active,asset_id,id)` 索引供旧分配反查；既有asset方向索引继续服务归档/清理。专项要求实际EXPLAIN按该索引ref定位且无filesort，但小夹具执行计划不证明大数据容量。

## 分阶段状态

- [x] 内部批量交集、冻结版本/摘要、安全元数据、显式未杀毒门禁代码。
- [x] 同事务精确引用登记/释放、旧新并集锁顺序、票据、审计/outbox代码。
- [x] 首批55项独立单测通过；接026门禁后新增旧READY拒登记，当前56项通过；Ruff检查和格式通过。
- [x] 024独立索引迁移源码及8组真实专项工具已准备。
- [x] 升级AV前024真实迁移/EXPLAIN及8+5组引用专项通过，主线回执 `python-material-references-http.json` 共27项（含初始化和人员fixture）。
- [x] 升级026后，8组内部服务及5组多身份专项局部通过；实际PNG对象+真实扫描Worker及旧READY拒登记已复验，来源为整体失败回执 `python-material-antivirus-security-attempt-01.json`；不代表后续legacy边界或整轮通过。
- [ ] 多身份actor/target各方撤权、真实并发替换CAS及死锁矩阵。
- [ ] 计划服务端到端引用登记/取消、真实能力约束和严格执行验收。
- [ ] 真实杀毒后READY、扫描证据与执行许可；仍按待修缺口处理。

内部工具 `run_material_reference_checks(admin,database,cases,*,scanner,object_root)` 仅接受本机13306且匹配当前UUID隔离库。当前两个安全PNG通过真实本地put/assemble、扫描Worker生成READY和receipt；legacy READY无证明分支不可登记。工具不代替HTTP上传或计划发布验收。
