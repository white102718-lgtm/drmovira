<script lang="ts" setup>
import type { VxeGridProps } from '#/adapter/vxe-table';
import type {
  FieldMapItem,
  SpecialAgentMapping,
  TableColumn,
} from '#/api/management/field-map';

import { ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';

import {
  Button,
  Input,
  message,
  Modal,
  Popover,
  Select,
  Switch,
  Tag,
  Textarea,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  addAgentMapping,
  createFieldMap,
  deleteAgentMapping,
  deleteFieldMap,
  getFieldMapList,
  getTableSchemas,
  updateAgentMapping,
  updateFieldMap,
} from '#/api/management/field-map';
import {
  getAgentOptions,
  getPlatOptions,
} from '#/api/management/platform-config';

const loadingSave = ref(false);
const searchKeyword = ref('');

async function handleBatchDelete() {
  const records = gridApi.grid?.getCheckboxRecords?.() || [];
  if (records.length === 0) {
    message.warning('请先选择要删除的字段映射');
    return;
  }
  Modal.confirm({
    cancelText: '取消',
    content: `确定要删除选中的 ${records.length} 条字段映射配置吗？`,
    okText: '确定',
    onOk: async () => {
      await Promise.all(
        records.map((row: FieldMapItem) => deleteFieldMap(row._id)),
      );
      message.success('批量删除成功');
    },
    afterClose: async () => {
      await gridApi.reload();
    },
    title: '批量删除',
  });
}

// 平台选项
const platformOptions = ref<Array<{ label: string; value: string }>>([]);

// 表结构字段选项
const sourceFieldOptions = ref<Array<{ label: string; value: string }>>([]);
const targetFieldOptions = ref<Array<{ label: string; value: string }>>([]);

// 加载表结构
async function loadTableSchemas() {
  try {
    const res = await getTableSchemas();
    const data = res?.data || res;

    // 源字段来自 ad_hourly_detail
    if (data?.ad_hourly_detail) {
      sourceFieldOptions.value = data.ad_hourly_detail.map(
        (col: TableColumn) => ({
          label: col.comment ? `${col.field} (${col.comment})` : col.field,
          value: col.field,
        }),
      );
    }

    // 目标字段来自 ad_hourly_cleaned
    if (data?.ad_hourly_cleaned) {
      targetFieldOptions.value = data.ad_hourly_cleaned.map(
        (col: TableColumn) => ({
          label: col.comment ? `${col.field} (${col.comment})` : col.field,
          value: col.field,
        }),
      );
    }
  } catch (error) {}
}
loadTableSchemas();

// 新增弹窗相关
const addModalVisible = ref(false);
const cloneSourceId = ref('');
const addForm = ref({
  platform_id: '',
  description: '',
  is_active: true,
  default_field_mappings: {} as Record<string, string>,
  special_agent_mappings: [] as SpecialAgentMapping[],
});
const addLoading = ref(false);

// 字段映射编辑相关
const mappingModalVisible = ref(false);
const currentPlatform = ref<FieldMapItem | null>(null);
const editingMappings = ref<Array<{ key: string; value: string }>>([]);

// 特殊代理线映射弹窗
const [AgentModal, agentModalApi] = useVbenModal();
const agentOptionsData = ref<Array<{ label: string; value: string }>>([]);
const specialMappings = ref<SpecialAgentMapping[]>([]);

// 编辑特殊代理线映射
const editAgentModalVisible = ref(false);
const editingAgentMapping = ref<{
  agent_line: string;
  description: string;
  field_mappings: Array<{ key: string; value: string }>;
  is_active: boolean;
}>({
  agent_line: '',
  description: '',
  is_active: true,
  field_mappings: [],
});
const isNewAgentMapping = ref(false);
const agentMappingLoading = ref(false);

// 加载平台选项
async function loadPlatformOptions() {
  try {
    const res = await getPlatOptions();
    if (Array.isArray(res)) {
      platformOptions.value = res.map((item: string) => ({
        label: item,
        value: item,
      }));
    }
  } catch (error) {}
}
loadPlatformOptions();

const gridOptions: VxeGridProps<FieldMapItem> = {
  autoResize: true,
  border: true,
  checkboxConfig: {
    highlight: true,
  },
  columns: [
    { type: 'checkbox', width: 50 },
    { title: '序号', type: 'seq', width: 80 },
    {
      field: '_id',
      minWidth: 180,
      title: '平台ID',
    },
    {
      field: 'description',
      minWidth: 200,
      title: '描述',
      editRender: {},
      slots: { edit: 'description_edit' },
    },
    {
      field: 'default_field_mappings',
      minWidth: 300,
      title: '默认字段映射',
      slots: { default: 'mappings_display' },
    },
    {
      field: 'special_agent_mappings',
      minWidth: 150,
      title: '特殊代理线数',
      slots: { default: 'special_count' },
    },
    {
      field: 'is_active',
      title: '是否启用',
      width: 120,
      editRender: {},
      slots: {
        default: 'is_active_default',
        edit: 'is_active_edit',
      },
    },
    {
      field: 'updated_at',
      title: '更新时间',
      width: 180,
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
    },
    {
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      width: 360,
    },
  ],
  editConfig: {
    mode: 'row',
    showStatus: true,
    trigger: 'manual',
    autoClear: false,
  },
  height: window.innerHeight - 140,
  keepSource: true,
  pagerConfig: {
    enabled: true,
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        try {
          const res = await getFieldMapList({
            platform_id: searchKeyword.value.trim() || undefined,
          });
          const data = res?.data || res;
          const items = data?.items || [];

          return {
            page: page.currentPage || 1,
            pageSize: page.pageSize || 20,
            total: data?.total || items.length,
            items,
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

function hasEditStatus(row: FieldMapItem) {
  return gridApi.grid?.isEditByRow(row);
}

function editRowEvent(row: FieldMapItem) {
  gridApi.grid?.setEditRow(row);
}

async function saveRowEvent(row: FieldMapItem) {
  loadingSave.value = true;
  try {
    const changedData: any = {};
    const fields = ['description', 'is_active'];

    fields.forEach((field) => {
      if (gridApi.grid?.isUpdateByRow(row, field)) {
        changedData[field] = row[field as keyof FieldMapItem];
      }
    });

    if (Object.keys(changedData).length > 0) {
      await updateFieldMap(row._id, changedData);
      message.success('保存成功');
    } else {
      message.info('没有修改任何内容');
    }

    await gridApi.grid?.clearEdit();
    await gridApi.reload();
  } finally {
    loadingSave.value = false;
  }
}

function cancelRowEvent() {
  gridApi.grid?.clearEdit();
}

async function handleDelete(row: FieldMapItem) {
  Modal.confirm({
    cancelText: '取消',
    content: `确定要删除平台 "${row._id}" 的字段映射配置吗？`,
    okText: '确定',
    onOk: async () => {
      await deleteFieldMap(row._id);
      message.success('删除成功');
    },
    afterClose: async () => {
      await gridApi.reload();
    },
    title: '确认删除',
  });
}

// 打开新增弹窗
function openAddModal() {
  cloneSourceId.value = '';
  addForm.value = {
    platform_id: '',
    description: '',
    is_active: true,
    default_field_mappings: {},
    special_agent_mappings: [],
  };
  addModalVisible.value = true;
}

// 克隆行 - 复制当前行信息打开新增弹窗
function handleClone(row: FieldMapItem) {
  cloneSourceId.value = row._id;
  addForm.value = {
    platform_id: '',
    description: row.description || '',
    is_active: row.is_active,
    default_field_mappings: { ...(row.default_field_mappings || {}) },
    special_agent_mappings: JSON.parse(
      JSON.stringify(row.special_agent_mappings || []),
    ),
  };
  addModalVisible.value = true;
}

// 确认新增
async function handleAddConfirm() {
  if (!addForm.value.platform_id) {
    message.warning('请选择平台');
    return;
  }

  addLoading.value = true;
  try {
    await createFieldMap(addForm.value.platform_id, {
      description: addForm.value.description || undefined,
      is_active: addForm.value.is_active,
      default_field_mappings: addForm.value.default_field_mappings,
      special_agent_mappings: addForm.value.special_agent_mappings,
    });
    message.success('新增成功');
    addModalVisible.value = false;
    cloneSourceId.value = '';
    await gridApi.reload();
  } finally {
    addLoading.value = false;
  }
}

// 打开字段映射编辑弹窗
function openMappingModal(row: FieldMapItem) {
  currentPlatform.value = row;
  const mappings = row.default_field_mappings || {};
  editingMappings.value = Object.entries(mappings).map(([key, value]) => ({
    key,
    value,
  }));
  mappingModalVisible.value = true;
}

// 添加映射行
function addMappingRow() {
  editingMappings.value.push({ key: '', value: '' });
}

// 删除映射行
function removeMappingRow(index: number) {
  editingMappings.value.splice(index, 1);
}

// 保存字段映射
async function saveMappings() {
  if (!currentPlatform.value) return;

  const mappings: Record<string, string> = {};
  for (const item of editingMappings.value) {
    if (item.key.trim()) {
      mappings[item.key.trim()] = item.value.trim();
    }
  }

  try {
    await updateFieldMap(currentPlatform.value._id, {
      default_field_mappings: mappings,
    });
    message.success('保存成功');
    mappingModalVisible.value = false;
    await gridApi.reload();
  } catch {
    // handled by request interceptor
  }
}

// 打开特殊代理线弹窗
async function openAgentModal(row: FieldMapItem) {
  currentPlatform.value = row;
  specialMappings.value = row.special_agent_mappings || [];

  try {
    const res = await getAgentOptions(row._id);
    if (Array.isArray(res)) {
      const platformData = res.find(
        (item: any) => item._id === row._id || item.game_platform === row._id,
      );
      agentOptionsData.value =
        platformData && Array.isArray(platformData.agent_lines)
          ? platformData.agent_lines.map((line: string) => ({
              label: line,
              value: line,
            }))
          : [];
    }
  } catch (error) {
    agentOptionsData.value = [];
  }

  agentModalApi.open();
}

// 打开新增代理线映射弹窗
function openAddAgentModal() {
  isNewAgentMapping.value = true;
  editingAgentMapping.value = {
    agent_line: '',
    description: '',
    is_active: true,
    field_mappings: [{ key: '', value: '' }],
  };
  editAgentModalVisible.value = true;
}

// 打开编辑代理线映射弹窗
function openEditAgentModal(mapping: SpecialAgentMapping) {
  isNewAgentMapping.value = false;
  editingAgentMapping.value = {
    agent_line: mapping.agent_line,
    description: mapping.description || '',
    is_active: mapping.is_active,
    field_mappings: Object.entries(mapping.field_mappings || {}).map(
      ([key, value]) => ({ key, value }),
    ),
  };
  if (editingAgentMapping.value.field_mappings.length === 0) {
    editingAgentMapping.value.field_mappings.push({ key: '', value: '' });
  }
  editAgentModalVisible.value = true;
}

// 添加代理线映射行
function addAgentMappingRow() {
  editingAgentMapping.value.field_mappings.push({ key: '', value: '' });
}

// 删除代理线映射行
function removeAgentMappingRow(index: number) {
  editingAgentMapping.value.field_mappings.splice(index, 1);
}

// 保存代理线映射
async function saveAgentMapping() {
  if (!currentPlatform.value) return;

  if (!editingAgentMapping.value.agent_line) {
    message.warning('请选择代理线');
    return;
  }

  const fieldMappings: Record<string, string> = {};
  for (const item of editingAgentMapping.value.field_mappings) {
    if (item.key.trim()) {
      fieldMappings[item.key.trim()] = item.value.trim();
    }
  }

  agentMappingLoading.value = true;
  try {
    if (isNewAgentMapping.value) {
      await addAgentMapping(currentPlatform.value._id, {
        agent_line: editingAgentMapping.value.agent_line,
        field_mappings: fieldMappings,
        description: editingAgentMapping.value.description || undefined,
        is_active: editingAgentMapping.value.is_active,
      });
      message.success('添加成功');
    } else {
      await updateAgentMapping(
        currentPlatform.value._id,
        editingAgentMapping.value.agent_line,
        {
          field_mappings: fieldMappings,
          description: editingAgentMapping.value.description || undefined,
          is_active: editingAgentMapping.value.is_active,
        },
      );
      message.success('更新成功');
    }

    editAgentModalVisible.value = false;
    await gridApi.reload();

    // 刷新特殊映射列表
    const updatedData = await getFieldMapList({
      platform_id: currentPlatform.value._id,
    });
    const items = updatedData?.data?.items || updatedData?.items || [];
    const updated = items.find(
      (item: FieldMapItem) => item._id === currentPlatform.value?._id,
    );
    if (updated) {
      specialMappings.value = updated.special_agent_mappings || [];
    }
  } finally {
    agentMappingLoading.value = false;
  }
}

// 删除代理线映射
async function handleDeleteAgentMapping(mapping: SpecialAgentMapping) {
  if (!currentPlatform.value) return;

  Modal.confirm({
    cancelText: '取消',
    content: `确定要删除代理线 "${mapping.agent_line}" 的特殊映射吗？`,
    okText: '确定',
    onOk: async () => {
      await deleteAgentMapping(currentPlatform.value!._id, mapping.agent_line);
      message.success('删除成功');

      // 刷新特殊映射列表
      const updatedData = await getFieldMapList({
        platform_id: currentPlatform.value!._id,
      });
      const items = updatedData?.data?.items || updatedData?.items || [];
      const updated = items.find(
        (item: FieldMapItem) => item._id === currentPlatform.value?._id,
      );
      if (updated) {
        specialMappings.value = updated.special_agent_mappings || [];
      }
      await gridApi.reload();
    },
    title: '确认删除',
  });
}

// Select 搜索过滤
function filterOption(input: string, option: any) {
  const label = option.label || option.value || '';
  return label.toLowerCase().includes(input.toLowerCase());
}
</script>

<template>
  <div>
    <Page class="[&>div]:m-0 [&>div]:p-0">
      <Grid>
        <template #toolbar-tools>
          <div class="flex w-full items-center justify-between gap-5">
            <div class="flex items-center gap-3">
              <Input
                v-model:value="searchKeyword"
                placeholder="搜索平台ID"
                class="text-[14px]"
                style="width: 200px"
                allow-clear
                @press-enter="gridApi.reload()"
              >
                <template #suffix>
                  <span
                    class="icon-[ant-design--search-outlined] cursor-pointer text-lg"
                    @click="gridApi.reload()"
                  ></span>
                </template>
              </Input>
            </div>
            <Button danger @click="handleBatchDelete"> 批量删除 </Button>
            <Button type="primary" @click="openAddModal"> 新增字段映射 </Button>
          </div>
        </template>

        <!-- 映射显示 -->
        <template #mappings_display="{ row }">
          <Popover
            v-if="
              row.default_field_mappings &&
              Object.keys(row.default_field_mappings).length > 0
            "
            placement="bottom"
            trigger="click"
          >
            <template #content>
              <div class="max-h-[300px] max-w-[500px] overflow-y-auto">
                <div
                  v-for="(value, key) in row.default_field_mappings"
                  :key="key"
                  class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:border-0 dark:border-gray-700"
                >
                  <span class="font-medium text-blue-600">{{ key }}</span>
                  <span class="text-gray-400">-></span>
                  <span class="font-medium text-green-600">{{ value }}</span>
                </div>
              </div>
            </template>
            <Tag color="blue" class="cursor-pointer">
              {{ Object.keys(row.default_field_mappings).length }} 个映射
            </Tag>
          </Popover>
          <span v-else class="text-gray-400">-</span>
        </template>

        <!-- 特殊代理线数量 -->
        <template #special_count="{ row }">
          <Popover
            v-if="row.special_agent_mappings?.length > 0"
            placement="bottom"
            trigger="click"
          >
            <template #content>
              <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
                <div
                  v-for="mapping in row.special_agent_mappings"
                  :key="mapping.agent_line"
                  class="mb-2 border-b border-gray-100 pb-2 last:border-0 dark:border-gray-700"
                >
                  <div class="mb-1 flex items-center gap-2">
                    <span class="font-medium">{{ mapping.agent_line }}</span>
                    <Tag :color="mapping.is_active ? 'green' : 'default'">
                      {{ mapping.is_active ? '启用' : '禁用' }}
                    </Tag>
                  </div>
                  <div class="text-xs text-gray-500">
                    {{ Object.keys(mapping.field_mappings || {}).length }}
                    个字段映射
                  </div>
                </div>
              </div>
            </template>
            <Tag color="orange" class="cursor-pointer">
              {{ row.special_agent_mappings.length }} 个
            </Tag>
          </Popover>
          <span v-else class="text-gray-400">-</span>
        </template>

        <!-- 是否启用 -->
        <template #is_active_default="{ row }">
          <Switch v-model:checked="row.is_active" disabled />
        </template>
        <template #is_active_edit="{ row }">
          <Switch v-model:checked="row.is_active" />
        </template>

        <!-- 描述编辑 -->
        <template #description_edit="{ row }">
          <Input v-model:value="row.description" placeholder="请输入描述" />
        </template>

        <!-- 操作列 -->
        <template #action="{ row }">
          <div class="flex items-center justify-center gap-1 whitespace-nowrap">
            <template v-if="hasEditStatus(row)">
              <Button :loading="loadingSave" @click="saveRowEvent(row)" danger>
                保存
              </Button>
              <Button @click="cancelRowEvent()">取消</Button>
            </template>
            <template v-else>
              <Button @click="openMappingModal(row)"> 编辑映射 </Button>
              <Button @click="openAgentModal(row)"> 特殊代理线 </Button>
              <Button @click="editRowEvent(row)">编辑</Button>
              <Button @click="handleClone(row)">克隆</Button>
              <Button danger @click="handleDelete(row)"> 删除 </Button>
            </template>
          </div>
        </template>
      </Grid>
    </Page>

    <!-- 新增字段映射弹窗 -->
    <Modal
      v-model:open="addModalVisible"
      :title="
        cloneSourceId ? `克隆字段映射（来自 ${cloneSourceId}）` : '新增字段映射'
      "
      :confirm-loading="addLoading"
      ok-text="确定"
      cancel-text="取消"
      @ok="handleAddConfirm"
    >
      <div class="space-y-4 py-4">
        <div>
          <div class="mb-2 text-sm">
            <span class="text-red-500">*</span> 平台
          </div>
          <Select
            v-model:value="addForm.platform_id"
            :options="platformOptions"
            placeholder="请选择平台"
            style="width: 100%"
            show-search
          />
        </div>
        <div>
          <div class="mb-2 text-sm">描述</div>
          <Input v-model:value="addForm.description" placeholder="请输入描述" />
        </div>
        <div>
          <div class="mb-2 text-sm">是否启用</div>
          <Switch v-model:checked="addForm.is_active" />
        </div>
      </div>
    </Modal>

    <!-- 编辑字段映射弹窗 -->
    <Modal
      v-model:open="mappingModalVisible"
      :title="`编辑字段映射 - ${currentPlatform?._id || ''}`"
      width="600px"
      ok-text="保存"
      cancel-text="取消"
      @ok="saveMappings"
    >
      <div class="py-4">
        <div class="mb-4 flex items-center justify-between">
          <span class="text-sm text-gray-600"
            >字段映射配置（源字段 -> 目标字段）</span
          >
          <Button @click="addMappingRow">添加映射</Button>
        </div>
        <div class="max-h-[400px] space-y-2 overflow-y-auto">
          <div
            v-for="(item, index) in editingMappings"
            :key="index"
            class="flex items-center gap-2"
          >
            <Select
              v-model:value="item.key"
              :options="sourceFieldOptions"
              placeholder="源字段"
              style="width: 220px"
              show-search
              :filter-option="filterOption"
              allow-clear
            />
            <span class="text-gray-400">-></span>
            <Select
              v-model:value="item.value"
              :options="targetFieldOptions"
              placeholder="目标字段"
              style="width: 220px"
              show-search
              :filter-option="filterOption"
              allow-clear
            />
            <Button danger @click="removeMappingRow(index)"> 删除 </Button>
          </div>
          <div
            v-if="editingMappings.length === 0"
            class="py-4 text-center text-gray-400"
          >
            暂无映射配置，点击"添加映射"开始配置
          </div>
        </div>
      </div>
    </Modal>

    <!-- 特殊代理线映射弹窗 -->
    <AgentModal
      :title="`特殊代理线映射 - ${currentPlatform?._id || ''}`"
      class="w-[800px]"
      :destroy-on-close="true"
      :footer="false"
    >
      <div class="py-4">
        <div class="mb-4 flex items-center justify-between">
          <span class="text-sm text-gray-600">
            特殊代理线映射可覆盖默认映射配置
          </span>
          <Button type="primary" @click="openAddAgentModal">
            添加特殊代理线
          </Button>
        </div>

        <div
          v-if="specialMappings.length === 0"
          class="py-8 text-center text-gray-400"
        >
          暂无特殊代理线映射配置
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="mapping in specialMappings"
            :key="mapping.agent_line"
            class="rounded-lg border p-4"
          >
            <div class="mb-2 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <span class="font-medium">{{ mapping.agent_line }}</span>
                <Switch
                  :checked="mapping.is_active"
                  disabled
                  checked-children="启用"
                  un-checked-children="禁用"
                />
              </div>
              <div class="flex gap-2">
                <Button @click="openEditAgentModal(mapping)"> 编辑 </Button>
                <Button danger @click="handleDeleteAgentMapping(mapping)">
                  删除
                </Button>
              </div>
            </div>
            <div v-if="mapping.description" class="mb-2 text-sm text-gray-500">
              {{ mapping.description }}
            </div>
            <div
              v-if="
                mapping.field_mappings &&
                Object.keys(mapping.field_mappings).length > 0
              "
              class="flex flex-wrap gap-2"
            >
              <Tag
                v-for="(value, key) in mapping.field_mappings"
                :key="key"
                color="processing"
                class="text-xs"
              >
                {{ key }} -> {{ value }}
              </Tag>
            </div>
            <div v-else class="text-sm text-gray-400">暂无字段映射</div>
          </div>
        </div>
      </div>
    </AgentModal>

    <!-- 编辑/新增特殊代理线映射弹窗 -->
    <Modal
      v-model:open="editAgentModalVisible"
      :title="isNewAgentMapping ? '添加特殊代理线映射' : '编辑特殊代理线映射'"
      width="600px"
      :confirm-loading="agentMappingLoading"
      ok-text="保存"
      cancel-text="取消"
      @ok="saveAgentMapping"
    >
      <div class="space-y-4 py-4">
        <div>
          <div class="mb-2 text-sm">
            <span class="text-red-500">*</span> 代理线
          </div>
          <Select
            v-model:value="editingAgentMapping.agent_line"
            :options="agentOptionsData"
            placeholder="请选择代理线"
            style="width: 100%"
            show-search
            :disabled="!isNewAgentMapping"
          />
        </div>
        <div>
          <div class="mb-2 text-sm">描述</div>
          <Textarea
            v-model:value="editingAgentMapping.description"
            placeholder="请输入描述"
            :rows="2"
          />
        </div>
        <div>
          <div class="mb-2 text-sm">是否启用</div>
          <Switch v-model:checked="editingAgentMapping.is_active" />
        </div>
        <div>
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm">字段映射</span>
            <Button @click="addAgentMappingRow">添加</Button>
          </div>
          <div class="max-h-[200px] space-y-2 overflow-y-auto">
            <div
              v-for="(item, index) in editingAgentMapping.field_mappings"
              :key="index"
              class="flex items-center gap-2"
            >
              <Select
                v-model:value="item.key"
                :options="sourceFieldOptions"
                placeholder="源字段"
                style="width: 200px"
                show-search
                :filter-option="filterOption"
                allow-clear
              />
              <span class="text-gray-400">-></span>
              <Select
                v-model:value="item.value"
                :options="targetFieldOptions"
                placeholder="目标字段"
                style="width: 200px"
                show-search
                :filter-option="filterOption"
                allow-clear
              />
              <Button
                danger
                @click="removeAgentMappingRow(index)"
                :disabled="editingAgentMapping.field_mappings.length <= 1"
              >
                删除
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>
