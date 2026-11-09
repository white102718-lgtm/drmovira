<script lang="ts" setup>
import { computed, ref, watch } from 'vue';

import {
  Button,
  Form,
  message,
  Modal,
  Progress,
  Select,
  Upload,
} from 'ant-design-vue';

import { useUserStore } from '@vben/stores';

import { addMaterialApi, uploadCommonMaterialApi } from '#/api';
import { useUploadQueue } from '#/composables/useUploadQueue';
import { MATERIAL_ALLOWED_EXTS, validateFileType } from '#/utils/upload';
import PlatformSelect from '#/views/components/PlatformSelect.vue';
import TagComboSelect from './TagComboSelect.vue';

interface MyTag {
  is_necessary: string;
  name: string;
  tags: string[];
  title: string;
}

interface Props {
  open: boolean;
  folderId?: string; // undefined = 公共素材库，有值 = 个人文件夹
  allMode?: boolean; // 所有素材模式：需填写投手等配置
  factTags?: MyTag[];
  operatorOptions?: Array<{ label: string; value: string }>;
  creativeEditorOptions?: Array<{ label: string; value: string }>;
  platformOptions?: Array<{ label: string; value: string }>;
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'success'): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const userStore = useUserStore();

const tagsNew = ref<string[]>([]);

// allMode 配置表单
const uploadConfigForm = ref<Record<string, any>>({
  country: undefined,
  operator: undefined,
  CreativeEditor: undefined,
  game_platform: undefined,
});

watch(
  () => props.open,
  async (val) => {
    if (val) {
      // allMode: 弹窗打开时 options 已就绪，直接设置默认投手（优先当前登录用户）
      if (props.allMode) {
        const options = props.operatorOptions;
        if (options?.length) {
          const currentRealName = userStore.userInfo?.realName;
          uploadConfigForm.value.operator =
            currentRealName && options.some((o) => o.value === currentRealName)
              ? currentRealName
              : options[0]?.value;
        }
      }
    } else {
      tagsNew.value = [];
    }
  },
);

const uploadResults = ref({ success: 0, duplicate: 0 });
const uploadedFiles = ref<
  Array<{
    errorMsg?: string;
    filename?: string;
    filetype: 'image' | 'video';
    isDuplicate?: boolean;
    name: string;
    percent?: number;
    status: 'error' | 'pending' | 'success' | 'uploading';
    thumbUrl?: string;
    uid: string;
  }>
>([]);

// 当前可见的错误文件数（重复不算错误，随文件删除自动同步）
const fileErrorNum = computed(
  () =>
    uploadedFiles.value.filter((f) => f.status === 'error' && !f.isDuplicate)
      .length,
);

const { activeUploads, pendingCount, enqueue } = useUploadQueue(5, () => {
  emit('success');
});

const clearRecords = () => {
  uploadResults.value = { success: 0, duplicate: 0 };
  uploadedFiles.value = [];
};

const removeFile = (uid: string) => {
  uploadedFiles.value = uploadedFiles.value.filter((f) => f.uid !== uid);
};

function beforeMaterialUpload(file: File): boolean {
  return validateFileType(file, MATERIAL_ALLOWED_EXTS, message.error);
}

const handleUpload = (file: any) => {
  if (props.allMode && !uploadConfigForm.value.operator) {
    message.error('请选择投手后再上传文件。');
    return;
  }

  const uid = `${Date.now()}-${file.name}`;
  if (activeUploads.value === 0 && pendingCount.value === 0) {
    uploadResults.value = { success: 0, duplicate: 0 };
  }
  uploadedFiles.value.unshift({
    uid,
    name: file.name,
    status: 'pending',
    filetype: file.type?.startsWith('video/') ? 'video' : 'image',
  });

  enqueue(async () => {
    uploadedFiles.value = uploadedFiles.value.map((item) =>
      item.uid === uid ? { ...item, status: 'uploading' as const } : item,
    );

    const onProgress = (percent: number) => {
      uploadedFiles.value = uploadedFiles.value.map((f) =>
        f.uid === uid ? { ...f, percent } : f,
      );
    };

    try {
      const formData = new FormData();
      formData.append('file', file);

      let results: any[];
      let duplicateMsg: string;

      if (props.folderId || props.allMode) {
        // 个人文件夹 或 所有素材模式 — 统一使用 addMaterialApi
        if (props.allMode) {
          const { country, operator, CreativeEditor, game_platform } =
            uploadConfigForm.value;
          if (country) formData.append('country', country);
          if (operator) formData.append('operator', operator);
          if (CreativeEditor)
            formData.append('creative_editor', CreativeEditor);
          if (game_platform) formData.append('game_platform', game_platform);
        }
        if (props.folderId) formData.append('folder_id', props.folderId);
        tagsNew.value.forEach((tag) => {
          if (tag != null) formData.append('tags_new', tag);
        });
        results = (await addMaterialApi(formData, onProgress)) as any[];
        duplicateMsg = '文件重复';
      } else {
        // 公共素材库
        results = (await uploadCommonMaterialApi(
          formData,
          tagsNew.value,
          undefined,
          onProgress,
        )) as any[];
        duplicateMsg = '该素材已存在';
      }

      const idx = uploadedFiles.value.findIndex((f) => f.uid === uid);
      if (idx !== -1) {
        const mapped = results.map((d: any) => {
          const isDuplicate = d?.message === duplicateMsg;
          if (isDuplicate) uploadResults.value.duplicate++;
          else uploadResults.value.success++;
          return {
            uid: d?.id || `${uid}-${Math.random()}`,
            name:
              results.length > 1
                ? d?.origin_filename || d?.basename || file.name
                : file.name,
            filetype: (d?.filetype === 'video' ? 'video' : 'image') as
              | 'image'
              | 'video',
            status: isDuplicate ? ('error' as const) : ('success' as const),
            isDuplicate,
            thumbUrl: d?.img ? `data:image/png;base64,${d.img}` : undefined,
            filename: d?.filename || d?.basename,
            errorMsg: isDuplicate ? `${duplicateMsg} ` : undefined,
          };
        });
        uploadedFiles.value.splice(idx, 1, ...mapped);
      }
    } catch (e: any) {
      const isTimeout =
        e?.code === 'ECONNABORTED' || /timeout/i.test(e?.message ?? '');
      const errorMsg = isTimeout ? '上传超时，请重新上传' : '上传失败';
      uploadedFiles.value = uploadedFiles.value.map((item) =>
        item.uid === uid
          ? { ...item, status: 'error' as const, errorMsg }
          : item,
      );
    }
  });
};
</script>

<template>
  <Modal
    :open="open"
    title="上传素材"
    :footer="null"
    :width="
      allMode
        ? 'min(1200px, calc(100vw - 24px))'
        : 'min(900px, calc(100vw - 24px))'
    "
    :body-style="{ maxHeight: '72dvh', overflowY: 'auto' }"
    @update:open="emit('update:open', $event)"
    @close="emit('update:open', false)"
  >
    <Form
      v-if="allMode"
      layout="vertical"
      class="mb-2 grid grid-cols-1 gap-x-2 sm:grid-cols-2 lg:grid-cols-5"
    >
      <Form.Item label="国家">
        <Select
          v-model:value="uploadConfigForm.country"
          :options="
            (factTags?.find((f) => f.name === 'country')?.tags || []).map(
              (tag) => ({ label: tag, value: tag }),
            )
          "
          placeholder="请选择国家"
          allow-clear
          show-search
          :filter-option="
            (input, option) =>
              option?.label?.toLowerCase().includes(input.toLowerCase())
          "
        />
      </Form.Item>
      <Form.Item label="投手" required>
        <Select
          v-model:value="uploadConfigForm.operator"
          :options="operatorOptions"
          placeholder="请选择投手"
          allow-clear
          show-search
          :filter-option="
            (input, option) =>
              option?.label?.toLowerCase().includes(input.toLowerCase())
          "
        />
      </Form.Item>
      <Form.Item label="剪辑">
        <Select
          v-model:value="uploadConfigForm.CreativeEditor"
          :options="creativeEditorOptions"
          placeholder="请选择剪辑"
          allow-clear
          show-search
          :filter-option="
            (input, option) =>
              option?.label?.toLowerCase().includes(input.toLowerCase())
          "
        />
      </Form.Item>
      <Form.Item label="平台">
        <PlatformSelect
          :value="uploadConfigForm.game_platform"
          :options="platformOptions"
          placeholder="请选择平台"
          style="width: 100%"
          @update:value="(val) => (uploadConfigForm.game_platform = val)"
        />
      </Form.Item>
      <Form.Item label="标签">
        <TagComboSelect
          v-model="tagsNew"
          placeholder="请选择标签"
          style="width: 100%"
        />
      </Form.Item>
    </Form>

    <!-- 上传拖拽区 -->
    <div class="mb-2">
      <Upload.Dragger
        :custom-request="(options) => handleUpload(options.file)"
        :before-upload="beforeMaterialUpload"
        :multiple="true"
        :show-upload-list="false"
      >
        <span class="icon-[ant-design--inbox-outlined] text-2xl"></span>
        <p class="text-sm">点击或拖拽文件到此区域</p>
        <p class="text-xs text-gray-500">
          支持图片（JPG/PNG/GIF 等）/ 视频（MP4/MOV/AVI 等）/
          压缩包（ZIP/7Z），可批量上传
        </p>
      </Upload.Dragger>
    </div>

    <!-- 进度统计 -->
    <div class="mt-1 flex justify-center gap-3 text-xs text-gray-500">
      <span v-if="activeUploads > 0">上传中 {{ activeUploads }}</span>
      <span v-if="pendingCount > 0">排队 {{ pendingCount }}</span>
      <span v-if="uploadResults.success > 0"
        >成功 {{ uploadResults.success }}</span
      >
      <span v-if="uploadResults.duplicate > 0"
        >重复 {{ uploadResults.duplicate }}</span
      >
      <span v-if="fileErrorNum > 0" class="text-red-500"
        >错误 {{ fileErrorNum }}</span
      >
    </div>

    <!-- 已上传文件列表 -->
    <div v-if="uploadedFiles.length > 0" class="mt-3 flex flex-col">
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-medium"
          >已上传文件 ({{ uploadedFiles.length }})</span
        >
        <Button @click="clearRecords">清空记录</Button>
      </div>
      <div
        class="grid grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5"
        style="max-height: 480px"
      >
        <div
          v-for="file in uploadedFiles"
          :key="file.uid"
          class="group relative h-[155px] min-w-0 overflow-hidden rounded border bg-white p-2"
        >
          <div class="mb-1 h-[100px] w-full overflow-hidden rounded">
            <img
              v-if="file.thumbUrl"
              :src="file.thumbUrl"
              class="h-full w-full object-contain"
              :alt="file.name"
            />
            <div
              v-else
              class="flex h-full flex-col items-center justify-center gap-1"
            >
              <span
                v-if="file.status === 'pending'"
                class="icon-[ant-design--clock-circle-outlined] text-2xl text-gray-400"
              ></span>
              <template v-else-if="file.status === 'uploading'">
                <template
                  v-if="file.percent !== undefined && file.percent < 100"
                >
                  <Progress
                    :percent="file.percent"
                    :stroke-width="4"
                    status="active"
                    style="width: 80%"
                  />
                </template>
                <template v-else>
                  <span
                    class="icon-[ant-design--loading-outlined] animate-spin text-2xl text-blue-400"
                  ></span>
                  <span
                    v-if="file.percent === 100"
                    class="text-xs text-gray-400"
                    >处理中...</span
                  >
                </template>
              </template>
              <span
                v-else
                class="icon-[ant-design--file-outlined] text-2xl"
              ></span>
            </div>
            <span
              v-if="file.filetype === 'video' && file.thumbUrl"
              class="icon-[ant-design--play-circle-filled] pointer-events-none absolute inset-0 m-auto text-2xl text-white opacity-80"
              style="width: fit-content; height: fit-content"
            ></span>
            <Button
              v-if="file.status !== 'uploading'"
              danger
              class="absolute right-[4px] top-[4px] !h-8 !w-8 !min-w-0 !p-0 opacity-90 transition-opacity hover:opacity-100"
              :aria-label="`移除 ${file.name}`"
              @click="removeFile(file.uid)"
            >
              <span class="icon-[ant-design--delete-outlined]"></span>
            </Button>
          </div>
          <div
            class="truncate text-xs"
            :title="file.errorMsg ? `${file.errorMsg} ${file.name}` : file.name"
          >
            <span v-if="file.errorMsg" class="mr-1 text-red-500">{{
              file.errorMsg
            }}</span>
            <span>{{ file.name }}</span>
          </div>
          <div class="truncate text-xs" :title="file.filename">
            {{ file.filename }}
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
