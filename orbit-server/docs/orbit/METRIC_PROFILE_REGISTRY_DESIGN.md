# 指标配置最小真实来源注册表

本阶段仅新增metric_profile_contract.py、metric_profile_store.py、专属纯测和docs/orbit/sql-drafts/040_metric_profile_registry_candidate.sql。实际040、原GET路由与launch_references接入由主线统一负责。51项纯测0.80秒/Ruff通过，真实MySQL迁移/权限/回滚/EXPLAIN与原HTTP尚未执行。没有默认Authority、版本、归因窗口或平台写入口。

## 原合同不变

原MetricProfile复用launch_execution_contract.MetricProfile，version严格保留1..64字符串；nullable action_type、opaque attribution_windows、ACCOUNT_LOCAL/TOTAL/maturity_days/verified均按原DTO。不会给原响应加内部revision或AttributionSpec。目标参数映射单独保存明确event_type/window_days数组，来源必须通过authority验证，不从窗口文本推导。ResolvedMetricProfile是内部消费者DTO，包含原profile、profile_source_hash、adapter_version、bound_profile_version、registry_revision和attribution_spec。

FIXTURE只允许ISOLATED_TEST Authority及session.bind.url精确127.0.0.1:13306、实际数据库orbit_py_it_<32hex>。TRUSTED发布只能META，实际META_BM source_config_id/revision必须存在、enabled且当前版本完全一致；默认authority=None在任何持久写前503。verified布尔和kind=TRUSTED本身都不是外部核验；MetricProfileAuthority必须真实取得映射及来源证明，当前生产子类未实现。

## 040候选六表与约束

- orbit_metric_profile_clock：每租户revision≥1，发布/停用/精确适配撤销同事务递增；新租户需要主线初始化该行，缺行503。
- orbit_metric_profile_version：(tenant,profile_id,version)不可变，原profile JSON/hash及source/config revision/观察时间/受控evidence/source SHA/proof JSON；FK至tenant及真实system_configuration，不反向FK head。
- orbit_metric_profile_head：(tenant,id)，current_version外键精确指向真实version，内部revision/state，索引(tenant,state,id)。
- orbit_metric_profile_adapter：(tenant,id,profile_version,adapter_version)，精确四列FK包括profile_hash；明确参数映射/hash、来源proof、首次registry_revision不可变；revoked_at仅允许空→真实时间，不允许复活。
- orbit_metric_profile_audit：只追加profile/version/摘要与必要状态变化、当前actor/request；不含秘密或完整请求。
- orbit_metric_profile_outbox：与audit同事务创建，按(state,created_at,tenant,event)有界投递。

主线已确认无延迟FK环方案：version→tenant，head/binding→exactversion；同一外层事务先完成version与binding再发布head，未有head的内部version不能被公开候选、lock_exact或执行消费者读取。旧版本及映射内容UPDATE/DELETE触发器拒绝；撤销不抹历史快照。旧任务冻结包可继续只读审计，不由本注册表给旧来源新执行权。

## 内部方法与共享接入点

1. MetricProfileStore(authority=None).prepare(profile_id,version,adapter_version)：无session；先受控入口核system.release.manage再调用，事务外authority.capture只读采集，返回MetricPublication（原profile字节、显式mapping字节、adapter版本、MetricSourceProof）。没有默认版本。
2. publish(session,current,prepared,expected,request_id)：要求调用者外层事务和当前system.release.manage。authority.revalidate仅SQL来源锁、不能网络I/O；proof必须与prepare完全相同。再核META_BM当前来源、数据库UTC观察时间、metric clock→head/version/binding。自然键重复同内容/同来源不重复审计；同版本换内容/hash/来源或同适配换mapping409，旧版本/撤销来源不能重激活。新发布严格内部head CAS。发布version/binding/head/audit/outbox/clock同事务，不自行commit。
3. lock_exact(session,current,owner_context,profile_id,version,adapter_version,permission='launch.edit')：root必须在launch clock/head之前的来源阶段调用。两context必须来自真实当前caller和计划目标owner；同租户，重新核caller真实原launch.read/create/edit/execute动作；目标owner只核当前启用且非受邀的业务用户、原生用户、身份、租户、团队、scope及五项BusinessContext字段完全一致，不额外要求目标launch.read或monitor.read。profile是租户配置，没有原Ownership字段；业务账户/素材/渠道的双方范围由原服务继续核，不能因可读profile扩大对象权限。先无锁预读不可变source元数据定位来源，再source_config SHARE→metric clock SHARE→head/version/binding SHARE；current_version/启用/adapter未撤销及全profile+mapping+proof摘要严格一致才返回完整ResolvedMetricProfile。来源配置改版或停用立即拒绝，不引入未经合同定义的全库TTL。
4. revoke(session,current,profile_id,expected,request_id)：当前release.manage，clock→head CAS，只停用head、递增revision并audit/outbox，不改历史profileJSON。
5. revoke_binding(session,current,profile_id,version,adapter_version,expected,request_id)：同上，只撤销精确映射revoked_at与内部head版本，不改参数JSON，不影响其他adapter绑定。
6. candidate_page(session,current,after='',limit=50)：monitor.read的内部keyset基础，limit只20/50/100/200，返回原profile items、内部after及registry_revision供root签游标；只包含有效head/current来源，fixture仍严格数据库guard。不是原GET全部完成。

Authority重新核验不可在持SQL锁时发网络；publishing源锁先于metric clock/head，精确读取也保持同序。调用者所有失败必须回滚外层事务，包括审计/outbox故障；本阶段未拿mock session证明真实事务隔离/触发器有效。

## 原GET尚未解决的过滤器

原GET /api/v1/metric-profiles还有q/status/date_from/date_to/operator_user_id/channel_id/metric_profile_id/entity_type；其中状态、日期依据、负责人/渠道适用性没有明确Profile字段或现成业务绑定定义。candidate_page只提供严格内部键集，不静默接受其他kwargs。root公共入口应在逐项定义前显式UNSUPPORTED/FIELD_INVALID，不擅猜q按版本包含或日期按created_at、也不声称已完成原GET。原Page.data_as_of、scope_version、权限/筛选/目录版本签名游标由root入口接入，不能直接把裸after暴露给浏览器。

## 当前证据及下一真实队列

60项纯测覆盖原字段/NULL/字符串version、明确mapping不推导、来源证明UTC/受控引用/空配拒绝、精确fixture边界、发布同版本冲突/重复不增事件、旧撤销不复活、source变化/未来观察阻断写、精确读取proof/hash/mapping/版本/撤销失败、当前META来源改版先于head拒绝、整配置及精确binding撤销只改状态并审计、未知page_size/未定义过滤器不默许；增加目标身份缺失及五字段漂移拒绝、目标无launch.read仍可用、caller实际launch.create核验，以及候选DDL六表六触发器与四种严格小写十六进制hash约束静态检查。真实SQL尚未执行。

下一需主线将SQL候选转正式040并排真实工具：空库/FK/不可变触发器，真实SQL发布→精确source/head→ResolvedMetricProfile，FIXTURE隔离拒生产，当前授权/目标owner/跨租户，来源配置换代与停用，双writer CAS/幂等重复，1644保证version/head/binding/audit/outbox/clock全部回滚，精确binding撤销不误伤同profile其他映射，EXPLAIN键集及精确复合键。生产META实际映射回读与能力包仍缺凭据/外部环境证据，不能标完成。


## 公共接入前置（本轮最终核对）

现授权桥中system不属于BUSINESS_MENUS；发行已改为复用现require_system_access(...,31086,'system.release.manage')，不走错误的business system注册。原monitor菜单尚未在role_bridge.BUSINESS_MENUS编译，candidate_page因此保持403关闭；需要root分配原monitor.read叶子和现菜单桥接后，才可开放原GET候选，不借system.read代替monitor.read。

最终51项纯测0.78秒及Ruff通过；source→metric clock SHARE→head/exact version/adapter的精确读取顺序已完成。META配置版本在head之前共享锁复核，候选SQL也排除来源已停用或改版的META行。所有实际SQL/触发器/FK/事务并发与HTTP仍待主线执行；此次只交候选DDL，不自动注册迁移或路由。

本轮定点审查：四种hash列均NOT NULL并要求64位小写十六进制；evidence_ref沿用受控ASCII字符与长度约束。MySQL仅检查存储边界，读取仍由应用重算原规范JSON摘要，不以JSON CAST替代canonical一致性。候选DDL为6张表、6个触发器。
