<script lang="ts" setup>
import type {
  AdjustAction,
  AutomationRule,
  Branch,
  ConditionOperator,
  MediaBuyer,
  PlatformConfig,
  RuleAction,
  RuleCondition,
  RuleLevel,
  RuleOptions,
  RulePayload,
  StatusAction,
} from '#/api/advertisement/automated-rule';

import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useTabs } from '@vben/hooks';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  DatePicker,
  Input,
  InputNumber,
  message,
  Radio,
  Select,
  Tag,
  TimePicker,
} from 'ant-design-vue';

import {
  createRule,
  getMediaBuyers,
  getOptions,
  getPlatformConfigs,
  getRule,
  updateRule,
} from '#/api/advertisement/automated-rule';

const route = useRoute();
const router = useRouter();
const { closeTabByKey } = useTabs();

const ruleId = computed(() => route.query.id as string | undefined);
const isEdit = computed(() => !!ruleId.value);
const isReadonly = computed(() => route.query.readonly === '1');
const loading = ref(false);
const submitting = ref(false);

// ── 动态选项（来自 /options 接口） ──────────────────────────
const options = ref<RuleOptions>({
  actions: [],
  adjust_directions: [],
  adjust_units: [],
  frequencies: [],
  levels: [],
  metrics: [],
  notification_channels: [],
  operators: [],
  status_values: [],
  time_windows: [],
  timezones: [],
});

const metricOptions = computed(() =>
  options.value.metrics.map((m) => ({ label: m.name, value: m.code })),
);

function branchMetricOptions(_bIdx: number, _cIdx: number) {
  return metricOptions.value;
}
const operatorOptions = computed(() =>
  options.value.operators.map((o) => ({ label: o.name, value: o.code })),
);
const timeWindowOptions = computed(() =>
  options.value.time_windows.map((t) => ({ label: t.name, value: t.code })),
);
const actionTypeOptions = computed(() =>
  options.value.actions.map((a) => ({ label: a.name, value: a.code })),
);
const statusValueOptions = computed(() =>
  options.value.status_values.map((s) => ({ label: s.name, value: s.code })),
);
const directionOptions = computed(() =>
  options.value.adjust_directions.map((d) => ({
    label: d.name,
    value: d.code,
  })),
);
const unitOptions = computed(() =>
  options.value.adjust_units.map((u: { name: string; code: string }) => ({
    label: u.name,
    value: u.code,
  })),
);
/** direction 为"改为"时，过滤掉百分比 */
function getUnitOptions(direction: string | undefined) {
  if (direction === 'set') {
    return unitOptions.value.filter(
      (u: { label: string; value: string }) => u.value !== 'percent',
    );
  }
  return unitOptions.value;
}
const notificationChannelOptions = computed(() =>
  options.value.notification_channels.map((c) => ({
    label: c.name,
    value: c.code,
  })),
);
const timezoneOptions = computed(() =>
  options.value.timezones.map((t) => ({ label: t.name, value: t.code })),
);
const frequencyOptions = computed(() => options.value.frequencies);
const levelOptions = computed(() =>
  options.value.levels.map((l) => ({ label: l.name, value: l.code })),
);
const limitTypeOptions = [
  { label: '不低于', value: 'min' },
  { label: '不超过', value: 'max' },
];

// ── 项目 / 平台配置 ────────────────────────────────────────
const platformConfigs = ref<PlatformConfig[]>([]);
const projectOptions = computed(() =>
  platformConfigs.value.map((c) => ({ label: c.name, value: c.id })),
);

const mediaBuyerList = ref<MediaBuyer[]>([]);
const mediaBuyerOptions = computed(() =>
  mediaBuyerList.value.map((m) => ({ label: m.real_name, value: m.real_name })),
);

// ── 表单状态 ──────────────────────────────────────────────
interface ConditionForm {
  logic: 'AND' | 'OR';
  metric: string | undefined;
  operator: ConditionOperator | undefined;
  time_window: string | undefined;
  value: null | number;
  value_max: null | number;
  value_min: null | number;
}

interface ActionForm {
  action_type: string | undefined;
  direction: string | undefined;
  limit_type: string | undefined;
  limit_value: null | number;
  status: string | undefined;
  unit: string | undefined;
  value: null | number;
}

interface BranchForm {
  actions: ActionForm[];
  branch_name: string;
  condition_expression: string;
  condition_logic: 'AND' | 'OR';
  conditions: ConditionForm[];
}

function emptyCondition(logic: 'AND' | 'OR' = 'AND'): ConditionForm {
  return {
    logic,
    metric: undefined,
    time_window: undefined,
    operator: undefined,
    value: null,
    value_min: null,
    value_max: null,
  };
}
function emptyAction(): ActionForm {
  return {
    action_type: undefined,
    status: undefined,
    direction: undefined,
    unit: 'fixed',
    value: null,
    limit_type: undefined,
    limit_value: null,
  };
}
function emptyBranch(name = '分支1'): BranchForm {
  return {
    branch_name: name,
    condition_expression: '',
    condition_logic: 'AND',
    conditions: [emptyCondition()],
    actions: [emptyAction()],
  };
}

const form = reactive({
  rule_name: '',
  auto_execute: false,
  enabled: false,
  project_ids: [] as string[],
  media_buyer: '',
  account_id: '',
  account_name: '',
  campaign_id: '',
  campaign_name: '',
  levels: 'campaign' as string,
  agent_line: '',
  branches: [emptyBranch()] as BranchForm[],
  notification: {
    channel: 'none',
    target_mode: 'group' as 'group' | 'private',
    target_id_type: 'mobile' as string,
    target: '',
    mention_user: '',
  },
  schedule: {
    timezone: 'UTC+8',
    effective_type: 'long_term' as 'custom' | 'long_term',
    effective_ranges: ['', ''] as [string, string],
    frequency: 'half_hour' as string,
    custom_cron: '' as string,
    custom_check_times: [] as string[],
    daily_check_times: [] as string[],
  },
});

const MAX_CONDITIONS = 5;
const MAX_BRANCHES = 2;

function onProjectIdsChange(v: any) {
  form.project_ids = v ?? [];
}

// ── 分支操作 ─────────────────────────────────────────────
function addBranch() {
  if (form.branches.length >= MAX_BRANCHES) return;
  form.branches.push(emptyBranch(`分支${form.branches.length + 1}`));
}

function removeBranch(bIdx: number) {
  if (form.branches.length > 1) form.branches.splice(bIdx, 1);
}

function addCondition(bIdx: number) {
  const b = form.branches[bIdx];
  if (!b || b.conditions.length >= MAX_CONDITIONS) return;
  b.conditions.push(emptyCondition());
}

function removeCondition(bIdx: number, cIdx: number) {
  const b = form.branches[bIdx];
  if (!b || b.conditions.length <= 1) return;
  b.conditions.splice(cIdx, 1);
}

// ── 判断 operator 是否为 between ──────────────────────────
function isBetween(operator: ConditionOperator | string) {
  return operator === 'between';
}

// ── 自定义生效时段 ─────────────────────────────────────────
function onRangeChange(_: any, dateStrings: [string, string]) {
  form.schedule.effective_ranges = dateStrings;
}

const newCheckTime = ref<string | undefined>(undefined);

function addCheckTime() {
  if (!newCheckTime.value) return;
  if (form.schedule.custom_check_times.includes(newCheckTime.value)) {
    message.warning('该时间已存在');
    return;
  }
  form.schedule.custom_check_times.push(newCheckTime.value);
  newCheckTime.value = undefined;
}

function removeCheckTime(t: string) {
  const idx = form.schedule.custom_check_times.indexOf(t);
  if (idx !== -1) form.schedule.custom_check_times.splice(idx, 1);
}

const newDailyCheckTime = ref<string | undefined>(undefined);
const dailyTimePickerKey = ref(0);
const batchStartHour = ref<string | undefined>(undefined);
const batchEndHour = ref<string | undefined>(undefined);

function addDailyCheckTime() {
  if (!newDailyCheckTime.value) return;
  if (form.schedule.daily_check_times.includes(newDailyCheckTime.value)) {
    message.warning('该时间已存在');
  } else {
    form.schedule.daily_check_times.push(newDailyCheckTime.value);
  }
  newDailyCheckTime.value = undefined;
  dailyTimePickerKey.value++;
}

function addBatchDailyCheckTimes() {
  if (!batchStartHour.value || !batchEndHour.value) {
    message.warning('请选择起止时间');
    return;
  }
  const start = Number.parseInt(batchStartHour.value.slice(0, 2), 10);
  const end = Number.parseInt(batchEndHour.value.slice(0, 2), 10);
  if (start > end) {
    message.warning('起始时间不能晚于结束时间');
    return;
  }
  let added = 0;
  for (let h = start; h <= end; h++) {
    const t = `${String(h).padStart(2, '0')}:00`;
    if (!form.schedule.daily_check_times.includes(t)) {
      if (form.schedule.daily_check_times.length >= 24) break;
      form.schedule.daily_check_times.push(t);
      added++;
    }
  }
  if (added === 0) message.warning('所选时间段内时间均已存在');
  batchStartHour.value = undefined;
  batchEndHour.value = undefined;
}

function removeDailyCheckTime(t: string) {
  const idx = form.schedule.daily_check_times.indexOf(t);
  if (idx !== -1) form.schedule.daily_check_times.splice(idx, 1);
}

// ── 加载编辑数据 ──────────────────────────────────────────
async function fillForm(rule: AutomationRule) {
  form.rule_name = rule.rule_name;
  form.auto_execute = rule.auto_execute ?? false;
  form.enabled = rule.enabled;
  form.project_ids = rule.project_ids?.length
    ? rule.project_ids
    : rule.project_id
      ? [rule.project_id]
      : [];
  form.agent_line = rule.agent_line;
  form.media_buyer = rule.media_buyer;
  form.account_id = rule.account_id;
  form.account_name = rule.account_name || '';
  form.campaign_id = rule.campaign_id || '';
  form.campaign_name = rule.campaign_name || '';
  function mapAction(a: RuleAction): ActionForm {
    if (a.action_type === 'status') {
      const sa = a as StatusAction;
      return {
        action_type: sa.action_type,
        status: sa.status,
        direction: undefined,
        unit: 'fixed',
        value: null,
        limit_type: undefined,
        limit_value: null,
      };
    }
    const aa = a as AdjustAction;
    return {
      action_type: aa.action_type,
      status: undefined,
      direction: aa.direction,
      unit: aa.unit,
      value:
        aa.value != null
          ? aa.unit === 'fixed'
            ? aa.value / 100
            : aa.value
          : null,
      limit_type: aa.limit_type,
      limit_value: aa.limit_value ?? null,
    };
  }

  if ((rule.branches?.length ?? 0) > 0) {
    form.branches = rule.branches!.map((b) => ({
      branch_name: b.branch_name,
      condition_expression: b.condition_expression || '',
      condition_logic: b.condition_logic || 'AND',
      conditions:
        b.conditions?.length > 0
          ? b.conditions.map((c, i) => ({
              logic: (i === 0 ? 'AND' : b.condition_logic || 'AND') as
                | 'AND'
                | 'OR',
              metric: c.metric,
              time_window: c.time_window,
              operator: c.operator,
              value: c.value,
              value_min: c.value_min,
              value_max: c.value_max,
            }))
          : [emptyCondition()],
      actions:
        b.actions?.length > 0
          ? b.actions.map((a) => mapAction(a))
          : [emptyAction()],
    }));
  } else {
    const logic = rule.condition_logic || 'AND';
    const conditions: ConditionForm[] =
      rule.conditions?.length > 0
        ? rule.conditions.map((c, i) => ({
            logic: (i === 0 ? 'AND' : logic) as 'AND' | 'OR',
            metric: c.metric,
            time_window: c.time_window,
            operator: c.operator,
            value: c.value,
            value_min: c.value_min,
            value_max: c.value_max,
          }))
        : [emptyCondition()];
    const actions: ActionForm[] =
      rule.actions?.length > 0
        ? rule.actions.map((a) => mapAction(a))
        : [emptyAction()];
    form.branches = [
      {
        branch_name: '分支1',
        condition_expression: '',
        condition_logic: rule.condition_logic || 'AND',
        conditions,
        actions,
      },
    ];
  }

  form.levels = rule.levels?.[0] || 'campaign';

  (() => {
    const notif = (rule.notification || {}) as any;
    const channel = notif.channel || 'none';
    let target_mode: 'group' | 'private' = notif.target_mode || 'group';
    let target_id_type: string = notif.target_id_type || 'mobile';
    let target: string = notif.target || '';
    // 无论新旧格式，统一从 target 中剥离 "prefix:" 前缀
    if (target) {
      const m = target.match(/^(chat_id|mobile|email|open_id|user_id):(.*)$/);
      if (m) {
        const prefix = m[1]!;
        target = m[2]!;
        if (!notif.target_mode) {
          if (prefix === 'chat_id') {
            target_mode = 'group';
            target_id_type = 'chat_id';
          } else {
            target_mode = 'private';
            target_id_type = prefix;
          }
        }
      }
    }
    form.notification = {
      channel,
      target_mode,
      target_id_type,
      target,
      mention_user: notif.mention_user || '',
    };
  })();

  form.schedule = {
    timezone: rule.schedule?.timezone || 'UTC+8',
    effective_type: rule.schedule?.effective_type || 'long_term',
    effective_ranges: (() => {
      const r = (rule.schedule?.effective_ranges || [])[0];
      return r
        ? ([r.start ?? r[0] ?? '', r.end ?? r[1] ?? ''] as [string, string])
        : ['', ''];
    })(),
    frequency: rule.schedule?.frequency || 'half_hour',
    custom_cron: rule.schedule?.custom_cron || '',
    custom_check_times: (rule.schedule as any)?.custom_check_times ?? [],
    daily_check_times: (rule.schedule as any)?.daily_check_times ?? [],
  };
}

onMounted(async () => {
  loading.value = true;
  try {
    const [opts, configs, buyers] = await Promise.all([
      getOptions(),
      getPlatformConfigs(),
      getMediaBuyers(),
    ]);
    options.value = opts;
    platformConfigs.value = configs;
    mediaBuyerList.value = buyers;

    if (ruleId.value) {
      const rule = await getRule(ruleId.value);
      fillForm(rule);
    }
  } finally {
    loading.value = false;
  }
});

// ── 提交 ──────────────────────────────────────────────────
async function handleSubmit() {
  if (!form.rule_name.trim()) {
    message.warning('请输入规则名称');
    return;
  }
  if (!form.project_ids.length) {
    message.warning('请选择项目');
    return;
  }
  if (!form.media_buyer) {
    message.warning('请选择投放师');
    return;
  }

  for (const b of form.branches) {
    if (b.conditions.some((c) => !c.metric || !c.time_window || !c.operator)) {
      message.warning(`分支「${b.branch_name}」请完善执行条件`);
      return;
    }
    const condKeys = b.conditions.map(
      (c) => `${c.metric}|${c.time_window}|${c.operator}`,
    );
    if (new Set(condKeys).size !== condKeys.length) {
      message.warning(
        `分支「${b.branch_name}」同一条件分支中不能存在数据指标、时间、指标范围完全相同的条件`,
      );
      return;
    }
    if (b.actions.some((a) => !a.action_type)) {
      message.warning(`分支「${b.branch_name}」请完善执行动作`);
      return;
    }
  }

  // 跨分支校验：不同分支不能存在数据指标、时间、指标范围同时相同的条件
  if (form.branches.length > 1) {
    for (let i = 0; i < form.branches.length; i++) {
      for (let j = i + 1; j < form.branches.length; j++) {
        const keysJ = new Set(
          form.branches[j]!.conditions.map(
            (c) => `${c.metric}|${c.time_window}|${c.operator}`,
          ),
        );
        const dup = form.branches[i]!.conditions.find((c) =>
          keysJ.has(`${c.metric}|${c.time_window}|${c.operator}`),
        );
        if (dup) {
          message.warning(
            `「${form.branches[i]!.branch_name}」与「${form.branches[j]!.branch_name}」存在数据指标、时间、指标范围完全相同的条件`,
          );
          return;
        }
      }
    }
  }

  // 跨分支校验：不同分支的执行动作不能完全相同
  if (form.branches.length > 1) {
    function actionKey(a: ActionForm) {
      return a.action_type === 'status'
        ? `status:${a.status}`
        : `budget:${a.direction}:${a.unit}:${a.value}:${a.limit_type}:${a.limit_value}`;
    }
    const actionKeys = form.branches.map((b) =>
      b.actions
        .map((a) => actionKey(a))
        .sort()
        .join(','),
    );
    for (let i = 0; i < actionKeys.length; i++) {
      for (let j = i + 1; j < actionKeys.length; j++) {
        if (actionKeys[i] === actionKeys[j]) {
          message.warning(
            `「${form.branches[i]!.branch_name}」与「${form.branches[j]!.branch_name}」的执行动作不能完全相同`,
          );
          return;
        }
      }
    }
  }

  if (form.notification.channel !== 'none') {
    if (!form.notification.target.trim()) {
      const hint =
        form.notification.target_mode === 'group'
          ? '请填写群 ID'
          : form.notification.target_id_type === 'email'
            ? '请填写邮箱'
            : '请填写手机号';
      message.warning(hint);
      return;
    }
  }

  function buildActions(acts: ActionForm[]): RuleAction[] {
    return acts.map((a) => {
      if (a.action_type === 'status') {
        return {
          action_type: 'status',
          status: a.status as 'active' | 'paused',
        } as StatusAction;
      }
      return {
        action_type: 'daily_budget',
        direction: a.direction as any,
        unit: a.unit as any,
        value: a.unit === 'fixed' ? (a.value ?? 0) * 100 : (a.value ?? 0),
        limit_type: a.limit_type as 'max' | 'min',
        limit_value: a.limit_value ?? 0,
      } as AdjustAction;
    });
  }

  const branches: Branch[] = form.branches.map((b) => {
    const conditions: RuleCondition[] = b.conditions.map((c) => ({
      metric: c.metric ?? '',
      time_window: c.time_window as any,
      operator: c.operator as ConditionOperator,
      value: isBetween(c.operator ?? '') ? null : c.value,
      value_min: isBetween(c.operator ?? '') ? c.value_min : null,
      value_max: isBetween(c.operator ?? '') ? c.value_max : null,
    }));
    const condition_logic = (b.conditions[1]?.logic ?? b.condition_logic) as
      | 'AND'
      | 'OR';
    return {
      branch_name: b.branch_name,
      condition_expression: b.condition_expression,
      condition_logic,
      conditions,
      actions: buildActions(b.actions),
    };
  });

  const firstBranch = branches[0]!;

  const payload: RulePayload = {
    rule_name: form.rule_name.trim(),
    auto_execute: form.auto_execute,
    enabled: form.enabled,
    project_ids: form.project_ids,
    media_buyer: form.media_buyer,
    agent_line: form.agent_line,
    account_id: form.account_id,
    account_name: form.account_name,
    campaign_id: form.campaign_id,
    campaign_name: form.campaign_name,
    levels: [form.levels as RuleLevel],
    target_scope: {
      campaign_ids: form.campaign_id ? [form.campaign_id] : [],
      adset_ids: [],
      ad_ids: [],
    },
    conditions: firstBranch.conditions,
    condition_logic: firstBranch.condition_logic,
    actions: firstBranch.actions,
    branches,
    notification: (() => {
      const { channel, target_mode, target_id_type, target, mention_user } =
        form.notification;
      if (channel === 'none') {
        return { channel: channel as any, target: '', mention_user: undefined };
      }
      const idType = target_mode === 'group' ? 'chat_id' : target_id_type;
      return {
        channel: channel as any,
        target_mode,
        target_id_type: idType,
        target: `${idType}:${target}`,
        mention_user:
          target_mode === 'group' ? mention_user || undefined : undefined,
      };
    })(),
    schedule: {
      timezone: form.schedule.timezone,
      effective_type: form.schedule.effective_type,
      effective_ranges:
        form.schedule.effective_ranges[0] && form.schedule.effective_ranges[1]
          ? [
              {
                end: form.schedule.effective_ranges[1],
                start: form.schedule.effective_ranges[0],
              },
            ]
          : [],
      frequency: form.schedule.frequency as any,
      custom_cron: null,
      custom_check_times:
        form.schedule.frequency === 'custom'
          ? form.schedule.custom_check_times
          : [],
      daily_check_times:
        form.schedule.frequency === 'daily_times'
          ? form.schedule.daily_check_times
          : [],
    },
  };

  submitting.value = true;
  try {
    if (isEdit.value) {
      await updateRule(ruleId.value!, payload);
      message.success('保存成功');
    } else {
      await createRule(payload);
      message.success('创建成功');
    }
    const tabKey = encodeURIComponent(route.path);
    await router.push('/AutomatedRules');
    await closeTabByKey(tabKey);
  } catch (error: any) {
    const errors: string[] =
      error?.response?.data?.data?.errors ??
      error?.data?.errors ??
      error?.errors;
    if (errors?.length) {
      errors.forEach((e) => message.error(e));
    } else {
      const msg = error?.response?.data?.message ?? error?.message;
      if (msg) message.error(msg);
    }
  } finally {
    submitting.value = false;
  }
}

async function handleCancel() {
  const tabKey = encodeURIComponent(route.path);
  router.back();
  await closeTabByKey(tabKey);
}
</script>

<template>
  <div
    class="adpulse-section-page automated-rule-config-page flex min-h-full flex-col"
  >
    <!-- eslint-disable vue/html-closing-bracket-newline -->
    <!-- 顶部导航 -->
    <div
      class="rule-config-topbar sticky top-0 z-10 flex shrink-0 items-center border-b bg-white"
    >
      <Button
        type="text"
        class="flex items-center gap-0.5 !px-1 text-gray-600"
        @click="handleCancel"
      >
        <IconifyIcon icon="lucide:chevron-left" class="text-base" />
        <span>返回</span>
      </Button>
      <div class="h-4 w-px bg-gray-200"></div>
      <span class="text-sm font-medium text-gray-800">
        {{ isReadonly ? '规则详情' : isEdit ? '编辑规则' : '新建规则' }}
      </span>
    </div>

    <!-- 加载 -->
    <div
      v-if="loading"
      class="flex flex-1 items-center justify-center text-sm text-gray-400"
    >
      加载中…
    </div>

    <!-- 主体 -->
    <div
      v-else
      class="flex-1 overflow-auto"
      :class="{ 'readonly-mode': isReadonly }"
    >
      <div class="rule-config-content w-full min-w-0">
        <!-- ── 基本设置 ── -->
        <Card title="基本设置">
          <div class="grid grid-cols-1 gap-x-10 gap-y-4 lg:grid-cols-2">
            <div class="form-row">
              <label class="form-label"
                >规则名称 <span class="text-red-500">*</span></label
              >
              <Input
                v-model:value="form.rule_name"
                :disabled="isReadonly"
                :maxlength="50"
                class="flex-1"
                placeholder="请输入规则名称"
                show-count
              />
            </div>
            <div class="form-row">
              <label class="form-label"
                >平台 <span class="text-red-500">*</span></label
              >
              <Select
                :value="form.project_ids"
                :disabled="isReadonly"
                :options="projectOptions"
                mode="multiple"
                allow-clear
                show-search
                class="flex-1"
                placeholder="请选择项目"
                max-tag-count="responsive"
                @update:value="onProjectIdsChange"
              />
            </div>
            <div class="form-row">
              <label class="form-label">广告层级</label>
              <Select
                v-model:value="form.levels"
                :disabled="isReadonly"
                :options="levelOptions"
                class="flex-1"
              />
            </div>
            <div class="form-row">
              <label class="form-label"
                >投放师 <span class="text-red-500">*</span></label
              >
              <Select
                v-model:value="form.media_buyer"
                :disabled="isReadonly"
                :options="mediaBuyerOptions"
                allow-clear
                show-search
                class="flex-1"
                placeholder="请选择投放师"
              />
            </div>
            <!-- <div class="form-row">
              <label class="form-label">广告系列</label>
              <Input
                v-model:value="form.campaign_id"
                :disabled="isReadonly"
                allow-clear
                class="flex-1"
                placeholder="请输入广告系列 ID"
              />
            </div> -->
            <div class="form-row">
              <label class="form-label">状态</label>
              <Radio.Group v-model:value="form.enabled" :disabled="isReadonly">
                <Radio :value="true">开启</Radio>
                <Radio :value="false">关闭</Radio>
              </Radio.Group>
            </div>
            <div class="form-row">
              <label class="form-label">自动执行</label>
              <Radio.Group
                v-model:value="form.auto_execute"
                :disabled="isReadonly"
              >
                <Radio :value="true">开启</Radio>
                <Radio :value="false">关闭</Radio>
              </Radio.Group>
            </div>
          </div>
        </Card>

        <!-- ── 条件分支与执行动作 ── -->
        <Card title="条件分支与执行动作">
          <template #extra>
            <Button
              v-if="!isReadonly"
              :disabled="form.branches.length >= MAX_BRANCHES"
              ghost
              size="small"
              type="primary"
              @click="addBranch"
            >
              + 添加分支 ({{ form.branches.length }}/{{ MAX_BRANCHES }})
            </Button>
          </template>

          <div class="space-y-3">
            <div
              v-for="(branch, bIdx) in form.branches"
              :key="bIdx"
              class="overflow-hidden rounded-md border border-gray-200"
            >
              <!-- 分支头 -->
              <div
                class="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-2"
              >
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-gray-700">{{
                    branch.branch_name
                  }}</span>
                </div>
                <Button
                  v-if="!isReadonly"
                  :disabled="form.branches.length === 1"
                  danger
                  type="text"
                  @click="removeBranch(bIdx)"
                >
                  <IconifyIcon icon="lucide:trash-2" class="text-sm" />
                </Button>
              </div>

              <div class="space-y-4 p-4">
                <!-- 命中条件 -->
                <div>
                  <div class="mb-2 flex items-center justify-between">
                    <span class="text-xs font-medium text-gray-500"
                      >命中条件</span
                    >
                    <Button
                      v-if="!isReadonly"
                      :disabled="branch.conditions.length >= MAX_CONDITIONS"
                      class="!text-primary h-auto p-0 text-xs"
                      size="small"
                      type="link"
                      @click="addCondition(bIdx)"
                    >
                      + 添加条件 ({{ branch.conditions.length }}/{{
                        MAX_CONDITIONS
                      }})
                    </Button>
                  </div>
                  <div class="space-y-1.5">
                    <div
                      v-for="(cond, cIdx) in branch.conditions"
                      :key="cIdx"
                      class="flex items-end gap-2 rounded bg-gray-50 px-3 py-2"
                    >
                      <!-- 关系 -->
                      <div class="w-24 shrink-0">
                        <div class="field-label">关系</div>
                        <span
                          v-if="cIdx === 0"
                          class="flex h-8 w-full items-center justify-center rounded border border-gray-200 bg-white text-xs text-gray-400"
                          >如果</span
                        >
                        <Select
                          v-else
                          v-model:value="cond.logic"
                          :disabled="isReadonly"
                          :options="[
                            { label: '并且', value: 'AND' },
                            { label: '或者', value: 'OR' },
                          ]"
                          class="w-full"
                        />
                      </div>
                      <!-- 数据指标 -->
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          数据指标 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          v-model:value="cond.metric"
                          :disabled="isReadonly"
                          :options="branchMetricOptions(bIdx, cIdx)"
                          class="w-full"
                          show-search
                          placeholder="请选择"
                        />
                      </div>
                      <!-- 时间 -->
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          时间 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          v-model:value="cond.time_window"
                          :disabled="isReadonly"
                          :options="timeWindowOptions"
                          class="w-full"
                          show-search
                          placeholder="请选择"
                        />
                      </div>
                      <!-- 指标范围 -->
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          指标范围 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          v-model:value="cond.operator"
                          :disabled="isReadonly"
                          :options="operatorOptions"
                          class="w-full"
                          show-search
                          placeholder="请选择"
                        />
                      </div>
                      <!-- 阈值 -->
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          阈值 <span class="text-red-400">*</span>
                        </div>
                        <template v-if="isBetween(cond.operator ?? '')">
                          <div class="flex items-center gap-1">
                            <InputNumber
                              :value="cond.value_min as any"
                              :disabled="isReadonly"
                              :min="0"
                              class="flex-1"
                              placeholder="最小值"
                              @update:value="
                                cond.value_min = ($event as number) ?? null
                              "
                            />
                            <span class="text-gray-300">–</span>
                            <InputNumber
                              :value="cond.value_max as any"
                              :disabled="isReadonly"
                              :min="0"
                              class="flex-1"
                              placeholder="最大值"
                              @update:value="
                                cond.value_max = ($event as number) ?? null
                              "
                            />
                          </div>
                        </template>
                        <template v-else>
                          <InputNumber
                            :value="cond.value as any"
                            :disabled="isReadonly"
                            :min="0"
                            class="w-full"
                            placeholder="请输入数值"
                            @update:value="
                              cond.value = ($event as number) ?? null
                            "
                          />
                        </template>
                      </div>
                      <!-- 删除条件 -->
                      <div v-if="!isReadonly" class="shrink-0">
                        <div class="field-label invisible">x</div>
                        <Button
                          :disabled="branch.conditions.length === 1"
                          class="!w-8 !p-0"
                          danger
                          type="text"
                          @click="removeCondition(bIdx, cIdx)"
                        >
                          <IconifyIcon icon="lucide:trash-2" class="text-sm" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 分隔 -->
                <div class="border-t border-dashed border-gray-200"></div>

                <!-- 执行动作 -->
                <div>
                  <div class="mb-2">
                    <span class="text-xs font-medium text-gray-500"
                      >执行动作</span
                    >
                  </div>
                  <div
                    v-for="(action, aIdx) in branch.actions"
                    :key="aIdx"
                    class="flex items-end gap-2"
                  >
                    <!-- 动作类型 -->
                    <div class="min-w-0 flex-1">
                      <div class="field-label">
                        动作 <span class="text-red-400">*</span>
                      </div>
                      <Select
                        v-model:value="action.action_type"
                        :disabled="isReadonly"
                        :options="actionTypeOptions"
                        class="w-full"
                        placeholder="请选择动作"
                      />
                    </div>
                    <!-- status -->
                    <template v-if="action.action_type === 'status'">
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          状态值 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          v-model:value="action.status"
                          :disabled="isReadonly"
                          :options="statusValueOptions"
                          class="w-full"
                          show-search
                          placeholder="请选择状态"
                        />
                      </div>
                      <div class="min-w-0 flex-[3]"></div>
                    </template>
                    <!-- daily_budget -->
                    <template v-else-if="action.action_type === 'daily_budget'">
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          调整方向 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          v-model:value="action.direction"
                          :disabled="isReadonly"
                          :options="directionOptions"
                          class="w-full"
                          show-search
                          placeholder="请选择"
                          @change="
                            () => {
                              if (action.direction === 'set') {
                                action.unit = 'fixed';
                                action.limit_type = undefined;
                                action.limit_value = null;
                              }
                            }
                          "
                        />
                      </div>
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          单位 <span class="text-red-400">*</span>
                        </div>
                        <Select
                          :value="action.unit"
                          :disabled="isReadonly"
                          :options="getUnitOptions(action.direction)"
                          class="w-full"
                          placeholder="请选择"
                          @change="(v) => (action.unit = String(v))"
                        />
                      </div>
                      <div class="min-w-0 flex-1">
                        <div class="field-label">
                          调整值 <span class="text-red-400">*</span>
                        </div>
                        <InputNumber
                          :value="action.value"
                          :disabled="isReadonly"
                          :min="0"
                          class="w-full"
                          placeholder="请输入"
                          @update:value="action.value = $event ?? null"
                        />
                      </div>
                      <template v-if="action.direction !== 'set'">
                        <div class="min-w-0 flex-1">
                          <div class="field-label">限制类型</div>
                          <Select
                            v-model:value="action.limit_type"
                            :disabled="isReadonly"
                            :options="limitTypeOptions"
                            class="w-full"
                            show-search
                            placeholder="请选择"
                          />
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="field-label">限制值</div>
                          <InputNumber
                            :value="action.limit_value as any"
                            :disabled="isReadonly"
                            :min="0"
                            class="w-full"
                            placeholder="请输入"
                            @update:value="
                              action.limit_value = ($event as number) ?? null
                            "
                          />
                        </div>
                      </template>
                      <div v-else class="min-w-0 flex-[2]"></div>
                    </template>
                    <template v-else>
                      <div class="min-w-0 flex-[4]"></div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <!-- ── 通知 ── -->
        <Card title="通知">
          <div class="flex flex-wrap items-center gap-3">
            <!-- 通知渠道 -->
            <Select
              v-model:value="form.notification.channel"
              :disabled="isReadonly"
              :options="notificationChannelOptions"
              class="w-36"
              placeholder="请选择通知渠道"
            />

            <!-- 飞书：发送方式 -->
            <template v-if="form.notification.channel === 'feishu'">
              <div class="h-4 w-px bg-gray-200"></div>
              <Select
                :value="form.notification.target_mode"
                :disabled="isReadonly"
                :options="[
                  { label: '群聊', value: 'group' },
                  { label: '私发个人', value: 'private' },
                ]"
                class="w-28"
                @change="
                  (val) => {
                    form.notification.target_mode = val;
                    form.notification.target = '';
                    form.notification.target_id_type = 'mobile';
                    form.notification.mention_user = '';
                  }
                "
              />

              <!-- 群聊：chat_id + mention_user -->
              <template v-if="form.notification.target_mode === 'group'">
                <div class="h-4 w-px bg-gray-200"></div>
                <span class="text-sm text-gray-500">群 ID</span>
                <Input
                  :value="form.notification.target"
                  :disabled="isReadonly"
                  class="w-56"
                  placeholder="chat_id，如 oc_xxx"
                  @update:value="(v) => (form.notification.target = v)"
                />
                <span class="text-sm text-gray-500">@成员</span>
                <Input
                  :value="form.notification.mention_user"
                  :disabled="isReadonly"
                  class="w-56"
                  placeholder="open_id，如 ou_xxx；填 all 则 @所有人"
                  @update:value="(v) => (form.notification.mention_user = v)"
                />
              </template>

              <!-- 私发：ID 类型 + 值 -->
              <template v-else>
                <div class="h-4 w-px bg-gray-200"></div>
                <Select
                  :value="form.notification.target_id_type"
                  :disabled="isReadonly"
                  :options="[
                    { label: '手机号', value: 'mobile' },
                    { label: '邮箱', value: 'email' },
                  ]"
                  class="w-28"
                  @change="
                    (val) => {
                      form.notification.target_id_type = val;
                      form.notification.target = '';
                    }
                  "
                />
                <Input
                  :value="form.notification.target"
                  :disabled="isReadonly"
                  class="w-56"
                  :placeholder="
                    form.notification.target_id_type === 'email'
                      ? '请输入邮箱，如 a@example.com'
                      : '请输入手机号，如 13800000000'
                  "
                  @update:value="(v) => (form.notification.target = v)"
                />
              </template>
            </template>
          </div>
        </Card>

        <!-- ── 检查时间 ── -->
        <Card title="检查时间">
          <div class="space-y-3">
            <div class="form-row">
              <label class="form-label">使用时区</label>
              <Select
                v-model:value="form.schedule.timezone"
                :disabled="isReadonly"
                :options="timezoneOptions"
                :filter-option="
                  (input, opt) =>
                    ((opt?.label as string) ?? '')
                      .toLowerCase()
                      .includes(input.toLowerCase())
                "
                show-search
                style="width: 15rem"
              />
            </div>
            <p class="pl-[76px] text-xs text-teal-600">
              请使用广告账户对应的时区，以保证和媒体广告面板数据一致
            </p>
            <div class="form-row">
              <label class="form-label">生效时段</label>
              <div class="flex flex-wrap items-center gap-2">
                <Button.Group>
                  <Button
                    :type="
                      form.schedule.effective_type === 'long_term'
                        ? 'primary'
                        : 'default'
                    "
                    @click="
                      !isReadonly &&
                      (form.schedule.effective_type = 'long_term')
                    "
                  >
                    长期
                  </Button>
                  <Button
                    :type="
                      form.schedule.effective_type === 'custom'
                        ? 'primary'
                        : 'default'
                    "
                    @click="
                      !isReadonly && (form.schedule.effective_type = 'custom')
                    "
                  >
                    自定义时段
                  </Button>
                </Button.Group>
                <DatePicker.RangePicker
                  v-if="form.schedule.effective_type === 'custom'"
                  :value="
                    form.schedule.effective_ranges[0] &&
                    form.schedule.effective_ranges[1]
                      ? form.schedule.effective_ranges
                      : undefined
                  "
                  :disabled="isReadonly"
                  :show-time="{ format: 'HH', defaultValue: undefined }"
                  format="YYYY-MM-DD HH:00"
                  value-format="YYYY-MM-DD HH:00:00"
                  @change="
                    (_, strs) => onRangeChange(_, strs as [string, string])
                  "
                />
              </div>
            </div>
            <div class="form-row !items-start">
              <label class="form-label !pt-1">检查频次</label>
              <div class="flex flex-wrap items-center gap-2">
                <Button.Group>
                  <Button
                    v-for="freq in frequencyOptions"
                    :key="freq.code"
                    :type="
                      form.schedule.frequency === freq.code
                        ? 'primary'
                        : 'default'
                    "
                    @click="
                      !isReadonly && (form.schedule.frequency = freq.code)
                    "
                  >
                    {{ freq.name }}
                  </Button>
                </Button.Group>
                <template v-if="form.schedule.frequency === 'daily_times'">
                  <div class="mt-2 w-full space-y-2">
                    <div v-if="!isReadonly" class="space-y-2">
                      <!-- 单个添加 -->
                      <div class="flex items-center gap-2">
                        <span
                          class="w-16 shrink-0 text-right text-xs text-gray-500"
                          >单个添加</span
                        >
                        <TimePicker
                          :key="dailyTimePickerKey"
                          :value="newDailyCheckTime"
                          :disabled="
                            form.schedule.daily_check_times.length >= 24
                          "
                          format="HH:mm"
                          value-format="HH:mm"
                          placeholder="选择时间"
                          class="w-32"
                          @update:value="(v) => (newDailyCheckTime = v)"
                          @ok="() => nextTick(addDailyCheckTime)"
                        />
                        <span class="text-xs text-gray-400">
                          {{ form.schedule.daily_check_times.length }}/24
                        </span>
                      </div>
                      <!-- 批量添加 -->
                      <div class="flex items-center gap-2">
                        <span
                          class="w-16 shrink-0 text-right text-xs text-gray-500"
                          >批量添加</span
                        >
                        <TimePicker
                          :value="batchStartHour"
                          :disabled="
                            form.schedule.daily_check_times.length >= 24
                          "
                          format="HH:00"
                          value-format="HH:mm"
                          placeholder="起始时间"
                          popup-class-name="batch-time-picker-popup"
                          class="w-36"
                          @update:value="(v) => (batchStartHour = v)"
                        />
                        <span class="text-xs text-gray-400">至</span>
                        <TimePicker
                          :value="batchEndHour"
                          :disabled="
                            form.schedule.daily_check_times.length >= 24
                          "
                          format="HH:00"
                          value-format="HH:mm"
                          placeholder="结束时间"
                          popup-class-name="batch-time-picker-popup"
                          class="w-36"
                          @update:value="(v) => (batchEndHour = v)"
                        />
                        <Button @click="addBatchDailyCheckTimes">添加</Button>
                      </div>
                    </div>
                    <div
                      v-if="form.schedule.daily_check_times.length > 0"
                      class="flex flex-wrap gap-1"
                    >
                      <Tag
                        v-for="t in form.schedule.daily_check_times"
                        :key="t"
                        :closable="!isReadonly"
                        @close="removeDailyCheckTime(t)"
                      >
                        {{ t }}
                      </Tag>
                    </div>
                  </div>
                </template>
                <template v-if="form.schedule.frequency === 'custom'">
                  <div class="mt-2 w-full space-y-2">
                    <div v-if="!isReadonly" class="flex items-center gap-2">
                      <DatePicker
                        v-model:value="newCheckTime"
                        :show-time="{ format: 'HH' }"
                        :disabled="
                          form.schedule.custom_check_times.length >= 24
                        "
                        format="YYYY-MM-DD HH"
                        value-format="YYYY-MM-DDTHH:00"
                        placeholder="选择年月日时"
                        class="w-44"
                        @ok="addCheckTime"
                      />
                      <span class="text-xs text-gray-400">
                        {{ form.schedule.custom_check_times.length }}/24
                      </span>
                    </div>
                    <div
                      v-if="form.schedule.custom_check_times.length > 0"
                      class="flex flex-wrap gap-1"
                    >
                      <Tag
                        v-for="t in form.schedule.custom_check_times"
                        :key="t"
                        :closable="!isReadonly"
                        @close="removeCheckTime(t)"
                      >
                        {{ t.replace('T', ' ') }}
                      </Tag>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </Card>

        <div class="h-2"></div>
      </div>
    </div>

    <!-- 固定底部操作栏 -->
    <div
      class="rule-config-footer sticky bottom-0 z-20 shrink-0 border-t bg-white"
    >
      <div v-if="!isReadonly" class="flex justify-end gap-3">
        <Button class="w-20" @click="handleCancel">取消</Button>
        <Button
          :loading="submitting"
          class="w-20"
          type="primary"
          @click="handleSubmit"
        >
          {{ isEdit ? '保存' : '创建' }}
        </Button>
      </div>
      <div v-else class="flex justify-end">
        <Button class="w-20" @click="handleCancel">返回</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.automated-rule-config-page {
  background: var(--adpulse-surface-muted);
}

.rule-config-topbar {
  gap: var(--adpulse-action-gap);
  min-height: var(--adpulse-card-head-height);
  padding-inline: var(--adpulse-page-gutter);
}

.rule-config-content {
  display: flex;
  flex-direction: column;
  gap: var(--adpulse-section-gap);
  padding: var(--adpulse-page-gutter);
}

.rule-config-footer {
  padding: var(--adpulse-action-gap) var(--adpulse-page-gutter);
}

.form-row {
  @apply flex items-center;

  gap: var(--adpulse-action-gap);
}

.form-label {
  flex: none;
  width: var(--adpulse-form-label-width);
  font-size: var(--adpulse-control-font-size);
  color: var(--adpulse-text-muted);
  text-align: right;
  white-space: nowrap;
}

.field-label {
  @apply mb-1 text-xs text-gray-600;
}
</style>

<style></style>
