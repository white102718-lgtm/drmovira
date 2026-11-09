<script lang="ts" setup>
import type { SystemDictionaryApi } from '#/api';

import { computed, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { Plus, RotateCw, Search } from '@vben/icons';

import {
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  RadioGroup,
  Select,
  Space,
  Table,
  Tag,
  Textarea,
} from 'ant-design-vue';

import {
  createDictionaryItem,
  createDictionaryType,
  deleteDictionaryItem,
  deleteDictionaryType,
  getDictionaryDetail,
  getDictionaryTypes,
  updateDictionaryItem,
  updateDictionaryType,
} from '#/api';
import { useListRouteState } from '#/composables/use-list-route-state';

type DictionaryType = SystemDictionaryApi.DictionaryType;
type DictionaryItem = SystemDictionaryApi.DictionaryItem;

const statusOptions = [
  { label: '启用', value: 1 },
  { label: '停用', value: 0 },
];
const typeColumns = [
  { dataIndex: 'dictName', key: 'dictName', title: '字典名称' },
  { dataIndex: 'dictCode', key: 'dictCode', title: '字典编码' },
  { dataIndex: 'status', key: 'status', title: '状态', width: 90 },
  { dataIndex: 'remark', key: 'remark', title: '备注' },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 180 },
  { key: 'operation', title: '操作', width: 220 },
];
const itemColumns = [
  { dataIndex: 'label', key: 'label', title: '显示标签' },
  { dataIndex: 'value', key: 'value', title: '字典值' },
  { dataIndex: 'sortOrder', key: 'sortOrder', title: '排序', width: 80 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 90 },
  { dataIndex: 'remark', key: 'remark', title: '备注' },
  { key: 'operation', title: '操作', width: 130 },
];

const loading = ref(false);
const types = ref<DictionaryType[]>([]);
const filters = reactive<{ keyword?: string; status?: number }>({});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: () => loadTypes(),
    state: filters,
  });

const typeModalOpen = ref(false);
const typeSaving = ref(false);
const editingTypeId = ref<string>();
const typeForm = reactive<SystemDictionaryApi.TypeSaveRequest>({
  dictCode: '',
  dictName: '',
  remark: undefined,
  status: 1,
});
const typeModalTitle = computed(() =>
  editingTypeId.value ? '编辑字典类型' : '新增字典类型',
);

const itemDrawerOpen = ref(false);
const detailLoading = ref(false);
const selectedDetail = ref<SystemDictionaryApi.DictionaryDetail>();
const itemModalOpen = ref(false);
const itemSaving = ref(false);
const editingItemId = ref<string>();
const itemForm = reactive<SystemDictionaryApi.ItemSaveRequest>({
  label: '',
  remark: undefined,
  sortOrder: 0,
  status: 1,
  value: '',
});
const itemModalTitle = computed(() =>
  editingItemId.value ? '编辑字典项' : '新增字典项',
);

async function loadTypes() {
  await commitQueryState();
  loading.value = true;
  try {
    types.value = await getDictionaryTypes({
      keyword: filters.keyword?.trim() || undefined,
      status: filters.status,
    });
  } finally {
    loading.value = false;
  }
}

async function resetFilters() {
  await resetQueryState();
  await loadTypes();
}

function openTypeModal(row?: DictionaryType | Record<string, any>) {
  editingTypeId.value = row?.id;
  Object.assign(typeForm, {
    dictCode: row?.dictCode ?? '',
    dictName: row?.dictName ?? '',
    remark: row?.remark ?? undefined,
    status: row?.status ?? 1,
  });
  typeModalOpen.value = true;
}

async function saveType() {
  const dictCode = typeForm.dictCode.trim().toUpperCase();
  const dictName = typeForm.dictName.trim();
  if (!/^[A-Z][A-Z0-9_]{1,63}$/.test(dictCode)) {
    message.warning('字典编码需以大写字母开头，仅包含大写字母、数字和下划线');
    return;
  }
  if (!dictName) {
    message.warning('请输入字典名称');
    return;
  }
  typeSaving.value = true;
  try {
    const payload: SystemDictionaryApi.TypeSaveRequest = {
      dictCode,
      dictName,
      remark: typeForm.remark?.trim() || undefined,
      status: typeForm.status,
    };
    await (editingTypeId.value
      ? updateDictionaryType(editingTypeId.value, payload)
      : createDictionaryType(payload));
    typeModalOpen.value = false;
    message.success(editingTypeId.value ? '字典类型已更新' : '字典类型已创建');
    await loadTypes();
  } finally {
    typeSaving.value = false;
  }
}

function removeType(row: DictionaryType | Record<string, any>) {
  Modal.confirm({
    cancelText: '取消',
    content: `删除后，“${row.dictName}”及其全部字典项将不可用。确认继续吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除字典类型',
    async onOk() {
      await deleteDictionaryType(row.id);
      message.success('字典类型已删除');
      await loadTypes();
    },
  });
}

async function loadDetail(id: string) {
  detailLoading.value = true;
  try {
    selectedDetail.value = await getDictionaryDetail(id);
  } finally {
    detailLoading.value = false;
  }
}

async function openItems(row: DictionaryType | Record<string, any>) {
  itemDrawerOpen.value = true;
  selectedDetail.value = { items: [], type: row };
  await loadDetail(row.id);
}

function openItemModal(row?: DictionaryItem | Record<string, any>) {
  editingItemId.value = row?.id;
  Object.assign(itemForm, {
    label: row?.label ?? '',
    remark: row?.remark ?? undefined,
    sortOrder: row?.sortOrder ?? 0,
    status: row?.status ?? 1,
    value: row?.value ?? '',
  });
  itemModalOpen.value = true;
}

async function saveItem() {
  const value = itemForm.value.trim();
  const label = itemForm.label.trim();
  if (!value || !label) {
    message.warning('请输入字典值和显示标签');
    return;
  }
  const typeId = selectedDetail.value?.type.id;
  if (!typeId) return;
  itemSaving.value = true;
  try {
    const payload: SystemDictionaryApi.ItemSaveRequest = {
      label,
      remark: itemForm.remark?.trim() || undefined,
      sortOrder: itemForm.sortOrder ?? 0,
      status: itemForm.status,
      value,
    };
    await (editingItemId.value
      ? updateDictionaryItem(editingItemId.value, payload)
      : createDictionaryItem(typeId, payload));
    itemModalOpen.value = false;
    message.success(editingItemId.value ? '字典项已更新' : '字典项已创建');
    await loadDetail(typeId);
  } finally {
    itemSaving.value = false;
  }
}

function removeItem(row: DictionaryItem | Record<string, any>) {
  Modal.confirm({
    cancelText: '取消',
    content: `确认删除字典项“${row.label}”吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除字典项',
    async onOk() {
      await deleteDictionaryItem(row.id);
      message.success('字典项已删除');
      const typeId = selectedDetail.value?.type.id;
      if (typeId) await loadDetail(typeId);
    },
  });
}

onMounted(async () => {
  await restoreFromRoute();
  await loadTypes();
});
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="维护系统通用枚举与显示文案，确保各业务模块使用一致口径。"
    title="字典管理"
  >
    <template #extra>
      <Button type="primary" @click="openTypeModal()">
        <Plus class="size-4" aria-hidden="true" />
        新增字典
      </Button>
    </template>
    <Card :bordered="false">
      <Form class="mb-4" layout="inline" @submit.prevent="loadTypes">
        <FormItem label="关键词">
          <Input
            v-model:value="filters.keyword"
            allow-clear
            placeholder="字典名称或编码"
            @press-enter="loadTypes"
          />
        </FormItem>
        <FormItem label="状态">
          <Select
            v-model:value="filters.status"
            allow-clear
            class="w-32"
            :options="statusOptions"
            placeholder="全部状态"
          />
        </FormItem>
        <FormItem>
          <Space>
            <Button type="primary" @click="loadTypes">
              <Search class="size-4" />查询
            </Button>
            <Button @click="resetFilters">
              <RotateCw class="size-4" />重置
            </Button>
          </Space>
        </FormItem>
      </Form>

      <Table
        :columns="typeColumns"
        :data-source="types"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 1050 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="record.status === 1 ? 'success' : 'default'">
              {{ record.status === 1 ? '启用' : '停用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'dictCode'">
            <span class="font-mono text-xs">{{ record.dictCode }}</span>
          </template>
          <template v-else-if="column.key === 'operation'">
            <Space :size="0">
              <Button type="link" @click="openItems(record)">字典项</Button>
              <Button type="link" @click="openTypeModal(record)">编辑</Button>
              <Button danger type="link" @click="removeType(record)">
                删除
              </Button>
            </Space>
          </template>
        </template>
        <template #emptyText>
          <Empty description="暂无字典类型" />
        </template>
      </Table>
    </Card>

    <Modal
      v-model:open="typeModalOpen"
      :confirm-loading="typeSaving"
      :title="typeModalTitle"
      @ok="saveType"
    >
      <Form class="pt-3" :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="字典名称" required>
          <Input v-model:value="typeForm.dictName" :maxlength="100" />
        </FormItem>
        <FormItem label="字典编码" required>
          <Input
            v-model:value="typeForm.dictCode"
            :disabled="Boolean(editingTypeId)"
            :maxlength="64"
            placeholder="例如 AD_MEDIA"
          />
        </FormItem>
        <FormItem label="状态">
          <RadioGroup
            v-model:value="typeForm.status"
            :options="statusOptions"
          />
        </FormItem>
        <FormItem label="备注">
          <Textarea
            v-model:value="typeForm.remark"
            :maxlength="500"
            :rows="3"
          />
        </FormItem>
      </Form>
    </Modal>

    <Drawer
      v-model:open="itemDrawerOpen"
      destroy-on-close
      placement="right"
      :title="`字典项 · ${selectedDetail?.type.dictName ?? ''}`"
      width="760"
    >
      <template #extra>
        <Button type="primary" @click="openItemModal()">
          <Plus class="size-4" />新增字典项
        </Button>
      </template>
      <Descriptions v-if="selectedDetail" class="mb-5" bordered>
        <DescriptionsItem label="字典编码">
          <span class="font-mono">{{ selectedDetail.type.dictCode }}</span>
        </DescriptionsItem>
        <DescriptionsItem label="状态">
          {{ selectedDetail.type.status === 1 ? '启用' : '停用' }}
        </DescriptionsItem>
      </Descriptions>
      <Table
        :columns="itemColumns"
        :data-source="selectedDetail?.items ?? []"
        :loading="detailLoading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 700 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="record.status === 1 ? 'success' : 'default'">
              {{ record.status === 1 ? '启用' : '停用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'value'">
            <span class="font-mono text-xs">{{ record.value }}</span>
          </template>
          <template v-else-if="column.key === 'operation'">
            <Space :size="0">
              <Button type="link" @click="openItemModal(record)">编辑</Button>
              <Button danger type="link" @click="removeItem(record)">
                删除
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Drawer>

    <Modal
      v-model:open="itemModalOpen"
      :confirm-loading="itemSaving"
      :title="itemModalTitle"
      @ok="saveItem"
    >
      <Form class="pt-3" :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="显示标签" required>
          <Input v-model:value="itemForm.label" :maxlength="100" />
        </FormItem>
        <FormItem label="字典值" required>
          <Input v-model:value="itemForm.value" :maxlength="100" />
        </FormItem>
        <FormItem label="排序">
          <InputNumber v-model:value="itemForm.sortOrder" class="w-full" />
        </FormItem>
        <FormItem label="状态">
          <RadioGroup
            v-model:value="itemForm.status"
            :options="statusOptions"
          />
        </FormItem>
        <FormItem label="备注">
          <Textarea
            v-model:value="itemForm.remark"
            :maxlength="500"
            :rows="3"
          />
        </FormItem>
      </Form>
    </Modal>
  </Page>
</template>
