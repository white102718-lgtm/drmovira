import { test, expect } from '@playwright/test'
import path from 'node:path'
import { writeFile } from 'node:fs/promises'

/** 隔离TLS代理及浏览器进程内域名映射；应用与IdP均走真实网络，不拦截认证响应。 */
test.use({ ignoreHTTPSErrors: true })
test('Python首次邀请、真实IdP回调、Cookie刷新与退出以及再次企业登录', async ({
  page,
  context,
}, info) => {
  const fixtures = JSON.parse(process.env.ORBIT_E2E_AUTH_FIXTURES || '{}')
  const fixture = fixtures[info.project.name]
  const port = Number(process.env.ORBIT_E2E_IDP_PORT)
  if (!fixture || !Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error('缺少本轮隔离认证夹具')
  const errors: string[] = []
  const events: { path: string; status: number }[] = []
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.pathname.includes('/api/v1/auth/') || url.hostname === 'orbit-idp.fixture.example')
      events.push({ path: url.pathname, status: response.status() })
  })
  info.attach('auth-diagnostic-reference', {
    body: '仅记录路径和状态，不记录URL参数、Cookie值或凭据',
    contentType: 'text/plain',
  })
  const saveDiagnostic = async () => {
    const value = {
      events,
      path: new URL(page.url()).pathname,
      alerts: await page.locator('.el-alert__title').allTextContents(),
      cookie_names: (await context.cookies('https://app.fixture.example')).map(
        (cookie) => cookie.name,
      ),
    }
    await writeFile(
      path.join(process.env.ORBIT_E2E_OUTPUT!, `auth-diagnostic-${info.project.name}.json`),
      JSON.stringify(value),
    )
    await page.screenshot({
      path: path.join(process.env.ORBIT_E2E_OUTPUT!, `auth-last-${info.project.name}.png`),
      animations: 'disabled',
    })
  }
  page.on('pageerror', () => errors.push('pageerror'))
  await context.addCookies([
    {
      name: 'fixture_project',
      value: info.project.name,
      domain: 'orbit-idp.fixture.example',
      path: '/',
      secure: true,
    },
  ])
  await page.goto('https://app.fixture.example/invite#' + fixture.invitation)
  await expect(page.getByRole('heading', { name: '接受人员邀请', exact: true })).toBeVisible()
  expect(await page.evaluate(() => location.hash === '' && location.search === '')).toBe(true)
  await expect(page.getByRole('button', { name: '验证身份并接受邀请', exact: true })).toBeEnabled()
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `auth-invite-${info.project.name}.png`),
    animations: 'disabled',
  })
  await page.getByRole('button', { name: '验证身份并接受邀请', exact: true }).click()
  try {
    await page.waitForFunction(() => location.pathname === '/index', undefined, { timeout: 15_000 })
  } finally {
    await saveDiagnostic()
  }
  await expect(page.locator('.navbar .avatar-wrapper')).toBeVisible()
  const own = await page.evaluate(async () => {
    const response = await fetch('/dev-api/api/v1/auth/session', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    const value = await response.json()
    return { status: response.status, id: value.user?.id, identity: value.user?.identity_status }
  })
  expect(own).toEqual({ status: 200, id: fixture.user_id, identity: 'OIDC_VERIFIED' })
  const cookies = await context.cookies('https://app.fixture.example')
  const session = cookies.find((cookie) => cookie.name === 'adpilot_session')
  expect(session?.httpOnly && session.secure && session.sameSite === 'Lax').toBe(true)
  expect(cookies.some((cookie) => cookie.name === 'Admin-Token')).toBe(false)
  const stored = await page.evaluate(() =>
    [...Object.values(localStorage), ...Object.values(sessionStorage)].join(' '),
  )
  expect(stored.includes(fixture.invitation)).toBe(false)
  expect(stored.includes(session!.value)).toBe(false)
  await page.reload()
  await expect(page.locator('.navbar .avatar-wrapper')).toBeVisible()
  expect(await page.evaluate(() => location.pathname)).toBe('/index')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `auth-session-${info.project.name}.png`),
    animations: 'disabled',
  })
  const logout = async () => {
    await page.locator('.avatar-wrapper').click()
    await page.getByRole('menuitem', { name: '退出登录', exact: true }).click()
    await page.getByRole('button', { name: '确定', exact: true }).click()
    await page.waitForFunction(() => location.pathname === '/login')
    expect(
      await page.evaluate(
        async () => (await fetch('/dev-api/api/v1/auth/session', { cache: 'no-store' })).status,
      ),
    ).toBe(401)
  }
  await logout()
  await page.getByRole('link', { name: '使用企业账号登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'ORBIT 企业登录', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '使用企业账号登录', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '使用企业账号登录', exact: true }).click()
  await page.waitForFunction(() => location.pathname === '/index')
  await expect(page.locator('.navbar .avatar-wrapper')).toBeVisible()
  await logout()
  expect(errors).toEqual([])
})
