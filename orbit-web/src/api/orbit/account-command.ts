/** 独立命令诊断；原Ack和Task协议均不改变，不通过GET触发执行。 */
import type { AccountAction } from './account-actions'
import { ReferenceApiError, referenceRequest } from './references'

export type AccountCommandState =
  | 'SCHEDULED'
  | 'WAITING_EXECUTOR'
  | 'WAITING_RETRY'
  | 'RUNNING'
  | 'BLOCKED'
  | 'SUCCEEDED'
  | 'FAILED'
export interface AccountCommandDiagnostic {
  command_id: string
  account_id: string
  kind: AccountAction
  accepted_request_id: string
  revision: number
  state: AccountCommandState
  attempt_count: number
  last_error_code: string | null
  effective_from: string | null
  next_attempt_at: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
}
const keys = [
  'command_id',
  'account_id',
  'kind',
  'accepted_request_id',
  'revision',
  'state',
  'attempt_count',
  'last_error_code',
  'effective_from',
  'next_attempt_at',
  'created_at',
  'updated_at',
  'completed_at',
]
  .sort()
  .join(',')
const states = new Set([
  'SCHEDULED',
  'WAITING_EXECUTOR',
  'WAITING_RETRY',
  'RUNNING',
  'BLOCKED',
  'SUCCEEDED',
  'FAILED',
])
const utc = (value: unknown) =>
  typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) &&
  Number.isFinite(Date.parse(value)) &&
  new Date(value).toISOString() === value

export const accountCommandApi = {
  async status(accountId: string, kind: AccountAction, requestId: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ kind, request_id: requestId })
    const value = await referenceRequest<AccountCommandDiagnostic>(
      `/accounts/${encodeURIComponent(accountId)}/actions/status?${query}`,
      { signal },
    )
    if (
      !value ||
      Object.keys(value).sort().join(',') !== keys ||
      value.account_id !== accountId ||
      value.kind !== kind ||
      value.accepted_request_id !== requestId ||
      typeof value.command_id !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.command_id) ||
      !Number.isSafeInteger(value.revision) ||
      value.revision < 1 ||
      !states.has(value.state) ||
      !Number.isInteger(value.attempt_count) ||
      value.attempt_count < 0 ||
      value.attempt_count > 4 ||
      !(
        value.last_error_code === null ||
        (typeof value.last_error_code === 'string' &&
          /^[A-Z][A-Z0-9_]{0,63}$/.test(value.last_error_code))
      ) ||
      !utc(value.created_at) ||
      !utc(value.updated_at) ||
      ![value.effective_from, value.next_attempt_at, value.completed_at].every(
        (instant) => instant === null || utc(instant),
      )
    ) {
      throw new ReferenceApiError(
        502,
        'INVALID_RESPONSE',
        '命令状态响应无法核验，原受理回执保持不变',
      )
    }
    return value
  },
}
