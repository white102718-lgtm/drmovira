import { test, expect, type Locator, type Request } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 使用主线独立SQL消费夹具，不产生真实平台账户或金额，不拦截/模拟网络成功。 */
test('Python账户18列、日期、列设置、详情及身份未就绪的真实页面闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  const actionWrites: string[] = []
  const observeActionWrites = (request: Request) => {
    const match = new URL(request.url()).pathname.match(
      /\/api\/v1\/accounts\/[^/]+\/(assignment|sync|unbind)$/,
    )
    if (match && ['POST', 'PUT'].includes(request.method()))
      actionWrites.push(`${request.method()}:${match[1]}`)
  }
  page.on('request', observeActionWrites)
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
    await expect(page.locator('.account-page h2')).toHaveText('广告账户')
    const search = page.getByPlaceholder('名称前缀或完整数字ID')
    await search.fill('详情受控-')
    await search.press('Enter')
    const table = page.locator('.account-page .account-table')
    await expect(table.locator('tbody tr').first()).toContainText('详情受控-')
    await expect(table.locator('thead th')).toHaveCount(18)
    async function contained(dialog: Locator) {
      await expect
        .poll(() =>
          dialog.evaluate((el) => {
            const r = el.getBoundingClientRect()
            return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
          }),
        )
        .toBe(true)
    }
    await page.getByRole('button', { name: '列设置', exact: true }).click()
    const columns = page.getByRole('dialog', { name: '账户字段显示', exact: true })
    await contained(columns)
    await expect(columns.getByRole('checkbox')).toHaveCount(17)
    await columns.getByText('所属户商代称', { exact: true }).click()
    await expect(
      columns.getByRole('checkbox', { name: '所属户商代称', exact: true }),
    ).not.toBeChecked()
    await columns.getByRole('button', { name: '取消', exact: true }).click()
    await expect(table.locator('thead th')).toHaveCount(18)
    await page.getByRole('button', { name: '列设置', exact: true }).click()
    await columns.getByText('所属户商代称', { exact: true }).click()
    await expect(
      columns.getByRole('checkbox', { name: '所属户商代称', exact: true }),
    ).not.toBeChecked()
    await columns.getByRole('button', { name: '应用字段设置', exact: true }).click()
    await expect(table.locator('thead th')).toHaveCount(17)
    await page.getByRole('button', { name: '列设置', exact: true }).click()
    await columns.getByRole('button', { name: '恢复默认', exact: true }).click()
    await columns.getByRole('button', { name: '应用字段设置', exact: true }).click()
    await expect(table.locator('thead th')).toHaveCount(18)
    await page.getByRole('button', { name: '今天', exact: true }).click()
    const dates = page.getByRole('dialog', { name: '账户消耗时间', exact: true })
    await dates.getByText('自定义', { exact: true }).click()
    await expect(dates.getByRole('radio', { name: '自定义', exact: true })).toBeChecked()
    await dates.getByPlaceholder('开始业务日').fill('2026-03-07')
    await dates.getByPlaceholder('结束业务日').fill('2026-03-08')
    await dates.getByPlaceholder('结束业务日').press('Tab')
    await dates.getByRole('button', { name: '确认日期', exact: true }).click()
    await expect(table.locator('tbody tr')).not.toHaveCount(0)
    await expect(table).toContainText('2026-03-07 至 2026-03-08')
    const detailsResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/accounts\/[^/]+\/details$/.test(new URL(response.url()).pathname) &&
        response.request().method() === 'GET',
    )
    await table.getByRole('button', { name: '详情', exact: true }).first().click()
    const originalDetails = await (await detailsResponse).json()
    const drawer = page.getByRole('dialog', { name: '广告账户详情', exact: true })
    await expect(drawer).toContainText('金额来源与更新时间')
    await expect(drawer).toContainText('累计总花费')
    await expect(drawer).toContainText('户商资料来源')
    const identityResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/accounts\/[^/]+\/identities$/.test(new URL(response.url()).pathname) &&
        response.request().method() === 'GET',
    )
    const identityButton = drawer.getByRole('button', { name: '读取身份资源', exact: true })
    await identityButton.click()
    const unavailable = await identityResponse
    expect(unavailable.status()).toBe(503)
    expect((await unavailable.json()).code).toBe('ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE')
    await expect(drawer.locator('.el-alert')).toBeVisible()
    await expect(drawer).not.toContainText('本次已观测快照中没有身份资源')
    await expect(identityButton).toBeEnabled()
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `account-details-${info.project.name}.png`),
      animations: 'disabled',
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    )
    await drawer.locator('button.el-drawer__close-btn').click()
    await expect(drawer).not.toBeVisible()
    const originalRow = await table.locator('tbody tr').first().innerText()

    async function openAction(name: string, kind: string) {
      const response = page.waitForResponse((item) => {
        const url = new URL(item.url())
        return (
          /\/api\/v1\/accounts\/[^/]+\/actions\/capabilities$/.test(url.pathname) &&
          url.searchParams.get('action') === kind &&
          item.request().method() === 'GET'
        )
      })
      await table.getByRole('button', { name: '更多操作', exact: true }).first().click()
      await page.getByRole('menuitem', { name, exact: true }).click()
      const actual = await response
      expect(actual.status()).toBe(200)
      expect(actual.headers()['cache-control']).toBe('no-store')
      const capability = await actual.json()
      expect(Object.keys(capability).sort()).toEqual([
        'csrf_token',
        'next_effective_from',
        'revision',
      ])
      expect(capability.csrf_token).toBeTruthy()
      expect(Number.isSafeInteger(capability.revision)).toBe(true)
      expect(capability.revision).toBeGreaterThan(0)
      return capability
    }

    for (const action of [
      { name: '只读同步', kind: 'SYNC', title: '只读同步账户', confirm: '确认受理只读同步' },
      { name: '本地解绑', kind: 'UNBIND', title: '本地解绑账户', confirm: '确认本地解绑' },
    ]) {
      const capability = await openAction(action.name, action.kind)
      expect(capability.next_effective_from).toBeNull()
      const dialog = page.getByRole('dialog', { name: action.title, exact: true })
      await contained(dialog)
      await expect(dialog).toContainText(originalDetails.account.external_id)
      await expect(dialog.getByRole('button', { name: action.confirm, exact: true })).toBeDisabled()
      await dialog
        .getByRole('textbox', { name: '账户操作原因', exact: true })
        .fill('本地浏览器验收只检查取消，不提交动作')
      await expect(dialog.getByRole('button', { name: action.confirm, exact: true })).toBeEnabled()
      if (action.kind === 'SYNC') await expect(dialog).toContainText('仅受理只读同步任务')
      else await expect(dialog).toContainText('平台广告、凭据和历史事实保留')
      await page.screenshot({
        path: path.join(
          process.env.ORBIT_E2E_OUTPUT!,
          `account-action-${action.kind.toLowerCase()}-${info.project.name}.png`,
        ),
        animations: 'disabled',
      })
      await dialog.getByRole('button', { name: '关闭', exact: true }).click()
      await expect(dialog).not.toBeVisible()
      // 与取消前使用相同的可见文本读取方式，逐字保留表格换行和制表符。
      await expect.poll(() => table.locator('tbody tr').first().innerText()).toBe(originalRow)
    }

    const ownersResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        /\/api\/v1\/accounts\/[^/]+\/assignment-options$/.test(url.pathname) &&
        url.searchParams.get('kind') === 'OWNER' &&
        response.request().method() === 'GET'
      )
    })
    const capability = await openAction('分配投手', 'ASSIGNMENT')
    expect(typeof capability.next_effective_from).toBe('string')
    expect(Number.isFinite(Date.parse(capability.next_effective_from))).toBe(true)
    const ownersActual = await ownersResponse
    expect(ownersActual.status()).toBe(200)
    const owners = (await ownersActual.json()).items as {
      id: string
      name: string
      team_id: string
      team_name: string
    }[]
    expect(owners.length).toBeGreaterThan(0)
    const target =
      owners.find((person) => person.id !== originalDetails.account.ownership.owner_user_id) ??
      owners[0]
    const assignment = page.getByRole('dialog', { name: '分配广告账户', exact: true })
    await contained(assignment)
    await expect(
      assignment.getByRole('button', { name: '确认未来分配', exact: true }),
    ).toBeDisabled()
    await expect(assignment.locator('input[type="date"],input[type="datetime-local"]')).toHaveCount(
      0,
    )
    const expectedTime = await page.evaluate(
      ({ value, timezone }) =>
        new Intl.DateTimeFormat('zh-CN', {
          timeZone: timezone,
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hourCycle: 'h23',
        }).format(new Date(value)),
      { value: capability.next_effective_from, timezone: originalDetails.account.timezone.id },
    )
    await expect(assignment).toContainText(expectedTime)
    await expect(assignment).toContainText(originalDetails.account.timezone.id)
    const vendorsResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        /\/api\/v1\/accounts\/[^/]+\/assignment-options$/.test(url.pathname) &&
        url.searchParams.get('kind') === 'VENDOR' &&
        url.searchParams.get('owner_user_id') === target.id &&
        response.request().method() === 'GET'
      )
    })
    // ElementPlus Select的placeholder是展示div；点击可见组件，不查不存在的input placeholder。
    await assignment.locator('.el-select').nth(0).click()
    await page
      .getByRole('option', { name: `${target.name}（${target.team_name}）`, exact: true })
      .first()
      .click()
    const vendorsActual = await vendorsResponse
    expect(vendorsActual.status()).toBe(200)
    const vendors = (await vendorsActual.json()).items as {
      id: string
      name: string
      alias: string | null
    }[]
    expect(Array.isArray(vendors)).toBe(true)
    await expect(assignment).toContainText(`目标团队：${target.team_name}`)
    await assignment.locator('.el-select').nth(1).click()
    if (vendors.length) {
      const vendor = vendors[0]
      const label = vendor.alias
        ? `${vendor.alias}（${vendor.name}）`
        : `${vendor.name}（未设代称）`
      await page.getByRole('option', { name: label, exact: true }).first().click()
      await assignment.locator('.el-select').nth(1).click()
    }
    await page.getByRole('option', { name: '不关联户商', exact: true }).click()
    await assignment
      .getByRole('textbox', { name: '账户分配原因', exact: true })
      .fill('校验真实候选及只读时刻后取消，保留当前归属')
    if (
      target.id !== originalDetails.account.ownership.owner_user_id ||
      originalDetails.account.vendor_id !== null
    )
      await expect(
        assignment.getByRole('button', { name: '确认未来分配', exact: true }),
      ).toBeEnabled()
    else
      await expect(
        assignment.getByRole('button', { name: '确认未来分配', exact: true }),
      ).toBeDisabled()
    await contained(assignment)
    await page.screenshot({
      path: path.join(
        process.env.ORBIT_E2E_OUTPUT!,
        `account-action-assignment-${info.project.name}.png`,
      ),
      animations: 'disabled',
    })
    await assignment.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(assignment).not.toBeVisible()
    await expect.poll(() => table.locator('tbody tr').first().innerText()).toBe(originalRow)
    await expect(table.locator('thead th')).toHaveCount(18)
    expect(actionWrites).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    )
  } finally {
    page.off('request', observeActionWrites)
    await finish()
  }
})
