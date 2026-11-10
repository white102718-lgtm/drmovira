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
it('点击连接立即前往Meta而不再二次确认', async () => {
  await start()
  await click('连接 Meta')
  expect(w.text()).not.toContain('继续前往 Meta')
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
it('已有连接只展示状态，不显示手工选择或静默启动导入', async () => {
  await start()
  expect(w.text()).not.toContain('选择账户')
  expect(metaConnectionApi.accounts).not.toHaveBeenCalled()
  expect(accountApi.owners).not.toHaveBeenCalled()
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

it('显示服务端真实自动接入进度，按批次打开逐项结果', async () => {
  const batch = {
    id,
    state: 'RUNNING' as const,
    total: 12,
    success_count: 4,
    failed_count: 1,
    duplicate_count: 0,
  }
  vi.mocked(metaConnectionApi.list).mockResolvedValue({
    items: [
      {
        ...connection,
        auto_import: {
          ...batch,
          state: 'IMPORTING',
          error_code: null,
          batches: [batch],
        },
      },
    ],
  })
  const detail = { ...batch, revision: 1, vendor_id: null, rows: [], next_cursor: null }
  vi.spyOn(accountApi, 'getImport').mockResolvedValue(detail)
  await start()
  expect(w.text()).toContain('接入中')
  expect(w.text()).toContain('成功 4')
  expect(w.text()).toContain('失败 1')
  await click('查看逐项结果')
  expect(w.emitted('accepted')?.[0]).toEqual([detail])
})

it('自动接入处理中继续读取真实状态，关闭面板停止轮询', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    vi.mocked(metaConnectionApi.list).mockResolvedValue({
      items: [
        {
          ...connection,
          auto_import: {
            id,
            state: 'DISCOVERING',
            error_code: null,
            total: 0,
            success_count: 0,
            failed_count: 0,
            duplicate_count: 0,
            batches: [],
          },
        },
      ],
    })
    await start()
    expect(w.text()).toContain('读取授权账户中')
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(metaConnectionApi.list).toHaveBeenCalledTimes(2)
    await w.setProps({ active: false })
    await vi.advanceTimersByTimeAsync(6000)
    expect(metaConnectionApi.list).toHaveBeenCalledTimes(2)
  } finally {
    vi.useRealTimers()
  }
})

it('枚举失败但已接收批次仍运行时继续读取进度，不误报全量成功', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    vi.mocked(metaConnectionApi.list).mockResolvedValue({
      items: [
        {
          ...connection,
          auto_import: {
            id,
            state: 'FAILED',
            error_code: 'META_DISCOVERY_FAILED',
            total: 2,
            success_count: 0,
            failed_count: 0,
            duplicate_count: 0,
            batches: [
              {
                id,
                state: 'QUEUED',
                total: 2,
                success_count: 0,
                failed_count: 0,
                duplicate_count: 0,
              },
            ],
          },
        },
      ],
    })
    await start()
    expect(w.text()).toContain('自动接入：失败')
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(metaConnectionApi.list).toHaveBeenCalledTimes(2)
  } finally {
    vi.useRealTimers()
  }
})

it('后台进度请求未返回时保留应用选择框且不禁用授权', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    vi.mocked(metaConnectionApi.capabilities).mockResolvedValue({
      csrf_token: 'csrf',
      configured: true,
      applications: [{ id, name: '应用 A', app_id: '123' }],
    })
    vi.mocked(metaConnectionApi.list).mockResolvedValue({
      items: [
        {
          ...connection,
          auto_import: {
            id,
            state: 'QUEUED',
            error_code: null,
            total: 0,
            success_count: 0,
            failed_count: 0,
            duplicate_count: 0,
            batches: [],
          },
        },
      ],
    })
    await start()
    const select = w.findComponent(ElSelect)
    select.vm.$emit('update:modelValue', id)
    await flushPromises()
    const element = select.element
    vi.mocked(metaConnectionApi.capabilities).mockImplementationOnce(() => new Promise(() => {}))
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(w.findComponent(ElSelect).element).toBe(element)
    expect(w.findComponent(ElSelect).props('disabled')).toBe(false)
    expect(w.findComponent(ElSelect).props('modelValue')).toBe(id)
  } finally {
    vi.useRealTimers()
  }
})
