# 本版范围适用说明

本文为原合同详细语义基线。已删除的独立模块流程不再实施，适用边界以01_修订需求与删除边界.md为准；保留页面的字段、AI闭环、预算、状态与双通道规则不因此删除。

# 权限合同

## 已确认规则

U-01：一般用户只能看自己的数据；团队管理员可看整个团队；超级管理员可看系统全部数据。U-02：菜单根据角色分配的菜单权限决定。以下具体实现为方案默认。

数据角色：USER、TEAM_ADMIN、SUPER_ADMIN。与自定义功能角色分开；用户可有多个功能角色，菜单与动作取并集，数据角色取已显式授予的最高等级。只有超级管理员能授予/撤销数据角色和团队管理范围；用户不能修改自己的角色。必须保留至少一名启用的超级管理员。

## 什么是自己的数据

|资源|所有权及筛选|
|---|---|
|当前账户、广告实体、余额及实时同步|当前账户operator_user_id为自己；团队按当前owner_team_id；超级管理员全部|
|历史投放事实、历史归属报表|事实冻结operator_user_id和owner_team_id；不随当前转移变化|
|计划、草稿、模板PRIVATE、素材、规则、建议、任务、申请|owner_user_id为自己；团队按owner_team_id；任务继承计划或建议所有权，不以Worker身份为拥有者|
|客户、产品、渠道、马甲包、户商|显式data_owner_user_ids包含自己；团队按owner_team_id；超级管理员全部。一个记录只属于一个团队，可分配多个同团队用户；默认仅创建者，团队管理员可以指派团队成员，普通用户不可扩展分配集合|
|模板TEAM|不绕过“自己的数据”：共享时记录明确recipient_user_ids，默认分享当前团队启用成员的冻结集合。接收者获得使用/查看权，不获得编辑权；新成员不自动加入，需管理员重新分配|
|提醒、操作日志、审计、导出|跟随原对象和当前角色可见范围；普通用户可读自身操作及自身对象相关事件，字段脱敏；导出下载再次鉴权|
|公共字典/系统配置|配置数据，不包含他人业务记录。须有对应菜单及read权限；密钥原值任何角色都不可读取|

主数据被分配给自己即为自己负责的数据，不是任意团队共享。团队管理员或超级管理员创建投放计划时必须指定一个所属目标团队的owner_user_id；计划内所有账户必须属于该投手和团队，同租户同币种。普通用户owner固定本人。管理员可以跨团队查看汇总，但一次写任务不跨租户/团队/投手。建议与规则同理，避免一个批次把A用户的命中结果授予B。

引用约束：写入时所有主数据/素材/账户引用均须在调用者可读范围，且计划拥有者也可读。只知道ID不能建立引用。跨团队引用拒绝422；无权引用返回404。不可通过增加子对象反向获得父对象权限。停用不删除历史；主数据撤销用户分配后，该用户不可再读当前记录，只保留已合法冻结的历史名称，不包含Token/联系人/费率等无关字段。

## 菜单与动作

读取接口须同时满足：登录有效、menu.read、对象数据范围。变更接口额外要求明确action_code及对象可编辑。原型隐藏菜单不作授权依据。无菜单/动作权限403；存在性敏感的对象无数据权限统一404。超级管理员的数据范围覆盖全部，但仍按角色配置显示菜单和执行动作。

|menu_code|页面|可分配action_codes|
|---|---|---|
|accounts|广告账户|read、import、assign、sync、unbind|
|launch|创建投放|read、create、edit、execute、publish|
|templates|模板|read、create、edit、share、archive|
|tasks|执行任务|read、cancel、retry、reconcile|
|monitor|数据监测及建议|read、suggestion.edit、suggestion.ignore、optimization.execute、manual.execute、emergency_pause、ad.delete|
|rules|规则|read、create、edit、enable、pause、archive|
|assets|素材|read、upload、edit、delete|
|tags|分类标签|read、create、edit、archive|
|reports|投手和渠道报表|read、export|
|requests|资源申请审批|read、create、edit、submit、withdraw、approve、fulfill、verify|
|clients/products/packages/channels/vendors|各独立菜单|read、create、edit、archive、assign；packages额外secret.write|
|environments|AdsPower监测|read、enroll、revoke、probe|
|system|人员团队角色及审计|read、users.manage、teams.manage、roles.manage、dictionaries.manage、integrations.manage、audit.read、kill_switch、release.manage|

实际permission_code为menu_code.action_code，例如launch.publish。CRUD的read权限不隐含写权限。系统菜单置最后，规则入口可在monitor下显示，但规则接口同时要求rules菜单授权；没有rules菜单时监测页不展示规则管理入口。

初始化功能角色模板：投放师拥有accounts.read/sync、launch.read/create/edit/execute、templates.read/create/edit、tasks.read/cancel/retry、monitor.read/suggestion.edit/suggestion.ignore/optimization.execute、rules全部非archive动作、assets全部、tags.read、reports.read/export、requests.read/create/edit/submit/withdraw及五类主数据read。publish、ad.delete默认不授予。团队管理员默认在此基础上增加accounts.import/assign、主数据create/edit/archive/assign及templates.share；审批/履约/核验需独立功能角色。超级管理员初始化获得全部菜单动作，但禁止自审及不可读密钥仍有效。各模板允许由超级管理员调整。

申请需职责分离：审批者不能是申请人；履约者不能是该申请审批者；核验者不能是申请人、审批者或履约者。同一用户可拥有多种功能角色，但不能在同一申请冲突兼任。缺少合格人员时保持待处理，不降级绕过。

## 跨租户与服务主体

系统支持多个租户；超级管理员“全部”指本系统所有租户，绝不指平台上未授权资产。全局查询服务取得session的server_scope，按目标租户逐事务SET LOCAL；聚合返回包含租户/币种/profile，禁止把不同币种合并。普通API不接收tenant_id；超级管理员写接口使用受控X-Target-Tenant请求头，服务端确认其角色，审计actor+目标租户。非超级管理员传该头直接403。数据内容仍不接收actor_id或任意tenant_id。

数据库应用角色不拥有表且无BYPASSRLS；每张租户表FORCE RLS。查询服务额外强制owner/team过滤；ClickHouse相同。缓存键含actor权限指纹、scope_version、tenant、筛选、profile和snapshot。权限变更增加scope_version，撤销缓存及SSE订阅。正在导出的文件立即撤销下载。

Worker保存initiator_user_id、owner_user_id、owner_team_id、policy_version、scope_version。每次外部发送前重新校验发起人有效、拥有者范围及动作授权；失效则未发送命令BLOCKED_AUTH。已发送操作继续由专用核验主体只读对账，不在撤权后盲目重发。用户调队立即失去旧团队当前资产写权；历史数据按冻结所有权规则可读。

## 认证

首期采用OIDC授权码流程，服务端会话Cookie为HttpOnly/Secure/SameSite=Lax，所有写请求验证CSRF。会话闲置30分钟、绝对有效期12小时。邀请一次性24小时有效；禁用用户立即撤销会话。开发环境使用本地fixture身份提供者，生产不能启用身份切换器。部署时配置受信OIDC issuer/client/redirect，未配置不开放生产登录。不实现自建密码恢复；跳转身份提供者受信入口。
