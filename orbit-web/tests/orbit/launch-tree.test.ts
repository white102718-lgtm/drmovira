import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import CampaignTree from '@/views/orbit/launch/CampaignTree.vue'
import type { CampaignConfig } from '@/api/orbit/launch'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})
function mounted(disabled = false) {
  const component = defineComponent({
    components: { CampaignTree },
    setup() {
      return { rows: ref<CampaignConfig[]>([]), locked: ref(disabled) }
    },
    template: '<CampaignTree v-model="rows" :disabled="locked" />',
  })
  const wrapper = mount(component, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper)
  return wrapper
}
async function click(wrapper: ReturnType<typeof mount>, label: string) {
  const button = wrapper.findAll('button').find((button) => button.text() === label)
  expect(button, label).toBeTruthy()
  await button!.trigger('click')
  await flushPromises()
}
it('三层增建与复制是字段表单操作，移除节点同步配置树', async () => {
  const wrapper = mounted()
  await click(wrapper, '新增系列')
  await click(wrapper, '新增广告组')
  await click(wrapper, '新增广告')
  const title = wrapper
    .findAll('.el-form-item')
    .find((item) => item.text().includes('标题（最多100码点）'))
  await title!.get('input').setValue('😀'.repeat(100))
  expect(title!.text()).toContain('100/100')
  await click(wrapper, '复制配置')
  const rows = (wrapper.vm as unknown as { rows: CampaignConfig[] }).rows
  expect(rows[0].adsets[0].ads).toHaveLength(2)
  expect(rows[0].adsets[0].ads[0].local_id).not.toBe(rows[0].adsets[0].ads[1].local_id)
  await click(wrapper, '移除节点')
  expect(rows[0].adsets[0].ads).toHaveLength(1)
})
it('父表单禁用时不能通过子组件新增或复制覆盖冻结意图', async () => {
  const wrapper = mounted(true)
  const add = wrapper.findAll('button').find((button) => button.text() === '新增系列')!
  expect(add.attributes('disabled')).toBeDefined()
  await add.trigger('click')
  expect((wrapper.vm as unknown as { rows: CampaignConfig[] }).rows).toEqual([])
})
it('广告组手填指标UUID不依赖目录权限，清空实际删除optional属性', async () => {
  const wrapper = mounted()
  await click(wrapper, '新增系列')
  await click(wrapper, '新增广告组')
  const input = wrapper.get('input[aria-label="指标配置ID（草稿可空）"]')
  const uuid = '00000000-0000-4000-8000-000000000099'
  await input.setValue(uuid)
  const rows = (wrapper.vm as unknown as { rows: CampaignConfig[] }).rows
  expect(rows[0].adsets[0].metric_profile_id).toBe(uuid)
  await input.setValue('')
  expect(rows[0].adsets[0]).not.toHaveProperty('metric_profile_id')
})
it('预算弹窗使用十进制字符串拒绝科学计数法，取消不会写入父节点', async () => {
  const wrapper = mounted()
  await click(wrapper, '新增系列')
  await click(wrapper, '配置预算')
  await flushPromises()
  const dialog = document.body.querySelector('[role="dialog"]')!
  const inputs = [...dialog.querySelectorAll('input')]
  const amount = inputs.find((input) => input.placeholder.includes('大于0'))!
  const currency = inputs.find((input) => input.placeholder.includes('真实币种'))!
  amount.value = '1e2'
  amount.dispatchEvent(new Event('input', { bubbles: true }))
  currency.value = 'USD'
  currency.dispatchEvent(new Event('input', { bubbles: true }))
  const confirm = [...dialog.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === '确认预算配置',
  )!
  confirm.click()
  await flushPromises()
  expect(dialog.textContent).toContain('请填写合法十进制金额')
  expect((wrapper.vm as unknown as { rows: CampaignConfig[] }).rows[0].budget).toBeUndefined()
  ;[...dialog.querySelectorAll('button')]
    .find((button) => button.textContent?.trim() === '取消')!
    .click()
  await flushPromises()
  expect((wrapper.vm as unknown as { rows: CampaignConfig[] }).rows[0].budget).toBeUndefined()
})
