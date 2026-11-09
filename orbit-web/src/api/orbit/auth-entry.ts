/** 入口凭据只保留一次内存引用；在路由和页面初始化前清理地址栏。 */
let entry: { invitation?: string; callback?: string } | null = null
export function captureAuthEntry(location: Location, history: History) {
  const pathname = location.pathname.replace(/\/+$/, '')
  if (!['/invite', '/auth/callback'].includes(pathname)) return
  if (pathname === '/invite' && !location.search && /^#[A-Za-z0-9_-]{43}$/.test(location.hash))
    entry = { invitation: location.hash.slice(1) }
  else if (pathname === '/auth/callback' && !location.hash && location.search.length <= 32768)
    entry = { callback: location.search.slice(1) }
  else entry = null
  // 旧history.state也可能含回调URL，不能随原状态把凭据保留下来。
  history.replaceState(null, '', pathname)
}
export function takeAuthEntry() {
  const value = entry
  entry = null
  return value
}

captureAuthEntry(window.location, window.history)
