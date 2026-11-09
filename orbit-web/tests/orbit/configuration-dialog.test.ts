import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElSelect, ElInputNumber } from 'element-plus'
import { nextTick } from 'vue'
import ConfigurationDialog from '@/views/orbit/system/configuration/ConfigurationDialog.vue'
import type { Configuration, ConfigSection } from '@/api/orbit/configuration'

const { save } = vi.hoisted(() => ({ save: vi.fn() }))
vi.mock('@/api/orbit/configuration', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/orbit/configuration')>()),
  saveConfiguration: save,
}))

const sections: ConfigSection[] = [
  {
    key: 'AI_GPT',
    label: 'GPT API',
    fields: [
      {
        key: 'maxRetries',
        label: '最多重试次数',
        type: 'integer',
        required: true,
        defaultValue: 2,
        minimum: 0,
        maximum: 2,
        options: [],
      },
      {
        key: 'model',
        label: '模型ID',
        type: 'text',
        required: true,
        defaultValue: '',
        minimum: null,
        maximum: 500,
        options: [],
      },
      {
        key: 'apiKey',
        label: 'OpenAI API Key',
        type: 'secret',
        required: true,
        defaultValue: null,
        minimum: 1,
        maximum: 8192,
        options: [],
      },
    ],
  },
]
const existing: Configuration = {
  id: 'fixture-config',
  section: 'AI_GPT',
  name: '测试模型',
  enabled: true,
  revision: 1,
  settings: { model: 'fixture-model' },
  secrets: { apiKey: { configured: true, hint: '已配置（不回显）' } },
  verificationStatus: 'UNTESTED',
  verifiedAt: null,
  updatedAt: '2026-11-07T00:00:00Z',
}
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => {
  wrappers.forEach((wrapper) => wrapper.unmount())
  wrappers.length = 0
  document.body.innerHTML = ''
  save.mockReset()
  vi.unstubAllGlobals()
})

async function open(encryptionReady = true) {
  const wrapper = mount(ConfigurationDialog, {
    props: { sections, configurations: [existing], encryptionReady },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  await wrapper.vm.open(existing)
  await flushPromises()
  return wrapper
}

describe('系统配置凭据弹窗', () => {
  it('已配置凭据保持不变时不要求重新输入，合法emoji名称可保存', async () => {
    save.mockResolvedValue(existing)
    const wrapper = await open()
    const nameInput = wrapper
      .findAll('input')
      .find((input) => input.element.value === existing.name)!
    await nameInput.setValue('😀'.repeat(100))
    const reason = document.querySelector<HTMLInputElement>('input[placeholder*="说明配置用途"]')!
    reason.value = '保持原凭据'
    reason.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const button = [...document.querySelectorAll('button')].find((item) =>
      item.textContent?.includes('保存配置'),
    )!
    button.click()
    await flushPromises()
    await vi.waitFor(() => expect(save).toHaveBeenCalledOnce())
    await flushPromises()
    expect(save.mock.calls[0][0].name).toBe('😀'.repeat(100))
    expect(save.mock.calls[0][0].secrets.apiKey).toEqual({ operation: 'KEEP' })
  })
  it('编辑只回填公开数据与配置状态，不生成掩码密钥输入', async () => {
    await open()
    expect(document.body.textContent).toContain('已配置（不回显）')
    expect(document.querySelector('input[type="password"]')).toBeNull()
    expect(document.querySelector('input[value="****"]')).toBeNull()
  })

  it('替换凭据后提交成功会清空密钥输入并发出刷新事件', async () => {
    save.mockResolvedValue(existing)
    const wrapper = await open()
    const secretSelect = wrapper
      .findAllComponents(ElSelect)
      .find((select) => select.props('modelValue') === 'KEEP')
    expect(secretSelect).toBeDefined()
    secretSelect!.vm.$emit('update:modelValue', 'REPLACE')
    await nextTick()
    const password = document.querySelector<HTMLInputElement>('input[type="password"]')!
    password.value = 'fixture-secret'
    password.dispatchEvent(new Event('input', { bubbles: true }))
    const reason = document.querySelector<HTMLInputElement>('input[placeholder*="说明配置用途"]')!
    reason.value = '测试密钥替换'
    reason.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const button = [...document.querySelectorAll('button')].find((item) =>
      item.textContent?.includes('保存配置'),
    )!
    button.click()
    await flushPromises()
    await vi.waitFor(() => expect(save).toHaveBeenCalledOnce())
    await flushPromises()
    expect(save.mock.calls[0][0].secrets.apiKey).toEqual({
      operation: 'REPLACE',
      value: 'fixture-secret',
    })
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(document.querySelector('input[type="password"]')).toBeNull()
  })
  it('旧配置缺新增字段时表单补默认值，读取对象不被改写', async () => {
    const wrapper = await open()
    expect(wrapper.findComponent(ElInputNumber).props('modelValue')).toBe(2)
    expect(existing.settings).not.toHaveProperty('maxRetries')
  })
})
