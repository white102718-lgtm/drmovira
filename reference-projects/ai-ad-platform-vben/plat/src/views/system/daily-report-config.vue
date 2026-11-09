<script lang="ts" setup>
import type {
  ReportFieldType,
  ReportRule,
  ReportRuleMember,
} from '#/domain/report-rules';
import type { DepartmentScopeUserOption } from '#/api/system/user';
import type { SystemDepartmentApi } from '#/api/system/department';
import type { SystemRoleApi } from '#/api/system/role';

import { computed, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Modal,
  Radio,
  Select,
  Switch,
  Tree,
  Tooltip,
  message,
} from 'ant-design-vue';

import { getSystemDepartmentTree } from '#/api/system/department';
import { getRoleList } from '#/api/system/role';
import { getDepartmentScopeUserOptions } from '#/api/system/user';
import { dailyReportApi } from '#/api/daily-report';
import {
  createRuleFromDailyReportTemplate,
  dailyReportQuickTemplates,
} from '#/domain/daily-report-templates';
import {
  getDefaultReportRule,
  loadReportRules,
  saveReportRules,
} from '#/domain/report-rules';
import {
  isFixedDailyReportRule,
  isMaterialDesignerMonthlyReportRule,
  mergeFixedDailyReportRules,
} from '#/domain/fixed-daily-report-rules';

defineOptions({ name: 'SystemDailyReportConfig' });

const rules = ref<ReportRule[]>(mergeFixedDailyReportRules(loadReportRules()));
const showCreate = ref(false);
const editing = ref(false);
const activeStep = ref<'content' | 'settings'>('content');
const draft = reactive<ReportRule>(getDefaultReportRule());
const rule = computed(() => rules.value[0] ?? getDefaultReportRule());
const isEditingFixedDailyReport = computed(() =>
  isFixedDailyReportRule(draft.id),
);
const isEditingMaterialDesignerMonthlyReport = computed(() =>
  isMaterialDesignerMonthlyReportRule(draft.id),
);
const timezoneOptions = [
  { label: '中国标准时间（Asia/Shanghai）', value: 'Asia/Shanghai' },
  { label: '日本标准时间（Asia/Tokyo）', value: 'Asia/Tokyo' },
  { label: '新加坡时间（Asia/Singapore）', value: 'Asia/Singapore' },
  { label: '洛杉矶时间（America/Los_Angeles）', value: 'America/Los_Angeles' },
  { label: '协调世界时（UTC）', value: 'UTC' },
];
const timeOptions = Array.from({ length: 24 }, (_, hour) => {
  const value = `${String(hour).padStart(2, '0')}:00`;
  return { label: value, value };
});
const monthDayOptions = Array.from({ length: 28 }, (_, index) => ({
  label: `${index + 1} 日`,
  value: index + 1,
}));
const fieldTypes: { label: string; value: ReportFieldType }[] = [
  { label: '文本', value: 'text' },
  { label: '数字', value: 'number' },
  { label: '单选', value: 'single-select' },
  { label: '多选', value: 'multi-select' },
  { label: '日期', value: 'date' },
  { label: '图片', value: 'image' },
  { label: '附件', value: 'upload' },
  { label: '多行文本', value: 'textarea' },
];

const submissionWeekday = computed<number>({
  get: () => draft.schedule.submissionDays[0] ?? 1,
  set: (day) => {
    draft.schedule.submissionDays = [day];
  },
});

function changeReportPeriod(period: ReportRule['period']) {
  draft.period = period;
  if (period === '每天' || period === '每月' || period === '不重复') {
    draft.schedule.submissionDays = [];
  }
  if (period === '每周' || period === '每双周') {
    draft.schedule.submissionDays = [submissionWeekday.value];
  }
  if (period === '每月') {
    draft.schedule.submissionDayOfMonth ??= 1;
  }
}

const reportIconOptions = [
  { color: '#ff8a00', icon: 'calendar-days', label: '日历' },
  { color: '#10cdb9', icon: 'clipboard-check', label: '清单' },
  { color: '#7c3aed', icon: 'bar-chart-3', label: '图表' },
  { color: '#12cbb5', icon: 'users-round', label: '团队' },
  { color: '#fb4b47', icon: 'briefcase-business', label: '工作' },
  { color: '#d33dcb', icon: 'message-circle-heart', label: '沟通' },
  { color: '#32bd29', icon: 'notebook-tabs', label: '笔记' },
] as const;

const legacyReportIcons: Record<string, string> = {
  '1': 'calendar-days',
  '7': 'clipboard-check',
  '31': 'bar-chart-3',
  L: 'briefcase-business',
  '●': 'users-round',
};

function reportIconName(icon?: string | null) {
  // Historical rules may not have an icon. Keep the configuration page usable while
  // rendering a stable default instead of calling startsWith on an undefined value.
  const normalized = legacyReportIcons[icon ?? ''] ?? icon ?? 'calendar-days';
  return normalized.startsWith('lucide:') ? normalized : `lucide:${normalized}`;
}

function isReportIconSelected(icon: string) {
  return reportIconName(draft.icon) === reportIconName(icon);
}

function selectReportIcon(icon: string) {
  draft.icon = icon;
}

function isOptionField(type: ReportFieldType) {
  return type === 'multi-select' || type === 'single-select';
}

type PersonnelTarget = 'cc' | 'reporters' | 'viewers' | 'writers';
type PersonnelScopeMode = 'department' | 'role' | 'user';

interface OrganizationDepartment {
  children?: OrganizationDepartment[];
  id: string;
  name: string;
}

const personnelTarget = ref<PersonnelTarget>('writers');
const personnelPickerOpen = ref(false);
const organizationLoading = ref(false);
const organizationLoaded = ref(false);
const organizationKeyword = ref('');
const organizationTree = ref<OrganizationDepartment[]>([]);
const organizationUsers = ref<DepartmentScopeUserOption[]>([]);
const organizationRoles = ref<SystemRoleApi.Role[]>([]);
const pickerMembers = ref<ReportRuleMember[]>([]);
const pickerDepartmentIds = ref<string[]>([]);
const personnelScopeMode = ref<PersonnelScopeMode>('user');

const personnelTargetMeta: Record<
  PersonnelTarget,
  { empty: string; title: string }
> = {
  cc: { empty: '选择需要抄送的组织成员', title: '选择抄送对象' },
  reporters: { empty: '选择需要接收汇报的组织成员', title: '选择汇报对象' },
  viewers: { empty: '选择可查看汇报的组织成员', title: '选择可查看人员' },
  writers: { empty: '选择可以填写汇报的组织成员', title: '选择填写人员' },
};

const filteredOrganizationRoles = computed(() => {
  const keyword = organizationKeyword.value.trim().toLowerCase();
  if (!keyword) return organizationRoles.value;
  return organizationRoles.value.filter((role) =>
    [role.roleCode, role.roleName].join(' ').toLowerCase().includes(keyword),
  );
});

const filteredOrganizationUsers = computed(() => {
  const keyword = organizationKeyword.value.trim().toLowerCase();
  if (!keyword) return organizationUsers.value;
  return organizationUsers.value.filter((user) =>
    [user.name, user.label, user.department]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(keyword),
  );
});

const legacyPersonnelMembers = computed(() =>
  (['writers', 'reporters', 'cc', 'viewers'] as const).flatMap((target) =>
    draft.personnel[target].filter(
      (member) => !/^(?:department|role|user):[1-9]\d*$/.test(member.id),
    ),
  ),
);

const requiresViewerScopeMigration = computed(
  () => draft.personnel.viewerScope === 'all',
);

const organizationTreeNodes = computed(() => {
  const toNodes = (nodes: OrganizationDepartment[]): any[] =>
    nodes.map((node) => ({
      children: node.children?.length ? toNodes(node.children) : undefined,
      key: node.id,
      title: node.name,
    }));
  return toNodes(organizationTree.value);
});

function selectedPersonnel(target: PersonnelTarget) {
  return draft.personnel[target];
}

function personnelMemberTypeLabel(type: ReportRuleMember['type']) {
  return {
    department: '部门',
    role: '角色',
    user: '人员',
  }[type];
}

async function loadOrganization() {
  if (organizationLoaded.value || organizationLoading.value) return;
  organizationLoading.value = true;
  try {
    const [departments, users, roles] = await Promise.all([
      getSystemDepartmentTree(),
      getDepartmentScopeUserOptions(),
      getRoleList({ page: 1, pageSize: 200, status: 1 }),
    ]);
    organizationTree.value = mapSystemDepartments(departments ?? []);
    organizationUsers.value = users ?? [];
    organizationRoles.value = roles.items ?? [];
  } catch {
    organizationTree.value = [];
    organizationUsers.value = [];
    organizationRoles.value = [];
    message.error('系统组织数据加载失败，请稍后重试');
  } finally {
    organizationLoading.value = false;
    organizationLoaded.value = true;
  }
}

function mapSystemDepartments(
  departments: readonly SystemDepartmentApi.Department[],
): OrganizationDepartment[] {
  return departments.map((department) => ({
    children: mapSystemDepartments(department.children ?? []),
    id: department.id,
    name: department.deptName,
  }));
}

function findDepartment(
  id: string,
  nodes = organizationTree.value,
): OrganizationDepartment | undefined {
  for (const node of nodes) {
    if (node.id === id) return node;
    const found = findDepartment(id, node.children ?? []);
    if (found) return found;
  }
}

async function openPersonnelPicker(target: PersonnelTarget) {
  personnelTarget.value = target;
  organizationKeyword.value = '';
  pickerMembers.value = selectedPersonnel(target).map((member) => ({
    ...member,
  }));
  pickerDepartmentIds.value = pickerMembers.value
    .filter((member) => member.type === 'department')
    .map((member) => member.id.replace('department:', ''));
  await loadOrganization();
  personnelScopeMode.value = pickerMembers.value[0]?.type ?? 'user';
  personnelPickerOpen.value = true;
}

function updatePersonnelScopeMode(mode: PersonnelScopeMode) {
  if (pickerMembers.value.length > 0 && pickerMembers.value[0]?.type !== mode) {
    pickerMembers.value = [];
    pickerDepartmentIds.value = [];
    message.info('已清空当前选择，请在新的范围类型中重新选择');
  }
  personnelScopeMode.value = mode;
}

function isPickerRoleSelected(role: SystemRoleApi.Role) {
  return pickerMembers.value.some((member) => member.id === `role:${role.id}`);
}

function isPickerUserSelected(user: DepartmentScopeUserOption) {
  return pickerMembers.value.some(
    (member) => member.id === `user:${user.userId}`,
  );
}

function togglePickerUser(user: DepartmentScopeUserOption) {
  const id = `user:${user.userId}`;
  if (isPickerUserSelected(user)) {
    pickerMembers.value = pickerMembers.value.filter(
      (member) => member.id !== id,
    );
    return;
  }
  pickerMembers.value = [
    ...pickerMembers.value,
    { id, label: user.label, type: 'user' },
  ];
}

function togglePickerRole(role: SystemRoleApi.Role) {
  const id = `role:${role.id}`;
  if (isPickerRoleSelected(role)) {
    pickerMembers.value = pickerMembers.value.filter(
      (member) => member.id !== id,
    );
    return;
  }
  pickerMembers.value = [
    ...pickerMembers.value,
    { id, label: `${role.roleName}（${role.roleCode}）`, type: 'role' },
  ];
}

function clearLegacyPersonnelMembers() {
  for (const target of ['writers', 'reporters', 'cc', 'viewers'] as const) {
    draft.personnel[target] = draft.personnel[target].filter((member) =>
      /^(?:department|role|user):[1-9]\d*$/.test(member.id),
    );
  }
  draft.personnel.viewerScope = 'custom';
  message.info('已清理旧范围，请按系统角色、部门或人员重新选择');
}

function onDepartmentCheck(checkedKeys: unknown) {
  if (personnelScopeMode.value !== 'department') return;
  const rawKeys = Array.isArray(checkedKeys)
    ? checkedKeys
    : checkedKeys &&
        typeof checkedKeys === 'object' &&
        'checked' in checkedKeys &&
        Array.isArray(checkedKeys.checked)
      ? checkedKeys.checked
      : [];
  const nextKeys = rawKeys.filter(
    (key): key is string => typeof key === 'string',
  );
  pickerDepartmentIds.value = nextKeys;
  const nonDepartments = pickerMembers.value.filter(
    (member) => member.type !== 'department',
  );
  const departments = nextKeys
    .map((id) => findDepartment(id))
    .filter((department): department is DepartmentConfig => Boolean(department))
    .map((department) => ({
      id: `department:${department.id}`,
      label: `部门：${department.name}`,
      type: 'department' as const,
    }));
  pickerMembers.value = [...nonDepartments, ...departments];
}

function confirmPersonnelPicker() {
  draft.personnel[personnelTarget.value] = pickerMembers.value.map(
    (member) => ({
      ...member,
    }),
  );
  personnelPickerOpen.value = false;
}

function removePersonnel(target: PersonnelTarget, memberId: string) {
  draft.personnel[target] = selectedPersonnel(target).filter(
    (member) => member.id !== memberId,
  );
}

function copyRule(value: ReportRule) {
  Object.assign(draft, {
    ...value,
    fields: value.fields.map((field) => ({
      ...field,
      options: field.options?.map((option) => option),
    })),
    notificationChannels: { ...value.notificationChannels },
    schedule: {
      ...value.schedule,
      submissionDays: [...value.schedule.submissionDays],
    },
    personnel: {
      ...value.personnel,
      cc: value.personnel.cc.map((member) => ({ ...member })),
      reporters: value.personnel.reporters.map((member) => ({ ...member })),
      viewers: value.personnel.viewers.map((member) => ({ ...member })),
      writers: value.personnel.writers.map((member) => ({ ...member })),
    },
  });
  changeReportPeriod(draft.period);
}

function saveRules(nextRules: ReportRule[]) {
  return saveReportRules(mergeFixedDailyReportRules(nextRules));
}

function reportContentSummary(value: ReportRule) {
  if (isFixedDailyReportRule(value.id)) {
    return '前端固定表单填写；此处仅配置日报规则和其他信息';
  }

  return value.fields.map((field) => field.label).join('、');
}

function personnelTitle(members: ReportRuleMember[]) {
  return members.map((member) => member.label).join('、') || '未设置';
}

function openEditor(value = rule.value) {
  copyRule(value);
  showCreate.value = false;
  activeStep.value = 'content';
  editing.value = true;
}
function createBlankRule() {
  copyRule({ ...getDefaultReportRule(), id: `rule-${Date.now()}`, name: '' });
  draft.fields = [
    { id: `field-${Date.now()}`, label: '', required: false, type: 'text' },
  ];
  showCreate.value = false;
  editing.value = true;
}

function createRuleFromTemplate(
  template: (typeof dailyReportQuickTemplates)[number],
) {
  copyRule(createRuleFromDailyReportTemplate(template, getDefaultReportRule()));
  showCreate.value = false;
  activeStep.value = 'content';
  editing.value = true;
}
function addField() {
  draft.fields.push({
    id: `field-${Date.now()}`,
    label: '',
    required: false,
    type: 'text',
  });
}
function removeField(index: number) {
  if (draft.fields.length > 1) draft.fields.splice(index, 1);
}

function updateFieldType(field: ReportRule['fields'][number], value: unknown) {
  const type = value as ReportFieldType;
  field.type = type;
  if (isOptionField(type)) {
    if (!field.options?.length) field.options = ['选项一', '选项二'];
    return;
  }
  delete field.options;
}

function addFieldOption(field: ReportRule['fields'][number]) {
  const options = field.options ?? [];
  field.options = [...options, `选项${options.length + 1}`];
}

function removeFieldOption(field: ReportRule['fields'][number], index: number) {
  if ((field.options?.length ?? 0) <= 2) {
    message.warning('单选和多选字段至少需要保留两个选项');
    return;
  }
  field.options?.splice(index, 1);
}
async function saveRule() {
  if (!draft.name.trim()) {
    message.warning('请填写汇报名称');
    activeStep.value = 'content';
    return;
  }
  if (draft.fields.some((field) => !field.label.trim())) {
    message.warning('请填写所有汇报内容标题');
    activeStep.value = 'content';
    return;
  }
  const invalidOptionField = draft.fields.find((field) => {
    if (!isOptionField(field.type)) return false;
    const options = (field.options ?? []).map((option) => option.trim());
    return (
      options.length < 2 ||
      options.some((option) => !option) ||
      new Set(options).size !== options.length
    );
  });
  if (invalidOptionField) {
    message.warning(
      `请为“${invalidOptionField.label}”配置至少两个不重复的选项`,
    );
    activeStep.value = 'content';
    return;
  }
  if (
    legacyPersonnelMembers.value.length > 0 ||
    requiresViewerScopeMigration.value
  ) {
    activeStep.value = 'settings';
    message.warning('请先清理旧范围，并按系统角色、部门或人员重新选择');
    return;
  }
  if (draft.personnel.writers.length === 0) {
    activeStep.value = 'settings';
    message.warning('请按角色、部门或人员选择至少一名填写人');
    return;
  }
  if (draft.personnel.reporters.length === 0) {
    activeStep.value = 'settings';
    message.warning('请按角色、部门或人员选择至少一名汇报对象');
    return;
  }
  const saved = {
    ...draft,
    deadline: `${draft.schedule.deadlineTime} (${draft.schedule.timezone})`,
    name: draft.name.trim(),
    personnel: draft.personnel,
    fields: draft.fields.map((field) => ({
      ...field,
      label: field.label.trim(),
      options: isOptionField(field.type)
        ? (field.options ?? []).map((option) => option.trim())
        : undefined,
    })),
  };
  try {
    const persisted = await dailyReportApi.saveRule(saved);
    rules.value = saveRules([
      persisted,
      ...rules.value.filter((item) => item.id !== persisted.id),
    ]);
    editing.value = false;
    message.success('日报规则已保存，人员范围和提醒任务已同步到服务端');
    return;
  } catch {
    message.error('日报规则未能同步到服务端，未保存本地副本');
    return;
  }
}

function handleEditorPrimaryAction() {
  if (activeStep.value === 'content') {
    activeStep.value = 'settings';
    return;
  }
  saveRule();
}

async function duplicateRule(value: ReportRule) {
  if (isFixedDailyReportRule(value.id)) return;

  const duplicated: ReportRule = {
    ...value,
    fields: value.fields.map((field) => ({
      ...field,
      options: field.options?.map((option) => option),
    })),
    id: `rule-${Date.now()}`,
    name: `${value.name}（副本）`,
    notificationChannels: { ...value.notificationChannels },
    schedule: {
      ...value.schedule,
      submissionDays: [...value.schedule.submissionDays],
    },
    personnel: {
      cc: value.personnel.cc.map((member) => ({ ...member })),
      reporters: value.personnel.reporters.map((member) => ({ ...member })),
      viewers: value.personnel.viewers.map((member) => ({ ...member })),
      // 服务端仅接受明确的自定义查看范围；复制规则时必须保留该约束。
      viewerScope: value.personnel.viewerScope,
      writers: value.personnel.writers.map((member) => ({ ...member })),
    },
  };
  try {
    const persisted = await dailyReportApi.saveRule(duplicated);
    rules.value = saveRules([persisted, ...rules.value]);
    message.success('日报规则已复制并同步到服务端');
    return;
  } catch {
    message.error('日报规则复制失败，未保存本地副本');
    return;
  }
}

function deleteRule(value: ReportRule) {
  if (isFixedDailyReportRule(value.id)) {
    message.info('投放日报、绩效报表和素材师月报为固定配置，不允许删除');
    return;
  }

  Modal.confirm({
    content: `删除后将无法恢复“${value.name}”及其填写规则。`,
    okText: '删除',
    okType: 'danger',
    title: '确认删除汇报规则？',
    onOk: async () => {
      await dailyReportApi.deleteRule(value.id);
      rules.value = saveRules(
        rules.value.filter((item) => item.id !== value.id),
      );
      message.success('日报规则已删除');
      return;
    },
  });
}

onMounted(async () => {
  try {
    rules.value = saveRules(await dailyReportApi.listManagedRules());
  } catch {
    message.error('无法读取服务端日报规则，请检查日报管理权限');
  }
});
</script>

<template>
  <Page auto-content-height class="system-management-page report-rule-page">
    <div v-if="!editing" class="w-full p-3 md:p-4">
      <Card class="report-panel" :bordered="false">
        <div class="mb-8 flex items-center justify-between">
          <h1 class="m-0 text-[22px] font-semibold text-slate-900">我管理的</h1>
          <Button type="primary" @click="showCreate = true"
            ><IconifyIcon
              icon="lucide:plus"
              class="mr-1 size-5"
            />新增汇报规则</Button
          >
        </div>
        <div class="rule-list-head">
          <span>汇报名称</span><span>填写周期</span><span>提交人</span
          ><span>汇报人</span><span>抄送人</span><span>截止时间</span
          ><span>汇报内容</span><span class="text-center">操作</span>
        </div>
        <div v-for="item in rules" :key="item.id" class="rule-list-row">
          <div class="flex items-center gap-4">
            <span class="rule-icon"
              ><IconifyIcon :icon="reportIconName(item.icon)" /></span
            ><span>{{ item.name }}</span>
          </div>
          <span data-label="填写周期">{{ item.period }}</span>
          <div
            class="personnel-tags"
            data-label="提交人"
            :title="personnelTitle(item.personnel.writers)"
          >
            <span
              v-for="member in item.personnel.writers.slice(0, 2)"
              :key="member.id"
              class="personnel-tag"
              :title="member.label"
              >{{ member.label }}</span
            >
            <span
              v-if="item.personnel.writers.length > 2"
              class="personnel-tag-more"
              >+{{ item.personnel.writers.length - 2 }}</span
            >
            <span
              v-if="item.personnel.writers.length === 0"
              class="personnel-tag-empty"
              >-</span
            >
          </div>
          <div
            class="personnel-tags"
            data-label="汇报人"
            :title="personnelTitle(item.personnel.reporters)"
          >
            <span
              v-for="member in item.personnel.reporters.slice(0, 2)"
              :key="member.id"
              class="personnel-tag"
              :title="member.label"
              >{{ member.label }}</span
            >
            <span
              v-if="item.personnel.reporters.length > 2"
              class="personnel-tag-more"
              >+{{ item.personnel.reporters.length - 2 }}</span
            >
            <span
              v-if="item.personnel.reporters.length === 0"
              class="personnel-tag-empty"
              >-</span
            >
          </div>
          <div
            class="personnel-tags"
            data-label="抄送人"
            :title="personnelTitle(item.personnel.cc)"
          >
            <span
              v-for="member in item.personnel.cc.slice(0, 2)"
              :key="member.id"
              class="personnel-tag"
              :title="member.label"
              >{{ member.label }}</span
            >
            <span v-if="item.personnel.cc.length > 2" class="personnel-tag-more"
              >+{{ item.personnel.cc.length - 2 }}</span
            >
            <span
              v-if="item.personnel.cc.length === 0"
              class="personnel-tag-empty"
              >-</span
            >
          </div>
          <span data-label="截止时间">{{
            item.deadline === '次月 0 时 0 分' ? '-' : item.deadline
          }}</span
          ><Tooltip :title="reportContentSummary(item)">
            <span class="block truncate" data-label="汇报内容">{{
              reportContentSummary(item)
            }}</span>
          </Tooltip>
          <div class="flex justify-center gap-2 text-slate-500">
            <button
              aria-label="编辑汇报规则"
              class="icon-action"
              title="编辑"
              @click="openEditor(item)"
            >
              <IconifyIcon icon="lucide:square-pen" class="size-5" /></button
            ><button
              v-if="!isFixedDailyReportRule(item.id)"
              aria-label="复制汇报规则"
              class="icon-action"
              title="复制"
              @click="duplicateRule(item)"
            >
              <IconifyIcon icon="lucide:copy-plus" class="size-5" /></button
            ><span
              v-if="isFixedDailyReportRule(item.id)"
              class="fixed-rule-lock"
              title="固定日报配置不允许删除"
            >
              <IconifyIcon
                icon="lucide:lock-keyhole"
                class="size-4"
              />固定配置 </span
            ><button
              v-else
              aria-label="删除汇报规则"
              class="icon-action icon-action-danger"
              title="删除"
              @click="deleteRule(item)"
            >
              <IconifyIcon icon="lucide:trash-2" class="size-5" />
            </button>
          </div>
        </div>
      </Card>
      <Card class="report-panel mt-8" :bordered="false">
        <h2 class="mb-7 mt-0 text-[22px] font-semibold text-slate-900">
          消息设置
        </h2>
        <div class="notification-layout">
          <div class="notification-copy">
            <p>
              日报提交、催办和审批进度均由统一通知服务投递，站内消息与飞书必须同时发送。
            </p>
            <div class="notification-channel-list">
              <div>
                <span>系统消息通知</span>
                <Switch :checked="rule.notificationChannels.system" disabled />
              </div>
              <div>
                <span>飞书通知</span>
                <Switch :checked="rule.notificationChannels.feishu" disabled />
              </div>
            </div>
            <small> 通知渠道由系统统一保证，避免只收到单侧消息。 </small>
          </div>
          <div class="notification-preview" aria-hidden="true">
            <strong>小王的设计组日报</strong>
            <div class="notification-preview-meta">
              汇报日期：&nbsp;&nbsp;&nbsp;&nbsp;所属部门：
            </div>
            <div class="mb-3 text-slate-500">
              2月21日&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;设计组
            </div>
            <b>今日工作</b>
            <p>
              1.重点项目设计稿产出<br />2.讨论产品需求<br />3.项目工作计划整理
            </p>
            <span>查看详情</span>
          </div>
        </div>
      </Card>
    </div>

    <div v-else class="min-h-full">
      <header class="editor-header">
        <button class="flex items-center gap-2" @click="editing = false">
          <IconifyIcon icon="lucide:arrow-left" />返回</button
        ><span class="h-5 border-l border-slate-300"></span><b>创建汇报规则</b>
        <div class="editor-steps">
          <button
            :class="{ active: activeStep === 'content' }"
            @click="activeStep = 'content'"
          >
            内容设置</button
          ><IconifyIcon icon="lucide:chevron-right" /><button
            :class="{ active: activeStep === 'settings' }"
            @click="activeStep = 'settings'"
          >
            规则设置
          </button>
        </div>
        <Button type="primary" @click="handleEditorPrimaryAction">{{
          activeStep === 'content' ? '下一步' : '保存规则'
        }}</Button>
      </header>
      <main class="editor-canvas">
        <Alert
          v-if="legacyPersonnelMembers.length || requiresViewerScopeMigration"
          class="mb-4"
          message="人员范围需要迁移"
          show-icon
          type="warning"
        >
          <template #description>
            当前规则包含旧组织 ID
            或“所有人可看”范围，无法用于服务端授权。请清理后，按系统角色、部门或人员重新选择。
            <Button type="link" @click="clearLegacyPersonnelMembers"
              >清理旧范围</Button
            >
          </template>
        </Alert>
        <Card
          v-if="activeStep === 'content'"
          class="editor-card"
          :bordered="false"
          ><label>汇报名称<span class="required">*</span></label
          ><Input
            v-model:value="draft.name"
            class="mt-2"
            :disabled="isEditingFixedDailyReport"
            placeholder="请输入汇报名称"
            :maxlength="128"
            show-count
          /><label class="mt-7 block">汇报内容</label>
          <Alert
            v-if="isEditingFixedDailyReport"
            class="mt-2"
            show-icon
            type="info"
            message="前端固定表单填写"
            description="投放日报、绩效报表和素材师月报的字段与展示逻辑由前端业务代码固定维护；素材师月报固定按月，可配置每月提交日、人员范围、提醒和通知等规则。"
          />
          <template v-else>
            <template v-for="(field, index) in draft.fields" :key="field.id">
              <div class="field-row">
                <Input
                  v-model:value="field.label"
                  placeholder="请输入内容标题"
                  :maxlength="128"
                  show-count
                /><Select
                  :value="field.type"
                  :options="fieldTypes"
                  @update:value="updateFieldType(field, $event)"
                /><Checkbox v-model:checked="field.required">必填</Checkbox
                ><button class="round-icon" title="新增字段" @click="addField">
                  <IconifyIcon icon="lucide:plus" /></button
                ><button
                  class="round-icon"
                  :disabled="draft.fields.length === 1"
                  title="删除字段"
                  @click="removeField(index)"
                >
                  <IconifyIcon icon="lucide:minus" />
                </button>
              </div>
              <div v-if="isOptionField(field.type)" class="field-options">
                <div class="field-options-head">
                  <div>
                    <strong>选项配置</strong>
                    <span>填写页将按此顺序展示，至少保留两个不重复选项</span>
                  </div>
                  <Button type="link" @click="addFieldOption(field)">
                    <template #icon
                      ><IconifyIcon icon="lucide:plus"
                    /></template>
                    新增选项
                  </Button>
                </div>
                <div
                  v-for="(option, optionIndex) in field.options"
                  :key="`${field.id}-option-${optionIndex}`"
                  class="field-option-row"
                >
                  <label :for="`${field.id}-option-${optionIndex}`"
                    >选项 {{ optionIndex + 1 }}</label
                  >
                  <Input
                    :id="`${field.id}-option-${optionIndex}`"
                    v-model:value="field.options![optionIndex]"
                    :maxlength="128"
                    placeholder="请输入选项内容"
                  />
                  <button
                    class="option-remove"
                    type="button"
                    :aria-label="`删除选项 ${optionIndex + 1}`"
                    :title="`删除选项 ${optionIndex + 1}`"
                    @click="removeFieldOption(field, optionIndex)"
                  >
                    <IconifyIcon icon="lucide:trash-2" />
                  </button>
                </div>
              </div>
            </template>
          </template>
        </Card>
        <div v-else class="settings-stack">
          <Card class="editor-card" :bordered="false"
            ><h3>基础信息</h3>
            <label>汇报图标</label>
            <div
              class="report-icon-options mt-3"
              role="radiogroup"
              aria-label="选择汇报图标"
            >
              <button
                v-for="option in reportIconOptions"
                :key="option.icon"
                :aria-label="`选择${option.label}图标`"
                :aria-pressed="isReportIconSelected(option.icon)"
                :class="{ selected: isReportIconSelected(option.icon) }"
                class="icon-choice"
                type="button"
                :style="{ background: option.color }"
                @click="selectReportIcon(option.icon)"
              >
                <IconifyIcon :icon="reportIconName(option.icon)" />
              </button>
            </div>
            <label class="mt-7 block">时区</label
            ><Select
              v-model:value="draft.schedule.timezone"
              class="mt-2 w-full"
              :options="timezoneOptions"
            /><label class="mt-7 block"
              >谁可以管理这个规则<span class="required">*</span></label
            >
            <div class="mt-2">
              <span class="member-chip">创建人（所有者）</span>
              <span class="member-chip">系统管理员</span>
            </div></Card
          >
          <Card class="editor-card" :bordered="false">
            <h3>人员设置</h3>
            <section class="personnel-setting">
              <label>谁可以写<span class="required">*</span></label>
              <div class="personnel-picker-trigger mt-2">
                <button
                  class="round-icon"
                  title="选择填写人员"
                  type="button"
                  @click="openPersonnelPicker('writers')"
                >
                  <IconifyIcon icon="lucide:plus" />
                </button>
                <span
                  v-if="selectedPersonnel('writers').length === 0"
                  class="personnel-empty"
                  >{{ personnelTargetMeta.writers.empty }}</span
                >
                <button
                  v-for="member in selectedPersonnel('writers')"
                  :key="member.id"
                  class="member-chip member-chip-removable"
                  type="button"
                  :title="`移除${member.label}`"
                  @click="removePersonnel('writers', member.id)"
                >
                  <span class="member-chip-type"
                    >{{ personnelMemberTypeLabel(member.type) }}：</span
                  >
                  {{ member.label }} <IconifyIcon icon="lucide:x" />
                </button>
              </div>
            </section>
            <section class="personnel-setting">
              <label>汇报给谁<span class="required">*</span></label>
              <div class="personnel-picker-trigger mt-2">
                <button
                  class="round-icon"
                  type="button"
                  @click="openPersonnelPicker('reporters')"
                >
                  <IconifyIcon icon="lucide:plus" />
                </button>
                <span
                  v-if="selectedPersonnel('reporters').length === 0"
                  class="personnel-empty"
                  >{{ personnelTargetMeta.reporters.empty }}</span
                >
                <button
                  v-for="member in selectedPersonnel('reporters')"
                  :key="member.id"
                  class="member-chip member-chip-removable"
                  type="button"
                  :title="`移除${member.label}`"
                  @click="removePersonnel('reporters', member.id)"
                >
                  <span class="member-chip-type"
                    >{{ personnelMemberTypeLabel(member.type) }}：</span
                  >
                  {{ member.label }} <IconifyIcon icon="lucide:x" />
                </button>
              </div>
            </section>
            <section class="personnel-setting">
              <label>抄送给谁</label>
              <div class="personnel-picker-trigger mt-2">
                <button
                  class="round-icon"
                  type="button"
                  @click="openPersonnelPicker('cc')"
                >
                  <IconifyIcon icon="lucide:plus" />
                </button>
                <span
                  v-if="selectedPersonnel('cc').length === 0"
                  class="personnel-empty"
                  >{{ personnelTargetMeta.cc.empty }}</span
                >
                <button
                  v-for="member in selectedPersonnel('cc')"
                  :key="member.id"
                  class="member-chip member-chip-removable"
                  type="button"
                  :title="`移除${member.label}`"
                  @click="removePersonnel('cc', member.id)"
                >
                  <span class="member-chip-type"
                    >{{ personnelMemberTypeLabel(member.type) }}：</span
                  >
                  {{ member.label }} <IconifyIcon icon="lucide:x" />
                </button>
              </div>
            </section>
            <section class="personnel-setting">
              <label>谁可以看</label>
              <div class="personnel-picker-trigger mt-2">
                <button
                  class="round-icon"
                  type="button"
                  @click="openPersonnelPicker('viewers')"
                >
                  <IconifyIcon icon="lucide:plus" />
                </button>
                <span
                  v-if="selectedPersonnel('viewers').length === 0"
                  class="personnel-empty"
                  >{{ personnelTargetMeta.viewers.empty }}</span
                >
                <button
                  v-for="member in selectedPersonnel('viewers')"
                  :key="member.id"
                  class="member-chip member-chip-removable"
                  type="button"
                  :title="`移除${member.label}`"
                  @click="removePersonnel('viewers', member.id)"
                >
                  <span class="member-chip-type"
                    >{{ personnelMemberTypeLabel(member.type) }}：</span
                  >
                  {{ member.label }} <IconifyIcon icon="lucide:x" />
                </button>
              </div>
            </section>
          </Card>
          <Card class="editor-card" :bordered="false"
            ><div class="flex items-start justify-between">
              <div>
                <h3 class="mb-1">填写要求</h3>
                <p class="m-0 text-sm text-slate-400">
                  将根据填写要求统计提交情况
                </p>
              </div>
              <Switch :checked="true" />
            </div>
            <label class="mt-6 block"
              >填写周期<span class="required">*</span></label
            ><Radio.Group
              v-model:value="draft.period"
              :disabled="isEditingMaterialDesignerMonthlyReport"
              class="mt-3"
              @update:value="changeReportPeriod"
            >
              ><Radio value="每天">每天</Radio><Radio value="每周">每周</Radio
              ><Radio value="每双周">每双周</Radio
              ><Radio value="每月">每月</Radio
              ><Radio value="不重复">不重复</Radio></Radio.Group
            ><template v-if="draft.period === '每天'">
              <p class="schedule-helper">每天均可提交，无需再选择提交日期。</p>
            </template>
            <template
              v-else-if="draft.period === '每周' || draft.period === '每双周'"
            >
              <label class="mt-6 block"
                >{{ draft.period === '每周' ? '每周提交日' : '双周提交日'
                }}<span class="required">*</span></label
              >
              <Radio.Group v-model:value="submissionWeekday" class="mt-3">
                <Radio :value="1">周一</Radio><Radio :value="2">周二</Radio>
                <Radio :value="3">周三</Radio><Radio :value="4">周四</Radio>
                <Radio :value="5">周五</Radio><Radio :value="6">周六</Radio>
                <Radio :value="7">周日</Radio>
              </Radio.Group>
              <p v-if="draft.period === '每双周'" class="schedule-helper">
                按 ISO 偶数周的所选星期提交。
              </p>
            </template>
            <template v-else-if="draft.period === '每月'">
              <label class="mt-6 block"
                >每月提交日<span class="required">*</span></label
              >
              <Select
                v-model:value="draft.schedule.submissionDayOfMonth"
                class="mt-2 w-full"
                :options="monthDayOptions"
              />
              <p class="schedule-helper">
                {{
                  isEditingMaterialDesignerMonthlyReport
                    ? '素材师月报固定按月提交；仅提供 1 至 28 日，避免月末日期不存在。'
                    : '仅提供 1 至 28 日，避免月末日期不存在。'
                }}
              </p>
            </template>
            <template v-else>
              <p class="schedule-helper">
                不设置定期提交日期，需要时可手动填写。
              </p>
            </template>
            <label class="mt-6 block">开始时间</label
            ><Select
              v-model:value="draft.schedule.startTime"
              class="mt-2 w-full"
              :options="timeOptions" /><label class="mt-5 block">截止时间</label
            ><Select
              v-model:value="draft.schedule.deadlineTime"
              class="mt-2 w-full"
              :options="timeOptions"
          /></Card>
          <Card class="editor-card" :bordered="false"
            ><div class="flex items-center justify-between">
              <div>
                <h3 class="mb-1">自动提醒未提交的人</h3>
                <p class="m-0 text-sm text-slate-400">提醒时间</p>
              </div>
              <Switch v-model:checked="draft.reminderEnabled" />
            </div>
            <Select
              v-model:value="draft.schedule.reminderTime"
              class="mt-4 w-full"
              :disabled="!draft.reminderEnabled"
              :options="timeOptions"
          /></Card>
        </div>
      </main>
    </div>

    <Modal
      v-model:open="personnelPickerOpen"
      cancel-text="取消"
      ok-text="确认选择"
      :title="personnelTargetMeta[personnelTarget].title"
      :width="680"
      wrap-class-name="personnel-picker-modal"
      @ok="confirmPersonnelPicker"
    >
      <div class="organization-picker">
        <div class="organization-picker-head">
          <Input
            v-model:value="organizationKeyword"
            allow-clear
            placeholder="搜索人员、部门或角色"
          />
          <span>已选 {{ pickerMembers.length }} 项</span>
        </div>
        <Radio.Group
          :value="personnelScopeMode"
          class="organization-scope-mode"
          @update:value="updatePersonnelScopeMode"
        >
          <Radio value="role">按角色</Radio>
          <Radio value="department">按部门</Radio>
          <Radio value="user">按人员</Radio>
        </Radio.Group>
        <div class="organization-picker-body">
          <div v-if="organizationLoading" class="organization-state">
            正在加载系统组织数据…
          </div>
          <section
            v-else-if="personnelScopeMode === 'department'"
            class="organization-tree-panel"
          >
            <strong>组织架构</strong>
            <Tree
              checkable
              :checked-keys="pickerDepartmentIds"
              :tree-data="organizationTreeNodes"
              @check="onDepartmentCheck"
            />
          </section>
          <section
            v-else-if="personnelScopeMode === 'role'"
            class="organization-member-panel"
          >
            <strong>系统角色</strong>
            <div
              v-if="filteredOrganizationRoles.length"
              class="organization-member-list"
            >
              <Checkbox
                v-for="role in filteredOrganizationRoles"
                :key="role.id"
                :checked="isPickerRoleSelected(role)"
                @change="togglePickerRole(role)"
              >
                <span class="organization-member-name">{{
                  role.roleName
                }}</span>
                <span class="organization-member-department">{{
                  role.roleCode
                }}</span>
              </Checkbox>
            </div>
            <div v-else class="organization-state">未找到匹配的系统角色</div>
          </section>
          <section v-else class="organization-member-panel">
            <strong>人员</strong>
            <div
              v-if="filteredOrganizationUsers.length"
              class="organization-member-list"
            >
              <Checkbox
                v-for="user in filteredOrganizationUsers"
                :key="user.userId"
                :checked="isPickerUserSelected(user)"
                :disabled="!user.available"
                @change="togglePickerUser(user)"
              >
                <span class="organization-member-name">{{ user.name }}</span>
                <span
                  v-if="user.department"
                  class="organization-member-department"
                  >{{ user.department }}</span
                >
              </Checkbox>
            </div>
            <div v-else class="organization-state">未找到匹配的人员</div>
          </section>
        </div>
        <div v-if="pickerMembers.length" class="organization-selected">
          <span>已选：</span>
          <span
            v-for="member in pickerMembers"
            :key="member.id"
            class="member-chip"
            ><span class="member-chip-type"
              >{{ personnelMemberTypeLabel(member.type) }}：</span
            >{{ member.label }}</span
          >
        </div>
      </div>
    </Modal>

    <Modal
      v-model:open="showCreate"
      :footer="null"
      :width="920"
      centered
      title="创建规则"
      wrap-class-name="rule-create-modal"
      ><Button type="primary" @click="createBlankRule">新建空白规则</Button>
      <h3 class="mt-8 text-slate-400">快速创建</h3>
      <div class="grid grid-cols-2 gap-4">
        <button
          v-for="template in dailyReportQuickTemplates"
          :key="template.name"
          class="quick-template"
          type="button"
          @click="createRuleFromTemplate(template)"
        >
          <span class="rule-icon"
            ><IconifyIcon :icon="reportIconName(template.icon)" /></span
          ><span
            ><b>{{ template.name }}</b
            ><small>{{ template.description }}</small></span
          >
        </button>
      </div></Modal
    >
  </Page>
</template>

<style scoped>
.report-rule-page {
  background: hsl(var(--background));
}
.report-panel {
  border: 1px solid #dfe3e8;
  border-radius: 10px;
  box-shadow: 0 8px 22px rgb(15 23 42 / 4%);
}
.rule-list-head,
.rule-list-row {
  display: grid;
  grid-template-columns: 1.05fr 0.55fr repeat(3, 0.85fr) 0.7fr 0.75fr 116px;
}
.rule-list-head {
  border-bottom: 1px solid #f0f1f3;
  padding-bottom: 16px;
  color: #6c7581;
  font-size: 16px;
}
.rule-list-row {
  align-items: center;
  padding: 30px 0;
  color: #303743;
  font-size: 18px;
}
.rule-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #7c3aed;
  color: white;
  font-weight: 700;
  font-size: 16px;
}
.icon-action {
  color: #687280;
  transition: color 0.15s;
}
.icon-action:hover {
  color: #356dff;
}
.personnel-tags {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.personnel-tag,
.personnel-tag-more,
.personnel-tag-empty {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  line-height: 18px;
}
.personnel-tag {
  overflow: hidden;
  background: #f1f5f9;
  color: #475569;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.personnel-tag-more {
  background: #eef2ff;
  color: #4f46e5;
}
.personnel-tag-empty {
  padding: 0;
  color: #94a3b8;
}
.editor-header {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  height: 56px;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid #e5e7eb;
  background: white;
  padding: 0 26px;
  color: #303743;
}
.editor-header > :last-child {
  margin-left: auto;
}
.editor-steps {
  position: absolute;
  left: 50%;
  display: flex;
  transform: translateX(-50%);
  align-items: center;
  gap: 15px;
  color: #a0a7b2;
}
.editor-steps .active {
  color: #356dff;
  font-weight: 600;
}
.editor-canvas {
  min-height: 100%;
  padding: 28px;
  background: #f4f5f7;
}
.editor-card {
  width: min(786px, 100%);
  margin: 0 auto;
  border-radius: 10px;
  box-shadow: 0 8px 22px rgb(15 23 42 / 5%);
}
.editor-card label {
  color: #3b4350;
  font-size: 15px;
}
.required {
  margin-left: 2px;
  color: #ff4d4f;
}
.field-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 154px 78px 28px 28px;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.field-options {
  margin: 10px 0 20px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fafcff;
  padding: 12px;
}
.field-options-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.field-options-head strong {
  display: block;
  color: #334155;
  font-size: 14px;
  font-weight: 600;
}
.field-options-head span {
  display: block;
  margin-top: 2px;
  color: #94a3b8;
  font-size: 12px;
}
.field-option-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) 32px;
  align-items: center;
  gap: 8px;
}
.field-option-row + .field-option-row {
  margin-top: 8px;
}
.field-option-row label {
  color: #64748b;
  font-size: 13px;
}
.option-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #94a3b8;
}
.option-remove:hover {
  background: #fff1f0;
  color: #ff4d4f;
}
.round-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid #d5dae2;
  border-radius: 50%;
  color: #697586;
}
.round-icon:disabled {
  opacity: 0.4;
}
.settings-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.settings-stack .editor-card {
  width: min(650px, 100%);
}
.settings-stack h3 {
  margin: 0 0 22px;
  color: #303743;
  font-size: 17px;
  font-weight: 600;
}
.icon-choice {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 2px solid transparent;
  border-radius: 50%;
  color: white;
  cursor: pointer;
  transition:
    box-shadow 150ms ease,
    transform 150ms ease;
}
.icon-choice:hover {
  transform: translateY(-1px);
}
.icon-choice:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}
.icon-choice.selected {
  border-color: #fff;
  box-shadow: 0 0 0 2px #2563eb;
}
.report-icon-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.schedule-helper {
  margin: 10px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}
.member-chip {
  display: inline-flex;
  margin-right: 6px;
  border-radius: 14px;
  background: #f1f3f5;
  padding: 4px 10px;
  font-size: 13px;
  color: #515b69;
}
.template-recent,
.quick-template {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 14px;
  border-radius: 8px;
  background: #f6f7f9;
  padding: 16px 20px;
  text-align: left;
}
.template-recent {
  max-width: 400px;
}
.template-recent:hover,
.quick-template:hover {
  background: #edf3ff;
}
.template-recent b,
.quick-template b {
  display: block;
  font-size: 18px;
  color: #303743;
}
.template-recent small,
.quick-template small {
  display: block;
  margin-top: 4px;
  color: #7a8491;
  font-size: 14px;
}
@media (max-width: 860px) {
  .rule-list-head,
  .rule-list-row {
    font-size: 13px;
  }
  .rule-list-head {
    display: none;
  }
  .rule-list-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 16px;
    padding: 16px 12px;
  }
  .rule-list-row > :first-child,
  .rule-list-row > :last-child {
    grid-column: 1 / -1;
  }
  .rule-list-row > :not(:first-child):not(:last-child) {
    display: flex;
    min-width: 0;
    align-items: center;
    gap: 6px;
  }
  .rule-list-row > :not(:first-child):not(:last-child)::before {
    flex: none;
    color: #737373;
    content: attr(data-label);
  }
  .rule-list-row > :last-child {
    justify-content: flex-end;
  }
  .field-row {
    grid-template-columns: 1fr 130px 66px 28px 28px;
    gap: 7px;
  }
  .field-option-row {
    grid-template-columns: 48px minmax(0, 1fr) 32px;
  }
  .editor-steps {
    display: none;
  }
}
.personnel-setting + .personnel-setting {
  margin-top: 28px;
}
.personnel-hint {
  margin: 8px 0 0;
  color: #94a3b8;
  font-size: 13px;
}
.personnel-picker-trigger {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 30px;
}
.personnel-empty {
  color: #94a3b8;
  font-size: 13px;
}
.member-chip-removable {
  align-items: center;
  border: 0;
  cursor: pointer;
  gap: 4px;
}
.member-chip-removable:hover {
  background: #e2e8f0;
  color: #2563eb;
}
.member-chip-type {
  color: #94a3b8;
  font-size: 12px;
}
.organization-picker {
  display: grid;
  gap: 14px;
  grid-template-rows: auto auto minmax(0, 190px) auto;
  max-height: min(70vh, 620px);
}
.organization-picker-head {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #64748b;
  font-size: 13px;
}
.organization-picker-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.organization-scope-mode {
  display: flex;
  gap: 18px;
  margin: 14px 0;
}
.organization-tree-panel,
.organization-member-panel {
  display: flex;
  min-height: 0;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
}
.organization-tree-panel {
  background: #fafcff;
}
.organization-member-list {
  display: grid;
  gap: 4px;
  min-height: 0;
  overflow: auto;
}
.organization-member-name {
  color: #334155;
}
.organization-member-department {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 12px;
}
.organization-state {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 13px;
}
.organization-selected {
  display: flex;
  max-height: 76px;
  flex-wrap: wrap;
  align-items: center;
  align-content: flex-start;
  gap: 4px;
  overflow-y: auto;
  border-radius: 7px;
  background: #f8fafc;
  padding: 8px 10px;
  color: #64748b;
  font-size: 13px;
}
@media (max-width: 640px) {
  .organization-picker {
    grid-template-rows: auto auto minmax(0, 170px) auto;
    max-height: 72vh;
  }
  .organization-picker-body {
    grid-template-columns: 1fr;
  }
  .organization-tree-panel {
    max-height: 180px;
    border-right: 0;
    border-bottom: 1px solid #e2e8f0;
  }
  .organization-picker-head {
    align-items: stretch;
    flex-direction: column;
    gap: 6px;
  }
}

/* 日报配置使用中性表面与紧凑层级，避免高饱和色和漂浮阴影分散注意力。 */
.report-rule-page :deep(.vben-page),
.editor-canvas {
  background: #fafafa;
}
.report-panel,
.editor-card {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow: none;
}
.rule-list-head {
  padding: 0 12px 12px;
  border-bottom-color: hsl(var(--border));
  color: #737373;
  font-size: 13px;
  font-weight: 500;
}
.rule-list-row {
  min-height: 76px;
  padding: 14px 12px;
  border-bottom: 1px solid #f0f0f0;
  color: #262626;
  font-size: 14px;
  transition: background-color 150ms ease;
}
.rule-list-row:last-child {
  border-bottom: 0;
}
.rule-list-row:hover {
  background: #fafafa;
}
.rule-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  border: 1px solid hsl(var(--primary) / 18%);
  background: hsl(var(--primary) / 10%);
  color: hsl(var(--primary));
  font-size: 13px;
}
.icon-action {
  display: inline-flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #525252;
  transition:
    background-color 150ms ease,
    color 150ms ease;
}
.icon-action:hover {
  background: #ededed;
  color: #171717;
}
.icon-action-danger:hover {
  background: #fef2f2;
  color: #b91c1c;
}
.fixed-rule-lock {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  gap: 4px;
  border-radius: 8px;
  background: #f5f5f5;
  padding: 0 10px;
  color: #525252;
  font-size: 12px;
  white-space: nowrap;
}
.notification-layout {
  display: grid;
  max-width: 720px;
  grid-template-columns: minmax(0, 1fr) 238px;
  gap: 28px;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  background: #fcfcfc;
  padding: 20px;
}
.notification-copy p {
  margin: 0;
  color: #525252;
  font-size: 14px;
  line-height: 1.65;
}
.notification-channel-list {
  display: grid;
  gap: 12px;
  margin-top: 20px;
}
.notification-channel-list > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #e5e5e5;
  padding-top: 12px;
  color: #262626;
  font-size: 14px;
  font-weight: 500;
}
.notification-copy small {
  display: block;
  margin-top: 14px;
  color: #737373;
  font-size: 12px;
}
.notification-preview {
  border: 1px solid #e5e5e5;
  border-radius: 9px;
  background: #fff;
  padding: 16px;
  color: #525252;
  font-size: 12px;
  line-height: 1.65;
}
.notification-preview strong {
  display: block;
  margin-bottom: 12px;
  color: #171717;
  font-size: 14px;
}
.notification-preview-meta,
.notification-preview span {
  color: #737373;
}
.notification-preview p {
  margin: 4px 0 10px;
}
.notification-preview span {
  display: block;
  border-top: 1px solid #e5e5e5;
  padding-top: 10px;
}
.editor-header {
  border-bottom-color: hsl(var(--border));
  background: hsl(var(--background));
  color: #262626;
}
.editor-steps {
  color: #737373;
}
.editor-steps .active {
  color: #171717;
}
.editor-card label,
.settings-stack h3 {
  color: #262626;
}
.field-options,
.organization-tree-panel,
.organization-selected {
  border-color: #e5e5e5;
  background: #fafafa;
}
.round-icon {
  border-color: #d4d4d4;
  border-radius: 8px;
  color: #525252;
}
.member-chip {
  background: #f5f5f5;
  color: #525252;
}
.template-recent,
.quick-template {
  border: 1px solid #e5e5e5;
  background: #fff;
}
.template-recent:hover,
.quick-template:hover {
  background: #fafafa;
}
.template-recent b,
.quick-template b {
  color: #262626;
  font-size: 15px;
}
.template-recent small,
.quick-template small,
.personnel-empty,
.organization-member-department,
.organization-state {
  color: #737373;
}
@media (max-width: 640px) {
  .notification-layout {
    grid-template-columns: 1fr;
  }
}
</style>
