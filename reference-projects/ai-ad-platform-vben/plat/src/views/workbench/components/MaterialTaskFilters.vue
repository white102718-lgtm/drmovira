<script setup lang="ts">
import type { MaterialOrderFilterOptions } from '#/api/requirement';
import type { MaterialTaskFilters } from './material-task-filters';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { IconifyIcon } from '@vben/icons';
import { Alert, Button, Form, Input, Select } from 'ant-design-vue';
import { getMaterialOrderFilterOptions } from '#/api/requirement';
import {
  copyMaterialTaskFilters,
  emptyMaterialTaskFilters,
  materialStatusOptions,
} from './material-task-filters';

type MaterialTaskGroupBy = 'kind' | 'none' | 'project' | 'status';

const props = defineProps<{
  filters: MaterialTaskFilters;
  loading: boolean;
  groupBy: MaterialTaskGroupBy;
  groupOptions: { label: string; value: string }[];
  fixedStatus?: { label: string; value: string };
}>();
const emit = defineEmits<{
  apply: [filters: MaterialTaskFilters, groupBy?: MaterialTaskGroupBy];
}>();
const open = ref(false);
const keyword = ref(props.filters.keyword);
const options = ref<MaterialOrderFilterOptions>({
  project: [],
  department: [],
  operators: [],
  designers: [],
  creative_planners: [],
  country: [],
});
const optionsLoading = ref(false);
const optionsError = ref(false);
watch(
  () => props.filters.keyword,
  (value) => {
    keyword.value = value;
  },
);
// 关键词防抖查询；筛选选择直接提交，并取消尚未执行的关键词查询。
let searchTimer: ReturnType<typeof setTimeout> | undefined;
function clearSearchTimer() {
  clearTimeout(searchTimer);
  searchTimer = undefined;
}
watch(keyword, (value) => {
  clearSearchTimer();
  if (value.trim() === props.filters.keyword) return;
  if (!value.trim()) {
    search();
    return;
  }
  searchTimer = setTimeout(search, 300);
});
onBeforeUnmount(clearSearchTimer);

async function loadOptions() {
  if (optionsLoading.value) return;
  optionsLoading.value = true;
  optionsError.value = false;
  try {
    options.value = await getMaterialOrderFilterOptions();
  } catch {
    optionsError.value = true;
  } finally {
    optionsLoading.value = false;
  }
}
onMounted(loadOptions);
function fieldOptions(key: 'department' | 'project') {
  return options.value[key].map((value) => ({ label: value, value }));
}
function userOptions(key: 'creative_planners' | 'designers' | 'operators') {
  // 列表按姓名快照筛选；重名用户合并为一个条件，避免重复的 Select value。
  return [...new Set(options.value[key].map((user) => user.full_name))].map(
    (name) => ({ label: name, value: name }),
  );
}
const priorityOptions = ['P0', 'P1', 'P2', 'P3'].map((value) => ({
  label: value,
  value,
}));
const typeOptions = [
  { label: '视频', value: 'video' },
  { label: '图片', value: 'image' },
];
const greenOptions = [
  { label: '是', value: 'true' },
  { label: '否', value: 'false' },
];
const sortOptions = [
  { label: '提交时间 ↓', value: 'submitted_at:desc' },
  { label: '提交时间 ↑', value: 'submitted_at:asc' },
  { label: '交付时间 ↓', value: 'expected_delivery_at:desc' },
  { label: '交付时间 ↑', value: 'expected_delivery_at:asc' },
];
const statusOptions = computed(() =>
  props.fixedStatus ? [props.fixedStatus] : materialStatusOptions,
);
const filterKeys: (keyof MaterialTaskFilters)[] = [
  'keyword',
  'project',
  'status',
  'priority',
  'demand_type',
  'is_green_material',
  'department',
  'creator',
  'designers',
  'creative_planners',
  'country',
];
// 不展示条件标签，仅保留已应用条件的计数和清空入口。
const activeFilterKeys = computed(() =>
  filterKeys.filter((key) => {
    if (key === 'status' && props.fixedStatus) return false;
    const value = props.filters[key];
    return (
      value !== undefined &&
      value !== '' &&
      (!Array.isArray(value) || value.length > 0)
    );
  }),
);
const advancedCount = computed(
  () =>
    activeFilterKeys.value.filter(
      (key) => !['keyword', 'project', 'status'].includes(key),
    ).length,
);
const hasChanges = computed(
  () =>
    activeFilterKeys.value.length > 0 ||
    props.filters.sort !== 'submitted_at' ||
    props.filters.order !== 'desc' ||
    props.groupBy !== 'none',
);
function updateFilters(
  change: Partial<MaterialTaskFilters>,
  nextGroupBy: MaterialTaskGroupBy = props.groupBy,
) {
  clearSearchTimer();
  emit(
    'apply',
    {
      ...copyMaterialTaskFilters(props.filters),
      keyword: keyword.value.trim(),
      ...change,
    },
    nextGroupBy,
  );
}
function setStringFilter(
  key:
    | 'country'
    | 'creator'
    | 'demand_type'
    | 'department'
    | 'project'
    | 'status',
  value: unknown,
) {
  updateFilters({ [key]: value ? String(value) : undefined });
}
function setMultipleFilter(
  key: 'creative_planners' | 'designers' | 'priority',
  value: unknown,
) {
  updateFilters({ [key]: Array.isArray(value) ? value.map(String) : [] });
}
function search() {
  clearSearchTimer();
  const value = keyword.value.trim();
  if (value !== props.filters.keyword) updateFilters({ keyword: value });
}
function toggleAdvancedFilters() {
  open.value = !open.value;
  if (open.value) void loadOptions();
}
function setGreen(value: unknown) {
  updateFilters({
    is_green_material:
      value === 'true' ? true : value === 'false' ? false : undefined,
  });
}
function setSort(value: unknown) {
  const [sort, order] = String(value).split(':');
  if (sort && (order === 'asc' || order === 'desc')) {
    updateFilters({ sort, order });
  }
}
function setGroup(value: unknown) {
  if (
    value === 'kind' ||
    value === 'none' ||
    value === 'project' ||
    value === 'status'
  ) {
    updateFilters({}, value);
  }
}
function resetApplied() {
  clearSearchTimer();
  keyword.value = '';
  emit('apply', emptyMaterialTaskFilters(), 'none');
}
</script>

<template>
  <div class="material-filters">
    <div class="material-filter-toolbar">
      <div class="material-filter-search">
        <label for="material-task-search" class="material-filter-label"
          >名称</label
        >
        <Input.Search
          id="material-task-search"
          v-model:value="keyword"
          allow-clear
          class="material-filter-control"
          placeholder="搜索工单名称"
          :loading="loading"
          @search="search"
        />
      </div>
      <div class="material-filter-field">
        <label for="material-task-project" class="material-filter-label"
          >项目</label
        >
        <Select
          id="material-task-project"
          :value="filters.project"
          allow-clear
          class="material-filter-control"
          show-search
          option-filter-prop="label"
          placeholder="全部项目"
          :loading="optionsLoading"
          :options="fieldOptions('project')"
          @change="(value) => setStringFilter('project', value)"
        />
      </div>
      <div class="material-filter-field">
        <label for="material-task-status" class="material-filter-label"
          >状态</label
        >
        <Select
          id="material-task-status"
          :value="fixedStatus?.value ?? filters.status"
          allow-clear
          class="material-filter-control"
          :disabled="!!fixedStatus"
          placeholder="全部状态"
          :options="statusOptions"
          @change="(value) => setStringFilter('status', value)"
        />
      </div>
      <Button
        class="material-filter-trigger"
        :aria-controls="'material-task-advanced-filters'"
        :aria-expanded="open"
        @click="toggleAdvancedFilters"
      >
        <template #icon
          ><IconifyIcon icon="lucide:list-filter" aria-hidden="true"
        /></template>
        {{ open ? '收起筛选' : '更多筛选' }}
        <span class="material-filter-count">{{ advancedCount }}</span>
        <IconifyIcon
          aria-hidden="true"
          :icon="open ? 'lucide:chevron-up' : 'lucide:chevron-down'"
        />
      </Button>
    </div>
    <div v-if="hasChanges" class="flex justify-end">
      <Button type="link" @click="resetApplied">清空筛选</Button>
    </div>
    <Alert
      v-if="optionsError"
      type="warning"
      show-icon
      message="筛选选项加载失败"
    >
      <template #action>
        <Button :loading="optionsLoading" @click="loadOptions">重试</Button>
      </template>
    </Alert>
    <section
      v-if="open"
      id="material-task-advanced-filters"
      aria-label="素材工单更多筛选"
      class="material-filter-panel"
    >
      <div class="material-filter-panel-header">
        <h3 class="material-filter-panel-title">更多筛选</h3>
        <Button type="link" @click="open = false">收起筛选</Button>
      </div>
      <Form
        name="material-task-filters"
        layout="vertical"
        class="material-task-filter-form ux-form-label-top"
      >
        <Form.Item name="priority" label="优先级" class="material-filter-field">
          <Select
            :value="filters.priority"
            mode="multiple"
            :max-tag-count="1"
            allow-clear
            show-arrow
            placeholder="全部优先级"
            :options="priorityOptions"
            @change="(value) => setMultipleFilter('priority', value)"
          />
        </Form.Item>
        <Form.Item
          name="demand_type"
          label="类型"
          class="material-filter-field"
        >
          <Select
            :value="filters.demand_type"
            allow-clear
            placeholder="全部类型"
            :options="typeOptions"
            @change="(value) => setStringFilter('demand_type', value)"
          />
        </Form.Item>
        <Form.Item name="creator" label="投手" class="material-filter-field">
          <Select
            :value="filters.creator"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="全部投手"
            :loading="optionsLoading"
            :options="userOptions('operators')"
            @change="(value) => setStringFilter('creator', value)"
          />
        </Form.Item>
        <Form.Item
          name="is_green_material"
          label="是否绿通"
          class="material-filter-field"
          ><Select
            :value="
              filters.is_green_material === undefined
                ? undefined
                : String(filters.is_green_material)
            "
            allow-clear
            placeholder="全部"
            :options="greenOptions"
            @change="setGreen"
        /></Form.Item>
        <Form.Item name="country" label="投放地区" class="material-filter-field"
          ><Select
            :value="filters.country"
            @change="(value) => setStringFilter('country', value)"
            allow-clear
            show-search
            :field-names="{ label: 'name', value: 'code' }"
            option-label-prop="name"
            option-filter-prop="name"
            placeholder="全部地区"
            :loading="optionsLoading"
            :options="options.country"
        /></Form.Item>
        <Form.Item name="department" label="部门" class="material-filter-field"
          ><Select
            :value="filters.department"
            @change="(value) => setStringFilter('department', value)"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="全部部门"
            :loading="optionsLoading"
            :options="fieldOptions('department')"
        /></Form.Item>
        <Form.Item name="designers" label="素材师" class="material-filter-field"
          ><Select
            :value="filters.designers"
            @change="(value) => setMultipleFilter('designers', value)"
            mode="multiple"
            :max-tag-count="1"
            :max-tag-text-length="4"
            :max-tag-placeholder="
              (omittedValues: unknown[]) => `+${omittedValues.length}`
            "
            allow-clear
            show-arrow
            show-search
            option-filter-prop="label"
            placeholder="全部素材师"
            :loading="optionsLoading"
            :options="userOptions('designers')"
        /></Form.Item>
        <Form.Item
          name="creative_planners"
          label="创意策划"
          class="material-filter-field"
          ><Select
            :value="filters.creative_planners"
            @change="(value) => setMultipleFilter('creative_planners', value)"
            mode="multiple"
            :max-tag-count="1"
            :max-tag-text-length="4"
            :max-tag-placeholder="
              (omittedValues: unknown[]) => `+${omittedValues.length}`
            "
            allow-clear
            show-arrow
            show-search
            option-filter-prop="label"
            placeholder="全部创意策划"
            :loading="optionsLoading"
            :options="userOptions('creative_planners')"
        /></Form.Item>
        <Form.Item name="sort" label="排序" class="material-filter-field"
          ><Select
            :value="`${filters.sort}:${filters.order}`"
            :options="sortOptions"
            @change="setSort"
        /></Form.Item>
        <Form.Item name="group" label="分组" class="material-filter-field">
          <Select :value="groupBy" :options="groupOptions" @change="setGroup" />
        </Form.Item>
      </Form>
    </section>
  </div>
</template>

<style scoped>
.material-filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  container-type: inline-size;
}

.material-filter-toolbar {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  align-items: center;
}

.material-filter-toolbar
  > :is(.material-filter-field, .material-filter-search) {
  display: flex;
  flex: 1 1 0;
  align-items: center;
  gap: 8px;
  min-width: 160px;
  max-width: 100%;
}

.material-filter-field {
  min-width: 0;
  max-width: 100%;
}

.material-filter-control {
  flex: 1 1 0;
  min-width: 0;
  width: 100%;
}

.material-filter-label {
  display: block;
  margin-bottom: 8px;
  text-align: left;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.material-filter-trigger {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 6px;
  align-items: center;
  justify-content: center;
  margin-inline-start: auto;
  white-space: nowrap;
}

.material-filter-toolbar .material-filter-label {
  flex: 0 0 auto;
  margin: 0;
}

.material-filter-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  font-size: 12px;
  line-height: 20px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 999px;
}

.material-filter-panel {
  padding: 16px;
  margin-top: 8px;
  background: hsl(var(--muted) / 40%);
  border-top: 1px solid hsl(var(--border));
  border-radius: 0 0 var(--radius) var(--radius);
}

.material-filter-panel-header {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.material-filter-panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.material-task-filter-form {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  align-items: end;
}

@container (max-width: 1179px) {
  .material-task-filter-form {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@container (max-width: 759px) {
  .material-filter-toolbar {
    flex-wrap: wrap;
  }

  .material-filter-toolbar > .material-filter-search {
    flex-basis: 100%;
    width: 100%;
  }

  .material-filter-toolbar > .material-filter-field {
    flex: 1 1 220px;
  }

  .material-task-filter-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container (max-width: 519px) {
  .material-filter-field,
  .material-filter-search,
  .material-filter-trigger {
    flex-basis: 100%;
    width: 100%;
  }

  .material-task-filter-form {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
