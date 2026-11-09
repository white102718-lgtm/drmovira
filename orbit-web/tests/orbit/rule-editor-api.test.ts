/** Editor GET传输/合同替身纯测；不等于真实候选权限或SQL验收。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  parseRuleEditorContext,
  parseRuleOwnerPage,
  parseRuleProfilePage,
  ruleEditorApi,
  RuleEditorApiError,
  type RuleEditorQuery,
  type RuleEditorTarget,
} from '@/api/orbit/rule-editor'
const auth = vi.hoisted(() => ({
  token: 'Bearer session-a',
  cookie: false,
  csrf: 'fixture-cookie-csrf',
}))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => (auth.cookie ? 'same-origin' : 'omit'),
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra).entries()),
    ...(auth.cookie ? { 'x-csrf-token': auth.csrf } : { Authorization: auth.token }),
  }),
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const owner = () => ({ id: id(), team_id: id(2), name: '真实投放师', team_name: '真实团队' })
const profile = () => ({
  id: id(4),
  version: 'profile-v1',
  source: 'META',
  register_action_type: null,
  purchase_action_type: 'purchase',
  value_action_type: 'purchase',
  attribution_windows: ['7d_click'],
  action_report_time: 'conversion',
  timezone_policy: 'ACCOUNT_LOCAL',
  breakdown: 'TOTAL',
  maturity_days: 28,
  verified: true,
})
const context = (update = false) => ({
  action: update ? 'UPDATE' : 'CREATE',
  rule_id: update ? id(3) : null,
  rule_revision: update ? 9 : null,
  editable: true,
  csrf_token: 'fixture-context-csrf-token',
  default_ownership: { owner_user_id: id(), owner_team_id: id(2) },
  selected_owner: { item: owner(), can_keep: true },
  selected_profile: update
    ? { id: id(4), bound_version: 'profile-v1', current: profile(), status: 'CURRENT' }
    : null,
})
const page = (items: unknown[] = [owner()]) => ({
  items,
  next_cursor: null,
  data_as_of: '2026-11-09T00:00:00.123Z',
  scope_version: Number.MAX_SAFE_INTEGER,
})
const server = (code = 'RULE_EDITOR_UNAVAILABLE') => ({
  code,
  message: '候选来源未就绪',
  field_errors: [{ path: '/owner_user_id', code: 'SOURCE', message: '重新加载', constraint: null }],
  retryable: true,
  request_id: id(90),
})
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const fetcher = vi.fn()
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
  auth.token = 'Bearer session-a'
  auth.cookie = false
  auth.csrf = 'fixture-cookie-csrf'
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
it('CREATE/UPDATE原Context8与GET路径，无body或额外动作', async () => {
  fetcher.mockResolvedValueOnce(response(context())).mockResolvedValueOnce(response(context(true)))
  expect(await ruleEditorApi.context({ action: 'CREATE' })).toEqual(context())
  expect(await ruleEditorApi.context({ action: 'UPDATE', rule_id: id(3) })).toEqual(context(true))
  const [path, init] = fetcher.mock.calls[0]
  expect(path).toContain('/api/v1/rules/edit-context?action=CREATE')
  expect(init).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'omit' })
  expect(init.body).toBeUndefined()
  expect(new Headers(init.headers).get('authorization')).toBe(auth.token)
})
it('OWNER字面prefix q仅trim+NFC，不扩成contains或改调用方', async () => {
  fetcher.mockResolvedValue(response(page()))
  const target = { action: 'CREATE', kind: 'OWNER', q: '  e\u0301%_!  ', page_size: 20 } as const
  await ruleEditorApi.options(target)
  const url = new URL(fetcher.mock.calls[0][0], 'https://fixture.test')
  expect(url.searchParams.get('q')).toBe('é%_!')
  expect(target.q).toBe('  e\u0301%_!  ')
  expect(url.searchParams.get('kind')).toBe('OWNER')
  expect(url.searchParams.has('owner_user_id')).toBe(false)
})
it('PROFILE复用原12字段，owner/team与UUID q明确query', async () => {
  fetcher.mockResolvedValue(response(page([profile()])))
  const result = await ruleEditorApi.options({
    action: 'UPDATE',
    rule_id: id(3),
    kind: 'PROFILE',
    owner_user_id: id(),
    owner_team_id: id(2),
    q: id(4),
    page_size: 200,
    cursor: 'opaque+/=',
  })
  expect(result.items[0]).toEqual(profile())
  expect(Object.keys(result.items[0])).toHaveLength(12)
  const url = new URL(fetcher.mock.calls[0][0], 'https://fixture.test')
  expect(Object.fromEntries(url.searchParams)).toEqual({
    action: 'UPDATE',
    rule_id: id(3),
    kind: 'PROFILE',
    owner_user_id: id(),
    owner_team_id: id(2),
    q: id(4),
    page_size: '200',
    cursor: 'opaque+/=',
  })
})
it.each([20, 50, 100, 200] as const)('四档%d与opaque cursor原样', async (size) => {
  fetcher.mockResolvedValue(response(page()))
  await ruleEditorApi.options({
    action: 'CREATE',
    kind: 'OWNER',
    page_size: size,
    cursor: 'opaque+/=',
  })
  const url = new URL(fetcher.mock.calls[0][0], 'https://fixture.test')
  expect(url.searchParams.get('page_size')).toBe(String(size))
  expect(url.searchParams.get('cursor')).toBe('opaque+/=')
})
it('合法不可保留旧owner和UNAVAILABLE/CHANGED profile不造资格', () => {
  const value = context(true)
  value.selected_owner = { item: null, can_keep: false } as unknown as typeof value.selected_owner
  value.selected_profile = {
    id: id(4),
    bound_version: 'old-v0',
    current: null,
    status: 'UNAVAILABLE',
  } as unknown as typeof value.selected_profile
  expect(parseRuleEditorContext(value)).toEqual(value)
  value.selected_profile!.current = profile()
  value.selected_profile!.status = 'CHANGED'
  expect(parseRuleEditorContext(value).selected_profile?.status).toBe('CHANGED')
})
it('Context严格键/当前profile状态与版本/owner关联不能伪造', () => {
  const bad: unknown[] = [
    { ...context(), extra: true },
    { ...context(), rule_id: id(3) },
    { ...context(true), rule_revision: 0 },
    { ...context(true), selected_profile: null },
    { ...context(), selected_owner: { item: null, can_keep: true } },
    { ...context(), selected_owner: { item: { ...owner(), team_id: id(88) }, can_keep: true } },
    {
      ...context(true),
      selected_profile: { ...context(true).selected_profile, status: 'CHANGED' },
    },
    {
      ...context(true),
      selected_profile: { ...context(true).selected_profile, current: null, status: 'CURRENT' },
    },
  ]
  for (const value of bad) expect(() => parseRuleEditorContext(value)).toThrow(RuleEditorApiError)
})
it('Page4严格类型/重复项/200上限/UTC与未知新增字段拒绝', () => {
  expect(parseRuleOwnerPage(page([]))).toEqual(page([]))
  for (const bad of [
    { ...page(), extra: 1 },
    page([owner(), owner()]),
    page(Array(201).fill(owner())),
    { ...page(), scope_version: 0 },
    { ...page(), data_as_of: '2026-02-30T00:00:00Z' },
    { ...page(), data_as_of: '2026-11-09T01:00:00+01:00' },
    { ...page([]), next_cursor: 'missing' },
  ])
    expect(() => parseRuleOwnerPage(bad)).toThrow(RuleEditorApiError)
  expect(() => parseRuleProfilePage(page([{ ...profile(), name: '虚构字段' }]))).toThrow(
    RuleEditorApiError,
  )
})
it('严格组合和未知参数在fetch前拒绝', async () => {
  const targets: unknown[] = [
    {},
    { action: 'EDIT' },
    { action: 'CREATE', rule_id: id() },
    { action: 'UPDATE' },
    { action: 'UPDATE', rule_id: 'not-uuid' },
    { action: 'CREATE', q: 'x' },
  ]
  for (const target of targets)
    await expect(ruleEditorApi.context(target as RuleEditorTarget)).rejects.toMatchObject({
      status: 422,
      code: 'FIELD_INVALID',
    })
  const options: unknown[] = [
    { action: 'CREATE', kind: 'OWNER', owner_user_id: id() },
    { action: 'CREATE', kind: 'OWNER', owner_team_id: id(2) },
    { action: 'CREATE', kind: 'PROFILE' },
    { action: 'CREATE', kind: 'ACCOUNT' },
    { action: 'CREATE', kind: 'OWNER', page_size: '20' },
    { action: 'CREATE', kind: 'OWNER', page_size: 201 },
    { action: 'CREATE', kind: 'OWNER', cursor: '' },
    { action: 'CREATE', kind: 'OWNER', q: '\n' },
    { action: 'CREATE', kind: 'OWNER', q: '\ud800' },
    { action: 'CREATE', kind: 'OWNER', q: '   ' },
    { action: 'CREATE', kind: 'PROFILE', owner_user_id: id(), owner_team_id: id(2), q: 'v1' },
  ]
  for (const value of options)
    await expect(ruleEditorApi.options(value as RuleEditorQuery)).rejects.toMatchObject({
      status: 422,
    })
  expect(fetcher).not.toHaveBeenCalled()
})
it('q先NFC按码点100/101边界且空串合法', async () => {
  fetcher.mockResolvedValue(response(page()))
  await ruleEditorApi.options({ action: 'CREATE', kind: 'OWNER', q: 'e\u0301'.repeat(100) })
  expect(new URL(fetcher.mock.calls[0][0], 'https://fixture.test').searchParams.get('q')).toBe(
    'é'.repeat(100),
  )
  await expect(
    ruleEditorApi.options({ action: 'CREATE', kind: 'OWNER', q: 'e\u0301'.repeat(101) }),
  ).rejects.toMatchObject({ status: 422 })
  fetcher.mockResolvedValue(response(page()))
  await ruleEditorApi.options({ action: 'CREATE', kind: 'OWNER', q: '' })
  expect(new URL(fetcher.mock.calls[1][0], 'https://fixture.test').searchParams.get('q')).toBe('')
})
it.each([503, 409])('原服务端%d/code/path/request_id保真且不重试', async (status) => {
  fetcher.mockResolvedValue(
    response(server(status === 409 ? 'RULE_EDITOR_CHANGED' : 'RULE_EDITOR_UNAVAILABLE'), status),
  )
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    status,
    code: status === 409 ? 'RULE_EDITOR_CHANGED' : 'RULE_EDITOR_UNAVAILABLE',
    field_errors: server().field_errors,
    request_id: id(90),
    source: 'server',
    unknown_result: false,
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('畸形服务端错误不能化为空页或冒充已核来源', async () => {
  fetcher.mockResolvedValue(response({ code: 'FAIL', token: 'must-not-echo' }, 503))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    status: 503,
    code: 'INVALID_ERROR_RESPONSE',
  })
})
it('Context必须匹配本次action/rule，跨对象响应拒绝', async () => {
  fetcher.mockResolvedValue(response(context(true)))
  await expect(ruleEditorApi.context({ action: 'UPDATE', rule_id: id(66) })).rejects.toMatchObject({
    status: 502,
    code: 'INVALID_RESPONSE',
  })
})
it('Cookie headers与credentials用既有auth，响应身份变化丢弃', async () => {
  auth.cookie = true
  fetcher.mockImplementation(async () => {
    auth.csrf = 'new-cookie'
    return response(context())
  })
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
  const init = fetcher.mock.calls[0][1]
  expect(init.credentials).toBe('same-origin')
  expect(new Headers(init.headers).get('x-csrf-token')).toBe('fixture-cookie-csrf')
  expect(new Headers(init.headers).has('authorization')).toBe(false)
})
it('已取消调用不发fetch，在途取消与listener清理', async () => {
  const pre = new AbortController()
  pre.abort()
  await expect(ruleEditorApi.context({ action: 'CREATE' }, pre.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
  expect(fetcher).not.toHaveBeenCalled()
  const controller = new AbortController()
  const remove = vi.spyOn(controller.signal, 'removeEventListener')
  fetcher.mockImplementation(
    (_path, init) =>
      new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('abort', 'AbortError')),
        ),
      ),
  )
  const pending = ruleEditorApi.context({ action: 'CREATE' }, controller.signal)
  controller.abort()
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  expect(remove).toHaveBeenCalledWith('abort', expect.any(Function))
})
it('超时15秒有界且不重试，网络错误不伪成功', async () => {
  vi.useFakeTimers()
  fetcher.mockImplementation(
    (_path, init) =>
      new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('abort', 'AbortError')),
        ),
      ),
  )
  const pending = ruleEditorApi.context({ action: 'CREATE' })
  const check = expect(pending).rejects.toMatchObject({ code: 'READ_TIMEOUT', retryable: true })
  await vi.advanceTimersByTimeAsync(15000)
  await check
  expect(fetcher).toHaveBeenCalledTimes(1)
  vi.useRealTimers()
  fetcher.mockRejectedValue(new TypeError('network'))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'NETWORK_UNAVAILABLE',
  })
})
it('错误HTTP状态/非法JSON/非法UTF8/预算溢出全部失败关闭', async () => {
  fetcher.mockResolvedValueOnce(response(context(), 201))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'UNEXPECTED_HTTP_STATUS',
  })
  fetcher.mockResolvedValueOnce(new Response('invalid json'))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
  })
  fetcher.mockResolvedValueOnce(new Response(new Uint8Array([0xff])))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
  })
  fetcher.mockResolvedValueOnce(new Response(' '.repeat(2 * 1024 * 1024 + 1)))
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
  })
})
it('响应正文在途取消立即停止流读取并移除监听', async () => {
  const controller = new AbortController(),
    cancel = vi.fn()
  fetcher.mockResolvedValue(
    new Response(
      new ReadableStream({
        start(stream) {
          stream.enqueue(new TextEncoder().encode('{'))
        },
        cancel,
      }),
    ),
  )
  const pending = ruleEditorApi.context({ action: 'CREATE' }, controller.signal)
  await Promise.resolve()
  await Promise.resolve()
  controller.abort()
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  expect(cancel).toHaveBeenCalledTimes(1)
})
it('响应流清理失败不替代原业务错误', async () => {
  // 单块已超过预算，使读取不依赖服务器主动结束；清理异常不得外泄。
  fetcher.mockResolvedValue(
    new Response(
      new ReadableStream({
        start(stream) {
          stream.enqueue(new TextEncoder().encode(' '.repeat(2 * 1024 * 1024 + 1)))
        },
        cancel() {
          throw new Error('cleanup-failed')
        },
      }),
    ),
  )
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
    message: '规则编辑来源响应未能确认',
  })
})
it('超过请求page_size或PROFILE精确UUID过滤的响应拒绝', async () => {
  fetcher.mockResolvedValueOnce(
    response(page(Array.from({ length: 21 }, (_, i) => ({ ...owner(), id: id(i + 100) })))),
  )
  await expect(
    ruleEditorApi.options({ action: 'CREATE', kind: 'OWNER', page_size: 20 }),
  ).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  fetcher.mockResolvedValueOnce(response(page([profile()])))
  await expect(
    ruleEditorApi.options({
      action: 'CREATE',
      kind: 'PROFILE',
      owner_user_id: id(),
      owner_team_id: id(2),
      q: id(5),
    }),
  ).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
it('Bearer晚回认证变更丢弃，不接受另一请求的context', async () => {
  fetcher.mockImplementation(async () => {
    auth.token = 'Bearer session-b'
    return response(context())
  })
  await expect(ruleEditorApi.context({ action: 'CREATE' })).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
})
