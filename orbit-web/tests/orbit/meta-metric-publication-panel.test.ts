import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton, ElSelect, ElInputNumber } from 'element-plus'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import Panel from '@/views/orbit/system/configuration/MetricPublicationPanel.vue'
import { metricPublicationApi, type PublicationOptions } from '@/api/orbit/meta-metric-publication'
import { metaConnectionApi } from '@/api/orbit/meta-connections'
const id = '00000000-0000-4000-8000-000000000001'
const source = '00000000-0000-4000-8000-000000000002'
let wrapper: VueWrapper
let options: PublicationOptions
beforeEach(() => {
  options = {
    csrf_token: 'csrf',
    configured: true,
    api_version: 'v24.0',
    adapter_version: 'META_INSIGHTS_V24_EXPLICIT_V1',
    attribution_windows: ['7d_click', '1d_view'],
    action_report_times: ['conversion'],
    configurations: [
      {
        id,
        name: '原指标配置',
        revision: 3,
        head_revision: 0,
        settings: {
          profileVersion: 'release1',
          registerActionType: 'registration',
          purchaseActionType: 'purchase',
          valueActionType: 'purchase_value',
        },
      },
    ],
    connections: [{ id: source, revision: 2, kind: 'LOGIN', status: 'ACTIVE' }],
  }
  vi.spyOn(metricPublicationApi, 'options').mockImplementation(async () => options)
  vi.spyOn(metaConnectionApi, 'accounts').mockResolvedValue({
    items: [
      { external_id: '123', name: '测试账户', currency: 'USD', timezone: 'America/New_York' },
    ],
    next_cursor: null,
  })
  vi.spyOn(metricPublicationApi, 'publish').mockResolvedValue({
    id,
    version: 'release1',
    revision: 1,
    adapter_version: 'META_INSIGHTS_V24_EXPLICIT_V1',
  })
})
afterEach(() => {
  wrapper?.unmount()
  vi.restoreAllMocks()
})
async function start() {
  wrapper = mount(Panel, {
    props: { active: true, configurationId: id, contextKey: 'user1' },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
async function select() {
  const selects = wrapper.findAllComponents(ElSelect)
  selects[0].vm.$emit('update:modelValue', source)
  await flushPromises()
  selects[1].vm.$emit('update:modelValue', '123')
  selects[2].vm.$emit('update:modelValue', ['7d_click'])
  selects[3].vm.$emit('update:modelValue', 'conversion')
  wrapper.findComponent(ElInputNumber).vm.$emit('update:modelValue', 28)
  await flushPromises()
}
async function publish() {
  const button = wrapper.findAllComponents(ElButton).find((b) => b.text().includes('发布'))!
  await button.trigger('click')
  await flushPromises()
}
it('没有默认归因，也不把未配置显示为验证通过', async () => {
  options.configured = false
  options.api_version = null
  await start()
  expect(wrapper.text()).toContain('待验证')
  expect(wrapper.text()).toContain('registration')
  expect(
    wrapper
      .findAllComponents(ElButton)
      .find((b) => b.text().includes('发布'))!
      .props('disabled'),
  ).toBe(true)
  expect(metricPublicationApi.publish).not.toHaveBeenCalled()
})
it('真实候选选择后保留原配置版本及所有明确口径', async () => {
  await start()
  await select()
  await publish()
  expect(metricPublicationApi.publish).toHaveBeenCalledWith(
    {
      configuration_id: id,
      configuration_revision: 3,
      connection_id: source,
      connection_revision: 2,
      account_id: '123',
      attribution_windows: ['7d_click'],
      action_report_time: 'conversion',
      maturity_days: 28,
      expected_revision: 0,
    },
    'csrf',
    expect.any(String),
  )
  expect(wrapper.text()).toContain('release1 已发布')
})
it('结果未知时重试复用原请求和幂等键', async () => {
  vi.mocked(metricPublicationApi.publish).mockRejectedValueOnce(new Error('network unknown'))
  await start()
  await select()
  await publish()
  const original = vi.mocked(metricPublicationApi.publish).mock.calls[0]
  expect(wrapper.text()).toContain('尚未确认')
  await publish()
  expect(vi.mocked(metricPublicationApi.publish).mock.calls[1]).toEqual(original)
})
