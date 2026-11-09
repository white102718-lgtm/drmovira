/** 真实ElementPlus挂载，网络替身仅验证组件边界，不是后端/平台身份验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import IdentityEditor from '@/views/orbit/launch/PlanIdentityBindings.vue'
import { accountIdentitiesApi } from '@/api/orbit/account-identities'
import type { AccountIdentities } from '@/api/orbit/account-details'
import type { CampaignConfig, IdentityBinding } from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const account = id(1),
  group = id(3),
  ad = id(4),
  page = '9'.repeat(64)
const tree = (
  objective: 'OUTCOME_SALES' | 'OUTCOME_APP_PROMOTION' = 'OUTCOME_SALES',
): CampaignConfig[] => [
  {
    local_id: id(2),
    copies: 1,
    objective,
    adsets: [{ local_id: group, copies: 1, ads: [{ local_id: ad, copies: 1 }] }],
  },
]
const observation = (): AccountIdentities => ({
  account_id: account,
  capability_version: 'observed-v1',
  observed_at: '2026-11-08T00:00:00Z',
  resources: [
    { external_id: page, name: '主页观察', kind: 'PAGE', usable: true, reason_code: null },
    { external_id: '22', name: '像素观察', kind: 'PIXEL', usable: true, reason_code: null },
    { external_id: '33', name: '应用观察', kind: 'APPLICATION', usable: true, reason_code: null },
    { external_id: '44', name: '已撤销主页', kind: 'PAGE', usable: false, reason_code: 'REVOKED' },
  ],
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.spyOn(accountIdentitiesApi, 'get').mockResolvedValue(observation())
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(extra: Record<string, unknown> = {}) {
  wrapper = mount(IdentityEditor, {
    attachTo: document.body,
    props: { modelValue: [], accountIds: [account], campaigns: tree(), canRead: true, ...extra },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
function button(text: string) {
  return [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (node) => node.textContent?.trim() === text,
  )!
}
async function click(text: string) {
  expect(button(text), text).toBeTruthy()
  button(text).click()
  await flushPromises()
}
async function open() {
  await click('配置身份')
}
async function loaded() {
  await open()
  await click('读取本账户身份')
}
async function choose(index: number, value: string) {
  wrapper!.findAllComponents({ name: 'ElSelectV2' })[index].vm.$emit('update:modelValue', value)
  await flushPromises()
}
async function input(label: string, value: string) {
  const node = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (node) => node.textContent?.trim() === label,
  )!
  expect(node, label).toBeTruthy()
  const field = document.getElementById(node.htmlFor) as HTMLInputElement
  field.value = value
  field.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
function applied() {
  return wrapper!.emitted('update:modelValue')?.at(-1)?.[0] as IdentityBinding[] | undefined
}
it('不自动扇出读取账户；逐账户主页/网站组/广告覆盖使用local_id与字符串ID完整应用', async () => {
  await start()
  expect(accountIdentitiesApi.get).not.toHaveBeenCalled()
  await loaded()
  await choose(0, page)
  await choose(1, '22')
  await input(`优化事件 ${group}（待能力核验）`, 'PURCHASE_CANDIDATE')
  wrapper!.findComponent({ name: 'ElTabs' }).vm.$emit('update:modelValue', 'ads')
  await flushPromises()
  await choose(2, page)
  await click('应用到本地草稿')
  expect(applied()).toEqual([
    {
      account_id: account,
      page_id: page,
      groups: [
        {
          adset_local_id: group,
          pixel_id: '22',
          conversion_event: 'PURCHASE_CANDIDATE',
          application_id: null,
          object_store_url: null,
        },
      ],
      ad_overrides: [{ ad_local_id: ad, page_id: page }],
    },
  ])
  expect(wrapper!.emitted('editing')?.at(-1)).toEqual([false])
})
it('应用配置只写应用字段，HTTPS及事件64码点校验有JSONPointer且不截断', async () => {
  await start({ campaigns: tree('OUTCOME_APP_PROMOTION') })
  await loaded()
  await choose(0, page)
  await choose(1, '33')
  await input(`应用商店HTTPS URL ${group}（域名待核验）`, 'http://example.com/app')
  await click('应用到本地草稿')
  expect(document.body.textContent).toContain('/identity_bindings/0/groups/0/object_store_url')
  expect(applied()).toBeUndefined()
  await input(`应用商店HTTPS URL ${group}（域名待核验）`, 'https://store.example.com/app')
  await click('应用到本地草稿')
  expect(applied()?.[0].groups[0]).toMatchObject({
    application_id: '33',
    pixel_id: null,
    conversion_event: null,
    object_store_url: 'https://store.example.com/app',
  })
})
it('优化事件65emoji拒绝而64完整保留，绝不默认PURCHASE', async () => {
  await start()
  await loaded()
  await choose(0, page)
  await choose(1, '22')
  expect(document.body.textContent).not.toContain('value="PURCHASE"')
  await input(`优化事件 ${group}（待能力核验）`, '😀'.repeat(65))
  await click('应用到本地草稿')
  expect(applied()).toBeUndefined()
  expect(document.body.textContent).toContain('/conversion_event')
  await input(`优化事件 ${group}（待能力核验）`, '😀'.repeat(64))
  await click('应用到本地草稿')
  expect(applied()?.[0].groups[0].conversion_event).toBe('😀'.repeat(64))
})
it('未配置目标不猜网站或应用；未知资源/不可用主页不能应用', async () => {
  await start({
    campaigns: [{ local_id: id(2), copies: 1, adsets: [{ local_id: group, copies: 1, ads: [] }] }],
  })
  await loaded()
  expect(document.body.textContent).toContain('目标未配置，身份输入关闭')
  expect(wrapper!.findAllComponents({ name: 'ElInput' })).toHaveLength(0)
  await choose(0, '44')
  await click('应用到本地草稿')
  expect(applied()).toBeUndefined()
  expect(document.body.textContent).toContain('/page_id')
})
it('读取503可重试/刷新，403撤权清观察但保留原输入；关闭abort及迟到结果不覆盖', async () => {
  vi.mocked(accountIdentitiesApi.get).mockRejectedValueOnce(
    new ReferenceApiError(503, 'IDENTITIES_UNAVAILABLE', '观察未同步'),
  )
  await start()
  await loaded()
  expect(document.body.textContent).toContain('观察未同步')
  await click('读取本账户身份')
  await choose(0, page)
  vi.mocked(accountIdentitiesApi.get).mockRejectedValueOnce(
    new ReferenceApiError(403, 'PERMISSION_DENIED', '读取权限已撤回'),
  )
  await click('刷新身份观察')
  expect(document.body.textContent).toContain('读取权限已撤回')
  expect(document.body.textContent).not.toContain('能力版本 observed-v1')
  let resolve!: (value: AccountIdentities) => void
  vi.mocked(accountIdentitiesApi.get).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  await click('读取本账户身份')
  const signal = vi.mocked(accountIdentitiesApi.get).mock.calls.at(-1)![1]!
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  await click('取消身份编辑')
  expect(signal.aborted).toBe(true)
  resolve(observation())
  await flushPromises()
  expect(wrapper!.emitted('editing')?.at(-1)).toEqual([false])
  expect(applied()).toBeUndefined()
})
it('取消确认不丢输入，确认取消不改草稿；全账户删除也需确认', async () => {
  await start()
  await loaded()
  await choose(0, page)
  const confirm = vi
    .spyOn(ElMessageBox, 'confirm')
    .mockRejectedValueOnce('cancel')
    .mockResolvedValueOnce('confirm')
  await click('取消身份编辑')
  expect(wrapper!.emitted('editing')?.at(-1)).toEqual([true])
  await click('取消身份编辑')
  expect(applied()).toBeUndefined()
  expect(confirm).toHaveBeenCalledTimes(2)
  await wrapper!.setProps({
    modelValue: [{ account_id: account, page_id: page, groups: [], ad_overrides: [] }],
  })
  confirm.mockRejectedValueOnce('cancel')
  await click('移除')
  expect(applied()).toBeUndefined()
  confirm.mockResolvedValueOnce('confirm')
  await click('移除')
  expect(applied()).toEqual([])
})
it('账户和树变化保留孤立绑定，明确标记并禁止旧弹窗覆盖新树', async () => {
  const original: IdentityBinding = {
    account_id: account,
    page_id: page,
    groups: [
      {
        adset_local_id: id(99),
        pixel_id: '22',
        conversion_event: 'KEEP',
        application_id: null,
        object_store_url: null,
      },
    ],
    ad_overrides: [{ ad_local_id: id(98), page_id: page }],
  }
  await start({ modelValue: [original] })
  await open()
  expect(document.body.textContent).toContain('2 条组或广告绑定已不在当前树中')
  expect(applied()).toBeUndefined()
  await wrapper!.setProps({ accountIds: [], campaigns: [] })
  expect(document.body.textContent).toContain('1 个绑定的账户已移出选择')
  expect(document.body.textContent).toContain('不能覆盖新配置')
  expect(button('应用到本地草稿').disabled).toBe(true)
  expect(wrapper!.props('modelValue')).toEqual([original])
})
it('网站切应用不自动丢像素/事件，原值可见并要求明确移除', async () => {
  const original: IdentityBinding = {
    account_id: account,
    page_id: page,
    groups: [
      {
        adset_local_id: group,
        pixel_id: '22',
        conversion_event: 'KEEP',
        application_id: null,
        object_store_url: null,
      },
    ],
    ad_overrides: [],
  }
  await start({ modelValue: [original], campaigns: tree('OUTCOME_APP_PROMOTION') })
  await loaded()
  expect(document.body.textContent).toContain('旧字段与当前目标不符')
  expect(document.body.textContent).toContain('KEEP')
  await choose(1, '33')
  await input(`应用商店HTTPS URL ${group}（域名待核验）`, 'https://store.example/app')
  await click('应用到本地草稿')
  expect(applied()).toBeUndefined()
  expect(document.body.textContent).toContain('应用配置不能混用网站字段')
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  await click('移除组绑定')
  await click('应用到本地草稿')
  expect(applied()?.[0].groups).toEqual([])
})
it('只读仍可打开并读观察但不出现应用按钮；未知保存disabled阻止配置和读取', async () => {
  await start({
    readOnly: true,
    modelValue: [{ account_id: account, page_id: page, groups: [], ad_overrides: [] }],
  })
  await click('查看身份')
  await click('读取本账户身份')
  expect(button('应用到本地草稿')).toBeUndefined()
  expect(wrapper!.findComponent({ name: 'ElSelectV2' }).props('disabled')).toBe(true)
  // 内部ElForm承担只读禁用，原值展示不因禁写而消失。
  await click('关闭身份详情')
  await wrapper!.setProps({ readOnly: false, disabled: true })
  expect(button('配置身份').disabled).toBe(true)
  expect(applied()).toBeUndefined()
})
it('没有accounts.read默认不读取，不从投放动作推断来源权限', async () => {
  await start({ canRead: false })
  await open()
  expect(button('读取本账户身份').disabled).toBe(true)
  await click('应用到本地草稿')
  expect(accountIdentitiesApi.get).not.toHaveBeenCalled()
  expect(applied()).toBeUndefined()
})
it('错误定位按实际binding账户与组/广告local_id，按需读一次观察且聚焦真实字段', async () => {
  const original: IdentityBinding = {
    account_id: account,
    page_id: page,
    groups: [
      {
        adset_local_id: group,
        pixel_id: '22',
        conversion_event: 'OLD_EVENT',
        application_id: null,
        object_store_url: null,
      },
    ],
    ad_overrides: [{ ad_local_id: ad, page_id: page }],
  }
  await start({ modelValue: [original], accountIds: [id(55), account] })
  const exposed = wrapper!.vm as unknown as {
    focusBinding: (index: number, path: string[]) => Promise<boolean>
  }
  expect(await exposed.focusBinding(0, ['groups', '0', 'conversion_event'])).toBe(true)
  expect(
    document.activeElement?.closest('.el-form-item')?.querySelector('label')?.textContent?.trim(),
  ).toBe(`优化事件 ${group}（待能力核验）`)
  expect(accountIdentitiesApi.get).not.toHaveBeenCalled()
  expect(await exposed.focusBinding(0, ['page_id'])).toBe(true)
  expect(accountIdentitiesApi.get).toHaveBeenCalledTimes(1)
  expect(accountIdentitiesApi.get).toHaveBeenCalledWith(account, expect.any(AbortSignal))
  expect(await exposed.focusBinding(0, ['ad_overrides', '0', 'page_id'])).toBe(true)
  expect(
    document.activeElement?.closest('[data-identity-ad]')?.getAttribute('data-identity-ad'),
  ).toBe(ad)
  expect(applied()).toBeUndefined()
  expect(wrapper!.props('modelValue')).toEqual([original])
})
it('未知身份路径或失效local_id不能打开错误账户或猜字段，原绑定保留', async () => {
  await start({
    modelValue: [{ account_id: account, page_id: page, groups: [], ad_overrides: [] }],
  })
  const exposed = wrapper!.vm as unknown as {
    focusBinding: (index: number, path: string[]) => Promise<boolean>
  }
  expect(await exposed.focusBinding(0, ['token'])).toBe(false)
  expect(await exposed.focusBinding(0, ['groups', '99', 'pixel_id'])).toBe(false)
  expect(await exposed.focusBinding(9, ['page_id'])).toBe(false)
  expect(wrapper!.emitted('editing')).toBeUndefined()
  expect(accountIdentitiesApi.get).not.toHaveBeenCalled()
})
it('500账户/万组/万广告均分页，末页完整且没有截断原model', async () => {
  const campaigns: CampaignConfig[] = [
    {
      local_id: id(100),
      copies: 1,
      objective: 'OUTCOME_SALES',
      adsets: Array.from({ length: 10000 }, (_, i) => ({
        local_id: id(20000 + i),
        copies: 1,
        ads: [{ local_id: id(40000 + i), copies: 1 }],
      })),
    },
  ]
  await start({ accountIds: Array.from({ length: 500 }, (_, i) => id(i + 1)), campaigns })
  expect(
    document.querySelectorAll('.identity-bindings > .el-table .el-table__body tr'),
  ).toHaveLength(20)
  expect(accountIdentitiesApi.get).not.toHaveBeenCalled()
  await open()
  const pages = wrapper!.findAllComponents({ name: 'ElPagination' })
  pages[1].vm.$emit('update:current-page', 500)
  await flushPromises()
  expect(document.body.textContent).toContain(id(29999))
  expect(document.body.textContent).not.toContain(id(20000))
  wrapper!.findComponent({ name: 'ElTabs' }).vm.$emit('update:modelValue', 'ads')
  await flushPromises()
  wrapper!.findAllComponents({ name: 'ElPagination' })[2].vm.$emit('update:current-page', 500)
  await flushPromises()
  expect(document.body.textContent).toContain(id(49999))
  expect(wrapper!.props('campaigns')).toEqual(campaigns)
  expect(applied()).toBeUndefined()
})
