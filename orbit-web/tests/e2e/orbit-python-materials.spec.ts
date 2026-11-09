import { test, expect, type Page, type TestInfo } from '@playwright/test'
import path from 'node:path'
import { materialBrowserDiagnostics } from './material-browser-diagnostics'

/** 本机隔离TLS与真实Worker；不拦截上传、处理、元数据或归档响应。 */
test.use({ ignoreHTTPSErrors: true })
const diagnostics = new WeakMap<Page, (info: TestInfo) => Promise<void>>()
test.beforeEach(async ({ page }) => {
  diagnostics.set(page, materialBrowserDiagnostics(page))
})
test.afterEach(async ({ page }, info) => {
  await diagnostics.get(page)?.(info)
  diagnostics.delete(page)
})
test('Python素材真实上传、处理、详情预览、标签分类、编辑与归档', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => {
    // 只输出错误类型和固定源码文件行号，禁止记录消息、完整URL、查询或响应内容。
    const type = ['Error', 'TypeError', 'SyntaxError', 'ReferenceError', 'RangeError'].includes(
      error.name,
    )
      ? error.name
      : 'Error'
    const location = error.stack?.match(
      /(?:src\/views\/orbit\/materials\/)(index|MaterialUpload|MaterialTaxonomy)\.vue(?:\?[^\s:)]*)?:(\d+):(\d+)/,
    )
    const diagnostic = location
      ? { type, file: `${location[1]}.vue`, line: Number(location[2]), column: Number(location[3]) }
      : { type, file: 'unavailable' }
    if (errors.length < 10) {
      errors.push(type)
      console.info('material-pageerror', JSON.stringify(diagnostic))
    }
  })
  await page.goto('https://app.fixture.example/login')
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('https://app.fixture.example/orbit/assets')
  await expect(page.getByRole('heading', { name: '素材库', exact: true })).toBeVisible()
  const name = `浏览器素材-${info.project.name}-${Date.now()}`
  const categoryName = `素材分类-${info.project.name}-${Date.now().toString(36)}`
  expect([...categoryName].length).toBeLessThanOrEqual(30)
  await page.getByRole('button', { name: '标签与分类', exact: true }).click()
  const taxonomy = page.getByRole('dialog', { name: '标签与分类管理', exact: true })
  await taxonomy.getByRole('tab', { name: '分类', exact: true }).click()
  await taxonomy.getByRole('textbox').first().fill(categoryName)
  const categorySaved = page.waitForResponse(
    (r) => r.url().endsWith('/api/v1/categories') && r.request().method() === 'POST',
  )
  await taxonomy.getByRole('button', { name: '新增', exact: true }).click()
  expect((await categorySaved).status()).toBe(201)
  await expect(taxonomy.locator('.el-table__body')).toContainText(categoryName)
  await page.keyboard.press('Escape')
  await expect(taxonomy).toBeHidden()
  await page.getByRole('button', { name: '上传素材', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '上传素材', exact: true })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('combobox').first().click()
  await page.getByRole('option', { name: categoryName, exact: true }).click()
  const content = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 48
    canvas.height = 32
    const context = canvas.getContext('2d')!
    context.fillStyle = `rgb(${Math.floor(Math.random() * 255)},80,140)`
    context.fillRect(0, 0, 48, 32)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  await dialog.getByLabel('选择素材文件', { exact: true }).setInputFiles({
    name: `${name}.png`,
    mimeType: 'image/png',
    buffer: Buffer.from(content, 'base64'),
  })
  await expect(dialog.getByRole('textbox', { name: '素材名称', exact: true })).toHaveValue(name)
  await expect
    .poll(() =>
      dialog.evaluate((e) => {
        const b = e.getBoundingClientRect()
        return b.left >= 0 && b.right <= innerWidth
      }),
    )
    .toBe(true)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `materials-upload-${info.project.name}.png`),
    animations: 'disabled',
  })
  const completed = page.waitForResponse((r) =>
    /\/assets\/upload-sessions\/[^/]+\/complete$/.test(new URL(r.url()).pathname),
  )
  await dialog.getByRole('button', { name: '开始上传', exact: true }).click()
  expect((await completed).status()).toBe(202)
  await expect(dialog).toContainText('上传完成，等待处理')
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  const row = page
    .locator('.material-page > .el-table .el-table__body tr')
    .filter({ hasText: name })
  // 真Worker确定性处理后主动刷新，等待条件是业务READY而非延长固定sleep。
  await expect
    .poll(
      async () => {
        await page.getByRole('button', { name: '刷新处理状态', exact: true }).click()
        return await row.innerText().catch(() => '')
      },
      { timeout: 20000 },
    )
    .toContain('可用')
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '素材详情与引用关系', exact: true })
  await expect(detail.getByAltText('服务端处理后的素材预览', { exact: true })).toBeVisible()
  await expect
    .poll(() =>
      detail.getByAltText('服务端处理后的素材预览', { exact: true }).evaluate((image) => {
        const preview = image as HTMLImageElement
        return preview.complete && preview.naturalWidth === 48 && preview.naturalHeight === 32
      }),
    )
    .toBe(true)
  await expect(detail).toContainText('无引用关系')
  await expect(detail).toContainText(categoryName)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `materials-detail-${info.project.name}.png`),
    animations: 'disabled',
  })
  await page.keyboard.press('Escape')
  await expect(detail).toBeHidden()
  await row.getByRole('button', { name: '编辑', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '编辑素材元数据', exact: true })
  await editor
    .getByRole('textbox')
    .first()
    .fill(name + '-修改')
  const edited = page.waitForResponse(
    (r) =>
      r.request().method() === 'PUT' && /\/api\/v1\/assets\/[^/]+$/.test(new URL(r.url()).pathname),
  )
  await editor.getByRole('button', { name: '保存', exact: true }).click()
  expect((await edited).status()).toBe(200)
  await expect(editor).toBeHidden()
  await expect(row).toContainText(name + '-修改')
  // Element Plus的原始input透明隐藏；使用用户可见label，再验证真实选择状态。
  const selection = row.locator('label.el-checkbox')
  await expect(selection).toBeVisible()
  await selection.click()
  await expect(row.getByRole('checkbox')).toBeChecked()
  await page.getByRole('button', { name: '批量归档（1）', exact: true }).click()
  const confirmation = page.getByRole('dialog', { name: '批量归档', exact: true })
  await confirmation.getByRole('textbox').fill('浏览器真实归档验收')
  const archived = page.waitForResponse((r) => r.url().endsWith('/api/v1/assets/bulk-delete'))
  await confirmation.getByRole('button', { name: '确定', exact: true }).click()
  expect((await archived).status()).toBe(200)
  await expect(row).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  expect(errors).toEqual([])
})
