/** 恢复身份纯协议；fetch替身不代表真实登录或HTTP。 */
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import {
  ruleRecoveryApi,
  parseRuleRecoveryContext,
  recoveryPrincipal,
  requireRecoveryPrincipal,
  requireInitialRuleActor,
} from '@/api/orbit/rule-recovery'
const auth = vi.hoisted(() => ({ token: 'current' }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'omit',
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra)),
    Authorization: auth.token,
  }),
}))
const tenant = '00000000-0000-4000-8000-000000000099'
const ctx = () => ({ actor_id: 1, tenant_id: tenant, csrf_token: 'current-transport-csrf-token' })
const fetcher = vi.fn()
beforeEach(() => {
  fetcher.mockReset()
  auth.token = 'current'
  vi.stubGlobal('fetch', fetcher)
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})
it.each(['CREATE', 'UPDATE', 'ENABLE', 'PAUSE', 'ARCHIVE', 'SIMULATE'] as const)(
  '原动作%s仅GET且不带写头',
  async (action) => {
    fetcher.mockResolvedValue(new Response(JSON.stringify(ctx())))
    expect(await ruleRecoveryApi.get(action)).toEqual(ctx())
    const [raw, init] = fetcher.mock.calls[0]
    const url = new URL(raw, 'https://fixture.local')
    expect(url.pathname).toBe('/dev-api/api/v1/rules/recovery-context')
    expect(Object.fromEntries(url.searchParams)).toEqual({ action })
    expect(init).toMatchObject({ method: 'GET', cache: 'no-store' })
    expect(init.body).toBeUndefined()
    for (const h of ['If-Match', 'Idempotency-Key', 'X-CSRF-Token'])
      expect(new Headers(init.headers).has(h)).toBe(false)
  },
)
it('严格三字段与native安全整数，不接受businessUUID或额外权限字段', () => {
  expect(parseRuleRecoveryContext(ctx())).toEqual(ctx())
  for (const value of [
    { ...ctx(), actor_id: 0 },
    { ...ctx(), actor_id: true },
    { ...ctx(), actor_id: tenant },
    { ...ctx(), actor_id: Number.MAX_SAFE_INTEGER + 1 },
    { ...ctx(), tenant_id: tenant.toUpperCase().replace('4000', 'A000') },
    { ...ctx(), csrf_token: 'short' },
    { ...ctx(), extra: true },
    { actor_id: 1, tenant_id: tenant },
  ])
    expect(() => parseRuleRecoveryContext(value)).toThrow()
})
it('真实principal不可变，仅同actor与tenant通过，空旧证明禁止恢复', () => {
  const principal = recoveryPrincipal(ctx())
  expect(Object.isFrozen(principal)).toBe(true)
  expect(() =>
    requireRecoveryPrincipal(principal, { ...ctx(), csrf_token: 'new-current-csrf-token' }),
  ).not.toThrow()
  for (const value of [
    { ...ctx(), actor_id: 2 },
    { ...ctx(), tenant_id: tenant.replace(/99$/, '98') },
  ])
    expect(() => requireRecoveryPrincipal(principal, value)).toThrowError(
      expect.objectContaining({ status: 403, code: 'RULE_RECOVERY_PRINCIPAL_CHANGED' }),
    )
  expect(() => requireRecoveryPrincipal(null, ctx())).toThrow()
  expect(() => requireInitialRuleActor(1, ctx())).not.toThrow()
  for (const id of [null, 2, 0])
    expect(() => requireInitialRuleActor(id, ctx())).toThrowError(
      expect.objectContaining({ code: 'RULE_RECOVERY_UI_ACTOR_CHANGED' }),
    )
})
it.each([401, 403, 409])('损坏HTTP%d正文保留已知状态，不降为普通502', async (status) => {
  fetcher.mockResolvedValue(new Response('<html>denied</html>', { status }))
  await expect(ruleRecoveryApi.get('UPDATE')).rejects.toMatchObject({
    status,
    code: 'INVALID_RESPONSE',
  })
})
it('损坏成功响应不能伪造principal', async () => {
  fetcher.mockResolvedValue(new Response(JSON.stringify({ ...ctx(), actor_id: '1' })))
  await expect(ruleRecoveryApi.get('UPDATE')).rejects.toMatchObject({ status: 502 })
})
it('认证换代丢弃迟到身份且不补写', async () => {
  fetcher.mockImplementation(async () => {
    auth.token = 'other'
    return new Response(JSON.stringify(ctx()))
  })
  await expect(ruleRecoveryApi.get('CREATE')).rejects.toMatchObject({
    status: 409,
    code: 'SESSION_CONTEXT_CHANGED',
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('调用前取消不发请求，无效动作不探测后端', async () => {
  const controller = new AbortController()
  controller.abort()
  await expect(ruleRecoveryApi.get('CREATE', controller.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
  await expect(ruleRecoveryApi.get('OTHER' as never)).rejects.toMatchObject({ status: 422 })
  expect(fetcher).not.toHaveBeenCalled()
})
