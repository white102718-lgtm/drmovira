import { test, expect, type Page } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'

const diagnostics = new WeakMap<Page, ReturnType<typeof observePythonBrowser>>()
test.beforeEach(({ page }, info) => {
  diagnostics.set(page, observePythonBrowser(page, info))
})
test.afterEach(async ({ page }) => {
  await diagnostics.get(page)?.()
})

/** 团队表单和确认弹窗连接真实Python/MySQL，无业务响应替身。 */
test('Python团队新增、详情、编辑及停用确认', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/system/teams')
  await expect(page.getByRole('heading', { name: '团队管理', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新增团队', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '新增团队', exact: true })
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog.getByText('请输入1至100个字符的团队名称', { exact: true })).toBeVisible()
  const name = `${'😀'.repeat(70)}-${info.project.name}`
  await dialog.getByLabel('团队名称', { exact: true }).fill(name)
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('按名称查询').fill(name)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const row = page.locator('.el-table__body tr').filter({ hasText: name })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '团队详情', exact: true })
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText(name)
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑团队', exact: true })
  await editor.locator('.el-radio').filter({ hasText: '停用' }).click()
  await expect(editor.getByRole('radio', { name: '停用', exact: true })).toBeChecked()
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: '停用团队', exact: true })
  await confirmation.getByRole('button', { name: '取消', exact: true }).click()
  await expect(confirmation).toBeHidden()
  await expect(editor).toBeVisible()
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  await confirmation.getByRole('button', { name: '确认停用', exact: true }).click()
  await expect(editor).toBeHidden()
  await expect(row).toContainText('停用')
  await expect(row.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
  const size = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }))
  expect(size.width).toBeLessThanOrEqual(size.viewport)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `teams-${info.project.name}.png`),
    fullPage: true,
  })
  expect(failures).toEqual([])
})
