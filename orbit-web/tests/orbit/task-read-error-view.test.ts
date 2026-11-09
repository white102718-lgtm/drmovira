/** 真实ElementPlus组件挂载；协议替身仅验证UI隔离，不作真实业务验收。 */
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import TaskReadError from '@/views/orbit/launch/TaskReadError.vue'
import TaskPanel from '@/views/orbit/launch/TaskPanel.vue'
import { TaskApiError, tasksApi, type TaskErrorBody } from '@/api/orbit/tasks'
import { taskPage, taskUuid } from './tasks-fixtures'
const details: TaskErrorBody = {
  code: 'FIELD_INVALID',
  message: '读取条件错误',
  field_errors: [
    {
      path: '/<img src=x onerror=alert(1)>',
      code: 'INVALID',
      message: '<script>private()</script>',
      constraint: '',
    },
  ],
  retryable: true,
  request_id: taskUuid(9999),
}
afterEach(() => {
  vi.restoreAllMocks()
})
it('中文只读展示完整五字段和原路径，恶意文本不变成HTML，不提供广告操作', () => {
  const wrapper = mount(TaskReadError, {
    props: { error: new TaskApiError(422, details.code, details.message, details) },
  })
  expect(wrapper.text()).toContain(details.request_id)
  for (const field of details.field_errors) {
    expect(wrapper.text()).toContain(field.path)
    expect(wrapper.text()).toContain(field.message)
    expect(wrapper.text()).toContain(field.code)
  }
  expect(wrapper.text()).toContain('不授权重发广告操作')
  expect(wrapper.text()).toContain('UNKNOWN')
  expect(wrapper.findAll('img,script,button,a')).toHaveLength(0)
  wrapper.unmount()
})
it('本地合成错误明确没有服务端编号且无服务端重试结论', () => {
  const wrapper = mount(TaskReadError, {
    props: { error: new TaskApiError(0, 'NETWORK_UNAVAILABLE', '网络中断') },
  })
  expect(wrapper.text()).toContain('未取得服务端请求编号')
  expect(wrapper.text()).toContain('本地错误，无服务端重试结论')
  wrapper.unmount()
})
it('撤权完整清理说明保留，本地控制帧不冒用旧HTTP或事件请求编号', async () => {
  vi.spyOn(tasksApi, 'list').mockResolvedValue(taskPage())
  const wrapper = mount(TaskPanel, {
    props: { active: true },
    global: { plugins: [ElementPlus], stubs: { TaskDetails: true } },
  })
  await flushPromises()
  wrapper
    .findComponent({ name: 'TaskDetails' })
    .vm.$emit('revoked', new TaskApiError(403, 'SCOPE_REVOKED', '当前任务读取权限已撤销'))
  await flushPromises()
  expect(wrapper.text()).toContain('当前任务读取权限已撤销，旧数据已清除。')
  expect(wrapper.text()).toContain('未取得服务端请求编号')
  expect(wrapper.text()).not.toContain(details.request_id)
  expect(wrapper.findAll('.task-list .el-table__body tr')).toHaveLength(0)
  wrapper.unmount()
})
it('真实HTTP撤权错误卡片编号只取本次服务端Error.request_id', async () => {
  const expected = { ...details, code: 'PERMISSION_DENIED', retryable: false }
  vi.spyOn(tasksApi, 'list').mockRejectedValue(
    new TaskApiError(403, expected.code, expected.message, expected),
  )
  const wrapper = mount(TaskPanel, {
    props: { active: true },
    global: { plugins: [ElementPlus], stubs: { TaskDetails: true } },
  })
  await flushPromises()
  expect(wrapper.findComponent(TaskReadError).props('error')).toMatchObject({
    source: 'server',
    request_id: expected.request_id,
  })
  expect(wrapper.text()).toContain(expected.request_id)
  expect(wrapper.text()).not.toContain('未取得服务端请求编号')
  expect(wrapper.findAll('.task-list .el-table__body tr')).toHaveLength(0)
  wrapper.unmount()
})
it('相同tasks.read的actor上下文切换清错/清数据，旧GET错误晚到不能盖住新用户', async () => {
  let rejectOld!: (error: unknown) => void
  const old = new Promise<never>((_, reject) => {
    rejectOld = reject
  })
  vi.spyOn(tasksApi, 'list')
    .mockRejectedValueOnce(new TaskApiError(422, details.code, details.message, details))
    .mockReturnValueOnce(old)
    .mockResolvedValue(taskPage())
  const wrapper = mount(TaskPanel, {
    props: { active: true, contextKey: 'actor-A:tasks.read' },
    global: { plugins: [ElementPlus], stubs: { TaskDetails: true } },
  })
  await flushPromises()
  expect(wrapper.text()).toContain(details.request_id)
  // 未attach的纯挂载不执行浏览器默认submit；显式派发表单原submit事件。
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(tasksApi.list).toHaveBeenCalledTimes(2)
  await wrapper.setProps({ contextKey: 'actor-B:tasks.read' })
  await flushPromises()
  expect(wrapper.text()).not.toContain(details.request_id)
  expect(wrapper.findAll('.task-list .el-table__body tr')).toHaveLength(1)
  rejectOld(new TaskApiError(403, details.code, details.message, details))
  await flushPromises()
  expect(wrapper.text()).not.toContain(details.request_id)
  expect(wrapper.findAll('.task-list .el-table__body tr')).toHaveLength(1)
  await wrapper.setProps({ active: false })
  expect(wrapper.text()).not.toContain(details.request_id)
  expect(wrapper.findAll('.task-list .el-table__body tr')).toHaveLength(0)
  wrapper.unmount()
})
