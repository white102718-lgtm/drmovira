# 账户范围冻结同请求墙钟诊断（阶段一）

本工具只供主线显式隔离测试启动，不注册生产中间件、不改变原认证/SQL/事务/响应。原阶段一接线已真实44/44通过；之后新增的统一contextmanager目前仅49项纯协议通过（1.35秒），Ruff与格式通过，尚未接入真实启动/健康/退出检查。原44不能继承为新manager实测。它不证明10秒ReadTimeout根因已找到，也不等同性能恢复。

## 先保留的实际证据

- 未加此工具的原44档，四档读取P95达标但范围POST发生原10秒ReadTimeout；失败回执和报告继续保留。
- 现有旧scope工具的一次同规模44档真实通过150.65秒。该50k请求的Store.create为4607.621ms、112次execute、50批成员写/51次账户读取；成员写4121.733ms、单批最大127.714ms，账户读167.229ms。全部execute相加4294.282ms，余313.339ms包含Python/结果适配及诊断落盘等墙钟，不能称CPU。
- 历史客户端4.8秒计时包含CAP GET和POST，测量边界与Store内不同，不能直接相减或全部归因于某次代码变化。当前失败缺少同请求轨迹，所以不能断言发生在成员写、认证、连接获取、事务尾部或网络。
- 原阶段一接线同规模档实际44/44 PASS169.58秒；证据为 `evidence/python-account-scope062-http-instrumented-pass.json`，另归档 `evidence/python-account-scope062-http-wall-clock-samples.json` 的14份安全技术trace。该50k trace的native_enter/exit为2.921→9.693ms、Store11.139→5094.875ms、response.start 5116.659→5118.934ms、最后body5120.888→5122.500ms、app_end5124.635ms；112次SQL/50批全完成。只是该仪表请求墙钟，未复现/定位/解决原无仪表超时；三个严格字段仍RUNNING。此时使用的是修改contextmanager之前的旧独立安装接线。

## 主线接线接口

新文件：`tools/account_scope_http_diagnostics.py`。

```python
with scope_http_diagnostics_context(
    app, old_output_dir, output_dir, isolated_test=True
) as observed_app:
    uvicorn.run(observed_app, ...)  # 原host/port/timeout/worker均不变
```

统一入口的准确签名为 `scope_http_diagnostics_context(app, old_output_dir, output_dir, *, isolated_test=False)`，同步contextmanager，yield包装后的原ASGI app。它将旧安装、新安装、wrap及uvicorn运行置于共同异常/清理边界。旧安装失败不留新层；新安装失败恢复已装旧层；wrap或运行失败逆序尝试两个cleanup。一个cleanup失败不跳过另一个。原setup/uvicorn异常与CancelledError身份原样传播，cleanup失败只保存固定标签/技术计数。无原异常而cleanup失败时抛固定 `SCOPE_HTTP_CLEANUP_FAILED`，不泄底层异常文本。

原独立 `install_scope_http_diagnostics` 和 `wrap_scope_http_diagnostics` 仍保留兼容，但root新接线应使用manager。新安装函数内部的descriptor赋值失败也只恢复自己已替换的值；不覆盖第三方包装。对“新安装已完成但调用边界再抛错”会按本次同路径私有安装回收。summary固定为本目录 `context-cleanup.json`，仅setup阶段、原异常类别、cleanup尝试/失败固定标签及写失败技术计数；不是请求trace，主线分析时须与随机32hex请求文件区分。summary写失败不能覆盖原异常。

这些入口均要求 `isolated_test is True`，拒绝1、字符串及默认false。输出只能是本server下 `.runtime/account-scope-http-profile/<32位小写hex>`；拒绝路径逃逸、符号链接及Windows reparse/junction，包括不可跟随的链接。重复install、活跃请求中卸载或被他人替换的descriptor均明确拒绝，不覆盖其它开发者的包装。

旧scope诊断先安装、新HTTP工具后安装，逆序卸载。组合纯测分别保留成功、原异常和取消时双方execute恢复，已有instance.execute恢复原对象，原来没有instance属性则delattr。未修改旧工具或公共runner。叠装后旧SQL计时包含新inflight进入/退出落盘，新SQLspan包含进入落盘而不含退出落盘；均不可称纯数据库耗时。

## 精确采样与字段

只采样ASGI `type=http`、`method=POST`、`path=/api/v1/scope-snapshots`。其它方法、路径、lifespan和没有本请求ContextVar的认证/Store调用完全透传。一个随机技术trace对应一份文件，不读取或写入业务ID、正文、查询、headers、Token、SQL文本/参数、结果业务值。原receive、每条response message和所有参数对象均原样传递。

每请求最多512个固定标签span，每目录至多1000个请求文件；达到上限后的原请求照常执行，进程内只累加技术dropped计数。文件经受控临时文件原子替换，每条SQL进入和退出均更新。因此诊断存在真实同步落盘开销，仪表档不能充作无仪表容量结论。

|字段|意义|
|trace|随机32位hex技术关联，非request_id/用户/租户/连接ID|
|status|RUNNING、APP_RETURNED、ERROR、CANCELLED；APP_RETURNED不等同客户端收到响应或发布成功|
|timing.http_enter_ms|本工具ASGI进入，相对起点0|
|timing.native_enter_ms/native_exit_ms|原LoginService._resolve_current_user入口/退出；只标native resolver，其它Cookie认证链工作未知|
|timing.store_enter_ms/store_exit_ms|原AccountScopeStore.create入口/返回；不将其后的外层事务退出称已测commit|
|timing.response_start_enter_ms/response_start_exit_ms|原response.start send前后|
|timing.last_body_enter_ms/last_body_exit_ms|原最后一段body send前后；不读取body内容|
|timing.app_end_ms|原app返回或异常退出后的时刻|
|spans|固定NATIVE_RESOLVER、STORE_CREATE以及旧sql_phase白名单的enter/exit/outcome|
|sql_calls|真实session.execute包装次数，非底层MySQL往返次数/触发器内部语句数|
|member_batches_attempted/completed|成员INSERT包装进入/成功次数；不读取SQL参数来猜成员数|
|inflight_sql|当前未返回的固定SQL phase、sql_ordinal、成员写批序号及进入时刻；无当前SQL时null|
|execute_restored|true为原instance状态已恢复；null为未进入Store；UNKNOWN为不支持自省而原样执行；false为恢复受干扰|
|diagnostic_write_failures/dropped_spans|技术计数，诊断失败不能覆盖原异常/取消|

所有时刻均为同请求perf_counter墙钟，不是CPU。native和Store、Store与SQL是嵌套区间，禁止直接将全部span相加；不能用不同请求P95相减。缺少某个钩子时字段保持缺失/未知，不补假0。

## 该阶段能回答与不能回答

在下次失败的同trace中，可区分认证未返、Store未进入、某个具体固定phase/写批未返、Store已返回但response/app尾部未结束。新的Store仍是普通lazy AsyncSession，**没有测量或宣称READ COMMITTED/checkout/池等待/CID/服务端事务退出**。首次SQL的墙钟可以包含连接获取，但不能将整段说成池耗尽；如它确实异常再按下一授权增加精确pool钩子。

本阶段不新增P_S observer、不读SQL_TEXT、不KILL、不释放人为holder，不改原10秒客户端截止、50k规模/1000分块、连接池或worker。异常/取消最终原样传播，诊断落盘失败仅技术计数；ContextVar精确reset，已结束观察对象不再接受迟到mark。真正SQL取消/commit/网络边界仍须后续实际证据。

## 纯协议检查

```text
PYTHONPATH=.;python;python/ruoyi_fastapi
.venv/Scripts/python.exe -m pytest python/tests/test_account_scope_http_diagnostics.py -q
# 49 passed in 1.35s
```

包含原32项显式True/路径及reparse拒绝、原返回对象/异常/取消、已有execute属性精确恢复、ASGI message与receive原样、非目标/lifespan/无请求上下文透传、SQL进入前持久inflight、请求配额/span上界、坏分类降OTHER、落盘失败不遮业务异常、重复与活跃卸载拒绝、不支持session自省的原样执行、并发隔离和迟到mark、原ContextVar恢复、旧scope工具叠装成功/异常/取消；另17项检查manager安装任一步失败、部分descriptor回滚、两个cleanup都尝试、uvicorn原异常/取消与cleanup错误优先级、无原异常固定失败、summary错误不遮原错，以及真实两层包装组合恢复。测试使用传输/Store替身，不是新manager实际认证、SQL或HTTP验收。
