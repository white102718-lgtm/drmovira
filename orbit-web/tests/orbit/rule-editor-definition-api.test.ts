/** 专属edit-definition协议纯测；不计真实rule编辑/manifest授权。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  parseRuleEditorDefinition,
  ruleEditorDefinitionApi,
} from '@/api/orbit/rule-editor-definition'
const auth = vi.hoisted(() => ({ token: 'Bearer current' }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'omit',
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra).entries()),
    Authorization: auth.token,
  }),
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const definition = () => ({
  rule: {
    id: id(),
    revision: 3,
    state: 'PAUSED',
    next_run_at: null,
    name: '原规则',
    ownership: { owner_user_id: id(2), owner_team_id: id(3) },
    target_level: 'AD',
    scope_snapshot_id: id(4),
    logic: 'AND',
    groups: [
      { logic: 'AND', conditions: [{ metric: 'spend', operator: 'GTE', threshold: '0.000001' }] },
    ],
    window: 'LAST_3D',
    metric_profile_id: id(5),
    schedule: {
      frequency: 'INTERVAL',
      interval_minutes: 30,
      time_of_day: null,
      weekday: null,
      timezone: 'America/New_York',
      start_date: '2026-01-01',
      end_date: '2026-12-31',
    },
    cooldown_minutes: 60,
    max_daily: 5,
  },
  stored_scope: { id: id(4), count: 521, owner_user_id: id(2), owner_team_id: id(3) },
})
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status })
const fetcher = vi.fn()
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
  auth.token = 'Bearer current'
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
it('专属rules.edit source GET，不调用通用read或其它模块', async () => {
  fetcher.mockResolvedValue(response(definition()))
  expect(await ruleEditorDefinitionApi.get(id())).toEqual(definition())
  expect(fetcher.mock.calls[0][0]).toBe(`/dev-api/api/v1/rules/${id()}/edit-definition`)
  expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store' })
  expect(fetcher.mock.calls[0][1].body).toBeUndefined()
})
it('strict两键/原Rule15/真实stored_scope4，521不套Plan500', () => {
  const result = parseRuleEditorDefinition(definition())
  expect(Object.keys(result)).toHaveLength(2)
  expect(Object.keys(result.rule)).toHaveLength(15)
  expect(Object.keys(result.stored_scope)).toHaveLength(4)
  expect(result.stored_scope.count).toBe(521)
  expect(result.stored_scope).not.toHaveProperty('hash')
  expect(result.stored_scope).not.toHaveProperty('created_at')
})
it('错scope/owner/team/count/新增键不能用作旧manifest', () => {
  for (const change of [
    { id: id(9) },
    { owner_user_id: id(9) },
    { owner_team_id: id(9) },
    { count: 0 },
    { count: 50001 },
    { hash: 'a'.repeat(64) },
  ])
    expect(() =>
      parseRuleEditorDefinition({
        ...definition(),
        stored_scope: { ...definition().stored_scope, ...change },
      }),
    ).toThrow()
  expect(() => parseRuleEditorDefinition({ ...definition(), extra: true })).toThrow()
})
it('对应请求规则ID仍须一致，不能接别的定义', async () => {
  fetcher.mockResolvedValue(response(definition()))
  await expect(ruleEditorDefinitionApi.get(id(9))).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
  })
  await expect(ruleEditorDefinitionApi.get('invalid')).rejects.toMatchObject({ status: 422 })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it.each([403, 409, 503])('真实%d错误code/path不伪空定义', async (status) => {
  fetcher.mockResolvedValue(
    response(
      {
        code: 'DEFINITION_SOURCE',
        message: '定义来源未就绪',
        field_errors: [],
        retryable: true,
        request_id: id(8),
      },
      status,
    ),
  )
  await expect(ruleEditorDefinitionApi.get(id())).rejects.toMatchObject({
    status,
    code: 'DEFINITION_SOURCE',
    source: 'server',
    unknown_result: false,
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('认证晚回与预取消拒绝，不把旧定义展示给新身份', async () => {
  fetcher.mockImplementation(async () => {
    auth.token = 'Bearer another'
    return response(definition())
  })
  await expect(ruleEditorDefinitionApi.get(id())).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
  const abort = new AbortController()
  abort.abort()
  await expect(ruleEditorDefinitionApi.get(id(), abort.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
})
