# 032 分配持久队列独立交付检查点

## 当前状态与可运行入口

新增032迁移、`launch_allocation_packet.py`、`launch_allocation_runtime.py`、`launch_allocation_worker.py`和两份专属纯测；未修改021、DAG冻结源、公共app/harness/Task表、A账户或C素材核心，未运行共享数据库/浏览器、Git或平台写入。

没有注册公开POST/GET路由，没有生产能力适配器。`AllocationRuntime(provider=None)`受理/领取前503 ALLOCATION_PROVIDER_UNAVAILABLE，不产生队列行。生产trusted provider需另行实现真实caller/实际owner来源权限、身份/能力包及C当前030扫描证明；当前A观察GET、任意capability_version、READY或fixture verified均不能代替该证明。

原Task ID明确null；runtime UUID不是公共Task，原GET allocation响应保持Allocation及AllocationItem严格字段，后者包含account_id。生产公开接收还须前述provider、原HTTP鉴权/CSRF/If-Match/幂等边界、真实事务/容量结果及实际素材引用验收，不因本次核心可导入就提前接入口。

## 冻结输入与64MiB边界

原PlanWrite仍严格5MiB。packet另限定内部完整文档64MiB、256KiB块、最多256块。材料证明只接受revision/sha256/kind/mime/byte_size/width_px/height_px/duration_seconds，不接受Token或额外私密字段。完整图每slot兼容bitset以固定宽度十六进制表示，500素材对应125位字符，不用可能丢精度的JSON大整数。

输入hash兼容原allocation-v1求解器，但其source_hash进一步绑定provider原来源指纹、完整计划hash、plan revision、当前授权指纹与完整素材元数据。这样即使slot key/素材集合相同，身份、URL、配置或计划版本变化也不能撞021唯一输入键、重用旧兼容图。每项原请求/旧seed和原capture来源完整冻结；恢复不能从当前新请求覆盖旧输入。

manifest有有序(ordinal,byte_size,payload_hash)清单摘要及连接文档摘要。每块先检查连续序号、真实字节数、256KiB/总64MiB限制和sha；重组后再验证完整hash、UTF8、规范JSON、严格schema、完整slot/素材/兼容图与原input_hash。不对单块单独UTF8或JSON解码，允许字节边界在emoji中间。任何缺块/篡改不返回部分输入，不把未知兼容边变成true。

纯容量已检查两种合法极端：精确5,242,880字节原配置+10000slot×500素材全部兼容图，内部6,659,451字节/26块；另500实际账户合计10000slot×500素材全部边完整恢复。没有截断。真实SQL容量专项另列下文，尚未执行不能标通过；生产最坏兼容图CPU、峰值内存、锁等待/故障压力仍待正式压测。

## 队列、围栏、发布与失败

032 runtime/chunk/guard均中文COMMENT、同租户FK；guard对(tenant,plan,allocation)复合FK，同计划只有一待求解指针。phase先CAPTURED，原配置/完整块/清单/真实allocation/guard/审计/outbox/幂等在同一事务内完整后才QUEUED。没有先响应202再补缺失块的窗口。

领取按QUEUED时间索引及过期租约索引分开有界SKIP LOCKED扫描，避免OR扫描大文档；固定provider_kind隔离。claim_token、worker_id、递增generation及数据库UTC lease共同校验。旧领取结果、过期租约、换代/已终态结果均409。输入读取前重新核原actor当前launch.edit、tenant及无锁计划可见性；不能因已有历史job就绕过撤权，也不提前持plan写锁逆转C→launch顺序。

CPU求解在spawn独立进程，不持数据库事务/源对象锁。纯建图/求解共享最多60秒预算，父进程另留启动/传输窗口并对超限进程terminate/kill；这不是已部署的系统内存JobObject限额。求解成功后续租，发布再次独立实时授权/来源证明。纯CPU超时沿原hash/seed/真实guard有界异步重排，达到受控尝试上限FAILED，不伪造部分解或换新Task。数据库/审计故障回滚并留租约恢复，不把自由异常正文写给用户。

生产provider必须先取得统一来源clock、旧新素材union全局排序锁和同事务旧引用ticket，再让runtime取得launch clock/plan CAS。发布核当前plan revision/hash/state、claim、guard、旧active UUID+input_hash及完整当前包；复用纯DAG检查全映射/兼容边/计数/素材版本。10000 items按200行批写但在单个发布事务提交；旧active及其真实引用直到新结果/引用/审计/outbox全部成功才替换，任何故障回滚旧结果不变。长发布完成前再次以数据库UTC核租约，持行锁不等于自动延长租约。

成功COMPLETE后才能公开SUCCEEDED及连续完整items；GET不把缺失/部分manifest或超过10000结果作为成功。FAILED有受控警告码、审计/outbox，guard同事务释放；原分配历史不删除。重新分配新意图需seed+1，溢出拒绝。原allocation原schema无CANCELLED，不创造该公开枚举；取消重新分配弹窗不删除原结果。

## 独立真实事务工具（首轮送验清单，最新结果见文末）

入口`tools/launch_allocation_runtime_checks.py`：

`run_launch_allocation_runtime_checks(admin, database, cases)`

固定`LAUNCH_ALLOCATION_RUNTIME_CASES`14组，只允许本机13306且严格`orbit_py_it_[a-f0-9]{32}`库，需001—032迁移。无需新HTTP/router/client；从已有root人员fixture取得真实业务授权。工具用显式ISOLATED_TEST provider和专属SQL计划/账户素材标识夹具，只证明队列与SQL事务协议，未调用C引用登记，不假称已通过真实素材扫描/平台兼容性或用户界面。

1. 无provider503且零受理写入。
2. 真实完整capture/块/幂等原键重放。
3. 实际并发同输入复用、不同意图BUSY、同键换请求409及单guard。
4. 真实MySQL审计trigger失败，allocation/runtime/chunk/guard/幂等整体回滚。
5. 两真实连接并发SKIP LOCKED仅一个claim及有效心跳。
6. 实际删除块导致整份拒绝，事务回滚后原块可恢复。
7. 数据库UTC过期后重领代次递增、旧结果不能写回。
8. 完整items发布及原schema、task_id=null。
9. 受信来源指纹变更、真实launch.edit菜单撤销均拒绝发布。
10. 新分配发布审计故障全回滚、旧active/items保持；恢复原claim后一次整批替换。
11. 跨租户复合外键实际1452与失效claim拒绝。
12. FAILED审计故障回滚/恢复，审计和outbox各恰好一次、guard释放且无部分items。
13. CPU超时协议沿原input_hash/seed重排，旧claim失效，围栏新代次领取及受控上限终结。
14. 原配置精确5MiB、10000slot×500素材完整兼容图实际SQL捕获/恢复/求解/10000 items单事务发布；返回安全数量metric及`real_platform_verified=false`。

工具不启动共享服务，由主线串行执行；首次送验时未记上述14组PASS，后续实际结果见文末。C的真实ALLOCATION引用释放/注册、最新CLEAN、生产身份/能力/政策provider和跨模块真实合法发布另需专项，不被ISOLATED_TEST SQL通过代替。

## 当前纯测与冻结

首次新packet/runtime30项纯测PASS5.04秒；包括UTF8跨块、完整规范恢复/篡改拒绝、来源指纹、64MiB边界、严格测试库、实际spawn进程。新30+原DAG/allocator64共94项PASS12.54秒。随后主线批准补load读取前门禁3项（当前撤权/换租户/计划范围不可见均在0次chunk SQL前拒绝），最终新33项PASS4.91秒，全部新源码/工具/测试Ruff PASS，工具py_compile PASS。

032生产源码与工具已冻结给主线真实串行队列；纯33、历史64与真实14分别计，不把重复组合数量当功能完成数，不标整投放模块验收。

## 首轮真实SQL结果：保留失败

主线`python-launch-allocation-runtime-attempt-01.json`实际20组计划中18 PASS、1 FAIL、1 NOTRUN；032迁移成功，前13个队列专项均实际PASS，容量第14组失败，后续退出未跑。不能把父FAIL写成完整032通过，也没有删容量断言或降低精确5MiB输入。

安全栈定位为工具容量enqueue→runtime.enqueue→既有LaunchStore.row首次读取真实5MiB计划时OperationalError2013，接收callback出现BufferError（仍有导出view时不能调整buffer大小）。5MiB fixture的INSERT此前已提交；此次失败尚未进入provider建图、032新冻结分块或CPU求解/结果发布，不能把它归因分配算法时限或分片写入。

本地安装asyncmy0.2.16的接收protocol将bytearray的memoryview交给transport，接收空间不足时原位extend，和异常机制一致；实际transport是否保留view仍由主线独立安全复现核对，不能只凭这段源码臆断。共享驱动/app/LaunchStore由主线处理，B没有修改已冻结源。独立无数据库安全probe已准备，未执行共享DB；容量用例保留待真实复验。

## 最终真实SQL通过与接收兼容证据

主线`python-launch-allocation-runtime-http.json`最终实际20/20 PASS（21.19秒），0 FAIL/NOTRUN，包含全部14个032队列专项。真实原计划5,242,880字节、内部manifest 6,659,460字节/26块、10000 slot、500素材，全部10000 items单事务发布；没有降低输入、截断字段、减少断言或跳过容量节点。该SQL结果与先前纯fixture的6,659,451字节差异来自真实夹具元数据文本，不是丢失字节。

历史回执分别保留，不把父FAIL改写：

| 回执 | 实际结果与根因 |
| --- | --- |
| attempt-01 | 18 PASS / 1 FAIL / 1 NOTRUN；首次真实5MiB读取，接收BufferError继发2013断连 |
| attempt-02、03 | 各18 PASS / 1 FAIL / 1 NOTRUN；独立SQL父进程没有导入config.database，兼容实际未安装，不能据此认定Cython缓存类或类替换无效 |
| attempt-04 | 18 PASS / 1 FAIL / 1 NOTRUN；真正显式安装兼容后大字段读取/求解通过，暴露DAG内部默认JSON空格让合法5MiB膨胀而413 |
| 最终http命名回执 | 20/20 PASS；限定接收兼容实际安装、DAG内部规范紧凑序列化，所有原校验仍保留 |

DAG修复只给内部`json.dumps`增加紧凑separators，未扩大原5MiB限制；新回归精确合法5MiB生成5000广告/20006真实节点，同一配置多1字节严格413，DAG38项实际PASS（5.77秒）。

接收问题已通过官方`asyncio.protocols._feed_data_to_buffered_proto`确定复现：该适配循环下一轮get_buffer仍可持有上一memoryview，原驱动原位扩容触发BufferError；兼容仅在该冲突时换新bytearray，旧view仍有效，继续复用原压缩/扩容逻辑。真实应用及独立SQL工具显式调用installer，不靠import副作用，也不保留未证实的Cython缓存推断。细节与官方源码链接见[MySQL接收兼容说明](MYSQL_ASYNCMY_RECEIVE_COMPAT.md)。

独立`launch_allocation_asyncmy_receive_probe.py`及`test_asyncmy_receive_probe.py`17项纯测PASS（0.22秒），覆盖原方法baseline、兼容完整5MiB二进制逐字节、held view、压缩、缩容、12轮消费追加、显式安装状态/平台版本围栏。标准库helper复现不等于普通TCP必然失败；原先普通TCP原版PASS保留。

新增eventgate TCP实验未修改transport，仅自有127.0.0.1随机端口/固定二进制数据：剩余32768接收空间时再发送65536，原方法Proactor实际接收262144字节后BufferError；兼容实际接收5242880全部字节且binary_exact=true、0 callback错误。此为特定受控分段的实际TCP复现，不泛化成所有分段都会失败；全程无数据库、SQL、凭据或平台。

边界保持：20/20是ISOLATED_TEST provider下的队列协议/当前launch权限/真实事务和输入容量通过；provider没有登记C真实素材引用，没有证明真实CLEAN、平台身份/能力/政策或广告写入。生产provider仍None→503，未注册分配公开路由，公共Task桥接仍后续节点。真实SQL规模也不是峰值RSS、冷缓存/并发压测或整PY06验收。
