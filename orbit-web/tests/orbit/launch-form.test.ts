import { describe, expect, it } from 'vitest'
import {
  cloneBranch,
  codePoints,
  newDraft,
  normalizeDraft,
  treeCounts,
} from '@/api/orbit/launch-form'
import type { CampaignConfig } from '@/api/orbit/launch'

const fixture = (): CampaignConfig[] => [
  {
    local_id: 'campaign',
    copies: 2,
    adsets: [{ local_id: 'group', copies: 3, ads: [{ local_id: 'ad', copies: 4 }] }],
  },
]
describe('投放配置树与原字段口径', () => {
  it('按真实父分支展开，不把平行分支相乘', () => {
    const value = fixture()
    expect(treeCounts(2, value)).toEqual({
      campaignCount: 4,
      adsetCount: 12,
      adCount: 48,
      withinLimit: true,
    })
    value.push({ local_id: 'second', copies: 1, adsets: [] })
    expect(treeCounts(2, value).adCount).toBe(48)
  })
  it('一万上限在复制公式后检查，空账户仍是草稿零展开', () => {
    expect(treeCounts(500, fixture()).withinLimit).toBe(false)
    expect(treeCounts(0, fixture()).adCount).toBe(0)
  })
  it('复制整个分支新UUID且不反向修改原配置', () => {
    const original = fixture()[0]
    const result = cloneBranch(original)
    expect(result.local_id).not.toBe(original.local_id)
    expect(result.adsets[0].local_id).not.toBe(original.adsets[0].local_id)
    expect(result.adsets[0].ads[0].local_id).not.toBe(original.adsets[0].ads[0].local_id)
    result.adsets[0].ads[0].title = 'copy'
    expect(original.adsets[0].ads[0].title).toBeUndefined()
  })
  it('新草稿不默认激活，也不复用外部身份和账户选择', () => {
    const ownership = { owner_user_id: 'own', owner_team_id: 'team' }
    const value = newDraft(ownership)
    expect(value.activate_after_create).toBe(false)
    expect(value.account_ids).toEqual([])
    expect(value.identity_bindings).toEqual([])
    value.ownership.owner_user_id = 'changed'
    expect(ownership.owner_user_id).toBe('own')
  })
  it('NFC后按码点，emoji不以UTF16长度计数', () => {
    expect(codePoints('e\u0301'.repeat(100))).toBe(100)
    expect(codePoints('😀'.repeat(100))).toBe(100)
  })
  it('替换式草稿清空可选字段省略，正文LF及显式null保留', () => {
    const value = newDraft({ owner_user_id: 'own', owner_team_id: 'team' })
    value.campaigns = fixture()
    const ad = value.campaigns[0].adsets[0].ads[0]
    ad.title = ''
    ad.body = '甲\n乙'
    ad.url = null
    ad.description = ''
    const normalized = normalizeDraft(value)
    const result = normalized.campaigns[0].adsets[0].ads[0]
    expect(result.title).toBeUndefined()
    expect(result.body).toBe('甲\n乙')
    expect(result.url).toBeNull()
    expect(result.description).toBe('')
    expect(ad.title).toBe('')
  })
})

it('结构汇总不删除旧草稿的空国家字段或回填新配置', () => {
  const value = fixture()
  value[0].adsets[0].country_codes = []
  const before = JSON.stringify(value)
  treeCounts(2, value)
  expect(JSON.stringify(value)).toBe(before)
  expect(value[0].meta_settings).toBeUndefined()
})
