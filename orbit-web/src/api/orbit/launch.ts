import { referenceRequest, writeHeaders, ReferenceApiError } from './references'
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError, type PlanHttpFieldError } from './launch-validation'

export interface PlanOwnership {
  owner_user_id: string
  owner_team_id: string
}
export interface Budget {
  owner: 'CAMPAIGN' | 'ADSET'
  type: 'DAILY' | 'LIFETIME'
  amount: string
  currency: string
  spend_cap: string | null
}
export interface CampaignMetaSettings {
  spending_limit?: string | null
  advantage_campaign_budget?: boolean
  bid_amount?: string | null
  roas_goal?: string | null
}
export interface ManualPlacements {
  facebook?: (
    | 'FEED'
    | 'STORY'
    | 'REELS'
    | 'RIGHT_COLUMN'
    | 'MARKETPLACE'
    | 'VIDEO_FEEDS'
    | 'SEARCH'
    | 'INSTREAM_VIDEO'
    | 'PROFILE_FEED'
    | 'REELS_OVERLAY'
  )[]
  instagram?: (
    | 'STREAM'
    | 'STORY'
    | 'REELS'
    | 'EXPLORE'
    | 'EXPLORE_HOME'
    | 'PROFILE_FEED'
    | 'SEARCH'
    | 'PROFILE_REELS'
  )[]
  messenger?: ('INBOX' | 'STORY' | 'SPONSORED_MESSAGES')[]
  audience_network?: ('CLASSIC' | 'REWARDED_VIDEO' | 'INSTREAM_VIDEO')[]
  threads?: 'FEED'[]
}
export interface DeviceSettings {
  platforms?: ('MOBILE' | 'DESKTOP')[]
  operating_systems?: ('ANDROID' | 'IOS')[]
  android_models?: string[]
  ios_models?: string[]
  excluded_android_models?: string[]
  excluded_ios_models?: string[]
  android_min_version?: string | null
  android_max_version?: string | null
  ios_min_version?: string | null
  ios_max_version?: string | null
}
export interface AdSetMetaSettings {
  conversion_location?: 'WEBSITE' | 'APP'
  conversion_event?:
    | 'ADD_TO_CART'
    | 'PURCHASE'
    | 'COMPLETE_REGISTRATION'
    | 'LEAD'
    | 'SUBSCRIBE'
    | null
  attribution_click_days?: 1 | 7
  attribution_view_days?: 0 | 1
  audience_mode?: 'ORIGINAL' | 'ADVANTAGE'
  excluded_country_codes?: string[]
  genders?: ('MALE' | 'FEMALE')[]
  excluded_custom_audience_ids?: string[]
  manual_placements?: ManualPlacements
  inventory_filter?: 'FULL' | 'STANDARD' | 'LIMITED'
  audience_network_inventory_filter?: 'FULL' | 'STANDARD' | 'LIMITED'
  devices?: DeviceSettings
}
export interface AdMetaSettings {
  format?: 'SINGLE' | 'CAROUSEL'
  start_time?: string | null
  end_time?: string | null
  carousel_asset_ids?: string[]
}
export interface AdConfig {
  meta_settings?: AdMetaSettings | null
  local_id: string
  copies: number
  name?: string
  title?: string
  body?: string
  description?: string
  url?: string | null
  url_tags?: string
  cta?: string
  asset_type?: 'ANY' | 'IMAGE' | 'VIDEO'
}
export interface AdSetConfig {
  meta_settings?: AdSetMetaSettings | null
  local_id: string
  copies: number
  ads: AdConfig[]
  name?: string
  budget?: Budget | null
  country_codes?: string[]
  age_min?: number
  age_max?: number
  locales?: string[]
  placements?: 'AUTO' | 'MANUAL'
  optimization_goal?: string
  billing_event?: string
  metric_profile_id?: string
  start_time?: string
  end_time?: string | null
}
export interface CampaignConfig {
  meta_settings?: CampaignMetaSettings | null
  local_id: string
  copies: number
  adsets: AdSetConfig[]
  objective?: 'OUTCOME_SALES' | 'OUTCOME_APP_PROMOTION' | 'OUTCOME_LEADS'
  buying_type?: 'AUCTION'
  special_ad_categories?: string[]
  budget?: Budget | null
  bid_strategy?:
    | 'LOWEST_COST_WITHOUT_CAP'
    | 'COST_CAP'
    | 'LOWEST_COST_WITH_MIN_ROAS'
    | 'LOWEST_COST_WITH_BID_CAP'
}
export interface GroupIdentity {
  adset_local_id: string
  pixel_id: string | null
  conversion_event: string | null
  application_id: string | null
  object_store_url: string | null
}
export interface IdentityBinding {
  account_id: string
  page_id: string
  groups: GroupIdentity[]
  ad_overrides: { ad_local_id: string; page_id: string }[]
}
export interface PlanWrite {
  name: string
  ownership: PlanOwnership
  account_ids: string[]
  channel_id?: string | null
  campaigns: CampaignConfig[]
  identity_bindings: IdentityBinding[]
  asset_ids: string[]
  allow_repeat: boolean
  activate_after_create: boolean
  execution_mode: 'META_API' | 'ADSPOWER_UI'
  account_scope_snapshot_id?: string | null
  profile_binding_ids?: string[]
  workflow_version?: string
  adapter_version?: string
}
export interface LaunchPlan extends PlanWrite {
  id: string
  revision: number
  state: 'DRAFT' | 'VALIDATED' | 'SUBMITTED' | 'ARCHIVED'
  created_at: string
  updated_at: string
}
export interface LaunchCapabilities {
  actions: string[]
  data_role: string
  csrf_token: string
  actor_user_id: string
  actor_team_id: string
  actor_label: string
  execution_available?: boolean
  validation_available?: boolean
  blocked_dependencies?: string[]
}
export interface OwnerOption {
  id: string
  name: string
  team_id: string
  team_name: string
}
export interface CollectionPage<T> {
  items: T[]
  next_cursor: string | null
  scope_version: number
  data_as_of: string
}
/** 草稿保存保留服务端字段Pointer；其余目录请求继续使用原客户端。 */
export class LaunchDraftError extends ReferenceApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    public field_errors: PlanHttpFieldError[] = [],
  ) {
    super(status, code, message)
  }
}
async function saveDraftRequest(path: string, init: RequestInit): Promise<LaunchPlan> {
  const context = JSON.stringify([orbitCredentials(), orbitAuthHeaders()]),
    controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 15000)
  try {
    let response: Response
    try {
      response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
        ...init,
        signal: controller.signal,
        credentials: orbitCredentials(),
        cache: 'no-store',
        headers: orbitAuthHeaders({ 'Content-Type': 'application/json', ...init.headers }),
      })
    } catch {
      throw new LaunchDraftError(
        0,
        'NETWORK_UNAVAILABLE',
        '草稿保存连接中断或超时，请重试原请求确认结果',
      )
    }
    let value
    try {
      value = await response.json()
    } catch {
      throw new LaunchDraftError(502, 'INVALID_RESPONSE', '草稿响应未能确认，请重试原请求')
    }
    if (context !== JSON.stringify([orbitCredentials(), orbitAuthHeaders()]))
      throw new LaunchDraftError(
        502,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，保存结果未能确认',
      )
    if (!response.ok || (typeof value?.code === 'number' && value.code !== 200)) {
      let fields: PlanHttpFieldError[] = []
      try {
        if (value?.field_errors !== undefined) {
          if (!Array.isArray(value.field_errors) || value.field_errors.length > 100)
            throw new Error()
          fields = value.field_errors.map(parsePlanHttpFieldError)
        }
      } catch {
        throw new LaunchDraftError(
          502,
          'INVALID_RESPONSE',
          '草稿错误响应字段未能确认，请保留原请求',
        )
      }
      throw new LaunchDraftError(
        response.status,
        value?.code ?? 'REQUEST_FAILED',
        value?.message ?? value?.msg ?? '草稿保存失败',
        fields,
      )
    }
    return value as LaunchPlan
  } finally {
    clearTimeout(timeout)
  }
}
export const launchApi = {
  capabilities: () => referenceRequest<LaunchCapabilities>('/launch-plans/capabilities'),
  owners: (cursor = '') =>
    referenceRequest<{ items: OwnerOption[]; next_cursor: string | null; scope_version: number }>(
      `/launch-plans/ownership-options?${new URLSearchParams({ page_size: '200', ...(cursor ? { cursor } : {}) })}`,
    ),
  list: (query: URLSearchParams) =>
    referenceRequest<CollectionPage<LaunchPlan>>(`/launch-plans?${query}`),
  get: (id: string) => referenceRequest<LaunchPlan>(`/launch-plans/${encodeURIComponent(id)}`),
  save: (
    body: PlanWrite,
    csrf: string,
    key: string,
    existing?: Pick<LaunchPlan, 'id' | 'revision'>,
  ) =>
    saveDraftRequest(
      existing ? `/launch-plans/${encodeURIComponent(existing.id)}` : '/launch-plans',
      {
        method: existing ? 'PUT' : 'POST',
        headers: writeHeaders(csrf, key, existing?.revision),
        body: JSON.stringify(body),
      },
    ),
}
