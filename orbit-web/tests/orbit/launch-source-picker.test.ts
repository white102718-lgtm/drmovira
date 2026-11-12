import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import SourcePicker from '@/views/orbit/launch/SourcePicker.vue'
const ownership = { owner_user_id: 'owner', owner_team_id: 'team' }
let wrapper: VueWrapper
const row = (id: string, owner = 'owner') => ({
  id,
  name: id,
  external_id: id,
  currency: 'USD',
  auth_status: 'AUTHORIZED',
  account_status: 'ACTIVE',
  ownership: { owner_user_id: owner, owner_team_id: 'team' },
})
function response(items: unknown[], next_cursor: string | null = null, status = 200) {
  return new Response(JSON.stringify({ items, next_cursor }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(selected: string[] = []) {
  wrapper = mount(SourcePicker, {
    attachTo: document.body,
    props: { modelValue: true, kind: 'accounts', ownership, selected },
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
it('跨页选择保留原未加载关联，不能把翻页当重置选择', async () => {
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response([row('first')], 'next'))
    .mockResolvedValueOnce(response([row('second')]))
  await start(['saved-unloaded'])
  await click('选择本页可用项')
  await click('下一页候选')
  await click('选择本页可用项')
  await click('确认选择 3 项')
  expect(wrapper.emitted('choose')?.[0]).toEqual([['saved-unloaded', 'first', 'second']])
  expect(String(fetch.mock.calls[1][0])).toContain('cursor=next')
})
it('501候选合并明确拒绝，原500选择不被静默截断或替换', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response([row('new-owner-account')]))
  const selected = Array.from({ length: 500 }, (_, index) => `old-${index}`)
  await start(selected)
  await click('选择本页可用项')
  expect(document.body.textContent).toContain('原选择保持不变')
  await click('确认选择 500 项')
  expect(wrapper.emitted('choose')?.[0]).toEqual([selected])
})
it('同团队另一投手的账户不能因管理员当前可读而被本负责人选择', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response([row('peer-account', 'another-owner')]))
  await start()
  await click('选择本页可用项')
  await click('确认选择 0 项')
  expect(wrapper.emitted('choose')?.[0]).toEqual([[]])
})
it('读取403保留已有选择，不伪成功或清空未读关联', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ code: 'PERMISSION_DENIED', message: '当前无来源读取权限' }), {
      status: 403,
    }),
  )
  await start(['saved-unloaded'])
  expect(document.body.textContent).toContain('当前无来源读取权限')
  await click('确认选择 1 项')
  expect(wrapper.emitted('choose')?.[0]).toEqual([['saved-unloaded']])
})
it('原型素材池按广告数选择，不重复不足时阻止确认，保留未知指标列', async () => {
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>String(url).includes('/assets?')?response([{id:'asset1',name:'素材1',kind:'IMAGE',state:'READY',tag_ids:[],ownership}]):response([]))
  wrapper=mount(SourcePicker,{attachTo:document.body,props:{modelValue:true,kind:'assets',ownership,selected:[],prototype:true,adCount:2,allowRepeat:false},global:{plugins:[ElementPlus]}})
  await flushPromises();await click('按广告数选择当前结果');await click('确认选择 1 项')
  expect(wrapper.emitted('choose')).toBeUndefined()
  expect(document.body.textContent).toContain('请按广告数量选择素材')
  expect(document.body.textContent).toContain('ROAS')
  await wrapper.setProps({allowRepeat:true});await click('确认选择 1 项')
  expect(wrapper.emitted('choose')?.[0]).toEqual([['asset1']])
})
