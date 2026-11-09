import { test, expect } from '@playwright/test'
import path from 'node:path'

/** 人员读取连接真实Python及数据库；覆盖独立姓名、详情、状态和游标，不冒充邀请验收。 */
test('Python人员真实列表、详情、状态筛选与分页', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.goto('/orbit/system/users?q=' + encodeURIComponent('人员目录专项'))
  await expect(page.getByRole('heading', { name: '人员管理', exact: true })).toBeVisible()
  await expect(page.locator('.el-table__body tr')).toHaveCount(28)
  await expect(page.locator('.el-table__body')).toContainText('本地账号')
  const row = page
    .locator('.el-table__body tr')
    .filter({ hasText: '人员目录专项姓名1' })
    .filter({ hasText: 'user_directory_1@' })
  await row.getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '人员详情', exact: true })
  await expect(detail).toContainText('人员目录专项姓名1')
  await expect(detail).toContainText('人员目录专项昵称1')
  await expect(detail).toContainText('+86 123456789')
  await expect(detail).toContainText('功能角色UUID')
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `users-detail-${info.project.name}.png`),
    animations: 'disabled',
  })
  await page.keyboard.press('Escape')
  await expect(detail).toBeHidden()
  // 本地账号已有身份，真实服务端必须拒绝发出首次验证邀请。
  const invitationRead = page.waitForResponse(
    (response) => response.url().endsWith('/invitation') && response.request().method() === 'GET',
  )
  await row.getByRole('button', { name: '邀请', exact: true }).click()
  const invitation = page.getByRole('dialog', { name: '人员邀请', exact: true })
  const invitationResult = await (await invitationRead).json()
  expect(invitationResult.can_invite).toBe(false)
  await expect(invitation).toContainText(invitationResult.blocked_reason)
  await expect(invitation.getByRole('button', { name: '发送邀请', exact: true })).toBeDisabled()
  await expect(invitation).toContainText('暂无通知记录')
  // 弹窗入场有transform动画；等动画稳定后验证实际边界，不在入场中途读取坐标。
  await expect
    .poll(() =>
      invitation.evaluate((element) => {
        const box = element.getBoundingClientRect()
        return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight
      }),
    )
    .toBe(true)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `users-invitation-${info.project.name}.png`),
    animations: 'disabled',
  })
  await invitation.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(invitation).toBeHidden()
  const size = page.getByRole('combobox', { name: '每页数量', exact: true })
  await size.focus()
  await size.press('ArrowDown')
  await page.getByRole('option', { name: '20条/页', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(20)
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(8)
  await page.getByRole('button', { name: '上一页', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(20)
  const status = page.getByRole('combobox', { name: '状态', exact: true })
  await status.focus()
  await status.press('ArrowDown')
  await page.getByRole('option', { name: '待邀请验证', exact: true }).click()
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(1)
  await expect(page.locator('.el-table__body')).toContainText('未验证')
  await page.getByPlaceholder('姓名、昵称、邮箱或联系方式').fill('不存在的人员')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByText('暂无符合条件的人员', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: '新增人员', exact: true }).click()
  const create = page.getByRole('dialog', { name: '新增人员', exact: true })
  await expect(create).toContainText('此操作不会发送邀请')
  const creationKeys: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/users'))
      creationKeys.push(request.headers()['idempotency-key'])
  })
  await create.getByLabel('姓名', { exact: true }).fill('😀'.repeat(51))
  await create.getByRole('button', { name: '保存人员', exact: true }).click()
  await expect(
    create.getByText('必填，最多50个字符，不能包含控制字符', { exact: true }),
  ).toBeVisible()
  expect(creationKeys).toHaveLength(0)
  const personName = `浏览器新增-${info.project.name}-${Date.now()}`
  await create.getByLabel('姓名', { exact: true }).fill(personName)
  await create.getByLabel('昵称', { exact: true }).fill('😀'.repeat(50))
  await create.getByLabel('邮箱', { exact: true }).fill(`browser-${Date.now()}@fixture.example.org`)
  await create.getByLabel('联系方式', { exact: true }).fill('+86 ' + '6'.repeat(28))
  const choose = async (label: string, name: string) => {
    const input = create.getByRole('combobox', { name: label, exact: true })
    await input.fill(name)
    await page.getByRole('option', { name, exact: true }).click()
  }
  await choose('所属团队', '人员目录专项团队0')
  await choose('功能角色', '人员目录专项权限')
  await page.keyboard.press('Escape')
  const dataRole = create.getByRole('combobox', { name: '数据角色', exact: true })
  await dataRole.focus()
  await dataRole.press('ArrowDown')
  await page.getByRole('option', { name: '团队管理员', exact: true }).click()
  await choose('管理团队', '人员目录专项团队1')
  await page.keyboard.press('Escape')
  await create.getByRole('heading', { name: '新增人员', exact: true }).click()
  await expect(page.getByRole('option', { name: '人员目录专项团队1', exact: true })).toBeHidden()
  await expect(create.getByRole('button', { name: '保存人员', exact: true })).toBeInViewport({
    ratio: 1,
  })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `users-create-${info.project.name}.png`),
    fullPage: true,
  })
  let committedId = ''
  // 真实后端已提交后丢弃首次响应，复现网络不确定；页面重试必须沿用原键和人员UUID。
  await page.route('**/api/v1/users', async (route) => {
    if (route.request().method() === 'POST' && !committedId) {
      const actual = await route.fetch()
      expect(actual.status()).toBe(201)
      committedId = (await actual.json()).id
      await route.abort('failed')
    } else await route.continue()
  })
  await create.getByRole('button', { name: '保存人员', exact: true }).click()
  await expect(
    create.getByText('网络中断，请重试；重复保存会沿用原幂等键', { exact: true }),
  ).toBeVisible()
  await create.getByRole('button', { name: '保存人员', exact: true }).click()
  await expect(create).toBeHidden()
  await expect(detail).toBeVisible()
  await expect(detail).toContainText(personName)
  await expect(detail).toContainText(committedId)
  await expect(detail).toContainText('未验证')
  expect(creationKeys).toHaveLength(2)
  expect(creationKeys[0]).toBe(creationKeys[1])
  await page.unroute('**/api/v1/users')
  await page.keyboard.press('Escape')
  // 编辑使用打开时的真实版本；另一请求先提交后必须409，并明确确认丢弃草稿再重读。
  await page.getByPlaceholder('姓名、昵称、邮箱或联系方式').fill(personName)
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.locator('.el-table__body tr')).toHaveCount(1)
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const edit = page.getByRole('dialog', { name: '编辑人员', exact: true })
  await expect(edit.locator('.reference-select').first()).toContainText('人员目录专项团队0')
  await expect(edit).toContainText('人员目录专项权限')
  const jwt = (await page.context().cookies()).find(
    (cookie) => cookie.name === 'Admin-Token',
  )!.value
  const apiHeaders = { Authorization: `Bearer ${jwt}` }
  const endpoint = `${process.env.ORBIT_E2E_BACKEND_URL}/api/v1/users`
  const priorPerson = await (
    await page.request.get(`${endpoint}/${committedId}`, { headers: apiHeaders })
  ).json()
  const caps = await (
    await page.request.get(`${endpoint}/capabilities`, { headers: apiHeaders })
  ).json()
  const { id: _id, revision: _revision, identity_status: _identity, ...personBody } = priorPerson
  const parallel = await page.request.put(`${endpoint}/${committedId}`, {
    headers: {
      ...apiHeaders,
      'X-CSRF-Token': caps.csrf_token,
      'Idempotency-Key': `browser-parallel-${Date.now()}`,
      'If-Match': `"${priorPerson.revision}"`,
    },
    data: { ...personBody, nickname: '另一请求已保存' },
  })
  expect(parallel.status()).toBe(200)
  await edit.getByLabel('昵称', { exact: true }).fill('尚未保存的页面修改')
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(edit.getByText('人员已被修改，请刷新后重试', { exact: true })).toBeVisible()
  await edit.getByRole('button', { name: '重新读取人员', exact: true }).click()
  await page.getByRole('button', { name: '确认重读', exact: true }).click()
  await expect(edit.getByLabel('昵称', { exact: true })).toHaveValue('另一请求已保存')
  await edit.getByLabel('联系方式', { exact: true }).fill('+86 ' + '4'.repeat(28))
  const accountState = edit.getByRole('combobox', { name: '账号状态', exact: true })
  await accountState.focus()
  await accountState.press('ArrowDown')
  await expect(page.getByRole('option', { name: '启用', exact: true })).toHaveCount(0)
  await page.getByRole('option', { name: '停用', exact: true }).click()
  let updates = 0
  page.on('request', (request) => {
    if (request.method() === 'PUT' && request.url().endsWith(`/api/v1/users/${committedId}`))
      updates++
  })
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  await page.getByRole('button', { name: '返回修改', exact: true }).click()
  expect(updates).toBe(0)
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  await page.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(edit).toBeHidden()
  await expect(detail).toContainText('+86 ' + '4'.repeat(28))
  await expect(detail).toContainText('停用')
  expect(updates).toBe(1)
  await page.keyboard.press('Escape')
  // 停用的新人员仍未验证；恢复待验证并不成为可登录身份。
  await status.focus()
  await status.press('ArrowDown')
  await page.getByRole('option', { name: '停用', exact: true }).click()
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  const pendingState = edit.getByRole('combobox', { name: '账号状态', exact: true })
  await pendingState.focus()
  await pendingState.press('ArrowDown')
  await page
    .getByRole('listbox', { name: '账号状态', exact: true })
    .getByRole('option', { name: '待邀请验证', exact: true })
    .click()
  await edit.getByRole('button', { name: '保存修改', exact: true }).click()
  await page.getByRole('button', { name: '确认保存', exact: true }).click()
  await expect(edit).toBeHidden()
  await expect(detail).toContainText('待邀请验证')
  await expect(detail).toContainText('未验证')
  await page.keyboard.press('Escape')
  // 原个人资料也必须接受相同字段容量，不能仅修改新人员页面而遗漏原入口。
  const profileLoaded = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' && response.url().endsWith('/system/user/profile'),
  )
  await page.goto('/user/profile')
  const initialProfile = (await (await profileLoaded).json()).data
  const nickname = page.getByLabel('用户昵称', { exact: true })
  const phone = page.getByLabel('手机号码', { exact: true })
  const email = page.getByLabel('邮箱', { exact: true })
  await expect(nickname).not.toHaveValue('')
  const prior = {
    nickname: await nickname.inputValue(),
    phone: await phone.inputValue(),
    email: await email.inputValue(),
  }
  let profileWrites = 0
  page.on('request', (request) => {
    if (request.method() === 'PUT' && request.url().endsWith('/system/user/profile'))
      profileWrites++
  })
  await nickname.fill('😀'.repeat(51))
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('昵称最多50个字符，不能包含控制字符', { exact: true })).toBeVisible()
  expect(profileWrites).toBe(0)
  const saveProfile = async () => {
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' && response.url().endsWith('/system/user/profile'),
    )
    await page.getByRole('button', { name: '保存', exact: true }).click()
    const result = await saved
    expect(result.status()).toBe(200)
    const body = await result.json()
    expect(body.code, body.msg ?? body.message ?? '个人资料保存失败').toBe(200)
    await expect(page.getByRole('button', { name: '保存', exact: true })).not.toHaveClass(
      /is-loading/,
    )
  }
  const longEmail =
    'z'.repeat(64) + '@' + 'b'.repeat(63) + '.' + 'c'.repeat(63) + '.' + 'd'.repeat(61)
  const international = '+86 ' + '8'.repeat(28)
  await nickname.fill('😀'.repeat(50))
  await phone.fill(international)
  await email.fill(longEmail)
  await saveProfile()
  await expect(page.getByText('昵称最多50个字符，不能包含控制字符', { exact: true })).toBeHidden()
  await expect(page.locator('.list-group')).toContainText(international)
  await expect(page.locator('.list-group')).toContainText(longEmail)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `native-profile-${info.project.name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
  await nickname.fill(prior.nickname)
  await phone.fill(prior.phone)
  await email.fill(prior.email)
  await saveProfile()
  const restoredProfile = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' && response.url().endsWith('/system/user/profile'),
  )
  await page.reload()
  const profile = (await (await restoredProfile).json()).data
  expect(profile.roleIds).toBe(initialProfile.roleIds)
  expect(profile.postIds).toBe(initialProfile.postIds)
  expect(profile.nickName).toBe(prior.nickname)
  expect(profile.phonenumber).toBe(prior.phone)
  expect(profile.email).toBe(prior.email)
  expect(profileWrites).toBe(2)
  expect(failures).toEqual([])
})
