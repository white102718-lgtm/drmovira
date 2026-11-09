import { test, expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'
import type { ConfigSection } from '../../src/api/orbit/configuration'

const diagnostics = new WeakMap<Page, ReturnType<typeof observePythonBrowser>>()
test.beforeEach(({ page }, info) => {
  diagnostics.set(page, observePythonBrowser(page, info))
})
test.afterEach(async ({ page }) => {
  await diagnostics.get(page)?.()
})

/** 真实Python/MySQL/Redis；平台HTTP为fixture，保存故障注入只丢弃已提交的真实响应。 */
test('Python原登录菜单与配置创建、保持凭据修改和历史抽屉', async ({ page }, info) => {
  async function choose(dialog: Locator, label: string, option: string, exact = true) {
    const control = dialog.getByLabel(label, { exact })
    await dialog
      .locator('.el-select')
      .filter({ has: page.getByLabel(label, { exact }) })
      .locator('.el-select__wrapper')
      .click()
    const listId = await control.getAttribute('aria-controls')
    expect(listId).toBeTruthy()
    // 多个凭据选择器关闭动画可重叠，必须使用当前combobox关联的listbox。
    await page
      .locator(`[id="${listId}"]`)
      .getByRole('option', { name: option, exact: true })
      .click()
  }
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await expect(page.getByPlaceholder('验证码', { exact: true })).toHaveCount(0)
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  const sidebar = page.locator('.sidebar-container')
  await expect(sidebar.getByText('系统管理', { exact: true })).toHaveCount(1)
  if (info.project.name === 'mobile-390') await page.locator('.hamburger-container').click()
  await sidebar.getByText('ORBIT工作台', { exact: true }).click()
  const system = sidebar.getByText('ORBIT系统管理', { exact: true })
  if (await system.isVisible()) await system.click()
  const metadataResponse = page.waitForResponse((response) =>
    response.url().endsWith('/system-configurations/metadata'),
  )
  await sidebar.getByText('系统配置', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '系统配置', exact: true })).toBeVisible()
  const { sections } = (await (await metadataResponse).json()) as { sections: ConfigSection[] }
  expect(sections).toHaveLength(12)
  const originalSections = sections.filter((section) => section.key !== 'MATERIAL_SCANNER')
  expect(originalSections).toHaveLength(11)
  expect(originalSections.reduce((count, section) => count + section.fields.length, 0)).toBe(62)
  const scannerSections = sections.filter((section) => section.key === 'MATERIAL_SCANNER')
  expect(scannerSections).toHaveLength(1)
  expect(scannerSections[0].fields.map((field) => field.key)).toEqual(['profileId'])
  if (info.project.name === 'mobile-390') {
    await page.locator('.drawer-bg').click({ position: { x: 380, y: 100 } })
    await expect(page.locator('.drawer-bg')).toHaveCount(0)
  }
  const name = `${'😀'.repeat(80)}-${info.project.name}`
  await page.getByRole('button', { name: '新增配置', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '新增系统配置', exact: true })
  await choose(dialog, '配置类型', 'GPT API', false)
  await dialog.getByLabel('配置名称', { exact: true }).fill(name)
  await dialog.getByLabel('模型ID', { exact: true }).fill('fixture-model')
  await dialog.locator('.el-switch').click()
  await dialog.locator('.configuration-secret .el-select__wrapper').click()
  await page.getByRole('option', { name: '替换凭据', exact: true }).click()
  await dialog
    .locator('input[type="password"][aria-label="OpenAI API Key"]')
    .fill('fixture-python-browser-key')
  await dialog.getByLabel('变更原因', { exact: true }).fill('Python真实浏览器新增')
  let committedId = ''
  let firstRequestKey = ''
  const savePattern = '**/api/v1/system-configurations'
  await page.route(savePattern, async (route) => {
    if (
      route.request().method() === 'POST' &&
      route.request().postDataJSON().name === name &&
      !committedId
    ) {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      committedId = (await response.json()).id
      firstRequestKey = route.request().headers()['idempotency-key']
      await route.abort('failed')
    } else await route.continue()
  })
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(page.getByText('网络连接中断，请检查后重试', { exact: true })).toBeVisible()
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
  await page.unroute(savePattern)
  expect(committedId).toBeTruthy()
  await choose(dialog, 'OpenAI API Key操作', '替换凭据')
  await dialog
    .locator('input[type="password"][aria-label="OpenAI API Key"]')
    .fill('fixture-python-browser-key')
  const retry = page.waitForRequest(
    (request) => request.method() === 'POST' && request.url().endsWith('/system-configurations'),
  )
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && response.url().endsWith('/system-configurations'),
  )
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  expect((await retry).headers()['idempotency-key']).toBe(firstRequestKey)
  expect((await (await saved).json()).id).toBe(committedId)
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('搜索配置名称').fill(name)
  const row = page.locator('.el-table__body tr').filter({ hasText: name })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('已配置（不回显）')
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
  await dialog.getByLabel('变更原因', { exact: true }).fill('Python保持原凭据修改')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(row.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
  await row.getByRole('button', { name: '变更历史', exact: true }).click()
  const drawer = page.locator('.el-drawer:visible')
  await expect(drawer).toContainText('Python保持原凭据修改')
  await expect(drawer).toContainText('Python真实浏览器新增')
  await expect(drawer).not.toContainText('fixture-python-browser-key')
  // 文本出现时抽屉仍可能处于滑入动画；等待实际几何位置，验证窄屏完整可见。
  await expect
    .poll(async () => {
      const box = await drawer.boundingBox()
      const viewport = page.viewportSize()!
      return !!box && box.x >= -1 && box.x + box.width <= viewport.width + 1
    })
    .toBe(true)
  await drawer.locator('.el-table__expand-icon').first().click()
  await expect(drawer.locator('.history-details')).toContainText('SHA256_STATE_V1')
  const scroll = drawer.locator('.el-table__body-wrapper .el-scrollbar__wrap')
  await scroll.evaluate((element) => {
    element.scrollLeft = element.scrollWidth
  })
  await expect(
    drawer.getByRole('cell', { name: 'Python保持原凭据修改', exact: true }),
  ).toBeInViewport()
  await expect(page.locator('.el-message')).toHaveCount(0)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-history.png`),
  })
  await page.keyboard.press('Escape')
  await expect(drawer).toHaveCount(0)
  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  let probe = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  await probe.getByRole('button', { name: '取消', exact: true }).click()
  await expect(probe).toBeHidden()
  await expect(row.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  probe = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  await probe.getByPlaceholder('填写测试原因，请勿填写密钥或Token').fill('Python浏览器人工只读测试')
  await probe.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(probe).toBeHidden()
  await expect(row).toContainText('只读认证通过')
  await expect(row.getByRole('cell', { name: '3', exact: true })).toHaveCount(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  const persisted = await page.evaluate(() =>
    JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
  )
  expect(persisted).not.toContain('fixture-python-browser-key')
  // 保留第一次真实GET响应，在新增及新一轮读取完成后才放行，验证旧读取不能覆盖新目录。
  let releaseOldRead!: () => void
  let capturedOldRead!: () => void
  const held = new Promise<void>((resolve) => {
    capturedOldRead = resolve
  })
  const release = new Promise<void>((resolve) => {
    releaseOldRead = resolve
  })
  let capture = true
  await page.route(savePattern, async (route) => {
    if (capture && route.request().method() === 'GET') {
      capture = false
      const response = await route.fetch()
      capturedOldRead()
      await release
      await route.fulfill({ response })
    } else await route.continue()
  })
  try {
    await page.getByRole('button', { name: '刷新', exact: true }).click()
    await held
    await page.getByRole('button', { name: '新增配置', exact: true }).click()
    dialog = page.getByRole('dialog', { name: '新增系统配置', exact: true })
    await choose(dialog, '配置类型', 'GPT API', false)
    const raceName = `读取竞态-${info.project.name}`
    await dialog.getByLabel('配置名称', { exact: true }).fill(raceName)
    await dialog.getByLabel('变更原因', { exact: true }).fill('验证迟到的真实读取不覆盖新保存')
    await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(dialog).toBeHidden()
    await page.getByPlaceholder('搜索配置名称').fill(raceName)
    const raceRow = page.locator('.el-table__body tr').filter({ hasText: raceName })
    await expect(raceRow).toHaveCount(1)
    const lateResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' && response.url().endsWith('/system-configurations'),
    )
    releaseOldRead()
    await (await lateResponse).finished()
    // 等待浏览器完成响应后的渲染帧，不用固定延时，也不延长断言超时。
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        }),
    )
    await expect(raceRow).toHaveCount(1)
  } finally {
    releaseOldRead()
    await page.unroute(savePattern)
  }
  expect(failures).toEqual([])
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-configuration.png`),
  })

  // 逐类型核对全部字段可达、默认值回填和密钥替换；停用配置不会调用外部平台。
  // 原11类62字段全量断言保留；扫描单例由独立真实专项编辑既有行验证。
  for (const section of originalSections) {
    await page.getByRole('button', { name: '新增配置', exact: true }).click()
    dialog = page.getByRole('dialog', { name: '新增系统配置', exact: true })
    if (section.key !== sections[0].key) {
      await choose(dialog, '配置类型', section.label, false)
    }
    const sectionName = `字段-${section.key}-${info.project.name}`
    await dialog.getByLabel('配置名称', { exact: true }).fill(sectionName)
    for (const field of section.fields) {
      if (field.type === 'secret') {
        await choose(dialog, `${field.label}操作`, '替换凭据')
        await dialog
          .locator(`input[type="password"][aria-label="${field.label}"]`)
          .fill('fixture-each-field')
      } else if (field.type === 'text' && field.key !== 'providerConfigId') {
        await expect(dialog.getByLabel(field.label, { exact: false })).toHaveValue(
          String(field.defaultValue ?? ''),
        )
      } else if (field.type === 'integer') {
        await expect(dialog.getByLabel(field.label, { exact: false })).toHaveValue(
          String(field.defaultValue),
        )
      } else {
        await expect(dialog.getByLabel(field.label, { exact: false })).toBeVisible()
      }
    }
    await dialog.getByLabel('变更原因', { exact: true }).fill('逐字段默认值与凭据替换')
    await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(dialog).toBeHidden()
    await page.getByPlaceholder('搜索配置名称').fill(sectionName)
    const sectionRow = page.locator('.el-table__body tr').filter({ hasText: sectionName })
    await expect(sectionRow).toHaveCount(1)
    await sectionRow.getByRole('button', { name: '编辑', exact: true }).click()
    dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
    await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
    await expect(dialog.getByLabel('配置类型', { exact: false })).toBeDisabled()
    for (const field of section.fields.filter((field) => field.type === 'secret')) {
      await expect(
        dialog.locator('.configuration-secret').filter({
          has: page.getByLabel(`${field.label}操作`, { exact: true }),
        }),
      ).toContainText('保持不变')
    }
    if (section.key === 'AI_GPT') {
      await choose(dialog, 'OpenAI API Key操作', '清除凭据')
      await dialog.getByLabel('变更原因', { exact: true }).fill('清除停用配置的测试凭据')
      await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
      let confirmation = page.getByRole('dialog', { name: '确认清除凭据', exact: true })
      await confirmation.getByRole('button', { name: '返回检查', exact: true }).click()
      await expect(confirmation).toBeHidden()
      await expect(dialog).toBeVisible()
      await expect(sectionRow.getByRole('cell', { name: '1', exact: true })).toHaveCount(1)
      await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
      confirmation = page.getByRole('dialog', { name: '确认清除凭据', exact: true })
      await confirmation.getByRole('button', { name: '清除并保存', exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(sectionRow).toContainText('未配置')
      await expect(sectionRow.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
    } else {
      await dialog.getByRole('button', { name: '取消', exact: true }).click()
      await expect(dialog).toBeHidden()
    }
  }
  expect(failures).toEqual([])
  expect(
    await page.evaluate(() =>
      JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
    ),
  ).not.toContain('fixture-each-field')
})
