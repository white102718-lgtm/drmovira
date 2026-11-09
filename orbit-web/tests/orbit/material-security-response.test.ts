import { describe, expect, it } from 'vitest'
import {
  isMaterialRescanResponse,
  isMaterialSecurityResponse,
} from '../e2e/material-security-response'

const id = '00000000-0000-4000-8000-000000000001'
const path = `/api/v1/assets/${id}/rescan`
const response = (url: string, method = 'POST') => ({
  url: () => url,
  request: () => ({ method: () => method }),
})

describe('素材安全刷新响应精确边界', () => {
  const securityPath = `/api/v1/assets/${id}/security`
  it.each([securityPath, `/dev-api${securityPath}`])('捕获目标GET%s', (pathname) => {
    expect(
      isMaterialSecurityResponse(response(`https://app.fixture.example${pathname}`, 'GET'), id),
    ).toBe(true)
  })
  it.each([
    [`https://app.fixture.example${securityPath}`, 'POST'],
    [`http://app.fixture.example${securityPath}`, 'GET'],
    [`https://untrusted.example${securityPath}`, 'GET'],
    [`https://app.fixture.example/other${securityPath}`, 'GET'],
    [`https://app.fixture.example${securityPath}/extra`, 'GET'],
    ['https://app.fixture.example/api/v1/assets/another-id/security', 'GET'],
    ['invalid-url', 'GET'],
  ])('拒绝非目标刷新%s %s', (url, method) => {
    expect(isMaterialSecurityResponse(response(url, method), id)).toBe(false)
  })
})

describe('素材重扫浏览器响应精确边界', () => {
  it.each([path, `/dev-api${path}`])('捕获可信网关的实际路径%s', (pathname) => {
    expect(isMaterialRescanResponse(response(`https://app.fixture.example${pathname}`), id)).toBe(
      true,
    )
  })
  it.each([
    [`https://app.fixture.example${path}`, 'GET'],
    [`http://app.fixture.example${path}`, 'POST'],
    [`https://untrusted.example${path}`, 'POST'],
    [`https://app.fixture.example/unexpected${path}`, 'POST'],
    [`https://app.fixture.example${path}/extra`, 'POST'],
    ['https://app.fixture.example/api/v1/assets/another-id/rescan', 'POST'],
    ['invalid-url', 'POST'],
  ])('拒绝非目标响应%s %s', (url, method) => {
    expect(isMaterialRescanResponse(response(url, method), id)).toBe(false)
  })
})
