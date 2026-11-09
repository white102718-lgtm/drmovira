import type { Page, TestInfo } from '@playwright/test'

/** 仅素材失败定位：路径去query与受控类型，不收集请求体/响应/凭据/原始错误消息。 */
export function materialBrowserDiagnostics(page: Page) {
  const events: { path: string; type: string; status?: number }[] = []
  const errors: string[] = []
  const pending = new Map<object, { path: string; type: string }>()
  page.on('request', (request) => {
    const url = new URL(request.url())
    pending.set(request, {
      path: ['http:', 'https:'].includes(url.protocol)
        ? url.pathname.slice(0, 256)
        : '[local-resource]',
      type: request.resourceType(),
    })
  })
  page.on('requestfinished', (request) => pending.delete(request))
  page.on('requestfailed', (request) => {
    const entry = pending.get(request)
    if (entry && events.length < 40) events.push(entry)
    pending.delete(request)
  })
  page.on('response', (response) => {
    const entry = pending.get(response.request())
    if (entry && response.status() >= 400 && events.length < 40)
      events.push({ ...entry, status: response.status() })
  })
  page.on('pageerror', (error) => {
    if (errors.length < 10)
      errors.push(
        ['Error', 'TypeError', 'SyntaxError', 'ReferenceError', 'RangeError'].includes(error.name)
          ? error.name
          : 'Error',
      )
  })
  return async (info: TestInfo) => {
    if (info.status === info.expectedStatus) return
    await info.attach('safe-material-browser-loading', {
      body: JSON.stringify({ events, pending: [...pending.values()].slice(-40), errors }),
      contentType: 'application/json',
    })
  }
}
