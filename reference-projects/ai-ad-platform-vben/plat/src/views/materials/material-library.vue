<script lang="ts" setup>
import type { Ref } from 'vue';

import type {
  MaterialFolderInput,
  MaterialFolderPatch,
  MaterialFolderQuery,
  MaterialFolderScope,
  MaterialFolderSummary,
  MaterialFolderVisibility,
  MaterialLibraryFolderItem,
  MaterialLibraryFolderPage,
} from '#/domain/material';

import { computed, markRaw, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccessStore, useUserStore } from '@vben/stores';
import {
  Button,
  Input,
  message,
  Modal,
  Pagination,
  Popconfirm,
  Popover,
  Select,
  Switch,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenForm } from '#/adapter/form';
import {
  batchDeleteCommonMaterialsApi,
  batchDeleteMaterials,
  batchUpdateMaterials,
  deleteFolderMaterialsApi,
  downloadCommonFilesAsZip,
  downloadFilesAsZip,
  downloadFilesAsZipNamed,
  getAnalysisDescApi,
  getMaterialUrlApi,
  listCommonMaterialsApi,
  listMaterialApi,
  publishMaterialsApi,
} from '#/api';
import { getUserOptions } from '#/api/system/user';
import {
  httpFolderService,
  httpMaterialLibraryService,
} from '#/domain/material';
import {
  MAX_MATERIAL_FILTER_NAMES,
  parseMaterialNames,
} from '#/domain/material/name-filter';
import {
  createMaterialPageRequestCache,
  MATERIAL_PAGE_CACHE_TTL,
} from '#/domain/material/page-request-cache';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import MaterialCard from '#/views/components/MaterialCard.vue';
import PlatformSelect from '#/views/components/PlatformSelect.vue';
import PushMaterialModal from '#/views/components/PushMaterialModal.vue';

import MaterialCloudHome from './components/MaterialCloudHome.vue';
import MaterialFolderTree from './components/MaterialFolderTree.vue';
import MaterialNameFilter from './components/MaterialNameFilter.vue';
import TagComboSelect from './components/TagComboSelect.vue';
import UploadMaterialModal from './components/UploadMaterialModal.vue';

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const accessStore = useAccessStore();
// 当前账号、部门和权限变化时切换缓存上下文，禁止复用其他会话的数据。
const materialCacheContext = computed(() =>
  JSON.stringify([
    userStore.userInfo,
    accessStore.accessCodes,
    accessStore.accessToken,
    accessStore.loginExpired,
  ]),
);

let materialLibraryMounted = false;

type DriveView = 'home' | 'personal' | 'project' | 'shared';

const driveView = ref<DriveView>('home');
const activeDriveFolder = ref<MaterialFolderSummary | null>(null);
const activeFolderTrail = ref<{ id: string; name: string }[]>([]);
const childFolders = ref<MaterialFolderSummary[]>([]);
const childFoldersLoading = ref(false);
const childFolderLoadSequence = ref(0);
const childFolderModalOpen = ref(false);
const childFolderName = ref('');
const childFolderSubmitting = ref(false);

type FolderHomeTab = 'personal' | 'recent' | 'shared';

// 文件夹接口按空间精确请求，避免发出不带筛选条件的全量请求。
const folderHomeTab = ref<FolderHomeTab>('recent');
const folderHomeLoading = ref(false);
const folderKeyword = ref('');
const materialNamesText = ref('');
const appliedMaterialNames = ref(parseMaterialNames(materialNamesText.value));
const searchingFolders = computed(() =>
  Boolean(folderKeyword.value || appliedMaterialNames.value.length),
);
const personalDriveFolders = ref<MaterialFolderSummary[]>([]);
const departmentDriveFolders = ref<MaterialFolderSummary[]>([]);
const recentDriveFolders = ref<MaterialFolderSummary[]>([]);
const folderLoadSequence = ref(0);
const folderRequests = createMaterialPageRequestCache<
  readonly MaterialFolderSummary[]
>({ maxEntries: 32 });
const materialRequests =
  createMaterialPageRequestCache<MaterialLibraryFolderPage>({
    maxEntries: 4,
    // 素材摘要包含缩略图；同时约束页数和估算内存，避免长时间浏览囤积图片。
    maxBytes: 16 * 1024 * 1024,
    sizeOf: (page) =>
      page.items.reduce(
        (bytes, item) =>
          bytes +
          1024 +
          (typeof item.legacy.img === 'string'
            ? item.legacy.img.length * 2
            : 0),
        0,
      ),
  });
const localFolderVisits = new Map<string, string>();
const visitedFolderSummaries = new Map<
  string,
  { folder: MaterialFolderSummary; expiresAt: number }
>();

const currentFolderOwner = computed(() => {
  const user = userStore.userInfo as Record<string, unknown> | undefined;
  const candidate = user?.full_name ?? user?.realName ?? user?.real_name;
  return typeof candidate === 'string' ? candidate.trim() : '';
});

const knownDriveFolders = computed(() => {
  const foldersById = new Map<string, MaterialFolderSummary>();
  [...personalDriveFolders.value, ...departmentDriveFolders.value].forEach(
    (folder) => foldersById.set(folder.id, folder),
  );
  return [...foldersById.values()];
});

const activeFolderPath = computed(() =>
  activeFolderTrail.value.map((folder) => folder.name).join(' / '),
);

const canCreateChildFolder = computed(
  () =>
    activeDriveFolder.value?.isOwner === true &&
    activeDriveFolder.value.level < 2,
);

const folderContentsLoading = computed(
  () => cardLoading.value || childFoldersLoading.value,
);

function folderQuery(scope: MaterialFolderScope) {
  return {
    scope,
    ...(scope === 'personal' && currentFolderOwner.value
      ? { owner: currentFolderOwner.value }
      : {}),
    ...(folderKeyword.value ? { keyword: folderKeyword.value } : {}),
    ...(appliedMaterialNames.value.length
      ? { basenames: appliedMaterialNames.value }
      : {}),
  };
}

function loadCachedFolders(query: MaterialFolderQuery = {}) {
  const key = JSON.stringify([
    materialCacheContext.value,
    query.scope ?? '',
    query.owner ?? '',
    query.keyword ?? '',
    query.parentId ?? '',
    query.folderId ?? '',
    [...(query.basenames ?? [])].sort(),
  ]);
  return folderRequests
    .get(key, () => httpFolderService.list(query))
    .then((folders) =>
      folders.map((folder) => {
        const visitedAt = localFolderVisits.get(folder.id);
        return visitedAt &&
          (!folder.lastVisitedAt ||
            Date.parse(visitedAt) > Date.parse(folder.lastVisitedAt))
          ? { ...folder, lastVisitedAt: visitedAt }
          : folder;
      }),
    );
}

function loadFoldersForScope(scope: MaterialFolderScope) {
  return loadCachedFolders(folderQuery(scope));
}

function clearFolderScopeCache() {
  folderRequests.clear();
  materialRequests.clear();
  visitedFolderSummaries.clear();
  // 已失效请求仍可能返回，序号阻止它覆盖刚修改过的列表。
  folderLoadSequence.value += 1;
  childFolderLoadSequence.value += 1;
  fetchSeq.value += 1;
  folderHomeLoading.value = false;
  childFoldersLoading.value = false;
  cardLoading.value = false;
}

function personalFolders(folders: readonly MaterialFolderSummary[]) {
  // owner 已由接口精确筛选；用户信息尚未就绪时再用服务端回传的归属标记兜底。
  const ownedFolders = currentFolderOwner.value
    ? [...folders]
    : folders.filter((folder) => folder.isOwner);
  return ownedFolders.filter(
    (folder) => searchingFolders.value || !folder.parentId,
  );
}

function sharedFolders(folders: readonly MaterialFolderSummary[]) {
  return folders.filter(
    (folder) =>
      (folder.visibility === 'department' ||
        folder.visibility === 'organization') &&
      (searchingFolders.value || !folder.parentId),
  );
}

function recentFolders(
  personal: readonly MaterialFolderSummary[],
  shared: readonly MaterialFolderSummary[],
) {
  const foldersById = new Map<string, MaterialFolderSummary>();
  [...personal, ...shared].forEach((folder) =>
    foldersById.set(folder.id, folder),
  );
  return [...foldersById.values()]
    .filter((folder) => searchingFolders.value || Boolean(folder.lastVisitedAt))
    .sort((left, right) =>
      (right.lastVisitedAt ?? '').localeCompare(left.lastVisitedAt ?? ''),
    );
}

function syncActiveDriveFolder(
  folders: readonly MaterialFolderSummary[] = knownDriveFolders.value,
) {
  if (!activeDriveFolder.value) return;
  const fresh = folders.find(
    (folder) => folder.id === activeDriveFolder.value?.id,
  );
  if (fresh) activeDriveFolder.value = fresh;
}

function clearChildFolders() {
  // 请求无法中断时以序号丢弃过期结果，避免返回首页后又闪出旧目录。
  childFolderLoadSequence.value += 1;
  childFolders.value = [];
  childFoldersLoading.value = false;
}

async function loadChildFolders(folder: MaterialFolderSummary) {
  const requestSequence = ++childFolderLoadSequence.value;
  childFoldersLoading.value = true;
  try {
    const folders = await loadCachedFolders({
      parentId: folder.id,
      scope: folder.scope,
      basenames: appliedMaterialNames.value,
    });
    if (
      requestSequence !== childFolderLoadSequence.value ||
      activeDriveFolder.value?.id !== folder.id
    ) {
      return;
    }
    childFolders.value = [...folders];
  } finally {
    if (requestSequence === childFolderLoadSequence.value) {
      childFoldersLoading.value = false;
    }
  }
}

function recordFolderVisit(folderId: string) {
  const context = materialCacheContext.value;
  // 访问记录单独写入；更新本地访问时间，不使目录/素材查询缓存失效。
  httpFolderService
    .recordVisit(folderId)
    .then(() => {
      if (context !== materialCacheContext.value) return;
      const lastVisitedAt = new Date().toISOString();
      localFolderVisits.set(folderId, lastVisitedAt);
      const updateVisitedAt = (folders: MaterialFolderSummary[]) =>
        folders.map((folder) =>
          folder.id === folderId ? { ...folder, lastVisitedAt } : folder,
        );
      personalDriveFolders.value = updateVisitedAt(personalDriveFolders.value);
      departmentDriveFolders.value = updateVisitedAt(
        departmentDriveFolders.value,
      );
      recentDriveFolders.value = recentFolders(
        personalDriveFolders.value,
        departmentDriveFolders.value,
      );
    })
    .catch(() => {});
}

const loadDriveFolders = async (tab: FolderHomeTab = folderHomeTab.value) => {
  const requestSequence = ++folderLoadSequence.value;
  folderHomeLoading.value = true;
  try {
    if (tab === 'recent') {
      const [personal, department] = await Promise.all([
        loadFoldersForScope('personal'),
        loadFoldersForScope('department'),
      ]);
      if (requestSequence !== folderLoadSequence.value) return;
      personalDriveFolders.value = personalFolders(personal);
      departmentDriveFolders.value = sharedFolders(department);
      recentDriveFolders.value = recentFolders(
        personalDriveFolders.value,
        departmentDriveFolders.value,
      );
    } else if (tab === 'personal') {
      const folders = await loadFoldersForScope('personal');
      if (requestSequence !== folderLoadSequence.value) return;
      personalDriveFolders.value = personalFolders(folders);
    } else {
      const folders = await loadFoldersForScope('department');
      if (requestSequence !== folderLoadSequence.value) return;
      departmentDriveFolders.value = sharedFolders(folders);
    }
    syncActiveDriveFolder();
  } finally {
    if (requestSequence === folderLoadSequence.value) {
      folderHomeLoading.value = false;
    }
  }
};

function applyMaterialNames(text: string) {
  const names = parseMaterialNames(text);
  if (names.length > MAX_MATERIAL_FILTER_NAMES) {
    message.warning(`最多筛选 ${MAX_MATERIAL_FILTER_NAMES} 个素材名称`);
    return false;
  }
  appliedMaterialNames.value = names;
  materialNamesText.value = names.join('\n');
  // 名称组合本身是缓存键，切回相同条件时仍可复用。
  return true;
}

function syncMaterialSearchQuery() {
  return router.replace({
    query: {
      ...route.query,
      basename: appliedMaterialNames.value.length
        ? appliedMaterialNames.value
        : undefined,
      folder_keyword: folderKeyword.value || undefined,
    },
  });
}

const searchDriveFolders = async (filters: {
  keyword: string;
  materialNamesText: string;
}) => {
  if (!applyMaterialNames(filters.materialNamesText)) return;
  folderKeyword.value = filters.keyword;
  await syncMaterialSearchQuery();
  await loadDriveFolders();
};

async function searchFolderMaterials() {
  if (!isCommonLib.value) {
    if (!applyMaterialNames(materialNamesText.value)) return;
    await syncMaterialSearchQuery();
    if (activeDriveFolder.value) void loadChildFolders(activeDriveFolder.value);
  }
  page.value = 1;
  await fetchMaterials(true);
}

async function resetFolderMaterialFilters() {
  commonFolderBasename.value = '';
  commonFolderFiletype.value = undefined;
  if (!isCommonLib.value) materialNamesText.value = '';
  dateRange.value = [
    toLocalDayStart(dayjs.tz().subtract(29, 'day')),
    dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
  ];
  await searchFolderMaterials();
}

const changeFolderHomeTab = async (tab: FolderHomeTab) => {
  folderHomeTab.value = tab;
  await loadDriveFolders(tab);
};

const folderVisibilityLabel: Record<MaterialFolderVisibility, string> = {
  organization: '全员可见',
  department: '本部门可见',
  private: '仅自己',
};
// ---------------- 最左侧：文件夹列表 ----------------
const treeRef = ref<InstanceType<typeof MaterialFolderTree> | null>(null);

interface TreeSelection {
  folderId?: string;
  folderName?: string;
  type: 'all' | 'common' | 'effectiveness' | 'folder';
}

const folderEditingId = ref('');
const folderEditValue = ref('');
const folderDeletingId = ref('');
const publishLoading = ref(false);
// null = 所有素材，string = 个人文件夹 id
// tab query: 'all' | 'common' | <folderId>
const initialTab = route.query.tab as string | undefined;
const selectedFolderId = ref<null | string>(
  initialTab && initialTab !== 'all' && initialTab !== 'common'
    ? initialTab
    : null,
);

// 公共素材库
const isCommonLib = ref(initialTab === 'common');
const commonUploadVisible = ref(false);

if (initialTab === 'common') {
  driveView.value = 'shared';
} else if (initialTab === 'all') {
  driveView.value = 'project';
} else if (initialTab) {
  driveView.value = 'personal';
}

const reloadFolders = async () => {
  clearFolderScopeCache();
  await Promise.all([
    treeRef.value?.reload(),
    loadDriveFolders(folderHomeTab.value),
  ]);
};

// 侧栏建的是个人空间、仅自己可见的文件夹；要建共享文件夹走首页那个带表单的入口
const addFolder = async () => {
  const existingNames = new Set(knownDriveFolders.value.map((f) => f.name));
  let name = '新建文件夹';
  let i = 1;
  while (existingNames.has(name)) {
    name = `新建文件夹${i++}`;
  }

  await httpFolderService.create({
    name,
    scope: 'personal',
    visibility: 'private',
  });
  message.success('创建成功');
  await reloadFolders();
};

const saveRenameFolder = async (id: string) => {
  const name = folderEditValue.value.trim();
  folderEditingId.value = '';
  folderEditValue.value = '';
  if (!name) return;
  await httpFolderService.update(id, { name });
  message.success('重命名成功');
  await reloadFolders();
};

const removeFolder = async (id: string) => {
  await httpFolderService.delete(id);
  folderDeletingId.value = '';
  if (selectedFolderId.value === id) {
    selectedFolderId.value = null;
  }
  if (activeDriveFolder.value?.id === id) {
    activeDriveFolder.value = null;
    driveView.value = 'home';
  }
  message.success('删除成功');
  await reloadFolders();
};

const selectFolder = (fid: null | string) => {
  isCommonLib.value = false;
  selectedFolderId.value = fid;
  driveView.value = fid === null ? 'project' : 'personal';
  if (fid === null) {
    activeDriveFolder.value = null;
    activeFolderTrail.value = [];
    clearChildFolders();
  }
  page.value = 1;
  if (fid !== null) {
    commonFolderBasename.value = '';
    commonFolderFiletype.value = undefined;
  }
  router.replace({ query: { ...route.query, tab: fid ?? 'all' } });
  fetchMaterials(true);
};

const selectCommonLib = () => {
  isCommonLib.value = true;
  selectedFolderId.value = null;
  activeDriveFolder.value = null;
  activeFolderTrail.value = [];
  clearChildFolders();
  driveView.value = 'shared';
  commonFolderBasename.value = '';
  commonFolderFiletype.value = undefined;
  page.value = 1;
  router.replace({ query: { ...route.query, tab: 'common' } });
  fetchMaterials(true);
};

function openDriveFolder(folder: MaterialFolderSummary) {
  // 返回上级可直接使用刚打开过的目录摘要，避免另发定位请求。
  visitedFolderSummaries.delete(folder.id);
  visitedFolderSummaries.set(folder.id, {
    folder,
    expiresAt: Date.now() + MATERIAL_PAGE_CACHE_TTL,
  });
  if (visitedFolderSummaries.size > 32) {
    const oldest = visitedFolderSummaries.keys().next().value;
    if (oldest) visitedFolderSummaries.delete(oldest);
  }
  recordFolderVisit(folder.id);
  activeDriveFolder.value = folder;
  // 搜索可直接命中任意层级；路径由后端按 parent_id 和可见权限生成。
  activeFolderTrail.value = folder.path?.length ? [...folder.path] : [folder];
  materialNamesText.value = appliedMaterialNames.value.join('\n');
  isCommonLib.value = false;
  page.value = 1;
  commonFolderBasename.value = '';
  commonFolderFiletype.value = undefined;

  selectedFolderId.value = folder.id;
  driveView.value = 'personal';
  router.replace({ query: { ...route.query, tab: folder.id } });
  void loadChildFolders(folder);
  fetchMaterials(true);
}

async function createDriveFolder(input: MaterialFolderInput) {
  await httpFolderService.create(input);
  message.success('文件夹已创建');
  await reloadFolders();
}

function openChildFolderModal() {
  if (!canCreateChildFolder.value) return;
  childFolderName.value = '';
  childFolderModalOpen.value = true;
}

async function createChildFolder() {
  const parent = activeDriveFolder.value;
  const name = childFolderName.value.trim();
  if (!parent || !canCreateChildFolder.value || !name) return;

  childFolderSubmitting.value = true;
  try {
    await httpFolderService.create({
      name,
      parentId: parent.id,
      // 服务端会以父目录为准继承这两个字段；这里保留完整输入类型。
      scope: parent.scope,
      visibility: parent.visibility,
    });
    childFolderModalOpen.value = false;
    message.success('子文件夹已创建');
    await reloadFolders();
    await loadChildFolders(parent);
  } finally {
    childFolderSubmitting.value = false;
  }
}

async function updateDriveFolder(folderId: string, patch: MaterialFolderPatch) {
  await httpFolderService.update(folderId, patch);
  message.success('文件夹设置已更新');
  await reloadFolders();
}

async function deleteDriveFolder(folder: MaterialFolderSummary) {
  await httpFolderService.delete(folder.id);
  if (activeDriveFolder.value?.id === folder.id) resetDriveHome();
  message.success(`已删除「${folder.name}」`);
  await reloadFolders();
}

function resetDriveHome() {
  activeDriveFolder.value = null;
  activeFolderTrail.value = [];
  clearChildFolders();
  selectedFolderId.value = null;
  isCommonLib.value = false;
  driveView.value = 'home';
  fetchSeq.value += 1;
  cardLoading.value = false;
  clearSelection();
  router.replace({
    query: Object.fromEntries(
      Object.entries(route.query).filter(([key]) => key !== 'tab'),
    ),
  });
}

const openDriveHome = () => {
  resetDriveHome();
  void loadDriveFolders();
};

async function openParentDriveFolder() {
  const parent = activeFolderTrail.value.at(-2);
  if (!parent) {
    openDriveHome();
    return;
  }
  const cached = visitedFolderSummaries.get(parent.id);
  const folder =
    cached && cached.expiresAt > Date.now()
      ? cached.folder
      : (await loadCachedFolders({ folderId: parent.id }))[0];
  if (folder) openDriveFolder(folder);
}

function folderDisplayColor(folder: MaterialFolderSummary): string {
  return folder.color || '#1677ff';
}

// 文件夹树组件的双向绑定状态
const selectedNode = computed<TreeSelection>({
  get() {
    if (isCommonLib.value) return { type: 'common' };
    if (selectedFolderId.value)
      return { type: 'folder', folderId: selectedFolderId.value };
    return { type: 'all' };
  },
  set(node) {
    if (node.type === 'common') {
      selectCommonLib();
    } else if (node.type === 'folder' && node.folderId) {
      selectFolder(node.folderId);
    } else {
      selectFolder(null);
    }
  },
});

const publishMaterials = async () => {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择素材');
    return;
  }
  publishLoading.value = true;
  try {
    await publishMaterialsApi(
      selectedFolderId.value!,
      [...selectedMap.value.values()].map((v) => v.basename),
    );
    message.success(`已将 ${selectedMap.value.size} 个素材公开到所有素材`);
    await refreshMaterialLibrary();
  } finally {
    publishLoading.value = false;
  }
};

// ---------------- 右侧：图片卡片列表 ----------------
interface FileResponse {
  ad_name?: string;
  analysis_description?: string;
  basename: string;
  category: string;
  country: string;
  created_at: string;
  creative_editor: string;
  file_md5: string;
  filename: string;
  filetype: string;
  game_platform: string;
  id: string;
  img: string;
  sha3_256: string;
  tag_description?: Record<string, any>;
  tags: string[];
  tags_len: number;
  tags_new: string[];
  tags_titles: string[];
  tags_tree?: Array<{
    children: any[];
    key: string;
    title: string;
  }>;
  total_spent?: number;
  updated_at: string;
  user: string;
}

/**
 * The legacy folder-material route still owns card display fields. The domain
 * adapter validates the stable ID; this bridge preserves all existing card
 * fields until the backend publishes a formal Material list contract.
 */
function toFileResponse(item: MaterialLibraryFolderItem): FileResponse {
  return { ...item.legacy, id: item.id } as FileResponse;
}

const cardLoading = ref(false);
const materials = ref<FileResponse[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(100);
const fetchSeq = ref(0); // 请求序列号，用于丢弃过期请求结果
const routeStateReady = ref(false);

const selectedMap = ref<Map<string, { basename: string; filename: string }>>(
  new Map(),
);

// 预览模式状态
const isPreviewMode = ref(false); // 默认为预览模式

// 公共素材库/个人文件夹 筛选状态
const commonFolderBasename = ref('');
const commonFolderFiletype = ref<string | undefined>(undefined);

// 日期选择器相关状态 - 使用时间戳
const toLocalDayStart = (d: ReturnType<typeof dayjs.tz>): number =>
  dayjs(d.format('YYYY-MM-DD')).valueOf();

const dateRange = ref<[number, number]>([
  toLocalDayStart(dayjs.tz().subtract(29, 'day')),
  dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
]);

// 框选功能相关状态
const isSelecting = ref(false);
const selectionBox = ref({
  startX: 0,
  startY: 0,
  endX: 0,
  endY: 0,
});
const gridContainer = ref<HTMLElement>();
const selectionStartSelected = ref<Set<string>>(new Set()); // 记录框选开始时的选中状态

// 框选功能
const startSelection = (event: MouseEvent) => {
  // 预览模式下禁用框选
  if (isPreviewMode.value) return;

  // 扩大可框选区域：允许在卡片上也开始框选，但排除交互元素
  const target = event.target as HTMLElement;
  const isInteractiveElement =
    target.tagName === 'INPUT' ||
    target.tagName === 'BUTTON' ||
    target.closest('input') ||
    target.closest('button') ||
    target.closest('.ant-checkbox');

  if (isInteractiveElement) return; // 排除交互元素

  isSelecting.value = true;
  // 记录框选开始时的选中状态
  selectionStartSelected.value = new Set<string>(selectedMap.value.keys());

  const rect = gridContainer.value!.getBoundingClientRect();
  selectionBox.value.startX =
    event.clientX - rect.left + gridContainer.value!.scrollLeft;
  selectionBox.value.startY =
    event.clientY - rect.top + gridContainer.value!.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;

  document.addEventListener('mousemove', updateSelection);
  document.addEventListener('mouseup', endSelection);
  event.preventDefault();
};

const updateSelection = (event: MouseEvent) => {
  if (!isSelecting.value) return;

  const rect = gridContainer.value!.getBoundingClientRect();
  selectionBox.value.endX =
    event.clientX - rect.left + gridContainer.value!.scrollLeft;
  selectionBox.value.endY =
    event.clientY - rect.top + gridContainer.value!.scrollTop;

  // 实时更新选中的卡片
  updateSelectedCards();
};

const endSelection = () => {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
};

const updateSelectedCards = () => {
  if (!gridContainer.value) return;

  const cards = gridContainer.value.querySelectorAll('[data-card-id]');
  const newSelected = new Set<string>(selectionStartSelected.value); // 从初始状态开始

  const selectionRect = {
    left: Math.min(selectionBox.value.startX, selectionBox.value.endX),
    top: Math.min(selectionBox.value.startY, selectionBox.value.endY),
    right: Math.max(selectionBox.value.startX, selectionBox.value.endX),
    bottom: Math.max(selectionBox.value.startY, selectionBox.value.endY),
  };

  // 只有当选择框有一定大小时才进行选择操作
  const minSelectionSize = 5;
  if (
    Math.abs(selectionBox.value.endX - selectionBox.value.startX) <
      minSelectionSize ||
    Math.abs(selectionBox.value.endY - selectionBox.value.startY) <
      minSelectionSize
  ) {
    return;
  }

  cards.forEach((card) => {
    const cardRect = card.getBoundingClientRect();
    const containerRect = gridContainer.value!.getBoundingClientRect();

    const cardRelativeRect = {
      left:
        cardRect.left - containerRect.left + gridContainer.value!.scrollLeft,
      top: cardRect.top - containerRect.top + gridContainer.value!.scrollTop,
      right:
        cardRect.right - containerRect.left + gridContainer.value!.scrollLeft,
      bottom:
        cardRect.bottom - containerRect.top + gridContainer.value!.scrollTop,
    };

    // 检查卡片是否与选择框相交
    const isIntersecting = !(
      cardRelativeRect.right < selectionRect.left ||
      cardRelativeRect.left > selectionRect.right ||
      cardRelativeRect.bottom < selectionRect.top ||
      cardRelativeRect.top > selectionRect.bottom
    );

    const cardId = (card as HTMLElement).dataset.cardId!;
    if (isIntersecting) {
      // 如果卡片在框选区域内
      if (selectionStartSelected.value.has(cardId)) {
        // 如果原本已选中，则取消选择
        newSelected.delete(cardId);
      } else {
        // 如果原本未选中，则添加选择
        newSelected.add(cardId);
      }
    }
  });

  // 重建selectedMap
  materials.value.forEach((m) => {
    if (newSelected.has(m.id)) {
      selectedMap.value.set(m.id, {
        basename: m.basename,
        filename: m.filename,
      });
    } else {
      selectedMap.value.delete(m.id);
    }
  });
};

const fetchMaterials = async (clearSelect = false) => {
  await commitQueryState();
  const currentSeq = ++fetchSeq.value;
  try {
    cardLoading.value = true;
    if (clearSelect) clearSelection();

    let items: FileResponse[] = [];
    let totalCount = 0;

    if (isCommonLib.value) {
      const res = await listCommonMaterialsApi({
        page: page.value,
        page_size: pageSize.value,
        filetype: commonFolderFiletype.value || undefined,
        basename: commonFolderBasename.value || undefined,
      });
      items = res.items || [];
      totalCount = res.total ?? items.length;
    } else if (selectedFolderId.value === null) {
      const params = { ...allSearchFormValues.value };
      const effectiveRange = params.created_at_range || allCreatedAtRange.value;
      if (
        effectiveRange &&
        Array.isArray(effectiveRange) &&
        effectiveRange.length === 2 &&
        typeof effectiveRange[0] === 'number'
      ) {
        params.start_time = dayjs(effectiveRange[0]).format('YYYY-MM-DD HH');
        params.end_time = dayjs(effectiveRange[1]).format('YYYY-MM-DD HH');
        delete params.created_at_range;
      }
      const res = await listMaterialApi({
        page: page.value,
        pageSize: pageSize.value,
        sortBy: 'created_at',
        sortOrder: 'descend',
        ...params,
      });
      items = res.items || [];
      totalCount = res.total ?? items.length;
    } else {
      const query = {
        basename: appliedMaterialNames.value.length
          ? appliedMaterialNames.value
          : undefined,
        filetype: commonFolderFiletype.value || undefined,
        folderId: selectedFolderId.value,
        page: page.value,
        pageSize: pageSize.value,
      };
      const key = JSON.stringify([
        materialCacheContext.value,
        query.folderId,
        query.page,
        query.pageSize,
        query.filetype ?? '',
        [...(query.basename ?? [])].sort(),
      ]);
      const result = await materialRequests.get(key, () =>
        httpMaterialLibraryService.listFolderMaterials(query),
      );
      items = result.items.map((item) => toFileResponse(item));
      totalCount = result.total;
    }

    if (currentSeq !== fetchSeq.value) return;
    materials.value = items;
    total.value = totalCount;
  } finally {
    if (currentSeq === fetchSeq.value) {
      cardLoading.value = false;
    }
  }
};

/** 写操作完成或手动刷新：失效当前页缓存，然后重新读取当前展示区域。 */
async function refreshMaterialLibrary() {
  clearFolderScopeCache();
  if (driveView.value === 'home') {
    await loadDriveFolders();
  } else {
    const context = materialCacheContext.value;
    const folderId = selectedFolderId.value;
    if (folderId) {
      const [folder] = await loadCachedFolders({ folderId });
      if (
        context !== materialCacheContext.value ||
        folderId !== selectedFolderId.value
      )
        return;
      if (!folder) {
        resetDriveHome();
        await loadDriveFolders();
        return;
      }
      activeDriveFolder.value = folder;
      activeFolderTrail.value = folder.path?.length
        ? [...folder.path]
        : [folder];
    }
    await Promise.all([
      fetchMaterials(true),
      activeDriveFolder.value
        ? loadChildFolders(activeDriveFolder.value)
        : Promise.resolve(),
    ]);
  }
}

const addSelection = (id: string, basename: string, filename: string = '') => {
  selectedMap.value.set(id, { basename, filename });
};

const removeSelection = (id: string) => {
  selectedMap.value.delete(id);
};

const toggleSelect = (
  id: string,
  checked: boolean,
  basename: string,
  filename: string = '',
) => {
  if (checked) {
    addSelection(id, basename, filename);
  } else {
    removeSelection(id);
  }
};

// 键盘快捷键支持
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    clearSelection();
  }
};

watch(
  materialCacheContext,
  () => {
    clearFolderScopeCache();
    localFolderVisits.clear();
    personalDriveFolders.value = [];
    departmentDriveFolders.value = [];
    recentDriveFolders.value = [];
    childFolders.value = [];
    materials.value = [];
    total.value = 0;
    activeDriveFolder.value = null;
    activeFolderTrail.value = [];
    clearSelection();
    if (
      materialLibraryMounted &&
      accessStore.accessToken &&
      !accessStore.loginExpired
    ) {
      void refreshMaterialLibrary();
    }
  },
  { flush: 'sync' },
);

onMounted(async () => {
  materialLibraryMounted = true;
  const context = materialCacheContext.value;
  document.addEventListener('keydown', handleKeyDown);
  await restoreFromRoute();
  // 文件夹要先拉回来，深链接 tab=<folderId> 才能定位到具体文件夹
  await loadDriveFolders('recent');
  if (!materialLibraryMounted || context !== materialCacheContext.value) return;
  if (initialTab && initialTab !== 'all' && initialTab !== 'common') {
    // 深链接可能是非根目录，不依赖首页当前筛选结果来定位。
    const [initialFolder] = await loadCachedFolders({
      folderId: initialTab,
    });
    if (initialFolder) {
      activeDriveFolder.value = initialFolder;
      activeFolderTrail.value = initialFolder.path?.length
        ? [...initialFolder.path]
        : [initialFolder];
      recordFolderVisit(initialFolder.id);
      void loadChildFolders(initialFolder);
    }
  }
  allSearchFormValues.value.created_at_range = allCreatedAtRange.value;
  routeStateReady.value = true;
  // 首页只显示文件夹，不额外请求一页未展示的公共素材。
  if (driveView.value !== 'home') await fetchMaterials();
});
onUnmounted(() => {
  materialLibraryMounted = false;
  clearFolderScopeCache();
  localFolderVisits.clear();
  document.removeEventListener('keydown', handleKeyDown);
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
});

const selectAllPage = () => {
  materials.value.forEach((m) => addSelection(m.id, m.basename, m.filename));
};

const invertSelection = () => {
  materials.value.forEach((m) => {
    if (selectedMap.value.has(m.id)) {
      selectedMap.value.delete(m.id);
    } else {
      selectedMap.value.set(m.id, {
        basename: m.basename,
        filename: m.filename,
      });
    }
  });
};

const clearSelection = () => {
  selectedMap.value = new Map<string, { basename: string; filename: string }>();
};

// 公共素材库批量删除
const deleteCommonMaterials = async () => {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择素材');
    return;
  }
  const ids = [...selectedMap.value.keys()];
  try {
    cardLoading.value = true;
    await batchDeleteCommonMaterialsApi(ids);
    message.success(`已删除 ${ids.length} 个素材`);
    clearSelection();
    await refreshMaterialLibrary();
  } finally {
    cardLoading.value = false;
  }
};

// 个人文件夹素材批量删除
const deleteFolderMaterials = async () => {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择素材');
    return;
  }
  const ids = [...selectedMap.value.keys()];
  try {
    cardLoading.value = true;
    await deleteFolderMaterialsApi(selectedFolderId.value!, ids);
    message.success(`已删除 ${ids.length} 个素材`);
    clearSelection();
    await refreshMaterialLibrary();
  } finally {
    cardLoading.value = false;
  }
};

const showTotal = (t: number) => `共 ${t} 条`;

// 分页处理：统一处理页码和 pageSize 变化
const handlePageChange = (p: number, size: number) => {
  if (p < 1) return;
  page.value = p;
  pageSize.value = size;
  fetchMaterials();
};

// ============================================================
// 所有素材 Tab：上传配置、搜索筛选、批量操作
// ============================================================

interface MyTag {
  is_necessary: string;
  name: string;
  tags: string[];
  title: string;
}

interface FormSchemaItem {
  [key: string]: any;
  component: any | string;
  componentProps?: Record<string, any>;
  fieldName: string;
  label: string;
  labelClass?: string;
  rules?: any | string;
}

// 素材库不加载事实标签和平台配置；显式传入空数组，避免子组件回退发起选项请求。
const factTags = ref<MyTag[]>([]);
const operatorOptions = ref<Array<{ label: string; value: string }>>([]);
const creativeEditorOptions = ref<Array<{ label: string; value: string }>>([]);
const platformOptions = ref<Array<{ label: string; value: string }>>([]);

// 投手/剪辑两个下拉框只属于「所有素材」和「公共素材库」的搜索表单，
// 云盘首页根本不渲染它们。首页是默认落点,所以按需拉,别在进页面时白发两个请求。
let userNameOptionsLoaded = false;
const fetchUserNameOptions = async () => {
  if (userNameOptionsLoaded) return;
  userNameOptionsLoaded = true;
  const [operatorRes, creatorRes] = await Promise.all([
    getUserOptions(['operator', 'operator_leader']),
    getUserOptions(['creator']),
  ]);
  operatorOptions.value = operatorRes.map((line: string) => ({
    label: line,
    value: line,
  }));
  creativeEditorOptions.value = creatorRes.map((line: string) => ({
    label: line,
    value: line,
  }));
};

// 只有这两个视图会渲染投手/剪辑筛选框。immediate 覆盖深链接 ?tab=all / ?tab=common
// 直接落到这两个视图的情况;fetchUserNameOptions 自身幂等,来回切不会重复请求。
watch(
  driveView,
  (view) => {
    if (view === 'project' || view === 'shared') fetchUserNameOptions();
  },
  { immediate: true },
);

// 搜索表单
const getDefaultCreatedAtRange = (): [number, number] => [
  toLocalDayStart(dayjs.tz().subtract(29, 'day')),
  dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
];

const allCreatedAtRange = ref<[number, number] | null | undefined>(
  getDefaultCreatedAtRange(),
);

const allSearchFormValues = ref<Record<string, any>>({
  country: undefined,
  operator: undefined,
  tags_new: undefined,
  CreativeEditor: undefined,
  game_platform: undefined,
  filetype: undefined,
  is_green_material: undefined,
  basename: undefined,
  created_at_range: allCreatedAtRange.value,
});

function searchFieldRef(key: string) {
  return computed({
    get: () => allSearchFormValues.value[key],
    set: (value) => (allSearchFormValues.value[key] = value),
  });
}

const folderNamesRouteState = computed({
  get: () => appliedMaterialNames.value,
  set(value: string[]) {
    appliedMaterialNames.value = value;
    materialNamesText.value = value.join('\n');
  },
});

const dateRangeCodec = {
  parse(value: any) {
    const dates = (Array.isArray(value) ? value : [value]).flatMap(
      (item) => item?.split(',') ?? [],
    );
    if (dates.length !== 2 || !dates[0] || !dates[1]) return undefined;
    const start = dayjs(dates[0]);
    const end = dayjs(dates[1]);
    return start.isValid() && end.isValid()
      ? ([start.valueOf(), end.endOf('day').valueOf()] as [number, number])
      : undefined;
  },
  serialize(value: [number, number] | null | undefined) {
    return value?.map((date) => dayjs(date).format('YYYY-MM-DD'));
  },
};

const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    allCreatedAt: { codec: dateRangeCodec, key: 'material_date' },
    basename: { key: 'material_basename' },
    commonBasename: { key: 'common_basename' },
    commonDate: { codec: dateRangeCodec, key: 'common_date' },
    commonFiletype: { key: 'common_filetype' },
    creator: { key: 'material_creator' },
    filetype: { key: 'material_filetype' },
    folderKeyword: { key: 'folder_keyword' },
    folderNames: { key: 'basename' },
    gamePlatform: { key: 'material_platform' },
    green: { key: 'material_green' },
    tags: { key: 'material_tags' },
  },
  onRouteStateRestored: () => {
    if (!routeStateReady.value) return;
    if (driveView.value === 'home') return loadDriveFolders();
    return fetchMaterials(true);
  },
  pagination: {
    defaultPageSize: 100,
    page,
    pageSize,
    pageSizes: [50, 100, 200, 400],
  },
  state: createListRouteStateTarget({
    allCreatedAt: allCreatedAtRange,
    basename: searchFieldRef('basename'),
    commonBasename: commonFolderBasename,
    commonDate: dateRange,
    commonFiletype: commonFolderFiletype,
    country: searchFieldRef('country'),
    creator: searchFieldRef('CreativeEditor'),
    filetype: searchFieldRef('filetype'),
    folderKeyword,
    folderNames: folderNamesRouteState,
    gamePlatform: searchFieldRef('game_platform'),
    green: searchFieldRef('is_green_material'),
    operator: searchFieldRef('operator'),
    tags: searchFieldRef('tags_new'),
  }),
});

const handleSearch = async () => {
  page.value = 1;
  selectedMap.value.clear();
  await fetchMaterials();
};

const resetAllSearchForm = async () => {
  const defaultRange = getDefaultCreatedAtRange();
  allCreatedAtRange.value = defaultRange;
  allSearchFormValues.value = {
    country: undefined,
    operator: undefined,
    tags_new: undefined,
    CreativeEditor: undefined,
    game_platform: undefined,
    filetype: undefined,
    is_green_material: undefined,
    basename: undefined,
    created_at_range: defaultRange,
  };
  selectedMap.value.clear();
  page.value = 1;
  await fetchMaterials();
};

const allUploadVisible = ref(false);
const showPushModal = ref(false);

const pushMaterialList = computed(() =>
  [...selectedMap.value.entries()].map(([id, v]) => ({
    id,
    title: v.basename,
  })),
);

function openPushModal() {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择要上传的素材');
    return;
  }
  showPushModal.value = true;
}

// 批量下载
const downloadLoading = ref(false);
const downloadNamedLoading = ref(false);
const downloadCommonLoading = ref(false);

const downloadFileByUrl = (url: string, fileName: string): void => {
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
};

const downloadZip = async (
  apiFn: (ids: string[]) => Promise<{ filename: string; url: string }>,
  loadingRef: Ref<boolean>,
) => {
  if (selectedMap.value.size === 0) {
    message.error('请至少选择一个文件');
    return;
  }
  const selectedIds = [...selectedMap.value.keys()];
  try {
    loadingRef.value = true;
    const response = await apiFn(selectedIds);
    downloadFileByUrl(response.url, response.filename);
  } catch {
    // 下载错误已由统一请求层提示。
  } finally {
    loadingRef.value = false;
  }
};

const downloadNamed = async () =>
  downloadZip(downloadFilesAsZipNamed, downloadNamedLoading);
const downloadCommon = async () =>
  downloadZip(downloadCommonFilesAsZip, downloadCommonLoading);

const download = async (isPackage: boolean) => {
  if (isPackage) {
    await downloadZip(downloadFilesAsZip, downloadLoading);
    return;
  }
  if (selectedMap.value.size === 0) {
    message.error('请至少选择一个文件');
    return;
  }
  const selectedFilenames = [...selectedMap.value.values()].map(
    (v) => v.filename,
  );
  for (const filename of selectedFilenames) {
    if (!filename) continue;
    const response = await getMaterialUrlApi(filename);
    downloadFileByUrl(response.url, response.filename);
  }
};

// 批量编辑
const isBatchEditMode = ref(false);

const openBatchEdit = () => {
  if (selectedMap.value.size === 0) {
    message.error('请至少选择一个文件');
    return;
  }
  isBatchEditMode.value = true;
};

const openBatchDelete = async () => {
  if (selectedMap.value.size === 0) {
    message.error('请至少选择一个文件');
    return;
  }
  const selectedFilenames = [...selectedMap.value.values()]
    .map((v) => v.filename)
    .filter(Boolean) as string[];
  await batchDeleteMaterials(selectedFilenames).then((res: any) => {
    message.success(
      `成功删除${res.deleted_count}个文件${res.errors?.length ? `，${res.errors.length}个文件删除失败` : ''}`,
    );
  });
  selectedMap.value.clear();
  await refreshMaterialLibrary();
};

// 分析内容
const analysisResults = ref<string[]>([]);
const analysisLoading = ref(false);

const fetchAnalysisResults = async () => {
  try {
    analysisLoading.value = true;
    analysisResults.value = await getAnalysisDescApi();
  } catch {
    message.error('获取分析内容失败');
  } finally {
    analysisLoading.value = false;
  }
};

// 批量编辑表单 schema 生成
const processSchema = (originalSchema: FormSchemaItem[]): FormSchemaItem[] => {
  return originalSchema.map(({ rules: _rules, ...rest }) => rest);
};

const generateSchema = () => {
  const factFields = factTags.value
    .filter(
      (row) =>
        !['creative_editor', 'CreativeEditor', 'operator'].includes(row.name),
    )
    .map((row) => ({
      component: 'Select',
      componentProps: {
        allowClear: true,
        filterOption: true,
        options: row.tags.map((tag) => ({ label: tag, value: tag })),
        showSearch: true,
      },
      fieldName: row.name,
      label: row.title,
      rules: 'required',
      labelClass: 'w-[50px]',
    }));

  return [
    ...factFields,
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        filterOption: (input: string, option: any) =>
          option.label.toLowerCase().includes(input.toLowerCase()),
        options: operatorOptions,
        showSearch: true,
      },
      fieldName: 'operator',
      label: '投手',
      rules: 'required',
      labelClass: 'w-[50px]',
    },
    {
      component: markRaw(TagComboSelect),
      componentProps: {
        allowClear: true,
        placeholder: '选择标签',
        style: { width: '100%' },
      },
      fieldName: 'tags_new',
      label: '标签',
      labelClass: 'w-[50px]',
      rules: 'required',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        filterOption: (input: string, option: any) =>
          option.label.toLowerCase().includes(input.toLowerCase()),
        options: creativeEditorOptions,
        showSearch: true,
      },
      fieldName: 'CreativeEditor',
      label: '剪辑',
      rules: 'required',
      labelClass: 'w-[50px]',
    },
    {
      component: markRaw(PlatformSelect),
      componentProps: {
        placeholder: '请选择平台',
        style: { width: '100%' },
        options: platformOptions,
      },
      fieldName: 'game_platform',
      label: '平台',
      rules: 'required',
      labelClass: 'w-[50px]',
    },
  ];
};

async function submitBatchEdit() {
  return editFormApi.validate().then(async () => {
    try {
      const formValues = editFormApi.form.values;
      const selectedIds = [...selectedMap.value.keys()];
      const selectedBasenames = [...selectedMap.value.values()].map(
        (v) => v.basename,
      );

      const updateData = {
        ids: selectedIds,
        basenames: selectedBasenames,
        ...Object.fromEntries(
          Object.entries({
            country: formValues.country,
            operator: formValues.operator,
            game_platform: formValues.game_platform,
            creative_editor: formValues.CreativeEditor,
            user: formValues.user,
            tags_new: formValues.tags_new?.length
              ? formValues.tags_new
              : undefined,
          }).filter(
            ([, value]) =>
              value !== undefined && value !== null && value !== '',
          ),
        ),
      };

      await batchUpdateMaterials(updateData);
      message.success('批量编辑成功');
      isBatchEditMode.value = false;
      await refreshMaterialLibrary();
    } catch {
      message.error('批量编辑失败');
    }
  });
}

const [EditForm, editFormApi] = useVbenForm({
  commonConfig: { colon: false, componentProps: { class: 'w-full' } },
  handleSubmit: submitBatchEdit,
  layout: 'horizontal',
  schema: [],
});

// 监听 factTags/options 变化，设置批量编辑表单 schema 和上传配置默认值
watch(
  [factTags, operatorOptions, creativeEditorOptions, platformOptions],
  () => {
    const schema = generateSchema();
    editFormApi.setState(() => ({ schema: processSchema(schema) }));
  },
  { deep: true, immediate: false },
);

// 监听 allSearchFormValues 中的 created_at_range 同步到 allCreatedAtRange
watch(
  () => allSearchFormValues.value.created_at_range,
  (newValue) => {
    if (JSON.stringify(newValue) !== JSON.stringify(allCreatedAtRange.value)) {
      allCreatedAtRange.value = newValue || null;
    }
  },
  { deep: true },
);
</script>

<template>
  <div
    class="adpulse-section-page material-library-page bg-muted/40 flex h-full min-h-0"
  >
    <div class="material-library-layout flex min-h-0 min-w-0 flex-1 gap-1">
      <!-- 文件夹树 -->
      <div
        v-if="false"
        class="material-folder-panel flex min-h-0 w-[248px] flex-shrink-0 flex-col border-r border-slate-200 bg-white p-2"
      >
        <div class="mb-2 border-b border-slate-100 pb-2">
          <p class="px-2 pb-1 text-xs font-medium text-slate-400">空间导航</p>
          <button
            type="button"
            class="flex min-h-11 w-full items-center gap-2 rounded-lg px-3 text-left text-sm transition-colors"
            :class="
              driveView === 'home'
                ? 'bg-blue-50 font-medium text-blue-700'
                : 'text-slate-700 hover:bg-slate-50'
            "
            @click="openDriveHome"
          >
            <span class="icon-[lucide--hard-drive] text-base"></span>
            <span>云盘首页</span>
          </button>
        </div>
        <MaterialFolderTree
          ref="treeRef"
          v-model="selectedNode"
          :show-effectiveness="false"
          class="flex-1"
        >
          <!-- 个人文件夹头部：新建按钮 -->
          <template #folder-header-actions>
            <Button
              type="text"
              class="!w-8 !min-w-0 !p-0"
              aria-label="新建文件夹"
              title="新建文件夹"
              @click="addFolder()"
            >
              <span class="icon-[ant-design--plus-outlined] text-xs"></span>
            </Button>
          </template>

          <!-- 文件夹名称（含重命名输入框） -->
          <template #folder-name="{ folder }">
            <span v-if="folderEditingId !== folder.id" class="truncate">{{
              folder.name
            }}</span>
            <Input
              v-else
              v-model:value="folderEditValue"
              class="max-w-24"
              @blur="saveRenameFolder(folder.id)"
              @press-enter="saveRenameFolder(folder.id)"
              @click.stop
            />
          </template>

          <!-- 文件夹操作按钮（重命名/删除） -->
          <template #folder-actions="{ folder }">
            <div
              class="ml-1 flex flex-shrink-0 flex-wrap items-center opacity-100 sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100"
            >
              <Button
                type="text"
                class="!w-8 !min-w-0 !p-0"
                :aria-label="`${folderEditingId === folder.id ? '取消重命名' : '重命名'} ${folder.name}`"
                title="重命名"
                @click.stop="
                  folderEditingId === folder.id
                    ? ((folderEditingId = ''), (folderEditValue = ''))
                    : ((folderEditingId = folder.id),
                      (folderEditValue = folder.name))
                "
              >
                <span
                  :class="
                    folderEditingId === folder.id
                      ? 'icon-[ant-design--close-outlined]'
                      : 'icon-[ant-design--edit-outlined]'
                  "
                  class="text-xs"
                ></span>
              </Button>
              <Popconfirm
                :open="folderDeletingId === folder.id"
                :title="`确定删除「${folder.name}」？`"
                ok-text="确定"
                cancel-text="取消"
                @update:open="
                  (open) => (folderDeletingId = open ? folder.id : '')
                "
                @confirm="removeFolder(folder.id)"
              >
                <Button
                  type="text"
                  danger
                  class="!w-8 !min-w-0 !p-0"
                  :aria-label="`删除 ${folder.name}`"
                  title="删除"
                  @click.stop
                >
                  <span
                    class="icon-[ant-design--delete-outlined] text-xs"
                  ></span>
                </Button>
              </Popconfirm>
            </div>
          </template>
        </MaterialFolderTree>
      </div>

      <!-- 右：图片卡片列表 -->
      <div
        class="material-library-content flex min-h-0 min-w-0 flex-1 flex-col"
      >
        <div v-if="driveView === 'home'" class="min-h-0 flex-1 overflow-y-auto">
          <MaterialCloudHome
            :active-tab="folderHomeTab"
            :keyword="folderKeyword"
            :material-names-text="materialNamesText"
            :searching="searchingFolders"
            :loading="folderHomeLoading"
            :personal-folders="personalDriveFolders"
            :recent-folders="recentDriveFolders"
            :shared-folders="departmentDriveFolders"
            @create-folder="createDriveFolder"
            @delete-folder="deleteDriveFolder"
            @open-folder="openDriveFolder"
            @search="searchDriveFolders"
            @refresh="refreshMaterialLibrary"
            @tab-change="changeFolderHomeTab"
            @update-folder="updateDriveFolder"
          />
        </div>

        <template v-else>
          <div
            class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4"
          >
            <div class="flex min-w-0 items-center gap-3">
              <!-- 左侧文件夹面板当前是隐藏的；层级目录优先返回父目录。 -->
              <Button @click="openParentDriveFolder">
                <span
                  class="inline-flex items-center gap-1.5"
                  style="display: inline-flex"
                >
                  <span class="icon-[lucide--arrow-left] flex-none"></span>
                  <span>
                    {{ activeDriveFolder?.parentId ? '返回上级' : '返回' }}
                  </span>
                </span>
              </Button>
              <div v-if="activeDriveFolder" class="min-w-0">
                <div class="mb-1 text-xs text-slate-500">当前文件夹</div>
                <div class="flex min-w-0 items-center gap-2">
                  <span
                    class="min-w-0 truncate text-sm font-semibold text-slate-900"
                    :title="activeFolderPath"
                  >
                    {{ activeFolderPath || activeDriveFolder.name }}
                  </span>
                  <span
                    class="inline-flex flex-none items-center gap-1 text-xs text-slate-500"
                  >
                    <span
                      :class="
                        activeDriveFolder.visibility === 'private'
                          ? 'icon-[lucide--lock] text-amber-600'
                          : 'icon-[lucide--users] text-emerald-600'
                      "
                    ></span>
                    {{ folderVisibilityLabel[activeDriveFolder.visibility] }}
                  </span>
                </div>
              </div>
            </div>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <Button
                v-if="canCreateChildFolder"
                type="primary"
                @click="openChildFolderModal"
              >
                <span
                  class="inline-flex items-center gap-1.5"
                  style="display: inline-flex"
                >
                  <span class="icon-[lucide--folder-plus] flex-none"></span>
                  <span>新建子文件夹</span>
                </span>
              </Button>
            </div>
          </div>

          <!-- ===== 所有素材 Tab ===== -->
          <template
            v-if="
              driveView === 'project' &&
              selectedFolderId === null &&
              !isCommonLib
            "
          >
            <!-- 搜索筛选区 -->
            <div class="mb-2 flex-shrink-0">
              <div class="mb-2 rounded border bg-white p-3">
                <div class="search-grid grid gap-3 text-xs">
                  <div
                    v-for="field in factTags.filter(
                      (row) =>
                        ![
                          'creative_editor',
                          'CreativeEditor',
                          'operator',
                        ].includes(row.name),
                    )"
                    :key="field.name"
                    class="flex flex-col gap-1"
                  >
                    <span class="text-sm font-medium text-gray-700">{{
                      field.title
                    }}</span>
                    <Select
                      :value="allSearchFormValues[field.name]"
                      :options="
                        field.tags.map((tag) => ({ label: tag, value: tag }))
                      "
                      placeholder="请选择"
                      allow-clear
                      show-search
                      :filter-option="
                        (input, option) =>
                          option?.label
                            ?.toLowerCase()
                            .includes(input.toLowerCase())
                      "
                      @change="(val) => (allSearchFormValues[field.name] = val)"
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">投手</span>
                    <Select
                      :value="allSearchFormValues.operator"
                      :options="operatorOptions"
                      placeholder="请选择投手"
                      allow-clear
                      show-search
                      :filter-option="
                        (input, option) =>
                          option?.label
                            ?.toLowerCase()
                            .includes(input.toLowerCase())
                      "
                      @change="(val) => (allSearchFormValues.operator = val)"
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">标签</span>
                    <TagComboSelect
                      v-model="allSearchFormValues.tags_new"
                      placeholder="选择标签"
                      allow-clear
                      style="width: 100%"
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">剪辑</span>
                    <Select
                      :value="allSearchFormValues.CreativeEditor"
                      :options="creativeEditorOptions"
                      placeholder="请选择剪辑"
                      allow-clear
                      show-search
                      :filter-option="
                        (input, option) =>
                          option?.label
                            ?.toLowerCase()
                            .includes(input.toLowerCase())
                      "
                      @change="
                        (val) => (allSearchFormValues.CreativeEditor = val)
                      "
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">平台</span>
                    <PlatformSelect
                      :value="allSearchFormValues.game_platform"
                      :options="platformOptions"
                      placeholder="请选择平台"
                      style="width: 100%"
                      @update:value="
                        (val) => (allSearchFormValues.game_platform = val)
                      "
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">{{
                      '文件类型'
                    }}</span>
                    <Select
                      :value="allSearchFormValues.filetype"
                      :options="[
                        { label: '图片', value: 'image' },
                        { label: '视频', value: 'video' },
                      ]"
                      placeholder="请选择"
                      allow-clear
                      show-search
                      @change="(val) => (allSearchFormValues.filetype = val)"
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">{{
                      '是否绿通'
                    }}</span>
                    <Select
                      :value="allSearchFormValues.is_green_material"
                      :options="[
                        { label: '绿通', value: true },
                        { label: '非绿通', value: false },
                      ]"
                      placeholder="请选择"
                      allow-clear
                      @change="
                        (val) => (allSearchFormValues.is_green_material = val)
                      "
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">{{
                      '文件名(无后缀)'
                    }}</span>
                    <Input
                      :value="allSearchFormValues.basename"
                      placeholder="请输入文件名"
                      allow-clear
                      @change="
                        (e) => (allSearchFormValues.basename = e?.target?.value)
                      "
                    />
                  </div>

                  <div class="flex flex-col gap-1">
                    <span class="text-sm font-medium text-gray-700">{{
                      '创建时间'
                    }}</span>
                    <DateRangePicker
                      :value="
                        allCreatedAtRange ||
                        allSearchFormValues.created_at_range
                      "
                      type="datetimerange"
                      format="yyyy-MM-dd HH"
                      time-picker-format="HH"
                      width="100%"
                      :clearable="false"
                      @update:value="
                        (value) => {
                          allCreatedAtRange = value;
                          allSearchFormValues.created_at_range = value;
                        }
                      "
                    />
                  </div>

                  <div class="search-actions flex items-end justify-end gap-2">
                    <Button type="primary" @click="handleSearch">搜索</Button>
                    <Button @click="resetAllSearchForm">重置</Button>
                  </div>
                </div>
              </div>

              <!-- 批量操作工具栏 -->
              <div
                class="mt-2 flex flex-wrap items-center justify-between gap-2 rounded border bg-white px-3 py-2"
              >
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <!-- 上传按钮 -->
                  <Button @click="allUploadVisible = true"> 上传 </Button>
                  <Popconfirm
                    :title="`确定下载 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="download(false)"
                  >
                    <Button @click="selectedMap.size === 0 && download(false)">
                      批量下载
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    :title="`确定打包下载 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="download(true)"
                  >
                    <Button
                      :loading="downloadLoading"
                      @click="selectedMap.size === 0 && download(true)"
                    >
                      打包下载
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    :title="`确定打包下载 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="downloadNamed"
                  >
                    <Button
                      :loading="downloadNamedLoading"
                      @click="selectedMap.size === 0 && downloadNamed()"
                    >
                      打包下载(长命名)
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    :title="`确定批量编辑 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="openBatchEdit"
                  >
                    <Button @click="selectedMap.size === 0 && openBatchEdit()">
                      批量编辑
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    :title="`确定删除 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="openBatchDelete"
                  >
                    <Button
                      danger
                      @click="selectedMap.size === 0 && openBatchDelete()"
                    >
                      批量删除
                    </Button>
                  </Popconfirm>
                  <Popover
                    title="等待处理文件"
                    trigger="hover"
                    placement="bottomLeft"
                    @open-change="
                      (visible) => visible && fetchAnalysisResults()
                    "
                  >
                    <template #content>
                      <div
                        style="
                          min-width: 120px;
                          max-height: 500px;
                          overflow-y: auto;
                        "
                      >
                        <div v-if="analysisLoading"><span>加载中...</span></div>
                        <div v-else-if="analysisResults.length === 0">
                          <span>暂无待分析内容</span>
                        </div>
                        <div v-else>
                          <ul>
                            <li
                              v-for="(result, index) in analysisResults"
                              :key="index"
                            >
                              {{ result }}
                            </li>
                          </ul>
                        </div>
                      </div>
                    </template>
                  </Popover>
                  <Button
                    @click="refreshMaterialLibrary"
                    :loading="cardLoading"
                    class="flex items-center justify-center p-2"
                  >
                    <span class="icon-[ant-design--reload-outlined]"></span>
                  </Button>
                  <Button @click="openPushModal"> 上传素材到广告账户 </Button>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <Tooltip>
                    <template #title>
                      <div v-if="!isPreviewMode">
                        选择模式：拖拽框选、勾选多选，再次框选可取消
                      </div>
                      <div v-else>
                        预览模式：点击缩略图快速预览，仅支持单个勾选
                      </div>
                    </template>
                    <Switch
                      :checked="!isPreviewMode"
                      @change="
                        (checked) => {
                          isPreviewMode = !checked;
                          isSelecting = false;
                        }
                      "
                      checked-children="选择"
                      un-checked-children="预览"
                    />
                  </Tooltip>
                  <Button.Group>
                    <Button @click="selectAllPage" :disabled="cardLoading">
                      全选
                    </Button>
                    <Button @click="invertSelection" :disabled="cardLoading">
                      反选
                    </Button>
                    <Button
                      @click="clearSelection"
                      :disabled="selectedMap.size === 0"
                    >
                      清空 ({{ selectedMap.size }})
                    </Button>
                  </Button.Group>
                </div>
              </div>
            </div>
          </template>

          <!-- ===== 公共素材库 / 个人文件夹工具栏 ===== -->
          <template v-if="isCommonLib || selectedFolderId !== null">
            <div class="mb-4 rounded-lg border border-slate-200 bg-white p-4">
              <div class="flex min-w-0 flex-wrap items-center gap-3">
                <DateRangePicker
                  :value="dateRange"
                  width="180px"
                  format="MM-dd"
                  @update:value="
                    (v) => {
                      dateRange = v;
                      fetchMaterials(true);
                    }
                  "
                />
                <MaterialNameFilter
                  v-if="!isCommonLib"
                  v-model:value="materialNamesText"
                  single-row
                  class="min-w-[280px] flex-[1_1_360px]"
                />
                <Input
                  v-else
                  :value="commonFolderBasename"
                  placeholder="文件名(无后缀)"
                  allow-clear
                  style="width: 140px"
                  @change="
                    (e) => (commonFolderBasename = e?.target?.value ?? '')
                  "
                  @press-enter="
                    () => {
                      page = 1;
                      fetchMaterials(true);
                    }
                  "
                />
                <Select
                  :value="commonFolderFiletype"
                  :options="[
                    { label: '图片', value: 'image' },
                    { label: '视频', value: 'video' },
                  ]"
                  placeholder="文件类型"
                  allow-clear
                  style="width: 110px"
                  @change="
                    (val) => {
                      commonFolderFiletype =
                        typeof val === 'string' ? val : undefined;
                      searchFolderMaterials();
                    }
                  "
                />
                <Button type="primary" @click="searchFolderMaterials">
                  <span
                    class="inline-flex items-center gap-1.5"
                    style="display: inline-flex"
                  >
                    <span class="icon-[lucide--search] flex-none"></span>
                    <span>搜索</span>
                  </span>
                </Button>
                <Button @click="resetFolderMaterialFilters">
                  <span
                    class="inline-flex items-center gap-1.5"
                    style="display: inline-flex"
                  >
                    <span class="icon-[lucide--rotate-ccw] flex-none"></span>
                    <span>重置</span>
                  </span>
                </Button>
                <Tooltip title="刷新">
                  <Button
                    aria-label="刷新素材列表"
                    @click="refreshMaterialLibrary"
                    :loading="cardLoading"
                    class="flex items-center justify-center"
                  >
                    <span class="icon-[ant-design--reload-outlined]"></span>
                  </Button>
                </Tooltip>
              </div>
              <div
                class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"
              >
                <div class="flex min-w-0 flex-wrap items-center gap-2">
                  <span class="mr-1 text-xs text-slate-500">
                    已选 {{ selectedMap.size }} 项
                  </span>
                  <Button @click="commonUploadVisible = true">
                    <span
                      class="inline-flex items-center gap-1.5"
                      style="display: inline-flex"
                    >
                      <span class="icon-[lucide--upload] flex-none"></span>
                      <span>上传</span>
                    </span>
                  </Button>
                  <Popconfirm
                    v-if="isCommonLib"
                    :title="`确定打包下载 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="downloadCommon"
                  >
                    <Button
                      :loading="downloadCommonLoading"
                      @click="selectedMap.size === 0 && downloadCommon()"
                    >
                      <span
                        class="inline-flex items-center gap-1.5"
                        style="display: inline-flex"
                      >
                        <span
                          class="icon-[ant-design--download-outlined] flex-none"
                        ></span>
                        <span>打包下载</span>
                      </span>
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    v-if="selectedFolderId !== null"
                    :title="`确定打包下载 ${selectedMap.size} 个文件吗?`"
                    :disabled="selectedMap.size === 0"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="download(true)"
                  >
                    <Button
                      :loading="downloadLoading"
                      @click="selectedMap.size === 0 && download(true)"
                    >
                      <span
                        class="inline-flex items-center gap-1.5"
                        style="display: inline-flex"
                      >
                        <span
                          class="icon-[ant-design--download-outlined] flex-none"
                        ></span>
                        <span>打包下载</span>
                      </span>
                    </Button>
                  </Popconfirm>
                  <Popconfirm
                    v-if="selectedMap.size > 0"
                    title="确定删除选中的素材？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="
                      isCommonLib
                        ? deleteCommonMaterials()
                        : deleteFolderMaterials()
                    "
                  >
                    <Button danger>
                      <span
                        class="inline-flex items-center gap-1.5"
                        style="display: inline-flex"
                      >
                        <span class="icon-[lucide--trash-2] flex-none"></span>
                        <span>删除 ({{ selectedMap.size }})</span>
                      </span>
                    </Button>
                  </Popconfirm>
                  <Button v-else danger disabled>
                    <span
                      class="inline-flex items-center gap-1.5"
                      style="display: inline-flex"
                    >
                      <span class="icon-[lucide--trash-2] flex-none"></span>
                      <span>删除</span>
                    </span>
                  </Button>
                  <Tooltip
                    v-if="selectedFolderId !== null"
                    title="将选中素材公开到所有素材"
                  >
                    <Button
                      type="primary"
                      ghost
                      :loading="publishLoading"
                      :disabled="selectedMap.size === 0"
                      @click="publishMaterials"
                    >
                      <span
                        class="inline-flex items-center gap-1.5"
                        style="display: inline-flex"
                      >
                        <span class="icon-[lucide--globe-2] flex-none"></span>
                        <span>
                          公开素材{{
                            selectedMap.size > 0 ? ` (${selectedMap.size})` : ''
                          }}
                        </span>
                      </span>
                    </Button>
                  </Tooltip>
                  <Tooltip title="将选中素材上传到广告账户">
                    <Button @click="openPushModal">
                      <span
                        class="inline-flex items-center gap-1.5"
                        style="display: inline-flex"
                      >
                        <span class="icon-[lucide--send] flex-none"></span>
                        <span>上传到广告账户</span>
                      </span>
                    </Button>
                  </Tooltip>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <Tooltip>
                    <template #title>
                      <div v-if="!isPreviewMode">
                        选择模式：拖拽框选 | Ctrl+A 全选 | Esc 清空
                      </div>
                      <div v-else>
                        预览模式：点击图片查看详情，可单选但无框选
                      </div>
                    </template>
                    <Switch
                      :checked="!isPreviewMode"
                      @change="
                        (checked) => {
                          isPreviewMode = !checked;
                        }
                      "
                      checked-children="选择"
                      un-checked-children="预览"
                    />
                  </Tooltip>
                  <Button.Group>
                    <Button @click="selectAllPage" :disabled="cardLoading">
                      全选
                    </Button>
                    <Button @click="invertSelection" :disabled="cardLoading">
                      反选
                    </Button>
                    <Button
                      @click="clearSelection"
                      :disabled="selectedMap.size === 0"
                    >
                      清空 ({{ selectedMap.size }})
                    </Button>
                  </Button.Group>
                </div>
              </div>
            </div>
          </template>

          <!-- ===== 共用：卡片网格 + 分页 ===== -->
          <div class="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
            <div
              v-if="folderContentsLoading"
              class="absolute inset-0 z-20 flex items-center justify-center bg-white/60"
            >
              <div class="flex items-center space-x-2">
                <div
                  class="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
                ></div>
                <span class="text-lg">加载中...</span>
              </div>
            </div>
            <div
              v-if="
                !folderContentsLoading &&
                materials.length === 0 &&
                childFolders.length === 0
              "
              class="flex flex-1 flex-col items-center justify-center py-16 text-gray-400"
            >
              <span
                class="icon-[ant-design--inbox-outlined] mb-3 text-2xl"
              ></span>
              <span class="text-sm">暂无数据</span>
            </div>
            <div
              v-else
              ref="gridContainer"
              class="relative grid w-full grid-cols-2 items-start gap-1 px-1 py-0 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6"
              :class="{
                'select-none': !isPreviewMode,
                'cursor-crosshair': isSelecting && !isPreviewMode,
                'border-2 border-dashed border-blue-200':
                  !isPreviewMode && materials.length > 0,
              }"
              @mousedown="startSelection"
            >
              <div
                v-if="isSelecting"
                class="pointer-events-none absolute z-10 rounded-sm border-2 border-blue-500"
                :style="{
                  left: `${Math.min(selectionBox.startX, selectionBox.endX)}px`,
                  top: `${Math.min(selectionBox.startY, selectionBox.endY)}px`,
                  width: `${Math.abs(selectionBox.endX - selectionBox.startX)}px`,
                  height: `${Math.abs(selectionBox.endY - selectionBox.startY)}px`,
                  boxShadow: '0 0 0 1px rgba(59, 130, 246, 0.5)',
                }"
              ></div>
              <MaterialCard
                v-for="item in materials"
                :key="item.id"
                :item="item"
                :items="materials"
                :checked="selectedMap.has(item.id)"
                :source="isCommonLib ? 'common' : 'material'"
                @update:checked="
                  (v) => toggleSelect(item.id, v, item.basename, item.filename)
                "
              />
              <button
                v-for="folder in childFolders"
                :key="folder.id"
                type="button"
                class="group flex min-h-[194px] min-w-0 flex-col justify-between rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition duration-200 hover:border-blue-300 hover:bg-blue-50/40 hover:shadow"
                :aria-label="`进入子文件夹：${folder.name}`"
                @mousedown.stop
                @click.stop="openDriveFolder(folder)"
              >
                <span
                  class="flex h-11 w-11 items-center justify-center rounded-xl"
                  :style="{
                    backgroundColor: `${folderDisplayColor(folder)}18`,
                    color: folderDisplayColor(folder),
                  }"
                >
                  <span class="icon-[lucide--folder] text-2xl"></span>
                </span>
                <span class="min-w-0">
                  <span
                    class="block truncate text-sm font-semibold text-slate-900 group-hover:text-blue-700"
                  >
                    {{ folder.name }}
                  </span>
                  <span class="mt-1 block text-xs text-slate-500">
                    子文件夹 ·
                    {{
                      folder.matchedMaterialCount === undefined
                        ? `${folder.materialCount} 个素材`
                        : `匹配 ${folder.matchedMaterialCount} 个素材（含子目录）`
                    }}
                  </span>
                  <span
                    class="mt-3 inline-flex items-center gap-1 text-xs text-blue-600"
                  >
                    打开文件夹
                    <span class="icon-[lucide--arrow-up-right] text-sm"></span>
                  </span>
                </span>
              </button>
            </div>
          </div>

          <div class="mt-1 flex justify-end">
            <Pagination
              :current="page"
              :page-size="pageSize"
              :page-size-options="['50', '100', '200', '400']"
              :total="total"
              show-size-changer
              :show-total="showTotal"
              @change="handlePageChange"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- 所有素材 上传 Modal -->
    <UploadMaterialModal
      all-mode
      :open="allUploadVisible"
      :fact-tags="factTags"
      :operator-options="operatorOptions"
      :creative-editor-options="creativeEditorOptions"
      :platform-options="platformOptions"
      @update:open="allUploadVisible = $event"
      @success="refreshMaterialLibrary"
    />

    <!-- 公共素材库 / 个人文件夹上传 Modal -->
    <UploadMaterialModal
      :open="commonUploadVisible"
      :folder-id="selectedFolderId ?? undefined"
      @update:open="commonUploadVisible = $event"
      @success="refreshMaterialLibrary"
    />

    <!-- 上传素材到广告账户 Modal -->
    <PushMaterialModal
      :open="showPushModal"
      :materials="pushMaterialList"
      @update:open="showPushModal = $event"
      @success="refreshMaterialLibrary"
    />

    <Modal
      v-model:open="childFolderModalOpen"
      title="新建子文件夹"
      :confirm-loading="childFolderSubmitting"
      :ok-button-props="{ disabled: !childFolderName.trim() }"
      ok-text="创建"
      @ok="createChildFolder"
    >
      <label
        for="material-child-folder-name"
        class="mb-2 block text-sm font-medium text-slate-700"
      >
        文件夹名称
      </label>
      <Input
        id="material-child-folder-name"
        v-model:value="childFolderName"
        :maxlength="50"
        placeholder="请输入子文件夹名称"
        @press-enter="createChildFolder"
      />
      <p class="mt-2 text-xs text-slate-500">
        子文件夹会继承「{{
          activeDriveFolder?.name
        }}」的空间与可见范围；最多创建三层。
      </p>
    </Modal>

    <!-- 批量编辑 Modal -->
    <Modal
      :open="isBatchEditMode"
      title="批量编辑（只需选择要修改的字段即可）"
      :footer="null"
      @update:open="(val) => (isBatchEditMode = val)"
      @close="isBatchEditMode = false"
    >
      <EditForm />
    </Modal>
  </div>
</template>

<style scoped>
.search-grid {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.search-actions {
  place-self: flex-end flex-end;
}

:deep(.overflow-y-auto)::-webkit-scrollbar {
  width: 6px;
}

:deep(.overflow-y-auto)::-webkit-scrollbar-thumb {
  background-color: rgb(0 0 0 / 20%);
  border-radius: 3px;
}

@media (max-width: 767px) {
  .material-library-layout {
    flex-direction: column;
    overflow: visible;
  }

  .material-folder-panel {
    width: 100%;
    min-height: 190px;
    max-height: 250px;
    flex: none;
    padding-right: 0;
    padding-bottom: 4px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .material-library-content {
    width: 100%;
    min-height: 0;
  }

  .search-grid {
    grid-template-columns: 1fr;
  }
}
</style>
