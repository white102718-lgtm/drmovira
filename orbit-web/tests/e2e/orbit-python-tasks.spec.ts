import { test, expect, type Locator, type Response } from '@playwright/test'
import type { Task, TaskNode, TaskPage } from '../../src/api/orbit/tasks'

/** 原Task只读真实HTTP：必须先运行T1非空夹具；无路由模拟、无SQL修改、无执行动作。 */
if (process.env.ORBIT_E2E_TASK_CORE !== '1') {
  throw new Error('任务浏览器验证必须使用T1非空真实夹具')
}
if (!process.env.ORBIT_E2E_TASK_READER_USERNAME) {
  throw new Error('任务浏览器验证缺少真实Task-only USER夹具')
}

/** 与账户命令专项保持一致：仅剥离已知Vite代理前缀一次，剩余完整路径必须精确匹配。 */
const apiPath = (value: string) => {
  const { pathname } = new URL(value)
  return pathname.startsWith('/dev-api/') ? pathname.slice('/dev-api'.length) : pathname
}

const isGet = (response: Response, path: string) =>
  response.request().method() === 'GET' && apiPath(response.url()) === `/api/v1${path}`
async function body<T>(response: Response): Promise<T> {
  expect(response.status()).toBe(200)
  return response.json() as Promise<T>
}

test('Python任务真实列表详情分页父依赖与关闭停止轮询', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', () => failures.push('PAGE_ERROR'))
  const listRead = () => page.waitForResponse((response) => isGet(response, '/tasks'))
  async function choose(input: Locator, option: string) {
    await input.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")][1]').click()
    await page.getByRole('option', { name: option, exact: true }).click()
  }
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号', { exact: true }).fill('admin')
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await page.goto('/orbit/launch')
  await expect(page.getByRole('tab', { name: '计划与草稿', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const firstRead = listRead()
  await page.getByRole('tab', { name: '任务', exact: true }).click()
  // 限定可见主内容容器，避免移动侧栏同文案。
  const taskPanel = page.locator('section.task-panel')
  let listing = await body<TaskPage>(await firstRead)
  let selected: Task | undefined
  for (let index = 0; index < 4; index++) {
    expect(listing.items.length).toBeGreaterThan(0)
    expect(listing.items.every((task) => task.nodes.length === 0 && task.node_count > 0)).toBe(true)
    selected = listing.items.find((task) => task.node_count === 1206)
    if (selected) break
    expect(listing.next_cursor).not.toBeNull()
    const nextRead = listRead()
    await taskPanel.getByRole('button', { name: '下一页任务', exact: true }).click()
    listing = await body<TaskPage>(await nextRead)
  }
  expect(selected, '真实T1的1206节点任务应可通过正常列表分页找到').toBeDefined()
  const task = selected!
  expect(task.state).toBe('QUEUED')
  const row = taskPanel.locator('.el-table__body tr').filter({ hasText: task.id })
  await expect(row).toContainText('1206')
  const detailRead = () => page.waitForResponse((response) => isGet(response, `/tasks/${task.id}`))
  const openRead = detailRead()
  await row.getByRole('button', { name: '任务详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '任务详情', exact: true })
  const actual = await body<Task>(await openRead)
  expect(actual.id).toBe(task.id)
  expect(actual.state).toBe('QUEUED')
  expect(actual.nodes).toHaveLength(200)
  expect(actual.node_count).toBe(1206)
  await expect(detail.locator('.task-node-table .el-table__body tr')).toHaveCount(200)
  for (const value of [
    actual.id,
    actual.ownership.owner_user_id,
    actual.ownership.owner_team_id,
    actual.created_at,
  ])
    await expect(detail).toContainText(value)
  await expect(detail).toContainText('排队中')
  await expect(detail).toContainText(`${actual.revision} / 1206`)
  await expect(detail).toContainText(actual.latest_event_id ?? '暂无事件')

  function nodesRead(size: number, cursor: boolean, prefix?: string) {
    return page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        isGet(response, `/tasks/${task.id}/nodes`) &&
        url.searchParams.get('page_size') === String(size) &&
        url.searchParams.has('cursor') === cursor &&
        (prefix === undefined || url.searchParams.get('q') === prefix)
      )
    })
  }
  const nextRead = nodesRead(50, true)
  await detail.getByRole('button', { name: '下一段节点', exact: true }).click()
  let nodes = await body<TaskPage<TaskNode>>(await nextRead)
  expect(nodes.items).toHaveLength(50)
  expect(nodes.items[0].id).not.toBe(actual.nodes[0].id)
  await expect(detail.locator('.task-node-table .el-table__body tr')).toHaveCount(50)
  for (const size of [20, 100, 200]) {
    const resized = nodesRead(size, false)
    await choose(detail.getByLabel('节点分页大小', { exact: true }), `${size}个`)
    nodes = await body<TaskPage<TaskNode>>(await resized)
    expect(nodes.items).toHaveLength(size)
    expect(nodes.items[0].id).toBe(actual.nodes[0].id)
    await expect(detail.locator('.task-node-table .el-table__body tr')).toHaveCount(size)
  }

  const node = nodes.items.find((entry) => entry.parent_ids.length > 0)!
  expect(node).toBeDefined()
  await detail
    .locator('.task-node-table .el-table__body tr')
    .filter({ has: page.getByText(node.node_key, { exact: true }) })
    .getByRole('button', { name: '节点详情', exact: true })
    .click()
  const nodeDetail = page.getByRole('dialog', { name: '任务节点详情', exact: true })
  await expect(nodeDetail).toBeVisible()
  for (const value of [node.id, node.node_key, node.updated_at])
    await expect(nodeDetail).toContainText(value)
  for (const label of [
    '节点 ID',
    '节点键',
    '节点类型',
    '处理状态',
    '配置核验',
    '投放状态',
    '平台对象 ID',
    '尝试次数',
    '可安全重试标记',
    '错误码',
    '错误说明',
    '执行通道',
    '无须重复操作',
    '更新时间（UTC）',
  ])
    await expect(
      nodeDetail.locator('.el-descriptions__label').filter({ hasText: label }).first(),
    ).toBeVisible()
  await expect(nodeDetail).toContainText('排队中')
  await expect(nodeDetail).toContainText('未核验')
  await expect(nodeDetail).toContainText('未知')
  await expect(nodeDetail).toContainText(node.external_id ?? '暂无平台对象 ID')
  await expect(nodeDetail).toContainText(node.error_code ?? '无')
  await expect(nodeDetail).toContainText(node.error_message ?? '无')
  async function field(label: string, value: string) {
    const cell = nodeDetail
      .locator('.el-descriptions__label')
      .filter({ hasText: new RegExp(`^${label}$`) })
    await expect(cell.locator('xpath=following-sibling::td[1]')).toHaveText(value)
  }
  const kinds = {
    UPLOAD: '素材上传',
    CAMPAIGN: '系列',
    ADSET: '广告组',
    CREATIVE: '创意',
    AD: '广告',
    VERIFY: '回读核验',
    ENABLE: '启用',
    ALLOCATION: '素材分配',
  }
  await field('节点类型', kinds[node.kind])
  await field('尝试次数', String(node.attempt))
  await field('可安全重试标记', node.retryable ? '是（只读标记）' : '否')
  await field(
    '执行通道',
    node.execution_mode ? (node.execution_mode === 'META_API' ? 'Meta API' : 'AdsPower') : '未提供',
  )
  await field('无须重复操作', node.no_op === undefined ? '未提供' : node.no_op ? '是' : '否')
  await expect(nodeDetail.locator('.parent-list li')).toHaveCount(node.parent_ids.length)
  for (const id of node.parent_ids)
    await expect(nodeDetail.locator('.parent-list')).toContainText(id)
  await nodeDetail.locator('button.el-drawer__close-btn').click()
  await expect(nodeDetail).toBeHidden()

  // 真正的空前缀查询以及本地非法输入恢复，不模拟503或修改Task状态来造错误。
  const prefix = detail.getByLabel('节点键前缀', { exact: true })
  await prefix.fill('🙂'.repeat(101))
  await detail.getByRole('button', { name: '查询节点', exact: true }).click()
  await expect(detail).toContainText('节点键前缀最多100个码点')
  const noMatch = 'NO_SUCH_REAL_TASK_NODE_'
  await prefix.fill(noMatch)
  const emptyRead = nodesRead(200, false, noMatch)
  await detail.getByRole('button', { name: '查询节点', exact: true }).click()
  const empty = await body<TaskPage<TaskNode>>(await emptyRead)
  expect(empty.items).toEqual([])
  await expect(detail).toContainText('没有符合条件的节点')
  await prefix.fill('')
  const restoreRead = nodesRead(200, false)
  await detail.getByRole('button', { name: '查询节点', exact: true }).click()
  await body<TaskPage<TaskNode>>(await restoreRead)
  await expect(detail.locator('.task-node-table .el-table__body tr')).toHaveCount(200)
  const refreshRead = detailRead()
  await detail.getByRole('button', { name: '重新读取任务', exact: true }).click()
  expect((await body<Task>(await refreshRead)).revision).toBe(actual.revision)
  await expect(detail.locator('.task-detail')).toHaveAttribute('aria-busy', 'false')
  await expect
    .poll(async () => {
      const box = await detail.boundingBox()
      return Boolean(box && box.x >= -1 && box.x + box.width <= page.viewportSize()!.width + 1)
    })
    .toBe(true)
  for (const name of ['执行任务', '安全重试', '取消任务', '开始投放'])
    await expect(detail.getByRole('button', { name, exact: true })).toHaveCount(0)
  await page.screenshot({
    path: info.outputPath(`task-readonly-${info.project.name}.png`),
    fullPage: true,
  })
  await detail.locator('button.el-drawer__close-btn').click()
  await expect(detail).toBeHidden()
  // 观察完整轮询周期内没有发起任务详情/节点请求；不延时掩盖页面断言。
  const unexpected = await page
    .waitForRequest(
      (request) => {
        const path = apiPath(request.url())
        return (
          request.method() === 'GET' &&
          (path === `/api/v1/tasks/${task.id}` || path === `/api/v1/tasks/${task.id}/nodes`)
        )
      },
      { timeout: 11000 },
    )
    .then(
      () => true,
      (error: Error) => {
        if (error.name !== 'TimeoutError') throw error
        return false
      },
    )
  expect(unexpected).toBe(false)
  // 原GET按冻结任务拥有者过滤；不是执行操作人，也不依赖系统用户目录。
  const ownerId = task.ownership.owner_user_id
  await taskPanel.getByLabel('冻结任务拥有者UUID', { exact: true }).fill(ownerId.toUpperCase())
  const ownedRead = page.waitForResponse((response) => {
    const query = new URL(response.url()).searchParams
    return (
      isGet(response, '/tasks') && query.get('operator_user_id') === ownerId && !query.has('cursor')
    )
  })
  await taskPanel.getByRole('button', { name: '查询任务', exact: true }).click()
  const owned = await body<TaskPage>(await ownedRead)
  expect(owned.items.length).toBeGreaterThan(0)
  expect(owned.items.every((entry) => entry.ownership.owner_user_id === ownerId)).toBe(true)
  await expect(taskPanel.getByLabel('冻结任务拥有者UUID', { exact: true })).toHaveValue(ownerId)
  await expect(taskPanel).toContainText(`已应用拥有者筛选：${ownerId}`)
  const clearedRead = page.waitForResponse((response) => {
    const query = new URL(response.url()).searchParams
    return isGet(response, '/tasks') && !query.has('operator_user_id') && !query.has('cursor')
  })
  await taskPanel.getByRole('button', { name: '清除拥有者筛选', exact: true }).click()
  const cleared = await body<TaskPage>(await clearedRead)
  expect(cleared.items.length).toBeGreaterThan(0)
  await expect(taskPanel.getByLabel('冻结任务拥有者UUID', { exact: true })).toHaveValue('')
  await expect(taskPanel).not.toContainText('已应用拥有者筛选')
  expect(failures).toEqual([])
})

/** 每个test由Playwright提供全新context；失败上下文直接指向Task-only页面，不借root会话。 */
test('Python真实Task-only父菜单别名安全降级与原菜单导航', async ({ page: reader }, info) => {
  const failures: string[] = []
  reader.on('pageerror', () => failures.push('READER_PAGE_ERROR'))
  type NativeTaskReader = {
    permissions: string[]
    isDefaultModifyPwd: boolean
    isPasswordExpired: boolean
  }
  async function dismissPasswordNotice(native: NativeTaskReader) {
    expect(native.permissions).toContain('launch.read')
    expect(native.permissions).toContain('tasks.read')
    expect(typeof native.isDefaultModifyPwd).toBe('boolean')
    expect(typeof native.isPasswordExpired).toBe('boolean')
    // 尊重若依原密码安全提示，按真实getInfo分支确认后取消导航，不更改安全配置或密码状态。
    const security = reader.getByRole('dialog', { name: '安全提示', exact: true })
    if (native.isDefaultModifyPwd || native.isPasswordExpired) {
      await expect(security).toBeVisible()
      await expect(security.locator('.el-message-box__message')).toHaveText(
        native.isDefaultModifyPwd
          ? '您的密码还是初始密码，请修改密码！'
          : '您的密码已过期，请尽快修改密码！',
      )
      await security.getByRole('button', { name: '取消', exact: true }).click()
      await expect(security).toBeHidden()
    } else await expect(security).toBeHidden()
  }
  let ownTasks!: TaskPage
  await test.step(
    '真实USER登录并核对父菜单与Task动作权限',
    async () => {
      const captcha = reader.waitForResponse((response) => response.url().endsWith('/captchaImage'))
      await reader.goto('/login')
      await captcha
      await reader
        .getByPlaceholder('账号', { exact: true })
        .fill(process.env.ORBIT_E2E_TASK_READER_USERNAME!)
      await reader
        .getByPlaceholder('密码', { exact: true })
        .fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
      const currentUser = reader.waitForResponse(
        (response) => apiPath(response.url()) === '/getInfo',
      )
      await reader.getByRole('button', { name: '登 录', exact: true }).click()
      const native = await body<NativeTaskReader>(await currentUser)
      await expect(reader).toHaveURL(/\/index$/)
      await expect(reader.locator('.app-wrapper')).toBeVisible()
      await dismissPasswordNotice(native)
      await expect(reader.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
    },
    { timeout: 15000 },
  )
  await test.step(
    '计划动作真实403后自动降级并读取非空Task',
    async () => {
      const rejectedPlan = reader.waitForResponse((response) =>
        isGet(response, '/launch-plans/capabilities'),
      )
      const readerTasks = reader.waitForResponse((response) => isGet(response, '/tasks'))
      // 整页重载会再次运行若依getInfo安全提示，必须基于本次响应处理，不能沿用登录时的标记。
      const reloadedUser = reader.waitForResponse(
        (response) => apiPath(response.url()) === '/getInfo',
      )
      await reader.goto('/orbit/launch')
      await dismissPasswordNotice(await body<NativeTaskReader>(await reloadedUser))
      expect((await rejectedPlan).status()).toBe(403)
      ownTasks = await body<TaskPage>(await readerTasks)
      expect(ownTasks.items.length).toBeGreaterThan(0)
      expect(ownTasks.items.every((entry) => entry.nodes.length === 0)).toBe(true)
      await expect(reader.getByRole('tab', { name: '任务', exact: true })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    },
    { timeout: 15000 },
  )
  await test.step(
    '原首页面包屑与移动侧栏展开后真实菜单导航',
    async () => {
      await reader
        .getByRole('navigation', { name: '面包屑' })
        .getByRole('link', { name: '首页', exact: true })
        .click({ timeout: 5000 })
      await expect(reader).toHaveURL(/\/index$/)
      const shell = reader.locator('.app-wrapper')
      if ((await shell.getAttribute('class'))?.includes('hideSidebar')) {
        await reader.locator('#hamburger-container').click({ timeout: 5000 })
        await expect(shell).toHaveClass(/openSidebar/)
      }
      const sidebar = reader.locator('.sidebar-container')
      const orbitTitle = sidebar.locator('.el-sub-menu__title').filter({ hasText: 'ORBIT工作台' })
      await expect(orbitTitle).toBeVisible()
      const orbitMenu = orbitTitle.locator('..')
      if ((await orbitMenu.getAttribute('aria-expanded')) !== 'true')
        await orbitTitle.click({ timeout: 5000 })
      await expect(orbitMenu).toHaveAttribute('aria-expanded', 'true')
      const launchLink = sidebar.locator('a[href="/orbit/launch"]')
      await expect(launchLink).toBeAttached()
      await expect(launchLink).toBeVisible()
      await expect(launchLink).toContainText('投放管理')
      await launchLink.click({ timeout: 5000 })
      await expect(reader).toHaveURL(/\/orbit\/launch$/)
    },
    { timeout: 15000 },
  )
  await test.step(
    'Task仍可读而计划动作仍403，不能借父菜单获得读取权限',
    async () => {
      await expect(reader.getByRole('tab', { name: '任务', exact: true })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      await expect(reader.getByRole('tab', { name: '计划与草稿', exact: true })).toHaveClass(
        /is-disabled/,
      )
      await expect(
        reader.getByText('当前账号可读取任务，计划读取权限尚未授予，已切换任务查询。', {
          exact: true,
        }),
      ).toBeVisible()
      await expect(reader.locator('section.task-panel .el-table__body tr')).toHaveCount(
        ownTasks.items.length,
      )
      // 当前页面真实SDK只向Node返回状态；凭据留在浏览器内存，不进入日志或产物。
      const forbidden = await reader.evaluate(async () => {
        const path = '/src/api/orbit/launch.ts'
        const { launchApi } = await import(/* @vite-ignore */ path)
        try {
          await launchApi.list(new URLSearchParams({ page_size: '20' }))
          return 200
        } catch (error) {
          return (error as { status?: number }).status ?? 0
        }
      })
      expect(forbidden).toBe(403)
      await expect(reader.getByRole('tab', { name: '任务', exact: true })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      expect(failures).toEqual([])
    },
    { timeout: 15000 },
  )
  await reader.screenshot({
    path: info.outputPath(`task-only-reader-${info.project.name}.png`),
    fullPage: true,
    timeout: 5000,
  })
})
