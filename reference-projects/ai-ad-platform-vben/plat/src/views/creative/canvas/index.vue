<script lang="ts" setup>
import type { ProjectOption } from '#/api';
import type { CanvasDraftPayload, CanvasSummary } from '#/api/canvas';

import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useUserStore } from '@vben/stores';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  message,
  Modal,
  Row,
  Select,
  Spin,
  Tag,
} from 'ant-design-vue';

import { getProjectOptionsApi, isFusionDemoMode } from '#/api';
import {
  archiveCanvasApi,
  createCanvasApi,
  getCanvasCapabilitiesApi,
  getCanvasListApi,
  updateCanvasApi,
} from '#/api/canvas';

type CanvasScope =
  | 'all'
  | 'archived'
  | 'mine'
  | 'project'
  | 'requirement'
  | 'shared'
  | 'template';
type CanvasStatus =
  | 'archived'
  | 'completed'
  | 'draft'
  | 'in_progress'
  | 'pending_review';
type CanvasType =
  | 'analysis'
  | 'exploration'
  | 'project'
  | 'requirement'
  | 'template'
  | 'variant'
  | 'video';

interface CanvasListItem {
  collaboratorCount: number;
  id: string;
  isMine: boolean;
  isShared: boolean;
  name: string;
  nodeCount: number;
  outputCount: number;
  ownerName: string;
  projectId?: string;
  projectName?: string;
  requirementId?: string;
  requirementName?: string;
  status: CanvasStatus;
  taskId?: string;
  thumbnailTone: 'amber' | 'blue' | 'cyan' | 'indigo' | 'rose' | 'violet';
  type: CanvasType;
  updatedAt: string;
}

const router = useRouter();
const userStore = useUserStore();
const isSystemAdmin = ref(false);
const legacyCanvasStoragePrefix = 'adpulse:adgen-canvas:draft:';
const keyword = ref('');
const loading = ref(false);
const creating = ref(false);
const archivingCanvasId = ref('');
const restoringCanvasId = ref('');
const createModalOpen = ref(false);
const createCanvasName = ref('');
const createCanvasNameError = ref('');
const createCanvasProjectId = ref<string>();
const createProjectLoading = ref(false);
const createProjectOptions = ref<ProjectOption[]>([]);
const editing = ref(false);
const editModalOpen = ref(false);
const editCanvasId = ref('');
const editCanvasName = ref('');
const editCanvasNameError = ref('');
const editCanvasProjectId = ref<string>();
const scope = ref<CanvasScope>('mine');
const statusFilter = ref<'all' | CanvasStatus>('all');
const typeFilter = ref<'all' | CanvasType>('all');

const demoCanvases: CanvasListItem[] = [
  {
    collaboratorCount: 4,
    id: 'canvas-starfall-summer-ugc',
    isMine: true,
    isShared: true,
    name: 'Starfall 夏季 UGC 创意生产',
    nodeCount: 28,
    outputCount: 12,
    ownerName: '林青',
    projectName: 'Starfall 全球增长',
    requirementName: '8 月美国市场竖版素材',
    status: 'in_progress',
    thumbnailTone: 'violet',
    type: 'requirement',
    updatedAt: '刚刚',
  },
  {
    collaboratorCount: 3,
    id: 'canvas-pixel-jp-launch',
    isMine: true,
    isShared: false,
    name: 'Pixel Quest 日本首发素材',
    nodeCount: 21,
    outputCount: 20,
    ownerName: '李想',
    projectName: 'Pixel Quest 日本首发',
    requirementName: '20 条 9:16 竖版视频',
    status: 'pending_review',
    thumbnailTone: 'rose',
    type: 'requirement',
    updatedAt: '18 分钟前',
  },
  {
    collaboratorCount: 6,
    id: 'canvas-ark-creative-space',
    isMine: false,
    isShared: true,
    name: 'Project Ark 长期创意空间',
    nodeCount: 42,
    outputCount: 18,
    ownerName: '周恩',
    projectName: 'Project Ark 美国市场',
    status: 'in_progress',
    thumbnailTone: 'blue',
    type: 'project',
    updatedAt: '1 小时前',
  },
  {
    collaboratorCount: 2,
    id: 'canvas-starfall-roas-variant',
    isMine: true,
    isShared: false,
    name: 'ROAS 3.1 高表现素材裂变',
    nodeCount: 16,
    outputCount: 10,
    ownerName: '林青',
    projectName: 'Starfall 全球增长',
    status: 'draft',
    thumbnailTone: 'cyan',
    type: 'variant',
    updatedAt: '昨天 16:42',
  },
  {
    collaboratorCount: 8,
    id: 'canvas-template-ugc-video',
    isMine: false,
    isShared: true,
    name: 'UGC 视频生产模板',
    nodeCount: 12,
    outputCount: 0,
    ownerName: '素材中心',
    status: 'completed',
    thumbnailTone: 'indigo',
    type: 'template',
    updatedAt: '8 月 8 日',
  },
  {
    collaboratorCount: 2,
    id: 'canvas-archived-spring-sale',
    isMine: true,
    isShared: false,
    name: '春季大促创意探索',
    nodeCount: 34,
    outputCount: 24,
    ownerName: '王琪',
    projectName: 'Starfall 全球增长',
    status: 'archived',
    thumbnailTone: 'amber',
    type: 'exploration',
    updatedAt: '7 月 18 日',
  },
];

const canvases = ref<CanvasListItem[]>(isFusionDemoMode() ? demoCanvases : []);

const statusMeta: Record<CanvasStatus, { color: string; label: string }> = {
  archived: { color: 'default', label: '已归档' },
  completed: { color: 'success', label: '已完成' },
  draft: { color: 'default', label: '草稿' },
  in_progress: { color: 'processing', label: '制作中' },
  pending_review: { color: 'warning', label: '待验收' },
};

const typeMeta: Record<CanvasType, { icon: string; label: string }> = {
  analysis: { icon: 'lucide:chart-no-axes-combined', label: '分析画布' },
  exploration: { icon: 'lucide:compass', label: '创意探索' },
  project: { icon: 'lucide:briefcase-business', label: '项目画布' },
  requirement: { icon: 'lucide:clipboard-list', label: '工单画布' },
  template: { icon: 'lucide:layout-template', label: '模板画布' },
  variant: { icon: 'lucide:git-branch-plus', label: '裂变画布' },
  video: { icon: 'lucide:clapperboard', label: '视频画布' },
};

const scopeOptions = computed<Array<{ label: string; value: CanvasScope }>>(
  () => [
    { label: '我的画布', value: 'mine' },
    { label: '已归档', value: 'archived' },
    ...(isSystemAdmin.value
      ? [{ label: '所有画布', value: 'all' as const }]
      : []),
  ],
);

const selectableProjectOptions = computed(() =>
  createProjectOptions.value
    .filter((project) => !['archived', 'ended'].includes(project.status))
    .map((project) => ({
      label: project.productName
        ? `${project.name} · ${project.productName}`
        : project.name,
      value: project.id,
    })),
);

const filteredCanvases = computed(() => {
  const normalizedKeyword = keyword.value.trim().toLowerCase();
  return canvases.value.filter((item) => {
    const matchesKeyword =
      !normalizedKeyword ||
      [item.name, item.ownerName, item.projectName, item.requirementName]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(normalizedKeyword));
    const matchesStatus =
      statusFilter.value === 'all' || item.status === statusFilter.value;
    const matchesType =
      typeFilter.value === 'all' || item.type === typeFilter.value;
    // 归档画布只在“已归档”中展示，避免继续混入我的画布或部门共享画布。
    const isArchived = item.status === 'archived';
    const matchesScope =
      (scope.value === 'all' && isSystemAdmin.value) ||
      (scope.value === 'mine' && item.isMine && !isArchived) ||
      (scope.value === 'shared' && item.isShared && !isArchived) ||
      (scope.value === 'archived' && item.isMine && isArchived) ||
      (!isArchived && item.type === scope.value);
    return matchesKeyword && matchesStatus && matchesType && matchesScope;
  });
});

const overview = computed(() => [
  {
    icon: 'lucide:panels-top-left',
    label: '我的画布',
    tone: 'bg-muted text-muted-foreground',
    value: canvases.value.filter(
      (item) => item.isMine && item.status !== 'archived',
    ).length,
  },
  {
    icon: 'lucide:loader-circle',
    label: '制作中',
    tone: 'bg-muted text-muted-foreground',
    value: canvases.value.filter((item) => item.status === 'in_progress')
      .length,
  },
  {
    icon: 'lucide:badge-check',
    label: '待验收',
    tone: 'bg-muted text-muted-foreground',
    value: canvases.value.filter((item) => item.status === 'pending_review')
      .length,
  },
  {
    icon: 'lucide:images',
    label: '画布产出',
    tone: 'bg-muted text-muted-foreground',
    value: canvases.value.reduce((sum, item) => sum + item.outputCount, 0),
  },
]);

function resetFilters() {
  keyword.value = '';
  statusFilter.value = 'all';
  typeFilter.value = 'all';
}

function mapCanvasSummary(item: CanvasSummary, index: number): CanvasListItem {
  const tones: CanvasListItem['thumbnailTone'][] = [
    'violet',
    'blue',
    'cyan',
    'rose',
    'indigo',
    'amber',
  ];
  return {
    collaboratorCount: 1,
    id: item.id,
    isMine:
      !item.ownerId || item.ownerId === String(userStore.userInfo?.userId),
    isShared: false,
    name: item.name,
    nodeCount: item.nodeCount ?? 0,
    outputCount: item.outputCount ?? 0,
    ownerName:
      !item.ownerId || item.ownerId === String(userStore.userInfo?.userId)
        ? '我'
        : `用户 ${item.ownerId}`,
    projectId: item.projectId,
    projectName: item.projectId ? `项目 · ${item.projectId}` : undefined,
    requirementId: item.requirementId,
    requirementName: item.requirementId
      ? `工单 · ${item.requirementId}`
      : undefined,
    status: item.status === 'archived' ? 'archived' : 'in_progress',
    taskId: item.taskId,
    thumbnailTone: tones[index % tones.length] ?? 'violet',
    type: item.requirementId ? 'requirement' : 'project',
    updatedAt: new Date(item.updatedAt).toLocaleString('zh-CN', {
      hour12: false,
    }),
  };
}

function readLegacyCanvasDrafts() {
  const drafts: Array<{
    canvasId: string;
    draft: CanvasDraftPayload;
    name: string;
  }> = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key?.startsWith(legacyCanvasStoragePrefix)) continue;
    const canvasId = key.slice(legacyCanvasStoragePrefix.length);
    if (!/^canvas-[\w-]{6,160}$/.test(canvasId)) continue;
    try {
      const value = window.localStorage.getItem(key);
      const draft = value ? JSON.parse(value) : null;
      if (
        !draft ||
        !Array.isArray(draft.nodes) ||
        !Array.isArray(draft.edges) ||
        typeof draft.viewport !== 'object' ||
        (draft.nodes.length === 0 && draft.edges.length === 0)
      ) {
        continue;
      }
      drafts.push({
        canvasId,
        draft: {
          edges: draft.edges,
          nodes: draft.nodes,
          title: String(draft.title || '未命名画布'),
          updatedAt: String(draft.updatedAt || new Date().toISOString()),
          version: 1,
          viewport: draft.viewport,
        },
        name: String(draft.title || '未命名画布'),
      });
    } catch {
      // Ignore malformed legacy entries and keep scanning other canvases.
    }
  }
  return drafts;
}

async function migrateLegacyCanvasDrafts(existingIds: Set<string>) {
  let migrated = 0;
  for (const legacy of readLegacyCanvasDrafts()) {
    if (existingIds.has(legacy.canvasId)) continue;
    try {
      await createCanvasApi(legacy);
      existingIds.add(legacy.canvasId);
      migrated += 1;
    } catch (error) {
      console.warn('[Canvas] 旧画布自动迁移失败:', legacy.canvasId, error);
    }
  }
  return migrated;
}

async function loadCanvases() {
  loading.value = true;
  try {
    const params = {
      includeArchived: true,
      ...(scope.value === 'all' && isSystemAdmin.value
        ? { scope: 'all' as const }
        : {}),
    };
    let result = await getCanvasListApi(params);
    const migrated =
      scope.value === 'all'
        ? 0
        : await migrateLegacyCanvasDrafts(
            new Set(result.items.map((item) => item.id)),
          );
    if (migrated > 0) {
      result = await getCanvasListApi(params);
      message.success(`已恢复 ${migrated} 个本地旧画布`);
    }
    const apiCanvases = result.items.map((item, index) =>
      mapCanvasSummary(item, index),
    );
    if (!isFusionDemoMode()) {
      canvases.value = apiCanvases;
      return;
    }
    const apiIds = new Set(apiCanvases.map((item) => item.id));
    canvases.value = [
      ...apiCanvases,
      ...demoCanvases.filter((item) => !apiIds.has(item.id)),
    ];
  } catch (error) {
    message.error(error instanceof Error ? error.message : '画布列表加载失败');
  } finally {
    loading.value = false;
  }
}

function openCanvas(item: CanvasListItem) {
  void router.push({
    path: `/creative/canvas/${encodeURIComponent(item.id)}`,
    query: {
      ...(item.projectId ? { projectId: item.projectId } : {}),
      ...(item.requirementId ? { requirementId: item.requirementId } : {}),
      ...(item.taskId ? { taskId: item.taskId } : {}),
      title: item.name,
      ...(!item.isMine ? { view: 'readonly' } : {}),
    },
  });
}

function editCanvas(item: CanvasListItem) {
  editCanvasId.value = item.id;
  editCanvasName.value = item.name;
  editCanvasNameError.value = '';
  editCanvasProjectId.value = item.projectId;
  editModalOpen.value = true;
  void loadCreateProjectOptions();
}

function closeEditCanvasModal() {
  if (editing.value) return;
  editModalOpen.value = false;
}

async function saveCanvasEdits() {
  if (editing.value || !editCanvasId.value) return;
  const name = editCanvasName.value.trim();
  if (!name) {
    editCanvasNameError.value = '请输入画布名称';
    return;
  }

  editing.value = true;
  try {
    const updatedCanvas = await updateCanvasApi(editCanvasId.value, {
      name,
      projectId: editCanvasProjectId.value ?? null,
    });
    const selectedProject = selectableProjectOptions.value.find(
      (project) => project.value === updatedCanvas.projectId,
    );
    canvases.value = canvases.value.map((canvas) =>
      canvas.id === editCanvasId.value
        ? {
            ...canvas,
            name: updatedCanvas.name,
            projectId: updatedCanvas.projectId,
            projectName: updatedCanvas.projectId
              ? selectedProject?.label || `项目 · ${updatedCanvas.projectId}`
              : undefined,
            updatedAt: new Date(updatedCanvas.updatedAt).toLocaleString(
              'zh-CN',
              { hour12: false },
            ),
          }
        : canvas,
    );
    editModalOpen.value = false;
    message.success('画布信息已更新');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '画布更新失败');
  } finally {
    editing.value = false;
  }
}

function archiveCanvas(item: CanvasListItem) {
  if (archivingCanvasId.value) return;

  Modal.confirm({
    cancelText: '取消',
    centered: true,
    content: '归档后，画布会移动到“已归档”，原有节点与产出不会被删除。',
    okButtonProps: { danger: true },
    okText: '归档',
    title: `归档“${item.name}”？`,
    async onOk() {
      archivingCanvasId.value = item.id;
      try {
        const archivedCanvas = await archiveCanvasApi(item.id);
        canvases.value = canvases.value.map((canvas) =>
          canvas.id === item.id
            ? {
                ...canvas,
                status: 'archived',
                updatedAt: new Date(archivedCanvas.updatedAt).toLocaleString(
                  'zh-CN',
                  { hour12: false },
                ),
              }
            : canvas,
        );
        message.success('画布已归档');
      } catch (error) {
        message.error(error instanceof Error ? error.message : '画布归档失败');
        throw error;
      } finally {
        archivingCanvasId.value = '';
      }
    },
  });
}

async function restoreCanvas(item: CanvasListItem) {
  if (restoringCanvasId.value) return;
  restoringCanvasId.value = item.id;
  try {
    const restoredCanvas = await updateCanvasApi(item.id, { status: 'active' });
    canvases.value = canvases.value.map((canvas) =>
      canvas.id === item.id
        ? {
            ...canvas,
            status: 'in_progress',
            updatedAt: new Date(restoredCanvas.updatedAt).toLocaleString(
              'zh-CN',
              { hour12: false },
            ),
          }
        : canvas,
    );
    message.success('画布已恢复');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '画布恢复失败');
  } finally {
    restoringCanvasId.value = '';
  }
}

async function loadCreateProjectOptions() {
  if (createProjectLoading.value || createProjectOptions.value.length > 0) {
    return;
  }
  createProjectLoading.value = true;
  try {
    createProjectOptions.value = await getProjectOptionsApi();
  } catch (error) {
    message.warning(
      error instanceof Error
        ? `项目列表加载失败：${error.message}`
        : '项目列表加载失败，仍可创建个人画布',
    );
  } finally {
    createProjectLoading.value = false;
  }
}

function openCreateCanvasModal() {
  createCanvasName.value = '';
  createCanvasNameError.value = '';
  createCanvasProjectId.value = undefined;
  createModalOpen.value = true;
  void loadCreateProjectOptions();
}

function closeCreateCanvasModal() {
  if (creating.value) return;
  createModalOpen.value = false;
}

async function createCanvas() {
  if (creating.value) return;
  const name = createCanvasName.value.trim();
  if (!name) {
    createCanvasNameError.value = '请输入画布名称';
    return;
  }
  creating.value = true;
  try {
    const canvas = await createCanvasApi({
      name,
      ...(createCanvasProjectId.value
        ? { projectId: createCanvasProjectId.value }
        : {}),
    });
    createModalOpen.value = false;
    await router.push({
      path: `/creative/canvas/${encodeURIComponent(canvas.id)}`,
      query: {
        ...(canvas.projectId ? { projectId: canvas.projectId } : {}),
        source: 'blank',
        title: canvas.name,
      },
    });
  } catch (error) {
    message.error(error instanceof Error ? error.message : '画布创建失败');
  } finally {
    creating.value = false;
  }
}

watch(scope, () => {
  void loadCanvases();
});
onMounted(async () => {
  try {
    isSystemAdmin.value = (await getCanvasCapabilitiesApi()).canViewAll;
  } catch {
    isSystemAdmin.value = false;
  }
  await loadCanvases();
});
</script>

<template>
  <Page class="bg-muted/40" content-class="p-3 sm:p-4">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section
        class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="min-w-0 flex-1">
          <h1 class="text-foreground m-0 text-xl font-semibold">AI创意画布</h1>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            在一个工作空间里串联项目上下文、创意方向、AI 生成与素材交付。
          </p>
        </div>
        <div class="flex w-full flex-none items-center gap-2 sm:w-auto">
          <Button
            aria-label="刷新画布列表"
            class="!inline-flex min-w-24 flex-1 items-center justify-center whitespace-nowrap sm:flex-none"
            :loading="loading"
            @click="loadCanvases"
          >
            <template #icon>
              <IconifyIcon icon="lucide:refresh-cw" />
            </template>
            刷新
          </Button>
          <Button
            class="!inline-flex min-w-28 flex-1 items-center justify-center whitespace-nowrap sm:flex-none"
            type="primary"
            :loading="creating"
            @click="openCreateCanvasModal"
          >
            <template #icon>
              <IconifyIcon icon="lucide:plus" />
            </template>
            新建画布
          </Button>
        </div>
      </section>

      <Row :gutter="[16, 16]">
        <Col v-for="item in overview" :key="item.label" :xs="12" :lg="6">
          <Card class="border-border bg-card" :body-style="{ padding: '16px' }">
            <div class="flex items-center gap-3">
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" class="text-lg" />
              </div>
              <div>
                <div class="text-muted-foreground text-xs">
                  {{ item.label }}
                </div>
                <div class="text-foreground mt-0.5 text-xl font-semibold">
                  {{ item.value }}
                </div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Card class="border-border bg-card" :body-style="{ padding: 0 }">
        <div class="border-border overflow-x-auto border-b px-4">
          <div
            class="flex min-w-max gap-1"
            role="tablist"
            aria-label="画布分类"
          >
            <button
              v-for="item in scopeOptions"
              :key="item.value"
              type="button"
              role="tab"
              :aria-selected="scope === item.value"
              class="relative cursor-pointer border-0 bg-transparent px-3 py-3.5 text-sm transition-colors"
              :class="
                scope === item.value
                  ? 'text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              "
              :disabled="loading"
              @click="scope = item.value"
            >
              {{ item.label }}
              <span
                v-if="scope === item.value"
                class="bg-primary absolute inset-x-2 bottom-0 h-0.5 rounded-full"
              ></span>
            </button>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3 p-4">
          <Input.Search
            v-model:value="keyword"
            allow-clear
            aria-label="搜索画布"
            class="min-w-0 flex-1 basis-full sm:basis-64 lg:max-w-md"
            placeholder="搜索画布、项目或工单"
          />
          <Select
            v-model:value="typeFilter"
            aria-label="按画布类型筛选"
            class="w-full sm:w-36"
            :options="[
              { label: '全部类型', value: 'all' },
              ...Object.entries(typeMeta).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
          />
          <Select
            v-model:value="statusFilter"
            aria-label="按画布状态筛选"
            class="w-full sm:w-36"
            :options="[
              { label: '全部状态', value: 'all' },
              ...Object.entries(statusMeta).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
          />
          <Button class="" @click="resetFilters">重置</Button>
        </div>
      </Card>

      <Spin :spinning="loading">
        <div
          v-if="filteredCanvases.length > 0"
          class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        >
          <article
            v-for="item in filteredCanvases"
            :key="item.id"
            class="border-border bg-card hover:bg-muted/50 group overflow-hidden rounded-[var(--adpulse-radius)] border transition-colors"
          >
            <button
              type="button"
              class="block w-full cursor-pointer border-0 bg-transparent p-0 text-left"
              :aria-label="
                item.isMine
                  ? `打开画布：${item.name}`
                  : `画布摘要：${item.name}`
              "
              :disabled="!item.isMine && !isSystemAdmin && !isFusionDemoMode()"
              @click="openCanvas(item)"
            >
              <div
                class="border-border bg-muted/60 relative flex h-28 items-center justify-center overflow-hidden border-b p-4"
              >
                <div class="flex items-center justify-center">
                  <div
                    class="border-border bg-card text-muted-foreground flex h-12 w-12 items-center justify-center rounded-md border"
                  >
                    <IconifyIcon
                      :icon="typeMeta[item.type].icon"
                      class="text-2xl"
                    />
                  </div>
                </div>
                <Tag class="absolute left-3 top-3 m-0">
                  {{ typeMeta[item.type].label }}
                </Tag>
                <Tag
                  class="absolute right-3 top-3 m-0"
                  :color="statusMeta[item.status].color"
                >
                  {{ statusMeta[item.status].label }}
                </Tag>
              </div>

              <div class="px-4 pt-4">
                <h2
                  class="text-foreground m-0 truncate text-base font-semibold"
                >
                  {{ item.name }}
                </h2>
                <p class="text-muted-foreground mb-0 mt-1.5 truncate text-xs">
                  {{ item.projectName || '未关联项目' }}
                  <template v-if="item.requirementName">
                    · {{ item.requirementName }}
                  </template>
                </p>
                <div
                  class="border-border text-muted-foreground mt-4 flex items-center justify-between border-t pt-3 text-xs"
                >
                  <span class="flex items-center gap-3">
                    <span class="flex items-center gap-1">
                      <IconifyIcon icon="lucide:blocks" />
                      {{ item.nodeCount }} 节点
                    </span>
                    <span class="flex items-center gap-1">
                      <IconifyIcon icon="lucide:images" />
                      {{ item.outputCount }} 产出
                    </span>
                  </span>
                  <span>{{ item.updatedAt }}</span>
                </div>
              </div>
            </button>

            <div class="flex items-center justify-between gap-3 px-4 pb-4 pt-3">
              <span
                class="text-muted-foreground flex min-w-0 items-center gap-1.5 text-xs"
              >
                <span
                  class="bg-muted text-muted-foreground flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-medium"
                >
                  {{ item.ownerName.slice(0, 1) }}
                </span>
                <span class="truncate">{{ item.ownerName }}</span>
                <span v-if="item.collaboratorCount > 1" class="shrink-0">
                  +{{ item.collaboratorCount - 1 }}
                </span>
              </span>

              <div v-if="item.isMine" class="flex shrink-0 items-center gap-2">
                <Button @click="editCanvas(item)">
                  <template #icon>
                    <IconifyIcon icon="lucide:pencil" />
                  </template>
                  编辑画布
                </Button>
                <Button
                  v-if="item.status !== 'archived'"
                  danger
                  :loading="archivingCanvasId === item.id"
                  @click="archiveCanvas(item)"
                >
                  <template #icon>
                    <IconifyIcon icon="lucide:archive" />
                  </template>
                  归档
                </Button>
                <Button
                  v-else
                  :loading="restoringCanvasId === item.id"
                  type="primary"
                  @click="restoreCanvas(item)"
                >
                  <template #icon>
                    <IconifyIcon icon="lucide:archive-restore" />
                  </template>
                  恢复
                </Button>
              </div>

              <Button
                v-else-if="isSystemAdmin || isFusionDemoMode()"
                class="!text-primary !p-0"
                type="link"
                @click="openCanvas(item)"
              >
                查看画布
                <IconifyIcon icon="lucide:arrow-right" />
              </Button>
              <span v-else class="text-muted-foreground text-xs"
                >仅查看摘要</span
              >
            </div>
          </article>
        </div>

        <Card v-else class="border-border bg-card">
          <Empty description="没有符合条件的画布">
            <Button class="" @click="resetFilters">清除筛选</Button>
          </Empty>
        </Card>
      </Spin>
    </div>

    <Modal
      v-model:open="createModalOpen"
      :closable="!creating"
      :footer="null"
      :keyboard="!creating"
      :mask-closable="!creating"
      :width="520"
      destroy-on-close
      title="新建画布"
      @cancel="closeCreateCanvasModal"
    >
      <form class="pt-1" @submit.prevent="createCanvas">
        <label class="block">
          <span class="text-foreground mb-2 block text-sm font-medium">
            <span class="mr-1 text-red-500">*</span>画布名称
          </span>
          <Input
            v-model:value="createCanvasName"
            :disabled="creating"
            :maxlength="120"
            :status="createCanvasNameError ? 'error' : undefined"
            allow-clear
            autofocus
            placeholder="例如：Starfall 新素材探索"
            @update:value="createCanvasNameError = ''"
          />
          <span
            v-if="createCanvasNameError"
            class="mt-1.5 block text-xs text-red-500"
          >
            {{ createCanvasNameError }}
          </span>
        </label>

        <label class="mt-6 block">
          <span class="text-foreground mb-2 block text-sm font-medium">
            关联项目（选填）
          </span>
          <Select
            v-model:value="createCanvasProjectId"
            :disabled="creating"
            :loading="createProjectLoading"
            :options="selectableProjectOptions"
            allow-clear
            class="w-full"
            option-filter-prop="label"
            placeholder="不选择则创建为我的画布"
            show-search
          />
        </label>

        <div class="mt-8 flex justify-end gap-2">
          <Button :disabled="creating" @click="closeCreateCanvasModal">
            取消
          </Button>
          <Button html-type="submit" :loading="creating" type="primary">
            创建画布
          </Button>
        </div>
      </form>
    </Modal>

    <Modal
      v-model:open="editModalOpen"
      :closable="!editing"
      :footer="null"
      :keyboard="!editing"
      :mask-closable="!editing"
      :width="520"
      destroy-on-close
      title="编辑画布"
      @cancel="closeEditCanvasModal"
    >
      <form class="pt-1" @submit.prevent="saveCanvasEdits">
        <label class="block">
          <span class="text-foreground mb-2 block text-sm font-medium">
            <span class="mr-1 text-red-500">*</span>画布名称
          </span>
          <Input
            v-model:value="editCanvasName"
            :disabled="editing"
            :maxlength="120"
            :status="editCanvasNameError ? 'error' : undefined"
            allow-clear
            autofocus
            placeholder="例如：Starfall 新素材探索"
            @update:value="editCanvasNameError = ''"
          />
          <span
            v-if="editCanvasNameError"
            class="mt-1.5 block text-xs text-red-500"
          >
            {{ editCanvasNameError }}
          </span>
        </label>

        <label class="mt-6 block">
          <span class="text-foreground mb-2 block text-sm font-medium">
            关联项目（选填）
          </span>
          <Select
            v-model:value="editCanvasProjectId"
            :disabled="editing"
            :loading="createProjectLoading"
            :options="selectableProjectOptions"
            allow-clear
            class="w-full"
            option-filter-prop="label"
            placeholder="不选择则归入我的画布"
            show-search
          />
          <span class="text-muted-foreground mt-2 block text-xs leading-5">
            关联项目后归入“项目画布”；取消关联则归入“我的画布”。
          </span>
        </label>

        <div class="mt-8 flex justify-end gap-2">
          <Button :disabled="editing" @click="closeEditCanvasModal">
            取消
          </Button>
          <Button html-type="submit" :loading="editing" type="primary">
            保存修改
          </Button>
        </div>
      </form>
    </Modal>
  </Page>
</template>
