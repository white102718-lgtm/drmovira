<script lang="ts" setup>
import type {
  MaterialFolderInput,
  MaterialFolderPatch,
  MaterialFolderScope,
  MaterialFolderSummary,
  MaterialFolderVisibility,
} from '#/domain/material';

import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue';

import {
  Button,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Tabs,
} from 'ant-design-vue';

import { parseMaterialNames } from '#/domain/material/name-filter';

import MaterialNameFilter from './MaterialNameFilter.vue';

type FolderHomeTab = 'personal' | 'recent' | 'shared';

interface Props {
  activeTab?: FolderHomeTab;
  loading?: boolean;
  keyword?: string;
  materialNamesText?: string;
  searching?: boolean;
  personalFolders: readonly MaterialFolderSummary[];
  recentFolders: readonly MaterialFolderSummary[];
  sharedFolders: readonly MaterialFolderSummary[];
}

const props = withDefaults(defineProps<Props>(), {
  activeTab: 'recent',
  loading: false,
  keyword: '',
  materialNamesText: '',
  searching: false,
});

const emit = defineEmits<{
  (event: 'createFolder', input: MaterialFolderInput): void;
  (event: 'deleteFolder', folder: MaterialFolderSummary): void;
  (event: 'openFolder', folder: MaterialFolderSummary): void;
  (
    event: 'search',
    filters: { keyword: string; materialNamesText: string },
  ): void;
  (event: 'tabChange', tab: FolderHomeTab): void;
  (event: 'refresh'): void;
  (event: 'updateFolder', folderId: string, patch: MaterialFolderPatch): void;
}>();

const FOLDER_RENDER_BATCH_SIZE = 12;

const activeTab = ref<FolderHomeTab>(props.activeTab);
const selectedSharedOwner = ref('all');
const keyword = ref(props.keyword);
const materialNamesText = ref(props.materialNamesText);
const materialNameCount = computed(
  () => parseMaterialNames(materialNamesText.value).length,
);
const modalOpen = ref(false);
const editingId = ref('');
const creationScope = ref<MaterialFolderScope>('personal');
const loadMoreSentinelRef = ref<HTMLElement>();
const renderedFolderCounts = reactive<Record<FolderHomeTab, number>>({
  personal: FOLDER_RENDER_BATCH_SIZE,
  recent: FOLDER_RENDER_BATCH_SIZE,
  shared: FOLDER_RENDER_BATCH_SIZE,
});

const form = reactive<{
  name: string;
  visibility: MaterialFolderVisibility;
}>({
  name: '',
  visibility: 'private',
});

watch(
  () => props.keyword,
  (value) => {
    keyword.value = value;
  },
);
watch(
  () => props.materialNamesText,
  (value) => {
    materialNamesText.value = value;
  },
);

function searchFolders() {
  emit('search', {
    keyword: keyword.value.trim(),
    materialNamesText: materialNamesText.value,
  });
}

function resetSearch() {
  keyword.value = '';
  materialNamesText.value = '';
  searchFolders();
}

function folderPath(folder: MaterialFolderSummary) {
  return folder.path?.map((part) => part.name).join(' / ') ?? folder.name;
}

function materialCountLabel(folder: MaterialFolderSummary) {
  return folder.matchedMaterialCount === undefined
    ? `${folder.materialCount} 个素材`
    : `匹配 ${folder.matchedMaterialCount} / 共 ${folder.materialCount} 个素材`;
}

watch(activeTab, (tab) => {
  resetRenderedFolders(tab);
  emit('tabChange', tab);
});

watch(
  () => props.activeTab,
  (tab) => {
    if (tab !== activeTab.value) activeTab.value = tab;
  },
);

/** 后端不存配色，按 id 稳定地取一个，保证同一文件夹每次渲染颜色一致。 */
function formatVisitedAt(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString('zh-CN', { hour12: false });
}

const ownerOptions = computed(() => {
  const owners = [
    ...new Map(
      props.sharedFolders
        .filter((folder) => folder.owner)
        .map((folder) => [
          folder.owner,
          { label: folder.owner, value: folder.owner },
        ]),
    ).values(),
  ];
  return [{ label: '全部创建人', value: 'all' }, ...owners];
});

const filteredSharedFolders = computed(() =>
  props.sharedFolders.filter(
    (folder) =>
      selectedSharedOwner.value === 'all' ||
      folder.owner === selectedSharedOwner.value,
  ),
);

const currentFolders = computed<readonly MaterialFolderSummary[]>(() => {
  if (activeTab.value === 'personal') return props.personalFolders;
  if (activeTab.value === 'shared') return filteredSharedFolders.value;
  return props.recentFolders;
});

const visibleFolders = computed(() =>
  currentFolders.value.slice(0, renderedFolderCounts[activeTab.value]),
);
const hasMoreFolders = computed(
  () => visibleFolders.value.length < currentFolders.value.length,
);

function resetRenderedFolders(tab: FolderHomeTab = activeTab.value) {
  renderedFolderCounts[tab] = FOLDER_RENDER_BATCH_SIZE;
}

function loadMoreFolders() {
  if (!hasMoreFolders.value) return;
  renderedFolderCounts[activeTab.value] += FOLDER_RENDER_BATCH_SIZE;
  void observeLoadMoreSentinel();
}

let loadMoreObserver: IntersectionObserver | undefined;

function stopLoadMoreObserver() {
  loadMoreObserver?.disconnect();
  loadMoreObserver = undefined;
}

async function observeLoadMoreSentinel() {
  await nextTick();
  stopLoadMoreObserver();
  if (
    !hasMoreFolders.value ||
    !loadMoreSentinelRef.value ||
    !('IntersectionObserver' in window)
  ) {
    return;
  }

  loadMoreObserver = new IntersectionObserver(
    ([entry]) => {
      if (entry?.isIntersecting) loadMoreFolders();
    },
    { rootMargin: '160px 0px' },
  );
  loadMoreObserver.observe(loadMoreSentinelRef.value);
}

watch(
  () => [
    activeTab.value,
    props.personalFolders,
    props.recentFolders,
    props.sharedFolders,
  ],
  () => {
    resetRenderedFolders();
    void observeLoadMoreSentinel();
  },
);

watch(hasMoreFolders, () => {
  void observeLoadMoreSentinel();
});

const visibilityOptions = [
  { label: '全员可见', value: 'organization' },
  { label: '本部门可见', value: 'department' },
  { label: '仅自己', value: 'private' },
];

const visibilityLabel: Record<MaterialFolderVisibility, string> = {
  organization: '全员可见',
  department: '本部门可见',
  private: '仅自己',
};

const modalTitle = computed(() => {
  if (editingId.value) return '文件夹设置';
  return creationScope.value === 'department' ? '新建共享文件夹' : '新建文件夹';
});

function openCreate(scope: MaterialFolderScope = 'personal') {
  editingId.value = '';
  creationScope.value = scope;
  form.name = '';
  form.visibility = scope === 'department' ? 'department' : 'private';
  modalOpen.value = true;
}

function openEdit(folder: MaterialFolderSummary) {
  editingId.value = folder.id;
  creationScope.value = folder.scope;
  form.name = folder.name;
  form.visibility = folder.visibility;
  modalOpen.value = true;
}

function saveFolder() {
  const name = form.name.trim();
  if (!name) {
    message.warning('请输入文件夹名称');
    return;
  }

  const input: MaterialFolderInput = {
    name,
    scope: creationScope.value,
    visibility: form.visibility,
  };

  if (editingId.value) {
    emit('updateFolder', editingId.value, input);
  } else {
    emit('createFolder', input);
  }
  modalOpen.value = false;
}

function openFolder(folder: MaterialFolderSummary) {
  emit('openFolder', folder);
}

function removeFolder(folder: MaterialFolderSummary) {
  emit('deleteFolder', folder);
}

onMounted(() => {
  void observeLoadMoreSentinel();
});

onUnmounted(() => {
  stopLoadMoreObserver();
});
</script>

<template>
  <div class="cloud-home min-w-0 space-y-4">
    <section class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <h1 class="text-foreground text-xl font-semibold tracking-tight">
          素材库
        </h1>
        <p class="text-muted-foreground mt-1 text-sm">
          集中管理个人与共享素材文件夹。
        </p>
      </div>
      <Button type="primary" class="sm: gap-2" @click="openCreate('personal')">
        <template #icon>
          <span class="icon-[lucide--folder-plus]"></span>
        </template>
        新建文件夹
      </Button>
    </section>

    <section class="border-border bg-card rounded-lg border p-3">
      <div class="flex flex-wrap items-start gap-3">
        <div class="w-full sm:w-[240px]">
          <label for="folder-keyword" class="mb-1 block text-sm"
            >文件夹名称</label
          >
          <Input
            id="folder-keyword"
            v-model:value="keyword"
            allow-clear
            placeholder="搜索文件夹"
            @press-enter="searchFolders"
          >
            <template #prefix>
              <span class="icon-[lucide--search] text-muted-foreground"></span>
            </template>
          </Input>
        </div>
        <div class="w-full sm:w-[360px]">
          <label for="folder-material-names" class="mb-1 block text-sm">
            素材名称
            <span class="text-muted-foreground text-xs"
              >每行一个 · {{ materialNameCount }} 个</span
            >
          </label>
          <MaterialNameFilter
            id="folder-material-names"
            v-model:value="materialNamesText"
            single-row
          />
        </div>
        <div class="flex gap-2 sm:pt-6">
          <Button type="primary" :loading="loading" @click="searchFolders"
            >搜索</Button
          >
          <Button @click="resetSearch">重置</Button>
          <Button :loading="loading" @click="emit('refresh')">刷新</Button>
        </div>
      </div>
    </section>

    <section class="border-border bg-card rounded-lg border p-4">
      <Tabs
        v-model:active-key="activeTab"
        :animated="false"
        class="cloud-home-tabs"
      >
        <Tabs.TabPane key="recent" :tab="searching ? '搜索结果' : '最近访问'">
          <section class="space-y-3">
            <div>
              <h2 class="text-foreground text-base font-semibold">
                {{ searching ? '搜索结果' : '最近访问' }}
              </h2>
              <p class="text-muted-foreground text-xs">
                {{
                  searching
                    ? '展示符合条件的可访问文件夹，点击后继续筛选对应素材。'
                    : '按最近打开时间展示文件夹。'
                }}
              </p>
            </div>
            <div v-if="loading" class="cloud-folder-feedback">
              正在加载文件夹…
            </div>
            <div
              v-else-if="visibleFolders.length > 0"
              class="folder-grid grid gap-3"
            >
              <article
                v-for="folder in visibleFolders"
                :key="folder.id"
                class="border-border bg-card hover:bg-accent group min-w-0 rounded-lg border p-4 transition-colors"
              >
                <button
                  type="button"
                  class="flex w-full min-w-0 items-start gap-3 text-left"
                  :aria-label="`打开最近访问的文件夹 ${folder.name}`"
                  @click="openFolder(folder)"
                >
                  <span
                    class="bg-muted text-muted-foreground flex h-11 w-11 flex-none items-center justify-center rounded-lg"
                  >
                    <span class="icon-[lucide--folder-clock] text-2xl"></span>
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="text-foreground block truncate font-medium">
                      {{ folder.name }}
                    </span>
                    <span
                      v-if="folder.path && folder.path.length > 1"
                      :title="folderPath(folder)"
                      class="text-muted-foreground mt-1 block truncate text-xs"
                      >{{ folderPath(folder) }}</span
                    >
                    <span
                      class="text-muted-foreground mt-1 block truncate text-xs"
                    >
                      {{ folder.owner }}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  class="text-muted-foreground border-border mt-4 flex w-full items-center justify-between gap-3 border-t pt-3 text-left text-xs"
                  :aria-label="`打开最近访问的文件夹 ${folder.name}`"
                  @click="openFolder(folder)"
                >
                  <span class="shrink-0">{{ materialCountLabel(folder) }}</span>
                  <span class="flex min-w-0 items-center gap-1 text-right">
                    <span class="icon-[lucide--history] shrink-0"></span>
                    <span class="truncate">{{
                      formatVisitedAt(folder.lastVisitedAt)
                    }}</span>
                  </span>
                </button>
              </article>
            </div>
            <div v-else class="cloud-folder-feedback">
              {{
                searching
                  ? '未找到符合条件的可访问文件夹'
                  : '打开文件夹后会显示在这里'
              }}
            </div>
          </section>
        </Tabs.TabPane>

        <Tabs.TabPane key="personal" tab="我的空间">
          <section class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h2 class="text-foreground text-base font-semibold">
                  我的空间
                </h2>
                <p class="text-muted-foreground text-xs">
                  仅展示当前用户创建的个人文件夹。
                </p>
              </div>
              <Button type="link" @click="openCreate('personal')">
                新建文件夹
              </Button>
            </div>
            <div v-if="loading" class="cloud-folder-feedback">
              正在加载我的空间…
            </div>
            <div
              v-else-if="visibleFolders.length > 0"
              class="folder-grid grid gap-3"
            >
              <article
                v-for="folder in visibleFolders"
                :key="folder.id"
                class="border-border bg-card hover:bg-accent group min-w-0 rounded-lg border p-4 transition-colors"
              >
                <div class="flex min-w-0 items-start gap-3">
                  <button
                    type="button"
                    class="flex min-w-0 flex-1 items-start gap-3 text-left"
                    :aria-label="`打开文件夹 ${folder.name}`"
                    @click="openFolder(folder)"
                  >
                    <span
                      class="bg-muted text-muted-foreground flex h-11 w-11 flex-none items-center justify-center rounded-lg"
                    >
                      <span class="icon-[lucide--folder] text-2xl"></span>
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="text-foreground block truncate font-medium">
                        {{ folder.name }}
                      </span>
                      <span
                        v-if="folder.path && folder.path.length > 1"
                        :title="folderPath(folder)"
                        class="text-muted-foreground mt-1 block truncate text-xs"
                        >{{ folderPath(folder) }}</span
                      >
                      <span
                        class="text-muted-foreground mt-1 block truncate text-xs"
                      >
                        {{ folder.owner }}
                      </span>
                    </span>
                  </button>
                  <div
                    v-if="folder.isOwner"
                    class="flex flex-none items-center"
                  >
                    <Button
                      type="text"
                      class="!w-10 !min-w-0 !p-0"
                      :aria-label="`设置 ${folder.name}`"
                      @click="openEdit(folder)"
                    >
                      <span class="icon-[lucide--settings-2]"></span>
                    </Button>
                    <Popconfirm
                      :title="`删除「${folder.name}」？文件夹里还有素材时不可删除。`"
                      ok-text="删除"
                      cancel-text="取消"
                      @confirm="removeFolder(folder)"
                    >
                      <Button
                        type="text"
                        danger
                        class="!w-10 !min-w-0 !p-0"
                        :aria-label="`删除 ${folder.name}`"
                      >
                        <span class="icon-[lucide--trash-2]"></span>
                      </Button>
                    </Popconfirm>
                  </div>
                </div>
                <button
                  type="button"
                  class="text-muted-foreground border-border mt-4 flex w-full items-center justify-between border-t pt-3 text-left text-xs"
                  @click="openFolder(folder)"
                >
                  <span>{{ materialCountLabel(folder) }}</span>
                  <span class="inline-flex items-center gap-1">
                    <span
                      :class="
                        folder.visibility === 'private'
                          ? 'icon-[lucide--lock] text-muted-foreground'
                          : 'icon-[lucide--users] text-muted-foreground'
                      "
                    ></span>
                    {{ visibilityLabel[folder.visibility] }}
                  </span>
                </button>
              </article>
            </div>
            <div v-else class="cloud-folder-feedback">当前空间暂无文件夹</div>
          </section>
        </Tabs.TabPane>

        <Tabs.TabPane key="shared" tab="共享文件夹">
          <section class="space-y-3">
            <div
              class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"
            >
              <div>
                <h2 class="text-foreground text-base font-semibold">
                  共享文件夹（部门文件夹）
                </h2>
                <p class="text-muted-foreground text-xs">
                  展示当前可访问的部门共享及全员可见素材目录。
                </p>
              </div>
              <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Select
                  v-model:value="selectedSharedOwner"
                  :options="ownerOptions"
                  class="w-full sm:w-44"
                  aria-label="按创建人筛选共享文件夹"
                />
                <Button type="link" @click="openCreate('department')">
                  新建共享文件夹
                </Button>
              </div>
            </div>
            <div v-if="loading" class="cloud-folder-feedback">
              正在加载共享文件夹…
            </div>
            <div
              v-else-if="visibleFolders.length > 0"
              class="folder-grid grid gap-3"
            >
              <article
                v-for="folder in visibleFolders"
                :key="folder.id"
                class="border-border bg-card hover:bg-accent group min-w-0 rounded-lg border p-4 transition-colors"
              >
                <div class="flex min-w-0 items-start gap-3">
                  <button
                    type="button"
                    class="flex min-w-0 flex-1 items-start gap-3 text-left"
                    :aria-label="`打开共享文件夹 ${folder.name}`"
                    @click="openFolder(folder)"
                  >
                    <span
                      class="bg-muted text-muted-foreground flex h-11 w-11 flex-none items-center justify-center rounded-lg"
                    >
                      <span class="icon-[lucide--folders] text-2xl"></span>
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="text-foreground block truncate font-medium">
                        {{ folder.name }}
                      </span>
                      <span
                        v-if="folder.path && folder.path.length > 1"
                        :title="folderPath(folder)"
                        class="text-muted-foreground mt-1 block truncate text-xs"
                        >{{ folderPath(folder) }}</span
                      >
                      <span
                        class="text-muted-foreground mt-1 block truncate text-xs"
                      >
                        创建人：{{ folder.owner }}
                      </span>
                      <span
                        class="text-muted-foreground mt-1 block truncate text-xs"
                      >
                        部门：{{ folder.ownerDepartment || '未记录部门' }}
                      </span>
                    </span>
                  </button>
                  <Button
                    v-if="folder.isOwner"
                    type="text"
                    class="!w-10 !min-w-0 !p-0"
                    :aria-label="`设置 ${folder.name}`"
                    @click="openEdit(folder)"
                  >
                    <span class="icon-[lucide--settings-2]"></span>
                  </Button>
                </div>
                <button
                  type="button"
                  class="text-muted-foreground border-border mt-4 flex w-full items-center justify-between border-t pt-3 text-left text-xs"
                  @click="openFolder(folder)"
                >
                  <span>{{ materialCountLabel(folder) }}</span>
                  <span
                    class="text-muted-foreground inline-flex items-center gap-1"
                  >
                    <span class="icon-[lucide--users]"></span>
                    {{ visibilityLabel[folder.visibility] }}
                  </span>
                </button>
              </article>
            </div>
            <div v-else class="cloud-folder-feedback">
              当前筛选条件下暂无共享文件夹
            </div>
          </section>
        </Tabs.TabPane>
      </Tabs>
    </section>

    <div
      v-if="hasMoreFolders && !loading"
      ref="loadMoreSentinelRef"
      class="text-muted-foreground flex flex-col items-center gap-2 py-6 text-sm"
    >
      <span>继续向下滚动可加载更多文件夹</span>
      <Button @click="loadMoreFolders">加载更多</Button>
    </div>

    <Modal
      v-model:open="modalOpen"
      :title="modalTitle"
      ok-text="保存"
      cancel-text="取消"
      :width="520"
      @ok="saveFolder"
    >
      <div class="space-y-4 py-2">
        <label class="block">
          <span class="text-foreground mb-1.5 block text-sm font-medium">
            文件夹名称 <span class="text-red-500">*</span>
          </span>
          <Input
            v-model:value="form.name"
            :maxlength="40"
            show-count
            placeholder="例如：8 月已审核素材"
          />
        </label>

        <label class="block">
          <span class="text-foreground mb-1.5 block text-sm font-medium">
            查看权限 <span class="text-red-500">*</span>
          </span>
          <Select
            v-model:value="form.visibility"
            class="w-full"
            :options="visibilityOptions"
          />
          <span class="text-muted-foreground mt-1.5 block text-xs">
            全员可见：所有成员；本部门可见：仅同部门成员；仅自己：仅文件夹所有者。
          </span>
        </label>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* 保留原有的自适应卡片栅格：即使项目较少，卡片宽度也保持稳定。 */
.folder-grid {
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
}

.cloud-folder-feedback {
  padding: 40px 16px;
  border: 1px dashed hsl(var(--border));
  border-radius: var(--adpulse-radius-lg);
  color: hsl(var(--muted-foreground));
  background: hsl(var(--card));
  font-size: 14px;
  text-align: center;
}

button:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 3px;
  border-radius: 8px;
}
</style>
