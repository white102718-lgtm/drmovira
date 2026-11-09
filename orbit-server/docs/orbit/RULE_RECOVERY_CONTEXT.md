# 规则原请求的再认证上下文

本技术扩展供规则定义的未确认写恢复直接消费，不改变原Rule15、原`/rules/capabilities`单csrf字段或任何动作状态机。新增静态入口须由主线在动态`/{rule_id}`前注册；B没有修改application、现有认证/路由、数据库或权限表。

## 准确接口

`GET /api/v1/rules/recovery-context?action=CREATE|UPDATE|ENABLE|PAUSE|ARCHIVE|SIMULATE`

只接受唯一action参数，无GET正文；未知/重复query参数400，显式x-target-tenant头403，无效/缺少action为422并指向`/action`，非空正文400。用户不能提交actor_id、tenant_id、rule_id、owner或任何过滤器。用户身份只从原CurrentUserDependency取，当前tenant只从原服务端业务授权取。

成功200严格三个必需字段，无其它属性：

|字段|准确语义|
|---|---|
|actor_id|原若依/native user_id正安全整数，1—9007199254740991；不是business user UUID|
|tenant_id|当前可信业务tenant规范小写UUID，不接客户端指定|
|csrf_token|原DIRECTORY_CSRF_V1真实会话绑定token，16—255字符；Cookie仍返回该当前内存会话原CSRF|

动作逐项沿原授权：CREATE→rules.create、UPDATE→rules.edit、ENABLE→rules.enable、PAUSE→rules.pause、ARCHIVE→rules.archive、SIMULATE→rules.read。它不为前五项增加rules.read，也不借accounts、system/users、monitor或目录权限。返回上下文不表示对应业务依赖/Simulation/provider已就绪，更不表示动作已受理。

外层原session.begin事务包围读取与响应；先authorize_rule当前动作，再签发原会话绑定CSRF，严格核三字段，最后revalidate_access完整当前范围。初始/末段会话失效、撤权或范围变化原样拒绝，不返回部分身份/CSRF。内部DTO损坏503固定安全错误，原Cookie主体/租户与当前上下文不符401。没有新增MAC用途、持久表、后台任务或写副作用。

## 直接前端消费者边界

1. 在首次发出实际规则写前获取本动作上下文，将真实actor+tenant与原私有intent关联；不能在已经未知之后把另一个当前会话身份猜成原提交者。
2. 原body、Idempotency-Key及带引号CAS必须保持；未知结果不能因重试本轮401/403/409就被当成原请求未受理。只允许手动恢复原请求。
3. 专属SPA内存持有者可保留原意图并允许进入既有认证页面；新身份隐藏旧规则name/原因等，不能自动重发，也不把原nonce简单替换成新nonce称重新授权。该接口不要求/实现跨整页刷新或浏览器重启持久恢复，不将凭据或业务事实放Storage。
4. 再认证后由此GET显式确认同一真实actor和tenant及本动作当前权限，才可让用户选择恢复。可更新的仅当前传输CSRF；原body/key/CAS不变。具体Rule当前可见性、原成功幂等回执及状态/CAS仍由原POST/PUT当前门禁核验；此接口没有给任意Rule或旧head永久许可。

原规则GET/metadata的读权仍独立，界面不得因当前动作上下文成功就直接披露内存中的旧对象内容。原同键成功回执可在head随后变化时返回，前端也不能私自用新CAS替换原请求。

## 文件及证据

- `python/orbit_api/rule_recovery_context_routes.py`：独立router、小型当前上下文函数及StrictInput响应。
- `python/tests/test_rule_recovery_context.py`：38项纯协议通过，0.93秒；覆盖六动作精确权限、三字段严格结构、native/tenant安全类型、初始及末段401/403/409、Cookie原CSRF/错主体租户、拒绝未知重复query/targettenant/GET正文、真实route函数一层外部事务。无SQL、HTTP服务或私有配置加载。
- 生产能力尚待主线注册和真实HTTP；纯测试不计再登录/恢复或浏览器闭环通过。

teamai-recall已检索相关ORBIT再认证/actor/tenant/CSRF口径，返回的两项均为其它AdPulse主题，未将其当成本接口需求。实现以本次明确授权、原API_SEMANTICS幂等重放与当前rule_access/DirectoryTokens为准。

## 独立真实HTTP工具（待主线串行执行）

`tools/rule_recovery_context_checks.py::run_rule_recovery_context_checks(client, admin, headers, password, cache, database, cases, *, keys)`；固定 `RULE_RECOVERY_CONTEXT_CASES` 八组。`keys`只能由主线现有隔离fixture显式传入，不读取私有配置、不写Token/CSRF或连接串。工具先检查127.0.0.1:13306及实际本轮`orbit_py_it_32hex`库，绝不自行启动HTTP/数据库。

1. root六动作精确三字段，actor为native整数1、当前tenant；使用原DIRECTORY_CSRF_V1核MAC与真实会话绑定。JWT有效期跨秒不要求与另一次capabilities响应字节相同。
2. 真实角色API各创建一个单动作角色，六名独立USER（990690—990695）只含对应原权限；其余五动作403，SIMULATE只归rules.read，没有额外目录/账户/监测动作。
3. CREATE-only用户用恢复上下文返回的真实JWT CSRF，经原editor-scope POST及原Rule POST创建DRAFT。root GET完整回读相同Rule；创建者本人无rules.read仍403，不以签发CSRF代替业务落库。
4. 未知/缺失/非法/重复query、客户端tenant/actor参数、X-Target-Tenant与GET正文按原边界拒绝；错误不含任何部分actor/tenant/CSRF字段。
5. 原业务角色rules.edit撤回后旧JWT立即403，恢复原单项后同JWT可重新读上下文；不提升角色或绕过原认证。
6. 实际创建独立外租户/团队，将read-only用户当前scope切换过去。缺真实当前身份时旧JWT严格401；补齐外租户本人及完整native/business只读角色映射（native role990696），再经原fixture_login重新认证取得新JWT，才只返回外租户本人上下文。原CREATE及指定root租户仍403，root自身上下文不变。finally恢复原scope和新增临时角色绑定，不再复用外租户claim访问原租户。
7. 专用UNTESTED OIDC配置和明确外部身份只作为隔离Cookie存储夹具，非OIDC回调验收。两次真实BrowserSessionStore.issue产生不同会话及CSRF，新Cookie取得原CSRF后实际创建另一个原Rule DRAFT并root回读；Cookie与root Bearer并存仍是Cookie本人的actor/tenant/CSRF。
8. 畸形/重复Cookie加有效root Bearer仍401，不回退；真实store.logout撤销后同Cookie两种认证头组合仍401，错误不披露部分上下文。

SQL账户/profile为技术样本，不代表Meta授权、Simulation成功、ENABLED或广告写入。CREATE-only样本严格不增加rules.read。工具只修改自建actor/角色/外租户/技术source，旧业务数据与旧角色不变；专属数据库由外层主线最终销毁。未新增公开配置入口或假写端点。

定向纯证据：新工具21项护栏，连同原endpoint38项共59项通过（1.11秒）；Ruff/format/py_compile通过。**这不是八组实际HTTP或前端再认证验收**，待主线接入原规则闭环后执行。

首真实档保留 `python-rule-recovery-context-first-failed.json`：基线6及root六动作组通过，共7 PASS/1 FAIL/7未跑。失败在工具将ORBIT的no-store断言误用于原native `/login`，未进入单动作身份矩阵，不改native产品。工具现将`/login`和`/getInfo`分离为严格原HTTP200、整数code200、有效字符串token及精确actor/permissions字段协议；ORBIT所有读取/写入仍沿原checked执行no-store断言。新增9项正反回归，当前endpoint38+工具30共68/68纯测通过（1.27秒），等待主线原15档复验。

第二真实档保留 `python-rule-recovery-context-second-failed.json`：11 PASS/1 FAIL/3未跑，已真实通过前五业务组；外租户尚无完整身份时原JWT实际401 SESSION_REQUIRED，工具原预期403有误。现严格保留401，并在补齐外租户完整native/business角色后原登录重新认证，新JWT核外租户上下文，不更改原产品或降低门禁。Cookie两组仍待真实执行。修后原68项纯测通过（1.07秒），Ruff/format通过。

第三轮主线真实15/15 PASS（12.77秒），回执 `docs/orbit/evidence/python-rule-recovery-context-http.json`：基线6+本工具8+退出1，六单动作6×6权限、JWT原CSRF真实DRAFT、外租户重新认证、真实Cookie新CSRF建DRAFT及root回读、畸形/重复/注销无Bearer回退均通过。仅本API与隔离技术夹具的有限HTTP证明；未将其当成前端完整再认证恢复浏览器验收，也未执行Simulation/Enable/平台广告写入。前两失败保留不覆盖。
