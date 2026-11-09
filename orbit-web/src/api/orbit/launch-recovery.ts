import type { PlanWrite, LaunchPlan } from './launch'
export interface DraftRecovery {
  actor: string
  body: PlanWrite
  existing?: Pick<LaunchPlan, 'id' | 'revision'>
  pendingKey?: string
}
const key = (actor: string) => `orbit.launch.draft.v1.${actor}`
/** 恢复缓存只含无凭证的配置/资源版本及重试意图；绝不缓存会话或CSRF。 */
export function cacheDraft(value: DraftRecovery) {
  sessionStorage.setItem(key(value.actor), JSON.stringify(value))
}
export function readDraftRecovery(actor: string): DraftRecovery | null {
  try {
    const raw = sessionStorage.getItem(key(actor))
    if (!raw) return null
    const value = JSON.parse(raw)
    if (
      value.actor !== actor ||
      typeof value.body !== 'object' ||
      !value.body?.ownership ||
      !Array.isArray(value.body.campaigns)
    )
      return null
    return value as DraftRecovery
  } catch {
    return null
  }
}
export function clearDraftRecovery(actor: string) {
  sessionStorage.removeItem(key(actor))
}

import type { TemplateWrite, LaunchTemplate } from './templates'
import type { PlanOwnership } from './launch'
type TemplateIdentity = Pick<LaunchTemplate, 'id' | 'revision'>
export type TemplateMutation =
  | { kind: 'save'; body: TemplateWrite; existing?: TemplateIdentity }
  | { kind: 'share'; existing: TemplateIdentity; recipients: string[]; reason: string }
  | { kind: 'archive'; existing: TemplateIdentity; reason: string }
  | { kind: 'apply'; existing: TemplateIdentity; ownership: PlanOwnership; reason: string }
export interface TemplateRecovery {
  actor: string
  key: string
  mutation: TemplateMutation
}
const templateKey = (actor: string) => `orbit.launch.template-intent.v1.${actor}`
export function cacheTemplateIntent(value: TemplateRecovery) {
  sessionStorage.setItem(templateKey(value.actor), JSON.stringify(value))
}
export function readTemplateIntent(actor: string): TemplateRecovery | null {
  try {
    const raw = sessionStorage.getItem(templateKey(actor))
    if (!raw) return null
    const value = JSON.parse(raw)
    if (
      value.actor !== actor ||
      !/^[ -~]{16,128}$/.test(value.key) ||
      !['save', 'share', 'archive', 'apply'].includes(value.mutation?.kind)
    )
      return null
    return value as TemplateRecovery
  } catch {
    return null
  }
}
export function clearTemplateIntent(actor: string) {
  sessionStorage.removeItem(templateKey(actor))
}
