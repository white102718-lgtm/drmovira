/** 固定隔离HTTPS网关只支持裸API或若依dev-api前缀，精确匹配方法、拥有域与素材。 */
export function isMaterialRescanResponse(
  response: { url(): string; request(): { method(): string } },
  assetId: string,
): boolean {
  return exactResponse(response, `/api/v1/assets/${assetId}/rescan`, 'POST')
}

/** 刷新必须等同一素材的真实安全详情响应，不能以任意列表/其他素材响应代替。 */
export function isMaterialSecurityResponse(
  response: { url(): string; request(): { method(): string } },
  assetId: string,
): boolean {
  return exactResponse(response, `/api/v1/assets/${assetId}/security`, 'GET')
}

function exactResponse(
  response: { url(): string; request(): { method(): string } },
  path: string,
  method: string,
): boolean {
  let url: URL
  try {
    url = new URL(response.url())
  } catch {
    return false
  }
  return (
    response.request().method() === method &&
    url.origin === 'https://app.fixture.example' &&
    (url.pathname === path || url.pathname === `/dev-api${path}`)
  )
}
