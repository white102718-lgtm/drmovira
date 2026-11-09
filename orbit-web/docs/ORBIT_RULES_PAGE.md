# 智能规则父页面接线

`src/views/orbit/rules/index.vue`保留若依既有布局，由主线菜单062指向该组件，不修改全局router。原规则路径下无mode为列表；`?mode=create`为创建二级页，`?mode=edit&rule_id=<UUID>`为编辑二级页。重复/数组mode、非法或缺ID、CREATE携rule_id都明确拒绝，不制造默认UUID。

## 当前权限与认证

真实`useUserStore`当前permissions决定原rules.read/create/edit动作。编辑直达不强制read，CREATE-only用父入口，其余创建沿RuleList已获授权的真实capabilities流程；Editor自身再次读取当前专属Context。父不默认任何owner/profile/count/date。

传给子组件的是公开用户ID与本地随机生命周期nonce；实际token/CSRF不进入路由、context或存储。user.id变化、token空与非空切换、权限清空退出状态更换nonce；同actor非空token刷新、普通权限列表变化不换nonce，允许原业务意图手动用当前传输认证确认。服务端和SDK继续当前授权/迟到校验。

## 列表与范围意图

List在相同actor生命周期内常驻，二级页仅隐藏，保留原筛选与未提交输入。新增最小List.refresh接口：保存返回时将cursor/history回首屏（写入已改变clock），保留appliedQuery及未提交输入，显式重新读取。它不通过改变filters触发search。进入创建/编辑前List在真实capability返回且当前无busy/pending时关闭teleport详情Drawer，避免只隐藏列表却留下遮挡；原Rule先clone保存为入口事实。

父仅在内存保存Editor的SAVE或SCOPE原pending并回传，原mode/rule/actor生命周期绑定。关闭回列表仍保留；有未确认意图时列表inert与事件捕获阻止新写，不能另开新Editor，提供明确恢复原请求入口。跨actor隐藏原Editor/业务正文，仅泛化提示，不重发。没有父组件全卸载/页面重载的持久恢复承诺；不将敏感正文塞入localStorage。

保存成功回到列表并显式refresh；失败或未知不自动刷新、不当作成功。Editor和Selector负责保留原body/key/CAS，仅当前CSRF可在明确手动恢复时更新。

## 尚未完成

RuleList内原RuleRun分页不等于全局触发记录。原`/rule-hits`仍缺独立真实接线；后5次预览已通过Form槽接真实专属只读接口，不使用空记录或客户端猜测替代。正向Simulation/ENABLE/定时运行来源也沿后端依赖状态，本父页不发行假资格。

父页挂载测试用真实VueRouter/ElementPlus、受控用户store，List/Editor为协议替身；List.refresh另用原真实List+SDK替身测查询保留。它们不是HTTP/后端授权/浏览器验收，主线另接真实三视口。

本轮父页17项协议挂载与原List20项（新增1项refresh）定向核对；完整真实HTTP与浏览器仍由主线串行验证，不能以这些替身测试标整页验收。

## 规则动作ACTION未确认意图

父页专属ACTION envelope与Editor SAVE/SCOPE分离，List在真实发送时上交冻结原业务body/key/CAS，父将其回传到跨:key重建的List。跨认证生命周期只隐藏内容并阻新写，不向不同actor重放；普通非空token刷新不换原actor生命周期。未知后新403/409不清先前未知，只有实际原成功回执清父。

onBeforeRouteLeave对当前未确认意图阻SPA离开，并有可见原因；原请求确认清父后恢复导航。没有本地Storage或新查询端点，不承诺硬刷新/浏览器重启恢复。父ACTION不会把整个List inert导致原确认不可用；Editor未知仍禁用List操作。原原因Dialog未发送不生成父pending。定向父测试使用真实RouterView以注册实际matched-record guard，不仅检查组件函数存在。

### 本轮剩余已确认认证边界

当前父页leave guard会先于全局认证导航执行；未确认意图时无条件阻离仍会阻止SPA前往登录。主线已知该确证缺口，后续需规则专属内存holder与受控认证路由恢复方案，不是已完成再认证恢复。本阶段不能把“业务页阻离”推广为完整401再登录闭环。硬刷新不持久化仍保持明确边界。当前源待主线裁决后窄修，不把90定向通过当该边界通过。

## 当前同主体恢复接线

原业务正文、幂等键及版本不变；首次写前实际读取原六动作恢复身份，手动恢复须再次同actor/tenant核验。新标签页登录和父页只读身份复核不自动发送写请求。完整约束与实际测试见 [ORBIT_RULE_RECOVERY.md](ORBIT_RULE_RECOVERY.md)。此节点仍需主线真实HTTP/浏览器验收，不继承旧UI证据。
