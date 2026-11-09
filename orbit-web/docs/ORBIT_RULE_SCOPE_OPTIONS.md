# 规则范围操作者/户商远程候选前端

## 精确来源合同

SDK `rule-scope-options.ts`只读GET `/api/v1/rules/editor-scope-options`。kind OPERATOR/VENDOR；action CREATE/UPDATE；CREATE省略rule_id、UPDATE必需；目标owner_user_id/owner_team_id必需（无team_id别名）。q是候选真实label字面前缀/完整UUID精确，不是账户搜索q；trim/NFC后最多100码点，空串合法而非空全空白拒绝。page_size20/50/100/200、默认50与不透明cursor。

Page4：items/next_cursor/data_as_of/scope_version；每页至多实际size/200，重复ID、错字段、坏UTC、非安全版本均拒绝整页，不凑假空。Operator5保留business UUID、真实name/team_id/team_name与active boolean；Vendor4保留真实name、alias string|null及availability。alias null显示“未设置代称”，真实资料名称单独标明；不从name截断/回填alias。停用操作者/UNAVAILABLE户商仍能供历史过滤，不授新分配/新绑定权。

传输复用现认证/取消/epoch规则，GET no-store，无写CAS/key/body，不借accounts.read/system.users/字典动作。15秒/2MiB客户端读取预算不冒称后台容量标准。参数在发出前冻结（包括kind/page_size），调用方后改对象不能改变迟到响应解析类型。服务器错误code/path原样显现，网络只读错误可手动重试，不自动请求/伪造成写入未知。

## Selector最小接线

`RuleScopeSelector`新增可选`remoteOptions`（默认false，保留原父受控Option[]）；实际RuleEditor显式true。打开真实范围弹窗时，两kind分别读取，不修改任何原Scope5/Member3/RuleWrite字段。每kind独立搜索、size、cursor/history、loading/error/asof与请求epoch；前后页是实际keyset，不能把首20/50项当全量。

候选不随其它账户五filters收缩，搜索只传本候选q。选择后通过原operator_user_id/vendor_id传给账户查询/最终FILTER冻结；不改变scope原5filter或偷偷把用户切成新owner。显式重查或改候选分页保留已实际选择的ID/标签；缓存只保留当前页与那个已选项，避免全页无限累积。每次新选择必须确实来自当前已知候选，未知UUID事件不会变成filter，UI没有自由UUID写入框。

403/401或409授权/来源漂移清两类候选、旧filter值、旧账户选择/快照，并阻新freeze，要求明确重新验证；未确认写入意图仍原样保留。改owner/action/rule/currenthead/认证上下文取消两类读取、清游标/旧标签；迟到旧响应不能混入新上下文。关闭/卸载中断读取。

**503仅候选读取失败，不给后台freeze额外资格门禁。** 保留实际已选ID/已知label和已验证scope；原freeze/应用仍按既有合同。失败该下拉禁止新增选择、清晰显示错误与重试，不伪空候选、也不把既有scope当不存在。最终scope写入由后端原5filter与完整当前双方范围重新验证，候选成功不是冻结授权证明。

## 受控验证范围

本轮SDK、Selector/Editor专属挂载及类型/格式由主线窗口前定向验证。SDK fetch替身、组件候选SDK替身不计真实MySQL/HTTP/浏览器。B后端合同已冻结，但源Store/route真实专项与实际两下拉操作需主线串行执行；原审计文档所列两个disabled缺口只有真实来源+浏览器对账后才能考虑关闭，不能因为组件测试存在就勾五filter完整验收。

没有修改原全局router/layout/menu、后台共享文件或真实凭据；没有调用DB、Meta/广告平台。百万目录/自然执行计划与所有参考数据状态不是本轮前端小样本容量验收。

最终定向SDK13 + Selector42（保留原32、增加10）+ Editor24 = 79/79 PASS（22.10秒），vue-tsc PASS。日志与JUnit：`.runtime/rule-scope-options-vitest.log`、`rule-scope-options-junit.xml`；类型：`rule-scope-options-type.log`。新增接线尚不继承后端HTTP或浏览器成功，待主线真实来源两下拉/最终五filter逐项对账后再决定覆盖状态。

## 畸形撤权正文补充与当前冻结

后续交叉审查发现：已收到401/403/409的HTML、截断JSON、非法UTF8或超过正文预算时，不能把实际HTTP状态降为502而保留旧授权数据。现SDK保留这三种已知状态并仅给固定安全INVALID_RESPONSE文案；200坏正文仍502，无response网络仍status0。SDK17+Selector45+Editor24=86/86 PASS（24.12秒），包括真实SDK解析Response→Selector清敏感及保留在途pending的3组；fetch仍受控替身，不冒充真实网关撤权。日志/JUnit/type为`.runtime/rule-scope-options-revocation-*`。此前79是原固定源码结果，不覆盖或改写。

## 主线内置浏览器最小执行流程（尚未执行）

1. 主线隔离fixture须保留真实规则编辑动作、目标owner，以及23个真实业务操作者和23个户商所对应的双主体可读账户。SQL账户/历史状态只证明本地业务协议，不证明Meta授权；不要给浏览器拼造返回值。原后端工具会在末尾恢复动作权限，但没有返回浏览器fixture元数据，需主线明确保留marker/target并与实际响应对账。
2. 从原规则菜单→创建或已有可编辑规则→“选择规则账户范围”Dialog，检查`规则账户操作者`与`规则账户户商`真实ElSelect已可选。监听严格已知/dev-api前缀后的`/api/v1/rules/editor-scope-options`，两请求owner_user_id/owner_team_id与当前编辑归属一致，无其它模块请求。
3. 用`操作者候选搜索`/`户商候选搜索`输入fixture marker，各自“查询操作者候选”/“查询户商候选”；各自每页条数设20，第一响应20+next_cursor，点“下一页操作者候选”/“下一页户商候选”第二响应3+null。按响应ID对账23唯一业务UUID；回上页和50/100/200查全23，不能凭DOM渲染数推全量。另一kind q/size不应跟着改动。
4. 展开真实选择框，实际点击可见option label，不点击ElementPlus隐藏input。停用项显示历史提示，UNAVAILABLE仍能作历史filter；alias=null显示“未设置代称”，资料name单列而非当alias。遇同名按完整UUID区分。搜索`%_!`字面前缀与完整业务UUID精确例，核返回ID而非只见文字。
5. 选真实operator/vendor并填写其余账户q、状态、授权状态，共原五filters。点“查询账户”，核原editor-accounts请求五值与界面一致；先用状态/授权UNKNOWN符合技术账户，再切匹配条件核真空，不将UNKNOWN说平台正常。原FILTER模式点“全选过滤结果”再冻结，POST selection.filters完整五键、account_ids=[]；不能把可见页ID拼成全量。核Scope5真实count/hash与members，再“应用真实范围”，最终RuleWrite使用该真实snapshot UUID。
6. 换owner/head/action后，旧候选/已选filter/游标清除，旧回包不出现；撤权401/403清敏感且不得新POST，503显示来源失败而不伪空或抹既有已验证scope。未知写保留原body/key/CAS，关闭/恢复不得自动重发。自然撤权/网络中断需实际具备受控方法才执行，未具备列NOT_RUN。
7. 1440/768/390三视口分别核两下拉、远程分页区、原账户表/横向滚动与Dialog焦点/关闭。真实命名和资源来源按fixture标注，不把本步骤文档存在算浏览器通过。

## 后端只读交审限定

当前Store用LABEL_SQL的orbit_business_user.id（非sys_user.user_id），账户EXISTS同时caller与owner visibility；VENDOR再叠两者reference_owner/显式管理团队交集。route显式独占READ COMMITTED，Store拒非真实AsyncConnection RC；顺序\_begin当前动作/归属→reference clock→directory clock→account clock→有界候选→_finish当前Rule/双方授权。cursor绑定session、双fingerprint、原Rule head、kind/q/size/目标与三clock。未发现新的确定实现阻断。

原8组工具有真实CREATE、23候选四档、历史状态、双scope、ref撤回、三clock/session/kind/q/size游标与当前动作撤权；UPDATE仅未知Rule404，没有实际存量Rule首末head漂移或旧UPDATE cursor随revision变化的真实并发负例。RC连接/clock与源代码相符，但单独连接池归还隔离、并发alias/ref撤回/管理撤回在本新增8组未直接观测；不要以静态审核替代这些验收。主线报告原62+新增8=70/70真实通过（22.47秒），该数字只作主线回报记录，本代理未自行运行DB。
