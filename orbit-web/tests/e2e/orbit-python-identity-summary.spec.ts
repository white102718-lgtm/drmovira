import { expect, test, type Request } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'

type Resource = {
  external_id: string
  name: string
  kind: 'PAGE' | 'PIXEL' | 'APPLICATION'
  usable: boolean
  reason_code: string | null
}
type Fixture = {
  account_id: string
  external_id: string
  expected_summary: {
    identity_status: 'SYNCED'
    identity_count: number
    identity_observed_at: string
  }
  expected: {
    account_id: string
    resources: Resource[]
    capability_version: string
    observed_at: string
  }
}

/** 仅去掉本项目明确的开发代理前缀，随后按同一账户完整路径严格相等。 */
const apiPath = (value: URL) =>
  value.pathname.startsWith('/dev-api/') ? value.pathname.slice('/dev-api'.length) : value.pathname

/** 主线055真实SQL摘要及原身份发布夹具；无route.fulfill、无HTTP写后门、不授Meta执行权。 */
test('Python身份摘要与原18列和Drawer真实身份读取逐项一致', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  const raw = process.env.ORBIT_E2E_IDENTITY_SUMMARY_FIXTURE
  expect(raw, '需要主线本轮055有效身份摘要fixture').toBeTruthy()
  const fixture = JSON.parse(raw!) as Fixture
  expect(fixture.expected.account_id).toBe(fixture.account_id)
  expect(fixture.expected.resources).toHaveLength(3)
  expect(fixture.expected.resources.some((row) => row.usable)).toBe(true)
  expect(fixture.expected.resources.some((row) => !row.usable)).toBe(true)
  const writes: string[] = []
  const platformRequests: string[] = []
  const observe = (request: Request) => {
    const url = new URL(request.url())
    const current = apiPath(url)
    if (current.startsWith('/api/v1/accounts') && request.method() !== 'GET')
      writes.push(`${request.method()}:${current}`)
    if (
      ['facebook.com', 'facebook.net', 'fb.com', 'fbcdn.net', 'meta.com'].some(
        (host) => url.hostname === host || url.hostname.endsWith(`.${host}`),
      )
    )
      platformRequests.push(url.hostname)
  }
  page.on('request', observe)
  try {
    const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
    await page.goto('/login')
    await captcha
    await page.getByPlaceholder('账号', { exact: true }).fill('admin')
    await page
      .getByPlaceholder('密码', { exact: true })
      .fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
    await page.getByRole('button', { name: '登 录', exact: true }).click()
    await expect(page).toHaveURL(/\/index$/)
    await expect(page.locator('.sidebar-container .el-menu[role="menubar"]').first()).toBeAttached()
    await expect(
      page.locator('.sidebar-container').getByText('ORBIT工作台', { exact: true }),
    ).toBeAttached()
    await page.goto('/orbit/accounts')
    await expect(page.locator('.account-page h2')).toHaveText('广告账户')
    const search = page.getByPlaceholder('名称前缀或完整数字ID')
    const listResponse = page.waitForResponse(
      (response) =>
        apiPath(new URL(response.url())) === '/api/v1/accounts/extended' &&
        new URL(response.url()).searchParams.get('q') === fixture.external_id &&
        response.request().method() === 'GET',
    )
    await search.fill(fixture.external_id)
    await search.press('Enter')
    const list = await listResponse
    expect(list.status()).toBe(200)
    const listed = (await list.json()).items.filter(
      (item: { account: { id: string } }) => item.account.id === fixture.account_id,
    )
    expect(listed).toHaveLength(1)
    for (const [field, value] of Object.entries(fixture.expected_summary))
      expect(listed[0].details[field]).toBe(value)
    const table = page.locator('.account-page .account-table')
    const row = table.locator('tbody tr').filter({ hasText: fixture.external_id })
    await expect(row).toHaveCount(1)
    await expect(table.locator('thead th')).toHaveCount(18)
    const originalRow = await row.innerText()
    const details = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        apiPath(url) === `/api/v1/accounts/${fixture.account_id}/details` &&
        response.request().method() === 'GET'
      )
    })
    await row.getByRole('button', { name: '详情', exact: true }).click()
    const detailResponse = await details
    expect(detailResponse.status()).toBe(200)
    const detail = await detailResponse.json()
    for (const [field, value] of Object.entries(fixture.expected_summary))
      expect(detail.details[field]).toBe(value)
    const drawer = page.getByRole('dialog', { name: '广告账户详情', exact: true })
    await expect(drawer).toContainText('有权查看资源不代表具备创建投放权限')
    await expect(drawer).toContainText('尚未读取身份资源')
    const summary = drawer.locator('.account-identity-summary')
    await expect(summary.locator('tr').filter({ hasText: '身份同步状态' })).toHaveText(
      '身份同步状态已同步',
    )
    await expect(summary.locator('tr').filter({ hasText: '身份资源数量' })).toHaveText(
      `身份资源数量${fixture.expected_summary.identity_count}`,
    )
    const summaryTime = await page.evaluate(
      (value) => new Date(value).toLocaleString('zh-CN'),
      fixture.expected_summary.identity_observed_at,
    )
    await expect(summary.locator('tr').filter({ hasText: '身份摘要观测时间' })).toHaveText(
      `身份摘要观测时间${summaryTime}（本地时间）`,
    )
    const read = drawer.getByRole('button', { name: '读取身份资源', exact: true })
    const expectedPath = `/api/v1/accounts/${fixture.account_id}/identities`
    async function requestCurrent() {
      const response = page.waitForResponse(
        (item) =>
          apiPath(new URL(item.url())) === expectedPath && item.request().method() === 'GET',
      )
      await read.click()
      const actual = await response
      expect(actual.status()).toBe(200)
      expect(await actual.json()).toEqual(fixture.expected)
      await expect(read).toBeEnabled()
    }
    await requestCurrent()
    await expect(drawer).toContainText(`能力版本：${fixture.expected.capability_version}`)
    const observed = await page.evaluate(
      (value) => new Date(value).toLocaleString('zh-CN'),
      fixture.expected.observed_at,
    )
    await expect(drawer).toContainText(`观测时间：${observed}（本地时间）`)
    await expect(drawer).not.toContainText('尚未同步身份资源')
    const resources = drawer.locator('.el-table').last()
    const resourceRows = resources.locator('.el-table__body-wrapper tbody tr')
    await expect(resourceRows).toHaveCount(fixture.expected.resources.length)
    for (const [index, expected] of fixture.expected.resources.entries()) {
      const cells = resourceRows.nth(index).locator('td .cell')
      await expect(cells).toHaveCount(4)
      await expect(cells.nth(0)).toHaveText(expected.kind)
      await expect(cells.nth(1)).toHaveText(expected.name)
      await expect(cells.nth(2)).toHaveText(expected.external_id)
      await expect(cells.nth(3)).toHaveText(
        expected.usable ? '可用' : expected.reason_code || '不可用',
      )
    }
    // 同一真实GET刷新不重发发布/同步命令，也不把旧DTO当新Authority。
    await requestCurrent()
    await expect(resourceRows).toHaveCount(3)
    await resources.scrollIntoViewIfNeeded()
    await expect
      .poll(() =>
        drawer.evaluate((element) => {
          const rect = element.getBoundingClientRect()
          return (
            rect.left >= 0 &&
            rect.right <= innerWidth &&
            rect.top >= 0 &&
            rect.bottom <= innerHeight
          )
        }),
      )
      .toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    )
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `identity-summary-${info.project.name}.png`),
      animations: 'disabled',
    })
    await drawer.locator('button.el-drawer__close-btn').click()
    await expect(drawer).not.toBeVisible()
    await expect.poll(() => row.innerText()).toBe(originalRow)
    expect(writes).toEqual([])
    expect(platformRequests).toEqual([])
  } finally {
    page.off('request', observe)
    await finish()
  }
})
