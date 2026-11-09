# 账户只读列表/详情的原认证短生命周期适配

生产改动仅新增 `python/orbit_api/account_read_identity.py`，并在 `account_details_routes.py` 增加独立 ReadUser alias，**只替换extended与details的user依赖**。原User alias及owner-options不动；原read_committed_session、完整账户Store、late business authorize与末段授权重核全部保留。

新依赖签名：`account_read_identity(request: Request, token: Annotated[str | None, Depends(oauth2_scheme)]) -> CurrentUserModel | None`。使用原oauth2_scheme取得参数；不自己解析Bearer/Cookie、不另写鉴权、不只复制user_id。自己创建 `DataSourceRegistry.session(log_sql=False)`，显式传给原 `LoginService.get_current_user(request, token, owned_session)`，原完整认证返回之后退出这个自有context，随后返回同一个原CurrentUserModel对象。没有关闭/回滚注入的共享session，也未修改公共DBSessionDependency、LoginService、Cookie/auth_snapshot、pool/worker/ping或缓存策略。

## 为什么不重建DTO

原 `_get_current_user_from_db` 已将ORM结果转为原Pydantic UserInfoModel，dept与role字段分别是DeptModel/RoleModel；permissions/roles由原查询结果物化。UserInfoModel.password有exclude=True。不能以model_dump/validate“证明物化”却漏掉exclude/private/extra，故适配直接返回原对象；不加每请求序列化或deepcopy。原RequestContext保持由原认证设置的同一个对象，原认证排除规则返回None时也保留原返回，不创建匿名成功对象。

原生路径完整保留：初始token→持久auth_version validator→原用户快照/DAO→策略pipeline→原最终token原子续期；Cookie通过原external resolver保留BrowserSessionStore/CSRF/用户资料与原ContextVar绑定。认证异常/取消不翻译、不重试。所有业务可见性和当前权限仍由原账户Store重新核验，短认证连接不成为永久授权票据。

## 现有调用边界与证据

原DBSessionProvider默认yield为request生命周期（FastAPI本机源码），被原配置/人员controller等同源依赖共享，所以不能在原resolver随便close/rollback。账户这两个ORBIT路由没有额外原query_db参数，也没有原controller的PreAuth APIRouterPro链；上游FastAPI创建没有全局Depends。它们只需要完整用户DTO后再进入独立RC事务，适合专属短适配。

上一实际native租约档800暖请求逐一证明：同pool、native/RC不同record、RC进入及返回时native活跃1，且native checkin在最后body之后、app_end之前。200行档同request双租约重叠下界均值386.693ms。这是实现动机，不是本新适配已验结果。原租约聚合和具体限制见 `ACCOUNT_LIST_QUERY_DIAGNOSTICS.md` 的062段。

**新适配实施之前**主线原无仪表44/44 PASS141.01s，四档P95=.387767/.458551/.700815/.842230秒；50k create4.9162s/full250pages22.9347s。此基线通过不能归因尚未实施的新短适配，也不称冷启动或新scope容量验收。

## 当前纯验证与未验边界

执行：`.venv/Scripts/python.exe -m pytest -q python/tests/test_account_read_identity.py python/tests/test_account_details_store.py python/tests/test_account_details_contract.py`，**56/56 PASS，.92秒**（新增14、原42），三文件Ruff check与format check PASS。

新纯测试用协议替身注入完整原认证入口，覆盖：原oauth2 Depends identity、原请求/token/owned-session精确传递、Bearer/None两路不手读Cookie、context退出先于业务、无共享session触碰、原对象及exclude/extra/private/嵌套角色/策略字段保留、源对象关闭后嵌套Pydantic值仍可读、原认证各阶段异常对象原样、在途取消及owned退出失败阻止业务结果、每次并发独立自有session。AST确认仅两个目标路由使用ReadUser、owner-options仍User、原业务RC和Store调用不变。

纯测试**不等于**重新实现或真实验证JWT/Cookie/Redis授权；真实链需主线当前HTTP/原生回归与原44容量串行重验。没有自行连接DB、运行真实HTTP/浏览器/Git；当前源码冻结交主线。新适配无幂等/写入动作，不执行广告或其它平台网络。

## 主线已执行范围

新适配接入后，主线原MySQL/Redis/JWT HTTP及容量整档44/44、140.78秒通过，回执`evidence/python-account-scope062-short-auth-pass.json`。原50k账户/百万事实、20并发、四档各200暖样本、一秒门槛及十秒POST不变；P95分别0.489427/0.551382/0.612837/0.824666秒，原50k范围创建4.823568秒/250页全程31.147130秒、完整hash和UUID集合一致。新56项纯测主线另重跑0.98秒通过。

此前无新适配基线已44/44通过，故不能把达标首次归因此新改动，也不能声称四档都更快；本轮证明有限回归与当前性能仍达标。Cookie路径的成功读取、当前权限撤销以及畸形Cookie+有效Bearer不得回退，另排真实专项，尚未据本段标通过；原全局共享provider/owner-options不受此两路由适配替换。

## 主线后续实际短认证回归

主线已执行新适配后的原44：**44/44 PASS，140.78秒**，四档P95=.489427/.551382/.612837/.824666秒，50k create4.823568s/full250pages31.14713s；证据 `docs/orbit/evidence/python-account-scope062-short-auth-pass.json` 与 `python-account-scope062-short-auth-report.json`。这一档证明本范围当前通过，不声称所有档均比基线快，不代替Cookie专项或真实平台验收。

## Cookie账户专属补充（已实际执行，限定范围）

新增 `tools/account_read_cookie_checks.py`，入口：

```
await run_account_read_cookie_checks(
    client, admin, sessions, store, issue, binding, actor, headers, cases,
    database=database,
)
```

由主线在 `browser_session_checks.py` 原 `await run_cookie_http_checks(...)` **完整六组结束之后、run_oidc_callback_checks之前**，用明确新flag条件调用。不能在原六组精确权限断言前加角色；不修改Cookie旧helper、原CASE清单或会话Store，不新建HTTP会话发行入口。复用原async `issue()`、sessions工厂、BrowserSessionStore和binding；工具本身不加载私有env或凭据。

原fixture actor为users[22]（固定原生980022、user_directory_22、启用USER），已有角色仅system.read/system.users.manage，无accounts.read。工具先验证host127.0.0.1:13306、实际SELECT DATABASE()与严格UUID库名、原当前身份；然后用root真实roles API创建只含accounts菜单和accounts.read的新随机角色。只临时SQL绑定该新角色给fixture actor，不改原role/epoch。两条随机账户分别归本人/原fixture另一个真实owner，币种USD、UTC、授权和账户状态UNKNOWN、无观测；这些是**SQL-only技术样本，不是平台采集或权威余额/花费**。

固定两业务组：

1. `pythonAccountReadCookieOwnScopeAndImmediateActionRevocation`：合法Cookie的extended仅一条本人数据、details本人200；另一个真实owner details404，list不可见。重复带有效root Bearer仍同样受Cookie本人范围约束。解除新增角色绑定后同Cookie两路由严格403，带root Bearer也403，不fallback。
2. `pythonAccountReadCookieRejectsMalformedDuplicateAndSignedOutWithoutBearerFallback`：恢复本轮新增绑定后两路由先严格200；畸形Cookie、重复session名称、重复Cookie头各带有效Bearer均严格401。调用原store.logout撤销该**同一个Cookie**，两路由带/不带Bearer都严格401。

所有成功响应校验原14字段Account与补充details结构、真实id/当前ownership；UNKNOWN余额/花费保持None，身份UNSYNCED且count=None，不以技术样本补零。每组只有所有严格断言完成才append固定CASE。finally只删除本工具新增的actor角色绑定和两条精确随机账户，推进account clock；不删除原角色、不改auth_version或原会话撤权。新未指派角色留当前隔离库的API审计，随本轮UUID库统一清理，不对原业务角色做额外操作。

对应 `python/tests/test_account_read_cookie_tool.py` **22/22纯护栏PASS .17秒**，Ruff/format PASS。覆盖错误host/port/真实DB/actor角色状态拒绝、仅SELECT拒绝路径、UNKNOWN不能伪0、当前owner字段、失败后精确清理新增绑定/seed及不改epoch。这个计数不是两组真实HTTP已通过；没有由本代理运行DB/HTTP/Git。主线负责注册显式flag、预期+2及串行实跑。

主线随后以 `--migration-through 62 --include-account-read-cookie` 实际执行原默认173组与新增两组，**175/175 PASS，112.99秒**。两组分别在14.43/14.49秒完成，原Cookie六组先执行，原OIDC及目录/配置/渠道回归随后完成；回执为 `evidence/python-account-read-cookie062-http.json`。因此上文“尚待”属于工具交接时历史，不再代表当前执行状态。本次限定证明账户两条短会话路由的Cookie成功读取、当前范围和撤权、畸形/重复/注销拒绝以及不回退Bearer；不代表生产IdP、完整账户模块或全产品验收。原44容量与本175回执分别保留，连接占用优化另以同规模显式诊断验证。

## 实际连接释放与性能限制

随后同原数据、四档各200次、20并发的显式仪表档保留为 `evidence/python-account-query062-short-auth-first-failed.json`：31通过、1失败、12未运行，200行P95为1.077179秒，超过原一秒门槛。其余三档P95为0.603815/0.687153/0.742468秒；不放宽标准，也不把本轮仪表档当无仪表容量通过。原无仪表44通过记录独立保留，波动与百万身份旧失败仍不代表已解决。

同档809份脱敏报告中，排除首个200行冷读，四档共800个暖读全部原生租约在RC获取前已释放；RC进入与返回时原生活跃租约均为零，监听器清理全部REMOVED。与旧800/800重叠的样本相比，本轮0/800重叠，支持最小短会话达到了减少同时占用连接的目的；不是所有响应更快或生产稳定性的证明。200行原生租约平均82.661毫秒，旧样本669.768毫秒，仅为不同轮次技术采样对比，不能作严格因果延迟结论。原始安全样本及汇总见 `python-account-query062-short-auth-samples.json`、`python-account-query062-short-auth-analysis.json`。

主线最终账户合同/Store/短认证/Cookie护栏定向78项通过1.01秒，八文件Ruff及格式通过；初次命令误写不存在的routes测试路径导致未收集，日志保留后改为实际contract/store文件完整运行，不计第一次为测试通过。
