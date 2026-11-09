<script setup lang="ts">
import type { Dayjs } from 'dayjs';

import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';
import type { CloakCountryOption, CloakRecord } from '#/domain/cloak';
import type { ProjectSearchOption } from '#/domain/project';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useDebounceFn } from '@vueuse/core';

import {
  Button,
  Card,
  Checkbox,
  Input,
  message,
  Modal,
  Pagination,
  RangePicker,
  Select,
  Tag,
} from 'ant-design-vue';

import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';
import { cloakService } from '#/domain/cloak';
import { projectService } from '#/domain/project';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import dayjs from 'dayjs';

import BusinessPageHeader from '../../components/BusinessPageHeader.vue';
import { exportCloakRecords } from './cloak-excel';

defineOptions({ name: 'WorkbenchCloaks' });

const router = useRouter();
const keyword = ref('');
const projectId = ref<string>();
const country = ref<string>();
const dateRange = ref<[Dayjs, Dayjs]>();
const records = ref<CloakRecord[]>([]);
const projectOptions = ref<ProjectSearchOption[]>([]);
const countryOptions = ref<CloakCountryOption[]>([]);
const loading = ref(false);
const deleting = ref(false);
const writingBack = ref(false);
const exporting = ref(false);
const selectedIds = ref<string[]>([]);
const loadingProjects = ref(false);
const page = ref(1);
const pageSize = ref(10);
const pageSizeOptions = [10, 20, 50, 100];
const total = ref(0);
const routeState = createListRouteStateTarget({
  country,
  date_range: dateRange,
  keyword,
  project_id: projectId,
});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    fields: {
      date_range: {
        codec: {
          parse(value) {
            const values = Array.isArray(value) ? value : [value];
            return values.length === 2 && values[0] && values[1]
              ? ([dayjs(values[0]), dayjs(values[1])] as [Dayjs, Dayjs])
              : undefined;
          },
          serialize(value) {
            return value?.map((item) => item.format('YYYY-MM-DD'));
          },
        },
      },
    },
    onRouteStateRestored: () => loadRecords(),
    pagination: {
      defaultPageSize: 10,
      page,
      pageSize,
      pageSizes: pageSizeOptions,
    },
    state: routeState,
  });
const projectSelectOptions = computed(() =>
  projectOptions.value.map((project) => ({
    label: project.name,
    value: project.id,
  })),
);
const allCurrentPageSelected = computed(
  () =>
    records.value.length > 0 &&
    records.value.every((record) => selectedIds.value.includes(record.id)),
);
const someCurrentPageSelected = computed(
  () =>
    !allCurrentPageSelected.value &&
    records.value.some((record) => selectedIds.value.includes(record.id)),
);

const columns: ShadcnDataTableColumn[] = [
  { align: 'left', key: 'select', title: '', width: 60 },
  { key: 'projectName', title: '所属项目', width: 220 },
  { key: 'sourceUrl', title: '投放链接', width: 300 },
  { key: 'reviewUrl', title: '审核链接', width: 300 },
  { key: 'promotionUrl', title: '斗篷链接', width: 300 },
  { key: 'mode', title: '模式', width: 90 },
  { key: 'countryLabel', title: '投放地区', width: 110 },
  { align: 'left', key: 'blockedLanguage', title: '禁止空语言', width: 110 },
  { align: 'left', key: 'blockedPc', title: '禁止PC', width: 90 },
  { align: 'left', key: 'blockedProxy', title: '禁止代理', width: 100 },
  {
    align: 'left',
    key: 'sheetWritebackStatus',
    title: 'Google回填',
    width: 120,
  },
  { key: 'createdAt', title: '创建时间', width: 180 },
  { align: 'left', key: 'actions', title: '操作', width: 100 },
];

async function loadRecords() {
  await commitQueryState();
  loading.value = true;
  try {
    const result = await cloakService.listRecords({
      country: country.value,
      endDate: dateRange.value?.[1].format('YYYY-MM-DD'),
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      pageSize: pageSize.value,
      projectId: projectId.value,
      startDate: dateRange.value?.[0].format('YYYY-MM-DD'),
    });
    records.value = result.items;
    total.value = result.total;
    selectedIds.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadProjectOptions(keyword = '') {
  loadingProjects.value = true;
  try {
    projectOptions.value = await projectService.searchOptions(keyword);
  } finally {
    loadingProjects.value = false;
  }
}

const handleProjectSearch = useDebounceFn((value: string) => {
  void loadProjectOptions(value);
}, 300);

function handleSearch() {
  page.value = 1;
  void loadRecords();
}

async function resetFilters() {
  await resetQueryState();
  await loadRecords();
}

function handlePaginationChange(nextPage: number, nextPageSize: number) {
  const pageSizeChanged = nextPageSize !== pageSize.value;
  pageSize.value = nextPageSize;
  page.value = pageSizeChanged ? 1 : nextPage;
  void loadRecords();
}

function openBatchCreate() {
  void router.push('/workbench/cloaks/batch-create');
}

function toggleRecord(id: string, checked: boolean) {
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, id])]
    : selectedIds.value.filter((selectedId) => selectedId !== id);
}

function toggleCurrentPageSelection(checked: boolean) {
  selectedIds.value = checked ? records.value.map((record) => record.id) : [];
}

function handleDelete(ids: string[]) {
  if (ids.length === 0 || deleting.value || exporting.value) return;
  Modal.confirm({
    cancelText: '取消',
    content: `删除后将同步删除服务商斗篷，共 ${ids.length} 条。`,
    okText: '删除',
    okType: 'danger',
    title: '确认删除斗篷？',
    async onOk() {
      deleting.value = true;
      try {
        await cloakService.deleteRecords(ids);
        message.success('删除成功');
        if (records.value.length <= ids.length && page.value > 1) {
          page.value -= 1;
        }
        await loadRecords();
      } finally {
        deleting.value = false;
      }
    },
  });
}

function showWritebackFailure(record: CloakRecord) {
  Modal.info({
    content: record.sheetWritebackMessage || '未记录具体失败原因',
    okText: '关闭',
    title: `${record.agencyLineName} 回填失败`,
  });
}

function handleWriteback() {
  const ids = [...selectedIds.value];
  if (ids.length === 0 || writingBack.value || exporting.value) return;
  Modal.confirm({
    cancelText: '取消',
    content: `将选中的 ${ids.length} 条斗篷链接回填到对应项目的 Google Sheet。`,
    okText: '开始回填',
    title: '确认Google回填？',
    async onOk() {
      writingBack.value = true;
      try {
        const result = await cloakService.writebackRecords(ids);
        if (result.failedCount > 0) {
          message.warning(
            `Google回填成功 ${result.successCount} 条，失败 ${result.failedCount} 条`,
          );
        } else {
          message.success(`Google回填成功 ${result.successCount} 条`);
        }
        await loadRecords();
      } finally {
        writingBack.value = false;
      }
    },
  });
}

async function handleExport() {
  if (selectedIds.value.length === 0 || exporting.value) return;
  exporting.value = true;
  try {
    const selectedIdSet = new Set(selectedIds.value);
    const selectedRecords = records.value.filter((record) =>
      selectedIdSet.has(record.id),
    );
    await exportCloakRecords(selectedRecords);
    message.success(`已导出 ${selectedRecords.length} 条斗篷记录`);
  } catch {
    message.error('导出失败，请重试');
  } finally {
    exporting.value = false;
  }
}

function modeLabel(mode: CloakRecord['mode']) {
  return { all: '全开', cloak: '斗篷', off: '全关' }[mode];
}

function formatDateTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '-';
}

onMounted(async () => {
  await restoreFromRoute();
  await loadRecords();
  void loadProjectOptions();
  void cloakService.listCountries().then((items) => {
    countryOptions.value = items;
  });
});
</script>

<template>
  <Page class="bg-muted/40">
    <div class="w-full min-w-0 space-y-4">
      <BusinessPageHeader
        compact
        description="管理通过服务商成功创建并保存到本地的斗篷链接。"
        icon="lucide:shield-check"
        title="斗篷管理"
      />

      <Card :bordered="true">
        <div class="flex flex-wrap items-end gap-4">
          <label class="w-[280px] max-w-full">
            <span class="text-foreground mb-2 block text-sm">关键词</span>
            <Input
              v-model:value="keyword"
              placeholder="搜索项目或链接"
              @press-enter="handleSearch"
            />
          </label>
          <label class="w-[220px] max-w-full">
            <span class="text-foreground mb-2 block text-sm">所属项目</span>
            <Select
              v-model:value="projectId"
              allow-clear
              class="w-full"
              :filter-option="false"
              :loading="loadingProjects"
              :options="projectSelectOptions"
              placeholder="全部项目"
              show-search
              @search="handleProjectSearch"
            />
          </label>
          <label class="w-[220px] max-w-full">
            <span class="text-foreground mb-2 block text-sm">投放地区</span>
            <Select
              v-model:value="country"
              allow-clear
              class="w-full"
              :options="countryOptions"
              placeholder="全部地区"
            />
          </label>
          <label class="w-[280px] max-w-full">
            <span class="text-foreground mb-2 block text-sm">创建时间</span>
            <RangePicker v-model:value="dateRange" class="w-full" />
          </label>
          <div class="ml-auto flex gap-2">
            <Button @click="resetFilters">重置</Button>
            <Button type="primary" @click="handleSearch">搜索</Button>
          </div>
        </div>
      </Card>

      <Card :body-style="{ padding: 0 }" :bordered="true">
        <div
          class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"
        >
          <div class="flex items-center gap-2">
            <Button type="primary" @click="openBatchCreate">
              <template #icon><IconifyIcon icon="lucide:plus" /></template>
              新增
            </Button>
            <Button
              danger
              :disabled="selectedIds.length === 0 || writingBack || exporting"
              :loading="deleting"
              @click="handleDelete(selectedIds)"
            >
              删除
            </Button>
            <Button
              :disabled="selectedIds.length === 0 || deleting || exporting"
              :loading="writingBack"
              @click="handleWriteback"
            >
              Google回填
            </Button>
            <Button
              :disabled="selectedIds.length === 0 || deleting || writingBack"
              :loading="exporting"
              @click="handleExport"
            >
              <template #icon>
                <IconifyIcon icon="lucide:download" />
              </template>
              导出
            </Button>
          </div>
          <span class="text-muted-foreground text-sm"> 共 {{ total }} 条 </span>
        </div>

        <ShadcnDataTable
          :columns="columns"
          :data="records"
          :loading="loading"
          :paginate="false"
          row-key="id"
        >
          <template #header-select>
            <Checkbox
              :checked="allCurrentPageSelected"
              :disabled="
                loading ||
                deleting ||
                writingBack ||
                exporting ||
                records.length === 0
              "
              :indeterminate="someCurrentPageSelected"
              aria-label="选择当前页全部斗篷"
              @change="
                toggleCurrentPageSelection(Boolean($event.target.checked))
              "
            />
          </template>
          <template #cell-select="{ record }">
            <Checkbox
              :checked="selectedIds.includes(record.id)"
              :disabled="deleting || writingBack || exporting"
              :aria-label="`选择斗篷 ${record.projectName}`"
              @change="toggleRecord(record.id, $event.target.checked)"
            />
          </template>
          <template #cell-sourceUrl="{ record }">
            <span
              class="block max-w-[280px] truncate"
              :title="record.sourceUrl"
            >
              {{ record.sourceUrl }}
            </span>
          </template>
          <template #cell-promotionUrl="{ record }">
            <span
              class="block max-w-[280px] truncate"
              :title="record.promotionUrl"
            >
              {{ record.promotionUrl }}
            </span>
          </template>
          <template #cell-reviewUrl="{ record }">
            <span
              class="block max-w-[280px] truncate"
              :title="record.reviewUrl"
            >
              {{ record.reviewUrl }}
            </span>
          </template>
          <template #cell-mode="{ record }">
            <Tag color="blue">{{ modeLabel(record.mode) }}</Tag>
          </template>
          <template #cell-countryLabel="{ record }">
            {{ record.countryLabel || record.country || '-' }}
          </template>
          <template #cell-blockedLanguage="{ record }">
            <Tag :color="record.blockedLanguage ? 'red' : 'default'">
              {{ record.blockedLanguage ? '开' : '关' }}
            </Tag>
          </template>
          <template #cell-blockedPc="{ record }">
            <Tag :color="record.blockedPc ? 'red' : 'default'">
              {{ record.blockedPc ? '开' : '关' }}
            </Tag>
          </template>
          <template #cell-blockedProxy="{ record }">
            <Tag :color="record.blockedProxy ? 'red' : 'default'">
              {{ record.blockedProxy ? '开' : '关' }}
            </Tag>
          </template>
          <template #cell-sheetWritebackStatus="{ record }">
            <Tag v-if="record.sheetWritebackStatus === 'success'" color="green">
              已回填
            </Tag>
            <Button
              v-else-if="record.sheetWritebackStatus === 'failed'"
              danger
              type="link"
              @click="showWritebackFailure(record)"
            >
              回填失败
            </Button>
            <Tag v-else>未回填</Tag>
          </template>
          <template #cell-createdAt="{ record }">
            {{ formatDateTime(record.createdAt) }}
          </template>
          <template #cell-actions="{ record }">
            <Button
              danger
              :disabled="deleting || writingBack || exporting"
              type="link"
              @click="handleDelete([record.id])"
            >
              删除
            </Button>
          </template>
        </ShadcnDataTable>
        <div v-if="total > 0" class="flex justify-end border-t px-4 py-3">
          <Pagination
            :current="page"
            :page-size="pageSize"
            :page-size-options="pageSizeOptions.map(String)"
            :total="total"
            show-less-items
            show-size-changer
            @change="handlePaginationChange"
          />
        </div>
      </Card>
    </div>
  </Page>
</template>
