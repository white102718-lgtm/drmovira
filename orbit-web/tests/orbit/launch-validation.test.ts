/** 新SDK严格合同/transport替身纯测；不表示预检/执行后端或页面已可用。 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import {
  launchValidationApi as api,
  LaunchValidationError,
  parseAllocation,
  parseNameReservation,
  parsePlanValidation,
  parsePlanMoney,
  parsePlanFieldError,
  type FrozenMutation,
} from '@/api/orbit/launch-validation'
import { ReferenceApiError } from '@/api/orbit/references'
import { taskFixture, taskUuid } from './tasks-fixtures'
const auth = vi.hoisted(() => ({ headers: vi.fn(), credentials: vi.fn() }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitAuthHeaders: auth.headers,
  orbitCredentials: auth.credentials,
}))
const fetcher = vi.fn()
const hash = 'a'.repeat(64)
const write: FrozenMutation = Object.freeze({
  csrf_token: 'frozen-csrf-token-123456',
  idempotency_key: 'frozen-idempotency-123456',
  if_match: '"9"',
})
const request = Object.freeze({ allocation_id: taskUuid(1), name_reservation_id: taskUuid(2) })
const field = () => ({
  path: '/campaigns/0/adsets/0/budget/amount',
  code: 'FIELD_VALIDATION_FAILED',
  message: '精度不合法',
  constraint: 'precision',
})
const validation = () => ({
  valid: true,
  hash,
  expires_at: '2026-11-08T03:04:05.123Z',
  errors: [],
  campaign_count: 1,
  adset_count: 2,
  ad_count: 3,
  budget_totals: [{ amount: '999999999999999999999.123456', currency: 'USD' }],
  scope_version: Number.MAX_SAFE_INTEGER,
  total_dag_node_count: 16,
})
const names = () => ({
  id: taskUuid(2),
  plan_revision: 7,
  naming_date: '2026-11-08',
  items: [
    {
      slot_key: 'ACCOUNT/CAMPAIGN/1',
      name: '渠道_昵称_20261108_0001',
      sequence: '000123456789012345678901234567',
    },
  ],
})
const allocation = () => ({
  id: taskUuid(1),
  plan_id: taskUuid(9),
  plan_revision: 7,
  state: 'SUCCEEDED',
  task_id: null,
  algorithm_version: 'allocation-v1',
  seed: 0,
  items: [
    {
      slot_key: 'slot',
      account_id: taskUuid(3),
      asset_id: taskUuid(4),
      asset_revision: Number.MAX_SAFE_INTEGER,
    },
  ],
  warnings: ['实际使用次数不一定相差1'],
  input_hash: hash,
})
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  auth.headers
    .mockReset()
    .mockImplementation((extra) => ({ ...extra, Authorization: 'Bearer memory-fixture' }))
  auth.credentials.mockReset().mockReturnValue('omit')
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
describe('投放预检原schema', () => {
  it('PlanValidation十字段完整保留、Money不转Float、无head_revision或客户端版本推算', () => {
    const result = parsePlanValidation(validation())
    expect(Object.keys(result)).toHaveLength(10)
    expect(result.budget_totals[0].amount).toBe('999999999999999999999.123456')
    expect(result.scope_version).toBe(Number.MAX_SAFE_INTEGER)
    expect(result).not.toHaveProperty('revision')
    expect(result).not.toHaveProperty('head_revision')
    const failed = {
      ...validation(),
      valid: false,
      hash: null,
      expires_at: null,
      errors: [field()],
    }
    expect(parsePlanValidation(failed)).toEqual(failed)
  })
  it.each(['extra', 'missing', 'unsafe', 'count', 'hash', 'expiry', 'errors', 'money', 'scope'])(
    '预检响应拒绝字段/上限错误：%s',
    (kind) => {
      const value: Record<string, unknown> = validation()
      if (kind === 'extra') value.runtime_id = taskUuid(1)
      if (kind === 'missing') delete value.total_dag_node_count
      if (kind === 'unsafe') value.scope_version = Number.MAX_SAFE_INTEGER + 1
      if (kind === 'count') value.ad_count = 2147483648
      if (kind === 'hash') value.hash = 'A'.repeat(64)
      if (kind === 'expiry') value.expires_at = '2026-02-30T00:00:00Z'
      if (kind === 'errors') value.errors = Array.from({ length: 1001 }, field)
      if (kind === 'money')
        value.budget_totals = Array.from({ length: 101 }, () => ({ amount: '0', currency: 'USD' }))
      if (kind === 'scope') value.scope_version = 0
      expect(() => parsePlanValidation(value)).toThrow()
    },
  )
  it('允许1000原FieldError、100币种项；constraint成功schema必须string，HTTP nullable另测', () => {
    const value = {
      ...validation(),
      errors: Array.from({ length: 1000 }, field),
      budget_totals: Array.from({ length: 100 }, () => ({ amount: '0', currency: 'USD' })),
    }
    expect(parsePlanValidation(value).errors).toHaveLength(1000)
    expect(parsePlanFieldError({ ...field(), constraint: '' }).constraint).toBe('')
    expect(() => parsePlanFieldError({ ...field(), constraint: null })).toThrow()
    expect(() => parsePlanFieldError({ ...field(), raw: '未知字段' })).toThrow()
    expect(() => parsePlanFieldError({ ...field(), message: '🙂'.repeat(1001) })).toThrow()
  })
  it.each([1.23, '1e3', '01', '-1', '1.1234567', '1,000', 'Infinity', '.1'])(
    '金额拒绝浮点/非规范十进制：%s',
    (amount) => {
      expect(() => parsePlanMoney({ amount, currency: 'USD' })).toThrow()
    },
  )
  it('Money允许零及六位小数原字符串，拒绝未知字段/非大写币种/长度溢出', () => {
    expect(parsePlanMoney({ amount: '0.000000', currency: 'JPY' }).amount).toBe('0.000000')
    for (const value of [
      { amount: '1', currency: 'usd' },
      { amount: '1', currency: 'USDX' },
      { amount: '1', currency: 'USD', converted: 1 },
      { amount: '9'.repeat(29), currency: 'USD' },
    ])
      expect(() => parsePlanMoney(value)).toThrow()
  })
  it('命名完整10000项、30位数字序号和前导零不转Number，真实日期不接受YYYYMMDD', () => {
    const value = names()
    value.items = Array.from({ length: 10000 }, () => value.items[0])
    expect(parseNameReservation(value).items).toHaveLength(10000)
    expect(parseNameReservation(names()).items[0].sequence).toBe('000123456789012345678901234567')
    for (const invalid of [
      { ...names(), naming_date: '20261108' },
      { ...names(), naming_date: '2026-02-29' },
      { ...names(), items: [] },
      { ...value, items: [...value.items, value.items[0]] },
      { ...names(), actor: taskUuid(1) },
    ])
      expect(() => parseNameReservation(invalid)).toThrow()
    expect(() =>
      parseNameReservation({ ...names(), items: [{ ...names().items[0], sequence: '1e3' }] }),
    ).toThrow()
  })
  it('Allocation task_id=null是合法异步分配，不能当Task；10000项/100警告保留', () => {
    const value = {
      ...allocation(),
      items: Array.from({ length: 10000 }, () => allocation().items[0]),
      warnings: Array.from({ length: 100 }, () => '警告'),
    }
    expect(parseAllocation(value).items).toHaveLength(10000)
    expect(parseAllocation(value).task_id).toBeNull()
    expect(() => parseAllocation({ ...value, items: [...value.items, value.items[0]] })).toThrow()
    expect(() => parseAllocation({ ...value, warnings: [...value.warnings, '超限'] })).toThrow()
  })
  it.each([
    'slot',
    'name',
    'sequence',
    'itemUnknown',
    'path',
    'code',
    'message',
    'constraint',
    'warning',
    'assetUuid',
  ])('嵌套文本及未知字段边界不遗漏：%s', (kind) => {
    if (['slot', 'name', 'sequence', 'itemUnknown'].includes(kind)) {
      const item: Record<string, unknown> = { ...names().items[0] }
      if (kind === 'slot') item.slot_key = '🙂'.repeat(513)
      if (kind === 'name') item.name = '🙂'.repeat(201)
      if (kind === 'sequence') item.sequence = '1'.repeat(31)
      if (kind === 'itemUnknown') item.asset_id = taskUuid(1)
      expect(() => parseNameReservation({ ...names(), items: [item] })).toThrow()
    } else if (kind === 'warning')
      expect(() => parseAllocation({ ...allocation(), warnings: ['🙂'.repeat(501)] })).toThrow()
    else if (kind === 'assetUuid')
      expect(() =>
        parseAllocation({ ...allocation(), items: [{ ...allocation().items[0], asset_id: 123 }] }),
      ).toThrow()
    else {
      const entry: Record<string, unknown> = { ...field() }
      entry[kind] = '🙂'.repeat(
        ({ path: 256, code: 65, message: 1001, constraint: 501 } as Record<string, number>)[kind],
      )
      expect(() => parsePlanFieldError(entry)).toThrow()
    }
  })
  it.each(['extra', 'state', 'revision', 'task', 'hash', 'seed', 'item', 'algorithm'])(
    'Allocation拒绝各字段错误：%s',
    (kind) => {
      const value: Record<string, unknown> = allocation()
      if (kind === 'extra') value.runtime_uuid = taskUuid(1)
      if (kind === 'state') value.state = 'COMPLETE'
      if (kind === 'revision') value.plan_revision = Number.MAX_SAFE_INTEGER + 1
      if (kind === 'task') value.task_id = 123
      if (kind === 'hash') value.input_hash = 'G'.repeat(64)
      if (kind === 'seed') value.seed = 2147483648
      if (kind === 'item') value.items = [{ ...allocation().items[0], asset_revision: 0 }]
      if (kind === 'algorithm') value.algorithm_version = ''
      expect(() => parseAllocation(value)).toThrow()
    },
  )
})
describe('冻结意图单次HTTP请求', () => {
  it.each([
    ['execute', 409, 'EXECUTION_PREPARATION_IN_PROGRESS', true],
    ['execute', 409, 'REVISION_CONFLICT', false],
    ['execute', 403, 'EXECUTION_PREPARATION_IN_PROGRESS', false],
    ['validate', 409, 'EXECUTION_PREPARATION_IN_PROGRESS', false],
  ] as const)('仅原execute忙态保留同键恢复：%s/%s/%s', async (operation, status, code, unknown) => {
    fetcher.mockResolvedValue(
      response(
        {
          code,
          message: '当前请求尚在准备',
          field_errors: [],
          retryable: false,
          request_id: taskUuid(8),
        },
        status,
      ),
    )
    const mutation =
      operation === 'execute'
        ? api.execute(taskUuid(9), { hash, activate_ack: false }, write)
        : api.validate(taskUuid(9), request, write)
    await expect(mutation).rejects.toMatchObject({
      code,
      status,
      unknown_result: unknown,
      http_status: status,
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(fetcher.mock.calls[0][1].headers['Idempotency-Key']).toBe(write.idempotency_key)
  })
  it('无正文原命名200，冻结三header不改写，认证仅内存header不在URL', async () => {
    fetcher.mockResolvedValue(response(names()))
    const result = await api.reserveNames(taskUuid(9), write)
    expect(result.plan_revision).toBe(7) // 不拿IfMatch=9冒充配置source_revision=7。
    const [url, init] = fetcher.mock.calls[0]
    expect(url).toContain(`/launch-plans/${taskUuid(9)}/campaign-names`)
    for (const secret of [write.csrf_token, write.idempotency_key, 'memory-fixture'])
      expect(url).not.toContain(secret)
    expect(init.body).toBeUndefined()
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({
      'If-Match': '"9"',
      'X-CSRF-Token': write.csrf_token,
      'Idempotency-Key': write.idempotency_key,
      Authorization: 'Bearer memory-fixture',
    })
    expect(init.cache).toBe('no-store')
  })
  it('Validate严格200，调用两次只由调用方明确重试同key，不猜head+1或改原对象', async () => {
    fetcher
      .mockResolvedValueOnce(response(validation()))
      .mockResolvedValueOnce(response(validation()))
    await api.validate(taskUuid(9), request, write)
    await api.validate(taskUuid(9), request, write)
    expect(fetcher).toHaveBeenCalledTimes(2)
    for (const [, init] of fetcher.mock.calls) {
      expect(JSON.parse(init.body)).toEqual(request)
      expect(init.headers['Idempotency-Key']).toBe(write.idempotency_key)
      expect(init.headers['If-Match']).toBe('"9"')
    }
    expect(Object.keys(request)).toEqual(['allocation_id', 'name_reservation_id'])
  })
  it('原202 Allocation与GET轮询分开，task_id=null不会生成任务ID', async () => {
    fetcher
      .mockResolvedValueOnce(response({ ...allocation(), state: 'QUEUED', items: [] }, 202))
      .mockResolvedValueOnce(response(allocation()))
    expect(
      (
        await api.allocate(
          taskUuid(9),
          {
            asset_ids: [taskUuid(4)],
            allow_repeat: false,
            seed: 0,
            algorithm_version: 'allocation-v1',
          },
          write,
        )
      ).task_id,
    ).toBeNull()
    expect((await api.allocation(taskUuid(9), taskUuid(1))).state).toBe('SUCCEEDED')
    expect(fetcher.mock.calls[1][1].method).toBe('GET')
    expect(fetcher.mock.calls[1][1].body).toBeUndefined()
    expect(fetcher.mock.calls[1][1].headers['If-Match']).toBeUndefined()
  })
  it('POST及GET分配结果必须属于请求的真实Plan及allocation，不接受外域ID', async () => {
    fetcher
      .mockResolvedValueOnce(response({ ...allocation(), plan_id: taskUuid(8) }, 202))
      .mockResolvedValueOnce(response({ ...allocation(), id: taskUuid(8) }))
    await expect(
      api.allocate(
        taskUuid(9),
        {
          asset_ids: [taskUuid(4)],
          allow_repeat: false,
          seed: 0,
          algorithm_version: 'allocation-v1',
        },
        write,
      ),
    ).rejects.toMatchObject({ code: 'INVALID_RESPONSE', unknown_result: true })
    await expect(api.allocation(taskUuid(9), taskUuid(1))).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
      unknown_result: false,
    })
  })
  it('execute严格202原Task，拒绝runtime/Allocation或错误200假受理', async () => {
    fetcher
      .mockResolvedValueOnce(response(taskFixture(), 202))
      .mockResolvedValueOnce(response(allocation(), 202))
      .mockResolvedValueOnce(response(taskFixture(), 200))
    expect((await api.execute(taskUuid(9), { hash, activate_ack: false }, write)).node_count).toBe(
      275,
    )
    await expect(
      api.execute(taskUuid(9), { hash, activate_ack: false }, write),
    ).rejects.toMatchObject({ code: 'INVALID_RESPONSE', unknown_result: true })
    await expect(
      api.execute(taskUuid(9), { hash, activate_ack: false }, write),
    ).rejects.toMatchObject({
      code: 'UNEXPECTED_HTTP_STATUS',
      http_status: 200,
      unknown_result: true,
    })
  })
  it.each([
    'unknown',
    'bareUUID',
    'braces',
    'missing',
    'ack',
    'hash',
    'duplicateAsset',
    'seed',
    'algorithm',
  ])('发送前拒绝原请求schema错误：%s', async (kind) => {
    let operation: Promise<unknown> | (() => Promise<unknown>)
    const run = () => {
      if (kind === 'unknown')
        return api.validate(taskUuid(9), { ...request, extra: true } as never, write)
      if (kind === 'bareUUID')
        return api.validate(
          taskUuid(9),
          { ...request, allocation_id: taskUuid(1).replaceAll('-', '') },
          write,
        )
      if (kind === 'braces') return api.validate(`{${taskUuid(9)}}`, request, write)
      if (kind === 'missing') return api.validate(taskUuid(9), {} as never, write)
      if (kind === 'ack')
        return api.execute(taskUuid(9), { hash, activate_ack: 'true' } as never, write)
      if (kind === 'hash')
        return api.execute(taskUuid(9), { hash: 'A'.repeat(64), activate_ack: true }, write)
      return api.allocate(
        taskUuid(9),
        {
          asset_ids:
            kind === 'duplicateAsset' ? [taskUuid(4), taskUuid(4).toUpperCase()] : [taskUuid(4)],
          allow_repeat: false,
          seed: kind === 'seed' ? -1 : 0,
          algorithm_version: kind === 'algorithm' ? 'other' : 'allocation-v1',
        } as never,
        write,
      )
    }
    // 请求函数可在调用点同步拒绝，统一观察Promise拒绝且不发任何HTTP。
    operation = Promise.resolve().then(run)
    await expect(operation).rejects.toBeInstanceOf(LaunchValidationError)
    expect(fetcher).not.toHaveBeenCalled()
  })
  it.each(['key', 'csrf', 'unquoted', 'unsafe', 'zero', 'missing', 'extra'])(
    '冻结header非法不补默认或生成新key：%s',
    async (kind) => {
      const headers: Record<string, unknown> = { ...write }
      if (kind === 'key') headers.idempotency_key = 'short'
      if (kind === 'csrf') headers.csrf_token = 'bad\r\nheader'
      if (kind === 'unquoted') headers.if_match = '9'
      if (kind === 'unsafe') headers.if_match = '"9007199254740992"'
      if (kind === 'zero') headers.if_match = '"0"'
      if (kind === 'missing') delete headers.csrf_token
      if (kind === 'extra') headers.actor = taskUuid(1)
      await expect(
        api.reserveNames(taskUuid(9), headers as unknown as FrozenMutation),
      ).rejects.toBeInstanceOf(LaunchValidationError)
      expect(fetcher).not.toHaveBeenCalled()
    },
  )
  it('Cookie当前csrf变化明确拒绝，不偷偷替换原冻结上下文', async () => {
    auth.headers.mockImplementation((extra) => ({
      ...extra,
      'X-CSRF-Token': 'changed-cookie-csrf',
    }))
    auth.credentials.mockReturnValue('same-origin')
    await expect(api.validate(taskUuid(9), request, write)).rejects.toMatchObject({
      code: 'CSRF_CONTEXT_CHANGED',
      status: 409,
    })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it.each([400, 401, 403, 404, 409, 410, 422, 429, 503])(
    'HTTP%s完整保留结构化Error和nullable通用constraint，不丢字段',
    async (status) => {
      const body = {
        code: 'FIELD_VALIDATION_FAILED',
        message: '字段校验未通过',
        field_errors: [{ ...field(), constraint: null }],
        retryable: status === 503,
        request_id: taskUuid(500),
      }
      fetcher.mockResolvedValueOnce(response(body, status))
      await expect(api.validate(taskUuid(9), request, write)).rejects.toMatchObject({
        status,
        http_status: status,
        ...body,
        unknown_result: false,
      })
      expect(fetcher).toHaveBeenCalledTimes(1)
    },
  )
  it('HTTP error继承现ReferenceApiError；异常error字段/100条上限严格拒绝但保留HTTP状态', async () => {
    const body = {
      code: 'ERROR',
      message: '请求失败',
      field_errors: [field()],
      retryable: false,
      request_id: taskUuid(500),
    }
    fetcher
      .mockResolvedValueOnce(response(body, 422))
      .mockResolvedValueOnce(response({ ...body, extra: true }, 422))
      .mockResolvedValueOnce(
        response({ ...body, field_errors: Array.from({ length: 101 }, field) }, 422),
      )
    await expect(api.validate(taskUuid(9), request, write)).rejects.toBeInstanceOf(
      ReferenceApiError,
    )
    for (let n = 0; n < 2; n++)
      await expect(api.validate(taskUuid(9), request, write)).rejects.toMatchObject({
        status: 422,
        code: 'INVALID_ERROR_RESPONSE',
      })
  })
  it.each([
    ['html', 502],
    ['html', 400],
    ['schema', 502],
    ['schema', 400],
  ] as const)(
    '非原%s错误HTTP%s不能证明mutation未受理，保留旧意图且不自动换键重试',
    async (kind, status) => {
      fetcher
        .mockResolvedValueOnce(
          kind === 'html'
            ? new Response('<html>gateway failure</html>', { status })
            : response({ message: 'non-contract error' }, status),
        )
        .mockResolvedValueOnce(response(names()))
      await expect(api.reserveNames(taskUuid(9), write)).rejects.toMatchObject({
        unknown_result: true,
        http_status: status,
      })
      expect(fetcher).toHaveBeenCalledTimes(1)
      await api.reserveNames(taskUuid(9), write)
      expect(fetcher.mock.calls[1][0]).toBe(fetcher.mock.calls[0][0])
      expect(fetcher.mock.calls[1][1].headers).toEqual(fetcher.mock.calls[0][1].headers)
      expect(fetcher.mock.calls[1][1].body).toBe(fetcher.mock.calls[0][1].body)
    },
  )
  it('GET遇网关HTML502或畸形400仍是只读失败，不产生未知写入意图', async () => {
    fetcher
      .mockResolvedValueOnce(new Response('<html>gateway</html>', { status: 502 }))
      .mockResolvedValueOnce(response({ unknown: true }, 400))
    for (const status of [502, 400])
      await expect(api.allocation(taskUuid(9), taskUuid(1))).rejects.toMatchObject({
        unknown_result: false,
        http_status: status,
      })
  })
  it('网络/超时写结果未知不自动重试，调用方保留原意图', async () => {
    fetcher.mockRejectedValueOnce(new TypeError('offline'))
    await expect(
      api.execute(taskUuid(9), { hash, activate_ack: false }, write),
    ).rejects.toMatchObject({ code: 'NETWORK_UNAVAILABLE', unknown_result: true })
    expect(fetcher).toHaveBeenCalledTimes(1)
    vi.useFakeTimers()
    fetcher.mockImplementationOnce(
      (_url, init) =>
        new Promise((_resolve, reject) =>
          init.signal.addEventListener('abort', () =>
            reject(new DOMException('abort', 'AbortError')),
          ),
        ),
    )
    const pending = api.validate(taskUuid(9), request, write)
    const rejected = expect(pending).rejects.toMatchObject({
      code: 'REQUEST_TIMEOUT',
      unknown_result: true,
    })
    await vi.advanceTimersByTimeAsync(15000)
    await rejected
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
  it('已取消不发送；写请求已发送后取消仅是结果未知，GET取消仍AbortError', async () => {
    const canceled = new AbortController()
    canceled.abort()
    await expect(api.validate(taskUuid(9), request, write, canceled.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(fetcher).not.toHaveBeenCalled()
    fetcher.mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) =>
          init.signal.addEventListener('abort', () =>
            reject(new DOMException('abort', 'AbortError')),
          ),
        ),
    )
    const writeController = new AbortController()
    const pending = api.validate(taskUuid(9), request, write, writeController.signal)
    writeController.abort()
    await expect(pending).rejects.toMatchObject({ code: 'REQUEST_ABORTED', unknown_result: true })
    const readController = new AbortController()
    const reading = api.allocation(taskUuid(9), taskUuid(1), readController.signal)
    readController.abort()
    await expect(reading).rejects.toMatchObject({ name: 'AbortError' })
  })
})
