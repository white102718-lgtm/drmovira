/** SDK传输/纯合同替身，不计规则scope真实HTTP/5万成员容量。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  freezeRuleEditorScopeIntent,
  parseRuleEditorMembers,
  parseRuleEditorScope,
  ruleEditorScopesApi,
  type RuleEditorAccountQuery,
  type RuleEditorScopeWrite,
} from '@/api/orbit/rule-editor-scopes'
const auth = vi.hoisted(() => ({
  cookie: false,
  token: 'Bearer session-a',
  csrf: 'cookie-original-csrf-token',
}))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => (auth.cookie ? 'same-origin' : 'omit'),
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra).entries()),
    ...(auth.cookie ? { 'x-csrf-token': auth.csrf } : { Authorization: auth.token }),
  }),
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const member = () => ({ account_id: id(), external_id: '000123', name: '真实账户😀' })
const page = () => ({
  items: [member()],
  next_cursor: null,
  data_as_of: '2026-11-09T00:00:00.123Z',
  scope_version: 3,
})
const scope = () => ({
  id: id(9),
  count: 1,
  scope_version: 3,
  hash: 'a'.repeat(64),
  created_at: '2026-11-09T00:00:00.123Z',
})
const headers = () => ({
  csrf_token: 'native-original-csrf-token',
  idempotency_key: 'original-rule-scope-key-001',
})
const owner = () => ({ owner_user_id: id(2), owner_team_id: id(3) })
const body = (update = false): RuleEditorScopeWrite =>
  update
    ? {
        action: 'UPDATE',
        rule_id: id(4),
        ownership: owner(),
        selection: { mode: 'IDS', account_ids: [id()], filter: null },
      }
    : {
        action: 'CREATE',
        rule_id: null,
        ownership: owner(),
        selection: { mode: 'IDS', account_ids: [id()], filter: null },
      }
const target = () => ({ action: 'CREATE' as const, ...owner() })
const failure = (code: string) => ({
  code,
  message: '范围来源暂未就绪',
  field_errors: [
    { path: '/selection', code: 'SOURCE', message: '请重新读取真实范围', constraint: null },
  ],
  retryable: true,
  request_id: id(99),
})
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
const fetcher = vi.fn()
beforeEach(() => {
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
  auth.cookie = false
  auth.token = 'Bearer session-a'
  auth.csrf = 'cookie-original-csrf-token'
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
it('三个rules路径精确，无launch/accounts权限端点请求', async () => {
  fetcher
    .mockResolvedValueOnce(response(page()))
    .mockResolvedValueOnce(response(scope(), 201))
    .mockResolvedValueOnce(response(page()))
  await ruleEditorScopesApi.accounts(target())
  await ruleEditorScopesApi.create(body(), headers())
  await ruleEditorScopesApi.members(id(9))
  expect(
    fetcher.mock.calls.map((call) => new URL(call[0], 'https://fixture.test').pathname),
  ).toEqual([
    '/dev-api/api/v1/rules/editor-accounts',
    '/dev-api/api/v1/rules/editor-scope-snapshots',
    `/dev-api/api/v1/rules/editor-scope-snapshots/${id(9)}/members`,
  ])
  expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store' })
  expect(fetcher.mock.calls[0][1].body).toBeUndefined()
  expect(fetcher.mock.calls[1][1].method).toBe('POST')
})
it('POST精确四键/Scope5 count保留521，不套Plan500', async () => {
  const value = body()
  value.selection.account_ids = Array.from({ length: 521 }, (_, index) => id(index + 1))
  fetcher.mockResolvedValue(response({ ...scope(), count: 521 }, 201))
  expect(await ruleEditorScopesApi.create(value, headers())).toEqual({ ...scope(), count: 521 })
  const init = fetcher.mock.calls[0][1]
  expect(JSON.parse(init.body)).toEqual(value)
  expect(Object.keys(JSON.parse(init.body))).toHaveLength(4)
  expect(new Headers(init.headers).get('if-match')).toBeNull()
  expect(new Headers(init.headers).get('idempotency-key')).toBe(headers().idempotency_key)
})
it('UPDATE必须quotedIfMatch且值精确，CREATE禁止版本头', async () => {
  fetcher.mockResolvedValue(response(scope(), 201))
  await ruleEditorScopesApi.create(body(true), { ...headers(), if_match: '"9007199254740991"' })
  expect(new Headers(fetcher.mock.calls[0][1].headers).get('if-match')).toBe('"9007199254740991"')
  for (const match of ['1', '"0"', '"01"', '"9007199254740992"'])
    await expect(
      ruleEditorScopesApi.create(body(true), { ...headers(), if_match: match }),
    ).rejects.toMatchObject({ status: 422 })
  await expect(
    ruleEditorScopesApi.create(body(), { ...headers(), if_match: '"1"' }),
  ).rejects.toMatchObject({ status: 422 })
  await expect(ruleEditorScopesApi.create(body(true), headers())).rejects.toMatchObject({
    status: 422,
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('IDS重复按规范UUID先限原数量、不静默去重', async () => {
  const value = body()
  value.selection.account_ids = [id(), id().toUpperCase()]
  await expect(ruleEditorScopesApi.create(value, headers())).rejects.toMatchObject({
    code: 'DUPLICATE_VALUE',
    field_errors: [
      {
        path: '/account_ids/1',
        code: 'DUPLICATE_VALUE',
        message: '不能重复选择同一账户',
        constraint: null,
      },
    ],
  })
  value.selection.account_ids = Array(50001).fill(id())
  await expect(ruleEditorScopesApi.create(value, headers())).rejects.toMatchObject({
    code: 'FIELD_INVALID',
  })
  expect(fetcher).not.toHaveBeenCalled()
})
it('5万纯DTO边界允许且50001先拒，非容量验收', () => {
  const value = body()
  value.selection.account_ids = Array.from({ length: 50000 }, (_, index) => id(index + 1))
  const fixed = freezeRuleEditorScopeIntent(value, headers())
  expect(fixed.body.selection.account_ids).toHaveLength(50000)
  expect(fixed.body.selection.account_ids[49999]).toBe(id(50000))
})
it('FILTER全五字段与空IDs原样冻结，不拉当前页拼全选', async () => {
  const value = body()
  value.selection = {
    mode: 'FILTER',
    account_ids: [],
    filter: {
      q: ' e\u0301%_! ',
      status: null,
      auth_status: 'AUTHORIZED',
      operator_user_id: null,
      vendor_id: null,
    },
  }
  fetcher.mockResolvedValue(response(scope(), 201))
  await ruleEditorScopesApi.create(value, headers())
  const wire = JSON.parse(fetcher.mock.calls[0][1].body)
  expect(wire.selection).toEqual({
    mode: 'FILTER',
    account_ids: [],
    filter: {
      q: 'é%_!',
      status: null,
      auth_status: 'AUTHORIZED',
      operator_user_id: null,
      vendor_id: null,
    },
  })
  expect(value.selection.filter.q).toBe(' e\u0301%_! ')
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('同步冻结原wire正文/key/CAS，调用方变化不能改在途请求', async () => {
  let release!: (value: Response) => void
  fetcher.mockReturnValue(
    new Promise<Response>((r) => {
      release = r
    }),
  )
  const value = body(true),
    original = { ...headers(), if_match: '"7"' }
  const frozen = freezeRuleEditorScopeIntent(value, original)
  expect(Object.isFrozen(frozen.body.selection.account_ids)).toBe(true)
  const pending = ruleEditorScopesApi.create(frozen.body, frozen.auth)
  value.selection.account_ids.push(id(8))
  original.if_match = '"8"'
  release(response(scope(), 201))
  await pending
  expect(JSON.parse(fetcher.mock.calls[0][1].body).selection.account_ids).toEqual([id()])
  expect(new Headers(fetcher.mock.calls[0][1].headers).get('if-match')).toBe('"7"')
})
it('未知结果后仅手动同frozen意图重试，不自动换key/body/CAS', async () => {
  const fixed = freezeRuleEditorScopeIntent(body(true), { ...headers(), if_match: '"7"' })
  fetcher.mockRejectedValueOnce(new TypeError('network')).mockResolvedValue(response(scope(), 201))
  await expect(ruleEditorScopesApi.create(fixed.body, fixed.auth)).rejects.toMatchObject({
    code: 'NETWORK_UNAVAILABLE',
    unknown_result: true,
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
  await ruleEditorScopesApi.create(fixed.body, fixed.auth)
  expect(fetcher.mock.calls[0][1].body).toBe(fetcher.mock.calls[1][1].body)
  expect(fetcher.mock.calls[0][1].headers).toEqual(fetcher.mock.calls[1][1].headers)
})
it.each([20, 50, 100, 200] as const)('候选/成员四档%d与原opaque cursor', async (size) => {
  fetcher.mockImplementation(async () => response(page()))
  await ruleEditorScopesApi.accounts({ ...target(), page_size: size, cursor: 'opaque+/=' })
  await ruleEditorScopesApi.members(id(9), { page_size: size, cursor: 'opaque+/=' })
  for (const call of fetcher.mock.calls) {
    const url = new URL(call[0], 'https://fixture.test')
    expect(url.searchParams.get('page_size')).toBe(String(size))
    expect(url.searchParams.get('cursor')).toBe('opaque+/=')
  }
})
it('accounts q空白可规范空，members原非空空白拒绝，NFC100/101', async () => {
  fetcher.mockImplementation(async () => response(page()))
  await ruleEditorScopesApi.accounts({
    ...target(),
    q: '  ',
    status: 'UNKNOWN',
    auth_status: 'REVOKED',
    operator_user_id: id(2),
    vendor_id: id(6),
  })
  expect(new URL(fetcher.mock.calls[0][0], 'https://fixture.test').searchParams.get('q')).toBe('')
  await ruleEditorScopesApi.members(id(9), { q: 'e\u0301'.repeat(100) })
  expect(new URL(fetcher.mock.calls[1][0], 'https://fixture.test').searchParams.get('q')).toBe(
    'é'.repeat(100),
  )
  await expect(ruleEditorScopesApi.members(id(9), { q: ' ' })).rejects.toMatchObject({
    status: 422,
  })
  await expect(
    ruleEditorScopesApi.accounts({ ...target(), q: 'e\u0301'.repeat(101) }),
  ).rejects.toMatchObject({ status: 422 })
})
it('严格query组合、非法Unicode/unknown字段在fetch前拒绝', async () => {
  const bad: unknown[] = [
    { ...target(), rule_id: id() },
    { ...target(), action: 'UPDATE' },
    { ...target(), owner_user_id: 'invalid' },
    { ...target(), q: '\n' },
    { ...target(), q: '\ud800' },
    { ...target(), status: null },
    { ...target(), auth_status: 'ACTIVE' },
    { ...target(), date_from: '2026-01-01' },
    { ...target(), page_size: '20' },
    { ...target(), cursor: '' },
  ]
  for (const value of bad)
    await expect(
      ruleEditorScopesApi.accounts(value as RuleEditorAccountQuery),
    ).rejects.toMatchObject({ status: 422 })
  await expect(ruleEditorScopesApi.members('invalid')).rejects.toMatchObject({ status: 422 })
  expect(fetcher).not.toHaveBeenCalled()
})
it('写入缺四键/错CREATE-null/不完整FILTER/空IDS均拒绝', async () => {
  const values: unknown[] = [
    { ...body(), extra: true },
    { ...body(), rule_id: id() },
    { ...body(true), rule_id: null },
    { ...body(), selection: { mode: 'IDS', account_ids: [], filter: null } },
    { ...body(), selection: { mode: 'FILTER', account_ids: [], filter: { q: '' } } },
    { ...body(), selection: { mode: 'FILTER', account_ids: [id()], filter: null } },
  ]
  for (const value of values)
    await expect(
      ruleEditorScopesApi.create(value as RuleEditorScopeWrite, headers()),
    ).rejects.toMatchObject({ status: 422 })
  expect(fetcher).not.toHaveBeenCalled()
})
it('Scope严格非空1..50000/hex/UTC，Member3与Page4拒坏结构', () => {
  for (const value of [
    { ...scope(), count: 0 },
    { ...scope(), count: 50001 },
    { ...scope(), hash: 'x'.repeat(64) },
    { ...scope(), extra: true },
    { ...scope(), created_at: '2026-11-09T01:00:00+01:00' },
  ])
    expect(() => parseRuleEditorScope(value)).toThrow()
  for (const value of [
    { ...page(), extra: 1 },
    { ...page(), items: [{ ...member(), extra: true }] },
    { ...page(), items: [member(), member()] },
  ])
    expect(() => parseRuleEditorMembers(value)).toThrow()
  expect(parseRuleEditorMembers(page()).items[0].external_id).toBe('000123')
})
it.each([403, 409, 422, 503])('明确服务器%d保留code/path/ID，不标网络未知', async (status) => {
  fetcher.mockResolvedValue(response(failure('RULE_SCOPE_SOURCE'), status))
  await expect(ruleEditorScopesApi.create(body(), headers())).rejects.toMatchObject({
    status,
    code: 'RULE_SCOPE_SOURCE',
    field_errors: failure('').field_errors,
    request_id: id(99),
    source: 'server',
    unknown_result: false,
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('写入坏响应/非201/认证晚回标未知，不伪成功', async () => {
  fetcher
    .mockResolvedValueOnce(response(scope(), 200))
    .mockResolvedValueOnce(response({ ...scope(), count: 0 }, 201))
  await expect(ruleEditorScopesApi.create(body(), headers())).rejects.toMatchObject({
    code: 'UNEXPECTED_HTTP_STATUS',
    unknown_result: true,
  })
  await expect(ruleEditorScopesApi.create(body(), headers())).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
    unknown_result: true,
  })
  fetcher.mockImplementation(async () => {
    auth.token = 'Bearer session-b'
    return response(scope(), 201)
  })
  await expect(ruleEditorScopesApi.create(body(), headers())).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
    unknown_result: true,
  })
})
it('Cookie真实CSRF覆盖变化在发送前409，不发旧意图也不标未知', async () => {
  auth.cookie = true
  await expect(ruleEditorScopesApi.create(body(), headers())).rejects.toMatchObject({
    code: 'CSRF_CONTEXT_CHANGED',
    unknown_result: false,
  })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockResolvedValue(response(scope(), 201))
  await ruleEditorScopesApi.create(body(), { ...headers(), csrf_token: auth.csrf })
  expect(fetcher.mock.calls[0][1].credentials).toBe('same-origin')
})
it('已取消不发送，发出后POST取消标未知，GET取消抛AbortError', async () => {
  const pre = new AbortController()
  pre.abort()
  await expect(ruleEditorScopesApi.create(body(), headers(), pre.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockImplementation(
    (_path, init) =>
      new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('abort', 'AbortError')),
        ),
      ),
  )
  const write = new AbortController()
  const pending = ruleEditorScopesApi.create(body(), headers(), write.signal)
  write.abort()
  await expect(pending).rejects.toMatchObject({ code: 'REQUEST_ABORTED', unknown_result: true })
  const read = new AbortController()
  const reading = ruleEditorScopesApi.accounts(target(), read.signal)
  read.abort()
  await expect(reading).rejects.toMatchObject({ name: 'AbortError' })
})
it('客户端15秒有界设置，不冒充原服务端10秒容量标准', async () => {
  vi.useFakeTimers()
  fetcher.mockImplementation(
    (_path, init) =>
      new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('abort', 'AbortError')),
        ),
      ),
  )
  const pending = ruleEditorScopesApi.create(body(), headers())
  const check = expect(pending).rejects.toMatchObject({
    code: 'READ_TIMEOUT',
    unknown_result: true,
  })
  await vi.advanceTimersByTimeAsync(15000)
  await check
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('IDS受理count必须完整对应原选择，不能静默丢成员', async () => {
  const value = body()
  value.selection.account_ids.push(id(2))
  fetcher.mockResolvedValue(response(scope(), 201))
  await expect(ruleEditorScopesApi.create(value, headers())).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
    unknown_result: true,
  })
})
it('members只能q/page/cursor，非primitive状态不能靠toString通过', async () => {
  await expect(
    ruleEditorScopesApi.members(id(9), { action: 'CREATE' } as never),
  ).rejects.toMatchObject({ status: 422 })
  await expect(
    ruleEditorScopesApi.accounts({ ...target(), status: new String('ACTIVE') } as never),
  ).rejects.toMatchObject({ status: 422 })
  expect(fetcher).not.toHaveBeenCalled()
})
