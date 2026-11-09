<script lang="ts" setup>
import type { UploadChangeParam, UploadFile } from 'ant-design-vue';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { PlatformConfigItem } from '#/api/management/platform-config';

import { onMounted, ref, watch, watchEffect } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import {
  Button,
  Input,
  InputNumber,
  InputSearch,
  message,
  Modal,
  Select,
  Switch,
  Upload,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  createPlatformConfig,
  deletePlatformConfig,
  downloadImportTemplate,
  getDepartmentOptions,
  getPlatformConfigList,
  importPlatformConfig,
  updatePlatformConfig,
} from '#/api/management/platform-config';
import facebookCountries from '#/data/facebook_countries.json';

const props = defineProps<{
  loading?: boolean;
  platforms: PlatformConfigItem[];
}>();

const emit = defineEmits<{
  refresh: [];
}>();

const route = useRoute();
const router = useRouter();

const countryOptions = facebookCountries.map((c) => ({
  label: `${c.name} (${c.code})`,
  value: c.code,
}));

const countryMap = Object.fromEntries(
  facebookCountries.map((c) => [c.code, `${c.name} (${c.code})`]),
);

const loadingSave = ref(false);
const loadingAdd = ref(false);
const newPlatformName = ref('');
const searchKeyword = ref('');
const selectedDepartment = ref<string | undefined>(undefined);
const departmentOptions = ref<{ label: string; value: string }[]>([]);

onMounted(async () => {
  try {
    const names = await getDepartmentOptions();
    departmentOptions.value = (names as string[]).map((name) => ({
      label: name,
      value: name,
    }));
  } catch {}
});

const gridOptions: VxeGridProps<PlatformConfigItem> = {
  autoResize: true,
  border: true,
  columns: [
    { title: '序号', type: 'seq', width: 60 },
    {
      align: 'center',
      editRender: {},
      slots: { default: 'game_platform_default', edit: 'game_platform_edit' },
      field: '_id',
      minWidth: 320,
      title: '项目名称',
    },
    {
      editRender: {},
      slots: { default: 'target_region_default', edit: 'target_region_edit' },
      field: 'target_region',
      title: '投放地区',
      width: 200,
    },
    {
      editRender: {},
      slots: { edit: 'total_budget_edit' },
      field: 'total_budget',
      title: '总预算',
      width: 120,
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
      field: 'visible',
      title: '是否显示',
      width: 130,
      editRender: {},
      slots: {
        default: 'visible_default',
        edit: 'visible_edit',
      },
      titleHelp: {
        message: '仅用于代理线选项的显示, 防止显示代理线过多造成卡顿',
      },
    },
    {
      field: 'attribution_platform',
      title: '归因平台',
      width: 160,
      editRender: {},
      slots: { edit: 'attribution_platform_edit' },
    },
    {
      editRender: {},
      slots: { default: 'departments_default', edit: 'departments_edit' },
      field: 'departments',
      title: '部门',
      width: 200,
    },
    {
      field: 'start_time',
      title: '开始时间',
      width: 160,
      slots: {
        default: ({ row }) => (row.start_time ? [row.start_time] : []),
      },
    },
    {
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      width: 150,
    },
  ],
  editConfig: {
    mode: 'row',
    showStatus: true,
    trigger: 'manual',
  },
  height: window.innerHeight - 140,
  keepSource: true,
  pagerConfig: {
    enabled: true,
    pageSize: 20,
    currentPage: Number(route.query.platformPage) || 1,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        try {
          const currentPage = page.currentPage || 1;
          const pageSize = page.pageSize || 20;
          const params: Record<string, any> = {
            page: currentPage,
            pageSize,
          };
          const keyword = searchKeyword.value.trim();
          if (keyword) params.game_platform = keyword;
          const dept = selectedDepartment.value;
          if (dept) params.department = dept;

          const res = await getPlatformConfigList(params);
          const data = (res as any)?.data || res;
          return {
            page: currentPage,
            pageSize,
            total: data?.total ?? 0,
            items: data?.items ?? [],
          };
        } catch {
          return {
            page: 1,
            pageSize: 20,
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

watchEffect(() => {
  gridApi.setLoading(props.loading ?? false);
});

// 检查是否有任何行处于编辑状态
function hasAnyRowInEditMode(): boolean {
  if (!gridApi.grid) return false;
  const tableData = gridApi.grid.getTableData();
  if (!tableData || !tableData.fullData) return false;

  return tableData.fullData.some((row: PlatformConfigItem) =>
    gridApi.grid?.isEditByRow(row),
  );
}

function hasEditStatus(row: PlatformConfigItem) {
  return gridApi.grid?.isEditByRow(row);
}

function editRowEvent(row: PlatformConfigItem) {
  (row as any)._originalId = row._id;
  gridApi.grid?.setEditRow(row);
}

async function saveRowEvent(row: PlatformConfigItem) {
  loadingSave.value = true;
  try {
    if (row.total_budget != null && row.total_budget !== '') {
      row.total_budget = Number(row.total_budget);
    }

    const originalId = (row as any)._originalId ?? row._id;

    // 排除 agent_lines / agent_lines_count，代理线由独立接口管理
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { agent_lines, agent_lines_count, ...updatePayload } = row as any;

    // 兼容旧的字符串格式，统一转为数组
    if (typeof updatePayload.target_region === 'string') {
      updatePayload.target_region = updatePayload.target_region
        ? [updatePayload.target_region]
        : [];
    }

    await (originalId
      ? updatePlatformConfig(originalId, updatePayload)
      : createPlatformConfig(row));

    await gridApi.grid?.clearEdit();
    message.success('保存成功');
    emit('refresh');
    await gridApi.grid?.commitProxy('query');
  } finally {
    loadingSave.value = false;
    if ((row as any)._originalId) {
      delete (row as any)._originalId;
    }
  }
}

function cancelRowEvent(row: PlatformConfigItem) {
  gridApi.grid?.clearEdit();
  gridApi.grid?.revertData(row);
  gridApi.grid?.commitProxy('query');
}

async function handleDelete(row: PlatformConfigItem) {
  Modal.confirm({
    cancelText: '取消',
    content: `确定要删除平台 "${row._id}" 及其所有代理线配置吗？`,
    okText: '确定',
    onOk: async () => {
      await deletePlatformConfig(row._id);
      message.success('删除平台配置成功');
      emit('refresh');
      await gridApi.grid?.commitProxy('query');
    },
    onCancel: () => {},
    title: '确认删除',
  });
}

async function addNewPlatform() {
  if (!newPlatformName.value.trim()) {
    message.warning('请输入平台名称');
    return;
  }

  loadingAdd.value = true;
  try {
    await createPlatformConfig({
      _id: newPlatformName.value.trim(),
    });
    message.success('新增平台成功');
    newPlatformName.value = '';
    emit('refresh');
    await gridApi.grid?.commitProxy('query');
  } finally {
    loadingAdd.value = false;
  }
}

// 批量导入相关
const importModalVisible = ref(false);
const importFileList = ref<UploadFile[]>([]);
const importLoading = ref(false);

function openImportModal() {
  importModalVisible.value = true;
}

function closeImportModal() {
  importModalVisible.value = false;
  importFileList.value = [];
}

function beforeImportUpload(file: File) {
  const allowedTypes = [
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'text/csv',
  ];
  const allowedExtensions = ['.xlsx', '.xls', '.csv'];
  const fileName = file.name.toLowerCase();
  const hasValidExtension = allowedExtensions.some((ext) =>
    fileName.endsWith(ext),
  );

  if (!allowedTypes.includes(file.type) && !hasValidExtension) {
    message.error('只支持 .xlsx, .xls, .csv 格式的文件');
    return Upload.LIST_IGNORE;
  }

  const maxSize = 5 * 1024 * 1024; // 5MB
  if (file.size > maxSize) {
    message.error('文件大小不能超过 5MB');
    return Upload.LIST_IGNORE;
  }

  return false;
}

function handleImportChange(info: UploadChangeParam) {
  importFileList.value = info.fileList.slice(-1);
}

async function handleImportConfirm() {
  if (importFileList.value.length === 0) {
    message.warning('请选择要导入的文件');
    return;
  }

  const file = importFileList.value[0]?.originFileObj;
  if (!file) {
    message.warning('请选择要导入的文件');
    return;
  }

  importLoading.value = true;
  try {
    const data = await importPlatformConfig(file);
    message.success(data || '导入成功');
    closeImportModal();
    emit('refresh');
    reloadToFirstPage();
  } catch {
  } finally {
    importLoading.value = false;
  }
}

// 下载模板
async function handleDownloadTemplate() {
  try {
    const response = await downloadImportTemplate();
    const { filename, content } = response;

    // 将base64内容解码为二进制数据
    const binaryString = atob(content);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    const blob = new Blob([bytes], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}.xlsx`;
    document.body.append(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);

    message.success('模板下载成功');
  } catch {}
}

function syncPlatformPageToUrl(page: number) {
  router.replace({
    query: {
      ...route.query,
      platformPage: page > 1 ? String(page) : undefined,
    },
  });
}

function reloadToFirstPage() {
  syncPlatformPageToUrl(1);
  gridApi.reload();
}

function onPlatformPageChange(e: { currentPage: number }) {
  syncPlatformPageToUrl(e.currentPage);
}

function handleQuickAction(tab: string, platformId: string) {
  router.push({
    query: {
      ...route.query,
      tab,
      platform: platformId,
    },
  });
}
</script>

<template>
  <div>
    <Page class="[&>div]:m-0 [&>div]:p-0">
      <Grid @page-change="onPlatformPageChange">
        <template #toolbar-actions>
          <div
            class="platform-filter-bar flex min-w-0 flex-wrap items-center gap-2"
          >
            <Select
              :value="selectedDepartment"
              placeholder="选择部门"
              style="width: 160px"
              :options="departmentOptions"
              allow-clear
              show-search
              :filter-option="
                (input, option) =>
                  String(option?.label ?? '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
              "
              @change="
                (val) => {
                  selectedDepartment = val ? String(val) : undefined;
                  reloadToFirstPage();
                }
              "
            />
            <Input
              v-model:value="searchKeyword"
              placeholder="前缀查找平台名称"
              class="text-[14px]"
              style="width: 200px"
              allow-clear
              @press-enter="reloadToFirstPage()"
            />
            <Button type="primary" @click="reloadToFirstPage()">搜索</Button>
          </div>
        </template>

        <template #toolbar-tools>
          <div
            class="platform-toolbar-tools flex min-w-0 flex-wrap items-center justify-end gap-2"
          >
            <div class="platform-sync-note text-sm text-gray-500">
              平台数据每 10 分钟自动从 Mpower 系统同步一次
            </div>
            <Button type="primary" @click="openImportModal"> 批量导入 </Button>
            <InputSearch
              v-model:value="newPlatformName"
              class="platform-add-search"
              placeholder="输入项目名称"
              style="width: 260px"
              @keyup.enter="addNewPlatform"
            >
              <template #enterButton>
                <Button :loading="loadingAdd" @click="addNewPlatform">
                  添加平台
                </Button>
              </template>
            </InputSearch>
          </div>
        </template>
        <template #agent_lines_default="{ row }">
          <div class="flex min-h-6 flex-wrap gap-1">
            <template
              v-if="
                Array.isArray(row.agent_lines) && row.agent_lines.length > 0
              "
            >
              <span
                v-for="tag in row.agent_lines.slice(0, 7)"
                :key="tag"
                class="mb-1 mr-1 inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600"
              >
                {{ tag }}
              </span>
              <span
                v-if="row.agent_lines.length > 7"
                class="mb-1 inline-flex items-center text-xs text-gray-500"
              >
                ... (+{{ row.agent_lines.length - 7 }})
              </span>
            </template>
            <span v-else class="text-sm text-gray-400">无代理线</span>
          </div>
        </template>

        <template #game_platform_default="{ row }">
          <div class="flex items-center justify-center gap-2">
            <span>{{ row._id }}</span>
            <div class="flex items-center gap-1">
              <Button
                type="link"
                class="p-0"
                @click.stop="handleQuickAction('PlatformManageConfig', row._id)"
              >
                代理线配置
              </Button>
              <span class="text-gray-300">|</span>
              <!-- <Button
                type="link"
                class=" p-0"
                @click.stop="handleQuickAction('PlatformKpiConfig', row._id)"
              >
                KPI配置
              </Button> -->
              <!-- <span class="text-gray-300">|</span> -->
              <Button
                type="link"
                class="p-0"
                @click.stop="handleQuickAction('TagConfig', row._id)"
              >
                产品建档
              </Button>
            </div>
          </div>
        </template>

        <template #game_platform_edit="{ row }">
          <Input v-model:value="row._id" style="width: 100%" />
        </template>

        <template #target_region_default="{ row }">
          <div class="flex flex-wrap gap-1">
            <template
              v-if="
                Array.isArray(row.target_region) && row.target_region.length > 0
              "
            >
              <span
                v-for="code in row.target_region.slice(0, 5)"
                :key="code"
                class="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600"
                >{{ countryMap[code] ?? code }}
              </span>
              <span
                v-if="row.target_region.length > 5"
                class="text-xs text-gray-400"
              >
                +{{ row.target_region.length - 5 }}
              </span>
            </template>
          </div>
        </template>

        <template #target_region_edit="{ row }">
          <Select
            :value="
              Array.isArray(row.target_region)
                ? row.target_region.filter(Boolean)
                : []
            "
            mode="multiple"
            @change="(val) => (row.target_region = val)"
            style="width: 100%"
            placeholder="选择投放地区"
            :options="countryOptions"
            :filter-option="
              (input, option) =>
                (option?.label ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase()) ||
                (option?.value ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
            "
            :max-tag-count="3"
            allow-clear
            show-search
          />
        </template>

        <template #total_budget_edit="{ row }">
          <InputNumber v-model:value="row.total_budget" style="width: 100%" />
        </template>

        <template #agent_lines_edit="{ row }">
          <div class="h-auto min-h-8 w-full">
            <Select
              v-model:value="row.agent_lines"
              mode="tags"
              class="w-full"
              placeholder="输入代理线并按回车添加"
              :allow-clear="true"
              :dropdown-match-select-width="false"
              :open="false"
              :show-search="false"
              :dropdown-style="{ display: 'none' }"
              :list-height="0"
              @change="
                (value) => {
                  row.agent_lines_count = Array.isArray(value)
                    ? value.length
                    : 0;
                }
              "
            />
          </div>
        </template>
        <template #enabled_default="{ row }">
          <Switch v-model:checked="row.enabled" disabled />
        </template>
        <template #enabled_edit="{ row }">
          <Switch v-model:checked="row.enabled" />
        </template>

        <template #visible_default="{ row }">
          <Switch
            v-model:checked="row.visible"
            checked-children="显示"
            un-checked-children="隐藏"
            disabled
          />
        </template>
        <template #visible_edit="{ row }">
          <Switch
            v-model:checked="row.visible"
            checked-children="显示"
            un-checked-children="隐藏"
          />
        </template>

        <template #attribution_platform_edit="{ row }">
          <Input v-model:value="row.attribution_platform" style="width: 100%" />
        </template>

        <template #departments_default="{ row }">
          <div class="flex flex-col gap-1">
            <div
              v-if="
                Array.isArray(row.departments) && row.departments.length > 0
              "
              class="flex flex-wrap items-center gap-1"
            >
              <span class="w-8 shrink-0 text-xs text-gray-500">部门</span>
              <span
                v-for="dept in row.departments"
                :key="`dept-${dept}`"
                class="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600"
              >
                {{ dept }}
              </span>
            </div>
            <div
              v-if="
                Array.isArray(row.internal_team) && row.internal_team.length > 0
              "
              class="flex flex-wrap items-center gap-1"
            >
              <span class="w-8 shrink-0 text-xs text-gray-500">内部</span>
              <span
                v-for="t in row.internal_team"
                :key="`in-${t}`"
                class="inline-flex items-center rounded bg-green-50 px-1.5 py-0.5 text-xs text-green-700"
              >
                {{ t }}
              </span>
            </div>
            <div
              v-if="
                Array.isArray(row.external_team) && row.external_team.length > 0
              "
              class="flex flex-wrap items-center gap-1"
            >
              <span class="w-8 shrink-0 text-xs text-gray-500">外部</span>
              <span
                v-for="t in row.external_team"
                :key="`ex-${t}`"
                class="inline-flex items-center rounded bg-orange-50 px-1.5 py-0.5 text-xs text-orange-600"
              >
                {{ t }}
              </span>
            </div>
          </div>
        </template>

        <template #departments_edit="{ row }">
          <Select
            :value="Array.isArray(row.departments) ? row.departments : []"
            mode="multiple"
            @change="(val) => (row.departments = val)"
            style="width: 100%"
            placeholder="选择部门"
            :options="departmentOptions"
            :max-tag-count="2"
            allow-clear
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
            <Button @click="cancelRowEvent(row)">取消</Button>
          </template>
          <template v-else>
            <Button @click="editRowEvent(row)" class="mr-2"> 编辑 </Button>
            <Button danger @click="handleDelete(row)"> 删除 </Button>
          </template>
        </template>
      </Grid>
    </Page>

    <!-- 批量导入弹窗 -->
    <Modal
      v-model:open="importModalVisible"
      title="批量导入任务"
      :confirm-loading="importLoading"
      ok-text="确定"
      cancel-text="取消"
      width="680px"
      @ok="handleImportConfirm"
      @cancel="closeImportModal"
    >
      <div class="py-4">
        <Upload.Dragger
          v-model:file-list="importFileList"
          :before-upload="beforeImportUpload"
          :max-count="1"
          accept=".xlsx,.xls,.csv"
          @change="handleImportChange"
        >
          <p class="ant-upload-drag-icon">
            <span
              class="icon-[ant-design--cloud-upload-outlined] text-4xl text-blue-400"
            ></span>
          </p>
          <p class="ant-upload-text">
            将文件拖到此处，或<span class="text-blue-500">点击选择文件</span>
          </p>
        </Upload.Dragger>
        <div class="mt-3 flex items-center justify-center">
          <p class="text-center text-sm text-gray-400">
            支持 .xlsx, .xls, .csv 格式的文件
          </p>
          <Button type="link" @click="handleDownloadTemplate">下载模板</Button>
        </div>
        <p class="mt-1 text-center text-sm text-gray-400">
          需含有
          <strong class="text-[#666]">
            项目(必填）、渠道号(必填）、投放链接、优化师、像素名称(创建广告时必填)
          </strong>
          等表头
        </p>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.platform-sync-note {
  min-width: 180px;
  max-width: 260px;
  line-height: 1.5;
}

@media (max-width: 1199px) {
  .platform-filter-bar,
  .platform-toolbar-tools {
    width: 100%;
  }

  .platform-toolbar-tools {
    justify-content: flex-start;
  }
}

@media (max-width: 767px) {
  .platform-add-search {
    width: 100% !important;
  }

  .platform-sync-note {
    width: 100%;
    max-width: none;
  }
}

@keyframes marquee {
  0% {
    transform: translateX(100%);
  }

  100% {
    transform: translateX(-100%);
  }
}

.marquee-text {
  display: inline-block;
  animation: marquee 12s linear infinite;
}
</style>
