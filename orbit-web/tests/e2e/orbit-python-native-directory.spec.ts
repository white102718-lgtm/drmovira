import { test, expect, type Page, type Locator } from '@playwright/test'
import path from 'node:path'

/** 原页面同样连接真实Python；不模拟成功、不提交角色变更或广告操作。 */
async function login(page: Page) {
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
}

/** 不先调用scrollIntoView：窗口及操作按钮必须本来就在视口内，不能用自动滚动掩盖裁切。 */
async function visiblePanel(dialog: Locator) {
  // 沿用默认5秒断言等待正常进入动画结束，持续越界仍失败；不移动窗口或放宽边界。
  await expect
    .poll(async () =>
      dialog.evaluate((node) => {
        const panel = node.matches('.el-dialog,.el-drawer')
          ? node
          : node.querySelector('.el-dialog,.el-drawer')
        const rect = panel?.getBoundingClientRect()
        const within =
          !!rect &&
          rect.width > 0 &&
          rect.height > 0 &&
          rect.left >= -1 &&
          rect.right <= innerWidth + 1 &&
          rect.top >= -1 &&
          rect.bottom <= innerHeight + 1
        return {
          within,
          rect: rect?.toJSON(),
          viewport: { width: innerWidth, height: innerHeight },
          panel: panel?.className,
        }
      }),
    )
    .toMatchObject({ within: true })
}

async function visibleFooter(dialog: Locator, action: RegExp) {
  await visiblePanel(dialog)
  await expect
    .poll(async () => {
      const box = await dialog.getByRole('button', { name: action }).boundingBox()
      return dialog.evaluate(
        (_node, rect) =>
          !!rect &&
          rect.x >= 0 &&
          rect.x + rect.width <= innerWidth + 1 &&
          rect.y >= 0 &&
          rect.y + rect.height <= innerHeight + 1,
        box,
      )
    })
    .toBe(true)
}

test('原人员列表、Unicode资料编辑与角色分配二级页', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await login(page)
  await page.goto('/system/user')
  const query = page.getByPlaceholder('请输入用户名称', { exact: true })
  await query.fill('foreign_user_directory')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(0)
  await query.fill('user_directory_1')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const row = page.locator('.el-table__body tr').filter({ hasText: /user_directory_1\b/ })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: 'user_directory_1', exact: true }).click()
  const drawer = page.getByRole('dialog', { name: '用户信息详情', exact: true })
  await expect(drawer).toContainText('user_directory_1@fixture.example.org')
  await expect(drawer).toContainText('人员目录专项权限')
  await visiblePanel(drawer)
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await row.getByRole('button', { name: '修改用户', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '修改用户', exact: true })
  await expect(editor).toBeVisible()
  await visibleFooter(editor, /^确\s*定$/)
  const nickname = editor.getByPlaceholder('请输入用户昵称', { exact: true })
  const phone = editor.getByPlaceholder('支持国际区号及分隔符', { exact: true })
  const email = editor.getByPlaceholder('请输入邮箱', { exact: true })
  const original = {
    nickname: await nickname.inputValue(),
    phone: await phone.inputValue(),
    email: await email.inputValue(),
  }
  let writes = 0
  page.on('request', (request) => {
    if (request.method() === 'PUT' && new URL(request.url()).pathname.endsWith('/system/user'))
      writes++
  })
  await nickname.fill('😀'.repeat(51))
  await editor.getByRole('button', { name: /^确\s*定$/ }).click()
  await expect(
    editor.getByText('昵称最多50个字符，不能包含控制字符', { exact: true }),
  ).toBeVisible()
  expect(writes).toBe(0)
  // 业务人员邮箱必填，空昵称合法；原技术账户仍保留原字段规则。
  await nickname.fill('')
  await email.fill('')
  await editor.getByRole('button', { name: /^确\s*定$/ }).click()
  await expect(editor.getByText('业务人员邮箱不能为空', { exact: true })).toBeVisible()
  expect(writes).toBe(0)
  await email.fill(original.email)
  const emptyNicknameSaved = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      new URL(response.url()).pathname.endsWith('/system/user'),
  )
  await editor.getByRole('button', { name: /^确\s*定$/ }).click()
  expect((await (await emptyNicknameSaved).json()).code).toBe(200)
  await expect(editor).toBeHidden()
  await row.getByRole('button', { name: '修改用户', exact: true }).click()
  await expect(nickname).toHaveValue('')
  await visibleFooter(editor, /^确\s*定$/)
  const maximumEmail =
    'p'.repeat(64) + '@' + 'q'.repeat(63) + '.' + 'r'.repeat(63) + '.' + 's'.repeat(57) + '.com'
  expect(maximumEmail.length).toBe(254)
  await nickname.fill('😀'.repeat(50))
  await phone.fill('+86 ' + '7'.repeat(28))
  await email.fill(maximumEmail)
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      new URL(response.url()).pathname.endsWith('/system/user'),
  )
  await editor.getByRole('button', { name: /^确\s*定$/ }).click()
  const saveResponse = await saved
  expect(saveResponse.status()).toBe(200)
  expect((await saveResponse.json()).code).toBe(200)
  await expect(editor).toBeHidden()
  await row.getByRole('button', { name: '修改用户', exact: true }).click()
  await expect(nickname).toHaveValue('😀'.repeat(50))
  await expect(phone).toHaveValue('+86 ' + '7'.repeat(28))
  await expect(email).toHaveValue(maximumEmail)
  await visibleFooter(editor, /^确\s*定$/)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `native-user-editor-${info.project.name}.png`),
    animations: 'disabled',
  })
  await nickname.fill(original.nickname)
  await phone.fill(original.phone)
  await email.fill(original.email)
  const restored = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      new URL(response.url()).pathname.endsWith('/system/user'),
  )
  await editor.getByRole('button', { name: /^确\s*定$/ }).click()
  const restoreResponse = await restored
  expect(restoreResponse.status()).toBe(200)
  expect((await restoreResponse.json()).code).toBe(200)
  await expect(editor).toBeHidden()
  await row.getByRole('button', { name: '分配角色', exact: true }).click()
  await expect(page.getByRole('heading', { name: '角色信息', exact: true })).toBeVisible()
  await expect(page.locator('.el-table__body')).toContainText('人员目录专项权限')
  await expect(page.locator('.el-table__body')).not.toContainText('另一租户')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `native-user-roles-${info.project.name}.png`),
    animations: 'disabled',
  })
  await page.goto('/system/user')
  await page.getByRole('button', { name: '导入', exact: true }).click()
  const importer = page.getByRole('dialog', { name: '用户导入', exact: true })
  await visibleFooter(importer, /^确\s*定$/)
  const overwrite = importer.getByRole('checkbox', { name: '是否更新已经存在的用户数据' })
  const overwriteLabel = importer
    .locator('.el-checkbox')
    .filter({ hasText: '是否更新已经存在的用户数据' })
  await expect(overwriteLabel).toBeVisible()
  await overwriteLabel.click()
  await expect(overwrite).toBeChecked()
  await importer
    .locator('input[type="file"]')
    .setInputFiles(
      path.join(process.env.ORBIT_E2E_OUTPUT!, `native-business-import-${info.project.name}.xlsx`),
    )
  const importResponse = () =>
    page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname.endsWith('/system/user/importData'),
    )
  const rejectedImport = importResponse()
  await importer.getByRole('button', { name: /^确\s*定$/ }).click()
  expect((await (await rejectedImport).json()).code).not.toBe(200)
  await expect(importer).toBeVisible()
  await expect(importer.locator('.el-upload-list__item')).toHaveCount(1)
  await expect(page.getByText(/业务人员请通过ORBIT人员页面编辑或停用/)).toBeVisible()
  // 同一文件改为跳过已存在账号后显式重试，不能被上传控件的success状态卡住。
  await overwriteLabel.click()
  await expect(overwrite).not.toBeChecked()
  const retriedImport = importResponse()
  await importer.getByRole('button', { name: /^确\s*定$/ }).click()
  const retried = await (await retriedImport).json()
  expect(retried.code).toBe(200)
  expect(retried.msg).toContain('已存在')
  const result = page.getByRole('dialog', { name: '导入结果', exact: true })
  await expect(result).toContainText('已存在')
  await result.getByRole('button', { name: /^确\s*定$/ }).click()
  await page.getByRole('button', { name: '导入', exact: true }).click()
  await importer
    .locator('input[type="file"]')
    .setInputFiles(
      path.join(process.env.ORBIT_E2E_OUTPUT!, `native-technical-import-${info.project.name}.xlsx`),
    )
  await visibleFooter(importer, /^确\s*定$/)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `native-user-import-${info.project.name}.png`),
    animations: 'disabled',
  })
  const acceptedImport = importResponse()
  await importer.getByRole('button', { name: /^确\s*定$/ }).click()
  expect((await (await acceptedImport).json()).code).toBe(200)
  await expect(result).toContainText('导入已完成')
  await result.getByRole('button', { name: /^确\s*定$/ }).click()
  const technicalName = `ui_import_${info.project.name.replaceAll('-', '_')}`
  await query.fill(technicalName)
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const technicalRow = page.locator('.el-table__body tr').filter({ hasText: technicalName })
  await expect(technicalRow).toContainText('浏览器导入专项')
  await technicalRow.getByRole('button', { name: '删除用户', exact: true }).click()
  const removed = page.waitForResponse(
    (response) =>
      response.request().method() === 'DELETE' &&
      new URL(response.url()).pathname.includes('/system/user/'),
  )
  await page
    .getByRole('dialog', { name: '系统提示', exact: true })
    .getByRole('button', { name: /^确\s*定$/ })
    .click()
  expect((await (await removed).json()).code).toBe(200)
  await expect(technicalRow).toHaveCount(0)
  expect(errors).toEqual([])
})

test('原角色编辑授权树、部门权限与成员选择弹窗', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await login(page)
  await page.goto('/system/role')
  await page.getByPlaceholder('请输入角色名称', { exact: true }).fill('人员目录专项权限')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  const row = page.locator('.el-table__body tr').filter({ hasText: '人员目录专项权限' })
  await expect(row).toHaveCount(1)
  await row.getByRole('button', { name: '修改角色', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '修改角色', exact: true })
  await expect(editor.getByPlaceholder('请输入角色名称', { exact: true })).toHaveValue(
    '人员目录专项权限',
  )
  await expect(editor.locator('.el-tree')).toBeVisible()
  await visibleFooter(editor, /^取\s*消$/)
  await editor.getByRole('button', { name: /^取\s*消$/ }).click()
  await expect(editor).toBeHidden()
  await row.getByRole('button', { name: '数据权限', exact: true }).click()
  const scope = page.getByRole('dialog', { name: '分配数据权限', exact: true })
  await expect(scope).toBeVisible()
  const scopeChoice = scope.getByRole('combobox', { name: '权限范围', exact: true })
  await scopeChoice.focus()
  await scopeChoice.press('ArrowDown')
  await page.getByRole('option', { name: '自定数据权限', exact: true }).click()
  await expect(scope.locator('.el-tree')).toBeVisible()
  await visibleFooter(scope, /^取\s*消$/)
  await scope.getByRole('button', { name: /^取\s*消$/ }).click()
  await expect(scope).toBeHidden()
  await row.getByRole('button', { name: '分配用户', exact: true }).click()
  await expect(page.getByRole('button', { name: '添加用户', exact: true })).toBeVisible()
  await page.getByPlaceholder('请输入用户名称', { exact: true }).fill('foreign_user_directory')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(0)
  await page.getByRole('button', { name: '添加用户', exact: true }).click()
  const chooser = page.getByRole('dialog', { name: '选择用户', exact: true })
  await expect(chooser).toBeVisible()
  await visibleFooter(chooser, /^取\s*消$/)
  await chooser.getByPlaceholder('请输入用户名称', { exact: true }).fill('foreign_user_directory')
  await chooser.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(chooser.locator('.el-table__body tr')).toHaveCount(0)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `native-role-members-${info.project.name}.png`),
    animations: 'disabled',
  })
  await chooser.getByRole('button', { name: /^取\s*消$/ }).click()
  await expect(chooser).toBeHidden()
  expect(errors).toEqual([])
})
