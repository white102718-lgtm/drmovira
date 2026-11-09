# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: orbit-python-identity-summary.spec.ts >> Python身份摘要与原18列和Drawer真实身份读取逐项一致
- Location: tests\e2e\orbit-python-identity-summary.spec.ts:33:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.sidebar-container').getByText('ORBIT', { exact: true })
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for locator('.sidebar-container').getByText('ORBIT', { exact: true })

```

```yaml
- link:
  - /url: /
  - img
- menubar:
  - link:
    - /url: /index
    - menuitem
  - menuitem
  - menuitem
  - menuitem
  - menuitem
  - link:
    - /url: http://ruoyi.vip
    - menuitem
- img
- navigation "面包屑":
  - link "首页"
- button "超级管理员":
  - img
  - text: 超级管理员
- img
- link "首页":
  - /url: /index
- img
- button:
  - img
- img
- text: 刷新
- heading "若依后台管理框架" [level=2]
- paragraph: 一直想做一款后台管理系统，看了很多优秀的开源项目但是发现没有合适自己的。于是利用空闲休息时间开始自己写一套后台系统。如此有了若依管理系统，她可以用于所有的Web应用程序，如网站管理后台，网站会员中心，CMS，CRM，OA等等，当然，您也可以对她进行深度定制，以做出更强系统。所有前端后台代码封装过后十分精简易上手，出错概率低。同时支持移动客户端访问。系统会陆续更新一些实用功能。
- paragraph: "当前版本: v3.9.2"
- paragraph: ¥免费开源
- paragraph:
  - button "访问码云":
    - img
    - text: 访问码云
  - button "访问主页":
    - img
    - text: 访问主页
- heading "技术选型" [level=2]
- heading "后端技术" [level=4]
- list:
  - listitem: SpringBoot
  - listitem: Spring Security
  - listitem: JWT
  - listitem: MyBatis
  - listitem: Druid
  - listitem: Fastjson
  - listitem: ...
- heading "前端技术" [level=4]
- list:
  - listitem: Vue
  - listitem: Vuex
  - listitem: Element-ui
  - listitem: Axios
  - listitem: Sass
  - listitem: Quill
  - listitem: ...
- separator
- text: 联系信息
- paragraph:
  - text: 官网：
  - link "http://www.ruoyi.vip":
    - /url: http://www.ruoyi.vip
- paragraph:
  - text: QQ群： 满937441 满887144332 满180251782 满104180207 满186866453 满201396349 满101456076 满101539465 满264312783 满167385320 满104748341 满160110482 满170801498 满108482800 满101046199 满136919097 满143961921 满174951577 满161281055 满138988063 满151450850 满224622315 满287842588 满187944233 满228578329 满191164766 满174569686 满127358632
  - link "113071109":
    - /url: http://qm.qq.com/cgi-bin/qm/qr?_wv=1027&k=EQz10zmHf6ga7Zv2U5kWNrpkBlnknJE-&authKey=65C4sdiKSSyJFEtartvUfLEHQiPYoysBoVkNuLP1AxpKdV4nQR%2FEvobGCI9jvDpQ&noverify=0&group_code=113071109
- paragraph:
  - text: 微信：
  - link "/ *若依":
    - /url: javascript:;
- paragraph:
  - text: 支付宝：
  - link "/ *若依":
    - /url: javascript:;
- text: 更新日志
- button "v3.9.2 - 2026-03-26":
  - text: v3.9.2 - 2026-03-26
  - img
- button "v3.9.1 - 2025-12-18":
  - text: v3.9.1 - 2025-12-18
  - img
- button "v3.9.0 - 2025-05-28":
  - text: v3.9.0 - 2025-05-28
  - img
- button "v3.8.9 - 2024-12-30":
  - text: v3.8.9 - 2024-12-30
  - img
- button "v3.8.8 - 2024-06-30":
  - text: v3.8.8 - 2024-06-30
  - img
- button "v3.8.7 - 2023-12-08":
  - text: v3.8.7 - 2023-12-08
  - img
- button "v3.8.6 - 2023-06-30":
  - text: v3.8.6 - 2023-06-30
  - img
- button "v3.8.5 - 2023-01-01":
  - text: v3.8.5 - 2023-01-01
  - img
- button "v3.8.4 - 2022-09-26":
  - text: v3.8.4 - 2022-09-26
  - img
- button "v3.8.3 - 2022-06-27":
  - text: v3.8.3 - 2022-06-27
  - img
- button "v3.8.2 - 2022-04-01":
  - text: v3.8.2 - 2022-04-01
  - img
- button "v3.8.1 - 2022-01-01":
  - text: v3.8.1 - 2022-01-01
  - img
- button "v3.8.0 - 2021-12-01":
  - text: v3.8.0 - 2021-12-01
  - img
- button "v3.7.0 - 2021-09-13":
  - text: v3.7.0 - 2021-09-13
  - img
- button "v3.6.0 - 2021-07-12":
  - text: v3.6.0 - 2021-07-12
  - img
- button "v3.5.0 - 2021-05-25":
  - text: v3.5.0 - 2021-05-25
  - img
- button "v3.4.0 - 2021-02-22":
  - text: v3.4.0 - 2021-02-22
  - img
- button "v3.3.0 - 2020-12-14":
  - text: v3.3.0 - 2020-12-14
  - img
- button "v3.2.1 - 2020-11-18":
  - text: v3.2.1 - 2020-11-18
  - img
- button "v3.2.0 - 2020-10-10":
  - text: v3.2.0 - 2020-10-10
  - img
- button "v3.1.0 - 2020-08-13":
  - text: v3.1.0 - 2020-08-13
  - img
- button "v3.0.0 - 2020-07-20":
  - text: v3.0.0 - 2020-07-20
  - img
- button "v2.3.0 - 2020-06-01":
  - text: v2.3.0 - 2020-06-01
  - img
- button "v2.2.0 - 2020-03-18":
  - text: v2.2.0 - 2020-03-18
  - img
- button "v2.1.0 - 2020-02-24":
  - text: v2.1.0 - 2020-02-24
  - img
- button "v2.0.0 - 2019-12-02":
  - text: v2.0.0 - 2019-12-02
  - img
- button "v1.1.0 - 2019-11-11":
  - text: v1.1.0 - 2019-11-11
  - img
- button "v1.0.0 - 2019-10-08":
  - text: v1.0.0 - 2019-10-08
  - img
- text: 捐赠支持
- img "donate"
- text: 你可以请作者喝杯咖啡表示鼓励
- img
```

# Test source

```ts
  1   | import { expect, test, type Request } from '@playwright/test'
  2   | import path from 'node:path'
  3   | import { observePythonBrowser } from './python-browser-diagnostics'
  4   |
  5   | type Resource = {
  6   |   external_id: string
  7   |   name: string
  8   |   kind: 'PAGE' | 'PIXEL' | 'APPLICATION'
  9   |   usable: boolean
  10  |   reason_code: string | null
  11  | }
  12  | type Fixture = {
  13  |   account_id: string
  14  |   external_id: string
  15  |   expected_summary: {
  16  |     identity_status: 'SYNCED'
  17  |     identity_count: number
  18  |     identity_observed_at: string
  19  |   }
  20  |   expected: {
  21  |     account_id: string
  22  |     resources: Resource[]
  23  |     capability_version: string
  24  |     observed_at: string
  25  |   }
  26  | }
  27  |
  28  | /** 仅去掉本项目明确的开发代理前缀，随后按同一账户完整路径严格相等。 */
  29  | const apiPath = (value: URL) =>
  30  |   value.pathname.startsWith('/dev-api/') ? value.pathname.slice('/dev-api'.length) : value.pathname
  31  |
  32  | /** 主线055真实SQL摘要及原身份发布夹具；无route.fulfill、无HTTP写后门、不授Meta执行权。 */
  33  | test('Python身份摘要与原18列和Drawer真实身份读取逐项一致', async ({ page }, info) => {
  34  |   const finish = observePythonBrowser(page, info)
  35  |   const raw = process.env.ORBIT_E2E_IDENTITY_SUMMARY_FIXTURE
  36  |   expect(raw, '需要主线本轮055有效身份摘要fixture').toBeTruthy()
  37  |   const fixture = JSON.parse(raw!) as Fixture
  38  |   expect(fixture.expected.account_id).toBe(fixture.account_id)
  39  |   expect(fixture.expected.resources).toHaveLength(3)
  40  |   expect(fixture.expected.resources.some((row) => row.usable)).toBe(true)
  41  |   expect(fixture.expected.resources.some((row) => !row.usable)).toBe(true)
  42  |   const writes: string[] = []
  43  |   const platformRequests: string[] = []
  44  |   const observe = (request: Request) => {
  45  |     const url = new URL(request.url())
  46  |     const current = apiPath(url)
  47  |     if (current.startsWith('/api/v1/accounts') && request.method() !== 'GET')
  48  |       writes.push(`${request.method()}:${current}`)
  49  |     if (
  50  |       ['facebook.com', 'facebook.net', 'fb.com', 'fbcdn.net', 'meta.com'].some(
  51  |         (host) => url.hostname === host || url.hostname.endsWith(`.${host}`),
  52  |       )
  53  |     )
  54  |       platformRequests.push(url.hostname)
  55  |   }
  56  |   page.on('request', observe)
  57  |   try {
  58  |     const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  59  |     await page.goto('/login')
  60  |     await captcha
  61  |     await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  62  |     await page
  63  |       .getByPlaceholder('密码', { exact: true })
  64  |       .fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  65  |     await page.getByRole('button', { name: '登 录', exact: true }).click()
  66  |     await expect(page).toHaveURL(/\/index$/)
  67  |     await expect(
  68  |       page.locator('.sidebar-container').getByText('ORBIT', { exact: true }),
> 69  |     ).toBeVisible()
      |       ^ Error: expect(locator).toBeVisible() failed
  70  |     await page.goto('/orbit/accounts')
  71  |     await expect(page.locator('.account-page h2')).toHaveText('广告账户')
  72  |     const search = page.getByPlaceholder('名称前缀或完整数字ID')
  73  |     const listResponse = page.waitForResponse(
  74  |       (response) =>
  75  |         apiPath(new URL(response.url())) === '/api/v1/accounts/extended' &&
  76  |         new URL(response.url()).searchParams.get('q') === fixture.external_id &&
  77  |         response.request().method() === 'GET',
  78  |     )
  79  |     await search.fill(fixture.external_id)
  80  |     await search.press('Enter')
  81  |     const list = await listResponse
  82  |     expect(list.status()).toBe(200)
  83  |     const listed = (await list.json()).items.filter(
  84  |       (item: { account: { id: string } }) => item.account.id === fixture.account_id,
  85  |     )
  86  |     expect(listed).toHaveLength(1)
  87  |     for (const [field, value] of Object.entries(fixture.expected_summary))
  88  |       expect(listed[0].details[field]).toBe(value)
  89  |     const table = page.locator('.account-page .account-table')
  90  |     const row = table.locator('tbody tr').filter({ hasText: fixture.external_id })
  91  |     await expect(row).toHaveCount(1)
  92  |     await expect(table.locator('thead th')).toHaveCount(18)
  93  |     const originalRow = await row.innerText()
  94  |     const details = page.waitForResponse((response) => {
  95  |       const url = new URL(response.url())
  96  |       return (
  97  |         apiPath(url) === `/api/v1/accounts/${fixture.account_id}/details` &&
  98  |         response.request().method() === 'GET'
  99  |       )
  100 |     })
  101 |     await row.getByRole('button', { name: '详情', exact: true }).click()
  102 |     const detailResponse = await details
  103 |     expect(detailResponse.status()).toBe(200)
  104 |     const detail = await detailResponse.json()
  105 |     for (const [field, value] of Object.entries(fixture.expected_summary))
  106 |       expect(detail.details[field]).toBe(value)
  107 |     const drawer = page.getByRole('dialog', { name: '广告账户详情', exact: true })
  108 |     await expect(drawer).toContainText('有权查看资源不代表具备创建投放权限')
  109 |     await expect(drawer).toContainText('尚未读取身份资源')
  110 |     const summary = drawer.locator('.account-identity-summary')
  111 |     await expect(summary.locator('tr').filter({ hasText: '身份同步状态' })).toHaveText(
  112 |       '身份同步状态已同步',
  113 |     )
  114 |     await expect(summary.locator('tr').filter({ hasText: '身份资源数量' })).toHaveText(
  115 |       `身份资源数量${fixture.expected_summary.identity_count}`,
  116 |     )
  117 |     const summaryTime = await page.evaluate(
  118 |       (value) => new Date(value).toLocaleString('zh-CN'),
  119 |       fixture.expected_summary.identity_observed_at,
  120 |     )
  121 |     await expect(summary.locator('tr').filter({ hasText: '身份摘要观测时间' })).toHaveText(
  122 |       `身份摘要观测时间${summaryTime}（本地时间）`,
  123 |     )
  124 |     const read = drawer.getByRole('button', { name: '读取身份资源', exact: true })
  125 |     const expectedPath = `/api/v1/accounts/${fixture.account_id}/identities`
  126 |     async function requestCurrent() {
  127 |       const response = page.waitForResponse(
  128 |         (item) =>
  129 |           apiPath(new URL(item.url())) === expectedPath && item.request().method() === 'GET',
  130 |       )
  131 |       await read.click()
  132 |       const actual = await response
  133 |       expect(actual.status()).toBe(200)
  134 |       expect(await actual.json()).toEqual(fixture.expected)
  135 |       await expect(read).toBeEnabled()
  136 |     }
  137 |     await requestCurrent()
  138 |     await expect(drawer).toContainText(`能力版本：${fixture.expected.capability_version}`)
  139 |     const observed = await page.evaluate(
  140 |       (value) => new Date(value).toLocaleString('zh-CN'),
  141 |       fixture.expected.observed_at,
  142 |     )
  143 |     await expect(drawer).toContainText(`观测时间：${observed}（本地时间）`)
  144 |     await expect(drawer).not.toContainText('尚未同步身份资源')
  145 |     const resources = drawer.locator('.el-table').last()
  146 |     const resourceRows = resources.locator('.el-table__body-wrapper tbody tr')
  147 |     await expect(resourceRows).toHaveCount(fixture.expected.resources.length)
  148 |     for (const [index, expected] of fixture.expected.resources.entries()) {
  149 |       const cells = resourceRows.nth(index).locator('td .cell')
  150 |       await expect(cells).toHaveCount(4)
  151 |       await expect(cells.nth(0)).toHaveText(expected.kind)
  152 |       await expect(cells.nth(1)).toHaveText(expected.name)
  153 |       await expect(cells.nth(2)).toHaveText(expected.external_id)
  154 |       await expect(cells.nth(3)).toHaveText(
  155 |         expected.usable ? '可用' : expected.reason_code || '不可用',
  156 |       )
  157 |     }
  158 |     // 同一真实GET刷新不重发发布/同步命令，也不把旧DTO当新Authority。
  159 |     await requestCurrent()
  160 |     await expect(resourceRows).toHaveCount(3)
  161 |     await resources.scrollIntoViewIfNeeded()
  162 |     await expect
  163 |       .poll(() =>
  164 |         drawer.evaluate((element) => {
  165 |           const rect = element.getBoundingClientRect()
  166 |           return (
  167 |             rect.left >= 0 &&
  168 |             rect.right <= innerWidth &&
  169 |             rect.top >= 0 &&
```
