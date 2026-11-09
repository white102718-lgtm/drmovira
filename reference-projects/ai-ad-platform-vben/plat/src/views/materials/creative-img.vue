<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Image,
  Input,
  InputNumber,
  message,
  Radio,
  Select,
  Upload,
} from 'ant-design-vue';

import {
  bulkUploadCreativeImages,
  checkCreativeImagesTaskStatus,
  getCreativeImageTasks,
  getImageUrl,
  getOriginalImageUrl,
  getRunningCreativeImageTasks,
  getThumbnailImgByFileIds,
  getUserOptions,
  uploadCreativeImages,
} from '#/api';
import { debounce } from '#/utils';

// 响应式数据
const promptText = ref('');
const imageNum = ref(2);
const taskType = ref(1); // 1: 多图修改, 2: 单图复刻
const modelType = ref('google'); // 模型选择: qwen(千问) 或 google(谷歌)
const isSubmitting = ref(false);
const fileList = ref<any[]>([]);

// 微调相关状态 - 用Map结构存储 filename -> base64Data
const fineTuneImages = ref<Record<string, string>>({});

// 重新生成的原图 - 独立存储
const regenerateImages = ref<Record<string, string>>({});

// 素材列表相关
const allMaterials = ref<any[]>([]);
const isLoadingMaterials = ref(false);
const pageSize = ref(15);
const searchFilename = ref('');
const searchRealName = ref('');
const currentPage = ref(1);
const hasMoreMaterials = ref(true);
const skipCount = ref(0);

// 用户选项
const userOptions = ref<Array<{ label: string; value: string }>>([]);

// 等待处理的图片列表
const runningMaterials = ref<any[]>([]);
const isLoadingRunning = ref(false);
const runningInfo = ref<{
  remaining_time: number;
  wait_num: number;
}>({
  wait_num: 0,
  remaining_time: 0,
});

// 获取用户选项
const fetchUserOptions = async () => {
  try {
    const res = await getUserOptions([
      'operator',
      'operator_leader',
      'creator',
    ]);
    userOptions.value = res.map((line: string) => ({
      label: line,
      value: line,
    }));
  } catch {}
};

const hasAllImages = computed(() => allMaterials.value.length > 0);

const hasRunningImages = computed(() => runningMaterials.value.length > 0);

// 计算上传文件的起始序号
const uploadStartIndex = computed(() => {
  return (
    Object.keys(regenerateImages.value).length +
    Object.keys(fineTuneImages.value).length
  );
});

const scrollToMaterials = (materials: any) => {
  // 如果是新数据，点击后移除 isNew 标识
  if (materials.isNew) {
    const originalItem = allMaterials.value.find(
      (item) => item._id === materials._id,
    );
    if (originalItem) {
      originalItem.isNew = false;
    }
  }
  const element = document.querySelector(`#materials-${materials._id}`);
  element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

// 处理上传变化 - 支持多文件
const handleUploadChange = async (info: any) => {
  fileList.value = [...info.fileList];
};

// 处理文件移除
const handleFileRemove = (file: any) => {
  return true; // 允许移除
};

const handleSubmit = async () => {
  try {
    isSubmitting.value = true;
    const formData = new FormData();

    for (const file of fileList.value) {
      if (file.originFileObj) {
        formData.append('files', file.originFileObj);
      }
    }

    formData.append('prompt', promptText.value.trim());
    formData.append('image_num', imageNum.value.toString());
    formData.append('task_type', taskType.value.toString());
    formData.append('model', modelType.value);

    // 如果有重新生成的原图，使用file_ids
    const regenerateFileIds = Object.keys(regenerateImages.value);
    if (regenerateFileIds.length > 0) {
      regenerateFileIds.forEach((fileId) => {
        formData.append('file_ids', fileId);
      });
    }

    // 如果有微调图片，添加unique_filenames参数
    const fineTuneFilenames = Object.keys(fineTuneImages.value);
    if (fineTuneFilenames.length > 0) {
      fineTuneFilenames.forEach((filename) => {
        formData.append('unique_filenames', filename);
      });
    }

    const result = await uploadCreativeImages(formData);
    message.success(result);
    // 上传成功后清空表单并刷新素材列表
    fileList.value = [];
    promptText.value = '';
    imageNum.value = 1;
    clearFineTune(); // 清空微调状态
    clearRegenerate(); // 清空重新生成状态
    await handleSearch();
  } finally {
    isSubmitting.value = false;
  }
};

// 重新生成图片
const handleRegenerate = async (materials: any) => {
  try {
    // 清空当前状态
    clearFineTune(); // 清空微调
    clearRegenerate(); // 清空重新生成
    fileList.value = []; // 清空上传文件列表

    // 将信息填入左侧表单
    promptText.value = materials.prompt;
    imageNum.value = materials.image_num;

    // 获取原图缩略图
    const fileIds = materials.file_ids.join(',');
    const thumbnailData = await getThumbnailImgByFileIds(fileIds);

    // 按照原始 file_ids 顺序添加到重新生成区域
    const orderedImages: Record<string, string> = {};
    materials.file_ids.forEach((fileId: string) => {
      if (thumbnailData[fileId]) {
        orderedImages[fileId] = thumbnailData[fileId] as string;
      }
    });
    regenerateImages.value = orderedImages;

    message.success(
      `已导入信息并加载${Object.keys(thumbnailData).length}张原图缩略图`,
    );
  } catch {}
};

// 清除重新生成图片
const clearRegenerate = () => {
  regenerateImages.value = {};
};

// 删除单个重新生成图片
const removeRegenerateImage = (fileId: string) => {
  delete regenerateImages.value[fileId];
};

// 微调图片 - 添加图片到微调列表
const handleFineTune = async (imageKey: string, imageData: any) => {
  try {
    // 检查图片是否已经在微调列表中
    if (imageKey in fineTuneImages.value) {
      message.warning('该图片已在微调列表中');
      return;
    }

    // 添加图片到微调列表
    fineTuneImages.value[imageKey] = imageData;

    message.success(
      `已添加图片到微调列表 (${Object.keys(fineTuneImages.value).length}张)`,
    );
  } catch {}
};

// 删除单个微调图片
const removeFineTuneImage = (uniqueFilename: string) => {
  delete fineTuneImages.value[uniqueFilename];
};

// 清除微调选择
const clearFineTune = () => {
  fineTuneImages.value = {};
};

// 下载图片
const downloadImage = async (filename: string) => {
  let loadingMsg: any = null;
  try {
    loadingMsg = message.loading('正在下载图片...', 0);
    // 获取图片的预签名URL
    const imageUrl = await getImageUrl(filename);
    // 通过fetch获取图片数据
    const response = await fetch(imageUrl);
    const blob = await response.blob();
    // 创建blob URL并下载
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    // 清理blob URL
    window.URL.revokeObjectURL(blobUrl);
    loadingMsg?.();
    message.success('图片下载成功');
  } catch {
    loadingMsg?.();
  }
};

// 加载素材列表
const loadMaterials = async (isLoadMore = false) => {
  if (!isLoadMore && isLoadingMaterials.value) return;
  if (isLoadMore && !hasMoreMaterials.value) return;
  try {
    isLoadingMaterials.value = true;
    const params = {
      page: isLoadMore ? currentPage.value + 1 : 1,
      page_size: pageSize.value,
      real_name: searchRealName.value,
      skip: skipCount.value,
      ...(searchFilename.value && { basename: searchFilename.value }),
    };
    const response = await getCreativeImageTasks(params);
    if (isLoadMore) {
      allMaterials.value.push(...response.materials);
      currentPage.value += 1;
    } else {
      allMaterials.value = response.materials;
      currentPage.value = 1;
    }
    hasMoreMaterials.value = response.has_more || false;
  } finally {
    isLoadingMaterials.value = false;
  }
};

// 格式化时间显示
const formatTime = (seconds: number): string => {
  if (!seconds || seconds <= 0) return '';

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  const parts = [];
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}秒`);

  return parts.join('');
};

// 加载等待处理的素材
const loadRunningMaterials = async () => {
  try {
    isLoadingRunning.value = true;
    const params = {
      real_name: searchRealName.value,
      ...(searchFilename.value && { basename: searchFilename.value }),
    };
    const response = await getRunningCreativeImageTasks(params);
    if (response?.data) {
      const runningDataObj = response.data;
      runningMaterials.value = Object.values(runningDataObj);
      runningInfo.value = {
        wait_num: runningMaterials.value.length,
        remaining_time: response.remaining_time || 0,
      };
      previousRunningIds.value = new Set(Object.keys(runningDataObj));
    } else {
      runningMaterials.value = [];
      runningInfo.value = {
        wait_num: 0,
        remaining_time: 0,
      };
      previousRunningIds.value = new Set();
    }
  } finally {
    isLoadingRunning.value = false;
  }
};

// 处理搜索
const handleSearch = async () => {
  currentPage.value = 1;
  skipCount.value = 0;
  await Promise.all([loadMaterials(), loadRunningMaterials()]);
};

// 模态窗口层级管理
let currentMaxZIndex = 1000;

const setModalTop = (modalType: 'original' | 'preview1' | 'preview2') => {
  // 递增z-index，确保被点击的模态框始终在最上层，不影响其他模态框的相对顺序
  currentMaxZIndex += 1;

  if (modalType === 'preview1') {
    previewModalApi.setState({ zIndex: currentMaxZIndex });
  } else if (modalType === 'preview2') {
    previewModalApi2.setState({ zIndex: currentMaxZIndex });
  } else {
    originalImageModalApi.setState({ zIndex: currentMaxZIndex });
  }
};

// 创建可拖拽的原图片查看弹窗
const [OriginalImageModal, originalImageModalApi] = useVbenModal({
  draggable: true,
  modal: false,
});

const originalImageUrls = ref<Array<[string, string]>>([]);

// 单一图片预览modal
const [PreviewModal, previewModalApi] = useVbenModal({
  draggable: true,
  modal: false,
});

// 第二个预览modal
const [PreviewModal2, previewModalApi2] = useVbenModal({
  draggable: true,
  modal: false,
});

// 批量复刻modal
const [BulkCloneModal, bulkCloneModalApi] = useVbenModal({
  draggable: true,
  modal: true,
  class:
    'w-[calc(100vw-24px)] min-w-0 max-w-[960px] lg:w-[min(960px,90vw)] lg:min-w-[800px]',
  contentClass: 'overflow-y-auto max-h-[60vh]',
});

// 批量复刻相关状态
const bulkCloneImages = ref<
  Array<{
    file: File;
    id: string;
    imageNum: number;
    prompt: string;
    url: string;
  }>
>([]);
const bulkUploadFileList = ref<any[]>([]);
const globalPrompt = ref('');
const globalImageNum = ref(1);
const bulkModel = ref('qwen');
const isBulkCloneUploading = ref(false);

const currentPreviewImage = ref('');
const currentPreviewImage2 = ref('');
const currentImageKey = ref('');
const currentImageKey2 = ref('');
const isPreviewLoading = ref(false);
const lastUsedPreviewModal = ref<1 | 2>(2); // 记录最后使用的modal

// 预览单张图片 - 核心逻辑
const previewImageCore = async (image: any) => {
  if (!image.unique_filename) {
    message.warning('没有图片数据!');
    return;
  }

  // 检查图片是否已经在某个modal中打开
  if (
    currentImageKey.value === image.unique_filename &&
    previewModalApi.store.state.isOpen
  ) {
    setModalTop('preview1');
    lastUsedPreviewModal.value = 1; // 更新最后使用的modal记录
    return;
  }
  if (
    currentImageKey2.value === image.unique_filename &&
    previewModalApi2.store.state.isOpen
  ) {
    setModalTop('preview2');
    lastUsedPreviewModal.value = 2; // 更新最后使用的modal记录
    return;
  }

  try {
    isPreviewLoading.value = true;
    // 获取图片URL
    const imageUrl = await getImageUrl(image.unique_filename);

    // 决定使用哪个modal：轮换使用
    if (lastUsedPreviewModal.value === 2) {
      // 使用第一个modal
      currentImageKey.value = image.unique_filename;
      currentPreviewImage.value = imageUrl;
      previewModalApi
        .setState({
          fullscreenButton: true,
          footer: false,
          showCancelButton: false,
          showConfirmButton: false,
        })
        .open();
      setModalTop('preview1');
      lastUsedPreviewModal.value = 1;
    } else {
      // 使用第二个modal
      currentImageKey2.value = image.unique_filename;
      currentPreviewImage2.value = imageUrl;
      previewModalApi2
        .setState({
          fullscreenButton: true,
          footer: false,
          showCancelButton: false,
          showConfirmButton: false,
        })
        .open();
      setModalTop('preview2');
      lastUsedPreviewModal.value = 2;
    }
  } finally {
    isPreviewLoading.value = false;
  }
};

// 防抖后的预览方法
const previewImage = debounce(previewImageCore, 300);

// 轮询管理
let pollingInterval: null | number = null;
const isPolling = ref(false);

// 倒计时管理
let countdownInterval: null | number = null;

// 当前查看原图的任务ID
const currentOriginalTaskId = ref('');

// 查看原图片 - 核心逻辑
const viewOriginalImagesCore = async (materials: any) => {
  // 防止重复查看同一个任务的原图
  if (
    currentOriginalTaskId.value === materials._id &&
    originalImageModalApi.store.state.isOpen
  ) {
    setModalTop('original');
    return;
  }

  try {
    currentOriginalTaskId.value = materials._id;
    originalImageUrls.value = [];
    for (const fileId of materials.file_ids) {
      const response = await getOriginalImageUrl(fileId);
      // 后端返回 [url, upload_filename] 的元组
      const [url, basename] = response;
      originalImageUrls.value.push([basename || '', url || '']);
    }

    originalImageModalApi
      .setState({
        title: `原图(${originalImageUrls.value.length}张)`,
        fullscreenButton: false,
        footer: false,
        showCancelButton: false,
        showConfirmButton: false,
      })
      .open();
    setModalTop('original');
  } catch {}
};

// 复制到剪贴板
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    message.success('文件名已复制到剪贴板');
  } catch {}
};

// 打开批量复刻modal
const openBulkCloneModal = () => {
  bulkCloneModalApi
    .setState({
      title: '批量复刻',
      fullscreenButton: false,
      footer: false, // 使用自定义footer
    })
    .open();
};

// 处理批量上传图片
const handleBulkImageUpload = (info: any) => {
  bulkUploadFileList.value = info.fileList;

  const newFiles = info.fileList.filter(
    (file: any) => !bulkCloneImages.value.some((img) => img.id === file.uid),
  );

  newFiles.forEach((file: any) => {
    if (file.originFileObj) {
      const url = URL.createObjectURL(file.originFileObj);
      bulkCloneImages.value.push({
        file: file.originFileObj,
        url,
        prompt: globalPrompt.value,
        imageNum: globalImageNum.value,
        id: file.uid,
      });
    }
  });
};

// 移除批量图片
const removeBulkImage = (id: string) => {
  const index = bulkCloneImages.value.findIndex((img) => img.id === id);
  if (index !== -1) {
    const imageItem = bulkCloneImages.value[index];
    if (imageItem) {
      URL.revokeObjectURL(imageItem.url);
      bulkCloneImages.value.splice(index, 1);
    }
  }
};

// 防抖后的查看原图片方法
const viewOriginalImages = debounce(viewOriginalImagesCore, 300);

// 应用全局设置到所有图片
const applyGlobalPrompt = () => {
  bulkCloneImages.value.forEach((img) => {
    img.prompt = globalPrompt.value;
  });
  message.success('已应用全局提示词到所有图片');
};

const applyGlobalImageNum = () => {
  bulkCloneImages.value.forEach((img) => {
    img.imageNum = globalImageNum.value;
  });
  message.success('已应用全局生成数量到所有图片');
};

// 清空所有图片
const clearAllImages = () => {
  // 释放所有已创建的 URL，避免内存泄漏
  bulkCloneImages.value.forEach((img) => URL.revokeObjectURL(img.url));
  bulkCloneImages.value = [];
  // 同步清空 Upload.Dragger 的文件列表
  bulkUploadFileList.value = [];
  message.success('已清空所有图片');
};

// 提交批量复刻
const submitBulkClone = async () => {
  if (bulkCloneImages.value.length === 0) {
    message.warning('请至少上传一张图片');
    return;
  }

  try {
    isBulkCloneUploading.value = true;

    // 构建批量上传数据
    const files: File[] = [];
    const bulkTasks: Array<{
      image_num: number;
      model: string;
      prompt: string;
      task_type: number;
    }> = [];

    bulkCloneImages.value.forEach((imageItem) => {
      // 收集文件
      files.push(imageItem.file);

      // 构建任务配置
      bulkTasks.push({
        prompt: imageItem.prompt.trim(),
        image_num: imageItem.imageNum,
        task_type: 2, // 单图复刻
        model: bulkModel.value,
      });
    });

    // 调用批量上传接口
    const response = await bulkUploadCreativeImages(files, bulkTasks);
    message.success(response.message);
    // 清空数据并关闭modal
    bulkCloneImages.value.forEach((img) => URL.revokeObjectURL(img.url));
    bulkCloneImages.value = [];
    globalPrompt.value = '';
    globalImageNum.value = 1;
    await bulkCloneModalApi.close();

    await handleSearch();
  } finally {
    isBulkCloneUploading.value = false;
  }
};

// 关闭预览模态框
const closePreviewModal = (type: 'all' | 'preview') => {
  if (type === 'preview' || type === 'all') {
    // 关闭预览1,2
    previewModalApi.close();
    previewModalApi2.close();
    currentImageKey.value = '';
    currentPreviewImage.value = '';
    currentImageKey2.value = '';
    currentPreviewImage2.value = '';
  }
  if (type === 'all') {
    // 关闭原图预览
    originalImageModalApi.close();
    originalImageUrls.value = [];
    currentOriginalTaskId.value = '';
  }
};

// 上一次等待任务列表的ID集合，用于对比
const previousRunningIds = ref<Set<string>>(new Set());

// 检查任务完成状态
const checkTaskCompletion = async () => {
  try {
    const params = {
      real_name: searchRealName.value,
      ...(searchFilename.value && { basename: searchFilename.value }),
    };
    const response = await getRunningCreativeImageTasks(params);

    const runningDataObj = response?.data || {};
    const newRunningMaterials = Object.values(runningDataObj);
    const currentRunningIds = new Set(Object.keys(runningDataObj));

    // 找出减少的任务ID（完成的任务）
    const completedTaskIds = [...previousRunningIds.value].filter(
      (id) => !currentRunningIds.has(id),
    );

    // 查询完成的任务结果并更新到待播放列表
    for (const completedTaskId of completedTaskIds) {
      try {
        const completedTask =
          await checkCreativeImagesTaskStatus(completedTaskId);
        if (completedTask) {
          // 检查任务是否属于当前用户
          const userStore = useUserStore();
          const currentUserName = userStore.userInfo?.realName;

          // 只有当前用户的任务才添加到列表中
          if (currentUserName && completedTask.real_name === currentUserName) {
            completedTask.isNew = true;
            allMaterials.value.unshift(completedTask);
            skipCount.value += 1;
          }
        }
      } catch {}
    }

    // 更新当前等待任务列表和相关信息
    runningMaterials.value = newRunningMaterials;
    runningInfo.value = {
      wait_num: newRunningMaterials.length,
      remaining_time: response?.remaining_time || 0,
    };

    // 更新上一次的ID集合
    previousRunningIds.value = currentRunningIds;

    // 安排下次检查
    scheduleNextCheck();
  } catch {
    scheduleNextCheck();
  }
};

// 安排下次检查
const scheduleNextCheck = () => {
  if (isPolling.value) {
    pollingInterval = window.setTimeout(checkTaskCompletion, 10_000);
  }
};

// 开始倒计时
const startCountdown = () => {
  if (countdownInterval) return;

  countdownInterval = window.setInterval(() => {
    if (runningInfo.value.remaining_time > 0) {
      runningInfo.value.remaining_time--;
    }
  }, 1000);
};

// 停止倒计时
const stopCountdown = () => {
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
};

// 开始轮询
const startPolling = () => {
  if (isPolling.value) return;

  isPolling.value = true;
  checkTaskCompletion();
  startCountdown();
};

// 停止轮询
const stopPolling = () => {
  if (pollingInterval) {
    clearTimeout(pollingInterval);
    pollingInterval = null;
  }
  stopCountdown();
  isPolling.value = false;
};

// 滚动加载更多素材
const handleScroll = (event: Event) => {
  const target = event.target as HTMLElement;
  const scrollTop = target.scrollTop;
  const scrollHeight = target.scrollHeight;
  const clientHeight = target.clientHeight;
  if (
    scrollTop + clientHeight >= scrollHeight - 10 &&
    hasMoreMaterials.value &&
    !isLoadingMaterials.value
  ) {
    loadMaterials(true);
  }
};

// 动态添加上传文件标识
const updateUploadBadges = () => {
  setTimeout(() => {
    // 移除之前的标识
    document
      .querySelectorAll('.upload-number-badge')
      .forEach((badge) => badge.remove());

    // 获取所有上传项容器
    const uploadItems = document.querySelectorAll(
      '.ant-upload-list-item-container',
    );

    uploadItems.forEach((item, index) => {
      if (index < fileList.value.length) {
        // 创建标识元素
        const badge = document.createElement('div');
        badge.className = 'upload-number-badge';
        badge.style.cssText = `
          position: absolute;
          right: 5px;
          top: 5px;
          z-index: 15;
          pointer-events: none;
        `;

        badge.innerHTML = `
          <div class="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-r from-orange-500 to-orange-600 text-xs font-medium text-white shadow-lg backdrop-blur-sm">
            ${uploadStartIndex.value + index + 1}
          </div>
        `;

        // 确保容器有relative定位
        (item as HTMLElement).style.position = 'relative';
        item.append(badge);
      }
    });
  }, 100);
};

// 监听fileList变化来更新标识
watch(fileList, updateUploadBadges, { deep: true });

onMounted(async () => {
  const userStore = useUserStore();
  await fetchUserOptions();
  if (userStore.userInfo?.realName) {
    searchRealName.value = userStore.userInfo.realName;
  }
  await loadMaterials();
  await loadRunningMaterials();
  if (runningMaterials.value.length > 0) {
    startPolling();
  }

  // 初始化上传标识
  updateUploadBadges();
});

watch(
  () => runningMaterials.value.length,
  (newLength) => {
    if (newLength > 0 && !isPolling.value) {
      startPolling();
    } else if (newLength === 0 && isPolling.value) {
      stopPolling();
    }
  },
);

onUnmounted(() => {
  stopPolling();
  stopCountdown();
});
</script>

<template>
  <div class="bg-background flex h-full flex-col">
    <!-- 顶部标题栏 -->
    <div class="border-b px-2 py-2">
      <div class="flex items-center justify-between gap-4">
        <div class="flex gap-2">
          <Select
            allow-clear
            v-model:value="searchRealName"
            placeholder="选择创建者"
            class="w-48"
            :options="userOptions"
            :filter-option="
              (input: string, option: any) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
            show-search
          />
          <Input
            v-model:value="searchFilename"
            placeholder="搜索文件名(无后缀)"
            class="w-48"
            allow-clear
            @keyup.enter="handleSearch"
          />
          <Button
            @click="handleSearch"
            :loading="isLoadingMaterials"
            :disabled="isLoadingMaterials"
            title="查询/刷新"
            class="flex items-center justify-center"
          >
            <span class="icon-[ant-design--search-outlined]"></span>
            <span class="icon-[ant-design--reload-outlined] ml-1"></span>
          </Button>
        </div>

        <!-- 等待处理的图片横向滚动区域 -->
        <div
          v-if="hasRunningImages || isLoadingRunning"
          class="flex min-w-0 max-w-2xl items-center gap-3"
        >
          <!-- 加载状态 -->
          <template v-if="isLoadingRunning">
            <div
              class="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent"
            ></div>
            <span class="text-sm opacity-60">加载中...</span>
          </template>

          <!-- 等待任务信息 -->
          <template v-else>
            <div
              class="flex flex-shrink-0 flex-col gap-0.5 text-sm font-medium"
              style="min-width: 120px"
            >
              <span class="whitespace-nowrap">
                等待处理 ({{ runningMaterials.length }}个)
              </span>
              <span
                v-if="runningInfo.remaining_time > 0"
                class="font-mono text-xs opacity-70"
              >
                预计完成: {{ formatTime(runningInfo.remaining_time) }}
              </span>
              <span
                v-if="runningInfo.wait_num > 0"
                class="font-mono text-xs opacity-70"
              >
                总耗时预计: {{ formatTime(runningInfo.wait_num * 50) }}
              </span>
            </div>

            <!-- 缩略图滚动区域 -->
            <div
              class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-400/40 hover:scrollbar-thumb-gray-400/70 flex min-w-0 flex-1 gap-2 overflow-x-auto overflow-y-hidden pb-1"
              style="scrollbar-width: thin"
              @wheel.stop
            >
              <div
                v-for="image in runningMaterials"
                :key="image._id"
                class="relative flex h-12 w-24 flex-shrink-0 flex-col items-center justify-center overflow-hidden rounded border-2 px-1 transition-all"
                :class="[
                  image.status === 'STARTED'
                    ? 'border-primary bg-primary/10'
                    : 'border',
                ]"
              >
                <!-- 用户名显示 -->
                <div class="w-full truncate text-center text-xs font-medium">
                  {{ image.real_name }}
                </div>

                <!-- 图片数量显示 -->
                <div class="text-xs opacity-70">共{{ image.image_num }}张</div>

                <!-- 处理中状态指示器 -->
                <div
                  v-if="image.status === 'STARTED'"
                  class="bg-primary absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full shadow-sm"
                >
                  <div
                    class="h-2 w-2 animate-pulse rounded-full bg-white"
                  ></div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="flex flex-1 overflow-hidden">
      <div class="flex w-[300px] flex-col border-r">
        <div
          class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-400/40 hover:scrollbar-thumb-gray-400/70 w-[300px] flex-1 overflow-y-auto p-2"
        >
          <!-- 重新生成原图预览区域 -->
          <div v-if="Object.keys(regenerateImages).length > 0" class="mb-2">
            <div class="grid grid-cols-2 gap-2">
              <div
                v-for="([fileId, base64Data], index) in Object.entries(
                  regenerateImages,
                )"
                :key="fileId"
                class="group relative aspect-square overflow-hidden rounded border"
              >
                <div
                  class="h-full w-full bg-cover bg-center bg-no-repeat"
                  :style="{
                    backgroundImage: `url(data:image/jpeg;base64,${base64Data})`,
                  }"
                ></div>
                <!-- 顺序标记 -->
                <div
                  class="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded bg-gradient-to-r from-blue-500 to-blue-600 text-xs font-medium text-white shadow-lg backdrop-blur-sm"
                >
                  {{ index + 1 }}
                </div>
                <!-- 删除遮罩 -->
                <div
                  @click="removeRegenerateImage(fileId)"
                  class="absolute inset-0 flex cursor-pointer items-center justify-center bg-black bg-opacity-0 opacity-0 transition-all hover:bg-opacity-15 group-hover:opacity-100"
                  title="点击删除"
                >
                  <span
                    class="icon-[ant-design--delete-outlined] text-2xl text-white"
                  ></span>
                </div>
              </div>
            </div>
          </div>

          <!-- 微调图片预览区域 -->
          <div v-if="Object.keys(fineTuneImages).length > 0" class="mb-2">
            <div class="grid grid-cols-2 gap-2">
              <div
                v-for="([filename, base64Data], index) in Object.entries(
                  fineTuneImages,
                )"
                :key="filename"
                class="group relative aspect-square overflow-hidden rounded border"
              >
                <div
                  class="h-full w-full bg-cover bg-center bg-no-repeat"
                  :style="{
                    backgroundImage: `url(data:image/jpeg;base64,${base64Data})`,
                  }"
                ></div>
                <!-- 顺序标记 -->
                <div
                  class="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded bg-gradient-to-r from-green-500 to-green-600 text-xs font-medium text-white shadow-lg backdrop-blur-sm"
                >
                  {{ Object.keys(regenerateImages).length + index + 1 }}
                </div>
                <!-- 删除遮罩 -->
                <div
                  @click="removeFineTuneImage(filename)"
                  class="absolute inset-0 flex cursor-pointer items-center justify-center bg-black bg-opacity-0 opacity-0 transition-all hover:bg-opacity-15 group-hover:opacity-100"
                  title="点击删除"
                >
                  <span
                    class="icon-[ant-design--delete-outlined] text-2xl text-white"
                  ></span>
                  <div
                    class="absolute bottom-0 left-0 right-0 bg-black bg-opacity-60 px-1 py-0.5 text-xs text-white"
                  >
                    {{ filename }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 文件上传区域 -->
          <div class="upload-with-numbers relative">
            <Upload
              v-model:file-list="fileList"
              name="images"
              :multiple="true"
              accept="image/*"
              :before-upload="() => false"
              @change="handleUploadChange"
              @remove="handleFileRemove"
              list-type="picture-card"
              :show-upload-list="{
                showPreviewIcon: false,
                showRemoveIcon: true,
                showDownloadIcon: false,
              }"
              class=""
            >
              <button :style="{ border: 0, background: 'none' }" type="button">
                <span
                  class="icon-[ant-design--plus-outlined] text-2xl text-gray-400"
                ></span>
                <div>上传图片(最多选择3张)</div>
              </button>
            </Upload>
          </div>

          <Input.TextArea
            v-model:value="promptText"
            placeholder="请输入您的提示词..."
            :maxlength="1000"
            show-count
            class="mb-6 w-full"
            :auto-size="{ minRows: 6, maxRows: 20 }"
          />

          <!-- 任务类型选择 -->
          <div class="mb-2 flex items-center justify-center">
            <Radio.Group v-model:value="taskType" class="">
              <Radio.Button :value="1">单/多图修改</Radio.Button>
              <Radio.Button :value="2">单图复刻</Radio.Button>
            </Radio.Group>
          </div>

          <!-- 模型选择 -->
          <div class="mb-2 rounded-lg border p-3">
            <div class="mb-2 flex items-center justify-center space-x-2">
              <span class="icon-[ant-design--robot-outlined] text-lg"></span>
              <span class="text-sm font-semibold">AI模型</span>
            </div>
            <Radio.Group
              v-model:value="modelType"
              class="flex w-full space-x-2"
            >
              <Radio.Button value="google" class="flex-1"> 谷歌 </Radio.Button>
              <Radio.Button value="qwen" class="flex-1"> 千问 </Radio.Button>
            </Radio.Group>
          </div>

          <!-- 图片数量选择 -->
          <div class="mb-2 rounded-lg border p-3">
            <div class="mb-2 flex items-center justify-center space-x-2">
              <span class="icon-[ant-design--picture-outlined] text-lg"></span>
              <span class="text-sm font-semibold">生成数量</span>
            </div>
            <Radio.Group
              v-model:value="imageNum"
              class="flex flex-col space-y-2"
            >
              <div class="flex w-full space-x-1">
                <Radio.Button v-for="i in 5" :key="i" :value="i" class="flex-1">
                  {{ i }}
                </Radio.Button>
              </div>
              <div class="flex w-full space-x-1">
                <Radio.Button
                  v-for="i in 5"
                  :key="i + 5"
                  :value="i + 5"
                  class="flex-1"
                >
                  {{ i + 5 }}
                </Radio.Button>
              </div>
            </Radio.Group>
          </div>

          <!-- 提交按钮区域 -->
          <div class="flex gap-2">
            <Button
              @click="handleSubmit"
              class="flex-1"
              :disabled="
                (taskType !== 2 && !promptText.trim()) ||
                fileList.length +
                  Object.keys(regenerateImages).length +
                  Object.keys(fineTuneImages).length ===
                  0 ||
                isSubmitting
              "
              :loading="isSubmitting"
            >
              {{ isSubmitting ? '提交中...' : '开始创作图片' }}
            </Button>
            <Button
              @click="openBulkCloneModal()"
              type="dashed"
              class="w-24 border-purple-400 text-purple-600 hover:border-purple-500 hover:text-purple-700"
            >
              批量复刻
            </Button>
          </div>
        </div>
      </div>

      <!-- 图片内容区 -->
      <div class="flex flex-1 overflow-hidden">
        <!-- 左侧：缩略图列表 -->
        <div
          class="scrollbar-thin scrollbar-track-transparent flex min-h-[200px] w-24 flex-col gap-0.5 overflow-y-auto overflow-x-hidden p-1"
          v-if="hasAllImages"
          @scroll="handleScroll"
        >
          <div
            v-for="materials in allMaterials"
            :key="materials._id"
            class="hover:border-primary relative h-20 w-20 flex-shrink-0 cursor-pointer overflow-hidden rounded border-2 border-transparent bg-gray-200 transition-all hover:shadow-md"
            @click="scrollToMaterials(materials)"
          >
            <div
              v-if="
                materials.results && Object.keys(materials.results).length > 0
              "
              class="absolute inset-0"
              :style="{
                backgroundImage: `url(data:image/jpeg;base64,${Object.values(materials.results)[0]})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                backgroundRepeat: 'no-repeat',
              }"
            ></div>
            <!-- 失败状态指示器 -->
            <div
              v-if="materials.status === 'FAILED'"
              class="absolute inset-0 z-10 flex items-center justify-center bg-red-600 bg-opacity-60"
            >
              <span
                class="icon-[ant-design--exclamation-circle-filled] text-2xl text-white"
              ></span>
            </div>
            <!-- 新图片提醒标识 -->
            <div
              v-if="materials.isNew"
              class="absolute right-1 top-1 z-30 h-3 w-3 rounded-full bg-red-500 shadow-lg"
            >
              <div
                class="absolute inset-0 animate-ping rounded-full bg-red-500 opacity-75"
              ></div>
            </div>
            <!-- 图片数量 -->
            <div
              class="absolute bottom-0 right-0 rounded-tl bg-black bg-opacity-70 px-1 text-xs font-bold text-white"
            >
              {{ Object.keys(materials.results).length }}
            </div>
          </div>
        </div>
        <!-- 右侧：主展示区 -->
        <div
          class="scrollbar-thin scrollbar-track-gray-100/50 scrollbar-thumb-gray-400/60 hover:scrollbar-thumb-gray-400/90 flex-1 space-y-3 overflow-y-auto"
          v-if="hasAllImages"
          @scroll="handleScroll"
        >
          <Card
            v-for="materials in allMaterials"
            :key="materials._id"
            :id="`materials-${materials._id}`"
            class="overflow-hidden"
            :body-style="{ padding: 0 }"
          >
            <div class="px-4 py-2">
              <div class="flex items-center justify-between">
                <div class="flex min-w-0 flex-1 items-center justify-between">
                  <h3 class="truncate text-base font-semibold">
                    (原图{{ materials.file_ids.length }}张) (实际输出{{
                      Object.keys(materials.results).length
                    }}张) {{ materials.basenames }}
                  </h3>
                  <div class="text-500 flex flex-shrink-0 items-center text-xs">
                    <span v-if="materials.real_name" class="mr-4">{{
                      materials.real_name
                    }}</span>
                    <span>{{ materials.created_at }}</span>
                  </div>
                </div>
                <div class="ml-4 flex items-center gap-2">
                  <button
                    class="h-[18px]"
                    title="查看原图片"
                    @click="viewOriginalImages(materials)"
                  >
                    <span
                      class="icon-[ant-design--eye-outlined] text-lg"
                    ></span>
                  </button>
                  <button
                    class="h-[18px]"
                    title="重新生成"
                    @click="handleRegenerate(materials)"
                  >
                    <span
                      class="icon-[ant-design--redo-outlined] text-lg"
                    ></span>
                  </button>
                </div>
              </div>
              <p class="text-600 mt-1 text-sm">
                [{{
                  materials.task_type === 1
                    ? '多图修改'
                    : materials.task_type === 2
                      ? '单图复刻'
                      : '未知类型'
                }}] [生成{{ materials.image_num }}张] {{ materials.prompt }}
              </p>
              <!-- 失败状态提示 -->
              <div
                v-if="materials.status === 'FAILED'"
                class="mt-3 flex items-center gap-2 rounded-lg bg-red-50 p-3"
              >
                <span
                  class="icon-[ant-design--exclamation-circle-filled] text-lg text-red-500"
                ></span>
                <div class="flex-1">
                  <p class="text-sm font-medium text-red-700">生成失败</p>
                  <p class="text-xs text-red-600">
                    {{ materials.error_message }}
                  </p>
                </div>
              </div>
            </div>

            <!-- 图片展示区域 (失败状态不显示) -->
            <div v-if="materials.status !== 'FAILED'">
              <div
                v-if="
                  materials.results && Object.keys(materials.results).length > 0
                "
                class="grid h-48 gap-3"
                :style="{
                  gridTemplateColumns: `repeat(${Object.keys(materials.results).length}, minmax(0, 1fr))`,
                }"
              >
                <div
                  v-for="[imageKey, imageData] in Object.entries(
                    materials.results,
                  )"
                  :key="imageKey"
                  class="group relative h-full w-full overflow-hidden rounded border"
                >
                  <!-- 图片展示 -->
                  <div
                    class="h-full w-full bg-contain bg-center bg-no-repeat"
                    :style="{
                      backgroundImage: `url(data:image/jpeg;base64,${imageData})`,
                    }"
                  ></div>

                  <!-- 整体遮罩背景 -->
                  <div
                    class="absolute inset-0 bg-black bg-opacity-0 transition-all group-hover:bg-opacity-10"
                  ></div>

                  <!-- 预览点击区域 -->
                  <div
                    class="absolute inset-0 cursor-pointer"
                    @click="
                      previewImage({
                        unique_filename: imageKey,
                        base64Data: imageData,
                      })
                    "
                  >
                    <span
                      class="icon-[ant-design--eye-outlined] pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-2xl text-white opacity-0 transition-opacity group-hover:opacity-100"
                    ></span>
                  </div>

                  <!-- 图片文件名和按钮组 -->
                  <div
                    class="absolute bottom-0 left-0 right-0 flex items-center justify-between bg-black bg-opacity-40 p-2 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100"
                  >
                    <p class="flex-1 truncate">{{ imageKey }}</p>
                    <div class="flex items-center">
                      <button
                        @click.stop="handleFineTune(imageKey, imageData)"
                        class="flex h-6 w-6 items-center justify-center rounded transition-colors hover:bg-white hover:bg-opacity-20"
                        title="微调"
                      >
                        <span
                          class="icon-[ant-design--edit-outlined] text-sm"
                        ></span>
                      </button>
                      <button
                        @click.stop="downloadImage(imageKey)"
                        class="flex h-6 w-6 items-center justify-center rounded transition-colors hover:bg-white hover:bg-opacity-20"
                        title="下载"
                      >
                        <span
                          class="icon-[ant-design--download-outlined] text-sm"
                        ></span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <!-- 加载更多提示 -->
          <div
            v-if="isLoadingMaterials"
            class="flex items-center justify-center py-4"
          >
            <div
              class="h-6 w-6 animate-spin rounded-full border-2 border-gray-400 border-t-transparent"
            ></div>
            <span class="text-500 ml-2">加载中...</span>
          </div>

          <!-- 没有更多数据提示 -->
          <div
            v-else-if="!hasMoreMaterials"
            class="flex items-center justify-center pb-4"
          >
            没有更多数据了
          </div>
        </div>
      </div>
    </div>

    <!-- 上传的原图片查看弹窗 -->
    <OriginalImageModal>
      <template #title>
        <div class="flex h-4 w-full items-center pr-4">
          <span
            class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-red-600"
          >
            原图预览
          </span>
          <div class="flex flex-shrink-0 items-center">
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭预览1,2"
              @click="closePreviewModal('preview')"
            >
              <div class="relative inline-block leading-none">
                <span
                  class="icon-[ant-design--close-square-outlined] block text-sm text-green-600"
                  style="clip-path: inset(0 50% 0 0)"
                ></span>
                <span
                  class="icon-[ant-design--close-square-outlined] absolute left-0 top-0 block text-sm text-blue-600"
                  style="clip-path: inset(0 0 0 50%)"
                ></span>
              </div>
            </span>
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭全部预览"
              @click="closePreviewModal('all')"
            >
              <span
                class="icon-[ant-design--close-circle-outlined] text-sm text-red-600"
              ></span>
            </span>
          </div>
        </div>
      </template>
      <div
        class="grid gap-4"
        :style="{
          gridTemplateColumns: `repeat(${originalImageUrls.length}, minmax(0, 1fr))`,
        }"
      >
        <div
          v-for="([basename, imageUrl], index) in originalImageUrls"
          :key="index"
          class="flex flex-col"
        >
          <!-- 文件名显示和复制 -->
          <div class="flex items-center rounded bg-gray-50">
            <span
              class="flex-1 truncate text-xs text-gray-600"
              :title="basename"
            >
              {{ basename }}
            </span>
            <button
              @click="copyToClipboard(basename)"
              class="flex items-center justify-center rounded transition-colors hover:bg-gray-200"
              title="复制文件名"
            >
              <span
                class="icon-[ant-design--copy-outlined] text-sm text-gray-500"
              ></span>
            </button>
          </div>
          <Image :src="imageUrl" class="rounded border object-contain" />
        </div>
      </div>
    </OriginalImageModal>

    <!-- 图片预览弹窗1 -->
    <PreviewModal>
      <template #title>
        <div class="flex h-4 w-full items-center pr-12">
          <span
            class="mr-2 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-green-600"
            :title="currentImageKey"
          >
            预览1 - {{ currentImageKey }}
          </span>
          <div class="flex flex-shrink-0 items-center">
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭预览1,2"
              @click="closePreviewModal('preview')"
            >
              <div class="relative inline-block leading-none">
                <span
                  class="icon-[ant-design--close-square-outlined] block text-sm text-green-600"
                  style="clip-path: inset(0 50% 0 0)"
                ></span>
                <span
                  class="icon-[ant-design--close-square-outlined] absolute left-0 top-0 block text-sm text-blue-600"
                  style="clip-path: inset(0 0 0 50%)"
                ></span>
              </div>
            </span>
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭全部预览"
              @click="closePreviewModal('all')"
            >
              <span
                class="icon-[ant-design--close-circle-outlined] text-sm text-red-600"
              ></span>
            </span>
          </div>
        </div>
      </template>
      <div class="flex min-h-[400px] items-center justify-center">
        <div v-if="isPreviewLoading" class="text-center">
          <p class="text-gray-500">图片加载中...</p>
        </div>
        <Image
          v-else-if="currentPreviewImage"
          :src="currentPreviewImage"
          class="object-contain"
        />
      </div>
    </PreviewModal>

    <!-- 图片预览弹窗2 -->
    <PreviewModal2>
      <template #title>
        <div class="flex h-4 w-full items-center pr-12">
          <span
            class="mr-2 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-blue-600"
            :title="currentImageKey2"
          >
            预览2 - {{ currentImageKey2 }}
          </span>
          <div class="flex flex-shrink-0 items-center">
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭预览1,2"
              @click="closePreviewModal('preview')"
            >
              <div class="relative inline-block leading-none">
                <span
                  class="icon-[ant-design--close-square-outlined] block text-sm text-green-600"
                  style="clip-path: inset(0 50% 0 0)"
                ></span>
                <span
                  class="icon-[ant-design--close-square-outlined] absolute left-0 top-0 block text-sm text-blue-600"
                  style="clip-path: inset(0 0 0 50%)"
                ></span>
              </div>
            </span>
            <span
              class="flex h-6 w-6 cursor-pointer items-center justify-center rounded transition-colors hover:bg-gray-100"
              title="关闭全部预览"
              @click="closePreviewModal('all')"
            >
              <span
                class="icon-[ant-design--close-circle-outlined] text-sm text-red-600"
              ></span>
            </span>
          </div>
        </div>
      </template>
      <div class="flex min-h-[400px] items-center justify-center">
        <div v-if="isPreviewLoading" class="text-center">
          <p class="text-gray-500">图片加载中...</p>
        </div>
        <Image
          v-else-if="currentPreviewImage2"
          :src="currentPreviewImage2"
          class="object-contain"
        />
      </div>
    </PreviewModal2>

    <!-- 批量复刻modal -->
    <BulkCloneModal>
      <template #title>
        <div class="flex h-4 w-full items-center">
          <span
            class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-purple-600"
          >
            批量复刻 ({{ bulkCloneImages.length }}张图片)
          </span>
        </div>
      </template>
      <div class="w-full">
        <!-- 全局设置区域 -->
        <div class="mb-2 w-full rounded-lg border-2 border-dashed p-4">
          <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <Input.TextArea
                v-model:value="globalPrompt"
                placeholder="输入全局提示词..."
                :maxlength="1000"
                show-count
                :auto-size="{ minRows: 3, maxRows: 6 }"
              />
              <Button @click="applyGlobalPrompt" class="mt-2 w-full">
                应用提示词到所有图片
              </Button>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium">
                全局生成数量
              </label>
              <InputNumber
                v-model:value="globalImageNum"
                :min="1"
                :max="10"
                placeholder="生成数量(1-10)"
                class="w-full"
              />
              <Button @click="applyGlobalImageNum" class="mt-2 w-full">
                应用生成数量到所有图片
              </Button>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium"> AI模型 </label>
              <Radio.Group
                v-model:value="bulkModel"
                class="flex w-full space-x-2"
              >
                <Radio.Button value="qwen" class="flex-1"> 千问 </Radio.Button>
                <Radio.Button value="google" class="flex-1">
                  谷歌
                </Radio.Button>
              </Radio.Group>
            </div>
          </div>
        </div>

        <!-- 图片上传区域 -->
        <div class="mb-2 flex w-full gap-2">
          <Upload.Dragger
            v-model:file-list="bulkUploadFileList"
            :multiple="true"
            accept="image/*"
            :before-upload="() => false"
            @change="handleBulkImageUpload"
            :show-upload-list="false"
            class="flex-1"
          >
            <div class="flex flex-col items-center justify-center">
              <span
                class="icon-[ant-design--plus-outlined] mb-1 text-2xl"
              ></span>
              <span class="text-sm font-medium"> 点击或拖拽上传图片 </span>
            </div>
          </Upload.Dragger>
          <Button
            @click="clearAllImages"
            danger
            class="flex h-full flex-col items-center justify-center whitespace-nowrap border-2 border-dashed px-4 py-4"
          >
            <span
              class="icon-[ant-design--delete-outlined] mb-1 text-2xl"
            ></span>
            <span class="text-sm font-medium">清空</span>
          </Button>
        </div>

        <!-- 图片列表 -->
        <div
          v-if="bulkCloneImages.length > 0"
          class="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
        >
          <div
            v-for="imageItem in bulkCloneImages"
            :key="imageItem.id"
            class="rounded-lg border p-3 shadow-sm"
          >
            <!-- 图片预览 -->
            <div
              class="group relative mb-3 aspect-square overflow-hidden rounded border"
            >
              <img
                :src="imageItem.url"
                alt="上传的图片"
                class="h-full w-full object-cover"
              />
              <!-- 删除遮罩 -->
              <div
                @click="removeBulkImage(imageItem.id)"
                class="absolute inset-0 flex cursor-pointer items-center justify-center bg-black bg-opacity-0 opacity-0 transition-all hover:bg-opacity-35 group-hover:opacity-100"
                title="点击删除"
              >
                <span
                  class="icon-[ant-design--delete-outlined] text-2xl text-white"
                ></span>
              </div>
            </div>

            <!-- 设置区域 -->
            <div class="space-y-3">
              <div>
                <Input.TextArea
                  v-model:value="imageItem.prompt"
                  placeholder="提示词(可以不写)"
                  :maxlength="1000"
                  show-count
                  :auto-size="{ minRows: 2, maxRows: 4 }"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium"> 生成数量 </label>
                <InputNumber
                  v-model:value="imageItem.imageNum"
                  :min="1"
                  :max="10"
                  placeholder="生成数量(1-10)"
                  class="w-full"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button
            @click="submitBulkClone"
            :loading="isBulkCloneUploading"
            :disabled="bulkCloneImages.length === 0"
          >
            {{
              isBulkCloneUploading
                ? '提交中...'
                : `开始批量复刻 (${bulkCloneImages.length}张)`
            }}
          </Button>
        </div>
      </template>
    </BulkCloneModal>
  </div>
</template>
