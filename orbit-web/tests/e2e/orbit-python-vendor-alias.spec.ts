import { test, expect, type Locator } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import path from 'node:path'

/** 真实Python/MySQL与界面导入及维护，无route.fulfill或直接DB代写。 */
test('Python户商真实代称读取维护清除与刷新闭环', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const vendor = randomUUID(),
    namespace = randomUUID().slice(0, 8)
  const name = `完整户商名称-${namespace}-不能自动截断为代称`
  const owner = '00000000-0000-0000-0000-000000000001'
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/system/dictionaries')
  async function choose(input: Locator, label: string) {
    await input.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: label, exact: true }).click()
  }
  await page.getByRole('button', { name: '导入预检', exact: true }).click()
  const imported = page.getByRole('dialog', { name: '引用资料导入预检', exact: true })
  await choose(imported.getByLabel('类别', { exact: true }), '户商')
  await imported.getByLabel('来源（必填，可追溯）', { exact: true }).fill('真实代称浏览器专项')
  await imported.getByLabel('导入原因（必填）', { exact: true }).fill('不以名称推算代称')
  await imported.getByLabel('JSON资料数组（1—500行，总正文不超过2MiB）', { exact: true }).fill(
    JSON.stringify([
      {
        id: vendor,
        kind: 'VENDOR',
        name,
        source_key: `alias-browser-${vendor}`,
        availability: 'AVAILABLE',
        owner_team_id: owner,
        data_owner_user_ids: [owner],
      },
    ]),
  )
  await imported.getByRole('button', { name: '开始预检', exact: true }).click()
  await expect(imported).toContainText('预检通过，尚未提交')
  await imported.getByRole('button', { name: '确认差异并原子提交', exact: true }).click()
  await expect(imported).toContainText('目录已原子提交成功')
  await imported.getByRole('button', { name: '关闭', exact: true }).click()
  const form = page.locator('.reference-page > .el-card .el-form').first()
  await choose(form.getByLabel('类别', { exact: true }), '户商')
  const section = page.getByRole('region', { name: '当前户商代称', exact: true })
  const row = section.getByRole('row').filter({ hasText: name })
  await expect(row).toContainText('未知')
  await row.getByRole('button', { name: '维护代称', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '维护户商代称', exact: true })
  await expect(dialog).toContainText(name)
  await expect(dialog).toContainText('当前代称版本')
  await dialog.getByLabel('真实代称（1至30字符）', { exact: true }).fill('户'.repeat(31))
  await dialog.getByLabel('维护原因（必填）', { exact: true }).fill('实际维护')
  await dialog.getByRole('button', { name: '确认维护代称', exact: true }).click()
  await expect(dialog).toContainText('代称须为1至30个字符')
  const alias = `真实代称-é-${namespace}`
  await dialog
    .getByLabel('真实代称（1至30字符）', { exact: true })
    .fill(`真实代称-e\u0301-${namespace}`)
  await dialog.getByRole('button', { name: '确认维护代称', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(row).toContainText(alias)
  await section.getByRole('button', { name: '刷新代称', exact: true }).click()
  await expect(row).toContainText(alias)
  await row.getByRole('button', { name: '维护代称', exact: true }).click()
  await expect(dialog.getByLabel('真实代称（1至30字符）', { exact: true })).toHaveValue(alias)
  await expect
    .poll(() =>
      dialog.evaluate((element) => {
        const bounds = element.getBoundingClientRect()
        return (
          bounds.left >= 0 &&
          bounds.right <= innerWidth &&
          bounds.top >= 0 &&
          bounds.bottom <= innerHeight
        )
      }),
    )
    .toBe(true)
  // Element Plus原始input隐藏，点击真实可见label后仍核验原checkbox状态。
  await dialog.locator('label.el-checkbox').filter({ hasText: '清除代称（设为未知）' }).click()
  await expect(dialog.getByLabel('清除代称（设为未知）', { exact: true })).toBeChecked()
  await dialog.getByLabel('维护原因（必填）', { exact: true }).fill('显式清除，历史不改写')
  await dialog.getByRole('button', { name: '确认维护代称', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(row).toContainText('未知')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `vendor-alias-${info.project.name}.png`),
    animations: 'disabled',
  })
  expect(failures).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
