<script lang="ts" setup>
import type { TreeProps } from 'ant-design-vue';

import type { TagConfig } from '#/api/tags/tree';

import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Button,
  Input,
  InputNumber,
  message,
  Pagination,
  Popconfirm,
  Popover,
  Radio,
  Select,
  Switch,
  Table,
  Tooltip,
  Tree,
  TreeSelect,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import isToday from 'dayjs/plugin/isToday';

import {
  batchUpdateMaterials,
  getAdsByTag,
  getBatchMaterialImgApi,
  getMaterialImgApi,
  listMaterialsWithTagTitles,
} from '#/api';
import { getUserDepartmentOptions, getUserOptions } from '#/api/system/user';
import {
  addNodeTreeTag,
  createTagConfig,
  deleteTagConfig,
  deleteTreeTag,
  exportTreeDataWithStats,
  getTagConfigOptions,
  getTreeDataWithStats,
  getTreeTags,
  updateTagConfig,
  updateTreeTag,
} from '#/api/tags/tree';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import MaterialCard from '#/views/components/MaterialCard.vue';
import PlatformSelect from '#/views/components/PlatformSelect.vue';

dayjs.extend(isoWeek);
dayjs.extend(isToday);

// ---------------- 左侧：标签树 ----------------
const treeData = ref<TreeProps['treeData']>([]);
const expandedKeys = ref<string[]>([]);

const editingKey = ref<string>('');
const editValue = ref<string>('');
const deletingKey = ref<string>(''); // 当前打开删除确认的节点 key

const loading = ref(false); // 左侧树统一 loading

// 收集所有节点的 key
const collectAllKeys = (nodes: any[]): string[] => {
  const keys: string[] = [];
  const traverse = (nodeList: any[]) => {
    for (const node of nodeList) {
      if (node.key) keys.push(node.key);
      if (node.children?.length) traverse(node.children);
    }
  };
  traverse(nodes);
  return keys;
};

const loadTreeData = async (showLoading = true) => {
  try {
    if (showLoading) loading.value = true;
    treeData.value = await getTreeTags(
      selectedConfigId.value,
      selectedUser.value,
    );
    // 首次加载时展开所有节点
    if (expandedKeys.value.length === 0) {
      expandedKeys.value = collectAllKeys(treeData.value || []);
    }
  } finally {
    if (showLoading) loading.value = false;
  }
};

const editNode = (key: string, title: string) => {
  editingKey.value = key;
  editValue.value = title;
};

const cancelEdit = () => {
  editingKey.value = '';
  editValue.value = '';
};

const saveEdit = async (key: string) => {
  if (editValue.value.trim()) {
    try {
      loading.value = true;
      await updateTreeTag(key, {
        title: editValue.value,
        config_id: selectedConfigId.value,
        real_name: selectedUser.value,
      });
      // 编辑成功后立即取消输入状态
      editingKey.value = '';
      editValue.value = '';
      message.success('节点编辑成功');
      await loadTreeData(false);
      await fetchMaterials();
    } finally {
      loading.value = false;
    }
  } else {
    // 如果内容为空，也要取消编辑状态
    editingKey.value = '';
    editValue.value = '';
  }
};

const addNode = async (
  parentId?: string,
  level?: number,
  realName?: string,
  configId?: string,
) => {
  try {
    loading.value = true;

    await addNodeTreeTag({
      title: '新标签',
      parent_id: parentId,
      level: level || 1,
      real_name: realName || selectedUser.value,
      config_id: configId || selectedConfigId.value,
    });
    message.success('添加节点成功');

    // 添加子节点时，确保父节点展开
    if (parentId && !expandedKeys.value.includes(parentId)) {
      expandedKeys.value = [...expandedKeys.value, parentId];
    }

    await loadTreeData(false);
  } finally {
    loading.value = false;
  }
};

const deleteNode = async (key: string) => {
  loading.value = true;
  await deleteTreeTag(key);
  deletingKey.value = ''; // 关闭弹窗
  message.success('删除成功');
  await loadTreeData(false);
  await fetchMaterials();
  loading.value = false;
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

const cardLoading = ref(false);
const materials = ref<FileResponse[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(100);

const selectedMap = ref<Map<string, string>>(new Map()); // id -> basename

// 预览模式状态
const isPreviewMode = ref(true); // 默认为预览模式

// 表格数据Modal状态
const tableViewLoading = ref(false);
const tableViewData = ref<any[]>([]);
const tableViewColumns = ref<any[]>([]);
const expandedRowKeysSet = ref<Set<string>>(new Set()); // 展开的行keys（Set存储）
const expandedRowKeys = computed(() => [...expandedRowKeysSet.value]); // Table组件需要数组
const loadingAdKeys = ref<Set<string>>(new Set()); // 正在加载广告数据的标签keys
const loadingAdImg = ref(false); // 正在加载广告图片
const tableDataNeedsRefresh = ref(true); // 标记表格数据是否需要刷新

// 树选择状态
const selectedTreeKeys = ref<string[]>([]);
const exportLoading = ref(false);
const originMode = ref(false);
const tableDateField = ref<'create_time' | 'date'>('create_time');

// TreeSelect状态
const selectedTagsForFilter = ref<string[]>([]);
const tagFilterCondition = ref<'contains' | 'excludes'>('contains');

// 配置选择状态
const selectedConfigId = ref<string | undefined>(undefined);
const selectedConfigName = ref<string | undefined>(undefined);
const configOptions = ref<TagConfig[]>([]);
const configLoading = ref(false);
const newConfigName = ref('');
const editingConfigId = ref<null | string>(null);
const editConfigName = ref('');
const configPopoverOpen = ref(false);

// 用户选择状态
const selectedUser = ref<string | undefined>(undefined);
const userOptions = ref<Array<{ label: string; value: string }>>([]);

// 右侧素材筛选的用户和平台状态
const rightSelectedUser = ref<string | undefined>(undefined);
const rightSelectedPlatform = ref<string | undefined>(undefined);
const rightSelectedDepartment = ref<string[]>([]);
const departmentOptions = ref<Array<{ label: string; value: string }>>([]);
const minSpent = ref<number | undefined>(undefined);

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
      selectedMap.value.set(m.id, m.basename);
    } else {
      selectedMap.value.delete(m.id);
    }
  });
};

const fetchMaterials = async (clearSelect = false) => {
  try {
    cardLoading.value = true;
    if (clearSelect) clearSelection();
    const res = await listMaterialsWithTagTitles({
      page: page.value,
      pageSize: pageSize.value,
      game_platform: rightSelectedPlatform.value,
      departments: rightSelectedDepartment.value?.length
        ? rightSelectedDepartment.value
        : undefined,
      real_name: rightSelectedUser.value,
      start_date: dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
      end_date: dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
      min_spent: minSpent.value,
      date_field: tableDateField.value,
      tags:
        selectedTagsForFilter.value.length > 0
          ? selectedTagsForFilter.value
          : undefined,
      tag_filter_condition: tagFilterCondition.value,
    });
    materials.value = res.items || [];
    total.value = res.total || (materials.value?.length ?? 0);
  } finally {
    cardLoading.value = false;
  }
};

const addSelection = (id: string, basename: string) => {
  selectedMap.value.set(id, basename);
};

const removeSelection = (id: string) => {
  selectedMap.value.delete(id);
};

const toggleSelect = (id: string, checked: boolean, basename: string) => {
  if (checked) {
    addSelection(id, basename);
  } else {
    removeSelection(id);
  }
};

// 多选超出时 hover 显示完整选中项
const buildMaxTagPlaceholder = (omittedValues: any[]) => {
  const labels = omittedValues
    .map((v: any) => v.label ?? v.title ?? v.value ?? String(v))
    .join('、');
  return h(Tooltip, { title: labels }, () => `+${omittedValues.length}`);
};

// 加载部门选项
const loadDepartmentOptions = async () => {
  const response = await getUserDepartmentOptions();
  if (Array.isArray(response)) {
    departmentOptions.value = response.map((d: string) => ({
      label: d,
      value: d,
    }));
  }
};

// 加载用户选项
const loadUserOptions = async () => {
  const response = await getUserOptions([
    'operator',
    'operator_leader',
    'creator',
  ]);
  if (Array.isArray(response) && response.length > 0) {
    userOptions.value = response.map((user: string) => ({
      label: user,
      value: user,
    }));

    // 默认不选择用户
    selectedUser.value = undefined;
  }
};

// 加载配置选项（根据用户筛选，不选择用户则加载全部）
const loadConfigOptions = async () => {
  try {
    configLoading.value = true;
    const response = await getTagConfigOptions(selectedUser.value);
    if (Array.isArray(response)) {
      configOptions.value = response;
    }
  } finally {
    configLoading.value = false;
  }
};

// 添加配置
const handleAddConfig = async () => {
  if (!selectedUser.value) {
    message.warning('请先选择用户');
    return;
  }

  const name = newConfigName.value.trim();
  if (!name) {
    message.warning('请输入配置名称');
    return;
  }

  // 检查是否已存在同名配置
  if (configOptions.value.some((c) => c.name === name)) {
    message.warning('该配置名称已存在');
    return;
  }

  try {
    configLoading.value = true;
    const newConfig = await createTagConfig(name, selectedUser.value);
    configOptions.value = [...configOptions.value, newConfig];
    newConfigName.value = '';
    message.success('配置添加成功');
  } catch {
    message.error('添加配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 开始编辑配置
const startEditConfig = (config: TagConfig) => {
  editingConfigId.value = config.id;
  editConfigName.value = config.name;
};

// 保存编辑配置
const saveEditConfig = async () => {
  const name = editConfigName.value.trim();
  if (!name || !editingConfigId.value) {
    cancelEditConfig();
    return;
  }

  // 检查是否已存在同名配置（排除当前编辑的配置）
  if (
    configOptions.value.some(
      (c) => c.name === name && c.id !== editingConfigId.value,
    )
  ) {
    message.warning('该配置名称已存在');
    return;
  }

  try {
    configLoading.value = true;
    await updateTagConfig(editingConfigId.value, name);
    const index = configOptions.value.findIndex(
      (c) => c.id === editingConfigId.value,
    );
    if (index !== -1) {
      const existing = configOptions.value[index]!;
      configOptions.value[index] = { ...existing, name };
    }
    // 如果修改的是当前选中的配置，更新选中值
    if (selectedConfigId.value === editingConfigId.value) {
      selectedConfigName.value = name;
    }
    message.success('配置更新成功');
    cancelEditConfig();
  } catch {
    message.error('更新配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 取消编辑配置
const cancelEditConfig = () => {
  editingConfigId.value = null;
  editConfigName.value = '';
};

// 删除配置
const handleDeleteConfig = async (config: TagConfig) => {
  try {
    configLoading.value = true;
    await deleteTagConfig(config.id);
    configOptions.value = configOptions.value.filter((c) => c.id !== config.id);

    // 如果删除的是当前选中的配置，清空选择
    if (selectedConfigId.value === config.id) {
      selectedConfigId.value = undefined;
      selectedConfigName.value = undefined;
    }

    message.success('配置删除成功');
  } catch {
    message.error('删除配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 配置变化处理
const onConfigChange = async () => {
  // 关闭弹出框
  configPopoverOpen.value = false;

  // 清空选择状态
  selectedTreeKeys.value = [];
  clearSelection();

  // 只重新加载左侧树数据，不刷新右侧素材列表
  await loadTreeData(true);
};

// 选择配置
const selectConfig = async (config: TagConfig) => {
  selectedConfigId.value = config.id;
  selectedConfigName.value = config.name;
  // 配置中包含 real_name，自动设置用户
  if (config.real_name && !selectedUser.value) {
    selectedUser.value = config.real_name;
    // 用户发生变化，需要重新加载配置选项以匹配当前用户
    await loadConfigOptions();
  }
  await onConfigChange();
};

// 清除配置选择
const clearConfigSelection = async () => {
  selectedConfigId.value = undefined;
  selectedConfigName.value = undefined;
  configPopoverOpen.value = false;
  selectedTreeKeys.value = [];
  clearSelection();
  await loadTreeData(true);
};

// 左侧用户变化处理
const onUserChange = async () => {
  // 清空选择状态
  selectedTreeKeys.value = [];
  clearSelection();

  // 清空配置选择，重新加载配置选项
  selectedConfigId.value = undefined;
  selectedConfigName.value = undefined;
  await loadConfigOptions();

  // 只重新加载左侧树数据，不刷新右侧素材列表
  await loadTreeData(true);
};

// 监听搜索条件变化，重置页码为1
watch(
  [
    rightSelectedUser,
    rightSelectedPlatform,
    rightSelectedDepartment,
    dateRange,
    minSpent,
    tagFilterCondition,
    selectedTagsForFilter,
    tableDateField,
  ],
  () => {
    page.value = 1;
  },
  { deep: true },
);

// 监听影响表格数据的查询条件变化，标记需要刷新
watch(
  [
    rightSelectedUser,
    rightSelectedPlatform,
    rightSelectedDepartment,
    dateRange,
    minSpent,
    tagFilterCondition,
    selectedTagsForFilter,
    tableDateField,
  ],
  () => {
    tableDataNeedsRefresh.value = true;
  },
  { deep: true },
);

// 添加键盘事件监听
onMounted(async () => {
  await Promise.all([
    loadUserOptions(),
    loadConfigOptions(),
    loadDepartmentOptions(),
  ]);
  await Promise.all([loadTreeData(), fetchMaterials()]);
});
onUnmounted(() => {
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
});

const selectAllPage = () => {
  materials.value.forEach((m) => addSelection(m.id, m.basename));
};

const invertSelection = () => {
  materials.value.forEach((m) => {
    if (selectedMap.value.has(m.id)) {
      selectedMap.value.delete(m.id);
    } else {
      selectedMap.value.set(m.id, m.basename);
    }
  });
};

const clearSelection = () => {
  selectedMap.value = new Map<string, string>();
};

// 转换树数据为TreeSelect格式（移除checkbox相关属性）
const getTreeSelectData = () => {
  const transformNode = (node: any): any => {
    const transformed: any = {
      value: node.key,
      title: node.title,
      key: node.key,
    };

    if (node.children && node.children.length > 0) {
      transformed.children = node.children.map((child: any) =>
        transformNode(child),
      );
    }

    return transformed;
  };

  return (treeData.value || []).map((node: any) => transformNode(node));
};

// 获取选中标签的所有父节点key和当前节点key（不拼接路径）
const getSelectedTagKeysWithParents = () => {
  if (selectedTreeKeys.value.length === 0 || !treeData.value?.length) {
    return [];
  }

  const tagSet = new Set<string>();

  // 创建节点映射以快速查找
  const nodeMap = new Map<string, any>();
  const parentMap = new Map<string, string>();

  // 构建节点映射和父子关系映射
  const buildMaps = (nodes: any[], parentKey?: string) => {
    for (const node of nodes) {
      nodeMap.set(node.key, node);
      if (parentKey) {
        parentMap.set(node.key, parentKey);
      }

      if (node.children?.length) {
        buildMaps(node.children, node.key);
      }
    }
  };

  buildMaps(treeData.value);

  // 对每个选中的节点，收集其路径上的所有节点key
  const collectParentKeys = (nodeKey: string) => {
    const path: string[] = [];
    let currentKey: string | undefined = nodeKey;

    while (currentKey) {
      path.unshift(currentKey);
      currentKey = parentMap.get(currentKey);
    }

    return path;
  };

  // 收集所有选中节点及其父节点的key
  for (const key of selectedTreeKeys.value) {
    if (nodeMap.has(key)) {
      const pathKeys = collectParentKeys(key);
      pathKeys.forEach((pathKey) => tagSet.add(pathKey));
    }
  }

  return [...tagSet];
};

// 批量应用选中的标签到选中的素材
const batchApplyTags = async () => {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择要应用标签的素材');
    return;
  }

  if (selectedTreeKeys.value.length === 0) {
    message.warning('请先选择要应用的标签');
    return;
  }

  try {
    loading.value = true;
    const tagKeys = getSelectedTagKeysWithParents();
    const materialIds = [...selectedMap.value.keys()];
    const basenames = [...selectedMap.value.values()];

    await batchUpdateMaterials({
      ids: materialIds,
      basenames,
      tags_new: tagKeys, // 使用 tags_new 参数
    });

    message.success(
      `已将 ${tagKeys.length} 个标签应用到 ${materialIds.length} 个素材`,
    );

    // 重新加载标签树和素材列表
    await loadTreeData(false);
    await fetchMaterials();
  } finally {
    loading.value = false;
  }
};

// 批量取消应用选中的标签
const batchRemoveTags = async () => {
  if (selectedMap.value.size === 0) {
    message.warning('请先选择要取消标签的素材');
    return;
  }

  if (selectedTreeKeys.value.length === 0) {
    message.warning('请先选择要取消的标签');
    return;
  }

  try {
    loading.value = true;
    // 只删除实心选中的标签（selectedTreeKeys已经是实心的）
    const tagKeys = selectedTreeKeys.value;
    const materialIds = [...selectedMap.value.keys()];
    const basenames = [...selectedMap.value.values()];

    // 对于取消应用，传递要移除的标签key
    await batchUpdateMaterials({
      ids: materialIds,
      basenames,
      tags_remove: tagKeys, // 只移除实心选中的标签
    });

    message.success(
      `已从 ${materialIds.length} 个素材中移除 ${tagKeys.length} 个标签`,
    );

    // 重新加载左侧标签树和右侧素材列表
    await loadTreeData(false);
    await fetchMaterials();
  } finally {
    loading.value = false;
  }
};

const previewCardRef = ref<InstanceType<typeof MaterialCard> | null>(null);

const previewAdMaterial = async (record: any) => {
  if (!record.filetype) return;
  await previewCardRef.value?.openPreview(record);
};

// 数据统计 Modal - 使用 VbenModal 支持拖动
const [TableModal, tableModalApi] = useVbenModal({
  modal: true,
  class: '!w-[90%] !h-[100%]',
  contentClass: '!overflow-hidden',
  showCancelButton: false,
  showConfirmButton: false,
  fullscreenButton: false,
  fullscreen: true,
  zIndex: 1001,
});

// 分页处理：统一处理页码和 pageSize 变化
const handlePageChange = (p: number, size: number) => {
  // 忽略无效的页码
  if (p < 1) {
    return;
  }
  page.value = p;
  pageSize.value = size;
  fetchMaterials();
};

// 递归更新树节点的 children
const updateNodeChildren = (
  data: any[],
  targetKey: string,
  newChildren: any[],
): boolean => {
  for (const node of data) {
    if (node.key === targetKey) {
      node.children = newChildren;
      return true;
    }
    if (
      node.children &&
      node.children.length > 0 &&
      updateNodeChildren(node.children, targetKey, newChildren)
    ) {
      return true;
    }
  }
  return false;
};

// 加载指定标签下的广告数据
const loadAdsForTag = async (tagNode: any) => {
  // 防止重复加载
  if (loadingAdKeys.value.has(tagNode.key)) {
    return;
  }

  try {
    loadingAdKeys.value.add(tagNode.key);

    const response = await getAdsByTag({
      tag_id: tagNode.key,
      game_platform: rightSelectedPlatform.value,
      departments: rightSelectedDepartment.value?.length
        ? rightSelectedDepartment.value
        : undefined,
      real_name: rightSelectedUser.value,
      start_date: dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
      end_date: dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
      min_spent: minSpent.value,
      date_field: tableDateField.value,
      origin: originMode.value, // 根据选择使用清洗数据或原始数据
    });

    // 将广告数据格式化
    const adChildren = (response.ads || []).map((ad: any) => ({
      key: `${tagNode.key}-ad-${ad.ad_id || ad.id}`,
      title: ad.ad_name || ad.title,
      is_tag: false,
      ad_name: ad.ad_name,
      ...ad, // 包含所有统计数据
    }));

    // 更新树数据
    updateNodeChildren(tableViewData.value, tagNode.key, adChildren);

    // 自动批量加载广告图片
    void loadAdsImages(adChildren);
  } finally {
    loadingAdKeys.value.delete(tagNode.key);
  }
};

// 批量加载广告图片
const loadAdsImages = async (adNodes: any[]) => {
  if (loadingAdImg.value) return;

  try {
    loadingAdImg.value = true;

    // 获取需要加载图片的广告名称（优先使用 unique_name，兼容 ad_name）
    const adsToLoad = adNodes.filter(
      (ad) => (ad.unique_name || ad.ad_name) && !ad.img,
    );
    const basenames = adsToLoad.map((ad) => ad.unique_name || ad.ad_name);

    if (basenames.length === 0) {
      return;
    }

    // 调用批量获取缩略图的API
    const response = await getBatchMaterialImgApi(basenames);
    const batchData = response.images || {};

    // 批量设置图片数据
    basenames.forEach((basename) => {
      const matchingAds = adNodes.filter(
        (ad) => (ad.unique_name || ad.ad_name) === basename,
      );

      if (matchingAds.length > 0 && batchData[basename]) {
        const imgData = batchData[basename];
        matchingAds.forEach((ad) => {
          ad.img = imgData.img;
          ad.filename = imgData.filename;
          ad.filetype = imgData.filetype;
        });
      }
    });
  } finally {
    loadingAdImg.value = false;
  }
};

// 加载单个广告图片
const loadSingleAdImage = async (record: any) => {
  // 优先使用 unique_name，如果没有则使用 ad_name
  const basename = record.unique_name || record.ad_name;
  if (!basename || record.img || loadingAdImg.value) return;

  try {
    loadingAdImg.value = true;
    const response = await getMaterialImgApi(basename);
    record.img = response.img;
    record.filename = response.filename;
    record.filetype = response.filetype;
  } catch {
  } finally {
    loadingAdImg.value = false;
  }
};

// 点击展开按钮加载广告数据（只针对没有 children 的最后一级标签）
const handleExpandAds = async (record: any) => {
  const isExpanded = expandedRowKeysSet.value.has(record.key);

  if (isExpanded) {
    // 已展开，则收起
    expandedRowKeysSet.value.delete(record.key);
  } else {
    // 未展开
    if (!record.children || record.children.length === 0) {
      // 首次展开，加载广告数据
      await loadAdsForTag(record);
    }
    // 加载完成后展开
    expandedRowKeysSet.value.add(record.key);
  }
};

// 处理 Table 原生的展开/收起事件（针对有 children 的节点点击加号）
const handleTableExpand = (expanded: boolean, record: any) => {
  if (expanded) {
    // 展开操作：添加到 expandedRowKeys
    expandedRowKeysSet.value.add(record.key);
  } else {
    // 收起操作：从 expandedRowKeys 移除
    expandedRowKeysSet.value.delete(record.key);
  }
};

// 递归收集所有有 children 的节点的 key（用于默认全部展开）
const collectExpandableKeys = (data: any[]): Set<string> => {
  const keys = new Set<string>();
  const traverse = (nodes: any[]) => {
    for (const node of nodes) {
      if (node.children && node.children.length > 0) {
        keys.add(node.key);
        traverse(node.children);
      }
    }
  };
  traverse(data);
  return keys;
};

// 使用 computed 缓存所有标签 keys，避免每次都重新计算
const allTreeTagKeys = computed(() => {
  if (!treeData.value || treeData.value.length === 0) {
    return [];
  }

  const keys: string[] = [];
  const traverse = (nodeList: any[]) => {
    for (const node of nodeList) {
      if (node.key) {
        keys.push(node.key);
      }
      if (node.children && node.children.length > 0) {
        traverse(node.children);
      }
    }
  };
  traverse(treeData.value);
  return keys;
});

// 加载表格视图数据
const loadTableViewData = async () => {
  try {
    tableViewLoading.value = true;

    // 决定要传递的标签：如果用户选择了标签，使用选择的；否则使用所有已展示的标签
    const tagsToSend: string[] =
      selectedTagsForFilter.value.length > 0
        ? selectedTagsForFilter.value
        : allTreeTagKeys.value;

    const response = await getTreeDataWithStats(
      dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
      dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
      rightSelectedPlatform.value,
      rightSelectedUser.value,
      selectedConfigId.value,
      tagsToSend, // 传递标签数组
      tagFilterCondition.value,
      minSpent.value,
      originMode.value, // 根据选择使用清洗数据或原始数据
      tableDateField.value,
    );
    tableViewData.value = response.tree_data || [];

    // 默认展开所有有 children 的节点
    expandedRowKeysSet.value = collectExpandableKeys(tableViewData.value);
    // 构建表格列
    const baseColumns = [
      {
        title: '名称',
        dataIndex: 'title',
        key: 'title',
        fixed: 'left',
        width: 400,
        customRender: ({ record }: any) => {
          if (record.is_tag) {
            // 标签节点
            const isLoading = loadingAdKeys.value.has(record.key);
            const isExpanded = expandedRowKeysSet.value.has(record.key);
            const hasLoadedAds = record.children !== undefined; // 是否已经尝试加载过广告
            const showExpandButton = !hasLoadedAds; // 只有未加载过才显示展开按钮

            const elements = [
              h(
                'span',
                {
                  class:
                    'bg-primary/10 text-primary inline-flex h-5 w-5 items-center justify-center rounded text-xs font-medium mr-2',
                },
                record.level,
              ),
              h('span', { class: 'font-medium' }, record.title),
            ];

            // 只在没有 children 的标签上添加展开/收起按钮
            if (showExpandButton) {
              elements.push(
                h(
                  Button,
                  {
                    type: 'link',
                    size: 'small',
                    loading: isLoading,
                    onClick: (e: Event) => {
                      e.stopPropagation();
                      handleExpandAds(record);
                    },
                    class: 'ml-2',
                  },
                  () => {
                    if (isLoading) return '加载中...';
                    return isExpanded ? '收起' : '展开';
                  },
                ),
              );
            }

            return h('div', { class: 'flex items-center' }, elements);
          } else {
            // 广告节点
            const adElements = [
              h(
                'span',
                { class: 'text-gray-600' },
                record.ad_name || record.title,
              ),
            ];

            // 如果没有图片，显示"显示"按钮
            if (!record.img) {
              adElements.push(
                h(
                  Button,
                  {
                    type: 'link',
                    size: 'small',
                    loading: loadingAdImg.value,
                    onClick: (e: Event) => {
                      e.stopPropagation();
                      loadSingleAdImage(record);
                    },
                    class: 'ml-2',
                  },
                  () => '显示',
                ),
              );
            }

            // 如果有图片，显示缩略图
            if (record.img) {
              adElements.push(
                h(
                  'div',
                  {
                    class: 'group relative ml-2',
                    style: {
                      width: '90px',
                      height: '90px',
                      cursor: 'pointer',
                      borderRadius: '4px',
                      overflow: 'hidden',
                      backgroundColor: '#f0f0f0',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                    },
                    onClick: (e: Event) => {
                      e.stopPropagation();
                      previewAdMaterial(record);
                    },
                  },
                  [
                    // 缩略图
                    h('img', {
                      src: `data:image/jpeg;base64,${record.img}`,
                      alt: 'Material Image',
                      style: {
                        width: '100%',
                        height: '100%',
                        objectFit: 'contain',
                      },
                    }),
                    // 视频播放图标
                    record.filetype === 'video'
                      ? h(
                          'div',
                          {
                            class:
                              'pointer-events-none absolute inset-0 flex items-center justify-center',
                          },
                          [
                            h('span', {
                              class:
                                'icon-[ant-design--play-circle-filled] text-3xl text-white opacity-80',
                            }),
                          ],
                        )
                      : null,
                    // hover 预览图标
                    h(
                      'div',
                      {
                        class:
                          'absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 opacity-0 transition-opacity group-hover:opacity-100',
                      },
                      [
                        h('span', {
                          class:
                            'icon-[ant-design--eye-outlined] text-2xl text-white',
                        }),
                      ],
                    ),
                  ],
                ),
              );
            }

            return h(
              'div',
              {
                class: 'flex items-center gap-2',
                style: {
                  maxWidth: '100%',
                  overflow: 'hidden',
                },
              },
              adElements,
            );
          }
        },
      },
    ];

    // 添加统计字段列
    const statColumns = (response.columns || []).map((columnName: string) => ({
      title: columnName,
      dataIndex: columnName,
      key: columnName,
      width: 100,
      customRender: ({ record }: any) => {
        const value = record[columnName];
        if (value === null || value === undefined) return '-';
        // 格式化数字显示
        if (typeof value === 'number') {
          return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
        }
        return value;
      },
    }));

    tableViewColumns.value = [...baseColumns, ...statColumns];

    // 数据加载完成后，重置刷新标记
    tableDataNeedsRefresh.value = false;
  } finally {
    tableViewLoading.value = false;
  }
};

// 打开数据表格Modal
const openTableModal = () => {
  tableModalApi.open();
  // 只有在查询条件改变或首次打开时才重新加载数据
  if (tableDataNeedsRefresh.value || tableViewData.value.length === 0) {
    loadTableViewData();
  }
};

// 刷新表格数据
const refreshTableData = () => {
  loadTableViewData();
};

// 导出数据
const handleExport = async () => {
  try {
    exportLoading.value = true;
    const tagsToSend: string[] =
      selectedTagsForFilter.value.length > 0
        ? selectedTagsForFilter.value
        : allTreeTagKeys.value;

    const response = await exportTreeDataWithStats({
      start_date: dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
      end_date: dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
      date_field: tableDateField.value,
      right_game_platform: rightSelectedPlatform.value,
      real_name: rightSelectedUser.value,
      config_id: selectedConfigId.value,
      tags: tagsToSend,
      tag_filter_condition: tagFilterCondition.value,
      min_spent: minSpent.value,
      origin: originMode.value, // 根据选择使用清洗数据或原始数据
    });

    // 处理文件下载
    if (response && response.filename && response.content) {
      // 将 base64 内容转换为 Blob
      const byteCharacters = atob(response.content);
      const byteArray = Uint8Array.from(
        { length: byteCharacters.length },
        (_, i) => byteCharacters.codePointAt(i)!,
      );
      const blob = new Blob([byteArray], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      // 创建下载链接
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = response.filename;
      document.body.append(link);
      link.click();

      link.remove();
      window.URL.revokeObjectURL(url);

      message.success('导出成功');
    }
  } catch {
    // ignore
  } finally {
    exportLoading.value = false;
  }
};
</script>

<template>
  <div class="tag-editor-page bg-background flex h-full min-h-0 p-1">
    <div class="tag-editor-layout flex min-h-0 min-w-0 flex-1 gap-1">
      <!-- 左：标签树 -->
      <div
        class="tag-tree-panel relative flex w-[420px] flex-shrink-0 flex-col border-r pr-1"
      >
        <!-- 上方：用户、平台选择和批量操作 -->
        <div class="flex items-center justify-between pb-1">
          <div class="flex items-center gap-1">
            <Select
              v-model:value="selectedUser"
              :options="userOptions"
              show-search
              :filter-option="
                (input: any, option: any) =>
                  option.label.toLowerCase().includes(input.toLowerCase())
              "
              placeholder="用户"
              style="width: 70px"
              allow-clear
              @change="onUserChange"
            />
            <Popover
              v-model:open="configPopoverOpen"
              trigger="click"
              placement="bottomLeft"
            >
              <template #content>
                <div class="w-64">
                  <!-- 配置列表 -->
                  <div class="max-h-60 overflow-y-auto">
                    <div
                      v-for="config in configOptions"
                      :key="config.id"
                      class="group flex items-center justify-between rounded px-2 py-1.5 hover:bg-gray-100"
                      :class="{
                        'bg-blue-50': selectedConfigId === config.id,
                      }"
                    >
                      <template v-if="editingConfigId === config.id">
                        <Input
                          v-model:value="editConfigName"
                          class="mr-1 flex-1"
                          @press-enter="saveEditConfig"
                        />
                        <Button
                          type="text"
                          class="!w-6 !min-w-0 !p-0 text-green-500"
                          @click="saveEditConfig"
                        >
                          <span
                            class="icon-[ant-design--check-outlined] text-sm"
                          ></span>
                        </Button>
                        <Button
                          type="text"
                          class="!w-6 !min-w-0 !p-0"
                          @click="cancelEditConfig"
                        >
                          <span
                            class="icon-[ant-design--close-outlined] text-sm"
                          ></span>
                        </Button>
                      </template>
                      <template v-else>
                        <span
                          class="flex-1 cursor-pointer truncate"
                          @click="selectConfig(config)"
                        >
                          {{ config.name }}
                        </span>
                        <div
                          class="ml-1 flex items-center opacity-0 group-hover:opacity-100"
                        >
                          <Button
                            type="text"
                            class="!w-6 !min-w-0 !p-0"
                            @click="startEditConfig(config)"
                          >
                            <span
                              class="icon-[ant-design--edit-outlined] text-sm"
                            ></span>
                          </Button>
                          <Popconfirm
                            :title="`确定删除「${config.name}」？`"
                            ok-text="确定"
                            cancel-text="取消"
                            @confirm="handleDeleteConfig(config)"
                          >
                            <Button
                              type="text"
                              danger
                              class="!w-6 !min-w-0 !p-0"
                            >
                              <span
                                class="icon-[ant-design--delete-outlined] text-sm"
                              ></span>
                            </Button>
                          </Popconfirm>
                        </div>
                      </template>
                    </div>
                    <div
                      v-if="configOptions.length === 0"
                      class="py-4 text-center text-gray-400"
                    >
                      暂无配置
                    </div>
                  </div>
                  <!-- 添加新配置 -->
                  <div class="mt-2 flex items-center gap-1 border-t pt-2">
                    <Input
                      v-model:value="newConfigName"
                      placeholder="新配置名称"
                      class="flex-1"
                      @press-enter="handleAddConfig"
                    />
                    <Button
                      type="primary"
                      :loading="configLoading"
                      @click="handleAddConfig"
                    >
                      添加
                    </Button>
                  </div>
                </div>
              </template>
              <Button
                :loading="configLoading"
                class="flex max-w-32 items-center gap-1"
              >
                <span class="truncate">{{
                  selectedConfigName || '选择配置'
                }}</span>
                <span
                  v-if="selectedConfigId && !configLoading"
                  class="icon-[ant-design--close-circle-outlined] text-gray-400 hover:text-gray-600"
                  @click.stop="clearConfigSelection"
                ></span>
                <span
                  v-else-if="!configLoading"
                  class="icon-[ant-design--down-outlined]"
                ></span>
              </Button>
            </Popover>
            <Tooltip title="刷新">
              <Button
                @click="loadTreeData(true)"
                :loading="loading"
                class="flex w-12 items-center justify-center"
              >
                <span class="icon-[ant-design--reload-outlined] text-lg"></span>
              </Button>
            </Tooltip>
          </div>
          <!-- 批量操作按钮 -->
          <div class="flex items-center">
            <Button.Group>
              <Button
                @click="batchApplyTags"
                :loading="loading"
                :disabled="
                  selectedMap.size === 0 || selectedTreeKeys.length === 0
                "
                class="flex w-16 items-center justify-center !px-2"
              >
                <span class="icon-[ant-design--check-outlined]"></span>
                <span class="ml-1">添加</span>
              </Button>
              <Tooltip title="去除☑️选中的标签，不会去除◼️半选的标签">
                <Button
                  @click="batchRemoveTags"
                  :loading="loading"
                  :disabled="
                    selectedMap.size === 0 || selectedTreeKeys.length === 0
                  "
                  class="flex w-16 items-center justify-center !px-2"
                >
                  <span class="icon-[ant-design--close-outlined]"></span>
                  <span class="ml-1">去除</span>
                </Button>
              </Tooltip>
            </Button.Group>
          </div>
        </div>

        <div class="relative flex-1 overflow-hidden">
          <!-- 加载遮罩 -->
          <div
            v-if="loading"
            class="absolute inset-0 z-10 flex items-center justify-center bg-white/60"
          >
            <div class="flex items-center space-x-2">
              <div
                class="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-500"
              ></div>
              <span>加载中...</span>
            </div>
          </div>
          <!-- 内容区域 -->
          <div class="h-full overflow-x-auto">
            <div class="h-full min-w-max space-y-4">
              <div
                v-if="(treeData?.length || 0) === 0 && !loading"
                class="py-8 text-center"
              >
                <Button
                  :loading="loading"
                  :disabled="!selectedUser || !selectedConfigId"
                  @click="addNode()"
                  :title="
                    !selectedUser || !selectedConfigId
                      ? '请先选择用户和配置'
                      : ''
                  "
                >
                  <span class="icon-[ant-design--plus-outlined] mr-1"></span>
                  初始化
                </Button>
              </div>

              <div v-else class="">
                <Tree
                  :tree-data="treeData"
                  :show-line="true"
                  :show-icon="false"
                  checkable
                  v-model:checked-keys="selectedTreeKeys"
                  v-model:expanded-keys="expandedKeys"
                >
                  <template
                    #title="{
                      title,
                      key,
                      level,
                      parent_id,
                      real_name,
                      config_id,
                    }"
                  >
                    <div class="group flex items-center justify-between">
                      <div class="flex flex-1 items-center">
                        <span
                          class="bg-primary/10 text-primary inline-flex h-5 w-5 items-center justify-center rounded text-xs font-medium"
                        >
                          {{ level }}
                        </span>
                        <span v-if="!editingKey || editingKey !== key">
                          {{ title }}
                        </span>
                        <Input
                          v-else
                          v-model:value="editValue"
                          class="max-w-32"
                          @blur="saveEdit(key)"
                          @press-enter="saveEdit(key)"
                          @click.stop
                        />
                      </div>
                      <div class="ml-2 flex opacity-0 group-hover:opacity-100">
                        <Button
                          type="text"
                          :disabled="false"
                          @click.stop="
                            editingKey === key
                              ? cancelEdit()
                              : editNode(key, title)
                          "
                          :title="editingKey === key ? '取消编辑' : '编辑节点'"
                          class="flex items-center justify-center"
                        >
                          <span
                            :class="
                              editingKey === key
                                ? 'icon-[ant-design--close-outlined]'
                                : 'icon-[ant-design--edit-outlined]'
                            "
                          ></span>
                        </Button>
                        <Button
                          type="text"
                          :disabled="false"
                          @click.stop="
                            addNode(key, level + 1, real_name, config_id)
                          "
                          title="添加子节点"
                          class="flex items-center justify-center"
                        >
                          <span
                            class="icon-[ant-design--arrow-down-outlined]"
                          ></span>
                        </Button>
                        <Button
                          type="text"
                          :disabled="false"
                          @click.stop="
                            addNode(parent_id, level, real_name, config_id)
                          "
                          title="添加同级节点"
                          class="flex items-center justify-center"
                        >
                          <span class="icon-[ant-design--plus-outlined]"></span>
                        </Button>
                        <Popconfirm
                          :open="deletingKey === key"
                          :title="`确定删除「${title}」？`"
                          ok-text="确定"
                          cancel-text="取消"
                          :ok-button-props="{ loading }"
                          @update:open="
                            (open: boolean) => (deletingKey = open ? key : '')
                          "
                          @confirm="deleteNode(key)"
                        >
                          <Button
                            type="text"
                            danger
                            title="删除节点"
                            class="flex items-center justify-center"
                            @click.stop
                          >
                            <span
                              class="icon-[ant-design--delete-outlined]"
                            ></span>
                          </Button>
                        </Popconfirm>
                      </div>
                    </div>
                  </template>
                </Tree>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：图片卡片列表 -->
      <div class="tag-result-panel flex min-w-0 flex-1 flex-col">
        <!-- 筛选操作行 -->
        <div class="mb-1 flex items-center justify-between">
          <div class="flex flex-1 items-center gap-1">
            <Select
              v-model:value="rightSelectedDepartment"
              :options="departmentOptions"
              mode="multiple"
              placeholder="部门"
              style="min-width: 80px; max-width: 150px"
              allow-clear
              max-tag-count="responsive"
              :max-tag-placeholder="buildMaxTagPlaceholder"
            />
            <Select
              v-model:value="rightSelectedUser"
              :options="userOptions"
              show-search
              :filter-option="
                (input: any, option: any) =>
                  option.label.toLowerCase().includes(input.toLowerCase())
              "
              placeholder="用户"
              style="width: 70px"
              allow-clear
            />
            <PlatformSelect
              v-model:value="rightSelectedPlatform"
              placeholder="平台"
              style="width: 100px"
              max-tag-count="responsive"
            />
            <DateRangePicker
              v-model:value="dateRange"
              width="180px"
              format="MM-dd"
              @update:value="() => fetchMaterials(true)"
            />
            <Tooltip
              :title="
                tableDateField === 'date'
                  ? '当前按成效日期统计，点击后切换为按创建时间统计'
                  : '当前按创建时间统计，点击后切换为按成效日期统计'
              "
            >
              <Switch
                :checked="tableDateField === 'date'"
                @change="
                  (checked: boolean) => {
                    tableDateField = checked ? 'date' : 'create_time';
                  }
                "
                checked-children="成效"
                un-checked-children="创建"
              />
            </Tooltip>
            <InputNumber
              v-model:value="minSpent"
              placeholder="最小花费"
              style="width: 80px"
              :min="0"
              :precision="0"
            />
            <Switch
              :checked="tagFilterCondition === 'excludes'"
              @change="
                (checked, _e) => {
                  tagFilterCondition = checked ? 'excludes' : 'contains';
                }
              "
              checked-children="排除"
              un-checked-children="包含"
            />
            <TreeSelect
              v-model:value="selectedTagsForFilter"
              :tree-data="getTreeSelectData()"
              :multiple="true"
              :show-checked-strategy="TreeSelect.SHOW_ALL"
              placeholder="选择标签"
              class="max-w-xs flex-1"
              :dropdown-style="{ maxHeight: '400px', overflow: 'auto' }"
              max-tag-count="responsive"
              :max-tag-placeholder="buildMaxTagPlaceholder"
              :virtual="false"
              tree-default-expand-all
              allow-clear
            />
            <Tooltip title="查询/刷新">
              <Button
                @click="fetchMaterials(true)"
                :loading="cardLoading"
                class="flex items-center justify-center"
              >
                <span class="icon-[ant-design--search-outlined]"></span>
                <span class="icon-[ant-design--reload-outlined] ml-1"></span>
              </Button>
            </Tooltip>
            <!-- 数据按钮 -->
            <Button @click="openTableModal"> 查看标签统计数据 </Button>
          </div>
          <div class="flex items-center gap-1">
            <!-- 模式切换开关 -->
            <Tooltip>
              <template #title>
                <div v-if="!isPreviewMode">
                  选择模式：拖拽框选 | Ctrl+A 全选 | Esc 清空
                </div>
                <div v-else>预览模式：点击图片查看详情，可单选但无框选</div>
              </template>
              <Switch
                :checked="!isPreviewMode"
                @change="
                  (checked: any) => {
                    isPreviewMode = !checked;
                  }
                "
                checked-children="选择"
                un-checked-children="预览"
              />
            </Tooltip>
            <!-- 选择操作按钮组 -->
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

        <div class="relative flex min-h-0 flex-1 flex-col">
          <!-- 全局加载遮罩 - 移到外层以覆盖整个区域 -->
          <div
            v-if="cardLoading"
            class="absolute inset-0 z-20 flex items-center justify-center bg-white/60"
          >
            <div class="flex items-center space-x-2">
              <div
                class="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
              ></div>
              <span class="text-lg">加载中...</span>
            </div>
          </div>

          <!-- 卡片视图 -->
          <div
            v-if="!cardLoading && materials.length === 0"
            class="flex flex-1 flex-col items-center justify-center py-16 text-gray-400"
          >
            <span
              class="icon-[ant-design--inbox-outlined] mb-3 text-5xl"
            ></span>
            <span class="text-sm">暂无数据</span>
          </div>
          <div
            v-else
            ref="gridContainer"
            class="relative grid w-full grid-cols-2 items-start gap-1 overflow-y-auto px-1 py-0 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6"
            :class="{
              'select-none': !isPreviewMode,
              'cursor-crosshair': isSelecting && !isPreviewMode,
              'border-2 border-dashed border-blue-200':
                !isPreviewMode && materials.length > 0,
            }"
            @mousedown="startSelection"
          >
            <!-- 框选视觉效果 -->
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
              @update:checked="(v) => toggleSelect(item.id, v, item.basename)"
            />
          </div>
        </div>

        <div class="mt-1 flex justify-end">
          <Pagination
            :current="page"
            :page-size="pageSize"
            :page-size-options="['50', '100', '200', '400']"
            :total="total"
            show-size-changer
            :show-total="(total) => `共 ${total} 条`"
            @change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <MaterialCard
      ref="previewCardRef"
      :item="{}"
      :items="materials"
      :checked="false"
      preview-only
    />

    <!-- 数据统计 Modal -->
    <TableModal>
      <template #title>
        <div class="flex items-center">
          <span class="mr-3">数据统计</span>
          <Radio.Group
            v-model:value="originMode"
            style="font-weight: normal"
            :disabled="tableViewLoading"
            @change="refreshTableData"
          >
            <Radio.Button :value="false">清洗数据</Radio.Button>
            <Radio.Button :value="true">原始数据</Radio.Button>
          </Radio.Group>
          <Button
            class="ml-1"
            @click="refreshTableData"
            :loading="tableViewLoading"
          >
            刷新
          </Button>
          <Button class="ml-1" :loading="exportLoading" @click="handleExport">
            导出
          </Button>
        </div>
      </template>
      <div class="h-full">
        <Table
          v-if="tableViewData.length > 0"
          :columns="tableViewColumns"
          :data-source="tableViewData"
          :loading="tableViewLoading"
          :pagination="false"
          :expanded-row-keys="expandedRowKeys"
          :scroll="{ y: 316 }"
          bordered
          size="small"
          row-key="key"
          :default-expand-all-rows="true"
          @expand="handleTableExpand"
        />
        <div v-else class="py-8 text-center text-gray-400">
          {{ tableViewLoading ? '加载中...' : '暂无数据' }}
        </div>
      </div>
    </TableModal>
  </div>
</template>

<style scoped>
@media (max-width: 767px) {
  .tag-editor-page {
    height: auto !important;
    min-height: 100%;
  }

  .tag-editor-layout {
    flex-direction: column;
    overflow: visible;
  }

  .tag-tree-panel {
    width: 100%;
    min-height: 260px;
    max-height: 360px;
    flex: none;
    padding-right: 0;
    padding-bottom: 4px;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }

  .tag-result-panel {
    width: 100%;
    min-height: 560px;
  }

  .tag-result-panel > :first-child {
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
