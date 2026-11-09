/** 仅组件逻辑fixture，不是实际预检、能力、资金或平台执行证据。 */
import type { LaunchCapabilities, LaunchPlan } from '@/api/orbit/launch'
import type { Allocation, NameReservation, PlanValidation } from '@/api/orbit/launch-validation'
import { newDraft } from '@/api/orbit/launch-form'
import { taskUuid as id } from './tasks-fixtures'
export const fixedTime = '2026-11-08T02:00:00.000Z'
export function plan(): LaunchPlan {
  return {
    ...newDraft({ owner_user_id: id(10), owner_team_id: id(20) }),
    id: id(1),
    revision: 7,
    state: 'DRAFT',
    name: '冻结计划',
    account_ids: [id(2)],
    asset_ids: [id(3)],
    channel_id: id(4),
    campaigns: [
      {
        local_id: id(5),
        copies: 1,
        adsets: [{ local_id: id(6), copies: 1, ads: [{ local_id: id(7), copies: 1 }] }],
      },
    ],
    created_at: fixedTime,
    updated_at: fixedTime,
  }
}
export function caps(): LaunchCapabilities {
  return {
    actions: ['edit', 'execute', 'publish'],
    data_role: 'USER',
    csrf_token: 'fixture-frozen-csrf-token',
    actor_user_id: id(10),
    actor_team_id: id(20),
    actor_label: '本人',
  }
}
export const campaignKey = `${id(2)}/${id(5)}/1`
export const slot = `${campaignKey}/${id(6)}/1/${id(7)}/1`
export function names(): NameReservation {
  return {
    id: id(100),
    plan_revision: 7,
    naming_date: '2026-11-08',
    items: [
      {
        slot_key: campaignKey,
        name: '渠道_本人_20261108_0001',
        sequence: '000123456789012345678901234567',
      },
    ],
  }
}
export function allocation(): Allocation {
  return {
    id: id(101),
    plan_id: id(1),
    plan_revision: 7,
    state: 'SUCCEEDED',
    task_id: null,
    algorithm_version: 'allocation-v1',
    seed: 0,
    items: [{ slot_key: slot, account_id: id(2), asset_id: id(3), asset_revision: 2 }],
    warnings: [],
    input_hash: 'a'.repeat(64),
  }
}
export function validation(): PlanValidation {
  return {
    valid: true,
    hash: 'b'.repeat(64),
    expires_at: '2026-11-08T02:15:00.000Z',
    errors: [],
    campaign_count: 1,
    adset_count: 1,
    ad_count: 1,
    budget_totals: [
      { amount: '999999999999999999999.123456', currency: 'USD' },
      { amount: '12.340000', currency: 'JPY' },
    ],
    scope_version: 99,
    total_dag_node_count: 9,
  }
}
