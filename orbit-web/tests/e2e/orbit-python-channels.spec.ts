import { test, expect, type Page, type Locator } from '@playwright/test'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

/** 只连接真实Python与专属MySQL；预检、提交、所有渠道弹窗均经界面操作。 */
test('Python引用导入到渠道创建编辑分配停用的完整页面闭环', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const tenant = '00000000-0000-0000-0000-000000000001'
  const namespace = `${info.project.name}-${randomUUID().slice(0, 8)}`
  const agentId = randomUUID(),
    productId = randomUUID()
  const agentName = `浏览器总代-${namespace}`,
    productName = `浏览器产品-${namespace}`
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/system/dictionaries')
  await expect(
    page.locator('.reference-page .el-card__header').getByText('字典与引用资料', { exact: true }),
  ).toBeVisible()

  const record = (kind: string, id: string, name: string) => ({
    kind,
    id,
    name,
    source_key: `browser-${id}`,
    availability: 'AVAILABLE',
    owner_team_id: tenant,
    data_owner_user_ids: [tenant],
    ...(kind === 'PRODUCT' ? { allowed_agent_ids: [agentId] } : {}),
  })
  async function choose(target: Locator, label: string) {
    // Element Plus的readonly输入由placeholder覆盖；点击实际可见选择框，保留真实交互。
    await target.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: label, exact: true }).click()
  }
  async function checkDialog(dialog: Locator) {
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
  }
  async function importRecord(
    kind: 'PRODUCT' | 'BUSINESS_AGENT',
    id: string,
    name: string,
    rejectFirst = false,
  ) {
    await page.getByRole('button', { name: '导入预检', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '引用资料导入预检', exact: true })
    await choose(dialog.getByLabel('类别', { exact: true }), kind === 'PRODUCT' ? '产品' : '总代')
    await dialog.getByLabel('来源（必填，可追溯）', { exact: true }).fill(`浏览器界面-${namespace}`)
    await dialog.getByLabel('导入原因（必填）', { exact: true }).fill('真实页面导入闭环验收')
    const json = dialog.getByLabel('JSON资料数组（1—500行，总正文不超过2MiB）', { exact: true })
    const item = record(kind, id, name)
    await json.fill(JSON.stringify(rejectFirst ? [item, item] : [item]))
    await dialog.getByRole('button', { name: '开始预检', exact: true }).click()
    if (rejectFirst) {
      await expect(dialog).toContainText('预检拒绝，请修正问题')
      await expect(dialog).toContainText('DUPLICATE_VALUE')
      await expect(
        dialog.getByRole('button', { name: '确认差异并原子提交', exact: true }),
      ).toHaveCount(0)
      await dialog.getByRole('button', { name: '修改后重新预检', exact: true }).click()
      await json.fill(JSON.stringify([item]))
      await dialog.getByRole('button', { name: '开始预检', exact: true }).click()
    }
    await expect(dialog).toContainText('预检通过，尚未提交')
    await expect(dialog).toContainText('本次变更差异')
    await expect(dialog).toContainText(name)
    await checkDialog(dialog)
    if (kind === 'PRODUCT')
      await page.screenshot({
        path: path.join(
          process.env.ORBIT_E2E_OUTPUT!,
          `reference-differences-${info.project.name}.png`,
        ),
        animations: 'disabled',
      })
    await dialog.getByRole('button', { name: '确认差异并原子提交', exact: true }).click()
    await expect(dialog).toContainText('目录已原子提交成功')
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  await importRecord('BUSINESS_AGENT', agentId, agentName, true)
  await importRecord('PRODUCT', productId, productName)
  await page.goto('/orbit/channels')
  await expect(
    page.locator('.channels-page .el-card__header').getByText('渠道管理', { exact: true }),
  ).toBeVisible()
  const ownersResponse = page.waitForResponse((response) =>
    response.url().includes('/channels/ownership-options'),
  )
  await page.getByRole('button', { name: '新增渠道', exact: true }).click()
  const ownerOptions = (await (await ownersResponse).json()).items
  const root = ownerOptions.find((item: { id: string }) => item.id === tenant)
  expect(root).toBeTruthy()
  const create = page.getByRole('dialog', { name: '新增渠道', exact: true })
  const code = `UI_${namespace.replaceAll('-', '_')}`
  await create.getByLabel('渠道ID（必填，同租户唯一）', { exact: true }).fill(code)
  await create.getByLabel('渠道名称', { exact: true }).fill(`渠道-${namespace}`)
  await choose(create.getByLabel('归属团队', { exact: true }), root.team_name)
  await choose(
    create.getByLabel('分配用户（1—500名）', { exact: true }),
    root.display_name || root.id,
  )
  await page.keyboard.press('Escape')
  await choose(create.getByLabel('产品（必填）', { exact: true }), productName)
  await choose(create.getByLabel('总代（仅限产品已关联）', { exact: true }), agentName)
  await create
    .getByLabel('HTTPS投放链接（不自动追加参数，不覆盖已保存计划）', { exact: true })
    .fill('http://example.com/unsafe')
  await create.getByRole('button', { name: '保存', exact: true }).click()
  await expect(create).toContainText('请输入无凭据且参数编码有效的公网HTTPS链接')
  await create
    .getByLabel('HTTPS投放链接（不自动追加参数，不覆盖已保存计划）', { exact: true })
    .fill(`https://example.com/landing?original=${namespace}`)
  await checkDialog(create)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `channel-create-${info.project.name}.png`),
    animations: 'disabled',
  })
  await create.getByRole('button', { name: '保存', exact: true }).click()
  await expect(create).toBeHidden()
  const row = () => page.locator('.el-table__body tr').filter({ hasText: code })
  await expect(row()).toHaveCount(1)
  await row().getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '渠道详情', exact: true })
  await expect(detail).toContainText(code)
  await expect(detail).toContainText('https://example.com/landing?original=')
  await expect(detail).toContainText('创建UTC时间')
  await expect(detail).toContainText('历史产品绑定')
  await expect(detail).toContainText('当前未锁定')
  await expect(detail).toContainText('产品引用状态')
  await page.keyboard.press('Escape')
  await expect(detail).toBeHidden()
  await row().getByRole('button', { name: '编辑', exact: true }).click()
  const edit = page.getByRole('dialog', { name: '编辑渠道', exact: true })
  await edit.getByLabel('渠道名称', { exact: true }).fill('😀'.repeat(101))
  await edit.getByRole('button', { name: '保存', exact: true }).click()
  await expect(edit).toContainText('渠道名称最多100个字符')
  await edit.getByLabel('渠道名称', { exact: true }).fill('😀'.repeat(100))
  await expect(edit.getByLabel('渠道名称', { exact: true })).toHaveValue('😀'.repeat(100))
  await edit.getByRole('button', { name: '保存', exact: true }).click()
  await expect(edit).toBeHidden()
  await expect(row()).toContainText('😀'.repeat(100))
  await row().getByRole('button', { name: '分配', exact: true }).click()
  const assignment = page.getByRole('dialog', { name: '分配渠道', exact: true })
  await expect(assignment.getByLabel('分配用户', { exact: true })).toBeVisible()
  await assignment.getByLabel('原因（必填）', { exact: true }).fill('核对当前团队与拥有者')
  await checkDialog(assignment)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `channel-assignment-${info.project.name}.png`),
    animations: 'disabled',
  })
  await assignment.getByRole('button', { name: '确认', exact: true }).click()
  await expect(assignment).toBeHidden()
  await row().getByRole('button', { name: '停用', exact: true }).click()
  const archive = page.getByRole('dialog', { name: '停用渠道', exact: true })
  await archive.getByLabel('原因（必填）', { exact: true }).fill('本次浏览器验收结束，保留历史')
  await archive.getByRole('button', { name: '确认', exact: true }).click()
  await expect(archive).toBeHidden()
  await expect(row()).toContainText('停用')
  await expect(row()).toContainText(`https://example.com/landing?original=${namespace}`)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(failures).toEqual([])
})
