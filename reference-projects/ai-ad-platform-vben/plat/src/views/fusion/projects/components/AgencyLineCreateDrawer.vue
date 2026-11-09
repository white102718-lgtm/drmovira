<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import type { ProjectPlatformCode, ProjectContextOption } from '#/api';
import type { AgencyLine, AgencyLineUpsertInput } from '#/domain/agency-line';

import { computed, nextTick, reactive, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Col,
  Drawer,
  Form,
  FormItem,
  Input,
  message,
  Row,
  Select,
} from 'ant-design-vue';

import { getUserList } from '#/api/system/user';
import { agencyLineService } from '#/domain/agency-line';
import {
  selectedOptimizer,
  withHistoricalOptimizer,
} from '#/domain/agency-line/optimizer';

interface AgencyLineFormState {
  cloakUrl: string;
  deliveryUrl: string;
  name: string;
  optimizerId?: string;
  pageId: string;
  pixelId: string;
  pixelName: string;
  platform?: ProjectPlatformCode;
  projectId?: string;
  testCode: string;
  token: string;
  type: string;
}

interface OptimizerOption {
  label: string;
  name: string;
  value: string;
}

interface CreateAttempt {
  fingerprint: string;
  requestId: string;
}

const props = defineProps<{
  /** When opened from a project detail, bind the new line to that project. */
  initialProjectId?: string;
  open: boolean;
  editingLine?: AgencyLine;
  platformOptions: Array<{ label: string; value: ProjectPlatformCode }>;
  projects: ProjectContextOption[];
}>();

const emit = defineEmits<{
  (event: 'openBatchImport'): void;
  (event: 'created', line: AgencyLine, projectId?: string): void;
  (event: 'saved', line: AgencyLine): void;
  (event: 'update:open', open: boolean): void;
}>();

const formRef = ref<FormInstance>();
const saving = ref(false);
const optimizerLoading = ref(false);
const optimizerLoadError = ref('');
const optimizerOptions = ref<OptimizerOption[]>([]);
const createAttempt = ref<CreateAttempt>();

const displayedOptimizerOptions = computed(() =>
  withHistoricalOptimizer(optimizerOptions.value, props.editingLine),
);

function getInitialState(): AgencyLineFormState {
  return {
    cloakUrl: '',
    deliveryUrl: '',
    name: '',
    optimizerId: undefined,
    pageId: '',
    pixelId: '',
    pixelName: '',
    platform: 'facebook',
    projectId: undefined,
    testCode: '',
    token: '',
    type: '',
  };
}

const formState = reactive<AgencyLineFormState>(getInitialState());

const projectOptions = computed(() =>
  props.projects.map((project) => ({
    label: `${project.name} · ${project.projectCode}`,
    value: project.id,
  })),
);

const selectedProject = computed(() =>
  props.projects.find((project) => project.id === formState.projectId),
);

function resetForm() {
  Object.assign(formState, getInitialState());
  if (props.editingLine) {
    Object.assign(formState, props.editingLine);
  } else if (props.initialProjectId) {
    formState.projectId = props.initialProjectId;
  }
  createAttempt.value = undefined;
  optimizerLoadError.value = '';
  void nextTick(() => formRef.value?.clearValidate());
}

async function loadOptimizerOptions() {
  optimizerLoading.value = true;
  optimizerLoadError.value = '';
  try {
    const seen = new Set<string>();
    const options: OptimizerOption[] = [];
    // 完整分页读取启用人员，避免迁入人员落在第二页后无法选择。
    for (let page = 1; ; page += 1) {
      const result = await getUserList({ page, pageSize: 200, status: 1 });
      for (const user of result.items) {
        if (seen.has(user.id) || user.status !== 1) continue;
        seen.add(user.id);
        const name = user.realName || user.displayName || user.id;
        options.push({ label: name, name, value: user.id });
      }
      if (page * 200 >= result.total) break;
      if (!result.items.length) throw new Error('人员列表分页中断');
    }
    optimizerOptions.value = options;
  } catch {
    optimizerOptions.value = [];
    optimizerLoadError.value =
      '投手列表加载失败，请重试；已有归属仍会保留，也可明确清空。';
  } finally {
    optimizerLoading.value = false;
  }
}

function validateHttpUrl() {
  const value = formState.deliveryUrl.trim();
  if (!value || /^https?:\/\//i.test(value)) return Promise.resolve();
  return Promise.reject(new Error('投放链接必须以 http:// 或 https:// 开头'));
}

function validateCloakUrl() {
  const value = formState.cloakUrl.trim();
  if (!value || /^https?:\/\//i.test(value)) return Promise.resolve();
  return Promise.reject(new Error('斗篷链接必须以 http:// 或 https:// 开头'));
}

function closeDrawer() {
  if (!saving.value) emit('update:open', false);
}

function openBatchImport() {
  if (saving.value) return;
  emit('update:open', false);
  emit('openBatchImport');
}

function isFormValidationError(
  error: unknown,
): error is { errorFields: unknown[] } {
  return typeof error === 'object' && error !== null && 'errorFields' in error;
}

function getCreateRequestId(input: AgencyLineUpsertInput) {
  const fingerprint = JSON.stringify(input);
  if (createAttempt.value?.fingerprint === fingerprint) {
    return createAttempt.value.requestId;
  }
  const suffix =
    typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const requestId = `agency-line-create-${suffix}`;
  createAttempt.value = { fingerprint, requestId };
  return requestId;
}

async function submitForm() {
  try {
    await formRef.value?.validate();
    const project = selectedProject.value;
    const platform = formState.platform;
    if (!platform) return;

    const optimizer = selectedOptimizer(
      formState.optimizerId,
      displayedOptimizerOptions.value,
    );
    const input: AgencyLineUpsertInput = {
      autoRun: false,
      cloakUrl: formState.cloakUrl.trim(),
      deliveryUrl: formState.deliveryUrl.trim(),
      enabled: true,
      isSend: false,
      legacyGamePlatform: project?.name,
      name: formState.name.trim(),
      objective: '',
      ...optimizer,
      packageName: '',
      packageType: '',
      pageId: formState.pageId.trim(),
      pixelId: formState.pixelId.trim(),
      pixelName: formState.pixelName.trim(),
      platform,
      projectId: props.editingLine?.projectId ?? project?.id,
      testCode: formState.testCode.trim(),
      token: formState.token.trim(),
      type: formState.type.trim(),
    };

    saving.value = true;
    if (props.editingLine) {
      const saved = await agencyLineService.save({
        ...input,
        id: props.editingLine.id,
      });
      message.success('代理线保存成功');
      emit('saved', saved);
      emit('update:open', false);
      return;
    }
    const savedLine = await agencyLineService.create(
      input,
      getCreateRequestId(input),
    );
    message.success(
      project
        ? '代理线创建成功，正在绑定项目'
        : '代理线创建成功，可稍后绑定项目',
    );
    emit('created', savedLine, project?.id);
    emit('update:open', false);
  } catch (error) {
    if (!isFormValidationError(error)) {
      message.error(error instanceof Error ? error.message : '代理线创建失败');
    }
  } finally {
    saving.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    resetForm();
    void loadOptimizerOptions();
  },
  { immediate: true },
);
</script>

<template>
  <Drawer
    :open="open"
    :closable="!saving"
    :mask-closable="!saving"
    :title="editingLine ? '编辑代理线' : '新建代理线'"
    width="min(720px, 100vw)"
    @close="closeDrawer"
  >
    <Alert
      class="mb-5"
      type="info"
      show-icon
      message="投手可留空。历史停用人员可保留，也可清空或更换为启用人员。"
    />

    <Alert
      v-if="optimizerLoadError"
      class="mb-5"
      type="warning"
      show-icon
      :message="optimizerLoadError"
    >
      <template #action>
        <Button :loading="optimizerLoading" @click="loadOptimizerOptions">
          重试
        </Button>
      </template>
    </Alert>

    <Form ref="formRef" :model="formState" layout="vertical">
      <Row :gutter="[16, 0]">
        <Col :xs="24" :md="12">
          <FormItem
            label="类型"
            name="type"
            :rules="[{ max: 50, message: '类型不能超过 50 个字符' }]"
          >
            <Input
              v-model:value="formState.type"
              :maxlength="50"
              placeholder="请输入类型"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="投放平台"
            name="platform"
            :rules="[{ required: true, message: '请选择投放平台' }]"
          >
            <Select
              v-model:value="formState.platform"
              placeholder="请选择平台"
              :options="props.platformOptions"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem label="像素名称" name="pixelName">
            <Input
              v-model:value="formState.pixelName"
              placeholder="请输入像素名称"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="像素 ID"
            name="pixelId"
            :rules="[{ max: 100, message: '像素 ID 不能超过 100 个字符' }]"
          >
            <Input
              v-model:value="formState.pixelId"
              :maxlength="100"
              placeholder="请输入像素 ID"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="Token"
            name="token"
            :rules="[{ max: 10000, message: 'Token 不能超过 10000 个字符' }]"
          >
            <Input.Password
              v-model:value="formState.token"
              :maxlength="10000"
              autocomplete="new-password"
              placeholder="请输入 Token"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="测试代码"
            name="testCode"
            :rules="[{ max: 200, message: '测试代码不能超过 200 个字符' }]"
          >
            <Input
              v-model:value="formState.testCode"
              :maxlength="200"
              placeholder="请输入测试代码"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="代理线"
            name="name"
            :rules="[
              { required: true, whitespace: true, message: '请输入代理线名称' },
              { max: 80, message: '代理线名称不能超过 80 个字符' },
            ]"
          >
            <Input
              v-model:value="formState.name"
              :maxlength="80"
              placeholder="例如：美国 Facebook 主线"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="投放链接"
            name="deliveryUrl"
            :rules="[
              { max: 2000, message: '投放链接不能超过 2000 个字符' },
              { validator: validateHttpUrl },
            ]"
          >
            <Input
              v-model:value="formState.deliveryUrl"
              :maxlength="2000"
              placeholder="https://example.com/landing-page"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem label="投手" name="optimizerId">
            <Select
              v-model:value="formState.optimizerId"
              allow-clear
              show-search
              option-filter-prop="label"
              placeholder="未分配"
              :loading="optimizerLoading"
              :options="displayedOptimizerOptions"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="斗篷链接"
            name="cloakUrl"
            :rules="[
              { max: 2000, message: '斗篷链接不能超过 2000 个字符' },
              { validator: validateCloakUrl },
            ]"
          >
            <Input
              v-model:value="formState.cloakUrl"
              :maxlength="2000"
              placeholder="https://example.com/cloak"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem label="关联项目（选填）" name="projectId">
            <Select
              v-model:value="formState.projectId"
              :disabled="Boolean(editingLine)"
              allow-clear
              show-search
              option-filter-prop="label"
              placeholder="可稍后绑定项目"
              :options="projectOptions"
            />
          </FormItem>
        </Col>

        <Col :xs="24" :md="12">
          <FormItem
            label="主页 ID"
            name="pageId"
            :rules="[{ max: 255, message: '主页 ID 不能超过 255 个字符' }]"
          >
            <Input
              v-model:value="formState.pageId"
              :maxlength="255"
              placeholder="请输入主页 ID"
            />
          </FormItem>
        </Col>
      </Row>
    </Form>

    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <Button
          v-if="!editingLine"
          class=""
          :disabled="saving"
          @click="openBatchImport"
        >
          批量导入
        </Button>
        <div class="flex justify-end gap-3">
          <Button class="min-w-20" :disabled="saving" @click="closeDrawer">
            取消
          </Button>
          <Button
            class="min-w-24"
            type="primary"
            :loading="saving"
            @click="submitForm"
          >
            {{ editingLine ? '保存' : '创建代理线' }}
          </Button>
        </div>
      </div>
    </template>
  </Drawer>
</template>
