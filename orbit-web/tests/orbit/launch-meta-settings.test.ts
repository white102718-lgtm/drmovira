import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it } from 'vitest'
import Fields from '@/views/orbit/launch/MetaSettingsFields.vue'
import Tree from '@/views/orbit/launch/CampaignTree.vue'
import { newCampaign, newAdSet, newAd, newDraft, normalizeDraft } from '@/api/orbit/launch-form'
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})
it('新节点采用安全产品默认，应用目标关联应用资源，不造预算或真实资源', () => {
  const campaign = newCampaign(),
    group = newAdSet(),
    app = newAdSet('OUTCOME_APP_PROMOTION'),
    ad = newAd()
  expect(campaign.objective).toBe('OUTCOME_SALES')
  expect(campaign.meta_settings?.advantage_campaign_budget).toBe(false)
  expect(group.meta_settings?.conversion_location).toBe('WEBSITE')
  expect(app.meta_settings?.conversion_location).toBe('APP')
  expect(app.optimization_goal).toBe('APP_INSTALLS')
  expect(group.budget).toBeUndefined()
  expect(group.country_codes).toBeUndefined()
  expect(group.metric_profile_id).toBeUndefined()
  expect(ad.meta_settings?.format).toBe('SINGLE')
})
it('高级控件折叠与字段定位不修改旧草稿，未知字段拒绝定位', async () => {
  const source = { local_id: 'c', copies: 1, adsets: [{ local_id: 'g', copies: 1, ads: [] }] }
  const before = JSON.stringify(source)
  const wrapper = mount(Tree, {
    attachTo: document.body,
    props: { modelValue: [source] },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  expect(wrapper.find('[data-meta-path="devices.ios_min_version"]').exists()).toBe(false)
  expect(await wrapper.vm.focusField('g', ['meta_settings', 'devices', 'ios_min_version'])).toBe(
    true,
  )
  expect(document.activeElement?.closest('.el-form-item')?.textContent).toContain('iOS 最低版本')
  expect(await wrapper.vm.focusField('g', ['meta_settings', 'devices', 'invented'])).toBe(false)
  expect(JSON.stringify(source)).toBe(before)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
it('新字段按合同保存回读，旧字段与未知历史版位保留显示', async () => {
  const settings = {
    manual_placements: { facebook: ['FEED', 'HISTORICAL_SLOT'] },
    devices: { ios_min_version: '16.0', excluded_ios_models: ['iPhone 12'] },
    attribution_click_days: 1 as const,
  }
  const wrapper = mount(Fields, {
    props: { kind: 'adset', placements: 'MANUAL', modelValue: settings },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await wrapper.get('button.advanced-toggle').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('HISTORICAL_SLOT')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  const draft = newDraft({ owner_user_id: 'a', owner_team_id: 't' })
  draft.campaigns = [newCampaign()]
  draft.campaigns[0].adsets = [newAdSet()]
  draft.campaigns[0].adsets[0].meta_settings = {
    devices: { ios_min_version: '16.0' },
    attribution_click_days: 1,
    conversion_event: 'PURCHASE',
  }
  expect(normalizeDraft(draft).campaigns[0].adsets[0].meta_settings).toEqual(
    draft.campaigns[0].adsets[0].meta_settings,
  )
})
it('只读新字段控件及高级定位不能编辑', async () => {
  const wrapper = mount(Fields, {
    props: { kind: 'campaign', disabled: true },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  expect(await wrapper.vm.focusField(['bid_amount'])).toBe(false)
  expect(await wrapper.vm.focusField(['bid_amount', '0'])).toBe(false)
  expect(
    wrapper.findAll('input').every((input) => input.attributes('disabled') !== undefined),
  ).toBe(true)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
it('竞价与轮播条件字段按选择展示，轮播只选素材池或保留既有引用', async () => {
  const campaign = mount(Fields, {
    props: { kind: 'campaign', bidStrategy: 'LOWEST_COST_WITHOUT_CAP' },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(campaign)
  expect(campaign.find('[data-meta-path="bid_amount"]').exists()).toBe(false)
  await campaign.setProps({ bidStrategy: 'COST_CAP' })
  await campaign.get('[data-meta-path="bid_amount"] input').setValue('12.34')
  expect(campaign.emitted('update:modelValue')?.[0][0]).toEqual({ bid_amount: '12.34' })
  const ad = mount(Fields, {
    props: { kind: 'ad', modelValue: { format: 'SINGLE' }, assetIds: ['pool-asset'] },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(ad)
  expect(ad.find('[data-meta-path="carousel_asset_ids"]').exists()).toBe(false)
  await ad.setProps({ modelValue: { format: 'CAROUSEL' } })
  const picker = ad.get('[data-meta-path="carousel_asset_ids"]')
  expect(picker.exists()).toBe(true)
  expect(picker.findComponent({ name: 'ElSelect' }).props('allowCreate')).toBe(false)
})

it('版位及设备对象级错误定位真实控件并展开，不回填配置', async () => {
  const wrapper = mount(Fields, {
    attachTo: document.body,
    props: { kind: 'adset' },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  expect(await wrapper.vm.focusField(['manual_placements'])).toBe(true)
  expect(document.activeElement?.closest('.el-form-item')?.textContent).toContain('Facebook 版位')
  expect(await wrapper.vm.focusField(['devices'])).toBe(true)
  expect(document.activeElement?.closest('.el-form-item')?.textContent).toContain('设备平台')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
it('转化事件按系列目标筛选，历史冲突值保留可见而不自动删除', async () => {
  const wrapper = mount(Fields, {
    attachTo: document.body,
    props: {
      kind: 'adset',
      objective: 'OUTCOME_LEADS',
      modelValue: { conversion_event: 'PURCHASE' },
    },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  const field = () => wrapper.get('[data-meta-path="conversion_event"]')
  await field().get('.el-select').trigger('click')
  await flushPromises()
  const choices = () => {
    const id = field().get('input').attributes('aria-controls')
    return [...document.getElementById(id)!.querySelectorAll('.el-select-dropdown__item')].map(
      (item) => item.textContent,
    )
  }
  expect(choices()).toContain('PURCHASE（已保存，待能力核验）')
  expect(choices()).toContain('潜在客户')
  await wrapper.setProps({ objective: 'OUTCOME_SALES', modelValue: {} })
  await flushPromises()
  expect(choices()).not.toContain('潜在客户')
  expect(choices()).toContain('购物')
  await wrapper.setProps({ objective: 'OUTCOME_APP_PROMOTION' })
  await flushPromises()
  expect(choices()).toEqual([])
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
})
