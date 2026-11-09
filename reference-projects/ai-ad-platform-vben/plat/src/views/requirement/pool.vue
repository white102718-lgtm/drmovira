<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  message,
  Popconfirm,
  Popover as APopover,
  Textarea,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';

dayjs.extend(isoWeek);
import {
  batchRejectMaterialOrders,
  getMaterialOrderStats,
} from '#/api/requirement';

import MaterialAssignmentModal from '#/views/workbench/components/MaterialAssignmentModal.vue';
import AnimatedCount from '#/views/components/AnimatedCount.vue';
import BaseButton from '#/views/components/BaseButton.vue';

import ChangeLogModal from './components/ChangeLogModal.vue';
import OrderTable from './components/OrderTable.vue';
import WorkspaceTabs from './components/WorkspaceTabs.vue';
import { useOrderWorkspace } from './composables/useOrderWorkspace';
import CreateView from './create.vue';

const route = useRoute();
const ws = useOrderWorkspace({
  acceptStatuses: [
    'partially_completed',
    'is_complete',
    'pending_accept',
    'accepted',
    'archived',
  ],
  onBackToList: () => {
    orderTableRef.value?.gridApi.grid.commitProxy('query');
    loadStats();
  },
});

const userStore = useUserStore();
const isAdmin = computed(
  () => userStore.userInfo?.roles?.includes('admin') ?? false,
);

// ==================== 统计卡片 ====================
interface RequirementPoolStatCard {
  decimals?: number;
  label: string;
  numVal: number;
  sub: string;
  suffix?: string;
  unit: string;
  valueClass?: string;
}

const statCards = ref<RequirementPoolStatCard[]>([
  { label: '待分配', numVal: 0, unit: '条', sub: '' },
  { label: '制作中', numVal: 0, unit: '条', sub: '' },
  { label: '待验收', numVal: 0, unit: '条', sub: '' },
]);

// ==================== SLA 预警 ====================
const showSlaAlert = ref(false);
const slaItems = ref<{ id: string; rawId: string; remain: string }[]>([]);

// ==================== 分配浮窗 ====================
const orderTableRef = ref<InstanceType<typeof OrderTable>>();
const assignVisible = ref(false);
const assignmentQueue = ref<string[]>([]);
const assignmentOrderId = computed(() => assignmentQueue.value[0]);
function openAssignPanel(row: { _rawId: string }, event: MouseEvent) {
  event.stopPropagation();
  assignmentQueue.value = [row._rawId];
  assignVisible.value = true;
}
async function onAssigned() {
  await orderTableRef.value?.gridApi.grid.commitProxy('query');
  await loadStats();
  assignmentQueue.value = assignmentQueue.value.slice(1);
  if (assignmentQueue.value.length) {
    message.info(`继续分配下一张工单，剩余 ${assignmentQueue.value.length} 张`);
    await nextTick();
    assignVisible.value = true;
  }
}
watch(
  () => route.query.focusOrderId,
  (value) => {
    const id = Array.isArray(value) ? value[0] : value;
    if (id) {
      assignmentQueue.value = [id];
      assignVisible.value = true;
    }
  },
  { immediate: true },
);

// ==================== 修改记录 ====================
const changeLogVisible = ref(false);
const changeLogOrderId = ref('');
const changeLogOrderNo = ref('');

function openChangeLog(row: any) {
  changeLogOrderId.value = row._rawId;
  changeLogOrderNo.value = row.id ?? row._rawId;
  changeLogVisible.value = true;
}

// ==================== 驳回 ====================
const rejecting = ref<string | null>(null);
const rejectPopOpenId = ref<null | string>(null);
const rejectReason = ref('');

async function handleReject(row: any) {
  rejecting.value = row._rawId;
  try {
    await batchRejectMaterialOrders([
      { id: row._rawId, reason: rejectReason.value.trim() },
    ]);
    message.success('已驳回');
    rejectPopOpenId.value = null;
    orderTableRef.value!.gridApi.grid.commitProxy('query');
  } catch {
  } finally {
    rejecting.value = null;
  }
}

// ==================== 批量驳回 ====================
const batchRejecting = ref(false);
const batchRejectRecords = ref<any[]>([]);
const batchRejectPopconfirmOpen = ref(false);
const batchRejectReason = ref('');

function onBatchRejectReasonChange(e: Event) {
  batchRejectReason.value = (e.target as HTMLTextAreaElement).value ?? '';
}

function onRejectReasonChange(e: Event) {
  rejectReason.value = (e.target as HTMLTextAreaElement).value ?? '';
}

function handleBatchReject() {
  const records: any[] = orderTableRef.value!.gridApi.grid.getCheckboxRecords();
  if (!records.length) {
    message.warning('请先勾选需要驳回的工单');
    return;
  }
  const rejectableRecords = records.filter((r) =>
    ['pending_assign', 'in_production'].includes(r.status),
  );
  if (!rejectableRecords.length) {
    message.warning(
      '所选工单中无可驳回的工单（仅"待分配"或"制作中"状态可驳回）',
    );
    return;
  }
  batchRejectRecords.value = rejectableRecords;
  batchRejectPopconfirmOpen.value = true;
}

async function handleBatchRejectConfirm() {
  batchRejecting.value = true;
  try {
    const { count } = await batchRejectMaterialOrders(
      batchRejectRecords.value.map((r) => ({
        id: r._rawId,
        reason: batchRejectReason.value.trim(),
      })),
    );
    message.success(`已成功驳回 ${count} 条工单`);
    orderTableRef.value!.gridApi.grid.commitProxy('query');
  } catch {
  } finally {
    batchRejecting.value = false;
    batchRejectPopconfirmOpen.value = false;
  }
}

// 批量选择后逐单填写分配明细，避免把不同子需求误用同一份人员和数量。
function handleBatchAssign(event: MouseEvent) {
  event.stopPropagation();
  const records = orderTableRef.value?.gridApi.grid.getCheckboxRecords() ?? [];
  assignmentQueue.value = records
    .filter((row: { canAssign: boolean }) => row.canAssign)
    .map((row: { _rawId: string }) => row._rawId);
  if (!assignmentQueue.value.length) {
    message.warning('请先勾选可分配的工单');
    return;
  }
  assignVisible.value = true;
}

// ==================== 统计数据 ====================
async function loadStats() {
  try {
    const statsRes = await getMaterialOrderStats({});
    const s = statsRes as any;
    if (s) {
      statCards.value[0]!.numVal = s.status_counts?.pending_assign ?? 0;
      statCards.value[1]!.numVal =
        (s.status_counts?.in_production ?? 0) +
        (s.status_counts?.assigned ?? 0);
      statCards.value[2]!.numVal = s.status_counts?.pending_accept ?? 0;
      const warnings: {
        id: string;
        order_no: string;
        remaining_hours: number;
      }[] = s.warnings ?? [];
      slaItems.value = warnings.map((w) => ({
        id: w.order_no,
        rawId: w.id,
        remain:
          w.remaining_hours >= 0
            ? `剩 ${w.remaining_hours}h`
            : `超时 ${Math.abs(w.remaining_hours)}h`,
      }));
      showSlaAlert.value = slaItems.value.length > 0;
    }
  } catch {}
}

onMounted(() => {
  loadStats();
});
</script>

<template>
  <Page
    auto-content-height
    class="bg-gray-50"
    content-class="requirement-workspace-scroll pt-0"
  >
    <div class="flex items-start gap-4">
      <WorkspaceTabs :ws="ws" :show-form="isAdmin" list-label="需求池" />

      <!-- 右侧内容区 -->
      <div class="min-w-0 flex-1">
        <div v-show="ws.view === 'list'" class="space-y-4">
          <div class="flex items-center justify-between">
            <h1 class="text-xl font-bold text-gray-900">需求池调度</h1>

            <!-- SLA 预警入口 -->
            <APopover
              v-if="showSlaAlert"
              trigger="click"
              placement="bottomRight"
              :overlay-style="{ width: '320px' }"
            >
              <template #default>
                <button
                  class="flex items-center gap-1.5 rounded-md border border-[#fbd4d5] bg-[#fef2f2] px-2 py-1 text-sm font-medium text-[#d43130] transition-colors hover:bg-[#fde8e8]"
                >
                  <span
                    class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-sm bg-[#d43130] text-xs font-bold text-white"
                    >!</span
                  >
                  {{ slaItems.length }} 条 SLA 风险
                  <span class="text-xs opacity-70">▼</span>
                </button>
              </template>
              <template #content>
                <div class="mb-2 text-sm font-semibold text-gray-700">
                  SLA 预警明细
                </div>
                <ul class="max-h-64 overflow-y-auto">
                  <li
                    v-for="item in slaItems"
                    :key="item.id"
                    class="flex items-center justify-between border-b border-gray-100 py-1.5 text-sm last:border-0"
                  >
                    <span class="font-medium text-gray-700">{{ item.id }}</span>
                    <span
                      class="rounded px-1.5 py-0.5 text-xs"
                      :class="
                        item.remain.startsWith('超时')
                          ? 'bg-red-100 text-red-600'
                          : 'bg-yellow-50 text-yellow-600'
                      "
                      >{{ item.remain }}</span
                    >
                  </li>
                </ul>
                <div
                  class="mt-2 flex justify-end border-t border-gray-100 pt-2"
                >
                  <button
                    class="text-xs text-gray-400 hover:text-gray-600"
                    @click="showSlaAlert = false"
                  >
                    忽略全部
                  </button>
                </div>
              </template>
            </APopover>
          </div>

          <!-- 统计卡片 -->
          <div class="grid grid-cols-3 gap-3">
            <div
              v-for="card in statCards"
              :key="card.label"
              class="rounded-xl border border-gray-100 bg-white p-4"
            >
              <div class="mb-2 text-sm text-gray-500">{{ card.label }}</div>
              <div class="flex items-baseline gap-1">
                <AnimatedCount
                  :value="card.numVal"
                  :decimals="card.decimals ?? 0"
                  :suffix="card.suffix ?? ''"
                  class="text-[calc(var(--adpulse-page-title-size)+3px)] font-semibold"
                  :class="card.valueClass ?? 'text-gray-900'"
                />
                <span v-if="card.unit" class="text-base text-gray-500">{{
                  card.unit
                }}</span>
              </div>
            </div>
          </div>

          <!-- 筛选栏 + 表格 -->
          <OrderTable
            ref="orderTableRef"
            persist-key="requirement_pool_filters"
            view="pool"
            :show-sort-select="true"
            :show-country="true"
            :show-green-material="true"
            :show-designer="true"
            :show-operator="true"
            :show-department="true"
            :exclude-statuses="['is_submit', 'is_complete']"
            :table-height-offset="410"
            :action-width="270"
            sort-by="submitted_at"
            sort-label="提交时间"
            time-field="submitted_at"
            default-status="pending_assign"
            @filters-change="loadStats"
            @refresh="loadStats"
          >
            <template #filter-actions>
              <BaseButton @click="handleBatchAssign($event)"
                >批量分配</BaseButton
              >
              <Popconfirm
                :open="batchRejectPopconfirmOpen"
                ok-text="驳回"
                cancel-text="取消"
                ok-type="danger"
                :ok-button-props="{ disabled: !batchRejectReason.trim() }"
                @confirm="handleBatchRejectConfirm"
                @cancel="batchRejectPopconfirmOpen = false"
                @update:open="
                  (v) => {
                    if (!v) batchRejectPopconfirmOpen = false;
                  }
                "
              >
                <template #title
                  >确定驳回所选
                  {{ batchRejectRecords.length }} 条工单吗？</template
                >
                <template #description>
                  <Textarea
                    :value="batchRejectReason"
                    :auto-size="{ minRows: 2, maxRows: 5 }"
                    placeholder="请输入驳回理由"
                    style="
                      width: 220px;
                      margin-top: 4px;
                      border-radius: 4px;
                      padding: 4px;
                    "
                    @change="onBatchRejectReasonChange"
                  />
                </template>
                <BaseButton :loading="batchRejecting" @click="handleBatchReject"
                  >批量驳回</BaseButton
                >
              </Popconfirm>
            </template>
            <template #action="{ row }">
              <div class="flex items-center justify-center gap-2">
                <button
                  v-if="row.canAssign"
                  class="text-sm font-medium text-blue-500 hover:text-blue-700"
                  @click="openAssignPanel(row, $event)"
                >
                  分配
                </button>
                <Popconfirm
                  v-if="row.canAssign"
                  :open="rejectPopOpenId === row._rawId"
                  ok-text="驳回"
                  ok-type="danger"
                  cancel-text="取消"
                  :ok-button-props="{ disabled: !rejectReason.trim() }"
                  @confirm="handleReject(row)"
                  @update:open="
                    (v) => {
                      if (!v) rejectPopOpenId = null;
                    }
                  "
                >
                  <template #title
                    >确定驳回「{{ row.title }}」需求吗？</template
                  >
                  <template #description>
                    <Textarea
                      :value="rejectReason"
                      :auto-size="{ minRows: 2, maxRows: 5 }"
                      placeholder="请输入驳回理由"
                      style="
                        width: 220px;
                        margin-top: 4px;
                        border-radius: 4px;
                        padding: 4px;
                      "
                      @change="onRejectReasonChange"
                    />
                  </template>
                  <button
                    class="text-sm font-medium text-red-500 hover:text-red-700"
                    :disabled="rejecting === row._rawId"
                    @click="rejectPopOpenId = row._rawId"
                  >
                    驳回
                  </button>
                </Popconfirm>
                <button
                  v-if="isAdmin"
                  class="text-sm font-medium text-blue-500 hover:text-blue-700"
                  @click="ws.openForm('edit', row)"
                >
                  编辑
                </button>
                <button
                  class="text-sm font-medium text-gray-500 hover:text-gray-700"
                  @click="openChangeLog(row)"
                >
                  修改记录
                </button>
                <a
                  :href="ws.viewHref('detail', row)"
                  @click="
                    (e) => {
                      if (e.ctrlKey || e.metaKey || e.shiftKey) return;
                      e.preventDefault();
                      ws.openDetail(row, 'detail');
                    }
                  "
                >
                  <button
                    class="text-sm font-medium text-blue-500 hover:text-blue-700"
                  >
                    需求详情
                  </button>
                </a>
                <a
                  :href="ws.viewHref('accept', row)"
                  @click="
                    (e) => {
                      if (e.ctrlKey || e.metaKey || e.shiftKey) return;
                      e.preventDefault();
                      ws.openDetail(row, 'accept');
                    }
                  "
                >
                  <button
                    v-if="
                      [
                        'partially_completed',
                        'is_complete',
                        'pending_accept',
                        'accepted',
                        'archived',
                      ].includes(row.status)
                    "
                    class="text-sm font-medium text-blue-500 hover:text-blue-700"
                  >
                    验收详情
                  </button>
                </a>
              </div>
            </template>
          </OrderTable>
        </div>

        <!-- 需求详情（只读表单） -->
        <CreateView
          v-if="ws.detailOpen && ws.mountedDetail"
          v-show="ws.view === 'detail'"
          :key="`detail-${ws.currentId}`"
          embedded
          mode="readonly"
          :id="ws.currentId"
          @go-accept="ws.openAcceptTab()"
          @loaded="ws.onDetailLoaded"
        />

        <!-- 编辑（admin） -->
        <CreateView
          v-if="isAdmin && ws.formOpen"
          v-show="ws.view === 'form'"
          :key="`form-${ws.formGen}`"
          embedded
          mode="edit"
          :id="ws.formId || undefined"
          @back="ws.handleFormDone()"
          @loaded="ws.onFormLoaded"
        />
      </div>
    </div>

    <!-- 修改记录弹窗 -->
    <ChangeLogModal
      v-model="changeLogVisible"
      :order-id="changeLogOrderId"
      :order-no="changeLogOrderNo"
    />

    <!-- 分配浮窗 -->
    <MaterialAssignmentModal
      v-model:open="assignVisible"
      :order-id="assignmentOrderId"
      @assigned="onAssigned"
    />
  </Page>
</template>

<style scoped>
:deep(.vxe-table .vxe-body--row:hover td) {
  background-color: #f9fafb !important;
}
</style>
