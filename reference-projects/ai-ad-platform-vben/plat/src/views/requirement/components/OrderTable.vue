<script setup lang="ts">
import type { OrderFilters } from './OrderFilterBar.vue';

import type { VxeGridProps } from '#/adapter/vxe-table';

import { h, onMounted, onUnmounted, reactive, ref, watch } from 'vue';

import { message, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { pushMaterialsToFbApi } from '#/api';
import { listMaterialOrders, ORDER_STATUS_MAP } from '#/api/requirement';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';

import { usePersistedFilters } from '../composables/usePersistedFilters';
import {
  buildTagLabels,
  demandTypeMap,
  mapDeadline,
  priorityConfig,
  renderDeadlineCell,
  renderTagRow,
} from '../utils';
import OrderFilterBar from './OrderFilterBar.vue';

const props = defineProps<{
  actionWidth?: number;
  defaultStatus?: string;
  excludeStatuses?: string[];
  extraParams?: Record<string, any>;
  persistKey: string;
  /** Local presentation predicate; production API and existing query shape stay unchanged. */
  rowPredicate?: (row: Record<string, unknown>) => boolean;
  showCountry?: boolean;
  showDeadlineSort?: boolean;
  showDepartment?: boolean;
  showDesigner?: boolean;
  showGreenMaterial?: boolean;
  showMaterials?: boolean;
  showOperator?: boolean;
  showSortSelect?: boolean;
  showUploadProgress?: boolean;
  sortBy?: string;
  sortLabel?: string;
  tableHeightOffset?: number;
  timeField?: string;
  view?: string;
}>();

const emit = defineEmits<{
  filtersChange: [filters: OrderFilters];
  refresh: [];
  selectionChange: [records: any[]];
}>();

const timeLabelMap: Record<string, string> = {
  created_at: '创建时间',
  submitted_at: '提交时间',
};

const retryPushingId = ref<number | string | undefined>();

const { initialFilters, save } = usePersistedFilters(
  props.persistKey,
  props.defaultStatus,
  props.sortBy,
);
const orderFilters = ref<OrderFilters>(initialFilters);
let querySeq = 0;
let lastValidResult: { items: any[]; total: number } = { items: [], total: 0 };
let requestedQuerySeq = 0;

// ==================== 响应式高度（支持 offset prop 动态变化）====================
const gridHeight = ref(window.innerHeight - (props.tableHeightOffset ?? 260));

function getOrderStatusTagColor(status: string) {
  if (['demand_rejected', 'rejected'].includes(status)) return 'error';
  if (['accepted', 'archived', 'draft', 'is_complete'].includes(status)) {
    return 'default';
  }
  return 'processing';
}

function normalizeRequirements(item: Record<string, any>) {
  if (Array.isArray(item.requirements)) return item.requirements;
  return [];
}

function handleResize() {
  gridHeight.value = window.innerHeight - (props.tableHeightOffset ?? 260);
}

onMounted(() => window.addEventListener('resize', handleResize));
onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
});

watch(
  () => props.tableHeightOffset,
  (offset) => {
    gridHeight.value = window.innerHeight - (offset ?? 260);
  },
);

// ==================== 列定义 ====================
function buildColumns(): NonNullable<VxeGridProps['columns']> {
  const cols: NonNullable<VxeGridProps['columns']> = [
    { type: 'checkbox', width: 46 },
    {
      title: '需求 ID',
      field: 'id',
      width: 160,
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'text-sm text-gray-500' }, row.id),
        ],
      },
    },
    {
      title: '需求标题',
      field: 'title',
      align: 'left',
      minWidth: 220,
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'py-1' }, [
            h(
              'div',
              { class: 'text-base font-semibold text-gray-900 leading-snug' },
              row.title,
            ),
            renderTagRow(row.tags),
          ]),
        ],
      },
    },
    ...(props.showGreenMaterial
      ? [
          {
            title: '是否绿通',
            field: 'is_green_material',
            width: 90,
            align: 'center' as const,
            slots: {
              default: ({ row }: any) => {
                if (
                  row.is_green_material !== true &&
                  row.is_green_material !== false
                )
                  return [];
                return [
                  h(
                    'span',
                    { class: 'text-sm text-gray-700' },
                    row.is_green_material ? '绿通' : '非绿通',
                  ),
                ];
              },
            },
          },
        ]
      : []),
    {
      title: '优先级',
      field: 'priority',
      width: 60,
      align: 'center',
      slots: {
        default: ({ row }: any) => {
          const cfg = priorityConfig[row.priority] ?? priorityConfig.P2;
          if (!cfg) return [];
          return [
            h(
              'span',
              {
                class:
                  'inline-flex items-center justify-center text-sm font-bold px-2 py-0.5 rounded',
                style: { backgroundColor: cfg.bg, color: cfg.color },
              },
              row.priority,
            ),
          ];
        },
      },
    },
    {
      title: '类型',
      field: 'type',
      width: 60,
      align: 'center',
      slots: {
        default: ({ row }: any) => {
          const color = row.type === 'image' ? 'blue' : 'purple';
          return [
            h(Tag, { color }, () => `${demandTypeMap[row.type] ?? row.type}`),
          ];
        },
      },
    },
    {
      title: '数量',
      field: 'count',
      width: 60,
      align: 'center',
      slots: {
        default: ({ row }: any) => {
          return [h(Tag, { type: 'default' }, () => `${row.count}`)];
        },
      },
    },
    {
      title: '需求方',
      field: 'requester',
      width: 80,
      align: 'center',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center justify-center gap-1.5' }, [
            h('span', { class: 'text-sm text-gray-700' }, row.requester),
          ]),
        ],
      },
    },
  ];

  if (props.showDepartment) {
    const requesterIdx = cols.findIndex(
      (c) => (c as any).field === 'requester',
    );
    cols.splice(requesterIdx, 0, {
      title: '部门',
      field: 'department',
      width: 90,
      align: 'center',
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'text-sm text-gray-600' }, row.department || '-'),
        ],
      },
    });
  }

  if (props.showDesigner) {
    cols.push(
      {
        title: '创意策划',
        field: 'creative_planners',
        minWidth: 70,
        align: 'center',
        slots: {
          default: ({ row }: any) => {
            const planners: string[] = row.creative_planners ?? [];
            return planners.length > 0
              ? [
                  h(
                    'span',
                    { class: 'text-sm text-gray-700' },
                    planners.join('、'),
                  ),
                ]
              : [h('span', { class: 'text-sm text-gray-400' }, '未分配')];
          },
        },
      },
      {
        title: '素材师',
        field: 'creator',
        minWidth: 60,
        align: 'center',
        slots: {
          default: ({ row }: any) => {
            const designers: string[] = row.designers ?? [];
            if (designers.length === 0) {
              return [h('span', { class: 'text-sm text-gray-400' }, '未分配')];
            }
            const completed: string[] = row.completed_designers ?? [];
            const nodes = [];
            for (const [index, name] of designers.entries()) {
              nodes.push(h('span', { class: 'text-sm text-gray-700' }, name));
              if (
                row.status === 'partially_completed' &&
                completed.includes(name)
              ) {
                nodes.push(
                  h(
                    'span',
                    {
                      style:
                        'color: #22c55e; font-size: 0.875rem; margin-left: 2px;',
                    },
                    '✔\uFE0E',
                  ),
                );
              }
              if (index < designers.length - 1) {
                nodes.push(h('span', { class: 'text-gray-400' }, '、'));
              }
            }
            return nodes;
          },
        },
      },
    );
  }

  cols.push(
    ...(props.timeField
      ? [
          {
            title: timeLabelMap[props.timeField] ?? props.timeField,
            field: props.timeField,
            width: 120,
            align: 'center' as const,
            slots: {
              default: ({ row }: any) => {
                const val = row[props.timeField!];
                return val ? val.slice(0, 16).replace('T', ' ') : '';
              },
            },
          },
        ]
      : []),
    {
      title: '交付时间',
      field: 'deadline',
      width: 90,
      align: 'center',
      slots: {
        default: ({ row }: any) => renderDeadlineCell(row),
      },
    },
    {
      title: '状态',
      field: 'status',
      width: 85,
      align: 'center',
      slots: {
        default: ({ row }: any) => [
          h(
            Tag,
            {
              color: getOrderStatusTagColor(row.status),
            },
            () => ORDER_STATUS_MAP[row.status] ?? row.status,
          ),
        ],
      },
    },
    ...(orderFilters.value.status === 'demand_rejected'
      ? [
          {
            title: '驳回理由',
            field: 'reject_reason',
            minWidth: 160,
            align: 'left' as const,
            slots: {
              default: ({ row }: any) => [
                h(OverflowTooltip, { text: row.reject_reason ?? '' }),
              ],
            },
          },
        ]
      : []),
    ...(props.showUploadProgress
      ? [
          {
            title: '上传状态',
            field: 'fb_push_status',
            width: 150,
            align: 'center' as const,
            slots: {
              header: () => [
                h('span', { title: '上传到FB的素材状态' }, '上传状态'),
              ],
              default: ({ row }: any) => {
                const statusMap: Record<
                  string,
                  { color: string; label: string }
                > = {
                  processing: { label: '进行中', color: 'processing' },
                  done: { label: '成功', color: 'success' },
                  partial: { label: '部分成功', color: 'warning' },
                  failed: { label: '失败', color: 'error' },
                };
                const s = statusMap[row.fb_push_status];
                if (!s)
                  return [h('span', { class: 'text-sm text-gray-400' }, '-')];
                const nodes: any[] = [
                  h(Tag, { color: s.color }, () => s.label),
                ];
                if (
                  row.fb_push_status === 'partial' ||
                  row.fb_push_status === 'failed'
                ) {
                  const isRetrying = retryPushingId.value === row._rawId;
                  nodes.push(
                    h(
                      'button',
                      {
                        class:
                          'text-xs text-blue-500 hover:text-blue-700 flex items-center gap-0.5 disabled:opacity-50 disabled:cursor-not-allowed',
                        disabled: isRetrying,
                        onClick: () => !isRetrying && handleRetryPush(row),
                      },
                      [
                        isRetrying
                          ? h('span', {
                              class:
                                'icon-[ant-design--loading-outlined] animate-spin text-sm',
                            })
                          : null,
                        '重新上传',
                      ],
                    ),
                  );
                }
                return [
                  h(
                    'div',
                    { class: 'flex justify-center items-center gap-0.5' },
                    nodes,
                  ),
                ];
              },
            },
          },
        ]
      : []),
    ...(props.showMaterials
      ? [
          {
            title: '上传素材',
            field: 'materials',
            width: 200,
            align: 'center' as const,
            slots: { default: 'materials' },
          },
        ]
      : []),
    {
      title: '操作',
      width: props.actionWidth ?? 120,
      align: 'center',
      slots: { default: 'action' },
    },
  );

  return cols;
}

// ==================== VxeTable ====================
const gridOptions = reactive<VxeGridProps>({
  border: false,
  height: gridHeight.value,
  pagerConfig: { pageSize: 10, pageSizes: [10, 20, 50] },
  rowConfig: { height: 52, keyField: 'id' },
  checkboxConfig: { highlight: true },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  columns: buildColumns(),
  proxyConfig: {
    ajax: {
      query: async ({ page }: any) => {
        const currentSeq = ++querySeq;
        const capturedRequestedSeq = requestedQuerySeq;
        const f = orderFilters.value;
        const sortOption =
          f.sortOption ?? `${props.sortBy ?? 'created_at'}_desc`;
        const sortDir = sortOption.endsWith('_asc') ? 'asc' : 'desc';
        const sortField = sortOption.replace(/_(?:asc|desc)$/, '');
        const params: Record<string, any> = {
          page: page.currentPage,
          page_size: page.pageSize,
          sort: sortField,
          order: sortDir,
          ...props.extraParams,
          scope: props.view === 'assigned' ? 'OWNER' : 'ALL',
        };
        if (f.project) params.project = f.project;
        if (f.priority.length > 0) params.priority = f.priority;
        if (f.type) params.demand_type = f.type;
        // extraParams 中的 status 优先（如草稿 tab），否则使用筛选值
        if (!params.status && f.status && f.status !== 'all')
          params.status = f.status;
        if (f.operator) params.operator = f.operator;
        if (f.keyword) params.keyword = f.keyword;
        if (f.department) params.department = f.department;
        if (f.designers?.length) params.designers = f.designers;
        if (f.creativePlanners?.length)
          params.creative_planners = f.creativePlanners;
        if (f.country) params.country = f.country;
        if (f.isGreenMaterial !== undefined)
          params.is_green_material = f.isGreenMaterial === 'true';
        const res = await listMaterialOrders(params);
        if (currentSeq !== querySeq) return lastValidResult;
        const items: Record<string, unknown>[] =
          (res as any)?.items ??
          (res as any)?.results ??
          (Array.isArray(res) ? res : []);
        const visibleItems = props.rowPredicate
          ? items.filter((item) => props.rowPredicate?.(item))
          : items;
        lastValidResult = {
          items: visibleItems.map((item) => mapOrderToRow(item)),
          total: props.rowPredicate
            ? visibleItems.length
            : ((res as any)?.total ?? items.length),
        };
        if (capturedRequestedSeq !== requestedQuerySeq) {
          setTimeout(() => gridApi.grid.commitProxy('query'), 0);
        }
        return lastValidResult;
      },
    },
  },
});

function syncSelection() {
  emit('selectionChange', gridApi.grid.getCheckboxRecords());
}

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions,
  gridClass: 'p-0',
  gridEvents: { checkboxChange: syncSelection, checkboxAll: syncSelection },
});

watch(gridHeight, (h) => {
  gridApi.setGridOptions({ height: h });
});

watch(
  orderFilters,
  (val) => {
    save(val);
    emit('filtersChange', val);
    requestedQuerySeq++;
    gridApi.grid.commitProxy('query');
  },
  { deep: true },
);

watch(
  () => props.extraParams,
  () => {
    gridApi.grid.commitProxy('query');
  },
  { deep: true },
);

watch(
  () => orderFilters.value.status,
  () => {
    gridApi.setGridOptions({ columns: buildColumns() });
  },
);

// ==================== 行数据映射 ====================
function mapOrderToRow(item: any) {
  const { deadlineSub, deadlineSubClass } = mapDeadline(item.remaining_hours);
  return {
    _rawId: item.id,
    id: item.order_no ?? item.id,
    priority: item.priority ?? 'P2',
    title: item.title ?? '',
    is_green_material: item.is_green_material,
    tags: buildTagLabels(item.tags),
    type: item.demand_type ?? '',
    count: item.quantity ?? 0,
    requester: item.creator ?? '',
    assignments: Array.isArray(item.assignments)
      ? item.assignments
      : (item.task_assignments ?? []),
    designers: Array.isArray(item.designers) ? item.designers : [],
    creative_planners: Array.isArray(item.creative_planners)
      ? item.creative_planners
      : [],
    creator:
      Array.isArray(item.designers) && item.designers.length > 0
        ? item.designers.join('、')
        : '未分配',
    canAssign:
      Boolean(item.permissions?.assign) &&
      ![
        'accepted',
        'archived',
        'demand_rejected',
        'is_complete',
        'pending_accept',
      ].includes(item.status),
    completed_designers: item.completed_designers ?? [],
    created_at: item.created_at ?? '',
    submitted_at: item.submitted_at ?? '',
    deadline: item.expected_delivery_at
      ? item.expected_delivery_at.slice(0, 10)
      : '',
    deadlineSub,
    deadlineSubClass,
    status: item.status,
    reject_reason: item.reject_reason ?? '',
    department: item.department ?? '',
    upload_done_count: item.upload_done_count ?? 0,
    upload_total_count: item.upload_total_count ?? 0,
    fb_push_status: item.fb_push_status ?? '',
    fb_push_failed: Array.isArray(item.fb_push_failed)
      ? item.fb_push_failed
      : [],
    requirements: normalizeRequirements(item),
    project_id: item.project_id,
  };
}

async function handleRetryPush(row: any) {
  if (retryPushingId.value !== undefined) return;

  const failedItems: Array<{
    basename: string;
    personal_id: string;
    target_id: string;
  }> = row.fb_push_failed;

  if (!failedItems?.length) {
    message.warning('没有需要重新上传的素材');
    return;
  }

  retryPushingId.value = row._rawId;
  try {
    const results = await Promise.allSettled(
      failedItems.map((item) =>
        pushMaterialsToFbApi({
          personal_id: item.personal_id,
          target_id: item.target_id,
          basenames: [item.basename],
          order_id: String(row._rawId),
        }),
      ),
    );

    let totalSucceeded = 0;
    let totalFailed = 0;
    const failedBasenames: string[] = [];
    const skippedMsgs: string[] = [];

    for (const r of results) {
      if (r.status === 'fulfilled') {
        totalSucceeded += r.value?.succeeded ?? 0;
        totalFailed += r.value?.failed ?? 0;
        const items = (r.value?.items ?? []).filter(
          (i: any) => i.status === 'failed',
        );
        failedBasenames.push(...items.map((i: any) => i.basename));
        if (r.value?.skipped) skippedMsgs.push(r.value.skipped);
      } else {
        totalFailed += 1;
      }
    }

    if (totalFailed > 0) {
      const parts: string[] = [];
      if (totalSucceeded > 0) parts.push(`成功 ${totalSucceeded} 个`);
      parts.push(
        `失败 ${totalFailed} 个${failedBasenames.length > 0 ? `：${failedBasenames.join('、')}` : ''}`,
      );
      message.error(`上传完成，${parts.join('，')}`);
    } else if (totalSucceeded > 0) {
      message.success(`上传完成，成功 ${totalSucceeded} 个`);
    }

    if (skippedMsgs.length > 0) message.warning(skippedMsgs.join('\n'));

    gridApi.grid.commitProxy('query');
  } finally {
    retryPushingId.value = undefined;
  }
}

const refreshLoading = ref(false);

async function handleRefresh() {
  refreshLoading.value = true;
  try {
    await gridApi.grid.commitProxy('query');
  } finally {
    refreshLoading.value = false;
  }
  emit('refresh');
}

defineExpose({ gridApi, orderFilters });
</script>

<template>
  <OrderFilterBar
    v-model="orderFilters"
    :exclude-statuses="excludeStatuses"
    :sort-label="sortLabel"
    :sort-by="sortBy"
    :show-sort-select="showSortSelect"
    :show-deadline-sort="showDeadlineSort"
    :show-country="showCountry"
    :loading="refreshLoading"
    :show-operator="showOperator"
    :show-department="showDepartment"
    :show-designer="showDesigner"
    :show-green-material="showGreenMaterial"
    @refresh="handleRefresh"
  >
    <slot name="filter-actions"></slot>
  </OrderFilterBar>
  <Grid>
    <template #materials="slotProps">
      <slot name="materials" v-bind="slotProps"></slot>
    </template>
    <template #action="slotProps">
      <slot name="action" v-bind="slotProps"></slot>
    </template>
  </Grid>
</template>
