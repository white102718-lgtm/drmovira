import { it, expect } from 'vitest'
import {
  parseConnections,
  parseAuthorization,
  parseMetaCapabilities,
} from '@/api/orbit/meta-connections'
it('连接列表保留失效状态和明确未知时间', () => {
  const row = {
    id: '00000000-0000-4000-8000-000000000001',
    kind: 'LOGIN',
    status: 'REAUTH_REQUIRED',
    revision: 2,
    principal_id: null,
    expires_at: null,
    data_access_expires_at: null,
    updated_at: '2026-11-10T00:00:00Z',
  }
  expect(parseConnections({ items: [row] }).items[0]).toEqual(row)
})
it('配置未齐不制造授权', () =>
  expect(parseMetaCapabilities({ csrf_token: 'csrf', configured: false }).configured).toBe(false))
it('只接受真实Meta HTTPS授权页', () => {
  expect(() =>
    parseAuthorization({
      authorize_url: 'https://evil.test/login',
      expires_at: '2026-11-10T00:00:00Z',
    }),
  ).toThrow()
  expect(() =>
    parseAuthorization({
      authorize_url: 'javascript:alert(1)',
      expires_at: '2026-11-10T00:00:00Z',
    }),
  ).toThrow()
})
it('应用候选只接收服务端公开身份，拒绝秘密字段和重复候选', () => {
  const app = {
    id: '00000000-0000-4000-8000-000000000001',
    name: '客户应用',
    app_id: '123',
    revision: 1,
  }
  expect(
    parseMetaCapabilities({ csrf_token: 'csrf', configured: true, applications: [app] })
      .applications,
  ).toEqual([app])
  expect(() =>
    parseMetaCapabilities({
      csrf_token: 'csrf',
      configured: true,
      applications: [{ ...app, app_secret: 'leak' }],
    }),
  ).toThrow()
  expect(() =>
    parseMetaCapabilities({ csrf_token: 'csrf', configured: true, applications: [app, app] }),
  ).toThrow()
})

it('连接解析接受可空自动导入和真实进度，拒绝负计数', () => {
  const row = {
    id: '00000000-0000-4000-8000-000000000001',
    kind: 'LOGIN',
    status: 'ACTIVE',
    revision: 1,
    principal_id: null,
    expires_at: null,
    data_access_expires_at: null,
    updated_at: '2026-11-10T00:00:00Z',
    auto_import: null,
  }
  expect(parseConnections({ items: [row] }).items[0].auto_import).toBeNull()
  const progress = {
    id: row.id,
    state: 'DISCOVERING',
    error_code: null,
    total: 0,
    success_count: 0,
    failed_count: 0,
    duplicate_count: 0,
    batches: [],
  }
  expect(
    parseConnections({ items: [{ ...row, auto_import: progress }] }).items[0].auto_import?.state,
  ).toBe('DISCOVERING')
  expect(() =>
    parseConnections({ items: [{ ...row, auto_import: { ...progress, total: -1 } }] }),
  ).toThrow()
})
