<script lang="ts" setup>
import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AgentLineConfig } from '#/api/management/platform-config';

import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import {
  AutoComplete,
  Button,
  Input,
  message,
  Modal,
  Popover,
  Select,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getPages, getUserOptions } from '#/api';
import { OBJECTIVE_MAP } from '#/api/advertisement/mappings';
import {
  batchUpdateAgentLineConfig,
  createAgentLineConfig,
  deleteAgentLineConfig,
  getAgentLineConfigList,
  updateAgentLineConfig,
} from '#/api/management/platform-config';

interface Props {
  agentOptions?: Array<{ label: string; value: string }>;
  agentSearch?: string;
  department?: string;
  platformName?: string;
}

const props = withDefaults(defineProps<Props>(), {
  platformName: '',
  agentOptions: () => [],
  agentSearch: '',
  department: '',
});

const route = useRoute();
const router = useRouter();

const userOptions = ref<{ label: string; value: string }[]>([]);
const loadingSave = ref(false);
const showBatchModal = ref(false);
const loadingBatch = ref(false);
const loadingExport = ref(false);
const objectiveOptions = Object.entries(OBJECTIVE_MAP).map(
  ([label, value]) => ({
    label,
    value,
  }),
);

const batchForm = reactive<{
  auto_run?: boolean;
  budget_cap: string;
  budget_floor: string;
  enabled?: boolean;
  is_send?: boolean;
  objective?: string;
  optimizer?: string;
  package_name: string;
  package_type?: string;
  package_url: string;
  pixel_name: string;
}>({
  package_url: '',
  pixel_name: '',
  optimizer: undefined,
  objective: undefined,
  package_type: undefined,
  package_name: '',
  budget_cap: '',
  budget_floor: '',
  enabled: false,
  auto_run: false,
  is_send: false,
});
const batchIds = ref<string[]>([]);

function filterUserOption(input: string, option: { label?: string }) {
  return (option.label ?? '').toLowerCase().includes(input.toLowerCase());
}

const fetchOptions = async () => {
  try {
    const users = await getUserOptions(['operator', 'operator_leader']);
    userOptions.value = users.map((item) => ({
      label: item,
      value: item,
    }));
  } catch {}
};

onMounted(() => {
  fetchOptions();
});

// 主页按名称搜索: 列头搜索复制 ID + 编辑格输入名称回填共用
const pageSearchKw = ref('');
const pageSearchLoading = ref(false);
const pageSearchResults = ref<Array<{ id: string; name: string }>>([]);
let pageSearchTimer: null | ReturnType<typeof setTimeout> = null;

function searchPagesByName(kw: string) {
  if (pageSearchTimer) clearTimeout(pageSearchTimer);
  const name = kw.trim();
  if (!name) {
    pageSearchResults.value = [];
    return;
  }
  pageSearchTimer = setTimeout(async () => {
    pageSearchLoading.value = true;
    try {
      const res = await getPages({ name, page: 1, page_size: 20 });
      pageSearchResults.value = (res.items ?? []).map((p) => ({
        id: String(p._id),
        name: p.name || String(p._id),
      }));
    } finally {
      pageSearchLoading.value = false;
    }
  }, 300);
}

const pageEditOptions = computed(() =>
  pageSearchResults.value.map((p) => ({
    value: p.id,
    label: `${p.name} (${p.id})`,
  })),
);

async function copyPageId(id: string) {
  try {
    await navigator.clipboard.writeText(id);
    message.success(`已复制: ${id}`);
  } catch {
    message.error('复制失败');
  }
}

function syncAgentPageToUrl(page: number) {
  router.replace({
    query: { ...route.query, agentPage: page > 1 ? String(page) : undefined },
  });
}

function onAgentPageChange(e: { currentPage: number }) {
  syncAgentPageToUrl(e.currentPage);
}

watch(
  [() => props.platformName, () => props.agentSearch, () => props.department],
  () => {
    syncAgentPageToUrl(1);
    gridApi?.reload();
  },
);

const gridOptions: VxeGridProps<AgentLineConfig> = {
  toolbarConfig: {
    refresh: { code: 'query' },
  },
  autoResize: true,
  border: true,
  columns: [
    {
      type: 'checkbox',
      width: 50,
      fixed: 'left',
    },
    {
      fixed: 'left',
      title: '序号',
      width: 60,
      slots: { default: 'seq' },
    },
    // {
    //   fixed: 'left',
    //   field: 'game_platform',
    //   title: '平台',
    //   width: 140,
    //   showOverflow: 'tooltip',
    // },
    {
      fixed: 'left',
      field: '_id',
      title: '代理线',
      width: 200,
      editRender: {},
      slots: {
        default: 'agent_line_default',
        edit: 'agent_line_edit',
      },
      formatter: ({ row }: { row: AgentLineConfig }) => {
        return row.agent_line || '';
      },
    },
    {
      field: 'package_url',
      title: '投放链接',
      width: 220,
      showOverflow: 'tooltip',
      formatter({ cellValue }) {
        return typeof cellValue === 'string' ? cellValue.trim() : cellValue;
      },
      slots: { edit: 'package_url_edit' },
      editRender: {},
    },
    {
      field: 'history_package_urls',
      title: '历史投放链接',
      width: 200,
      editRender: {},
      slots: {
        default: 'history_package_urls_default',
        edit: 'history_package_urls_edit',
      },
    },
    {
      field: 'pixel_name',
      title: '像素名称(创建广告时必填)',
      width: 200,
      showOverflow: 'tooltip',
      formatter({ cellValue }) {
        return typeof cellValue === 'string' ? cellValue.trim() : cellValue;
      },
      slots: { edit: 'pixel_edit' },
      editRender: {},
    },
    {
      field: 'optimizer',
      title: '优化师(关联数据需要)',
      width: 160,
      slots: {
        default: 'optimizer_default',
        edit: 'optimizer_edit',
      },
      editRender: {},
      formatter: ({ cellValue }) => {
        if (!cellValue) return '';
        return typeof cellValue === 'string' ? cellValue : String(cellValue);
      },
    },
    {
      field: 'page_id',
      title: '主页ID',
      width: 160,
      showOverflow: 'tooltip',
      slots: { header: 'page_id_header', edit: 'page_id_edit' },
      editRender: {},
    },
    {
      field: 'objective',
      title: '系列目标',
      width: 120,
      editRender: {},
      slots: {
        default: 'objective_default',
        edit: 'objective_edit',
      },
      formatter: ({ cellValue }) => {
        if (!cellValue) return '';
        const entry = Object.entries(OBJECTIVE_MAP).find(
          ([, v]) => v === cellValue,
        );
        return entry ? entry[0] : cellValue;
      },
    },
    {
      field: 'package_type',
      title: '包类型',
      width: 100,
      editRender: {},
      slots: {
        default: 'package_type_default',
        edit: 'package_type_edit',
      },
    },
    {
      field: 'package_name',
      title: '包名',
      width: 140,
      slots: { edit: 'package_name_edit' },
      editRender: {},
    },
    {
      field: 'budget_cap',
      title: '预算上限',
      width: 120,
      editRender: {
        name: 'VxeNumberInput',
        props: { type: 'integer', controlConfig: { showButton: false } },
      },
    },
    {
      field: 'budget_floor',
      title: '预算下限',
      width: 120,
      editRender: {
        name: 'VxeNumberInput',
        props: { type: 'integer', controlConfig: { showButton: false } },
      },
    },
    {
      field: 'enabled',
      title: '是否启用',
      width: 100,
      editRender: {},
      slots: {
        default: 'enabled_default',
        edit: 'enabled_edit',
      },
    },
    {
      field: 'auto_run',
      title: '自动运行',
      width: 100,
      editRender: {},
      slots: {
        default: 'auto_run_default',
        edit: 'auto_run_edit',
      },
    },
    {
      field: 'is_send',
      title: '是否发送',
      width: 100,
      editRender: {},
      slots: {
        default: 'is_send_default',
        edit: 'is_send_edit',
      },
    },
    {
      fixed: 'right',
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      width: 160,
    },
  ],
  editConfig: {
    mode: 'row',
    showStatus: true,
    trigger: 'manual',
    autoClear: false,
  },
  height: window.innerHeight - 180,
  scrollY: {
    enabled: true,
    gt: 0,
  },
  keepSource: true,
  pagerConfig: {
    enabled: true,
    pageSize: 20,
    currentPage: Number(route.query.agentPage) || 1,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        const currentPage = page.currentPage || 1;
        const pageSize = page.pageSize || 20;
        try {
          const result = await getAgentLineConfigList(
            props.platformName || undefined,
            props.agentSearch || undefined,
            props.department || undefined,
            currentPage,
            pageSize,
          );
          return {
            page: result.page ?? currentPage,
            pageSize: result.page_size ?? pageSize,
            total: result.total ?? 0,
            items: result.items ?? [],
          };
        } catch {
          return {
            page: currentPage,
            pageSize,
            total: 0,
            items: [],
          };
        }
      },
    },
  },
  showOverflow: false,
};

const [Grid, gridApi] = useVbenVxeGrid({ gridOptions });

function hasEditStatus(row: AgentLineConfig) {
  return gridApi.grid?.isEditByRow(row);
}

function editRowEvent(row: AgentLineConfig) {
  gridApi.grid?.setEditRow(row);
}

async function saveRowEvent(row: AgentLineConfig) {
  loadingSave.value = true;
  try {
    if (row.id === null) {
      await createAgentLineConfig(props.platformName, row);
      message.success('新增成功');
    } else {
      await updateAgentLineConfig(props.platformName || '', row);
      message.success('保存成功');
    }
    await gridApi.grid?.clearEdit();
    await gridApi.grid?.commitProxy('query');
  } finally {
    loadingSave.value = false;
  }
}

function cancelRowEvent() {
  gridApi.grid?.clearEdit();
}

async function handleDelete(row: AgentLineConfig) {
  if (row._id) {
    Modal.confirm({
      cancelText: '取消',
      content: `确定要删除代理线 "${row._id || ''}" 的配置吗？`,
      okText: '确定',
      onOk: async () => {
        try {
          await deleteAgentLineConfig(row._id);
          message.success('删除代理线配置成功');
        } catch {}
      },
      onCancel: () => {},
      afterClose: async () => {
        await gridApi.reload();
      },
      title: '确认删除',
    });
  } else {
    await gridApi.grid.remove(row);
  }
}

async function addAgentLineConfig() {
  if (!props.platformName) {
    message.warning('请先选择平台');
    return;
  }
  const newRow = {
    id: null,
    agent_line: null,
    game_platform: props.platformName,
    optimizer: null,
    objective: null,
    package_type: null,
    package_name: null,
    package_url: null,
    pixel_name: null,
    auto_run: false,
    enabled: false,
    is_send: false,
    page_id: null,
  };
  const { row: insertedRow } = await gridApi.grid.insert(newRow);
  await gridApi.grid.setEditRow(insertedRow);
}

function resetBatchForm() {
  batchForm.package_url = '';
  batchForm.pixel_name = '';
  batchForm.optimizer = undefined;
  batchForm.objective = undefined;
  batchForm.package_type = undefined;
  batchForm.package_name = '';
  batchForm.budget_cap = '';
  batchForm.budget_floor = '';
  batchForm.enabled = false;
  batchForm.auto_run = false;
  batchForm.is_send = false;
}

async function handleBatchEdit() {
  const records = gridApi.grid?.getCheckboxRecords?.() || [];
  if (records.length === 0) {
    message.warning('请先选择需要编辑的代理线');
    return;
  }
  const ids = records
    .map((item: AgentLineConfig) => item._id)
    .filter((id): id is string => !!id);
  if (ids.length === 0) {
    message.warning('选中的代理线缺少有效的标识');
    return;
  }
  batchIds.value = ids;
  resetBatchForm();
  showBatchModal.value = true;
}

async function handleBatchConfirm() {
  if (batchIds.value.length === 0) {
    showBatchModal.value = false;
    return;
  }

  const commonFields: Record<string, any> = {
    enabled: batchForm.enabled,
    auto_run: batchForm.auto_run,
    is_send: batchForm.is_send,
  };

  if (batchForm.package_url.trim()) {
    commonFields.package_url = batchForm.package_url.trim();
  }
  if (batchForm.pixel_name.trim()) {
    commonFields.pixel_name = batchForm.pixel_name.trim();
  }
  if (batchForm.optimizer) {
    commonFields.optimizer = batchForm.optimizer;
  }
  if (batchForm.objective) {
    commonFields.objective = batchForm.objective;
  }
  if (batchForm.package_type) {
    commonFields.package_type = batchForm.package_type;
  }
  if (batchForm.package_name.trim()) {
    commonFields.package_name = batchForm.package_name.trim();
  }
  if (batchForm.budget_cap.trim()) {
    const num = Number(batchForm.budget_cap.trim());
    if (!Number.isNaN(num)) {
      commonFields.budget_cap = num;
    }
  }
  if (batchForm.budget_floor.trim()) {
    const num = Number(batchForm.budget_floor.trim());
    if (!Number.isNaN(num)) {
      commonFields.budget_floor = num;
    }
  }

  const configs = batchIds.value.map((id) => ({ _id: id, ...commonFields }));

  loadingBatch.value = true;
  try {
    await batchUpdateAgentLineConfig(configs);
    message.success('批量编辑成功');
    showBatchModal.value = false;
    await gridApi.grid?.commitProxy('query');
  } catch {
  } finally {
    loadingBatch.value = false;
  }
}

async function exportCurrentPageCSV() {
  const pager = gridApi.grid?.getProxyInfo()?.pager;
  const currentPage = pager?.currentPage || 1;
  const pageSize = pager?.pageSize || 20;

  loadingExport.value = true;
  try {
    const result = await getAgentLineConfigList(
      props.platformName || undefined,
      props.agentSearch || undefined,
      props.department || undefined,
      currentPage,
      pageSize,
    );
    const exportItems = result.items ?? [];
    if (exportItems.length === 0) {
      message.info('当前没有可导出的代理线配置');
      return;
    }

    const columnConfig = [
      { title: '序号', key: 'index' },
      { title: '代理线', key: '_id' },
      { title: '投放链接', key: 'package_url' },
      { title: '像素名称(创建广告时必填)', key: 'pixel_name' },
      { title: '优化师(关联数据需要)', key: 'optimizer' },
      { title: '主页ID', key: 'page_id' },
      { title: '系列目标', key: 'objective' },
      { title: '包类型', key: 'package_type' },
      { title: '包名', key: 'package_name' },
      { title: '预算上限', key: 'budget_cap' },
      { title: '预算下限', key: 'budget_floor' },
      { title: '是否启用', key: 'enabled' },
      { title: '自动运行', key: 'auto_run' },
      { title: '是否发送', key: 'is_send' },
    ];

    const headers = columnConfig.map((column) => column.title);
    const rows = exportItems.map((item, index) =>
      columnConfig.map((column) => {
        let value =
          column.key === 'index'
            ? index + 1
            : (item as Record<string, unknown>)[column.key];
        if (value === undefined || value === null) return '';
        if (typeof value === 'boolean') value = value ? '是' : '否';
        const text = String(value);
        return text.includes(',') || text.includes('"') || text.includes('\n')
          ? `"${text.replaceAll('"', '""')}"`
          : text;
      }),
    );

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.join(',')),
    ].join('\n');
    const blob = new Blob(['\uFEFF', csvContent], {
      type: 'text/csv;charset=utf-8;',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = '代理线配置.csv';
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    message.error('导出失败');
  } finally {
    loadingExport.value = false;
  }
}

// 当 Tab 切换到代理线配置时，强制让表格重新计算尺寸，避免在隐藏状态初始化导致的布局异常
watch(
  () => route.query.tab,
  async (tab) => {
    if (tab === 'PlatformManageConfig') {
      await nextTick();
      // 这里调用 any 是为了兼容 VxeGrid 的实例方法类型声明差异
      (gridApi.grid as any)?.resize?.();
    }
  },
);
</script>

<template>
  <Page class="[&>div]:m-0 [&>div]:p-0">
    <template #default>
      <Grid @page-change="onAgentPageChange">
        <template #toolbar-actions>
          <span class="mr-4">代理线配置</span>
        </template>

        <template #toolbar-tools>
          <Button
            class="mr-2"
            :loading="loadingExport"
            @click="exportCurrentPageCSV"
          >
            导出表格
          </Button>
          <Button class="mr-2" @click="handleBatchEdit"> 批量编辑</Button>
          <Button @click="addAgentLineConfig"> 新增配置</Button>
        </template>

        <template #seq="{ rowIndex }">
          {{
            ((gridApi.grid?.getProxyInfo()?.pager?.currentPage || 1) - 1) *
              (gridApi.grid?.getProxyInfo()?.pager?.pageSize || 20) +
            rowIndex +
            1
          }}
        </template>

        <template #agent_line_default="{ row }">
          <span class="text-blue-600">
            {{ row._id }}
          </span>
        </template>

        <template #agent_line_edit="{ row }">
          <Input
            v-model:value="row._id"
            placeholder="请输入代理线"
            style="width: 100%"
          />
        </template>

        <template #enabled_default="{ row }">
          <Switch v-model:checked="row.enabled" disabled />
        </template>
        <template #enabled_edit="{ row }">
          <Switch v-model:checked="row.enabled" />
        </template>

        <template #auto_run_default="{ row }">
          <Switch v-model:checked="row.auto_run" disabled />
        </template>
        <template #auto_run_edit="{ row }">
          <Switch v-model:checked="row.auto_run" />
        </template>

        <template #is_send_default="{ row }">
          <Switch v-model:checked="row.is_send" disabled />
        </template>
        <template #is_send_edit="{ row }">
          <Switch v-model:checked="row.is_send" />
        </template>

        <template #objective_default="{ row }">
          <span v-if="row.objective">
            {{
              Object.entries(OBJECTIVE_MAP).find(
                ([, v]) => v === row.objective,
              )?.[0] || row.objective
            }}
          </span>
        </template>
        <template #objective_edit="{ row }">
          <Select
            :value="row.objective || undefined"
            class="w-full"
            placeholder="请选择"
            :allow-clear="true"
            :options="objectiveOptions"
            @change="
              (value) => {
                row.objective = value || null;
              }
            "
          />
        </template>

        <template #optimizer_default="{ row }">
          <span v-if="row.optimizer">
            {{ row.optimizer }}
          </span>
        </template>

        <template #optimizer_edit="{ row }">
          <Select
            :value="row.optimizer || undefined"
            placeholder="请选择优化师"
            style="width: 100%"
            :options="userOptions"
            :allow-clear="true"
            show-search
            :filter-option="filterUserOption"
            @change="
              (value) => {
                row.optimizer = value || null;
              }
            "
          />
        </template>

        <template #package_type_default="{ row }">
          <span v-if="row.package_type">
            {{ row.package_type }}
          </span>
        </template>

        <template #package_type_edit="{ row }">
          <Select
            v-model:value="row.package_type"
            class="w-full"
            placeholder="请选择包类型"
            :allow-clear="true"
            :options="[
              { label: 'W2A', value: 'W2A' },
              { label: 'PWA', value: 'PWA' },
              { label: 'Store', value: 'Store' },
            ]"
          />
        </template>

        <template #package_name_edit="{ row }">
          <Input v-model:value="row.package_name" style="width: 100%" />
        </template>

        <template #package_url_edit="{ row }">
          <Input v-model:value="row.package_url" style="width: 100%" />
        </template>

        <template #history_package_urls_default="{ row }">
          <template
            v-if="
              row.history_package_urls && row.history_package_urls.length > 0
            "
          >
            <div
              v-if="row.history_package_urls.length === 1"
              class="flex justify-center"
            >
              <Tooltip :title="row.history_package_urls[0]">
                <Tag
                  style="margin-right: 0; max-width: 170px"
                  class="block overflow-hidden truncate text-[13px]"
                  >{{ row.history_package_urls[0] }}</Tag
                >
              </Tooltip>
            </div>
            <div v-else class="flex justify-center">
              <Popover>
                <template #content>
                  <div
                    class="flex max-h-[300px] max-w-[400px] flex-col gap-1 overflow-y-auto"
                  >
                    <Tooltip
                      v-for="url in row.history_package_urls"
                      :key="url"
                      :title="url"
                    >
                      <Tag
                        class="block max-w-[360px] overflow-hidden truncate text-[13px]"
                        >{{ url }}</Tag
                      >
                    </Tooltip>
                  </div>
                </template>
                <Tag
                  class="cursor-pointer"
                  color="blue"
                  style="margin-right: 0"
                >
                  {{ row.history_package_urls.length }} 个
                </Tag>
              </Popover>
            </div>
          </template>
        </template>

        <template #history_package_urls_edit="{ row }">
          <div class="flex max-h-[70px] flex-col overflow-y-auto py-1">
            <div
              v-for="(url, index) in row.history_package_urls"
              :key="index"
              class="flex items-center gap-1"
            >
              <span class="flex-1 truncate" :title="url">{{ url }}</span>
              <span
                class="cursor-pointer text-[16px] text-gray-600 hover:text-red-500"
                @click="row.history_package_urls.splice(index, 1)"
                >×</span
              >
            </div>
          </div>
        </template>

        <template #pixel_edit="{ row }">
          <Input v-model:value="row.pixel_name" style="width: 100%" />
        </template>

        <template #page_id_header>
          <div class="flex items-center justify-center gap-1">
            <span>主页ID</span>
            <Popover trigger="click" placement="bottom" destroy-tooltip-on-hide>
              <template #content>
                <div class="w-[360px]">
                  <Input
                    v-model:value="pageSearchKw"
                    allow-clear
                    placeholder="输入主页名称搜索"
                    @change="searchPagesByName(pageSearchKw)"
                  />
                  <div class="mt-2 max-h-[240px] overflow-y-auto">
                    <div
                      v-if="pageSearchLoading"
                      class="py-4 text-center text-xs text-gray-400"
                    >
                      搜索中…
                    </div>
                    <template v-else-if="pageSearchResults.length">
                      <div
                        v-for="item in pageSearchResults"
                        :key="item.id"
                        class="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-1 py-1 last:border-0 hover:bg-gray-50"
                        @click="copyPageId(item.id)"
                      >
                        <span class="min-w-0 flex-1 truncate">
                          {{ item.name }}
                        </span>
                        <span class="font-mono text-xs text-gray-400">
                          {{ item.id }}
                        </span>
                      </div>
                    </template>
                    <div v-else class="py-4 text-center text-xs text-gray-400">
                      {{
                        pageSearchKw ? '未匹配到主页' : '点击结果行复制主页ID'
                      }}
                    </div>
                  </div>
                </div>
              </template>
              <Button type="link" class="px-0">搜ID</Button>
            </Popover>
          </div>
        </template>

        <template #page_id_edit="{ row }">
          <AutoComplete
            v-model:value="row.page_id"
            :options="pageEditOptions"
            :filter-option="false"
            placeholder="主页ID, 输入名称可搜索"
            style="width: 100%"
            @search="searchPagesByName"
          />
        </template>

        <template #action="{ row }">
          <template v-if="hasEditStatus(row)">
            <Button
              :loading="loadingSave"
              @click="saveRowEvent(row)"
              class="mr-2"
              danger
            >
              保存
            </Button>
            <Button @click="cancelRowEvent()">取消</Button>
          </template>
          <template v-else>
            <Button @click="editRowEvent(row)" class="mr-2"> 编辑 </Button>
            <Button danger @click="handleDelete(row)"> 删除 </Button>
          </template>
        </template>
      </Grid>
      <Modal
        v-model:open="showBatchModal"
        title="批量编辑代理线配置"
        :confirm-loading="loadingBatch"
        destroy-on-close
        @ok="handleBatchConfirm"
      >
        <div class="grid grid-cols-2 gap-x-4 gap-y-3">
          <div>
            <div class="mb-1">投放链接</div>
            <Input v-model:value="batchForm.package_url" placeholder="请输入" />
          </div>
          <div>
            <div class="mb-1">像素名称(创建广告时必填)</div>
            <Input v-model:value="batchForm.pixel_name" placeholder="请输入" />
          </div>
          <div>
            <div class="mb-1">优化师(关联数据需要)</div>
            <Select
              :value="batchForm.optimizer"
              placeholder="请选择"
              style="width: 100%"
              :options="userOptions"
              :allow-clear="true"
              show-search
              :filter-option="filterUserOption"
              @change="
                (val) =>
                  (batchForm.optimizer =
                    typeof val === 'string' ? val : undefined)
              "
            />
          </div>
          <div>
            <div class="mb-1">包类型</div>
            <Select
              :value="batchForm.package_type"
              class="w-full"
              placeholder="请选择"
              :allow-clear="true"
              :options="[
                { label: 'W2A', value: 'W2A' },
                { label: 'PWA', value: 'PWA' },
                { label: 'Store', value: 'Store' },
              ]"
              @change="
                (val) =>
                  (batchForm.package_type =
                    typeof val === 'string' ? val : undefined)
              "
            />
          </div>
          <div>
            <div class="mb-1">系列目标</div>
            <Select
              :value="batchForm.objective"
              class="w-full"
              placeholder="请选择"
              :allow-clear="true"
              :options="objectiveOptions"
              @change="
                (val) => (batchForm.objective = (val as string) || undefined)
              "
            />
          </div>
          <div>
            <div class="mb-1">包名</div>
            <Input
              v-model:value="batchForm.package_name"
              placeholder="请输入"
            />
          </div>
          <div></div>
          <div>
            <div class="mb-1">预算上限</div>
            <Input
              :value="batchForm.budget_cap"
              placeholder="请输入"
              @update:value="(v) => (batchForm.budget_cap = v)"
            />
          </div>
          <div>
            <div class="mb-1">预算下限</div>
            <Input
              :value="batchForm.budget_floor"
              placeholder="请输入"
              @update:value="(v) => (batchForm.budget_floor = v)"
            />
          </div>
          <div class="flex items-center gap-6">
            <span class="text-sm">是否启用</span>
            <Switch
              :checked="batchForm.enabled"
              @change="(val) => (batchForm.enabled = Boolean(val))"
            />
          </div>
          <div class="flex items-center gap-6">
            <span class="text-sm">自动运行</span>
            <Switch
              :checked="batchForm.auto_run"
              @change="(val) => (batchForm.auto_run = Boolean(val))"
            />
          </div>
          <div class="flex items-center gap-6">
            <span class="text-sm">是否发送</span>
            <Switch
              :checked="batchForm.is_send"
              @change="(val) => (batchForm.is_send = Boolean(val))"
            />
          </div>
        </div>
      </Modal>
    </template>
  </Page>
</template>
