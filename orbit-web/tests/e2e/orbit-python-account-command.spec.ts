import { expect, test, type Request } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 仅去除本项目明确配置的开发代理前缀；未知前缀不会通过账户路径等值判断。 */
const apiPath = (url: URL) =>
  url.pathname.startsWith('/dev-api/') ? url.pathname.slice('/dev-api'.length) : url.pathname

/** 仅持久受理本地SYNC，不启动Worker；数据/Token由主线隔离夹具准备。 */
test('Python账户原受理回执与本人命令GET刷新真实关联', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  const projectIndex = ['desktop-1440', 'wide-1920', 'mobile-390'].indexOf(info.project.name)
  expect(projectIndex).toBeGreaterThanOrEqual(0)
  const writes: string[] = []
  const platformRequests: string[] = []
  const observe = (request: Request) => {
    const url = new URL(request.url())
    if (
      /^\/api\/v1\/accounts\/[^/]+\/(sync|unbind|assignment)$/.test(apiPath(url)) &&
      ['POST', 'PUT'].includes(request.method())
    )
      writes.push(request.method() + ':' + apiPath(url))
    if (url.hostname.endsWith('facebook.com')) platformRequests.push(url.hostname)
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
    await page.goto('/orbit/accounts')
    const search = page.getByPlaceholder('名称前缀或完整数字ID')
    await search.fill('详情受控-')
    await search.press('Enter')
    const table = page.locator('.account-page .account-table')
    const row = table.locator('tbody tr').nth(projectIndex)
    await expect(row).toContainText('详情受控-')
    const detailsResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/accounts\/[^/]+\/details(?:\?|$)/.test(response.url()) &&
        response.request().method() === 'GET',
    )
    await row.getByRole('button', { name: '详情', exact: true }).click()
    const details = await detailsResponse
    expect(details.status()).toBe(200)
    const original = (await details.json()).account
    const drawer = page.getByRole('dialog', { name: '广告账户详情', exact: true })
    await drawer.locator('button.el-drawer__close-btn').click()
    await expect(drawer).not.toBeVisible()

    const base = `/api/v1/accounts/${original.id}`
    const capabilityResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        apiPath(url) === base + '/actions/capabilities' &&
        url.searchParams.get('action') === 'SYNC' &&
        response.request().method() === 'GET'
      )
    })
    await row.getByRole('button', { name: '更多操作', exact: true }).click()
    await page.getByRole('menuitem', { name: '只读同步', exact: true }).click()
    const capability = await capabilityResponse
    expect(capability.status()).toBe(200)
    const caps = await capability.json()
    const dialog = page.getByRole('dialog', { name: '只读同步账户', exact: true })
    await expect(dialog).toContainText(original.external_id)
    await dialog
      .getByRole('textbox', { name: '账户操作原因', exact: true })
      .fill('隔离浏览器仅受理本地只读命令，不启动执行器')
    const acceptedResponse = page.waitForResponse(
      (response) =>
        apiPath(new URL(response.url())) === base + '/sync' &&
        response.request().method() === 'POST',
    )
    await dialog.getByRole('button', { name: '确认受理只读同步', exact: true }).click()
    const accepted = await acceptedResponse
    expect(accepted.status()).toBe(202)
    expect(accepted.request().postDataJSON()).toEqual({
      reason: '隔离浏览器仅受理本地只读命令，不启动执行器',
    })
    const ack = await accepted.json()
    expect(Object.keys(ack).sort()).toEqual(['id', 'request_id', 'revision', 'state'])
    expect(ack.id).toBe(original.id)
    expect(ack.revision).toBe(caps.revision + 1)
    expect(ack.state).toBe('WAITING_EXECUTOR')
    expect(ack.request_id).toMatch(/^[0-9a-f-]{36}$/i)
    await expect(dialog).toContainText('只读同步已受理，尚未确认执行结果')
    await expect(dialog).toContainText(`账户版本：${ack.revision}`)
    await expect(dialog).toContainText(`请求编号：${ack.request_id}`)

    const section = dialog.getByRole('region', { name: '原受理命令当前状态', exact: true })
    const waitStatus = () =>
      page.waitForResponse((response) => {
        const url = new URL(response.url())
        return (
          apiPath(url) === base + '/actions/status' &&
          url.searchParams.get('kind') === 'SYNC' &&
          url.searchParams.get('request_id') === ack.request_id &&
          response.request().method() === 'GET'
        )
      })
    const firstStatusResponse = waitStatus()
    await section.getByRole('button', { name: '查询当前状态', exact: true }).click()
    const first = await firstStatusResponse
    expect(first.status()).toBe(200)
    expect(first.headers()['cache-control']).toBe('no-store')
    const status = await first.json()
    expect(status.account_id).toBe(original.id)
    expect(status.accepted_request_id).toBe(ack.request_id)
    expect(status.kind).toBe('SYNC')
    expect(status.state).toBe('WAITING_EXECUTOR')
    expect(status.attempt_count).toBe(0)
    expect(status.last_error_code).toBe('ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED')
    expect(status.effective_from).toBeNull()
    expect(status.next_attempt_at).toBeNull()
    expect(status.completed_at).toBeNull()
    for (const field of ['created_at', 'updated_at']) {
      expect(status[field]).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
      expect(new Date(status[field]).toISOString()).toBe(status[field])
      await expect(section.getByText(status[field], { exact: true }).first()).toBeVisible()
    }
    await expect(section.getByText(status.command_id, { exact: true })).toBeVisible()
    await expect(section.getByText(ack.request_id, { exact: true })).toBeVisible()
    await expect(section).toContainText('等待只读执行器（WAITING_EXECUTOR）')
    await expect(section).toContainText('ACCOUNT_SYNC_EXECUTOR_UNCONFIGURED')
    await expect(section.getByText('未提供（null）', { exact: true })).toHaveCount(3)
    const attempts = section.locator('tr').filter({ hasText: '已开始尝试次数' })
    await expect(attempts.getByText('0', { exact: true })).toBeVisible()
    expect(status.command_id).not.toBe(original.id)
    await expect(section.getByRole('button')).toHaveCount(1)

    const refreshedResponse = waitStatus()
    await section.getByRole('button', { name: '刷新当前状态', exact: true }).click()
    const refreshed = await refreshedResponse
    expect(refreshed.status()).toBe(200)
    expect(await refreshed.json()).toEqual(status)
    await expect(dialog).toContainText(`请求编号：${ack.request_id}`)
    await expect(dialog).toContainText(`账户版本：${ack.revision}`)
    expect(writes).toEqual(['POST:' + base + '/sync'])
    expect(platformRequests).toEqual([])
    await expect
      .poll(() =>
        dialog.evaluate((el) => {
          const r = el.getBoundingClientRect()
          return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
        }),
      )
      .toBe(true)
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `account-command-${info.project.name}.png`),
      animations: 'disabled',
    })
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(table.locator('thead th')).toHaveCount(18)
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true)
  } finally {
    page.off('request', observe)
    await finish()
  }
})
