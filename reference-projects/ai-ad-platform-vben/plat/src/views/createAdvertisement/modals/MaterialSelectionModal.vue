<script lang="ts" setup>
import type { MaterialItem } from '../types';

import type { VxeGridProps } from '#/adapter/vxe-table';

import { computed, nextTick, onUnmounted, ref, watch } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  Input,
  message,
  Modal,
  Pagination,
  Select,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAllFactTags,
  getBatchMaterialImgApi,
  getPlatOptions,
  listCommonMaterialsApi,
  listFolderMaterialsApi,
  listMaterialApi,
} from '#/api';
import { getDashboardDetail } from '#/api/dashboard';
import { getUserNameOptions } from '#/api/system/user';

import DateRangePicker from '../../components/DateRangePicker.vue';
import MaterialCard from '../../components/MaterialCard.vue';
import PlatformSelect from '../../components/PlatformSelect.vue';
import TagComboSelect from '../../materials/components/TagComboSelect.vue';
import MaterialFolderTree from '../../materials/components/MaterialFolderTree.vue';
import UploadMaterialModal from '../../materials/components/UploadMaterialModal.vue';

import { useMaterial } from '../composables/useMaterial';
import { useMaterialSelection } from '../composables/useMaterialSelection';

interface Props {
  open: boolean;
  operatorOptions: Array<{ label: string; value: string }>;
  uploadedMaterialIds?: string[];
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'confirm', materials: MaterialItem[]): void;
}

const props = defineProps<Props>();

const emit = defineEmits<Emits>();

dayjs.extend(isoWeek);

const {
  materialDateRange,
  selectedMaterialCategory,
  loadingImg,
  loadSingleImage,
} = useMaterial();

const {
  view1SelectedIds,
  view2SelectedIds,
  getMaterialId,
  updatePageSelections,
  removeSelection,
  getSelectionCount,
  clearSelections,
  getSelectedRows,
} = useMaterialSelection();

const modalOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
});

interface TreeSelection {
  type: 'effectiveness' | 'all' | 'common' | 'folder';
  folderId?: string;
  folderName?: string;
}

const selectedNode = ref<TreeSelection>({ type: 'all' });

const view2DataLoaded = ref(false);

const dateRange = ref<[number, number]>([
  dayjs(dayjs.tz().subtract(29, 'day').format('YYYY-MM-DD')).valueOf(),
  dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
]);

// 公共素材库/个人文件夹 筛选状态
const commonFolderBasename = ref('');
const commonFolderFiletype = ref<string | undefined>(undefined);

interface MyTag {
  is_necessary: string;
  name: string;
  tags: string[];
  title: string;
}

interface FileResponse {
  analysis_description: string;
  country: string;
  created_at: string;
  creative_editor?: string;
  filename: string;
  filetype: string;
  game_platform?: string;
  id: string;
  img: string;
  isUsedToday?: boolean;
  operator: string;
  tag_description: Record<string, any>;
  tags_new?: string[];
  tags_tree?: Array<{ children: any[]; key: string; title: string }>;
  updated_at: string;
  user?: string;
}

const factTags = ref<MyTag[]>([]);
const platformOptions = ref<Array<{ label: string; value: string }>>([]);
const creatorOptions = ref<Array<{ label: string; value: string }>>([]);

const createdAtRange = ref<[number, number] | null>([
  dayjs(dayjs.tz().subtract(30, 'days').format('YYYY-MM-DD')).valueOf(),
  dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
]);

const searchFormValues2 = ref<Record<string, any>>({
  country: undefined,
  operator: undefined,
  tags_new: undefined,
  CreativeEditor: undefined,
  game_platform: undefined,
  filetype: undefined,
  basename: undefined,
  created_at_range: createdAtRange.value,
});

const cardMaterials = ref<FileResponse[]>([]);
const cardTotal = ref(0);
const cardPage = ref(1);
const cardPageSize = ref(24);
const cardLoading = ref(false);
const currentPageSelectedIds = ref<Set<string>>(new Set());

const isPreviewMode = ref(false);
const isSelecting = ref(false);
const selectionBox = ref({ startX: 0, startY: 0, endX: 0, endY: 0 });
const gridContainer = ref<HTMLElement | null>(null);
const selectionStartSelected = ref<Set<string>>(new Set());

const previewCardRef = ref<InstanceType<typeof MaterialCard> | null>(null);

function openCardPreview(item: any) {
  previewCardRef.value?.openPreview(item);
}

const fetchPlatformOptions = async () => {
  if (platformOptions.value.length > 0) return;
  const res = await getPlatOptions();
  platformOptions.value = res.map((platform: string) => ({
    label: platform,
    value: platform,
  }));
};

const fetchCreatorOptions = async () => {
  if (creatorOptions.value.length > 0) return;
  try {
    const users = await getUserNameOptions(['creator']);
    creatorOptions.value = users.map((user) => ({
      label: user.full_name,
      value: user.real_name,
    }));
  } catch {}
};

const getDefaultFilterValues = (): Record<string, any> => {
  const defaultValues: Record<string, any> = {};
  factTags.value.forEach((row) => {
    if (row.tags && row.tags.length > 0 && ['category'].includes(row.name)) {
      defaultValues[row.name] = row.tags[0];
    }
  });
  return defaultValues;
};

const applyDefaultFilterValues = () => {
  const defaultValues = getDefaultFilterValues();
  if (Object.keys(defaultValues).length > 0) {
    Object.assign(searchFormValues2.value, defaultValues);
  }
};

const statusMap: Record<string, { color: string; text: string }> = {
  ACTIVE: { text: '投放中', color: 'green' },
  ENABLED: { text: '投放中', color: 'green' },
  DISAPPROVED: { text: '已拒绝', color: 'red' },
  ADSET_PAUSED: { text: '组暂停', color: 'orange' },
  ARCHIVED: { text: '已删除', color: 'gray' },
  CAMPAIGN_PAUSED: { text: '系列暂停', color: 'orange' },
  PAUSED: { text: '已暂停', color: 'orange' },
  IN_PROCESS: { text: '处理中', color: 'blue' },
  DELETED: { text: '已删除', color: 'gray' },
  WITH_ISSUES: { text: '有问题', color: 'red' },
  PENDING_REVIEW: { text: '待审核', color: 'cyan' },
};

const initData = async () => {
  if (factTags.value.length > 0) return;
  try {
    factTags.value = await getAllFactTags();
  } catch {}
};

function refreshCardSelectionUI() {
  const newSet = new Set<string>();
  cardMaterials.value.forEach((item) => {
    if (view2SelectedIds.has(item.id)) newSet.add(item.id);
  });
  currentPageSelectedIds.value = newSet;
}

function toggleCardSelect(item: FileResponse) {
  const checked = !currentPageSelectedIds.value.has(item.id);
  const currentPageRows = cardMaterials.value as any[];
  const selectedOnPage = currentPageRows.filter((r) =>
    currentPageSelectedIds.value.has(r.id),
  );
  if (checked) {
    selectedOnPage.push(item);
  } else {
    const idx = selectedOnPage.findIndex((r: any) => r.id === item.id);
    if (idx !== -1) selectedOnPage.splice(idx, 1);
  }
  updatePageSelections('view2', currentPageRows as any, selectedOnPage as any);
  const newSet = new Set(currentPageSelectedIds.value);
  if (checked) {
    newSet.add(item.id);
  } else {
    newSet.delete(item.id);
  }
  currentPageSelectedIds.value = newSet;
}

function selectAllPage() {
  const currentPageRows = cardMaterials.value as any[];
  updatePageSelections('view2', currentPageRows as any, currentPageRows as any);
  currentPageSelectedIds.value = new Set(cardMaterials.value.map((m) => m.id));
}

function invertSelection() {
  const currentPageRows = cardMaterials.value as any[];
  const newSelectedOnPage = currentPageRows.filter(
    (r) => !currentPageSelectedIds.value.has(r.id),
  );
  updatePageSelections(
    'view2',
    currentPageRows as any,
    newSelectedOnPage as any,
  );
  currentPageSelectedIds.value = new Set(
    newSelectedOnPage.map((r: any) => r.id),
  );
}

function clearSelection() {
  clearSelections('view2');
  currentPageSelectedIds.value = new Set();
}

const startSelection = (event: MouseEvent) => {
  if (isPreviewMode.value) return;

  const target = event.target as HTMLElement;
  const isInteractiveElement =
    target.tagName === 'INPUT' ||
    target.tagName === 'BUTTON' ||
    target.closest('input') ||
    target.closest('button') ||
    target.closest('.ant-checkbox');

  if (isInteractiveElement) return;
  if (!gridContainer.value) return;

  isSelecting.value = true;
  selectionStartSelected.value = new Set<string>(currentPageSelectedIds.value);

  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.startX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.startY =
    event.clientY - rect.top + gridContainer.value.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;

  document.addEventListener('mousemove', updateSelection);
  document.addEventListener('mouseup', endSelection);
  event.preventDefault();
};

const updateSelection = (event: MouseEvent) => {
  if (!isSelecting.value || !gridContainer.value) return;

  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.endX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.endY =
    event.clientY - rect.top + gridContainer.value.scrollTop;

  updateSelectedCards();
};

const endSelection = () => {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
};

const updateSelectedCards = () => {
  if (!gridContainer.value) return;

  const container = gridContainer.value;
  const cards = container.querySelectorAll<HTMLElement>('[data-card-id]');
  const newSelected = new Set<string>(selectionStartSelected.value);

  const selectionRect = {
    left: Math.min(selectionBox.value.startX, selectionBox.value.endX),
    top: Math.min(selectionBox.value.startY, selectionBox.value.endY),
    right: Math.max(selectionBox.value.startX, selectionBox.value.endX),
    bottom: Math.max(selectionBox.value.startY, selectionBox.value.endY),
  };

  const minSelectionSize = 5;
  if (
    Math.abs(selectionBox.value.endX - selectionBox.value.startX) <
      minSelectionSize ||
    Math.abs(selectionBox.value.endY - selectionBox.value.startY) <
      minSelectionSize
  ) {
    return;
  }

  const containerRect = container.getBoundingClientRect();

  cards.forEach((card) => {
    const cardRect = card.getBoundingClientRect();
    const cardRelativeRect = {
      left: cardRect.left - containerRect.left + container.scrollLeft,
      top: cardRect.top - containerRect.top + container.scrollTop,
      right: cardRect.right - containerRect.left + container.scrollLeft,
      bottom: cardRect.bottom - containerRect.top + container.scrollTop,
    };

    const isIntersecting = !(
      cardRelativeRect.right < selectionRect.left ||
      cardRelativeRect.left > selectionRect.right ||
      cardRelativeRect.bottom < selectionRect.top ||
      cardRelativeRect.top > selectionRect.bottom
    );

    const cardId = card.dataset.cardId!;
    if (isIntersecting) {
      if (selectionStartSelected.value.has(cardId)) {
        newSelected.delete(cardId);
      } else {
        newSelected.add(cardId);
      }
    }
  });

  currentPageSelectedIds.value = newSelected;
  const currentPageRows = cardMaterials.value as any[];
  const selectedOnPage = currentPageRows.filter((r) => newSelected.has(r.id));
  updatePageSelections('view2', currentPageRows as any, selectedOnPage as any);
};

// 竞态防护:切文件夹/搜索会连发请求,响应回来时 token 已被新请求顶替则丢弃
let cardRequestToken = 0;

async function fetchCardMaterials() {
  cardRequestToken += 1;
  const myToken = cardRequestToken;
  cardLoading.value = true;
  try {
    const nodeType = selectedNode.value.type;
    let items: FileResponse[] = [];
    let total = 0;

    if (nodeType === 'common') {
      const res = await listCommonMaterialsApi({
        page: cardPage.value,
        page_size: cardPageSize.value,
        filetype: commonFolderFiletype.value || undefined,
        basename: commonFolderBasename.value || undefined,
      });
      items = res.items || [];
      total = res.total || items.length;
    } else if (nodeType === 'folder') {
      const res = await listFolderMaterialsApi(
        selectedNode.value.folderId!,
        cardPage.value,
        cardPageSize.value,
        {
          filetype: commonFolderFiletype.value || undefined,
          basename: commonFolderBasename.value || undefined,
        },
      );
      items = res.items || [];
      total = res.total || items.length;
    } else {
      const params: Record<string, any> = { ...searchFormValues2.value };
      const effectiveRange = params.created_at_range || createdAtRange.value;
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
        page: cardPage.value,
        pageSize: cardPageSize.value,
        sortBy: 'created_at',
        sortOrder: 'descend',
        ...params,
      });
      items = res.items || [];
      total = res.total || 0;
    }

    if (myToken !== cardRequestToken) return;
    cardMaterials.value = items;
    cardTotal.value = total;
    await nextTick();
    refreshCardSelectionUI();
  } finally {
    if (myToken === cardRequestToken) {
      cardLoading.value = false;
    }
  }
}

function handleCardSearch() {
  cardPage.value = 1;
  fetchCardMaterials();
}

function resetCardSearchForm() {
  searchFormValues2.value = {
    country: undefined,
    operator: undefined,
    tags_new: undefined,
    CreativeEditor: undefined,
    game_platform: undefined,
    filetype: undefined,
    basename: undefined,
    created_at_range: createdAtRange.value,
  };
  const defaultValues = getDefaultFilterValues();
  Object.assign(searchFormValues2.value, defaultValues);
  cardPage.value = 1;
  fetchCardMaterials();
}

function resetDateFilter() {
  dateRange.value = [
    dayjs(dayjs.tz().subtract(29, 'day').format('YYYY-MM-DD')).valueOf(),
    dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
  ];
  commonFolderBasename.value = '';
  commonFolderFiletype.value = undefined;
  cardPage.value = 1;
  fetchCardMaterials();
}

function resetEffectivenessFilter() {
  materialDateRange.value = [
    dayjs(dayjs.tz().subtract(29, 'day').format('YYYY-MM-DD')).valueOf(),
    dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
  ];
}

function handleCardPageChange(p: number, size: number) {
  if (p < 1) return;
  cardPage.value = p;
  cardPageSize.value = size;
  fetchCardMaterials();
}

function buildVxeGridColumns(columns: string[]): any[] {
  const baseColumns = [
    { align: 'left', minWidth: 38, title: '', type: 'checkbox', fixed: 'left' },
    { minWidth: 38, title: '序号', type: 'seq' },
  ];

  const filteredColumns = columns.filter(
    (column: string) => !column.startsWith('1d'),
  );

  const dynamicColumns = filteredColumns.map((column: string) => {
    switch (column) {
      case 'name': {
        return {
          field: column,
          width: 200,
          resizable: true,
          sortable: true,
          slots: { default: 'name' },
          title: '名称',
          fixed: 'left',
        };
      }
      case 'unique_name': {
        return {
          field: column,
          title: 'unique_name',
          width: 105,
        };
      }
      case '创建时间': {
        return {
          field: column,
          title: '创建时间',
          width: 100,
        };
      }
      case '状态': {
        return {
          field: column,
          title: '状态',
          width: 100,
          slots: { default: 'status' },
        };
      }
      case '花费金额': {
        return {
          field: column,
          title: '花费金额',
          width: 140,
        };
      }
      default: {
        const colConfig: any = {
          field: column,
          title: column,
          width: 100,
        };
        return colConfig;
      }
    }
  });

  return [...baseColumns, ...dynamicColumns];
}

const view1GridColumns = ref<any[]>([
  { align: 'left', minWidth: 38, title: '', type: 'checkbox', fixed: 'left' },
  { minWidth: 38, title: '序号', type: 'seq' },
  {
    field: 'name',
    minWidth: 200,
    sortable: true,
    slots: { default: 'name' },
    title: '名称',
    fixed: 'left',
  },
]);

const view1GridOptions: VxeGridProps<MaterialItem> = {
  checkboxConfig: {
    highlight: true,
    trigger: 'default',
    checkMethod: undefined,
    reserve: true,
  },
  rowConfig: {
    keyField: 'id',
  },
  columns: [
    { align: 'left', minWidth: 38, title: '', type: 'checkbox', fixed: 'left' },
    { minWidth: 38, title: '序号', type: 'seq' },
    {
      field: 'name',
      minWidth: 200,
      sortable: true,
      slots: { default: 'name' },
      title: '名称',
      fixed: 'left',
    },
  ],
  height: 540,
  keepSource: true,
  pagerConfig: {
    pageSize: 20,
  },
  proxyConfig: {
    autoLoad: false,
    ajax: {
      query: async ({ page }) => {
        const params: Record<string, string> = {
          category: selectedMaterialCategory.value,
          page: String(page.currentPage),
          page_size: String(page.pageSize),
        };

        const [startDate, endDate] = materialDateRange.value || [];
        if (startDate && endDate) {
          const startStr = dayjs(startDate).format('YYYY-MM-DD');
          const endStr = dayjs(endDate).format('YYYY-MM-DD');
          params.date = `${startStr},${endStr}`;
        }

        try {
          const response = await getDashboardDetail('ad_id', params);

          if (response.columns && response.columns.length > 0) {
            const newColumns = buildVxeGridColumns(response.columns);
            const validColumns = newColumns
              .filter((col: any) => {
                return (
                  col &&
                  typeof col === 'object' &&
                  (col.field !== undefined ||
                    col.type === 'checkbox' ||
                    col.type === 'seq')
                );
              })
              .map((col: any) => {
                if (col.slots && typeof col.slots !== 'object') {
                  delete col.slots;
                }
                return col;
              });
            await nextTick();
            view1GridColumns.value = [...validColumns];

            await nextTick();
            if (View1GridApi.grid && View1GridApi.grid.reloadColumn) {
              try {
                View1GridApi.grid.reloadColumn(validColumns);
              } catch {}
            }
          } else {
            await nextTick();
            view1GridColumns.value = buildVxeGridColumns(['name']);
          }

          const rows = (response.data || []).map((item: any) => {
            const row = {
              ...item,
              id: item.id || item.materialId || item.key,
              key: item.id || item.materialId,
              materialId: item.id || item.materialId,
            };
            return row;
          });

          view1Data.value = rows;

          const total =
            (response.pagination && (response.pagination as any).total) ||
            Math.max(0, rows.length);

          await nextTick();
          await loadAllImages();

          const returnData = {
            items: rows,
            total,
          };

          setTimeout(async () => {
            await nextTick();
            await restoreView1SelectionsFromIds();
          }, 0);

          return returnData;
        } catch {
          return {
            items: [],
            total: 0,
          };
        }
      },
    },
  },
  showOverflow: false,
};

(view1GridOptions as any).onCheckboxChange = () =>
  handleView1GridCheckboxChange();
(view1GridOptions as any).onCheckboxAll = () => handleView1GridCheckboxChange();
(view1GridOptions as any).onCheckboxSelectAll = () =>
  handleView1GridCheckboxChange();
(view1GridOptions as any).onCheckboxSelectChange = () =>
  handleView1GridCheckboxChange();

const [View1Grid, View1GridApi] = useVbenVxeGrid({
  gridOptions: view1GridOptions,
  routeState: false,
});

const view1Data = ref<any[]>([]);

const loadAllImages = async () => {
  if (loadingImg.value) return;

  loadingImg.value = true;

  try {
    const itemsToLoad = view1Data.value.filter(
      (item) => item.unique_name && !item.img,
    );
    const basenames = itemsToLoad.map((item) => item.unique_name);

    if (basenames.length === 0) {
      loadingImg.value = false;
      return;
    }

    const response = await getBatchMaterialImgApi(basenames);
    const batchData = response.images || {};

    view1Data.value.forEach((item) => {
      if (item.unique_name && batchData[item.unique_name]) {
        const imgData = batchData[item.unique_name];
        item.img = imgData.img;
        item.filename = imgData.filename;
        item.filetype = imgData.filetype;
      }
    });
  } finally {
    loadingImg.value = false;
  }
};

async function handleDateChange() {
  await nextTick();
  if (selectedNode.value.type === 'effectiveness') {
    if (View1GridApi.grid) {
      await View1GridApi.grid.commitProxy('query');
    }
  } else if (selectedNode.value.type === 'all') {
    cardPage.value = 1;
    await fetchCardMaterials();
  }
}

function handleConfirm() {
  const viewKey =
    selectedNode.value.type === 'effectiveness' ? 'view1' : 'view2';
  const selected = getSelectedRows(viewKey);

  if (selected.length === 0) {
    message.warning('请至少选择一个素材');
    return;
  }

  const selectedMaterials = selected.map((item) => ({
    ...item,
    name: item.name || (item as any).basename || '',
    materialId: item.materialId || item.id || '',
    _sourceView: viewKey,
  }));

  emit('confirm', selectedMaterials);

  modalOpen.value = false;
}

function handleCancel() {
  modalOpen.value = false;
}

watch(
  () => materialDateRange.value,
  async (newRange, oldRange) => {
    if (oldRange === undefined) return;
    if (!newRange || !Array.isArray(newRange) || newRange.length !== 2) return;
    if (oldRange && oldRange[0] === newRange[0] && oldRange[1] === newRange[1])
      return;

    await handleDateChange();
  },
  { deep: true },
);

watch(
  () => modalOpen.value,
  async (isOpen) => {
    if (isOpen) {
      await nextTick();
      await Promise.all([
        fetchPlatformOptions(),
        fetchCreatorOptions(),
        initData(),
      ]);
      if (
        selectedNode.value.type !== 'effectiveness' &&
        !view2DataLoaded.value
      ) {
        applyDefaultFilterValues();
        view2DataLoaded.value = true;
        await fetchCardMaterials();
      }
    }
  },
);

watch(
  () => selectedNode.value,
  async (node, oldNode) => {
    // 树每次点击都 emit 新对象,点同一节点不重复搜索
    if (
      oldNode &&
      node.type === oldNode.type &&
      node.folderId === oldNode.folderId
    ) {
      return;
    }
    if (modalOpen.value) {
      await nextTick();
      if (node.type === 'effectiveness') {
        if (View1GridApi.grid) {
          await View1GridApi.grid.commitProxy('query');
        }
      } else {
        if (node.type === 'all') {
          applyDefaultFilterValues();
        } else {
          commonFolderBasename.value = '';
          commonFolderFiletype.value = undefined;
        }
        cardPage.value = 1;
        await fetchCardMaterials();
        view2DataLoaded.value = true;
      }
    }
  },
  { deep: true },
);

watch(
  [factTags, () => props.operatorOptions, platformOptions],
  async () => {
    applyDefaultFilterValues();
    if (
      modalOpen.value &&
      selectedNode.value.type === 'all' &&
      view2DataLoaded.value
    ) {
      await fetchCardMaterials();
    }
  },
  { deep: true, immediate: false },
);

function handleView1GridCheckboxChange() {
  if (!View1GridApi?.grid) return;
  const tableData = View1GridApi.grid.getTableData();
  const currentPageRows = tableData.tableData || tableData.visibleData || [];
  const selectedRows = View1GridApi.grid.getCheckboxRecords(false);
  updatePageSelections('view1', currentPageRows, selectedRows);
}

async function restoreView1SelectionsFromIds() {
  if (!modalOpen.value) return;

  if (!View1GridApi?.grid) return;

  try {
    const tableData = View1GridApi.grid.getTableData();
    const currentPageRows = tableData.tableData || tableData.visibleData || [];

    currentPageRows.forEach((row: any) => {
      const id = getMaterialId(row, 'view1');
      View1GridApi.grid.setCheckboxRow(row, view1SelectedIds.has(id));
    });
  } catch {}
}

watch(
  () => props.uploadedMaterialIds,
  (newIds) => {
    if (!newIds) return;

    const uploadedSet = new Set(newIds);

    const view1IdsToRemove: string[] = [];
    view1SelectedIds.forEach((id) => {
      if (!uploadedSet.has(id)) {
        view1IdsToRemove.push(id);
      }
    });

    const view2IdsToRemove: string[] = [];
    view2SelectedIds.forEach((id) => {
      if (!uploadedSet.has(id)) {
        view2IdsToRemove.push(id);
      }
    });

    view1IdsToRemove.forEach((id) => removeSelection('view1', id));
    view2IdsToRemove.forEach((id) => removeSelection('view2', id));

    if (view2IdsToRemove.length > 0) {
      refreshCardSelectionUI();
    }
  },
  { deep: true },
);

onUnmounted(() => {
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
});

// ===== 上传功能 =====
const uploadVisible = ref(false);

const openUpload = () => {
  uploadVisible.value = true;
};
</script>

<template>
  <div>
    <Modal
      v-model:open="modalOpen"
      width="1600px"
      centered
      class="material-selection-modal"
      @ok="handleCancel"
    >
      <template #title>选择素材</template>
      <div class="ux-modal-workspace flex gap-2">
        <!-- 左侧：文件夹树 -->
        <MaterialFolderTree
          v-model="selectedNode"
          :show-effectiveness="true"
          class="w-[200px] flex-shrink-0 overflow-y-auto border-r pr-2"
        />

        <!-- 右侧：成效视图 -->
        <div
          v-if="selectedNode.type === 'effectiveness'"
          class="flex flex-1 flex-col overflow-hidden"
        >
          <div class="mb-2 flex-shrink-0 rounded border bg-white p-3">
            <div class="search-grid-modal grid gap-2 text-xs">
              <div class="col-span-2 flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">上传时间</span>
                <DateRangePicker
                  v-model="materialDateRange"
                  width="100%"
                  format="yyyy-MM-dd"
                />
              </div>
              <div class="flex items-end gap-2">
                <Button type="primary" @click="handleDateChange">搜索</Button>
                <Button @click="resetEffectivenessFilter">重置</Button>
              </div>
            </div>
          </div>

          <div class="flex-1 overflow-hidden">
            <Page class="flex-1">
              <View1Grid
                @checkbox-change="handleView1GridCheckboxChange"
                @checkbox-all="handleView1GridCheckboxChange"
                @checkbox-select-all="handleView1GridCheckboxChange"
                @checkbox-select-change="handleView1GridCheckboxChange"
              >
                <template #status="{ row }">
                  <Tag
                    :color="
                      statusMap[row['状态'] || row.status]?.color || 'default'
                    "
                  >
                    {{
                      statusMap[row['状态'] || row.status]?.text ||
                      row['状态'] ||
                      row.status ||
                      '未知'
                    }}
                  </Tag>
                </template>

                <template #name="{ row }">
                  <div class="flex items-center justify-between">
                    <a
                      class="cursor-pointer text-blue-600 hover:underline"
                      @click="openCardPreview(row)"
                    >
                      {{ row.name || row.materialId }}
                    </a>
                    <div>
                      <Button
                        v-if="!row.img"
                        type="link"
                        :loading="loadingImg"
                        @click="loadSingleImage(row)"
                      >
                        显示
                      </Button>
                      <div
                        v-if="row.img"
                        class="group relative"
                        style="
                          width: 90px;
                          height: 90px;
                          overflow: hidden;
                          cursor: pointer;
                          background-color: #f0f0f0;
                          border-radius: 4px;
                          box-shadow: 0 2px 4px rgb(0 0 0 / 10%);
                        "
                        @click="openCardPreview(row)"
                      >
                        <img
                          :src="`data:image/jpeg;base64,${row.img}`"
                          alt="Material Image"
                          style="width: 100%; height: 100%; object-fit: contain"
                        />
                        <div
                          v-if="row.filetype === 'video'"
                          class="pointer-events-none absolute inset-0 flex items-center justify-center"
                        >
                          <span
                            class="icon-[ant-design--play-circle-filled] text-2xl text-white opacity-80"
                          ></span>
                        </div>
                        <div
                          class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 opacity-0 transition-opacity group-hover:opacity-100"
                        >
                          <span
                            class="icon-[ant-design--eye-outlined] text-2xl text-white"
                          ></span>
                        </div>
                      </div>
                    </div>
                  </div>
                </template>

                <template #isUsedToday="{ row }">
                  <span v-if="row.isUsedToday" class="text-green-600">是</span>
                  <span v-else class="text-gray-400">否</span>
                </template>
              </View1Grid>
            </Page>
          </div>
        </div>

        <!-- 右侧：素材卡片视图 -->
        <div v-else class="flex flex-1 flex-col overflow-hidden">
          <!-- 所有素材：完整筛选面板 -->
          <div
            v-if="selectedNode.type === 'all'"
            class="mb-2 flex-shrink-0 rounded border bg-white p-3"
          >
            <div class="search-grid-modal grid gap-2 text-xs">
              <div
                v-for="field in factTags.filter(
                  (row) =>
                    ![
                      'creative_editor',
                      'CreativeEditor',
                      'operator',
                      'country',
                    ].includes(row.name),
                )"
                :key="field.name"
                class="flex flex-col gap-1"
              >
                <span class="text-sm font-medium text-gray-700">
                  {{ field.title }}
                </span>
                <Select
                  :value="searchFormValues2[field.name]"
                  :options="
                    field.tags.map((tag) => ({ label: tag, value: tag }))
                  "
                  placeholder="请选择"
                  allow-clear
                  show-search
                  :filter-option="
                    (input, option) =>
                      option?.label?.toLowerCase().includes(input.toLowerCase())
                  "
                  @change="(val) => (searchFormValues2[field.name] = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">国家</span>
                <Select
                  :value="searchFormValues2.country"
                  :options="
                    (
                      factTags.find((f) => f.name === 'country')?.tags || []
                    ).map((tag) => ({ label: tag, value: tag }))
                  "
                  placeholder="请选择国家"
                  allow-clear
                  show-search
                  :filter-option="
                    (input, option) =>
                      option?.label?.toLowerCase().includes(input.toLowerCase())
                  "
                  @change="(val) => (searchFormValues2.country = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">投手</span>
                <Select
                  :value="searchFormValues2.operator"
                  :options="props.operatorOptions"
                  placeholder="请选择投手"
                  allow-clear
                  show-search
                  :filter-option="
                    (input, option) =>
                      option?.label?.toLowerCase().includes(input.toLowerCase())
                  "
                  @change="(val) => (searchFormValues2.operator = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">标签</span>
                <TagComboSelect
                  v-model="searchFormValues2.tags_new"
                  placeholder="选择标签"
                  allow-clear
                  style="width: 100%"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">剪辑</span>
                <Select
                  :value="searchFormValues2.CreativeEditor"
                  :options="creatorOptions"
                  placeholder="请选择剪辑"
                  allow-clear
                  show-search
                  :filter-option="
                    (input, option) =>
                      option?.label?.toLowerCase().includes(input.toLowerCase())
                  "
                  @change="(val) => (searchFormValues2.CreativeEditor = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">平台</span>
                <PlatformSelect
                  :value="searchFormValues2.game_platform"
                  :options="platformOptions"
                  placeholder="请选择平台"
                  style="width: 100%"
                  @update:value="
                    (val) => (searchFormValues2.game_platform = val)
                  "
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">文件类型</span>
                <Select
                  :value="searchFormValues2.filetype"
                  :options="[
                    { label: '图片', value: 'image' },
                    { label: '视频', value: 'video' },
                  ]"
                  placeholder="请选择"
                  allow-clear
                  show-search
                  @change="(val) => (searchFormValues2.filetype = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">
                  文件名(无后缀)
                </span>
                <Input
                  :value="searchFormValues2.basename"
                  placeholder="请输入文件名"
                  allow-clear
                  @change="
                    (e) => (searchFormValues2.basename = e?.target?.value)
                  "
                />
              </div>

              <div class="col-span-2 flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">上传时间</span>
                <DateRangePicker
                  :value="createdAtRange"
                  type="datetimerange"
                  format="yyyy-MM-dd HH"
                  time-picker-format="HH"
                  width="100%"
                  :clearable="false"
                  @update:value="
                    (value) => {
                      createdAtRange = value;
                      searchFormValues2.created_at_range = value;
                    }
                  "
                />
              </div>

              <div class="flex items-end gap-2">
                <Button type="primary" @click="handleCardSearch">搜索</Button>
                <Button @click="resetCardSearchForm">重置</Button>
              </div>
            </div>
          </div>

          <!-- 公共素材库/个人文件夹 -->
          <div v-else class="mb-2 flex-shrink-0 rounded border bg-white p-3">
            <div class="flex flex-wrap items-end gap-3">
              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">上传时间</span>
                <DateRangePicker
                  :value="dateRange"
                  width="240px"
                  format="yyyy-MM-dd"
                  @update:value="
                    (v) => {
                      dateRange = v;
                    }
                  "
                />
              </div>
              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">文件名</span>
                <Input
                  :value="commonFolderBasename"
                  placeholder="文件名(无后缀)"
                  allow-clear
                  style="width: 140px"
                  @change="
                    (e) => (commonFolderBasename = e?.target?.value ?? '')
                  "
                  @press-enter="
                    () => {
                      cardPage = 1;
                      fetchCardMaterials();
                    }
                  "
                />
              </div>
              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">文件类型</span>
                <Select
                  :value="commonFolderFiletype"
                  :options="[
                    { label: '图片', value: 'image' },
                    { label: '视频', value: 'video' },
                  ]"
                  placeholder="请选择"
                  allow-clear
                  style="width: 110px"
                  @change="(val) => (commonFolderFiletype = val)"
                />
              </div>
              <div class="flex items-end gap-2">
                <Button
                  type="primary"
                  @click="
                    () => {
                      cardPage = 1;
                      fetchCardMaterials();
                    }
                  "
                  >搜索</Button
                >
                <Button @click="resetDateFilter">重置</Button>
              </div>
            </div>
          </div>

          <div
            class="flex flex-shrink-0 items-center justify-between px-3 py-2"
          >
            <Button
              v-if="
                selectedNode.type === 'common' || selectedNode.type === 'folder'
              "
              @click="openUpload"
            >
              上传
            </Button>
            <span v-else />
            <div class="flex items-center gap-2">
              <Tooltip>
                <template #title>
                  <div v-if="!isPreviewMode">
                    选择模式：拖拽框选 | 勾选多选 | 再次框选可取消
                  </div>
                  <div v-else>预览模式：点击缩略图快速预览</div>
                </template>
                <Switch
                  :checked="!isPreviewMode"
                  checked-children="选择"
                  un-checked-children="预览"
                  @change="
                    (checked) => {
                      isPreviewMode = !checked;
                      isSelecting = false;
                    }
                  "
                />
              </Tooltip>
              <Button.Group>
                <Button :disabled="cardLoading" @click="selectAllPage">
                  全选
                </Button>
                <Button :disabled="cardLoading" @click="invertSelection">
                  反选
                </Button>
                <Button
                  :disabled="getSelectionCount('view2') === 0"
                  @click="clearSelection"
                >
                  清空 ({{ getSelectionCount('view2') }})
                </Button>
              </Button.Group>
            </div>
          </div>

          <div class="relative min-h-0 flex-1">
            <div
              v-if="cardLoading"
              class="absolute inset-0 z-20 flex items-center justify-center bg-white/60"
            >
              <div class="flex items-center space-x-2">
                <div
                  class="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
                ></div>
                <span>加载中...</span>
              </div>
            </div>

            <div class="h-full overflow-y-auto">
              <div
                v-if="!cardLoading && cardMaterials.length === 0"
                class="flex h-full flex-col items-center justify-center py-16 text-gray-400"
              >
                <span
                  class="icon-[ant-design--inbox-outlined] mb-3 text-2xl"
                ></span>
                <span class="text-sm">暂无数据</span>
              </div>
              <div
                v-else
                ref="gridContainer"
                class="relative grid grid-cols-6 gap-1 px-1"
                :class="{
                  'select-none': !isPreviewMode,
                  'cursor-crosshair': isSelecting && !isPreviewMode,
                  'border-2 border-dashed border-blue-200':
                    !isPreviewMode && cardMaterials.length > 0,
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
                  v-for="item in cardMaterials"
                  :key="item.id"
                  :item="item"
                  :items="cardMaterials"
                  :checked="currentPageSelectedIds.has(item.id)"
                  :source="
                    selectedNode.type === 'common' ? 'common' : 'material'
                  "
                  @update:checked="() => toggleCardSelect(item)"
                />
              </div>
            </div>
          </div>

          <div class="mt-1 flex flex-shrink-0 justify-end">
            <Pagination
              :current="cardPage"
              :page-size="cardPageSize"
              :total="cardTotal"
              show-size-changer
              :page-size-options="['24', '48', '100']"
              @change="handleCardPageChange"
            />
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex items-center justify-between">
          <div class="text-sm text-gray-600">
            已选择
            <span class="font-semibold text-blue-600">{{
              getSelectionCount(
                selectedNode.type === 'effectiveness' ? 'view1' : 'view2',
              )
            }}</span>
            个素材
          </div>
          <div class="flex gap-3">
            <Button class="rounded-md" @click="handleCancel">取消</Button>
            <Button
              type="primary"
              class="rounded-md"
              :disabled="
                getSelectionCount(
                  selectedNode.type === 'effectiveness' ? 'view1' : 'view2',
                ) === 0
              "
              @click="handleConfirm"
            >
              确认选择
            </Button>
          </div>
        </div>
      </template>
    </Modal>

    <MaterialCard
      ref="previewCardRef"
      :item="{}"
      :checked="false"
      preview-only
    />

    <UploadMaterialModal
      :open="uploadVisible"
      :folder-id="
        selectedNode.type === 'folder' ? selectedNode.folderId : undefined
      "
      @update:open="uploadVisible = $event"
      @success="fetchCardMaterials()"
    />
  </div>
</template>

<style lang="scss" scoped>
.material-selection-modal {
  .material-tree-item {
    user-select: none;
  }

  .material-table {
  }
}

.search-grid-modal {
  grid-template-columns: repeat(10, minmax(0, 1fr));
}
</style>
