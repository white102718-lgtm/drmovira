import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Channels from '@/views/orbit/channels/index.vue'
import { channelApi, type Channel } from '@/api/orbit/channels'
import { ReferenceApiError, referenceApi } from '@/api/orbit/references'

const channel: Channel = {
  id: 'channel',
  code: 'CODE',
  name: '原名称',
  ownership: { owner_team_id: 'team', data_owner_user_ids: ['owner'] },
  type: 'APP',
  media: 'META',
  url: 'https://example.com/',
  status: 'ENABLED',
  revision: 1,
  created_at: '2026-11-08T00:00:00Z',
  updated_at: '2026-11-08T00:00:00Z',
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.spyOn(channelApi, 'capabilities').mockResolvedValue({
    actions: ['create', 'edit', 'assign', 'archive'],
    data_role: 'SUPER_ADMIN',
    csrf_token: 'csrf',
  })
  vi.spyOn(channelApi, 'list').mockResolvedValue({
    items: [channel],
    next_cursor: null,
    data_as_of: channel.updated_at,
    scope_version: 1,
  })
  vi.spyOn(channelApi, 'get').mockResolvedValue(channel)
  vi.spyOn(channelApi, 'labels').mockResolvedValue({
    items: [
      {
        id: 'channel',
        team_name: '团队',
        owners: [{ id: 'owner', name: '本人' }],
      },
    ],
  })
  vi.spyOn(channelApi, 'owners').mockResolvedValue({
    items: [{ id: 'owner', display_name: '本人', team_id: 'team', team_name: '团队' }],
    next_after: null,
  })
  vi.spyOn(referenceApi, 'list').mockRejectedValue(new Error('已移除的字典不应被请求'))
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function click(text: string) {
  const button = [...document.querySelectorAll('button')].find(
    (element) => element.textContent?.trim() === text,
  )
  expect(button).toBeTruthy()
  button!.click()
  await flushPromises()
}
function input(labelText: string) {
  const label = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (element) => element.textContent?.trim() === labelText,
  )!
  return document.getElementById(label.htmlFor) as HTMLInputElement
}
async function fillName(value: string) {
  input('渠道名称').value = value
  input('渠道名称').dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function openEdit() {
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('编辑')
}

it('100个emoji完整保存，101码点拒绝而不是按UTF16截断', async () => {
  const save = vi.spyOn(channelApi, 'save').mockResolvedValue({ ...channel, revision: 2 })
  await openEdit()
  await fillName('😀'.repeat(101))
  await click('保存')
  expect(save).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('渠道名称最多100个字符')
  await fillName('😀'.repeat(100))
  expect(input('渠道名称').value).toBe('😀'.repeat(100))
  expect(input('渠道名称').getAttribute('maxlength')).toBeNull()
  await click('保存')
  expect(save.mock.calls[0][0].name).toBe('😀'.repeat(100))
})

it('未知结果冻结字段，并禁止取消与Escape丢弃原键', async () => {
  const save = vi
    .spyOn(channelApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '未知结果'))
    .mockResolvedValueOnce({ ...channel, revision: 2 })
  await openEdit()
  await click('保存')
  expect(input('渠道名称').disabled).toBe(true)
  const cancel = [...document.querySelectorAll('button')].find(
    (element) => element.textContent?.trim() === '取消',
  )!
  expect(cancel.disabled).toBe(true)
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  await flushPromises()
  expect(document.body.textContent).toContain('上次提交结果未知')
  await click('重试本次保存')
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
})

it('详情使用当前渠道且不再请求产品总代或历史绑定', async () => {
  vi.mocked(channelApi.get).mockResolvedValue({ ...channel, name: '最新渠道名称' })
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('详情')
  expect(channelApi.get).toHaveBeenCalledWith('channel')
  expect(document.body.textContent).toContain('最新渠道名称')
  expect(document.body.textContent).not.toMatch(/产品|总代|历史马甲包/)
  expect(referenceApi.list).not.toHaveBeenCalled()
})

it('渠道无产品总代即可保存，归属和地址仍完整提交', async () => {
  const save = vi.spyOn(channelApi, 'save').mockResolvedValue({ ...channel, revision: 2 })
  await openEdit()
  await click('保存')
  expect(save.mock.calls[0][0]).not.toHaveProperty('product_id')
  expect(save.mock.calls[0][0]).not.toHaveProperty('agent_id')
  expect(save.mock.calls[0][0]).toMatchObject({ ownership: channel.ownership, url: channel.url })
  expect(referenceApi.list).not.toHaveBeenCalled()
})

it('409重新读取后用当前版本及新键，不重放旧CAS', async () => {
  const save = vi
    .spyOn(channelApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(409, 'REVISION_CONFLICT', '旧版本'))
    .mockResolvedValueOnce({ ...channel, revision: 3 })
  await openEdit()
  await click('保存')
  expect(input('渠道名称').disabled).toBe(true)
  vi.mocked(channelApi.get).mockResolvedValue({ ...channel, revision: 2 })
  await click('重新读取当前渠道')
  await fillName('基于新版本')
  await click('保存')
  expect(save.mock.calls[0][3]!.revision).toBe(1)
  expect(save.mock.calls[1][3]!.revision).toBe(2)
  expect(save.mock.calls[0][2]).not.toBe(save.mock.calls[1][2])
})

it.each(['分配', '停用'] as const)('%s未知结果同样禁止关闭并保留原操作键', async (label) => {
  const operation = label === '分配' ? 'assign' : 'archive'
  const action = vi
    .spyOn(channelApi, operation)
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '未知结果'))
    .mockResolvedValueOnce({ ...channel, revision: 2 })
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click(label)
  const reason = document.querySelector('textarea')!
  reason.value = '恢复原操作'
  reason.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  await click('确认')
  expect(reason.disabled).toBe(true)
  expect(
    [...document.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === '取消',
    )!.disabled,
  ).toBe(true)
  await click('重试本次操作')
  expect(action.mock.calls[0]).toEqual(action.mock.calls[1])
})

it('冲突后当前对象读取失败仍保持冻结，不放行旧版本', async () => {
  vi.spyOn(channelApi, 'save').mockRejectedValueOnce(
    new ReferenceApiError(409, 'REVISION_CONFLICT', '旧版本'),
  )
  await openEdit()
  await click('保存')
  vi.mocked(channelApi.get).mockRejectedValueOnce(
    new ReferenceApiError(403, 'PERMISSION_DENIED', '权限已撤销'),
  )
  await click('重新读取当前渠道')
  expect(input('渠道名称').disabled).toBe(true)
  expect(document.body.textContent).toContain('重新读取失败')
})

function ownerPages(total: number) {
  const owners = Array.from({ length: total }, (_, index) => ({
    id: `bulk-${index}`,
    display_name: `批量成员${index}`,
    team_id: 'team',
    team_name: '团队',
  }))
  vi.mocked(channelApi.owners).mockImplementation(async (after = '') => {
    const start = after ? Number(after) : 0
    return {
      items: owners.slice(start, start + 200),
      next_after: start + 200 < total ? String(start + 200) : null,
    }
  })
}

it('三页加载后只合并当前已加载目标，不静默选择下一页，500项折叠回显', async () => {
  ownerPages(500)
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('新增渠道')
  const summary = () => document.querySelector('[data-testid="create-owner-summary"]')!.textContent
  expect(summary()).toContain('已加载当前团队 200 人；已选择 0 / 500 人')
  await click('选择当前团队已加载用户')
  expect(summary()).toContain('已选择 200 / 500 人')
  await click('加载更多可分配用户')
  expect(summary()).toContain('已加载当前团队 400 人；已选择 200 / 500 人')
  await click('选择当前团队已加载用户')
  await click('加载更多可分配用户')
  expect(summary()).toContain('已加载当前团队 500 人；已选择 400 / 500 人')
  await click('选择当前团队已加载用户')
  expect(summary()).toContain('已选择 500 / 500 人')
  expect(
    input('分配用户（1—500名）')
      .closest('.el-select')!
      .querySelectorAll('.el-select__selection .el-tag').length,
  ).toBeLessThanOrEqual(4)
})

it('批选合并超过500时明确拒绝且保持原400集合，不静默截断', async () => {
  ownerPages(501)
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('新增渠道')
  await click('选择当前团队已加载用户')
  await click('加载更多可分配用户')
  await click('选择当前团队已加载用户')
  await click('加载更多可分配用户')
  await click('选择当前团队已加载用户')
  expect(document.body.textContent).toContain('本次没有截断或改变选择')
  expect(document.querySelector('[data-testid="create-owner-summary"]')!.textContent).toContain(
    '已选择 400 / 500 人',
  )
})

it('末页null游标不能掩盖重新打开分配时尚未返回的首屏候选', async () => {
  ownerPages(500)
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('新增渠道')
  await click('加载更多可分配用户')
  await click('加载更多可分配用户')
  await click('取消')
  let resolve!: (value: Awaited<ReturnType<typeof channelApi.owners>>) => void
  const pending = new Promise<Awaited<ReturnType<typeof channelApi.owners>>>((done) => {
    resolve = done
  })
  vi.mocked(channelApi.owners).mockImplementationOnce(() => pending)
  vi.mocked(channelApi.get).mockResolvedValue({
    ...channel,
    ownership: {
      owner_team_id: 'team',
      data_owner_user_ids: Array.from({ length: 500 }, (_, index) => `bulk-${index}`),
    },
  })
  await click('分配')
  const summary = () => document.querySelector('[data-testid="assignment-owner-summary"]')!
  expect(summary().getAttribute('aria-busy')).toBe('true')
  expect(summary().textContent).toContain('已加载当前团队 0 人；已选择 500 / 500 人')
  resolve({
    items: Array.from({ length: 200 }, (_, index) => ({
      id: `bulk-${index}`,
      display_name: `批量成员${index}`,
      team_id: 'team',
      team_name: '团队',
    })),
    next_after: '200',
  })
  await flushPromises()
  expect(summary().getAttribute('aria-busy')).toBe('false')
  expect(summary().textContent).toContain('已加载当前团队 200 人；已选择 500 / 500 人')
  await click('加载更多用户')
  await click('加载更多用户')
  expect(summary().textContent).toContain('已加载当前团队 500 人；已选择 500 / 500 人')
})

it('初次候选失败明确显示并可重试，不把失败当合法末页', async () => {
  wrapper = mount(Channels, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  vi.mocked(channelApi.owners).mockRejectedValueOnce(new Error('候选读取失败'))
  await click('分配')
  expect(document.body.textContent).toContain('候选读取失败')
  expect(
    document.querySelector('[data-testid="assignment-owner-summary"]')!.getAttribute('aria-busy'),
  ).toBe('false')
  await click('重试候选读取')
  expect(document.body.textContent).not.toContain('候选读取失败')
  expect(document.querySelector('[data-testid="assignment-owner-summary"]')!.textContent).toContain(
    '已加载当前团队 1 人',
  )
})
