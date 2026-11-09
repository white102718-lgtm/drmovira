<script setup lang="ts">
import type { FormProps, UploadFile, UploadProps } from 'ant-design-vue';

import type { FeedbackCategory } from '#/api';

import { reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Form,
  FormItem,
  Input,
  message,
  Select,
  Switch,
  Upload,
} from 'ant-design-vue';

import {
  createFeedbackApi,
  deleteFeedbackAttachmentApi,
  uploadFeedbackAttachmentApi,
} from '#/api';
import {
  clearFeedbackConsoleEntries,
  collectFeedbackDiagnostics,
} from '#/utils/feedback-diagnostics';

const MAX_FILE_COUNT = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_MEDIA_TYPES = 'image/*,video/*';
const ALLOWED_MEDIA_EXTENSIONS = new Set([
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'mp4',
  'mov',
]);

const route = useRoute();
const submitting = ref(false);
const includeDiagnostics = ref(true);
const files = ref<UploadFile[]>([]);
const uploadedFileIds = new Map<string, string>();
const form = reactive({
  category: 'FEATURE' as FeedbackCategory,
  content: '',
  title: '',
});

const categoryOptions = [
  { label: '功能需求', value: 'FEATURE' },
  { label: '问题反馈', value: 'BUG' },
  { label: '体验建议', value: 'EXPERIENCE' },
];
const validationRules: FormProps['rules'] = {
  category: [{ message: '请选择反馈类型', required: true }],
  content: [
    { message: '请填写反馈内容', required: true, trigger: 'blur' },
    { max: 5000, message: '反馈内容不能超过 5000 个字', trigger: 'blur' },
  ],
  title: [
    { message: '请填写反馈标题', required: true, trigger: 'blur' },
    { max: 100, message: '反馈标题不能超过 100 个字', trigger: 'blur' },
  ],
};

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  if (files.value.length >= MAX_FILE_COUNT) {
    message.warning(`最多上传 ${MAX_FILE_COUNT} 个附件`);
    return Upload.LIST_IGNORE;
  }
  if (file.size > MAX_FILE_SIZE) {
    message.warning(`${file.name} 超过 10 MB，无法上传`);
    return Upload.LIST_IGNORE;
  }
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (
    !ALLOWED_MEDIA_EXTENSIONS.has(extension) ||
    !/^(image|video)\//.test(file.type)
  ) {
    message.warning(
      `${file.name} 不是支持的图片或视频文件，请上传 PNG、JPG、JPEG、GIF、WEBP、MP4 或 MOV 格式`,
    );
    return Upload.LIST_IGNORE;
  }
  if (
    files.value.some(
      (item) =>
        item.name === file.name &&
        item.size === file.size &&
        item.originFileObj?.lastModified === file.lastModified,
    )
  ) {
    message.warning(`${file.name} 已在附件列表中`);
    return Upload.LIST_IGNORE;
  }
  files.value.push({
    name: file.name,
    originFileObj: file,
    size: file.size,
    status: 'done',
    type: file.type,
    uid: file.uid,
  });
  return Upload.LIST_IGNORE;
};

const handleRemove: UploadProps['onRemove'] = async (file) => {
  const uploadedFileId = uploadedFileIds.get(file.uid);
  if (uploadedFileId) {
    await deleteFeedbackAttachmentApi(uploadedFileId);
    uploadedFileIds.delete(file.uid);
  }
  files.value = files.value.filter((item) => item.uid !== file.uid);
  return true;
};

function resetForm() {
  form.category = 'FEATURE';
  form.title = '';
  form.content = '';
  files.value = [];
  uploadedFileIds.clear();
}

async function handleSubmit() {
  submitting.value = true;
  try {
    const hasUnreadableFile = files.value.some((file) => !file.originFileObj);
    if (hasUnreadableFile) {
      message.error('附件读取失败，请移除后重新选择');
      return;
    }
    const attachmentFileIds = await Promise.all(
      files.value.map(async (file) => {
        const cachedFileId = uploadedFileIds.get(file.uid);
        if (cachedFileId) return cachedFileId;
        const originalFile = file.originFileObj;
        if (!originalFile) throw new Error('附件读取失败，请移除后重新选择');
        const uploaded = await uploadFeedbackAttachmentApi(originalFile);
        uploadedFileIds.set(file.uid, uploaded.id);
        return uploaded.id;
      }),
    );
    await createFeedbackApi({
      attachmentFileIds,
      category: form.category,
      content: form.content.trim(),
      diagnostics: includeDiagnostics.value
        ? collectFeedbackDiagnostics(String(route.name ?? route.path))
        : undefined,
      title: form.title.trim(),
    });
    message.success('反馈已提交，感谢您的建议');
    clearFeedbackConsoleEntries();
    resetForm();
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Page
    description="提交产品需求、问题或体验建议；附件和诊断信息可以帮助我们更快定位问题。"
    title="需求建议反馈"
  >
    <div class="w-full space-y-3">
      <Alert
        show-icon
        message="提交时会记录账号和 IP；诊断信息仅采集脱敏后的设备、浏览器与当前页面信息。"
        type="info"
      />

      <Card :bordered="false">
        <Form
          class=""
          layout="vertical"
          :model="form"
          :rules="validationRules"
          @finish="handleSubmit"
        >
          <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <FormItem label="反馈类型" name="category">
              <Select
                v-model:value="form.category"
                :options="categoryOptions"
                aria-label="反馈类型"
              />
            </FormItem>
            <FormItem label="反馈标题" name="title">
              <Input
                v-model:value="form.title"
                :maxlength="100"
                allow-clear
                placeholder="用一句话概括需求或问题"
                show-count
              />
            </FormItem>
          </div>

          <FormItem label="反馈内容" name="content">
            <Input.TextArea
              v-model:value="form.content"
              :auto-size="{ minRows: 4, maxRows: 8 }"
              :maxlength="5000"
              placeholder="请说明使用场景、操作步骤、实际结果和期待效果；问题反馈可注明大致发生时间"
              show-count
            />
          </FormItem>

          <FormItem label="相关附件（可选）">
            <Upload.Dragger
              :accept="ACCEPTED_MEDIA_TYPES"
              :before-upload="beforeUpload"
              :file-list="files"
              :multiple="true"
              :on-remove="handleRemove"
            >
              <p class="mb-1">
                <IconifyIcon
                  aria-hidden="true"
                  class="text-primary mx-auto size-6"
                  icon="lucide:cloud-upload"
                />
              </p>
              <p class="ant-upload-text text-sm">点击或拖拽文件到此处</p>
              <p class="ant-upload-hint">
                支持图片和视频，最多 5 个，单个不超过 10 MB
              </p>
            </Upload.Dragger>
          </FormItem>

          <div
            class="border-border flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="flex min-w-0 items-center gap-3">
              <Switch
                v-model:checked="includeDiagnostics"
                aria-label="随反馈附带诊断信息"
              />
              <div>
                <p class="text-foreground m-0 text-sm font-medium">
                  随反馈附带诊断信息
                </p>
                <p class="text-muted-foreground m-0 text-xs">
                  建议开启，便于复现和定位问题
                </p>
              </div>
            </div>
            <Button
              class="w-full sm:w-auto"
              html-type="submit"
              :disabled="submitting"
              :loading="submitting"
              type="primary"
            >
              {{ submitting ? '正在上传并提交' : '提交反馈' }}
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  </Page>
</template>

<style scoped></style>
