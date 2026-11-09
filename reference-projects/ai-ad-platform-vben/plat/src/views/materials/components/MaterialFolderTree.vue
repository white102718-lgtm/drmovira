<script lang="ts" setup>
import type { MaterialFolderSummary } from '#/domain/material';

import { computed, onMounted, ref, watch } from 'vue';

import { httpFolderService } from '#/domain/material';
import { message } from 'ant-design-vue';
import Input from 'ant-design-vue/es/input';

import MaterialFolderCreatePopover from './MaterialFolderCreatePopover.vue';

export interface TreeSelection {
  folderId?: string;
  folderName?: string;
  type: 'all' | 'common' | 'effectiveness' | 'folder';
}

const props = defineProps<{
  /** 验收选择器开放创建入口，其他目录树保持既有操作。 */
  allowCreate?: boolean;
  /** 选择弹窗随目录内容增减高度；侧栏继续占满可用空间。 */
  autoHeight?: boolean;
  modelValue: TreeSelection;
  showEffectiveness?: boolean;
  showLibrary?: boolean;
}>();
const emit = defineEmits<{
  (e: 'update:modelValue', v: TreeSelection): void;
}>();

const folders = ref<MaterialFolderSummary[]>([]);
const folderLoading = ref(false);
const keyword = ref('');
const foldersById = computed(
  () => new Map(folders.value.map((folder) => [folder.id, folder])),
);

const loadFolders = async () => {
  folderLoading.value = true;
  try {
    // 保留完整的可见目录，搜索在本地进行，避免后端按名称筛掉匹配项的祖先。
    const [personal, department] = await Promise.all([
      httpFolderService.list({ scope: 'personal' }),
      httpFolderService.list({ scope: 'department' }),
    ]);
    folders.value = [
      ...new Map(
        [...personal, ...department].map((folder) => [folder.id, folder]),
      ).values(),
    ];
  } finally {
    folderLoading.value = false;
  }
};

// 侧栏与首页保持一致：共享区同时显示本部门和全员可见文件夹。服务端的
// department 查询已负责 scope 与可见性权限，前端不能再按 scope 丢掉全员可见项。
const myFolders = computed(() =>
  folders.value.filter((f) => f.scope === 'personal' && f.isOwner),
);
const sharedFolders = computed(() =>
  folders.value.filter(
    (f) => f.visibility === 'department' || f.visibility === 'organization',
  ),
);

interface FolderNode {
  children: FolderNode[];
  folder: MaterialFolderSummary;
}

interface FolderRow {
  depth: number;
  folder: MaterialFolderSummary;
  hasChildren: boolean;
}

const expandedFolderIds = ref(new Set<string>());
const collapsedSearchFolderIds = ref(new Set<string>());
const searchKeyword = computed(() => keyword.value.trim().toLocaleLowerCase());

function isExpanded(folderId: string) {
  return searchKeyword.value
    ? !collapsedSearchFolderIds.value.has(folderId)
    : expandedFolderIds.value.has(folderId);
}

function setExpanded(folderId: string, expanded: boolean) {
  hideFolderTooltip();
  const ids = searchKeyword.value
    ? collapsedSearchFolderIds.value
    : expandedFolderIds.value;
  if (searchKeyword.value ? !expanded : expanded) ids.add(folderId);
  else ids.delete(folderId);
}

/** 按父级 ID 建树；无可见父级的共享目录仍作为入口展示，不丢失访问权限。 */
function buildFolderRows(list: MaterialFolderSummary[]): FolderRow[] {
  const nodes = new Map<string, FolderNode>(
    list.map((folder) => [folder.id, { children: [], folder }]),
  );
  const roots: FolderNode[] = [];
  for (const node of nodes.values()) {
    const parent = nodes.get(node.folder.parentId ?? '');
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }

  // 搜索子目录时保留祖先路径，并默认展开；清空搜索后恢复原有展开状态。
  const filterNodes = (items: FolderNode[]): FolderNode[] =>
    items.flatMap((node) => {
      const children = filterNodes(node.children);
      return children.length ||
        node.folder.name.toLocaleLowerCase().includes(searchKeyword.value)
        ? [{ ...node, children }]
        : [];
    });
  const rows: FolderRow[] = [];
  const appendRows = (items: FolderNode[], depth: number) => {
    for (const node of items) {
      rows.push({
        depth,
        folder: node.folder,
        hasChildren: node.children.length > 0,
      });
      if (isExpanded(node.folder.id)) appendRows(node.children, depth + 1);
    }
  };
  appendRows(searchKeyword.value ? filterNodes(roots) : roots, 0);
  return rows;
}

const myFolderRows = computed(() => buildFolderRows(myFolders.value));
const sharedFolderRows = computed(() => buildFolderRows(sharedFolders.value));

watch(searchKeyword, () => collapsedSearchFolderIds.value.clear());

// 外部选中子目录或重新打开弹窗时，展开其祖先，让当前目标始终可见。
watch([folders, () => props.modelValue.folderId], () => {
  if (props.modelValue.type !== 'folder') return;
  const byId = new Map(folders.value.map((folder) => [folder.id, folder]));
  const visited = new Set<string>();
  let parentId = byId.get(props.modelValue.folderId ?? '')?.parentId;
  while (parentId && !visited.has(parentId)) {
    visited.add(parentId);
    expandedFolderIds.value.add(parentId);
    parentId = byId.get(parentId)?.parentId;
  }
});

function focusAdjacentFolder(event: KeyboardEvent, offset: number) {
  const current = event.currentTarget as HTMLElement;
  const rows = [
    ...(current.parentElement?.querySelectorAll<HTMLElement>(
      '[role="treeitem"]',
    ) ?? []),
  ];
  rows[rows.indexOf(current) + offset]?.focus();
}

const select = (node: TreeSelection) => emit('update:modelValue', node);

const isSelected = (folder: MaterialFolderSummary) =>
  props.modelValue.type === 'folder' && props.modelValue.folderId === folder.id;

const selectFolder = (folder: MaterialFolderSummary) =>
  select({ type: 'folder', folderId: folder.id, folderName: folder.name });

async function handleFolderCreated(
  folder: Pick<MaterialFolderSummary, 'id' | 'name' | 'parentId'>,
) {
  keyword.value = '';
  if (folder.parentId) expandedFolderIds.value.add(folder.parentId);
  select({ type: 'folder', folderId: folder.id, folderName: folder.name });
  try {
    await loadFolders();
  } catch {
    message.warning('文件夹已创建，目录刷新失败，请点击刷新重试');
  }
}

const VISIBILITY_ICON: Record<string, string> = {
  organization: 'icon-[lucide--globe] text-sky-500',
  department: 'icon-[lucide--users] text-emerald-500',
  private: 'icon-[lucide--lock] text-amber-500',
};

const VISIBILITY_LABEL: Record<string, string> = {
  organization: '全员可见',
  department: '本部门可见',
  private: '仅自己',
};

onMounted(() => {
  loadFolders();
});

const folderTooltip = ref({ visible: false, text: '', top: 0, left: 0 });

function showFolderTooltip(event: MouseEvent, name: string) {
  const wrapper = event.currentTarget as HTMLElement;
  const textEl = wrapper.querySelector<HTMLElement>('.truncate') ?? wrapper;
  if (textEl.scrollWidth <= textEl.clientWidth) return;
  const rect = textEl.getBoundingClientRect();
  folderTooltip.value = {
    visible: true,
    text: name,
    top: rect.bottom + 4,
    left: rect.left,
  };
}

function hideFolderTooltip() {
  folderTooltip.value.visible = false;
}

defineExpose({ reload: loadFolders, folders });
</script>

<template>
  <div
    class="flex min-h-0 flex-col"
    :class="autoHeight ? 'folder-tree-auto-height' : 'h-full'"
  >
    <div class="flex-shrink-0 px-2 pb-1">
      <div class="bg-border h-px w-full"></div>
    </div>

    <div class="flex min-h-0 flex-1 flex-col text-sm">
      <!-- 成效视图 -->
      <div v-if="showEffectiveness !== false" class="order-4 pt-1">
        <div
          class="flex cursor-pointer items-center rounded px-2 py-1 pl-4 hover:bg-gray-100"
          :class="{
            'bg-blue-100 font-medium text-blue-700':
              modelValue.type === 'effectiveness',
          }"
          @click="select({ type: 'effectiveness' })"
        >
          <span class="truncate">成效视图</span>
        </div>
      </div>

      <!-- 项目素材：沿用 all selection，避免影响现有查询参数 -->
      <div v-if="showLibrary !== false" class="order-2 pt-1">
        <div
          class="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-500"
        >
          <span
            class="icon-[lucide--folder-kanban] text-sm text-blue-500"
          ></span>
          <span>项目文件夹</span>
        </div>
        <div
          class="flex cursor-pointer items-center rounded px-2 py-1.5 pl-6 hover:bg-gray-100"
          :class="{
            'bg-blue-100 font-medium text-blue-700': modelValue.type === 'all',
          }"
          @click="select({ type: 'all' })"
        >
          <span class="truncate">全部项目素材</span>
        </div>
      </div>

      <!-- 部门素材：沿用 common selection，避免影响现有查询参数 -->
      <div v-if="showLibrary !== false" class="order-3 pt-1">
        <div
          class="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-500"
        >
          <span
            class="icon-[lucide--building-2] text-sm text-emerald-500"
          ></span>
          <span>部门素材</span>
        </div>
        <div
          class="flex cursor-pointer items-center rounded px-2 py-1.5 pl-6 hover:bg-gray-100"
          :class="{
            'bg-blue-100 font-medium text-blue-700':
              modelValue.type === 'common',
          }"
          @click="select({ type: 'common' })"
        >
          <span class="truncate">部门共享素材</span>
        </div>
      </div>

      <!-- 我的文件夹 -->
      <div
        class="folder-tree-personal order-1 flex min-h-0 flex-1 flex-col pt-1"
      >
        <div class="flex items-center justify-between px-2 py-1">
          <span
            class="flex items-center gap-1.5 text-xs font-medium text-gray-500"
          >
            <span
              class="icon-[lucide--user-round] text-sm text-violet-500"
            ></span>
            <span>我的文件夹</span>
          </span>
          <div class="flex items-center gap-1">
            <span
              class="flex h-4 w-4 cursor-pointer items-center rounded text-gray-400 transition-colors hover:bg-gray-100"
              title="刷新"
              @click="loadFolders"
            >
              <span class="icon-[ant-design--reload-outlined]"></span>
            </span>
            <MaterialFolderCreatePopover
              v-if="allowCreate"
              :disabled="folderLoading"
              @created="handleFolderCreated"
            />
            <slot name="folder-header-actions"></slot>
          </div>
        </div>

        <div class="px-2 pb-1">
          <Input
            v-model:value="keyword"
            allow-clear
            placeholder="搜索文件夹"
            aria-label="搜索文件夹"
          >
            <template #prefix>
              <span class="icon-[lucide--search] text-xs text-gray-400"></span>
            </template>
          </Input>
        </div>

        <div
          class="min-h-0 flex-1 overflow-y-auto"
          role="tree"
          aria-label="我的文件夹"
        >
          <div
            v-for="{ folder, depth, hasChildren } in myFolderRows"
            :key="folder.id"
            class="focus-visible:outline-primary group flex cursor-pointer items-center justify-between rounded px-2 py-1.5 hover:bg-gray-100 focus-visible:outline focus-visible:outline-2"
            :class="{
              'bg-blue-100 font-medium text-blue-700': isSelected(folder),
            }"
            :style="{ paddingLeft: `${8 + depth * 16}px` }"
            role="treeitem"
            tabindex="0"
            :aria-label="folder.name"
            :aria-level="depth + 1"
            :aria-selected="isSelected(folder)"
            :aria-expanded="hasChildren ? isExpanded(folder.id) : undefined"
            @click="selectFolder(folder)"
            @keydown.enter.self.prevent="selectFolder(folder)"
            @keydown.space.self.prevent="selectFolder(folder)"
            @keydown.right.self.prevent="
              hasChildren && setExpanded(folder.id, true)
            "
            @keydown.left.self.prevent="setExpanded(folder.id, false)"
            @keydown.down.self.prevent="focusAdjacentFolder($event, 1)"
            @keydown.up.self.prevent="focusAdjacentFolder($event, -1)"
          >
            <button
              v-if="hasChildren"
              type="button"
              class="focus-visible:outline-primary mr-1 flex h-4 w-4 flex-shrink-0 cursor-pointer items-center justify-center rounded text-gray-500 focus-visible:outline focus-visible:outline-2"
              :aria-label="`${isExpanded(folder.id) ? '收起' : '展开'} ${folder.name}`"
              :aria-expanded="isExpanded(folder.id)"
              @click.stop="setExpanded(folder.id, !isExpanded(folder.id))"
            >
              <span
                class="icon-[ant-design--caret-right-filled] text-xs"
                :class="{ 'rotate-90': isExpanded(folder.id) }"
                aria-hidden="true"
              ></span>
            </button>
            <span
              v-else
              class="mr-1 h-4 w-4 flex-shrink-0"
              aria-hidden="true"
            ></span>
            <div
              class="flex min-w-0 flex-1 items-center gap-1.5"
              @mouseenter="showFolderTooltip($event, folder.name)"
              @mouseleave="hideFolderTooltip"
            >
              <span
                class="flex-shrink-0 text-xs"
                :class="VISIBILITY_ICON[folder.visibility]"
                :title="VISIBILITY_LABEL[folder.visibility]"
              ></span>
              <slot name="folder-name" :folder="folder">
                <span class="truncate">{{ folder.name }}</span>
              </slot>
            </div>
            <MaterialFolderCreatePopover
              v-if="allowCreate && folder.isOwner"
              class="ml-1"
              :folder="folder"
              :parent-folder="foldersById.get(folder.parentId ?? '')"
              :disabled="folderLoading"
              @created="handleFolderCreated"
            />
            <slot name="folder-actions" :folder="folder"></slot>
          </div>

          <div
            v-if="myFolderRows.length === 0 && !folderLoading"
            class="px-4 py-2 text-xs text-gray-400"
          >
            {{ keyword ? '没有匹配的文件夹' : '暂无文件夹' }}
          </div>
        </div>
      </div>

      <!-- 共享文件夹：当前部门内创建且仅本部门可见的文件夹 -->
      <div
        v-if="sharedFolderRows.length > 0"
        class="folder-tree-shared order-5 flex min-h-0 flex-1 flex-col pt-1"
      >
        <div
          class="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-500"
        >
          <span
            class="icon-[lucide--users-round] text-sm text-amber-500"
          ></span>
          <span>共享文件夹</span>
        </div>
        <div
          class="min-h-0 flex-1 overflow-y-auto"
          role="tree"
          aria-label="共享文件夹"
        >
          <div
            v-for="{ folder, depth, hasChildren } in sharedFolderRows"
            :key="folder.id"
            class="focus-visible:outline-primary flex cursor-pointer items-center justify-between rounded px-2 py-1.5 hover:bg-gray-100 focus-visible:outline focus-visible:outline-2"
            :class="{
              'bg-blue-100 font-medium text-blue-700': isSelected(folder),
            }"
            :style="{ paddingLeft: `${8 + depth * 16}px` }"
            role="treeitem"
            tabindex="0"
            :aria-label="folder.name"
            :aria-level="depth + 1"
            :aria-selected="isSelected(folder)"
            :aria-expanded="hasChildren ? isExpanded(folder.id) : undefined"
            @click="selectFolder(folder)"
            @keydown.enter.self.prevent="selectFolder(folder)"
            @keydown.space.self.prevent="selectFolder(folder)"
            @keydown.right.self.prevent="
              hasChildren && setExpanded(folder.id, true)
            "
            @keydown.left.self.prevent="setExpanded(folder.id, false)"
            @keydown.down.self.prevent="focusAdjacentFolder($event, 1)"
            @keydown.up.self.prevent="focusAdjacentFolder($event, -1)"
          >
            <button
              v-if="hasChildren"
              type="button"
              class="focus-visible:outline-primary mr-1 flex h-4 w-4 flex-shrink-0 cursor-pointer items-center justify-center rounded text-gray-500 focus-visible:outline focus-visible:outline-2"
              :aria-label="`${isExpanded(folder.id) ? '收起' : '展开'} ${folder.name}`"
              :aria-expanded="isExpanded(folder.id)"
              @click.stop="setExpanded(folder.id, !isExpanded(folder.id))"
            >
              <span
                class="icon-[ant-design--caret-right-filled] text-xs"
                :class="{ 'rotate-90': isExpanded(folder.id) }"
                aria-hidden="true"
              ></span>
            </button>
            <span
              v-else
              class="mr-1 h-4 w-4 flex-shrink-0"
              aria-hidden="true"
            ></span>
            <div
              class="flex min-w-0 flex-1 items-center gap-1.5"
              @mouseenter="showFolderTooltip($event, folder.name)"
              @mouseleave="hideFolderTooltip"
            >
              <span
                class="flex-shrink-0 text-xs"
                :class="VISIBILITY_ICON[folder.visibility]"
                :title="VISIBILITY_LABEL[folder.visibility]"
              ></span>
              <span class="truncate">{{ folder.name }}</span>
            </div>
            <MaterialFolderCreatePopover
              v-if="allowCreate && folder.isOwner"
              class="ml-1"
              :folder="folder"
              :parent-folder="foldersById.get(folder.parentId ?? '')"
              :disabled="folderLoading"
              @created="handleFolderCreated"
            />
            <span
              v-if="!folder.isOwner && folder.owner"
              class="ml-1 flex-shrink-0 truncate text-xs text-gray-400"
            >
              {{ folder.owner }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="folderTooltip.visible"
        class="pointer-events-none fixed z-[9999]"
        :style="{
          top: `${folderTooltip.top}px`,
          left: `${folderTooltip.left}px`,
        }"
      >
        <div
          class="ml-2.5 h-0 w-0 border-x-4 border-b-[6px] border-x-transparent border-b-[rgba(0,0,0,0.85)]"
        ></div>
        <div
          class="max-w-xs break-words rounded-md bg-[rgba(0,0,0,0.85)] px-2 py-1.5 text-sm leading-[1.5714] text-white shadow-[0_6px_16px_0_rgba(0,0,0,0.08),0_3px_6px_-4px_rgba(0,0,0,0.12),0_9px_28px_8px_rgba(0,0,0,0.05)]"
        >
          {{ folderTooltip.text }}
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* 弹窗内两组按实际内容排布，展开增加高度，收起立即回收空白。 */
.folder-tree-auto-height .folder-tree-personal,
.folder-tree-auto-height .folder-tree-shared {
  flex: none;
}

/* 每行约 32px：个人目录最多展示 8 行，共享目录最多展示 5 行。 */
.folder-tree-auto-height .folder-tree-personal [role='tree'] {
  flex: none;
  max-height: 256px;
}

.folder-tree-auto-height .folder-tree-shared [role='tree'] {
  flex: none;
  max-height: 160px;
}
</style>
