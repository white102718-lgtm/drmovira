import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { listMaterialScannerProfiles } from '@/api/orbit/configuration'
import MaterialScannerProfileSelect from '@/views/orbit/system/configuration/MaterialScannerProfileSelect.vue'
import ConfigurationDialog from '@/views/orbit/system/configuration/ConfigurationDialog.vue'
import type { ConfigSection } from '@/api/orbit/configuration'

vi.mock('@/utils/auth', () => ({ getToken: () => 'fixture-session' }))
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('扫描候选公开边界', () => {
  it.each(['MATERIAL_SCANNER', 'AI_GPT'])('版本变更影响仅在扫描配置弹窗提示：%s', async (key) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [] }))),
    )
    const section: ConfigSection = {
      key,
      label: key === 'MATERIAL_SCANNER' ? '素材安全扫描' : 'GPT API',
      fields: [
        {
          key: key === 'MATERIAL_SCANNER' ? 'profileId' : 'model',
          label: '配置选项',
          type: 'text',
          required: true,
          defaultValue: '',
          minimum: 0,
          maximum: 40,
          options: [],
        },
      ],
    }
    const wrapper = mount(ConfigurationDialog, {
      props: { sections: [section], configurations: [], encryptionReady: true },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    try {
      await wrapper.vm.open()
      await flushPromises()
      expect(
        document.body.textContent?.includes(
          '保存或测试会更新扫描配置版本，正在处理的素材可能需要重新检查',
        ),
      ).toBe(key === 'MATERIAL_SCANNER')
    } finally {
      wrapper.unmount()
    }
  })

  it('只请求固定同源候选接口，返回标识标签及可用性', async () => {
    const items = [{ id: 'trusted', label: '受控扫描', availability: 'READY' }]
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items })))
    vi.stubGlobal('fetch', fetch)
    expect(await listMaterialScannerProfiles()).toEqual(items)
    expect(fetch.mock.calls[0][0]).toMatch(
      /\/api\/v1\/system-configurations\/material-scanner-profiles$/,
    )
    expect(fetch.mock.calls[0][1].cache).toBe('no-store')
  })

  it.each([
    { id: 'trusted', label: '受控扫描', availability: 'READY', port: 19310 },
    { id: '../trusted', label: '受控扫描', availability: 'READY' },
    { id: 'trusted', label: '受控扫描', availability: 'UNKNOWN' },
    { id: 'trusted', label: '受控扫描', availability: ['READY'] },
    { id: 'trusted', label: 'x\u202e', availability: 'READY' },
    { id: 'trusted', label: 'x\ud800', availability: 'READY' },
    { id: 'trusted', label: 'x\n', availability: 'READY' },
    { id: 'trusted', label: '😀'.repeat(81), availability: 'READY' },
  ])('拒绝基础设施泄露或不完整候选，不渲染原响应', async (item) => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [item] }))),
    )
    await expect(listMaterialScannerProfiles()).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('候选标签按Unicode码点限制80并统一NFC及两端空白', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              items: [
                { id: 'emoji', label: '😀'.repeat(80), availability: 'READY' },
                { id: 'nfc', label: ' Cafe\u0301 ', availability: 'UNAVAILABLE' },
              ],
            }),
          ),
      ),
    )
    expect(await listMaterialScannerProfiles()).toEqual([
      { id: 'emoji', label: '😀'.repeat(80), availability: 'READY' },
      { id: 'nfc', label: 'Café', availability: 'UNAVAILABLE' },
    ])
  })

  it('无候选时保留旧选择并明确提示，不提供自由输入路径或地址', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }))))
    const wrapper = mount(MaterialScannerProfileSelect, {
      props: { modelValue: 'old-trusted' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无可用扫描候选')
    expect(wrapper.props('modelValue')).toBe('old-trusted')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(
      wrapper.findAll('input').every((input) => input.attributes('readonly') !== undefined),
    ).toBe(true)
    wrapper.unmount()
  })

  it('读取失败可显式刷新，错误文案不回显原始连接内容', async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('private-path-fixture'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] })))
    vi.stubGlobal('fetch', fetch)
    const wrapper = mount(MaterialScannerProfileSelect, {
      props: { modelValue: '' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toBe('扫描候选读取失败，请刷新重试')
    expect(wrapper.text()).not.toContain('private-path-fixture')
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
