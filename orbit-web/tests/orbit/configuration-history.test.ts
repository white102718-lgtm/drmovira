import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import History from '@/views/orbit/system/configuration/ConfigurationHistory.vue'
import type { Configuration } from '@/api/orbit/configuration'
const { fetchHistory } = vi.hoisted(() => ({ fetchHistory: vi.fn() }))
vi.mock('@/api/orbit/configuration', () => ({ getConfigurationHistory: fetchHistory }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
  document.body.innerHTML = ''
  fetchHistory.mockReset()
})
function setup() {
  const wrapper = mount(History, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  wrappers.push(wrapper)
  return wrapper
}
const config = (id: string) => ({ id, name: id }) as Configuration
const item = (id: string, revision: number) => ({
  id,
  revision,
  actorId: 7,
  action: 'UPDATE',
  changedFields: ['secret:apiKey:replaced'],
  reason: '凭据轮换',
  createdAt: '2026-11-07T00:00:00Z',
})
it('展示脱敏历史并使用服务器版本游标继续加载', async () => {
  fetchHistory
    .mockResolvedValueOnce({ items: [item('a', 3)], nextBeforeRevision: 3 })
    .mockResolvedValueOnce({ items: [item('b', 2)], nextBeforeRevision: null })
  const wrapper = setup()
  wrapper.vm.open(config('config-a'))
  await flushPromises()
  expect(document.body.textContent).toContain('凭据轮换')
  const button = Array.from(document.querySelectorAll('button')).find((b) =>
    b.textContent?.includes('继续加载'),
  )!
  button.click()
  await flushPromises()
  expect(fetchHistory).toHaveBeenLastCalledWith('config-a', 3)
  expect(document.querySelectorAll('.el-table__body tbody tr')).toHaveLength(2)
})
it('切换配置后丢弃旧请求结果', async () => {
  let resolveOld!: (value: unknown) => void
  fetchHistory
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        }),
    )
    .mockResolvedValueOnce({ items: [item('new', 2)], nextBeforeRevision: null })
  const wrapper = setup()
  wrapper.vm.open(config('old'))
  wrapper.vm.open(config('new'))
  await flushPromises()
  resolveOld({ items: [{ ...item('old', 1), reason: '过期响应不可见' }], nextBeforeRevision: null })
  await flushPromises()
  expect(document.body.textContent).not.toContain('过期响应不可见')
  expect(document.body.textContent).toContain('凭据轮换')
})
it('失败明确显示错误并可重试', async () => {
  fetchHistory
    .mockRejectedValueOnce(new Error('历史读取失败'))
    .mockResolvedValueOnce({ items: [], nextBeforeRevision: null })
  const wrapper = setup()
  wrapper.vm.open(config('config-a'))
  await flushPromises()
  expect(document.body.textContent).toContain('历史读取失败')
  Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent?.includes('重试加载'))!
    .click()
  await flushPromises()
  expect(document.body.textContent).not.toContain('历史读取失败')
  expect(fetchHistory).toHaveBeenCalledTimes(2)
})

it('展开显示摘要并区分新增配置与未采集的历史', async () => {
  fetchHistory.mockResolvedValueOnce({
    items: [
      {
        ...item('a', 1),
        beforeRevision: 0,
        beforeHash: null,
        afterHash: 'a'.repeat(64),
        hashAlgorithm: 'SHA256_STATE_V1',
      },
    ],
    nextBeforeRevision: null,
  })
  const wrapper = setup()
  wrapper.vm.open(config('config-a'))
  await flushPromises()
  ;(document.querySelector('.el-table__expand-icon') as HTMLElement).click()
  await flushPromises()
  expect(document.body.textContent).toContain('新增配置，无旧状态')
  expect(document.body.textContent).toContain('a'.repeat(64))
  expect(document.body.textContent).toContain('SHA256_STATE_V1')
})
it('旧记录无摘要显示未采集，不填零或伪造摘要', async () => {
  fetchHistory.mockResolvedValueOnce({ items: [item('legacy', 3)], nextBeforeRevision: null })
  const wrapper = setup()
  wrapper.vm.open(config('config-a'))
  await flushPromises()
  ;(document.querySelector('.el-table__expand-icon') as HTMLElement).click()
  await flushPromises()
  expect(document.body.textContent).toContain('历史记录未采集')
  expect(document.body.textContent).toContain('未知 → 3')
})
