# 系统配置Servlet接口与安全边界测试

## 实现范围

`OrbitConfigurationSecurity`独立安全链只匹配`/api/v1/system-configurations`及其子路径，优先于若依默认安全链，继续使用若依JWT过滤器和`ss`权限服务。原若依接口、登录、布局和菜单保留。系统配置未登录返回真实HTTP401与固定`UNAUTHENTICATED`错误，不回显请求URI、原异常、请求体或Authorization。

这些接口的所有安全链响应均设置`Cache-Control: no-store`和`Pragma: no-cache`，包括Controller之前的401/403；采用无状态会话，不保存请求、不跳转登录页面、不创建JSESSIONID。Controller层继续要求system.read和system.integrations.manage，Service复验活跃租户SUPER_ADMIN数据角色，风控编辑另需system.release.manage。

## 实际测试方式

`OrbitConfigurationHttpTest`使用MockMvc加载真实Servlet分发、若依原SecurityConfig/ResourcesConfig/重复提交拦截器、JWT过滤器、权限表达式、ORBIT安全链、Controller、Service和异常处理器。TokenService会话存储、RedisCache、Mapper、平台传输使用fixture；这不是TCP网络HTTP或真实Redis验收。

运行完整后端单测及编译：

```powershell
python -u tools/run_orbit_checks.py --java-home D:/progress/adpulse-power-system/.codex-toolchain/jdk --maven D:/progress/adpulse-power-system/.codex-toolchain/maven/bin/mvn.cmd --frontend D:/progress/orbit/orbit-web --skip-frontend
```

前端源码本轮未变，复用其原执行时间的成功回执。Java回执现在汇总所有模块的Surefire结果，包含admin Servlet测试，不能只统计system测试。专项明细、源码hash及测试边界另见`evidence/http-configuration-boundary.json`。

## 覆盖断言

- 系统配置未登录真实401、脱敏错误、request_id、防缓存及不创建Cookie；原若依未登录HTTP200/body401保持原行为。
- 菜单权限和集成维护权限必须同时存在；USER/TEAM_ADMIN即使持有若依通配权限也被服务端数据角色拒绝；撤销租户授权后不可读取。
- 元数据/列表、新增201、脱敏详情、幂等重放；真实Java时间字段按ISO字符串返回。响应和捕获日志均不含输入凭据或密文信封。
- 保留原重复提交拦截器，配置新增/重放不触发Redis请求体缓存；配置接口不加默认@Log请求体记录。
- 非法JSON、未知字段、缺请求头、非法If-Match、查询类型错误返回安全400；不可见配置/历史404，旧版本及重名409，未知持久化错误500，均不输出原始异常内容。
- 历史版本游标及脱敏摘要输出，风控缺发布管理权限403。

第一轮测试发现WebMvc slice仍会加载若依原资源/重复提交拦截器，补入RedisCache测试替身；第二轮发现登录fixture缺SysUser，补齐与若依身份对象一致的基础信息。第三轮新增重名冲突用例时，Mockito重新设桩触发了旧Answer，改用doThrow正确覆盖；三轮失败均保留回执。不得通过移除原拦截器或绕过方法权限让测试通过。

## 仍须验证

此回执只证明Servlet范围。真实JWT/Redis/网络HTTP已另见NETWORK_INTEGRATION.md；完整应用原登录、动态菜单和GPT配置弹窗专项另见BROWSER_INTEGRATION.md。所有页面/弹窗、验证码启用流程、完整权限矩阵、真实平台凭据和模型质量仍待验收，不能从本专项扩大结论。

人工原因接口新增一项Servlet回归：缺请求体、未知字段/凭据字段、非字符串安全400，空白原因422；这些输入均不调用探测、不写验证或审计，日志不包含探针凭据。以最新实际回执为准。
