import type { Page, TestInfo } from '@playwright/test'

/** 只采集路径、状态与耗时；不采集请求体、查询串、Cookie、Token或配置凭据。 */
export function observePythonBrowser(page: Page, info: TestInfo) {
  const events: Record<string, unknown>[] = []
  const pending = new Map<object, { path: string; type: string; started: number }>()
  page.on('request', (request) => {
    const url = new URL(request.url())
    const path = ['http:', 'https:'].includes(url.protocol) ? url.pathname : '[local-resource]'
    pending.set(request, { path, type: request.resourceType(), started: Date.now() })
  })
  page.on('requestfailed', (request) => {
    const entry = pending.get(request)
    pending.delete(request)
    if (entry)
      events.push({ path: entry.path, type: entry.type, failure: request.failure()?.errorText })
  })
  page.on('response', async (response) => {
    const request = response.request()
    const entry = pending.get(request)
    pending.delete(request)
    if (!entry) return
    if (response.status() >= 400 || entry.path.endsWith('/system-configurations')) {
      const event: Record<string, unknown> = {
        path: entry.path,
        type: entry.type,
        method: request.method(),
        status: response.status(),
        elapsedMs: Date.now() - entry.started,
      }
      events.push(event)
      if (
        response.ok() &&
        request.method() === 'GET' &&
        entry.path.endsWith('/system-configurations')
      ) {
        try {
          const rows = await response.json()
          if (Array.isArray(rows)) {
            event.rows = rows.length
            event.hasTarget = rows.some((row) => row.name === `字段-META_BM-${info.project.name}`)
          }
        } catch {
          event.invalidJson = true
        }
      }
    }
  })
  return async () => {
    if (info.status === info.expectedStatus) return
    const safe = {
      events: events.slice(-50),
      pending: [...pending.values()].map(({ path, type, started }) => ({
        path,
        type,
        elapsedMs: Date.now() - started,
      })),
    }
    await info.attach('safe-browser-network', {
      body: JSON.stringify(safe),
      contentType: 'application/json',
    })
  }
}
