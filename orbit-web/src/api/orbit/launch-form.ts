import type { AdConfig, AdSetConfig, CampaignConfig, PlanOwnership, PlanWrite } from './launch'

/** 界面计数按Unicode码点；金额始终为字符串，不从二进制浮点数推算。 */
export const codePoints = (value: string) => [...value.normalize('NFC').trim()].length
export const cloneValue = <T>(value: T): T => JSON.parse(JSON.stringify(value))
export function newCampaign(): CampaignConfig {
  return {
    local_id: crypto.randomUUID(),
    copies: 1,
    adsets: [],
    objective: 'OUTCOME_SALES',
    buying_type: 'AUCTION',
    bid_strategy: 'LOWEST_COST_WITHOUT_CAP',
    meta_settings: { advantage_campaign_budget: false },
  }
}
export function newAdSet(objective?: CampaignConfig['objective']): AdSetConfig {
  return {
    local_id: crypto.randomUUID(),
    copies: 1,
    ads: [],
    age_min: 18,
    age_max: 65,
    placements: 'AUTO',
    billing_event: 'IMPRESSIONS',
    optimization_goal:
      objective === 'OUTCOME_APP_PROMOTION' ? 'APP_INSTALLS' : 'OFFSITE_CONVERSIONS',
    meta_settings: {
      conversion_location: objective === 'OUTCOME_APP_PROMOTION' ? 'APP' : 'WEBSITE',
      attribution_click_days: 7,
      attribution_view_days: 1,
      audience_mode: 'ORIGINAL',
      inventory_filter: 'STANDARD',
      audience_network_inventory_filter: 'STANDARD',
    },
  }
}
export function newAd(): AdConfig {
  return {
    local_id: crypto.randomUUID(),
    copies: 1,
    cta: 'SHOP_NOW',
    asset_type: 'ANY',
    meta_settings: { format: 'SINGLE' },
  }
}
export function newDraft(ownership: PlanOwnership): PlanWrite {
  return {
    name: '',
    ownership: { ...ownership },
    account_ids: [],
    channel_id: null,
    campaigns: [],
    identity_bindings: [],
    asset_ids: [],
    allow_repeat: false,
    activate_after_create: false,
    execution_mode: 'META_API',
  }
}
export function cloneBranch<T extends CampaignConfig | AdSetConfig | AdConfig>(input: T): T {
  const value = cloneValue(input)
  const visit = (node: CampaignConfig | AdSetConfig | AdConfig) => {
    node.local_id = crypto.randomUUID()
    if ('adsets' in node) node.adsets.forEach(visit)
    if ('ads' in node) node.ads.forEach(visit)
  }
  visit(value)
  return value
}
export function treeCounts(accounts: number, campaigns: CampaignConfig[]) {
  let campaignCount = 0,
    adsetCount = 0,
    adCount = 0
  for (const campaign of campaigns) {
    const factor = accounts * campaign.copies
    campaignCount += factor
    for (const group of campaign.adsets) {
      const multiplier = factor * group.copies
      adsetCount += multiplier
      adCount += multiplier * group.ads.reduce((sum, ad) => sum + ad.copies, 0)
    }
  }
  return {
    campaignCount,
    adsetCount,
    adCount,
    withinLimit: Math.max(campaignCount, adsetCount, adCount) <= 10000,
  }
}
/** 可缺业务必填的草稿仍保留已填写字段；空的可选短文本移除，不能发送非法空枚举。 */
export function normalizeDraft(input: PlanWrite): PlanWrite {
  const value = cloneValue(input)
  const normalize = (node: Record<string, unknown>) => {
    for (const [key, item] of Object.entries(node)) {
      if (typeof item === 'string') {
        node[key] = item.normalize('NFC').trim()
        if (node[key] === '' && !['name', 'description', 'url_tags', 'body'].includes(key))
          delete node[key]
      } else if (Array.isArray(item)) {
        item.forEach((child) => {
          if (child && typeof child === 'object' && !Array.isArray(child))
            normalize(child as Record<string, unknown>)
        })
      } else if (item && typeof item === 'object') normalize(item as Record<string, unknown>)
    }
  }
  normalize(value as unknown as Record<string, unknown>)
  for (const campaign of value.campaigns) {
    for (const group of campaign.adsets) {
      if (!group.country_codes?.length) delete group.country_codes
      if (!group.name?.trim()) delete group.name
      for (const ad of group.ads) {
        if (!ad.name?.trim()) delete ad.name
        if (!ad.body?.trim()) delete ad.body
        if (!ad.title?.trim()) delete ad.title
      }
    }
  }
  return value
}
