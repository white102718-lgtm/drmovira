# PY06 素材分配持久化方案（032已批准，真实事务待验）

## 复用与不可伪造的依赖

复用021已有`orbit_launch_allocation`、`orbit_launch_allocation_item`、`orbit_launch_idempotency/event/outbox`。不修改021，不借`task_id`写入不存在的Task，不改公共Task表。本文件是设计提案，尚无032 SQL或真实store/worker验收。

公开接口保留原`POST /launch-plans/{id}/allocations`严格AllocationRequest及202 Allocation，GET原结果路径；公开state仅QUEUED/RUNNING/SUCCEEDED/FAILED。完整匹配才写items，失败无部分映射。独立算法已有最大匹配/重复全局Σusage²最优纯证明；provider未知时503，不能先返回一个永远无法求解的假队列。

仍须权威provider：冻结完整plan/revision、caller与实际owner来源权限、实际账户身份与能力版本、C素材READY/LIVE/CLEAN及revision/hash、全部兼容边。provider只能读取受控本地已核验包，不在500万条边循环联网。普通GET identities或可读READY并不是平台能力证明。

## 建议032新增表结构

仅增加以下三张专属表，所有实际SQL字段/表/索引都必须中文COMMENT；以下字段清单为DDL批准稿，不是已执行迁移。

| 表 | 主键及字段提案 | 索引/约束 |
| --- | --- | --- |
| orbit_launch_allocation_runtime | `(tenant_id,allocation_id)`；actor_id BIGINT；plan_id CHAR(36)；phase VARCHAR(16)；input_schema_version INT；plan_input_hash、source_hash、authority_fingerprint、manifest_hash CHAR(64)；capability_version VARCHAR(64)；chunk_count INT；slot_count INT；attempt INT；claim_token CHAR(36) NULL；claim_generation BIGINT；lease_until、heartbeat_at、next_attempt_at DATETIME(3) NULL；error_code VARCHAR(64) NULL；created_at/updated_at DATETIME(3) | FK到021 allocation与plan；phase限定CAPTURED/QUEUED/SOLVING/PUBLISHING/COMPLETE/FAILED；slot_count 1..10000；chunk_count有受控上限；队列`(phase,next_attempt_at,tenant_id,allocation_id)`和租约恢复`(phase,lease_until,tenant_id,allocation_id)`；不存平台Token/自由异常正文 |
| orbit_launch_allocation_chunk | `(tenant_id,allocation_id,ordinal)`；kind VARCHAR(16)；payload_json JSON；payload_hash CHAR(64)；byte_size INT；created_at DATETIME(3) | FK到runtime；ordinal非负；单块UTF8规范字节<=256KiB，整份manifest有总量上限；按主键键集读取、每次<=200；禁止无界单JSON承载500万边/十万节点 |
| orbit_launch_allocation_guard | `(tenant_id,plan_id)`；allocation_id CHAR(36)；generation BIGINT；updated_at DATETIME(3) | FK到真实plan/allocation；一计划一个待求解指针，强制claim代次及发布CAS；终态同事务清除/释放，不删历史allocation或items |

冻结内容分块种类：PLAN原配置/真实ID/原snapshot provenance、SOURCES受控授权和实体版本指纹、MATERIALS实际revision/hash/尺寸等、GRAPH完整兼容bitset及stable slot manifest。bitset以固定长度十六进制或规范编码储存，附精确N/M/排序版本，不将Python无限整数转非规范JSON数字。chunk manifest包含有序(kind,ordinal,hash,byte_size)及总字节/项数，缺块、重复块、hash不符均不能进入QUEUED。不能先标受理再后台补不完整源快照。

输入总量上限需结合原5MiB配置、最多10000slot/500素材和实际压测明确后才写CHECK/接收校验；本设计不猜一个可能拒绝合法计划的过小总量。固定256KiB块是实现分块策略，不是扩大原5MiB配置限制；原配置本身仍<=5MiB。

## 事务、异步与恢复

1. HTTP验证原请求/If-Match/幂等/当前动作与来源权限；按照来源统一clock及全局排序素材锁，再launch clock/plan锁。冻结本地可信包及完整输入/manifest、真实allocation/runtime/guard、同事务审计/outbox/幂等响应。无provider先503；没有SQL成功提交不返回202。
2. 发布前旧active分配及引用保持不变。新runtime guard只是求解任务，不是新活跃映射；不提前把所有选池素材注册ALLOCATION活跃引用。归档/改版本在求解期间允许由自身规则决定，发布实时重核失败即可，不能伪造成功。
3. claim使用有界队列索引、FOR UPDATE SKIP LOCKED及claim_token+generation+租约；实际CPU求解在数据库事务外，由独立进程限定总时间/内存。纯算法建图和两阶段共享60秒预算，超时沿同输入hash进入真实持久异步恢复，不新seed、不发部分映射。进程失联必须租约到期后新generation接管，旧claim不得写回。
4. 发布重新取来源锁并核caller/实际owner当前权限、账户/身份/能力/provider完整输入指纹及C当前CLEAN/revision/hash。旧active无锁预读后，通过C `lock_active_material_reference_set`以旧资源UUID和新池取得旧新union全局排序锁，再launch/plan和runtime guard CAS；原active已变化409，不能在持plan锁后反向取素材锁。
5. 确认plan revision/输入、claim代次、完整最优解一致后，分块INSERT所有021 items但仅在一个受控发布事务内提交；最终SUCCEEDED、active替换、旧引用ticket释放/新C活跃引用登记、审计/outbox/幂等结果同事务。任何SQL/审计故障全部回滚，旧分配继续可用。不能把分块commit的半份items暴露为成功。
6. 重复受理命中原021 `(tenant,plan,input_hash)`结果；相同原键不同请求409。重新分配必须原用户明确确认且seed+1（最大seed溢出拒绝），仅新分配成功才替换。用户取消重新分配弹窗不创建新意图、不删除原分配。无原公开取消endpoint时不自创CANCELLED Allocation枚举。

`Allocation.task_id`原schema允许null；建议在独立allocation-runtime真实异步队列阶段保持null并用原GET allocation轮询，不能把runtime UUID充作不存在的/tasks对象。是否接受此内部异步实现，或必须等待公共Task/ALLOCATION真实manifest接线，由主线确认；此点未确认前不能注册假202。若要求公共Task，必须由对应真实模块创建完整ALLOCATION节点与审计，不能在本提案中建空Task绕过。

## 必须真实验证的最小矩阵

同计划并发受理仅一guard/输入、同键与不同key复用；60秒实际超时/进程死后claim恢复/旧claim写回拒绝；manifest缺块/hash错/超限拒绝；caller/owner撤权与跨租户不可读；账户/素材/能力改变后发布失败；原active与素材引用保留；审计/批量items故障全回滚；有约束的全局最优和seed仅平局；10000slot与500素材真实SQL、内存/CPU/锁等待容量；历史与幂等两年保留按合同，输入chunk删除须另外明确留存/审计可重建策略，不擅自定短TTL。

上述提案送审阶段的“待确认”保留历史上下文，当前实施结论以下节为准。

## 主线批准及当前实施检查点

主线已批准独立032三表及真正持久allocation-runtime异步队列，公开原schema允许`task_id=null`并用原GET allocation轮询；绝不将runtime UUID冒充公共Task。公共Task/ALLOCATION桥接后续另做，当前不建空Task、不修改021。

内部完整冻结输入安全上限已定64MiB，单块256KiB、最多256块；完整manifest一次事务提交且可领取前全部校验。实际迁移采用MEDIUMBLOB存规范UTF8文档片段：BLOB不足256KiB，跨UTF8码点/JSON对象片段也不能逐块当JSON；须先核块/清单/总字节/hash，再重组及严格规范JSON/schema恢复。所有表/字段/索引中文COMMENT、同租户FK、guard计划复合FK和claim代次/旧输入CAS已写入032独立迁移。

新增packet/runtime/worker与对应纯测已进入独立WIP，生产provider默认未配置503。A确认尚无生产即时身份/能力provider；C最新可信CLEAN需026+030四列收据/实际实例证明，旧READY或旧026种子不作为发布正例。真实provider与C引用联调仍未验，不注册无法求解的假202队列。

当前30项定向纯测PASS（5.04秒），包括真实spawn CPU进程边界、默认provider503和严格测试库隔离。纯容量fixture精确原配置5,242,880字节、10000slot×500完整兼容图，内部冻结文档6,659,451字节/26块，无截断；500账户×10000slots另一合法极端也已完整恢复。该6.659451MB仅纯序列化/上限边界证据，不是SQL、真实CPU最坏图、生产能力、C素材发布或公开接口验收。

真实事务工具正在独立准备，ISOLATED_TEST生产者仅允许`orbit_py_it_[a-f0-9]{32}`本机隔离库，明确只验队列SQL，不伪造已通过C/平台能力。032源码/工具待主线串行真实事务验证后独立提交，当前不与前一DAG阶段混标。
