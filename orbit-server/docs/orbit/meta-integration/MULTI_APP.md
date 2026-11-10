# 后台绑定多个 Meta 应用

2026-11-10。此变更替代仅依赖服务器环境变量选择单一应用的操作方式。既有受控服务器应用仅作为历史来源兼容，不能悄悄替换绑定来源。

## 操作

1. ORBIT工作台 → ORBIT系统管理 → 系统配置 → 绑定 Meta 应用。
2. 填写应用名称、应用编号（App ID）、应用密钥（App Secret）、市场营销 Token、企业登录配置 ID。Graph API 版本保持当前支持的 v24.0。市场营销 Token 单独加密保存，OAuth授权本身不需要预填它，且不会把它自动用作客户Token或BM凭据。
3. 密钥字段选“替换”并输入。编辑已保存配置时默认“保持”，任何接口不返回明文或密文。启用并填写变更原因后保存。
4. 广告账户 → Meta连接，或系统配置 → Meta连接与授权状态，选择应用后点连接Meta，再点继续前往Meta。授权成功后选择账户与原有投手、团队、户商、渠道。
5. 重新授权沿用原连接绑定的应用，不能借重新授权切换到其他应用。更改App ID应创建新应用配置和新连接。

## Meta开发者后台

- 有效OAuth跳转URI：`https://drmovira.com/api/v1/integrations/meta/callback`，必须完整一致；首页地址不能代替。
- 当前采用服务器授权码交换，不使用JS SDK。保持“使用JavaScript SDK登录”关闭，“JavaScript SDK允许使用的网域”留空。
- 应用设置 → 基本设置 → 应用域名：`drmovira.com`。
- 网站URL（若界面要求）：`https://drmovira.com/`。
- OAuth客户端授权登录、OAuth网页授权登录启用，HTTPS与严格匹配保留。
- Business Login配置ID来自该应用的“企业版Facebook登录 → 配置”；它不是BM ID，也不是App ID。
- 每个后台应用绑定使用独立签名回调：取消授权`https://drmovira.com/api/v1/integrations/meta/applications/<配置UUID>/deauthorization`；删除请求`https://drmovira.com/api/v1/integrations/meta/applications/<配置UUID>/data-deletion`。保存后编辑该应用，复制表单显示的完整回调地址；其中配置UUID不是Meta App ID。删除请求先登记待处理，不宣称立即删除全部历史。
- 对外客户使用仍须Meta实际权限、应用发布及审核；开发模式只能在Meta允许的应用角色范围验证。固定只读用途，不开放广告写入。

## 安全及升级

显式执行076迁移。原生登录的有效Bearer经同源POST转换成HttpOnly/Secure/SameSite=Lax浏览器会话，转换消耗原Bearer；同源与权限检查不因此放宽。过期会话清理Cookie，转换中退出等待并撤销新会话；其他接口不从失效Cookie自动回退Bearer。

授权state冻结应用配置UUID和版本，幂等摘要含应用来源，回调从state查回应用。网络前后重验配置；配置停用/修改会阻止旧来源采集，已有历史仍保留。客户Token与应用密钥分别加密。撤销回调、发布互斥与回执按应用配置隔离，自行声明同一个公开App ID不能撤销别的配置或租户。

验收报告另附；真实Meta授权必须由实际应用管理员在后台填写秘密并完成Meta页面授权。不要通过聊天或GitHub提供密钥、Token或验证码。
