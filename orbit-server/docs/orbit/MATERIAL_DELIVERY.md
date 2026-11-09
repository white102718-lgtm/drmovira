# PY-05 素材库首批交付记录

2026-11-08，实施文档第七节 C 线。此文档为局部开发记录，不代替总台账；当前模块尚未完成验收。

## 当前交付状态（2026-11-08）

正式租户扫描配置消费者已接入并完成本轮局部真实验收：034租户单例、12类63字段（原11类62字段保留）、受控候选/安全PNG测试、配置版本CAS、030正式来源绑定、原子状态/审计/outbox与扫描配置页面。最新 `evidence/python-material-scanner-configuration-scope-browser.json` 为40/40 PASS（34.99秒），含原10配置组、12范围负例、USER8及初始化/元数据/退出和实际新配置3视口；新业务影响文案已实测。旧配置原11类62字段 `evidence/python-configuration-existing-browser.json` 另3视口及7组汇总PASS（151.31秒）。精确范围与失败沿革见 `MATERIAL_SCANNER_CONFIGURATION_DESIGN.md`。

本轮范围负例实际覆盖真实异租户、SUPER/TEAM与动作、同Token撤权/身份停用、无配置/停用/空registry、扫描后内存注册撤销/换代、A→B→A、真实外租户FK及历史CLEAN来源不回写。候选Unicode/严格availability边界的54项Python和21项前端纯测独立计，不以其代替固定中文fixture的实际HTTP/UI结果。

每应用默认空registry，未明确发布服务器可信profile时仍不可用；受控launcher、生产正式profile、多进程registry尚未完成。素材指标/业务日期/渠道事实筛选、大规模查询容量、HTTP500MiB/资源峰值、生产云存储与调度等仍存在缺口；生产物理清理默认关闭及历史证据保留边界继续有效。本模块没有标全部PRD完成，也没有部署或真实广告写入验收。

以下为按实施阶段保留的历史记录。早期表格中的“浏览器待运行/AV待接/030未加入”等仅代表当时基线，不是当前状态；当前结果以文首、后续具名回执和专项交付文档为准。

## 历史首批基线：首个闭环与真实边界

目标入口为 `/orbit/assets`，保留若依 layout、菜单和 Vue3 + Element Plus。首批流程为分类/标签目录 → 分片上传 → SHA256/尺寸/魔数核验 → 持久队列 → 真实图片解码/缩略图或视频处理 → READY → 元数据编辑/详情预览/引用关系 → 整批逻辑归档。

开发文件为 `python/orbit_api/material_*.py`、`migrations/010_material_library.sql`、前端 `src/api/orbit/material*.ts` 与 `src/views/orbit/materials/`。公共菜单、权限、配置、路由注册和真实集成由主任务统一负责。

| 页面或流程 | 开发 | 测试 | 验收与缺口 |
| --- | --- | --- | --- |
| 素材列表、名称/分类/标签 ALL/ANY/类型/状态/名称排序、键集续页 | 已有代码 | 90629筛选局部HTTP通过；游标/浏览器待专项 | 指标、业务日、渠道/指标配置筛选尚未接事实 |
| 上传弹窗、每批50个、逐项结果/内存重试、停止剩余上传 | 已有代码 | 53单测及小PNG HTTP通过；浏览器待运行 | 中断后仅当前页面内存续传，过期清理任务待补 |
| 分片幂等、尺寸、总 SHA256、MIME/魔数 | 已有代码 | 小PNG HTTP/MySQL通过；9.44MB双分片纯文件通过 | 大文件API/浏览器与边界仍待，不以纯文件替代 |
| 图片真实解码/预览、视频封面/时长 | 已有代码 | PNG真实HTTP、JPEG EXIF/MP4纯文件通过 | 视频HTTP/Worker/浏览器、故障恢复与恶意样本待补 |
| 标签分类新增/读取/编辑/停用、固定未分类、停用标签保留旧关联 | 已有代码 | 基础HTTP/MySQL专项通过 | 目录搜索、标签恢复（合同未定义）不伪造已有功能 |
| READY 元数据编辑、详情和授权预览 | 已有代码 | HTTP相关专项通过；浏览器待运行 | 三视口、无权/撤权/冲突、并发需真实复验 |
| 引用二级页、批量归档/引用拒绝/CAS/事务回滚 | 已有代码 | 90629实际多素材归档/引用拒绝/回滚通过 | 后续分配/执行模块真实登记引用、历史证据保留需联调 |
| 大规模指标筛选、七项指标排序、查询性能 | 未完成 | 未运行 | 不把未知指标填0，不用名称排序冒充完整指标排序 |
| 云对象存储、生命周期/孤立分片清理、生产Worker调度 | 未完成 | 未运行 | 本地隔离对象适配器不代表生产存储验收 |

## 字段、状态与异常

- `name` 为1至100个字符，NFC、去首尾空白；默认文件名去扩展名，仅显示，不用作路径。
- `metadata.category_id` 必须为本租户启用分类；系统固定“未分类”不可改名或停用。有活跃素材的分类停用被拒绝，先迁移素材分类。
- `tag_ids` 为0至20个不同UUID。停用标签不能新关联，编辑时可保留已有旧关联。
- MIME白名单 JPEG/PNG/MP4；图片20MiB、视频500MiB；上传页面每批50个，API单次一个上传会话。客户端以1MiB块增量计算 SHA256，不整读500MiB文件；上传分片8MiB，服务端合并以1MiB流式读取。
- 原合同状态保留 `INITIATED/UPLOADING/SCANNING/PROCESSING/READY/UPLOAD_FAILED/QUARANTINED/PROCESSING_FAILED/ARCHIVED`。当前实现实际推进前五项、损坏图片隔离、处理工具缺失/异常失败与归档；上传最终失败持久状态及24小时自动清理仍待补，不能因枚举存在标完成。
- 只有 READY 能修改业务元数据或被后续分配。视频时长来自服务器 Decimal；未知或图片时长返回 null。
- 同租户、同拥有者、READY、相同真实已校验 SHA256/字节数/MIME 时返回既有素材ID。不同拥有者不泄露去重结果。技术约定为上传会话 `part_size=0`（原Schema允许0）表示已有READY素材复用，前端重新读取并核验已有对象，不再上传文件；90629同拥有者去重专项已通过，跨拥有者/跨租户仍待。
- 批次归档先按UUID锁全部素材、校验版本和活跃 ALLOCATION/EXECUTION 引用，再修改。任意失败整批回滚。历史证据不阻止逻辑归档，阻止物理清理；当前不执行物理删除，因此不会提前突破30日保留要求，但自动生命周期尚未完成。
- 数值指标范围最多6位小数、计数只允许整数、未知值后置等原要求尚未接统计事实。当前明确返回503，不悄悄忽略筛选，不伪造0。

## 存储、安全和共享接入

主任务通过 `create_material_router(objects=None, origin_provider=None)` 注册。对象适配器为 `LocalMaterialObjects(Path(主任务可信分配目录))`；目录必须预先存在，逐层拒绝链接及 Windows 重解析点。只接受服务端规范UUID键，文件名固定，未知路径不创建、不递归删除。原始文件/衍生文件不直接公开静态服务；预览请求重新执行实时权限与数据范围校验。

URL只使用 `orbit_api.cookie_auth.public_origin` 或主任务注入的可信 provider，不能信任 Host/Forwarded。浏览器上传客户端固定同源技术路由，不把任意服务响应 URL 的主机作为凭据发送目标。

权限使用公共 `require_business_access(..., 'assets', permission)`；素材 `assets.read/upload/edit/delete`，标签分类沿用 `tags.read/create/edit/archive`。一般用户仅自己的拥有者，团队管理员加显式管理团队，超级管理员租户范围。CSRF、If-Match、独立幂等键、审计与 outbox 同事务。每次重新进入对象登记事务都再次授权；大文件 I/O 和处理不持数据库事务锁。

技术扩展（不改原PRD）：`GET assets/capabilities`、`PUT assets/upload-sessions/{id}/parts/{number}`、`GET assets/{id}/references`、`GET assets/{id}/preview`。原始标签分类/素材接口保留；完整API矩阵及覆盖总台账由主任务登记。

## 数据访问路径与容量证据

| 查询 | 索引/边界 | 水位及风险 |
| --- | --- | --- |
| 用户拥有者+状态素材列表 | `idx_material_owner_page(tenant,owner_user,state,id)` | 每页20/50/100/200；无深OFFSET。按name排序仍可能filesort，需EXPLAIN，不宣称已达容量目标 |
| 管理团队素材 | `idx_material_team_page(tenant,owner_team,state,id)` | 管理团队EXISTS与owner并集可能OR扫描；需实际分布评估 |
| 分类筛选 | `idx_material_category_page(tenant,category,state,id)` | name排序与分类组合可能回表/filesort，不以LIMIT声称查询有界扫描 |
| 名称排序/包含搜索 | `idx_material_name_page(tenant,name,id)`；q用字面INSTR不当SQL模式 | keyset `(name,id)`；包含搜索不能直接利用前缀索引，大数据须真实计划及容量测试 |
| 标签ANY/ALL | `idx_material_tag_assets(tenant,tag,asset)` + 素材标签主键 | ANY EXISTS/ALL多个EXISTS；标签低选择性时扫描风险，最多20标签，不用分页掩盖代价 |
| 同拥有者READY去重 | `idx_material_dedup(tenant,owner,sha,state)` | 校验size/MIME，不跨用户返回ID |
| 标签分类列表 | `idx_material_taxonomy_page(tenant,kind,state,id)`及主键 | signed keyset；UI选择器自动读取有上限，专用目录分页，海量标签交互仍待优化 |
| 素材引用 | 主键 `(tenant,asset,id)`，唯一业务引用键 | 技术二级页最多50/页，真实后续写方必须锁素材行，防止与归档竞态 |
| 待处理领取 | `idx_material_job_claim(state,created_at,tenant,asset)` | 一次1至50件，clock→job→asset统一锁顺序；SKIP LOCKED；外部文件处理不持锁 |
| 上传过期候选 | `idx_material_upload_expiry(state,expires_at,tenant,id)` | 24h任务尚未实现；不把已有索引当作清理功能 |

素材游标签名用途 `MATERIAL_CURSOR_V1`，分类标签 `MATERIAL_TAXONOMY_CURSOR_V1`；包含身份、租户、数据范围、筛选/类别、版本与时间水位，过期或变更返回错误重载。当前采用素材目录全局水位使并发变更时游标失效，正确性优先，但频繁写入下体验/吞吐待容量验证。

所有表/字段/索引具中文 COMMENT。当前没有素材规模 EXPLAIN/吞吐/P95/P99 证据，不宣称素材大容量通过。主任务统一执行5万账户/100万事实等容量验收；素材自身需按真实对象数和标签分布补充数据集。

## 已执行和待排队验证

- 2026-11-08：`pytest python/tests/test_material_contract.py python/tests/test_material_objects.py python/tests/test_material_job_policy.py -q`：53通过。覆盖原字段缺失、严格类型、边界、hash、重复标签、完整分片、魔数、真实临时文件、不可覆盖分片、真实PNG解码/衍生和坏PNG拒绝。
- 前端 `material-hash.test.ts`：10通过，跨填充边界/分片及1MiB以上数据与独立Node SHA256一致。`pnpm check:orbit` 通过。它们均不等于业务验收。
- 排队专项 `tools/material_checks.py::run_material_checks(client,admin,database,headers,object_root,cases)`：12组HTTP/MySQL/真实文件/实际Worker，90629合跑中12组均通过；整轮因后续账户失败为FAIL，不可标成完整集成PASS。
- 三视口 `tests/e2e/orbit-python-materials.spec.ts`：计划覆盖真实HTTPS原登录、目录创建、PNG上传、实际Worker、READY、预览/编辑/归档。53716首次实际运行三个视口均在页面挂载失败，未到达业务操作；下文登记真实根因及修复，复验待主线排队。`start_material_browser_worker(...)`只在UUID测试库启真实处理线程，stop/join后才可清理；不注册生产任务。
- 待补：跨租户/跨拥有者/撤权、游标并发、其余审计注入与批次边界、参考写入竞态、进程重启/租约恢复、视频真实工具及异常、所有指标字段、任务调度与清理、容量与浏览器异常恢复全矩阵。不能据53项Python及18项前端测试打勾整个素材模块。

## 认领及完成授权补强（90629相关场景局部通过）

010已在主任务解除冻结后增加 `job.actor_id/actor_auth_version/scope_digest` 与 `audit.change_json`。完成上传时冻结真实发起人版本及该素材相关身份/租户/数据角色/团队/拥有者/文件元数据范围，不以全租户目录clock作为任务有效性依赖。Worker认领、完成和恢复都实时检查 `assets.upload`、当前启用身份与授权版本；撤权进入 `FAILED/PROCESSING_FAILED` 终态，重新启用不会重排旧任务。停用租户的旧任务也会有限处理为失败并继续后续队列。归档使PENDING/RUNNING处理任务失败，不能被恢复器复活。

统一锁顺序为身份授权→素材clock→job→asset；原始文件处理不持DB锁。审计持久化实际归档原因、必要字段前后变化、状态/失败代码，不记录原始文件正文、完整请求或凭据。12组真实专项新增认领前撤权、真实解码后撤权、重新启用不复活、停用租户首条不阻塞有效任务、多素材整批回滚及实际原因审计断言；上述场景已在90629实际通过；恢复器租约故障/并发争抢及auth_version单独变更等扩展矩阵仍待。

原合同 taxonomy 列表的q/status/page_size/日期筛选目前尚未全部实现，不能把标签分类基础CRUD标为完整合同完成。当前接口明确拒绝未接入参数，后续继续补齐。

## 首轮真实专项失败与修复

主任务51795合跑中，分类/标签创建201及capabilities200通过后，固定分类归档失败；未把该轮标PASS。已定位路由误用 `identity_contract._uuid(value,pointer)` 为单参数调用导致TypeError转503。已逐个修复素材/标签分类按ID读取、编辑、归档、预览、引用以及UUID筛选的字段pointer；真实专项增加无效ID/筛选422与固定分类GET及归档409断言，并在失败时仅记录(status,code,message)。另补MIME非字符串结构400及真实JPEG EXIF旋转后尺寸/预览元数据清除。修后53个Python专项单测通过，HTTP重验在90629完成12组局部通过；全模块及浏览器验收仍未完成。

## 90629 素材HTTP局部通过（整体合跑仍FAIL）

真实回执时间 `2026-11-08T04:32:07.775076+00:00`，命令为 `.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 13 --include-materials --include-accounts --browser --browser-module channels`。回执 `docs/orbit/evidence/python-framework-integration.json` 当轮记录182通过、1失败、5未运行；失败发生在后续账户按ID读取，素材12个命名场景均在通过列表中。此结论仅覆盖素材实际HTTP/MySQL/磁盘/处理Worker专项，素材浏览器未运行，整轮不得标PASS。

素材专项已实际证明：分类/标签创建读取、固定未分类不可归档、UUID无效输入422、真实PNG分片/摘要/处理/授权预览、同拥有者READY去重、元数据CAS、停用标签旧关联、标签ANY/ALL与未知指标拒绝、活跃引用整批拒绝、多素材审计失败全回滚及归档原因持久化、损坏PNG隔离、认领前/实际解码后撤权、恢复权限不复活、停用租户排在首条不饿死有效任务。未覆盖项仍按上表列为待办，不据此勾整个素材模块。

另在独占临时目录执行纯文件补充专项：真实PNG 9,441,806字节，2分片8,388,608+1,053,198，合并摘要、真实解码2048×1536及预览1024×768通过，临时对象目录已按最终路径核验后仅清理本次UUID目录。回执在 [纯文件媒体专项回执](evidence/python-material-local-media-processing.json)，含源码SHA及Python/Pillow版本。这不代表HTTP/MySQL/浏览器大文件上传或20/500MiB边界、并发容量通过。本机ffmpeg/ffprobe均未找到，视频尚未实测，未全局安装或改PATH。

## 隔离FFmpeg及真实MP4纯文件专项

经主任务明确授权，仅在 本项目独立临时工具缓存（9.0.2固定版本） 解压固定发布包；未安装到系统、未写全局PATH、未修改服务。来源为[FFmpeg下载页](https://ffmpeg.org/download.html)所链接的[Gyan发布者](https://www.gyan.dev/ffmpeg/builds/)，固定[9.0.2发布](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2)。ZIP下载与展开有界，拒绝路径穿越/链接，实际SHA256必须等于发布者校验值 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` 后才执行；工具版本及二进制hash见 [工具版本与SHA回执](evidence/python-material-local-media-tools.json)。

2026-11-08 12:41（北京时间），仅测试子进程PATH注入该bin，使用真实libx264生成2秒160×120 MP4，经过原素材分片/合并/真实ffprobe/ffmpeg处理，返回时长 `2.000000`，封面JPEG1024×768；截断MP4实际工具失败为 `VIDEO_PROCESSING_FAILED` 且无预览，均PASS。回执为 [纯文件媒体专项回执](evidence/python-material-local-media-processing.json)，独占临时对象目录已核验绝对路径后清理。此证据仅纯文件与工具，不算HTTP/MySQL/Worker/浏览器或500MiB/并发容量验收。生产处理器可信可执行路径与Worker调度仍待接入，默认PATH上仍无ffmpeg/ffprobe，不会误称系统已具备生产视频处理环境。

上述纯文件/视频与工具回执已脱敏归档到 `evidence/python-material-local-media-processing.json`、`evidence/python-material-local-media-tools.json`，未复制ZIP/EXE或任何绝对运行时对象路径。原始本机回执仅用于排查，提交文档以脱敏归档为准；三组纯媒体专项与两项工具检查不计入HTTP12组，也不重复累计为整模块验收。

## 下一轮真实媒体HTTP专项（已准备，尚未运行）

新文件 `tools/material_video_checks.py` 提供 `run_material_video_checks(client, admin, database, headers, object_root, cases, ffmpeg_bin)`，5个独立命名组：真实MP4上传/持久Worker/时长与认证封面；真实截断MP4不可READY/预览404；图片20MiB与视频500MiB超限请求不创建对象；故意移除子进程工具可见性后明确失败、恢复工具不复活旧任务；9,441,806字节PNG双分片的真实HTTP/Worker/预览。每组需实际运行后才能记录结果，当前仅Ruff、内嵌子进程脚本语法和固定工具SHA校验通过。

工具只注入专用测试子进程PATH，两个EXE分别匹配固定9.0.2校验值；DB只允许本机13306的当前UUID测试库，连接参数仅stdin传给子进程，不输出原始异常。临时媒体源文件位于本函数独占目录，超时先kill/join子进程，再核验最终绝对路径并仅清理该目录。既有对象由主运行器管理，不自行清理主对象根或启动共享服务。

当前损坏视频真实处理失败归为 `PROCESSING_FAILED`，不可分配/无预览；不伪称杀毒隔离或 `QUARANTINED` 分支已覆盖。该阶段曾登记处理器待加固项：capture_output在返回后才检查stdout大小且stderr无字节硬上限、操作系统CPU/内存限额、空/伪造预览输出拒绝。后续stdout/stderr上限和预览验证已按下文补强并完成纯测，更新后HTTP复验仍待；操作系统CPU/内存及后代约束仍未完成。不用小视频PASS替代全资源边界。


## 53716 三视口首次挂载失败及定点修复

该轮194个后台专项实际通过，但素材浏览器三个视口都未显示素材库标题，不能称浏览器验收完成。Vite实际日志定位 `src/views/orbit/materials/index.vue:11`：上传按钮的多行模板表达式缺少语句分隔符，导致Vue编译器报Unexpected token，动态路由组件无法加载；并非标题选择器或菜单加载竞态。

经主任务允许定点解冻，将按钮改为命名 `openUpload()` 函数，保留创建新上传视图与会话队列的行为。新增 `material-components.test.ts`，用真实Vue SFC解析器、脚本编译器及模板编译器分别编译素材主页面/上传弹窗/分类管理抽屉；3项通过，SDK5项与SHA10项一并通过，合计18项前端专项；`pnpm check:orbit`通过。该检查仅验证组件可编译，不能替代浏览器操作。

E2E保留标题、上传、处理、预览及归档完整断言；pageerror诊断仅允许输出错误类型、固定源码文件名与行列，不输出错误消息、完整URL/查询、响应或凭据。产品源码及专项已再次冻结，等待主线browser-only真实HTTPS三视口复验。


## 69621 三视口末段复选框操作失败

页面加载修复后的真实浏览器复验中，三个视口均已实际完成原登录、目录创建、PNG上传、Worker READY、认证预览和元数据编辑；在归档前，Playwright对Element Plus透明隐藏的原始checkbox执行check而超时，整轮仍FAIL，未把归档或全流程标通过。

主线确认运行结束后，专属E2E改为点击该行用户可见的 `label.el-checkbox`，随后断言实际checkbox为checked，再继续保留“批量归档（1）”、归档接口200与行消失的完整断言。未使用force、延长超时或跳过验证。该修改仅测试操作方式，产品源码保持冻结；格式检查通过后再次排队三视口复验。


## 下一阶段：标签分类查询及引用数设计（在测源码冻结，尚未实现）

来源为PRD FR-AST-03/原保留章节第5标签分类字段、OpenAPI的TagPage/CategoryPage与API_SEMANTICS。先补独立目录能力，再与指标事实筛选合流，不能以原型隐藏字段缩减需求。

1. **合同一致性纠偏**：名称要求租户内同类唯一。目前010的唯一键含group_name，错误允许同名标签因分组不同而重复。后续新增受控迁移改为 `(tenant_id,kind,name)`；先探测既有重复并明确阻断迁移，保留历史记录与关联，禁止自动覆盖、合并或删除。真实专项需覆盖相同名不同组冲突、修改分组仍冲突和不同租户/类型可同名。不能修改已经形成真实回执的010历史来掩盖差异。
2. **原查询字段**：先完整支持q名称模糊查询（转义LIKE元字符）、领域status仅ENABLED/DISABLED、page_size仅20/50/100/200、签名cursor。未知status、非法日期/UUID、重复参数和不支持的组合保持明确422/结构错误，不能忽略。日期端点包含；原合同没有为目录通用日期参数明确事实时间字段，因此先由主线统一是目录创建时间还是关联事实业务日，再登记技术解释。若用于目录创建时间，按项目明确业务时区的完整日边界转UTC查询，不能直接把浏览器本地时区或UTC日当业务日；未来业务日限制也不能无依据套用到目录历史。operator_user_id若使用只可收窄当前授权可见素材范围，不能扩大权限。channel_id/metric_profile_id/entity_type须有真实引用/事实来源后支持；之前明确422，并列为合同尚未完全实现。
3. **引用数扩展**：原Tag schema没有引用数字段，但PRD要求显示。登记额外字段 `visible_asset_count`（0至安全整数），仅统计调用者当前可见且未归档的不同素材，包含旧停用标签关联；不代表平台广告使用次数、不暴露租户其他拥有者数量。分类可用同一字段，历史引用仍在独立引用详情。权限仍assets菜单+tags.read，引用数不能绕过素材当前数据范围。对计数无定义/缺来源显示未知，禁止造0。
4. **有界查询与索引**：先读取目录一页最多200+1，再一次聚合这些ID的关联数，避免逐项N+1。标签关联使用已有反向索引 `(tenant,tag,asset)`，关联asset后套当前拥有者/显式管理团队范围及非归档状态；分类使用已有 `(tenant,category,state,...)` 索引。目录无status路径现有state中间列可能filesort，需真实EXPLAIN后新增 `(tenant,kind,id)` 游标索引；按日期选取是否增加created_at索引由实际选择性决定。q包含搜索明确有扫描风险，不能因LIMIT200宣称大容量完成。
5. **一致性游标**：沿用MATERIAL_TAXONOMY_CURSOR_V1用途，签名绑定tenant/actor/subject/数据角色与管理团队、kind、规范化全部筛选、page_size、目录水位和时间水位。标签或素材关联变化使目录计数旧游标失效；身份/数据权限变更返回CURSOR_STALE，禁止以新scope续旧页。对每页计数使用同一事务可见视图，展示计数口径。
6. **逐项验证**：纯字段/查询解析测试→真实MySQL字段/唯一约束/索引EXPLAIN→跨租户/自己/管理团队/撤权计数矩阵→真实浏览器检索、状态、页长、续页、引用数、停用旧关联→真实容量压测。每阶段独立记录，已有素材三视口成功不覆盖本阶段尚未开发的筛选及引用数。

以上为下一阶段设计，暂未增加API字段、DDL或UI，不计开发/测试/验收完成。日期与泛用事实筛选解释在实现前与主任务统一，避免擅自声称原合同已有该语义。


### 016唯一性纠偏迁移与独立专项准备

已准备 `016_material_taxonomy_contract.sql`（尚未执行）：第一条ALTER原子创建正确的 `(tenant_id,kind,name)` 唯一索引，并创建无status查询的 `(tenant_id,kind,id)` 键集索引。MySQL在创建唯一索引时先验证全部既有行；跨分组重名将以1062明确失败，旧表数据与原索引保持。只有该检查创建成功后第二条ALTER才移除旧分组唯一约束。不引入需要额外权限的存储过程、不自动变更业务数据。迁移须在受控维护窗口执行，DDL元数据锁及大表建索引耗时尚未容量验证。

新工具 `tools/material_taxonomy_checks.py::run_material_taxonomy_migration_checks(admin,database,cases)` 准备两组真实MySQL专项：独占克隆旧结构，注入跨组同名后实际执行016验证1062、两条数据和旧索引仍在；另一克隆实际成功迁移后验证跨组同名拒绝、跨租户/类型可同名。仅当前UUID隔离测试库，临时表名小于64字符且有固定前缀；finally只删除本次显式记录的克隆表，不更改业务原表，不单独启动数据库。当前仅Ruff/语法检查通过，真实迁移执行与EXPLAIN尚待主线排队，不能标通过。


## 57681 实际媒体HTTP/Worker及后续处理器加固

主线through015合跑中208后台组通过，包含 `material_video_checks.py` 全部5组真实专项：固定SHA的MP4实际上传/Worker时长/认证封面、截断MP4明确失败、超限请求不建对象、工具缺失明确失败且恢复后不复活、9,441,806字节PNG双分片HTTP/Worker/预览。整轮仍因后续新账户详情SQL失败而FAIL，7项未跑，不能写整体通过。该证据不代表500MiB成功上传或并发容量。

主线解除限定冻结后仅修改 `material_processing.py` 与专属处理测试：ffprobe/ffmpeg改为Popen双管道分块读取，每流最多保留/容许64KiB；任一输出超限立即终止并回收，继续保留20/60秒超时。不记录工具原始输出。衍生提交前必须1至5MiB、真实静态JPEG且宽高各不超过1024；工具退出0也不能发布空文件或伪装图片。

新增13项专项通过，含真实本机短子进程stdout/stderr超限、超时kill/reap与关闭管道，以及真实JPEG/空/伪造/PNG/尺寸/大小边界；其中2项处理器替身只用于验证最终发布边界，不当成工具实测。素材Python合计66项通过，Ruff及格式检查通过。另重新核对固定9.0.2两个EXE的SHA，在仅测试子进程PATH中实际复验2秒MP4处理和截断视频拒绝，均通过，独占对象目录已清理。证据见 [处理器资源与预览边界回执](evidence/python-material-processing-resource-guards.json)。

这些为新处理器纯测/真实本机工具证据；更新后的5组HTTP/Worker尚待主线快速模式复验，不能沿用修改前57681直接验收新源码。操作系统CPU/内存硬配额、进程后代约束、生产处理工具可信配置与调度仍未完成，不因有界管道及超时而声称资源隔离完整。


## 69409 新处理器真实HTTP快速回归（局部23组PASS）

主线独立素材快速模式实际23/23通过：6组初始化、原12组素材HTTP以及5组固定工具真实媒体HTTP/Worker；此回执绑定bounded输出/预览验证后的处理器源码。它不是其他模块216项整轮，未据此声称全部模块通过。随后taxonomy扩展开发修改了素材路由/读模型，新的taxonomy源码仍须单独through016复验，不沿用69409直接通过。

## 016标签分类生产实现与受控扩展（待真实集成）

已实现原q（literal名称包含）、status（ENABLED/DISABLED）、page_size（20/50/100/200）与签名cursor；查询默认50。游标签名显式绑定actor/tenant/subject/data_role/当前管理团队/kind/全部实际筛选、素材目录和授权目录版本。素材主列表游标亦补actor。日期与operator/channel/profile/entity参数没有猜测语义，明确422 FILTER_UNSUPPORTED，保留需求缺口。未知字段400、重复参数400、非法领域字段422。

**技术扩展 MAT-TAXONOMY-COUNT-V1**：仅GET标签/分类列表items及按ID读取额外返回 `visible_asset_count: integer|null`（0至9007199254740991）。统计当前调用者拥有assets.read且当前数据范围内、未ARCHIVED的素材关联数；单素材对单标签只计一次。无assets.read返回null，前端显示未知；该字段不是Meta使用次数或全租户引用量。创建/修改/停用响应仍保留原Tag/Category结构。原始OpenAPI的additionalProperties=false保持不变，扩展必须显式登记，不能把任意额外字段当通过。

列表先键集读取最多200+1目录，再对当前页ID做一次聚合，关联真实asset当前拥有者/显式管理团队，避免N+1及跨范围计数。详情使用同一计数策略。抽屉保留名称/分组编辑和停用，新增目录q/状态/页长与引用数口径提示；分页使用已提交筛选快照，不把输入未提交的新条件混入旧游标。当前新增18项taxonomy纯测通过（含不可变RowMapping与actor跨用旧游标拒绝），素材Python84项、前端19项及类型/Ruff/格式通过。另原schema校验器2项纯测通过；以下真实工具尚未执行。

- 016唯一性迁移工具2组：`run_material_taxonomy_migration_checks(admin,database,cases)`。
- 查询合同工具5组：`run_material_taxonomy_query_checks(client,headers,cases)`。
- 原始响应schema工具3组：`run_material_schema_checks(client,headers,cases)`；须排在原素材与真实视频组后，读取PRD原始openapi-current.json，验证实际AssetPage/TagPage/CategoryPage；唯一引用数扩展单独校验后再校验原字段，不忽略其他额外字段。自实现的受限validator遇未知关键字/type/format明确失败，非通用JSON Schema验收器。

跨租户/自己/管理团队非零计数与撤权、21条跨页和筛选变化游标、真实索引EXPLAIN、三视口目录筛选与大规模容量仍待补齐；不据纯测试勾选整标签模块。

## 原始Asset/Tag/Category类型核对与字段映射（只读提供主线，不直接改总账）

依据为PRD `contracts/openapi-current.json`，不是前端interface或自身测试。原Asset仅11个属性（name/category_id/tag_ids/id/revision/ownership/kind/state/sha256/preview_url/duration_seconds）；数据库width_px/height_px是实际解码内部数据，原Asset响应并没有宽高字段，不能误标原外显schema字段已验。

| 总账字段ID | 原合同实际类型与边界 | 已有真实case及待补校验 |
|---|---|---|
| SCHEMA-Asset.id/category_id/tag_ids/ownership | UUID字符串；tag_ids数组0至20；ownership含两个必填UUID且无额外字段 | 原PNG上传/元数据/保留停用标签case已有实际值；原schema工具第1组待运行后才可确认严格UUID/结构 |
| SCHEMA-Asset.revision | integer，1至9007199254740991，不能是boolean | 原metadata CAS真实case；原schema工具第1组待实际类型与范围核验 |
| SCHEMA-Asset.duration_seconds | **十进制定点字符串或null**，不是JSON number；0或正数，最多6位小数，最长28字符 | 实际MP4 HTTP/Worker case明确返回字符串2.000000；图片为null，原schema工具第1组补全格式验证；不能把全部视频边界等同小视频通过 |
| SCHEMA-Asset.name/kind/sha256/preview_url | 名称1..100；IMAGE/VIDEO；hash64字符串；预览绝对URI或null | PNG/MP4/认证封面、真实浏览器编辑预览已执行；原schema工具第1组待运行；state完整状态流不能借schema类型验证代替 |
| SCHEMA-Tag.id/name/group/revision/state | UUID；name1..30；group0..30必填字符串（允许空）；integer版本；ENABLED/DISABLED | 原taxonomy/停用历史case已有；新唯一性和过滤尚待016真实回归，原schema工具第2组待运行 |
| SCHEMA-Category.id/name/revision/state | UUID；name1..30；integer版本；ENABLED/DISABLED；无group | 固定未分类读取/归档拒绝、真实分类创建已执行；原schema工具第3组待运行 |

以上斜杠写法表示各自独立ID，不是一个合并条目。可独立结清只针对已具真实证据的字段性质，由主线结合证据源hash逐项核定；此表不授权把完整状态机、未接入指标、未知日期语义或新增引用数字段划为原合同已验收。


### 37038首轮016回归失败与工具合同同步

33组计划首轮在前5组初始化通过后失败，原素材工具把新GET标签读响应与旧创建响应直接全字典相等；唯一已登记的visible_asset_count只属于读响应，因此旧断言未区分原字段与技术扩展。未把这轮或新taxonomy标通过。主线确认运行结束后，仅修改专属素材工具：标签与分类GET均先断言当前无关联的count为严格整数0，只拆出该确切扩展键，然后其余全部键值仍与创建响应严格相等，额外未知字段仍会失败。检查其他同类断言与E2E，没有其他Tag/Category全字典相等需要同步；分片ACK严格结构保持。产品源码及前端未改，修正工具Ruff/格式通过后再排队。


### 49983 素材016真实专项33/33通过

修复扩展读响应断言后，主线素材专用through016实际33/33通过：6初始化、12原HTTP、5真实视频/跨8MiB分片、2迁移冲突/正确唯一性、5目录查询、3原始schema响应校验。该结果不代替其他模块整轮，也不代表新目录UI已浏览器复验；主线随后排新UI三视口。

原schema3组实际通过意味着从原PRD读取的AssetPage含IMAGE/VIDEO、视频定点字符串时长、UUID/版本/ownership/标签数组及Tag/Category原始结构已校验；额外visible_asset_count按唯一登记扩展单独核验。字段ID仍由主线结合总账逐项核定，完整状态机/日期/指标/容量缺口不因此结清。

### 下一独立真实计数与游标范围矩阵（尚未运行）

`tools/material_taxonomy_scope_checks.py::run_material_taxonomy_scope_checks(client,admin,headers,fixture,password,cache,cases)`，7组命名场景。复用主线实际user_fixture、真实登录与角色API：自己可见计数1、显式管理团队加自己3、超级管理员当前租户4；归档与真实异租户同ID标签关联不计入；tags.read无assets.read用户count=null；21个真实HTTP创建标签按20+1严格UUID键集，无重无漏且同时间水位；跨actor复用及改变筛选复用旧签名均409；移除素材读角色后同会话立即count=null，finally恢复测试角色。

计数源夹具是隔离数据库中明确的INITIATED元数据，未创建对象/任务，不声称实际上传或处理成功。另插入一条ARCHIVED与一条外租户素材用于真实SQL范围排除。角色通过真实API创建，现有临时用户通过当前库sys_user_role装配；所有写入限制本机13306且数据库名为当前orbit_py_it_UUID，未启动共享服务、不修改原参考仓库。当前仅Ruff/语法检查，真实7组待主线排队；0计数或合成单元读模型不能代替此矩阵通过。


### 标签分类计数范围及新UI真实局部回归

主线回执 `python-material-taxonomy-scope-http.json` 实际21/21通过，包含7组新多身份计数/游标矩阵：非0计数按自己/显式管理团队/当前租户收窄，排除归档和外租户，无assets.read为null，跨actor及筛选变化复用游标被拒绝，21条目录20+1无重漏，撤权后即时unknown。由此补上此前只有0计数不能证明权限隔离的证据，不将INITIATED元数据夹具说成真实上传。

新目录UI三视口回执 `python-browser-material-taxonomy.json` 实际7/7通过。以上为模块专项，不代替所有需求、容量或生产环境验收。原指标/日期组合与清理/生产Worker等缺口继续保留。

### cursor显式长度边界定点补齐（真实回归待through018）

原OpenAPI要求已提供cursor时长度1至2048。审计发现空字符串曾按无游标首页处理；主线允许定点解冻后，分类标签纯parser增加空/超2048长度明确422 FIELD_INVALID且pointer=/cursor。补2项纯测后taxonomy20项通过；既有真实查询工具仍保留5个case，仅在原非法参数矩阵增加tags/categories的空和2049字符cursor断言。Ruff/格式通过，其余产品/前端未动，源码已再次冻结。新边界尚未实际HTTP复验，不能把此前签名/跨actor/续页证据冒充长度完整验收。

### 47350 素材写方保护完整专项66/66真实通过

后续回执 `evidence/python-material-writer-full.json` 覆盖through020素材套餐66/66：65个后台/初始化/文件/协议专项与3个实际浏览器视口的汇总组1项。含019生命周期基础、恢复、跨进程put/assemble/process争用3组、真实HTTP上传与清理交错3组，以及既有上传/Worker、真实视频/大于8MiB分片、标签分类查询/范围和原schema校验。新cursor长度422矩阵随实际查询组通过；不是只用旧签名用例代替新边界。

跨进程实际写方在整个I/O期间持同对象guard；清理争用返回忙，不在写入中删文件，持久墓碑拒迟到写。HTTP专项实际使用100-continue作为body前屏障，过期清理后再送正文被拒绝且无数据库分片登记/对象目录复活；已complete素材不按上传过期清理；历史引用在claim前插入阻止物理回收。历史写入属于内部夹具，不是新增历史证据HTTP功能验收。

本轮证明明确限定素材专项与实际三视口，不代表全项目回归、真实容量或生产环境。生产物理清理仍默认关闭；未完成上传先归档与24h孤立分片/30d原对象交错的语义未闭合时保留数据。当前READY直出仍缺原需求要求的真实杀毒证明，不能标完整READY状态业务验收通过。

### 下一内部引用阶段

独立合同见 `MATERIAL_REFERENCES.md`：当前只新增安全批量视图、ALLOCATION/EXECUTION精确登记和取消释放，不实现分配算法、不注册HTTP、不写历史证据。55项单测和格式检查通过；024反查索引、8组真实SQL与5组多身份工具已准备，尚待主线执行。保守返回UNVERIFIED及execution_eligible=false显式保持杀毒缺口，不能冒充可执行或完整素材模块完成。
