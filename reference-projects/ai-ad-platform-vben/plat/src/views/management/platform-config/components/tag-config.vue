<script lang="ts" setup>
import type {
  MaterialCategoryContentItem,
  PlatformConfigItem,
  TagContent,
  TagParentCategory,
  TagSubCategory,
} from '#/api/management/platform-config';

import { computed, nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useVbenForm, useVbenModal } from '@vben/common-ui';

import {
  Button,
  Card,
  Image,
  Input,
  message,
  Popconfirm,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import {
  createMaterialCategory,
  createMaterialContent,
  createMaterialSubCategory,
  deleteMaterialCategory,
  deleteMaterialContent,
  deleteMaterialSubCategory,
  getMaterialCategorySubCategoryContents,
  getTagParentCategoryList,
  updateMaterialCategory,
  updateMaterialContent,
  updateMaterialSubCategory,
} from '#/api/management/platform-config';

import { usePlatformFromRoute } from './usePlatformFromRoute';

interface CategoryItem {
  description?: string;
  enabled?: boolean;
  id: string;
  name: string;
}

const props = defineProps<{
  platforms: PlatformConfigItem[];
}>();
const route = useRoute();
const router = useRouter();

const selectedPlatform = ref<string | undefined>('');
const platformOptions = ref<Array<{ label: string; value: string }>>([]);
const platformSearchText = ref<string>('');

const platformListRef = computed(() => {
  return props.platforms.map((p) => p._id || '').filter(Boolean);
});

const filteredPlatformOptions = computed(() => {
  if (!platformSearchText.value.trim()) {
    return platformOptions.value;
  }
  const searchLower = platformSearchText.value.toLowerCase().trim();
  return platformOptions.value.filter((platform) =>
    platform.label.toLowerCase().includes(searchLower),
  );
});

// 用于跟踪最新的请求，防止竞态条件
let loadCategoryRequestId = 0;
let loadContentRequestId = 0;

const parentCategoryList = ref<CategoryItem[]>([]);
const selectedParentKey = ref<string>('');
const fullParentCategories = ref<
  (TagParentCategory & { children?: TagSubCategory[] })[]
>([]);

const subCategoryList = ref<CategoryItem[]>([]);
const selectedSubKey = ref<string>('');

const contentList = ref<MaterialCategoryContentItem[]>([]);
const loadingTree = ref(false);
const loadingSub = ref(false);
const loadingContent = ref(false);
const loadingSave = ref(false);
const loadingAddParent = ref(false);
const loadingAddSub = ref(false);
const loadingAddContent = ref(false);

const uploadFile = ref<File | null>(null);
const previewUrl = ref<string>('');
const previewFileType = ref<'image' | 'video'>('image');

const currentEditParentCategory = ref<null | TagParentCategory>(null);
const currentEditSubCategory = ref<null | TagSubCategory>(null);
const currentEditContent = ref<
  null | (TagContent & { type?: string; url?: string })
>(null);

async function loadCategoryList() {
  if (!selectedPlatform.value) {
    return;
  }

  const currentRequestId = ++loadCategoryRequestId;

  try {
    const res = await getTagParentCategoryList(selectedPlatform.value);

    if (currentRequestId !== loadCategoryRequestId) {
      return;
    }

    let categories: any[] = [];
    if (Array.isArray(res)) {
      categories = res;
    } else {
      const data = (res as any)?.data;
      categories = Array.isArray(data) ? data : [];
    }

    fullParentCategories.value = categories;

    parentCategoryList.value = categories.map((parent: any) => ({
      id: parent.id,
      name: parent.name,
      description: parent.description || '',
      enabled: parent.enabled ?? true,
    }));
  } catch {
    if (currentRequestId !== loadCategoryRequestId) {
      return;
    }
    parentCategoryList.value = [];
    fullParentCategories.value = [];
  } finally {
    if (currentRequestId === loadCategoryRequestId) {
      loadingTree.value = false;
    }
  }
}

function handleParentCategoryClick(item: CategoryItem) {
  if (selectedParentKey.value === item.id) {
    return;
  }

  loadingSub.value = true;
  loadingContent.value = false;
  selectedParentKey.value = item.id;
  selectedSubKey.value = '';
  subCategoryList.value = [];
  contentList.value = [];

  nextTick(() => {
    const parent = fullParentCategories.value.find((p) => p.id === item.id);
    if (parent?.children) {
      subCategoryList.value = parent.children.map((sub: any) => ({
        id: sub.id,
        name: sub.name,
        description: sub.description || '',
        enabled: sub.enabled ?? true,
      }));
    }
    loadingSub.value = false;
  });
}

async function handleSubCategoryClick(item: CategoryItem) {
  if (selectedSubKey.value === item.id) {
    return;
  }

  loadingContent.value = true;
  selectedSubKey.value = item.id;
  contentList.value = [];

  await loadContentList();
}

async function loadContentList() {
  if (!selectedSubKey.value) {
    return;
  }

  // 生成新的请求ID
  const currentRequestId = ++loadContentRequestId;

  try {
    const res = await getMaterialCategorySubCategoryContents(
      selectedSubKey.value,
    );

    if (currentRequestId !== loadContentRequestId) {
      return;
    }

    const data = (res as any)?.data || res;
    const contents = (data?.contents || []) as MaterialCategoryContentItem[];
    contentList.value = contents;
  } catch {
    if (currentRequestId !== loadContentRequestId) {
      return;
    }
    contentList.value = [];
  } finally {
    if (currentRequestId === loadContentRequestId) {
      loadingContent.value = false;
    }
  }
}

async function handlePlatformChange(value: any) {
  const platformId = typeof value === 'string' ? value : String(value || '');

  loadingTree.value = true;
  loadingSub.value = false;
  loadingContent.value = false;
  parentCategoryList.value = [];
  fullParentCategories.value = [];
  selectedParentKey.value = '';
  subCategoryList.value = [];
  selectedSubKey.value = '';
  contentList.value = [];

  if (!platformId) {
    loadingTree.value = false;
    return;
  }

  selectedPlatform.value = platformId;

  // 更新URL参数
  router.push({
    query: {
      ...route.query,
      platform: platformId,
    },
  });

  await loadCategoryList();
}

function handlePlatformSearchChange(e: Event) {
  const target = e.target as HTMLInputElement;
  platformSearchText.value = target.value;
}

function convertToTagContent(
  content: MaterialCategoryContentItem,
): TagContent & { type?: string; url?: string } {
  return {
    id: content.id,
    name: content.name,
    value: content.text,
    url: content.url,
    type: content.type,
    description: content.remark || '',
    sub_category_id: selectedSubKey.value,
    parent_category_id: selectedParentKey.value,
    product_id: selectedPlatform.value,
    enabled: true,
    sort_order: 0,
  } as TagContent & { type?: string; url?: string };
}

function getParentCategory(id: string): TagParentCategory | undefined {
  return fullParentCategories.value.find((p) => p.id === id);
}

function getSubCategory(
  parentId: string,
  subId: string,
): TagSubCategory | undefined {
  const parent = fullParentCategories.value.find((p) => p.id === parentId);
  return parent?.children?.find((s: any) => s.id === subId);
}

const [ParentCategoryModal, parentCategoryModalApi] = useVbenModal({
  onConfirm: async () => {
    await saveParentCategory();
  },
});

const [ParentCategoryForm, parentCategoryFormApi] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: '节点名称',
      component: 'Input',
      rules: 'required',
      componentProps: { placeholder: '请输入节点名称' },
    },
    {
      fieldName: 'description',
      label: '描述',
      component: 'Textarea',
      componentProps: { placeholder: '请输入描述', rows: 3 },
    },
  ],
});

async function openParentCategoryModal(parentCategory?: TagParentCategory) {
  currentEditParentCategory.value = parentCategory || null;

  if (parentCategory) {
    parentCategoryModalApi.setState({ title: '编辑一级分类' });
  } else {
    parentCategoryModalApi.setState({ title: '添加一级分类' });
  }

  parentCategoryModalApi.open();

  await nextTick();

  if (parentCategory) {
    parentCategoryFormApi.setValues({
      name: parentCategory.name,
      description: parentCategory.description || '',
    });
  } else {
    parentCategoryFormApi.resetForm();
  }
}

async function saveParentCategory() {
  loadingSave.value = true;
  try {
    const formData = parentCategoryFormApi.form.values;

    if (currentEditParentCategory.value?.id) {
      await updateMaterialCategory(currentEditParentCategory.value.id, {
        name: formData.name,
        description: formData.description || undefined,
      });
      message.success('更新成功');
    } else {
      await createMaterialCategory(selectedPlatform.value!, {
        name: formData.name,
        description: formData.description || undefined,
      });
      message.success('添加成功');
    }
    parentCategoryModalApi.close();
    loadingAddParent.value = true;
    await loadCategoryList();
  } finally {
    loadingSave.value = false;
    loadingAddParent.value = false;
  }
}

async function handleDeleteParentCategory(parentCategory: TagParentCategory) {
  try {
    await deleteMaterialCategory(selectedPlatform.value!, parentCategory.id!);
    message.success('删除成功');

    if (selectedParentKey.value === parentCategory.id) {
      selectedParentKey.value = '';
      selectedSubKey.value = '';
      subCategoryList.value = [];
      contentList.value = [];
    }

    await loadCategoryList();
  } catch {}
}

const [SubCategoryModal, subCategoryModalApi] = useVbenModal({
  onConfirm: async () => {
    await saveSubCategory();
  },
});

const [SubCategoryForm, subCategoryFormApi] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: '节点名称',
      component: 'Input',
      rules: 'required',
      componentProps: { placeholder: '请输入节点名称' },
    },
    {
      fieldName: 'description',
      label: '描述',
      component: 'Textarea',
      componentProps: { placeholder: '请输入描述', rows: 3 },
    },
  ],
});

async function openSubCategoryModal(subCategory?: TagSubCategory) {
  if (!subCategory && !selectedParentKey.value) {
    message.warning('请先选择一级分类');
    return;
  }

  currentEditSubCategory.value = subCategory || null;

  if (subCategory) {
    subCategoryModalApi.setState({ title: '编辑二级分类' });
  } else {
    subCategoryModalApi.setState({ title: '添加二级分类' });
  }

  subCategoryModalApi.open();

  await nextTick();

  if (subCategory) {
    subCategoryFormApi.setValues({
      name: subCategory.name,
      description: subCategory.description || '',
    });
  } else {
    subCategoryFormApi.resetForm();
  }
}

async function saveSubCategory() {
  loadingSave.value = true;
  try {
    const formData = subCategoryFormApi.form.values;

    if (currentEditSubCategory.value?.id) {
      await updateMaterialSubCategory(
        selectedParentKey.value,
        currentEditSubCategory.value.id,
        { name: formData.name, description: formData.description || undefined },
      );
      message.success('更新成功');
    } else {
      await createMaterialSubCategory(selectedParentKey.value, {
        name: formData.name,
        description: formData.description || undefined,
      });
      message.success('添加成功');
    }
    subCategoryModalApi.close();
    loadingAddSub.value = true;
    await loadCategoryList();
    if (selectedParentKey.value) {
      const parent = fullParentCategories.value.find(
        (p) => p.id === selectedParentKey.value,
      );
      if (parent?.children) {
        subCategoryList.value = parent.children.map((sub: any) => ({
          id: sub.id,
          name: sub.name,
          description: sub.description || '',
          enabled: sub.enabled ?? true,
        }));
      }
    }
  } finally {
    loadingSave.value = false;
    loadingAddSub.value = false;
  }
}

async function handleDeleteSubCategory(subCategory: TagSubCategory) {
  try {
    await deleteMaterialSubCategory(selectedParentKey.value, subCategory.id!);
    message.success('删除成功');

    if (selectedSubKey.value === subCategory.id) {
      selectedSubKey.value = '';
      contentList.value = [];
    }

    subCategoryList.value = [];

    loadingAddSub.value = true;
    loadingSub.value = true;

    await loadCategoryList();

    if (selectedParentKey.value) {
      const parent = fullParentCategories.value.find(
        (p) => p.id === selectedParentKey.value,
      );
      if (parent?.children) {
        subCategoryList.value = parent.children.map((sub: any) => ({
          id: sub.id,
          name: sub.name,
          description: sub.description || '',
          enabled: sub.enabled ?? true,
        }));
      }
    }
  } catch {
  } finally {
    loadingAddSub.value = false;
    loadingSub.value = false;
  }
}

const [ContentModal, contentModalApi] = useVbenModal({
  onConfirm: async () => {
    await saveContent();
  },
});

const [ContentForm, contentFormApi] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: '名称',
      component: 'Input',
      rules: 'required',
      componentProps: { placeholder: '请输入名称' },
    },
    {
      fieldName: 'description',
      label: '备注',
      component: 'Textarea',
      componentProps: { placeholder: '请输入备注', rows: 3 },
    },
  ],
});

async function openContentModal(
  row?: TagContent & { type?: string; url?: string },
) {
  if (!row && !selectedSubKey.value) {
    message.warning('请先选择二级分类');
    return;
  }

  currentEditContent.value = row || null;
  uploadFile.value = null;
  previewUrl.value = '';
  previewFileType.value = 'image';

  if (row) {
    contentModalApi.setState({ title: '编辑内容' });
    if (row.url) {
      previewUrl.value = row.url;
      // 根据接口返回的type字段判断文件类型
      previewFileType.value = row.type === 'video' ? 'video' : 'image';
    }
  } else {
    contentModalApi.setState({ title: '添加内容' });
  }

  contentModalApi.open();

  await nextTick();

  if (row) {
    contentFormApi.setValues({
      name: row.name,
      description: row.description || '',
    });
  } else {
    contentFormApi.resetForm();
  }
}

async function saveContent() {
  loadingSave.value = true;
  try {
    const formData = contentFormApi.form.values;

    if (currentEditContent.value?.id) {
      const updateFormData = new FormData();
      updateFormData.append('name', formData.name);
      if (formData.description) {
        updateFormData.append('remark', formData.description);
      }
      if (uploadFile.value) {
        updateFormData.append('file', uploadFile.value);
      }

      await updateMaterialContent(
        selectedSubKey.value,
        currentEditContent.value.id,
        updateFormData,
      );
      message.success('更新成功');
    } else {
      const createFormData = new FormData();
      if (uploadFile.value) {
        createFormData.append('file', uploadFile.value);
      }
      createFormData.append('name', formData.name);
      createFormData.append('product_id', 'default');
      createFormData.append('category_id', 'default');
      if (formData.description) {
        createFormData.append('remark', formData.description);
      }

      await createMaterialContent(selectedSubKey.value, createFormData);
      message.success('创建成功');
    }
    contentModalApi.close();
    loadingAddContent.value = true;
    await loadContentList();
  } finally {
    loadingSave.value = false;
    loadingAddContent.value = false;
  }
}

async function handleDeleteContent(
  row: TagContent & { type?: string; url?: string },
) {
  try {
    await deleteMaterialContent(selectedSubKey.value, row.id!);
    message.success('删除成功');
    await loadContentList();
  } catch {}
}

function handleModalFileChange(info: any) {
  const file = info.file.originFileObj || info.file;
  if (!file) return;

  const validImageTypes = [
    'png',
    'jpg',
    'jpeg',
    'gif',
    'bmp',
    'webp',
    'svg',
    'ico',
    'avif',
    'heic',
    'tiff',
  ];
  const validVideoTypes = new Set([
    'avi',
    'flv',
    'mkv',
    'mov',
    'mp4',
    'webm',
    'wmv',
  ]);

  const fileExt = file.name.split('.').pop()?.toLowerCase();
  const isValidFile =
    fileExt &&
    (validImageTypes.includes(fileExt) || validVideoTypes.has(fileExt));

  if (!isValidFile) {
    message.error('不支持的文件格式');
    return;
  }

  const maxSize = 10 * 1024 * 1024;
  if (file.size > maxSize) {
    message.error('文件大小不能超过 10MB');
    return;
  }

  uploadFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  previewFileType.value =
    fileExt && validVideoTypes.has(fileExt) ? 'video' : 'image';
}

async function initPlatformData() {
  if (props.platforms.length === 0) return;

  platformOptions.value = props.platforms.map((p) => ({
    label: p._id || '',
    value: p._id || '',
  }));

  const platformFromRoute = route.query.platform as string;
  const targetPlatform =
    platformFromRoute &&
    platformOptions.value.some((p) => p.value === platformFromRoute)
      ? platformFromRoute
      : '';

  if (targetPlatform) {
    if (selectedPlatform.value === targetPlatform) {
      return;
    }

    loadingTree.value = true;
    parentCategoryList.value = [];
    fullParentCategories.value = [];
    selectedParentKey.value = '';
    subCategoryList.value = [];
    selectedSubKey.value = '';
    contentList.value = [];

    selectedPlatform.value = targetPlatform;
    await loadCategoryList();
  }
}

watch(
  () => props.platforms,
  async (newPlatforms) => {
    if (newPlatforms && newPlatforms.length > 0) {
      await initPlatformData();
    }
  },
  { deep: true, immediate: true },
);

usePlatformFromRoute({
  selectedPlatform,
  onPlatformChange: async (platformId) => {
    if (selectedPlatform.value !== platformId) {
      await handlePlatformChange(platformId);
    }
  },
  immediate: false,
});
</script>

<template>
  <div class="tag-container p-4">
    <div
      class="grid min-w-0 items-stretch gap-4 md:grid-cols-2 xl:grid-cols-[12rem_16rem_16rem_minmax(0,1fr)]"
    >
      <div class="min-w-0">
        <Card class="h-full">
          <template #title>
            <div class="text-sm font-medium">平台名称</div>
          </template>
          <div class="tag-panel-scroll flex flex-col">
            <div class="mb-3 flex-shrink-0">
              <Input
                v-model="platformSearchText"
                placeholder="搜索平台"
                allow-clear
                @change="handlePlatformSearchChange"
              >
                <template #prefix>
                  <span class="icon-[ant-design--search-outlined]"></span>
                </template>
              </Input>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto pr-[8px]">
              <div
                v-if="platformOptions.length === 0"
                class="flex h-48 items-center justify-center text-gray-400"
              >
                暂无平台
              </div>
              <div
                v-else-if="filteredPlatformOptions.length === 0"
                class="flex h-48 items-center justify-center text-gray-400"
              >
                未找到匹配的平台
              </div>
              <div
                v-for="platform in filteredPlatformOptions"
                :key="platform.value"
                class="mb-2 cursor-pointer rounded border px-3 py-2 transition-all"
                :class="[
                  selectedPlatform === platform.value
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50',
                ]"
                @click="handlePlatformChange(platform.value)"
              >
                <span class="text-sm">{{ platform.label }}</span>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div class="min-w-0">
        <Card class="h-full">
          <template #title>
            <div class="text-sm font-medium">一级分类</div>
          </template>
          <template #extra>
            <Button
              type="primary"
              :disabled="!selectedPlatform"
              :loading="loadingAddParent"
              @click="openParentCategoryModal()"
            >
              <template v-if="loadingAddParent"> 加载中 </template>
              <template v-else> 添加 </template>
            </Button>
          </template>
          <div class="tag-panel-scroll overflow-y-auto">
            <div
              v-if="loadingTree"
              class="flex h-48 flex-col items-center justify-center text-gray-400"
            >
              <span
                class="icon-[line-md--loading-loop] mb-2 text-3xl text-blue-500"
              ></span>
              <span class="text-sm">加载中...</span>
            </div>
            <div
              v-else-if="parentCategoryList.length === 0"
              class="flex h-48 items-center justify-center text-gray-400"
            >
              暂无分类，请添加
            </div>
            <div
              v-for="item in parentCategoryList"
              :key="item.id"
              class="group relative mb-2 cursor-pointer rounded border px-3 py-2 transition-all"
              :class="[
                selectedParentKey === item.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50',
                item.enabled === false && 'cursor-not-allowed opacity-50',
              ]"
              @click="item.enabled !== false && handleParentCategoryClick(item)"
            >
              <div class="flex items-center justify-between">
                <div class="min-w-0 flex-1">
                  <span class="line-clamp-2 text-sm" :title="item.name">{{
                    item.name
                  }}</span>
                  <div
                    v-if="item.description"
                    class="mt-0.5 line-clamp-2 text-xs text-gray-400"
                    :title="item.description"
                  >
                    {{ item.description }}
                  </div>
                </div>
                <div
                  class="flex flex-shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                  @click.stop
                >
                  <Button
                    type="text"
                    title="编辑"
                    @click="
                      () => {
                        const cat = getParentCategory(item.id);
                        if (cat) openParentCategoryModal(cat);
                      }
                    "
                  >
                    <span
                      class="icon-[ant-design--edit-outlined] text-base"
                    ></span>
                  </Button>
                  <Popconfirm
                    title="确定要删除吗？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="
                      () => {
                        const cat = getParentCategory(item.id);
                        if (cat) handleDeleteParentCategory(cat);
                      }
                    "
                  >
                    <Button type="text" danger title="删除">
                      <span
                        class="icon-[ant-design--delete-outlined] text-base"
                      ></span>
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div class="min-w-0">
        <Card class="h-full">
          <template #title>
            <div class="text-sm font-medium">二级分类</div>
          </template>
          <template #extra>
            <Button
              type="primary"
              :disabled="!selectedParentKey"
              :loading="loadingAddSub"
              @click="openSubCategoryModal()"
            >
              <template v-if="loadingAddSub"> 加载中 </template>
              <template v-else> 添加 </template>
            </Button>
          </template>
          <div class="tag-panel-scroll overflow-y-auto">
            <div
              v-if="!selectedParentKey"
              class="flex h-48 items-center justify-center text-gray-400"
            >
              请先选择一级分类
            </div>
            <div
              v-else-if="loadingSub"
              class="flex h-48 flex-col items-center justify-center text-gray-400"
            >
              <span
                class="icon-[line-md--loading-loop] mb-2 text-3xl text-blue-500"
              ></span>
              <span class="text-sm">加载中...</span>
            </div>
            <div
              v-else-if="subCategoryList.length === 0"
              class="flex h-48 items-center justify-center text-gray-400"
            >
              暂无分类，请添加
            </div>
            <div
              v-for="item in subCategoryList"
              :key="item.id"
              class="group relative mb-2 cursor-pointer rounded border px-3 py-2 transition-all"
              :class="[
                selectedSubKey === item.id
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50',
                item.enabled === false && 'cursor-not-allowed opacity-50',
              ]"
              @click="item.enabled !== false && handleSubCategoryClick(item)"
            >
              <div class="flex items-center justify-between">
                <div class="min-w-0 flex-1">
                  <span class="line-clamp-2 text-sm" :title="item.name">{{
                    item.name
                  }}</span>
                  <div
                    v-if="item.description"
                    class="mt-0.5 line-clamp-2 text-xs text-gray-400"
                    :title="item.description"
                  >
                    {{ item.description }}
                  </div>
                </div>
                <div
                  class="flex flex-shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                  @click.stop
                >
                  <Button
                    type="text"
                    title="编辑"
                    @click="
                      () => {
                        const cat = getSubCategory(selectedParentKey, item.id);
                        if (cat) openSubCategoryModal(cat);
                      }
                    "
                  >
                    <span
                      class="icon-[ant-design--edit-outlined] text-base"
                    ></span>
                  </Button>
                  <Popconfirm
                    title="确定要删除吗？"
                    ok-text="确定"
                    cancel-text="取消"
                    @confirm="
                      () => {
                        const cat = getSubCategory(selectedParentKey, item.id);
                        if (cat) handleDeleteSubCategory(cat);
                      }
                    "
                  >
                    <Button type="text" danger title="删除">
                      <span
                        class="icon-[ant-design--delete-outlined] text-base"
                      ></span>
                    </Button>
                  </Popconfirm>
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div class="min-w-0 flex-1">
        <Card class="h-full">
          <template #title>
            <div class="text-sm font-medium">内容列表</div>
          </template>
          <template #extra>
            <Button
              type="primary"
              :disabled="!selectedSubKey"
              :loading="loadingAddContent"
              @click="openContentModal()"
            >
              <template v-if="loadingAddContent"> 加载中 </template>
              <template v-else> 添加内容 </template>
            </Button>
          </template>
          <div class="tag-panel-scroll overflow-y-auto">
            <div
              v-if="!selectedSubKey"
              class="flex h-full items-center justify-center text-gray-400"
            >
              请选择二级分类查看内容
            </div>
            <div
              v-else-if="loadingContent"
              class="flex h-full flex-col items-center justify-center text-gray-400"
            >
              <span
                class="icon-[line-md--loading-loop] mb-2 text-3xl text-blue-500"
              ></span>
              <span class="text-sm">加载中...</span>
            </div>
            <div
              v-else-if="contentList.length === 0"
              class="flex h-full items-center justify-center text-gray-400"
            >
              暂无内容，请添加
            </div>
            <div
              v-else
              class="grid grid-cols-1 gap-4 p-2 md:grid-cols-2 lg:grid-cols-2"
            >
              <Card
                v-for="content in contentList"
                :key="content.id"
                class="content-card relative"
              >
                <template #title>
                  <div class="flex items-center justify-between">
                    <span class="font-semibold">{{ content.name }}</span>
                    <div class="flex gap-2">
                      <Button
                        type="text"
                        title="编辑"
                        @click="openContentModal(convertToTagContent(content))"
                      >
                        <span class="icon-[ant-design--edit-outlined]"></span>
                      </Button>
                      <Popconfirm
                        title="确定要删除吗？"
                        ok-text="确定"
                        cancel-text="取消"
                        @confirm="
                          handleDeleteContent(convertToTagContent(content))
                        "
                      >
                        <Button type="text" danger title="删除">
                          <span
                            class="icon-[ant-design--delete-outlined]"
                          ></span>
                        </Button>
                      </Popconfirm>
                    </div>
                  </div>
                </template>
                <div class="flex gap-4">
                  <div
                    v-if="content.type === 'image' || content.type === 'video'"
                    class="flex-shrink-0"
                  >
                    <div
                      v-if="content.type === 'image'"
                      class="h-32 w-32 overflow-hidden rounded-lg border border-gray-200"
                    >
                      <Image
                        :src="content.url"
                        :alt="content.name"
                        class="h-full w-full object-cover"
                        :preview="true"
                      />
                    </div>
                    <div
                      v-else-if="content.type === 'video'"
                      class="h-32 w-32 overflow-hidden rounded-lg border border-gray-200"
                    >
                      <video
                        :src="content.url"
                        class="h-full w-full object-cover"
                        controls
                      ></video>
                    </div>
                    <div
                      v-else
                      class="flex h-32 w-32 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50"
                    >
                      <span class="text-gray-400">暂无内容</span>
                    </div>
                  </div>
                  <div
                    v-if="content.remark"
                    class="h-[220px] flex-1 overflow-y-auto text-sm text-gray-800"
                  >
                    {{ content.remark }}
                  </div>
                </div>
              </Card>
            </div>
          </div>
        </Card>
      </div>
    </div>

    <ParentCategoryModal :loading="loadingSave">
      <ParentCategoryForm />
    </ParentCategoryModal>

    <SubCategoryModal :loading="loadingSave">
      <SubCategoryForm />
    </SubCategoryModal>

    <ContentModal :loading="loadingSave">
      <ContentForm />
      <div class="mt-4">
        <div class="mb-2 text-sm font-medium">
          {{ currentEditContent ? '更新文件' : '上传文件' }}
        </div>

        <div v-if="currentEditContent && !uploadFile">
          <div v-if="previewUrl">
            <div class="relative w-full">
              <div
                class="flex h-48 w-full items-center justify-center rounded-lg border border-gray-200 bg-gray-50"
              >
                <video
                  v-if="previewFileType === 'video'"
                  :src="previewUrl"
                  class="max-h-48 w-auto rounded-lg object-contain"
                  controls
                ></video>
                <Image
                  v-else
                  :src="previewUrl"
                  :alt="currentEditContent.name"
                  class="max-h-48 w-auto rounded-lg object-contain"
                  :preview="true"
                />
              </div>
            </div>
          </div>
          <Upload
            :before-upload="() => false"
            accept="image/*,video/*"
            :show-upload-list="false"
            @change="handleModalFileChange"
          >
            <Button type="dashed" class="mt-4" block>更换文件</Button>
          </Upload>
        </div>

        <div v-if="!currentEditContent">
          <Upload
            v-if="!previewUrl"
            :before-upload="() => false"
            accept="image/*,video/*"
            :show-upload-list="false"
            @change="handleModalFileChange"
          >
            <div
              class="flex h-48 w-full cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 transition-colors hover:border-blue-400 hover:bg-blue-50"
            >
              <span
                class="icon-[ant-design--cloud-upload-outlined] mb-2 text-4xl text-blue-400"
              ></span>
              <p class="text-sm text-gray-600">点击或拖拽文件到此处上传</p>
              <p class="mt-1 text-xs text-gray-400">支持图片和视频，最大10MB</p>
            </div>
          </Upload>

          <div v-else>
            <div class="relative w-full">
              <div
                class="flex h-48 w-full items-center justify-center rounded-lg border border-gray-200 bg-gray-50"
              >
                <video
                  v-if="previewFileType === 'video'"
                  :src="previewUrl"
                  class="max-h-48 w-auto rounded-lg object-contain"
                  controls
                ></video>
                <Image
                  v-else
                  :src="previewUrl"
                  alt="预览图"
                  class="max-h-48 w-auto rounded-lg object-contain"
                  :preview="true"
                />
              </div>
            </div>
            <Upload
              :before-upload="() => false"
              accept="image/*,video/*"
              :show-upload-list="false"
              @change="handleModalFileChange"
              class="mt-2"
            >
              <Button type="dashed" class="mt-4" block>更换文件</Button>
            </Upload>
          </div>
        </div>

        <div v-if="currentEditContent && uploadFile">
          <div class="relative w-full">
            <div
              class="flex h-48 w-full items-center justify-center rounded-lg bg-gray-50"
            >
              <video
                v-if="previewFileType === 'video'"
                :src="previewUrl"
                class="max-h-48 w-auto rounded-lg object-contain"
                controls
              ></video>
              <Image
                v-else
                :src="previewUrl"
                :alt="uploadFile.name"
                class="max-h-48 w-auto rounded-lg object-contain"
                :preview="true"
              />
            </div>
          </div>
          <Upload
            :before-upload="() => false"
            accept="image/*,video/*"
            :show-upload-list="false"
            @change="handleModalFileChange"
            class="mt-2"
          >
            <Button>
              <span class="icon-[ant-design--reload-outlined] mr-1"></span>
              重新选择
            </Button>
          </Upload>
        </div>
      </div>
    </ContentModal>
  </div>
</template>

<style scoped>
.tag-panel-scroll {
  block-size: clamp(20rem, 56dvh, 36rem);
}

/* 修复按钮loading状态的opacity */
</style>
