# 下一有界闭环：500拥有者与历史只读来源

当前渠道改动及既有工具继续冻结。以下为接力实施方案，不是完成证据；只读核对后记录，等主线当前全量结束再修改受测源。

## 先完成：500名有效拥有者跨候选页分配

原SharedOwnership.data_owner_user_ids允许1—500；当前真实负例验证了空、重复、501和失效成员，但没有500个不同有效成员正例。ownership-options每页最多200，前端已有“加载更多”并累加候选，拥有者选择器尚未collapse-tags，500个tag会使表单很长。只证明HTTP接收500还不能结清UI分配能力；只证明LIMIT200不能结清容量。

首个完整交付限制为一个隔离测试租户下的一个新团队、500个有效已激活本地身份、一个可见产品/总代、一个渠道：

1. 新专属临时DB工具按现有fixture方式创建受控500人，无真实邀请/邮件，先检查随机原若依ID区间无占用。实际sys_user、orbit_user_scope、orbit_business_user及团队状态满足现有生产查询，不为通过移除候选过滤。所有成员UUID、native ID与来源属于专属临时库，测试退出恢复临时角色/管理团队授权。
2. 通过原受控导入API给产品和总代分别设置这500个真实拥有者，导入预检/提交都接受真实500集合，审计版本完整。不能把JSON直接写渠道主表来冒充创建成功。
3. HTTP实测ownership-options至少3页，不重复、不漏人；渠道create/assign/get/display-labels均核500个精确UUID/500个可读名称，事件/归属/版本一致。第501个有效人加入时422，整事务无部分写入；其中一人跨组/停用，整批拒绝，恢复后合法成功。
4. 最小前端改造仅在原分配/新增弹窗增加“选择当前团队已加载用户”及当前加载/选择数量提示，明确只合并已加载且同团队候选，绝不偷偷选择尚未加载的人，不静默截断超过500。复用原加载更多，让用户真实加载3页再选500；不需要浏览器点击500次，也不延长普通闭环超时来掩盖不可用交互。
5. Element Plus选择器使用collapse-tags及tooltip，让500项不会挤出屏幕；名称回显从已有真实labels/候选读取，已分配但尚未加载项不得当成不存在。普通USER只获得原API允许的本人候选，批选按钮不能扩权；团队管理员只收到明确管理/本人范围，后端仍复验。
6. 浏览器由主线传专属fixture描述（团队名称/产品名称/总代名称/预计500 IDs的摘要），只用页面真实加载候选、批选、填原因、提交、重新打开及详情读取；DB仅构造身份资料，不代写被验业务操作。三个视口核弹窗边界、500总数和mobile文档无溢出。

需要的真实用例分组：候选三页集合；500引用原子预检提交；500创建/分配/详情/labels；501原子拒绝；失效混合成员原子拒绝；USER/TEAM权限不扩集合；三视口加载/批选/提交/重读。仅作为500字段边界验收，不命名为50k/1m容量压测。

候选稳定ID：SCHEMA-SharedOwnership.data_owner_user_ids、SCHEMA-ChannelWrite.ownership、SCHEMA-OwnershipAssignment.ownership、CHN-04及分配API。SharedOwnership被多模块复用，单线通过仍不结清其他模块共享合同。

## 再完成：历史锁定从真实来源迁入，而非永远依赖测试SQL

只读搜索当前Python源码：product_locked仅在009中默认0、channel_store读取/拒改；没有历史包约束导入/同步生产入口。现有真实HTTP工具通过直接设置锁定夹具验证拒改，新的前端挂载测试验证只读解释；这两者证明锁定消费逻辑，不能证明真实旧数据迁移。新浏览器对自行创建未锁定渠道显示“当前未锁定”，也不能代表带历史包约束的真实迁入案例。

最小技术方案是受控迁移manifest，不恢复马甲包/产品完整菜单，不增加用户“解锁历史”按钮：

- 只读提取旧渠道UUID、产品UUID及历史包关系的原始稳定ID，附来源库/导出版本与SHA256；先对照实际参考仓库数据结构/可用旧导出，缺少源数据则明确阻断真实迁移，不能编造旧包关系。
- dry-run逐项核同租户、渠道当前product匹配、资料存在、同键幂等和源绑定唯一；出现错绑/重建UUID/旧快照差异直接报告，不自动改当前产品或重写计划快照。
- 审阅后commit按当前渠道CAS和manifest hash锁事务，只允许product_locked从0到1，保留渠道/产品原ID、现有投放链接、原快照；原子追加来源审计。无自动解锁、无硬删除；同一来源重复导入一次结果，冲突来源报错。
- 主线先验证内部最小迁移fixture的dry-run/拒绝/原子commit/重放及失败回滚，再浏览器只读详情/编辑确实锁定且换产品提示新建。原fixture需明确“历史资料初始化”，页面操作仍通过UI验证，不以DB代写假冒维护功能。

是否需要新增独立受控迁移接口或运维CLI，应在读清真实旧源及当前迁移实施文档后定案；本节点不擅自创建新的对外入口。候选CHN-03/CHN-09/FR-CHN-02在真实源迁移和跨模块历史快照对账前继续IN_PROGRESS。

## 内部alias冻结接口与A020

新增vendor_alias_snapshot.freeze_vendor_alias_snapshots只读helper已实现，不注册HTTP，不改在测alias resolver。它重新验证accounts.import/assign原动作、完整BusinessContext不漂移、当前tenant真实受锁VENDOR与调用者已验证行fingerprint一致、AVAILABLE及readable交集，然后集合读取真实alias共享锁。Worker可显式acting_subject=False但仍做当前授权。调用者负责原动作目标owner/team交集并在同事务写020不可变快照/原审计；helper不提交也不落库。

21纯测试验证撤动作/范围/版本/来源/状态漂移和TEAM显式管理，不计A020落库验收。HTTP当前读仍沿原accounts.read或维护分支，import-only冻结能力不能变成新的数据读取入口。

## 已实施的500成员节点与剩余真实UI验证

主线27485专属真实专项已23/23通过，其中新9组见`evidence/python-channel-owners500-http.json`，证明500个不同有效目标成员、三页候选精确并集、500引用预检原子提交、500渠道创建/详情/列表/名称回显、TEAM500分配与USER本人交集、501/外域/停用/移属整笔拒绝、撤管理范围成功键重放拒绝、审计失败全回滚后原键恢复。第9组同时证明TEAM未明确管理自己所属团队时可选本人、同团队peer不可选；生产候选predicate已修为仅本人OR明确管理团队，仍叠加原租户/启用/激活条件。

前端两处拥有者多选已支持折叠tag/tooltip、已加载与已选计数、当前团队已加载候选合并选择、串行加载与去重。批选501时明确拒绝并保留原集合，不截断、不自动选下一页。9个挂载测试包含新增三页200→400→500和501保持原400的行为，类型/格式通过。独立`orbit-python-channel-owners500.spec.ts`要求主线提供安全manifest本地文件，UI读取、跨3页加载、批选、创建/分配响应500精确集合及真实详情均待主线三视口验证；此处尚不勾UI验收。

历史来源额外只读核对：参考adpulse-power-system的`adpulse-main/.../V9__create_channel_management_tables.sql`中media_channel的类型为代理商/号商，字段是结算/账户供应商，不是ORBIT APP/WEBSITE/OTHER的投放落地页渠道；schedulers/scripts/fb_ad_channel.sql也是同一供应商语义，没有product/历史马甲包关联。`ChannelMigrationMappingResolver.java`可借鉴来源/目标指纹、账本hash和冲突映射拒绝策略，但不能将其media_channel ID直接当ORBIT渠道/产品绑定，更不能据表名猜product_locked。当前没有可证明原ORBIT马甲包绑定的实际旧导出，仍需明确源数据或受控manifest，并保留真实迁入阻断，不伪造来源。
