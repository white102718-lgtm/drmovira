import { referenceRequest, writeHeaders } from './references'
import type {
  CampaignConfig,
  CollectionPage,
  LaunchCapabilities,
  LaunchPlan,
  PlanOwnership,
} from './launch'

export interface TemplateWrite {
  name: string
  description: string
  visibility: 'PRIVATE' | 'TEAM'
  recipient_user_ids: string[]
  campaigns: CampaignConfig[]
}
export interface LaunchTemplate extends TemplateWrite {
  id: string
  revision: number
  ownership: PlanOwnership
  state: 'ACTIVE' | 'ARCHIVED'
}
export const templateApi = {
  recipients: (templateId = '', cursor = '') =>
    referenceRequest<{
      items: { id: string; name: string; team_id: string; team_name: string }[]
      next_cursor: string | null
      scope_version: number
      owner_team_id: string
      csrf_token: string
    }>(
      `/templates/recipient-options?${new URLSearchParams({
        page_size: '200',
        ...(templateId ? { template_id: templateId } : {}),
        ...(cursor ? { cursor } : {}),
      })}`,
    ),
  capabilities: () => referenceRequest<LaunchCapabilities>('/templates/capabilities'),
  list: (query: URLSearchParams) =>
    referenceRequest<CollectionPage<LaunchTemplate>>(`/templates?${query}`),
  get: (id: string) => referenceRequest<LaunchTemplate>(`/templates/${encodeURIComponent(id)}`),
  save: (
    body: TemplateWrite,
    csrf: string,
    key: string,
    existing?: Pick<LaunchTemplate, 'id' | 'revision'>,
  ) =>
    referenceRequest<LaunchTemplate>(
      existing ? `/templates/${encodeURIComponent(existing.id)}` : '/templates',
      {
        method: existing ? 'PUT' : 'POST',
        headers: writeHeaders(csrf, key, existing?.revision),
        body: JSON.stringify(body),
      },
    ),
  share: (
    existing: Pick<LaunchTemplate, 'id' | 'revision'>,
    recipient_user_ids: string[],
    reason: string,
    csrf: string,
    key: string,
  ) =>
    referenceRequest<LaunchTemplate>(`/templates/${encodeURIComponent(existing.id)}/share`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, existing.revision),
      body: JSON.stringify({ recipient_user_ids, reason }),
    }),
  archive: (
    existing: Pick<LaunchTemplate, 'id' | 'revision'>,
    reason: string,
    csrf: string,
    key: string,
  ) =>
    referenceRequest<LaunchTemplate>(`/templates/${encodeURIComponent(existing.id)}/archive`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, existing.revision),
      body: JSON.stringify({ reason }),
    }),
  apply: (
    existing: Pick<LaunchTemplate, 'id' | 'revision'>,
    ownership: PlanOwnership,
    reason: string,
    csrf: string,
    key: string,
  ) =>
    referenceRequest<LaunchPlan>(`/templates/${encodeURIComponent(existing.id)}/apply`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, existing.revision),
      body: JSON.stringify({ ownership, reason }),
    }),
}
