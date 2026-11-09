import { test, expect } from '@playwright/test'
import path from 'node:path'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 复用025独立SQL协议夹具的521成员，不拦截网络，不作为真实平台或50k容量证据。 */
test('Python账户原入口、跨页范围冻结、成员弹窗和重复ID的真实闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
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
    await page.getByRole('button', { name: '账户范围', exact: true }).click()
    await expect(page).toHaveURL(/\/orbit\/account-scopes$/)
    await expect(page.getByRole('heading', { name: '账户范围', exact: true })).toBeVisible()
    await page.getByLabel('账户名称或外部ID', { exact: true }).fill('范围受控-')
    const freeze = page
      .locator('.scope-page form')
      .getByRole('button', { name: /^(冻结并查看成员|重试冻结范围)$/ })
    const response = page.waitForResponse(
      (item) =>
        /\/api\/v1\/scope-snapshots$/.test(new URL(item.url()).pathname) &&
        item.request().method() === 'POST',
    )
    await freeze.click()
    const created = await response
    expect(created.status()).toBe(201)
    expect((await created.json()).count).toBe(521)
    const dialog = page.getByRole('dialog', { name: '账户范围成员', exact: true })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('冻结账户 521 个')
    await expect(dialog.locator('.el-table__body tbody tr')).toHaveCount(50)
    await expect
      .poll(() =>
        dialog.evaluate((element) => {
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
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `scope-members-${info.project.name}.png`),
      animations: 'disabled',
    })
    const firstId = await dialog
      .locator('.el-table__body tbody tr')
      .first()
      .locator('td')
      .last()
      .innerText()
    await dialog.locator('.el-select__wrapper').click()
    await page.getByRole('option', { name: '20', exact: true }).click()
    await expect(dialog.locator('.el-table__body tbody tr')).toHaveCount(20)
    await dialog.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(dialog).toContainText('第 2 页')
    await expect(
      dialog.locator('.el-table__body tbody tr').first().locator('td').last(),
    ).not.toHaveText(firstId)
    await dialog.getByRole('button', { name: '上一页', exact: true }).click()
    await expect(dialog).toContainText('第 1 页')
    await expect(
      dialog.locator('.el-table__body tbody tr').first().locator('td').last(),
    ).toHaveText(firstId)
    await dialog.getByLabel('成员搜索', { exact: true }).fill('not-a-matching-scope-member')
    await dialog.getByRole('button', { name: '搜索成员', exact: true }).click()
    await expect(dialog).toContainText('没有匹配的账户')
    await expect(dialog).toContainText('冻结账户 521 个')
    await expect(dialog.getByRole('button', { name: '使用此范围', exact: true })).toBeEnabled()
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.getByLabel('已选择范围', { exact: true })).toHaveCount(0)
    await freeze.click()
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('.el-table__body tbody tr')).toHaveCount(50)
    await dialog.getByRole('button', { name: '使用此范围', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.getByLabel('已选择范围', { exact: true })).toContainText('已选择 521 个账户')
    await page.getByLabel('账户名称或外部ID', { exact: true }).fill('changed-filter')
    await expect(page.getByLabel('已选择范围', { exact: true })).toHaveCount(0)
    await page.getByText('指定账户ID', { exact: true }).click()
    await expect(page.getByRole('radio', { name: '指定账户ID', exact: true })).toBeChecked()
    const posted: string[] = []
    page.on('request', (request) => {
      if (
        /\/api\/v1\/scope-snapshots$/.test(new URL(request.url()).pathname) &&
        request.method() === 'POST'
      )
        posted.push(request.url())
    })
    await page
      .getByLabel('账户ID清单', { exact: true })
      .fill(firstId + '\n' + firstId.toUpperCase())
    await freeze.click()
    await expect(page.locator('.scope-page .el-alert')).toContainText('账户ID清单包含重复项')
    expect(posted).toHaveLength(0)
    await page.getByLabel('账户ID清单', { exact: true }).fill(firstId)
    await freeze.click()
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('冻结账户 1 个')
    await expect(dialog.locator('.el-table__body tbody tr')).toHaveCount(1)
    await dialog.getByRole('button', { name: '使用此范围', exact: true }).click()
    await expect(page.getByLabel('已选择范围', { exact: true })).toContainText('已选择 1 个账户')
    await page.getByRole('button', { name: '清除选择', exact: true }).click()
    await expect(page.getByLabel('已选择范围', { exact: true })).toHaveCount(0)
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `scope-page-${info.project.name}.png`),
      animations: 'disabled',
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    )
  } finally {
    await finish()
  }
})
