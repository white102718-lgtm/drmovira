import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton, ElMessageBox } from 'element-plus'
import { it, expect, vi, beforeEach, afterEach } from 'vitest'
import ConfigurationPage from '@/views/orbit/system/configuration/index.vue'
import * as configuration from '@/api/orbit/configuration'
import { metaConnectionApi } from '@/api/orbit/meta-connections'
import { ReferenceApiError } from '@/api/orbit/references'
vi.mock('@/store/modules/user', () => ({ default: () => ({ id: 1, permissions: ['*:*:*'] }) }))
const id = '00000000-0000-4000-8000-000000000001'
let w: VueWrapper
beforeEach(() => {
  vi.spyOn(configuration, 'getConfigurationMetadata').mockResolvedValue({
    sections: [{ key: 'META_BM', label: 'Meta/BM', fields: [] }],
    encryptionReady: true,
  })
  vi.spyOn(configuration, 'listConfigurations').mockResolvedValue([
    {
      id,
      section: 'META_BM',
      name: 'BM读取配置',
      enabled: true,
      revision: 3,
      settings: {},
      secrets: { accessToken: { configured: true, hint: '已配置' } },
      verificationStatus: 'UNTESTED',
      verifiedAt: null,
      updatedAt: '2026-11-10T00:00:00Z',
    },
  ])
  vi.spyOn(metaConnectionApi, 'capabilities').mockResolvedValue({
    csrf_token: 'csrf',
    configured: true,
  })
  vi.spyOn(metaConnectionApi, 'connectBm').mockResolvedValue({
    id,
    revision: 1,
    status: 'ACTIVE',
    kind: 'BM',
    accessible_account_count: 7,
  })
})
afterEach(() => {
  w?.unmount()
  vi.restoreAllMocks()
})
async function start() {
  w = mount(ConfigurationPage, {
    global: {
      plugins: [ElementPlus],
      stubs: {
        MetaConnectionsPanel: true,
        ImportAccounts: true,
        ConfigurationDialog: true,
        ConfigurationHistory: true,
      },
    },
  })
  await flushPromises()
}
async function click(label: string) {
  const b = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(b).toBeTruthy()
  await b!.trigger('click')
  await flushPromises()
}
it('接入BM与旧只读测试分开，取消不发起请求', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  await start()
  expect(w.text()).toContain('只读连接测试')
  await click('接入账户读取')
  expect(metaConnectionApi.connectBm).not.toHaveBeenCalled()
})
it('明确确认后只发送当前配置ID/版本，不含Token', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  await start()
  await click('接入账户读取')
  expect(metaConnectionApi.connectBm).toHaveBeenCalledWith(
    id,
    3,
    'csrf',
    expect.stringMatching(/^meta-bm-/),
  )
  expect(w.text()).toContain('实际可读账户 7 个')
})
it('未知BM接入保留原版本和幂等键重试', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.mocked(metaConnectionApi.connectBm).mockRejectedValueOnce(
    new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', 'offline'),
  )
  await start()
  await click('接入账户读取')
  const first = vi.mocked(metaConnectionApi.connectBm).mock.calls[0]
  await click('重试 BM 接入原请求')
  expect(vi.mocked(metaConnectionApi.connectBm).mock.calls[1]).toEqual(first)
  expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
})
