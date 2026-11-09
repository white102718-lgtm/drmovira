<script lang="ts" setup>
import type {
  ApplicationDefinition,
  ApplicationDefinitionSaveRequest,
  ApprovalConfig,
  ApplicationType,
  ApplicationTypeSaveRequest,
} from '#/api/asset-flow';

import { computed, onMounted, reactive, ref, toRef } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon, Plus, RotateCw, Search } from '@vben/icons';

import { Alert, Button, Card, Input, Tag } from 'ant-design-vue';

import {
  Empty,
  Form,
  FormItem,
  Dropdown,
  InputNumber,
  message,
  Menu,
  MenuItem,
  Modal,
  RadioGroup,
  Select,
  Space,
  Switch,
  Table,
  Textarea,
} from 'ant-design-vue';

import { assetFlowApi } from '#/api';
import { useListRouteState } from '#/composables/use-list-route-state';

defineOptions({ name: 'SystemApplicationManagement' });

const statusOptions = [
  { label: '启用', value: 1 },
  { label: '停用', value: 0 },
];
const visibilityOptions = [
  { label: '全部成员', value: 'all' },
  { label: '仅管理员', value: 'admins' },
];
const resourceApplicationDisplayOptions = [
  { label: '显示', value: true },
  { label: '隐藏', value: false },
];
const iconOptions = [
  'lucide:file-plus-2',
  'lucide:badge-plus',
  'lucide:badge-minus',
  'lucide:wallet-cards',
  'lucide:banknote',
  'lucide:archive',
  'lucide:unlink',
  'lucide:refresh-cw',
].map((value) => ({ label: value, value }));

const columns = [
  { key: 'application', title: '申请', width: 260 },
  {
    dataIndex: 'applicationCode',
    key: 'applicationCode',
    title: '申请编码',
    width: 210,
  },
  { key: 'applicationType', title: '申请类型', width: 170 },
  { key: 'approvalConfig', title: '关联审批配置', width: 230 },
  { dataIndex: 'visibility', key: 'visibility', title: '可见范围', width: 110 },
  {
    dataIndex: 'showInResourceApplication',
    key: 'showInResourceApplication',
    title: '资源申请入口',
    width: 130,
  },
  { dataIndex: 'sortOrder', key: 'sortOrder', title: '排序', width: 80 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 100 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 180 },
  { fixed: 'right' as const, key: 'operation', title: '操作', width: 132 },
];
const typeColumns = [
  { key: 'type', title: '申请类型', width: 260 },
  { dataIndex: 'sortOrder', key: 'sortOrder', title: '排序', width: 90 },
  { key: 'status', title: '状态', width: 100 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 180 },
  { fixed: 'right' as const, key: 'operation', title: '操作', width: 90 },
];

const loading = ref(false);
const definitions = ref<ApplicationDefinition[]>([]);
const approvalConfigs = ref<ApprovalConfig[]>([]);
const applicationTypes = ref<ApplicationType[]>([]);
const applicationPagination = reactive({
  current: 1,
  pageSize: 10,
});
const filters = reactive<{
  approvalConfigId?: string;
  applicationTypeId?: string;
  keyword?: string;
  status?: 0 | 1;
}>({});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: () => loadData(false),
    pagination: {
      defaultPageSize: 10,
      page: toRef(applicationPagination, 'current'),
      pageSize: toRef(applicationPagination, 'pageSize'),
    },
    state: filters,
  });

const modalOpen = ref(false);
const saving = ref(false);
const editingId = ref<string>();
const form = reactive<ApplicationDefinitionSaveRequest>({
  applicationName: '',
  applicationTypeId: '',
  description: '',
  icon: 'lucide:file-plus-2',
  sortOrder: 0,
  showInResourceApplication: true,
  status: 1,
  visibility: 'all',
});
const typeModalOpen = ref(false);
const typeManagerOpen = ref(false);
const typeSaving = ref(false);
const editingTypeId = ref<string>();
const typeForm = reactive<ApplicationTypeSaveRequest>({
  description: '',
  icon: 'lucide:folder-open',
  sortOrder: 0,
  status: 1,
  typeName: '',
});

const modalTitle = computed(() => (editingId.value ? '编辑申请' : '创建申请'));
const approvalConfigOptions = computed(() =>
  approvalConfigs.value.map((config) => ({
    label: `${config.name} · ${config.assetType}${config.enabled ? '' : '（已停用）'}`,
    value: config.id,
  })),
);
const applicationTypeOptions = computed(() =>
  applicationTypes.value.map((type) => ({
    label: type.typeName,
    value: type.id,
  })),
);
async function loadData(resetPage: boolean | Event = true) {
  if (resetPage !== false) applicationPagination.current = 1;
  await commitQueryState();
  loading.value = true;
  try {
    const [itemsResult, configsResult, typesResult] = await Promise.allSettled([
      assetFlowApi.managedApplicationDefinitions({
        approvalConfigId: filters.approvalConfigId,
        keyword: filters.keyword?.trim() || undefined,
        status: filters.status,
      }),
      assetFlowApi.managedConfigs(),
      assetFlowApi.managedApplicationTypes(),
    ]);
    const loadedDefinitions =
      itemsResult.status === 'fulfilled' ? itemsResult.value : [];
    definitions.value = filters.applicationTypeId
      ? loadedDefinitions.filter(
          (definition) =>
            definition.applicationTypeId === filters.applicationTypeId,
        )
      : loadedDefinitions;
    approvalConfigs.value =
      configsResult.status === 'fulfilled' ? configsResult.value : [];
    applicationTypes.value =
      typesResult.status === 'fulfilled' ? typesResult.value : [];
  } finally {
    loading.value = false;
  }
}

async function handleApplicationTableChange(pagination: {
  current?: number;
  pageSize?: number;
}) {
  const pageSizeChanged =
    pagination.pageSize !== undefined &&
    pagination.pageSize !== applicationPagination.pageSize;
  applicationPagination.pageSize =
    pagination.pageSize ?? applicationPagination.pageSize;
  applicationPagination.current = pageSizeChanged
    ? 1
    : (pagination.current ?? applicationPagination.current);
  await commitQueryState();
}

async function resetFilters() {
  await resetQueryState();
  await loadData(false);
}

function openModal(row?: ApplicationDefinition, applicationTypeId?: string) {
  editingId.value = row?.id;
  Object.assign(form, {
    applicationCode: row?.applicationCode,
    applicationName: row?.applicationName ?? '',
    applicationTypeId:
      row?.applicationTypeId ??
      applicationTypeId ??
      filters.applicationTypeId ??
      '',
    description: row?.description ?? '',
    icon: row?.icon ?? 'lucide:file-plus-2',
    sortOrder: row?.sortOrder ?? definitions.value.length * 10 + 10,
    showInResourceApplication: row?.showInResourceApplication ?? true,
    status: row?.status ?? 1,
    visibility: row?.visibility ?? 'all',
  });
  modalOpen.value = true;
}

function openTypeModal(type?: ApplicationType) {
  editingTypeId.value = type?.id;
  Object.assign(typeForm, {
    description: type?.description ?? '',
    icon: type?.icon ?? 'lucide:folder-open',
    sortOrder: type?.sortOrder ?? applicationTypes.value.length * 10 + 10,
    status: type?.status ?? 1,
    typeName: type?.typeName ?? '',
  });
  typeModalOpen.value = true;
}

async function saveDefinition() {
  const applicationName = form.applicationName.trim();
  if (!applicationName) {
    message.warning('请填写申请名称');
    return;
  }
  if (!form.applicationTypeId) {
    message.warning('请选择申请类型');
    return;
  }
  saving.value = true;
  try {
    const payload: ApplicationDefinitionSaveRequest = {
      ...form,
      applicationCode: editingId.value ? form.applicationCode : undefined,
      applicationName,
      description: form.description?.trim() || undefined,
    };
    await (editingId.value
      ? assetFlowApi.updateApplicationDefinition(editingId.value, payload)
      : assetFlowApi.createApplicationDefinition(payload));
    modalOpen.value = false;
    message.success(editingId.value ? '申请已更新' : '申请已创建');
    await loadData();
  } finally {
    saving.value = false;
  }
}

async function saveType() {
  const typeName = typeForm.typeName.trim();
  if (!typeName) {
    message.warning('请填写申请类型名称');
    return;
  }
  typeSaving.value = true;
  try {
    const payload: ApplicationTypeSaveRequest = {
      ...typeForm,
      description: typeForm.description?.trim() || undefined,
      typeName,
    };
    await (editingTypeId.value
      ? assetFlowApi.updateApplicationType(editingTypeId.value, payload)
      : assetFlowApi.createApplicationType(payload));
    typeModalOpen.value = false;
    message.success(editingTypeId.value ? '申请类型已更新' : '申请类型已创建');
    await loadData();
  } finally {
    typeSaving.value = false;
  }
}

async function toggleStatus(row: ApplicationDefinition, checked: boolean) {
  const previous = row.status;
  row.status = checked ? 1 : 0;
  try {
    await assetFlowApi.updateApplicationDefinition(row.id, {
      applicationCode: row.applicationCode,
      applicationName: row.applicationName,
      applicationTypeId: row.applicationTypeId,
      description: row.description,
      icon: row.icon,
      sortOrder: row.sortOrder,
      showInResourceApplication: row.showInResourceApplication,
      status: row.status,
      visibility: row.visibility,
    });
    message.success(checked ? '申请已启用' : '申请已停用');
  } catch {
    row.status = previous;
  }
}

function confirmDeleteDefinition(row: ApplicationDefinition) {
  Modal.confirm({
    cancelText: '取消',
    content: `删除后，“${row.applicationName}”将不再作为申请入口展示，且无法恢复。`,
    okText: '删除',
    okType: 'danger',
    title: '确认删除申请？',
    async onOk() {
      await assetFlowApi.deleteApplicationDefinition(row.id);
      message.success('申请已删除');
      await loadData();
    },
  });
}

function formatDateTime(value?: string) {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 19);
}

onMounted(async () => {
  await restoreFromRoute();
  await loadData(false);
});
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="维护申请入口、展示状态及审批配置关联；多个申请可以共用同一套审批流程。"
    title="申请管理"
  >
    <template #extra>
      <Space>
        <Button @click="typeManagerOpen = true">申请类型管理</Button>
        <Button type="primary" @click="openModal()">
          <Plus class="size-4" aria-hidden="true" />
          创建申请
        </Button>
      </Space>
    </template>

    <Alert
      class="mb-4"
      message="先维护资源申请类型；创建申请时选择所属类型。申请表单与办理表单仍在关联的审批配置中维护。"
      show-icon
      type="info"
    />

    <Card :bordered="false">
      <Form
        class="ux-filter-form mb-4"
        layout="inline"
        @submit.prevent="loadData"
      >
        <FormItem label="关键词">
          <Input
            v-model:value="filters.keyword"
            allow-clear
            class="ux-filter-search"
            placeholder="申请名称或编码"
            @press-enter="loadData"
          />
        </FormItem>
        <FormItem label="申请类型">
          <Select
            v-model:value="filters.applicationTypeId"
            allow-clear
            class="ux-filter-field"
            :options="applicationTypeOptions"
            placeholder="全部申请类型"
          />
        </FormItem>
        <FormItem label="审批配置">
          <Select
            v-model:value="filters.approvalConfigId"
            allow-clear
            class="ux-filter-field"
            :options="approvalConfigOptions"
            placeholder="全部审批配置"
            show-search
            :filter-option="
              (input: string, option: any) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
          />
        </FormItem>
        <FormItem label="状态">
          <Select
            v-model:value="filters.status"
            allow-clear
            class="ux-filter-field"
            :options="statusOptions"
            placeholder="全部状态"
          />
        </FormItem>
        <FormItem>
          <Space class="ux-filter-actions">
            <Button type="primary" @click="loadData">
              <Search aria-hidden="true" class="size-4" />查询
            </Button>
            <Button @click="resetFilters">
              <RotateCw aria-hidden="true" class="size-4" />重置
            </Button>
          </Space>
        </FormItem>
      </Form>

      <Table
        :columns="columns"
        :data-source="definitions"
        :loading="loading"
        :pagination="{
          current: applicationPagination.current,
          pageSize: applicationPagination.pageSize,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
          total: definitions.length,
        }"
        row-key="id"
        :scroll="{ x: 1360 }"
        @change="handleApplicationTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'application'">
            <div class="flex min-w-0 items-center gap-3">
              <span
                class="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg"
              >
                <IconifyIcon
                  :icon="record.icon"
                  aria-hidden="true"
                  class="size-5"
                />
              </span>
              <div class="min-w-0">
                <div class="text-foreground font-medium">
                  {{ record.applicationName }}
                </div>
                <div class="text-muted-foreground mt-0.5 truncate text-xs">
                  {{ record.description }}
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'applicationCode'">
            <span class="font-mono text-xs">{{ record.applicationCode }}</span>
          </template>
          <template v-else-if="column.key === 'applicationType'">
            {{ record.applicationTypeName }}
          </template>
          <template v-else-if="column.key === 'approvalConfig'">
            <template v-if="record.approvalConfigId">
              <div>{{ record.approvalConfigName }}</div>
              <div
                class="text-muted-foreground mt-0.5 flex items-center gap-1 text-xs"
              >
                <span class="font-mono">{{ record.approvalAssetType }}</span>
                <Tag v-if="!record.approvalConfigEnabled" color="warning">
                  配置已停用
                </Tag>
              </div>
            </template>
            <div v-else class="text-muted-foreground flex items-center gap-2">
              <Tag>未关联</Tag>
              <span class="text-xs">请在审批配置中设置</span>
            </div>
          </template>
          <template v-else-if="column.key === 'visibility'">
            {{ record.visibility === 'admins' ? '仅管理员' : '全部成员' }}
          </template>
          <template v-else-if="column.key === 'showInResourceApplication'">
            <Tag
              :color="record.showInResourceApplication ? 'success' : 'default'"
            >
              {{ record.showInResourceApplication ? '显示' : '隐藏' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <Switch
              :checked="record.status === 1"
              checked-children="启用"
              un-checked-children="停用"
              @change="(checked: boolean) => toggleStatus(record, checked)"
            />
          </template>
          <template v-else-if="column.key === 'updatedAt'">
            {{ formatDateTime(record.updatedAt) }}
          </template>
          <template v-else-if="column.key === 'operation'">
            <div class="flex items-center gap-1">
              <Button type="link" @click="openModal(record)">编辑</Button>
              <Dropdown :trigger="['click']">
                <Button type="link">更多</Button>
                <template #overlay>
                  <Menu>
                    <MenuItem
                      key="delete"
                      danger
                      @click="confirmDeleteDefinition(record)"
                    >
                      删除
                    </MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </div>
          </template>
        </template>
        <template #emptyText>
          <Empty description="暂无符合条件的申请" />
        </template>
      </Table>
    </Card>

    <Modal
      v-model:open="typeManagerOpen"
      :footer="null"
      title="申请类型管理"
      width="900px"
    >
      <div class="mb-4 flex items-center justify-between gap-3">
        <p class="text-muted-foreground m-0 text-sm">
          类型会展示在资源申请左侧，可在此处统一维护。
        </p>
        <Button type="primary" @click="openTypeModal()">
          <Plus class="size-4" aria-hidden="true" />
          新建申请类型
        </Button>
      </div>

      <Table
        :columns="typeColumns"
        :data-source="applicationTypes"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 720 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'type'">
            <div class="flex min-w-0 items-center gap-3">
              <span
                class="bg-muted text-foreground flex size-9 shrink-0 items-center justify-center rounded-lg"
              >
                <IconifyIcon
                  :icon="record.icon"
                  aria-hidden="true"
                  class="size-5"
                />
              </span>
              <div class="min-w-0">
                <div class="text-foreground font-medium">
                  {{ record.typeName }}
                </div>
                <div class="text-muted-foreground mt-0.5 truncate text-xs">
                  {{ record.description || '暂无说明' }}
                </div>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <Tag :color="record.status === 1 ? 'success' : 'default'">
              {{ record.status === 1 ? '启用' : '停用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'updatedAt'">
            {{ formatDateTime(record.updatedAt) }}
          </template>
          <template v-else-if="column.key === 'operation'">
            <Button type="link" @click="openTypeModal(record)">编辑</Button>
          </template>
        </template>
        <template #emptyText>
          <Empty description="暂无申请类型，请先新建类型" />
        </template>
      </Table>
    </Modal>

    <Modal
      v-model:open="modalOpen"
      :confirm-loading="saving"
      :title="modalTitle"
      width="680px"
      @ok="saveDefinition"
    >
      <Alert
        class="mb-5 mt-2"
        message="申请创建后，请在审批配置中关联该申请并设置表单字段。"
        show-icon
        type="info"
      />
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="申请名称" required>
          <Input
            v-model:value="form.applicationName"
            :maxlength="100"
            placeholder="例如 广告账户充值申请"
          />
        </FormItem>
        <FormItem label="申请类型" required>
          <Select
            v-model:value="form.applicationTypeId"
            :options="applicationTypeOptions"
            placeholder="请选择类型"
          />
        </FormItem>
        <FormItem label="说明">
          <Textarea
            v-model:value="form.description"
            :maxlength="255"
            :rows="3"
            show-count
          />
        </FormItem>
        <FormItem label="图标" required>
          <Select v-model:value="form.icon" :options="iconOptions" show-search>
            <template #option="option">
              <span class="flex items-center gap-2">
                <IconifyIcon
                  :icon="option.value"
                  aria-hidden="true"
                  class="size-4"
                />{{ option.value }}
              </span>
            </template>
          </Select>
        </FormItem>
        <FormItem label="可见范围">
          <RadioGroup
            v-model:value="form.visibility"
            :options="visibilityOptions"
          />
        </FormItem>
        <FormItem label="资源申请入口">
          <RadioGroup
            v-model:value="form.showInResourceApplication"
            :options="resourceApplicationDisplayOptions"
          />
          <div class="text-muted-foreground mt-1 text-xs">
            隐藏后不会在资源申请页展示；日报页等专用入口仍可继续使用该审批配置。
          </div>
        </FormItem>
        <FormItem label="状态">
          <RadioGroup v-model:value="form.status" :options="statusOptions" />
        </FormItem>
        <FormItem label="排序">
          <InputNumber
            v-model:value="form.sortOrder"
            class="w-full"
            :max="9999"
            :min="0"
          />
        </FormItem>
      </Form>
    </Modal>

    <Modal
      v-model:open="typeModalOpen"
      :confirm-loading="typeSaving"
      :title="editingTypeId ? '编辑申请类型' : '创建申请类型'"
      width="640px"
      @ok="saveType"
    >
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="类型名称" required>
          <Input v-model:value="typeForm.typeName" :maxlength="64" />
        </FormItem>
        <FormItem label="说明">
          <Textarea
            v-model:value="typeForm.description"
            :maxlength="255"
            :rows="3"
          />
        </FormItem>
        <FormItem label="图标" required>
          <Select
            v-model:value="typeForm.icon"
            :options="iconOptions"
            show-search
          />
        </FormItem>
        <FormItem label="状态">
          <RadioGroup
            v-model:value="typeForm.status"
            :options="statusOptions"
          />
        </FormItem>
        <FormItem label="排序">
          <InputNumber
            v-model:value="typeForm.sortOrder"
            class="w-full"
            :max="9999"
            :min="0"
          />
        </FormItem>
      </Form>
    </Modal>
  </Page>
</template>
