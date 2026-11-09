# 043：完整范围可见性的正向证明

## 当前状态与交付边界

主线已将独立 helper 接入 `AccountScopeStore`，并在专属隔离库实际执行 001—043 迁移。源文件、043 与专项工具现已冻结。此处记录限定范围的实际结果，不代表整个账户、投放、平台或生产部署验收完成。

- [043真实SQL/HTTP回执](evidence/python-scope-verdict043-http.json)：**58/58 PASS**，包含原40组与新18组；0失败、0未执行。包含三身份、真实旧RR视图、管理关系正反变化、双miss、命中锁观察、数据库护栏及清理标记。
- [043容量HTTP回执](evidence/python-scope-verdict-capacity043-http.json)：**44/44 PASS**；[原始容量指标](evidence/python-scope-verdict-capacity043-metrics.json)。50000成员、250页、0遗漏/0重复，完整冻结值hash一致；创建 **4.758695秒**，创建加全部成员读取 **27.704133秒**（此前同容量基线219.21秒）。
- 同轮50000账户/1000000日事实、20并发、每档200个有效样本，20/50/100/200行P95分别 **0.313258 / 0.478541 / 0.561848 / 0.697748秒**，均低于固定1秒目标；没有降低目标、删失败样本或缩小容量。

容量机为本机MySQL8.4.13，装载后缓存可能已热；这些数据是本轮真实本地首读/暖读证据，不能称生产冷启动、所有查询条件或任意硬件容量承诺。正式留存/幂等tombstone和平台调用仍不在本次验收中。

当前专属验证：`python -m pytest python/tests/test_scope_visibility_verdict.py -q` **35/35 PASS，0.54 秒**；两份新 Python 文件 Ruff check 与 format --check 均通过。测试使用事务替身，迁移测试仅检查护栏结构，不能证明 MySQL SQL 语法、锁语义、触发器或真实权限/容量通过。

目标是消除 50000 成员快照连续 250 页读取时，对同一版本执行 250 次完整当前可见性连接；不是以过期授权缓存代替实时授权。原 count、hash、冻结成员、响应、游标和历史记录不变。

## 已核实的依赖与失效路径

现 `account_access.visible_clause` 的精确语义：SUPER_ADMIN 为当前租户内全部账户；USER 为 `owner_user_id=当前subject`；TEAM_ADMIN 为本人或明确启用的管理团队。不存在的账户不可见。目标拥有者启用状态、目标团队状态、账户授权状态或解绑状态不在该谓词中，本实现不擅自新增这些筛选。

每次读取仍必须先调用原 `AccountScopeStore.authorize`：原菜单与 `accounts.read` 当前角色求交、原生身份快照、当前主体/团队状态、显式管理关系当前锁定读取、身份 auth_version、原七项授权指纹。任何动作撤权立即被原门禁拒绝；指纹/版本变化仍按原快照规则返回 SCOPE_CHANGED，不借证明继续读取。

已定位的全部生产账户 INSERT/UPDATE：

| 路径 | 写入 | 版本保护 |
| --- | --- | --- |
| account_worker.complete | 新绑定、户商补齐 | lock_batch 账户 clock UPDATE → 对象；成功 event 增加账户 clock |
| account_actions_store.command/unbind | 动作 revision、解绑 | lock_account clock UPDATE → 对象；command 成功 event 增加 clock |
| account_actions_worker.advance_due | 到期 owner/team/vendor 投影 | clock UPDATE → 对象；成功 event 增加 clock |
| account_actions_sync.complete | 元数据、状态与 revision | lock(write=True) clock UPDATE → 对象；成功 event 增加 clock |

账户读 clock 每次还执行真实到期投影门禁；没有版本写入但时间到期的待生效任务仍返回 ACCOUNT_ASSIGNMENT_PROJECTION_LAG，不能命中旧证明绕过。没有发现生产账户 DELETE 路径；将来新增写入或删除必须遵循同一 clock 协议，否则不能接入该证明。

不增加 directory_clock。当前身份、角色、本人团队变化由实时门禁/原指纹覆盖；显式管理范围由当前锁定列表及指纹覆盖。不参与当前可见谓词的目录名称改变不需要令证明失效。

## 表与权限边界

新增一张 `orbit_scope_access_verdict`，主键 `(tenant_id,snapshot_id,actor_id)`，同租户快照外键。保存 auth_version、auth_digest、account_version、members_hash、member_count、predicate_version 和 verified_at。每快照创建人最多一条记录，miss 成功后覆盖原行，不按访问次数/水位增加历史。不记录 Token、会话票据或隐私资料，不对 HTTP 接收或返回证明元数据。

verified_at 只是实际完整验证时刻，不作 TTL，不凭时间延长授权。只保存成功证明，失败不插入负向记录。GET 命中不更新时间、不写审计假事件；缺失/不匹配才做完整校验并原子 UPSERT。新表不提供公开写入或清理接口。

`predicate_version=1` 对应本次精确谓词。将来任何谓词含义改变必须提升版本并审查全部写入失效路径，不能把旧证明直接继承给新授权逻辑。

## 内部接口与锁序

`verified_snapshot(session, current: BusinessContext, auth_version, auth_digest, snapshot_id) -> dict`

调用方必须先完成原 authorize，使用同一显式事务及其可信结果；接口没有独立认证能力，不接受浏览器自己生成上下文或证明字段。它不是可执行账户许可，也不代替 `resolve_for_plan` 对 <=500 个实际账户的当前 owner/team/currency 和目标交集重验。

执行顺序：

1. 每次账户 clock FOR SHARE + 到期投影 guard，持有到外层事务结束。
2. 父 snapshot 当前 FOR SHARE，必须同 tenant、原创建 actor、ready=1、cleanup_requested=0；校验原版本与指纹。清理标记为 1 的快照一律 404。
3. 精确主键查正向证明。此查询不锁缺失行，不对不存在的键取得 gap SHARE 再升级 INSERT。即使 RR 下读到旧证明，依赖完全相等才命中；不相等只会多做完整重验。
4. 未命中时完整扫描冻结成员 LEFT JOIN 当前账户；账户读取必须是 `FOR SHARE OF a` 当前读，避免 RR 旧账户归属与新账户时钟组合。TEAM_ADMIN 再调用原 managed_teams 当前锁读并复算原七项指纹；匹配后按真实集合生成本人 OR 明确管理团队 IN 谓词，避免外层 OF a 不给嵌套 EXISTS 加锁导致旧管理关系参与授权。USER/SUPER 与命中不增加该查询。任何一项不存在或不可见整份 SCOPE_CHANGED，不返回可见子集、不 LIMIT 500 截断全成员校验。
5. 所有成员成功后同事务单行 UPSERT。写入异常传播给外层，不吞错误、不自行 commit。

零成员遵循原 0..50000 范围，不能借本次优化增加非空限制。账户普通变更只使证明 miss；完整重验仍可读时快照继续有效，不改原冻结名称/hash/游标。

## 数据库不可变护栏与合法清理

025 原先只有生产代码不修改 ready 成员，**并没有数据库硬冻结**。已实际执行的043增加内部 cleanup_requested（默认 0）及六个触发器：

- snapshot INSERT：必须从 ready=0、cleanup=0 开始。
- snapshot UPDATE：允许初始 ready0→1；ready1 后原全部字段不可变，只允许 cleanup0→1，不能退回 ready0/cleanup0。
- snapshot DELETE：ready1 必须先标记清理。
- member INSERT/UPDATE：ready1 父快照禁止变更；UPDATE 更换父快照时新旧两端都检查。
- member DELETE：ready1 仅在父 cleanup=1 的受控清理事务允许删除。

父锁在前：正常创建已经持有父写锁；维护父/成员必须同事务。未来合法清理应父 UPDATE 锁→cleanup=1→删 proof/成员→删父快照同一事务，保留原审计/outbox。读父 FOR SHARE 与清理写锁互斥；即便错误提交了 cleanup=1，也必须 404，不能暴露部分成员。

本轮不实现公开删除、定时清理或留存产品策略，也不宣称留存已交付。**未来正式清理必须先解决原 actor/request_key 的幂等 tombstone**：不能盲删快照后允许相同旧 key 创建另一个 UUID。现隔离测试工具 `account_scope_visibility_plan_checks.py` 的直接成员清理须主线适配内部标记；本线不改冻结工具。

## 主线真实验证覆盖与后续回归要求

以下列出的本次专项路径已由上述58组与44组限定回执验证；将来依赖谓词或写路径改变时仍须重跑，不能依纯测继承通过。正式清理产品策略仍属未来边界。

- 043 的全部触发器实际 MySQL 行为、ready0 创建以及 0/50000 完整 ready 发布；原幂等重放与响应不变。
- 原本人、TEAM 明确管理、SUPER、跨租户、动作撤回及完整成员一项越权的原矩阵。
- 先建立 RR 旧一致性视图，再账户 ownership/存在性变化，确认新时钟不能配旧可见性。
- 当前 managed 关系在旧读视图前后改变的 TEAM 矩阵，确认所有谓词依赖是当前授权证据。
- 首次完整校验、随后精确命中、每项依赖变化重验、并发 miss 和更新证明无 gap 升级死锁。
- cleanup=1、ready 成员三种 DML 与父字段篡改全部拒绝；正常创建/合法原子清理允许，异常清理 flag 提交后读 404。
- 原 50000 冻结成员 250 页 UUID/数量/hash 对账，以及四档真实并发容量；纯测试不替代这些证据。

## 独立真实专项工具（18组已实际执行通过）

新增 `tools/scope_visibility_verdict_checks.py`，固定 `SCOPE_VISIBILITY_VERDICT_CASES` **18 组**。入口为 `run_scope_visibility_verdict_checks(client,admin,headers,password,cache,database,cases,*,identities=None)`。默认复用旧计划工具的三身份准备函数，固定占用 990360/990361；因此新证明独立档与旧 SQL 计划档互斥，或主线显式传入已准备的三身份 map。身份角色、真实业务归属与数据库/主机/端口均在装载前核对。

用真实 API 创建原快照；直接 SQL 只用于隔离样本、受控变动与锁观察。命中验证不是只查看表行：证明 verified_at 设置为历史时刻，同时另一事务持有实际成员账户的排他锁，真实 HTTP 成员 GET 仍须有界成功、verified_at 不变，从而证明未执行会受该锁阻塞的完整 current 扫描，也证明时间不是 TTL 许可。

三个 RR 组使用真实 asyncmy/SQLAlchemy `REPEATABLE READ` 事务，先建立一致性读视图，再独立连接提交账户或管理关系变动；再次普通读取须仍见旧值，然后调用实际 authorize/helper，并断言当前结果。管理移除场景在当前移到不可管理团队的账户上拒绝，新增场景在最终确有授权的管理团队上成功。管理变动仅隔离夹具，不能冒充生产人员变更流程。

并发组对两条真实事务加有界阶段屏障：只有两者都实际读取不到 proof、到达完整扫描前，才共同继续；断言两者提交且最终只有一条 proof。不模拟查询结果、不降低失败为重试成功。

工具新专属纯测 **15/15 PASS，0.34 秒**，覆盖独立库/实际库名防护、固定 18 组/接口、错误诊断不读取业务响应/不格式化私密 SQL，以及拒绝探测无论成功/错误都回滚。与 helper 的 35 项纯测性质相同，均不构成真实 SQL 验收。

043 与旧夹具的兼容点已交主线处理：旧计划工具直接 ready1 INSERT 必须改成 ready0→完整成员→ready1；`launch_scope_consumption_checks.py` 的跨租户/他人 ready 快照复制也须合法装载后发布，不可删减旧权限负例。MySQL 官方限制针对修改调用语句正在使用的表；当前 member trigger 只 SELECT INTO 另一父表。此次真实58组中的创建、发布及I/U/D护栏已经实际通过，不再只依据文档推断其 `FOR SHARE` 可行性。

参考：[MySQL 8.0 存储程序限制](https://dev.mysql.com/doc/refman/8.0/en/stored-program-restrictions.html)、[MySQL 8.0 锁定读](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)。
