import type { ListOrderParams } from '#/api/requirement';

export type MaterialTaskFilters = Pick<
  ListOrderParams,
  | 'project'
  | 'status'
  | 'demand_type'
  | 'department'
  | 'creator'
  | 'country'
  | 'is_green_material'
> & {
  keyword: string;
  priority: string[];
  designers: string[];
  creative_planners: string[];
  sort: string;
  order: 'asc' | 'desc';
};

export function emptyMaterialTaskFilters(): MaterialTaskFilters {
  return {
    keyword: '',
    priority: [],
    designers: [],
    creative_planners: [],
    sort: 'submitted_at',
    order: 'desc',
  };
}

export function copyMaterialTaskFilters(
  filters: MaterialTaskFilters,
): MaterialTaskFilters {
  return {
    ...filters,
    priority: [...filters.priority],
    designers: [...filters.designers],
    creative_planners: [...filters.creative_planners],
  };
}

export const materialStatusOptions = [
  { label: '待分配', value: 'pending_assign' },
  { label: '制作中', value: 'in_production' },
  { label: '部分完成', value: 'partially_completed' },
  { label: '待验收', value: 'pending_accept' },
  { label: '待返工', value: 'rejected' },
  { label: '已验收', value: 'accepted' },
  { label: '已入库', value: 'archived' },
  { label: '已驳回', value: 'demand_rejected' },
  { label: '已暂停', value: 'paused' },
  { label: '已取消', value: 'cancelled' },
];

export const materialQuickStatuses: Record<
  string,
  { label: string; value: string }
> = {
  paused: { label: '已暂停', value: 'paused' },
  cancelled: { label: '已取消', value: 'cancelled' },
  acceptance: { label: '待验收', value: 'pending_acceptance' },
  completed: { label: '已完成', value: 'completed' },
  failed: { label: '已驳回', value: 'failed' },
  pending_assignment: { label: '待分配', value: 'pending_assignment' },
  submission: { label: '待提交', value: 'submission' },
};
