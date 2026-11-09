# 当前用户密码策略单请求批量读取

最终采用**非事务 pipeline 的三个原 GET**；MGET 候选没有采用。每次 `_resolve_current_user` 在原身份快照之后创建独立 `redis.pipeline(transaction=False)`，依原顺序排队 chrtype、initPasswordModify、passwordValidateDays，再一次 `execute()`。使用默认 `raise_on_error=True`，没有跨请求缓存，不改变前置 token、validators、末段原子续期或插件最终 token 重读。三个独立 helper 继续各自 GET。

## 原语义与客户端协议

- 缺失/空 chrtype 仍返回字符串 `0`；初始密码提示仅配置等于字符串 `1` 且密码更新时间为 None。
- 天数只有原 `int(...)>0` 分支生效；无更新时间仍过期，UTC 当前时间严格大于到期时刻才过期。非法整数、naive/aware 比较异常和日期溢出均保留，未增加默认吞错。
- [Redis MGET 官方说明](https://redis.io/docs/latest/commands/mget/)将非字符串 key 当 nil；这会弱化原 GET 的 WRONGTYPE 行为，故主线明确拒绝该候选。pipeline 保留三个 GET 的服务端错误；批次会排队执行所有只读 GET，默认抛首个错误，不返回部分策略、不写配置。
- 本地 redis.asyncio 8.1.0 的 `Pipeline._execute_pipeline` 一次打包发送、读取全部响应，再 `raise_first_error`；`execute` finally `reset`，async context 的退出也 `reset`。reset 先摘下 connection，再 shield pool.release。本批不改客户端、不增加 Lua/TYPE，也不改变其原连接/重试配置。协议测试使用真实客户端 Pipeline + 假连接，未连接 Redis。

## 纯验证与冻结范围

三文件纯协议档实际 **165/165 PASS**（最终实际时间见 `.runtime/native-password-policy-pipeline-unit.log`）：新策略106、原 session renewal53、原 login service6。新策略保留先前101边界，并补三个 key 各自 WRONGTYPE、真实 Pipeline 默认错误传播/完整 drain、传输失败和取消后的真实 reset/release 协议。

包含8请求并发每请求各一次批次、下一请求配置变化、前token/validator撤权、后token撤权（续期和插件两路）、策略异常/在途取消不发布身份不续期、UTC精确边界及独立helper等价。纯测试不能替代真实Redis/HTTP或四档20并发容量。

旧测试仅修真实协议替身：

1. `test_login_session_renewal.py`：SessionRedis 新增独立 SessionReadPipeline，明确 transaction=False，仅排队GET并沿原 `_read` 和受控时钟执行；request增加 `scope={}`。
2. `test_login_service.py`：畸形claim请求增加 `scope={}`。

原断言、撤权/取消等待和DAO未调用断言全保留。原 AuthPolicy 对空scope采用 current_user 模式，没有生产认证绕过。

相关5个Python源/工具/测试 Ruff check和format check通过。生产唯一修改为 `python/ruoyi_fastapi/module_admin/service/login_service.py`。工具 `tools/run_password_policy_native_unit_checks.py` 沿原 native 隔离配置机制、不读私有env，JWT随机只在内存。

最终runner追加原 plugin routes与logout controller后，主线实际完整183/183通过，固定九文件源码前后hash一致，证据`evidence/python-password-policy-native.json`。包含本地in-memory SQLite和ASGI，但不是实际业务MySQL或容量。上游原锁定aiosqlite0.22.1已安装于本项目.venv，未改依赖版本，不是外部阻断。

主线真实16379/DB15独占空库专项8/8通过，证据`evidence/python-password-policy-redis.json`：正常值、缺失默认、非法天数字符串、三个key分别WRONGTYPE、错误后连接可复用、下次请求立即观察配置变化；仅清理本工具固定三键，结束remaining_keys=0，无FLUSHDB。网络发送后的取消未在该小档测量，取消/drain/release协议由上述纯测试单独证明，不混报。

原44容量在同1GiB pool/redo、原数据/20并发/一秒门槛/十秒timeout下仍失败：四档P95=.453265/.572955/.740427/1.012793秒，31通过/1失败/12未运行，范围创建未执行。见`evidence/python-account-scope061-policy-pipeline-failed.json`及report；不能把减少两次串行往返说成容量已解决，继续同trace连接获取诊断，不修改池参数或worker。

## 历史失败与后续真实门禁

- MGET原候选160纯项曾通过，但因错误Redis类型会降为默认值而未采用；不能引用为最终语义验收。
- 首次100PASS后旧session fixture缺scope失败；补后153PASS再遇原malformedclaim fixture缺scope。后者 `.runtime/native-password-policy-old-fixture-scope-failed.xml` 保留，前者原因具名记录于此。均未进入对应策略读取。
- 额外plugin档首次160PASS后缺aiosqlite导入失败，尚未连SQLite；`.runtime/native-password-policy-plugin-dependency-failed.xml/.log`保留，不删除原测试，不声称其通过。
- 最终纯档日志 `.runtime/native-password-policy-pipeline-unit.log`，JUnit独立副本 `.runtime/native-password-policy-pipeline-pure.xml`。
- 后续由主线串行真实HTTP/Redis及原44容量重验。只减少串行策略读取往返，不保证解决P95，不更改数据量、阈值、并发、读取池或worker。
