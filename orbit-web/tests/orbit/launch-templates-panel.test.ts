import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TemplatesPanel from '@/views/orbit/launch/TemplatesPanel.vue'
import { templateApi, type LaunchTemplate } from '@/api/orbit/templates'
import { launchApi, type LaunchCapabilities, type LaunchPlan } from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
import { newDraft } from '@/api/orbit/launch-form'
import { readTemplateIntent } from '@/api/orbit/launch-recovery'
import CampaignTree from '@/views/orbit/launch/CampaignTree.vue'
import PlanMetricProfileField from '@/views/orbit/launch/PlanMetricProfileField.vue'
const caps: LaunchCapabilities = {
  actions: ['create', 'edit', 'share', 'archive'],
  data_role: 'SUPER_ADMIN',
  csrf_token: 'csrf-only-memory',
  actor_user_id: 'owner',
  actor_team_id: 'team',
  actor_label: '当前本人',
}
const fixture = (): LaunchTemplate => ({
  id: 'template',
  revision: 1,
  name: '模板甲',
  description: '',
  visibility: 'PRIVATE',
  recipient_user_ids: [],
  campaigns: [{ local_id: 'campaign', copies: 1, adsets: [] }],
  ownership: { owner_user_id: 'owner', owner_team_id: 'team' },
  state: 'ACTIVE',
})
let wrapper: VueWrapper
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(templateApi, 'capabilities').mockResolvedValue(caps)
  vi.spyOn(templateApi, 'list').mockResolvedValue({
    items: [fixture()],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  vi.spyOn(templateApi, 'get').mockResolvedValue(fixture())
  vi.spyOn(templateApi, 'recipients').mockResolvedValue({
    items: [{ id: 'owner', name: '当前本人', team_id: 'team', team_name: '团队' }],
    next_cursor: null,
    scope_version: 1,
    owner_team_id: 'team',
    csrf_token: 'recipient-csrf',
  })
  vi.spyOn(launchApi, 'owners').mockResolvedValue({
    items: [{ id: 'owner', name: '当前本人', team_id: 'team', team_name: '团队' }],
    next_cursor: null,
    scope_version: 1,
  })
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  sessionStorage.clear()
})
async function start() {
  wrapper = mount(TemplatesPanel, {
    attachTo: document.body,
    props: { active: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
async function click(text: string) {
  const button = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === text,
  )
  expect(button, text).toBeTruthy()
  button!.click()
  await flushPromises()
}
async function fill(labelText: string, value: string) {
  const label = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (label) => label.textContent?.trim() === labelText,
  )!
  const input = document.getElementById(label.htmlFor) as HTMLInputElement
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
it('模板共用原广告组指标字段，无monitor.read仍能保存手填UUID并保留其它配置', async () => {
  const original = fixture()
  original.campaigns[0].adsets = [{ local_id: 'group', copies: 1, ads: [] }]
  vi.mocked(templateApi.get).mockResolvedValue(original)
  const save = vi.spyOn(templateApi, 'save').mockResolvedValue(original)
  await start()
  await click('编辑')
  await wrapper.findComponent(CampaignTree).vm.focusField('group', ['metric_profile_id'])
  const field = wrapper.findComponent(PlanMetricProfileField)
  expect(field.props('canRead')).toBe(false)
  const uuid = '00000000-0000-4000-8000-000000000099'
  await field.get('input').setValue(uuid)
  await click('保存模板')
  expect(save.mock.calls[0][0].campaigns[0].adsets[0].metric_profile_id).toBe(uuid)
  expect(save.mock.calls[0][0].campaigns[0].local_id).toBe('campaign')
})
it('模板指标二级页阻止父保存/关闭/刷新，不改变既有unknown恢复', async () => {
  const save = vi.spyOn(templateApi, 'save')
  await start()
  await click('编辑')
  wrapper.findComponent(CampaignTree).vm.$emit('browsing', true)
  await flushPromises()
  for (const text of ['保存模板', '关闭', '重新读取服务器版本']) {
    const button = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent?.trim() === text,
    )!
    expect(button.disabled).toBe(true)
    button.click()
  }
  await flushPromises()
  expect(save).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('编辑配置模板')
})
it('从已有配置实际编辑保存模板，正文与NFC保留且不夹带账户或身份', async () => {
  const save = vi.spyOn(templateApi, 'save').mockResolvedValue(fixture())
  await start()
  await click('编辑')
  await fill('模板名称（1—80码点）', 'e\u0301'.repeat(80))
  await fill('说明（最多500码点，允许LF）', '甲\n乙')
  await click('保存模板')
  expect(save.mock.calls[0][0].name).toBe('é'.repeat(80))
  expect(save.mock.calls[0][0].description).toBe('甲\n乙')
  expect(save.mock.calls[0][0]).not.toHaveProperty('account_ids')
  expect(save.mock.calls[0][0]).not.toHaveProperty('identity_bindings')
})
it('可见的其他所有者模板只有查看使用权，SUPER范围不出现维护按钮', async () => {
  vi.mocked(templateApi.list).mockResolvedValue({
    items: [
      fixture() as LaunchTemplate & { ownership: { owner_user_id: string; owner_team_id: string } },
    ].map((row) => ({ ...row, ownership: { owner_user_id: 'peer', owner_team_id: 'team' } })),
    next_cursor: null,
    data_as_of: 'now',
    scope_version: 1,
  })
  await start()
  expect(
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent?.trim() === '编辑',
    ),
  ).toBe(false)
  expect(
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent?.trim() === '分享',
    ),
  ).toBe(false)
  expect(
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent?.trim() === '归档',
    ),
  ).toBe(false)
})
it('归档原因必填，按原资源版本调用真实动作API', async () => {
  const archive = vi
    .spyOn(templateApi, 'archive')
    .mockResolvedValue({ ...fixture(), state: 'ARCHIVED', revision: 2 })
  await start()
  await click('归档')
  await click('确认归档')
  expect(archive).not.toHaveBeenCalled()
  await fill('操作原因（1—1000码点）', '停止使用\n保留历史')
  await click('确认归档')
  expect(archive.mock.calls[0][0].revision).toBe(1)
  expect(archive.mock.calls[0][1]).toBe('停止使用\n保留历史')
})
it('模板应用使用已验证本人默认负责人，完成后发出新草稿而非执行成功', async () => {
  const plan: LaunchPlan = {
    ...newDraft({ owner_user_id: 'owner', owner_team_id: 'team' }),
    id: 'new-plan',
    revision: 1,
    state: 'DRAFT',
    created_at: 'now',
    updated_at: 'now',
  }
  const apply = vi.spyOn(templateApi, 'apply').mockResolvedValue(plan)
  await start()
  await click('加载为新草稿')
  await fill('操作原因（1—1000码点）', '加载配置')
  await click('确认创建草稿')
  expect(apply.mock.calls[0][1]).toEqual({ owner_user_id: 'owner', owner_team_id: 'team' })
  expect(wrapper.emitted('applied')?.[0]).toEqual([plan])
})
it('未知结果刷新后从无凭证缓存恢复同一次模板保存', async () => {
  const save = vi
    .spyOn(templateApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '结果未确认'))
    .mockResolvedValueOnce(fixture())
  await start()
  await click('编辑')
  await fill('模板名称（1—80码点）', '缓存中待确认模板')
  await click('保存模板')
  const recovered = readTemplateIntent('owner')!
  expect(recovered.key).toBe(save.mock.calls[0][2])
  expect(sessionStorage.getItem('orbit.launch.template-intent.v1.owner')).not.toContain(
    caps.csrf_token,
  )
  wrapper.unmount()
  document.body.innerHTML = ''
  await start()
  await click('恢复并重试待确认操作')
  expect(save.mock.calls[1][2]).toBe(recovered.key)
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
  expect(readTemplateIntent('owner')).toBeNull()
})
it('按钮读取详情失败时显示错误，不打开假成功弹窗', async () => {
  vi.mocked(templateApi.get).mockRejectedValue(
    new ReferenceApiError(403, 'PERMISSION_DENIED', '当前无权读取模板'),
  )
  await start()
  await click('分享')
  expect(document.body.textContent).toContain('当前无权读取模板')
  // Element Plus会保留隐藏overlay骨架；关键是读取失败不得打开任何可见业务弹窗。
  expect(
    [...document.querySelectorAll('[role="dialog"]')].every((dialog) =>
      Boolean(dialog.closest('[style*="display: none"]')),
    ),
  ).toBe(true)
})

it('真实ElSelect在异步候选结束后选择成员并提交中文原因，原生输入与业务模型一致', async () => {
  let resolveCandidates!: (value: Awaited<ReturnType<typeof templateApi.recipients>>) => void
  vi.mocked(templateApi.recipients).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveCandidates = resolve
      }),
  )
  const share = vi.spyOn(templateApi, 'share').mockResolvedValue({
    ...fixture(),
    visibility: 'TEAM',
    recipient_user_ids: ['owner'],
    revision: 2,
  })
  await start()
  // 先保存含textarea的编辑器，保留隐藏DOM后再走真实失败的分享路径。
  vi.spyOn(templateApi, 'save').mockResolvedValue(fixture())
  await click('编辑')
  await fill('说明（最多500码点，允许LF）', '真实配置模板\n保留预算及三层结构')
  await click('保存模板')
  await click('分享')
  const state = () => document.querySelector('[aria-label="操作候选读取状态"]')!
  expect(state().getAttribute('aria-busy')).toBe('true')
  resolveCandidates({
    items: [{ id: 'owner', name: '当前本人', team_id: 'team', team_name: '团队' }],
    next_cursor: null,
    scope_version: 1,
    owner_team_id: 'team',
    csrf_token: 'actual-recipient-csrf',
  })
  await flushPromises()
  expect(state().getAttribute('aria-busy')).toBe('false')
  const dialog = [...document.querySelectorAll('[role="dialog"]')].find((item) =>
    item.textContent?.includes('确认分享'),
  )!
  const selector = dialog.querySelector('.el-select__wrapper') as HTMLElement
  selector.click()
  await flushPromises()
  const option = [...document.querySelectorAll('.el-select-dropdown__item')].find(
    (item) => item.textContent?.trim() === '当前本人',
  ) as HTMLElement
  expect(option).toBeTruthy()
  option.click()
  await flushPromises()
  const input = dialog.querySelector('textarea')!
  input.value = '浏览器确认真实共享'
  input.dispatchEvent(
    new InputEvent('input', { bubbles: true, inputType: 'insertText', data: '浏览器确认真实共享' }),
  )
  await flushPromises()
  expect(input.value).toBe('浏览器确认真实共享')
  expect(dialog.querySelector('[aria-label="操作原因输入状态"]')?.textContent).toBe(
    '已输入 9/1000 码点',
  )
  input.dispatchEvent(new Event('change', { bubbles: true }))
  input.dispatchEvent(new FocusEvent('blur'))
  await flushPromises()
  await click('确认分享')
  expect(share).toHaveBeenCalledOnce()
  expect(share.mock.calls[0][1]).toEqual(['owner'])
  expect(share.mock.calls[0][2]).toBe('浏览器确认真实共享')
  expect(share.mock.calls[0][3]).toBe('actual-recipient-csrf')
})
