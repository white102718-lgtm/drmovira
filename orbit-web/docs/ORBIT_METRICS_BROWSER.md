# Metrics独立真实浏览器专项

专属文件为`tests/e2e/orbit-metrics.spec.ts`，三条独立测试，每条由主线在desktop/wide/mobile三个原视口执行，总预期9项。保留原配置的60秒单项、零重试，不修改公共Playwright配置、不自行运行DB/服务/浏览器。主线真实三视口9/9通过（46.15秒），父档19/19、117.29秒含原限流自然冷却；使用独立SQL技术来源，未作生产Meta发行验收。

## 主线注入

登录沿用已有`ORBIT_E2E_FIXTURE_PASSWORD`与隔离admin，不写入磁盘或回复。新增唯一数据环境变量`ORBIT_E2E_METRICS_FIXTURE`为JSON，顶层严格六字段：

```text
{
  version: 1,
  kind: 'SQL_ONLY_NOT_PLATFORM',
  route: '/orbit/monitor/data',
  profile: { id: prepare.profile.id, version: prepare.profile.version },
  query: prepare.query,
  expected: prepare.expected
}
```

`query`为完整原13字段；`expected`来自冻结后端`prepare_metrics_browser_fixture`返回的真实安全集合，包含summary_entity_ids、verified_ad_ids、unknown_ad_id、summary_ad_count22、day_ad_count44、literal_entity_id/name及totals。不得注入控制文件路径、随机登记表、Token或凭据。缺失manifest直接抛固定错误，不skip或拿空库代替。

child配置与SQL样本由主线使用独立后端工具准备。样本是SQL_ONLY_NOT_PLATFORM：21条USD广告两日日事实、EUR完整空和GBP未知单元，不能宣称Meta发行已验证。测试不拦截HTTP、不更改SQL状态、不新增公开写夹具接口，不触发真实广告写入。

## 三条测试

1. **Metrics原七Tab四实体目录选择及公开查询真实集合**：原登录及真实getInfo安全提示，原查询capabilities单CSRF字段（不在断言中输出值），七Tab顺序，真实目录版本选择与范围“全部当前可见账户”；四dataset原13字段POST，完整真实实体ID集合逐一对账，AD跨页不漏项。
2. **Metrics广告22条四档游标历史DAY44及原币种完整totals**：20+2下一页与历史回退、下一页totals不变，50/100/200重新首查22条，DAY44按两个业务日逐日对完整实体集合；totals真实USD5040/EUR0/GBP未知与GBP缺失2，USD注册值NULL，不以页内相加或跨币种换算替代。
3. **Metrics字面通配符两日筛选全部字段详情与无结果恢复**：q=%\_!仅匹配改名实体，但金额包含两日240；只读Drawer逐值核14元字段加完整12指标、所有NULL显示未知，真实关闭；无结果查询独立成功空实体，清q恢复首20与nextcursor，手机详情动画结束后的几何边界及页面宽度。

每次查询严格METHOD+完整path匹配，只移除一次已知/dev-api前缀。断言原Metrics8字段、MetricRow15、MetricValues12、MetricTotal8、金额字符串及分页上限；不读取认证header值到产物。ElementPlus选择点击可见wrapper和option，不点击被遮挡readonly input、不force。手机若原侧栏展开，真实点击drawer-bg右侧并断言hideSidebar/遮罩消失，不改原布局。登录及整页重载分别依据getInfo真实flags处理原安全提示。

业务写请求观察在完成登录后启用，仅原指标POST允许；若出现其他/api/v1写操作即失败。失败诊断复用既有`observePythonBrowser`只采安全path/status/耗时，禁原始trace或请求体落盘。实际HTTP或浏览器失败必须保留，由主线按证据修复，不以延长timeout、删断言或模拟响应通过。

当前`pnpm check:orbit`及专属spec Prettier检查通过；生产前端、公共配置、后端fixture与runner未由本批修改。公开200与三视口已归档至server docs/orbit/evidence/python-metrics-public060-three-viewports.json及对应playwright回执。

指标配置版本可以重名。真实目录选项与已选值显示完整配置 ID，浏览器按 fixture 的真实 profile.id 精确选择，不能以相同版本的第一个选项猜测。首桌面因两个 observed-v001 选项同名失败保留；修复后桌面3/3再到完整三视口9/9均实际通过；首次失败回执保留。
