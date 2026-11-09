# 素材生命周期设计与逐项交付

状态：设计完成，生产接入/真实验收未完成。依据原WORKFLOWS：24小时未完成上传取消并清理孤立分片；逻辑归档保留历史；历史证据引用阻止物理清理；文件最短保留30日。010历史不改，新增019迁移。

## 时间、状态与可恢复边界

- 仅可信系统Worker入口，无用户请求可传任意根目录/租户/文件路径；不提供匿名清理API。默认不自动注册调度、不自动启用物理删除。每次1至50任务，数据库候选最多50，显式固定UTC时钟便于边界测试。
- 上传过期：upload在INITIATED/UPLOADING且expires_at<=当前UTC；资产也必须仍在INITIATED/UPLOADING。短事务把upload置EXPIRED、asset置UPLOAD_FAILED并记录UPLOAD_EXPIRED，递增版本/目录clock，原子写审计+outbox+唯一生命周期任务。已COMPLETE/SCANNING/PROCESSING/READY绝不因旧上传记录误删。READY去重的别名upload只能回收自己的upload.id对象，不能回收asset.object_upload_id指向的已就绪共享对象。
- 孤立未完成分片是24小时回收例外；完整资产物理保留采用保守的归档后至少30个完整24小时，不能按“创建已满30日”使刚归档文件立即消失。等号边界可清理，早1毫秒拒绝；所有查询用UTC时刻，未猜业务日期筛选含义。
- 归档候选：asset.state=ARCHIVED、archived_at非空且<=now-30d、physical_cleanup_state=LIVE、无活跃分配/执行引用、无任何HISTORICAL_EVIDENCE引用（不因其active=false而放行）。保留数据库资产/审计/引用元数据，物理清理不调用Meta删除。
- 019只加生命周期队列和物理状态/删除时间。队列PENDING/RUNNING/RETRY/DONE；kind=UPLOAD_EXPIRY/ARCHIVE_RETENTION，唯一tenant+kind+upload。领取token与generation防迟到回写，lease有界；失败记录安全错误码与退避due_at，不能把删了一部分当DONE。恢复过期租约时先改token/generation，旧完成回写不匹配则STALE。

## 事务、租约与引用竞争

1. 统一短锁顺序clock→asset→upload/生命周期job→引用，业务job检查不倒置已定processing锁顺序。并发扫描使用键集/索引与SKIP LOCKED，一次认领不持数据库锁进行文件I/O。
2. 对ARCHIVE_RETENTION，在同一事务重新检查期限、asset版本及引用后，先置physical_cleanup_state=CLEANING并持久认领token。所有未来引用写入必须先锁同一asset并要求LIVE，再插入；这样禁止“无引用检查后、物理删除前”追加新历史证据。提供独立门禁helper，但未来引用调用方未接入前不能声称物理清理整体可启用。
3. 文件操作成功后再次核对token/generation与CLEANING，写PURGED/physical_deleted_at、DONE和审计。若DB提交失败但文件已删，租约恢复后重复删除不存在文件视幂等成功，元数据不会误复活。若文件删一部分后失败，状态CLEANING、任务RETRY，后续只继续受控剩余键。
4. 清理服务不借用某个已离职用户的功能权限。系统维护权限是可信进程构造和固定对象适配器，租户范围永远来自数据库任务而非调用入参；审计actor_id=0并明确系统维护动作。生产服务身份/调度必须由主线配置接入，普通HTTP用户不能触发任意租户清理。停用租户可继续完成安全过期/已归档保留策略，不扫描或处理投放数据。

## 文件系统协议与默认禁用条件

现LocalMaterialObjects把HTTP文件I/O放在两段短事务之间。只有Worker查状态然后unlink会与已取得快照的迟到PUT/合并/处理器写竞争，导致回收后文件再次出现。因此需要per-upload跨进程文件guard和持久tombstone：

- guard与tombstone放在可信root下固定内部目录、仅规范tenant/upload UUID键，拒绝任意路径、symlink或Windows reparse point。不能递归删除root或租户目录。
- 分片、合并、预览发布等所有真实写方都须在guard内检查tombstone；生命周期在同一guard内先持久写tombstone（只保留原因/任务标识），再删除允许键。墓碑保留在对象目录外，不能在清理对象后丢失；旧UUID写入永远拒绝。
- 仅删除目标upload目录内受控普通文件：part-五位数字、服务端temporary-UUID、preview-UUID.jpg、original、preview.jpg。事先枚举有界并检查所有条目；未知文件、子目录、链接/重解析点明确失败，不能追随或用递归删除绕过。文件不存在幂等；目录仅在空时rmdir。对象根从可信构造传入，不创建或清理用户指定根。
- 当前原写方尚未接入该协议；新Worker默认writers_fenced=false，允许登记过期与排队，但物理删除明确FENCE_NOT_INTEGRATED重试，不能伪成功。主线后续允许定点改现对象适配器/预览发布后，才打开真实物理清理专项。保留原预览进程和现有对象，不对共享对象根做试验性删除。
- 进程死亡/部分删除/权限错误/墓碑持久化失败均用真实独占临时文件测试恢复。媒体处理最大时限不代替文件写guard，Windows锁与POSIX锁分别按当前平台实际验证。

## 开发、测试、验收清单

- [x] 逐阶段设计和引用/写入竞争依赖登记。
- [ ] 019 DDL与候选索引；真实迁移/EXPLAIN验证。
- [ ] 独立系统Worker：24h精确边界、完成上传不取消、去重别名不删原对象、30d边界、历史证据/活跃任务阻止。
- [ ] 持久墓碑+跨进程guard，现所有写方接入并真实并发验证。
- [ ] 文件缺失幂等、未知键拒绝、链接拒绝、删除失败重试、DB提交失败/进程死亡恢复、迟到租约回写拒绝。
- [ ] 真实HTTP上传→过期/归档→实际对象回收、审计/版本/历史元数据检查；只用本轮UUID临时库/目录。
- [ ] 真实容量候选EXPLAIN/批次延迟、生产调度/对象云适配和权限接入。

## AV只读现状及后续真实适配

本机PATH未发现clamscan/clamdscan/clamd；指定参考backend、schedulers的Python/文档检索未找到ClamAV扫描实现（不等于所有隐藏配置或二进制都不存在）。现素材SCANNING只证明魔数/媒体解码，没有病毒扫描引擎证据。

建议独立受控AV适配器记录引擎版本/可信可执行文件SHA/签名库版本和更新时间；扫描原始不可变对象，时间、输入大小、stdout/stderr严格有界。实际发现病毒→QUARANTINED；引擎缺失、签名库未知/过旧、超时、协议异常→明确未验证/处理失败，不伪CLEAN。合成协议夹具只能证明分支与门禁，必须用真实引擎、真实更新的签名库及安全测试签名完成正/负实测后才说AV已验收。部署策略、固定版本来源与允许的签名库更新由主线确定；当前未安装、未改变全局PATH、未启用生产扫描。媒体READY的既有证据不能替代AV完成标记。


## 首阶段实际开发结果（尚未数据库验收）

019队列DDL、独立 `material_lifecycle.py` 与 `material_lifecycle_objects.py` 已实现，无app/定时器注册，不改冻结的旧objects/routes/store/library。Worker在writers_fenced=false时只重试排队，保持物理LIVE、不删除文件。新引用门禁先锁clock再asset，与系统锁顺序一致。候选过期/归档、认领/租约恢复、迟到完成拒绝、元数据物理状态和审计/outbox仍需真实MySQL检验。

`test_material_lifecycle_objects.py` 12项实际通过：独占临时文件的默认拒删、白名单回收/墓碑防旧UUID写入、部分真实unlink后注入失败及幂等重试、未知键/目录/任意路径拒绝；另启动真实第二进程持有OS文件锁，当前进程互斥失败，杀死持锁进程后锁释放。Ruff/格式与新模块语法通过。这只证明当前平台的文件协议，不代表现HTTP上传/合并/预览写方已接入，也不证明所有平台的锁行为。

`tools/material_lifecycle_checks.py::run_material_lifecycle_checks(admin,database,object_root,cases)` 已准备6个真实MySQL/本轮临时对象专项：精确过期边界与完成上传保留、默认禁用物理删除、独占过期对象实删墓碑、30日边界/历史证据阻止、物理回收保留元数据审计与迟到回写拒绝。尚未运行。数据是明确独占元数据夹具，不把COMPLETE/READY夹具当成实际上传证明；后续真实HTTP全闭环需对象写方统一接入后另验。

仍待补：真实租约并发/崩溃恢复、数据库提交失败后恢复、历史引用竞争、完成上传与过期同锁顺序、软链接/Windows重解析点专项、目录/文件数上限容量与EXPLAIN；生产进程身份/调度与对象云清理也未接入。不会因12项文件单测标完整生命周期验收。


### 官方AV资料核对与不能漏的限制判定

已核对[ClamAV官方安装文档](https://docs.clamav.net/manual/Installing.html)：存在官方Windows构建，但需要独立配置签名库/更新器；本轮只读，不安装。[官方扫描说明](https://docs.clamav.net/manual/Usage/Scanning.html)区分一次性clamscan与常驻clamdscan；每次clamscan重新载入引擎/签名，因此生产容量宜独立受控扫描服务，隔离本机验证可先一次性工具。[官方FreshClam说明](https://docs.clamav.net/faq/faq-freshclam)要求使用受支持更新流程，不用自造循环裸下载签名包。

关键风险：官方说明max-filesize限制可能跳过过大文件并将其当clean。因此适配器不能仅看退出0；必须验证扫描对象字节数/已扫描数量、全部限制告警、签名库有效性与引擎健康。合法MP4上限500MiB必须落在实际配置的文件扫描上限内；容器展开/总扫描量/时间仍设硬上限，任何限额跳过都标未验证/失败，不标CLEAN。建议执行命令不启用remove/move/copy，原对象始终由ORBIT隔离状态和生命周期保管，避免引擎擅自删除或搬移造成历史缺失。扫描返回日志只提取安全分类/版本/签名ID，不透传原始路径或日志。

集成Worker时还需把“病毒扫描耗时+媒体处理”纳入认领租约/心跳与授权复验，不能扫描超出旧lease后继续发布READY。真实AV验收包含：普通真实PNG/MP4、标准安全测试签名、过大/跳过扫描、旧或缺失签名库、超时与引擎错误；协议模拟只算测试适配分支。尚未下载官方AV包或签名库、尚无真实引擎回执，不计开发/测试/验收完成。


### 新独立恢复矩阵工具（5组待实际执行）

`tools/material_lifecycle_recovery_checks.py::run_material_lifecycle_recovery_checks(admin,database,object_root,cases)` 使用主线同一UUID库和独占对象，另创建明确ARCHIVED元数据/队列夹具，不声称HTTP上传已完成。五组包含：实际claim租约超时后recover使generation/token变化，真实旧claim不能提交；新claim实际回收/完成且重复完成拒绝；CLEANING期间调用真实引用门禁拒绝；实际文件已删后MySQL审计触发器1644使整个元数据事务回滚（不能吞任意异常当成功）；移除触发器后恢复租约，缺失文件幂等回收并仅一条完成审计。

该工具和019基础6组相互独立，尚未真实运行；只完成Ruff/语法。没有把“程序抛错”或模拟ACK称作崩溃恢复验收。触发器命名固定前缀+UUID片段，finally只删除本次触发器；不接app或共享预览、不改旧C受测模块。


## 019两轮真实局部验证及写方保护接入

主线 `python-material-lifecycle-http.json` 基础12/12通过，含6组真实Worker/文件；`python-material-lifecycle-recovery.json` 恢复17/17通过，含5组新故障矩阵，实际文件先删后审计1644导致DB回滚，再recover重领、缺失文件幂等续完。两者均是独立生命周期专项，不等于全项目验收，也不证明旧HTTP写方已接协议。生产物理删除仍未启用。

恢复轮结束后，经主线允许定点改旧 `material_objects.py`、`material_processing.py`：put_part/assemble的完整I/O分别持同一per-upload OS guard；process_material从源读取到临时预览/发布完整持guard。数据库snapshot和registration前后两段短事务不改变，任何文件处理期间不持DB锁。original()/preview()使用existing-directory纯读解析，不mkdir，避免回收后迟到读取重建空对象目录。

顺序保证：清理先持guard并写永久tombstone，则后到的分片/合并/预览写入在创建目录前拒绝；写方先持guard，清理只能等其释放后再删，因此不能出现清理DONE后旧写重新生成分片。完成上传若先提交COMPLETE/SCANNING，过期Worker短事务重新核状态后不得取消。历史引用先插入则claim必须阻止；清理先置CLEANING则新增引用门禁拒绝，未来实际引用调用方仍必须接入该门禁，不能仅凭helper存在声称全部调用已保护。

素材当前101项纯测一次合跑通过（含13项生命周期文件专项）。新 `tools/material_lifecycle_race_checks.py::run_material_lifecycle_race_checks(object_root,cases)` 三组实际本机跨进程竞争已通过：part/assemble/Pillow真实写段持guard暂停，另进程回收得到OBJECT_BUSY；释放后真实写或解码完成，再真实回收；所有迟到写拒绝且目录不重建。证据 `python-material-lifecycle-local-writer-races.json` 仅本机文件，不代HTTP/数据库快照竞争。

### 新真实HTTP/引用竞争工具（3组尚未执行）

`tools/material_lifecycle_http_race_checks.py::run_material_lifecycle_http_race_checks(client,admin,database,headers,object_root,cases)`：

1. 对隔离18083实际发送Expect:100-continue PUT，只发headers。按[Uvicorn官方行为](https://uvicorn.dev/server-behavior/)，100只有应用调用receive读body时发出；该分片路由先完成授权/上传snapshot事务才读body，相关当前中间件不提前消费该普通二进制body。因此100是已取快照的屏障，不用sleep猜测。仅加速这一个测试upload deadline为过期，运行真实系统Worker及对象回收，再发真实PNG body；必须409 OBJECT_EXPIRED、无part登记、无目录/分片复活。凭据仅在内存构造HTTP，不打印headers。
2. 另一个真实HTTP上传先成功part+complete202到SCANNING，再将其旧deadline置过去，过期维护必须保留COMPLETE/SCANNING/LIVE与真实original。
3. 通过真实批量归档接口归档第二素材，加速保留时间为31日；enqueue后、claim前通过真实referenceable门禁及SQL事务写入历史证据（当前无产品历史引用API，不虚构一个接口），随后Worker必须保留ARCHIVED/LIVE及原文件。反顺序CLEANING时门禁拒绝已在恢复5组验证。引用模块实际业务权限/生产接入不由此假定完成。

该工具只在当前orbit_py_it_UUID、本机13306/18083和本轮对象目录运行，未启动服务、未部署、未在共享对象上试删。当前仅Ruff/语法检查，3组HTTP尚待主线串行执行。过期后用户先归档UPLOAD_FAILED的交错仍为明确gap：不能凭猜测将完整已接受原对象按24h删除；后续须区分孤立parts与已完成原对象再补合同矩阵。
