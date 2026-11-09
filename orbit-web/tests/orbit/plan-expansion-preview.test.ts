import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import Preview from '@/views/orbit/launch/PlanExpansionPreview.vue'
import { allocation, names, campaignKey } from './plan-validation-fixtures'
import { taskUuid as id } from './tasks-fixtures'
let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
})
function button(text: string) {
  return [...document.querySelectorAll('button')].find((node) => node.textContent?.trim() === text)!
}
it('完整10000映射本地有界分页，最后一项不截断，命名按真实三段前缀且保留序号字符串', async () => {
  const value = allocation()
  value.items = Array.from({ length: 10000 }, (_, n) => ({
    ...value.items[0],
    slot_key: `${campaignKey}/${id(6)}/1/${id(7)}/${n + 1}`,
  }))
  wrapper = mount(Preview, {
    attachTo: document.body,
    props: {
      modelValue: true,
      allocation: value,
      reservation: names(),
      assetIds: [id(3), id(999)],
    },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  expect(document.querySelectorAll('.mapping-table .el-table__body tr')).toHaveLength(20)
  expect(document.body.textContent).toContain('000123456789012345678901234567')
  const size = wrapper.findComponent({ name: 'ElSelect' })
  size.vm.$emit('update:modelValue', 200)
  size.vm.$emit('change', 200)
  await flushPromises()
  button('末页映射').click()
  await flushPromises()
  expect(document.querySelectorAll('.mapping-table .el-table__body tr')).toHaveLength(200)
  expect(document.body.textContent).toContain(`${campaignKey}/${id(6)}/1/${id(7)}/10000`)
  expect(button('下一页映射').disabled).toBe(true)
  expect(document.querySelector('.usage-table')?.textContent).toContain('10000')
  expect(document.querySelector('.usage-table')?.textContent).toContain(id(999))
  expect(document.body.textContent).toContain('次数不承诺相差不超过')
})
it('所有冻结名称另有分页，未知路径明确显示缺失而不猜名称，XSS为纯文本', async () => {
  const value = allocation()
  value.items[0].slot_key = '<img src=x onerror=alert(1)>'
  const reservation = names()
  reservation.items = Array.from({ length: 101 }, (_, i) => ({
    ...reservation.items[0],
    slot_key: `path/${i}`,
    name: `名称${i}`,
  }))
  wrapper = mount(Preview, {
    attachTo: document.body,
    props: { modelValue: true, allocation: value, reservation, assetIds: [id(3)] },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  expect(document.body.textContent).toContain('未匹配冻结系列名称')
  expect(document.querySelector('img[src="x"]')).toBeNull()
  expect(document.querySelectorAll('.name-table .el-table__body tr')).toHaveLength(50)
  button('下一页名称').click()
  await flushPromises()
  button('下一页名称').click()
  await flushPromises()
  expect(document.querySelector('.name-table')?.textContent).toContain('名称100')
  expect(button('下一页名称').disabled).toBe(true)
})
