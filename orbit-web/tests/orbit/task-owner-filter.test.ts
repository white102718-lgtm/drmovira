/** 真实ElementPlus挂载，Task读取协议替身；不是后端授权或浏览器验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TaskPanel from '@/views/orbit/launch/TaskPanel.vue'
import { tasksApi, TaskApiError } from '@/api/orbit/tasks'
import { taskPage, taskUuid } from './tasks-fixtures'
let wrapper: VueWrapper | undefined
const input = () => wrapper!.get('input[aria-label="冻结任务拥有者UUID"]')
const owner = taskUuid(80000)
async function query(value: string) {
  await input().setValue(value)
  await wrapper!.find('form').trigger('submit')
  await flushPromises()
}
async function button(text: string) {
  await wrapper!
    .findAll('button')
    .find((node) => node.text() === text)!
    .trigger('click')
  await flushPromises()
}
async function start() {
  wrapper = mount(TaskPanel, {
    props: { active: true, contextKey: 'A:tasks.read' },
    global: { plugins: [ElementPlus], stubs: { TaskDetails: true } },
  })
  await flushPromises()
}
beforeEach(() => {
  vi.spyOn(tasksApi, 'list').mockResolvedValue(taskPage())
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
})
it('中文明确冻结拥有者而非执行操作人；已知UUID可直接查询且保留原status/page_size', async () => {
  await start()
  expect(wrapper!.text()).toContain('不是执行操作人')
  const select = wrapper!.findAllComponents({ name: 'ElSelect' })
  select[0].vm.$emit('update:modelValue', 'UNKNOWN')
  select[1].vm.$emit('update:modelValue', 100)
  const knownOwner = 'abcdefab-cdef-abcd-efab-cdefabcdefab'
  await query(` ${knownOwner.toUpperCase()} `)
  expect(tasksApi.list).toHaveBeenLastCalledWith(
    { page_size: 100, status: 'UNKNOWN', operator_user_id: knownOwner },
    expect.any(AbortSignal),
  )
  expect((input().element as HTMLInputElement).value).toBe(knownOwner)
  expect(wrapper!.text()).toContain(`已应用拥有者筛选：${knownOwner}`)
})
it.each([
  'not-uuid',
  owner.replaceAll('-', ''),
  `{${owner}}`,
  `${owner}x`,
  '<script>unsafe()</script>',
])('严格拒绝无效UUID %s，不发查询且旧游标失效', async (value) => {
  await start()
  vi.mocked(tasksApi.list).mockClear()
  await query(value)
  expect(tasksApi.list).not.toHaveBeenCalled()
  expect(wrapper!.text()).toContain('UUID格式无效')
  expect(
    wrapper!
      .findAll('button')
      .find((node) => node.text() === '下一页任务')!
      .attributes('disabled'),
  ).toBeDefined()
  expect(wrapper!.find('script').exists()).toBe(false)
})
it('查询从首页开始，翻页沿同拥有者，换UUID禁旧翻页并移除原cursor', async () => {
  await start()
  await query(owner)
  await button('下一页任务')
  expect(tasksApi.list).toHaveBeenLastCalledWith(
    { page_size: 20, operator_user_id: owner, cursor: 'task-list-page2' },
    expect.any(AbortSignal),
  )
  await input().setValue(taskUuid(80001))
  expect(
    wrapper!
      .findAll('button')
      .find((node) => node.text() === '上一页任务')!
      .attributes('disabled'),
  ).toBeDefined()
  await wrapper!.find('form').trigger('submit')
  await flushPromises()
  expect(tasksApi.list).toHaveBeenLastCalledWith(
    { page_size: 20, operator_user_id: taskUuid(80001) },
    expect.any(AbortSignal),
  )
  expect(
    wrapper!
      .findAll('button')
      .find((node) => node.text() === '上一页任务')!
      .attributes('disabled'),
  ).toBeDefined()
})
it('清除按钮和空白值都删除operator参数而不发null，原行筛选保持可用', async () => {
  await start()
  await button('仅查看此拥有者')
  expect((input().element as HTMLInputElement).value).toBe(owner)
  await button('清除拥有者筛选')
  expect(tasksApi.list).toHaveBeenLastCalledWith({ page_size: 20 }, expect.any(AbortSignal))
  await query(owner)
  await query('   ')
  expect(tasksApi.list).toHaveBeenLastCalledWith({ page_size: 20 }, expect.any(AbortSignal))
  expect((input().element as HTMLInputElement).value).toBe('')
})
it('无效输入后的新查询清旧错误并真实重新读取', async () => {
  await start()
  await query('bad')
  expect(wrapper!.text()).toContain('UUID格式无效')
  await query(owner)
  expect(wrapper!.text()).not.toContain('UUID格式无效')
  expect(wrapper!.findAll('.task-list .el-table__body tr')).toHaveLength(1)
})
it('context变化清拥有者和错误，旧读取晚到不能覆盖新用户或恢复旧条件', async () => {
  await start()
  let complete!: (value: ReturnType<typeof taskPage>) => void
  vi.mocked(tasksApi.list).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      }),
  )
  await query(owner)
  const previous = vi.mocked(tasksApi.list).mock.calls.at(-1)![1]!
  await wrapper!.setProps({ contextKey: 'B:tasks.read' })
  await flushPromises()
  expect(previous.aborted).toBe(true)
  expect(tasksApi.list).toHaveBeenLastCalledWith({ page_size: 20 }, expect.any(AbortSignal))
  expect((input().element as HTMLInputElement).value).toBe('')
  const stale = taskPage()
  stale.items[0].id = taskUuid(999999)
  complete(stale)
  await flushPromises()
  expect(wrapper!.text()).not.toContain(taskUuid(999999))
  expect(wrapper!.text()).not.toContain('已应用拥有者筛选')
})
it('撤权清拥有者/旧结果和历史，不以筛选赋予权限', async () => {
  await start()
  vi.mocked(tasksApi.list).mockRejectedValueOnce(
    new TaskApiError(403, 'PERMISSION_DENIED', '读取权限已变化'),
  )
  await query(owner)
  expect((input().element as HTMLInputElement).value).toBe('')
  expect(wrapper!.findAll('.task-list .el-table__body tr')).toHaveLength(0)
  expect(wrapper!.text()).toContain('读取权限已变化')
  expect(wrapper!.text()).not.toContain('已应用拥有者筛选')
})
