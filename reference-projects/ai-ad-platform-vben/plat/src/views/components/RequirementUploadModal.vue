<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';

import {
  Button,
  message,
  Modal,
  notification,
  Progress,
  Select,
  Upload,
} from 'ant-design-vue';

import type { UploadTaskResult } from '#/api/requirement';

import { useUserStore } from '@vben/stores';

import { getCreators, uploadMaterialOrderAttachment } from '#/api/requirement';
import { getTaskAssigneeNames } from '#/api/system/user';
import { uploadTaskFileApi } from '#/api/task-center';
import { useUploadQueue } from '#/composables/useUploadQueue';
import {
  ORDER_ATTACHMENT_ARCHIVE_EXTS,
  ORDER_ATTACHMENT_IMAGE_EXTS,
  ORDER_ATTACHMENT_VIDEO_EXTS,
  validateFileType,
  validateUploadFileSize,
} from '#/utils/upload';

export interface UploadFileItem {
  uid: string;
  name: string;
  status: 'done' | 'error' | 'uploading';
  percent?: number;
  file?: File;
  errorMsg?: string;
  uploadData?: {
    /** Optional immutable file identifier returned by newer upload services. */
    id?: string;
    object_key: string;
    name: string;
    basename: string;
    size: number;
    content_type: string;
    filetype: string;
    file_md5: string;
    sha3_256: string;
    width: number;
    height: number;
    duration: number | null;
    url: string;
    img: string;
  };
}

const props = withDefaults(
  defineProps<{
    open: boolean;
    demandType: string;
    /** 已分配素材师；传入后优先作为下拉候选，避免展示无关用户。 */
    designerOptions?: string[];
    /** 默认选中的素材师，任务中心传当前登录人。 */
    defaultDesigner?: string;
    /** 已分配创意策划；传入后优先作为下拉候选。 */
    creativePlannerOptions?: string[];
    /** 默认选中的创意策划，任务中心传工单的首位已分配人员。 */
    defaultCreativePlanner?: string;
    /** 交付素材的工单 ID；参考附件不传。 */
    orderId?: string;
    persistKey: string;
    title?: string;
    isUnzip?: boolean;
    showDesigner?: boolean;
    maxFiles?: number;
    notificationTitle?: string;
    descriptionOptions?: {
      label: string;
      value: string;
      designer?: string;
      creativePlanner?: string;
      remark?: string;
    }[];
    assignmentMode?: boolean;
    taskCenterUpload?: boolean;
  }>(),
  {
    title: '上传素材',
    orderId: undefined,
    isUnzip: true,
    showDesigner: false,
  },
);

const emit = defineEmits<{
  'update:open': [value: boolean];
  'all-done': [
    key: string,
    files: UploadFileItem[],
    designer?: string,
    reqId?: string,
    creativePlanner?: string,
  ];
  'upload-change': [key: string, files: UploadFileItem[]];
  cancel: [];
}>();

// 以 persistKey 为维度持久化上传列表，关闭弹窗后再开状态不丢失
const uploadMap = reactive<Record<string, UploadFileItem[]>>({});

// 聚合各 poll task 的提交统计
interface AggregatedStats {
  total: number;
  success: number;
  failed: number;
  duplicate_count: number;
  duplicate_names: string[];
}
const uploadStatsMap = reactive<Record<string, AggregatedStats>>({});

const uploadFileList = computed(() => uploadMap[props.persistKey] ?? []);
const completedFiles = computed(() =>
  uploadFileList.value.filter((file) => file.status === 'done'),
);
const uploadingFiles = computed(() =>
  uploadFileList.value.filter((file) => file.status === 'uploading'),
);
const failedFiles = computed(() =>
  uploadFileList.value.filter((file) => file.status === 'error'),
);

// ==================== 素材师 / 创意策划 / 需求点 ====================
const userStore = useUserStore();
const selectedDesigner = ref<string | undefined>(undefined);
const selectedCreativePlanner = ref<string | undefined>(undefined);
const selectedReqId = ref<string | undefined>(undefined);
const creatorOptions = ref<{ label: string; value: string }[]>([]);
const plannerOptions = ref<{ label: string; value: string }[]>([]);

function participantOptions(names: string[] | undefined) {
  return [
    ...new Set((names ?? []).map((name) => name.trim()).filter(Boolean)),
  ].map((name) => ({ label: name, value: name }));
}

const designerOptions = computed(() => {
  const assigned = participantOptions(props.designerOptions);
  return assigned.length > 0 ? assigned : creatorOptions.value;
});

const creativePlannerOptions = computed(() => {
  const assigned = participantOptions(props.creativePlannerOptions);
  return assigned.length > 0 ? assigned : plannerOptions.value;
});

async function loadCreators() {
  const [creators, planners] = await Promise.allSettled([
    getCreators(),
    getTaskAssigneeNames('operator'),
  ]);
  if (creators.status === 'fulfilled') {
    creatorOptions.value = (creators.value ?? []).map((c: any) => ({
      label: c.full_name,
      value: c.full_name,
    }));
  } else {
    creatorOptions.value = [];
  }
  if (planners.status === 'fulfilled') {
    plannerOptions.value = (planners.value ?? []).map((name) => ({
      label: name,
      value: name,
    }));
  } else {
    plannerOptions.value = [];
  }
  if (creators.status === 'rejected' && planners.status === 'rejected') {
    message.error('素材师与创意策划列表加载失败，请稍后重试');
  }
}

function handleDesignerChange(v: any) {
  selectedDesigner.value = v != null ? String(v) : undefined;
}

function handleCreativePlannerChange(v: any) {
  selectedCreativePlanner.value = v != null ? String(v) : undefined;
}

function handleRequirementChange(v: any) {
  selectedReqId.value = v != null ? String(v) : undefined;
}

const selectedAssignment = computed(() =>
  props.assignmentMode
    ? props.descriptionOptions?.find(
        (item) => item.value === selectedReqId.value,
      )
    : undefined,
);
watch(selectedAssignment, (record) => {
  if (!props.assignmentMode) return;
  selectedDesigner.value = record?.designer;
  selectedCreativePlanner.value = record?.creativePlanner;
});
const sessionCancelled = ref(false);

watch(
  () => props.open,
  (open) => {
    sessionCancelled.value = !open;
    if (open && props.showDesigner) {
      selectedDesigner.value =
        props.defaultDesigner ??
        (userStore.userInfo as any)?.full_name ??
        undefined;
      selectedCreativePlanner.value =
        props.defaultCreativePlanner ?? props.creativePlannerOptions?.[0];
      selectedReqId.value = props.descriptionOptions?.[0]?.value;
      if (!props.assignmentMode) void loadCreators();
    }
  },
);

const canSubmit = computed(
  () =>
    props.showDesigner &&
    completedFiles.value.length > 0 &&
    uploadingFiles.value.length === 0 &&
    failedFiles.value.length === 0 &&
    Boolean(selectedDesigner.value) &&
    (props.descriptionOptions === undefined ||
      (props.descriptionOptions.length > 0 && Boolean(selectedReqId.value))),
);

const uploadStatusText = computed(() => {
  if (uploadingFiles.value.length > 0) {
    return `${uploadingFiles.value.length} 个文件正在上传`;
  }
  if (failedFiles.value.length > 0) {
    return `${failedFiles.value.length} 个文件上传失败，请重试或移除`;
  }
  if (completedFiles.value.length > 0) {
    return `${completedFiles.value.length} 个文件已上传完成`;
  }
  return '尚未选择文件';
});

function emitCompletedFiles() {
  emit(
    'all-done',
    props.persistKey,
    completedFiles.value,
    selectedDesigner.value,
    selectedReqId.value,
    selectedCreativePlanner.value,
  );
}

function submitCompletedFiles() {
  if (uploadingFiles.value.length > 0) {
    message.warning('文件仍在上传，请等待上传完成');
    return;
  }
  if (failedFiles.value.length > 0) {
    message.warning('请先重试或移除上传失败的文件');
    return;
  }
  if (completedFiles.value.length === 0) {
    message.warning('请至少上传一个文件');
    return;
  }
  if (!selectedDesigner.value) {
    message.warning('请选择素材师');
    return;
  }
  if (props.descriptionOptions !== undefined && !selectedReqId.value) {
    message.warning('请选择需求点');
    return;
  }
  emitCompletedFiles();
}

// onAllDone：队列全部完成时触发
const { enqueue } = useUploadQueue(5, () => {
  if (
    sessionCancelled.value ||
    props.showDesigner ||
    failedFiles.value.length > 0
  ) {
    return;
  }
  emit('all-done', props.persistKey, completedFiles.value);
});

// uid → AbortController，用于取消正在上传/队列中等待的任务
const abortControllerMap = new Map<string, AbortController>();

// 图片和视频工单都允许混合上传，需求类型不限制交付文件类型。
const uploadAccept = computed(() => {
  const imgs = ORDER_ATTACHMENT_IMAGE_EXTS.map((e) => `.${e}`).join(',');
  const vids = ORDER_ATTACHMENT_VIDEO_EXTS.map((e) => `.${e}`).join(',');
  const arc = ORDER_ATTACHMENT_ARCHIVE_EXTS.map((e) => `.${e}`).join(',');
  return `${imgs},${vids},${arc}`;
});

function scheduleUpload(item: UploadFileItem, key: string) {
  // 入队时固定工单，避免等待期间切换弹窗把文件命名到其他工单。
  const orderId = props.orderId;
  const requiresOrder = props.assignmentMode && !props.taskCenterUpload;
  const controller = new AbortController();
  abortControllerMap.set(item.uid, controller);

  enqueue(async () => {
    try {
      if (requiresOrder && !orderId) {
        throw new Error('工单信息未加载完成，请重新打开上传窗口');
      }
      const taskResult = props.taskCenterUpload
        ? ({
            duplicate_count: 0,
            duplicate_names: [],
            errors: [],
            failed: 0,
            items: [await uploadTaskFileApi(item.file!)].map((file) => ({
              basename: file.originalName,
              content_type: file.mimeType,
              duration: null,
              file_md5: '',
              filetype: file.originalName.split('.').pop() ?? '',
              height: 0,
              id: file.id,
              img: '',
              name: file.originalName,
              object_key: file.id,
              sha3_256: '',
              size: item.file!.size,
              url: '',
              width: 0,
            })),
            success: 1,
            skipped: [],
            total: 1,
          } as UploadTaskResult)
        : ((await uploadMaterialOrderAttachment(
            item.file!,
            props.isUnzip,
            (p) => {
              const list = uploadMap[key];
              const idx = list?.indexOf(item) ?? -1;
              if (idx !== -1) {
                list![idx]!.percent = p;
                emit('upload-change', key, [...(uploadMap[key] ?? [])]);
              }
            },
            controller.signal,
            orderId,
          )) as UploadTaskResult);
      // 始终累计 stats
      const s = (uploadStatsMap[key] ??= {
        total: 0,
        success: 0,
        failed: 0,
        duplicate_count: 0,
        duplicate_names: [],
      });
      s.total += taskResult.total ?? 0;
      s.success += taskResult.success ?? 0;
      s.failed += taskResult.failed ?? 0;
      s.duplicate_count += taskResult.duplicate_count ?? 0;
      s.duplicate_names.push(...(taskResult.duplicate_names ?? []));
      const fileItems = taskResult.items ?? [];
      const list = uploadMap[key];
      const idx = list?.indexOf(item) ?? -1;
      if (idx !== -1) {
        list!.splice(
          idx,
          1,
          ...fileItems.map((res: any) => ({
            uid: res.object_key,
            name: res.name ?? item.name,
            status: 'done' as const,
            file: item.file,
            uploadData: res,
          })),
        );
        emit('upload-change', key, [...(uploadMap[key] ?? [])]);
      }
    } catch (e: any) {
      if (controller.signal.aborted) return;
      const isTimeout =
        e?.code === 'ECONNABORTED' || /timeout/i.test(e?.message ?? '');
      const errMsg = isTimeout ? '上传超时，请重试' : e?.message || '上传失败';
      const list = uploadMap[key];
      const idx = list?.indexOf(item) ?? -1;
      if (idx !== -1) {
        list![idx]!.status = 'error';
        list![idx]!.errorMsg = errMsg;
      }
      emit('upload-change', key, [...(uploadMap[key] ?? [])]);
      notification.error({
        message: '上传失败',
        description: `${item.name}：${errMsg}`,
        duration: 0,
      });
    } finally {
      abortControllerMap.delete(item.uid);
    }
  });
}

function closeModal() {
  sessionCancelled.value = true;
  emit('cancel');
  const key = props.persistKey;
  const items = uploadMap[key] ?? [];
  // 中止所有 uploading 条目（含队列中等待的——controller 在 enqueue 前已创建并存储）
  for (const item of items) {
    if (item.status === 'uploading') {
      abortControllerMap.get(item.uid)?.abort();
    }
  }
  const remaining = items.filter((f) => f.status !== 'uploading');
  uploadMap[key] = remaining;
  emit('upload-change', key, [...remaining]);
  emit('update:open', false);
}

const closeConfirmationOpen = ref(false);

function requestClose() {
  if (closeConfirmationOpen.value) return;
  if (uploadingFiles.value.length === 0) {
    closeModal();
    return;
  }

  closeConfirmationOpen.value = true;
  Modal.confirm({
    title: '确认取消上传？',
    content: `仍有 ${uploadingFiles.value.length} 个文件正在上传，关闭后将取消这些上传任务。`,
    okText: '取消上传并关闭',
    okType: 'danger',
    cancelText: '继续上传',
    onOk: () => {
      closeConfirmationOpen.value = false;
      closeModal();
    },
    onCancel: () => {
      closeConfirmationOpen.value = false;
    },
  });
}

function handleFileAdded(file: File) {
  if (props.taskCenterUpload && file.size > 10 * 1024 * 1024) {
    message.error(`${file.name} 超过 10 MB，无法上传`);
    return false;
  }
  if (props.maxFiles !== undefined) {
    const existCount = (uploadMap[props.persistKey] ?? []).filter(
      (f) => f.status !== 'error',
    ).length;
    if (existCount >= props.maxFiles) {
      message.warning({
        content: `最多上传 ${props.maxFiles} 个附件`,
        key: 'upload-max-files',
      });
      return false;
    }
  }
  if (!validateUploadFileSize(file, message.error)) return false;
  if (
    !validateFileType(
      file,
      [
        ...ORDER_ATTACHMENT_IMAGE_EXTS,
        ...ORDER_ATTACHMENT_VIDEO_EXTS,
        ...ORDER_ATTACHMENT_ARCHIVE_EXTS,
      ],
      message.error,
    )
  )
    return false;
  const key = props.persistKey;
  const item: UploadFileItem = {
    uid: `${Date.now()}-${Math.random()}`,
    name: file.name,
    status: 'uploading',
    file,
  };
  (uploadMap[key] ??= []).push(item);
  emit('upload-change', key, [...uploadMap[key]]);
  scheduleUpload(item, key);
  return false;
}

function retryFile(key: string, item: UploadFileItem) {
  item.status = 'uploading';
  item.percent = undefined;
  scheduleUpload(item, key);
  emit('upload-change', key, [...(uploadMap[key] ?? [])]);
}

function retryUpload(item: UploadFileItem) {
  retryFile(props.persistKey, item);
}

function removeUpload(item: UploadFileItem) {
  if (item.status === 'uploading') {
    abortControllerMap.get(item.uid)?.abort();
    abortControllerMap.delete(item.uid);
  }
  const list = uploadMap[props.persistKey];
  const idx = list?.indexOf(item) ?? -1;
  if (idx !== -1) list!.splice(idx, 1);
  emit('upload-change', props.persistKey, [
    ...(uploadMap[props.persistKey] ?? []),
  ]);
}

// 暴露给父组件：预填充/清空某个 key 的文件列表
function initFiles(key: string, files: UploadFileItem[]) {
  uploadMap[key] = files;
  if (!files.length) delete uploadStatsMap[key]; // 兜底：清文件时同步清 stats
}

// 展示上传结果通知（从各 poll task 聚合的 stats）
// 必须在 initFiles(key, []) 之前调用，内部会立即清除 stats
function showDeliverResult(key: string, title = '素材提交成功') {
  const s = uploadStatsMap[key];
  delete uploadStatsMap[key];
  if (!s) return;
  const dupCount = s.duplicate_count;
  notification.info({
    message: title,
    description: [
      `总数量：${s.total}`,
      s.success > 0 && `成功：${s.success}`,
      s.failed > 0 && `失败：${s.failed}`,
      dupCount > 0 && `去重：${dupCount}（${s.duplicate_names.join('、')}）`,
    ]
      .filter(Boolean)
      .join(' · '),
    placement: 'topRight',
    duration: dupCount > 0 ? 0 : 4,
  });
}

// key 不存在或列表为空时才初始化，保留已上传但未确认的文件
function initFilesIfEmpty(key: string, files: UploadFileItem[]) {
  if (!(key in uploadMap) || uploadMap[key]!.length === 0) {
    uploadMap[key] = files;
  }
}

onBeforeUnmount(() => {
  for (const controller of abortControllerMap.values()) controller.abort();
  abortControllerMap.clear();
});

defineExpose({
  initFiles,
  initFilesIfEmpty,
  uploadMap,
  retryFile,
  showDeliverResult,
});
</script>

<template>
  <Modal
    :open="open"
    :closable="false"
    :keyboard="true"
    :mask-closable="false"
    :width="'min(1000px, calc(100vw - 24px))'"
    :body-style="{ maxHeight: '72dvh', overflowY: 'auto' }"
    @cancel="requestClose"
  >
    <template #title>
      <div
        class="flex w-full flex-col items-stretch justify-between gap-3 pr-1 sm:flex-row sm:items-start"
      >
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-3">
            <span class="w-full sm:w-auto">{{ title }}</span>
            <template v-if="showDesigner">
              <Select
                v-if="!assignmentMode"
                :value="selectedDesigner"
                :options="designerOptions"
                placeholder="请选择素材师"
                show-search
                option-filter-prop="label"
                class="w-full sm:w-36"
                @change="handleDesignerChange"
              />
              <Select
                v-if="!assignmentMode"
                :value="selectedCreativePlanner"
                :options="creativePlannerOptions"
                placeholder="请选择创意策划（可选）"
                allow-clear
                show-search
                option-filter-prop="label"
                class="w-full sm:w-44"
                @change="handleCreativePlannerChange"
              />
              <Select
                v-if="descriptionOptions?.length"
                :value="selectedReqId"
                :options="descriptionOptions"
                :placeholder="assignmentMode ? '请选择分配项' : '请选择需求点'"
                :aria-label="
                  assignmentMode ? '选择上传对应的分配记录' : '选择需求点'
                "
                class="w-full sm:max-w-lg"
                @change="handleRequirementChange"
              />
            </template>
          </div>
          <p
            v-if="assignmentMode && selectedAssignment"
            class="mt-2 text-sm font-normal"
          >
            素材师：{{ selectedAssignment.designer }} · 创意策划：{{
              selectedAssignment.creativePlanner || '未指定'
            }}
            <span
              v-if="selectedAssignment.remark"
              class="block whitespace-pre-wrap break-words"
              >备注：{{ selectedAssignment.remark }}</span
            >
          </p>
          <p v-if="showDesigner" class="mt-1 text-sm font-normal text-gray-400">
            {{
              assignmentMode
                ? '选择已确认接单的分配项，上传素材后点击“完成”。'
                : '上传完成后确认素材师和需求点，再点击“完成”；创意策划可选。'
            }}
          </p>
        </div>
        <button
          type="button"
          class="min-h-9 self-end rounded px-2 text-sm text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 sm:self-start"
          aria-label="关闭上传弹窗"
          @click="requestClose"
        >
          取消
        </button>
      </div>
    </template>
    <Upload.Dragger
      :accept="uploadAccept"
      :multiple="true"
      :show-upload-list="false"
      :before-upload="handleFileAdded"
    >
      <div class="px-3 py-5 text-center sm:py-6">
        <span
          class="icon-[ant-design--inbox-outlined] mx-auto mb-2 block text-2xl text-gray-400"
        />
        <p class="text-base text-gray-500">点击或将文件拖到此处上传</p>
        <p class="mt-1 text-sm text-gray-400">
          支持视频（MP4/MOV）/ 图片（PNG/JPG/JPEG/GIF）/
          压缩包（ZIP/7Z），单文件 ≤
          {{ taskCenterUpload ? '10 MB' : '10 GB' }}
        </p>
        <p class="mt-1 text-sm text-gray-400">如需上传更多文件, 请上传压缩包</p>
      </div>
    </Upload.Dragger>

    <div
      v-if="uploadFileList.length"
      class="mt-3 grid max-h-[var(--adpulse-popup-table-height)] grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3"
    >
      <div
        v-for="f in uploadFileList"
        :key="f.uid"
        class="flex min-w-0 items-center justify-between gap-2 rounded-md border border-gray-100 px-3 py-2 text-sm"
      >
        <span class="min-w-0 flex-1 truncate text-gray-700" :title="f.name">{{
          f.name
        }}</span>
        <div class="flex flex-shrink-0 items-center gap-2">
          <template v-if="f.status === 'uploading'">
            <template v-if="f.percent !== undefined && f.percent < 100">
              <!-- 网络传输中 -->
              <Progress
                :percent="f.percent"
                :stroke-width="4"
                style="width: 80px"
                status="active"
              />
            </template>
            <template v-else-if="f.percent === 100">
              <!-- 字节已到服务器，等待后端处理 -->
              <span
                class="icon-[ant-design--loading-outlined] animate-spin text-base text-blue-400"
              />
              <span class="text-xs text-gray-400">处理中...</span>
            </template>
            <template v-else>
              <!-- 排队等待中-->
              <span
                class="icon-[ant-design--loading-outlined] animate-spin text-base text-gray-300"
              />
              <span class="text-xs text-gray-300">等待中...</span>
            </template>
          </template>
          <template v-else-if="f.status === 'done'">
            <span
              class="icon-[ant-design--check-circle-outlined] text-green-500"
            />
            <button
              type="button"
              :aria-label="`移除已上传文件 ${f.name}`"
              class="rounded text-gray-400 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              @click.stop="removeUpload(f)"
            >
              <span class="icon-[ant-design--close-circle-outlined]" />
            </button>
          </template>
          <template v-else>
            <span
              v-if="f.errorMsg"
              class="max-w-[80px] truncate text-xs text-red-400"
              :title="f.errorMsg"
              >{{ f.errorMsg }}</span
            >
            <button
              type="button"
              :aria-label="`移除上传失败的文件 ${f.name}`"
              class="rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              @click.stop="removeUpload(f)"
            >
              <span
                class="icon-[ant-design--close-circle-outlined] text-red-400"
              />
            </button>
            <button
              type="button"
              class="rounded text-xs text-blue-500 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              @click="retryUpload(f)"
            >
              重试
            </button>
          </template>
        </div>
      </div>
    </div>

    <template #footer>
      <div
        class="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <span
          class="text-left text-sm"
          :class="failedFiles.length ? 'text-red-500' : 'text-gray-500'"
          aria-live="polite"
        >
          {{ uploadStatusText }}
        </span>
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button class="w-full sm:w-auto" @click="requestClose">
            {{ showDesigner ? '取消' : '关闭' }}
          </Button>
          <Button
            v-if="showDesigner"
            type="primary"
            class="w-full sm:w-auto"
            :disabled="!canSubmit"
            @click="submitCompletedFiles"
          >
            完成
          </Button>
        </div>
      </div>
    </template>
  </Modal>
</template>
