# 生产预检、提交与任务控制实施设计

本文为下一阶段的实施设计，未代表功能已开发或验收。仅整理原契约、现有接口边界与待核对的技术补充；本次不修改生产代码、迁移或公共注册。

## 1. 依据与当前边界

权威依据均位于 `data/ORBIT_Codex开发PRD`：

| 依据 | 约束 |
| --- | --- |
| `contracts/API_SEMANTICS.md:7`、`:11` | 严格结构、字段指针、If-Match、CSRF、幂等；202仅表示受理 |
| `contracts/WORKFLOWS.md:21`、`:25` | 单租户/团队/投手/币种；完整分配、固定种子及版本；不得部分匹配 |
| `contracts/WORKFLOWS.md:60`、`:101`、`:103` | 状态CAS与revision递增；规范预检hash、15分钟/上海午夜失效；名称和同计划版本单Task |
| `contracts/WORKFLOWS.md:66`、`:68`、`:73`、`:111`、`:117`、`:127`、`:137` | 命令/DAG状态、UNKNOWN、对账、完整manifest、人工恢复 |
| `contracts/PERMISSIONS.md:18`、`:26`、`:36`、`:38` | 冻结投手所有权、当前资源交集及独立动作权限 |
| `reference/03_原合同保留章节.md:598`、`:599` | validate需要launch.edit；execute需要launch.execute |
| `contracts/ADSPOWER_WORKFLOWS.md:77`、`:79`、`:82`、`:157` | Task/DAG/命令/outbox完整；即时身份核验；写意图先持久化；不可变执行manifest |

现有代码可复用，但有明确边界：

- `launch_contract.py:385`已有ValidatePlan/ExecutePlan解析器，未构成生产接口闭环。
- `launch_references.py:45`身份/配置绑定缺少权威来源时503，`:235`指标配置依赖缺失时503；不能用任意字符串版本替代来源。
- `launch_allocation_runtime.py:31`定义AllocationProvider三阶段协议，`:99`没有生产provider时503；公共Allocation的task_id仍为null，内部runtime ID不是Task。
- `launch_naming.py:348`现核验函数硬依赖launch.edit，不能直接借给execute并暗加edit权限。
- `task_manifest.py:30`仅允许隔离测试生产者；`:47`要求当前head等于源版本。033仅允许ISOLATED_TEST，035补全完整DAG头。这些不证明生产execute可用。
- T1已验证真实持久读模型及十万节点，T2已验证事件读取/授权/完整性；尚无生产预检、执行受理、写命令和Task控制验收。既有成功证据不能转记到本阶段。

## 2. 原HTTP合同保持不变

下表路径均以 `/api/v1` 为前缀。所有写请求遵循原幂等、CSRF、If-Match及当前权限要求；不新增 `/preflight` 别名。

| 路径 | 请求/响应 | 权限与语义 |
| --- | --- | --- |
| POST `/launch-plans/{id}/allocations` | AllocationRequest →202 Allocation | launch.edit；可能仍在求解，不是Task |
| GET `/launch-plans/{id}/allocations/{allocation_id}` | 200 Allocation | 当前授权及来源范围 |
| POST `/launch-plans/{id}/campaign-names` | 无body →200 NameReservation | launch.edit；固定命名日/配置源版本 |
| POST `/launch-plans/{id}/validate` | `{allocation_id,name_reservation_id}` →200 PlanValidation | launch.edit；真实完整预检 |
| POST `/launch-plans/{id}/execute` | `{hash,activate_ack}` →202 Task | launch.execute；需要激活时另核launch.publish及确认 |
| POST `/tasks/{id}/cancel` | `{reason}` →202 Task | tasks.cancel；不能假称已取消平台写入 |
| POST `/tasks/{id}/retry` | `{node_ids,reason}` →202 Task | tasks.retry；1..500个原节点，安全失败才可重试 |
| POST `/tasks/{id}/resume` | `{reason,binding_revision}` →200 Task | 原表未列独立resume权限，见第7节待核对映射 |

原OpenAPI定位：validate `openapi-current.json:8790`，execute `:9035`，ValidatePlan `:37388`，PlanValidation `:37406`，ExecutePlan `:37491`；cancel `:14507`、retry `:14752`、resume `:34819`。

PlanValidation严格保留十个字段：`valid/hash/expires_at/errors/campaign_count/adset_count/ad_count/budget_totals/scope_version/total_dag_node_count`。不加入revision字段。业务条件不满足时返回真实errors和计数，valid=false、hash/expires_at=null；缺少权威来源返回503，不用valid=false及虚构零计数伪装完成检查。

## 3. 配置源版本与状态CAS接力

### 3.1 需要解决的问题

原合同同时要求：状态流转revision+1，分配/名称/hash绑定plan_revision。若validate把head递增后再用head比较分配版本，会令刚成功的预检立即失效。现TaskManifestStore的head==source检查也不能直接用于状态流转后的生产提交。

建议引入以下内部术语，外部Plan.revision仍为原CAS字段：

| 内部字段 | 含义 | 变化条件 |
| --- | --- | --- |
| source_revision | 真实不可变PlanVersion配置源键 | 保存配置或所有权等影响执行输入的内容时变化 |
| head_revision | 对外Plan.revision，状态与内容的CAS头 | 原合同规定的每次有效流转递增 |
| validated_head_revision | 本次validate成功后的CAS头 | 记录预检接力，不替换source_revision |
| source_payload_hash | 对应PlanVersion真实配置摘要 | 防止错引用或损坏，不能代替完整预检hash |

**这是主线已核定的内部技术映射，原Plan对外仍只有revision，不增加第二个公开字段。** source_revision为不可变配置锚点，head_revision每次状态CAS递增；名称/分配不复制或重绑。内部命名不应写成原合同新增字段。

原WORKFLOWS:101的canonical键仍为`plan_revision`，其值取内部source_revision；不把内部术语改成hash字段名，head_revision不进入配置hash。FrozenValidation内部字段仍名为source_revision，便于Store明确区分CAS头。

### 3.2 有界接力示例

1. 保存配置：head=1、source=1；分配及名称均冻结source=1。
2. validate以If-Match="1"核验全部来源，成功CAS为VALIDATED、head=2；validation冻结source=1、validated_head=2和原名称/分配引用。
3. execute以If-Match="2"重验当前授权、预检有效期及来源，成功CAS为SUBMITTED、head=3；Task来源仍为source=1。
4. 单纯状态变化不改名称、分配、素材版本和canonical hash内的配置源引用。不得把head=2/3自动当成新配置版本、重新随机分配或重新命名。
5. 配置变更产生新的真实配置源版本，旧预检不可用于新配置。先验证其真实PlanVersion，不用状态head猜测或回填一个“已验证”源。

validate响应没有revision字段。主线决定客户端通过原GET重读head；不增加ETag或body字段、不让客户端自行计算head+1。

原历史版本读取保持不变；旧记录仅在真实PlanVersion、payload hash和归属能够对应时建立源关系。不能按当前head批量回填旧VALIDATED为已核验。主线采用候选落地方式：不增加plan.source列，持head锁后以现有PlanVersion复合PK逆序LIMIT 1取得最新真实配置源，先界定payload大小，再核source<=head、payload_hash、归属与当前配置一致；状态变化不插入伪配置version。validation单独保存source与接受head。独立launch_plan_source.py及038迁移/公共Store由主线负责，本纯模块不修改这些文件。

## 4. 生产权威来源与锁序

先实现内部只读AuthorityProvider，禁止任意HTTP客户端发布“verified=true”的证据。证据必须来自真实已配置来源及可校验版本，至少包括：

- 调用者/实际投手当前权限与团队交集、真实scope_version；所有账户启用/绑定/币种/IANA时区及到期投影守卫。
- 当前账户下Page、Pixel、Application、转化事件与对应目标能力，真实授权版本、来源配置revision、已知到期/撤销状态；identities GET观察不能充当写授权。
- MATERIAL当前CLEAN证明、sha256、mime、尺寸/时长、不可变revision，以及本账户/目标能力的兼容性依据。
- Capability/Policy/指标配置的权威版本及evidence；渠道/产品当前快照；ADSPOWER_UI还需真实绑定revision和已核验环境能力，不自动切换通道。
- URL安全探测真实结果；重定向、DNS重绑定、内网/元数据地址不得被绕过。未知或无法验证的组合不可用。

建议capture外部只读证据时不持数据库长锁，记录版本指纹；最终事务按既有来源clock/排序资源锁→launch clock→plan行→预检/manifest→Task/命令的统一顺序重新核验。具体跨模块锁顺序需与B/C现有接口逐一确认，不能只靠口头约定。网络请求不得置于持锁长事务内。

可直接研究复用：`launch_references.validate_sources`、`AccountScopeStore.resolve_for_plan`、`material_references.require_allocation_assets`及active reference事务ticket、AllocationProvider.capture/prepare_publication/publish_references。需新增的实时平台权限及能力provider仍是缺口；现account_platform仅只读账户元数据，不具备这些接口。

## 5. validate最小实现闭环

1. 严格解析原请求、头和字段指针；当前launch.edit+菜单+对象范围。成功幂等回放先核当前权限与范围，再处理原成功结果，不能先因旧If-Match拒绝成功重放。
2. 取得真实source版本及所有权；核分配SUCCEEDED、完整slot映射、名称保留及当前上海命名日。allocation input_hash、graph_hash、payload_hash分别保留用途，均不冒充PlanValidation.hash。
3. 完整验证：1..500账户、素材<=500、单投手/团队/租户/币种；每层<=10000、总DAG<=100000；identity条件必填与各账户授权；互斥预算与Decimal精度/上下限；时间、CTA/创意/URL、能力与素材兼容。
4. API_SEMANTICS规定的AD无预算、DAILY/LIFETIME互斥、LIFETIME结束及366天上限等逐项落实。新建预算不凭空构造旧预算0应用变更比例；新对象验证后的初始预算建立基线。
5. 按WORKFLOWS:101完整canonical字段构建服务器SHA256；集合排序、配置树兄弟顺序保留、金额字符串、UTC时间固定。hash覆盖source版本、完整展开树、分配、名称、能力/策略/scope、渠道/产品、币种和激活选项。
6. 数据库UTC确定expires_at=验证时刻+15分钟，同时保留上海业务日；到时或跨上海午夜均失效。保存不可变证据引用、实际计数/预算、输入摘要，并CAS状态/审计/outbox。
7. prepared DAG可以分块构建，但未完整密封前不能受理可执行Task。预检、准备完成与公开状态关系需在实现前核对：不得因后台准备尚未完成仍声称可以execute。

开始时间须在实际发送时再次满足至少+5分钟；预检通过后排队变旧不能沿用旧结论发出。预检不授写权限，验证成功也不等于发送成功。

## 6. execute、完整manifest与可靠受理

execute只要求原launch.execute及当前对象范围；activate_after_create为true时再核launch.publish、activate_ack及二次确认。不得为复用函数而额外要求launch.edit或launch.read。名称核验应拆为接受已授权动作context的内部函数，公共campaign-names仍保持原edit门禁。

execute原子事务至少包含：

- 锁定当前CAS head、source、validation记录；核hash、时间/上海日、当前来源/权限、kill switch与资源证据。
- 核已完整密封DAG的源、节点/边/配置hash、计数、预算、分配和名称引用；冻结实际owner/team及执行证据。
- 按tenant+plan+source版本唯一接受一个Task；同版本并发不同幂等键也不得产生第二Task。同键异payload409，成功重放返回原202及同一Task，仍先核当前权限/范围。
- 发布Task可查询首200节点及真实node_count/cursor，完整命令依赖、审计/outbox、Plan状态CAS及幂等回执同事务成立；事务失败全部回滚。

十万节点不得在execute单事务重新展开/插入全部数据。建议新建私有prepared manifest分块密封，再在execute短事务切换可见性并绑定Task；**这是待实施的存储技术方案**。现033节点/manifest FK及唯一键不能仅把ISOLATED_TEST改名TRUSTED就满足该方案，需独立DDL与崩溃清理设计。202后不能GET404或返回空占位Task；内部runtime ID不得冒用Task ID。

执行器另阶段落地：共享目标锁、预算预留、队列lease/fence，发送前当前动作权限/授权/来源/kill switch重验，WRITE_INTENT先持久化后单次发送；不确定提交保持UNKNOWN，readonly回读证明前不重发。配置SUCCEEDED不等于广告ACTIVE，ENABLE为独立节点。

## 7. Task控制及恢复权限

| 动作 | 最小实现要求 | 原依据/待核对项 |
| --- | --- | --- |
| cancel | 仅取消可证明未提交节点；已成功不回滚、UNKNOWN不改为未发送；CAS/审计/outbox/幂等 | WORKFLOWS:68；原202 Task |
| retry | 仅请求中1..500个原安全失败节点；成功节点不重建，用户取消不复活；当前权限及目标资源重验 | tasks.retry；WORKFLOWS:68、:117 |
| resume | 仅NEEDS_HUMAN且未提交挑战；核binding_revision、真实环境、锁、当前权限及预览/指标有效期 | WORKFLOWS:137；原200 Task；主线已登记技术映射为tasks.retry（安全重试未提交挑战），不新增tasks.resume或暗借edit |
| 对账 | 原reconciliation-cases创建/claim/decision流程；另一tasks.reconcile人员审核，唯一外部ID/请求关联/回读证据；证据不足仍UNKNOWN | WORKFLOWS:111、:117；原201 ReconcileCase、claim/decision 200，不发明/tasks/{id}/reconcile别名 |

Task拥有者是冻结plan/suggestion投手，created_by仅审计。控制动作不能复用硬要求tasks.read的GET授权函数来增加权限；按原launch菜单、对应动作、冻结拥有者范围及当前执行资源分别核验。撤权即时阻止新发送/重试；不因Worker身份绕过。

## 8. 可独立开工的模块边界

| 模块 | 独立交付内容 | 依赖及接入边界 |
| --- | --- | --- |
| V1 AuthorityProvider | 严格证据DTO、真实只读采集接口、来源指纹/撤销重验、缺依赖503 | 可先做协议及负例；真实adapter需权威registry，不能fixture升格生产 |
| V2 版本接力/预检 | source/head关系、canonical hash、15分钟/上海日、原ValidatePlan与响应、事务审计 | 先核第3节技术补充；依V1和真实allocation/name；公共路由由主线注册 |
| V3 生产manifest受理 | 私有分块准备/密封、execute短事务、真实Task/命令/outbox、同源唯一与崩溃恢复 | 依V2；独立迁移申请，保留T1隔离producer边界 |
| V4 命令执行安全层 | lease/fence/目标锁/预算预留/WRITE_INTENT/真实readback/UNKNOWN | 依V3及真实通道adapter；与预检读模型分开验收 |
| V5 Task控制 | 原cancel/retry/resume及reconciliation流程，CAS/幂等/逐节点安全判断 | 依真实命令/尝试日志；resume复用tasks.retry，不新增假状态端点 |
| V6 前端完整流程 | 分配/名称→预检字段错误→确认提交→真实Task状态/控制弹窗 | 按原SDK和响应；无后端依赖时明确不可用，不展示模拟成功 |

共享修改清单须先审阅：原名称内部action context、生产provider注入、source/head迁移、公共路由/权限映射及客户端ETag读取。独立模块不能自行修改公共入口或复用其他线受测文件绕过流程。

## 9. 逐项开发、测试、验收台账

以下全部为本阶段待办。三列分别记录代码完成、针对性验证、需求验收；仅文档存在、纯测或隔离fixture成功不能代替生产来源验收。

| 编号/交付项 | 开发 | 测试 | 验收 | 必需证据 |
| --- | --- | --- | --- | --- |
| V01 严格原路径/字段/头/错误指针 | [ ] | [ ] | [ ] | 原DTO逐字段、未知字段400/边界422、CSRF/If-Match负例 |
| V02 source/head CAS接力及历史兼容 | [ ] | [ ] | [ ] | validate后名称/分配仍有效；execute接新head；配置改动失效；并发CAS与回滚 |
| V03 当前caller/投手/资源交集 | [ ] | [ ] | [ ] | 三角色、仅execute无edit、仅控制无read、转属/撤权/foreign拒绝 |
| V04 权威身份/能力/策略/渠道来源 | [ ] | [ ] | [ ] | 真实版本/撤销/到期；无provider503；GET观察不冒写授权 |
| V05 分配完整性与素材证明 | [ ] | [ ] | [ ] | 全局兼容、禁重复/允许重复、CLEAN及版本变化、全量映射与活动引用回滚 |
| V06 名称冻结与午夜 | [ ] | [ ] | [ ] | 同source重放不改名；上海边界前后；状态递增不使引用失效 |
| V07 预算/币种/创意/时间逐字段 | [ ] | [ ] | [ ] | Decimal、预算归属/互斥/上下限、CTA/身份条件、DST、实际发送+5分钟 |
| V08 URL探测与素材安全 | [ ] | [ ] | [ ] | DNS/重定向/私网/元数据拒绝、真实sha/mime/扫描证据 |
| V09 canonical及PlanValidation十字段 | [ ] | [ ] | [ ] | 集合排列等价、树序差异、金额/UTC、业务invalid真实计数、15分钟/午夜精确边界 |
| V10 分块完整manifest与202可查询 | [ ] | [ ] | [ ] | 崩溃/缺块/hash错/半发布拒绝、真实首200及分页、受理前完整性 |
| V11 execute幂等/同source唯一 | [ ] | [ ] | [ ] | 同键/异键并发、旧If-Match成功回放、异payload409、撤权后不泄漏原Task |
| V12 原子命令/Task/审计/outbox | [ ] | [ ] | [ ] | 任一故障全部回滚、唯一请求关联、重复消费者不重复写入 |
| V13 激活确认和publish拆分 | [ ] | [ ] | [ ] | 默认暂停、无publish拒绝、未确认拒绝、VERIFY后独立ENABLE |
| V14 执行/UNKNOWN/kill switch | [ ] | [ ] | [ ] | 发前复验、lease失效、超时不重发、真实readback、全局/租户/账户开关 |
| V15 cancel/retry/resume字段与弹窗 | [ ] | [ ] | [ ] | 状态矩阵、节点上限、binding_revision、取消不复活、过期/已提交安全分流 |
| V16 对账双人审批与恢复 | [ ] | [ ] | [ ] | 不自审、证据唯一、UNKNOWN保留、确认未发才可安全失败/重试 |
| V17 规模与性能 | [ ] | [ ] | [ ] | 500账户/500素材/每层10000/十万DAG，分块内存、并发CAS、队列恢复、索引EXPLAIN及实际计时 |
| V18 三视口完整正负流程 | [ ] | [ ] | [ ] | 原字段/弹窗/二级Task页、真实API、未知/503不伪成功；外部写实测单独授权 |

规模验证复用既有十万T1仅作基线，不能宣称V17已过。原业务总体1亿/3亿、100权限组及长期混合负载要求仍属全系统容量项，本阶段样本不覆盖它们。每次证据记录固定源码、环境、实际执行/失败/未跑/阻断；凭据缺失只阻断对应外测。

## 10. 实施前需核对的技术补充

1. source/head内部映射已核定，客户端原GET刷新head、不新增ETag；具体038 DDL及公共Store由主线实现，独立纯模块不视为存储迁移已完成。
2. prepared manifest完成时点与validate响应关系、私有准备数据清理/可见性切换及生产来源证明。原合同要求完整再发送，但未替我们定义该内部存储协议。
3. resume技术映射已核定为tasks.retry，原文没有tasks.resume权限枚举。后续仍需实际路由/状态机/实时授权验收，不因口径核定勾选实现。
4. 每个权威provider的真实版本registry、撤销/证据来源与外部只读访问方式；不存在时继续明确503，不能只校验自填version字符串。
5. 既有allocation成功回写DRAFT却不递增head（`launch_allocation_runtime.py:579`）与新预检作废的统一规则，需纳入版本接力修正，不静默沿用。

参考旧ad项目只用于字段/API链核对，不移植其宽泛创建重试或Mongo任务ID语义。所有生产写入及远程发布均不在本文设计执行范围。

## 11. 首个独立纯模块检查点

新增 `python/orbit_api/launch_validation_contract.py` 与专属 `python/tests/test_launch_validation_contract.py`。当前定向纯测试56/56通过（1.33秒），两文件Ruff检查及格式检查通过。没有执行SQL、共享集成、浏览器或平台调用；本节不为第9节任何完整业务验收打勾。

提供以下内部调用点：

- `parse_validation_action(raw, action)`：仅包装原validate/execute严格解析器，不扩请求字段。
- `freeze_validation(plan, *, plan_id, source_revision, allocation, name_reservation, capability_version, policy_version, scope_version, channel_snapshot, product_snapshot, currency, total_dag_node_count, validated_at) -> FrozenValidation`。
- `is_current(record, now) -> bool`：数据库/可信aware时钟由未来Store传入；UTC毫秒、15分钟等号失效、上海午夜及未来记录不可用。
- `validation_response(record=None, *, errors=(), counts=None, totals=None, scope_version=None, total_dag_node_count=None)`：严格原十字段；成功需冻结记录；业务invalid可传真实Counts/币种金额对/错误，不伪造hash或零计数。

冻结接口接受原完整Allocation/NameReservation对象；核真实plan/source引用和完整展开slot。每个展开系列携最终保留名称及序号，每个广告携实际slot→asset/revision及当前账户/group/page override解析结果。广告素材revision不混用、原不重复分配限制、名称日、预算币种等结构交叉一致性由纯模块核对；名称/分配对象本身是否来自可信数据库及素材/资源真实授权仍必须由未来Provider/Store证明。

先用有界编码和原严格plan解析守住5MiB输入/500账户/每层10000，再流式逐账户、原树兄弟序和副本序输出完整节点JSON token；不先deepcopy整树、不物化复制笛卡尔积，也不保存展开树。集合排序、Decimal规范串及UTC毫秒进入schema1摘要，channel/product快照只按原JSON语义冻结，不误套计划集合或金额字段规则。测试含10000广告实际纯编码，观察单次摘要feed保持小token；这不是十万Task或生产内存/吞吐验收。

FrozenValidation仅保存不可变摘要、配置源、Counts、Money元组、scope及时间，没有verified/authority/Task ID。输入传入verified=true不会获得权威许可。缺生产来源的503由未来Provider负责；本纯模块允许结构合法但业务必填仍未验证的配置被摘要承诺，不得仅因能构造记录或序列化valid=true就绕过真实业务预检。摘要承诺输入，与准许执行是两个独立结论。

## 12. validate Store独立实现检查点（未做真实SQL/HTTP验收）

新增 `launch_validation_store.py`、`test_launch_validation_store.py`；Store40项纯协议测试与冻结协议56项合跑96/96通过（1.89秒），定向Ruff/格式通过。替身只验证调用及错误边界，不证明MySQL事务、实际权限、FK/锁并发、HTTP或外部Provider已可用。038由主线提供，本线未修改迁移/入口，也未创建Task或发送广告。

接线入口：

```python
store = LaunchValidationStore(tokens, provider=None)  # 缺省明确503
prepared = await store.prepare(
    session_factory, actor, authorization, csrf, key, value, plan_id, expected_head
)
# prepare已经退出自有短事务；capture和完整树编码均发生于事务外。
result = await store.validate(
    outer_session, actor, authorization, csrf, key, value, plan_id,
    expected_head, request_id, prepared
)
```

`outer_session`必须处于主线统一事务/回滚边界；完整成功对象仍为原十字段PlanValidation、HTTP200。公共路由、实际Provider、038及独立SQL工具由主线串行接入。

受控ABC `ValidationAuthorityProvider`仅定义两步：`capture(ValidationInput)`不接session，负责外部只读采集；`revalidate(session,current,source,evidence)`仅数据库来源锁与当前交集重验，不做网络或持久写。kind仅TRUSTED、ISOLATED_TEST；后者必须127.0.0.1:13306及精确本轮UUID库。没有默认生产实现，不接受verified字典。`ValidationEvidence`使用不可变bytes/tuple及SHA256指纹，Provider不能填充虚假预算/三层计数：Store从真实source重算Counts及Decimal预算。

最终顺序为当前动作/对象授权→外部来源clock/排序资源锁→launch clock→Plan/head与最新配置源→allocation/name头→validation/审计/outbox/幂等。allocation/name为launch所属持久头，不能提前锁后再等待launch clock，否则与032发布及现命名流程反向。Store直接核allocation/name当前tenant/plan/source归属及成功active/algorithm/input_hash/命名日，不把复合FK等同业务归属证明；完整slot/来源证据仍由Provider重验并由纯冻结协议检查。

capture开始时从数据库取得UTC时间；final再次读数据库UTC，若观察阶段达到15分钟或跨上海日则STALE_PREVIEW且无成功写入。成功后TTL从final完成时刻起恰15分钟；只replace不可变record时间并重建十字段summary，不在锁内重算完整树。hash不含issued/expires，所以时间接力不会改变配置摘要。成功新幂等键允许再验证并head+1、source/名称/分配不变，旧记录不可覆盖。

成功记录写入主线确认的 `orbit_launch_validation` 全部字段。summary仅严格十字段成功响应；观察引用仅白名单kind、UUID id、正安全revision，最多4000项/1MiB，拒任意Token、路径、URL或freebody。业务invalid只保存原幂等结果与审计/outbox；若原状态VALIDATED则CAS回DRAFT/head+1，原DRAFT保持head。未知来源/损坏Provider协议503，不伪造valid=false/零计数。

成功回放先当前launch.edit及对象范围，不受旧If-Match或重新采集影响；探测既有回执不先锁幂等行，真正读取仍复用原replay并保持launch锁序。实际并发重放、CAS竞争和任一失败后的全事务回滚，必须由后续真实MySQL用例验证。未来execute不能直接借用本Store的edit入口，须以launch.execute调用共同的内部Provider/来源协议。

## 13. 完整持久items防线与隔离专项真实检查点

Store在launch/head及allocation/name头锁之后，各一次集合读取最多10001项，核完整slot/account/asset/revision，以及name/Decimal序号转str(int(...))，按稳定slot比较集合。零项、超限、多项、缺项及头input_hash未变的明细篡改均拒绝；不把ordinal或JSON数组的无语义顺序差异当漂移，不引入N+1。新增对应纯测试后，Store/工具安全协议52项与原冻结56项合跑108/108通过（1.91秒），四个自有文件Ruff及格式检查通过。受测源已冻结交主线。主线实际默认provider=None档11/11通过，隔离Provider档22/22通过（10.39秒），包括初始化项；两档不是生产平台authority验收。

独立工具导出：

```python
IsolatedValidationProvider(session_factory, control_dir=None)
run_launch_validation_checks(
    client, admin, headers, password, cache, database, cases,
    *, include_provider=False, cipher=None, control_dir=None
)
```

`LAUNCH_VALIDATION_BASELINE_CASES`为5组：正式provider=None、原字段/头、默认503零写、当前动作/对象范围、当前CSRF及无Task。`LAUNCH_VALIDATION_CASES`为16组：成功持久、旧CAS幂等、配置源不变刷新、invalid两种原状态、异payload、CAS并发、配置源漂移、即时撤权、两类完整items多变体、实际1644与事务回滚、CHECK/FK、采集期来源clock漂移、SQL TTL三点及上海午夜两点。主线初始化项另外计数，不合并成新的业务通过数。

Provider仅允许本轮127.0.0.1:13306/精确UUID库，捕获真实fixture allocation/name/scope。字段及生产来源能力仍是隔离协议，不冒充平台authority。额外正向DAG计数从真实纯编译获得；ONCE模式先通过本协议成功，再在同配置源下明确业务invalid，用于检查旧VALIDATED撤销，不直接伪造成功头。

跨阶段篡改采用主线指定 `backend/.runtime/launch-validation-control/run-<uuid>` 自有目录，仅ready/release关联文件，禁止symlink/junction，等待上限8秒。capture已读取完整事实并退出短事务后才发ready；工具修改真实SQL明细、释放握手，结束后finally恢复原明细。没有普通HTTP控制后门或平台调用。

时钟组由主线传本轮cipher，在专属工具构造DirectoryTokens和真实Store，通过独立连接 `SET timestamp` 精确毫秒注入、先核实际SQL UTC值，finally复位timestamp=0。测试capture年龄15分钟前1ms/等号/后1ms，以及上海午夜前/等号；这是实际Store/事务的SQL时钟注入，不是自然等待15分钟或完整HTTP时间测试。缺cipher仅阻断这些具名组，不追加PASS。主线已保存本节两档真实回执；时间组通过仅证明实际Store/事务在注入SQL时钟下的边界，不标自然等待或生产平台预检通过。第9节端到端功能仍逐项保持未完成。


## 14. execute完整准备清单纯模块检查点

新增 `python/orbit_api/launch_execution_contract.py` 与专属 `python/tests/test_launch_execution_contract.py`，42/42定向纯测试通过（13.30秒），Ruff及格式检查通过。没有新增迁移、路由、Task或平台发送；现有validate、Task及公共源保持冻结。原execute仍应返回HTTP202完整Task，不能用PreparedExecution、032 runtime ID或graph_hash代替受理结果。本检查点不勾第9节V10—V14整体验收。

内部调用点：

```python
prepare_execution(
    source, validation, *, validated_head_revision,
    allocation, name_reservation, compatibility,
    material_revisions, material_metadata, resolved_metric_profiles,
    capability_version, policy_version, scope_version,
    channel_snapshot, product_snapshot, currency,
    observation_refs, request, now,
) -> PreparedExecution
iter_execution_nodes(prepared)  # 完整实际resolved配置及配置摘要
iter_prepared_chunks(prepared, *, chunk_bytes=65536)  # 完整JSON文档的有界字节块
```

输入为原PlanSource不可变规范字节、FrozenValidation、原完整Allocation/NameReservation对象及真实来源事实。严格解析原ExecutePlan的hash、activate_ack两个字段；不增HTTP字段。核配置source/validated head、SHA、15分钟/上海日、完整counts/Money、原冻结hash、全量名称/素材slot和版本，并重新编译真实DAG。当前auth、launch.execute、条件launch.publish、当前来源/目标投手交集、完整policy与即时能力均须未来受理Store/Provider重验，不能从结构合法推导。产物execution_authorized恒False且不接受构造参数设True。

现有launch_dag的node只保留配置hash/指针/目标，因此本模块另外流式携实际最终系列名、广告组/广告必填名、预算/日期/投放配置、逐账户group/page override、slot→asset、真实文件描述及归因适配参数。每个节点增加resolved_configuration及其SHA256；不把旧configuration_hash冒充完整命令。CREATE默认PAUSED，activate_after_create仅在原明确确认后编译独立ENABLE/VERIFY，仍不授发布权。原配置顺序保留；allocation/name items按无语义的slot稳定排序，输入数组排列不同不改变清单。

素材描述冻结id/revision/sha256/mime/size/width/height/duration与实际owner_user/team。按C真实素材来源同team及caller/目标scope交集规则，不暗加“素材必须与计划同一owner_user”限制；后者权限交集仍由外部Provider负责。已知非READY、非LIVE、未CLEAN或未知/不可执行观察明确503，正向布尔只作观察完整性条件。输出不带临时下载URL或execution_eligible布尔，不能靠自填verified取得写授权。图片/视频原类型与大小、实际尺寸和视频时长未知时拒绝，不补零。

`request_payload_hash`覆盖tenant/plan/source/head和原完整execute请求，包括activate_ack，即使非激活请求的ack变化也不能同幂等键偷换；`manifest_hash`覆盖稳定配置源、完整名字/分配/身份/资源/观察引用及每个实际节点。状态CAS head与短期expiry不进入稳定清单，所以相同source重新预检刷新TTL不产生不同执行清单，但未来Store必须按原成功回放优先级处理旧CAS，不能仅凭新hash重复受理。相同source唯一Task与原子Task/commands/审计/outbox仍未实现。

有界策略先守原5MiB配置、500账户、每层10000展开项，再使用原<=100000节点DAG；原始附加输入编码预算64MiB，不先deepcopy完整展开配置。准备物仅留不可变原始字节、DAG及映射，逐节点解析配置并流式产生完整字节文档，不保存resolved_nodes全列表。42项包含10000广告实际纯solve/compile/清单密封与逐节点遍历；这是纯编译规模测试，不是SQL/HTTP/生产内存或吞吐验收。字节块可跨UTF8字符，持久层需用BLOB并整体/增量解码，不能把每块当独立JSON；总展开载荷不套032旧256块上限，未来DDL与批发布协议尚需明确。

### 14.1 指标配置与平台参数的明确技术适配

原OpenAPI MetricProfile字段version是字符串，没有整数revision或attribution_spec。新内部ResolvedMetricProfile保留完整原profile与其source SHA256、原version绑定、adapter_version，再以明确registry_revision关联观察引用；该内部registry版本不冒充原字段。目标attribution_spec仅按[Meta官方SDK AttributionSpec字段类型](https://github.com/meta/facebook-python-business-sdk/blob/main/facebook_business/adobjects/attributionspec.py)的event_type字符串、window_days整数，以及[AdSet字段类型](https://github.com/meta/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adset.py)的list<AttributionSpec>定义严格结构，不从attribution_windows文本猜测数组、不定义自由格式附加参数。SDK主分支仅作结构证据，绝不是当前账户/目标/Graph API固定版本的能力许可；合法枚举/窗口组合和适配版本必须由未来权威registry及实际只读能力证据确认。profile未verified、缺绑定、源摘要不符或缺显式目标适配均503。

渠道快照必须明确WEBSITE或APP：网站像素/事件和广告HTTPS落地页，与应用application/store URL互斥，未知不猜。实际URL DNS/重定向/SSRF、即时资源权限、生产metric registry/目标适配器、广告发送+5分钟时间规则、kill switch、WRITE_INTENT/UNKNOWN与readback仍未接。本模块拒绝缺必要结构依赖并冻结完整输入；不会因fixture中version/verified合法而声称来源可信。

### 14.2 可独立接力的下一阶段

- [x] 原execute严格请求、完整不可变准备载荷、最终名/素材/identity/归因显式映射和PAUSED/ENABLE纯编译。
- [x] 对应42项纯协议测试、10000广告实际纯编译、格式及静态检查。
- [ ] 生产ExecutionAuthorityProvider与即时双方权限/能力/策略/URL/素材证据来源；默认缺来源503。
- [ ] 持久分块准备/完整seal/同source唯一/成功幂等回放及当前对象范围复核。
- [ ] 原202 Task与完整DAG/commands/审计/outbox原子受理、CAS并发及崩溃恢复的真实SQL/HTTP验收。
- [ ] 实际发送前即时授权、WRITE_INTENT、UNKNOWN不重发、独立readback和原Task控制流程。

上述后续由主线分配Store/DDL/接线窗口；本线没有占用039，也未启动共享服务或平台写入。
