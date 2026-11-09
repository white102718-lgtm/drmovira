import { test, expect } from '@playwright/test'
import path from 'node:path'
import { isMaterialRescanResponse, isMaterialSecurityResponse } from './material-security-response'

/** 主线一次装配的独占legacy PNG，真实HTTPS/数据库/ClamD/处理Worker，不mock网络。 */
test.use({ ignoreHTTPSErrors: true })

test('历史READY安全门禁、原因弹窗及真实重新检查恢复预览', async ({ page }, info) => {
  const raw = process.env.ORBIT_E2E_MATERIAL_SECURITY_FIXTURE
  if (!raw) throw new Error('请由主线隔离素材安全夹具运行')
  const manifest = JSON.parse(raw) as {
    kind: string
    assets: { project: string; id: string; name: string; width: number; height: number }[]
  }
  if (manifest.kind !== 'isolated-legacy-material-security-v1') throw new Error('夹具类型无效')
  const fixture = manifest.assets.find((item) => item.project === info.project.name)
  if (!fixture) throw new Error('当前视口缺少独立素材夹具')
  const errors: string[] = []
  const pending = new Map<object, { path: string; type: string }>()
  const network: { path: string; type: string; status?: number }[] = []
  page.on('request', (request) => {
    const url = new URL(request.url())
    pending.set(request, {
      path: ['https:', 'http:'].includes(url.protocol) ? url.pathname : '[local-resource]',
      type: request.resourceType(),
    })
  })
  page.on('requestfinished', (request) => pending.delete(request))
  page.on('requestfailed', (request) => {
    const item = pending.get(request)
    if (item && network.length < 40) network.push(item)
    pending.delete(request)
  })
  page.on('response', (response) => {
    const item = pending.get(response.request())
    if (item && response.status() >= 400 && network.length < 40)
      network.push({ ...item, status: response.status() })
  })
  page.on('pageerror', (error) => {
    if (errors.length < 10)
      errors.push(
        ['Error', 'TypeError', 'SyntaxError', 'ReferenceError', 'RangeError'].includes(error.name)
          ? error.name
          : 'Error',
      )
  })
  await page.goto('https://app.fixture.example/login')
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  // URL先变化；真实权限菜单与首页壳挂载后才启动下一次整页导航。
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await page.goto('https://app.fixture.example/orbit/assets')
  try {
    await expect(page.getByRole('heading', { name: '素材库', exact: true })).toBeVisible()
  } catch (error) {
    await info.attach('safe-material-security-loading', {
      body: JSON.stringify({ network, pending: [...pending.values()].slice(-40), errors }),
      contentType: 'application/json',
    })
    console.info('material-security-pageerror-types', JSON.stringify(errors))
    throw error
  }
  await page.getByPlaceholder('按名称搜索', { exact: true }).fill(fixture.name)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  const row = page
    .locator('.material-page > .el-table .el-table__body tr')
    .filter({ hasText: fixture.name })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('待安全复核（历史状态）')
  await expect(row.getByRole('button', { name: '编辑', exact: true })).toBeDisabled()
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '素材详情与引用关系', exact: true })
  await expect(detail).toContainText('历史READY，安全未验证')
  await expect(detail.getByAltText('服务端处理后的素材预览', { exact: true })).toHaveCount(0)
  await expect(detail.getByRole('button', { name: '重新安全检查', exact: true })).toBeEnabled()
  await detail.getByRole('button', { name: '重新安全检查', exact: true }).click()
  const prompt = page.getByRole('dialog', { name: '重新安全检查', exact: true })
  await expect(prompt).toBeVisible()
  await prompt.getByRole('textbox').fill('浏览器实际安全重扫验收')
  const queued = page.waitForResponse((response) => isMaterialRescanResponse(response, fixture.id))
  await prompt.getByRole('button', { name: '确定', exact: true }).click()
  expect((await queued).status()).toBe(202)
  await expect(prompt).toBeHidden()
  // 用真实状态刷新按钮推进等待；不延长默认测试超时、不使用响应拦截或固定sleep。
  await expect
    .poll(
      async () => {
        const refresh = detail.getByRole('button', { name: '刷新安全状态', exact: true })
        const refreshed = page.waitForResponse((response) =>
          isMaterialSecurityResponse(response, fixture.id),
        )
        await refresh.click()
        expect((await refreshed).status()).toBe(200)
        // 按真实界面加载完成同步，避免每轮点击后立即读取请求尚未完成的旧状态。
        await expect(refresh).toBeEnabled()
        await expect(detail.getByRole('status')).toHaveCount(0)
        return await detail.innerText()
      },
      { timeout: 20000 },
    )
    .toContain('安全检查通过')
  const preview = detail.getByAltText('服务端处理后的素材预览', { exact: true })
  await expect(preview).toBeVisible()
  await expect
    .poll(() =>
      preview.evaluate(
        (image, dimensions) => {
          const element = image as HTMLImageElement
          return (
            element.complete &&
            element.naturalWidth === dimensions.width &&
            element.naturalHeight === dimensions.height
          )
        },
        { width: fixture.width, height: fixture.height },
      ),
    )
    .toBe(true)
  await expect(detail).toContainText('与当前文件一致')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `materials-security-${info.project.name}.png`),
    animations: 'disabled',
  })
  await page.keyboard.press('Escape')
  await expect(detail).toBeHidden()
  await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
  await expect(row).toContainText('安全检查通过')
  await expect(row.getByRole('button', { name: '编辑', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})
