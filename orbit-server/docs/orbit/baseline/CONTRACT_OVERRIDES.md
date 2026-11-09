# 合同覆盖表（开发必须先读）

本文件与PRD共同解释当前合同。旧文档中的“用户已确认”“首期全部页面”等历史措辞不构成新授权。未在本表变更的保留业务规则继续适用；不能凭一个历史段落重建被删除模块。

|编号|旧材料冲突或缺口|本版唯一处理|
|---|---|---|
|OV-01|WORKFLOWS首期范围含全部管理、审批人工履约；DOMAIN含M12审批表|只做八模块；删除资源申请/审批/履约/核验开发，M12不作为新系统活动表。历史归档保留在受控离线存档，不恢复UI/API/Worker。|
|OV-02|PERMISSIONS含templates/tasks/tags/reports等独立菜单|动作名保留，菜单分别归launch/launch/assets/monitor；launch-stats归launch并叠加reports.read。以menu-action-map.json为准。|
|OV-03|API_SEMANTICS要求产品菜单读取business-agents，旧产品/总代路由已移除|产品与总代候选通过新reference-catalogs接口按channels.read和数据范围读取，不需要products菜单；户商候选按accounts.read。禁止复活旧完整管理接口。|
|OV-04|DOMAIN的M04有完整clients/products/packages/vendors实体|只迁移被账户、渠道、历史引用所需的最小资料与关联；业务新表可用reference_records/reference_product_agents，旧ID映射稳定。历史包绑定产品关系保留为只读约束，不能让新系统调用旧包CRUD。|
|OV-05|原字段有account_id最多64位，导入项最多32位|不是全局缩短ID；64位为已同步账户ID存储约束，32位是该导入入口的更严格输入规则。必须对两个入口分别验收。|
|OV-06|旧文档“原型上下布局”与紧凑版双列、六列素材|舒适版优先：投放六主区上下单列，素材桌面四列，宽表内部滚动。不能为了不滚动压缩或隐藏信息。|
|OV-07|AdsPower仅监测的早期名字可能被解读为删除写适配|保留原自动化投放的双通道能力，属于执行基础设施；监测页只提供状态/绑定/能力/恢复入口。所有写必须通过同一命令服务和独立动作门禁，未验证默认关闭。|
|OV-08|旧规则固定候选动作、旧前端桥接可执行|规则无预设执行动作，命中自动AI分析后人工确认。隐藏iframe/DOM桥仅是视觉与交互参考，不是生产框架。|
|OV-09|原合同“主数据无status/被引用不能删”与新引用目录启停|新目录availability仅表示是否允许新增引用，不能覆盖旧产品原始字段或历史快照。失效保留历史名称，已存在关联可读；新写必须重新复验。无硬删除端点。|
|OV-10|原openapi可能保留旧共享schema、旧Cookie名称adpilot_session|活动路径以openapi-current为准；旧共享schema作为依赖保留不代表开放功能。Cookie名称是内部兼容字段，保留不等于用户可见品牌；若更名须单独迁移会话，不能未经记录改合同。|
|OV-11|原型生产能力未实现|本PRD描述待实现目标，不能以按钮回显、模拟状态或静态检查替代真实API/权限/核验验收。|

## 新引用目录：精确业务语义

这是为保留必填关联而补全的实施合同。数据位于系统管理→字典与引用资料，提供下载模板、导入预检、差异与错误展示、提交结果；不增加产品、总代或户商一级页面，不引入完整费率/联系人/CRM等编辑业务。

### 数据与关联

- ReferenceInput包括kind、id、name、availability、owner_team_id、data_owner_user_ids、source_key；PRODUCT额外allowed_agent_ids。id是租户内稳定引用UUID，现有资料必须沿用原ID，不能重建导致渠道断链；同租户(kind,source_key)唯一且不能改绑不同id。
- 每个记录一个owner_team_id，1—500名同团队启用拥有者；普通用户不能扩展集合。跨租户ID不得被用于覆盖现有资料；导入上下文tenant由服务端确定。
- 产品allowed_agent_ids引用同租户、同目标团队、对产品拥有者可用的BUSINESS_AGENT；先导入总代再导入产品。候选读取及保存渠道时都检查product-agent关联，不能只靠前端过滤。
- 新记录由管理员提供经预检的UUID与来源键，服务端校验格式、冲突和租户归属。禁止以名称匹配替换引用。已有记录改名只更新当前目录，不改历史计划、事实、渠道提交快照。
- availability=UNAVAILABLE后不得在新渠道、新导入、新计划或待提交执行中新增使用；已保存对象继续显示原关联，不自动清空。对历史绑定渠道产品变更仍拒绝。

### 查询与数据权限

GET /api/v1/reference-catalogs/{kind}只返回调用者当前可读的资料。PRODUCT/BUSINESS_AGENT需要channels菜单+channels.read，VENDOR需要accounts菜单+accounts.read；system菜单+system.dictionaries.manage可进入维护查询。这三条是替代授权分支，但均必须叠加会话、tenant和数据范围，不允许靠维护权限跨越未授予范围。

BUSINESS_AGENT查询必须带product_id，返回该产品关联且可读的总代；缺失422，无权product_id返回404。owner_user_id可选，只能指定调用者有权管理且与目标写任务同团队的拥有者，返回调用者和目标拥有者可见范围交集；普通用户传他人403。失效资料可返回availability用于历史解释，表单禁选；不因名称已知而允许不可见记录出现在候选中。

页大小20/50/100/200；cursor绑定kind、product_id、owner_user_id、scope_version、catalog_revision。目录/权限版本变化拒绝旧游标409 CATALOG_CHANGED或SCOPE_CHANGED，并让前端重新查询。无权限对象不返回名称、来源或导入者。

### 导入与并发

POST /reference-catalog-imports需system+system.dictionaries.manage与CSRF、Idempotency-Key。一次1—500项且kind一致，name/source_key/reason等NFC与文本规则沿用API_SEMANTICS。body最大2MiB是本补全接口的实施保护值，与原账户导入上限不同。item.id/source_key重复、owner无效、总代关联非法均REJECTED，不修改目录。

合法预览201返回VALIDATED、id、revision、base_catalog_revision、expires_at、issues=[]、预计新增/更新数量；业务预检发现行错误也返回201及REJECTED和issues用于展示。JSON结构错误400，权限错误403/404，总量或正文上限422/413，不创建预览。过期时间15分钟为本补全方案默认；不能把预览当已提交成功。

GET /reference-catalog-imports/{id}仅维护权限且同可见租户/团队范围，返回同结构。POST /{id}/commit不带新业务payload，必须If-Match预览版本、Idempotency-Key、CSRF。重新验证当前权限、全部引用、原目录版本、未过期和state=VALIDATED；冲突409、过期410、引用已失效422。成功在同一事务更新全部目录记录、各record.revision、catalog_revision与审计/outbox，预览COMMITTED、revision+1；任一错误整批无写入。禁止自动把未出现在导入中的资料置失效。

同键同payload重放按全局幂等语义返回原响应；并发提交不同预览仅基于当前目录版本的一次成功。一次成功后新键重提同预览409 INVALID_TRANSITION；同幂等键仍返回原结果。审核操作者、来源、原因、变更前后hash和目录版本写入审计，不额外恢复被删的资源审批流程。

迁移表建议：reference_records、reference_product_agents、reference_catalog_versions、reference_imports、reference_import_items；全部有tenant、scope约束和必要revision。导入本身不发起任何外部广告操作。

## 开发门禁

必须对上述覆盖关系编写契约/权限测试，尤其新目录不依赖旧products菜单。旧文档保留的审批表、撤销申请等场景不进入当前验收矩阵。不得扫描旧材料关键词后自动新增需求。
