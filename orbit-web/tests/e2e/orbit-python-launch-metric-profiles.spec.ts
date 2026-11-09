import { randomUUID } from 'node:crypto'
import { test, expect, type Locator, type Page, type Response } from '@playwright/test'
import type { LaunchPlan } from '../../src/api/orbit/launch'
import type { LaunchTemplate } from '../../src/api/orbit/templates'
import type { MetricProfilePage } from '../../src/api/orbit/metric-profiles'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 真实隔离后端原API；只写内部草稿/模板，不调用命名、分配、预检或广告执行。 */
if (
  process.env.ORBIT_E2E_LAUNCH_METRIC_PROFILES !== '1' ||
  !process.env.ORBIT_E2E_LAUNCH_METRIC_WRITER_USERNAME ||
  !/^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(
    process.env.ORBIT_E2E_LAUNCH_METRIC_PROFILE_ID ?? '',
  )
) {
  throw new Error('必须由主线注入独立指标选择浏览器fixture及无目录权限身份')
}
const profilesPath = '/api/v1/metric-profiles',
  plansPath = '/api/v1/launch-plans',
  templatesPath = '/api/v1/templates'
const apiPath = (url: string) => {
  const path = new URL(url).pathname
  return path.startsWith('/dev-api/') ? path.slice('/dev-api'.length) : path
}
const match = (response: Response, method: string, path: string) =>
  response.request().method() === method && apiPath(response.url()) === path
type NativeUser = { permissions: string[]; isDefaultModifyPwd: boolean; isPasswordExpired: boolean }
async function notice(page: Page, response: Response, monitor: boolean) {
  expect(response.status()).toBe(200)
  const user = (await response.json()) as NativeUser
  expect(user.permissions.some((value) => value === '*:*:*' || value === 'monitor.read')).toBe(
    monitor,
  )
  expect(user.permissions.some((value) => value === '*:*:*' || value === 'launch.create')).toBe(
    true,
  )
  expect(typeof user.isDefaultModifyPwd).toBe('boolean')
  expect(typeof user.isPasswordExpired).toBe('boolean')
  const dialog = page.getByRole('dialog', { name: '安全提示', exact: true })
  if (user.isDefaultModifyPwd || user.isPasswordExpired) {
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('.el-message-box__message')).toHaveText(
      user.isDefaultModifyPwd
        ? '您的密码还是初始密码，请修改密码！'
        : '您的密码已过期，请尽快修改密码！',
    )
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await expect(dialog).toBeHidden()
  } else await expect(dialog).toBeHidden()
}
async function enter(page: Page, monitor = true) {
  const captcha = page.waitForResponse((response) => match(response, 'GET', '/captchaImage'))
  await page.goto('/login')
  await captcha
  await page
    .getByPlaceholder('账号', { exact: true })
    .fill(monitor ? 'admin' : process.env.ORBIT_E2E_LAUNCH_METRIC_WRITER_USERNAME!)
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  const info = page.waitForResponse((response) => match(response, 'GET', '/getInfo'))
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await notice(page, await info, monitor)
  const shell = page.locator('.app-wrapper')
  if ((await shell.getAttribute('class'))?.includes('hideSidebar')) {
    await page.locator('#hamburger-container').click()
    await expect(shell).toHaveClass(/openSidebar/)
  }
  const sidebar = page.locator('.sidebar-container')
  const title = sidebar.locator('.el-sub-menu__title').filter({ hasText: 'ORBIT工作台' })
  const menu = title.locator('..')
  if ((await menu.getAttribute('aria-expanded')) !== 'true') await title.click()
  await expect(menu).toHaveAttribute('aria-expanded', 'true')
  const link = sidebar.locator('a[href="/orbit/launch"]')
  await expect(link).toBeVisible()
  await expect(link).toContainText('投放管理')
  const capabilities = page.waitForResponse((response) =>
    match(response, 'GET', plansPath + '/capabilities'),
  )
  await link.click()
  await expect(page).toHaveURL(/\/orbit\/launch$/)
  expect((await capabilities).status()).toBe(200)
  await expect(page.getByRole('heading', { name: '投放计划与配置模板', exact: true })).toBeVisible()
  // 原手机导航不会自动收栏；点侧栏之外的真实遮罩，中心点可能仍被侧栏覆盖。
  if (
    (await shell.getAttribute('class'))?.includes('mobile') &&
    (await shell.getAttribute('class'))?.includes('openSidebar')
  ) {
    const background = page.locator('.drawer-bg')
    await expect(background).toBeVisible()
    const box = await background.boundingBox()
    expect(box).not.toBeNull()
    await background.click({ position: { x: box!.width - 12, y: 12 } })
    await expect(shell).toHaveClass(/hideSidebar/)
    await expect(background).toHaveCount(0)
  }
  await expect(page.getByRole('button', { name: '新建服务器草稿', exact: true })).toBeEnabled()
}
function noPlatformWrites(page: Page) {
  const writes: string[] = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      /^\/api\/v1\/launch-plans\/[^/]+\/(campaign-names|allocations|validate|execute)$/.test(
        apiPath(request.url()),
      )
    )
      writes.push('unexpected-launch-action')
  })
  return writes
}
async function structure(editor: Locator) {
  await editor.getByRole('button', { name: '新增系列', exact: true }).click()
  await editor.getByRole('button', { name: '新增广告组', exact: true }).click()
  await editor.getByLabel('广告组名称（最多200码点）', { exact: true }).fill('指标引用组')
}
async function chooseProfile(page: Page, editor: Locator) {
  const read = page.waitForResponse((response) => match(response, 'GET', profilesPath))
  await editor.getByRole('button', { name: '从指标目录选择', exact: true }).click()
  const response = await read
  expect(response.status()).toBe(200)
  const body = (await response.json()) as MetricProfilePage
  expect(body.items).toHaveLength(21)
  expect(body.next_cursor).toBeNull()
  const chosen = body.items[0]
  expect(chosen.source).toBe('FIXTURE')
  const picker = page.getByRole('dialog', { name: '选择广告组指标配置', exact: true })
  await expect(picker).toBeVisible()
  await expect(picker).toContainText('即使verified=true也不代表真实平台验证')
  const row = picker.locator('.el-table__body tr').filter({ hasText: chosen.id })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '查看并选择', exact: true }).click()
  const detail = picker.locator('.metric-detail')
  await expect(detail.locator('.el-descriptions__label')).toHaveCount(12)
  await expect(detail).toContainText(chosen.id)
  await expect(detail).toContainText(chosen.version)
  await expect(detail).toContainText('FIXTURE（隔离样本，非真实平台验证）')
  for (const [key, value] of Object.entries(chosen)) {
    if (key === 'source') continue
    const rendered =
      value === null ? '未知（null）' : Array.isArray(value) ? value.join('、') : String(value)
    await expect(detail).toContainText(rendered)
  }
  await picker.getByRole('button', { name: '使用此指标配置', exact: true }).click()
  await expect(picker).toBeHidden()
  await expect(
    editor.getByRole('textbox', { name: '指标配置ID（草稿可空）', exact: true }),
  ).toHaveValue(chosen.id)
  return chosen.id
}
async function planEditor(page: Page, name: string) {
  await page.getByRole('button', { name: '新建服务器草稿', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '新建投放草稿', exact: true })
  await expect(editor).toBeVisible()
  await editor.getByLabel('计划名称（草稿可空，最多100码点）', { exact: true }).fill(name)
  await structure(editor)
  return editor
}
async function createPlan(page: Page, editor: Locator, profile: string) {
  const response = page.waitForResponse((value) => match(value, 'POST', plansPath))
  await editor.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
  const written = await response
  expect(written.status()).toBe(201)
  const request = written.request().postDataJSON() as LaunchPlan
  expect(request.campaigns[0].adsets[0].metric_profile_id).toBe(profile)
  const saved = (await written.json()) as LaunchPlan
  expect(saved.state).toBe('DRAFT')
  expect(saved.campaigns[0].adsets[0].metric_profile_id).toBe(profile)
  const current = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
  await expect(current).toContainText('服务器已保存')
  await current.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(current).toBeHidden()
  return saved
}
async function openPlan(page: Page, plan: LaunchPlan, action: '详情' | '编辑草稿') {
  const input = page.getByPlaceholder('搜索计划名称', { exact: true })
  const list = page.waitForResponse(
    (response) =>
      match(response, 'GET', plansPath) &&
      new URL(response.url()).searchParams.get('q') === plan.name,
  )
  await input.fill(plan.name)
  await input.press('Enter')
  expect((await list).status()).toBe(200)
  const row = page
    .locator('.launch-page .el-tab-pane .el-table__body tr')
    .filter({ hasText: plan.name })
  await expect(row).toHaveCount(1)
  const read = page.waitForResponse((response) => match(response, 'GET', plansPath + '/' + plan.id))
  await row.getByRole('button', { name: action, exact: true }).click()
  const response = await read
  expect(response.status()).toBe(200)
  return (await response.json()) as LaunchPlan
}

test('Python计划指标目录原详情选择保存与清除真实闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info),
    writes = noPlatformWrites(page)
  try {
    await test.step('真实原菜单进入并新增广告组', async () => enter(page))
    const name = 'UI_METRIC_PLAN_' + randomUUID().slice(0, 8)
    const editor = await planEditor(page, name)
    const profile = await test.step('目录原12字段及FIXTURE语义，选择真实ID', async () =>
      chooseProfile(page, editor))
    const plan = await test.step('实际POST后GET确认原引用', async () => {
      const saved = await createPlan(page, editor, profile)
      const fetched = await openPlan(page, saved, '编辑草稿')
      expect(fetched.campaigns[0].adsets[0].metric_profile_id).toBe(profile)
      return saved
    })
    await test.step('清除后PUT不含optional字段或null，再实际GET核对', async () => {
      const edit = page.getByRole('dialog', { name: '编辑投放草稿', exact: true })
      await edit.getByText('指标引用组 ×1', { exact: true }).click()
      await edit.getByRole('textbox', { name: '指标配置ID（草稿可空）', exact: true }).fill('')
      const update = page.waitForResponse((response) =>
        match(response, 'PUT', plansPath + '/' + plan.id),
      )
      await edit.getByRole('button', { name: '保存服务器草稿', exact: true }).click()
      const written = await update
      expect(written.status()).toBe(200)
      const request = written.request().postDataJSON() as LaunchPlan
      expect(request.campaigns[0].adsets[0]).not.toHaveProperty('metric_profile_id')
      const updated = (await written.json()) as LaunchPlan
      expect(updated.campaigns[0].adsets[0]).not.toHaveProperty('metric_profile_id')
      await expect(edit).toContainText('服务器已保存')
      await edit.getByRole('button', { name: '关闭', exact: true }).click()
      await expect(edit).toBeHidden()
      const fetched = await openPlan(page, updated, '详情')
      expect(fetched.campaigns[0].adsets[0]).not.toHaveProperty('metric_profile_id')
    })
    expect(writes).toEqual([])
    await page.screenshot({ path: info.outputPath('launch-metric-plan.png'), fullPage: true })
  } finally {
    await finish()
  }
})

test('Python模板共享指标字段目录选择保存重读真实闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info),
    writes = noPlatformWrites(page)
  try {
    await enter(page)
    await page.getByRole('tab', { name: '配置模板', exact: true }).click()
    await page.getByRole('button', { name: '新建配置模板', exact: true }).click()
    const editor = page.getByRole('dialog', { name: '保存配置模板', exact: true })
    const name = 'UI_METRIC_TEMPLATE_' + randomUUID().slice(0, 8)
    await editor.getByLabel('模板名称（1—80码点）', { exact: true }).fill(name)
    await structure(editor)
    const profile = await chooseProfile(page, editor)
    const write = page.waitForResponse((response) => match(response, 'POST', templatesPath))
    await editor.getByRole('button', { name: '保存模板', exact: true }).click()
    const saved = await write
    expect(saved.status()).toBe(201)
    expect(
      (saved.request().postDataJSON() as LaunchTemplate).campaigns[0].adsets[0].metric_profile_id,
    ).toBe(profile)
    const template = (await saved.json()) as LaunchTemplate
    expect(template.campaigns[0].adsets[0].metric_profile_id).toBe(profile)
    await expect(editor).toBeHidden()
    const query = page.waitForResponse(
      (response) =>
        match(response, 'GET', templatesPath) &&
        new URL(response.url()).searchParams.get('q') === name,
    )
    const input = page.getByPlaceholder('搜索模板名称', { exact: true })
    await input.fill(name)
    await input.press('Enter')
    expect((await query).status()).toBe(200)
    const row = page.locator('.template-panel .el-table__body tr').filter({ hasText: name })
    const get = page.waitForResponse((response) =>
      match(response, 'GET', templatesPath + '/' + template.id),
    )
    await row.getByRole('button', { name: '详情', exact: true }).click()
    const fetched = await get
    expect(fetched.status()).toBe(200)
    expect(
      ((await fetched.json()) as LaunchTemplate).campaigns[0].adsets[0].metric_profile_id,
    ).toBe(profile)
    const detail = page.getByRole('dialog', { name: '模板详情', exact: true })
    await detail.getByText('指标引用组 ×1', { exact: true }).click()
    await expect(
      detail.getByRole('textbox', { name: '指标配置ID（草稿可空）', exact: true }),
    ).toHaveValue(profile)
    await expect(
      detail.getByRole('textbox', { name: '指标配置ID（草稿可空）', exact: true }),
    ).toBeDisabled()
    expect(writes).toEqual([])
    await page.screenshot({ path: info.outputPath('launch-metric-template.png'), fullPage: true })
  } finally {
    await finish()
  }
})

test('Python无monitor读取权限角色手填指标UUID保存且目录零请求', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info),
    writes = noPlatformWrites(page)
  let profileRequests = 0
  page.on('request', (request) => {
    if (request.method() === 'GET' && apiPath(request.url()) === profilesPath) profileRequests++
  })
  try {
    await enter(page, false)
    const editor = await planEditor(page, 'UI_METRIC_MANUAL_' + randomUUID().slice(0, 8))
    const profile = process.env.ORBIT_E2E_LAUNCH_METRIC_PROFILE_ID!
    await expect(editor.getByRole('button', { name: '从指标目录选择', exact: true })).toBeDisabled()
    await expect(editor).toContainText('没有指标目录读取权限；仍可填写已有UUID保存草稿')
    await editor.getByRole('textbox', { name: '指标配置ID（草稿可空）', exact: true }).fill(profile)
    const saved = await createPlan(page, editor, profile)
    const actual = await openPlan(page, saved, '详情')
    expect(actual.campaigns[0].adsets[0].metric_profile_id).toBe(profile)
    expect(profileRequests).toBe(0)
    expect(writes).toEqual([])
    await page.screenshot({ path: info.outputPath('launch-metric-manual.png'), fullPage: true })
  } finally {
    await finish()
  }
})
