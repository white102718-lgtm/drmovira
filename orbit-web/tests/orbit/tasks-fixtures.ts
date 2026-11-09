/** 严格原合同的只读fixture，仅用于SDK/组件纯测，不是接口联调或执行证据。 */
import type { Task, TaskNode, TaskPage } from '@/api/orbit/tasks'
export const taskUuid = (number: number) =>
  `00000000-0000-4000-8000-${number.toString(16).padStart(12, '0')}`
export function taskNode(number = 1): TaskNode {
  return {
    id: taskUuid(number),
    node_key: `AD/${taskUuid(800)}/${number}`,
    parent_ids: [],
    kind: 'AD',
    state: 'UNKNOWN',
    external_id: '1234567890123456789012345678901234567890',
    attempt: 1,
    error_code: 'RESULT_UNKNOWN',
    error_message: '结果尚未核实，请勿重复发送。',
    retryable: false,
    configuration_state: 'UNVERIFIED',
    delivery_state: 'UNKNOWN',
    updated_at: '2026-11-08T00:00:00.000Z',
  }
}
export function taskFixture(id = taskUuid(10000), nodeCount = 275): Task {
  return {
    id,
    revision: 1,
    ownership: { owner_user_id: taskUuid(80000), owner_team_id: taskUuid(90000) },
    state: 'UNKNOWN',
    nodes: Array.from({ length: Math.min(nodeCount, 200) }, (_, i) => taskNode(i + 1)),
    latest_event_id: null,
    needs_manual_reconciliation: true,
    created_at: '2026-11-08T00:00:00.000Z',
    node_count: nodeCount,
    next_node_cursor: nodeCount > 200 ? 'detail-start-201-default50' : null,
  }
}
export function taskPage(): TaskPage {
  return {
    items: [{ ...taskFixture(), nodes: [], next_node_cursor: 'list-start-first-default50' }],
    next_cursor: 'task-list-page2',
    data_as_of: '2026-11-08T00:00:00.000Z',
    scope_version: 1,
  }
}
export function nodePage(start = 201, count = 50): TaskPage<TaskNode> {
  return {
    items: Array.from({ length: count }, (_, i) => taskNode(start + i)),
    next_cursor: start + count <= 275 ? 'node-page-next' : null,
    data_as_of: '2026-11-08T00:00:00.000Z',
    scope_version: 1,
  }
}
