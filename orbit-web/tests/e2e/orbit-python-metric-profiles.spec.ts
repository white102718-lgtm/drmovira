import { test, expect, type Page, type Response } from '@playwright/test'
import type { MetricProfile, MetricProfilePage } from '../../src/api/orbit/metric-profiles'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 主线独立UUID库中的21条SQL FIXTURE样本；不模拟网络、不执行平台写、不冒充Meta发布权威。 */
const route = '/orbit/monitor/metric-profiles',
  endpoint = '/api/v1/metric-profiles'
const fields = [
  'id',
  'version',
  'source',
  'register_action_type',
  'purchase_action_type',
  'value_action_type',
  'attribution_windows',
  'action_report_time',
  'timezone_policy',
  'breakdown',
  'maturity_days',
  'verified',
].sort()
const apiPath = (value: string) => {
  const { pathname } = new URL(value)
  return pathname.startsWith('/dev-api/') ? pathname.slice('/dev-api'.length) : pathname
}
const isGet = (response: Response, path: string) =>
  response.request().method() === 'GET' && apiPath(response.url()) === path
type NativeUser = { permissions: string[]; isDefaultModifyPwd: boolean; isPasswordExpired: boolean }
async function securityNotice(page: Page, response: Response) {
  expect(response.status()).toBe(200)
  const native = (await response.json()) as NativeUser
  expect(native.permissions.some((p) => p === '*:*:*' || p === 'monitor.read')).toBe(true)
  expect(typeof native.isDefaultModifyPwd).toBe('boolean')
  expect(typeof native.isPasswordExpired).toBe('boolean')
  const dialog = page.getByRole('dialog', { name: '安全提示', exact: true })
  if (native.isDefaultModifyPwd || native.isPasswordExpired) {
    await expect(dialog).toBeVisible()
    await expect(dialog.locator('.el-message-box__message')).toHaveText(
      native.isDefaultModifyPwd
        ? '您的密码还是初始密码，请修改密码！'
        : '您的密码已过期，请尽快修改密码！',
    )
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await expect(dialog).toBeHidden()
  } else await expect(dialog).toBeHidden()
}
async function login(page: Page) {
  const password = process.env.ORBIT_E2E_FIXTURE_PASSWORD
  if (!password) throw new Error('必须由主线独立真实浏览器fixture注入登录上下文')
  const captcha = page.waitForResponse((r) => apiPath(r.url()) === '/captchaImage')
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(password)
  const user = page.waitForResponse((r) => isGet(r, '/getInfo'))
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await securityNotice(page, await user)
}
async function payload(response: Response): Promise<MetricProfilePage> {
  expect(response.status()).toBe(200)
  const result = (await response.json()) as MetricProfilePage
  expect(Object.keys(result).sort()).toEqual([
    'data_as_of',
    'items',
    'next_cursor',
    'scope_version',
  ])
  expect(Number.isSafeInteger(result.scope_version) && result.scope_version >= 1).toBe(true)
  expect(Number.isFinite(Date.parse(result.data_as_of))).toBe(true)
  expect(result.items.length).toBeLessThanOrEqual(200)
  for (const row of result.items) {
    expect(Object.keys(row).sort()).toEqual(fields)
    expect(row.source).toBe('FIXTURE')
    expect(row.timezone_policy).toBe('ACCOUNT_LOCAL')
    expect(row.breakdown).toBe('TOTAL')
  }
  return result
}
async function open(page: Page, reload = false) {
  const first = page.waitForResponse(
    (r) =>
      isGet(r, endpoint) &&
      new URL(r.url()).searchParams.get('page_size') === '50' &&
      !new URL(r.url()).searchParams.has('cursor'),
  )
  const user = page.waitForResponse((r) => isGet(r, '/getInfo'))
  if (reload) await page.reload()
  else await page.goto(route)
  await securityNotice(page, await user)
  await expect(
    page.locator('.metric-profiles').getByRole('heading', { name: '指标配置目录', exact: true }),
  ).toBeVisible()
  const result = await payload(await first)
  expect(result.items).toHaveLength(21)
  expect(new Set(result.items.map((item) => item.id)).size).toBe(21)
  expect(result.next_cursor).toBeNull()
  expect(result.items.map((x) => x.version).sort()).toEqual(
    Array.from({ length: 21 }, (_, i) => `observed-v${String(i + 1).padStart(3, '0')}`),
  )
  await expect(rows(page)).toHaveCount(21)
  return result
}
const panel = (page: Page) => page.locator('.metric-profiles')
const rows = (page: Page) => panel(page).locator('.el-table__body-wrapper tbody tr')
async function readAfter(
  page: Page,
  action: () => Promise<unknown>,
  size: number,
  cursor: boolean,
  q?: string,
  id?: string,
) {
  const response = page.waitForResponse((r) => {
    if (!isGet(r, endpoint)) return false
    const p = new URL(r.url()).searchParams
    return (
      p.get('page_size') === String(size) &&
      p.has('cursor') === cursor &&
      (q === undefined || p.get('q') === (q || null)) &&
      (id === undefined || p.get('metric_profile_id') === (id || null))
    )
  })
  await action()
  return payload(await response)
}
async function chooseSize(page: Page, size: number) {
  return readAfter(
    page,
    async () => {
      await panel(page)
        .getByRole('combobox', { name: '指标配置每页条数', exact: true })
        .locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]')
        .click()
      await page.getByRole('option', { name: String(size), exact: true }).click()
    },
    size,
    false,
  )
}
async function query(page: Page, q: string, id: string, size = 50) {
  await panel(page).getByLabel('指标UUID搜索（精确匹配）', { exact: true }).fill(q)
  await panel(page).getByLabel('指标配置ID筛选（精确匹配）', { exact: true }).fill(id)
  return readAfter(
    page,
    () => panel(page).getByRole('button', { name: '查询指标配置', exact: true }).click(),
    size,
    false,
    q.toLowerCase(),
    id.toLowerCase(),
  )
}
async function assertDetail(page: Page, profile: MetricProfile) {
  const row = rows(page).filter({ hasText: profile.id })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '查看全部字段', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '指标配置全部字段', exact: true })
  await expect(detail).toBeVisible()
  await expect(detail.locator('.el-descriptions__label')).toHaveCount(12)
  for (const key of fields)
    await expect(
      detail.locator('.el-descriptions__label').filter({ hasText: new RegExp(`^${key} /`) }),
    ).toHaveCount(1)
  for (const value of [
    profile.id,
    profile.version,
    profile.source,
    profile.purchase_action_type!,
    profile.action_report_time,
    'ACCOUNT_LOCAL',
    'TOTAL',
    `${profile.maturity_days}个账户当地日`,
    profile.verified ? 'true（是）' : 'false（否）',
  ])
    await expect(detail).toContainText(value)
  expect(profile.register_action_type).toBeNull()
  expect(profile.value_action_type).toBeNull()
  await expect(detail.getByText('未知（null；未映射，不补默认事件）', { exact: true })).toHaveCount(
    2,
  )
  await expect(detail.locator('li')).toHaveText(profile.attribution_windows)
  await expect(detail).toContainText('FIXTURE测试配置，不能视为Meta生产验证或执行许可')
  await expect
    .poll(() =>
      detail.evaluate((el) => {
        const b = el.getBoundingClientRect()
        return b.left >= 0 && b.right <= innerWidth + 1
      }),
    )
    .toBe(true)
  await detail.getByRole('button', { name: '关闭详情', exact: true }).click()
  await expect(detail).toBeHidden()
}

test('Python指标配置21条四档分页历史及十二字段详情真实闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await test.step('真实登录与21项隔离样本', async () => {
      await login(page)
    })
    const initial = await open(page)
    const twenty = await test.step('20加1真实分页与历史返回', async () => {
      const first = await chooseSize(page, 20)
      expect(first.items).toHaveLength(20)
      expect(first.next_cursor).not.toBeNull()
      await expect(rows(page)).toHaveCount(20)
      const last = await readAfter(
        page,
        () => panel(page).getByRole('button', { name: '下一页', exact: true }).click(),
        20,
        true,
      )
      expect(last.items).toHaveLength(1)
      expect(last.next_cursor).toBeNull()
      expect(new Set([...first.items, ...last.items].map((x) => x.id)).size).toBe(21)
      await expect(rows(page)).toHaveCount(1)
      const back = await readAfter(
        page,
        () => panel(page).getByRole('button', { name: '上一页', exact: true }).click(),
        20,
        false,
      )
      expect(back.items).toEqual(first.items)
      await expect(rows(page)).toHaveCount(20)
      return first
    })
    await test.step('逐档50/100/200均回首完整读取', async () => {
      for (const size of [50, 100, 200]) {
        const result = await chooseSize(page, size)
        expect(result.items).toEqual(initial.items)
        expect(result.next_cursor).toBeNull()
        await expect(rows(page)).toHaveCount(21)
        await expect(
          panel(page).getByRole('button', { name: '上一页', exact: true }),
        ).toBeDisabled()
      }
    })
    await test.step('全部原字段与测试来源详情', async () => {
      await assertDetail(page, twenty.items[0])
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true)
    })
  } finally {
    await finish()
  }
})

test('Python指标配置UUID双筛选交集无结果及游标重置真实闭环', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await login(page)
    const initial = await open(page),
      [first, second] = initial.items
    await chooseSize(page, 20)
    await readAfter(
      page,
      () => panel(page).getByRole('button', { name: '下一页', exact: true }).click(),
      20,
      true,
    )
    await test.step('q与profile_id各自exactUUID以及双条件交集', async () => {
      let result = await query(page, first.id.toUpperCase(), '', 20)
      expect(result.items.map((x) => x.id)).toEqual([first.id])
      await expect(rows(page)).toHaveCount(1)
      await expect(panel(page).getByRole('button', { name: '上一页', exact: true })).toBeDisabled()
      result = await query(page, '', second.id, 20)
      expect(result.items.map((x) => x.id)).toEqual([second.id])
      result = await query(page, first.id, first.id, 20)
      expect(result.items.map((x) => x.id)).toEqual([first.id])
      result = await query(page, first.id, second.id, 20)
      expect(result.items).toHaveLength(0)
      expect(result.next_cursor).toBeNull()
      await expect(panel(page)).toContainText('当前筛选没有指标配置')
    })
    await test.step('清空双条件重新建立第一页及原下一页', async () => {
      const result = await query(page, '', '', 20)
      expect(result.items).toHaveLength(20)
      expect(result.next_cursor).not.toBeNull()
      await expect(rows(page)).toHaveCount(20)
      await expect(panel(page).getByRole('button', { name: '上一页', exact: true })).toBeDisabled()
      const tail = await readAfter(
        page,
        () => panel(page).getByRole('button', { name: '下一页', exact: true }).click(),
        20,
        true,
      )
      expect(tail.items).toHaveLength(1)
    })
  } finally {
    await finish()
  }
})

test('Python指标配置真实刷新重进及空搜索恢复', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await login(page)
    const initial = await open(page)
    await test.step('当前有效会话刷新仍读同一真实目录', async () => {
      const refreshed = await open(page, true)
      expect(refreshed.items).toEqual(initial.items)
      expect(refreshed.scope_version).toBe(initial.scope_version)
    })
    await test.step('离开目录后重新进入，读取权限菜单壳真实挂载', async () => {
      const user = page.waitForResponse((r) => isGet(r, '/getInfo'))
      await page.goto('/index')
      await securityNotice(page, await user)
      await expect(page.locator('.app-wrapper')).toBeVisible()
      await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
      const entered = await open(page)
      expect(entered.items).toEqual(initial.items)
    })
    await test.step('真实空结果并清空搜索恢复，不拦截伪造错误', async () => {
      let result = await query(page, initial.items[0].id, initial.items[1].id)
      expect(result.items).toHaveLength(0)
      await expect(panel(page)).toContainText('当前筛选没有指标配置')
      result = await query(page, '', '')
      expect(result.items).toEqual(initial.items)
      await expect(rows(page)).toHaveCount(21)
      await assertDetail(page, initial.items[0])
    })
  } finally {
    await finish()
  }
})
