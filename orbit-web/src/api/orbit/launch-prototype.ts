import type { Budget, CampaignConfig } from './launch'
import { newCampaign, newAdSet, newAd } from './launch-form'
export function prototypeCampaign(): CampaignConfig {
  const c = newCampaign(),
    g = newAdSet(c.objective),
    a = newAd()
  a.name = '广告 1'
  a.cta = 'LEARN_MORE'
  g.name = '广告组 1'
  g.ads = [a]
  c.adsets = [g]
  // 原型未列出的高级字段不产生隐式投放意图；已有草稿字段原样保留。
  delete c.meta_settings
  delete g.meta_settings
  delete a.meta_settings
  c.budget = { owner: 'CAMPAIGN', type: 'DAILY', amount: '50', currency: 'USD', spend_cap: null }
  return c
}
export function setBudgetOwner(c: CampaignConfig, owner: Budget['owner']) {
  const previous = c.budget ?? c.adsets.find((g) => g.budget)?.budget
  const base = {
    type: 'DAILY' as const,
    amount: '50',
    currency: 'USD',
    spend_cap: null,
    ...previous,
    owner,
  }
  if (owner === 'CAMPAIGN') {
    c.budget = { ...base }
    c.adsets.forEach((g) => (g.budget = null))
  } else {
    c.budget = null
    c.adsets.forEach((g) => (g.budget = { ...base }))
  }
  if (c.meta_settings) c.meta_settings.advantage_campaign_budget = owner === 'CAMPAIGN'
}
/** 展示预算使用整数分位；按币种和日/总预算分桶，缺失预算不补零。 */
export function prototypeBudgetTotals(accounts: number, campaigns: CampaignConfig[]) {
  const sums = new Map<string, { currency: string; type: string; cents: bigint }>()
  function add(b: Budget | null | undefined, n: number) {
    if (!b || !/^\d+(\.\d{1,6})?$/.test(b.amount)) return
    const [whole, part = ''] = b.amount.split('.'),
      key = b.currency + ':' + b.type
    const row = sums.get(key) ?? { currency: b.currency, type: b.type, cents: 0n }
    row.cents += (BigInt(whole) * 1000000n + BigInt(part.padEnd(6, '0'))) * BigInt(n)
    sums.set(key, row)
  }
  for (const c of campaigns) {
    add(c.budget, accounts * c.copies)
    if (!c.budget) for (const g of c.adsets) add(g.budget, accounts * c.copies * g.copies)
  }
  return [...sums.values()].map((x) => ({
    currency: x.currency,
    type: x.type,
    amount: `${x.cents / 1000000n}.${String(x.cents % 1000000n)
      .padStart(6, '0')
      .replace(/0{1,4}$/, '')}`,
  }))
}
