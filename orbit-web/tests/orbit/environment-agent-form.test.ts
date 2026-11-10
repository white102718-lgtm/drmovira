import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import AgentRegistrationForm from '@/views/orbit/environments/AgentRegistrationForm.vue'
const wrappers: ReturnType<typeof mount>[] = []
function start(props = {}) {
  const wrapper = mount(AgentRegistrationForm, { props, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
  vi.restoreAllMocks()
})
it('keeps original fields, defaults only interval, explains independent unknown layers', () => {
  const wrapper = start()
  expect(wrapper.text()).toContain('机器名称')
  expect(wrapper.text()).toContain('本地 API 地址')
  expect(wrapper.text()).toContain('探测周期')
  for (const text of ['设备证书', '心跳', 'Meta 登录', '操作能力', '未知'])
    expect(wrapper.text()).toContain(text)
  expect(wrapper.find('input[aria-label="本地 API 地址"]').element.value).toBe('')
  expect(wrapper.find('input[aria-label="探测周期（秒）"]').element.value).toBe('30')
  expect(wrapper.findAll('input[type="password"]')).toHaveLength(0)
})
it('emits validated registration data only and never probes localhost', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch')
  const wrapper = start()
  await wrapper.find('input[aria-label="机器名称"]').setValue('执行机')
  await wrapper.find('input[aria-label="本地 API 地址"]').setValue('http://localhost:50325/')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(wrapper.emitted('submit')?.[0]).toEqual([
    { name: '执行机', endpoint: 'http://127.0.0.1:50325', probe_interval: 30 },
  ])
  expect(fetchSpy).not.toHaveBeenCalled()
})
it('invalid data stays visible and is not emitted', async () => {
  const wrapper = start()
  await wrapper.find('input[aria-label="机器名称"]').setValue('执行机')
  await wrapper.find('input[aria-label="本地 API 地址"]').setValue('ftp://api.example:50325')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('submit')).toBeUndefined()
  expect(wrapper.text()).toContain('HTTP')
  expect(wrapper.find('input[aria-label="本地 API 地址"]').element.value).toContain('api.example')
})
it('locked or unauthorized registration cannot emit even via direct form submit', async () => {
  const wrapper = start({ disabled: true, disabledReason: '请先核对上次登记结果' })
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('submit')).toBeUndefined()
  expect(wrapper.text()).toContain('请先核对上次登记结果')
})
it('initializes edit fields without copying response state into the submitted body', async () => {
  const initialValue = { name: '旧机器', endpoint: 'http://127.0.0.1:50325', probe_interval: 60 }
  const wrapper = start({ initialValue, submitLabel: '保存修改' })
  expect(wrapper.find('input[aria-label="机器名称"]').element.value).toBe('旧机器')
  await wrapper.find('input[aria-label="机器名称"]').setValue('新机器')
  await wrapper.find('form').trigger('submit')
  expect(wrapper.emitted('submit')?.[0]).toEqual([{ ...initialValue, name: '新机器' }])
  expect(initialValue.name).toBe('旧机器')
})
