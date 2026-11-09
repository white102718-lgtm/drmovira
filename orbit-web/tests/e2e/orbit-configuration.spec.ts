import { test, expect } from '@playwright/test'
import path from 'node:path'

/** 完整若依登录/菜单 + 实际配置接口，不拦截或伪造API响应；只使用独立fixture账号。 */
test('保留原菜单并逐项验证配置弹窗、凭据动作、连接结果与历史', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const captchaReady = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captchaReady
  await expect(page.getByPlaceholder('验证码', { exact: true })).toHaveCount(0)
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(
    page.locator('.sidebar-container').getByText('系统管理', { exact: true }),
  ).toHaveCount(1)
  if (info.project.name === 'mobile-390') await page.locator('.hamburger-container').click()
  const sidebar = page.locator('.sidebar-container')
  await sidebar.getByText('ORBIT工作台', { exact: true }).click()
  const system = sidebar.getByText('ORBIT系统管理', { exact: true })
  if (await system.isVisible()) await system.click()
  await sidebar.getByText('系统配置', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '系统配置', exact: true })).toBeVisible()
  // 原若依移动菜单通过遮罩关闭，不修改其布局或假设路由自动收起。
  if (info.project.name === 'mobile-390') {
    await page.locator('.drawer-bg').click({ position: { x: 380, y: 100 } })
    await expect(page.locator('.drawer-bg')).toHaveCount(0)
  }
  const name = `浏览器配置-${info.project.name}`
  await page.getByRole('button', { name: '新增配置', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '新增系统配置', exact: true })
  await expect(dialog).toBeVisible()
  await dialog.getByLabel('配置名称', { exact: true }).fill(name)
  await dialog.getByLabel('模型ID', { exact: true }).fill('fixture-model')
  await dialog.locator('.el-switch').click()
  await dialog.locator('.configuration-secret .el-select__wrapper').click()
  await page.getByRole('option', { name: '替换凭据', exact: true }).click()
  await dialog
    .locator('input[type="password"][aria-label="OpenAI API Key"]')
    .fill('fixture-browser-key-not-a-real-api-key')
  await dialog.getByLabel('变更原因', { exact: true }).fill('独立浏览器fixture新增')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('搜索配置名称').fill(name)
  const row = page.locator('.el-table__body tr').filter({ hasText: name })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('已配置（不回显）')

  await row.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)

  // 第二个真实页面提交新版本，让首页面提交旧If-Match，验证失败后凭据输入释放。
  const concurrent = await page.context().newPage()
  await concurrent.goto('/orbit/system/configuration')
  await concurrent.getByPlaceholder('搜索配置名称').fill(name)
  await concurrent
    .locator('.el-table__body tr')
    .filter({ hasText: name })
    .getByRole('button', { name: '编辑', exact: true })
    .click()
  const concurrentDialog = concurrent.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await concurrentDialog.getByLabel('变更原因', { exact: true }).fill('另一个页面提交新版本')
  await concurrentDialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(concurrentDialog).toBeHidden()
  await concurrent.close()
  await dialog.locator('.configuration-secret .el-select__wrapper').click()
  await page.getByRole('option', { name: '替换凭据', exact: true }).click()
  await dialog
    .locator('input[type="password"][aria-label="OpenAI API Key"]')
    .fill('fixture-stale-key-not-a-real-api-key')
  await dialog.getByLabel('变更原因', { exact: true }).fill('旧版本应被拒绝')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(page.getByText('配置已变化，请刷新后重试', { exact: true })).toBeVisible()
  await expect(dialog.locator('input[type="password"]')).toHaveCount(0)
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  // 等关闭动画完成，并确认刷新后的真实版本，避免把旧弹窗/旧行当成可编辑新状态。
  await expect(dialog).toBeHidden()
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(row.getByRole('cell', { name: '2', exact: true })).toHaveCount(1)
  await expect(page.getByRole('button', { name: '刷新', exact: true })).not.toHaveClass(
    /is-loading/,
  )
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await dialog.getByLabel('变更原因', { exact: true }).fill('保持原凭据')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).toBeHidden()
  const probeRequests: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/test')) {
      probeRequests.push(request.postData() || '')
    }
  })
  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  let testPrompt = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  await expect(testPrompt).toContainText(name)
  await testPrompt.getByRole('button', { name: '取消', exact: true }).click()
  await expect(testPrompt).toBeHidden()
  expect(probeRequests).toHaveLength(0)
  await row.getByRole('button', { name: '只读连接测试', exact: true }).click()
  testPrompt = page.getByRole('dialog', { name: '只读连接测试', exact: true })
  await testPrompt.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(testPrompt).toContainText('测试原因必填')
  expect(probeRequests).toHaveLength(0)
  await testPrompt.getByPlaceholder('填写测试原因，请勿填写密钥或Token').fill('浏览器人工测试原因')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-test-reason.png`),
  })
  await testPrompt.getByRole('button', { name: '开始测试', exact: true }).click()
  await expect(row).toContainText('待连接器实测')
  expect(probeRequests).toHaveLength(1)
  expect(JSON.parse(probeRequests[0])).toEqual({ reason: '浏览器人工测试原因' })

  await row.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await dialog.locator('.el-switch').click()
  await dialog.locator('.configuration-secret .el-select__wrapper').click()
  await page.getByRole('option', { name: '清除凭据', exact: true }).click()
  await dialog.getByLabel('变更原因', { exact: true }).fill('清除凭据并停用')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: '确认清除凭据', exact: true })
  await expect(confirmation).toBeVisible()
  await confirmation.getByRole('button', { name: '返回检查', exact: true }).click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await page
    .getByRole('dialog', { name: '确认清除凭据', exact: true })
    .getByRole('button', { name: '清除并保存', exact: true })
    .click()
  await expect(dialog).toBeHidden()
  await expect(row).toContainText('未配置')
  await expect(row).toContainText('已停用')
  await row.getByRole('button', { name: '变更历史', exact: true }).click()
  const history = page.getByRole('dialog', { name: `${name} · 变更历史`, exact: true })
  await expect(history).toBeVisible()
  await expect(history).toContainText('清除凭据并停用')
  await expect(history).toContainText('浏览器人工测试原因')
  await history.locator('.el-table__expand-icon').first().click()
  await expect(history).toContainText('SHA256_STATE_V1')
  await expect(page.locator('body')).not.toContainText('fixture-browser-key-not-a-real-api-key')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-history.png`),
  })
  await page.keyboard.press('Escape')
  await expect(page.locator('.el-drawer:visible')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
  expect(failures).toEqual([])
  // 检查浏览器持久化存储中没有平台凭据；原若依会话Cookie不输出到报告。
  const persisted = await page.evaluate(() =>
    JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }),
  )
  expect(persisted).not.toContain('fixture-browser-key-not-a-real-api-key')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-configuration.png`),
  })
  // AI策略新增字段通过真实保存和重新打开验证；停用草稿不声称规则计数器已生效。
  await page.getByRole('button', { name: '新增配置', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '新增系统配置', exact: true })
  await dialog.locator('.el-select__wrapper').first().click()
  await page.getByRole('option', { name: 'AI建议策略', exact: true }).click()
  const policyName = `分析限制-${info.project.name}`
  await dialog.getByLabel('配置名称', { exact: true }).fill(policyName)
  await expect(dialog.getByRole('spinbutton', { name: '输入最多逐日点', exact: true })).toHaveValue(
    '28',
  )
  await expect(
    dialog.getByRole('spinbutton', { name: '输入最多证据条数', exact: true }),
  ).toHaveValue('500')
  await expect(
    dialog.getByRole('spinbutton', { name: '建议最大输出Token', exact: true }),
  ).toHaveValue('4096')
  await dialog.getByRole('spinbutton', { name: '输入最多逐日点', exact: true }).fill('7')
  await dialog.getByRole('spinbutton', { name: '输入最多证据条数', exact: true }).fill('20')
  await dialog.getByRole('spinbutton', { name: '建议最大输出Token', exact: true }).fill('1024')
  await expect(
    dialog.getByRole('spinbutton', { name: '分析冷却下限（分钟）', exact: true }),
  ).toHaveValue('60')
  await expect(
    dialog.getByRole('spinbutton', { name: '每规则每对象每日分析上限', exact: true }),
  ).toHaveValue('5')
  await dialog.getByRole('spinbutton', { name: '分析冷却下限（分钟）', exact: true }).fill('0')
  await dialog.getByRole('spinbutton', { name: '每规则每对象每日分析上限', exact: true }).fill('7')
  await dialog.getByLabel('变更原因', { exact: true }).fill('保存分析限制草稿')
  await dialog.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(dialog).toBeHidden()
  await page.getByPlaceholder('搜索配置名称').fill(policyName)
  const policyRow = page.locator('.el-table__body tr').filter({ hasText: policyName })
  await policyRow.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑系统配置', exact: true })
  await expect(dialog.getByRole('spinbutton', { name: '输入最多逐日点', exact: true })).toHaveValue(
    '7',
  )
  await expect(
    dialog.getByRole('spinbutton', { name: '输入最多证据条数', exact: true }),
  ).toHaveValue('20')
  await expect(
    dialog.getByRole('spinbutton', { name: '建议最大输出Token', exact: true }),
  ).toHaveValue('1024')
  await expect(
    dialog.getByRole('spinbutton', { name: '分析冷却下限（分钟）', exact: true }),
  ).toHaveValue('0')
  await expect(
    dialog.getByRole('spinbutton', { name: '每规则每对象每日分析上限', exact: true }),
  ).toHaveValue('7')
  await dialog
    .getByRole('spinbutton', { name: '每规则每对象每日分析上限', exact: true })
    .scrollIntoViewIfNeeded()
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-analysis-limits.png`),
  })
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
})
