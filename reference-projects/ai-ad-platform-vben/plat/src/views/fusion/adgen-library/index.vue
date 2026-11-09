<script lang="ts" setup>
import type { TableColumnsType, UploadProps } from 'ant-design-vue';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Drawer,
  Empty,
  Form,
  FormItem,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Upload,
  message,
} from 'ant-design-vue';

import {
  createStorageFolderApi,
  deleteCreativeTemplateApi,
  deleteGenerationRecordApi,
  deleteStorageObjectApi,
  getAiCapabilitiesApi,
  getCreativeTemplatesApi,
  getGenerationHistoryApi,
  getStorageBucketsApi,
  getStorageObjectsApi,
  saveCreativeTemplateApi,
  uploadStorageObjectApi,
  type AiCapability,
  type CreativeTemplate,
  type GenerationAsset,
  type GenerationRecord,
  type StorageBucket,
  type StorageObject,
} from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

const router = useRouter();
const route = useRoute();
const activeTab = ref('history');
const loading = ref(false);
const capabilities = ref<AiCapability[]>([]);

const historyRows = ref<GenerationRecord[]>([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyPageSize = ref(10);
const historyKeyword = ref(
  typeof route.query.generationJob === 'string'
    ? route.query.generationJob
    : '',
);
const historyStatus = ref<string>();
const historyCapability = ref<string>();
const selectedHistory = ref<GenerationRecord>();
const historyDrawerOpen = ref(false);

const templates = ref<CreativeTemplate[]>([]);
const templateKeyword = ref('');
const templateCategory = ref<string>('all');
const templateModalOpen = ref(false);
const templateDetailOpen = ref(false);
const selectedTemplate = ref<CreativeTemplate>();
const templateForm = reactive<Partial<CreativeTemplate>>({
  category: 'general',
  description: '',
  name: '',
  prompt: '',
  status: 'draft',
  structure: '',
  tags: [],
});

const buckets = ref<StorageBucket[]>([]);
const selectedBucketId = ref('');
const storageObjects = ref<StorageObject[]>([]);
const storageKeyword = ref('');
const storagePage = ref(1);
const storagePageSize = ref(8);
const folderModalOpen = ref(false);
const folderName = ref('');
const lifecycleModalOpen = ref(false);
const lifecycleDays = ref(30);
const routeStateReady = ref(false);

const {
  commitQueryState: commitTabQueryState,
  restoreFromRoute: restoreTabFromRoute,
} = useListRouteState({
  fields: { tab: { always: true } },
  state: createListRouteStateTarget({ tab: activeTab }),
});
const {
  commitQueryState: commitHistoryQueryState,
  restoreFromRoute: restoreHistoryFromRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeTab.value === 'history')
      return loadHistory();
  },
  pagination: {
    defaultPageSize: 10,
    page: historyPage,
    pageSize: historyPageSize,
    pageSizes: [10, 20, 50, 100],
  },
  scope: 'history',
  state: createListRouteStateTarget({
    capability: historyCapability,
    keyword: historyKeyword,
    status: historyStatus,
  }),
});
const {
  commitQueryState: commitTemplateQueryState,
  restoreFromRoute: restoreTemplateFromRoute,
} = useListRouteState({
  scope: 'template',
  state: createListRouteStateTarget({
    category: templateCategory,
    keyword: templateKeyword,
  }),
});
const {
  commitQueryState: commitStorageQueryState,
  restoreFromRoute: restoreStorageFromRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeTab.value === 'storage')
      return loadStorageObjects();
  },
  pagination: {
    defaultPageSize: 8,
    page: storagePage,
    pageSize: storagePageSize,
    pageSizes: [8, 20, 50],
  },
  scope: 'storage',
  state: createListRouteStateTarget({
    bucket: selectedBucketId,
    keyword: storageKeyword,
  }),
});

async function handleTabChange() {
  await commitTabQueryState();
}

async function handleHistorySearch() {
  historyPage.value = 1;
  await commitHistoryQueryState();
  await loadHistory();
}

async function handleHistoryPageChange(page: any) {
  const sizeChanged = page.pageSize !== historyPageSize.value;
  historyPageSize.value = page.pageSize;
  historyPage.value = sizeChanged ? 1 : page.current;
  await commitHistoryQueryState();
  await loadHistory();
}

async function handleTemplateFilterChange() {
  await commitTemplateQueryState();
}

async function handleStorageFilterChange() {
  storagePage.value = 1;
  await commitStorageQueryState();
}

async function handleStoragePageChange(page: any) {
  const sizeChanged = page.pageSize !== storagePageSize.value;
  storagePageSize.value = page.pageSize;
  storagePage.value = sizeChanged ? 1 : page.current;
  await commitStorageQueryState();
}

async function selectBucket(bucketId: string) {
  selectedBucketId.value = bucketId;
  storagePage.value = 1;
  await commitStorageQueryState();
  await loadStorageObjects();
}

const historyColumns: TableColumnsType<GenerationRecord> = [
  { key: 'record', title: '生成记录', width: 300 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 92 },
  { key: 'assets', title: '产出', width: 210 },
  { key: 'parameters', title: '参数', width: 210 },
  { dataIndex: 'createdAt', key: 'createdAt', title: '创建时间', width: 160 },
  { fixed: 'right', key: 'action', title: '操作', width: 196 },
];

const storageColumns: TableColumnsType<StorageObject> = [
  { key: 'name', title: '对象名称', width: 320 },
  { dataIndex: 'kind', key: 'kind', title: '类型', width: 100 },
  { dataIndex: 'size', key: 'size', title: '大小', width: 120 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 170 },
  { fixed: 'right', key: 'action', title: '操作', width: 160 },
];

const statusMeta = {
  failed: { color: 'red', label: '失败' },
  pending: { color: 'blue', label: '进行中' },
  success: { color: 'green', label: '成功' },
} as const;

const templateCategoryOptions = [
  { label: '全部分类', value: 'all' },
  { label: '游戏', value: 'game' },
  { label: '产品展示', value: 'product' },
  { label: '生活方式', value: 'lifestyle' },
  { label: '视频结构', value: 'video' },
  { label: '脚本与文案', value: 'script' },
  { label: '通用', value: 'general' },
];

const categoryLabel = (category: string) =>
  templateCategoryOptions.find((item) => item.value === category)?.label ??
  category;

const filteredTemplates = computed(() => {
  const keyword = templateKeyword.value.trim().toLowerCase();
  return templates.value.filter((item) => {
    const categoryMatches =
      templateCategory.value === 'all' ||
      item.category === templateCategory.value;
    const keywordMatches =
      !keyword ||
      `${item.name}${item.description}${item.prompt}${item.tags.join('')}`
        .toLowerCase()
        .includes(keyword);
    return categoryMatches && keywordMatches;
  });
});

const selectedBucket = computed(() =>
  buckets.value.find((item) => item.id === selectedBucketId.value),
);

const filteredStorageObjects = computed(() => {
  const keyword = storageKeyword.value.trim().toLowerCase();
  return storageObjects.value.filter(
    (item) => !keyword || item.name.toLowerCase().includes(keyword),
  );
});

const summaryStats = computed(() => [
  {
    icon: 'lucide:history',
    label: '生成记录',
    value: historyTotal.value,
    note: `${historyRows.value.filter((item) => item.status === 'pending').length} 条执行中`,
  },
  {
    icon: 'lucide:panels-top-left',
    label: '创意模板',
    value: templates.value.length,
    note: `${templates.value.filter((item) => item.status === 'published').length} 个已发布`,
  },
  {
    icon: 'lucide:library-big',
    label: '产品档案',
    value: 3,
    note: '均已关联 Java Product',
  },
  {
    icon: 'lucide:hard-drive',
    label: '存储桶',
    value: buckets.value.length,
    note: `${buckets.value.reduce((total, item) => total + item.objectCount, 0)} 个对象`,
  },
]);

function assetIcon(kind: GenerationAsset['kind'] | StorageObject['kind']) {
  return (
    {
      audio: 'lucide:audio-lines',
      folder: 'lucide:folder',
      image: 'lucide:image',
      other: 'lucide:file-archive',
      text: 'lucide:file-text',
      video: 'lucide:clapperboard',
    }[kind] ?? 'lucide:file'
  );
}

function capabilityName(code: string) {
  return capabilities.value.find((item) => item.code === code)?.name ?? code;
}

function getHistoryStatusMeta(status: unknown) {
  return statusMeta[status as GenerationRecord['status']] ?? statusMeta.pending;
}

async function loadHistory() {
  loading.value = true;
  try {
    const result = await getGenerationHistoryApi({
      capability: historyCapability.value as never,
      keyword: historyKeyword.value,
      page: historyPage.value,
      pageSize: historyPageSize.value,
      status: historyStatus.value as never,
    });
    historyRows.value = result.items;
    historyTotal.value = result.total;
  } finally {
    loading.value = false;
  }
}

async function loadTemplates() {
  templates.value = await getCreativeTemplatesApi();
}

async function loadBuckets() {
  buckets.value = await getStorageBucketsApi();
  if (!selectedBucketId.value && buckets.value[0]) {
    selectedBucketId.value = buckets.value[0].id;
  }
  await loadStorageObjects();
}

async function loadStorageObjects() {
  if (!selectedBucketId.value) return;
  storageObjects.value = await getStorageObjectsApi(selectedBucketId.value);
}

function showHistory(record: Record<string, any>) {
  selectedHistory.value = record as GenerationRecord;
  historyDrawerOpen.value = true;
}

function reuseHistory(recordValue: Record<string, any>) {
  const record = recordValue as GenerationRecord;
  if (record.status !== 'success') {
    message.warning('只有成功记录可以恢复到工作台');
    return;
  }
  localStorage.setItem(
    'fusion-ai-restore',
    JSON.stringify({
      capability: record.capability,
      parameters: record.parameters,
      prompt: record.prompt,
      sourceRecordId: record.id,
    }),
  );
  router.push({
    path: '/fusion/ai-studio',
    query: { capability: record.capability, restore: record.id },
  });
  message.success('已恢复提示词与参数');
}

async function removeHistory(id: string) {
  await deleteGenerationRecordApi(id);
  historyRows.value = historyRows.value.filter((item) => item.id !== id);
  historyTotal.value = Math.max(0, historyTotal.value - 1);
  message.success('生成记录已删除');
}

function openTemplateEditor(template?: CreativeTemplate) {
  selectedTemplate.value = template;
  Object.assign(templateForm, {
    category: template?.category ?? 'general',
    description: template?.description ?? '',
    id: template?.id,
    name: template?.name ?? '',
    prompt: template?.prompt ?? '',
    status: template?.status ?? 'draft',
    structure: template?.structure ?? '',
    tags: template?.tags ? [...template.tags] : [],
  });
  templateModalOpen.value = true;
}

async function saveTemplate() {
  if (!templateForm.name?.trim() || !templateForm.prompt?.trim()) {
    message.warning('请填写模板名称和提示词');
    return;
  }
  const saved = await saveCreativeTemplateApi({
    ...(templateForm as CreativeTemplate),
    name: templateForm.name,
  });
  const index = templates.value.findIndex((item) => item.id === saved.id);
  templates.value =
    index >= 0
      ? templates.value.map((item) => (item.id === saved.id ? saved : item))
      : [saved, ...templates.value];
  templateModalOpen.value = false;
  message.success(templateForm.id ? '模板已更新' : '模板已创建');
}

async function removeTemplate(id: string) {
  await deleteCreativeTemplateApi(id);
  templates.value = templates.value.filter((item) => item.id !== id);
  message.success('模板已删除');
}

function viewTemplate(template: CreativeTemplate) {
  selectedTemplate.value = template;
  templateDetailOpen.value = true;
}

function applyTemplate(template: CreativeTemplate) {
  localStorage.setItem(
    'fusion-ai-template',
    JSON.stringify({
      id: template.id,
      name: template.name,
      prompt: template.prompt,
      structure: template.structure,
    }),
  );
  router.push({ path: '/fusion/ai-studio', query: { template: template.id } });
  message.success(`已套用模板：${template.name}`);
}

async function createFolder() {
  if (!folderName.value.trim() || !selectedBucketId.value) {
    message.warning('请输入文件夹名称');
    return;
  }
  const folder = await createStorageFolderApi(
    selectedBucketId.value,
    folderName.value.trim(),
  );
  storageObjects.value = [folder, ...storageObjects.value];
  folderName.value = '';
  folderModalOpen.value = false;
  message.success('文件夹已创建');
}

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  if (!selectedBucketId.value) return false;
  const object = await uploadStorageObjectApi(
    selectedBucketId.value,
    file.name,
  );
  storageObjects.value = [object, ...storageObjects.value];
  message.success(`${file.name} 已加入上传队列`);
  return false;
};

async function removeStorageObject(id: string) {
  await deleteStorageObjectApi(id);
  storageObjects.value = storageObjects.value.filter((item) => item.id !== id);
  message.success('对象已删除');
}

function saveLifecycle() {
  if (selectedBucket.value) {
    selectedBucket.value.lifecycleDays = lifecycleDays.value;
  }
  lifecycleModalOpen.value = false;
  message.success('生命周期规则已保存');
}

function openLifecycle() {
  lifecycleDays.value = selectedBucket.value?.lifecycleDays ?? 30;
  lifecycleModalOpen.value = true;
}

function downloadObject(recordValue: Record<string, any>) {
  const record = recordValue as StorageObject;
  if (record.kind === 'folder') {
    message.info('已进入文件夹；Mock 环境展示当前层级对象');
    return;
  }
  message.success(`${record.name} 下载任务已创建`);
}

onMounted(async () => {
  loading.value = true;
  try {
    await restoreTabFromRoute();
    await restoreHistoryFromRoute();
    await restoreTemplateFromRoute();
    await restoreStorageFromRoute();
    capabilities.value = await getAiCapabilitiesApi();
    await Promise.all([loadHistory(), loadTemplates(), loadBuckets()]);
    await commitStorageQueryState();
    routeStateReady.value = true;
    const generationJob = route.query.generationJob;
    if (typeof generationJob === 'string') {
      const record = historyRows.value.find(
        (item) =>
          item.sessionId === generationJob ||
          item.id === generationJob ||
          item.id === `history-${generationJob}`,
      );
      if (record) showHistory(record);
    }
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '素材库数据加载失败，请稍后重试',
    );
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <Page class="bg-slate-50" content-class="pb-6">
    <div class="w-full min-w-0 space-y-4">
      <header class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1
            class="text-foreground mb-0 font-semibold text-[var(--adpulse-page-title-size)]"
          >
            历史、模板与存储
          </h1>
          <p class="mb-0 mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            直接管理生成记录、创意模板、产品知识和对象存储；所有产出均可回到工作台复用或进入素材库。
          </p>
        </div>
        <Space wrap>
          <Button @click="router.push('/fusion/ai-tasks')">
            <template #icon><IconifyIcon icon="lucide:activity" /></template>
            全局任务
          </Button>
          <Button type="primary" @click="router.push('/fusion/ai-studio')">
            <template #icon
              ><IconifyIcon icon="lucide:wand-sparkles"
            /></template>
            开始创作
          </Button>
        </Space>
      </header>

      <section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Card
          v-for="item in summaryStats"
          :key="item.label"
          class="border-slate-200"
          :body-style="{ padding: '15px 16px' }"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-xs text-slate-500">{{ item.label }}</div>
              <div class="mt-1 text-2xl font-semibold text-slate-950">
                {{ item.value }}
              </div>
              <div class="mt-1 truncate text-xs text-slate-500">
                {{ item.note }}
              </div>
            </div>
            <div class="rounded-lg bg-blue-50 p-2 text-blue-700">
              <IconifyIcon :icon="item.icon" class="text-lg" />
            </div>
          </div>
        </Card>
      </section>

      <Card class="library-shell border-slate-200" :body-style="{ padding: 0 }">
        <Tabs
          v-model:active-key="activeTab"
          class="library-tabs"
          @change="handleTabChange"
        >
          <Tabs.TabPane key="history" tab="生成历史">
            <div class="space-y-4 px-4 pb-5 sm:px-5">
              <div class="flex flex-wrap gap-2 rounded-lg bg-slate-50 p-3">
                <Input.Search
                  v-model:value="historyKeyword"
                  allow-clear
                  class="min-w-[220px] flex-1"
                  placeholder="搜索提示词、标题或会话 ID"
                  @search="handleHistorySearch"
                />
                <Select
                  v-model:value="historyCapability"
                  allow-clear
                  class="w-[170px]"
                  placeholder="全部能力"
                  :options="
                    capabilities.map((item) => ({
                      label: item.name,
                      value: item.code,
                    }))
                  "
                  @change="handleHistorySearch"
                />
                <Select
                  v-model:value="historyStatus"
                  allow-clear
                  class="w-[130px]"
                  placeholder="全部状态"
                  :options="[
                    { label: '成功', value: 'success' },
                    { label: '进行中', value: 'pending' },
                    { label: '失败', value: 'failed' },
                  ]"
                  @change="handleHistorySearch"
                />
                <Button :loading="loading" @click="loadHistory">
                  <template #icon
                    ><IconifyIcon icon="lucide:refresh-cw"
                  /></template>
                  刷新
                </Button>
              </div>

              <Table
                :columns="historyColumns"
                :data-source="historyRows"
                :loading="loading"
                :pagination="{
                  current: historyPage,
                  pageSize: historyPageSize,
                  showSizeChanger: true,
                  showTotal: (total: number) => `共 ${total} 条`,
                  total: historyTotal,
                }"
                :scroll="{ x: 1180 }"
                row-key="id"
                size="middle"
                @change="handleHistoryPageChange"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'record'">
                    <div class="min-w-0">
                      <div class="truncate text-sm font-medium text-slate-900">
                        {{ record.title }}
                      </div>
                      <div
                        class="mt-1 line-clamp-2 text-xs leading-5 text-slate-500"
                      >
                        {{ record.prompt }}
                      </div>
                      <div class="mt-1 font-mono text-[11px] text-slate-400">
                        {{ record.sessionId }}
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'status'">
                    <Tag :color="getHistoryStatusMeta(record.status).color">
                      {{ getHistoryStatusMeta(record.status).label }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'assets'">
                    <div
                      v-if="record.assets.length"
                      class="flex items-center gap-1"
                    >
                      <div
                        v-for="asset in record.assets.slice(0, 3)"
                        :key="asset.id"
                        class="asset-tile"
                        :title="asset.name"
                      >
                        <IconifyIcon :icon="assetIcon(asset.kind)" />
                      </div>
                      <span
                        v-if="record.assets.length > 3"
                        class="text-xs text-slate-500"
                      >
                        +{{ record.assets.length - 3 }}
                      </span>
                    </div>
                    <div v-else class="text-xs text-slate-400">
                      暂无有效产出
                    </div>
                  </template>
                  <template v-else-if="column.key === 'parameters'">
                    <div class="text-xs text-slate-600">
                      {{ capabilityName(record.capability) }}
                    </div>
                    <div class="mt-1 truncate text-xs text-slate-400">
                      {{
                        Object.entries(record.parameters)
                          .slice(0, 3)
                          .map(([key, value]) => `${key}: ${value}`)
                          .join(' · ')
                      }}
                    </div>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <Space :size="4">
                      <Button type="link" @click="showHistory(record)"
                        >详情</Button
                      >
                      <Button
                        type="link"
                        :disabled="record.status !== 'success'"
                        @click="reuseHistory(record)"
                        >复用</Button
                      >
                      <Popconfirm
                        title="确定删除这条生成记录？"
                        @confirm="removeHistory(record.id)"
                      >
                        <Button danger type="link">删除</Button>
                      </Popconfirm>
                    </Space>
                  </template>
                </template>
              </Table>
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="templates" tab="模板管理">
            <div class="space-y-4 px-4 pb-5 sm:px-5">
              <div
                class="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3"
              >
                <Input.Search
                  v-model:value="templateKeyword"
                  allow-clear
                  class="min-w-[220px] flex-1"
                  placeholder="搜索模板名称、提示词或标签"
                  @update:value="handleTemplateFilterChange"
                />
                <Select
                  v-model:value="templateCategory"
                  class="w-[160px]"
                  :options="templateCategoryOptions"
                  @change="handleTemplateFilterChange"
                />
                <Button type="primary" @click="openTemplateEditor()">
                  <template #icon><IconifyIcon icon="lucide:plus" /></template>
                  新建模板
                </Button>
              </div>

              <div
                v-if="filteredTemplates.length"
                class="grid gap-3 md:grid-cols-2 2xl:grid-cols-3"
              >
                <Card
                  v-for="template in filteredTemplates"
                  :key="template.id"
                  class="template-card border-slate-200"
                  :body-style="{ padding: '16px' }"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <h3
                          class="m-0 truncate text-base font-semibold text-slate-900"
                        >
                          {{ template.name }}
                        </h3>
                        <Tag
                          :color="
                            template.status === 'published'
                              ? 'green'
                              : 'default'
                          "
                        >
                          {{
                            template.status === 'published' ? '已发布' : '草稿'
                          }}
                        </Tag>
                      </div>
                      <div class="mt-1 text-xs text-slate-500">
                        {{ categoryLabel(template.category) }} · 使用
                        {{ template.usageCount }} 次
                      </div>
                    </div>
                    <IconifyIcon
                      icon="lucide:panels-top-left"
                      class="text-xl text-blue-700"
                    />
                  </div>
                  <p
                    class="mb-0 mt-4 line-clamp-2 min-h-10 text-sm leading-5 text-slate-600"
                  >
                    {{ template.description }}
                  </p>
                  <div
                    class="mt-4 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600"
                  >
                    {{ template.structure }}
                  </div>
                  <div class="mt-3 flex min-h-6 flex-wrap gap-1">
                    <Tag v-for="tag in template.tags" :key="tag">{{ tag }}</Tag>
                  </div>
                  <Divider class="my-3" />
                  <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-slate-400">{{
                      template.updatedAt
                    }}</span>
                    <Space :size="2">
                      <Button type="link" @click="viewTemplate(template)"
                        >查看</Button
                      >
                      <Button type="link" @click="openTemplateEditor(template)"
                        >编辑</Button
                      >
                      <Popconfirm
                        title="确定删除该模板？"
                        @confirm="removeTemplate(template.id)"
                      >
                        <Button danger type="link">删除</Button>
                      </Popconfirm>
                      <Button type="primary" @click="applyTemplate(template)"
                        >套用</Button
                      >
                    </Space>
                  </div>
                </Card>
              </div>
              <Empty v-else description="没有符合筛选条件的模板" />
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="knowledge" tab="产品创意知识库">
            <div class="space-y-4 px-4 pb-5 sm:px-5">
              <Alert
                message="Java Product 是唯一产品主数据；此处只维护通过 product_id 关联的 CreativeProfile。"
                type="info"
                show-icon
              />
              <div class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
                <Card
                  title="已关联产品档案"
                  class="border-slate-200"
                  :body-style="{ padding: 0 }"
                >
                  <div
                    v-for="product in [
                      {
                        name: 'Starfall',
                        project: 'Starfall 全球增长',
                        points: '首充奖励、团队战斗、即时反馈',
                        assets: 26,
                        status: '完整',
                      },
                      {
                        name: 'Project Ark',
                        project: 'Project Ark 美国市场',
                        points: '沙盒建造、多人协作、生存挑战',
                        assets: 18,
                        status: '完整',
                      },
                      {
                        name: 'Pixel Quest',
                        project: 'Pixel Quest 日本首发',
                        points: '像素风、预约奖励、轻量养成',
                        assets: 9,
                        status: '待补充',
                      },
                    ]"
                    :key="product.name"
                    class="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-4 last:border-0"
                  >
                    <div
                      class="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-50 font-semibold text-blue-700"
                    >
                      {{ product.name.slice(0, 1) }}
                    </div>
                    <div class="min-w-[220px] flex-1">
                      <div class="flex flex-wrap items-center gap-2">
                        <span class="font-medium text-slate-900">{{
                          product.name
                        }}</span>
                        <Tag
                          :color="
                            product.status === '完整' ? 'green' : 'orange'
                          "
                          >{{ product.status }}</Tag
                        >
                      </div>
                      <div class="mt-1 text-xs text-slate-500">
                        {{ product.project }}
                      </div>
                      <div class="mt-1 text-xs text-slate-600">
                        {{ product.points }}
                      </div>
                    </div>
                    <div class="text-right text-xs text-slate-500">
                      <div>{{ product.assets }} 个参考素材</div>
                      <Button
                        class="mt-1"
                        type="link"
                        @click="router.push('/fusion/product-knowledge')"
                        >管理档案</Button
                      >
                    </div>
                  </div>
                </Card>
                <Card title="知识完整度" class="border-slate-200">
                  <div class="space-y-4">
                    <div
                      v-for="metric in [
                        { label: '核心卖点', percent: 100 },
                        { label: '目标人群', percent: 88 },
                        { label: '参考素材', percent: 76 },
                        { label: '禁用信息', percent: 92 },
                      ]"
                      :key="metric.label"
                    >
                      <div
                        class="mb-1 flex justify-between text-xs text-slate-600"
                      >
                        <span>{{ metric.label }}</span
                        ><span>{{ metric.percent }}%</span>
                      </div>
                      <Progress :percent="metric.percent" :show-info="false" />
                    </div>
                    <Button
                      block
                      type="primary"
                      @click="router.push('/fusion/product-knowledge')"
                    >
                      打开完整知识库
                    </Button>
                  </div>
                </Card>
              </div>
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="storage" tab="存储桶管理">
            <div class="grid min-h-0 lg:grid-cols-[240px_minmax(0,1fr)]">
              <aside class="border-r border-slate-200 bg-slate-50 p-3">
                <div class="mb-2 flex items-center justify-between px-1">
                  <span class="text-muted-foreground text-xs font-semibold"
                    >存储桶</span
                  >
                  <Button type="text" @click="loadBuckets">
                    <IconifyIcon icon="lucide:refresh-cw" />
                  </Button>
                </div>
                <button
                  v-for="bucket in buckets"
                  :key="bucket.id"
                  type="button"
                  class="mb-2 w-full rounded-lg border p-3 text-left transition-colors"
                  :class="
                    selectedBucketId === bucket.id
                      ? 'border-blue-200 bg-white shadow-sm'
                      : 'border-transparent hover:bg-white'
                  "
                  @click="selectBucket(bucket.id)"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="truncate text-sm font-medium text-slate-800">{{
                      bucket.name
                    }}</span>
                    <span
                      class="h-2 w-2 rounded-full"
                      :class="
                        bucket.status === 'healthy'
                          ? 'bg-emerald-500'
                          : 'bg-amber-500'
                      "
                    ></span>
                  </div>
                  <div class="mt-2 flex justify-between text-xs text-slate-500">
                    <span>{{ bucket.usedSize }}</span
                    ><span>{{ bucket.objectCount }} 项</span>
                  </div>
                </button>
              </aside>
              <main class="min-w-0 p-4">
                <div
                  class="mb-4 flex flex-wrap items-start justify-between gap-3"
                >
                  <div>
                    <h3 class="m-0 text-base font-semibold text-slate-900">
                      {{ selectedBucket?.name || '存储对象' }}
                    </h3>
                    <p class="mb-0 mt-1 text-xs text-slate-500">
                      {{ selectedBucket?.region }} · 生命周期
                      {{ selectedBucket?.lifecycleDays || '永久'
                      }}{{ selectedBucket?.lifecycleDays ? ' 天' : '' }}
                    </p>
                  </div>
                  <Space wrap>
                    <Button @click="openLifecycle"
                      ><template #icon
                        ><IconifyIcon icon="lucide:timer-reset" /></template
                      >生命周期</Button
                    >
                    <Button @click="folderModalOpen = true"
                      ><template #icon
                        ><IconifyIcon icon="lucide:folder-plus" /></template
                      >新建文件夹</Button
                    >
                    <Upload
                      :before-upload="beforeUpload"
                      :show-upload-list="false"
                      multiple
                    >
                      <Button type="primary"
                        ><template #icon
                          ><IconifyIcon icon="lucide:upload" /></template
                        >上传文件</Button
                      >
                    </Upload>
                  </Space>
                </div>
                <Input.Search
                  v-model:value="storageKeyword"
                  allow-clear
                  class="mb-3 max-w-[420px]"
                  placeholder="搜索当前存储桶对象"
                  @update:value="handleStorageFilterChange"
                />
                <Table
                  :columns="storageColumns"
                  :data-source="filteredStorageObjects"
                  :pagination="{
                    current: storagePage,
                    pageSize: storagePageSize,
                    showSizeChanger: true,
                    showTotal: (total: number) => `共 ${total} 项`,
                  }"
                  :scroll="{ x: 900 }"
                  row-key="id"
                  size="middle"
                  @change="handleStoragePageChange"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'name'">
                      <div class="flex min-w-0 items-center gap-3">
                        <div
                          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
                        >
                          <IconifyIcon :icon="assetIcon(record.kind)" />
                        </div>
                        <div class="min-w-0">
                          <div
                            class="truncate text-sm font-medium text-slate-800"
                          >
                            {{ record.name }}
                          </div>
                          <div class="mt-0.5 text-xs text-slate-400">
                            {{ record.folder }}
                          </div>
                        </div>
                      </div>
                    </template>
                    <template v-else-if="column.key === 'kind'">
                      <Tag>{{ record.kind }}</Tag>
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <Space :size="2">
                        <Button type="link" @click="downloadObject(record)">
                          {{ record.kind === 'folder' ? '打开' : '下载' }}
                        </Button>
                        <Popconfirm
                          title="确定删除该对象？"
                          @confirm="removeStorageObject(record.id)"
                        >
                          <Button danger type="link">删除</Button>
                        </Popconfirm>
                      </Space>
                    </template>
                  </template>
                </Table>
              </main>
            </div>
          </Tabs.TabPane>
        </Tabs>
      </Card>
    </div>

    <Drawer
      v-model:open="historyDrawerOpen"
      title="生成记录详情"
      width="min(560px, 92vw)"
    >
      <template v-if="selectedHistory">
        <div class="mb-4 flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-lg font-semibold text-slate-900">
              {{ selectedHistory.title }}
            </h3>
            <div class="mt-1 text-xs text-slate-500">
              {{ selectedHistory.sessionId }}
            </div>
          </div>
          <Tag :color="statusMeta[selectedHistory.status].color">{{
            statusMeta[selectedHistory.status].label
          }}</Tag>
        </div>
        <Descriptions :column="1" bordered>
          <DescriptionsItem label="能力">{{
            capabilityName(selectedHistory.capability)
          }}</DescriptionsItem>
          <DescriptionsItem label="创建时间">{{
            selectedHistory.createdAt
          }}</DescriptionsItem>
          <DescriptionsItem label="输入 / 产出"
            >{{ selectedHistory.inputCount }} /
            {{ selectedHistory.resultCount }}</DescriptionsItem
          >
          <DescriptionsItem label="提示词">{{
            selectedHistory.prompt
          }}</DescriptionsItem>
        </Descriptions>
        <h4 class="mb-2 mt-5 text-sm font-semibold text-slate-800">生成参数</h4>
        <div
          class="rounded-lg bg-slate-950 p-3 font-mono text-xs leading-6 text-slate-100"
        >
          {{ JSON.stringify(selectedHistory.parameters, null, 2) }}
        </div>
        <Alert
          v-if="selectedHistory.errorMessage"
          class="mt-4"
          :message="selectedHistory.errorMessage"
          type="error"
          show-icon
        />
        <h4 class="mb-2 mt-5 text-sm font-semibold text-slate-800">产出文件</h4>
        <div
          v-if="selectedHistory.assets.length"
          class="grid grid-cols-2 gap-2"
        >
          <div
            v-for="asset in selectedHistory.assets"
            :key="asset.id"
            class="flex items-center gap-3 rounded-lg border border-slate-200 p-3"
          >
            <div class="asset-tile">
              <IconifyIcon :icon="assetIcon(asset.kind)" />
            </div>
            <div class="min-w-0 flex-1 truncate text-xs text-slate-600">
              {{ asset.name }}
            </div>
            <Button
              type="text"
              @click="message.success(`${asset.name} 下载任务已创建`)"
              ><IconifyIcon icon="lucide:download"
            /></Button>
          </div>
        </div>
        <Empty v-else description="没有有效产出" />
        <Button
          class="mt-5"
          block
          type="primary"
          :disabled="selectedHistory.status !== 'success'"
          @click="reuseHistory(selectedHistory)"
          >恢复到 AI 工作台</Button
        >
      </template>
    </Drawer>

    <Modal
      v-model:open="templateModalOpen"
      :title="templateForm.id ? '编辑模板' : '新建模板'"
      width="680px"
      @ok="saveTemplate"
    >
      <Form layout="vertical">
        <div class="grid gap-x-4 sm:grid-cols-2">
          <FormItem label="模板名称" required
            ><Input
              v-model:value="templateForm.name"
              placeholder="输入模板名称"
          /></FormItem>
          <FormItem label="分类"
            ><Select
              v-model:value="templateForm.category"
              :options="templateCategoryOptions.slice(1)"
          /></FormItem>
        </div>
        <FormItem label="说明"
          ><Input.TextArea v-model:value="templateForm.description" :rows="2"
        /></FormItem>
        <FormItem label="提示词" required
          ><Input.TextArea
            v-model:value="templateForm.prompt"
            :rows="5"
            show-count
            :maxlength="2000"
        /></FormItem>
        <FormItem label="创意结构"
          ><Input.TextArea v-model:value="templateForm.structure" :rows="3"
        /></FormItem>
        <div class="grid gap-x-4 sm:grid-cols-2">
          <FormItem label="标签"
            ><Select
              v-model:value="templateForm.tags"
              mode="tags"
              placeholder="输入后回车"
          /></FormItem>
          <FormItem label="状态"
            ><Select
              v-model:value="templateForm.status"
              :options="[
                { label: '草稿', value: 'draft' },
                { label: '已发布', value: 'published' },
              ]"
          /></FormItem>
        </div>
      </Form>
    </Modal>

    <Drawer
      v-model:open="templateDetailOpen"
      title="模板详情"
      width="min(560px, 92vw)"
    >
      <template v-if="selectedTemplate">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="m-0 text-lg font-semibold text-slate-900">
              {{ selectedTemplate.name }}
            </h3>
            <p class="mb-0 mt-1 text-sm text-slate-500">
              {{ selectedTemplate.description }}
            </p>
          </div>
          <Tag color="blue">{{ categoryLabel(selectedTemplate.category) }}</Tag>
        </div>
        <Divider />
        <h4 class="text-sm font-semibold text-slate-800">提示词</h4>
        <div
          class="rounded-lg bg-slate-50 p-4 text-sm leading-6 text-slate-700"
        >
          {{ selectedTemplate.prompt }}
        </div>
        <h4 class="mt-5 text-sm font-semibold text-slate-800">创意结构</h4>
        <div
          class="rounded-lg border border-slate-200 p-4 text-sm leading-6 text-slate-700"
        >
          {{ selectedTemplate.structure }}
        </div>
        <div class="mt-4 flex flex-wrap gap-1">
          <Tag v-for="tag in selectedTemplate.tags" :key="tag">{{ tag }}</Tag>
        </div>
        <Button
          class="mt-6"
          block
          type="primary"
          @click="applyTemplate(selectedTemplate)"
          >套用到 AI 工作台</Button
        >
      </template>
    </Drawer>

    <Modal v-model:open="folderModalOpen" title="新建文件夹" @ok="createFolder">
      <Form layout="vertical"
        ><FormItem label="文件夹名称" required
          ><Input
            v-model:value="folderName"
            placeholder="例如 project-starfall"
            @press-enter="createFolder" /></FormItem
      ></Form>
    </Modal>

    <Modal
      v-model:open="lifecycleModalOpen"
      title="生命周期规则"
      @ok="saveLifecycle"
    >
      <Alert
        class="mb-4"
        message="仅临时生成文件建议自动清理；正式素材与交付文件应永久保留或归档。"
        type="warning"
        show-icon
      />
      <Form layout="vertical"
        ><FormItem label="自动清理天数"
          ><Select
            v-model:value="lifecycleDays"
            :options="[
              { label: '永久保留', value: 0 },
              { label: '7 天', value: 7 },
              { label: '14 天', value: 14 },
              { label: '30 天', value: 30 },
              { label: '90 天', value: 90 },
            ]" /></FormItem
      ></Form>
    </Modal>
  </Page>
</template>

<style scoped>
.asset-tile {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.template-card {
  min-width: 0;
  height: 100%;
}

@media (max-width: 767px) {
}
</style>
