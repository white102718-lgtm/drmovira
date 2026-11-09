import { test, expect, type Locator } from '@playwright/test'
import { randomUUID } from 'node:crypto'

/** D1真实UI/HTTP：不模拟响应，不直接改数据库；只保存内部配置，不执行广告。 */
test('Python投放草稿三层预算及模板分享加载归档真实闭环', async ({ page }, info) => {
  const failures: string[] = []
  const preflightWrites: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname.replace(/^.*(?=\/api\/v1\/)/, '')
    if (
      request.method() === 'POST' &&
      /\/launch-plans\/[^/]+\/(campaign-names|allocations|validate|execute)$/.test(path)
    ) {
      preflightWrites.push(path)
    }
  })
  const suffix = randomUUID().replaceAll('-', '').slice(0, 12)
  const planName = `UI_DRAFT_${suffix}`,
    templateName = `UI_TEMPLATE_${suffix}`,
    appliedName = `UI_LOADED_${suffix}`
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await page.goto('/orbit/launch')
  await expect(page.getByRole('heading', { name: '投放计划与配置模板', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新建服务器草稿', exact: true }).click()
  let editor = page.getByRole('dialog', { name: '新建投放草稿', exact: true })
  await expect(editor).toBeVisible()
  const planInput = editor.getByLabel('计划名称（草稿可空，最多100码点）', { exact: true })
  await planInput.fill('😀'.repeat(101))
  await editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
  await expect(editor).toContainText('计划名称最多100个Unicode码点')
  await planInput.fill(planName)
  await editor.getByRole('button', { name: '选择账户（0/500）', exact: true }).click()
  const accountsDialog = page.getByRole('dialog', { name: '选择投放账户', exact: true })
  const accountRead = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/accounts') &&
      response.request().method() === 'GET',
  )
  await accountsDialog.getByRole('button', { name: '查询账户', exact: true }).click()
  expect((await accountRead).status()).toBe(200)
  await accountsDialog.getByRole('button', { name: '取消本地选择', exact: true }).click()
  await expect(accountsDialog).toBeHidden()
  for (const source of [
    { button: '选择素材池（0/500）', title: '选择素材池', path: '/assets' },
    { button: '选择渠道（草稿可空）', title: '选择渠道', path: '/channels' },
  ]) {
    const received = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.endsWith(source.path) &&
        response.request().method() === 'GET',
    )
    await editor.getByRole('button', { name: source.button, exact: true }).click()
    expect((await received).status()).toBe(200)
    const dialog = page.getByRole('dialog', { name: source.title, exact: true })
    await expect(dialog.getByRole('status')).toHaveAttribute('aria-busy', 'false')
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  async function choose(input: Locator, option: string) {
    await input.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: option, exact: true }).click()
  }
  await editor.getByRole('button', { name: '新增系列', exact: true }).click()
  await choose(editor.getByLabel('投放目标', { exact: true }), '销量')
  await choose(editor.getByLabel('购买方式', { exact: true }), '竞价 AUCTION')
  await editor.getByRole('button', { name: '配置预算', exact: true }).click()
  const budget = page.getByRole('dialog', { name: '配置预算', exact: true })
  await budget.getByLabel('金额（十进制字符串）', { exact: true }).fill('12.340000')
  await budget.getByLabel('币种', { exact: true }).fill('USD')
  await expect(budget.getByLabel('预算拥有者', { exact: true })).toBeDisabled()
  await budget.getByRole('button', { name: '确认预算配置', exact: true }).click()
  await editor.getByRole('button', { name: '新增广告组', exact: true }).click()
  await editor.getByLabel('广告组名称（最多200码点）', { exact: true }).fill('真实广告组')
  await editor.getByRole('button', { name: '新增广告', exact: true }).click()
  await editor.getByLabel('广告名称（最多200码点）', { exact: true }).fill('真实广告配置')
  await editor.getByLabel('标题（最多100码点）', { exact: true }).fill('😀'.repeat(100))
  await editor.getByLabel('正文（最多2000码点，保留换行）', { exact: true }).fill('第一行\n第二行')
  await editor.getByRole('button', { name: '复制配置', exact: true }).click()
  const created = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/launch-plans') &&
      response.request().method() === 'POST',
  )
  await editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
  const createResponse = await created
  expect(createResponse.status()).toBe(201)
  const original = await createResponse.json()
  expect(original.state).toBe('DRAFT')
  expect(original.activate_after_create).toBe(false)
  expect(original.account_ids).toEqual([])
  expect(original.asset_ids).toEqual([])
  expect(original.campaigns[0].budget.amount).toBe('12.340000')
  expect(original.campaigns[0].adsets[0].ads).toHaveLength(2)
  expect(original.campaigns[0].adsets[0].ads[0].title).toBe('😀'.repeat(100))
  expect(original.campaigns[0].adsets[0].ads[0].local_id).not.toBe(
    original.campaigns[0].adsets[0].ads[1].local_id,
  )
  // 首次保存返回真实ID后，抽屉切换为编辑标题，重新按可访问名称定位。
  editor = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
  await expect(editor).toContainText('服务器已保存')
  await editor.getByRole('button', { name: '从当前配置另存模板', exact: true }).click()
  const templateEditor = page.getByRole('dialog', { name: '保存配置模板', exact: true })
  await templateEditor.getByLabel('模板名称（1—80码点）', { exact: true }).fill(templateName)
  await templateEditor
    .getByLabel('说明（最多500码点，允许LF）', { exact: true })
    .fill('真实配置模板\n保留预算及三层结构')
  const savedTemplate = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith('/templates') &&
      response.request().method() === 'POST',
  )
  await templateEditor.getByRole('button', { name: '保存模板', exact: true }).click()
  const templateResponse = await savedTemplate
  expect(templateResponse.status()).toBe(201)
  const template = await templateResponse.json()
  expect(template.visibility).toBe('PRIVATE')
  expect(template).not.toHaveProperty('account_ids')
  expect(template).not.toHaveProperty('identity_bindings')
  await expect(templateEditor).toBeHidden()
  editor = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
  await editor.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(editor).toBeHidden()
  await page.getByRole('tab', { name: '配置模板', exact: true }).click()
  const templateSearch = page.getByPlaceholder('搜索模板名称', { exact: true })
  await templateSearch.fill(templateName)
  await templateSearch.press('Enter')
  let templateRow = page
    .locator('.template-panel .el-table__body tr')
    .filter({ hasText: templateName })
  await expect(templateRow).toHaveCount(1)
  const recipientRead = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith('/templates/recipient-options'),
  )
  await templateRow.getByRole('button', { name: '分享', exact: true }).click()
  const recipientResponse = await recipientRead
  expect(recipientResponse.status()).toBe(200)
  const members = await recipientResponse.json()
  expect(members.items.length).toBeGreaterThan(0)
  const shareDialog = page.getByRole('dialog', { name: '分享配置模板', exact: true })
  await expect(shareDialog.getByRole('status', { name: '操作候选读取状态' })).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await shareDialog
    .getByLabel('明确接收者（至少1人）', { exact: true })
    .locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]')
    .click()
  await page.getByRole('option').first().click()
  const shareReason = shareDialog.getByLabel('操作原因（1—1000码点）', { exact: true })
  // 真实点击触发多选弹层clickoutside，避免其焦点陷阱把fill的键盘输入接回搜索框。
  await shareReason.click()
  await expect(shareDialog.getByLabel('明确接收者（至少1人）', { exact: true })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  await expect(shareReason).toBeFocused()
  await shareReason.fill('浏览器确认真实共享')
  await expect(shareReason).toHaveValue('浏览器确认真实共享')
  await shareReason.press('Tab')
  await expect(shareDialog.getByRole('status', { name: '操作原因输入状态' })).toHaveText(
    '已输入 9/1000 码点',
  )
  await expect(shareReason).toHaveValue('浏览器确认真实共享')
  const shareWrite = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/templates/${template.id}/share`),
  )
  await shareDialog.getByRole('button', { name: '确认分享', exact: true }).click()
  const shareResponse = await shareWrite
  expect(shareResponse.status()).toBe(200)
  expect((await shareResponse.json()).recipient_user_ids).toContain(members.items[0].id)
  await expect(shareDialog).toBeHidden()
  templateRow = page.locator('.template-panel .el-table__body tr').filter({ hasText: templateName })
  await templateRow.getByRole('button', { name: '加载为新草稿', exact: true }).click()
  const applyDialog = page.getByRole('dialog', { name: '从模板创建新草稿', exact: true })
  await expect(applyDialog.getByRole('status', { name: '操作候选读取状态' })).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await applyDialog.getByLabel('操作原因（1—1000码点）', { exact: true }).fill('浏览器加载真实配置')
  const applied = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/templates/${template.id}/apply`),
  )
  await applyDialog.getByRole('button', { name: '确认创建草稿', exact: true }).click()
  const applyResponse = await applied
  expect(applyResponse.status()).toBe(201)
  const newPlan = await applyResponse.json()
  expect(newPlan.id).not.toBe(original.id)
  expect(newPlan.state).toBe('DRAFT')
  expect(newPlan.account_ids).toEqual([])
  expect(newPlan.identity_bindings).toEqual([])
  expect(newPlan.asset_ids).toEqual([])
  expect(newPlan.channel_id).toBeNull()
  expect(newPlan.campaigns[0].local_id).not.toBe(template.campaigns[0].local_id)
  editor = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
  await editor.getByLabel('计划名称（草稿可空，最多100码点）', { exact: true }).fill(appliedName)
  const rename = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith(`/launch-plans/${newPlan.id}`) &&
      response.request().method() === 'PUT',
  )
  await editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
  expect((await rename).status()).toBe(200)
  await expect(editor).toContainText('服务器已保存')
  await editor.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(editor).toBeHidden()
  await page.getByRole('tab', { name: '配置模板', exact: true }).click()
  templateRow = page.locator('.template-panel .el-table__body tr').filter({ hasText: templateName })
  await templateRow.getByRole('button', { name: '归档', exact: true }).click()
  const archiveDialog = page.getByRole('dialog', { name: '归档模板', exact: true })
  await archiveDialog
    .getByLabel('操作原因（1—1000码点）', { exact: true })
    .fill('浏览器归档保留已应用计划')
  const archive = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/templates/${template.id}/archive`),
  )
  await archiveDialog.getByRole('button', { name: '确认归档', exact: true }).click()
  expect((await archive).status()).toBe(200)
  await expect(archiveDialog).toBeHidden()
  await page.getByRole('tab', { name: '计划与草稿', exact: true }).click()
  const planSearch = page.getByPlaceholder('搜索计划名称', { exact: true })
  await planSearch.fill(appliedName)
  await planSearch.press('Enter')
  const planRow = page
    .locator('.launch-page .el-tab-pane .el-table__body tr')
    .filter({ hasText: appliedName })
  await expect(planRow).toHaveCount(1)
  // 正式来源仍缺失：真实能力门禁须关闭入口，不能偷偷执行任一预检/创建阶段。
  await expect(planRow.getByRole('button', { name: '投放预检', exact: true })).toBeDisabled()
  await expect(
    page.getByRole('alert').filter({ hasText: '预检依赖尚未就绪或当前账号没有计划编辑权限' }),
  ).toBeVisible()
  const detailRead = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith(`/launch-plans/${newPlan.id}`) &&
      response.request().method() === 'GET',
  )
  await planRow.getByRole('button', { name: '详情', exact: true }).click()
  const detailResponse = await detailRead
  expect(detailResponse.status()).toBe(200)
  const immutable = await detailResponse.json()
  expect(immutable.campaigns[0].adsets[0].ads[0].title).toBe('😀'.repeat(100))
  const detail = page.getByRole('dialog', { name: '投放计划详情', exact: true })
  await expect(
    detail.getByLabel('计划名称（草稿可空，最多100码点）', { exact: true }),
  ).toBeDisabled()
  await expect(detail.getByRole('button', { name: '保存服务器草稿', exact: true })).toHaveCount(0)
  const viewport = page.viewportSize()!
  // 详情GET结束不等于右侧抽屉动画结束；按真实几何等待入视口，不加固定延时或放宽边界。
  await expect
    .poll(async () => {
      const box = await detail.boundingBox()
      return box ? Math.max(-box.x, box.x + box.width - viewport.width) : Number.POSITIVE_INFINITY
    })
    .toBeLessThanOrEqual(2)
  const bounds = await detail.boundingBox()
  expect(bounds!.x).toBeGreaterThanOrEqual(0)
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    viewport.width + 2,
  )
  expect(failures).toEqual([])
  expect(preflightWrites).toEqual([])
  await page.screenshot({
    path: info.outputPath(`launch-draft-template-${info.project.name}.png`),
    fullPage: true,
  })
})

/** 数据由父工具在本轮UUID库准备；这里只验证真实列表，不把种子记录算创建功能。 */
test('Python计划模板四档分页历史及UTC筛选真实闭环', async ({ page }, info) => {
  // 仅记录本专项固定API路径和网络状态，不记录查询、请求头、正文或凭据。
  const network: { method: string; path: string; status?: number; failure?: string }[] = []
  const observedPaths = new Set([
    '/api/v1/launch-plans',
    '/api/v1/launch-plans/capabilities',
    '/api/v1/templates',
    '/api/v1/templates/capabilities',
  ])
  page.on('requestfailed', (request) => {
    const path = new URL(request.url()).pathname.replace(/^.*(?=\/api\/v1\/)/, '')
    if (observedPaths.has(path)) {
      network.push({ method: request.method(), path, failure: request.failure()?.errorText })
    }
  })
  page.on('response', (response) => {
    const path = new URL(response.url()).pathname.replace(/^.*(?=\/api\/v1\/)/, '')
    if (observedPaths.has(path)) {
      network.push({ method: response.request().method(), path, status: response.status() })
    }
  })
  page.on('close', () => {
    console.log('pagination-network', JSON.stringify(network))
  })
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/launch')
  await expect(page.getByRole('heading', { name: '投放计划与配置模板', exact: true })).toBeVisible()

  async function readList(path: string, action: () => Promise<unknown>) {
    const response = page.waitForResponse(
      (item) => new URL(item.url()).pathname.endsWith(path) && item.request().method() === 'GET',
    )
    await action()
    const actual = await response
    expect(actual.status()).toBe(200)
    return { body: await actual.json(), url: new URL(actual.url()) }
  }
  async function chooseSize(label: string, size: number) {
    await page
      .getByRole('combobox', { name: label, exact: true })
      .locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]')
      .click()
    await page.getByRole('option', { name: `${size}个`, exact: true }).click()
  }
  for (const kind of ['计划', '模板'] as const) {
    if (kind === '模板') await page.getByRole('tab', { name: '配置模板', exact: true }).click()
    const path = kind === '计划' ? '/launch-plans' : '/templates'
    const prefix = kind === '计划' ? 'UI_PAGE_PLAN_' : 'UI_PAGE_TEMPLATE_'
    const table = page.locator(
      kind === '计划'
        ? '.launch-page .el-tab-pane .el-table__body tr'
        : '.template-panel .el-table__body tr',
    )
    const input = page.getByPlaceholder(`搜索${kind}名称`, { exact: true })
    await input.fill(prefix)
    const first = await readList(path, () => input.press('Enter'))
    expect(first.url.searchParams.get('page_size')).toBe('20')
    expect(first.body.items).toHaveLength(20)
    expect(first.body.next_cursor).toEqual(expect.any(String))
    const firstIds = first.body.items.map((item: { id: string }) => item.id)
    await expect(table).toHaveCount(20)
    const next = await readList(path, () =>
      page.getByRole('button', { name: `下一页${kind}`, exact: true }).click(),
    )
    expect(next.body.items).toHaveLength(1)
    expect(next.url.searchParams.get('cursor')).toBe(first.body.next_cursor)
    await expect(table).toHaveCount(1)
    const previous = await readList(path, () =>
      page.getByRole('button', { name: `上一页${kind}`, exact: true }).click(),
    )
    expect(previous.body.items.map((item: { id: string }) => item.id)).toEqual(firstIds)
    expect(previous.url.searchParams.has('cursor')).toBe(false)
    for (const size of [50, 100, 200]) {
      const larger = await readList(path, () => chooseSize(`每页${kind}数量`, size))
      expect(larger.url.searchParams.get('page_size')).toBe(String(size))
      expect(larger.url.searchParams.has('cursor')).toBe(false)
      expect(larger.body.items).toHaveLength(21)
      await expect(table).toHaveCount(21)
    }
    if (kind === '模板') {
      for (const [day, count] of [
        ['2020-01-01', 0],
        ['2026-01-02', 21],
      ] as const) {
        if (count === 21) {
          const dateEditor = page.locator('.template-tools .el-date-editor')
          await dateEditor.hover()
          await dateEditor.locator('.el-range__close-icon').click()
          await expect(page.getByPlaceholder('模板创建日期起（UTC）', { exact: true })).toHaveValue(
            '',
          )
        }
        await page.getByPlaceholder('模板创建日期起（UTC）', { exact: true }).fill(day)
        await page.getByPlaceholder('模板创建日期止（UTC）', { exact: true }).fill(day)
        // Element Plus范围输入须确认编辑后才发布model；先完成用户的日期输入，再查询。
        await page.getByPlaceholder('模板创建日期止（UTC）', { exact: true }).press('Enter')
        // 窄屏面板覆盖查询按钮；正常点击面板外完成编辑，Escape会取消本次输入。
        await page.getByRole('heading', { name: '投放计划与配置模板', exact: true }).click()
        await expect(page.locator('.el-date-range-picker:visible')).toHaveCount(0)
        const filtered = await readList(path, () =>
          page.getByRole('button', { name: '查询模板', exact: true }).click(),
        )
        expect(filtered.url.searchParams.get('date_from')).toBe(day)
        expect(filtered.url.searchParams.get('date_to')).toBe(day)
        expect(filtered.body.items).toHaveLength(count)
      }
      const firstRow = table.first()
      const detailResponse = page.waitForResponse(
        (item) =>
          /\/templates\/[a-f0-9-]+$/.test(new URL(item.url()).pathname) &&
          item.request().method() === 'GET',
      )
      await firstRow.getByRole('button', { name: '详情', exact: true }).click()
      const response = await detailResponse
      expect(response.status()).toBe(200)
      const template = await response.json()
      const detail = page.getByRole('dialog', { name: '模板详情', exact: true })
      for (const id of [
        template.id,
        template.ownership.owner_user_id,
        template.ownership.owner_team_id,
      ]) {
        await expect(detail.locator('.template-metadata')).toContainText(id)
      }
      await expect(detail.locator('.template-metadata')).toContainText('1 / ACTIVE')
      await detail.getByRole('button', { name: '关闭', exact: true }).click()
    }
  }
  const viewport = page.viewportSize()!
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    viewport.width + 2,
  )
  await page.screenshot({
    path: info.outputPath(`launch-pagination-${info.project.name}.png`),
    fullPage: true,
  })
})

/** 原025快照→计划实际IDs；账户样本由父工具准备，浏览器不拦截或伪造接口。 */
test('Python投放账户跨页选择及501快照拒绝和21账户解析真实闭环', async ({ page }, info) => {
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/launch')
  await page.getByRole('button', { name: '新建服务器草稿', exact: true }).click()
  let editor = page.getByRole('dialog', { name: '新建投放草稿', exact: true })
  await editor
    .getByLabel('计划名称（草稿可空，最多100码点）', { exact: true })
    .fill(`UI_SCOPE_PLAN_${randomUUID().slice(0, 8)}`)
  async function responseFor(path: RegExp, method: string, action: () => Promise<unknown>) {
    const pending = page.waitForResponse(
      (item) => path.test(new URL(item.url()).pathname) && item.request().method() === method,
    )
    await action()
    const response = await pending
    expect(response.status()).toBe(method === 'POST' ? 201 : 200)
    return { response, body: await response.json() }
  }
  async function chooseNumber(select: Locator, value: number) {
    await select.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: String(value), exact: true }).click()
  }
  async function toggleFirstAccount() {
    // Element Plus使用隐藏原生input；用户点击可见label，仍用真实input核对勾选状态。
    await picker.locator('label.el-checkbox:visible').first().click()
  }
  await editor.getByRole('button', { name: '选择账户（0/500）', exact: true }).click()
  const picker = page.getByRole('dialog', { name: '选择投放账户', exact: true })
  await expect(picker).toBeVisible()
  await picker.getByLabel('账户名称或平台账户ID', { exact: true }).fill('UI_SCOPE_OK_')
  await chooseNumber(picker.getByLabel('每页账户数', { exact: true }), 20)
  const first = await responseFor(/\/accounts$/, 'GET', () =>
    picker.getByRole('button', { name: '查询账户', exact: true }).click(),
  )
  expect(first.body.items).toHaveLength(20)
  expect(first.body.next_cursor).toEqual(expect.any(String))
  await toggleFirstAccount()
  const next = await responseFor(/\/accounts$/, 'GET', () =>
    picker.getByRole('button', { name: '下一页账户', exact: true }).click(),
  )
  expect(next.body.items).toHaveLength(1)
  await toggleFirstAccount()
  await expect(picker.getByRole('status')).toHaveText('已明确勾选 2 / 500 个账户')
  const previous = await responseFor(/\/accounts$/, 'GET', () =>
    picker.getByRole('button', { name: '上一页账户', exact: true }).click(),
  )
  expect(previous.body.items.map((item: { id: string }) => item.id)).toEqual(
    first.body.items.map((item: { id: string }) => item.id),
  )
  await expect(picker.getByRole('checkbox').first()).toBeChecked()
  await toggleFirstAccount()
  await expect(picker.getByRole('status')).toHaveText('已明确勾选 1 / 500 个账户')
  await toggleFirstAccount()
  await picker.getByRole('button', { name: '应用到账户选择', exact: true }).click()
  await expect(picker).toBeHidden()
  await expect(editor.getByRole('button', { name: '选择账户（2/500）', exact: true })).toBeVisible()

  await editor.getByRole('button', { name: '选择账户（2/500）', exact: true }).click()
  const filterRadio = picker.getByRole('radio', { name: '按条件冻结', exact: true })
  await filterRadio.locator('xpath=ancestor::label[1]').click()
  await expect(filterRadio).toBeChecked()
  await picker.getByLabel('账户名称或平台账户ID', { exact: true }).fill('UI_SCOPE_OVER_')
  const oversized = await responseFor(/\/scope-snapshots$/, 'POST', () =>
    picker.getByRole('button', { name: '冻结并核对完整范围', exact: true }).click(),
  )
  expect(oversized.body.count).toBe(501)
  expect(oversized.response.request().postDataJSON()).toMatchObject({
    mode: 'FILTER',
    account_ids: [],
    filter: { q: 'UI_SCOPE_OVER_' },
  })
  await expect(picker).toContainText('此快照不会截断')
  await expect(picker.getByRole('button', { name: '应用到账户选择', exact: true })).toBeDisabled()
  await picker.getByLabel('账户名称或平台账户ID', { exact: true }).fill('UI_SCOPE_OK_')
  const frozen = await responseFor(/\/scope-snapshots$/, 'POST', () =>
    picker.getByRole('button', { name: '冻结并核对完整范围', exact: true }).click(),
  )
  expect(frozen.body.count).toBe(21)
  await expect(picker).toContainText(frozen.body.id)
  await expect(picker).toContainText(frozen.body.hash)
  await chooseNumber(picker.getByRole('combobox', { name: '每页成员数', exact: true }), 20)
  const members = await responseFor(/\/scope-snapshots\/[^/]+\/members$/, 'GET', () =>
    picker.getByRole('button', { name: '查询成员', exact: true }).click(),
  )
  expect(members.body.items).toHaveLength(20)
  const tail = await responseFor(/\/scope-snapshots\/[^/]+\/members$/, 'GET', () =>
    picker.getByRole('button', { name: '下一页成员', exact: true }).click(),
  )
  expect(tail.body.items).toHaveLength(1)
  await responseFor(/\/scope-snapshots\/[^/]+\/members$/, 'GET', () =>
    picker.getByRole('button', { name: '上一页成员', exact: true }).click(),
  )
  await picker.getByRole('button', { name: '应用到账户选择', exact: true }).click()
  await expect(picker).toBeHidden()
  const created = await responseFor(/\/launch-plans$/, 'POST', () =>
    editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click(),
  )
  expect(created.response.request().postDataJSON()).toMatchObject({
    account_ids: [],
    account_scope_snapshot_id: frozen.body.id,
  })
  expect(created.body.account_ids).toHaveLength(21)
  expect(created.body.account_scope_snapshot_id).toBeNull()
  editor = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
  await expect(
    editor.getByRole('button', { name: '选择账户（21/500）', exact: true }),
  ).toBeVisible()
  // 真实修改后再保存以验证新CAS；完全相同配置的幂等无变化PUT不应强求增加版本。
  await editor
    .getByLabel('计划名称（草稿可空，最多100码点）', { exact: true })
    .fill(`${created.body.name}_修改`)
  const updatedResponse = page.waitForResponse(
    (item) =>
      new URL(item.url()).pathname.endsWith(`/launch-plans/${created.body.id}`) &&
      item.request().method() === 'PUT',
  )
  await editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
  const updated = await updatedResponse
  expect(updated.status()).toBe(200)
  expect(updated.request().postDataJSON().account_ids).toEqual(created.body.account_ids)
  expect(updated.request().postDataJSON().account_scope_snapshot_id).toBeNull()
  expect((await updated.json()).revision).toBe(created.body.revision + 1)
  const viewport = page.viewportSize()!
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    viewport.width + 2,
  )
  await page.screenshot({
    path: info.outputPath(`launch-account-scope-${info.project.name}.png`),
    fullPage: true,
  })
})
