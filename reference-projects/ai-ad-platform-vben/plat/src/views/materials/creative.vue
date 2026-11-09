<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useVbenModal } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Input,
  InputNumber,
  message,
  Select,
  Upload,
} from 'ant-design-vue';

import {
  bulkUploadCreativeVideos,
  checkCreativeTaskStatus,
  getCreativeMaterials,
  getOriginalVideoUrl,
  getRunningCreativeMaterials,
  getThumbnailByFileId,
  getUserOptions,
  getVideoUrl,
  uploadCreativeMaterial,
} from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

// 响应式数据
const promptText = ref('');
const videoNum = ref(1);
const uploadedFile = ref<any>(null);
const isSubmitting = ref(false);
const fileList = ref<any[]>([]);

// 素材列表相关
const allMaterials = ref<any[]>([]);
const isLoadingMaterials = ref(false);
const pageSize = ref(15);
const searchFilename = ref('');
const searchRealName = ref('');
const currentPage = ref(1);
const hasMoreMaterials = ref(true);
const skipCount = ref(0);
const route = useRoute();
const routeStateReady = ref(false);

const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    searchFilename: { key: 'filename' },
    searchRealName: { key: 'creator' },
  },
  onRouteStateRestored: async () => {
    if (routeStateReady.value) await handleSearch();
  },
  state: createListRouteStateTarget({ searchFilename, searchRealName }),
});

// 用户选项
const userOptions = ref<Array<{ label: string; value: string }>>([]);

// 等待处理的视频列表
const runningMaterials = ref<any[]>([]);
const isLoadingRunning = ref(false);
const runningInfo = ref<{
  remaining_time: number;
  wait_num: number;
}>({
  wait_num: 0,
  remaining_time: 0,
});

// 批量复刻相关状态
const bulkCloneVideos = ref<
  Array<{
    file: File;
    id: string;
    prompt: string;
    url: string;
    videoNum: number;
  }>
>([]);
const globalPrompt = ref('');
const globalVideoNum = ref(1);
const isBulkCloneUploading = ref(false);

// 获取用户选项
const fetchUserOptions = async () => {
  const res = await getUserOptions(['operator', 'operator_leader', 'creator']);
  userOptions.value = res.map((line: string) => ({
    label: line,
    value: line,
  }));
};

// 视频数量选项
const videoNumOptions = Array.from({ length: 10 }, (_, i) => ({
  label: `${i + 1}条`,
  value: i + 1,
}));

// 数据转换函数
const transformToVideoItem = (item: any) => ({
  ...item,
  thumbnail: item.thumbnail ? `data:image/jpeg;base64,${item.thumbnail}` : '',
});

// 计算属性 - 所有素材列表
const allVideoList = computed(() => {
  return allMaterials.value.map((material: any) =>
    transformToVideoItem(material),
  );
});

const hasAllVideos = computed(() => allVideoList.value.length > 0);

const hasRunningVideos = computed(() => runningMaterials.value.length > 0);

// 视频状态判断
const getVideoState = (videoId: string) => ({
  isPlaying:
    currentPlayingVideo.value?.id === videoId &&
    currentPlayingVideo.value?.videoUrl &&
    !currentPlayingVideo.value?.isLoading,
  isLoading:
    currentPlayingVideo.value?.id === videoId &&
    currentPlayingVideo.value?.isLoading,
  isCurrent: currentPlayingVideo.value?.id === videoId,
});

const scrollToVideo = (video: any) => {
  // 如果是新视频，点击后移除 isNew 标识
  if (video.isNew) {
    // 在原始数据中找到对应的项并移除 isNew 标识
    const originalItem = allMaterials.value.find(
      (item) => item._id === video._id,
    );
    if (originalItem) {
      originalItem.isNew = false;
    }
  }
  const element = document.querySelector(`#video-${video._id}`);
  element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

// 获取文件的base64预览
function getBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.addEventListener('load', () => resolve(reader.result as string));
    reader.addEventListener('error', (error) => reject(error));
  });
}

// 统一设置文件显示的方法
const setFileDisplay = async (options: {
  file?: File;
  fileId?: string;
  name: string;
  preview?: string;
  uniqueFilename?: string;
}) => {
  const { file, name, preview, fileId, uniqueFilename } = options;
  uploadedFile.value = {
    name,
    size: file?.size || 0,
    ...(file && { originFile: file }), // 保存原始文件对象
    ...(uniqueFilename && { uniqueFilename }), // 如果是unique_filename则标记
    ...(fileId && { fileId }), // 如果是unique_filename则标记
  };

  // 获取或使用现有的预览图
  let thumbnailData = preview || '';
  if (!thumbnailData && file) {
    try {
      thumbnailData = await (file.type.startsWith('video/')
        ? generateVideoPreview(file)
        : getBase64(file));
    } catch {}
  }

  // 添加预览图到uploadedFile
  uploadedFile.value.preview = thumbnailData;

  // 为了兼容Upload组件，仍需要设置fileList
  fileList.value = [
    {
      uid: Date.now().toString(),
      name,
      status: 'done' as const,
      preview: thumbnailData,
      thumbUrl: thumbnailData,
      ...(file && { originFileObj: file }),
    },
  ];
};

// 处理上传变化
const handleUploadChange = async (info: any) => {
  let newFileList = [...info.fileList];

  // 只保留最新的一个文件（支持覆盖）
  if (newFileList.length > 1) {
    newFileList = [newFileList[newFileList.length - 1]];
  }

  if (newFileList.length > 0) {
    const file = newFileList[0];
    const actualFile = file.originFileObj || file;

    await setFileDisplay({
      file: actualFile,
      name: file.name,
    });

    message.success(`${file.name} 文件选择成功`);
  } else {
    uploadedFile.value = null;
    fileList.value = [];
  }
};

// 为视频生成预览缩略图
function generateVideoPreview(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    video.addEventListener('loadedmetadata', () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      video.currentTime = 1; // 第1秒处截图
    });

    video.addEventListener('seeked', () => {
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const thumbnail = canvas.toDataURL('image/jpeg', 0.8);
        resolve(thumbnail);
      } else {
        reject(new Error('无法创建canvas上下文'));
      }
    });

    video.addEventListener('error', () => {
      reject(new Error('视频加载失败'));
    });

    video.src = URL.createObjectURL(file);
    video.load();
  });
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`;
};

const handleSubmit = async () => {
  try {
    isSubmitting.value = true;
    const formData = new FormData();
    // 如果有上传的真实文件，使用文件；否则根据存储的标识符判断类型
    if (uploadedFile.value?.originFile) {
      formData.append('file', uploadedFile.value.originFile);
    } else if (uploadedFile.value?.uniqueFilename) {
      formData.append('unique_filename', uploadedFile.value.uniqueFilename);
    } else if (uploadedFile.value?.fileId) {
      formData.append('file_id', uploadedFile.value.fileId);
    } else {
      message.warning('请上传文件或选择重新生成');
      return;
    }

    formData.append('prompt', promptText.value.trim());
    formData.append('video_num', videoNum.value.toString());
    const result = await uploadCreativeMaterial(formData);
    message.success(result.message);
    // 上传成功后刷新素材列表
    await handleSearch();
  } finally {
    isSubmitting.value = false;
  }
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

// 处理批量上传视频
const handleBulkVideoUpload = (info: any) => {
  const newFiles = info.fileList.filter(
    (file: any) =>
      !bulkCloneVideos.value.some((video) => video.id === file.uid),
  );

  newFiles.forEach((file: any) => {
    if (file.originFileObj) {
      const url = URL.createObjectURL(file.originFileObj);
      bulkCloneVideos.value.push({
        file: file.originFileObj,
        url,
        prompt: globalPrompt.value,
        videoNum: globalVideoNum.value,
        id: file.uid,
      });
    }
  });
};

// 移除批量视频
const removeBulkVideo = (id: string) => {
  const index = bulkCloneVideos.value.findIndex((video) => video.id === id);
  if (index !== -1) {
    const videoItem = bulkCloneVideos.value[index];
    if (videoItem) {
      URL.revokeObjectURL(videoItem.url);
      bulkCloneVideos.value.splice(index, 1);
    }
  }
};

// 应用全局设置到所有视频
const applyGlobalPrompt = () => {
  bulkCloneVideos.value.forEach((video) => {
    video.prompt = globalPrompt.value;
  });
  message.success('已应用全局提示词到所有视频');
};

const applyGlobalVideoNum = () => {
  bulkCloneVideos.value.forEach((video) => {
    video.videoNum = globalVideoNum.value;
  });
  message.success('已应用全局生成数量到所有视频');
};

// 清空所有视频
const clearAllVideos = () => {
  bulkCloneVideos.value = [];
  message.success('已清空所有视频');
};

// 提交批量复刻
const submitBulkClone = async () => {
  if (bulkCloneVideos.value.length === 0) {
    message.warning('请至少上传一个视频');
    return;
  }

  try {
    isBulkCloneUploading.value = true;

    // 构建批量上传数据
    const files: File[] = [];
    const bulkTasks: Array<{
      prompt: string;
      video_num: number;
    }> = [];

    bulkCloneVideos.value.forEach((videoItem) => {
      // 收集文件
      files.push(videoItem.file);

      // 构建任务配置
      bulkTasks.push({
        prompt: videoItem.prompt.trim(),
        video_num: videoItem.videoNum,
      });
    });

    // 调用批量上传接口
    const response = await bulkUploadCreativeVideos(files, bulkTasks);
    message.success(response.message);

    // 清空数据并关闭modal
    bulkCloneVideos.value.forEach((video) => URL.revokeObjectURL(video.url));
    bulkCloneVideos.value = [];
    globalPrompt.value = '';
    globalVideoNum.value = 1;
    await bulkCloneModalApi.close();

    // 刷新列表
    await handleSearch();
  } catch {
    message.error('批量复刻失败');
  } finally {
    isBulkCloneUploading.value = false;
  }
};

// 重新生成视频
const handleRegenerate = async (video: any) => {
  try {
    // 将视频信息填入左侧表单
    promptText.value = video.prompt;
    videoNum.value = video.video_num;
    // 同步获取缩略图
    let thumbnailData = '';
    if (video.file_id) {
      const rawThumbnail = await getThumbnailByFileId(video.file_id);
      if (rawThumbnail) {
        thumbnailData = `data:image/jpeg;base64,${rawThumbnail}`;
      }
    }
    await setFileDisplay({
      name: `${video.basename}.mp4`,
      preview: thumbnailData,
      fileId: video.file_id,
    });
    message.success('已导入视频信息，可重新生成');
  } catch {
    message.error('导入视频信息失败');
  }
};

// 微调视频
const handleFineTune = async (video: any) => {
  try {
    promptText.value = video.prompt;
    videoNum.value = video.video_num;
    const thumbnailData = video.thumbnail || '';
    await setFileDisplay({
      name: video.unique_filename,
      preview: thumbnailData,
      uniqueFilename: video.unique_filename,
    });
    message.success('已导入视频信息，可微调生成');
  } catch {
    message.error('导入视频信息失败');
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
    const response = await getCreativeMaterials(params);
    if (isLoadMore) {
      allMaterials.value.push(...(response.materials || response));
      currentPage.value += 1;
    } else {
      allMaterials.value = response.materials || response;
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
    const response = await getRunningCreativeMaterials(params);
    if (response?.data) {
      const runningDataObj = response.data;
      runningMaterials.value = Object.values(runningDataObj);
      runningInfo.value = {
        wait_num: response.wait_num,
        remaining_time: response.remaining_time,
      };
      previousRunningIds.value = new Set(Object.keys(runningDataObj));
    } else {
      runningMaterials.value = [];
      runningInfo.value = {
        wait_num: response.wait_num,
        remaining_time: response.remaining_time,
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
  await commitQueryState();
  await Promise.all([loadMaterials(), loadRunningMaterials()]);
};

// 当前播放的视频状态
const currentPlayingVideo = ref<null | {
  id: string;
  isLoading: boolean;
  videoUrl?: string;
}>(null);

// 播放视频
const playVideo = async (video: any) => {
  // 如果点击的是当前正在处理的视频，不执行操作
  if (currentPlayingVideo.value?.id === video._id) {
    return;
  }
  if (!video.unique_filename) {
    message.warning('视频不存在');
    return;
  }

  // 如果是新视频，播放时清除 isNew 标识
  if (video.isNew) {
    const originalItem = allMaterials.value.find(
      (item) => item._id === video._id,
    );
    if (originalItem) {
      originalItem.isNew = false;
    }
  }

  try {
    currentPlayingVideo.value = { id: video._id, isLoading: true };
    const videoUrl = await getVideoUrl(video.unique_filename);
    currentPlayingVideo.value = { id: video._id, videoUrl, isLoading: false };
  } catch {
    currentPlayingVideo.value = null;
  }
};

// 停止播放
const stopVideo = () => {
  currentPlayingVideo.value = null;
};

// 创建可拖拽的原视频播放弹窗
const [OriginalVideoModal, originalVideoModalApi] = useVbenModal({
  draggable: true, // 启用拖拽
  modal: false, // 非阻塞，可以同时操作主界面
});

const originalVideoUrl = ref<null | string>(null);
const currentOriginalVideo = ref<any>(null);

// 批量复刻modal
const [BulkCloneModal, bulkCloneModalApi] = useVbenModal({
  draggable: true,
  modal: true,
  class:
    'w-[calc(100vw-24px)] min-w-0 max-w-[960px] lg:w-[min(960px,90vw)] lg:min-w-[800px]',
  contentClass: 'overflow-y-auto max-h-[60vh]',
});

// 轮询管理
let pollingInterval: null | number = null;
const isPolling = ref(false);

// 倒计时管理
let countdownInterval: null | number = null;

// 播放原视频
const playOriginalVideo = async (video: any) => {
  try {
    currentOriginalVideo.value = video;
    originalVideoUrl.value = await getOriginalVideoUrl(video.file_id);
    // 截断过长的文件名，避免标题溢出
    const maxLength = 25;
    const displayName =
      video.basename.length > maxLength
        ? `${video.basename.slice(0, Math.max(0, maxLength))}...`
        : video.basename;

    originalVideoModalApi
      .setState({
        title: `原视频预览 - ${displayName}`,
        fullscreenButton: false, // 禁用全屏按钮
        footer: false, // 不显示底部按钮区域
        showCancelButton: false, // 不显示取消按钮
        showConfirmButton: false, // 不显示确认按钮
      })
      .open();
  } catch {}
};

// 上一次等待任务列表的ID集合，用于对比
const previousRunningIds = ref<Set<string>>(new Set());

// 检查任务完成状态 - 新的批量对比模式
const checkTaskCompletion = async () => {
  try {
    // 获取当前等待任务列表
    const params = {
      real_name: searchRealName.value,
      ...(searchFilename.value && { basename: searchFilename.value }),
    };
    const response = await getRunningCreativeMaterials(params);

    // 适配新的数据结构：data现在是以_id为key的对象
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
        const completedTask = await checkCreativeTaskStatus(completedTaskId);
        if (completedTask) {
          completedTask.isNew = true;
          allMaterials.value.unshift(completedTask);
          skipCount.value += 1;
        }
      } catch (error) {}
    }

    // 更新当前等待任务列表和相关信息
    runningMaterials.value = newRunningMaterials;
    runningInfo.value = {
      wait_num: response?.wait_num || 0,
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
  // 立即开始第一次检查
  checkTaskCompletion();
  // 同时开始倒计时
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
  // 滚动到底部时加载更多
  if (
    scrollTop + clientHeight >= scrollHeight - 10 &&
    hasMoreMaterials.value &&
    !isLoadingMaterials.value
  ) {
    loadMaterials(true);
  }
};
onMounted(async () => {
  const userStore = useUserStore();
  const hadCreatorQuery = Object.hasOwn(route.query, 'creator');
  await restoreFromRoute();
  // 获取用户选项
  await fetchUserOptions();
  // 设置默认用户为当前登录用户
  if (!hadCreatorQuery && userStore.userInfo?.realName) {
    searchRealName.value = userStore.userInfo.realName;
  }
  await commitQueryState();
  routeStateReady.value = true;
  // 加载素材列表
  await loadMaterials();
  // 加载等待处理的素材
  await loadRunningMaterials();
  // 如果有等待处理的任务，开始轮询
  if (runningMaterials.value.length > 0) {
    startPolling();
  }
});

// 监听等待处理任务变化，自动管理轮询状态
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

// 组件卸载时清理轮询和倒计时
onUnmounted(() => {
  stopPolling();
  stopCountdown();
});
</script>

<template>
  <div
    class="adpulse-section-page bg-background flex min-h-full flex-col overflow-y-auto lg:h-full lg:overflow-hidden"
  >
    <h1 class="sr-only">创意素材</h1>
    <!-- 顶部标题栏 -->
    <div class="border-b px-2 py-2">
      <div
        class="flex flex-col items-stretch justify-between gap-3 lg:flex-row lg:items-center lg:gap-4"
      >
        <div class="flex flex-wrap gap-2">
          <Select
            allow-clear
            v-model:value="searchRealName"
            placeholder="选择创建者"
            class="min-w-[160px] flex-1 sm:w-48 sm:flex-none"
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
            class="min-w-[160px] flex-1 sm:w-48 sm:flex-none"
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

        <!-- 等待处理的视频横向滚动区域 -->
        <div
          v-if="hasRunningVideos || isLoadingRunning"
          class="flex min-w-0 max-w-2xl items-center gap-3"
        >
          <!-- 加载状态 -->
          <template v-if="isLoadingRunning">
            <div
              class="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent"
            ></div>
            <span class="text-sm text-gray-500">加载中...</span>
          </template>

          <!-- 等待任务信息 -->
          <template v-else>
            <div
              class="flex flex-shrink-0 flex-col gap-0.5 text-sm font-medium text-gray-600"
              style="min-width: 120px"
            >
              <span class="whitespace-nowrap">
                等待处理 ({{ runningMaterials.length }})
              </span>
              <span
                v-if="runningInfo.remaining_time > 0"
                class="font-mono text-xs text-blue-600"
              >
                预计完成: {{ formatTime(runningInfo.remaining_time) }}
              </span>
              <span
                v-if="runningInfo.wait_num > 0"
                class="font-mono text-xs text-purple-600"
              >
                总耗时预计: {{ formatTime(runningInfo.wait_num * 180) }}
              </span>
            </div>

            <!-- 缩略图滚动区域 -->
            <div
              class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-400/40 hover:scrollbar-thumb-gray-400/70 flex min-w-0 flex-1 gap-2 overflow-x-auto overflow-y-hidden pb-1"
              style="scrollbar-width: thin"
              @wheel.stop
            >
              <div
                v-for="video in runningMaterials"
                :key="video._id"
                class="relative h-12 w-12 flex-shrink-0 overflow-hidden rounded border-2 border-gray-300 bg-gray-200"
              >
                <!-- 缩略图背景 -->
                <div
                  v-if="video.thumbnail"
                  class="h-full w-full rounded bg-cover bg-center bg-no-repeat"
                  :style="{
                    backgroundImage: `url(data:image/jpeg;base64,${video.thumbnail})`,
                  }"
                ></div>

                <!-- STARTED 状态覆盖 -->
                <div
                  v-if="video.status === 'STARTED'"
                  class="absolute inset-0 flex items-center justify-center rounded bg-blue-500 bg-opacity-50"
                >
                  <span class="text-xs text-white">处理中</span>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div
      class="flex flex-1 flex-col overflow-visible lg:flex-row lg:overflow-hidden"
    >
      <div
        class="flex w-full flex-col border-b lg:w-[300px] lg:border-b-0 lg:border-r"
      >
        <div
          class="scrollbar-thin scrollbar-track-transparent scrollbar-thumb-gray-400/40 hover:scrollbar-thumb-gray-400/70 w-full flex-1 overflow-y-auto p-2 lg:w-[300px]"
        >
          <!-- 文件上传区域 -->
          <div class="relative mb-2 h-48 min-w-0 lg:min-w-[270px]">
            <Upload
              v-model:file-list="fileList"
              name="video"
              :multiple="false"
              accept="video/*"
              :before-upload="() => false"
              :show-upload-list="false"
              @change="handleUploadChange"
              class=""
            >
              <!-- 初始上传区域 -->
              <div
                v-if="!uploadedFile"
                class="mx-auto h-48 w-full cursor-pointer rounded-lg border-2 border-dashed border-gray-300 p-6 text-center transition-colors hover:border-blue-400"
              >
                <div class="flex h-full flex-col items-center justify-center">
                  <span
                    class="icon-[ant-design--inbox-outlined] text-400 text-2xl"
                  ></span>
                  <p class="text-600 mt-2 text-sm">
                    点击或拖拽视频文件到此区域上传
                  </p>
                  <p class="text-500 mt-1 text-xs">
                    支持单个文件上传，支持的格式：MP4、AVI、MOV等
                  </p>
                </div>
              </div>
              <!-- 已上传文件显示 -->
              <div
                v-else
                class="mx-auto h-48 w-full cursor-pointer overflow-hidden rounded-lg border-2 border-dashed border-gray-300 transition-colors hover:border-blue-400 hover:bg-blue-50"
              >
                <div class="flex h-full flex-col">
                  <!-- 视频缩略图预览 -->
                  <div
                    v-if="uploadedFile.preview"
                    class="group relative flex-1 overflow-hidden bg-gray-100"
                  >
                    <img
                      :src="uploadedFile.preview"
                      alt="视频缩略图"
                      class="h-full w-full object-contain"
                    />
                    <!-- 覆盖提示层 -->
                    <div
                      class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <div class="text-center text-white">
                        <span
                          class="icon-[ant-design--upload-outlined] mb-1 block text-2xl"
                        ></span>
                        <p class="text-sm">点击或拖拽新视频覆盖</p>
                      </div>
                    </div>
                  </div>
                  <!-- 文件信息 -->
                  <div class="flex h-16 items-center space-x-3 bg-white px-4">
                    <span
                      class="icon-[ant-design--video-camera-outlined] text-xl text-blue-500"
                    ></span>
                    <div class="min-w-0 flex-1">
                      <p class="text-900 truncate text-sm font-medium">
                        {{ uploadedFile.name }}
                      </p>
                      <p class="text-500 text-xs">
                        {{
                          uploadedFile.originFile
                            ? formatFileSize(uploadedFile.size)
                            : '原始视频文件'
                        }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
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

          <!-- 视频数量选择 -->
          <Select
            v-model:value="videoNum"
            :options="videoNumOptions"
            class="mb-2 w-full"
            placeholder="选择要生成的视频数量"
          />

          <!-- 提交按钮区域 -->
          <div class="flex gap-2">
            <Button
              @click="handleSubmit"
              class="flex-1"
              :loading="isSubmitting"
            >
              {{ isSubmitting ? '提交中...' : '开始创作' }}
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

      <!-- 视频内容区 -->
      <div
        class="flex min-w-0 flex-1 flex-col overflow-visible lg:flex-row lg:overflow-hidden"
      >
        <!-- 左侧：视频列表 -->
        <div
          class="scrollbar-thin scrollbar-track-transparent flex min-h-0 w-full flex-row gap-0.5 overflow-x-auto overflow-y-hidden p-1 lg:min-h-[200px] lg:w-24 lg:flex-col lg:overflow-y-auto lg:overflow-x-hidden"
          v-if="hasAllVideos"
          @scroll="handleScroll"
        >
          <div
            v-for="video in allVideoList"
            :key="video._id"
            class="hover:border-primary relative h-20 w-20 flex-shrink-0 cursor-pointer overflow-hidden rounded border-2 border-transparent bg-gray-200 transition-all hover:shadow-md"
            @click="scrollToVideo(video)"
          >
            <!-- 缩略图背景层 -->
            <div
              v-if="video.thumbnail"
              class="absolute inset-0"
              :style="{
                backgroundImage: `url(${video.thumbnail})`,
                backgroundSize: 'contain',
                backgroundPosition: 'center',
                backgroundRepeat: 'no-repeat',
              }"
            ></div>
            <!-- 失败状态指示器 -->
            <div
              v-if="video.status === 'FAILED'"
              class="absolute inset-0 z-10 flex items-center justify-center bg-red-600 bg-opacity-60"
            >
              <span
                class="icon-[ant-design--exclamation-circle-filled] text-2xl text-white"
              ></span>
            </div>
            <!-- 新视频提醒标识 -->
            <div
              v-if="video.isNew"
              class="absolute right-1 top-1 z-30 h-3 w-3 rounded-full bg-red-500 shadow-lg"
            >
              <div
                class="absolute inset-0 animate-ping rounded-full bg-red-500 opacity-75"
              ></div>
            </div>
            <!-- 当前播放指示器 -->
            <div
              v-if="getVideoState(video._id).isCurrent"
              class="border-1 absolute inset-0 z-20 border-blue-500 bg-blue-500 bg-opacity-20"
            ></div>
          </div>
        </div>
        <!-- 右侧：主播放区 -->
        <div
          class="scrollbar-thin scrollbar-track-gray-100/50 scrollbar-thumb-gray-400/60 hover:scrollbar-thumb-gray-400/90 flex-1 space-y-6 overflow-y-auto"
          v-if="hasAllVideos"
          @scroll="handleScroll"
        >
          <Card
            v-for="video in allVideoList"
            :key="video._id"
            :id="`video-${video._id}`"
            class="overflow-hidden"
            :body-style="{ padding: 0 }"
          >
            <!-- 视频信息 -->
            <div
              class="px-4 py-2"
              :class="video.status === 'FAILED' ? '' : 'border-b'"
            >
              <div class="flex items-center justify-between">
                <div class="flex min-w-0 flex-1 items-center justify-between">
                  <h3 class="truncate text-base font-semibold">
                    {{ video.basename }} → {{ video.unique_filename }}
                  </h3>
                  <div class="text-500 flex flex-shrink-0 items-center text-xs">
                    <span v-if="video.real_name" class="mr-4">{{
                      video.real_name
                    }}</span>
                    <span>{{ video.created_at }}</span>
                  </div>
                </div>
                <div class="ml-4 flex items-center gap-2">
                  <button
                    type="button"
                    class="flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    title="播放原视频"
                    aria-label="播放原视频"
                    @click="playOriginalVideo(video)"
                  >
                    <span
                      class="icon-[ant-design--eye-outlined] text-lg"
                    ></span>
                  </button>
                  <button
                    type="button"
                    class="flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    title="重新生成"
                    aria-label="重新生成"
                    @click="handleRegenerate(video)"
                  >
                    <span
                      class="icon-[ant-design--redo-outlined] text-lg"
                    ></span>
                  </button>
                  <button
                    type="button"
                    class="flex size-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    title="微调"
                    aria-label="微调"
                    @click="handleFineTune(video)"
                  >
                    <span
                      class="icon-[ant-design--edit-outlined] text-lg"
                    ></span>
                  </button>
                </div>
              </div>
              <p v-if="video.prompt" class="text-600 mt-1 truncate text-sm">
                {{ video.prompt }}
              </p>
              <!-- 失败状态提示 -->
              <div
                v-if="video.status === 'FAILED'"
                class="mt-3 flex items-center gap-2 rounded-lg bg-red-50 p-3"
              >
                <span
                  class="icon-[ant-design--exclamation-circle-filled] text-lg text-red-500"
                ></span>
                <div class="flex-1">
                  <p class="text-sm font-medium text-red-700">生成失败</p>
                  <p class="text-xs text-red-600">
                    视频处理过程中发生错误，请重新生成
                  </p>
                </div>
              </div>
            </div>

            <!-- 视频播放区域 (失败状态不显示) -->
            <div
              v-if="video.status !== 'FAILED'"
              class="bg-muted relative h-[58dvh] max-h-[520px] min-h-[320px]"
            >
              <!-- 如果正在播放，显示视频播放器 -->
              <div
                v-if="getVideoState(video._id).isPlaying"
                class="relative h-full"
              >
                <video
                  :src="currentPlayingVideo?.videoUrl"
                  class="h-full w-full"
                  controls
                  autoplay
                  loop
                ></video>
                <button
                  type="button"
                  aria-label="关闭视频播放"
                  @click="stopVideo()"
                  class="absolute right-2 top-2 rounded-full bg-black bg-opacity-50 p-2 text-white hover:bg-opacity-70"
                >
                  ✕
                </button>
              </div>
              <!-- 默认显示缩略图 -->
              <div
                v-else
                class="group relative h-full"
                :class="
                  video.status === 'FAILED' ||
                  getVideoState(video._id).isLoading
                    ? ''
                    : 'cursor-pointer'
                "
                @click="
                  video.status === 'COMPLETED' &&
                  !getVideoState(video._id).isLoading &&
                  playVideo(video)
                "
                :role="video.status === 'COMPLETED' ? 'button' : undefined"
                :tabindex="
                  video.status === 'COMPLETED' &&
                  !getVideoState(video._id).isLoading
                    ? 0
                    : -1
                "
                @keydown.enter.prevent="
                  video.status === 'COMPLETED' &&
                  !getVideoState(video._id).isLoading &&
                  playVideo(video)
                "
                @keydown.space.prevent="
                  video.status === 'COMPLETED' &&
                  !getVideoState(video._id).isLoading &&
                  playVideo(video)
                "
              >
                <!-- 缩略图背景 -->
                <div
                  v-if="video.thumbnail"
                  class="relative h-full w-full bg-contain bg-center bg-no-repeat"
                  :style="{
                    backgroundImage: `url(${video.thumbnail})`,
                  }"
                >
                  <!-- 播放按钮 -->
                  <div
                    v-if="!getVideoState(video._id).isLoading"
                    class="absolute inset-0 flex items-center justify-center"
                  >
                    <span
                      class="icon-[ant-design--play-circle-filled] text-3xl text-white opacity-80 transition-transform group-hover:scale-110"
                    ></span>
                  </div>
                </div>

                <!-- 视频加载状态覆盖层 -->
                <div
                  v-else-if="getVideoState(video._id).isLoading"
                  class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-50"
                >
                  <div class="text-center text-white">
                    <div
                      class="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-white border-t-transparent"
                    ></div>
                    <p class="text-lg font-medium">视频加载中</p>
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
            v-else-if="!hasMoreMaterials && allMaterials.length > 0"
            class="text-500 flex items-center justify-center pb-4"
          >
            没有更多数据了
          </div>
        </div>
      </div>
    </div>

    <!-- 原视频播放弹窗 - 使用vben可拖拽Modal -->
    <OriginalVideoModal>
      <div v-if="originalVideoUrl" class="flex justify-center">
        <video
          :src="originalVideoUrl"
          controls
          autoplay
          style="width: auto; min-width: 100%; height: auto; max-height: 68vh"
        ></video>
      </div>
      <div v-else class="flex items-center justify-center py-8">
        <div class="text-center">
          <div
            class="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600"
          ></div>
          <p class="text-500">视频加载中...</p>
        </div>
      </div>
    </OriginalVideoModal>

    <!-- 批量复刻modal -->
    <BulkCloneModal>
      <template #title>
        <div class="flex h-4 w-full items-center">
          <span
            class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-purple-600"
          >
            批量复刻 ({{ bulkCloneVideos.length }}个视频)
          </span>
        </div>
      </template>
      <div class="w-full">
        <!-- 全局设置区域 -->
        <div
          class="mb-2 w-full rounded-lg border-2 border-dashed border-purple-300 bg-purple-50 p-4"
        >
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Input.TextArea
                v-model:value="globalPrompt"
                placeholder="输入全局提示词..."
                :maxlength="1000"
                show-count
                :auto-size="{ minRows: 3, maxRows: 6 }"
              />
              <Button @click="applyGlobalPrompt" class="mt-2 w-full">
                应用提示词到所有视频
              </Button>
            </div>
            <div>
              <label class="mb-2 block text-sm font-medium text-gray-700">
                全局生成数量
              </label>
              <InputNumber
                v-model:value="globalVideoNum"
                :min="1"
                :max="10"
                placeholder="生成数量(1-10)"
                class="w-full"
              />
              <Button @click="applyGlobalVideoNum" class="w-full">
                应用生成数量到所有视频
              </Button>
            </div>
          </div>
        </div>

        <!-- 视频上传区域 -->
        <div class="mb-2 flex w-full gap-2">
          <Upload.Dragger
            :multiple="true"
            accept="video/*"
            :before-upload="() => false"
            @change="handleBulkVideoUpload"
            :show-upload-list="false"
            class="flex-1"
          >
            <div class="flex flex-col items-center justify-center">
              <span
                class="text-primary icon-[ant-design--plus-outlined] mb-1 text-2xl"
              ></span>
              <span class="text-foreground text-sm font-medium">
                点击或拖拽上传视频
              </span>
            </div>
          </Upload.Dragger>
          <Button
            @click="clearAllVideos"
            danger
            class="flex h-full flex-col items-center justify-center whitespace-nowrap border-2 border-dashed border-red-300 bg-red-50 px-4 py-4 hover:border-red-400 hover:bg-red-100"
          >
            <span
              class="icon-[ant-design--delete-outlined] mb-1 text-2xl text-red-600"
            ></span>
            <span class="text-sm font-medium text-red-700">清空</span>
          </Button>
        </div>

        <!-- 视频列表 -->
        <div
          v-if="bulkCloneVideos.length > 0"
          class="grid w-full grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
        >
          <div
            v-for="videoItem in bulkCloneVideos"
            :key="videoItem.id"
            class="rounded-lg border border-gray-200 bg-white p-3 shadow-sm"
          >
            <!-- 视频预览 -->
            <div
              class="group relative mb-3 aspect-video overflow-hidden rounded border"
            >
              <video
                :src="videoItem.url"
                class="h-full w-full object-cover"
                muted
                preload="metadata"
              ></video>
              <!-- 删除遮罩 -->
              <div
                @click="removeBulkVideo(videoItem.id)"
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
                  v-model:value="videoItem.prompt"
                  placeholder="提示词..."
                  :maxlength="1000"
                  show-count
                  :auto-size="{ minRows: 2, maxRows: 4 }"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-gray-700">
                  生成数量
                </label>
                <InputNumber
                  v-model:value="videoItem.videoNum"
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
            :disabled="bulkCloneVideos.length === 0"
          >
            {{
              isBulkCloneUploading
                ? '提交中...'
                : `开始批量复刻 (${bulkCloneVideos.length}个)`
            }}
          </Button>
        </div>
      </template>
    </BulkCloneModal>
  </div>
</template>
