/** SDK合同/传输替身纯测，不是Rule HTTP、模拟来源或浏览器验收。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  parseConditionResult,
  parseRule,
  parseRuleCondition,
  parseRulePage,
  parseRuleRun,
  parseRuleRunPage,
  parseRuleSchedule,
  parseRuleSimulation,
  parseRuleWrite,
  RuleApiError,
  rulesApi,
  type RuleWrite,
} from '@/api/orbit/rules'

const auth = vi.hoisted(() => ({
  token: 'Bearer old-session',
  cookie: false,
  csrf: 'cookie-csrf-original-0001',
}))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => (auth.cookie ? 'same-origin' : 'omit'),
  orbitAuthHeaders: (extra: HeadersInit = {}) => {
    const result = Object.fromEntries(new Headers(extra).entries())
    if (auth.cookie) {
      delete result.authorization
      result['x-csrf-token'] = auth.csrf
    } else result.authorization = auth.token
    return result
  },
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const now = '2026-11-09T00:00:00.123Z'
const frozen = () => ({
  csrf_token: 'native-csrf-original-0001',
  idempotency_key: 'original-rule-key-000001',
})
const versioned = () => ({ ...frozen(), if_match: '"9007199254740991"' })
const write = (): RuleWrite => ({
  name: '规则😀',
  ownership: { owner_user_id: id(1), owner_team_id: id(2) },
  target_level: 'AD',
  scope_snapshot_id: id(3),
  logic: 'AND',
  groups: [
    {
      logic: 'OR',
      conditions: [
        { metric: 'spend', operator: 'GTE', threshold: '0.000001' },
        { metric: 'clicks', operator: 'NEQ', threshold: '9007199254740993000000' },
      ],
    },
  ],
  window: 'LAST_3D',
  metric_profile_id: id(4),
  schedule: {
    frequency: 'INTERVAL',
    interval_minutes: 30,
    time_of_day: null,
    weekday: null,
    timezone: 'America/New_York',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
  },
  cooldown_minutes: 60,
  max_daily: 5,
})
const rule = () => ({
  ...write(),
  id: id(5),
  revision: Number.MAX_SAFE_INTEGER,
  state: 'DRAFT',
  next_run_at: null,
})
const condition = () => ({
  entity_id: id(),
  condition_index: 0,
  value: null,
  result: 'UNKNOWN',
  reason_code: 'MISSING',
})
const simulation = () => ({
  id: id(),
  rule_id: id(5),
  revision: 1,
  snapshot_id: id(7),
  hash: 'a'.repeat(64),
  account_count: 521,
  scanned_count: 3,
  hit_count: 1,
  unknown_count: 1,
  false_count: 1,
  conditions: [condition()],
  expires_at: now,
  next_cursor: 'opaque+/=',
})
const run = () => ({
  id: id(),
  rule_id: id(5),
  rule_revision: 1,
  schedule_slot: now,
  snapshot_id: id(7),
  state: 'UNKNOWN',
  hit_count: 0,
  reason_code: null,
})
const page = (items: unknown[]) => ({
  items,
  next_cursor: null,
  data_as_of: now,
  scope_version: Number.MAX_SAFE_INTEGER,
})
const serverError = (code = 'RULE_SIMULATION_SOURCE_UNAVAILABLE') => ({
  code,
  message: '来源尚未接入',
  field_errors: [{ path: '/schedule', code: 'SOURCE', message: '未就绪', constraint: null }],
  retryable: true,
  request_id: id(9),
})
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
const fetcher = vi.fn()
beforeEach(() => {
  auth.token = 'Bearer old-session'
  auth.cookie = false
  auth.csrf = 'cookie-csrf-original-0001'
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('严格原DTO', () => {
  it('保留11/15/13/5/8字段及大整数Decimal文本/null，不借number转换', () => {
    expect(Object.keys(parseRuleWrite(write()))).toHaveLength(11)
    expect(Object.keys(parseRule(rule()))).toHaveLength(15)
    expect(Object.keys(parseRuleSimulation(simulation()))).toHaveLength(13)
    expect(Object.keys(parseConditionResult(condition()))).toHaveLength(5)
    expect(Object.keys(parseRuleRun(run()))).toHaveLength(8)
    expect(parseRuleWrite(write()).groups[0].conditions[1].threshold).toBe('9007199254740993000000')
    expect(parseConditionResult(condition()).value).toBeNull()
  })
  it('全部Schedule互斥null键必须存在，366含首尾但不接受367或无效日期', () => {
    const value = write().schedule
    expect(parseRuleSchedule(value)).toEqual(value)
    expect(() => parseRuleSchedule({ ...value, weekday: undefined })).toThrow()
    expect(() => parseRuleSchedule({ ...value, end_date: '2025-01-01' })).toThrow()
    expect(() => parseRuleSchedule({ ...value, start_date: '2024-02-30' })).toThrow()
    expect(() => parseRuleSchedule({ ...value, time_of_day: '10:30' })).toThrow()
    expect(() => parseRuleSchedule({ ...value, timezone: 'Mars/Not_A_Zone' })).toThrow()
    expect(
      parseRuleSchedule({
        ...value,
        frequency: 'WEEKLY',
        interval_minutes: null,
        time_of_day: '02:30',
        weekday: 7,
      }).weekday,
    ).toBe(7)
  })
  it.each([
    { threshold: 1 },
    { threshold: '1e2' },
    { threshold: '-1' },
    { threshold: '0.1234567' },
    { metric: 'clicks', threshold: '0.1' },
    { metric: 'ctr', threshold: '100.000001' },
    { metric: 'roas', threshold: '1000000.000001' },
    { metric: 'spend', threshold: '1000000000.000001' },
  ])('拒绝阈值错误类型/范围 %j', (change) => {
    expect(() =>
      parseRuleCondition({ metric: 'spend', operator: 'GTE', threshold: '0', ...change }),
    ).toThrow()
  })
  it('只允许Rule→group→leaf两层AST且全部条件≤20', () => {
    const value = write()
    value.groups = Array.from({ length: 3 }, () => ({
      logic: 'AND',
      conditions: Array.from({ length: 7 }, () => ({
        metric: 'spend',
        operator: 'GTE',
        threshold: '0',
      })),
    })) as RuleWrite['groups']
    expect(() => parseRuleWrite(value)).toThrow()
    expect(() => parseRuleWrite({ ...write(), groups: [{ logic: 'AND', groups: [] }] })).toThrow()
    expect(() => parseRuleWrite({ ...write(), unknown: true })).toThrow()
    expect(() => parseRuleWrite({ ...write(), name: 'bad\ud800' })).toThrow()
    expect(() => parseRuleWrite({ ...write(), name: 'bad\n' })).toThrow()
  })
  it('逐码点处理Unicode且不保留调用方可变引用', () => {
    const value = write()
    value.name = '😀'.repeat(80)
    const parsed = parseRuleWrite(value)
    value.groups[0].conditions[0].threshold = '999'
    expect(parsed.groups[0].conditions[0].threshold).toBe('0.000001')
    expect(() => parseRuleWrite({ ...value, name: '😀'.repeat(81) })).toThrow()
    expect(parseRuleWrite({ ...value, name: ' ' + 'e\u0301'.repeat(80) + ' ' }).name).toBe(
      'é'.repeat(80),
    )
  })
  it('Simulation分类必须完整对账、10000叶边界、未知值不补0', () => {
    expect(() => parseRuleSimulation({ ...simulation(), false_count: 0 })).toThrow()
    expect(() => parseConditionResult({ ...condition(), value: 0 })).toThrow()
    expect(() => parseConditionResult({ ...condition(), reason_code: '' })).toThrow()
    expect(
      parseRuleSimulation({ ...simulation(), conditions: Array.from({ length: 10000 }, condition) })
        .conditions,
    ).toHaveLength(10000)
    expect(() =>
      parseRuleSimulation({
        ...simulation(),
        conditions: Array.from({ length: 10001 }, condition),
      }),
    ).toThrow()
  })
  it('页与运行记录严格四/八字段，非法UTC和假状态不变为空成功', () => {
    expect(parseRulePage(page([rule()])).items).toHaveLength(1)
    expect(parseRuleRunPage(page([run()])).items).toHaveLength(1)
    expect(() => parseRuleRun({ ...run(), state: 'ENABLED' })).toThrow()
    expect(() => parseRuleRun({ ...run(), schedule_slot: '2026-02-30T00:00:00Z' })).toThrow()
    expect(() => parseRule({ ...rule(), next_run_at: '2026-11-09T08:00:00+08:00' })).toThrow()
    expect(() => parseRulePage(page(Array.from({ length: 201 }, rule)))).toThrow()
  })
})

describe('原九接口/六动作与冻结传输', () => {
  it.each(['CREATE', 'UPDATE', 'ENABLE', 'PAUSE', 'ARCHIVE', 'SIMULATE'] as const)(
    '能力入口只请求原%s动作',
    async (action) => {
      fetcher.mockResolvedValue(response({ csrf_token: frozen().csrf_token }))
      expect(await rulesApi.capabilities(action)).toEqual({ csrf_token: frozen().csrf_token })
      expect(
        new URL(String(fetcher.mock.calls[0][0]), 'https://fixture').searchParams.get('action'),
      ).toBe(action)
    },
  )
  it('create201与PUT200保留原完整body/key/quoted safe If-Match且不写Storage', async () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, 'setItem')
    fetcher.mockResolvedValueOnce(response(rule(), 201)).mockResolvedValueOnce(response(rule()))
    const value = write()
    const pending = rulesApi.create(value, frozen())
    value.name = '在途更名'
    await pending
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit]
    expect(url.endsWith('/api/v1/rules')).toBe(true)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body)).name).toBe('规则😀')
    expect(new Headers(init.headers).get('idempotency-key')).toBe(frozen().idempotency_key)
    expect(new Headers(init.headers).has('if-match')).toBe(false)
    expect(init.cache).toBe('no-store')
    expect(init.credentials).toBe('omit')
    await rulesApi.update(id(5), write(), versioned())
    expect(fetcher.mock.calls[1][1].method).toBe('PUT')
    expect(new Headers(fetcher.mock.calls[1][1].headers).get('if-match')).toBe('"9007199254740991"')
    expect(localStorageSpy).not.toHaveBeenCalled()
  })
  it('归档/暂停原Reason、enable原单字段、simulate严格无正文', async () => {
    fetcher.mockImplementation(() => Promise.resolve(response(rule())))
    await rulesApi.archive(id(5), { reason: '归档'.repeat(500) }, versioned())
    await rulesApi.pause(id(5), { reason: '暂停' }, versioned())
    await rulesApi.enable(id(5), { simulation_id: id(6) }, versioned())
    fetcher.mockResolvedValue(response(simulation()))
    await rulesApi.simulate(id(5), versioned())
    expect(fetcher.mock.calls.map((call) => String(call[0]).split('/').pop())).toEqual([
      'archive',
      'pause',
      'enable',
      'simulate',
    ])
    expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual({ simulation_id: id(6) })
    expect(Object.hasOwn(fetcher.mock.calls[3][1], 'body')).toBe(false)
  })
  it('list/runs保留原十参数与literal Unicode查询，GET不附加写头', async () => {
    const query = {
      q: '😀 %_\\',
      cursor: 'opaque+/=',
      page_size: 20 as const,
      status: 'DRAFT' as const,
      date_from: '2026-01-01',
      date_to: '2026-01-02',
      operator_user_id: id(),
      channel_id: id(2),
      metric_profile_id: id(4),
      entity_type: 'AD' as const,
    }
    fetcher
      .mockResolvedValueOnce(response(page([rule()])))
      .mockResolvedValueOnce(response(page([run()])))
    await rulesApi.list(query)
    const url = new URL(String(fetcher.mock.calls[0][0]), 'https://fixture')
    expect([...url.searchParams.keys()]).toHaveLength(10)
    expect(url.searchParams.get('q')).toBe(query.q)
    expect(new Headers(fetcher.mock.calls[0][1].headers).has('idempotency-key')).toBe(false)
    await rulesApi.runs(id(5), { ...query, status: 'RUNNING' })
    expect(String(fetcher.mock.calls[1][0])).toContain(`/rules/${id(5)}/runs?`)
  })
  it('本地字段/未知参数与错header拒绝，不能悄悄补默认值', async () => {
    await expect(rulesApi.list({ q: 'x'.repeat(101) })).rejects.toMatchObject({ status: 422 })
    await expect(rulesApi.list({ unknown: true } as never)).rejects.toMatchObject({ status: 422 })
    await expect(
      rulesApi.update(id(5), write(), { ...versioned(), if_match: '1' }),
    ).rejects.toMatchObject({ status: 422 })
    await expect(
      rulesApi.create({ ...write(), schedule: {} } as never, frozen()),
    ).rejects.toMatchObject({ status: 422 })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('查询q先NFC再核100码点且保持调用方原对象，101拒绝', async () => {
    const original = Object.freeze({ q: 'e\u0301'.repeat(100) })
    fetcher.mockResolvedValue(response(page([rule()])))
    await rulesApi.list(original)
    expect(new URL(String(fetcher.mock.calls[0][0]), 'https://fixture').searchParams.get('q')).toBe(
      'é'.repeat(100),
    )
    expect(original.q).toBe('e\u0301'.repeat(100))
    await expect(rulesApi.list({ q: 'e\u0301'.repeat(101) })).rejects.toMatchObject({ status: 422 })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('503保留完整server Error/nullable constraint，不伪装空Simulation或Run', async () => {
    fetcher.mockImplementation(() => Promise.resolve(response(serverError(), 503)))
    await expect(rulesApi.simulate(id(5), versioned())).rejects.toMatchObject({
      status: 503,
      code: 'RULE_SIMULATION_SOURCE_UNAVAILABLE',
      source: 'server',
      unknown_result: false,
      request_id: id(9),
      field_errors: serverError().field_errors,
    })
    await expect(rulesApi.runs(id(5))).rejects.toBeInstanceOf(RuleApiError)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
  it('200 envelope/缺字段不当原成功，create200也不当201', async () => {
    fetcher
      .mockResolvedValueOnce(response({ code: 200, data: rule() }, 201))
      .mockResolvedValueOnce(response(rule(), 200))
    await expect(rulesApi.create(write(), frozen())).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
      unknown_result: true,
    })
    await expect(rulesApi.create(write(), frozen())).rejects.toMatchObject({
      code: 'UNEXPECTED_HTTP_STATUS',
      unknown_result: true,
    })
  })
  it('网络未知保留同key且不自动重发', async () => {
    fetcher.mockRejectedValue(new Error('PRIVATE NETWORK BODY'))
    await expect(rulesApi.create(write(), frozen())).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
      unknown_result: true,
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('Cookie机制已换CSRF则发出前拒绝，不覆盖调用方冻结key/body', async () => {
    auth.cookie = true
    await expect(rulesApi.create(write(), frozen())).rejects.toMatchObject({
      code: 'CSRF_CONTEXT_CHANGED',
      unknown_result: false,
    })
    expect(fetcher).not.toHaveBeenCalled()
    fetcher.mockResolvedValue(response(rule(), 201))
    await rulesApi.create(write(), { ...frozen(), csrf_token: auth.csrf })
    expect(fetcher.mock.calls[0][1].credentials).toBe('same-origin')
    expect(new Headers(fetcher.mock.calls[0][1].headers).has('authorization')).toBe(false)
  })
  it('会话切换的迟到成功不回填新身份，写结果保持未知', async () => {
    let resolve!: (value: Response) => void
    fetcher.mockReturnValue(
      new Promise<Response>((r) => {
        resolve = r
      }),
    )
    const pending = rulesApi.create(write(), frozen())
    auth.token = 'Bearer new-session'
    resolve(response(rule(), 201))
    await expect(pending).rejects.toMatchObject({
      code: 'SESSION_CONTEXT_CHANGED',
      unknown_result: true,
    })
  })
  it('已取消读取不发出，发出后超时写不换key重试', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(rulesApi.get(id(5), controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(fetcher).not.toHaveBeenCalled()
    vi.useFakeTimers()
    fetcher.mockImplementation(
      (_url, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    const pending = rulesApi.create(write(), frozen())
    const assertion = expect(pending).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
      unknown_result: true,
    })
    await vi.advanceTimersByTimeAsync(15000)
    await assertion
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
