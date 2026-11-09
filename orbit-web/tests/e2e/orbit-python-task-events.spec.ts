import { test, expect, type Page, type Response } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFile, writeFile, rename, stat } from 'node:fs/promises'
import { isAbsolute, join, resolve } from 'node:path'
import type { Task, TaskPage } from '../../src/api/orbit/tasks'

/** 真实SSE及ISOLATED_TEST publisher协同；不模拟HTTP、不新增写端点、不发送平台广告。 */
const uuid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value)
const keys = (value: unknown, fields: string[]): value is Record<string, unknown> =>
  !!value &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  Object.keys(value).length === fields.length &&
  fields.every((field) => Object.hasOwn(value, field))
const control: unknown = JSON.parse(process.env.ORBIT_E2E_TASK_EVENT_CONTROL || 'null')
if (
  !keys(control, ['version', 'run_id', 'directory']) ||
  control.version !== 1 ||
  !uuid(control.run_id) ||
  typeof control.directory !== 'string' ||
  !isAbsolute(control.directory) ||
  !process.env.ORBIT_E2E_TASK_READER_USERNAME ||
  !process.env.ORBIT_E2E_FIXTURE_PASSWORD
)
  throw new Error('Task事件浏览器验证缺少合法受控协议及真实USER夹具')
const directory = resolve(control.directory),
  runId = control.run_id
type Action = 'PUBLISH_RUNNING' | 'REVOKE_TASK_READ' | 'RESTORE_TASK_READ'
interface Receipt {
  version: 1
  run_id: string
  request_id: string
  state: 'APPLIED' | 'FAILED'
  action: Action
  task_id: string
  node_id: string | null
  task_revision: number | null
  code: null | 'FIXTURE_CONTROL_FAILED'
}
async function apply(action: Action, taskId: string, nodeId: string | null): Promise<Receipt> {
  if (
    !uuid(taskId) ||
    !(nodeId === null || uuid(nodeId)) ||
    (action === 'PUBLISH_RUNNING') !== (nodeId !== null)
  )
    throw new Error('受控夹具动作参数无效')
  const requestId = randomUUID()
  const request = {
    version: 1,
    run_id: runId,
    request_id: requestId,
    action,
    task_id: taskId,
    node_id: nodeId,
  }
  const temporary = join(directory, `${requestId}.request.tmp`)
  await writeFile(temporary, JSON.stringify(request), { encoding: 'utf8', flag: 'wx', mode: 0o600 })
  await rename(temporary, join(directory, `${requestId}.request.json`))
  const path = join(directory, `${requestId}.response.json`)
  let result: Receipt | null = null
  await expect
    .poll(
      async () => {
        let value: unknown
        try {
          if ((await stat(path)).size > 4096) throw new Error('受控夹具回执超出大小限制')
          value = JSON.parse(await readFile(path, 'utf8'))
        } catch (cause) {
          if ((cause as NodeJS.ErrnoException).code === 'ENOENT') return false
          throw new Error('受控夹具回执读取失败')
        }
        if (
          !keys(value, [
            'version',
            'run_id',
            'request_id',
            'state',
            'action',
            'task_id',
            'node_id',
            'task_revision',
            'code',
          ]) ||
          value.version !== 1 ||
          value.run_id !== runId ||
          value.request_id !== requestId ||
          value.action !== action ||
          value.task_id !== taskId ||
          value.node_id !== nodeId ||
          !['APPLIED', 'FAILED'].includes(String(value.state)) ||
          !(
            value.task_revision === null ||
            (typeof value.task_revision === 'number' &&
              Number.isSafeInteger(value.task_revision) &&
              value.task_revision >= 1)
          ) ||
          (value.state === 'APPLIED'
            ? value.code !== null
            : value.code !== 'FIXTURE_CONTROL_FAILED')
        )
          throw new Error('受控夹具回执与当前动作不匹配')
        result = value as unknown as Receipt
        return true
      },
      { timeout: 5000, intervals: [50, 100, 200], message: '等待当前内部夹具动作真实提交回执' },
    )
    .toBe(true)
  if (result!.state !== 'APPLIED') throw new Error('FIXTURE_CONTROL_FAILED')
  return result!
}
const apiPath = (url: string) => {
  const { pathname } = new URL(url)
  return pathname.startsWith('/dev-api/') ? pathname.slice('/dev-api'.length) : pathname
}
const get = (response: Response, path: string) =>
  response.request().method() === 'GET' && apiPath(response.url()) === `/api/v1${path}`
async function json<T>(response: Response): Promise<T> {
  expect(response.status()).toBe(200)
  return response.json()
}
type Native = { permissions: string[]; isDefaultModifyPwd: boolean; isPasswordExpired: boolean }
async function security(page: Page, native: Native) {
  expect(native.permissions).toContain('tasks.read')
  expect(typeof native.isDefaultModifyPwd).toBe('boolean')
  expect(typeof native.isPasswordExpired).toBe('boolean')
  const notice = page.getByRole('dialog', { name: '安全提示', exact: true })
  if (native.isDefaultModifyPwd || native.isPasswordExpired) {
    await expect(notice).toBeVisible()
    await expect(notice.locator('.el-message-box__message')).toHaveText(
      native.isDefaultModifyPwd
        ? '您的密码还是初始密码，请修改密码！'
        : '您的密码已过期，请尽快修改密码！',
    )
    await notice.getByRole('button', { name: '取消', exact: true }).click()
    await expect(notice).toBeHidden()
  } else await expect(notice).toBeHidden()
}
async function open(page: Page) {
  const captcha = page.waitForResponse((response) => response.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page
    .getByPlaceholder('账号', { exact: true })
    .fill(process.env.ORBIT_E2E_TASK_READER_USERNAME!)
  await page.getByPlaceholder('密码', { exact: true }).fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  const user = page.waitForResponse((response) => apiPath(response.url()) === '/getInfo')
  await page.getByRole('button', { name: '登 录', exact: true }).click()
  const native = await json<Native>(await user)
  await expect(page).toHaveURL(/\/index$/)
  await expect(page.locator('.app-wrapper')).toBeVisible()
  await expect(page.locator('.sidebar-container .el-menu[role="menubar"]')).toBeAttached()
  await security(page, native)
  const reloaded = page.waitForResponse((response) => apiPath(response.url()) === '/getInfo')
  const list = page.waitForResponse((response) => get(response, '/tasks'))
  await page.goto('/orbit/launch')
  await security(page, await json<Native>(await reloaded))
  let listing = await json<TaskPage>(await list)
  const panel = page.locator('section.task-panel')
  await expect(page.getByRole('tab', { name: '任务', exact: true })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  let selected: Task | undefined
  for (let index = 0; index < 4; index++) {
    selected = listing.items.find((entry) => entry.node_count === 1206)
    if (selected) break
    expect(listing.next_cursor).not.toBeNull()
    const next = page.waitForResponse((response) => get(response, '/tasks'))
    await panel.getByRole('button', { name: '下一页任务', exact: true }).click()
    listing = await json<TaskPage>(await next)
  }
  expect(selected, '须使用USER真实拥有的完整1206节点Task').toBeDefined()
  const id = selected!.id
  const detailRead = page.waitForResponse((response) => get(response, `/tasks/${id}`))
  const stream = page.waitForResponse((response) => get(response, `/tasks/${id}/events`))
  await panel
    .locator('.el-table__body tr')
    .filter({ hasText: id })
    .getByRole('button', { name: '任务详情', exact: true })
    .click()
  const detailResponse = await detailRead
  expect(Boolean(detailResponse.headers()['x-task-event-checkpoint'])).toBe(true)
  const task = await json<Task>(detailResponse)
  expect(task.node_count).toBe(1206)
  expect(task.nodes).toHaveLength(200)
  const connected = await stream
  expect(connected.status()).toBe(200)
  expect(connected.headers()['content-type']).toContain('text/event-stream')
  const detail = page.getByRole('dialog', { name: '任务详情', exact: true })
  await expect(detail.getByRole('status', { name: '任务观察状态' })).toHaveText('任务更新已连接')
  await expect(detail.locator('.task-node-table .el-table__body tr')).toHaveCount(200)
  return { task, detail, panel }
}
async function noFurtherReads(page: Page, id: string) {
  const found = await page
    .waitForRequest(
      (request) =>
        request.method() === 'GET' &&
        [`/api/v1/tasks/${id}`, `/api/v1/tasks/${id}/nodes`, `/api/v1/tasks/${id}/events`].includes(
          apiPath(request.url()),
        ),
      { timeout: 11000 },
    )
    .then(
      () => true,
      (cause: Error) => {
        if (cause.name !== 'TimeoutError') throw cause
        return false
      },
    )
  expect(found).toBe(false)
}

test('Python真实SSE内部提交后读取新版本节点并关闭停流', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', () => failures.push('PAGE_ERROR'))
  const { task, detail } = await test.step(
    '真实USER登录并打开非空Task快照与事件流',
    () => open(page),
    { timeout: 20000 },
  )
  const node = task.nodes.find((entry) => entry.state === 'QUEUED')
  expect(node, '逐视口选用当前未发送节点，不能复用已RUNNING节点').toBeDefined()
  await test.step(
    '主线真实事务提交与页面实际SSE刷新结果逐项对账',
    async () => {
      const refreshed = page.waitForResponse(
        async (response) =>
          get(response, `/tasks/${task.id}`) &&
          response.status() === 200 &&
          (await response.json()).revision > task.revision,
      )
      const receipt = await apply('PUBLISH_RUNNING', task.id, node!.id)
      expect(receipt.task_revision).toBeGreaterThan(task.revision)
      const current = await json<Task>(await refreshed)
      expect(current.revision).toBe(receipt.task_revision)
      expect(current.state).toBe('RUNNING')
      expect(current.nodes.find((entry) => entry.id === node!.id)?.state).toBe('RUNNING')
      await expect(detail).toContainText(`${current.revision} / 1206`)
      const row = detail
        .locator('.task-node-table .el-table__body tr')
        .filter({ has: page.getByText(node!.node_key, { exact: true }) })
      await expect(row).toContainText('处理中')
      await expect(detail.getByRole('status', { name: '任务观察状态' })).toHaveText(
        '任务更新已连接',
      )
      // 用本次真实提交回执关联SSE事件，不能把Task刷新或fixture文件当日志显示成功。
      const log = detail.getByRole('region', { name: '本次订阅观察记录', exact: true })
      await expect(log).toContainText('最近200条记录，不是完整历史或平台执行成功证明。')
      const observed = log.locator('details').filter({ hasText: receipt.request_id })
      await expect(observed).toHaveCount(1)
      await observed.locator('summary').click()
      await expect(observed).toHaveAttribute('open', '')
      await expect(observed.locator('dt')).toHaveText([
        '事件 ID（event_id）',
        '事件序号（sequence）',
        '结构版本（schema_version）',
        '任务 ID（task_id）',
        '任务版本（task_revision）',
        '节点 ID（node_id）',
        '观察状态（state）',
        '发生时间（occurred_at）',
        '请求编号（request_id）',
      ])
      const values = observed.locator('dd')
      await expect(values).toHaveCount(9)
      expect(uuid(await values.nth(0).innerText())).toBe(true)
      const sequence = await values.nth(1).innerText()
      expect(sequence).toMatch(/^[1-9][0-9]*$/)
      expect(Number.isSafeInteger(Number(sequence))).toBe(true)
      await expect(values.nth(2)).toHaveText('1')
      await expect(values.nth(3)).toHaveText(task.id)
      await expect(values.nth(4)).toHaveText(String(receipt.task_revision))
      await expect(values.nth(5)).toHaveText(node!.id)
      await expect(values.nth(6)).toHaveText('RUNNING')
      const occurredAt = await values.nth(7).innerText()
      expect(occurredAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/)
      expect(Number.isFinite(Date.parse(occurredAt))).toBe(true)
      await expect(values.nth(8)).toHaveText(receipt.request_id)
      for (const name of ['执行任务', '安全重试', '取消任务', '开始投放'])
        await expect(detail.getByRole('button', { name, exact: true })).toHaveCount(0)
      await expect
        .poll(async () => {
          const box = await detail.boundingBox()
          return Boolean(box && box.x >= -1 && box.x + box.width <= page.viewportSize()!.width + 1)
        })
        .toBe(true)
      await page.screenshot({
        path: info.outputPath(`task-event-observed-${info.project.name}.png`),
        fullPage: true,
      })
    },
    { timeout: 15000 },
  )
  await detail.locator('button.el-drawer__close-btn').click()
  await expect(detail).toBeHidden()
  await noFurtherReads(page, task.id)
  expect(failures).toEqual([])
})

test('Python真实SSE读取动作撤权清空与停止并恢复夹具权限', async ({ page }, info) => {
  const failures: string[] = []
  page.on('pageerror', () => failures.push('PAGE_ERROR'))
  let taskId: string | null = null,
    revokeIntent = false,
    primaryFailure = false
  try {
    const { task, detail, panel } = await test.step(
      '真实USER独立会话读取Task并建立observer',
      () => open(page),
      { timeout: 20000 },
    )
    taskId = task.id
    await test.step(
      '真实撤权控制帧清空页面，原TaskGET仍然403',
      async () => {
        revokeIntent = true
        await apply('REVOKE_TASK_READ', task.id, null)
        await expect(detail).toBeHidden()
        await expect(panel).toContainText('当前任务读取权限已撤销，旧数据已清除。')
        await expect(panel).not.toContainText(task.id)
        await expect(panel.locator('.task-list .el-table__body tr')).toHaveCount(0)
        const status = await page.evaluate(async (id) => {
          const path = '/src/api/orbit/tasks.ts'
          const { tasksApi } = await import(/* @vite-ignore */ path)
          try {
            await tasksApi.get(id)
            return 200
          } catch (cause) {
            return (cause as { status?: number }).status ?? 0
          }
        }, task.id)
        expect(status).toBe(403)
        await page.screenshot({
          path: info.outputPath(`task-event-revoked-${info.project.name}.png`),
          fullPage: true,
        })
      },
      { timeout: 15000 },
    )
    await noFurtherReads(page, task.id)
    expect(failures).toEqual([])
  } catch (cause) {
    primaryFailure = true
    throw cause
  } finally {
    if (taskId && revokeIntent) {
      try {
        await apply('RESTORE_TASK_READ', taskId, null)
      } catch {
        // 原失败保留原栈；恢复失败单独登记且由主线最终数据库核验明确拒收。
        info.annotations.push({ type: 'fixture-restore', description: 'FAILED' })
        if (!primaryFailure) throw new Error('RESTORE_TASK_READ failed')
      }
    }
  }
})
