<script lang="ts" setup>
import type {
  ApplicationDefinition,
  DynamicFieldCondition,
  DynamicFormField,
} from '#/api/asset-flow';
import type { SystemRoleApi } from '#/api/system/role';
import type { SystemUserApi } from '#/api/system/user';
import type { ApplicationApprovalRole } from '#/domain/application';
import type {
  ApprovalAssigneeMode,
  ApprovalFlowNode,
  ApprovalFlowNodeKind,
  MediaApprovalConfig,
} from '#/store/media-approval-config';

import { computed, onMounted, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Drawer,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Menu,
  MenuItem,
  Modal,
  Radio,
  Select,
  Switch,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import { assetFlowApi } from '#/api';
import { getRoleList } from '#/api/system/role';
import { getUserList } from '#/api/system/user';
import { resolveDynamicFieldPlaceholder } from '#/domain/application';
import { isFixedDailyReportApplication } from '#/domain/daily-report-applications';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import {
  approvalApplicationTypeLabels,
  cloneApprovalConfig,
  createApprovalConfigDraft,
  useMediaApprovalConfigStore,
} from '#/store/media-approval-config';

import ListLoading from '../components/ListLoading.vue';
import DepartmentTreeSelect from '../components/DepartmentTreeSelect.vue';

defineOptions({ name: 'SystemApprovalConfig' });

const approvalConfigStore = useMediaApprovalConfigStore();

const roleMeta: Record<
  ApplicationApprovalRole,
  { color: string; label: string; surface: string }
> = {
  finance: {
    color: 'green',
    label: '财务审批',
    surface: 'bg-emerald-600',
  },
  media: {
    color: 'blue',
    label: '媒介审批',
    surface: 'bg-blue-600',
  },
  office: {
    color: 'purple',
    label: '行政与资产审批',
    surface: 'bg-slate-600',
  },
};

const systemUsers = ref<SystemUserApi.User[]>([]);
const systemRoles = ref<SystemRoleApi.Role[]>([]);
const applicationDefinitions = ref<ApplicationDefinition[]>([]);
const approverOptions = computed(() =>
  systemUsers.value
    .filter((user) => user.status === 1)
    .map((user) => ({
      label: user.realName || user.displayName,
      userId: user.id,
      value: user.id,
    })),
);
const roleOptions = computed(() =>
  systemRoles.value
    .filter((role) => role.status === 1)
    .map((role) => ({ label: role.roleName, value: role.id })),
);
const ccOptions = computed(() => approverOptions.value);

const assigneeOptions: Array<{
  disabled?: boolean;
  label: string;
  value: ApprovalAssigneeMode;
}> = [
  { label: '角色', value: 'role' },
  { label: '部门', value: 'department' },
  { label: '指定成员', value: 'member' },
];

const nodeMeta: Record<
  ApprovalFlowNodeKind,
  { icon: string; label: string; tone: string }
> = {
  approval: {
    icon: 'lucide:user-round-check',
    label: '审批人',
    tone: 'bg-amber-500',
  },
  copy: {
    icon: 'lucide:copy',
    label: '抄送人',
    tone: 'bg-indigo-500',
  },
  handler: {
    icon: 'lucide:clipboard-pen-line',
    label: '办理人',
    tone: 'bg-violet-500',
  },
};

const availableFields: Array<{
  icon: string;
  label: string;
  type: DynamicFormField['type'];
}> = [
  { icon: 'lucide:heading-2', label: '分组标题', type: 'section' },
  { icon: 'lucide:text-cursor-input', label: '单行文本', type: 'text' },
  { icon: 'lucide:align-left', label: '多行文本', type: 'textarea' },
  { icon: 'lucide:list-checks', label: '下拉单选', type: 'select' },
  { icon: 'lucide:list-tree', label: '下拉多选', type: 'multi-select' },
  { icon: 'lucide:scan-line', label: '像素选择', type: 'pixel-selector' },
  { icon: 'lucide:calendar-days', label: '日期', type: 'date' },
  { icon: 'lucide:calendar-range', label: '日期范围', type: 'date-range' },
  { icon: 'lucide:circle-dollar-sign', label: '数字/金额', type: 'number' },
];

const handlerFieldTypeOptions = [
  { label: '单行文本', value: 'text' },
  { label: '多行文本', value: 'textarea' },
  { label: '数字/金额', value: 'number' },
  { label: '图片上传', value: 'image-upload' },
];

function createNodeId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function cloneConfig(config: MediaApprovalConfig): MediaApprovalConfig {
  return cloneApprovalConfig(config);
}

const searchKeyword = ref('');
const { commitQueryState, restoreFromRoute } = useListRouteState({
  state: createListRouteStateTarget({ keyword: searchKeyword }),
});
watch(searchKeyword, () => void commitQueryState());
const configListLoading = ref(true);
const filteredConfigs = computed(() => {
  const keyword = searchKeyword.value.trim().toLocaleLowerCase();
  if (!keyword) return approvalConfigStore.configs;
  return approvalConfigStore.configs.filter((config) =>
    [config.name, config.description, config.approver]
      .join(' ')
      .toLocaleLowerCase()
      .includes(keyword),
  );
});

const editorOpen = ref(false);
const editorStep = ref(3);
const editor = ref<MediaApprovalConfig>(
  cloneConfig(approvalConfigStore.configs[0]!),
);
const addableNodeKinds = computed<ApprovalFlowNodeKind[]>(() =>
  editor.value.settings.completionMode === 'pixel-auto-assign'
    ? ['approval', 'copy']
    : ['approval', 'copy', 'handler'],
);
const activeNodeId = ref('');
const activeFieldIndex = ref(0);
const addMenuAfterIndex = ref<number>();
const zoom = ref(100);
const previewOpen = ref(false);

const activeNode = computed(() =>
  editor.value.nodes.find((node) => node.id === activeNodeId.value),
);
const activeField = computed(
  () => editor.value.formFields[activeFieldIndex.value],
);
/** 固定日报的业务字段在专用页面维护，审批配置只能调整流程与可见范围。 */
const isFixedDailyReportConfig = computed(() =>
  editor.value.types.some((type) => isFixedDailyReportApplication(type)),
);
const applicationDefinitionOptions = computed(() => {
  const currentApplicationIds = new Set(editor.value.applicationDefinitionIds);
  return applicationDefinitions.value
    .filter(
      (definition) =>
        !definition.approvalConfigId ||
        definition.approvalConfigId === editor.value.id ||
        currentApplicationIds.has(definition.id),
    )
    .map((definition) => ({
      label: definition.applicationName,
      value: definition.id,
    }));
});
const linkedApplicationDefinitions = computed(() => {
  const linkedIds = new Set(editor.value.applicationDefinitionIds);
  return applicationDefinitions.value.filter((definition) =>
    linkedIds.has(definition.id),
  );
});
const linkedApplicationCodeOptions = computed(() =>
  linkedApplicationDefinitions.value.map((definition) => ({
    label: definition.applicationName,
    value: definition.applicationCode,
  })),
);
const applicationFieldOptions = computed(() =>
  editor.value.formFields
    .filter((field) => field.type !== 'section')
    .map((field) => ({
      label: `${field.label}（${field.key}）`,
      value: field.key,
    })),
);
const applicationAssetTypeFieldOptions = computed(() =>
  editor.value.formFields
    .filter((field) => field.type === 'select')
    .map((field) => ({
      label: `${field.label}（${field.key}）`,
      value: field.key,
    })),
);
const handlerSourceOptions = [
  { label: '固定人员', value: 'fixed-user' },
  { label: '指定审批节点的审批人', value: 'approval-node' },
];
const handlerApprovalNodeOptions = computed(() =>
  editor.value.nodes
    .filter((node) => node.kind === 'approval')
    .map((node) => ({
      disabled:
        node.assigneeMode === 'role'
          ? !node.roleIds?.length
          : node.assigneeMode === 'department'
            ? !node.departmentIds?.length
            : !node.approverId || node.approverId === '0' || !node.approver,
      label: node.approver
        ? `${node.label}（${node.approver}）`
        : `${node.label}（未配置审批人）`,
      value: node.id,
    })),
);

function ensureHandlerAction(node: ApprovalFlowNode) {
  node.handlerAction ??= { formSchema: [] };
  node.handlerAction.formSchema ??= [];
  return node.handlerAction;
}

function toggleResourceAssignment(checked: unknown) {
  if (!activeNode.value || activeNode.value.kind !== 'handler') return;
  const action = ensureHandlerAction(activeNode.value);
  action.resourceAssignment = checked
    ? {
        assetTypeSource: 'application',
        assetTypeFieldKey: editor.value.types.includes('TG')
          ? 'socialAssetType'
          : undefined,
        channelFieldKey: 'channelId',
        enabled: true,
        quantityFieldKey: 'quantity',
      }
    : undefined;
}

function addHandlerField(type: DynamicFormField['type'] = 'text') {
  if (!activeNode.value || activeNode.value.kind !== 'handler') return;
  const action = ensureHandlerAction(activeNode.value);
  const index = (action.formSchema?.length ?? 0) + 1;
  action.formSchema?.push({
    accept: type === 'image-upload' ? 'image/*' : undefined,
    key: `processingField${Date.now()}`,
    label: type === 'image-upload' ? '办理图片' : `办理字段${index}`,
    maxCount: type === 'image-upload' ? 3 : undefined,
    maxFileSizeMb: type === 'image-upload' ? 3 : undefined,
    required: false,
    type,
    width: 'full',
  });
}

function removeHandlerField(index: number) {
  if (!activeNode.value || activeNode.value.kind !== 'handler') return;
  ensureHandlerAction(activeNode.value).formSchema?.splice(index, 1);
}

function toggleAutoFill(field: DynamicFormField, checked: unknown) {
  field.autoFill = checked
    ? {
        resultKey: 'channelYesterdayCost',
        source: 'channel-payment-context',
        triggerFieldKey: 'channelId',
      }
    : undefined;
}

function applicationScopeMode(field: DynamicFormField) {
  return Array.isArray(field.applicableApplicationCodes) ? 'specific' : 'all';
}

function updateApplicationScopeMode(field: DynamicFormField, mode: string) {
  if (mode === 'all') {
    field.applicableApplicationCodes = undefined;
    return;
  }
  const firstApplication = linkedApplicationCodeOptions.value[0];
  field.applicableApplicationCodes = firstApplication
    ? [firstApplication.value]
    : [];
}

function syncApplicableApplicationCodes() {
  const linkedCodes = new Set(
    linkedApplicationDefinitions.value.map(
      (definition) => definition.applicationCode,
    ),
  );
  editor.value.formFields.forEach((field) => {
    if (!field.applicableApplicationCodes?.length) return;
    field.applicableApplicationCodes = field.applicableApplicationCodes.filter(
      (code) => linkedCodes.has(code),
    );
  });
}

const incompleteCount = computed(() => {
  let count = 0;
  if (!editor.value.name.trim()) count += 1;
  if (editor.value.applicationDefinitionIds.length === 0) count += 1;
  if (editor.value.types.length === 0) count += 1;
  if (
    editor.value.settings.approvalType === 'manual' &&
    editor.value.nodes
      .filter((node) => node.kind === 'approval')
      .some((node) => !node.approver)
  ) {
    count += 1;
  }
  return count;
});

function openEditor(config: MediaApprovalConfig, step = 3) {
  editor.value = cloneConfig(config);
  editorStep.value = step;
  activeNodeId.value =
    editor.value.nodes.find((node) => node.kind === 'approval')?.id ||
    editor.value.nodes[0]?.id ||
    '';
  addMenuAfterIndex.value = undefined;
  zoom.value = 100;
  editorOpen.value = true;
}

function createConfig() {
  const draft = createApprovalConfigDraft();
  draft.sortOrder =
    Math.max(0, ...approvalConfigStore.configs.map((item) => item.sortOrder)) +
    10;
  openEditor(draft, 1);
}

function closeEditor() {
  editorOpen.value = false;
}

function syncCompatibilityFields() {
  const firstApproval = editor.value.nodes.find(
    (node) => node.kind === 'approval',
  );
  if (firstApproval) {
    editor.value.approver = firstApproval.approver || '';
    editor.value.approverId = firstApproval.approverId;
    editor.value.role = firstApproval.role || 'media';
  }
  editor.value.ccUsers = [
    ...new Set(
      editor.value.nodes
        .filter((node) => node.kind === 'copy')
        .flatMap((node) => node.users || []),
    ),
  ];
  if (!editor.value.description.trim()) {
    editor.value.description = editor.value.types
      .map((type) => approvalApplicationTypeLabels[type])
      .join('、');
  }
}

async function publishConfig() {
  try {
    if (editor.value.applicationDefinitionIds.length === 0) {
      editorStep.value = 1;
      message.warning('请至少关联一个申请');
      return;
    }
    syncApplicableApplicationCodes();
    const fieldWithoutApplication = editor.value.formFields.find(
      (field) =>
        Array.isArray(field.applicableApplicationCodes) &&
        field.applicableApplicationCodes.length === 0,
    );
    if (fieldWithoutApplication) {
      editorStep.value = 2;
      activeFieldIndex.value = editor.value.formFields.indexOf(
        fieldWithoutApplication,
      );
      message.warning(`请为“${fieldWithoutApplication.label}”选择适用申请`);
      return;
    }
    syncCompatibilityFields();
    const saved = await approvalConfigStore.update(editor.value);
    editor.value = cloneConfig(saved);
    editorOpen.value = false;
    message.success('审批已发布，后续新申请将采用此流程');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '审批发布失败');
  }
}

async function toggleConfig(config: MediaApprovalConfig) {
  try {
    await approvalConfigStore.toggleEnabled(config.id);
    message.success(config.enabled ? '审批已停用' : '审批已启用');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '审批状态更新失败');
  }
}

async function toggleVisibility(config: MediaApprovalConfig) {
  try {
    await approvalConfigStore.update({
      ...cloneConfig(config),
      visibility: config.visibility === 'all' ? 'admins' : 'all',
    });
    message.success(
      config.visibility === 'all' ? '已设为仅管理员可见' : '已设为全员可见',
    );
  } catch (error) {
    message.error(error instanceof Error ? error.message : '可见范围更新失败');
  }
}

function deleteConfig(config: MediaApprovalConfig) {
  Modal.confirm({
    cancelText: '取消',
    content: `删除后“${config.name}”将无法恢复，已提交的申请会保留历史审批记录，关联申请将不能再使用此配置发起。`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除审批配置',
    async onOk() {
      await approvalConfigStore.remove(config.id);
      message.success('审批配置已删除');
    },
  });
}

function nodeSummary(node: ApprovalFlowNode) {
  if (node.kind === 'approval') {
    if (editor.value.settings.approvalType === 'auto-approve')
      return '自动通过';
    if (editor.value.settings.approvalType === 'auto-reject') return '自动拒绝';
    return node.approver ? `审批人：${node.approver}` : '请设置审批人';
  }
  if (node.kind === 'copy') {
    return node.users?.length
      ? `抄送：${node.users.join('、')}`
      : '请设置抄送人';
  }
  if (node.kind === 'handler') {
    if (node.handlerSource === 'approval-node') {
      const source = editor.value.nodes.find(
        (candidate) => candidate.id === node.handlerApprovalNodeId,
      );
      return source
        ? `办理人：使用「${source.label}」的审批人`
        : '请选择关联审批节点';
    }
    return node.approver ? `办理人：${node.approver}` : '请设置办理人';
  }
  return node.label || '设置进入该分支的条件';
}

function addNode(kind: ApprovalFlowNodeKind, afterIndex: number) {
  if (
    kind === 'handler' &&
    editor.value.settings.completionMode === 'pixel-auto-assign'
  ) {
    message.warning('像素自动分配流程不需要办理节点');
    return;
  }
  if (
    kind === 'handler' &&
    editor.value.nodes.some((node) => node.kind === 'handler')
  ) {
    message.warning('一个审批流程只能配置一个办理节点');
    return;
  }
  const base: ApprovalFlowNode = {
    id: createNodeId(kind),
    kind,
    label: nodeMeta[kind].label,
  };
  switch (kind) {
    case 'approval': {
      Object.assign(base, {
        approver: '',
        assigneeMode: 'member' as const,
        label: '审批',
        role: editor.value.role,
      });

      break;
    }
    case 'copy': {
      base.users = [];

      break;
    }
    case 'handler': {
      Object.assign(base, {
        approver: '',
        assigneeMode: 'member' as const,
        handlerAction: { formSchema: [] },
        handlerSource: 'fixed-user' as const,
        role: editor.value.role,
      });

      break;
    }
  }
  editor.value.nodes.splice(afterIndex + 1, 0, base);
  activeNodeId.value = base.id;
  addMenuAfterIndex.value = undefined;
}

function removeNode() {
  const index = editor.value.nodes.findIndex(
    (node) => node.id === activeNodeId.value,
  );
  if (index === -1) return;
  editor.value.nodes.splice(index, 1);
  activeNodeId.value =
    editor.value.nodes[index]?.id || editor.value.nodes.at(-1)?.id || '';
}

function handleApproverChange(value: unknown) {
  if (!activeNode.value) return;
  const selected = approverOptions.value.find(
    (item) => item.value === String(value),
  );
  if (!selected) return;
  activeNode.value.approver = selected.label;
  activeNode.value.approverId = selected.userId;
  activeNode.value.users = [selected.userId];
  activeNode.value.userNames = [selected.label];
}

function handleRoleChange(values: unknown) {
  if (!activeNode.value || !Array.isArray(values)) return;
  const ids = values.map(String);
  const selected = roleOptions.value.filter((role) => ids.includes(role.value));
  activeNode.value.roleIds = ids;
  activeNode.value.approverId = '0';
  activeNode.value.approver = selected.map((role) => role.label).join('、');
}

function handleDepartmentChange(
  values: string | string[],
  departments: Array<{ id: string; name: string }>,
) {
  if (!activeNode.value) return;
  activeNode.value.departmentIds = Array.isArray(values) ? values : [values];
  activeNode.value.departmentNames = departments.map(
    (department) => department.name,
  );
  activeNode.value.approverId = '0';
  activeNode.value.approver = activeNode.value.departmentNames.join('、');
}

function handleAssigneeModeChange() {
  if (!activeNode.value) return;
  const mode = activeNode.value.assigneeMode ?? 'member';
  activeNode.value.approver = '';
  activeNode.value.approverId = mode === 'member' ? '' : '0';
  activeNode.value.departmentIds = [];
  activeNode.value.departmentNames = [];
  activeNode.value.roleIds = [];
  activeNode.value.users = [];
  activeNode.value.userNames = [];
}

function addApprovalAfterCurrent() {
  const index = editor.value.nodes.findIndex(
    (node) => node.id === activeNodeId.value,
  );
  addNode('approval', index === -1 ? editor.value.nodes.length - 1 : index);
}

function addFormField(fieldDefinition: (typeof availableFields)[number]) {
  let nextLabel = fieldDefinition.label;
  let suffix = 2;
  while (editor.value.formFields.some((field) => field.label === nextLabel)) {
    nextLabel = `${fieldDefinition.label}${suffix}`;
    suffix += 1;
  }
  const nextField: DynamicFormField = {
    key:
      fieldDefinition.type === 'pixel-selector'
        ? 'pixelAssetIds'
        : `field_${Date.now()}`,
    label: nextLabel,
    optionSource:
      fieldDefinition.type === 'pixel-selector'
        ? 'available-pixels'
        : ['multi-select', 'select'].includes(fieldDefinition.type)
          ? 'custom'
          : undefined,
    options: ['multi-select', 'select'].includes(fieldDefinition.type)
      ? ['选项一', '选项二']
      : undefined,
    placeholder: resolveDynamicFieldPlaceholder({
      type: fieldDefinition.type,
    }),
    required: false,
    type: fieldDefinition.type,
    width: ['pixel-selector', 'section', 'textarea'].includes(
      fieldDefinition.type,
    )
      ? 'full'
      : 'half',
  };
  editor.value.formFields.push(nextField);
  activeFieldIndex.value = editor.value.formFields.length - 1;
}

function removeFormField(index: number) {
  editor.value.formFields.splice(index, 1);
  activeFieldIndex.value = Math.max(
    0,
    Math.min(activeFieldIndex.value, editor.value.formFields.length - 1),
  );
}

function moveFormField(index: number, direction: -1 | 1) {
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= editor.value.formFields.length) return;
  const [field] = editor.value.formFields.splice(index, 1);
  if (!field) return;
  editor.value.formFields.splice(targetIndex, 0, field);
  activeFieldIndex.value = targetIndex;
}

function customOptionsText(field: DynamicFormField) {
  return (field.options ?? []).join('\n');
}

function updateCustomOptions(field: DynamicFormField, value: string) {
  field.options = value
    .split(/\r?\n/)
    .map((option) => option.trim())
    .filter(Boolean);
}

function conditionValueText(condition?: DynamicFieldCondition) {
  if (!condition) return '';
  return Array.isArray(condition.value)
    ? condition.value.join(',')
    : condition.value;
}

function conditionFieldOptions(field: DynamicFormField) {
  return editor.value.formFields
    .filter((item) => item.key !== field.key && item.type !== 'section')
    .map((item) => ({ label: item.label, value: item.key }));
}

function toggleFieldCondition(
  field: DynamicFormField,
  kind: 'requiredWhen' | 'visibleWhen',
  checked: boolean | number | string,
) {
  if (checked !== true) {
    field[kind] = undefined;
    return;
  }
  const firstDependency = conditionFieldOptions(field)[0];
  field[kind] = {
    fieldKey: firstDependency?.value ?? '',
    operator: 'equals',
    value: '',
  };
}

function updateConditionValue(condition: DynamicFieldCondition, value: string) {
  condition.value =
    condition.operator === 'in'
      ? value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
      : value;
}

function updateDefaultValue(field: DynamicFormField, value: string) {
  if (!value.trim()) {
    field.defaultValue = undefined;
    return;
  }
  field.defaultValue =
    field.type === 'multi-select'
      ? value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
      : value;
}

function defaultValueText(field: DynamicFormField) {
  if (field.defaultValue === undefined) return '';
  return Array.isArray(field.defaultValue)
    ? field.defaultValue.join(',')
    : String(field.defaultValue);
}

function changeZoom(delta: number) {
  zoom.value = Math.min(140, Math.max(60, zoom.value + delta));
}

onMounted(async () => {
  await restoreFromRoute();
  configListLoading.value = true;
  try {
    const [users, roles, configs, definitions] = await Promise.allSettled([
      getUserList({ page: 1, pageSize: 500, status: 1 }),
      getRoleList({ page: 1, pageSize: 500, status: 1 }),
      approvalConfigStore.load(),
      assetFlowApi.managedApplicationDefinitions(),
    ]);
    if (users.status === 'fulfilled') {
      systemUsers.value = users.value.items ?? [];
    }
    if (roles.status === 'fulfilled') {
      systemRoles.value = roles.value.items ?? [];
    }
    if (configs.status === 'rejected') {
      message.error('审批配置加载失败，请刷新后重试');
    }
    if (definitions.status === 'fulfilled') {
      applicationDefinitions.value = definitions.value;
    }
  } finally {
    configListLoading.value = false;
  }
});
</script>

<template>
  <div
    class="adpulse-section-page approval-management mx-auto w-full min-w-0 max-w-[1680px]"
  >
    <section class="approval-hero business-page-header rounded-xl">
      <div class="max-w-3xl">
        <h1 class="m-0 font-semibold tracking-tight text-slate-950">
          审批管理
        </h1>
        <p class="mb-0 mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          统一管理资源、资产与财务审批。你可以设计表单、编排多级审批流程，并设置每个节点的审批人与权限。
        </p>
      </div>
    </section>

    <section
      class="mt-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-center"
    >
      <Input
        v-model:value="searchKeyword"
        allow-clear
        class="approval-search w-full sm:w-[360px]"
        placeholder="搜索审批名称或审批人"
      >
        <template #prefix>
          <IconifyIcon icon="lucide:search" class="text-slate-400" />
        </template>
      </Input>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <Button type="primary" @click="createConfig">
          <template #icon>
            <IconifyIcon icon="lucide:plus" aria-hidden="true" />
          </template>
          创建审批配置
        </Button>
      </div>
    </section>

    <p class="mb-0 mt-2 text-sm text-slate-500">
      申请目录在申请管理中维护；此处仅配置表单、审批人与办理人。
    </p>

    <ListLoading v-if="configListLoading" />
    <section
      v-show="!configListLoading"
      :aria-busy="configListLoading"
      class="mt-5 space-y-4"
    >
      <article
        v-for="config in filteredConfigs"
        :key="config.id"
        class="approval-group overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
      >
        <div class="divide-y divide-slate-100 dark:divide-slate-800">
          <div
            class="approval-row group/row grid gap-4 px-5 py-4 transition-colors hover:bg-slate-50/80 lg:grid-cols-[minmax(320px,1.35fr)_minmax(180px,.7fr)_auto] lg:items-center dark:hover:bg-slate-800/50"
          >
            <div class="flex min-w-0 items-center gap-4">
              <div
                class="grid size-10 shrink-0 place-items-center rounded-lg text-lg text-white"
                :class="roleMeta[config.role].surface"
              >
                <IconifyIcon :icon="config.icon" />
              </div>
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    class="truncate border-0 bg-transparent p-0 text-left text-[15px] font-semibold text-slate-900 hover:text-blue-600 dark:text-white"
                    @click="openEditor(config)"
                  >
                    {{ config.name }}
                  </button>
                  <Tag v-if="!config.enabled" class="!m-0">已停用</Tag>
                  <Tag :color="roleMeta[config.role].color" class="!m-0">
                    {{ roleMeta[config.role].label }}
                  </Tag>
                </div>
                <p class="mb-0 mt-1 truncate text-sm text-slate-500">
                  {{ config.description || '暂未填写审批说明' }}
                </p>
              </div>
            </div>

            <div class="min-w-0 text-sm">
              <div
                class="flex items-center gap-2 text-slate-700 dark:text-slate-200"
              >
                <IconifyIcon icon="lucide:users-round" class="text-slate-400" />
                <span>{{
                  config.visibility === 'all' ? '全员可见' : '仅管理员可见'
                }}</span>
              </div>
              <div class="mt-1 flex items-center gap-2 text-xs text-slate-400">
                <span>
                  {{
                    config.nodes.filter((node) => node.kind === 'approval')
                      .length
                  }}
                  个审批节点
                </span>
                <span>·</span>
                <span>{{ config.updatedAt || '尚未发布' }}</span>
              </div>
            </div>

            <div class="flex items-center justify-end gap-0.5">
              <Tooltip title="编辑">
                <Button
                  type="text"
                  aria-label="编辑审批"
                  @click="openEditor(config)"
                >
                  <IconifyIcon icon="lucide:pencil" />
                </Button>
              </Tooltip>
              <Dropdown :trigger="['click']">
                <Button type="text" aria-label="更多审批操作" title="更多">
                  <IconifyIcon icon="lucide:ellipsis" />
                </Button>
                <template #overlay>
                  <Menu>
                    <MenuItem @click="toggleVisibility(config)">
                      {{
                        config.visibility === 'all'
                          ? '设为仅管理员可见'
                          : '设为全员可见'
                      }}
                    </MenuItem>
                    <MenuItem @click="toggleConfig(config)">
                      {{ config.enabled ? '停用' : '启用' }}
                    </MenuItem>
                    <MenuItem danger @click="deleteConfig(config)">
                      删除
                    </MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </div>
          </div>
        </div>
      </article>
    </section>

    <div
      v-if="!configListLoading && filteredConfigs.length === 0"
      class="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-14 text-center dark:border-slate-700 dark:bg-slate-900"
    >
      <IconifyIcon
        icon="lucide:file-search-2"
        class="mx-auto text-2xl text-slate-400"
      />
      <p class="mb-0 mt-3 text-sm text-slate-500">没有找到匹配的审批</p>
    </div>

    <Drawer
      v-model:open="editorOpen"
      class="approval-editor-drawer"
      root-class-name="approval-editor-drawer-root"
      :body-style="{ padding: '0', overflow: 'hidden' }"
      :closable="false"
      :header-style="{ display: 'none' }"
      :root-style="{ inset: '0', position: 'fixed' }"
      width="100vw"
      destroy-on-close
      placement="right"
    >
      <div class="flex h-full min-h-0 flex-col bg-slate-100 dark:bg-slate-950">
        <header
          class="editor-header grid shrink-0 grid-cols-[minmax(200px,1fr)_auto_minmax(260px,1fr)] items-center gap-4 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900"
        >
          <div class="flex min-w-0 items-center gap-3">
            <Button type="text" aria-label="返回审批列表" @click="closeEditor">
              <IconifyIcon icon="lucide:arrow-left" class="text-lg" />
            </Button>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span
                  class="truncate text-base font-semibold text-slate-900 dark:text-white"
                >
                  {{ editor.name }}
                </span>
                <IconifyIcon
                  icon="lucide:pencil"
                  class="text-xs text-slate-400"
                />
              </div>
              <p class="m-0 mt-0.5 text-xs text-slate-400">
                最近更新：{{ editor.updatedAt || '尚未同步' }}
              </p>
            </div>
          </div>

          <nav class="editor-steps flex items-center" aria-label="审批配置步骤">
            <button
              v-for="(step, index) in [
                '基础信息',
                '表单设计',
                '流程设计',
                '更多设置',
              ]"
              :key="step"
              type="button"
              class="editor-step"
              :class="{
                active: editorStep === index + 1,
                complete: editorStep > index + 1,
              }"
              @click="editorStep = index + 1"
            >
              <span class="step-number">{{ index + 1 }}</span>
              <span>{{ step }}</span>
            </button>
          </nav>

          <div class="flex items-center justify-end gap-2">
            <button
              v-if="incompleteCount"
              type="button"
              class="mr-1 border-0 bg-transparent p-0 text-xs text-red-500"
              @click="editorStep = incompleteCount ? 1 : editorStep"
            >
              {{ incompleteCount }} 项不完整
            </button>
            <Button @click="previewOpen = true">预览</Button>
            <Button type="primary" @click="publishConfig">发布</Button>
          </div>
        </header>

        <main
          v-if="editorStep === 1"
          class="min-h-0 flex-1 overflow-auto p-6 sm:p-10"
        >
          <section
            class="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 dark:border-slate-800 dark:bg-slate-900"
          >
            <div class="mb-7">
              <h2
                class="m-0 text-xl font-semibold text-slate-900 dark:text-white"
              >
                基础信息
              </h2>
              <p class="mb-0 mt-2 text-sm text-slate-500">
                设置审批名称及适用的资源申请。
              </p>
            </div>
            <Form layout="vertical">
              <FormItem label="审批名称" required>
                <Input
                  v-model:value="editor.name"
                  :maxlength="30"
                  show-count
                  placeholder="请输入审批名称"
                />
              </FormItem>
              <FormItem
                label="关联申请"
                required
                extra="一个申请只能关联一个审批配置，仅可选择尚未关联审批配置的申请。"
              >
                <Select
                  v-model:value="editor.applicationDefinitionIds"
                  mode="multiple"
                  :options="applicationDefinitionOptions"
                  placeholder="请选择适用当前流程的申请"
                  show-search
                  :filter-option="
                    (input: string, option: any) =>
                      option.label.toLowerCase().includes(input.toLowerCase())
                  "
                />
              </FormItem>
              <FormItem label="审批说明">
                <Textarea
                  v-model:value="editor.description"
                  :rows="4"
                  :maxlength="120"
                  show-count
                  placeholder="描述该审批的适用场景"
                />
              </FormItem>
              <FormItem label="审批图标">
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="icon in [
                      'lucide:workflow',
                      'lucide:radio-tower',
                      'lucide:laptop',
                      'lucide:badge-dollar-sign',
                      'lucide:briefcase-business',
                    ]"
                    :key="icon"
                    type="button"
                    class="grid size-10 place-items-center rounded-lg border bg-white text-lg text-slate-600 transition hover:border-blue-400 hover:text-blue-600 dark:bg-slate-900"
                    :class="
                      editor.icon === icon
                        ? 'border-blue-500 ring-2 ring-blue-100'
                        : 'border-slate-200 dark:border-slate-700'
                    "
                    @click="editor.icon = icon"
                  >
                    <IconifyIcon :icon="icon" />
                  </button>
                </div>
              </FormItem>
            </Form>
            <div class="mt-3 flex justify-end">
              <Button type="primary" @click="editorStep = 2">
                下一步：表单设计
              </Button>
            </div>
          </section>
        </main>

        <main
          v-else-if="editorStep === 2"
          class="relative grid min-h-0 flex-1 grid-cols-[240px_minmax(420px,1fr)_280px] overflow-hidden"
        >
          <section
            v-if="isFixedDailyReportConfig"
            class="bg-background absolute inset-0 z-10 flex items-center justify-center p-6"
          >
            <div
              class="border-border bg-card max-w-xl rounded-xl border p-6 text-center shadow-sm"
            >
              <IconifyIcon
                icon="lucide:lock-keyhole"
                class="text-muted-foreground size-8"
              />
              <h2 class="text-foreground mb-2 mt-4 text-lg font-semibold">
                固定日报表单
              </h2>
              <p class="text-muted-foreground m-0 text-sm leading-6">
                投放日报的字段和计算规则由业务代码固定维护，以保证与 MPower
                表单一致。请继续配置审批流程、可见范围和通知策略。
              </p>
              <Button class="mt-5" type="primary" @click="editorStep = 3"
                >进入流程设计</Button
              >
            </div>
          </section>
          <aside
            class="overflow-auto border-r border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
          >
            <h2
              class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
            >
              字段组件
            </h2>
            <p class="mb-4 mt-1 text-xs text-slate-400">
              点击组件添加至申请表单
            </p>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="field in availableFields"
                :key="field.label"
                type="button"
                class="flex min-h-20 flex-col items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-xs text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950"
                @click="addFormField(field)"
              >
                <IconifyIcon :icon="field.icon" class="text-xl" />
                <span>{{ field.label }}</span>
              </button>
            </div>
          </aside>
          <section class="overflow-auto p-8">
            <div
              class="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <header
                class="border-b border-slate-100 px-6 py-5 dark:border-slate-800"
              >
                <div class="flex items-center gap-3">
                  <div
                    class="grid size-10 place-items-center rounded-xl bg-blue-600 text-white"
                  >
                    <IconifyIcon :icon="editor.icon" />
                  </div>
                  <div>
                    <h3
                      class="m-0 text-base font-semibold text-slate-900 dark:text-white"
                    >
                      {{ editor.name }}
                    </h3>
                    <p class="m-0 mt-1 text-xs text-slate-400">
                      请填写以下信息后提交申请
                    </p>
                  </div>
                </div>
              </header>
              <div class="space-y-4 p-6">
                <div
                  v-for="(field, index) in editor.formFields"
                  :key="field.key"
                  class="group/field cursor-pointer rounded-xl border p-4 transition hover:border-blue-300 dark:border-slate-700"
                  :class="
                    activeFieldIndex === index
                      ? 'border-blue-500 bg-blue-50/40 ring-2 ring-blue-100 dark:bg-blue-950/20'
                      : 'border-slate-200'
                  "
                  @click="activeFieldIndex = index"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div
                        v-if="field.type === 'section'"
                        class="flex items-center gap-2"
                      >
                        <IconifyIcon
                          icon="lucide:heading-2"
                          class="shrink-0 text-blue-600"
                        />
                        <h4
                          class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                        >
                          {{ field.label }}
                        </h4>
                      </div>
                      <label
                        v-else
                        class="text-sm font-medium text-slate-700 dark:text-slate-200"
                      >
                        <span v-if="field.required" class="mr-1 text-red-500">
                          *
                        </span>
                        {{ field.label }}
                      </label>
                      <p
                        v-if="field.type === 'section' && field.helpText"
                        class="mb-0 mt-1 text-xs leading-5 text-slate-400"
                      >
                        {{ field.helpText }}
                      </p>
                    </div>
                    <div
                      class="flex shrink-0 opacity-0 transition group-hover/field:opacity-100"
                    >
                      <Button
                        type="text"
                        :disabled="index === 0"
                        aria-label="上移"
                        @click.stop="moveFormField(index, -1)"
                      >
                        <IconifyIcon icon="lucide:arrow-up" />
                      </Button>
                      <Button
                        type="text"
                        :disabled="index === editor.formFields.length - 1"
                        aria-label="下移"
                        @click.stop="moveFormField(index, 1)"
                      >
                        <IconifyIcon icon="lucide:arrow-down" />
                      </Button>
                      <Button
                        type="text"
                        danger
                        aria-label="删除字段"
                        @click.stop="removeFormField(index)"
                      >
                        <IconifyIcon icon="lucide:trash-2" />
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    v-if="field.type === 'textarea'"
                    class="mt-2"
                    disabled
                    :rows="2"
                    :placeholder="field.placeholder"
                  />
                  <InputNumber
                    v-else-if="field.type === 'number'"
                    disabled
                    class="mt-2 w-full"
                    :placeholder="field.placeholder"
                  />
                  <Button
                    v-else-if="field.type === 'pixel-selector'"
                    class="mt-2 w-full !justify-start"
                    disabled
                  >
                    {{ field.placeholder || '打开弹窗选择像素' }}
                  </Button>
                  <Select
                    v-else-if="['multi-select', 'select'].includes(field.type)"
                    disabled
                    class="mt-2 w-full"
                    :placeholder="resolveDynamicFieldPlaceholder(field)"
                  />
                  <Input
                    v-else-if="field.type !== 'section'"
                    class="mt-2"
                    disabled
                    :placeholder="field.placeholder"
                  />
                </div>
              </div>
            </div>
          </section>
          <aside
            class="overflow-auto border-l border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
          >
            <h2
              class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
            >
              表单设置
            </h2>
            <div v-if="activeField" class="mt-5 space-y-4">
              <Form layout="vertical">
                <FormItem
                  :label="
                    activeField.type === 'section' ? '分组标题' : '字段名称'
                  "
                  required
                >
                  <Input v-model:value="activeField.label" :maxlength="30" />
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="字段标识"
                  extra="保存后用于流程数据，建议仅使用字母、数字和下划线。"
                  required
                >
                  <Input v-model:value="activeField.key" :maxlength="40" />
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="控件类型"
                >
                  <Select
                    v-model:value="activeField.type"
                    :options="
                      availableFields.map((item) => ({
                        label: item.label,
                        value: item.type,
                      }))
                    "
                  />
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="占用宽度"
                >
                  <Radio.Group v-model:value="activeField.width">
                    <Radio.Button value="half">半行</Radio.Button>
                    <Radio.Button value="full">整行</Radio.Button>
                  </Radio.Group>
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="输入提示"
                >
                  <Input
                    v-model:value="activeField.placeholder"
                    :maxlength="100"
                  />
                </FormItem>
                <FormItem
                  :label="
                    activeField.type === 'section' ? '分组说明' : '帮助说明'
                  "
                >
                  <Input
                    v-model:value="activeField.helpText"
                    :maxlength="120"
                  />
                </FormItem>
                <FormItem
                  label="适用申请"
                  extra="默认对当前审批配置关联的全部申请展示。"
                >
                  <Radio.Group
                    :value="applicationScopeMode(activeField)"
                    @update:value="
                      updateApplicationScopeMode(activeField, $event)
                    "
                  >
                    <Radio.Button value="all">全部申请</Radio.Button>
                    <Radio.Button value="specific">指定申请</Radio.Button>
                  </Radio.Group>
                  <Select
                    v-if="applicationScopeMode(activeField) === 'specific'"
                    v-model:value="activeField.applicableApplicationCodes"
                    class="mt-3 w-full"
                    mode="multiple"
                    :options="linkedApplicationCodeOptions"
                    placeholder="请选择至少一个申请"
                    show-search
                  />
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="默认值"
                  extra="多选字段使用英文逗号分隔；系统数据源请填写对应 ID。"
                >
                  <Input
                    :value="defaultValueText(activeField)"
                    :maxlength="300"
                    placeholder="可选"
                    @update:value="updateDefaultValue(activeField, $event)"
                  />
                </FormItem>
                <FormItem
                  v-if="['multi-select', 'select'].includes(activeField.type)"
                  label="选项来源"
                  :extra="
                    activeField.optionSource === 'ad-accounts'
                      ? '申请人打开表单时，将实时读取账户管理中的最新广告账户。'
                      : undefined
                  "
                >
                  <Select
                    v-model:value="activeField.optionSource"
                    :options="[
                      { label: '自定义选项', value: 'custom' },
                      { label: '系统部门', value: 'departments' },
                      { label: '系统人员', value: 'users' },
                      { label: '系统项目', value: 'projects' },
                      { label: '系统角色', value: 'roles' },
                      { label: '系统渠道', value: 'channels' },
                      { label: '系统广告账户', value: 'ad-accounts' },
                    ]"
                  />
                </FormItem>
                <FormItem
                  v-if="
                    ['multi-select', 'select'].includes(activeField.type) &&
                    activeField.optionSource === 'custom'
                  "
                  label="自定义选项"
                  extra="每行一个选项；保存顺序即用户看到的顺序。"
                >
                  <Textarea
                    :value="customOptionsText(activeField)"
                    :rows="5"
                    @update:value="updateCustomOptions(activeField, $event)"
                  />
                </FormItem>
                <FormItem v-if="activeField.type === 'number'" label="数值范围">
                  <div class="grid grid-cols-2 gap-2">
                    <InputNumber
                      v-model:value="activeField.minValue"
                      class="w-full"
                      placeholder="最小值"
                    />
                    <InputNumber
                      v-model:value="activeField.maxValue"
                      class="w-full"
                      placeholder="最大值"
                    />
                  </div>
                </FormItem>
                <FormItem
                  v-else-if="activeField.type !== 'section'"
                  label="最大长度"
                >
                  <InputNumber
                    v-model:value="activeField.maxLength"
                    class="w-full"
                    :min="1"
                    placeholder="不限制"
                  />
                </FormItem>
                <FormItem
                  v-if="activeField.type !== 'section'"
                  label="格式校验"
                >
                  <Select
                    v-model:value="activeField.validationRule"
                    allow-clear
                    placeholder="不限制"
                    :options="[
                      { label: '数字 ID 列表', value: 'digit-list' },
                      { label: 'Pixel 名称列表', value: 'pixel-list' },
                      { label: '邮箱地址', value: 'email' },
                      { label: '网页链接', value: 'url' },
                      { label: '正数金额', value: 'positive-money' },
                    ]"
                  />
                </FormItem>
                <div
                  v-if="activeField.type !== 'section'"
                  class="flex items-center justify-between py-2"
                >
                  <span class="text-sm text-slate-700 dark:text-slate-200">
                    必填字段
                  </span>
                  <Switch v-model:checked="activeField.required" />
                </div>
                <div
                  v-if="activeField.type !== 'section'"
                  class="flex items-center justify-between py-2"
                >
                  <div>
                    <span class="text-sm text-slate-700 dark:text-slate-200">
                      只读字段
                    </span>
                    <p class="mb-0 mt-1 text-xs text-slate-400">
                      用户不可编辑，适合由系统接口自动回填的数据。
                    </p>
                  </div>
                  <Switch v-model:checked="activeField.readOnly" />
                </div>
                <section
                  v-if="activeField.type !== 'section'"
                  class="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3
                        class="m-0 text-sm font-semibold text-slate-800 dark:text-slate-100"
                      >
                        接口联动回填
                      </h3>
                      <p class="mb-0 mt-1 text-xs text-slate-400">
                        选择依赖字段后，从受控业务接口读取并写入当前字段。
                      </p>
                    </div>
                    <Switch
                      :checked="Boolean(activeField.autoFill)"
                      @change="toggleAutoFill(activeField, $event)"
                    />
                  </div>
                  <div v-if="activeField.autoFill" class="mt-4 space-y-3">
                    <Select
                      v-model:value="activeField.autoFill.source"
                      class="w-full"
                      :options="[
                        {
                          label: '渠道付款信息（昨日消耗/收款地址）',
                          value: 'channel-payment-context',
                        },
                      ]"
                    />
                    <Select
                      v-model:value="activeField.autoFill.triggerFieldKey"
                      class="w-full"
                      :options="applicationFieldOptions"
                      placeholder="请选择触发字段"
                    />
                    <Select
                      v-model:value="activeField.autoFill.resultKey"
                      class="w-full"
                      :options="[
                        {
                          label: '渠道昨日消耗',
                          value: 'channelYesterdayCost',
                        },
                        { label: '收款地址', value: 'paymentAddress' },
                      ]"
                      placeholder="请选择回填结果"
                    />
                  </div>
                </section>
                <section
                  v-if="
                    activeField.type !== 'section' &&
                    conditionFieldOptions(activeField).length > 0
                  "
                  class="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3
                        class="m-0 text-sm font-semibold text-slate-800 dark:text-slate-100"
                      >
                        条件显示
                      </h3>
                      <p class="mb-0 mt-1 text-xs text-slate-400">
                        满足条件时才向申请人展示该字段。
                      </p>
                    </div>
                    <Switch
                      :checked="Boolean(activeField.visibleWhen)"
                      @change="
                        toggleFieldCondition(activeField, 'visibleWhen', $event)
                      "
                    />
                  </div>
                  <div
                    v-if="activeField.visibleWhen"
                    class="mt-4 grid grid-cols-2 gap-2"
                  >
                    <Select
                      v-model:value="activeField.visibleWhen.fieldKey"
                      :options="conditionFieldOptions(activeField)"
                      placeholder="依赖字段"
                    />
                    <Select
                      v-model:value="activeField.visibleWhen.operator"
                      :options="[
                        { label: '等于', value: 'equals' },
                        { label: '不等于', value: 'not-equals' },
                        { label: '属于其中之一', value: 'in' },
                      ]"
                    />
                    <Input
                      class="col-span-2"
                      :value="conditionValueText(activeField.visibleWhen)"
                      placeholder="条件值；多个值用英文逗号分隔"
                      @update:value="
                        updateConditionValue(activeField.visibleWhen, $event)
                      "
                    />
                  </div>
                </section>
                <section
                  v-if="
                    activeField.type !== 'section' &&
                    conditionFieldOptions(activeField).length > 0
                  "
                  class="mt-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h3
                        class="m-0 text-sm font-semibold text-slate-800 dark:text-slate-100"
                      >
                        条件必填
                      </h3>
                      <p class="mb-0 mt-1 text-xs text-slate-400">
                        满足条件时，将该字段动态设为必填。
                      </p>
                    </div>
                    <Switch
                      :checked="Boolean(activeField.requiredWhen)"
                      @change="
                        toggleFieldCondition(
                          activeField,
                          'requiredWhen',
                          $event,
                        )
                      "
                    />
                  </div>
                  <div
                    v-if="activeField.requiredWhen"
                    class="mt-4 grid grid-cols-2 gap-2"
                  >
                    <Select
                      v-model:value="activeField.requiredWhen.fieldKey"
                      :options="conditionFieldOptions(activeField)"
                      placeholder="依赖字段"
                    />
                    <Select
                      v-model:value="activeField.requiredWhen.operator"
                      :options="[
                        { label: '等于', value: 'equals' },
                        { label: '不等于', value: 'not-equals' },
                        { label: '属于其中之一', value: 'in' },
                      ]"
                    />
                    <Input
                      class="col-span-2"
                      :value="conditionValueText(activeField.requiredWhen)"
                      placeholder="条件值；多个值用英文逗号分隔"
                      @update:value="
                        updateConditionValue(activeField.requiredWhen, $event)
                      "
                    />
                  </div>
                </section>
              </Form>
              <Button block type="primary" @click="editorStep = 3">
                下一步：流程设计
              </Button>
            </div>
            <div v-else class="mt-5 text-sm text-slate-400">
              请先添加或选择一个表单字段。
            </div>
          </aside>
        </main>

        <main
          v-else-if="editorStep === 3"
          class="flex min-h-0 flex-1 overflow-hidden"
        >
          <section class="flow-canvas relative min-w-0 flex-1 overflow-auto">
            <div
              class="flow-stage mx-auto flex min-h-full w-[720px] flex-col items-center px-20 py-12 transition-transform"
              :style="{
                transform: `scale(${zoom / 100})`,
                transformOrigin: 'top center',
              }"
            >
              <div class="flow-node flow-node-static border-slate-400">
                <div class="flow-node-header bg-slate-500">提交</div>
                <div class="flow-node-body">
                  <strong>提交人：全员可提交</strong>
                  <span>可设置抄送人</span>
                </div>
              </div>

              <template v-for="(node, index) in editor.nodes" :key="node.id">
                <div class="flow-connector">
                  <span class="flow-line"></span>
                  <button
                    type="button"
                    class="flow-add-button"
                    :aria-label="`在${node.label}前添加节点`"
                    @click="
                      addMenuAfterIndex =
                        addMenuAfterIndex === index - 1 ? undefined : index - 1
                    "
                  >
                    <IconifyIcon icon="lucide:plus" />
                  </button>
                  <div
                    v-if="addMenuAfterIndex === index - 1"
                    class="flow-add-menu"
                  >
                    <button
                      v-for="kind in addableNodeKinds"
                      :key="kind"
                      type="button"
                      @click="addNode(kind, index - 1)"
                    >
                      <span
                        class="grid size-7 place-items-center rounded-lg text-white"
                        :class="nodeMeta[kind].tone"
                      >
                        <IconifyIcon :icon="nodeMeta[kind].icon" />
                      </span>
                      <span>{{ nodeMeta[kind].label }}</span>
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  class="flow-node text-left"
                  :class="[
                    activeNodeId === node.id ? 'active' : '',
                    node.kind === 'approval'
                      ? 'border-amber-500'
                      : node.kind === 'copy'
                        ? 'border-indigo-500'
                        : 'border-violet-500',
                  ]"
                  @click="activeNodeId = node.id"
                >
                  <div
                    class="flow-node-header"
                    :class="nodeMeta[node.kind].tone"
                  >
                    <span class="flex items-center gap-1.5">
                      <IconifyIcon :icon="nodeMeta[node.kind].icon" />{{
                        node.label
                      }}
                    </span>
                    <IconifyIcon icon="lucide:chevron-right" />
                  </div>
                  <div class="flow-node-body">
                    <strong>{{ nodeSummary(node) }}</strong>
                    <span v-if="node.kind === 'approval'">{{
                      node.assigneeMode === 'role'
                        ? '按系统角色审批'
                        : node.assigneeMode === 'department'
                          ? '按直属部门成员审批'
                          : '指定成员审批'
                    }}</span>
                    <span v-else>{{ nodeMeta[node.kind].label }}节点</span>
                  </div>
                </button>
              </template>

              <div class="flow-connector">
                <span class="flow-line"></span>
                <button
                  type="button"
                  class="flow-add-button"
                  aria-label="在结束前添加节点"
                  @click="
                    addMenuAfterIndex =
                      addMenuAfterIndex === editor.nodes.length - 1
                        ? undefined
                        : editor.nodes.length - 1
                  "
                >
                  <IconifyIcon icon="lucide:plus" />
                </button>
                <div
                  v-if="addMenuAfterIndex === editor.nodes.length - 1"
                  class="flow-add-menu"
                >
                  <button
                    v-for="kind in addableNodeKinds"
                    :key="kind"
                    type="button"
                    @click="addNode(kind, editor.nodes.length - 1)"
                  >
                    <span
                      class="grid size-7 place-items-center rounded-lg text-white"
                      :class="nodeMeta[kind].tone"
                    >
                      <IconifyIcon :icon="nodeMeta[kind].icon" />
                    </span>
                    <span>{{ nodeMeta[kind].label }}</span>
                  </button>
                </div>
              </div>

              <div class="flow-node flow-node-static border-slate-400">
                <div class="flow-node-header bg-slate-500">结束</div>
                <div class="flow-node-body">
                  <strong>
                    {{
                      editor.settings.completionMode === 'pixel-auto-assign'
                        ? '自动分配所选像素'
                        : '流程完成'
                    }}
                  </strong>
                  <span>
                    {{
                      editor.settings.completionMode === 'pixel-auto-assign'
                        ? '最终审批通过后写入项目和使用团队'
                        : '可设置抄送人'
                    }}
                  </span>
                </div>
              </div>
            </div>

            <div class="flow-zoom-controls">
              <Button
                type="text"
                aria-label="缩小流程图"
                @click="changeZoom(-10)"
              >
                <IconifyIcon icon="lucide:zoom-out" />
              </Button>
              <span>{{ zoom }}%</span>
              <Button
                type="text"
                aria-label="放大流程图"
                @click="changeZoom(10)"
              >
                <IconifyIcon icon="lucide:zoom-in" />
              </Button>
              <Button type="text" aria-label="重置缩放" @click="zoom = 100">
                <IconifyIcon icon="lucide:scan" />
              </Button>
            </div>
          </section>

          <aside
            v-if="activeNode"
            class="node-settings-panel w-[440px] shrink-0 overflow-auto border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
          >
            <header
              class="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800"
            >
              <div class="flex min-w-0 items-center gap-2">
                <h2
                  class="m-0 truncate text-lg font-semibold text-slate-900 dark:text-white"
                >
                  {{ activeNode.label }}
                </h2>
                <IconifyIcon icon="lucide:pencil" class="text-slate-400" />
              </div>
              <Tooltip title="删除节点">
                <Button
                  type="text"
                  danger
                  aria-label="删除节点"
                  @click="removeNode"
                >
                  <IconifyIcon icon="lucide:trash-2" />
                </Button>
              </Tooltip>
            </header>

            <div class="p-5">
              <template v-if="activeNode.kind === 'approval'">
                <section>
                  <div class="mb-3 flex items-center justify-between gap-3">
                    <h3
                      class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                    >
                      审批类型
                    </h3>
                  </div>
                  <Radio.Group
                    v-model:value="editor.settings.approvalType"
                    class="flex flex-wrap gap-x-5 gap-y-2"
                  >
                    <Radio value="manual">人工审批</Radio>
                    <Radio value="auto-approve">自动通过</Radio>
                    <Radio value="auto-reject">自动拒绝</Radio>
                  </Radio.Group>
                </section>
                <section class="settings-card mt-3">
                  <h3 class="settings-card-title">审批人</h3>
                  <Radio.Group
                    v-model:value="activeNode.assigneeMode"
                    class="grid grid-cols-3 gap-x-3 gap-y-3 p-4"
                    @change="handleAssigneeModeChange"
                  >
                    <Radio
                      v-for="option in assigneeOptions"
                      :key="option.value"
                      :value="option.value"
                      :disabled="option.disabled"
                    >
                      {{ option.label }}
                    </Radio>
                  </Radio.Group>
                  <div
                    class="border-t border-slate-100 p-4 dark:border-slate-800"
                  >
                    <label
                      class="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-200"
                    >
                      {{
                        activeNode.assigneeMode === 'role'
                          ? '指定审批角色'
                          : activeNode.assigneeMode === 'department'
                            ? '指定审批部门'
                            : '指定审批成员'
                      }}
                    </label>
                    <Select
                      v-if="activeNode.assigneeMode === 'role'"
                      v-model:value="activeNode.roleIds"
                      class="w-full"
                      mode="multiple"
                      :options="roleOptions"
                      option-filter-prop="label"
                      placeholder="请选择系统角色"
                      show-search
                      @change="handleRoleChange"
                    />
                    <DepartmentTreeSelect
                      v-else-if="activeNode.assigneeMode === 'department'"
                      v-model="activeNode.departmentIds"
                      class="w-full"
                      multiple
                      placeholder="请选择系统部门"
                      value-mode="id"
                      @change="handleDepartmentChange"
                    />
                    <Select
                      v-else
                      v-model:value="activeNode.approverId"
                      class="w-full"
                      :options="approverOptions"
                      option-filter-prop="label"
                      placeholder="请选择系统人员"
                      show-search
                      @change="handleApproverChange"
                    />
                    <p class="mb-0 mt-2 text-xs leading-5 text-slate-400">
                      部门审批仅包含所选部门的直属启用成员；系统会在申请提交时确定实际审批人。
                    </p>
                  </div>
                </section>

                <Button
                  type="link"
                  class="!mt-3 !px-0"
                  @click="addApprovalAfterCurrent"
                >
                  <template #icon>
                    <IconifyIcon icon="lucide:plus" />
                  </template>
                  添加审批人
                </Button>
              </template>

              <template v-else-if="activeNode.kind === 'copy'">
                <h3
                  class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                >
                  设置抄送人
                </h3>
                <p class="mb-4 mt-1 text-xs leading-5 text-slate-400">
                  审批流转到该节点时，系统会向所选成员发送审批进度。
                </p>
                <Select
                  v-model:value="activeNode.users"
                  class="w-full"
                  mode="multiple"
                  :options="ccOptions"
                  placeholder="请选择系统人员"
                />
                <div
                  class="mt-6 rounded-xl bg-indigo-50 p-4 text-xs leading-5 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300"
                >
                  抄送人只能查看审批，不会阻塞流程。
                </div>
              </template>

              <template v-else-if="activeNode.kind === 'handler'">
                <h3
                  class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                >
                  设置办理人
                </h3>
                <p class="mb-4 mt-1 text-xs leading-5 text-slate-400">
                  办理人需要完成指定任务后，流程才会继续。
                </p>
                <FormItem label="办理人来源" class="mb-3">
                  <Radio.Group v-model:value="activeNode.handlerSource">
                    <Radio
                      v-for="option in handlerSourceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </Radio>
                  </Radio.Group>
                </FormItem>
                <FormItem
                  v-if="
                    (activeNode.handlerSource ?? 'fixed-user') === 'fixed-user'
                  "
                  label="办理人"
                  class="mb-3"
                >
                  <Select
                    v-model:value="activeNode.approverId"
                    :options="approverOptions"
                    placeholder="请选择办理人"
                    @change="handleApproverChange"
                  />
                </FormItem>
                <FormItem v-else label="关联审批节点" class="mb-3">
                  <Select
                    v-model:value="activeNode.handlerApprovalNodeId"
                    :options="handlerApprovalNodeOptions"
                    placeholder="请选择审批节点"
                  />
                  <p class="mb-0 mt-2 text-xs leading-5 text-slate-400">
                    支持成员、角色和部门审批节点；办理阶段将由该节点实际完成审批的人负责。
                  </p>
                </FormItem>
                <section
                  class="mt-6 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h4
                        class="m-0 text-sm font-semibold text-slate-800 dark:text-slate-100"
                      >
                        分配系统资源
                      </h4>
                      <p class="mb-0 mt-1 text-xs leading-5 text-slate-400">
                        办理时从对应类型的可用库存中选择并分配给申请人。
                      </p>
                    </div>
                    <Switch
                      :checked="
                        Boolean(
                          activeNode.handlerAction?.resourceAssignment?.enabled,
                        )
                      "
                      @change="toggleResourceAssignment"
                    />
                  </div>
                  <div
                    v-if="activeNode.handlerAction?.resourceAssignment?.enabled"
                    class="mt-4 space-y-3"
                  >
                    <FormItem label="实际资产类型字段" class="mb-3">
                      <Select
                        v-model:value="
                          activeNode.handlerAction.resourceAssignment
                            .assetTypeFieldKey
                        "
                        allow-clear
                        :options="applicationAssetTypeFieldOptions"
                        placeholder="默认使用审批配置类型"
                      />
                    </FormItem>
                    <FormItem label="数量字段" class="mb-3">
                      <Select
                        v-model:value="
                          activeNode.handlerAction.resourceAssignment
                            .quantityFieldKey
                        "
                        :options="applicationFieldOptions"
                        placeholder="默认按申请数量"
                      />
                    </FormItem>
                    <FormItem label="渠道字段" class="mb-0">
                      <Select
                        v-model:value="
                          activeNode.handlerAction.resourceAssignment
                            .channelFieldKey
                        "
                        allow-clear
                        :options="applicationFieldOptions"
                        placeholder="不限制渠道"
                      />
                    </FormItem>
                  </div>
                </section>

                <section
                  class="mt-4 rounded-xl border border-slate-200 p-4 dark:border-slate-700"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <h4
                        class="m-0 text-sm font-semibold text-slate-800 dark:text-slate-100"
                      >
                        办理表单
                      </h4>
                      <p class="mb-0 mt-1 text-xs leading-5 text-slate-400">
                        这些字段只在办理人完成处理时显示，不会出现在审批弹窗。
                      </p>
                    </div>
                    <Button @click="addHandlerField('text')"> 添加字段 </Button>
                  </div>
                  <div
                    v-if="activeNode.handlerAction?.formSchema?.length"
                    class="mt-4 space-y-3"
                  >
                    <div
                      v-for="(field, fieldIndex) in activeNode.handlerAction
                        .formSchema"
                      :key="field.key"
                      class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/70"
                    >
                      <div class="grid grid-cols-2 gap-2">
                        <Input
                          v-model:value="field.label"
                          placeholder="字段名称"
                        />
                        <Input
                          v-model:value="field.key"
                          placeholder="字段标识"
                        />
                        <Select
                          v-model:value="field.type"
                          :options="handlerFieldTypeOptions"
                        />
                        <div class="flex items-center justify-between px-1">
                          <span class="text-xs text-slate-500">办理时必填</span>
                          <Switch v-model:checked="field.required" />
                        </div>
                      </div>
                      <Input
                        v-model:value="field.placeholder"
                        class="mt-2"
                        placeholder="输入提示（可选）"
                      />
                      <div
                        v-if="field.type === 'number'"
                        class="mt-2 grid grid-cols-2 gap-2"
                      >
                        <InputNumber
                          v-model:value="field.minValue"
                          class="w-full"
                          placeholder="最小值"
                        />
                        <InputNumber
                          v-model:value="field.maxValue"
                          class="w-full"
                          placeholder="最大值"
                        />
                      </div>
                      <div
                        v-if="field.type === 'image-upload'"
                        class="mt-2 grid grid-cols-2 gap-2"
                      >
                        <InputNumber
                          v-model:value="field.maxCount"
                          class="w-full"
                          :min="1"
                          :max="9"
                          placeholder="最多图片数"
                        />
                        <InputNumber
                          v-model:value="field.maxFileSizeMb"
                          class="w-full"
                          :min="1"
                          :max="20"
                          placeholder="单张大小 MB"
                        />
                      </div>
                      <Button
                        class="mt-2"
                        danger
                        type="link"
                        @click="removeHandlerField(fieldIndex)"
                      >
                        删除字段
                      </Button>
                    </div>
                  </div>
                  <p v-else class="mb-0 mt-4 text-xs text-slate-400">
                    没有办理表单时，办理人只需填写统一处理说明。
                  </p>
                </section>
              </template>
            </div>
          </aside>
        </main>

        <main v-else class="min-h-0 flex-1 overflow-auto p-6 sm:p-10">
          <section
            class="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8 dark:border-slate-800 dark:bg-slate-900"
          >
            <div class="mb-7">
              <h2
                class="m-0 text-xl font-semibold text-slate-900 dark:text-white"
              >
                更多设置
              </h2>
              <p class="mb-0 mt-2 text-sm text-slate-500">
                设置审批可见范围、启用状态及通知策略。
              </p>
            </div>
            <div class="divide-y divide-slate-100 dark:divide-slate-800">
              <div class="flex items-center justify-between gap-5 py-5">
                <div>
                  <h3
                    class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                  >
                    启用审批
                  </h3>
                  <p class="mb-0 mt-1 text-xs text-slate-400">
                    停用后不能发起新的申请，历史审批不受影响。
                  </p>
                </div>
                <Switch v-model:checked="editor.enabled" />
              </div>
              <div class="flex items-start justify-between gap-5 py-5">
                <div>
                  <h3
                    class="m-0 text-sm font-semibold text-slate-900 dark:text-white"
                  >
                    可见范围
                  </h3>
                  <p class="mb-0 mt-1 text-xs text-slate-400">
                    控制哪些成员可以在发起申请时看到此审批。
                  </p>
                </div>
                <Radio.Group
                  v-model:value="editor.visibility"
                  button-style="solid"
                >
                  <Radio.Button value="all">全员可见</Radio.Button>
                  <Radio.Button value="admins">仅管理员</Radio.Button>
                </Radio.Group>
              </div>
            </div>
            <div class="mt-5 flex justify-end gap-2">
              <Button @click="previewOpen = true">预览</Button>
              <Button type="primary" @click="publishConfig">发布审批</Button>
            </div>
          </section>
        </main>
      </div>

      <Modal
        v-model:open="previewOpen"
        centered
        :footer="null"
        title="审批预览"
        width="640px"
      >
        <div class="pt-2">
          <div class="bg-primary text-primary-foreground rounded-xl p-5">
            <div class="flex items-center gap-3">
              <div
                class="grid size-11 place-items-center rounded-xl bg-white/15 text-xl"
              >
                <IconifyIcon :icon="editor.icon" />
              </div>
              <div>
                <h3 class="m-0 text-lg font-semibold text-white">
                  {{ editor.name }}
                </h3>
                <p class="m-0 mt-1 text-xs text-blue-100">
                  {{ editor.description || '审批申请' }}
                </p>
              </div>
            </div>
          </div>
          <div class="mt-5 grid gap-3 sm:grid-cols-2">
            <div
              v-for="field in editor.formFields"
              :key="field.key"
              :class="
                field.type === 'section' || field.width === 'full'
                  ? 'sm:col-span-2'
                  : ''
              "
            >
              <template v-if="field.type === 'section'">
                <h4 class="m-0 text-sm font-semibold text-slate-900">
                  {{ field.label }}
                </h4>
                <p
                  v-if="field.helpText"
                  class="mb-0 mt-1 text-xs text-slate-400"
                >
                  {{ field.helpText }}
                </p>
                <div class="mt-2 h-px bg-slate-100"></div>
              </template>
              <template v-else>
                <div class="mb-1.5 text-xs font-medium text-slate-600">
                  {{ field.label }}
                </div>
                <div
                  class="h-9 rounded-lg border border-slate-200 bg-slate-50"
                ></div>
              </template>
            </div>
          </div>
          <div class="mt-6 border-t border-slate-100 pt-5">
            <h4 class="m-0 text-sm font-semibold text-slate-900">审批流程</h4>
            <div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span
                class="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600"
              >
                提交人
              </span>
              <template v-for="node in editor.nodes" :key="node.id">
                <IconifyIcon icon="lucide:arrow-right" class="text-slate-300" />
                <span class="rounded-full bg-blue-50 px-3 py-1.5 text-blue-700">
                  {{ node.label }}
                </span>
              </template>
              <IconifyIcon icon="lucide:arrow-right" class="text-slate-300" />
              <span
                class="rounded-full bg-emerald-50 px-3 py-1.5 text-emerald-700"
              >
                完成
              </span>
            </div>
          </div>
        </div>
      </Modal>
    </Drawer>
  </div>
</template>

<style scoped>
.approval-management {
  padding: var(--adpulse-page-gutter);
  color: var(--adpulse-text);
}

.approval-hero {
  min-height: var(--adpulse-page-header-min-height);
  padding: var(--adpulse-page-header-padding-block) var(--adpulse-page-gutter);
  border: 1px solid hsl(var(--border));
  background: var(--adpulse-surface);
  box-shadow: var(--adpulse-card-shadow);
}

.approval-hero h1 {
  font-size: var(--adpulse-page-title-size);
  line-height: 1.35;
}

.approval-group {
  box-shadow: 0 1px 2px rgb(15 23 42 / 3%);
}

.approval-management :deep(.rounded-2xl) {
  border-radius: var(--adpulse-card-radius);
}

.editor-header {
  z-index: 20;
  box-shadow: 0 1px 8px rgb(15 23 42 / 5%);
}

.editor-step {
  position: relative;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 9px 22px 12px;
  color: #64748b;
  font-size: 14px;
  white-space: nowrap;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.editor-step::after {
  position: absolute;
  right: 0;
  bottom: -13px;
  left: 0;
  height: 2px;
  content: '';
  background: transparent;
}

.editor-step.active {
  color: #2563eb;
  font-weight: 600;
}

.editor-step.active::after {
  background: #2563eb;
}

.step-number {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border: 1px solid currentcolor;
  border-radius: 50%;
  font-size: 12px;
}

.editor-step.complete .step-number,
.editor-step.active .step-number {
  color: white;
  background: #2563eb;
  border-color: #2563eb;
}

.flow-canvas {
  background-color: #f1f5f9;
  background-image: radial-gradient(#cbd5e1 0.8px, transparent 0.8px);
  background-size: 22px 22px;
}

.flow-stage {
  isolation: isolate;
}

.flow-node {
  position: relative;
  z-index: 2;
  width: 300px;
  overflow: hidden;
  color: inherit;
  background: white;
  border: 2px solid;
  border-radius: 10px;
  box-shadow: 0 6px 18px rgb(15 23 42 / 9%);
  cursor: pointer;
}

.flow-node.active {
  box-shadow:
    0 0 0 5px rgb(59 130 246 / 16%),
    0 9px 24px rgb(15 23 42 / 12%);
}

.flow-node-static {
  cursor: default;
}

.flow-node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 31px;
  padding: 5px 11px;
  color: white;
  font-size: 12px;
  font-weight: 600;
}

.flow-node-body {
  display: flex;
  min-height: 54px;
  flex-direction: column;
  justify-content: center;
  padding: 9px 13px;
}

.flow-node-body strong {
  overflow: hidden;
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.flow-node-body span {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 11px;
}

.flow-connector {
  position: relative;
  z-index: 5;
  width: 44px;
  height: 74px;
}

.flow-line {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  background: #cbd5e1;
  transform: translateX(-50%);
}

.flow-line::after {
  position: absolute;
  bottom: -1px;
  left: 50%;
  width: 0;
  height: 0;
  content: '';
  border-top: 7px solid #94a3b8;
  border-right: 5px solid transparent;
  border-left: 5px solid transparent;
  transform: translateX(-50%);
}

.flow-add-button {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 3;
  display: grid;
  width: 27px;
  height: 27px;
  place-items: center;
  color: #2563eb;
  background: white;
  border: 1px solid #bfdbfe;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgb(37 99 235 / 14%);
  cursor: pointer;
  transform: translate(-50%, -50%);
}

.flow-add-button:hover {
  color: white;
  background: #2563eb;
  border-color: #2563eb;
}

.flow-add-menu {
  position: absolute;
  top: 50%;
  left: calc(50% + 27px);
  z-index: 30;
  width: 178px;
  overflow: hidden;
  padding: 5px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 16px 38px rgb(15 23 42 / 18%);
  transform: translateY(-50%);
}

.flow-add-menu button {
  display: flex;
  width: 100%;
  gap: 9px;
  align-items: center;
  padding: 8px;
  color: #334155;
  font-size: 13px;
  background: transparent;
  border: 0;
  border-radius: 7px;
  cursor: pointer;
}

.flow-add-menu button:hover {
  color: #2563eb;
  background: hsl(var(--accent));
}

.flow-zoom-controls {
  position: fixed;
  bottom: 22px;
  left: 22px;
  z-index: 15;
  display: flex;
  align-items: center;
  padding: 3px;
  color: #475569;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 5px 18px rgb(15 23 42 / 10%);
}

.flow-zoom-controls > span {
  min-width: 48px;
  text-align: center;
  font-size: 12px;
}

.settings-tabs {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.settings-tabs button {
  padding: 8px 6px;
  color: #475569;
  font-size: 13px;
  background: white;
  border: 0;
  border-right: 1px solid #e2e8f0;
  cursor: pointer;
}

.settings-tabs button:last-child {
  border-right: 0;
}

.settings-tabs button.active {
  color: white;
  font-weight: 600;
  background: #3563d9;
}

.settings-card {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.settings-card-title {
  margin: 0;
  padding: 10px 14px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
  background: #f8fafc;
}

@media (max-width: 1180px) {
  .editor-header {
    grid-template-columns: minmax(180px, 1fr) auto;
  }

  .editor-steps {
    grid-row: 2;
    grid-column: 1 / -1;
    justify-content: center;
  }

  .editor-step::after {
    bottom: -4px;
  }

  .node-settings-panel {
    width: 390px;
  }
}

@media (max-width: 900px) {
  .editor-header {
    display: flex;
    flex-wrap: wrap;
  }

  .editor-steps {
    order: 3;
    width: 100%;
    overflow-x: auto;
    justify-content: flex-start;
  }

  .editor-step {
    padding-inline: 12px;
  }

  .node-settings-panel {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(420px, 92vw);
    z-index: 30;
    box-shadow: -12px 0 30px rgb(15 23 42 / 14%);
  }
}
</style>
