# 系统配置使用与安全边界

> 当前技术覆盖：RuoYi-FastAPI/Python + MySQL8 + Redis，全部功能重新开发。下文历史Java实现描述仅供核对，旧PASS不计新版本通过。现行方案见[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)，状态见PROGRESS.md。
用户已确认AI使用GPT API和Claude API，不运行Claude Code CLI。入口为ORBIT工作台→ORBIT系统管理→系统配置；保留若依原参数设置，两者不混用。

Python当前实现及证据范围见[Python系统配置检查点](PYTHON_CONFIGURATION.md)。以下各节保留Java阶段的业务设计与历史验证描述，其中Java属性、JDBC连接参数、旧SQL迁移命令和旧测试通过结论不能直接用于Python启动或验收。

Python主密钥变量为`ORBIT_PYTHON_SECRETS_ACTIVE_KEY_ID`与JSON映射`ORBIT_PYTHON_SECRETS_KEYS`，仅从指定私有文件读取；新库按顺序执行`python/orbit_api/migrations/`内已审核SQL（目前001—007），必须在明确目标的隔离数据库中显式执行，应用不自动建表。

## 业务目标与历史实现说明

- 配置类型：GPT、Claude、AI建议、Meta应用、Facebook BM、AdsPower执行设置、OIDC、对象存储、指标同步、通知、执行风控。可创建多个模型或BM配置。
- 新增、公开信息回填、编辑、启用/停用、凭据保持/替换/清除，以及只读认证测试。清除须确认，关闭或提交结束释放密钥输入。
- 变更历史抽屉展示操作人、操作后版本、实际变更字段、原因和UTC时间；服务端验证配置可见性并按租户与版本游标分页（每页1至100条）。读历史不读取密文或配置值。
- 公开字段规则需从Python实际配置目录导出并与原62字段扩展合同逐项核对，新增62个字段单列进度。新增接口为独立扩展合同，不篡改原产品127路径。
- 所有写入带幂等键，更新带If-Match；配置、加密凭据、脱敏审计与幂等结果同事务。列表和详情仅返回configured/hint，不返回明文或密文。
- 普通权限同时要求system.read与system.integrations.manage，服务端再校验当前会话用户的活跃租户和SUPER_ADMIN数据角色。风控编辑还需system.release.manage。
- GPT/Claude只读测试查询指定模型，Meta只读测试查询指定应用或BM。仅固定官方域名、Bearer请求头、GET和禁止重定向；不调用AI生成或广告写入。
- OIDC/存储/通知/指标/AdsPower等连接器尚未完成的真实探测返回BLOCKED，不能返回假成功。真实平台凭据未在本任务提供或使用。

## 审计状态摘要口径

新增、修改和只读认证测试均记录操作前后版本、`beforeHash`、`afterHash`和`hashAlgorithm`。`SHA256_STATE_V1`对固定字段的规范JSON计算SHA-256：租户、配置ID、类型、名称、启用状态、版本、公开参数、加密凭据信封和验证状态。JSON键排序，不因键顺序或空白变化而变化；数据库更新时间和探测时间不参与摘要。

凭据不解密、不对明文生成摘要；随机化密文参与整体摘要，因此替换相同Token也会改变摘要。接口及审计不返回摘要输入快照、密文或明文。摘要用于状态核对，不作为数字签名或不可篡改存证，也不能恢复旧值。

新增配置的旧版本为0且旧摘要为NULL。V003之前的历史版本/摘要保留NULL，页面显示“历史记录未采集”，禁止编造旧快照回填。摘要仅记录整体配置状态，变更字段名单另外保存。只读测试在保存结果前复验当前租户，授权切换或版本冲突时拒绝追加结果和审计。

## 凭据与部署配置

AES-256-GCM使用每次随机96位nonce；信封携带key_id，认证附加数据绑定租户ID、配置UUID与字段名。登录JWT密钥不参与凭据加密。旧key可在轮换期间读取，重新加密完成前不能删除旧key。

服务端属性为`orbit.secrets.active-key-id`及`orbit.secrets.keys.<key_id>`，环境变量可用`ORBIT_SECRETS_ACTIVE_KEY_ID`、`ORBIT_SECRETS_KEYS_V1`（active key id为v1）。密钥值由管理员在既有受控私有环境中提供，必须是独立随机32字节的Base64，不在本仓库或页面填写。遵从本机约定，后端私有环境只从`D:/progress/adpulse-power-system/.env.local`加载；不得因为参考项目有凭据就自动复用或连接其数据库。

未配置主密钥时允许应用启动与脱敏查看；新增/替换或内部解密操作失败并禁用，不能明文落库或临时使用默认密钥。

密钥接口不使用若依默认`@Log`请求体日志；前端独立fetch客户端不经过会缓存POST/PUT正文的默认防重复提交机制。使用若依Bearer认证、不携带Cookie，不能把Token放URL。

## 数据库初始化与时间

先使用独立ORBIT数据库执行若依原SQL，再审核依次执行`sql/orbit/V001__system_configuration.sql`、`sql/orbit/V002__configuration_history_cursor.sql`、`sql/orbit/V003__configuration_audit_fingerprints.sql`、`sql/orbit/V004__analysis_job_queue.sql`、`sql/orbit/V005__rule_draft_versions.sql`、`sql/orbit/V006__business_identity_mapping.sql`、`sql/orbit/V007__metric_profile_versions.sql`、`sql/orbit/V008__account_scope_snapshots.sql`、`sql/orbit/V009__scope_permission_versions.sql`、`sql/orbit/V010__scope_directory_identity_versions.sql`和`sql/orbit/V011__scope_public_request_keys.sql`。新空库仅将现有若依用户1映射到默认ORBIT租户，其他用户没有默认业务租户；现有数据迁移须显式核对映射。脚本新增ORBIT菜单、表和权限版本触发器，保留若依原菜单及功能。

所有新DATETIME按UTC保存；运行时MySQL连接须配置`connectionTimeZone=UTC`及`forceConnectionTimeZoneToSession=true`，避免默认若依GMT+8连接误解释UTC字段。业务账户时区另存IANA，不用数据库会话时区推算业务日。

## 尚未验收的事项

系统配置整体仍处于开发/测试阶段：真实MySQL8配置专项已增加独立集成测试，完整HTTP与业务流程仍待验收；完整应用原登录/动态菜单及GPT配置弹窗三视口专项已另见BROWSER_INTEGRATION.md；其余类型全部字段/弹窗、批量主密钥轮换工作流、各业务消费者实际使用配置、真实平台认证与AI建议生成尚须逐项验证。已有单元/组件测试不替代这些验收，详细状态见PROGRESS.md。

## 官方接入依据

- [OpenAI认证](https://developers.openai.com/api/reference/overview)与[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)。
- [Claude API协议、认证和版本头](https://platform.claude.com/docs/en/api/overview)。
- Meta Graph只读探测参考ad-mpower已有HTTP调用与BM对象读取约定；真实权限和版本仍需官方资料及沙箱验证，不因保存Token就声称支持投放。

## 数据库专项测试

独立实例、执行命令、实际覆盖及失败修复记录见[MySQL集成测试](MYSQL_INTEGRATION.md)。配置保存显式READ_COMMITTED，解决并发幂等重放旧快照问题；ORBIT Mapper显式字段映射，不修改若依全局设置。专项测试不等于全量业务验收。

## Servlet接口安全专项

系统配置使用独立安全链，未登录返回真实HTTP401并禁止缓存；不改变若依原接口。权限、异常、日志捕获与缓存专项见[Servlet安全测试](HTTP_SECURITY_TESTS.md)，Servlet专项本身Token会话和Mapper为fixture；真实网络、Redis和MySQL组件联合测试另见下节，完整验收仍未完成。

## 网络联合测试

真实Tomcat/HTTP、JWT、Redis会话和MySQL联合验证见[网络集成测试](NETWORK_INTEGRATION.md)。仅平台探测传输为fixture；完整应用与浏览器专项另见BROWSER_INTEGRATION.md，所有页面和全部配置类型的验收仍未完成。JWT异常日志已改为固定说明加异常类型，防止恶意Header解析错误带出输入。

## Meta应用凭据与对象证据校验

未保存App Secret的Meta应用配置只读测试返回BLOCKED，不拼接`AppID|null`或向平台发送请求。返回的Meta应用ID与BM ID分别必须与当前配置匹配；其他对象的成功响应不能作为本配置通过证据。凭据仅通过Authorization传递，不进入URL，错误信息不回传平台原始响应。

此修复仍不等于BM账户权限枚举、缺失授权展示、真实平台认证或广告写能力验收。受控传输回归证据见`evidence/meta-app-probe-regression.json`，以实际回执结果为准。

## 只读测试人工原因（扩展接口1.1）

页面点击“只读连接测试”后，原生Element Plus弹窗显示当前配置名称与版本；填写测试原因后点击“开始测试”。取消不发送请求、不改变版本；空值、超过500个Unicode字符或控制字符由前后端分别校验。

`POST /api/v1/system-configurations/{id}/test`除带引号的If-Match外，必须提交JSON对象`{"reason":"人工核对连接"}`。仅接受reason字符串；缺失请求体、未知字段或非字符串返回安全400，内容不合法返回422。原因经NFC规范化和首尾空格处理后存入READ_TEST审计，取代此前固定的系统说明。探测结果仍独立写入验证状态；人工原因不能使失败或BLOCKED结果转为成功。

原配置的权限、租户范围、旧版本冲突、测试期间撤权/配置变更的CAS保护保留；不执行广告写入，不自动启用能力。

## AI建议分析限制配置

新增`minimumCooldownMinutes`（分析冷却下限，0—10080分钟，默认60）及`maximumDailyAnalysesPerObject`（每规则每对象每日分析上限，1—1000，默认5）。数值范围与规则合同`fields.json`的cooldown_minutes/max_daily一致；字符串、分数及越界值由服务端拒绝，前端使用原生数字控件。

后续执行语义：冷却取规则值与全局值的较大者，日上限取较小者；额度按规则+对象+调度当地日统计，不按页面人数。执行器原子计数、并发扣额、时区日界和实际调度尚未实现，保存配置不能称为限制已生效。

旧版本公开设置不做读取时回填或数据库静默改写；编辑表单合并当前字段默认值，操作者确认保存后才写入新版本，并记录新增/变更字段。配置采用现有公开JSON字段存储，无新增明文凭据或SQL列。输入/输出限制和租户Token/费用预算仍待补齐。

输入逐日点/证据规模及建议输出Token配置已补齐，边界与输入校验核心见[AI分析输入](ANALYSIS_INPUT.md)。内部分析入队已原子检查冷却和当地日额度，见[分析任务入队](ANALYSIS_JOBS.md)；真实规则分发与模型消费仍未接通。

历史configuration-*-development.json保留当时的开发检查点、命令、时间及源码hash；后续源码演进后不把这些旧hash当最新测试证据。当前测试以java-tests-and-compile.json、http-configuration-boundary.json、network-configuration-integration.json、application-browser-integration.json及对应真实MySQL回执为准，开发完成不等于整条测试或验收完成。
