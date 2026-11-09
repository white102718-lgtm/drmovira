<script setup lang="ts">
import { ref, watch } from 'vue';

import { Modal, Spin } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getMaterialOrderChangelog } from '#/api/requirement';
import { ORDER_STATUS_MAP } from '#/api/requirement/all';
import type { ChangeLogEntry } from '#/api/requirement/all';
import facebookCountries from '#/data/facebook_countries.json';
import languages from '#/data/languages.json';
import Button from 'ant-design-vue/es/button';
import AntDataTable from '#/components/ui/AntDataTable.vue';

const FOLD_THRESHOLD = 4;

const changeColumns = [
  { dataIndex: 'field', key: 'field', title: '字段', width: '18%' },
  { dataIndex: 'old', key: 'old', title: '修改前', width: '41%' },
  { dataIndex: 'new', key: 'new', title: '修改后', width: '41%' },
];

const FIELD_LABEL_MAP: Record<string, string> = {
  title: '需求标题',
  project: '项目',
  demand_type: '类型',
  quantity: '交付数量',
  sizes: '素材尺寸',
  priority: '优先级',
  department: '部门',
  language: '语种',
  is_green_material: '绿通素材',
  expected_delivery_at: '预期交付时间',
  product_info: '官方台子名称',
  tags: '标签',
  requirements: '子需求',
  assignments: '分配记录',
  assignment_event: '分配流程',
  review_event: '验收记录',
  task_scope: '任务归属',
  responsible_department_id: '负责部门',
  cc_user_id: '抄送人',
  references: '参考资料',
  status: '状态',
};

const PRIORITY_LABEL_MAP: Record<string, string> = {
  P0: 'P0 突发紧急',
  P1: 'P1 常规/迭代',
  P2: 'P2 素材储备',
};

const DEMAND_TYPE_MAP: Record<string, string> = {
  video: '视频',
  image: '图片',
};

const countryNameMap = Object.fromEntries(
  (facebookCountries as { code: string; name: string }[]).map((c) => [
    c.code,
    c.name,
  ]),
);

const languageNameMap = Object.fromEntries(
  (languages as { label: string; value: string }[]).map((l) => [
    l.value,
    l.label,
  ]),
);

function formatTagsValue(value: any): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '无';
  const parts: string[] = [];
  const country: string[] = Array.isArray(value.country) ? value.country : [];
  const theme: string[] = Array.isArray(value.theme) ? value.theme : [];
  const gameplay: string[] = Array.isArray(value.gameplay)
    ? value.gameplay
    : [];
  if (country.length)
    parts.push(
      `国家：${country.map((c) => countryNameMap[c] ?? c).join('、')}`,
    );
  if (theme.length) parts.push(`题材：${theme.join('、')}`);
  if (gameplay.length) parts.push(`玩法：${gameplay.join('、')}`);
  return parts.length ? parts.join('；') : '无';
}

function formatValue(field: string, value: any): string {
  if (value === null || value === undefined || value === '') return '无';
  if (field === 'assignments') {
    return `${value.designer_name || ''} · ${value.quantity || 0} 条 · 创意策划：${value.creative_planner_name || '未指定'}${value.remark ? ` · ${value.remark}` : ''}`;
  }
  if (field === 'requirements') {
    return typeof value === 'object'
      ? `${value.seq_label ?? ''}：${value.description ?? ''}（${value.quantity ?? 0} 个）`
      : String(value);
  }
  if (field === 'references') {
    if (!Array.isArray(value) || value.length === 0) return '无';
    return (
      value
        .map((v: any) => v.name ?? v.basename ?? '')
        .filter(Boolean)
        .join('、') || `${value.length} 项`
    );
  }
  if (field === 'tags') {
    return formatTagsValue(value);
  }
  if (field === 'demand_type') {
    return DEMAND_TYPE_MAP[String(value)] ?? String(value);
  }
  if (field === 'language') {
    return languageNameMap[String(value)] ?? String(value);
  }
  if (field === 'is_green_material') {
    return value === true ? '是' : value === false ? '否' : String(value);
  }
  if (field === 'status') {
    return ORDER_STATUS_MAP[String(value)] ?? String(value);
  }
  if (field === 'priority') {
    return PRIORITY_LABEL_MAP[String(value)] ?? String(value);
  }
  if (field === 'expected_delivery_at') {
    return dayjs(value).isValid()
      ? dayjs(value).format('YYYY-MM-DD')
      : String(value);
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? '无' : value.join('、');
  }
  return String(value);
}

const props = defineProps<{
  modelValue: boolean;
  orderId: string;
  orderNo: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [boolean];
}>();

const loading = ref(false);
const logs = ref<ChangeLogEntry[]>([]);
const expandedIds = ref<Set<string>>(new Set());

watch(
  () => props.modelValue,
  async (val) => {
    if (!val || !props.orderId) return;
    loading.value = true;
    expandedIds.value = new Set();
    try {
      logs.value = await getMaterialOrderChangelog(props.orderId);
    } catch {
      logs.value = [];
    } finally {
      loading.value = false;
    }
  },
);

function formatTime(iso: string) {
  return dayjs(iso).format('YYYY-MM-DD HH:mm');
}

function toggleExpand(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id);
  } else {
    expandedIds.value.add(id);
  }
  expandedIds.value = new Set(expandedIds.value);
}

function visibleChanges(entry: ChangeLogEntry) {
  const changes =
    expandedIds.value.has(entry.id) || entry.changes.length < FOLD_THRESHOLD
      ? entry.changes
      : entry.changes.slice(0, 5);
  return changes.map((change, index) => ({
    ...change,
    key: `${change.field}-${change.assignment_id || change.req_id || index}`,
  }));
}
</script>

<template>
  <Modal
    :open="modelValue"
    :title="`修改记录 — ${orderNo}`"
    :footer="null"
    width="1000px"
    :body-style="{ maxHeight: '65vh', overflowY: 'auto' }"
    @cancel="emit('update:modelValue', false)"
  >
    <div v-if="loading" class="flex items-center justify-center py-12">
      <Spin />
    </div>

    <div
      v-else-if="!logs.length"
      class="flex items-center justify-center py-12 text-sm text-gray-400"
    >
      暂无修改记录
    </div>

    <div v-else class="pl-[22px]">
      <div
        v-for="entry in logs"
        :key="entry.id"
        class="relative pb-7 before:absolute before:bottom-0 before:left-[-12px] before:top-0 before:w-px before:bg-gray-200 first:before:top-[11px] last:pb-0 last:before:hidden"
      >
        <div
          class="bg-foreground ring-muted absolute left-[-17px] top-[6px] h-[10px] w-[10px] rounded-full border-2 border-white ring-2"
        />

        <div class="mb-3 flex items-center gap-2">
          <span class="text-sm text-gray-400">{{
            formatTime(entry.created_at)
          }}</span>
          <span class="text-base font-medium text-gray-600">{{
            entry.operator
          }}</span>
        </div>

        <AntDataTable
          :columns="changeColumns"
          :data="visibleChanges(entry)"
          :paginate="false"
          row-key="key"
        >
          <template #cell-field="{ record }">
            <span class="text-muted-foreground font-medium">
              {{ FIELD_LABEL_MAP[record.field] ?? record.field }}
            </span>
          </template>
          <template #cell-old="{ record }">
            <span class="text-muted-foreground line-through">
              {{ formatValue(record.field, record.old) }}
            </span>
          </template>
          <template #cell-new="{ record }">
            <span class="text-foreground">
              {{ formatValue(record.field, record.new) }}
            </span>
          </template>
        </AntDataTable>

        <table v-if="false" class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-gray-50">
              <th
                class="w-[12%] border border-gray-100 px-3 py-2 text-left font-medium text-gray-400"
              >
                字段
              </th>
              <th
                class="w-[39%] border border-gray-100 px-3 py-2 text-left font-medium text-gray-400"
              >
                修改前
              </th>
              <th
                class="w-[39%] border border-gray-100 px-3 py-2 text-left font-medium text-gray-400"
              >
                修改后
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="change in visibleChanges(entry)"
              :key="change.field"
              class="transition-colors hover:bg-gray-50/60"
            >
              <td
                class="border border-gray-100 px-3 py-2 font-medium text-gray-500"
              >
                {{ FIELD_LABEL_MAP[change.field] ?? change.field }}
              </td>
              <td
                class="border border-gray-100 px-3 py-2 text-gray-400 line-through"
              >
                {{ formatValue(change.field, change.old) }}
              </td>
              <td class="border border-gray-100 px-3 py-2 text-gray-800">
                {{ formatValue(change.field, change.new) }}
              </td>
            </tr>
          </tbody>
        </table>

        <Button
          v-if="entry.changes.length >= FOLD_THRESHOLD"
          class="mt-2"
          size="small"
          type="text"
          @click="toggleExpand(entry.id)"
        >
          <span v-if="!expandedIds.has(entry.id)"
            >展开全部 {{ entry.changes.length }} 项</span
          >
          <span v-else>收起</span>
        </Button>

        <button
          v-if="false"
          class="mt-2 flex items-center gap-1 text-sm text-gray-400 transition-colors hover:text-gray-600"
          @click="toggleExpand(entry.id)"
        >
          <span v-if="!expandedIds.has(entry.id)"
            >展开全部 {{ entry.changes.length }} 项 ▾</span
          >
          <span v-else>收起 ▴</span>
        </button>
      </div>
    </div>
  </Modal>
</template>
