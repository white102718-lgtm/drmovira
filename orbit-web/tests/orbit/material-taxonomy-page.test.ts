import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/materials/index.vue'
import { materialApi } from '@/api/orbit/materials'
import { taxonomyApi } from '@/api/orbit/material-taxonomy'
const user = vi.hoisted(() => ({ id: 1, permissions: ['tags.read', 'tags.create'] }))
vi.mock('@/store/modules/user', () => ({ default: () => user }))
afterEach(() => vi.restoreAllMocks())
it('tags-only通过素材入口打开独立目录，不先申请assets.read能力或素材列表', async () => {
  const caps = vi.spyOn(materialApi, 'capabilities').mockRejectedValue(new Error('无素材权限'))
  const assets = vi.spyOn(materialApi, 'list')
  vi.spyOn(taxonomyApi, 'capabilities').mockResolvedValue({
    actor_id: 1,
    tenant_id: '00000000-0000-4000-8000-000000000001',
    csrf_token: null,
  })
  vi.spyOn(taxonomyApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00.000Z',
    scope_version: 1,
  })
  const w = mount(Page, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  expect(caps).not.toHaveBeenCalled()
  expect(assets).not.toHaveBeenCalled()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '标签与分类')!
    .trigger('click')
  await flushPromises()
  expect(taxonomyApi.list).toHaveBeenCalled()
  expect(document.body.textContent).toContain('标签与分类管理')
  w.unmount()
})
