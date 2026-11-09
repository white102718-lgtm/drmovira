<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';
import type {
  KpiAgentTarget,
  KpiBaselinePayload,
  KpiBaselineRule,
  KpiCondition,
  KpiSnapshot,
  KpiAlertFeedItem,
} from '#/api/advertisement/kpi-baseline-rule';

import { computed, onActivated, onMounted, reactive, ref, toRefs } from 'vue';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Divider,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputNumber,
  Menu,
  MenuItem,
  message,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  createKpiBaselineRule,
  createKpiBaselineRulesBatch,
  deleteKpiBaselineBatchGroup,
  deleteKpiBaselineRule,
  getKpiBaselineOptions,
  listKpiAlertFeed,
  listKpiBaselineRules,
  listKpiSnapshots,
  previewKpiBaselineRule,
  refreshKpiSnapshots,
  toggleKpiBaselineBatchGroup,
  toggleKpiBaselineRule,
  updateKpiBaselineBatchGroup,
  updateKpiBaselineRule,
} from '#/api/advertisement/kpi-baseline-rule';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

const TabPane = Tabs.TabPane;
const activeTab = ref('rules');
const routeStateReady = ref(false);
const optionsLoading = ref(false);
const ruleModalVisible = ref(false);
const previewModalVisible = ref(false);
const submitLoading = ref(false);
const previewLoading = ref(false);
const editingRule = ref<KpiBaselineRule | null>(null);
// 正在整批编辑的批次 ID（非空表示整批编辑模式；此模式下不允许改代理线和规则名称）
const batchEditGroupId = ref<null | string>(null);
// 打开整批编辑时的启用状态，用于判断是否需要额外调用整批启停接口
const batchEditOriginalEnabled = ref(false);
const previewResult = ref<any>(null);
// 目标代理线下拉的展开状态（选中「全选」后需要主动收起）
const targetSelectOpen = ref(false);

const kpiOptions = ref<any>({
  agent_targets: [],
  condition_logics: [],
  delta_types: [],
  directions: [],
  metrics: [],
  schedule: { frequency: 'half_hour', name: '每半小时' },
});

interface KpiRuleRow extends KpiBaselineRule {
  children?: KpiRuleRow[];
  // 批次内各规则的代理线，用于整批编辑时回显（表格不识别该字段，不会当作树形子项）
  batchTargets?: Array<Pick<KpiAgentTarget, 'agent_line' | 'platform'>>;
  isBatchGroup?: boolean;
  ruleCount?: number;
}

const agentTargets = computed<KpiAgentTarget[]>(
  () => kpiOptions.value.agent_targets ?? [],
);
const projectOptions = computed(() => {
  const map = new Map<string, string>();
  agentTargets.value.forEach((item) => {
    if (item.project_id)
      map.set(item.project_id, item.project_name || item.project_id);
  });
  return [...map.entries()].map(([value, label]) => ({ label, value }));
});
const targetOptions = computed(() =>
  agentTargets.value.map((item) => ({
    label:
      item.label ||
      `${item.project_name || item.project_id} · ${item.platform}/${item.agent_line}`,
    value: targetKey(item),
  })),
);
// 「全选」选项的哨兵值，选中后自动替换为全部代理线
const ALL_TARGET_KEY = '__ALL__';
// 下拉选项：在真实代理线前追加一个「全选」选项
const targetSelectOptions = computed(() => [
  {
    label: '全部代理线',
    value: ALL_TARGET_KEY,
  },
  ...targetOptions.value,
]);
// 全部代理线的 key，用于判断批次是否覆盖当前所有有效代理线
const allTargetKeys = computed(() =>
  targetOptions.value.map((item) => item.value),
);

/**
 * 判断目标代理线集合是否等于当前全部有效代理线
 * @param keys 目标代理线 key 集合
 */
function isAllTargetScope(keys: string[]) {
  if (!keys.length || keys.length !== allTargetKeys.value.length) return false;
  const keySet = new Set(keys);
  return allTargetKeys.value.every((key) => keySet.has(key));
}
/**
 * 目标代理线选择变化：命中「全选」时用全部代理线的 key 替换当前选择
 * @param {unknown} value 当前选中的值集合（多选时为数组）
 */
function handleTargetChange(value: unknown) {
  const values = Array.isArray(value) ? (value as string[]) : [];
  if (values.includes(ALL_TARGET_KEY)) {
    // 全选：只保留哨兵值，避免展示所有代理线标签
    formState.target_keys = [ALL_TARGET_KEY];
    targetSelectOpen.value = false;
  }
}
const metricOptions = computed(() =>
  (kpiOptions.value.metrics ?? []).map((item: any) => ({
    label: item.name,
    value: item.code,
  })),
);
const directionOptions = computed(() =>
  (kpiOptions.value.directions ?? []).map((item: any) => ({
    label: item.name,
    value: item.code,
  })),
);
const deltaTypeOptions = computed(() =>
  (kpiOptions.value.delta_types ?? []).map((item: any) => ({
    label: item.name,
    value: item.code,
  })),
);
const conditionLogicOptions = computed(() =>
  (kpiOptions.value.condition_logics ?? []).map((item: any) => ({
    label: item.name,
    value: item.code,
  })),
);

// 当日消耗（daily_spend）是绝对阈值条件，不参与项目平均值偏离计算：
// 方向仅保留大于/小于的语义，偏差类型固定为「固定金额」
function getConditionDirectionOptions(metric?: string) {
  if (metric === 'daily_spend') {
    return directionOptions.value.map((item: any) => ({
      ...item,
      label: item.value === 'below' ? '小于' : '大于',
    }));
  }
  return directionOptions.value;
}

function getConditionDeltaTypeOptions(metric?: string) {
  if (metric === 'daily_spend') {
    return deltaTypeOptions.value.filter((item: any) => item.value === 'fixed');
  }
  return deltaTypeOptions.value;
}

/**
 * 指标切换为「当日消耗」时，偏差类型强制改为固定金额
 * @param condition 当前编辑的条件行
 */
function handleConditionMetricChange(condition: KpiCondition) {
  if (condition.metric === 'daily_spend' && condition.delta_type !== 'fixed') {
    condition.delta_type = 'fixed';
  }
}

const defaultCondition = (): KpiCondition => ({
  metric: 'subscription_cost',
  direction: 'above',
  delta_type: 'percent',
  threshold: 10,
});

const formState = reactive({
  rule_name: '',
  enabled: true,
  target_keys: [] as string[],
  condition_logic: 'AND' as 'AND' | 'OR',
  conditions: [defaultCondition()] as KpiCondition[],
  notification: {
    channel: 'none' as 'feishu' | 'lark' | 'none' | 'telegram',
    target: '',
    mention_user: '',
  },
  severity: 'warning',
});

function targetKey(item: Pick<KpiAgentTarget, 'agent_line' | 'platform'>) {
  return `${item.platform}@@${item.agent_line}`;
}

function parseTargetKey(key: string) {
  const [platform = '', agent_line = ''] = key.split('@@');
  return { platform, agent_line };
}

function formatTime(value?: string) {
  return value ? String(value).slice(0, 19).replace('T', ' ') : '-';
}

function formatNumber(value?: null | number, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value)))
    return '-';
  return Number(value).toFixed(digits);
}

function formatSnapshotMetric(record: Record<string, any>, key?: string) {
  if (key === 'total_spend') return formatNumber(record.total_spend);
  if (key === 'subscription_cost')
    return formatNumber(record.subscription_cost);
  if (key === 'purchase_cost') return formatNumber(record.purchase_cost);
  return '-';
}

function metricLabel(code?: string) {
  return (
    kpiOptions.value.metrics?.find((item: any) => item.code === code)?.name ||
    code ||
    '-'
  );
}

function directionLabel(code?: string) {
  return (
    kpiOptions.value.directions?.find((item: any) => item.code === code)
      ?.name ||
    code ||
    '-'
  );
}

function deltaTypeLabel(code?: string) {
  return (
    kpiOptions.value.delta_types?.find((item: any) => item.code === code)
      ?.name ||
    code ||
    '-'
  );
}

function buildConditionText(conditions: KpiCondition[] = [], logic = 'AND') {
  if (!conditions.length) return '-';
  const joiner = logic === 'OR' ? ' 或 ' : ' 且 ';
  return conditions
    .map((item) => {
      // 当日消耗是绝对阈值条件，不与项目平均值比较，展示文案用「大于/小于」
      if (item.metric === 'daily_spend') {
        const directionText = item.direction === 'below' ? '小于' : '大于';
        return `${metricLabel(item.metric)} ${directionText} ${item.threshold} USD`;
      }
      const unit = item.delta_type === 'percent' ? '%' : ' USD';
      return `${metricLabel(item.metric)} ${directionLabel(item.direction)} ${deltaTypeLabel(item.delta_type)} ${item.threshold}${unit}`;
    })
    .join(joiner);
}

function uniqueText(values: Array<string | undefined>) {
  const list = [...new Set(values.filter(Boolean) as string[])];
  if (list.length === 0) return '-';
  if (list.length === 1) return list[0] || '-';
  return `多项（${list.length}）`;
}

function getBatchDisplayRuleName(ruleName?: string, fallback = '') {
  return (ruleName || fallback).split(' · ')[0]?.trim() || fallback;
}

function groupRulesByBatch(items: KpiBaselineRule[] = []) {
  const batchMap = new Map<string, KpiRuleRow[]>();
  const singles: KpiRuleRow[] = [];

  items.forEach((item) => {
    const row: KpiRuleRow = { ...item };
    if (!item.batch_group_id) {
      singles.push(row);
      return;
    }
    const group = batchMap.get(item.batch_group_id) ?? [];
    group.push(row);
    batchMap.set(item.batch_group_id, group);
  });

  const groups: KpiRuleRow[] = [...batchMap.entries()].map(
    ([batchGroupId, children]) => {
      const first = children[0] as KpiRuleRow;
      const allEnabled = children.every((item) => item.enabled);
      return {
        ...first,
        id: `batch:${batchGroupId}`,
        rule_name: getBatchDisplayRuleName(first.rule_name, batchGroupId),
        batch_group_id: batchGroupId,
        project_id: uniqueText(children.map((item) => item.project_id)),
        project_name: uniqueText(children.map((item) => item.project_name)),
        platform: uniqueText(children.map((item) => item.platform)),
        agent_line: `${children.length} 条代理线`,
        placer_id: '-',
        enabled: allEnabled,
        last_error: children.find((item) => item.last_error)?.last_error || '',
        batchTargets: children.map((item) => ({
          platform: item.platform,
          agent_line: item.agent_line,
        })),
        isBatchGroup: true,
        ruleCount: children.length,
      };
    },
  );

  return [...groups, ...singles];
}

function resetForm() {
  editingRule.value = null;
  batchEditGroupId.value = null;
  formState.rule_name = '';
  formState.enabled = true;
  formState.target_keys = [];
  formState.condition_logic = 'AND';
  formState.conditions = [defaultCondition()];
  formState.notification = { channel: 'none', target: '', mention_user: '' };
  formState.severity = 'warning';
  previewResult.value = null;
}

function openCreateModal() {
  resetForm();
  ruleModalVisible.value = true;
}

function openEditModal(row: any) {
  resetForm();
  editingRule.value = row;
  formState.rule_name = row.rule_name;
  formState.enabled = row.enabled;
  formState.target_keys = [targetKey(row)];
  formState.condition_logic = row.condition_logic || 'AND';
  formState.conditions = row.conditions?.length
    ? row.conditions.map((item: KpiCondition) => ({ ...item }))
    : [defaultCondition()];
  formState.notification = {
    channel: row.notification?.channel || 'none',
    target: row.notification?.target || '',
    mention_user: row.notification?.mention_user || '',
  };
  formState.severity = row.severity || 'warning';
  ruleModalVisible.value = true;
}

/**
 * 打开整批编辑弹窗：只编辑批次内共同的偏差条件/通知/启用状态等，
 * 不允许修改代理线和规则名称
 * @param {any} row 批次汇总行
 */
function openBatchEditModal(row: any) {
  resetForm();
  batchEditGroupId.value = row.batch_group_id;
  batchEditOriginalEnabled.value = row.enabled;
  formState.rule_name = row.rule_name;
  formState.enabled = row.enabled;
  // 回显批次内所有代理线（禁用态，仅展示不可改）
  const batchTargetKeys = (row.batchTargets ?? []).map((item: any) =>
    targetKey(item),
  );
  formState.target_keys = isAllTargetScope(batchTargetKeys)
    ? [ALL_TARGET_KEY]
    : batchTargetKeys;
  formState.condition_logic = row.condition_logic || 'AND';
  formState.conditions = row.conditions?.length
    ? row.conditions.map((item: KpiCondition) => ({ ...item }))
    : [defaultCondition()];
  formState.notification = {
    channel: row.notification?.channel || 'none',
    target: row.notification?.target || '',
    mention_user: row.notification?.mention_user || '',
  };
  formState.severity = row.severity || 'warning';
  ruleModalVisible.value = true;
}

function addCondition() {
  if (formState.conditions.length >= 5) {
    message.warning('每条规则最多允许 5 个条件');
    return;
  }
  formState.conditions.push(defaultCondition());
}

function removeCondition(index: number) {
  if (formState.conditions.length <= 1) {
    message.warning('每条规则至少需要 1 个条件');
    return;
  }
  formState.conditions.splice(index, 1);
}

function validateForm() {
  if (!formState.rule_name.trim()) return '请输入规则名称';
  // 整批编辑不涉及代理线，跳过代理线校验
  if (!batchEditGroupId.value) {
    if (!formState.target_keys.length) return '请选择代理线';
    if (editingRule.value && formState.target_keys.length !== 1)
      return '编辑单条规则只能选择一个代理线';
  }
  if (
    formState.notification.channel !== 'none' &&
    !formState.notification.target.trim()
  ) {
    return '通知渠道不是 none 时必须填写通知目标';
  }
  for (const [index, condition] of formState.conditions.entries()) {
    if (
      condition.threshold === null ||
      condition.threshold === undefined ||
      condition.threshold < 0
    ) {
      return `条件 ${index + 1} 的阈值必须大于等于 0`;
    }
  }
  return '';
}

function getApiErrorMessage(error: any, fallback: string) {
  const responseData = error?.response?.data ?? error?.data ?? {};
  const errors = responseData?.data?.errors ?? responseData?.errors;
  if (Array.isArray(errors) && errors.length > 0) return errors.join('；');
  return (
    responseData?.message || responseData?.error || error?.message || fallback
  );
}

// 整批修改统一覆盖的字段：条件、条件关系、通知
// （按接口文档 11.1，整批接口不改名称/项目/平台/代理线/投手 ID/启停状态/severity）
function buildBatchPayload() {
  return {
    conditions: formState.conditions.map((item) => ({
      ...item,
      threshold: Number(item.threshold),
    })),
    condition_logic: formState.condition_logic,
    notification: {
      channel: formState.notification.channel,
      target:
        formState.notification.channel === 'none'
          ? ''
          : formState.notification.target.trim(),
      mention_user: formState.notification.mention_user?.trim() || undefined,
    },
  };
}

function buildPayload(targetKeyValue: string): KpiBaselinePayload {
  return {
    ...parseTargetKey(targetKeyValue),
    rule_name: formState.rule_name.trim(),
    enabled: formState.enabled,
    ...buildBatchPayload(),
    severity: formState.severity,
  };
}

function selectedTargetKey(index = 0) {
  return formState.target_keys[index] || '';
}

async function submitRule() {
  const error = validateForm();
  if (error) {
    message.error(error);
    return;
  }
  submitLoading.value = true;
  try {
    if (batchEditGroupId.value) {
      // 整批编辑：批量接口只覆盖条件/条件关系/通知
      await updateKpiBaselineBatchGroup(
        batchEditGroupId.value,
        buildBatchPayload(),
      );
      // 启停状态不在批量修改接口内，变更时单独调用整批启停接口
      if (formState.enabled !== batchEditOriginalEnabled.value) {
        await toggleKpiBaselineBatchGroup(
          batchEditGroupId.value,
          formState.enabled,
        );
      }
      message.success('规则已更新');
    } else if (editingRule.value) {
      await updateKpiBaselineRule(
        editingRule.value.id,
        buildPayload(selectedTargetKey()),
      );
      message.success('规则已更新');
    } else if (formState.target_keys.includes(ALL_TARGET_KEY)) {
      const batchBase = {
        rule_name: formState.rule_name.trim(),
        enabled: formState.enabled,
        ...buildBatchPayload(),
        severity: formState.severity,
      };
      await createKpiBaselineRulesBatch({
        ...batchBase,
        all_agent_targets: true,
      });
      message.success('批量规则已创建');
    } else if (formState.target_keys.length === 1) {
      await createKpiBaselineRule(buildPayload(selectedTargetKey()));
      message.success('规则已创建');
    } else {
      const batchBase = {
        rule_name: formState.rule_name.trim(),
        enabled: formState.enabled,
        ...buildBatchPayload(),
        severity: formState.severity,
      };
      await createKpiBaselineRulesBatch({
        ...batchBase,
        agent_targets: formState.target_keys.map(parseTargetKey),
      });
      message.success('批量规则已创建');
    }
    ruleModalVisible.value = false;
    await loadRules();
  } catch (error: any) {
    message.error(getApiErrorMessage(error, '保存失败'));
  } finally {
    submitLoading.value = false;
  }
}

async function runPreview() {
  const error = validateForm();
  if (error) {
    message.error(error);
    return;
  }
  if (formState.target_keys.includes(ALL_TARGET_KEY)) {
    message.error('预览只支持一个代理线，请选择具体代理线');
    return;
  }
  if (formState.target_keys.length !== 1) {
    message.error('预览只支持一个代理线，请先只选择一个目标');
    return;
  }
  previewLoading.value = true;
  try {
    previewResult.value = await previewKpiBaselineRule(
      buildPayload(selectedTargetKey()),
    );
    previewModalVisible.value = true;
  } catch (error: any) {
    message.error(getApiErrorMessage(error, '预览失败'));
  } finally {
    previewLoading.value = false;
  }
}

async function loadOptions() {
  optionsLoading.value = true;
  try {
    kpiOptions.value = await getKpiBaselineOptions();
  } catch {
    message.error('加载 KPI 规则配置失败');
  } finally {
    optionsLoading.value = false;
  }
}

const ruleRows = ref<KpiRuleRow[]>([]);
const ruleLoading = ref(false);
// 一次性拉回全部规则，用表格自带的客户端分页渲染，避免数千行同时渲染导致卡死
const rulePagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
});
const ruleFilters = reactive({
  agent_line: undefined as string | undefined,
  batch_group_id: undefined as string | undefined,
  enabled: undefined as string | undefined,
  project_id: undefined as string | undefined,
});
const ruleFilterRefs = toRefs(ruleFilters);
const ruleOverflowTooltip = reactive({
  key: '',
  open: false,
  title: '',
});

const ruleColumns: TableColumnsType<KpiRuleRow> = [
  {
    title: '规则名称',
    dataIndex: 'rule_name',
    key: 'rule_name',
    width: 360,
    fixed: 'left',
  },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 120 },
  { title: '代理线', dataIndex: 'agent_line', key: 'agent_line', width: 170 },
  { title: '偏差条件', dataIndex: 'conditions', key: 'conditions', width: 280 },
  {
    title: '批次ID',
    dataIndex: 'batch_group_id',
    key: 'batch_group_id',
    width: 280,
  },
  {
    title: '快照时间',
    dataIndex: 'last_snapshot_at',
    key: 'last_snapshot_at',
    width: 150,
  },
  { title: '修改时间', dataIndex: 'updated_at', key: 'updated_at', width: 160 },
  {
    title: '操作',
    dataIndex: 'operate',
    key: 'operate',
    width: 120,
    fixed: 'right',
  },
];

async function loadRules(resetPage = true) {
  ruleLoading.value = true;
  try {
    const rawEnabled = ruleFilters.enabled;
    const res = await listKpiBaselineRules({
      agent_line: ruleFilters.agent_line,
      batch_group_id: ruleFilters.batch_group_id,
      enabled:
        rawEnabled === 'true'
          ? true
          : rawEnabled === 'false'
            ? false
            : undefined,
      page: 1,
      page_size: 99999999,
      project_id: ruleFilters.project_id,
    });
    ruleRows.value = groupRulesByBatch(res.items);
    if (resetPage) {
      rulePagination.current = 1;
      await commitRuleQueryState();
    }
  } finally {
    ruleLoading.value = false;
  }
}

async function handleRuleTableChange(paginationData: any) {
  const sizeChanged = paginationData.pageSize !== rulePagination.pageSize;
  rulePagination.current = paginationData.current;
  rulePagination.pageSize = paginationData.pageSize;
  if (sizeChanged) rulePagination.current = 1;
  await commitRuleQueryState();
}

async function handleRuleSearch() {
  rulePagination.current = 1;
  await commitRuleQueryState();
  await loadRules(false);
}

async function resetRuleFilters() {
  ruleFilters.agent_line = undefined;
  ruleFilters.batch_group_id = undefined;
  ruleFilters.enabled = undefined;
  ruleFilters.project_id = undefined;
  await handleRuleSearch();
}

function getRuleRowClassName(record: KpiRuleRow) {
  return record.isBatchGroup ? 'kpi-rule-parent-row' : 'kpi-rule-child-row';
}

function isRuleTooltipColumn(key: unknown) {
  return [
    'agent_line',
    'batch_group_id',
    'conditions',
    'last_snapshot_at',
    'project_name',
    'rule_name',
    'updated_at',
  ].includes(String(key));
}

function getRuleColumnText(record: any, key: unknown) {
  const columnKey = String(key);
  if (columnKey === 'conditions') {
    return buildConditionText(record.conditions, record.condition_logic);
  }
  if (columnKey === 'last_snapshot_at')
    return formatTime(record.last_snapshot_at);
  if (columnKey === 'updated_at') return formatTime(record.updated_at);
  return record?.[columnKey] || '-';
}

function getRuleTooltipKey(record: any, key: unknown) {
  return `${record?.id || ''}-${String(key)}`;
}

function handleRuleCellMouseEnter(
  event: MouseEvent,
  text: string,
  key: string,
) {
  const el = event.currentTarget as HTMLElement;
  const isOverflow = el.scrollWidth > el.clientWidth;
  ruleOverflowTooltip.key = key;
  ruleOverflowTooltip.title = isOverflow ? text : '';
  ruleOverflowTooltip.open = isOverflow;
}

function hideRuleOverflowTooltip() {
  ruleOverflowTooltip.open = false;
  ruleOverflowTooltip.key = '';
  ruleOverflowTooltip.title = '';
}

const severityLabelMap: Record<string, string> = {
  critical: '严重',
  info: '信息',
  warning: '警告',
};

const alertStatusLabelMap: Record<string, string> = {
  handled: '已处理',
  ignored: '已忽略',
  pending: '待处理',
  snoozed: '已延后',
};

async function handleToggleEnabled(row: any) {
  if (row.isBatchGroup) {
    await handleBatchToggle(row, !row.enabled);
    return;
  }
  const next = !row.enabled;
  row.enabled = next;
  try {
    const res = await toggleKpiBaselineRule(row.id, next);
    row.enabled = res.enabled;
  } catch {
    row.enabled = !next;
    message.error('切换失败');
  }
}

async function handleDelete(row: any) {
  await deleteKpiBaselineRule(row.id);
  message.success('删除成功');
  await loadRules();
}

async function handleBatchToggle(row: any, enabled: boolean) {
  if (!row.batch_group_id) return;
  await toggleKpiBaselineBatchGroup(row.batch_group_id, enabled);
  message.success(enabled ? '已启用' : '已暂停');
  await loadRules();
}

async function handleBatchDelete(row: any) {
  if (!row.batch_group_id) return;
  await deleteKpiBaselineBatchGroup(row.batch_group_id);
  message.success('删除成功');
  await loadRules();
}

function handleBatchMore(row: any, action: 'delete' | 'enable' | 'pause') {
  if (!row.batch_group_id) return;
  const configMap = {
    delete: {
      content: '确定删除规则吗？',
      okType: 'danger' as const,
      title: '删除',
      onOk: () => handleBatchDelete(row),
    },
    enable: {
      content: '确定启用规则吗？',
      okType: 'primary' as const,
      title: '启用',
      onOk: () => handleBatchToggle(row, true),
    },
    pause: {
      content: '确定暂停规则吗？',
      okType: 'primary' as const,
      title: '暂停',
      onOk: () => handleBatchToggle(row, false),
    },
  };
  Modal.confirm({
    cancelText: '取消',
    okText: '确定',
    ...configMap[action],
  });
}

const snapshotLoading = ref(false);
const snapshotProjectId = ref<string | undefined>();
const snapshots = ref<KpiSnapshot[]>([]);

const snapshotColumns: TableColumnsType<KpiSnapshot> = [
  { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 140 },
  { title: '项目ID', dataIndex: 'project_id', key: 'project_id', width: 120 },
  {
    title: '快照时间',
    dataIndex: 'snapshot_at',
    key: 'snapshot_at',
    width: 170,
  },
  {
    title: '代理线数',
    dataIndex: 'agent_line_count',
    key: 'agent_line_count',
    width: 90,
    align: 'right',
  },
  {
    title: '总消耗',
    dataIndex: 'total_spend',
    key: 'total_spend',
    width: 100,
    align: 'right',
  },
  {
    title: '订阅数',
    dataIndex: 'subscriptions',
    key: 'subscriptions',
    width: 90,
    align: 'right',
  },
  {
    title: '付费数',
    dataIndex: 'purchases',
    key: 'purchases',
    width: 90,
    align: 'right',
  },
  {
    title: '订阅成本',
    dataIndex: 'subscription_cost',
    key: 'subscription_cost',
    width: 110,
    align: 'right',
  },
  {
    title: '付费成本',
    dataIndex: 'purchase_cost',
    key: 'purchase_cost',
    width: 110,
    align: 'right',
  },
];

async function loadSnapshots() {
  snapshotLoading.value = true;
  try {
    const res = await listKpiSnapshots({
      project_id: snapshotProjectId.value,
      limit: 200,
    });
    snapshots.value = res.items ?? [];
  } finally {
    snapshotLoading.value = false;
  }
}

async function handleRefreshSnapshots() {
  snapshotLoading.value = true;
  try {
    const res = await refreshKpiSnapshots();
    message.success(
      `快照刷新完成：成功 ${res.project_count}/${res.requested_project_count} 个项目`,
    );
    if (res.errors?.length)
      message.warning(`部分项目失败：${res.errors.slice(0, 3).join('；')}`);
    await loadSnapshots();
  } finally {
    snapshotLoading.value = false;
  }
}

const alertLoading = ref(false);
const alertStatus = ref<string | undefined>();
const alertRows = ref<KpiAlertFeedItem[]>([]);
const alertPagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
});

const rulePaginationRefs = toRefs(rulePagination);
const alertPaginationRefs = toRefs(alertPagination);
const {
  commitQueryState: commitTabQueryState,
  restoreFromRoute: restoreTabFromRoute,
} = useListRouteState({
  fields: { tab: { always: true } },
  state: createListRouteStateTarget({ tab: activeTab }),
});
const {
  commitQueryState: commitRuleQueryState,
  restoreFromRoute: restoreRulesFromRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeTab.value === 'rules')
      return loadRules(false);
  },
  pagination: {
    defaultPageSize: 20,
    page: rulePaginationRefs.current,
    pageSize: rulePaginationRefs.pageSize,
    pageSizes: [10, 20, 50, 100],
  },
  scope: 'rule',
  state: createListRouteStateTarget(ruleFilterRefs),
});
const {
  commitQueryState: commitSnapshotQueryState,
  restoreFromRoute: restoreSnapshotsFromRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeTab.value === 'snapshots')
      return loadSnapshots();
  },
  scope: 'snapshot',
  state: createListRouteStateTarget({ project_id: snapshotProjectId }),
});
const {
  commitQueryState: commitAlertQueryState,
  restoreFromRoute: restoreAlertsFromRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeTab.value === 'alerts')
      return loadAlertFeed();
  },
  pagination: {
    defaultPageSize: 20,
    page: alertPaginationRefs.current,
    pageSize: alertPaginationRefs.pageSize,
    pageSizes: [10, 20, 50, 100],
  },
  scope: 'alert',
  state: createListRouteStateTarget({ status: alertStatus }),
});

const alertColumns: TableColumnsType<KpiAlertFeedItem> = [
  { title: '规则', dataIndex: 'rule_name', key: 'rule_name', width: 180 },
  { title: '项目', dataIndex: 'project_name', key: 'project_name', width: 120 },
  { title: '代理线', dataIndex: 'agent_line', key: 'agent_line', width: 170 },
  { title: '投手ID', dataIndex: 'placer_id', key: 'placer_id', width: 120 },
  { title: '级别', dataIndex: 'severity', key: 'severity', width: 90 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  {
    title: '快照时间',
    dataIndex: 'snapshot_at',
    key: 'snapshot_at',
    width: 170,
  },
  {
    title: '条件',
    dataIndex: 'condition_results',
    key: 'condition_results',
    width: 320,
  },
];

async function loadAlertFeed() {
  alertLoading.value = true;
  try {
    const res = await listKpiAlertFeed({
      page: alertPagination.current,
      page_size: alertPagination.pageSize,
      status: alertStatus.value,
    });
    alertRows.value = res.items ?? [];
    alertPagination.total = res.total ?? 0;
  } finally {
    alertLoading.value = false;
  }
}

async function handleAlertTableChange(paginationData: any) {
  const sizeChanged = paginationData.pageSize !== alertPagination.pageSize;
  alertPagination.current = paginationData.current;
  alertPagination.pageSize = paginationData.pageSize;
  if (sizeChanged) alertPagination.current = 1;
  await commitAlertQueryState();
  await loadAlertFeed();
}

async function handleAlertStatusChange() {
  alertPagination.current = 1;
  await commitAlertQueryState();
  await loadAlertFeed();
}

async function handleSnapshotSearch() {
  await commitSnapshotQueryState();
  await loadSnapshots();
}

async function handleTabChange(key: string | number) {
  activeTab.value = String(key);
  await commitTabQueryState();
  if (key === 'rules') await loadRules(false);
  if (key === 'snapshots') await loadSnapshots();
  if (key === 'alerts') await loadAlertFeed();
}

onMounted(async () => {
  await restoreTabFromRoute();
  await restoreRulesFromRoute();
  await restoreSnapshotsFromRoute();
  await restoreAlertsFromRoute();
  // options 接口较慢，先让当前 tab 进入加载态，避免出现空表格
  if (activeTab.value === 'rules') ruleLoading.value = true;
  await loadOptions();
  routeStateReady.value = true;
  // 只加载当前 tab 的数据，切换 tab 时再按需加载（见 handleTabChange）
  await handleTabChange(activeTab.value);
});

// 首次挂载时 onActivated 会紧跟 onMounted 触发，跳过这一次避免重复请求
let activatedBefore = false;
onActivated(() => {
  if (!activatedBefore) {
    activatedBefore = true;
    return;
  }
  if (activeTab.value === 'rules') loadRules();
});
</script>

<template>
  <div
    class="adpulse-section-page adpulse-tabs-page bg-muted/40 h-full min-h-0 p-[var(--adpulse-page-gap)]"
  >
    <section class="alert-rule-workspace h-full min-h-0" aria-label="投放预警">
      <Tabs
        v-model:active-key="activeTab"
        class="h-full"
        @change="handleTabChange"
      >
        <TabPane key="rules" tab="KPI基准规则">
          <div class="h-full">
            <div class="flex h-full flex-col gap-4">
              <div class="flex flex-wrap items-center gap-2">
                <Input
                  v-model:value="ruleFilters.agent_line"
                  allow-clear
                  placeholder="代理线"
                  class="w-56"
                />
                <Select
                  v-model:value="ruleFilters.project_id"
                  allow-clear
                  show-search
                  placeholder="全部项目"
                  class="w-48"
                  :options="projectOptions"
                />
                <Input
                  v-model:value="ruleFilters.batch_group_id"
                  allow-clear
                  placeholder="批次ID"
                  class="w-56"
                />
                <Select
                  v-model:value="ruleFilters.enabled"
                  allow-clear
                  placeholder="全部状态"
                  class="w-36"
                  :options="[
                    { label: '开启', value: 'true' },
                    { label: '关闭', value: 'false' },
                  ]"
                />
                <Button @click="handleRuleSearch">查询</Button>
                <Button @click="resetRuleFilters">重置</Button>
                <div class="ml-auto flex items-center gap-2">
                  <Tooltip
                    title="每半小时读取最新小时数据，与项目平均 KPI 对比；仅通知，不执行操作。"
                  >
                    <Tag color="blue">{{
                      kpiOptions.schedule?.name || '每半小时'
                    }}</Tag>
                  </Tooltip>
                  <Button type="primary" @click="openCreateModal"
                    >+ 创建 KPI 规则</Button
                  >
                </div>
              </div>

              <Table
                :columns="ruleColumns"
                :data-source="ruleRows"
                :loading="ruleLoading"
                :pagination="rulePagination"
                :row-class-name="getRuleRowClassName"
                :scroll="{ x: 1660, y: 440 }"
                row-key="id"
                @change="handleRuleTableChange"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'enabled'">
                    <Switch
                      :checked="record.enabled"
                      checked-children="开启"
                      un-checked-children="暂停"
                      @change="handleToggleEnabled(record)"
                    />
                  </template>
                  <template v-else-if="isRuleTooltipColumn(column.key)">
                    <Tooltip
                      :open="
                        ruleOverflowTooltip.open &&
                        ruleOverflowTooltip.key ===
                          getRuleTooltipKey(record, column.key)
                      "
                      :title="ruleOverflowTooltip.title"
                    >
                      <span
                        class="inline-block max-w-full truncate align-bottom"
                        @mouseenter="
                          handleRuleCellMouseEnter(
                            $event,
                            getRuleColumnText(record, column.key),
                            getRuleTooltipKey(record, column.key),
                          )
                        "
                        @mouseleave="hideRuleOverflowTooltip"
                      >
                        {{ getRuleColumnText(record, column.key) }}
                      </span>
                    </Tooltip>
                  </template>
                  <template v-else-if="column.key === 'operate'">
                    <div
                      class="flex flex-nowrap items-center gap-1 whitespace-nowrap"
                    >
                      <Button
                        v-if="!record.isBatchGroup"
                        type="link"
                        class="px-1"
                        @click="openEditModal(record)"
                        >编辑</Button
                      >
                      <Popconfirm
                        v-if="!record.isBatchGroup"
                        cancel-text="取消"
                        ok-text="确定"
                        placement="left"
                        title="确定删除该规则吗？"
                        @confirm="handleDelete(record)"
                      >
                        <Button type="link" class="px-1" danger>删除</Button>
                      </Popconfirm>
                      <template v-if="record.isBatchGroup">
                        <Button
                          type="link"
                          class="px-1"
                          @click="openBatchEditModal(record)"
                          >编辑</Button
                        >
                        <Dropdown>
                          <Button type="link" class="px-1">更多</Button>
                          <template #overlay>
                            <Menu>
                              <MenuItem
                                v-if="!record.enabled"
                                @click="handleBatchMore(record, 'enable')"
                                >启用</MenuItem
                              >
                              <MenuItem
                                v-else
                                @click="handleBatchMore(record, 'pause')"
                                >暂停</MenuItem
                              >
                              <MenuItem
                                danger
                                @click="handleBatchMore(record, 'delete')"
                                >删除</MenuItem
                              >
                            </Menu>
                          </template>
                        </Dropdown>
                      </template>
                    </div>
                  </template>
                </template>
              </Table>
            </div>
          </div>
        </TabPane>

        <TabPane key="snapshots" tab="项目KPI快照">
          <div class="flex h-full flex-col gap-4">
            <Alert
              show-icon
              type="info"
              message="项目快照是项目内全部代理线的小时汇总：订阅成本=总消耗/总订阅数，付费成本=总消耗/总付费数。"
            />
            <div class="flex items-center gap-2">
              <Select
                v-model:value="snapshotProjectId"
                allow-clear
                show-search
                placeholder="全部项目"
                class="w-64"
                :options="projectOptions"
                @change="handleSnapshotSearch"
              />
              <Button @click="handleSnapshotSearch">查询</Button>
              <Button
                type="primary"
                :loading="snapshotLoading"
                @click="handleRefreshSnapshots"
                >立即刷新全部快照</Button
              >
            </div>
            <Table
              :columns="snapshotColumns"
              :data-source="snapshots"
              :loading="snapshotLoading"
              :pagination="false"
              :scroll="{ x: 1100, y: 440 }"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'snapshot_at'">{{
                  formatTime(record.snapshot_at)
                }}</template>
                <template
                  v-if="
                    [
                      'total_spend',
                      'subscription_cost',
                      'purchase_cost',
                    ].includes(String(column.key))
                  "
                >
                  {{ formatSnapshotMetric(record, String(column.key)) }}
                </template>
              </template>
            </Table>
          </div>
        </TabPane>

        <TabPane key="alerts" tab="触发预警">
          <div class="flex h-full flex-col gap-4">
            <div class="flex items-center gap-2">
              <Select
                v-model:value="alertStatus"
                allow-clear
                placeholder="全部状态"
                class="w-48"
                :options="[
                  { label: '待处理', value: 'pending' },
                  { label: '已延后', value: 'snoozed' },
                  { label: '已忽略', value: 'ignored' },
                  { label: '已处理', value: 'handled' },
                ]"
                @change="handleAlertStatusChange"
              />
              <Button :loading="alertLoading" @click="loadAlertFeed"
                >刷新</Button
              >
            </div>
            <Table
              :columns="alertColumns"
              :data-source="alertRows"
              :loading="alertLoading"
              :pagination="alertPagination"
              :scroll="{ x: 1250, y: 440 }"
              row-key="id"
              @change="handleAlertTableChange"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'severity'">
                  <Tag
                    :color="record.severity === 'critical' ? 'red' : 'orange'"
                    >{{ severityLabelMap[record.severity] || '警告' }}</Tag
                  >
                </template>
                <template v-if="column.key === 'status'">
                  <Tag>{{
                    alertStatusLabelMap[
                      record.status || record.notification_item?.record_status
                    ] ||
                    record.status ||
                    '-'
                  }}</Tag>
                </template>
                <template v-if="column.key === 'snapshot_at'">{{
                  formatTime(record.snapshot_at)
                }}</template>
                <template v-if="column.key === 'condition_results'">
                  <div class="space-y-1">
                    <div
                      v-for="(item, index) in record.condition_results || []"
                      :key="index"
                      class="text-xs"
                    >
                      {{ metricLabel(item.metric) }}：实际
                      {{ formatNumber(item.actual_value) }} / 基准
                      {{ formatNumber(item.baseline_value) }} / 偏差
                      {{ formatNumber(item.difference_rate) }}%
                    </div>
                  </div>
                </template>
              </template>
            </Table>
          </div>
        </TabPane>
      </Tabs>
    </section>

    <Modal
      v-model:open="ruleModalVisible"
      :confirm-loading="submitLoading"
      :title="
        editingRule || batchEditGroupId
          ? '编辑 KPI 基准规则'
          : '创建 KPI 基准规则'
      "
      width="920px"
      ok-text="保存"
      cancel-text="取消"
      @ok="submitRule"
    >
      <Form :model="formState" layout="vertical">
        <div class="grid grid-cols-2 gap-x-4">
          <FormItem label="规则名称" required>
            <Input
              v-model:value="formState.rule_name"
              class="rule-name-input"
              allow-clear
              :disabled="!!batchEditGroupId"
              placeholder="例如：订阅成本偏高"
            />
          </FormItem>
          <FormItem label="启用状态">
            <Switch
              v-model:checked="formState.enabled"
              checked-children="开启"
              un-checked-children="暂停"
            />
          </FormItem>
        </div>

        <FormItem label="目标代理线" required>
          <Select
            v-model:value="formState.target_keys"
            class="target-select"
            mode="multiple"
            :max-tag-count="'responsive'"
            allow-clear
            show-search
            :disabled="!!editingRule || !!batchEditGroupId"
            :filter-option="
              (input, option) =>
                String(option?.label ?? '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
            "
            :options="targetSelectOptions"
            :open="targetSelectOpen"
            placeholder="从后端 /options 返回的有效代理线中选择"
            @change="handleTargetChange"
            @dropdown-visible-change="(v) => (targetSelectOpen = v)"
          />
          <div class="mt-1 text-xs text-gray-500">
            {{
              batchEditGroupId
                ? '编辑不支持修改代理线和规则名称，仅更新偏差条件与通知设置。'
                : '多选时自动调用批量创建接口；后端会自动补充项目、项目名称和投手 ID。'
            }}
          </div>
        </FormItem>

        <Divider orientation="left">偏差条件</Divider>
        <div class="mb-3 flex items-center gap-3">
          <span>条件关系</span>
          <Select
            v-model:value="formState.condition_logic"
            class="w-40"
            :options="conditionLogicOptions"
          />
          <Button @click="addCondition">+ 添加条件</Button>
        </div>
        <div
          v-for="(condition, index) in formState.conditions"
          :key="index"
          class="mb-2 grid grid-cols-1 items-center gap-2 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_160px_70px]"
        >
          <Select
            v-model:value="condition.metric"
            :options="metricOptions"
            @change="handleConditionMetricChange(condition)"
          />
          <Select
            v-model:value="condition.direction"
            :options="getConditionDirectionOptions(condition.metric)"
          />
          <Select
            v-model:value="condition.delta_type"
            :disabled="condition.metric === 'daily_spend'"
            :options="getConditionDeltaTypeOptions(condition.metric)"
          />
          <InputNumber
            v-model:value="condition.threshold"
            class="w-full"
            :min="0"
            :precision="2"
            :addon-after="condition.delta_type === 'percent' ? '%' : 'USD'"
          />
          <Button danger @click="removeCondition(index)">删除</Button>
        </div>

        <Divider orientation="left">通知设置</Divider>
        <div class="grid grid-cols-3 gap-x-4">
          <FormItem label="通知渠道" required>
            <Select
              v-model:value="formState.notification.channel"
              :options="[
                { label: '不通知', value: 'none' },
                { label: '飞书', value: 'feishu' },
                { label: 'Lark', value: 'lark' },
                { label: 'Telegram', value: 'telegram' },
              ]"
            />
          </FormItem>
          <FormItem label="通知目标">
            <Input
              v-model:value="formState.notification.target"
              allow-clear
              placeholder="oc_xxx / chat id"
              :disabled="formState.notification.channel === 'none'"
            />
          </FormItem>
          <FormItem label="提醒用户">
            <Input
              v-model:value="formState.notification.mention_user"
              allow-clear
              placeholder="ou_xxx，可选"
              :disabled="formState.notification.channel === 'none'"
            />
          </FormItem>
        </div>

        <Alert
          show-icon
          type="warning"
          message="KPI 基准预警只写入预警中心并发送通知，不会暂停广告、调整预算或执行其他操作。"
        />
      </Form>
      <template #footer>
        <Button @click="ruleModalVisible = false">取消</Button>
        <Button
          v-if="!batchEditGroupId"
          :loading="previewLoading"
          @click="runPreview"
          >预览最新数据</Button
        >
        <Button type="primary" :loading="submitLoading" @click="submitRule"
          >保存</Button
        >
      </template>
    </Modal>

    <Modal
      v-model:open="previewModalVisible"
      title="规则预览"
      width="760px"
      :footer="null"
    >
      <Descriptions v-if="previewResult" bordered :column="2">
        <DescriptionsItem label="目标">{{
          previewResult.target?.label ||
          `${previewResult.target?.platform}/${previewResult.target?.agent_line}`
        }}</DescriptionsItem>
        <DescriptionsItem label="投手ID">{{
          previewResult.target?.placer_id || '-'
        }}</DescriptionsItem>
        <DescriptionsItem label="快照时间">{{
          formatTime(previewResult.snapshot_at)
        }}</DescriptionsItem>
        <DescriptionsItem label="是否命中">
          <Tag :color="previewResult.matched ? 'red' : 'green'">{{
            previewResult.matched ? '命中' : '未命中'
          }}</Tag>
        </DescriptionsItem>
        <DescriptionsItem label="代理线订阅成本">{{
          formatNumber(previewResult.agent_metrics?.subscription_cost)
        }}</DescriptionsItem>
        <DescriptionsItem label="项目订阅成本">{{
          formatNumber(previewResult.project_metrics?.subscription_cost)
        }}</DescriptionsItem>
        <DescriptionsItem label="代理线付费成本">{{
          formatNumber(previewResult.agent_metrics?.purchase_cost)
        }}</DescriptionsItem>
        <DescriptionsItem label="项目付费成本">{{
          formatNumber(previewResult.project_metrics?.purchase_cost)
        }}</DescriptionsItem>
      </Descriptions>
      <Table
        class="mt-4"
        :data-source="previewResult?.condition_results || []"
        :pagination="false"
        row-key="metric"
      >
        <Table.Column title="指标" data-index="metric">
          <template #default="{ text }">{{ metricLabel(text) }}</template>
        </Table.Column>
        <Table.Column title="实际值" data-index="actual_value">
          <template #default="{ text }">{{ formatNumber(text) }}</template>
        </Table.Column>
        <Table.Column title="基准值" data-index="baseline_value">
          <template #default="{ text }">{{ formatNumber(text) }}</template>
        </Table.Column>
        <Table.Column title="目标值" data-index="target_value">
          <template #default="{ text }">{{ formatNumber(text) }}</template>
        </Table.Column>
        <Table.Column title="偏差率" data-index="difference_rate">
          <template #default="{ text }">{{ formatNumber(text) }}%</template>
        </Table.Column>
        <Table.Column title="结果" data-index="matched">
          <template #default="{ record }">
            <Tag :color="record.matched ? 'red' : 'default'">{{
              record.matched ? '命中' : record.reason || '未命中'
            }}</Tag>
          </template>
        </Table.Column>
      </Table>
    </Modal>
  </div>
</template>
<style scoped>
.alert-rule-workspace {
  box-sizing: border-box;
  padding: var(--adpulse-card-padding);
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--adpulse-page-radius);
  box-shadow: var(--adpulse-card-shadow);
}

:deep(.kpi-rule-parent-row > td) {
  background-color: #f7f8fa !important;
}

:deep(.kpi-rule-parent-row:hover > td) {
  background-color: #eef0f4 !important;
}

:deep(.kpi-rule-child-row > td) {
  background-color: #ffffff !important;
}

:deep(.kpi-rule-child-row:hover > td) {
  background-color: #f5f5f5 !important;
}
</style>
