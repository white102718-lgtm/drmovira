import { test, expect } from '@playwright/test'
import path from 'node:path'

test('Python功能角色内置复制、重试、详情与撤权确认', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  const capabilityResponse = page.waitForResponse((response) =>
    response.url().endsWith('/roles/capabilities'),
  )
  await page.goto('/orbit/system/roles')
  const caps = await (await capabilityResponse).json()
  await expect(page.getByRole('heading', { name: '功能角色', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新增角色', exact: true }).click()
  const empty = page.getByRole('dialog', { name: '新增角色', exact: true })
  await empty.getByRole('button', { name: '保存角色', exact: true }).click()
  await expect(empty.getByText('请输入1至50个字符的角色名称', { exact: true })).toBeVisible()
  await empty.getByLabel('角色名称', { exact: true }).fill('😀'.repeat(51))
  await empty.getByRole('button', { name: '保存角色', exact: true }).click()
  await expect(empty.getByText('请输入1至50个字符的角色名称', { exact: true })).toBeVisible()
  await empty.getByRole('button', { name: '取消', exact: true }).click()
  await expect(empty).toBeHidden()
  const builtin = page.locator('.el-table__body tr').filter({ hasText: '内置只读' })
  await expect(builtin).toHaveCount(1)
  await expect(builtin.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0)
  await builtin.getByRole('button', { name: '复制', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '复制角色', exact: true })
  const name = `${'😀'.repeat(30)}-${info.project.name}`
  await dialog.getByLabel('角色名称', { exact: true }).fill(name)
  await expect(dialog.getByRole('checkbox')).toHaveCount(
    caps.menus.length + caps.permissions.length,
  )
  expect(
    await dialog
      .getByRole('checkbox')
      .evaluateAll((nodes) => nodes.every((node) => (node as HTMLInputElement).checked)),
  ).toBe(true)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `roles-editor-${info.project.name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
  const pattern = '**/api/v1/roles'
  let committedId = '',
    firstKey = ''
  await page.route(pattern, async (route) => {
    if (
      route.request().method() === 'POST' &&
      route.request().postDataJSON().name === name &&
      !committedId
    ) {
      const response = await route.fetch()
      expect(response.status()).toBe(201)
      committedId = (await response.json()).id
      firstKey = route.request().headers()['idempotency-key']
      await route.abort('failed')
    } else await route.continue()
  })
  await dialog.getByRole('button', { name: '保存角色', exact: true }).click()
  await expect(
    dialog.getByText('网络中断，重试会保留同一次保存意图', { exact: true }),
  ).toBeInViewport({ ratio: 1 })
  await expect(dialog.getByRole('button', { name: '保存角色', exact: true })).toBeInViewport({
    ratio: 1,
  })
  await page.unroute(pattern)
  const retryRequest = page.waitForRequest(
    (request) => request.method() === 'POST' && request.url().endsWith('/api/v1/roles'),
  )
  const retryResponse = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/api/v1/roles'),
  )
  await dialog.getByRole('button', { name: '保存角色', exact: true }).click()
  expect((await retryRequest).headers()['idempotency-key']).toBe(firstKey)
  expect((await (await retryResponse).json()).id).toBe(committedId)
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('按角色名称查询').fill(name)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const row = page.locator('.el-table__body tr').filter({ hasText: name })
  await expect(row).toHaveCount(1)
  const chooseStatus = async (label: string) => {
    const input = page.getByLabel('状态', { exact: true })
    await page.locator('.el-select').filter({ has: input }).locator('.el-select__wrapper').click()
    const listId = await input.getAttribute('aria-controls')
    await page.locator(`[id="${listId}"]`).getByRole('option', { name: label, exact: true }).click()
    await page.getByRole('button', { name: '查询', exact: true }).click()
  }
  await chooseStatus('停用')
  await expect(page.getByText('暂无符合条件的角色', { exact: true })).toBeVisible()
  await chooseStatus('启用')
  await expect(row).toHaveCount(1)
  await page.getByPlaceholder('开始日期', { exact: true }).fill('2999-01-01')
  await page.getByPlaceholder('结束日期', { exact: true }).fill('2999-01-01')
  const calendar = page.locator('.orbit-directory-date-popper').filter({ visible: true })
  await expect(calendar).toBeVisible()
  if (info.project.name === 'mobile-390') {
    const box = await calendar.boundingBox()
    expect(box).toBeTruthy()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(390)
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, 'roles-calendar-mobile.png'),
      fullPage: true,
      animations: 'disabled',
    })
  }
  // 手工日期输入用原生Enter确认范围后再查询，不强制穿透仍打开的日期弹层。
  await page.getByPlaceholder('结束日期', { exact: true }).press('Enter')
  await expect(calendar).toBeHidden()
  const datedResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/roles?') && response.url().includes('date_from=2999-01-01'),
  )
  await page.getByRole('button', { name: '查询', exact: true }).click()
  expect((await (await datedResponse).json()).items).toEqual([])
  await expect(page.getByText('暂无符合条件的角色', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await page.getByPlaceholder('按角色名称查询').fill(name)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '角色详情', exact: true })
  await expect(drawer).toContainText(committedId)
  await expect(drawer.locator('.role-detail-actions li')).toHaveCount(caps.permissions.length)
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑角色', exact: true })
  await editor.getByText('管理团队', { exact: true }).click()
  await expect(editor.getByRole('checkbox', { name: '管理团队', exact: true })).not.toBeChecked()
  await editor.getByRole('button', { name: '保存角色', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: '撤销角色授权', exact: true })
  await confirmation.getByRole('button', { name: '返回检查', exact: true }).click()
  await expect(editor).toBeVisible()
  await editor.getByRole('button', { name: '保存角色', exact: true }).click()
  await confirmation.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(editor).toBeHidden()
  await expect(row.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }))
  expect(size.width).toBeLessThanOrEqual(size.viewport)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `roles-${info.project.name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
  expect(failures).toEqual([])
  expect(
    await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    ),
  ).not.toContain(caps.csrf_token)
})
