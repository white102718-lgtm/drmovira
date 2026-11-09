# Meta 身份来源的官方文档核对

核对时间：2026-11-09（北京时间）。普通文档抓取未取得正文后，使用内部浏览器直接读取 Meta 官方页面；未登录平台、未发送 Graph 请求、未执行广告或权限写操作。本记录是接口设计依据，不能作为实际账户具备资格的证明。

## 已确认的区别

1. [广告账户指南](https://developers.facebook.com/docs/business-management-apis/business-asset-management/guides/ad-accounts)区分企业资产清单与指定主体的账户访问权限。企业拥有的账户清单包含可分配任务及所有者/代理关系；不能据此推导当前配置主体已经获准创建广告。主体获分配的账户以及账户获分配的用户需独立查询并逐个绑定真实主体、企业和账户。
2. [公共主页指南](https://developers.facebook.com/docs/business-management-apis/business-asset-management/guides/pages)分别提供企业拥有/客户主页清单、主体获分配主页以及主页获分配用户的查询方式。分析任务与广告任务作用不同；仅在清单中出现不代表该主页在目标广告账户上可用于当前投放。
3. [系统用户权限指南](https://developers.facebook.com/docs/business-management-apis/system-users/guides/permissions)明确系统用户的资产任务需要实际分配。该文档提供读取主体获分配账户/主页的入口，且区分用户编号、企业、令牌权限和资产任务。页面中的写入示例仅为文档说明，本项目未执行这些操作。
4. [系统用户概述](https://developers.facebook.com/docs/business-management-apis/system-users)把系统用户与服务器/软件关联，并说明代理真实用户时的 OAuth 归因要求。配置中的数字 ID 或一次 `/me` 匹配不能单独证明主体类型、全部权限或真实用户归因。
5. [应用指南](https://developers.facebook.com/docs/business-management-apis/business-asset-management/guides/apps)区分企业拥有、可访问及待审批应用。待审批项不能作为可用项。该页面未给出足以实现目标账户广告用途判断的完整响应合同；不能把清单存在直接映射成 `usable=true`。

## 后续生产发行实现必须补齐

- 针对实际 Graph 版本核对精确只读字段、分页、返回任务与失败语义，并验证指定凭据能实际读取；不能只凭上述概述拼装未验证的响应格式。
- 资产库存、配置主体匹配、账户与主体任务、资源与目标账户用途兼容性分别记录完整来源。分页缺失、来源撤销、任务不足、版本不支持或目标关系未知均不得发行可用资格。
- 主页、应用、像素及其他用途不能互相套用权限规则；当前核对未补齐像素和应用投放用途的生产判断合同。
- 源请求必须限定只读；不得执行文档中的权限分配、移除资产、创建账户或广告写入示例。
- 现有隔离协议发行与 SQL 技术样本仍保持技术样本标识。055 摘要 MAC 只校验本系统已经完整发布的数据，不替代上述 Meta 来源，也不授予执行权。

这次解决了官方文档正文读取途径的问题；真实凭据、真实主体/资产对应关系及生产资格发行仍需独立验证。
