/** 原列表读合同的真实ElementPlus测试；网络替身不等于MySQL/浏览器验收。 */
import { defineComponent, h } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import LaunchPage from '@/views/orbit/launch/index.vue'
import Templates from '@/views/orbit/launch/TemplatesPanel.vue'
import { launchApi } from '@/api/orbit/launch'
import { templateApi, type LaunchTemplate } from '@/api/orbit/templates'
import { ReferenceApiError } from '@/api/orbit/references'
import { plan, caps } from './plan-validation-fixtures'
const state = vi.hoisted(() => ({ permissions: ['*:*:*'] }))
vi.mock('@/store/modules/user', () => ({ default: () => state }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
const stub = (name: string) =>
  defineComponent({
    name,
    props: ['active', 'modelValue'],
    emits: ['blocked', 'applied', 'failure', 'locked', 'update:modelValue'],
    setup: () => () => h('div'),
  })
const DraftStub = stub('DraftEditor'),
  ValidationStub = stub('PlanValidationDialog')
const template = (): LaunchTemplate => ({
  id: '00000000-0000-4000-8000-000000000111',
  name: '第一页模板',
  description: '真实说明',
  visibility: 'PRIVATE',
  recipient_user_ids: [],
  campaigns: plan().campaigns,
  revision: 11,
  ownership: {
    owner_user_id: '00000000-0000-4000-8000-000000000888',
    owner_team_id: '00000000-0000-4000-8000-000000000999',
  },
  state: 'ACTIVE',
})
const page = (items: unknown[], next_cursor: string | null) => ({
  items,
  next_cursor,
  data_as_of: '2026-11-08T00:00:00Z',
  scope_version: 1,
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  sessionStorage.clear()
  state.permissions = ['*:*:*']
  vi.spyOn(launchApi, 'capabilities').mockResolvedValue({
    ...caps(),
    actions: ['create', 'edit'],
    validation_available: false,
  })
  vi.spyOn(templateApi, 'capabilities').mockResolvedValue({
    ...caps(),
    actions: ['create', 'edit', 'share', 'archive'],
  })
  vi.spyOn(launchApi, 'list').mockResolvedValue(page([plan()], 'cursor2') as never)
  vi.spyOn(templateApi, 'list').mockResolvedValue(page([template()], 'cursor2') as never)
  vi.spyOn(templateApi, 'get').mockResolvedValue(template())
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  sessionStorage.clear()
  vi.restoreAllMocks()
})
async function start(kind: 'plan' | 'template') {
  wrapper =
    kind === 'plan'
      ? mount(LaunchPage, {
          attachTo: document.body,
          global: {
            plugins: [ElementPlus],
            stubs: {
              DraftEditor: DraftStub,
              PlanValidationDialog: ValidationStub,
              TemplatesPanel: stub('TemplatesPanel'),
              TaskPanel: stub('TaskPanel'),
              TaskDetails: stub('TaskDetails'),
            },
          },
        })
      : mount(Templates, {
          attachTo: document.body,
          props: { active: true },
          global: { plugins: [ElementPlus] },
        })
  await flushPromises()
}
const button = (name: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (row) => row.textContent?.trim() === name,
  )!
async function click(name: string) {
  expect(button(name), name).toBeTruthy()
  button(name).click()
  await flushPromises()
}
async function size(value: number) {
  const select = wrapper!
    .findAllComponents({ name: 'ElSelect' })
    .find((row) => String(row.props('ariaLabel') ?? '').startsWith('每页'))!
  expect(select).toBeTruthy()
  select.vm.$emit('update:modelValue', value)
  select.vm.$emit('change', value)
  await flushPromises()
}
const api = (kind: 'plan' | 'template') =>
  kind === 'plan' ? vi.mocked(launchApi.list) : vi.mocked(templateApi.list)
const noun = (kind: 'plan' | 'template') => (kind === 'plan' ? '计划' : '模板')
for (const kind of ['plan', 'template'] as const) {
  it(`${kind}字节短页仍有下一页，三页历史游标回退使用原签名而非合成页码`, async () => {
    api(kind).mockImplementation(async (query) => {
      const cursor = query.get('cursor')
      return page(
        kind === 'plan'
          ? [{ ...plan(), name: cursor ?? '首页' }]
          : [{ ...template(), name: cursor ?? '首页' }],
        cursor === 'cursor3' ? null : cursor === 'cursor2' ? 'cursor3' : 'cursor2',
      ) as never
    })
    await start(kind)
    expect(api(kind).mock.calls[0][0].get('page_size')).toBe('20')
    await click(`下一页${noun(kind)}`)
    await click(`下一页${noun(kind)}`)
    await click(`上一页${noun(kind)}`)
    await click(`上一页${noun(kind)}`)
    expect(api(kind).mock.calls.map(([query]) => query.get('cursor'))).toEqual([
      null,
      'cursor2',
      'cursor3',
      'cursor2',
      null,
    ])
    expect(button(`上一页${noun(kind)}`).disabled).toBe(true)
    expect(document.body.textContent).toContain('当前返回 1 项')
  })
  it(`${kind}四档page_size都真实发送，换大小从首游标重新建立历史`, async () => {
    await start(kind)
    await click(`下一页${noun(kind)}`)
    for (const value of [50, 100, 200, 20]) {
      await size(value)
      const query = api(kind).mock.calls.at(-1)![0]
      expect(query.get('page_size')).toBe(String(value))
      expect(query.get('cursor')).toBeNull()
      expect(button(`上一页${noun(kind)}`).disabled).toBe(true)
    }
  })
  it(`${kind}换名称/状态/UTC日期禁旧游标，原日期字符串不自行加日或转换时区`, async () => {
    await start(kind)
    await click(`下一页${noun(kind)}`)
    await wrapper!.findComponent({ name: 'ElInput' }).find('input').setValue('新条件')
    wrapper!
      .findAllComponents({ name: 'ElSelect' })[0]
      .vm.$emit('update:modelValue', kind === 'plan' ? 'DRAFT' : 'ACTIVE')
    wrapper!
      .findComponent({ name: 'ElDatePicker' })
      .vm.$emit('update:modelValue', ['2026-11-01', '2026-11-08'])
    await flushPromises()
    expect(button(`下一页${noun(kind)}`).disabled).toBe(true)
    expect(button(`上一页${noun(kind)}`).disabled).toBe(true)
    await click(kind === 'plan' ? '查询计划' : '查询模板')
    const query = api(kind).mock.calls.at(-1)![0]
    expect(Object.fromEntries(query)).toEqual({
      page_size: '20',
      q: '新条件',
      status: kind === 'plan' ? 'DRAFT' : 'ACTIVE',
      date_from: '2026-11-01',
      date_to: '2026-11-08',
    })
    expect(button(`上一页${noun(kind)}`).disabled).toBe(true)
  })
  it(`${kind}409清除旧目录与游标，明确回首重新读取；403清旧数据和写能力`, async () => {
    await start(kind)
    api(kind).mockRejectedValueOnce(new ReferenceApiError(409, 'SCOPE_CHANGED', '目录水位改变'))
    await click(`下一页${noun(kind)}`)
    expect(document.body.textContent).toContain('旧分页已清除')
    expect(button(`下一页${noun(kind)}`)).toBeUndefined()
    expect(button(`上一页${noun(kind)}`).disabled).toBe(true)
    await click(kind === 'plan' ? '重新读取首页' : '重新读取模板首页')
    expect(api(kind).mock.calls.at(-1)![0].get('cursor')).toBeNull()
    api(kind).mockRejectedValueOnce(new ReferenceApiError(403, 'PERMISSION_DENIED', '权限已撤回'))
    await click(`下一页${noun(kind)}`)
    expect(button(`下一页${noun(kind)}`)).toBeUndefined()
    expect(button(kind === 'plan' ? '新建服务器草稿' : '新建配置模板')).toBeUndefined()
  })
  it(`${kind}网络错误保留上次成功页和筛选，重试仍沿用同一下一页游标`, async () => {
    await start(kind)
    api(kind).mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '读取中断'))
    await click(`下一页${noun(kind)}`)
    expect(document.body.textContent).toContain('保留上次成功读取的数据')
    await click(`下一页${noun(kind)}`)
    expect(
      api(kind)
        .mock.calls.slice(-2)
        .map(([query]) => query.get('cursor')),
    ).toEqual(['cursor2', 'cursor2'])
  })
}
it('模板详情完整回显真实id/revision/ownership/state，不从当前actor猜拥有者名称或时间', async () => {
  await start('template')
  await click('详情')
  const metadata = document.querySelector('.template-metadata')!
  for (const text of [
    template().id,
    '11 / ACTIVE',
    template().ownership.owner_user_id,
    template().ownership.owner_team_id,
    '名称未读取',
  ])
    expect(metadata.textContent).toContain(text)
  expect(metadata.textContent).not.toContain(caps().actor_label)
  expect(metadata.textContent).not.toContain('创建时间')
  expect(button('下一页模板').disabled).toBe(true)
  expect(button('上一页模板').disabled).toBe(true)
})
it('模板切离再进入时迟到旧页和旧caps不能盖新页', async () => {
  let resolve!: (value: unknown) => void
  api('template')
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        }) as never,
    )
    .mockResolvedValueOnce(page([{ ...template(), name: '新范围页面' }], null) as never)
  await start('template')
  await wrapper!.setProps({ active: false })
  await wrapper!.setProps({ active: true })
  await flushPromises()
  expect(document.body.textContent).toContain('新范围页面')
  resolve(page([{ ...template(), name: '迟到旧页' }], 'old-cursor'))
  await flushPromises()
  expect(document.body.textContent).not.toContain('迟到旧页')
  expect(button('下一页模板')).toBeUndefined()
})
it('计划切tab后旧读取失效，新查询完成后迟到页不覆盖当前结果', async () => {
  let resolve!: (value: unknown) => void
  api('plan')
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        }) as never,
    )
    .mockResolvedValueOnce(page([{ ...plan(), name: '新的计划页' }], null) as never)
  await start('plan')
  const tabs = wrapper!.findAll('[role="tab"]')
  await tabs.find((row) => row.text() === '任务')!.trigger('click')
  await flushPromises()
  await tabs.find((row) => row.text() === '计划与草稿')!.trigger('click')
  await flushPromises()
  await click('查询计划')
  resolve(page([{ ...plan(), name: '迟到计划页' }], 'old'))
  await flushPromises()
  expect(document.body.textContent).toContain('新的计划页')
  expect(document.body.textContent).not.toContain('迟到计划页')
  expect(button('下一页计划')).toBeUndefined()
})
async function ownedTemplate() {
  const own = {
    ...template(),
    ownership: { owner_user_id: caps().actor_user_id, owner_team_id: caps().actor_team_id },
  }
  api('template').mockResolvedValue(page([own], 'cursor2') as never)
  vi.mocked(templateApi.get).mockResolvedValue(own)
  return own
}
async function editTemplateName(value: string) {
  const label = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (row) => row.textContent?.trim() === '模板名称（1—80码点）',
  )!
  const input = document.getElementById(label.htmlFor) as HTMLInputElement
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
it('模板保存确认后内部刷新真正落到首游标，不被busy转场误取消，原分页不残留', async () => {
  const own = await ownedTemplate()
  let committed = false
  api('template').mockImplementation(
    async () =>
      page([{ ...own, name: committed ? '已保存的新模板' : '旧模板' }], 'cursor2') as never,
  )
  vi.spyOn(templateApi, 'save').mockImplementation(async () => {
    committed = true
    return { ...own, name: '已保存的新模板', revision: 12 }
  })
  await start('template')
  await click('下一页模板')
  await click('编辑')
  await editTemplateName('已保存的新模板')
  await click('保存模板')
  expect(api('template')).toHaveBeenCalledTimes(3)
  expect(api('template').mock.calls.at(-1)![0].get('cursor')).toBeNull()
  expect(button('上一页模板').disabled).toBe(true)
  expect(document.querySelector('.template-panel .el-table__body')?.textContent).toContain(
    '已保存的新模板',
  )
})
it('模板未知保存不允许列表页数/条件或关闭操作丢失原意图', async () => {
  await ownedTemplate()
  vi.spyOn(templateApi, 'save').mockRejectedValue(
    new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '保存待确认'),
  )
  await start('template')
  await click('下一页模板')
  await click('编辑')
  await editTemplateName('待确认原意图')
  await click('保存模板')
  expect(button('下一页模板').disabled).toBe(true)
  expect(button('上一页模板').disabled).toBe(true)
  const queries = api('template').mock.calls.length
  await click('下一页模板')
  expect(api('template')).toHaveBeenCalledTimes(queries)
  expect(button('关闭').disabled).toBe(true)
  expect(document.body.textContent).toContain('原操作')
})
it('2020日期编辑本身不发请求，cap读取中断不发list，显式重试保留原日期与名称条件', async () => {
  await start('template')
  await wrapper!.findComponent({ name: 'ElInput' }).find('input').setValue('UI_PAGE_TEMPLATE_')
  wrapper!
    .findComponent({ name: 'ElDatePicker' })
    .vm.$emit('update:modelValue', ['2020-01-01', '2020-01-01'])
  await flushPromises()
  expect(templateApi.capabilities).toHaveBeenCalledTimes(1)
  expect(templateApi.list).toHaveBeenCalledTimes(1)
  vi.mocked(templateApi.capabilities).mockRejectedValueOnce(
    new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '网络中断；请使用重试保留本次幂等键'),
  )
  await click('查询模板')
  expect(templateApi.capabilities).toHaveBeenCalledTimes(2)
  expect(templateApi.list).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('网络中断')
  vi.mocked(templateApi.list).mockResolvedValueOnce(page([], null) as never)
  await click('查询模板')
  expect(templateApi.list).toHaveBeenCalledTimes(2)
  expect(Object.fromEntries(vi.mocked(templateApi.list).mock.calls.at(-1)![0])).toEqual({
    page_size: '20',
    q: 'UI_PAGE_TEMPLATE_',
    date_from: '2020-01-01',
    date_to: '2020-01-01',
  })
  expect(wrapper!.findComponent({ name: 'ElDatePicker' }).props('modelValue')).toEqual([
    '2020-01-01',
    '2020-01-01',
  ])
})
