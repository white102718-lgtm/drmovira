<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { Tabs } from 'ant-design-vue';

import { getFilterOptions } from '#/api/dashboard';
import {
  getDepartmentOptions,
  getPlatformConfigList,
} from '#/api/management/platform-config';
import { getCreators } from '#/api/requirement';
import { getUserFullNames } from '#/api/system/user';
import facebookCountries from '#/data/facebook_countries.json';

import FilterDropdown from '#/views/components/FilterDropdown.vue';

export interface OrderFilters {
  project?: string;
  priority: string[];
  type?: string;
  status?: string;
  operator?: string;
  department?: string;
  keyword: string;
  sortOption: string;
  designers: string[];
  creativePlanners: string[];
  country?: string;
  isGreenMaterial?: 'true' | 'false';
}

const props = defineProps<{
  modelValue: OrderFilters;
  excludeStatuses?: string[];
  sortLabel?: string;
  sortBy?: string;
  showSortSelect?: boolean;
  showDeadlineSort?: boolean;
  showCountry?: boolean;
  loading?: boolean;
  showOperator?: boolean;
  showDepartment?: boolean;
  showDesigner?: boolean;
  showGreenMaterial?: boolean;
}>();
const emit = defineEmits<{
  'update:modelValue': [v: OrderFilters];
  refresh: [];
}>();

function update(patch: Partial<OrderFilters>) {
  emit('update:modelValue', { ...props.modelValue, ...patch });
}

const countryNameMap = Object.fromEntries(
  (facebookCountries as { code: string; name: string }[]).map((c) => [
    c.code,
    c.name,
  ]),
);

// ==================== 选项数据 ====================
const projectOptions = ref<{ label: string; value: string }[]>([]);
const projectLoading = ref(false);
const operatorOptions = ref<{ label: string; value: string }[]>([]);
const operatorLoading = ref(false);
const departmentOptions = ref<{ label: string; value: string }[]>([]);
const departmentLoading = ref(false);
const designerOptions = ref<{ label: string; value: string }[]>([]);
const designerLoading = ref(false);
const countryOptions = ref<{ label: string; value: string }[]>([]);
const countryLoading = ref(false);

const allStatusOptions = [
  { label: '待分配', value: 'pending_assign' },
  { label: '已提交', value: 'is_submit' },
  { label: '制作中', value: 'in_production' },
  { label: '部分完成', value: 'partially_completed' },
  { label: '待验收', value: 'pending_accept' },
  { label: '已验收', value: 'accepted' },
  { label: '已完成', value: 'is_complete' },
  { label: '已入库', value: 'archived' },
  { label: '已驳回', value: 'demand_rejected' },
];
const statusOptions = computed(() =>
  props.excludeStatuses?.length
    ? allStatusOptions.filter((o) => !props.excludeStatuses!.includes(o.value))
    : allStatusOptions,
);

const priorityOptions = [
  { label: 'P0', value: 'P0' },
  { label: 'P1', value: 'P1' },
  { label: 'P2', value: 'P2' },
];

const typeOptions = [
  { label: '视频', value: 'video' },
  { label: '图片', value: 'image' },
];

const greenMaterialOptions = [
  { label: '绿通', value: 'true' },
  { label: '非绿通', value: 'false' },
];

onMounted(async () => {
  projectLoading.value = true;
  try {
    const res = await getPlatformConfigList({ pageSize: 500 });
    const items: any[] = (res as any)?.data?.items ?? (res as any)?.items ?? [];
    projectOptions.value = items.map((item: any) => ({
      label: item._id,
      value: item._id,
    }));
  } catch {
  } finally {
    projectLoading.value = false;
  }

  operatorLoading.value = true;
  try {
    const names = await getUserFullNames(['operator', 'operator_leader']);
    const list: string[] = Array.isArray(names) ? names : [];
    operatorOptions.value = list.map((n) => ({ label: n, value: n }));
  } catch {
  } finally {
    operatorLoading.value = false;
  }

  departmentLoading.value = true;
  try {
    const deptNames = await getDepartmentOptions();
    const deptList: string[] = Array.isArray(deptNames) ? deptNames : [];
    departmentOptions.value = deptList.map((n) => ({ label: n, value: n }));
  } catch {
  } finally {
    departmentLoading.value = false;
  }

  designerLoading.value = true;
  getCreators()
    .then((res: any) => {
      const list: any[] = Array.isArray(res)
        ? res
        : (res?.items ?? res?.data ?? []);
      designerOptions.value = list.map((n: any) => {
        const name = typeof n === 'string' ? n : (n.full_name ?? String(n));
        return { label: name, value: name };
      });
    })
    .finally(() => {
      designerLoading.value = false;
    });

  countryLoading.value = true;
  getFilterOptions()
    .then((res: any) => {
      countryOptions.value =
        res?.region_options ??
        (res?.regions ?? []).map((code: string) => ({
          label: countryNameMap[code] ?? code,
          value: code,
        }));
    })
    .finally(() => {
      countryLoading.value = false;
    });
});

function toSingle(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? undefined : v || undefined;
}

function toGreenMaterial(
  v: string | string[] | undefined,
): 'true' | 'false' | undefined {
  const value = toSingle(v);
  return value === 'true' || value === 'false' ? value : undefined;
}

function selectStatus(val?: string) {
  update({ status: val });
}

const primaryField = computed(() => props.sortBy ?? 'created_at');

const activeSortField = computed(() =>
  props.modelValue.sortOption.replace(/_(?:asc|desc)$/, ''),
);
const activeSortDir = computed(() =>
  props.modelValue.sortOption.endsWith('_asc') ? 'asc' : 'desc',
);

// 按钮模式
function toggleSortOption(field: string) {
  if (activeSortField.value === field) {
    update({
      sortOption: `${field}_${activeSortDir.value === 'asc' ? 'desc' : 'asc'}`,
    });
  } else {
    update({ sortOption: `${field}_desc` });
  }
}

// 自定义下拉模式
const sortSelectOptions = computed(() => [
  {
    label: `${props.sortLabel ?? '创建时间'} ↓`,
    value: `${primaryField.value}_desc`,
  },
  {
    label: `${props.sortLabel ?? '创建时间'} ↑`,
    value: `${primaryField.value}_asc`,
  },
  { label: '交付时间 ↓', value: 'expected_delivery_at_desc' },
  { label: '交付时间 ↑', value: 'expected_delivery_at_asc' },
]);

function onKeywordInput(e: Event) {
  update({ keyword: (e.target as HTMLInputElement).value });
}
</script>

<template>
  <div class="rounded-md border border-gray-100 bg-white px-4 py-1.5">
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-gray-400">筛选</span>

        <!-- 项目 -->
        <FilterDropdown
          label="项目"
          :model-value="modelValue.project"
          :options="projectOptions"
          :loading="projectLoading"
          placeholder="请搜索"
          empty-text="无匹配数据"
          @update:model-value="(v) => update({ project: toSingle(v) })"
        />

        <!-- 优先级 -->
        <FilterDropdown
          label="优先级"
          :model-value="modelValue.priority"
          :options="priorityOptions"
          :multiple="true"
          @update:model-value="
            (v) => update({ priority: Array.isArray(v) ? v : [] })
          "
        />

        <!-- 是否绿通 -->
        <FilterDropdown
          v-if="showGreenMaterial"
          label="是否绿通"
          :model-value="modelValue.isGreenMaterial"
          :options="greenMaterialOptions"
          :searchable="false"
          empty-text="无匹配项"
          @update:model-value="
            (v) => update({ isGreenMaterial: toGreenMaterial(v) })
          "
        />

        <!-- 部门 -->
        <FilterDropdown
          v-if="showDepartment"
          label="部门"
          :model-value="modelValue.department"
          :options="departmentOptions"
          :loading="departmentLoading"
          placeholder="请搜索"
          empty-text="无匹配数据"
          @update:model-value="(v) => update({ department: toSingle(v) })"
        />

        <!-- 投手 -->
        <FilterDropdown
          v-if="showOperator !== false"
          label="投手"
          :model-value="modelValue.operator"
          :options="operatorOptions"
          :loading="operatorLoading"
          placeholder="请搜索"
          empty-text="无匹配数据"
          @update:model-value="(v) => update({ operator: toSingle(v) })"
        />

        <!-- 类型 -->
        <FilterDropdown
          label="类型"
          :model-value="modelValue.type"
          :options="typeOptions"
          :searchable="false"
          empty-text="无匹配类型"
          @update:model-value="(v) => update({ type: toSingle(v) })"
        />

        <!-- 素材师 -->
        <FilterDropdown
          v-if="showDesigner"
          label="素材师"
          :model-value="modelValue.designers"
          :options="designerOptions"
          :loading="designerLoading"
          :multiple="true"
          placeholder="请搜索"
          empty-text="无匹配素材师"
          @update:model-value="
            (v) => update({ designers: Array.isArray(v) ? v : [] })
          "
        />

        <!-- 创意策划：与素材师同一份人员数据 -->
        <FilterDropdown
          v-if="showDesigner"
          label="创意策划"
          :model-value="modelValue.creativePlanners"
          :options="designerOptions"
          :loading="designerLoading"
          :multiple="true"
          placeholder="请搜索"
          empty-text="无匹配创意策划"
          @update:model-value="
            (v) => update({ creativePlanners: Array.isArray(v) ? v : [] })
          "
        />

        <!-- 投放地区 -->
        <FilterDropdown
          v-if="showCountry"
          label="投放地区"
          :model-value="modelValue.country"
          :options="countryOptions"
          :loading="countryLoading"
          placeholder="请搜索"
          empty-text="无匹配"
          @update:model-value="(v) => update({ country: toSingle(v) })"
        />

        <!-- 排序下拉 -->
        <FilterDropdown
          v-if="showSortSelect"
          label="排序"
          :model-value="modelValue.sortOption"
          :options="sortSelectOptions"
          :searchable="false"
          :clearable="false"
          @update:model-value="
            (v) => {
              const val = toSingle(v);
              if (val) update({ sortOption: val });
            }
          "
        />

        <!-- 按钮模式 -->
        <template v-else>
          <button
            v-if="
              primaryField !== 'expected_delivery_at' &&
              showDeadlineSort !== false
            "
            class="inline-flex items-center gap-1 rounded-md bg-gray-100 px-3 py-1 text-sm text-gray-700 transition-colors hover:bg-gray-200"
            @click="toggleSortOption('expected_delivery_at')"
          >
            交付时间
            <svg
              v-if="
                activeSortField === 'expected_delivery_at' &&
                activeSortDir === 'asc'
              "
              xmlns="http://www.w3.org/2000/svg"
              class="h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
            <svg
              v-else-if="activeSortField === 'expected_delivery_at'"
              xmlns="http://www.w3.org/2000/svg"
              class="h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="19 12 12 19 5 12" />
            </svg>
          </button>

          <button
            class="inline-flex items-center gap-1 rounded-md bg-gray-100 px-3 py-1 text-sm text-gray-700 transition-colors hover:bg-gray-200"
            @click="toggleSortOption(primaryField)"
          >
            {{ sortLabel ?? '创建时间' }}
            <svg
              v-if="activeSortField === primaryField && activeSortDir === 'asc'"
              xmlns="http://www.w3.org/2000/svg"
              class="h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="19" x2="12" y2="5" />
              <polyline points="5 12 12 5 19 12" />
            </svg>
            <svg
              v-else-if="activeSortField === primaryField"
              xmlns="http://www.w3.org/2000/svg"
              class="h-3 w-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="19 12 12 19 5 12" />
            </svg>
          </button>
        </template>

        <div
          class="flex w-56 items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 transition-colors focus-within:border-gray-400"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-3.5 w-3.5 flex-shrink-0 text-gray-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            :value="modelValue.keyword"
            type="text"
            placeholder="搜索标题，支持模糊搜索"
            class="min-w-0 flex-1 bg-transparent text-sm text-gray-700 placeholder-gray-400 outline-none"
            @change="onKeywordInput"
          />
          <button
            v-if="modelValue.keyword"
            class="flex-shrink-0 text-base leading-none text-gray-300 hover:text-gray-500"
            @click="update({ keyword: '' })"
          >
            ×
          </button>
        </div>

        <!-- 刷新 -->
        <button
          class="inline-flex items-center justify-center rounded-md bg-gray-100 p-2 text-gray-600 transition-colors hover:bg-gray-200"
          :class="{ 'cursor-not-allowed opacity-60': loading }"
          :disabled="loading"
          title="刷新"
          @click="emit('refresh')"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="h-4 w-4"
            :class="{ 'animate-spin': loading }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path
              d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
            />
          </svg>
        </button>
      </div>
    </div>

    <!-- 第二行：状态 Tabs + 右侧插槽 -->
    <div class="flex items-center justify-between">
      <Tabs
        v-if="statusOptions.length"
        :active-key="modelValue.status ?? 'all'"
        class="status-tabs"
        @change="(key) => selectStatus(String(key))"
      >
        <Tabs.TabPane key="all" tab="全部" />
        <Tabs.TabPane
          v-for="opt in statusOptions"
          :key="opt.value"
          :tab="opt.label"
        />
      </Tabs>
      <div class="flex flex-shrink-0 items-center gap-2">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped></style>
