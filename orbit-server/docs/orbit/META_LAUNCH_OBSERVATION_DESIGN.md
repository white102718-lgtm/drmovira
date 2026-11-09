# Meta投放只读观察最小闭环

当前仅新增`python/orbit_api/meta_launch_observation.py`和专属纯测试。没有改现有MetaAccountPlatform、Worker、身份Store、AuthorityProvider、路由或迁移，也没有使用用户凭据请求Meta。精确关键词teamai recall无匹配；实现依据原合同与Meta官方源，不采用搜索结果的第三方镜像。

## 已核primary来源与限制

2026-11-08读取Meta官方Python Business SDK公开源码；它证明官方客户端存在对应GET与字段，不证明当前配置的API版本、app权限或实际账户一定支持这些读取：

- [Business官方源码](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/business.py)：`get_client_ad_accounts`、`get_owned_ad_accounts`对应BM两条GET边，返回AdAccount。
- [AdAccount官方源码](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adaccount.py)：`api_get`及Field列账户ID、状态、币种、时区、capabilities、user_tasks；`get_promote_pages`、`get_ads_pixels`、`get_advertisable_applications`分别对应GET `/promote_pages`、`/adspixels`、`/advertisable_applications`。

APP选用明确可推广应用边，未把普通`applications`关联清单当可推广证据。配置必须显式提供api_version，不采用SDK默认版本或“latest”。这些main链接是本次检索证据，不宣称每个Graph版本均具完全一致语义。

[Meta BM owned账户文档](https://developers.facebook.com/docs/marketing-api/reference/business/owned_ad_accounts/)此次返回Not Logged In；[官方权限页](https://developers.facebook.com/docs/permissions)与其他边文档返回429。故business_management/ads_read仅是待管理员与官方权限页、真实app/token核对的候选前置，未将其写成已经验证的最小权限集合；Page/App读取的具体scope同样未核。未添加任意ads_management权限请求，未查询、输出或日志记录token。读成功只表示这次目标GET可读取，不等于任意广告写权。

## 原合同与既有代码边界

原`contracts/WORKFLOWS.md:19`要求逐账户page/pixel/application绑定与最终资源预检，`:101`冻结完整树、capability/policy/scope版本。保留章节03第165行要求服务端profile归因。当前`AccountIdentitiesStore`要求真实registry、内部账户revision、来源配置revision及完整能力证据，原公开响应不能擅加本观察技术字段。

本采集器只产生外部账户与身份资源观察，不能产生policy_version、workflow_version或内部capability_version，不把Graph capabilities/user_tasks列表映射成这些版本。未生成public identities的usable=true，也未绕过现有受信publisher/registry约束。

## 接口与实际字段

`MetaLaunchReadConfiguration(source_config_id,source_config_revision,business_id,api_version,token)`为不可变、repr不显示字段的配置；UUID规范字符串、revision正安全整数、外部ID始终数字字符串1至64、版本格式`vN.N`、token仅可见ASCII且不能含空白/CRLF。token只进Authorization Bearer头，不进URL、摘要、返回对象或日志。

`await MetaLaunchObserver(configuration,transport=None,limits=None).observe(account_ids)`接受1至500个无重复外部账户ID，不接受内部UUID、act_前缀或数字类型，不去掉前导零。接口不接收数据库session；组合producer必须先关闭自身事务再await该网络采集，当前未注册该producer。

1. 固定 `https://graph.facebook.com/{api_version}/{business_id}/owned_ad_accounts`与`client_ad_accounts`，fields仅id/account_id；完整枚举后求并集，保留每个目标所属的实际观察边。两边交集允许去重，单边重复记录拒绝为INCOMPLETE。目标不在完整观察BM范围时不继续猜读账户或资源。
2. 固定`/{api_version}/act_{external_id}`，fields为id/account_id/name/currency/timezone_name/account_status/capabilities/user_tasks；响应ID必须精确对应原目标。
3. 每账户固定promote_pages/adspixels/advertisable_applications，fields仅id/name，三种资源全部完成分页才返回成功结果。

缺失字段保留null并列入unknown_fields；真实0状态不改写为未知0，未知也不补0。平台名称不按公开输入255长度静默截断，内部保留最多4096码点；将来public publisher仍须按原schema明确处理。完整空边允许返回空观察清单，但不据此表示已有可投放能力。

返回`MetaLaunchObservation`及内部账户/资源不可变元组和规范JSON字节。包含来源配置ID/revision、BM、实际API版本、开始/完成UTC毫秒、精确请求数/字节数及完整规范观察SHA256；不包含token。complete仅表示此轮有界分页均结束，不表示跨多个GET存在平台原子快照；所有数据属于开始至完成的观察窗口。execution_authorized固定False，policy_version/workflow_version固定None，不能由构造参数或调用者verified布尔改变。

## 固定网络与分页预算

默认transport仅GET，系统TLS证书验证，使用既有PublicNetworkBackend避免解析私网目标；transport本身再次核固定Graph host、版本化只读路径及fields/limit/after白名单，拒绝access_token等任意URL参数。Accept-Encoding为identity，拒绝redirect，不跟随Location。

paging.next必须HTTPS同Graph origin、同配置版本和当前完整path，不允许userinfo/fragment/其他端口。只将其当继续标志并提取不透明after，重建原固定path；绝不跟随原next或转发其中token。next存在而after缺失、空、重复或含控制字符时明确META_OBSERVATION_INCOMPLETE，不返回部分清单假装complete。

硬上限：每边250页、每页200；每BM边50000记录；每账户三类资源总5000；整轮2500请求、单响应256KiB、总响应32MiB、总60秒，单GET最多15秒。调用者只能收紧预算。超过页、请求、记录或字节限制一律失败，未来大批量由独立producer分片，不在本采集器无限拉取。每轮预算独立，不共享上一次授权结果或资源缓存。

错误仅固定code/retryable；401/403及Graph权限错误为固定拒绝，429/已知限流与5xx/瞬态故障可由上层有界重读，redirect/结构错误拒绝。Graph错误message、body、完整next URL以及第三方transport异常正文均不进入错误；无平台写入，因此不把只读失败冒充广告UNKNOWN或成功。

## 当前验证与后续

65/65受控transport纯测试通过（0.48秒），Ruff/格式通过；覆盖固定host/header与URL无token、完整三边观察、BM并集、前导零、unknown/null、真实长名、不透明after、错origin/path、缺失/重复cursor、页/请求/字节/资源预算、坏JSON、Graph固定错误、摘要版本绑定及并发预算独立。新增4个边界用例验证原始capabilities/user_tasks中的NUL与孤立surrogate均按固定错误拒绝，不能在UTF8摘要阶段泄露未脱敏异常。另核第三方transport异常正文/上下文及任意错误code均不能带出token，所有错误重建为固定白名单类别。没有真实Meta调用、TLS外部联通或凭据权限成功证据，不计外部验收。

仍缺：真实凭据/app授权与每边支持核验；内部账户revision/当前授权与观察绑定的可信registry写入；身份执行任务/目标组合兼容证明；真实META指标profile+显式归因映射；policy/workflow版本发行；实时URL/SSRF预检；写前即时授权与真实命令/VERIFY链。本采集器不能使生产默认None或execution_available=False自动开放。
