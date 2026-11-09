# 渠道原页面、字段与弹窗逐项审计

本文件是只读核对及待验候选，不修改总台账，不把源码存在记为DONE。依据原PRD FR-CHN-01—03、补充章节372—377行、原OpenAPI ChannelWrite/Channel/ChannelPage/SharedOwnership/OwnershipAssignment及progress.json实际稳定ID。

## 页面与弹窗

|稳定ID|现有落点与实际证据|明确差距/下一验证|
|---|---|---|
|CHN-01 / API-listChannel|channels/index.vue主列表：搜索、产品、状态、20/50/100/200分页、字段与动作；原B已有分页水位及三视口闭环|请求乱序取消、完整组合和真实容量未验；新6组HTTP仅拟核基础筛选，不代替容量|
|CHN-02 / API-createChannel / API-updateChannel|新增/编辑弹窗，产品清空总代、按当前product候选；默认APP；历史锁定产品在编辑表单解释|Unicode输入框maxlength按UTF16限制，100emoji原schema正例无法完整从UI输入；500拥有者交互边界未验；显式disabled与父form禁用覆盖须专项复现|
|CHN-03 / API-getChannel|详情drawer有全部业务字段、对象版本、创建/更新UTC，名称空值回退code|openDetail只GET渠道，未取edit-context；详情没有历史绑定只读关系解释。列表旧labels可能在详情并发变更后过时，来源/引用版本完整追溯未展示|
|CHN-04 / API-assignChannelOwners|专用分配弹窗、reason、CAS/assign独立授权；B32已含USER本人/TEAM显式团队、混合拥有者原子拒绝|有效500人正例、超200候选多次加载选择及大量名称回显未验；不把同团队peer权限扩给USER|
|CHN-05 / API-archiveChannel|专用停用确认弹窗，原因、版本、保留历史；B32含撤权及成功键重放|未发送任务停用后阻断、已有投放落地页不覆盖、未知渠道统计单列依赖投放/统计，不能在本模块勾选|
|CHN-06|HTTPS公网地址/参数/长度及原链接保留，有真实HTTP|URL2048码点与所有追踪字符组合新工具待跑；前端未知结果期间取消关闭允许丢弃本次重试意图，完整恢复仍有缺口|
|CHN-07 / CHN-08|PRODUCT/AGENT走channels.read、VENDOR走accounts.read/维护交集；product限定、失效新引用拒绝、目录游标水位|全候选权限/分页/500拥有者/竞态组合仍未穷尽；不能从别名单独接口通过推导账户全部代称验收|
|CHN-09|product_locked后端拒改、编辑UI解释新建；最小引用目录不恢复删除菜单|真实历史旧包约束迁移与任务快照对账尚无完整证据；详情锁定解释缺失如CHN-03|
|FR-CHN-01/02/03|上述最小闭环已实现且多个真实专项通过|保留IN_PROGRESS，以上跨模块/字段/异常/容量差距未消除|

## 原字段逐项与稳定ID候选

|字段/机器ID|原边界及当前实现|本次独立真实HTTP拟核|仍不覆盖|
|---|---|---|---|
|FIELD-B-渠道.code；SCHEMA-ChannelWrite.code / Channel.code|1—64，ASCII字母数字下划线短横线，同租户唯一|64正例，空/65/中文/空格/控制符拒绝，原响应pattern|全部前端字符组合及任务命名依赖|
|FIELD-B-渠道.name；SCHEMA-ChannelWrite.name / Channel.name|0—100 Unicode码点，NFC；空值展示回退code|空、100emoji、100个分解音符规范化，101emoji/控制符拒绝|UI100emoji被maxlength限制，跨模块回退未验|
|FIELD-B-渠道.product_id；SCHEMA-ChannelWrite.product_id / Channel.product_id|UUID、真实最小产品、当前归属交集|UUID字段类型/格式、原返回UUID；已有跨租户/外域专项|全部失效/历史迁移组合|
|FIELD-B-渠道.agent_id；SCHEMA-ChannelWrite.agent_id / Channel.agent_id|UUID、选中产品允许集合、拥有者交集|UUID格式与原响应；已有产品总代解除后重启用拒绝|快速切产品的迟到响应UI竞态|
|FIELD-B-渠道.type；SCHEMA-ChannelWrite.type / Channel.type|APP/WEBSITE/OTHER，默认APP|与media/status全24组合及未知枚举拒绝|真实其他媒体连接器能力不等于枚举可保存|
|FIELD-B-渠道.media；SCHEMA-ChannelWrite.media / Channel.media|META/GOOGLE/TIKTOK/OTHER|同上；原响应禁止额外字段|没有真实平台投放写入证据|
|FIELD-B-渠道.url；SCHEMA-ChannelWrite.url / Channel.url|1—2048，HTTPS、无凭据、参数编码合法，不自动改计划落地页|2048正例、2049/http/内网/凭据/坏百分号拒绝|任务落地页不覆盖由对应模块验；URL允许性不代表网络可达|
|FIELD-B-渠道.status；SCHEMA-ChannelWrite.status / Channel.status|ENABLED/DISABLED；停用不删除历史|枚举全组合、非法值及bool类型拒绝、生命周期原schema|待发送任务阻断与统计未知渠道|
|SCHEMA-SharedOwnership.owner_team_id / data_owner_user_ids；ChannelWrite.ownership / Channel.ownership|团队UUID，1—500字符串UUID、无重复；功能/数据权限交集|结构、空/501/重复/非字符串拒绝，原嵌套闭合schema|500个不同有效拥有者正例及UI容量；SharedOwnership是跨模块，不能本线全部结清|
|SCHEMA-OwnershipAssignment.reason|必填1—1000，NFC码点/无控制符|1000正例，空/空白/1001/控制符拒绝|全前端原因边界及其他模块共享合同|
|SCHEMA-Channel.id / revision / created_at / updated_at|业务UUID、正整数安全上限、ISO带时区|create/get/edit/owners/archive每次都按原Channel全部required/additionalProperties/类型/格式校验|已有id/revision字段回填由主线管理；日期语义/时钟容量不从schema格式通过推导|
|SCHEMA-ChannelPage.items / next_cursor / data_as_of / scope_version|闭合原schema，最多200、游标nullable、时区水位、安全版本|所有page_size与筛选返回严格schema|大数据分布、EXPLAIN、P95与高并发不是这6组检查的目标|

PARAM-listChannel.query.q/page_size/status/date_from/date_to、ChannelWrite所有required、OwnershipAssignment字段等是候选映射，必须等独立工具实际通过后再由主线逐项决定，不在这里标DONE。X-Target-Tenant正向跨租户合同仍未实现，只拒绝客户端伪造不能称全部header合同完成。

## 新独立工具与证据边界

`tools/channel_field_contract_checks.py`直接读取原`contracts/openapi-current.json`，针对本次渠道schema树实际关键字验证required/additionalProperties/类型/嵌套引用/边界/格式/enum/anyOf；未知schema约束直接失败，不静默忽略，不声称通用完整JSON Schema引擎。未引入依赖或修改生产校验。六固定组入口：`run_channel_field_contract_checks(client, admin, headers, reference_fixture, cases, contract_path=None)`，reference_fixture复用原B工具返回的product_id/agent_id（当前恢复AVAILABLE）。

六组覆盖：全生命周期严格原响应；字段正边界；24枚举组合；原字段和所有必填负例无部分写入；拥有者/原因边界；literal包含搜索、产品/状态/UTC日期及四page_size。拒绝写请求比较现有九张目录/渠道/关系/时钟/预览/event/idem完整小夹具快照，检测同数量内容变更。10个校验器纯测试与Ruff已通过，真实HTTP尚未运行。没有改冻结的前后端产品/原工具/浏览器spec，没有自行启动共享服务。

## 后续授权解冻修正节点（源码已修，待新三视口）

前述审计指出的四项缺口已在主线明确解冻index.vue后接力修正：详情现在读取真实edit-context及当前labels，显示历史绑定/引用状态；名称以NFC码点100校验而不被UTF16 maxlength截断；显式disabled叠加saving/未知意图/版本冲突；新增编辑及分配停用的未知结果禁止取消/ESC/关闭，原键和正文冻结，409重新读取后新版本/新键，重读失败仍禁止旧CAS提交。

7项真实ElementPlus挂载测试已通过（100与101emoji、未锁定产品仍冻结、编辑/分配/停用原键恢复、历史锁定详情、CAS冲突及当前对象读失败），vue-tsc与专属Prettier通过。浏览器spec已补真实详情绑定/引用状态与101拒绝→100emoji保存断言，旧闭环断言保留；此新版三视口仍待主线排队。实际带product_locked=true的历史资料在浏览器中的独立阅读仍可增加夹具验证，不能仅以挂载测试当真实历史迁移验收。全模块和前述跨模块/500拥有者/容量项仍未结清。
