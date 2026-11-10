# ORBIT 开发交接与 Codex 接续

更新日期：2026-11-09，北京时间。面向第一次接触此项目的开发同事及其Codex。

**项目尚未完成。先收口规则业务闭环，再按覆盖台账逐项继续。不要从头重建项目，也不要将已上传代码或已有测试数量解释为全部功能完成。**

## 1. 获取代码与资料

```powershell
git clone https://github.com/white102718-lgtm/drmovira.git
cd drmovira
git status --short
python tools/verify_handoff.py
```

在Codex中打开这个仓库根目录，而不是旧机器的独立前端或后端目录。`orbit-web`、`orbit-server`保持原名称，现有相邻目录引用因此可继续解析。当前交付分支为`main`；不自行切换/新建分支或worktree。

| 资料 | 仓库位置 | 用途 |
| --- | --- | --- |
| 原始产品需求包，43文件 | `data/ORBIT_Codex开发PRD/` | 产品原文、合同、字段、流程、验收用例、原型、校验工具 |
| 原独立HTML原型 | `data/ORBIT原型.html` | 原始界面参考；技术与样式已被用户覆盖 |
| 后端原文基线 | `orbit-server/docs/orbit/baseline/` | 与上述43文件逐字节相同；禁止直接修改原文 |
| 现行实施计划 | `orbit-server/docs/orbit/IMPLEMENTATION_PLAN.md` | **第七节及末尾最新节点**为当前执行顺序 |
| 逐项进度状态源 | `orbit-server/docs/orbit/progress.json` | 开发/测试/验收分列，不能重置 |
| 可读进度及模块逻辑 | 同目录`PROGRESS.md`、`MODULE_LOGIC.md` | 需求覆盖及全部模块逻辑 |
| 字段与接口清单 | 同目录`FIELD_MATRIX.md`、`API_MATRIX.md` | 逐字段、参数、接口核对 |
| 当前规则交付范围 | 同目录`RULE_DEFINITION_BUSINESS_FLOW.md` | 已实际操作、证据、失败与剩余缺口 |
| Python替换与容量设计 | 同目录`PYTHON_BACKEND_MIGRATION.md` | 当前框架、大数据量要求、历史与新实现的边界 |
| 真实验收回执与截图 | 同目录`evidence/` | 有限通过和失败都保留；先核源码及适用范围 |
| 近期前端定向回执/日志 | `docs/handoff/evidence/` | 原本只在旧机.runtime内的有限回执，本次补入 |
| 历史参考项目源码及索引 | [本地路径导航](docs/handoff/REFERENCE_PATHS.md)、[来源清单](docs/handoff/REFERENCE_SOURCES.json) | 四份已提交源码的目录入口，克隆后直接可查，详见第7节 |

阅读顺序：根`AGENTS.md` → 本文 → 实施计划第七节/末尾 → 当前规则闭环 → `PROGRESS.md`/`progress.json` → `MODULE_LOGIC.md` → 本次要做的原合同及字段 → 对应源码/证据。文档按时间追加，较早节点的“待实现”可能已有后续进展，不能只看文件开头。

`SOURCE_MANIFEST.json`记录首次合并导入的原双仓分支、提交及工作区逐文件指纹，包含当时未提交代码，并非仅两个旧提交的内容。`HANDOFF_MANIFEST.json`校验本次交接后的当前仓库资料；不要用首次导入清单误判后续文档变更。

跨系统Git可能转换普通文本的CRLF/LF。校验工具单独统计仅换行差异，仍要求其他字符完全一致；原始`data/`和后端`baseline/`始终按原字节校验，不放宽原需求完整性。

## 2. 已确认、不能自行改变的决定

- 新后端直接采用`insistence/RuoYi-FastAPI`底座，Python、MySQL8、Redis；不继续Java业务，不改成MongoDB。上游固定提交及许可证见迁移文档。
- 前端Vue3、Element Plus，保留若依layout、原菜单及原功能，业务通过新路由/菜单进入。原生Element Plus风格即可，功能、字段、弹窗、二级页优先。
- PRD原技术栈要求已被覆盖，其他业务要求仍完整有效；历史参考代码不能覆盖原需求。
- AI使用GPT API和Claude API，**不是运行Claude Code命令行**。系统配置中的Token等凭据认证加密、只写不回显，不落Storage或日志。
- 关注大数据量：有界读取、游标/索引/汇总/异步任务、真实数据量压测；未知值不能补零，金额Decimal及十进制字符串，业务日采用账户IANA时区。
- 用户要持续实际开发，不是只汇报或重复跑无关容量测试。但定时监督已经用户明确关闭，不自动恢复。
- AWS部署已推迟，原账号权限不足；本次交接不含部署授权，不执行真实广告写入。

## 3. 当前真实状态及有限证据

严格覆盖台账为2342条，最近记录29条已开发、26条测试通过、0条完整验收。这是台账条目统计，不是工期或完成百分比；大量内部代码/局部检查不能直接增加整个业务模块的验收勾选。

当前主要闭环入口：原若依菜单「ORBIT工作台 → 规则管理 → 规则列表与编辑」，路由`/orbit/rules/definitions`。

| 检查点 | 实际证据与限制 |
| --- | --- |
| 规则定义/元数据 | `python-rule-definition-metadata-flow-http.json`真实15/15；MySQL UNION排序规则1271已实际修复，四轮失败保留 |
| 再认证上下文 | `python-rule-recovery-context-http.json`真实15/15；六动作独立权限、JWT与Cookie新CSRF真实创建草稿、外租户重新登录、撤销无Bearer回退 |
| 原规则/日历技术联合档 | `python-rules062-options-simulation-calendar102.json`102/102；是内部SQL/HTTP有限范围，**不是公开模拟、启用或调度成功** |
| 最终有限页面8项 | `python-rule-definition-recovery-browser.json`及`-parent.json`；原生登录/菜单、真实名称、技术状态输入下暂停2→3、归档已200提交丢响应后的原请求恢复；父档23/23包含手动等待 |
| 恢复实际过程 | 弹窗内新标签登录，独立页注销使旧会话无效，旧页复核仅GET且保留未知；重新登录后5次GET零POST；显式重试原body/key/quoted CAS，返回原归档版本2而非重复变更 |
| 遮罩缺陷 | 首次恢复入口被弹窗遮罩挡住，已修复并从另一条草稿完整重验；首条开发HMR丢的内存不算恢复成功，截图/失败保留 |
| 后端定向 | `python-rule-business-fixed-unit.json`164/164、源码前后一致；不是全量业务验收 |
| 前端定向 | 近期185项恢复检查、后续弹窗窄补丁及49项频次/q检查分开记录于`docs/handoff/evidence/`，不能相加冒充同一快照全量通过 |

前端最后改动已展示具体每N分钟/每日时刻/每周星期与IANA；q按NFC后100码点校验，中文、emoji和组合字符都不能被UTF16 maxlength误截断。49项定向通过，但该改动发生在上述页面8项之后，不能宣称最新页面已全量重验。

历史Java证据、SQL技术FIXTURE、编译/构建成功、页面占位和替身成功均不能替代Python真实业务验收。旧证据含旧机绝对路径和原工作区hash；接手时对照当前内容，改动影响证据则定向复验，不只改hash。

## 4. 下一步按这个顺序执行

1. **规则列表只读筛选候选接线。** 原接口已有`operator_user_id`和`metric_profile_id`过滤，但页面缺可用选择器。候选三文件`python/orbit_api/rule_list_filter_contract.py`、`rule_list_filter_store.py`、`rule_list_filter_routes.py`及`python/tests/test_rule_list_filters.py`是被中断的在制候选；尚未接公共路由，未完成真实专项，不计交付。先核完整性/定向测试，再注册静态路由于`/{rule_id}`前，补真实HTTP与前端消费者。
2. 候选只允许`rules.read`，从当前可见Rule head真实引用提取OPERATOR/METRIC_PROFILE，20/50/100/200有界、按ID排序；不借CREATE/UPDATE、人员目录或monitor权限。拥有者真名可null，原MetricProfile没有name不能制造名称；游标用途隔离、会话/tenant/actor/auth_fingerprint/kind/page_size/当前规则水位绑定，末段重验授权。候选源码不能因本说明存在就直接认定已正确实现。
3. 实际验证第二页动作成功后保留筛选、重置分页回读；写后沿旧cursor会409的问题已组件修正，但真正第二页UI仍待验。
4. 补SAVE/SCOPE未知结果、新标签再认证、异actor/tenant拒绝、撤权/403/409保留原未知及Cookie实际页面组合；本轮真实UI只有ACTION链，不能继承到其他链。
5. 补1440×900、1920×1080、390px适用视口。1440宽表已实际横向滚动；390旧截图异常不计通过，不能拿空白/缩放异常截图勾选。
6. **日期与渠道筛选待产品口径。** 后端原`date_from/date_to/channel_id`非空明确拒绝，不能称已实现。已提问但尚未得到确认：建议日期按规则创建时间，渠道按规则账户范围中至少一个账户当前渠道；备选日期按生效日。不要自行把建议当已确认，也不要删字段。
7. 当前定义闭环收口、具名证据及逐项状态更新并推送后，继续台账中模拟/启用、全局RuleHit、执行/任务、报表/AI、素材、设备、渠道和系统等未完成项。不要为了继续开发再扩展无直接页面消费者的协议旁支。

公开规则simulate/enable及runs仍有明确503来源/执行依赖；RuleRun入口现称「运行记录」，不等于PRD要求的全局触发记录。`rule_metric_publication_access.py`及其测试/文档是此前暂停的在制候选，不应绕过当前主要闭环直接标为已交付。

容量失败独立保留：无仪表五万范围POST曾十秒ReadTimeout；百万身份资源200账户×5000、20并发200请求P95约1.518秒，仍未达原1秒门槛。仪表档通过不能覆盖原失败，不能改超时/阈值、减少数据量或增加worker来冒充验收。

## 5. 新机环境与验证

旧机实际工具版本：Node v24.18.0、pnpm 11.17.0、Python 3.13.15；后端声明Python>=3.12，项目锁定版本以仓库文件为准。依赖目录、MySQL/Redis二进制、数据库数据、对象文件、私有配置均不在Git中，不要假设clone后即可无配置运行。

Windows示例，先从官方来源安装工具，保留锁文件：

```powershell
cd orbit-web
pnpm install --frozen-lockfile
pnpm check:orbit
pnpm exec vitest run --config vitest.config.ts tests/orbit/rule-list.test.ts
cd ../orbit-server
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r python/ruoyi_fastapi/requirements.txt
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe tools/orbit_progress.py check
.venv/Scripts/python.exe -m pytest python/tests/test_rule_store.py python/tests/test_rule_display_metadata.py python/tests/test_rule_recovery_context.py -q
```

先跑受影响的有限检查；不是要求每次重跑全部历史容量档。`orbit_progress.py check`仅校验台账与证据规则，不是产品验收；`render`生成报告，不可用`sync`/初始化工具清零已有进度。

真实SQL/HTTP专项使用独立MySQL回环13306、Redis16379/DB15、临时`orbit_py_it_<UUID>`库、后端18083；内置浏览器窗口另起18084，登录只用本轮临时夹具凭据，测试退出会清理。因此截图中的URL/账号不是长期可用预览账号。

先审阅`tools/start-mysql-test.ps1`和`tools/start-redis-test.ps1`，它们支持显式`-MysqlHome`/`-RedisHome`路径。仅在新机自有隔离实例上准备测试环境；真实工具校验datadir及库名，不得绕过护栏接业务库。Linux/macOS尚无等价完整启动脚本，需要适配并保持护栏，不能照抄Windows路径宣称可运行。

环境准备好后，在`orbit-server`运行当前最小业务专项：

```powershell
.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 62 --rules-only --rules-definition-flow --include-rule-display-metadata --include-rule-recovery-context
```

需要实际UI时再加`--rules-internal-browser`，保持进程，优先Codex内部浏览器操作，按具名操作记录真实结果；不能只看到待验窗口就写PASS。工具仍有旧机器路径/临时目录假设，迁移时先核代码，缺工具或端口就如实记阻断，不自动停止其他项目。

日常Python预览：准备受控私有配置与已审核数据库后，用`tools/start-orbit.ps1`；前端代理通过`ORBIT_E2E_BACKEND_URL=http://127.0.0.1:18083`的现有Vite分支连Python，不能误连旧Java或参考项目。`LOCAL_PREVIEW.md`的18080/18081/13307/16380是旧机Java预览历史，不能当作新机已运行状态。

生产式预览配置加载器目前`python/ruoyi_fastapi/config/orbit_runtime.py`固定读取旧机`D:/progress/adpulse-power-system/.env.local`，只采用`ORBIT_PYTHON_`命名空间，禁插值/通用进程环境回退。新机让负责人提供**独立受控配置来源及所需秘密**后显式适配此路径；不要把旧路径所在参考项目配置复制进Git，不要自动回退读取上游.env。隔离测试通过`configure_isolated_fixture`注入随机测试配置，与真实预览密钥不同。

真实预览至少需要独立DB源JSON、Redis连接、32字符以上JWT签名密钥、独立凭据加密keyring/active key ID；具体字段以OrbitSettings/`credential_cipher`校验为准，不能复制历史测试随机密钥作为业务主密钥。Meta/BM、GPT/Claude、AdsPower、邮件/OIDC等真实实测另需对应配置、权限及设备。秘密由负责人安全单独交接，不写进本文、仓库或聊天。

## 6. 提交、验收及交付方式

- 原双仓导入源为前端`5495cf5`、后端`c1c03c9e`，还包含导入时工作区改动；不要再次clone旧双仓覆盖本仓库。
- 统一在本仓库当前main开发，提交前核状态和`git diff --check`，完成可复验节点后推送`origin main`。两端同一个提交即可，不再推送旧hesong0105-bit两仓。
- 不部署、不执行真实广告写入；参考项目只读。当前GitHub仓库公开，任何凭据和真实业务数据都不得入库。
- 逐条登记开发、测试、验收及具名证据；明确失败、未运行和外部阻断。日志/原始DOM回执如需保存先检查敏感信息。
- `HANDOFF_MANIFEST.json`是本次交接快照；后续开发改源码后清单会报变更，这是预期，不能为了校验通过改证据伪造原测试。

## 7. 需要负责人单独交接的外部依赖

先打开[历史参考代码本地路径导航](docs/handoff/REFERENCE_PATHS.md)，按业务进入四个仓库内源码目录；所有导航路径以本仓库根目录为基准，不要求存在旧机的D盘目录。

四个ad-mpower历史参考项目的已提交源码现已附在[reference-projects/](reference-projects/README.md)，不再要求同事有原仓库权限才能查看这些快照。来源/原分支/固定提交见`docs/handoff/REFERENCE_SOURCES.json`，逐文件指纹、排除项及脱敏次数见`reference-projects/SNAPSHOT_MANIFEST.json`。只导出Git提交对象，不含本地改动、node_modules、虚拟环境、构建运行数据或真实凭据；原项目工作区未改动。若需要快照之后的远端新版本才需另申请原仓库权限，不把快照等同于远端持续同步。

同事仍需目标仓库写权限、开发工具及隔离数据库、必要的私有配置/外部服务授权。参考快照仅用于查阅历史逻辑，不执行其中部署/广告脚本，不采用其框架替代ORBIT技术栈。Codex不会继承本聊天记忆、旧agent、浏览器登录、临时账号或机器文件。当前`orbit-10`已按用户要求暂停，不重建定时器来代替开发。

## 8. 直接发给接手同事Codex的指令

```text
请接续当前ORBIT项目，不从头重建。先阅读根AGENTS.md、HANDOFF.md，运行python tools/verify_handoff.py并核对当前Git分支/工作区；再读orbit-server/docs/orbit/IMPLEMENTATION_PLAN.md第七节及最新节点、RULE_DEFINITION_BUSINESS_FLOW.md、PROGRESS.md、progress.json、MODULE_LOGIC.md与本次相关原合同/证据。

历史参考代码按docs/handoff/REFERENCE_PATHS.md和REFERENCE_SOURCES.json的local_path/entry_points从本仓库读取，统一位于reference-projects/下；previous_machine_path只记录来源，不用于定位。原始需求在data/ORBIT_Codex开发PRD/。不要寻找旧机D:/progress下的独立参考仓库。

最终框架是Vue3/Element Plus + RuoYi-FastAPI/Python + MySQL8 + Redis。保留若依layout和原菜单，原需求除技术栈覆盖外都有效，全部字段、弹窗、二级页、权限和异常不得漏掉。只在当前统一仓库和当前分支工作，不新建branch/worktree，不部署、不真实写广告、不停未知预览、不泄密，不自动恢复已关闭的定时监督。提交推送目标是white102718-lgtm/drmovira。

先完成规则可操作闭环，第一步审查在制rule_list_filter三文件与测试，按rules.read专属可见Rule引用候选实现有界分页、当前权限/会话/水位绑定，完成真实HTTP后接投放师与指标配置过滤UI；不要借CREATE/UPDATE或目录权限。随后真实验第二页动作回读、SAVE/SCOPE及异身份未知请求恢复、三视口。日期/渠道筛选口径仍待产品确认。现有技术模拟/启用/运行记录503依赖、容量失败和全局RuleHit缺口均不能假装已完成。

按依赖持续实际开发、定向测试、真实联调并逐项更新开发/测试/验收及证据；不要只汇报或重复无关容量档。旧证据按源码和适用范围复核，组件/构建/技术SQL状态不冒充全业务验收。新机私有配置或平台权限缺失只阻对应实测，继续其余可做功能。先告知核对到的实际状态与下一项，然后立即执行。
```


## 2026-11-10：Meta 多应用后台绑定

已增加后台绑定应用、授权时选择应用、来源版本隔离及原生登录会话转换，部署迁移至 076。操作说明见 `orbit-server/docs/orbit/meta-integration/MULTI_APP.md`，测试与外部验收边界见 `orbit-server/docs/orbit/meta-integration/MULTI_APP_VALIDATION.md`。真实 Meta 客户授权与数据对账仍需实际应用配置及授权，不视为已完成。


## 2026-11-10：AdsPower 自定义地址与真实监测部署

用户授权后已部署自定义API地址支持，并安装服务器mTLS接收服务及Mac常驻只读监测。test2真实心跳READY，完整Profile库存1条，无API认证错误；另一设备test未接入，保持OFFLINE。设备尚未绑定广告账户，此验收不代表Meta身份或广告写能力通过。部署维护和证据分别见 `orbit-server/docs/orbit/ADSPOWER_CONNECTION_SETUP.md`、`orbit-server/docs/orbit/ADSPOWER_CONNECTION_VALIDATION.md`。设备证书90天需续签；所有私钥、API Key和运行队列保留受控主机，不入库。
