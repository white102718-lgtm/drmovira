import { test, expect, type Locator, type Page, type Response } from '@playwright/test'
import type { Metrics, MetricQuery, MetricRow } from '../../src/api/orbit/metrics'
import type { MetricProfilePage } from '../../src/api/orbit/metric-profiles'
import { observePythonBrowser } from './python-browser-diagnostics'

/** 仅真实隔离公开API与SQL技术样本，不拦截响应、不触发平台广告操作。 */
interface Fixture {
  version: 1
  kind: 'SQL_ONLY_NOT_PLATFORM'
  route: '/orbit/monitor/data'
  profile: { id: string; version: string }
  query: MetricQuery
  expected: {
    summary_ad_count: number
    day_ad_count: number
    literal_entity_id: string
    literal_name: string
    verified_ad_ids: string[]
    unknown_ad_id: string
    summary_entity_ids: Record<'ACCOUNT' | 'CAMPAIGN' | 'ADSET' | 'AD', string[]>
    totals: Record<string, { spend: string | null; ad_count: number; registrations?: null }>
  }
}
function fixture(): Fixture {
  try {
    const value = JSON.parse(process.env.ORBIT_E2E_METRICS_FIXTURE ?? '') as Fixture
    if (
      Object.keys(value).sort().join(',') !== 'expected,kind,profile,query,route,version' ||
      value.version !== 1 ||
      value.kind !== 'SQL_ONLY_NOT_PLATFORM' ||
      value.route !== '/orbit/monitor/data' ||
      !value.profile?.id ||
      !value.profile.version ||
      value.query?.metric_profile_id !== value.profile.id ||
      value.expected?.summary_ad_count !== 22 ||
      value.expected.day_ad_count !== 44 ||
      value.expected.verified_ad_ids?.length !== 21
    )
      throw new Error()
    return value
  } catch {
    throw new Error('必须由主线注入独立Metrics技术fixture安全manifest，不能使用空库或模拟响应')
  }
}
const data = fixture(),
  endpoint = '/api/v1/metrics/query'
const valueKeys = [
  'spend',
  'impressions',
  'clicks',
  'registrations',
  'purchases',
  'purchase_value',
  'roas',
  'cpm',
  'ctr',
  'cpc',
  'cpa',
  'usage',
] as const
const queryKeys = [
  'date_from',
  'date_to',
  'dataset',
  'metric_profile_id',
  'scope_snapshot_id',
  'channel_id',
  'operator_user_id',
  'q',
  'sort',
  'direction',
  'cursor',
  'page_size',
  'granularity',
].sort()
const rowKeys = [
  'tenant_id',
  'owner_team_id',
  'operator_user_id',
  'entity_id',
  'name',
  'channel_id',
  'product_name_snapshot',
  'currency',
  'metric_profile_id',
  'business_date',
  'account_count',
  'ad_count',
  'values',
  'quality',
  'coverage',
].sort()
const totalKeys = [
  'tenant_id',
  'currency',
  'metric_profile_id',
  'values',
  'account_count',
  'ad_count',
  'missing_count',
  'coverage',
].sort()
const path = (url: string) => {
  const value = new URL(url).pathname
  return value.startsWith('/dev-api/') ? value.slice('/dev-api'.length) : value
}
const match = (response: Response, method: string, exact: string) =>
  response.request().method() === method && path(response.url()) === exact
const panel = (page: Page) => page.locator('.metrics-page')
const bodyRows = (page: Page) =>
  panel(page)
    .locator('section[aria-label="指标查询结果"] .el-table')
    .first()
    .locator('.el-table__body-wrapper tbody tr')
const totalRows = (page: Page) =>
  panel(page)
    .locator('section[aria-label="指标查询结果"] .el-table')
    .nth(1)
    .locator('.el-table__body-wrapper tbody tr')
async function security(page: Page, response: Response) {
  expect(response.status()).toBe(200)
  const user = (await response.json()) as {
    permissions: string[]
    isDefaultModifyPwd: boolean
    isPasswordExpired: boolean
  }
  expect(user.permissions.some((p) => p === '*:*:*' || p === 'monitor.read')).toBe(true)
  expect(typeof user.isDefaultModifyPwd).toBe('boolean')
  expect(typeof user.isPasswordExpired).toBe('boolean')
  const notice = page.getByRole('dialog', { name: '安全提示', exact: true })
  if (user.isDefaultModifyPwd || user.isPasswordExpired) {
    await expect(notice).toBeVisible()
    await expect(notice.locator('.el-message-box__message')).toHaveText(
      user.isDefaultModifyPwd
        ? '您的密码还是初始密码，请修改密码！'
        : '您的密码已过期，请尽快修改密码！',
    )
    await notice.getByRole('button', { name: '取消', exact: true }).click()
    await expect(notice).toBeHidden()
  } else await expect(notice).toBeHidden()
}
async function open(page: Page) {
  const password = process.env.ORBIT_E2E_FIXTURE_PASSWORD
  if (!password) throw new Error('必须使用主线隔离登录上下文')
  const captcha = page.waitForResponse((r) => path(r.url()) === '/captchaImage')
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(password)
  const user = page.waitForResponse((r) => match(r, 'GET', '/getInfo'))
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await security(page, await user)
  const again = page.waitForResponse((r) => match(r, 'GET', '/getInfo'))
  const capabilities = page.waitForResponse((r) => match(r, 'GET', '/api/v1/metrics/capabilities'))
  await page.goto(data.route)
  await security(page, await again)
  const context = await capabilities
  expect(context.status()).toBe(200)
  const value = (await context.json()) as { csrf_token: string }
  expect(Object.keys(value)).toEqual(['csrf_token'])
  // 不在assert产物中输出实际CSRF值。
  expect(typeof value.csrf_token === 'string' && value.csrf_token.length >= 16).toBe(true)
  await expect(
    panel(page).getByRole('heading', { name: '广告投放数据', exact: true }),
  ).toBeVisible()
  const shell = page.locator('.app-wrapper')
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
}
async function selectTab(page: Page, label: string) {
  await panel(page).getByRole('tab', { name: label, exact: true }).click()
}
async function prepare(page: Page) {
  const profiles = page.waitForResponse((r) => match(r, 'GET', '/api/v1/metric-profiles'))
  await selectTab(page, '广告账户')
  const response = await profiles
  expect(response.status()).toBe(200)
  const candidates = (await response.json()) as MetricProfilePage
  const selected = candidates.items.find((profile) => profile.id === data.profile.id)
  expect(
    Boolean(selected && selected.version === data.profile.version && selected.source === 'FIXTURE'),
  ).toBe(true)
  await expect(panel(page).getByText('全部当前可见账户', { exact: true })).toBeVisible()
  await panel(page).getByLabel('开始业务日', { exact: true }).fill(data.query.date_from)
  await panel(page).getByLabel('结束业务日', { exact: true }).fill(data.query.date_to)
  await choose(
    page,
    '指标配置',
    `${selected!.version} · 测试样本 · ${selected!.verified ? '已登记' : '待核验'} · ${data.profile.id}`,
  )
  await expect(panel(page)).toContainText('此配置为隔离测试样本')
}
async function choose(page: Page, name: string, option: string) {
  await panel(page)
    .getByRole('combobox', { name, exact: true })
    .locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]')
    .click()
  await page.getByRole('option', { name: option, exact: true }).click()
}
async function read(
  page: Page,
  action: () => Promise<unknown>,
  expected: Partial<MetricQuery> = {},
): Promise<Metrics> {
  const response = page.waitForResponse((r) => {
    if (!match(r, 'POST', endpoint)) return false
    try {
      const body = r.request().postDataJSON() as MetricQuery
      return Object.entries(expected).every(
        ([key, value]) => body[key as keyof MetricQuery] === value,
      )
    } catch {
      return false
    }
  })
  await action()
  const actual = await response
  const request = actual.request().postDataJSON() as MetricQuery
  expect(Object.keys(request).sort()).toEqual(queryKeys)
  expect(request.metric_profile_id).toBe(data.profile.id)
  expect(request.date_from).toBe(data.query.date_from)
  expect(request.date_to).toBe(data.query.date_to)
  expect(request.scope_snapshot_id).toBeNull()
  expect(request.channel_id).toBeNull()
  expect(request.operator_user_id).toBeNull()
  const headers = actual.request().headers()
  expect(
    typeof headers['idempotency-key'] === 'string' && headers['idempotency-key'].length >= 16,
  ).toBe(true)
  expect(typeof headers['x-csrf-token'] === 'string' && headers['x-csrf-token'].length >= 16).toBe(
    true,
  )
  expect(actual.status()).toBe(200)
  const value = (await actual.json()) as Metrics
  expect(Object.keys(value).sort()).toEqual(
    [
      'items',
      'next_cursor',
      'scope_version',
      'snapshot_id',
      'data_as_of',
      'missing_count',
      'query_snapshot_id',
      'totals',
    ].sort(),
  )
  expect(Number.isSafeInteger(value.scope_version) && value.scope_version > 0).toBe(true)
  expect(Number.isFinite(Date.parse(value.data_as_of))).toBe(true)
  expect(value.items.length).toBeLessThanOrEqual(request.page_size)
  for (const row of value.items) {
    expect(Object.keys(row).sort()).toEqual(rowKeys)
    expect(Object.keys(row.values).sort()).toEqual([...valueKeys].sort())
    expect(row.metric_profile_id).toBe(data.profile.id)
    expect(['COMPLETE', 'PARTIAL', 'STALE', 'UNKNOWN']).toContain(row.quality)
    for (const key of valueKeys)
      expect(
        row.values[key] === null ||
          (typeof row.values[key] === 'string' &&
            /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(row.values[key]!) &&
            row.values[key]!.length <= 28),
      ).toBe(true)
  }
  for (const total of value.totals) {
    expect(Object.keys(total).sort()).toEqual(totalKeys)
    expect(Object.keys(total.values).sort()).toEqual([...valueKeys].sort())
  }
  await expect(bodyRows(page)).toHaveCount(value.items.length)
  return value
}
const query = (page: Page, expected: Partial<MetricQuery> = {}) =>
  read(
    page,
    () => panel(page).getByRole('button', { name: '查询指标', exact: true }).click(),
    expected,
  )
async function totals(page: Page, value: Metrics) {
  expect(value.totals.map((total) => total.currency).sort()).toEqual(['EUR', 'GBP', 'USD'])
  await expect(totalRows(page)).toHaveCount(3)
  for (const currency of ['USD', 'EUR', 'GBP']) {
    const total = value.totals.find((item) => item.currency === currency)!,
      expected = data.expected.totals[currency]
    expect(total.values.spend).toBe(expected.spend)
    expect(total.ad_count).toBe(expected.ad_count)
    const row = totalRows(page).filter({ hasText: currency })
    await expect(row).toHaveCount(1)
    await expect(row.locator('td').nth(3)).toHaveText(expected.spend ?? '未知')
  }
  expect(value.totals.find((t) => t.currency === 'USD')!.values.registrations).toBeNull()
  expect(value.totals.find((t) => t.currency === 'GBP')!.coverage).toBe('0')
  expect(value.totals.find((t) => t.currency === 'GBP')!.missing_count).toBe(2)
}
function forbidden(page: Page) {
  const actions: string[] = []
  page.on('request', (request) => {
    const route = path(request.url())
    if (
      ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method()) &&
      route.startsWith('/api/v1/') &&
      route !== endpoint
    )
      actions.push('unexpected-business-write')
  })
  return actions
}

test('Metrics原七Tab四实体目录选择及公开查询真实集合', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await test.step('原登录、查询上下文与目录真实读取', async () => {
      await open(page)
      await expect(panel(page).getByRole('tab')).toHaveText([
        '监测与规则优化',
        '投放师',
        '渠道',
        '广告账户',
        '广告系列',
        '广告组',
        '广告',
      ])
      await prepare(page)
    })
    const actions = forbidden(page)
    await test.step('四实体真实13字段查询及全量ID集合', async () => {
      for (const [label, dataset] of [
        ['广告账户', 'ACCOUNT'],
        ['广告系列', 'CAMPAIGN'],
        ['广告组', 'ADSET'],
        ['广告', 'AD'],
      ] as const) {
        await selectTab(page, label)
        const first = await query(page, {
          dataset,
          granularity: 'SUMMARY',
          page_size: 20,
          cursor: null,
        })
        const rows = [...first.items]
        if (first.next_cursor) {
          const second = await read(
            page,
            () => panel(page).getByRole('button', { name: '下一页', exact: true }).click(),
            { dataset, cursor: first.next_cursor },
          )
          rows.push(...second.items)
          expect(second.next_cursor).toBeNull()
        }
        expect(rows.map((row) => row.entity_id).sort()).toEqual(
          data.expected.summary_entity_ids[dataset],
        )
      }
    })
    expect(actions).toEqual([])
  } finally {
    await finish()
  }
})

test('Metrics广告22条四档游标历史DAY44及原币种完整totals', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await open(page)
    await prepare(page)
    await selectTab(page, '广告')
    const actions = forbidden(page)
    await test.step('20加2真实下一页与历史，totals不受页数影响', async () => {
      const first = await query(page, {
        dataset: 'AD',
        page_size: 20,
        granularity: 'SUMMARY',
        cursor: null,
      })
      expect(first.items).toHaveLength(20)
      expect(first.next_cursor).not.toBeNull()
      await totals(page, first)
      const second = await read(
        page,
        () => panel(page).getByRole('button', { name: '下一页', exact: true }).click(),
        { cursor: first.next_cursor },
      )
      expect(second.items).toHaveLength(2)
      expect(second.next_cursor).toBeNull()
      expect(second.totals).toEqual(first.totals)
      expect([...first.items, ...second.items].map((row) => row.entity_id).sort()).toEqual(
        data.expected.summary_entity_ids.AD,
      )
      const previous = await read(
        page,
        () => panel(page).getByRole('button', { name: '上一页', exact: true }).click(),
        { cursor: null },
      )
      expect(previous.items).toEqual(first.items)
      await totals(page, previous)
    })
    await test.step('50/100/200重新首查均完整22条', async () => {
      for (const size of [50, 100, 200] as const) {
        await choose(page, '指标每页条数', String(size))
        const value = await query(page, { page_size: size, cursor: null })
        expect(value.items).toHaveLength(data.expected.summary_ad_count)
        expect(value.next_cursor).toBeNull()
        await totals(page, value)
      }
    })
    await test.step('DAY44保留两日相同实体且汇总不重复广告数', async () => {
      await choose(page, '汇总粒度', '账户当地业务日')
      const value = await query(page, { granularity: 'DAY', page_size: 200, cursor: null })
      expect(value.items).toHaveLength(data.expected.day_ad_count)
      for (const date of [data.query.date_from, data.query.date_to])
        expect(
          value.items
            .filter((row) => row.business_date === date)
            .map((row) => row.entity_id)
            .sort(),
        ).toEqual(data.expected.summary_entity_ids.AD)
      await totals(page, value)
    })
    expect(actions).toEqual([])
  } finally {
    await finish()
  }
})

test('Metrics字面通配符两日筛选全部字段详情与无结果恢复', async ({ page }, info) => {
  const finish = observePythonBrowser(page, info)
  try {
    await open(page)
    await prepare(page)
    await selectTab(page, '广告')
    const actions = forbidden(page)
    let value!: Metrics
    await test.step('字面%_!按最新名选实体但保留两日金额', async () => {
      await panel(page).getByLabel('名称 / 平台ID', { exact: true }).fill('%_!')
      value = await query(page, { dataset: 'AD', q: '%_!', cursor: null })
      expect(value.items).toHaveLength(1)
      expect(value.items[0].entity_id).toBe(data.expected.literal_entity_id)
      expect(value.items[0].name).toBe(data.expected.literal_name)
      expect(value.items[0].values.spend).toBe('240')
      expect(value.items[0].values.registrations).toBeNull()
    })
    await test.step('原15字段含完整12指标的只读Drawer及响应式关闭', async () => {
      const row = value.items[0]
      await bodyRows(page).getByRole('button', { name: '只读详情', exact: true }).click()
      const detail = page.getByRole('dialog', { name: '指标实体详情', exact: true })
      await expect(detail).toBeVisible()
      await expect(detail.locator('dt')).toHaveCount(26)
      await expect(detail.locator('dd')).toHaveCount(26)
      const labels: Record<Exclude<keyof MetricRow, 'values'>, string> = {
        tenant_id: '租户ID',
        owner_team_id: '拥有团队ID',
        operator_user_id: '投放师ID',
        entity_id: '实体ID',
        name: '历史名称',
        channel_id: '渠道ID',
        product_name_snapshot: '产品名称快照',
        currency: '原币种',
        metric_profile_id: '指标配置ID',
        business_date: '账户当地业务日',
        account_count: '账户数',
        ad_count: '去重广告数',
        quality: '质量',
        coverage: '覆盖率',
      }
      const valueLabels = [
        '消耗',
        '曝光',
        '点击',
        '注册',
        '购物',
        '转化价值',
        'ROAS',
        'CPM',
        'CTR',
        'CPC',
        'CPA',
        '素材使用量',
      ]
      const field = (label: string): Locator =>
        detail
          .locator('dt')
          .filter({ hasText: new RegExp(`^${label}$`) })
          .locator('xpath=following-sibling::dd[1]')
      for (const key of Object.keys(labels) as Exclude<keyof MetricRow, 'values'>[])
        await expect(field(labels[key])).toHaveText(row[key] === null ? '未知' : String(row[key]))
      for (const [index, key] of valueKeys.entries())
        await expect(field(valueLabels[index])).toHaveText(row.values[key] ?? '未知')
      await expect
        .poll(() =>
          detail.evaluate((el) => {
            const box = el.getBoundingClientRect()
            return box.left >= 0 && box.right <= innerWidth + 1
          }),
        )
        .toBe(true)
      await detail.locator('button.el-drawer__close-btn').click()
      await expect(detail).toBeHidden()
    })
    await test.step('无结果是合法空实体，清空q恢复22条分页', async () => {
      await panel(page).getByLabel('名称 / 平台ID', { exact: true }).fill('不存在的指标')
      const empty = await query(page, { q: '不存在的指标', cursor: null })
      expect(empty.items).toEqual([])
      expect(empty.next_cursor).toBeNull()
      await expect(panel(page)).toContainText('当前筛选没有实体')
      await panel(page).getByLabel('名称 / 平台ID', { exact: true }).fill('')
      const restored = await query(page, { q: '', cursor: null })
      expect(restored.items).toHaveLength(20)
      expect(restored.next_cursor).not.toBeNull()
      await totals(page, restored)
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBe(true)
    })
    expect(actions).toEqual([])
  } finally {
    await finish()
  }
})
