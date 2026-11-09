import { test, expect } from '@playwright/test'
import type { Page, Response } from '@playwright/test'
import path from 'node:path'
import type { Configuration, MaterialScannerProfile } from '../../src/api/orbit/configuration'
import { observePythonBrowser } from './python-browser-diagnostics'

const diagnostics = new WeakMap<Page, ReturnType<typeof observePythonBrowser>>()
test.beforeEach(({ page }, info) => {
  diagnostics.set(page, observePythonBrowser(page, info))
})
test.afterEach(async ({ page }) => {
  await diagnostics.get(page)?.()
})

function responseAt(page: Page, response: Response, suffix: string, method = 'GET') {
  const url = new URL(response.url())
  return (
    url.origin === new URL(page.url()).origin &&
    response.request().method() === method &&
    [
      `/api/v1/system-configurations${suffix}`,
      `/dev-api/api/v1/system-configurations${suffix}`,
    ].includes(url.pathname)
  )
}

/** 真实Python/SQL/受控registry/实际ClamD；三视口编辑同一个单例，不mock接口或重置版本。 */
test('正式扫描配置候选、取消、保存、实际安全PNG测试与历史', async ({ page }, info) => {
  if (process.env.ORBIT_E2E_MATERIAL_SCANNER_CONFIGURATION !== '1') {
    throw new Error('正式扫描配置专项需由主线真实夹具运行')
  }
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.name))
  await page.goto('/login')
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  const listed = page.waitForResponse((response) => responseAt(page, response, ''))
  await page.goto('/orbit/system/configuration')
  await expect(page.getByRole('heading', { name: '系统配置', exact: true })).toBeVisible()
  const response = await listed
  expect(response.status()).toBe(200)
  const configurations = (await response.json()) as Configuration[]
  const scannerRows = configurations.filter((item) => item.section === 'MATERIAL_SCANNER')
  expect(scannerRows).toHaveLength(1)
  const initial = scannerRows[0]
  expect(initial.name).toBe('正式扫描专项')
  expect(Object.keys(initial.settings)).toEqual(['profileId'])
  expect(initial.secrets).toEqual({})
  await page.getByPlaceholder('搜索配置名称').fill(initial.name)
  const row = page.locator('.el-table__body tr').filter({ hasText: initial.name })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('素材安全扫描')

  let saves = 0
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (request.method() === 'PUT' && url.pathname.endsWith(`/system-configurations/${initial.id}`))
      saves += 1
  })
  const candidates = page.waitForResponse((result) =>
    responseAt(page, result, '/material-scanner-profiles'),
  )
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await expect(dialog).toContainText('保存或测试会更新扫描配置版本，正在处理的素材可能需要重新检查')
  const candidateResponse = await candidates
  expect(candidateResponse.status()).toBe(200)
  const candidateBody = (await candidateResponse.json()) as { items: MaterialScannerProfile[] }
  expect(Object.keys(candidateBody)).toEqual(['items'])
  expect(candidateBody.items.length).toBeGreaterThan(0)
  for (const item of candidateBody.items) {
    expect(Object.keys(item).sort()).toEqual(['availability', 'id', 'label'])
  }
  const selected = candidateBody.items.find((item) => item.id === initial.settings.profileId)
  expect(selected?.availability).toBe('READY')
  const control = dialog.getByRole('combobox', { name: '服务端扫描候选', exact: true })
  await expect(control).toHaveAttribute('readonly')
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
  for (const forbidden of ['端口', '进程PID', '可执行文件路径', '数据库路径', '扫描地址']) {
    await expect(dialog.getByLabel(forbidden, { exact: true })).toHaveCount(0)
  }
  await dialog.getByLabel('变更原因', { exact: true }).fill(`取消不写-${info.project.name}`)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(saves).toBe(0)
  const refreshed = page.waitForResponse((result) => responseAt(page, result, ''))
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  const unchanged = ((await (await refreshed).json()) as Configuration[]).find(
    (item) => item.id === initial.id,
  )
  expect(unchanged?.revision).toBe(initial.revision)

  const reopened = page.waitForResponse((result) =>
    responseAt(page, result, '/material-scanner-profiles'),
  )
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  expect((await reopened).status()).toBe(200)
  const combo = dialog.getByRole('combobox', { name: '服务端扫描候选', exact: true })
  await dialog.locator('.scanner-profile-control .el-select__wrapper').click()
  const listId = await combo.getAttribute('aria-controls')
  expect(listId).toBeTruthy()
  await page
    .locator(`[id="${listId}"]`)
    .getByRole('option', { name: selected!.label, exact: true })
    .click()
  const reason = `浏览器扫描配置保存-${info.project.name}`
  await dialog.getByLabel('变更原因', { exact: true }).fill(reason)
  const saved = page.waitForResponse((result) => responseAt(page, result, `/${initial.id}`, 'PUT'))
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  const saveResponse = await saved
  expect(saveResponse.status()).toBe(200)
  const savedConfiguration = (await saveResponse.json()) as Configuration
  expect(saveResponse.request().headers()['if-match']).toBe(`"${initial.revision}"`)
  expect(savedConfiguration.revision).toBe(initial.revision + 1)
  expect(savedConfiguration.settings).toEqual(initial.settings)
  expect(savedConfiguration.verificationStatus).toBe('UNTESTED')
  await expect(dialog).toBeHidden()
  await expect(row).toContainText('尚未验证')

  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  let prompt = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  await prompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(prompt).toBeHidden()
  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  prompt = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  const probeReason = `浏览器实际安全PNG检查-${info.project.name}`
  await prompt.getByPlaceholder('填写测试原因，请勿填写密钥或Token').fill(probeReason)
  const tested = page.waitForResponse((result) =>
    responseAt(page, result, `/${initial.id}/test`, 'POST'),
  )
  await prompt.getByRole('button', { name: '开始测试', exact: true }).click()
  const testedResponse = await tested
  expect(testedResponse.status()).toBe(200)
  const result = await testedResponse.json()
  expect(testedResponse.request().headers()['if-match']).toBe(`"${savedConfiguration.revision}"`)
  expect(result.result.status).toBe('READ_VERIFIED')
  expect(result.configuration.revision).toBe(initial.revision + 2)
  expect(result.result.message).toBe('实际安全PNG扫描与运行实例复核通过')
  await expect(prompt).toBeHidden()
  await expect(row).toContainText('只读认证通过')
  await row.getByRole('button', { name: '变更历史', exact: true }).click()
  const drawer = page.locator('.el-drawer:visible')
  await expect(drawer).toContainText(reason)
  await expect(drawer).toContainText(probeReason)
  await expect(drawer).not.toContainText(`取消不写-${info.project.name}`)
  await expect
    .poll(async () => {
      const box = await drawer.boundingBox()
      return !!box && box.x >= -1 && box.x + box.width <= page.viewportSize()!.width + 1
    })
    .toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(pageErrors).toEqual([])
  await page.screenshot({
    path: path.join(
      process.env.ORBIT_E2E_OUTPUT!,
      `${info.project.name}-scanner-configuration.png`,
    ),
  })
})
