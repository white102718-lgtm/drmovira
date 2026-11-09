/** 真实控件焦点与二级预算弹窗；没有后端/平台成功替身。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Tree from '@/views/orbit/launch/CampaignTree.vue'
import Draft from '@/views/orbit/launch/DraftEditor.vue'
import { launchApi } from '@/api/orbit/launch'
import { plan, caps } from './plan-validation-fixtures'
import { readDraftRecovery } from '@/api/orbit/launch-recovery'
const wrappers: VueWrapper[] = []
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(launchApi, 'owners').mockResolvedValue({
    items: [],
    next_cursor: null,
    scope_version: 1,
  })
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
  sessionStorage.clear()
  vi.restoreAllMocks()
})
async function tree() {
  const source = plan()
  source.campaigns[0].adsets[0].ads[0].title = '原广告标题'
  const wrapper = mount(Tree, {
    attachTo: document.body,
    props: { modelValue: source.campaigns },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return {
    wrapper,
    source,
    focus: wrapper.vm as unknown as {
      focusField: (id: string, path: string[]) => Promise<boolean>
    },
  }
}
const activeLabel = () =>
  document.activeElement?.closest('.el-form-item')?.querySelector('label')?.textContent?.trim()
it('真实系列/组/广告local_id选中并聚焦各自字段，切换不改任何原配置', async () => {
  const { source, wrapper, focus } = await tree(),
    original = JSON.stringify(source.campaigns)
  expect(await focus.focusField(source.campaigns[0].local_id, ['objective'])).toBe(true)
  expect(activeLabel()).toBe('投放目标')
  expect(await focus.focusField(source.campaigns[0].adsets[0].local_id, ['billing_event'])).toBe(
    true,
  )
  expect(activeLabel()).toBe('计费事件')
  expect(
    await focus.focusField(source.campaigns[0].adsets[0].local_id, ['metric_profile_id']),
  ).toBe(true)
  expect(activeLabel()).toBe('指标配置ID（草稿可空）')
  expect(await focus.focusField(source.campaigns[0].adsets[0].ads[0].local_id, ['title'])).toBe(
    true,
  )
  expect(activeLabel()).toBe('标题（最多100码点）')
  expect((document.activeElement as HTMLInputElement).value).toBe('原广告标题')
  expect(JSON.stringify(wrapper.props('modelValue'))).toBe(original)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
it('预算金额定位打开真实二级页、聚焦原十进制字符串，不自动确认或写树', async () => {
  const { source, wrapper, focus } = await tree()
  source.campaigns[0].budget = {
    owner: 'CAMPAIGN',
    type: 'DAILY',
    amount: '12.340000',
    currency: 'USD',
    spend_cap: null,
  }
  expect(await focus.focusField(source.campaigns[0].local_id, ['budget', 'amount'])).toBe(true)
  expect(activeLabel()).toBe('金额（十进制字符串）')
  expect((document.activeElement as HTMLInputElement).value).toBe('12.340000')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
it('未知字段/缺失local_id拒绝假焦点，只读控件不得借定位变成可编辑', async () => {
  const { source, wrapper, focus } = await tree()
  expect(await focus.focusField('missing', ['name'])).toBe(false)
  expect(await focus.focusField(source.campaigns[0].local_id, ['name'])).toBe(false)
  expect(await focus.focusField(source.campaigns[0].local_id, ['objective', 'unknown'])).toBe(false)
  await wrapper.setProps({ disabled: true })
  expect(await focus.focusField(source.campaigns[0].local_id, ['objective'])).toBe(false)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
async function draft(path: string, segments: string[], revision = 7) {
  const source = plan()
  source.campaigns[0].adsets[0].ads[0].title = '真实保存标题'
  const wrapper = mount(Draft, {
    attachTo: document.body,
    props: {
      modelValue: true,
      plan: source,
      capabilities: caps(),
      focusField: { path, segments, revision },
    },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, source }
}
it('父传同head Pointer穿过Draft选中真实广告标题，定位不产生草稿改动', async () => {
  await draft('/campaigns/0/adsets/0/ads/0/title', [
    'campaigns',
    '0',
    'adsets',
    '0',
    'ads',
    '0',
    'title',
  ])
  expect(activeLabel()).toBe('标题（最多100码点）')
  expect((document.activeElement as HTMLInputElement).value).toBe('真实保存标题')
  expect(document.body.textContent).toContain('已定位当前版本的实际字段')
  expect(readDraftRecovery(caps().actor_user_id)).toBeNull()
})
it('未知合法Pointer保留原文和不可定位提示，不选择相似字段；旧来源版本也拒绝', async () => {
  const { wrapper } = await draft('/unknown~1field~0', ['unknown/field~'])
  expect(document.body.textContent).toContain('/unknown~1field~0')
  expect(document.body.textContent).toContain('未假定其他字段')
  expect(document.activeElement?.getAttribute('role')).toBe('status')
  await wrapper.setProps({ focusField: { path: '/name', segments: ['name'], revision: 99 } })
  await flushPromises()
  expect(document.body.textContent).toContain('错误来源版本或编辑意图已变化')
  expect(activeLabel()).toBeUndefined()
})
it('顶层计划名称焦点是实际可编辑控件，错误的Pointer解码与不存在树索引不得定位', async () => {
  const { wrapper } = await draft('/name', ['name'])
  expect(activeLabel()).toBe('计划名称（草稿可空，最多100码点）')
  await wrapper.setProps({
    focusField: {
      path: '/campaigns/999/ads/0/title',
      segments: ['campaigns', '999', 'ads', '0', 'title'],
      revision: 7,
    },
  })
  await flushPromises()
  expect(document.body.textContent).toContain('未假定其他字段')
  await wrapper.setProps({ focusField: { path: '/name~2', segments: ['name'], revision: 7 } })
  await flushPromises()
  expect(document.body.textContent).toContain('不符合JSON Pointer')
})
it('身份字段Pointer穿过Draft按账户和组local_id打开真实输入，未应用不改原缓存', async () => {
  const source = plan(),
    gid = source.campaigns[0].adsets[0].local_id
  source.campaigns[0].objective = 'OUTCOME_SALES'
  source.identity_bindings = [
    {
      account_id: source.account_ids[0],
      page_id: '1234567890',
      groups: [
        {
          adset_local_id: gid,
          pixel_id: '22',
          conversion_event: 'EXISTING_EVENT',
          application_id: null,
          object_store_url: null,
        },
      ],
      ad_overrides: [],
    },
  ]
  const path = '/identity_bindings/0/groups/0/conversion_event'
  const wrapper = mount(Draft, {
    attachTo: document.body,
    props: {
      modelValue: true,
      plan: source,
      capabilities: caps(),
      focusField: {
        path,
        segments: ['identity_bindings', '0', 'groups', '0', 'conversion_event'],
        revision: 7,
      },
    },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  expect(activeLabel()).toBe(`优化事件 ${gid}（待能力核验）`)
  expect((document.activeElement as HTMLInputElement).value).toBe('EXISTING_EVENT')
  expect(document.body.textContent).toContain('已定位当前版本的实际字段')
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([true])
  expect(readDraftRecovery(caps().actor_user_id)).toBeNull()
})
