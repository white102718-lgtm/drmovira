import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton, ElSelect, ElCheckbox } from 'element-plus'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import Panel from '@/views/orbit/accounts/components/MetaConnectionsPanel.vue'
import { metaConnectionApi } from '@/api/orbit/meta-connections'
import { accountApi } from '@/api/orbit/accounts'
import { referenceApi, ReferenceApiError } from '@/api/orbit/references'
vi.mock('@/store/modules/user', () => ({ default: () => ({ permissions: [] }) }))
const id = '00000000-0000-4000-8000-000000000001'
const owner = '00000000-0000-4000-8000-000000000002'
const team = '00000000-0000-4000-8000-000000000003'
const vendor = '00000000-0000-4000-8000-000000000004'
const connection = {
  id,
  kind: 'LOGIN' as const,
  status: 'ACTIVE' as const,
  revision: 1,
  principal_id: '123',
  expires_at: null,
  data_access_expires_at: null,
  updated_at: '2026-11-10T00:00:00Z',
}
const authorization = {
  authorize_url: 'https://www.facebook.com/v24.0/dialog/oauth?state=opaque',
  expires_at: '2099-11-10T00:00:00Z',
}
let w: VueWrapper
beforeEach(() => {
  vi.spyOn(metaConnectionApi, 'capabilities').mockResolvedValue({
    csrf_token: 'csrf',
    configured: true,
  })
  vi.spyOn(metaConnectionApi, 'list').mockResolvedValue({ items: [connection] })
  vi.spyOn(metaConnectionApi, 'authorize').mockResolvedValue(authorization)
  vi.spyOn(metaConnectionApi, 'navigate').mockImplementation(() => {})
  vi.spyOn(metaConnectionApi, 'disconnect').mockResolvedValue({
    id,
    status: 'DISCONNECTED',
    revision: 2,
  })
  vi.spyOn(metaConnectionApi, 'accounts').mockResolvedValue({
    items: [{ external_id: '123', name: '账户 A', currency: 'USD', timezone: 'UTC' }],
    next_cursor: null,
  })
  vi.spyOn(accountApi, 'capabilities').mockResolvedValue({
    csrf_token: 'import-csrf',
    default_owner_user_id: owner,
    default_owner_team_id: team,
  })
  vi.spyOn(accountApi, 'owners').mockResolvedValue({
    items: [{ id: owner, name: '投手 A', team_id: team, team_name: '团队 A' }],
    next_cursor: null,
  })
  vi.spyOn(referenceApi, 'list').mockResolvedValue({
    items: [
      {
        value: {
          id: vendor,
          kind: 'VENDOR',
          name: '户商 A',
          availability: 'AVAILABLE',
          source_key: 'a',
          owner_team_id: team,
          data_owner_user_ids: [owner],
        },
        revision: 1,
        catalog_revision: 1,
        updated_at: '2026-11-10T00:00:00Z',
      },
    ],
    next_cursor: null,
    catalog_revision: 1,
    scope_version: 1,
  })
})
afterEach(() => {
  w?.unmount()
  vi.restoreAllMocks()
})
async function start() {
  w = mount(Panel, {
    props: { active: true, contextKey: 'actor1' },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
function button(label: string) {
  const value = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(value, label).toBeTruthy()
  return value!
}
async function click(label: string) {
  await button(label).trigger('click')
  await flushPromises()
}
it('未配置明确阻断，保留状态与有效期字段', async () => {
  vi.mocked(metaConnectionApi.capabilities).mockResolvedValue({
    csrf_token: 'csrf',
    configured: false,
  })
  await start()
  expect(w.text()).toContain('Meta 平台应用尚未配置完整')
  expect(button('连接 Meta').attributes('disabled')).toBeDefined()
  for (const name of ['数据访问有效期', '授权有效期', 'Meta 主体 ID', '连接 ID'])
    expect(w.text()).toContain(name)
  expect(metaConnectionApi.authorize).not.toHaveBeenCalled()
})
it('授权不自动跳转，用户明确继续才前往Meta', async () => {
  await start()
  await click('连接 Meta')
  expect(metaConnectionApi.navigate).not.toHaveBeenCalled()
  await click('继续前往 Meta')
  expect(metaConnectionApi.navigate).toHaveBeenCalledWith(authorization)
})
it('不确定授权结果只重试原幂等键', async () => {
  vi.mocked(metaConnectionApi.authorize).mockRejectedValueOnce(
    new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', 'offline'),
  )
  await start()
  await click('连接 Meta')
  expect(w.text()).toContain('提交结果尚未确认')
  expect(button('连接 Meta').attributes('disabled')).toBeDefined()
  const first = vi.mocked(metaConnectionApi.authorize).mock.calls[0]
  await click('重试原请求')
  expect(vi.mocked(metaConnectionApi.authorize).mock.calls[1]).toEqual(first)
})
it('取消断开不提交，确认包含原因和原版本', async () => {
  await start()
  await click('断开')
  await click('取消')
  expect(metaConnectionApi.disconnect).not.toHaveBeenCalled()
  await click('断开')
  await w.get('textarea[aria-label="断开原因"]').setValue('停止读取')
  await click('确认断开')
  expect(metaConnectionApi.disconnect).toHaveBeenCalledWith(
    id,
    1,
    '停止读取',
    'csrf',
    expect.stringMatching(/^meta-disconnect-/),
  )
})
it('导入额外权限拒绝时不枚举账户', async () => {
  vi.mocked(accountApi.capabilities).mockRejectedValue(
    new ReferenceApiError(403, 'PERMISSION_DENIED', 'denied'),
  )
  await start()
  await click('选择账户')
  expect(metaConnectionApi.accounts).not.toHaveBeenCalled()
  expect(w.text()).toContain('没有此操作权限')
})
it('选择账户复用投手团队户商并返回原批次结果', async () => {
  const batch = {
    id,
    revision: 1,
    vendor_id: vendor,
    state: 'QUEUED' as const,
    total: 1,
    success_count: 0,
    failed_count: 0,
    duplicate_count: 0,
    rows: [],
    next_cursor: null,
  }
  vi.spyOn(metaConnectionApi, 'select').mockResolvedValue(batch)
  await start()
  await click('选择账户')
  let selects = w.findAllComponents(ElSelect)
  selects[0]!.vm.$emit('update:modelValue', owner)
  selects[0]!.vm.$emit('change', owner)
  await flushPromises()
  selects = w.findAllComponents(ElSelect)
  selects[1]!.vm.$emit('update:modelValue', vendor)
  await flushPromises()
  w.findComponent(ElCheckbox).vm.$emit('change', true)
  await flushPromises()
  await click('确认接入所选账户')
  expect(metaConnectionApi.select).toHaveBeenCalledWith(
    id,
    {
      account_ids: ['123'],
      operator_user_id: owner,
      owner_team_id: team,
      vendor_id: vendor,
      channel_id: null,
    },
    'csrf',
    expect.stringMatching(/^meta-accounts-/),
  )
  expect(w.emitted('accepted')?.[0]).toEqual([batch])
})
it('身份变化清除未确认动作与授权URL', async () => {
  vi.mocked(metaConnectionApi.authorize).mockRejectedValueOnce(
    new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', 'offline'),
  )
  await start()
  await click('连接 Meta')
  await w.setProps({ contextKey: 'actor2' })
  await flushPromises()
  expect(w.text()).not.toContain('重试原请求')
  expect(w.text()).not.toContain('继续前往 Meta')
})

it('BM重新验证只引导系统配置，不调用个人登录授权', async () => {
  vi.mocked(metaConnectionApi.list).mockResolvedValue({
    items: [{ ...connection, kind: 'BM', status: 'REAUTH_REQUIRED' }],
  })
  await start()
  await click('重新验证')
  expect(w.text()).toContain('对应 Meta/BM 配置行')
  expect(metaConnectionApi.authorize).not.toHaveBeenCalled()
})
it('新授权必须明确选择应用，重新授权沿用连接来源而不传其他应用', async () => {
  vi.mocked(metaConnectionApi.capabilities).mockResolvedValue({
    csrf_token: 'csrf',
    configured: true,
    applications: [
      { id: owner, name: '应用A', app_id: '111', revision: 1 },
      { id: team, name: '应用B', app_id: '222', revision: 1 },
    ],
  })
  await start()
  const connect = w.findAllComponents(ElButton).find((b) => b.text() === '连接 Meta')!
  expect(connect.props('disabled')).toBe(true)
  w.findComponent(ElSelect).vm.$emit('update:modelValue', team)
  await flushPromises()
  await click('连接 Meta')
  expect(metaConnectionApi.authorize).toHaveBeenLastCalledWith(
    'csrf',
    expect.any(String),
    undefined,
    team,
  )
  await click('重新授权')
  expect(metaConnectionApi.authorize).toHaveBeenLastCalledWith(
    'csrf',
    expect.any(String),
    id,
    undefined,
  )
})

it('业务资料不完整时指出个人中心补全资料而非反复重试', async () => {
  vi.mocked(metaConnectionApi.capabilities).mockRejectedValue(
    Object.assign(new Error('internal detail'), { code: 'DIRECTORY_MAPPING_REQUIRED' }),
  )
  await start()
  expect(w.text()).toContain('个人中心')
  expect(w.text()).toContain('邮箱')
  expect(w.text()).not.toContain('internal detail')
})
