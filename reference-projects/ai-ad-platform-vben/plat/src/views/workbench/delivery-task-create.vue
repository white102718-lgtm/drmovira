<script lang="ts" setup>
import type {
  FormInstance,
  FormProps,
  UploadFile,
  UploadProps,
} from 'ant-design-vue';

import type { ProjectSummary } from '#/api';
import type { AgencyLine } from '#/domain/agency-line';
import type { ProjectSearchOption } from '#/domain/project';
import type {
  DeliveryTaskFormData,
  TaskAttachmentMeta,
} from '#/store/task-center';

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  DatePicker,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Select,
  Tag,
  Upload,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  createDeliveryTaskApi,
  getTaskApi,
  createTaskDraftApi,
  getTaskDraftApi,
  updateTaskDraftApi,
  resubmitDeliveryTaskApi,
  uploadTaskFileApi,
} from '#/api';
import { useDeliveryTaskAccess } from '#/composables/useDeliveryTaskAccess';
import { agencyLineService } from '#/domain/agency-line';
import { projectService } from '#/domain/project';
import facebookCountries from '#/data/facebook_countries.json';
import { useTaskCenterStore } from '#/store/task-center';

import { validateDeliveryItems } from '#/domain/task/delivery-items';

import StableUserSelect from '../components/StableUserSelect.vue';
import DeliveryTaskItems from './components/DeliveryTaskItems.vue';

defineOptions({ name: 'WorkbenchDeliveryTaskCreate' });

const route = useRoute();
const router = useRouter();
const taskCenterStore = useTaskCenterStore();
const userStore = useUserStore();
const { canCreateDeliveryTask } = useDeliveryTaskAccess();

const formRef = ref<FormInstance>();
type DeliveryAttachmentFile = UploadFile & { serverFileId?: string };

const attachmentFiles = ref<DeliveryAttachmentFile[]>([]);
const currentDraftId = ref('');
const resubmitTaskId = ref('');
const canSubmitCurrentForm = computed(
  () => Boolean(resubmitTaskId.value) || canCreateDeliveryTask.value,
);
const initialSnapshot = ref('');
const allocationError = ref('');
const savingDraft = ref(false);
const submitting = ref(false);
const submitError = ref('');
const leavingAfterSubmit = ref(false);
const projectLeaderMessage = ref('');
const selectedProjectContext = ref<null | ProjectSummary>(null);
const selectedProjectAgencyLines = ref<AgencyLine[]>([]);
const projectContextLoading = ref(false);
const projectOptionsLoading = ref(false);
const projectSelectOptions = ref<ProjectSearchOption[]>([]);
const hydratingDraft = ref(false);
let projectContextRequest = 0;

function createDefaultForm(): DeliveryTaskFormData {
  return {
    allocations: [],
    items: [],
    amOwner: '',
    attachments: [],
    dueAt: '',
    platforms: [],
    productUrl: '',
    ownerId: undefined,
    ownerName: undefined,
    projectId: '',
    projectName: '',
    region: '',
    startAt: dayjs().add(1, 'day').hour(9).minute(0).format('YYYY-MM-DD HH:mm'),
    target: '',
    title: '',
  };
}

const formState = reactive<DeliveryTaskFormData>(createDefaultForm());

const currentUserName = computed(
  () =>
    userStore.userInfo?.realName || userStore.userInfo?.full_name || '当前用户',
);

const projectOptions = computed(() =>
  projectSelectOptions.value.map((project) => ({
    label: project.name,
    value: project.id,
  })),
);

const platformOptions = [
  { label: 'Facebook', value: 'Facebook' },
  { label: 'Google', value: 'Google' },
  { label: 'TikTok', value: 'TikTok' },
  { label: 'Kwai', value: 'Kwai' },
];

const projectPlatformLabels: Record<string, string> = {
  facebook: 'Facebook',
  google: 'Google',
  kwai: 'Kwai',
  tiktok: 'TikTok',
};

const countryNameMap = Object.fromEntries(
  (facebookCountries as { code: string; name: string }[]).map((country) => [
    country.code.toUpperCase(),
    country.name,
  ]),
);

function toCountryNames(countries: string[]) {
  return countries.map(
    (country) => countryNameMap[country.toUpperCase()] ?? country,
  );
}

const formRules: FormProps['rules'] = {
  dueAt: [
    {
      async validator() {
        if (
          formState.startAt &&
          formState.dueAt &&
          !dayjs(formState.dueAt).isAfter(dayjs(formState.startAt))
        ) {
          throw new Error('截止时间必须晚于开始时间');
        }
      },
      trigger: 'change',
    },
  ],
  platforms: [
    { required: true, message: '请至少选择一个投放平台', trigger: 'change' },
  ],
  projectId: [{ required: true, message: '请选择所属项目', trigger: 'change' }],
  region: [
    { required: true, message: '请选择投放地区 / 国家', trigger: 'change' },
  ],
  startAt: [{ required: true, message: '请选择开始时间', trigger: 'change' }],
  target: [
    {
      required: true,
      message: '请填写投放目标与执行说明',
      trigger: ['blur', 'change'],
    },
    { max: 1000, message: '投放说明最多 1000 个字符', trigger: 'blur' },
  ],
  title: [
    {
      required: true,
      message: '请输入任务标题',
      trigger: ['blur', 'change'],
      whitespace: true,
    },
    { max: 80, message: '任务标题最多 80 个字符', trigger: 'blur' },
  ],
};

function attachmentMeta(): TaskAttachmentMeta[] {
  return attachmentFiles.value.map((file) => ({
    id: String(file.uid),
    name: file.name,
    serverFileId: file.serverFileId,
    size: Number(file.size) || 0,
    type: file.type || 'application/octet-stream',
  }));
}

function buildPayload(): DeliveryTaskFormData {
  const project = projectSelectOptions.value.find(
    (item) => item.id === formState.projectId,
  );
  return {
    ...formState,
    allocations: [],
    items: (formState.items ?? []).map((item) => ({ ...item })),
    attachments: attachmentMeta(),
    projectName: project?.name ?? formState.projectName,
    productUrl: formState.productUrl.trim(),
    target: formState.target.trim(),
    title: formState.title.trim(),
  };
}

function formSnapshot() {
  return JSON.stringify(buildPayload());
}

const hasUnsavedChanges = computed(
  () =>
    initialSnapshot.value !== '' && formSnapshot() !== initialSnapshot.value,
);

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  const maxSize = 50 * 1024 * 1024;
  if (file.size > maxSize) {
    message.error(`${file.name} 超过 50 MB，无法添加`);
    return Upload.LIST_IGNORE;
  }
  if (
    attachmentFiles.value.some(
      (item) => item.name === file.name && item.size === file.size,
    )
  ) {
    message.warning(`${file.name} 已在附件列表中`);
    return Upload.LIST_IGNORE;
  }
  attachmentFiles.value = [
    ...attachmentFiles.value,
    {
      lastModified: file.lastModified,
      name: file.name,
      originFileObj: file,
      size: file.size,
      type: file.type,
      uid: file.uid,
    },
  ];
  return false;
};

const removeAttachment: UploadProps['onRemove'] = (file) => {
  attachmentFiles.value = attachmentFiles.value.filter(
    (item) => item.uid !== file.uid,
  );
  return true;
};

function formatFileSize(size?: number) {
  if (!size) return '0 KB';
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

/**
 * 确保附件已上传并返回稳定文件 ID，新草稿恢复后可直接复用该 ID。
 */
async function ensureAttachmentUploaded(file: DeliveryAttachmentFile) {
  if (file.serverFileId) return file.serverFileId;
  if (!file.originFileObj) {
    throw new Error(`附件“${file.name}”缺少原始文件，请重新选择`);
  }

  const uploaded = await uploadTaskFileApi(file.originFileObj);
  file.serverFileId = uploaded.id;
  return uploaded.id;
}

async function hydrateDraft(draftId: string) {
  let draft;
  try {
    draft = await getTaskDraftApi<DeliveryTaskFormData>(draftId);
  } catch {
    message.warning('未找到该草稿，已为你打开新建页面');
    return;
  }
  hydratingDraft.value = true;
  Object.assign(formState, draft.payload, {
    allocations: [],
    items: (draft.payload.items ?? []).map((item) => ({ ...item })),
    attachments: draft.payload.attachments.map((attachment) => ({
      ...attachment,
    })),
  });
  attachmentFiles.value = draft.payload.attachments.map((attachment) => ({
    name: attachment.name,
    serverFileId: attachment.serverFileId,
    size: attachment.size,
    status: 'done',
    type: attachment.type,
    uid: attachment.id,
  }));
  currentDraftId.value = draft.id;
  void nextTick(() => {
    hydratingDraft.value = false;
    projectLeaderMessage.value = draft.payload.ownerId
      ? ''
      : '该历史草稿未记录稳定负责人 ID，已保留原负责人姓名。';
  });
}

async function hydrateResubmission(taskId: string) {
  const detail = await getTaskApi(taskId);
  if (
    detail.task.taskType !== 'DELIVERY' ||
    !['REJECTED', 'WITHDRAWN'].includes(detail.task.status)
  ) {
    throw new Error('该投放任务当前不可再次提交');
  }
  hydratingDraft.value = true;
  Object.assign(formState, {
    allocations: [],
    items: (detail.delivery?.items ?? []).map((item) => ({ ...item })),
    amOwner: '',
    attachments: detail.taskFiles
      .filter((item) => item.targetType === 'DELIVERY_TASK')
      .map((item) => ({
        id: item.id,
        name: item.originalName,
        serverFileId: item.id,
        size: item.fileSize,
        type: item.mimeType,
      })),
    dueAt: detail.task.dueAt
      ? dayjs(detail.task.dueAt).format('YYYY-MM-DD HH:mm')
      : '',
    platforms: detail.platforms,
    productUrl: detail.delivery?.productUrl ?? '',
    projectId: detail.task.projectId,
    projectName: '',
    region: detail.delivery?.region ?? '',
    startAt: detail.delivery
      ? dayjs(detail.delivery.plannedStartAt).format('YYYY-MM-DD HH:mm')
      : '',
    target: detail.delivery?.target ?? '',
    title: detail.task.title,
    ownerId: undefined,
    ownerName: undefined,
  });
  attachmentFiles.value = formState.attachments.map((item) => ({
    name: item.name,
    serverFileId: item.serverFileId,
    size: item.size,
    status: 'done',
    type: item.type,
    uid: item.id,
  }));
  resubmitTaskId.value = taskId;
  await nextTick();
  hydratingDraft.value = false;
}

async function saveDraft() {
  if (!canSubmitCurrentForm.value) {
    message.warning('没有新建投放任务权限');
    return;
  }
  submitError.value = '';

  savingDraft.value = true;
  try {
    await Promise.all(
      attachmentFiles.value.map((file) => ensureAttachmentUploaded(file)),
    );
    const payload = buildPayload();
    let saved = currentDraftId.value
      ? await updateTaskDraftApi(currentDraftId.value, {
          payload,
          projectId: payload.projectId,
          taskType: 'DELIVERY',
          title: payload.title,
        })
      : undefined;
    saved ??= await createTaskDraftApi({
      payload,
      projectId: payload.projectId,
      taskType: 'DELIVERY',
      title: payload.title,
    });
    currentDraftId.value = saved.id;
    await router.replace({
      query: { ...route.query, draftId: saved.id },
    });
    initialSnapshot.value = formSnapshot();
    message.success('草稿已保存，可稍后继续编辑');
  } catch (error) {
    submitError.value =
      error instanceof Error && error.message
        ? error.message
        : '草稿保存失败，请稍后重试';
  } finally {
    savingDraft.value = false;
  }
}

async function submitTask() {
  if (!canSubmitCurrentForm.value) {
    message.warning('没有新建投放任务权限');
    return;
  }
  submitError.value = '';
  let formValid = true;
  try {
    await formRef.value?.validate();
  } catch {
    formValid = false;
  }
  allocationError.value = validateDeliveryItems(formState.items ?? []);
  if (!formValid || allocationError.value) {
    message.warning('请先补全标红的必填内容');
    return;
  }

  submitting.value = true;
  try {
    const payload = buildPayload();
    const files = await Promise.all(
      attachmentFiles.value.map(async (item, sortOrder) => {
        return {
          fileId: await ensureAttachmentUploaded(item),
          sortOrder,
          usageType: 'ATTACHMENT' as const,
        };
      }),
    );
    const request: Parameters<typeof createDeliveryTaskApi>[0] = {
      draftId: currentDraftId.value || undefined,
      items: payload.items ?? [],
      files,
      plannedStartAt: dayjs(payload.startAt).format('YYYY-MM-DDTHH:mm:ss'),
      platforms: payload.platforms,
      productUrl: payload.productUrl,
      region: payload.region,
      target: payload.target,
      task: {
        description: payload.target,
        dueAt: payload.dueAt
          ? dayjs(payload.dueAt).format('YYYY-MM-DDTHH:mm:ss')
          : undefined,
        ownerId: payload.ownerId,
        priority: 'P1',
        projectId: payload.projectId,
        title: payload.title,
      },
    };
    const detail = resubmitTaskId.value
      ? await resubmitDeliveryTaskApi(resubmitTaskId.value, request)
      : await createDeliveryTaskApi(request);
    const task = taskCenterStore.addTask({
      actionLabel: '查看投放任务',
      audiences: ['am', 'operator', 'operator_leader'],
      createdBy: currentUserName.value,
      delivery: payload,
      dueAt: payload.dueAt,
      id: detail.task.id,
      kind: 'am',
      owner: payload.ownerName || '投放负责人',
      ownerId: payload.ownerId,
      ownerName: payload.ownerName ?? payload.amOwner,
      progress: 0,
      project: payload.projectName,
      projectId: payload.projectId,
      route: '/workbench/tasks',
      status: 'assigned_pending_confirmation',
      summary: `${payload.region} · ${payload.platforms.join('/')}`,
      title: payload.title,
    });
    initialSnapshot.value = formSnapshot();
    leavingAfterSubmit.value = true;
    message.success(`投放任务 ${task.id} 已提交，并关联到“${task.project}”`);
    await router.push({
      path: '/workbench/tasks',
      query: { createdTaskId: task.id },
    });
  } catch (error) {
    submitError.value =
      error instanceof Error && error.message
        ? error.message
        : '任务提交失败，请检查网络后重试';
  } finally {
    submitting.value = false;
  }
}

function goBack() {
  void router.push('/workbench/tasks');
}

function confirmDiscardChanges() {
  return new Promise<boolean>((resolve) => {
    Modal.confirm({
      cancelText: '继续编辑',
      content: '离开后，尚未保存的修改将丢失。你也可以先保存草稿再离开。',
      okText: '放弃修改',
      okType: 'danger',
      onCancel: () => resolve(false),
      onOk: () => resolve(true),
      title: '确认离开新建投放任务？',
    });
  });
}

onBeforeRouteLeave(() => {
  if (leavingAfterSubmit.value || !hasUnsavedChanges.value) return true;
  return confirmDiscardChanges();
});

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges.value || leavingAfterSubmit.value) return;
  event.preventDefault();
  event.returnValue = '';
}

function projectKpiLabel(project: ProjectSummary) {
  const requirements = project.kpiRequirements ?? [];
  if (requirements.length === 0)
    return project.primaryKpi || '项目暂未配置 KPI';
  return requirements
    .map(
      ({ comparator, metric, target }) => `${metric} ${comparator} ${target}`,
    )
    .join('；');
}

function toDeliveryPlatforms(project: ProjectSummary) {
  const platforms: string[] = [];
  for (const platform of project.platforms) {
    const label = projectPlatformLabels[platform.toLowerCase()];
    if (label) platforms.push(label);
  }
  return platforms;
}

function readProjectProductUrl(project: ProjectSummary) {
  return (project.productLinks ?? [])
    .map((link) => link.trim())
    .filter(Boolean)
    .join('\n');
}

async function hydrateProjectContext(
  projectId: string,
  options: { fillForm?: boolean } = {},
) {
  const requestId = ++projectContextRequest;
  const fillForm = options.fillForm ?? true;
  if (!projectId) {
    selectedProjectContext.value = null;
    selectedProjectAgencyLines.value = [];
    if (fillForm) {
      formState.ownerId = undefined;
      formState.ownerName = undefined;
      formState.amOwner = '';
    }
    projectLeaderMessage.value = '';
    return;
  }
  projectContextLoading.value = true;
  try {
    const project = await projectService.get(projectId);
    if (requestId !== projectContextRequest) return;
    selectedProjectContext.value = project;
    const lines = await agencyLineService
      .list({ page: 1, pageSize: 100, projectId })
      .catch(() => undefined);
    if (requestId !== projectContextRequest) return;
    selectedProjectAgencyLines.value = lines?.items ?? [];
    if (!fillForm) return;

    formState.projectName = project.name;
    formState.region = toCountryNames(project.countryRegions).join(' / ');
    formState.platforms = toDeliveryPlatforms(project);
    formState.ownerId = project.deliveryLeaderId;
    formState.ownerName = project.deliveryLeaderName;
    formState.amOwner =
      project.amUsers?.map((user) => user.userName).join('、') ||
      project.amName ||
      '';
    formState.productUrl = readProjectProductUrl(project);
    projectLeaderMessage.value = !project.deliveryLeaderId
      ? '该项目尚未配置投放负责人，请在创建任务时选择。'
      : '';
  } catch {
    if (requestId !== projectContextRequest) return;
    selectedProjectContext.value = null;
    selectedProjectAgencyLines.value = [];
    if (fillForm) {
      formState.ownerId = undefined;
      formState.ownerName = undefined;
      formState.amOwner = '';
    }
    projectLeaderMessage.value = '项目负责人读取失败，请稍后重试。';
  } finally {
    if (requestId === projectContextRequest) {
      projectContextLoading.value = false;
    }
  }
}

/** 新建投放任务只展示当前用户项目数据范围内的轻量选项。 */
async function loadScopedProjectOptions() {
  projectOptionsLoading.value = true;
  try {
    projectSelectOptions.value = await projectService.searchScopedOptions();
  } finally {
    projectOptionsLoading.value = false;
  }
}

watch(
  () => formState.projectId,
  (projectId) => {
    const project = projectSelectOptions.value.find(
      (item) => item.id === projectId,
    );
    if (project) formState.projectName = project.name;
    if (!hydratingDraft.value) void hydrateProjectContext(projectId);
  },
);

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload);
  await loadScopedProjectOptions();

  const draftId = Array.isArray(route.query.draftId)
    ? route.query.draftId[0]
    : route.query.draftId;
  const retryId = Array.isArray(route.query.resubmitTaskId)
    ? route.query.resubmitTaskId[0]
    : route.query.resubmitTaskId;
  if (typeof retryId === 'string' && retryId) {
    await hydrateResubmission(retryId);
    if (typeof draftId === 'string' && draftId) await hydrateDraft(draftId);
    await hydrateProjectContext(formState.projectId);
  } else if (typeof draftId === 'string' && draftId) {
    await hydrateDraft(draftId);
    await hydrateProjectContext(formState.projectId);
  } else {
    const queryProjectId = Array.isArray(route.query.projectId)
      ? route.query.projectId[0]
      : route.query.projectId;
    const preferredProjectId =
      typeof queryProjectId === 'string' ? queryProjectId : '';
    if (preferredProjectId) {
      formState.projectId = preferredProjectId;
      await hydrateProjectContext(preferredProjectId);
    }
  }
  await nextTick();
  initialSnapshot.value = formSnapshot();
});

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload);
});
</script>

<template>
  <Page class="delivery-task-page bg-slate-50">
    <div class="w-full min-w-0 space-y-4">
      <section
        class="sticky top-0 z-20 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-5"
      >
        <div
          class="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between"
        >
          <div class="flex min-w-0 items-start gap-3">
            <Button aria-label="返回任务中心" shape="circle" @click="goBack">
              <template #icon>
                <IconifyIcon icon="lucide:arrow-left" />
              </template>
            </Button>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h1 class="m-0 text-xl font-semibold text-slate-900">
                  新建投放任务
                </h1>
                <Tag v-if="currentDraftId" color="default">草稿已保存</Tag>
              </div>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                填写投放明细并指定投手；提交后由投放负责人确认，再由投手执行交付。
              </p>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-2 self-end xl:self-auto">
            <Button
              :disabled="submitting || !canSubmitCurrentForm"
              :loading="savingDraft"
              @click="saveDraft"
            >
              <template #icon><IconifyIcon icon="lucide:save" /></template>
              保存草稿
            </Button>
            <Button
              :disabled="savingDraft || !canSubmitCurrentForm"
              :loading="submitting"
              type="primary"
              @click="submitTask"
            >
              <template #icon><IconifyIcon icon="lucide:send" /></template>
              提交任务
            </Button>
          </div>
        </div>
      </section>

      <Alert
        v-if="submitError"
        closable
        :message="submitError"
        show-icon
        type="error"
        @close="submitError = ''"
      />

      <Form
        ref="formRef"
        layout="vertical"
        :model="formState"
        :rules="formRules"
      >
        <div class="grid grid-cols-1 gap-4">
          <Card :bordered="false" class="border border-slate-200 shadow-sm">
            <template #title>
              <span class="inline-flex items-center gap-2">
                <span class="h-5 w-1 rounded-full bg-blue-600"></span>
                基础信息
              </span>
            </template>

            <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2 xl:grid-cols-3">
              <FormItem
                class="md:col-span-2 xl:col-span-2"
                label="任务标题"
                name="title"
                required
              >
                <Input
                  v-model:value="formState.title"
                  :maxlength="80"
                  placeholder="例如：F9 巴西新版首轮投放"
                  show-count
                />
              </FormItem>

              <FormItem label="所属项目" name="projectId" required>
                <Select
                  v-model:value="formState.projectId"
                  :loading="projectOptionsLoading"
                  :options="projectOptions"
                  option-filter-prop="label"
                  placeholder="请选择项目"
                  show-search
                />
              </FormItem>

              <Alert
                v-if="projectLeaderMessage"
                class="md:col-span-2 xl:col-span-2"
                show-icon
                type="warning"
                :message="projectLeaderMessage"
              />

              <section
                v-if="selectedProjectContext || projectContextLoading"
                class="md:col-span-2 xl:col-span-3"
              >
                <div
                  class="rounded-lg border border-blue-100 bg-blue-50/50 p-3"
                >
                  <div
                    class="flex flex-wrap items-center justify-between gap-2"
                  >
                    <div class="font-medium text-slate-800">
                      项目基础信息
                      <span class="ml-1 text-xs font-normal text-slate-500">
                        来自项目管理
                      </span>
                    </div>
                    <span
                      v-if="selectedProjectContext"
                      class="text-xs text-slate-500"
                    >
                      {{ selectedProjectContext.projectCode }}
                    </span>
                  </div>
                  <div
                    v-if="projectContextLoading"
                    class="mt-3 text-sm text-slate-500"
                  >
                    正在读取项目基础信息…
                  </div>
                  <dl
                    v-else-if="selectedProjectContext"
                    class="mt-3 grid grid-cols-1 gap-x-5 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-3"
                  >
                    <div>
                      <dt class="text-xs text-slate-500">产品信息</dt>
                      <dd class="mt-1 break-words text-slate-800">
                        {{
                          selectedProjectContext.productInfo ||
                          '项目暂未填写产品信息'
                        }}
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-slate-500">投放</dt>
                      <dd class="mt-1 flex flex-wrap gap-1">
                        <Tag
                          v-for="platform in selectedProjectContext.platforms"
                          :key="platform"
                          color="blue"
                        >
                          {{ projectPlatformLabels[platform] ?? platform }}
                        </Tag>
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-slate-500">投放线路</dt>
                      <dd class="mt-1 flex flex-wrap gap-1">
                        <Tag
                          v-for="line in selectedProjectAgencyLines"
                          :key="line.id"
                          color="geekblue"
                        >
                          {{ line.name }}
                        </Tag>
                        <span
                          v-if="selectedProjectAgencyLines.length === 0"
                          class="text-slate-500"
                        >
                          暂未绑定代理线
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-slate-500">KPI</dt>
                      <dd class="mt-1 text-slate-800">
                        {{ projectKpiLabel(selectedProjectContext) }}
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-slate-500">素材要求</dt>
                      <dd class="mt-1 text-slate-800">
                        已关联 {{ selectedProjectContext.materialCount }} 条素材
                      </dd>
                    </div>
                    <div>
                      <dt class="text-xs text-slate-500">任务开启时间</dt>
                      <dd class="mt-1 text-slate-800">
                        {{ selectedProjectContext.startDate }}
                      </dd>
                    </div>
                  </dl>
                </div>
              </section>

              <FormItem label="投放地区 / 国家" name="region" required>
                <Input
                  v-model:value="formState.region"
                  disabled
                  placeholder="选择项目后自动带入"
                />
              </FormItem>

              <FormItem label="投放平台" name="platforms" required>
                <Select
                  v-model:value="formState.platforms"
                  :options="platformOptions"
                  disabled
                  mode="multiple"
                  placeholder="选择项目后自动带入"
                />
              </FormItem>

              <FormItem label="任务负责人 / AM" name="amOwner">
                <Input
                  :value="formState.amOwner"
                  disabled
                  placeholder="选择项目后自动带入"
                />
              </FormItem>

              <FormItem label="投放负责人" name="ownerId" required>
                <StableUserSelect
                  v-model="formState.ownerId"
                  :disabled="Boolean(selectedProjectContext?.deliveryLeaderId)"
                  :legacy-label="formState.ownerName"
                  placeholder="项目未配置时请选择投放负责人"
                  @change="
                    (userId, user) => {
                      formState.ownerId = Array.isArray(userId)
                        ? userId[0]
                        : userId;
                      formState.ownerName = user?.name;
                    }
                  "
                />
              </FormItem>

              <FormItem
                class="md:col-span-2 xl:col-span-3"
                label="产品信息 URL（可多个，选填）"
                name="productUrl"
              >
                <Input.TextArea
                  v-model:value="formState.productUrl"
                  :auto-size="{ minRows: 1, maxRows: 5 }"
                  disabled
                  placeholder="项目暂未配置产品链接"
                />
              </FormItem>

              <FormItem label="开始时间" name="startAt" required>
                <DatePicker
                  v-model:value="formState.startAt"
                  class="w-full"
                  format="YYYY-MM-DD HH:mm"
                  :show-time="{ format: 'HH:mm' }"
                  value-format="YYYY-MM-DD HH:mm"
                />
              </FormItem>

              <FormItem label="截止时间（选填）" name="dueAt">
                <DatePicker
                  v-model:value="formState.dueAt"
                  class="w-full"
                  format="YYYY-MM-DD HH:mm"
                  :show-time="{ format: 'HH:mm' }"
                  value-format="YYYY-MM-DD HH:mm"
                />
              </FormItem>
            </div>
          </Card>
        </div>

        <Card :bordered="false" class="mt-4 min-w-0" title="投放任务明细">
          <Alert
            v-if="allocationError"
            :message="allocationError"
            type="error"
            show-icon
            class="mb-3"
          />
          <DeliveryTaskItems
            v-model="formState.items"
            :platforms="formState.platforms"
            :project-id="formState.projectId"
          />
        </Card>

        <Card :bordered="false" class="mt-4 border border-slate-200 shadow-sm">
          <template #title>
            <span class="inline-flex items-center gap-2">
              <span class="bg-primary h-5 w-1 rounded-full"></span>
              投放目标与说明
            </span>
          </template>
          <FormItem class="mb-0" name="target" required>
            <Input.TextArea
              v-model:value="formState.target"
              :auto-size="{ minRows: 5, maxRows: 10 }"
              :maxlength="1000"
              placeholder="填写投放目标、预算约束、受众、素材组合、验收口径，以及需要团队特别注意的事项"
              show-count
            />
          </FormItem>
        </Card>

        <Card :bordered="false" class="mt-4 border border-slate-200 shadow-sm">
          <template #title>
            <span class="inline-flex items-center gap-2">
              <span class="bg-primary h-5 w-1 rounded-full"></span>
              参考附件
              <span
                class="text-xs font-normal text-slate-400"
                v-text="'支持图片、文档与压缩包'"
              ></span>
            </span>
          </template>
          <Upload.Dragger
            accept=".png,.jpg,.jpeg,.webp,.pdf,.doc,.docx,.xls,.xlsx,.zip,.7z"
            :before-upload="beforeUpload"
            :file-list="attachmentFiles"
            :multiple="true"
            @remove="removeAttachment"
          >
            <div class="py-5">
              <IconifyIcon
                class="text-primary mx-auto text-2xl"
                icon="lucide:cloud-upload"
              />
              <p class="mb-1 mt-3 text-sm font-medium text-slate-700">
                点击或拖拽文件到此处
              </p>
              <p class="m-0 text-xs text-slate-400">
                单个文件不超过 50 MB，仅保存在当前演示环境
              </p>
            </div>
          </Upload.Dragger>

          <div
            v-if="attachmentFiles.length > 0"
            class="mt-3 flex flex-wrap gap-2 text-xs text-slate-500"
          >
            <span>{{ attachmentFiles.length }} 个附件</span>
            <span>·</span>
            <span>
              {{
                formatFileSize(
                  attachmentFiles.reduce(
                    (total, file) => total + (Number(file.size) || 0),
                    0,
                  ),
                )
              }}
            </span>
          </div>
        </Card>
      </Form>

      <section
        class="sticky bottom-0 z-10 flex flex-col-reverse gap-2 rounded-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="text-xs text-slate-500">
          <span v-if="hasUnsavedChanges">当前有未保存修改</span>
          <span v-else-if="currentDraftId">草稿内容已保存</span>
          <span v-else>填写完整后可直接提交任务</span>
        </div>
        <div class="flex justify-end gap-2">
          <Button
            :disabled="submitting"
            :loading="savingDraft"
            @click="saveDraft"
          >
            保存草稿
          </Button>
          <Button
            :disabled="savingDraft"
            :loading="submitting"
            type="primary"
            @click="submitTask"
          >
            提交任务
          </Button>
        </div>
      </section>
    </div>
  </Page>
</template>

<style scoped>
@media (max-width: 639px) {
}
</style>
