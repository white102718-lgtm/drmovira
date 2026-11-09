import { referenceRequest, writeHeaders, type Ownership } from './references'

export interface ChannelWrite {
  ownership: Ownership
  code: string
  name: string
  product_id: string
  agent_id: string
  type: 'APP' | 'WEBSITE' | 'OTHER'
  media: 'META' | 'GOOGLE' | 'TIKTOK' | 'OTHER'
  url: string
  status: 'ENABLED' | 'DISABLED'
}
export interface Channel extends ChannelWrite {
  id: string
  revision: number
  created_at: string
  updated_at: string
}
export interface ChannelPage {
  items: Channel[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface ChannelCapabilities {
  actions: string[]
  data_role: string
  csrf_token: string
}
export interface ChannelEditContext {
  product_locked: boolean
  references: Record<string, { id: string; name: string; availability: string }>
}
export interface ChannelOwner {
  id: string
  display_name: string
  team_id: string
  team_name: string
}
export interface ChannelLabels {
  id: string
  product_name: string
  agent_name: string
  team_name: string
  owners: { id: string; name: string }[]
}
export const channelApi = {
  labels: (ids: string[]) =>
    referenceRequest<{ items: ChannelLabels[] }>(
      `/channels/display-labels?${new URLSearchParams({ ids: ids.join(',') })}`,
    ),
  capabilities: () => referenceRequest<ChannelCapabilities>('/channels/capabilities'),
  list: (query: URLSearchParams) => referenceRequest<ChannelPage>(`/channels?${query}`),
  get: (id: string) => referenceRequest<Channel>(`/channels/${encodeURIComponent(id)}`),
  context: (id: string) =>
    referenceRequest<ChannelEditContext>(`/channels/${encodeURIComponent(id)}/edit-context`),
  owners: (after = '') =>
    referenceRequest<{ items: ChannelOwner[]; next_after: string | null }>(
      `/channels/ownership-options?${new URLSearchParams({ page_size: '200', ...(after ? { after } : {}) })}`,
    ),
  save: (value: ChannelWrite, csrf: string, key: string, existing?: Channel) =>
    referenceRequest<Channel>(
      existing ? `/channels/${encodeURIComponent(existing.id)}` : '/channels',
      {
        method: existing ? 'PUT' : 'POST',
        headers: writeHeaders(csrf, key, existing?.revision),
        body: JSON.stringify(value),
      },
    ),
  assign: (existing: Channel, ownership: Ownership, reason: string, csrf: string, key: string) =>
    referenceRequest<Channel>(`/channels/${encodeURIComponent(existing.id)}/owners`, {
      method: 'PUT',
      headers: writeHeaders(csrf, key, existing.revision),
      body: JSON.stringify({ ownership, reason }),
    }),
  archive: (existing: Channel, reason: string, csrf: string, key: string) =>
    referenceRequest<Channel>(`/channels/${encodeURIComponent(existing.id)}/archive`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, existing.revision),
      body: JSON.stringify({ reason }),
    }),
}
