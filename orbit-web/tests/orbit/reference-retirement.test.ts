import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import Catalog from '@/views/orbit/channels/ReferenceCatalog.vue'
import { referenceApi } from '@/api/orbit/references'

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})
it('字典只读取户商，页面和导入类别均无产品总代', async () => {
  vi.spyOn(referenceApi, 'capabilities').mockResolvedValue({
    catalog_revision: 0,
    csrf_token: 'test',
  })
  const list = vi
    .spyOn(referenceApi, 'list')
    .mockResolvedValue({ items: [], next_cursor: null, catalog_revision: 0, scope_version: 1 })
  const wrapper = mount(Catalog, {
    attachTo: document.body,
    global: { plugins: [ElementPlus], stubs: { VendorAliases: true } },
  })
  try {
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(1)
    expect(list.mock.calls[0][0]).toBe('VENDOR')
    expect(document.body.textContent).not.toMatch(/产品|总代/)
    const button = [...document.querySelectorAll('button')].find(
      (item) => item.textContent?.trim() === '导入预检',
    )!
    button.click()
    await flushPromises()
    expect(document.body.textContent).toContain('户商')
    expect(document.body.textContent).not.toMatch(/产品|总代/)
  } finally {
    wrapper.unmount()
  }
})
