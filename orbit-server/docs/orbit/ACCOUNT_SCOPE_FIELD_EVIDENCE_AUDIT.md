# 跨页账户三个响应字段的限定证据

只登记 `ScopeSnapshot.id`、`ScopeSnapshot.hash` 和 `ScopeMember.account_id` 的开发与测试；不批量通过整个 ScopeRequest、全部响应字段或两个完整 API。验收阶段仍保留未运行。

- `ScopeSnapshot.id`：服务端生成 UUID；实际 201 原值在同键反序集合重放时保持一致，并被真实成员 GET 接受为 UUID 路径。外租户及撤权场景不能读取该快照。
- `ScopeSnapshot.hash`：实际冻结五万成员后，测试按全部冻结字段逐条重算规范 SHA256，与原响应严格相等；不是只比较摘要长度，也没有仅取当前页生成摘要。
- `ScopeMember.account_id`：实际 250 页、每页 200 条，与五万已知 UUID 的完整有序集合相等，唯一数量也为五万，遗漏和重复均为零。成员结构严格只有 account_id/external_id/name。

证据父运行：`evidence/python-account-scope-capacity-current042-http.json`，44/44。同轮测量见 `python-account-scope-capacity-current042-metrics.json`；五万成员创建及全部读取共 219.21 秒。四档账户列表各 20 并发 P95 达标不代表成员页延迟分位数已经实测。成员每页全体权限复核仍有重复开销，后续优化必须保持即时撤权及全体求交的语义。

这些字段不因此提升为完整账户模块验收。created_at/data_as_of、count 边界和其他 Scope 字段仍按各自覆盖清单推进；原超级管理员 X-Target-Tenant 路径及成员 GET 通用筛选的未定义语义也未被本证据补齐。原始审计矩阵在前端仓库 `docs/ORBIT_ACCOUNT_SCOPE_FIELD_AUDIT.md`。


## 043 当前授权证明的真实复验

`python-scope-verdict-capacity043-http.json`实际44/44通过：同机同规模五万账户/百万日事实，冻结五万成员后读取全部250页，数量、UUID、完整hash一致且遗漏/重复为零。冻结创建4.76秒，创建及全部成员读取27.70秒；此前042相同合同整轮219.21秒。四档20并发P95分别0.313/0.479/0.562/0.698秒，800个实际样本。该测量是本地暖缓存专项，未证明冷启动、生产网络或所有报表性能。

`python-scope-verdict043-http.json`实际58/58通过，其中18组专门核验：命中证明仍实时授权、被锁成员不阻塞精确命中且不依赖时间TTL；账户时钟变化后完整重验；一成员归属丢失或删除整份409；跨人跨租户不可借证明；真实旧RR账户/管理关系撤回与新增；ready父/成员DML数据库拒绝；清理标记失败关闭；并发两次真实未命中最后只存一行证明。纯测、DDL存在和这两项专项均不等于整个账户模块验收。

## 062失败留档后的正式恢复

060/061多次原容量ReadTimeout或200行P95超过一秒后，上述三个限定字段测试曾降为RUNNING，旧成功仅历史保留。062新native租约仪表44/44通过后，再以无仪表原44完整复验，实际44/44、141.01秒通过：50000账户/1000000日事实、20并发、每档200暖样本，原一秒门槛和十秒范围POST超时保持。四档P95为0.387767/0.458551/0.700815/0.842230秒。

本轮实际冻结50000成员，POST创建4.916205秒，创建及250页完整读取22.934725秒；原冻结列规范SHA256与全部UUID集合一致，遗漏和重复为零。证据`evidence/python-account-scope062-capacity-pass.json`和`python-account-scope062-capacity-report.json`，限定字段父回执已由实际四个具名用例刷新。仅恢复这三个字段测试PASS，完整模块验收仍0；旧失败不删除，也不据一次无仪表通过宣称根因已完全解决或生产/冷启动容量已达标。
