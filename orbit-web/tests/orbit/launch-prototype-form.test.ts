import { describe, it, expect } from 'vitest'
import {
  prototypeCampaign,
  setBudgetOwner,
  prototypeBudgetTotals,
} from '@/api/orbit/launch-prototype'
describe('原型创建广告配置', () => {
  it('新建完整层级、独立ID，不预填业务素材或账户', () => {
    const a = prototypeCampaign(),
      b = prototypeCampaign()
    expect(a.adsets).toHaveLength(1)
    expect(a.adsets[0].ads).toHaveLength(1)
    expect(a.local_id).not.toBe(b.local_id)
    expect(a.adsets[0].ads[0].local_id).not.toBe(b.adsets[0].ads[0].local_id)
    expect(a.adsets[0].ads[0].url).toBeUndefined()
  })
  it('预算切换清除相反层预算并保留金额', () => {
    const c = prototypeCampaign()
    c.budget = {
      owner: 'CAMPAIGN',
      type: 'DAILY',
      amount: '12.34',
      currency: 'USD',
      spend_cap: null,
    }
    setBudgetOwner(c, 'ADSET')
    expect(c.budget).toBeNull()
    expect(c.adsets[0].budget?.amount).toBe('12.34')
    setBudgetOwner(c, 'CAMPAIGN')
    expect(c.budget?.amount).toBe('12.34')
    expect(c.adsets[0].budget).toBeNull()
  })
  it('预算按币种周期分开，十进制计算不重复计算CBO', () => {
    const c = prototypeCampaign()
    c.copies = 2
    c.budget = {
      owner: 'CAMPAIGN',
      type: 'DAILY',
      amount: '0.10',
      currency: 'USD',
      spend_cap: null,
    }
    c.adsets[0].copies = 3
    const d = prototypeCampaign()
    d.budget = {
      owner: 'CAMPAIGN',
      type: 'LIFETIME',
      amount: '2.30',
      currency: 'EUR',
      spend_cap: null,
    }
    expect(prototypeBudgetTotals(3, [c, d])).toEqual([
      { currency: 'USD', type: 'DAILY', amount: '0.60' },
      { currency: 'EUR', type: 'LIFETIME', amount: '6.90' },
    ])
  })
})
