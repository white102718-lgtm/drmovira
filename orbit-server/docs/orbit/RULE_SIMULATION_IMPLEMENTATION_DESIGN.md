# 规则模拟、启用确认与运行记录实施设计（冻结提案）

当前S1独立纯流式解释器已57纯测通过，S2持久化仍仅提案，没有新增SQL/生产模拟provider/执行授权。已有规则定义与061消费48/48实际通过17.58s，证据`evidence/python-rule-scope-consumer061-http.json`，不据此标simulate/enable/runs完成。外部Meta来源尚未发行不能伪造成功；应继续独立真实SQL技术发行内测。

## 原合同锚点

- `data/ORBIT_Codex开发PRD/contracts/openapi-current.json`：POST `/rules/{id}/simulate`原rules.read，CSRF/Idempotency-Key/If-Match均必填，无body/无cursor参数；200为Simulation。enable沿rules.enable，严格`{simulation_id}`，返回原Rule15；runs沿rules.read，返回RuleRunPage。
- 原Simulation13键：id/rule_id/revision/snapshot_id/hash/account_count/scanned_count/hit_count/unknown_count/false_count/conditions/expires_at/next_cursor。conditions每页最多10000，ConditionResult五键entity_id/condition_index/value/result/reason_code；entity_id为真实内部UUID，不用平台外部数字串或随意快照UUID替代。
- 原RuleRun8键：id/rule_id/rule_revision/schedule_slot/snapshot_id/state/hit_count/reason_code；state仅RUNNING/SUCCEEDED/SKIPPED/UNKNOWN/FAILED。Page4原items/next_cursor/data_as_of/scope_version。
- `reference/03_原合同保留章节.md:311–319`：两层AST、三值逻辑、null!=0仍UNKNOWN；同evaluator用于模拟与生产；15分钟同版本模拟；模拟无模型/外部写；租约/slot/冷却/日额度与hit→analysis_job→outbox独立原子链。
- `WORKFLOWS.md:47–51,63`：原profile全部字段，独立预期(account, business_date, profile)覆盖，完整分页/合法空与缺字段区别，最旧observed_at，age>30min为STALE，成熟/稀疏只观察，规则状态边与15分钟同版本要求。
- `FIELDS.md:567–644`、`API_SEMANTICS.md`规则行：名称/1–50000冻结范围、总条件≤20、Decimal/阈值/计数整数/单位、原Schedule约束，不执行eval，不新增固定预算/删除动作。

## 原型触发记录、建议、广告与分析的独立后续接力

经原OpenAPI逐入口核对，全局“触发记录”是`GET /api/v1/rule-hits`与`GET /api/v1/rule-hits/{id}`，均沿`monitor.read`，不是`/rules/{id}/runs`，不能用RuleRun8替代。原Hit14字段完整保留：id/rule_id/rule_revision/entity_id/account_id/ownership/snapshot_id/occurred_at/analysis_job_id/analysis_state/analysis_error_code/analysis_error_message/suggestion_id/generation；analysis_state仅QUEUED/RUNNING/RETRY_WAIT/SUCCEEDED/FAILED/SUPERSEDED。HitPage仍原四键，通用q/status/date/operator/channel/profile/entity过滤的具体含义须按原合同补齐/显式拒绝，不吞条件。Entity UUID与account_id/ownership必须来自同一已冻结观察快照和实际命中，不能拿模拟统计随意造Hit。

“管理优化建议”对应`GET /api/v1/suggestions`及`GET /api/v1/suggestions/{id}`（monitor.read），保留原Suggestion15：id/revision/ownership/hit_id/generation/snapshot_id/original/current/state/generated_at/submitted_at/operation_ids/analysis_state/policy_version/model_version。state为PENDING/EDITED/IGNORED/SUBMITTED/EXPIRED/SUPERSEDED；此对象analysis_state原schema仅SUCCEEDED，失败分析不能伪造一条成功Suggestion。原始建议original与编辑后current分别完整保留原SuggestionAction8：action/target_entity_id/budget_owner_id/before/after/currency/reason/delete_ack；nullable before/after或budget owner不得补0/假UUID。

“处理建议”先落原`PATCH /api/v1/suggestions/{id}`（monitor.suggestion.edit，严格SuggestionEdit={action,edit_reason}）及`POST /api/v1/suggestions/{id}/ignore`（monitor.suggestion.ignore，原Reason），均原If-Match/Idempotency/CSRF门禁。采纳并发送另走`POST /api/v1/optimization-batches/preview`与`/execute`（monitor.optimization.execute），原BatchPreviewRequest→BatchPreview、BatchExecute→202 BatchResult；不能从rules.edit/enable或分析成功推导执行许可。批命令原suggestion_ids1..500/affected_entity_ids1..10000与去重/冲突、预算、对象锁、三级kill-switch、平台authority/UNKNOWN回读仍属独立执行接力，本阶段零广告写。

“查看广告”使用Hit.entity_id或SuggestionAction.target_entity_id进入原`GET /api/v1/entities/{id}`（monitor.read→原Entity），不能将外部Meta数字ID当UUID，也不因“规则可读”免掉该广告对象当前范围校验。详情没有可信实体/来源时保留明确依赖错误，不能拿监控列表的空行当成功详情。

“查看分析”以Hit.analysis_job_id/analysis_state展示真实任务状态及原错误（按原安全边界），成功建议的证据走`GET /api/v1/suggestions/{id}/evidence`（monitor.read），原SuggestionEvidence10：suggestion_id/snapshot_id/window_from/window_to/metric_profile_id/observed_at/model_version/policy_version/evidence/risks。每AnalysisEvidence7字段id/metric/value/unit/date_from/date_to/entity_id，evidence1..500、risks0..10；未知value仍null。原OpenAPI没有通用`GET /analysis/{id}`，不得为原型按钮猜造已实现的入口。后续若需失败任务细节扩展必须另提严格合同，不强塞SuggestionEvidence成功对象。

最小实现顺序：完整已授权事实→真正RuleRun/Hit+analysis_job+outbox同事务→analysis generation/租约与稳定输入→GPT/Claude严格provider输出校验/来源及模型政策版本→Suggestion immutable original+可审计current→独立建议详情/处理/证据和实体详情。真实外部模型或平台缺凭据仅阻对应实测；仍可用严格标注的SQL技术来源/固定测试输出验证内部持久协议，不能把这些夹具称模型分析或平台执行验收。

当前上述Hit/建议/广告/分析路径仅需求映射，均未因S1纯计算或现Rule定义验收勾选完成；同样不以RuleRun8字段实现推断Hit14/建议15/证据10已开发。

## 已有核心与不能直接借用的路径

可复用`rule_contract`严格原DTO/白名单/阈值；`rule_conditions.compile_conditions/evaluate_conditions`已提供Decimal/两层三值及稳定flatten condition_index；`rule_schedule.preview_schedule/latest_due`已提供当地锚点/真实分钟/DST跳过和重复一次/最近missed slot；`rule_metric_windows`按每账户真实IANA时区计算TODAY/YESTERDAY/LAST_3D/LAST_7D，统一注入同一个可信UTC evaluated_at。

040提供精确不可变profile+来源proof/映射；`lock_rule_profile(expected_version=...)`当前启用head与冻结版本/源config精确校验，不能悄悄改用latest。048有PUBLISHED完整publication、capture cell独立页/实体/fieldmask、分代事实/真实内部实体UUID/冻结归属。049有持久查询/排序行/完整总计及构建租约；056补独立预期单元/实体membership根。`metrics_aggregation.MetricAccumulator`仅按同币种/profile聚合分子，缺失污染该列，分母0比率NULL、六位half-up；不自授质量或完整来源。

不可直接调用公开`MetricsQueryStore/ResultStore`：当前严格monitor.read、原049scope FK仅025私有snapshot，query仅统一date_from/to；Rule沿rules.read/enable、同Rule公开manifest及双方当前范围、不同账户业务日窗口，不能把Rule manifest UUID塞公共scope字段、不能加monitor/accounts读权限，也不能复写整个Store假装共享。

需root分配共享内部授权read扩展，或新小型`RuleMetricSource`适配器明确接受当前RuleAccess+OwnerScope+同Rule manifest及每账户窗口。复用048/056独立issuer+哈希/来源核验，不复用未经过授权的私有方法/伪造MetricReadContext。同事务能力句柄不得跨commit；public monitor API与creator私有scope原语义不改。

## 事实边界与失败关闭

1. 缺受控source provider/独立预期issuer时明确503，无成功Simulation/空对象/默认零。原HTTP认证、当前rules动作/Rule可见性仍先执行，不能因provider缺失把原403降成可观察假成功。kind=TRUSTED字符串、hash/DTO通过都不等于真实Meta发行或写权限。
2. 每个账户窗口来自真实账户IANA+同evaluated_at，调度timezone只管slot，不能覆盖账户切日。DST/UTC跨日/历史归属按原冻结时区与归属版本核；无有效账户时区/来源拒绝，不猜UTC/上海。
3. 预期单元和目标实体全集必须来自独立完整受控清单；不能从返回cells/事实行/分页条数推预期。两个源所需profile/version/hash/config rev/algorithm/generation、所有页/实体根、完整空fieldmask均严格绑定。最新高generation不能改变已经冻结的结果。
4. caller与目标owner的当前全体账户范围，以及业务日历史事实所有权过滤均必须成立。当前拥有者不能自动看原投手历史，UNASSIGNED不默认归当前人。若有独立当前可读实体清单而某业务日不可读/缺单元，可为这些已知对象给UNKNOWN；若连真实授权对象全集都不能证明，503，不伪造未知占位对象或泄露foreign名字/数量。
5. 缺字段/未映射register_action_type/purchase/value、缺cell、分母0均NULL；完整已证明合法零才为0。money在每对象自身账户currency比较原阈值，不跨币求和/换汇，不平均ROAS；campaign/adset由同账户AD分子正确聚合后再算比率。unknown/invalid原值不进入真命中。
6. 叶子观测TRUE/FALSE/UNKNOWN与后续“可执行建议资格”分开。稀疏/STALE/PARTIAL/归因未成熟/关键字段缺失/空quality_flags沿WORKFLOWS §4限制后续建议，不授广告执行资格。主线复核§5后裁决：完整授权计算可含UNKNOWN/稀疏并200，不增加enable全TRUE/无UNKNOWN门槛；15分钟同版本成功simulate是确认条件，enable仍另核原权限/状态/CAS/范围/profile，不等于可执行建议。恶意hash/错proof/不完整预期issuer仍503，不降成正常UNKNOWN。
7. 完整已采集空账户单元可有account_count>0、scanned_count=0、三个对象结果计数0；是否可启用需真实完整单元/空清单证明，不把缺来源“无行”当成功空结果。

## 稳定模拟与过期/启用

- 先冻结Rule revision/body/hash、当前owner/manifest/member根、精确profile/源配置/算法版本、单一fact publication/generation及独立预期根、每账户窗口、SQL UTC evaluated_at。按200/1000等有界批次/键集流式读取，不把50k账户及所有AD/叶子全放内存；单对象≤20条件，恒定Decimal聚合内存。
- scanned_count是完整独立授权实体数，不是账户数或页数；hit+unknown+false=scanned。condition_index沿既有compile_conditions的全树稳定0-based顺序，每对象重复相同索引，不把全局ordinal当condition_index。结果根绑定完整有序实体/叶子/来源及全部统计。
- 构建采用独占connection/显式phase与有界预算；长构建不持续持全Rule/授权锁。各phase重发同冻结来源上下文，禁止跨事务复用旧票据；取消需精确await清理，不orphan。只有最终来源/权限/完整成员/Rule CAS仍一致且所有结果根完成，才READY并发布receipt+audit/outbox；无半包200。
- expires_at建议实际完整seal SQL UTC时刻+15min，评估时刻/最旧数据时刻另存；now>=expires失效，最旧关键observed age>30min为STALE（精确30min仍按原age语义）。未来观测/时钟不一致拒绝。TTL边界需root定稿后真实测；成功旧key不续期、不重新算最新数据。
- simulate完整意图包含原rule_id/IfMatch，独立ledger，因为057 rule_idempotency的response为Rule且注明simulate另存。原key当前rules.read+Rule可见+全体当前scope重验后原结果；同键异完整意图409。head编辑/状态版本变化使旧模拟无法用于启用，不删除历史证据。
- enable先原成功ENABLE key当前原动作+Rule范围原结果；新key需DRAFT/PAUSED、原IfMatch、同tenant同Rule同source revision的READY完整授权模拟、15min内、结果完整性及当前scope/profile等原依赖可用，不重绑源。过期/旧版/foreign/完整性未证拒绝，不能靠客户端hash/200状态；UNKNOWN叶子或稀疏本身不另加禁止启用条件，后续建议质量独立门禁。S2本轮不实现enable。
- ENABLE本身会使Rule revision+1；Simulation仍记被确认的原revision，不回写成新revision。应另存activation绑定source_rule_revision和enabled_revision/模拟id，审计明确前后。next_run_at来自真实schedule核心和due登记；若调度持久层尚未接，保持503，不以标ENABLED冒充会运行。

## 大条件分页技术扩展（root已批准方向，未落代码）

原simulate POST无cursor，不能给旧next_cursor捏造入口。新增独立signed GET `/rules/{rule_id}/simulations/{simulation_id}/conditions`，rules.read+当前Rule/完整范围、严格cursor/page_size，返回原Simulation13（相同id/root/count/expiry，conditions为当前页）；不重算事实。首POST可取首200叶子并给next_cursor；GET四档20/50/100/200，内部结果仍全部持久、完整counts/root，不把每页当扫描总数。游标签新独立用途，绑定session/actor/current scope/Rule+模拟源revision/manifest+结果根/ordinal/page size，不复用Rule列表cursor。root后续详审精确DTO/路径/期满历史读规则。

原Simulation没有quality_flags/enable_eligible字段，不能偷偷增加。需root进一步批准独立readiness技术读合同，或明确采用逐条件reason_code+enable错误反馈；原RUL-05要求的质量/阻断原因完整UI不能用不存在字段假实现。此为待定接点，不先发明公共schema。

## 最小实施阶段/持久化概念（不创建SQL）

S1优先完整SQL技术来源模拟：新增`rule_simulation_contract.py`(仅内部来源/结果证明)，`rule_simulation_evaluator.py`(组合既有纯evaluator，不重写AND/OR)，`rule_simulation_source.py`(显式authority默认None，完整窗口/预期/来源协议)，对应纯测。先有意义定向纯测后root分配Store/来源reader共享接口。

S2新增`rule_simulation_store.py`及独立真实工具；正式迁移编号由主线另分配（062已留规则页面菜单），root审持久化候选。最少持久对象建议simulation头、每账户窗口/源单元、完整entity结果、condition叶子、simulate请求ledger、成功audit/outbox。头保存不可变Rule/manifest/profile/来源根与算法、统计/结果根、sealed/expires/内部eligible和固定阻断码；BUILDING不可读，READY不可改。窗口最多50000×7日需实测索引/容量；叶子PK(tenant,simulation,entity_ordinal,condition_index)用于有界分页，不存无限factsJSON。所有FK严格同tenant/Rule/revision/source；不对7日可清理TaskEvent建永久FK。root可按评审合并必要表，不自行分配其它编号。

S3 enable确认activation、原057事件/版本/head/outbox+下一真实due slot同事务；当前Store留503直至最小可运行调度配置成立。S4真实RuleRun/lease/due调度和命中AI排队，沿原slot/revision/snapshot去重及tenant+rule+entity冷却/日额原子账本。不能把模拟表当RuleRun，不能用模拟命中调用模型。定时运行先RUNNING，未齐/过期/口径变按SKIPPED/UNKNOWN等原状态记录；真实hit/analysis_job/outbox另统一事务，多worker唯一slot与generation晚到保护。

GET runs未来严格原RuleRun8/Page4，status只原枚举；q/date/operator/channel等原generic参数的具体含义未完全定义，不能忽略后返回假完整列表。建议第一档仅明确Rule_id+status+稳定slot/id键集，其余显式unsupported（按API语义422，root统一错误风格）；完整原接口仍有缺口。规则Schedule/IANA自然日与run日期过滤的界限须明确后才能支持，不猜UTC/上海。

## 真实失败/边界矩阵

- 仅rules.read可simulate、不借monitor/accounts；只有enable无read能确认已获合法Simulation需原enable动作+当前可见性，不强加read；撤权/跨tenant/foreign正确401/403/404。
- 默认无provider/预期issuer503，无simulation/任务/假零；完整真实SQL技术发行分组ISOLATED_TEST必须实际13306+UUID+SELECT DATABASE，不能当Meta证据。
- 040profile坏hash/proof/observed独立列错、head/config换版；048完整页/空mask/critical不足/迟到代际；056独立membership/units漏/重复/后页错都整包失败关闭。
- mixed USD/EUR、跨日IANA/DST、历史归属/UNASSIGNED、ratio先分子和、NULL!=0、0分母、registration缺映射、完整空单元与无源无行区别。
- >200实体、多于10000叶子、全叶子ID/顺序/根/数量对账、首尾页/签名session/page/Rule/scope篡改、后台新generation后旧snapshot不变。
- 模拟同key/异body/并发一个结果，构建取消/预算/DB1205无假READY；审计/outbox1644结果/receipt/统计/行全回滚；恢复不跨事务复用旧capability。
- 14:59.999与15:00失效边、事实age精确30min/>30min、未来obs拒；enable旧revision/改条件/改范围/保护参数/停用配置/权限变化拒，成功原ENABLE key不再创建新版本/slot。
- run slot唯一、DST不存在日志/重复一次、停机只最近slot、冷却日额竞争/重传、旧generation晚到不覆盖、新snapshot冷却后允许新分析；模拟始终0模型调用/0广告写。

TeamAI本次没有命中ORBIT规则模拟专门约定，命中其它项目业务日/费用文档不用于推导本项目权限/状态。所有状态/质量与时间边界仍以以上原PRD合同及root裁决为准。
