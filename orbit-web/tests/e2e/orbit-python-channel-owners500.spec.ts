import { test, expect, type Locator } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import path from 'node:path'

interface Fixture {
  team_name: string
  owner_ids: string[]
  product_name: string
  agent_name: string
}

/** 数据库只构造隔离身份/资料夹具；被验批选、创建、分配、详情全部经真实界面。 */
test('Python渠道跨三页候选500人批选创建分配与详情', async ({ page }, info) => {
  const file = process.env.ORBIT_E2E_OWNERS500_FIXTURE
  expect(file, '主线必须先执行500人HTTP专项并提供非敏感夹具文件').toBeTruthy()
  const fixture: Fixture = JSON.parse(readFileSync(file!, 'utf8'))
  expect(new Set(fixture.owner_ids).size).toBe(500)
  const failures: string[] = []
  const cursorPages = new Set<string>()
  page.on('pageerror', (error) => failures.push(error.message))
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.pathname.endsWith('/channels/ownership-options') && response.status() === 200)
      cursorPages.add(url.searchParams.get('after') || 'first')
  })
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/channels')
  await page.getByRole('button', { name: '新增渠道', exact: true }).click()
  const create = page.getByRole('dialog', { name: '新增渠道', exact: true })
  async function choose(input: Locator, label: string) {
    await input.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: label, exact: true }).click()
  }
  async function loadAll(dialog: Locator, label: string) {
    for (let index = 0; index < 10; index++) {
      // 弹窗可见不代表首次候选已回来；只按真实UI加载状态等待，不把旧null游标当末页。
      await expect(dialog.getByRole('status')).toHaveAttribute('aria-busy', 'false')
      const button = dialog.getByRole('button', { name: label, exact: true })
      if (!(await button.count())) return
      await expect(button).toBeEnabled()
      const loaded = page.waitForResponse((response) =>
        new URL(response.url()).pathname.endsWith('/channels/ownership-options'),
      )
      await button.click()
      expect((await loaded).status()).toBe(200)
      await expect
        .poll(async () => !(await button.count()) || (await button.isEnabled()))
        .toBe(true)
    }
    expect(await dialog.getByRole('button', { name: label, exact: true }).count()).toBe(0)
  }
  await loadAll(create, '加载更多可分配用户')
  await choose(create.getByLabel('归属团队', { exact: true }), fixture.team_name)
  await expect(create.getByTestId('create-owner-summary')).toContainText(
    '已加载当前团队 500 人；已选择 0 / 500 人',
  )
  await create.getByRole('button', { name: '选择当前团队已加载用户', exact: true }).click()
  await expect(create.getByTestId('create-owner-summary')).toContainText('已选择 500 / 500 人')
  expect(cursorPages.size).toBeGreaterThanOrEqual(3)
  const selection = create
    .locator('.el-select')
    .filter({ has: create.getByLabel('分配用户（1—500名）', { exact: true }) })
  expect(await selection.locator('.el-select__selection .el-tag').count()).toBeLessThanOrEqual(4)
  const code = 'UI500_' + randomUUID().replaceAll('-', '').slice(0, 16)
  await create.getByLabel('渠道ID（必填，同租户唯一）', { exact: true }).fill(code)
  await create.getByLabel('渠道名称', { exact: true }).fill('真实界面500成员')
  await choose(create.getByLabel('产品（必填）', { exact: true }), fixture.product_name)
  await choose(create.getByLabel('总代（仅限产品已关联）', { exact: true }), fixture.agent_name)
  await create
    .getByLabel('HTTPS投放链接（不自动追加参数，不覆盖已保存计划）', { exact: true })
    .fill('https://example.com/ui500')
  const response = page.waitForResponse(
    (result) =>
      new URL(result.url()).pathname.endsWith('/api/v1/channels') &&
      result.request().method() === 'POST',
  )
  await create.getByRole('button', { name: '保存', exact: true }).click()
  const createdResponse = await response
  expect(createdResponse.status()).toBe(201)
  const created = await createdResponse.json()
  expect([...created.ownership.data_owner_user_ids].sort()).toEqual([...fixture.owner_ids].sort())
  await expect(create).toBeHidden()
  const row = page.locator('.el-table__body tr').filter({ hasText: code })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '分配', exact: true }).click()
  const assigned = page.getByRole('dialog', { name: '分配渠道', exact: true })
  await loadAll(assigned, '加载更多用户')
  await assigned.getByRole('button', { name: '选择当前团队已加载用户', exact: true }).click()
  await expect(assigned.getByTestId('assignment-owner-summary')).toContainText(
    '已加载当前团队 500 人；已选择 500 / 500 人',
  )
  await assigned.getByLabel('原因（必填）', { exact: true }).fill('界面重新分配完整500集合')
  await expect
    .poll(() =>
      assigned.evaluate((element) => {
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
  const saved = page.waitForResponse(
    (result) =>
      new URL(result.url()).pathname.endsWith(`/channels/${created.id}/owners`) &&
      result.request().method() === 'PUT',
  )
  await assigned.getByRole('button', { name: '确认', exact: true }).click()
  const savedResponse = await saved
  expect(savedResponse.status()).toBe(200)
  expect([...(await savedResponse.json()).ownership.data_owner_user_ids].sort()).toEqual(
    [...fixture.owner_ids].sort(),
  )
  await expect(assigned).toBeHidden()
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '渠道详情', exact: true })
  await expect(detail).toContainText('五百成员000')
  await expect(detail).toContainText('五百成员499')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `channel-owners500-${info.project.name}.png`),
    animations: 'disabled',
  })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(failures).toEqual([])
})
