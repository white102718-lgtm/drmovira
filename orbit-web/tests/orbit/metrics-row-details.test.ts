/** 只读详情完整原15字段及12个值，不增加不存在的操作或外部对象字段。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import Details from '@/views/orbit/monitor/MetricRowDetails.vue'
import { metricValueKeys, type MetricRow } from '@/api/orbit/metrics'
let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
})
it('14元字段加values的12子字段全部显示，null明确未知并转义名称', async () => {
  const id = '00000000-0000-0000-0000-000000000001'
  const row: MetricRow = {
    tenant_id: id,
    owner_team_id: null,
    operator_user_id: null,
    entity_id: '00000123',
    name: '<img src=x onerror=alert(1)>',
    channel_id: null,
    product_name_snapshot: null,
    currency: 'USD',
    metric_profile_id: id,
    business_date: '2026-01-01',
    account_count: 0,
    ad_count: 0,
    values: Object.fromEntries(metricValueKeys.map((k) => [k, null])) as MetricRow['values'],
    quality: 'UNKNOWN',
    coverage: '0',
  }
  wrapper = mount(Details, {
    props: { row },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  expect(document.querySelectorAll('dt')).toHaveLength(26)
  expect(document.querySelectorAll('dd')).toHaveLength(26)
  expect(document.body.textContent).toContain('00000123')
  expect(document.body.textContent).toContain('未知')
  expect(document.querySelector('img')).toBeNull()
  expect(document.body.textContent).toContain(row.name)
  expect(document.body.textContent).not.toContain('重新执行')
})
