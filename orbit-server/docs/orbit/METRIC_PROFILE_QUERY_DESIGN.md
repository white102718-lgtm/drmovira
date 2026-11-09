# 指标配置分页与配置来源水位设计

本阶段实现新 `metric_profile_query.py` 和041候选SQL。此前040注册内部真实13组已由主线24/24档通过并推送；本阶段分页/041仅纯测，不继承为真实MySQL或HTTP验收。原GET的未定义筛选语义仍有缺口。

## 入口与合同

`MetricProfileQuery(tokens: DirectoryTokens, *, isolated_fixture=False).page(session, actor: int, authorization: str, raw_filters: dict)`。session必须空闲，由page自行begin；不得先在route使用同一session普通SELECT或套begin。内部一次原`require_business_access(session, actor, 'monitor', 'monitor.read')`产生current并复核当前授权。主线注册monitor原菜单/权限与`METRIC_PROFILE_CURSOR_V1`密钥用途；本阶段不改公共鉴权/路由/凭据类。

输出严格`MetricProfilePage`四字段：items（每条原12字段）、next_cursor、数据库UTC data_as_of、真实目录scope_version。profile为租户共享配置，无虚构Ownership/目标owner动作；不返回adapter、配置UUID、凭据、内部证明或来源连接信息。verified保持原实际布尔值，列表展示不能解释成平台写授权。

支持q和metric_profile_id精确UUID，相互AND；不同UUID取空交集，q不做名称包含或前缀扫描。page_size仅20/50/100/200字符串，cursor显式空/超长422。status/date_from/date_to/operator_user_id/channel_id/entity_type及未知字段400 UNKNOWN_FIELD，不静默吞掉。原接口这些字段含义尚未明确，不能声称GET所有功能已完整验收。

## 新事务、锁顺序与游标

1. page拒绝已开启事务的session，避免MySQL RR在旧snapshot下配上新clock。
2. 当前monitor授权、identity.auth_version、orbit_directory_clock及metric_profile_clock全部locking read；fixture模式SELECT DATABASE()不读InnoDB。
3. 持metric clock共享锁后，列表JOIN为本事务首个普通InnoDB一致读。配置、profile版本与head均不在这里加锁，不形成clock→config反序。
4. 来源写入保持source configuration行→metric clock顺序；配置事务必须先完成触发clock更新才能提交，因此新列表快照与clock一致。
5. 签名游标绑定真实session_binding、actor、tenant、subject/team/data_role、当前auth_version、目录scope版本、精确规范filters/page_size、metric clock、last UUID与data_as_of。改session/actor/范围/筛选409 SCOPE_CHANGED，改clock409 METRIC_PROFILE_CHANGED；签名/时间损坏400。前后页沿用首批data_as_of，但不声称长期快照保留；水位变化要求回首页。

主查询按`(tenant_id,state,id)`索引的ENABLED keyset，current_version通过版本主键定位；配置通过(tenant,id)定位。LIMIT+1最多201原profile，不做OFFSET或无界历史扫描。q/id均等值条件。需要真实EXPLAIN及21+分页/并发来源变化专项，纯测与LIMIT本身不构成容量验收。

## 来源与坏行

正式默认只能返回已040发布的META行；校验authority_kind=TRUSTED、当前META_BM配置enabled和精确revision、profile规范SHA256、原schema/id/version/source、来源证明严格五字段/受控文本/UTC时间/source SHA/evidence/config pair。TRUSTED字符串不是实际Meta连接证据；本接口也不建立新权威来源。配置停用或版本不再匹配的profile按可用候选不可见，payload/hash/proof坏行使整页503，不跳过后续假成功。未返回完整原对象路径或来源秘密。

显式isolated_fixture=True仅主线隔离夹具使用，开页先核127.0.0.1:13306和实际orbit_py_it_<32hex>，空items同样受控；FIXTURE必须ISOLATED_TEST。默认正式模式读到FIXTURE会503，不能自动降级。纯测使用本地专用HMAC fixture验证DirectoryTokens真实签名/篡改拒绝，不是生产密钥或真实权限验收。

## 041候选

仅3个`orbit_system_configuration` AFTER INSERT/UPDATE/DELETE触发器。只涉及META_BM变化；任意META_BM行更新保守递增完整目录版本（包括与展示无关的配置变化），不猜业务字段子集。删除/移出META更新旧tenant；插入/移入META更新新tenant；META跨tenant同时更新旧新clock并`ORDER BY tenant_id`，精确ROW_COUNT=2。任何缺clock/MAX耗尽SIGNAL 1644，整个来源事务回滚，不允许来源变化静默失去游标水位。

不新建表、不修改040，不在触发器里创建clock。新租户必须由主线初始化所有业务clock后才允许META_BM配置写入；缺clock不是自动fixture初始化。现FK可能阻止删除已被历史版本引用的配置，041不放宽既有FK，也不声称所有DELETE可执行。主线负责真实迁移、触发器与已有配置触发器共存/回滚/死锁专项；多个来源配置并发writer仍按来源→clock约束由既有事务重试策略处理。

## 当前验证

47项纯测覆盖严格过滤、21条真实签名keyset模拟、多维游标绑定、坏签名、新事务拒绝、空fixture生产边界、原12字段/共享无Ownership、坏profile/proof/meta来源失败关闭及041结构护栏。未运行真实041、HTTP、浏览器、容量或外部Meta核验。下一由主线注册路由/MAC/原monitor菜单，串行执行真实SQL与HTTP后记录具名证据。


2026-11-08定点审查补充：列表现读取040独立observed_at列，与proof观察值按MySQL DATETIME(3)默认半毫秒四舍五入比较，包含跨秒/日/年进位；不能简单truncate原微秒值。数据库列本身必须毫秒整齐且不晚于数据库now(3)，错列/未来/无法进位日期失败关闭。SQL样本使用同一毫秒对齐观察值写proof和独立列。当前query纯测61项，真实MySQL/HTTP尚未跑。本设计前述47为此前历史纯测范围。
