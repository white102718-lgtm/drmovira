/** 表格仅呈现服务端快照，禁止客户端页内汇总或金额浮点化。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import Rows from '@/views/orbit/monitor/MetricRows.vue'
import { metricValueKeys, type Metrics, type MetricRow } from '@/api/orbit/metrics'
let wrapper: VueWrapper | undefined
const id = '00000000-0000-0000-0000-000000000001'
const values = Object.fromEntries(
  metricValueKeys.map((k) => [k, k === 'spend' ? '123456789012345678901.123456' : null]),
) as MetricRow['values']
const row: MetricRow = {
  tenant_id: id,
  owner_team_id: null,
  operator_user_id: null,
  entity_id: '0012345',
  name: '<script>不是HTML</script>',
  channel_id: null,
  product_name_snapshot: null,
  currency: 'USD',
  metric_profile_id: id,
  business_date: null,
  account_count: 1,
  ad_count: 2,
  values,
  quality: 'PARTIAL',
  coverage: '0.5',
}
const page: Metrics = {
  items: [row],
  next_cursor: 'opaque',
  scope_version: 8,
  snapshot_id: id,
  data_as_of: '2026-11-08T00:00:00Z',
  missing_count: 1,
  query_snapshot_id: id,
  totals: [
    {
      tenant_id: id,
      currency: 'EUR',
      metric_profile_id: id,
      account_count: 3,
      ad_count: 7,
      missing_count: 1,
      coverage: '0.75',
      values: { ...values, spend: '999.000001' },
    },
  ],
}
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
})
it('全部12指标可见，完整大金额/前导零原样，totals独立币种不合并', async () => {
  wrapper = mount(Rows, {
    props: { data: page },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  const text = wrapper.text()
  for (const value of [
    '123456789012345678901.123456',
    '999.000001',
    '0012345',
    'USD',
    'EUR',
    '注册',
    '购物',
    '素材使用量',
    '0.75',
    '缺失单元1',
    '权限版本8',
  ])
    expect(text).toContain(value)
  expect(wrapper.find('script').exists()).toBe(false)
  expect(text).toContain('<script>不是HTML</script>')
  expect(wrapper.findAllComponents({ name: 'ElTable' })).toHaveLength(2)
  const buttons = wrapper.findAll('button').filter((b) => b.text() === '只读详情')
  await buttons[0].trigger('click')
  expect(wrapper.emitted('detail')![0][0]).toEqual(row)
})
it('初始/成功空实体/仍有totals三个状态不混为来源失败', async () => {
  wrapper = mount(Rows, { props: { data: null }, global: { plugins: [ElementPlus] } })
  expect(wrapper.text()).toContain('尚无成功查询')
  await wrapper.setProps({ data: { ...page, items: [] } })
  await flushPromises()
  expect(wrapper.text()).toContain('当前筛选没有实体')
  expect(wrapper.text()).toContain('999.000001')
})
