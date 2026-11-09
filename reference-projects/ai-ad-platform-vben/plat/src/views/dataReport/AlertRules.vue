<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import AnimatedCount from '../components/AnimatedCount.vue';
import type { VxeGridProps } from '#/adapter/vxe-table';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import BaseButton from '../components/BaseButton.vue';
import { listRules, toggleRule } from '#/api/advertisement/automated-rule';
import type { RuleQuery } from '#/api/advertisement/automated-rule';
import {
  getAlertRulesOverview,
  getNotificationChannels,
} from '#/api/advertisement/alert-rules';
import type {
  AlertRulesOverview,
  NotificationChannelItem,
} from '#/api/advertisement/alert-rules';
import { getAlertFeed } from '#/api/dashboard';
import { Select, Tabs, Button } from 'ant-design-vue';
import { getPlatformConfigList } from '#/api/management/platform-config';

// ==================== 类型定义 ====================
interface RuleWithCategory {
  id: string;
  rule_name: string;
  enabled: boolean;
  notification: { channel: string; target?: string };
  condition_summary?: string;
  target_summary?: string;
  rule_type?: string; // 后端字段，值与 category_counts.category 对应
  category_name?: string; // 后端派生的中文分类名
  description?: string;
  [key: string]: any;
}

const router = useRouter();
const route = useRoute();

// ==================== 页面级 Tab ====================
const TabPane = Tabs.TabPane;
const pageTab = ref<'records' | 'rules'>('rules');

function initPageTabFromUrl() {
  const t = route.query.tab as string;
  if (t === 'records' || t === 'rules') pageTab.value = t;
}

watch(pageTab, (val) => {
  router.replace({ query: { ...route.query, tab: val } });
});

// 切到触发记录 tab 时懒加载数据
watch(pageTab, (val) => {
  if (val === 'records') loadTriggerRecords();
});

// ==================== 状态 ====================
const activeTab = ref('all');
const overviewData = ref<AlertRulesOverview | null>(null);
const rulesList = ref<RuleWithCategory[]>([]);
const channelsList = ref<NotificationChannelItem[]>([]);

// ==================== 常量映射 ====================
const categoryToRuleType: Record<string, string> = {
  cost: 'spend',
  conversion: 'conversion',
  account: 'account',
  behavior: 'behavior',
  creative: 'creative',
};
const channelNameMap: Record<string, string> = {
  feishu: '飞书',
  lark: '飞书',
  telegram: 'TG',
  email: '邮件',
  none: '无',
};

const channelDisplayConfig: Record<
  string,
  { initials: string; bg: string; text: string }
> = {
  feishu: { initials: '飞', bg: '#eff6ff', text: '#2563eb' },
  lark: { initials: '飞', bg: '#eff6ff', text: '#2563eb' },
  telegram: { initials: 'TG', bg: '#f0f9ff', text: '#0284c7' },
  email: { initials: '邮', bg: '#fef3c7', text: '#b45309' },
};

const severityColorMap: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#3b82f6',
};

// ==================== 辅助函数 ====================

/** 格式化通知渠道为显示文本 */
function formatChannelLabel(rule: RuleWithCategory): string {
  const ch = rule.notification?.channel;
  return channelNameMap[ch] ?? ch ?? '-';
}

// ==================== 计算属性 ====================
// 分页状态
const currentPage = ref(1);
const pageSize = ref(10);
const total = ref(0);

const totalTriggers = computed(
  () => overviewData.value?.trigger_stats.total ?? 0,
);

const statsItems = computed(() => {
  return (overviewData.value?.trigger_stats.by_severity ?? []).map((s) => ({
    label: s.name,
    labelColor: severityColorMap[s.severity] ?? '#6b7280',
    count: s.count,
    avg: `均日 ${s.daily_average.toFixed(1)}`,
  }));
});

const topRules = computed(
  () => overviewData.value?.trigger_stats.top_rules ?? [],
);

const channels = computed(() => {
  return channelsList.value.map((ch) => ({
    ...ch,
    ...(channelDisplayConfig[ch.channel] ?? {
      initials: ch.channel.toUpperCase().slice(0, 2),
      bg: '#f3f4f6',
      text: '#374151',
    }),
  }));
});

const enabledRuleCount = computed(
  () => overviewData.value?.enabled_rule_count ?? 0,
);

// ==================== VxeGrid ====================

const rulesGridOptions = reactive<VxeGridProps>({
  border: false,
  height: window.innerHeight - 400,
  pagerConfig: {
    enabled: true,
    currentPage: 1,
    pageSize: 10,
    total: 0,
    pageSizes: [10, 20, 50],
  },
  cellConfig: { height: 52 },
  rowClassName: ({ row }: any) => (!row.enabled ? 'opacity-60' : ''),
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  columns: [
    {
      title: '规则名称',
      field: 'rule_name',
      minWidth: 220,
      align: 'left',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center gap-3 py-1' }, [
            h('span', {
              class: 'w-2 h-2 rounded-full flex-shrink-0',
              style: { backgroundColor: row.enabled ? '#ef4444' : '#d1d5db' },
            }),
            h('div', [
              h(
                'div',
                { class: 'font-medium text-gray-900 text-sm' },
                row.rule_name,
              ),
              row.description
                ? h(
                    'div',
                    { class: 'text-xs text-gray-400 mt-0.5' },
                    row.description,
                  )
                : null,
            ]),
          ]),
        ],
      },
    },
    {
      title: '触发条件',
      field: 'condition_summary',
      minWidth: 180,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            {
              class: 'font-mono text-sm text-gray-700 px-2 py-1 rounded',
            },
            row.condition_summary ?? '-',
          ),
        ],
      },
    },
    { title: '适用范围', field: 'target_summary', minWidth: 110 },
    {
      title: '通知渠道',
      field: 'notification',
      minWidth: 130,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { class: 'text-sm text-gray-600' },
            formatChannelLabel(row),
          ),
        ],
      },
    },
    {
      title: '状态',
      field: 'enabled',
      width: 90,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            {
              class: 'px-2 py-0.5 rounded text-xs font-medium',
              style: row.enabled
                ? { backgroundColor: '#f0fdf4', color: '#15803d' }
                : { backgroundColor: '#f9fafb', color: '#9ca3af' },
            },
            row.enabled ? '启用' : '已停用',
          ),
        ],
      },
    },
    {
      title: '操作',
      field: 'action',
      width: 120,
      slots: {
        default: ({ row }: any) => [
          h(
            'button',
            {
              class:
                'text-xs text-blue-500 hover:text-blue-700 font-medium mr-2',
              onClick: () => handleEditRule(row),
            },
            '编辑',
          ),
          h(
            'button',
            {
              class: `text-xs font-medium ${row.enabled ? 'text-gray-400 hover:text-gray-600' : 'text-green-500 hover:text-green-700'}`,
              onClick: () => handleToggleRule(row),
            },
            row.enabled ? '停用' : '启用',
          ),
        ],
      },
    },
  ],
  data: [],
});

const [RulesGrid, rulesGridApi] = useVbenVxeGrid({
  gridOptions: rulesGridOptions,
  gridEvents: {
    pageChange({ currentPage: cp, pageSize: ps }: any) {
      currentPage.value = cp;
      pageSize.value = ps;
      loadRules();
    },
  },
  gridClass: 'p-0',
});

// tab 切换时重置到第一页并重新查询
watch(activeTab, () => {
  currentPage.value = 1;
  loadRules();
});

// ==================== 事件处理 ====================

/** 新建规则 */
function handleAddRule() {
  router.push('/createAdvertisement/automated-rule-config');
}

/** 编辑规则 */
function handleEditRule(row: RuleWithCategory) {
  router.push(`/createAdvertisement/automated-rule-config?id=${row.id}`);
}

/** 切换规则启停状态 */
async function handleToggleRule(row: RuleWithCategory) {
  await toggleRule(row.id);
  await loadRules();
}

// ==================== 数据加载 ====================

/** 加载预警规则概览 */
async function loadOverview() {
  overviewData.value = await getAlertRulesOverview();
}

/** 加载规则列表（服务端分页，category 透传给后端过滤） */
async function loadRules() {
  rulesGridApi.setLoading(true);
  try {
    const params: RuleQuery = {
      page: currentPage.value,
      page_size: pageSize.value,
    };
    // tab key 来自 category_counts.category（cost/conversion/...），
    // 映射为后端 rule_type（如 cost -> spend）后透传过滤
    if (activeTab.value !== 'all') {
      params.rule_type = categoryToRuleType[activeTab.value] ?? activeTab.value;
    }
    const result = await listRules(params);
    rulesList.value = (result.items ?? []) as RuleWithCategory[];
    total.value = result.total ?? 0;
    rulesGridApi.setGridOptions({
      data: rulesList.value,
      pagerConfig: {
        currentPage: currentPage.value,
        pageSize: pageSize.value,
        total: total.value,
      },
    });
  } finally {
    rulesGridApi.setLoading(false);
  }
}

/** 加载通知渠道状态 */
async function loadChannels() {
  const result = await getNotificationChannels();
  channelsList.value = result.items ?? [];
}

onMounted(async () => {
  initPageTabFromUrl();
  await Promise.all([loadOverview(), loadRules(), loadChannels()]);
  if (pageTab.value === 'records') loadTriggerRecords();
});

// ==================== 触发记录 ====================

const recordsFilter = reactive({
  project_id: undefined as string | undefined,
  platform: undefined as string | undefined,
  status: undefined as string | undefined,
  severity: undefined as string | undefined,
});

const projectOptions = ref<Array<{ label: string; value: string }>>([]);

const statusLabelMap: Record<string, string> = {
  pending: '待处理',
  action_pending: '已提交',
  snoozed: '已推迟',
  ignored: '已忽略',
  handled: '已人工处理',
  executed: '已成功',
  failed: '执行失败',
  skipped: '已跳过',
  dry_run: '仅预览',
};

const statusOptions = Object.entries(statusLabelMap).map(([value, label]) => ({
  label,
  value,
}));

const severityOptions = [
  { label: '严重', value: 'critical' },
  { label: '观察', value: 'warning' },
  { label: '提示', value: 'info' },
];

const severityColorMap2: Record<string, { bg: string; text: string }> = {
  critical: { bg: '#fef2f2', text: '#dc2626' },
  warning: { bg: '#fffbeb', text: '#d97706' },
  info: { bg: '#eff6ff', text: '#2563eb' },
};

const recordsPage = ref(1);
const recordsPageSize = ref(20);
const recordsTotal = ref(0);

const recordsGridOptions = reactive<VxeGridProps>({
  border: false,
  height: window.innerHeight - 230,
  pagerConfig: {
    enabled: true,
    currentPage: 1,
    pageSize: 20,
    total: 0,
    pageSizes: [20, 50, 100],
  },
  cellConfig: { height: 52 },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  columns: [
    {
      title: '标题',
      field: 'title',
      minWidth: 200,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { class: 'text-sm text-gray-800 font-medium' },
            row.title ?? '-',
          ),
        ],
      },
    },
    {
      title: '项目',
      field: 'project_name',
      width: 120,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { class: 'text-xs text-gray-600' },
            row.project_name ?? '-',
          ),
        ],
      },
    },
    {
      title: '对象',
      field: 'object_name',
      minWidth: 140,
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'text-xs text-gray-600' }, row.object_name ?? '-'),
        ],
      },
    },
    {
      title: '投手',
      field: 'placer_id',
      width: 90,
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'text-xs text-gray-600' }, row.placer_id ?? '-'),
        ],
      },
    },
    {
      title: '等级',
      field: 'severity',
      width: 80,
      slots: {
        default: ({ row }: any) => {
          const colors = severityColorMap2[row.severity] ?? {
            bg: '#f3f4f6',
            text: '#374151',
          };
          return [
            h(
              'span',
              {
                class: 'px-2 py-0.5 rounded text-xs font-medium',
                style: { backgroundColor: colors.bg, color: colors.text },
              },
              row.severity_label ?? row.severity,
            ),
          ];
        },
      },
    },
    {
      title: '预警类型',
      field: 'rule_type_label',
      width: 90,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { class: 'text-xs text-gray-500' },
            row.rule_type_label ?? row.rule_type ?? '-',
          ),
        ],
      },
    },
    {
      title: '状态',
      field: 'status',
      width: 90,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { class: 'text-xs text-gray-500' },
            statusLabelMap[row.status] ?? row.status ?? '-',
          ),
        ],
      },
    },
    {
      title: '触发时间',
      field: 'checked_at',
      width: 160,
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'text-xs text-gray-600' }, row.checked_at ?? '-'),
        ],
      },
    },
    {
      title: '操作',
      field: '_action',
      width: 80,
      slots: {
        default: ({ row }: any) => [
          row.level && row.object_id
            ? h(
                'button',
                {
                  class:
                    'text-xs text-blue-500 hover:text-blue-700 font-medium',
                  onClick: () =>
                    router.push(
                      `/data-report/drilldown?level=${row.level}&object_id=${row.object_id}`,
                    ),
                },
                '去查看',
              )
            : null,
        ],
      },
    },
  ],
  data: [],
});

const [RecordsGrid, recordsGridApi] = useVbenVxeGrid({
  gridOptions: recordsGridOptions,
  gridEvents: {
    pageChange({ currentPage: cp, pageSize: ps }: any) {
      recordsPage.value = cp;
      recordsPageSize.value = ps;
      loadTriggerRecords();
    },
  },
  gridClass: 'p-0',
});

async function loadTriggerRecords() {
  recordsGridApi.setLoading(true);
  try {
    const params: Record<string, any> = {
      include_handled: true,
      all_records: true,
      page: recordsPage.value,
      page_size: recordsPageSize.value,
    };
    if (recordsFilter.project_id) params.project_id = recordsFilter.project_id;
    if (recordsFilter.platform) params.platform = recordsFilter.platform;
    if (recordsFilter.status) params.status = recordsFilter.status;
    if (recordsFilter.severity) params.severity = recordsFilter.severity;
    const res = await getAlertFeed(params);
    recordsTotal.value = res?.total ?? 0;
    recordsGridApi.setGridOptions({
      data: res?.items ?? [],
      pagerConfig: {
        currentPage: recordsPage.value,
        pageSize: recordsPageSize.value,
        total: recordsTotal.value,
      },
    });
  } finally {
    recordsGridApi.setLoading(false);
  }
}

async function applyRecordsFilter() {
  recordsPage.value = 1;
  await loadTriggerRecords();
}

function resetRecordsFilter() {
  recordsFilter.project_id = undefined;
  recordsFilter.platform = undefined;
  recordsFilter.status = undefined;
  recordsFilter.severity = undefined;
  recordsPage.value = 1;
  loadTriggerRecords();
}

function filterProjectOption(input: string, option: any): boolean {
  return String(option?.label ?? '')
    .toLowerCase()
    .includes(input.toLowerCase());
}

onMounted(() => {
  getPlatformConfigList({ pageSize: 1000 })
    .then((res: any) => {
      const items: any[] = res?.items ?? res?.data?.items ?? [];
      projectOptions.value = items
        .filter((i: any) => i._id)
        .map((i: any) => ({ label: i._id, value: i._id }));
    })
    .catch(() => {});
});
</script>

<template>
  <Page class="adpulse-section-page adpulse-tabs-page bg-white p-0">
    <Tabs
      :active-key="pageTab"
      type="card"
      class=""
      @change="
        (key) => {
          pageTab = key;
        }
      "
    >
      <!-- ===== 预警规则 Tab ===== -->
      <TabPane key="rules" tab="预警规则">
        <div class="space-y-6">
          <div class="rounded-xl bg-white p-3">
            <div class="mb-3 flex items-end justify-between">
              <div>
                <h1 class="mb-1 text-3xl font-bold text-gray-900">
                  预警规则配置
                </h1>
                <p class="text-sm text-gray-400">
                  管理所有自动检测规则、阈值设定与通知渠道。当前
                  {{ enabledRuleCount }} 条规则启用中。
                </p>
              </div>
              <BaseButton
                variant="black"
                class="mt-1 transition-colors hover:bg-gray-800"
                @click="handleAddRule"
                >+ 新建规则</BaseButton
              >
            </div>

            <RulesGrid />
          </div>

          <!-- 通知渠道 + 触发统计 -->
          <div class="grid grid-cols-2 gap-6">
            <div class="rounded-2xl bg-white p-5 shadow-sm">
              <div class="mb-4 text-xs uppercase tracking-widest text-gray-400">
                Channels · 通知渠道
              </div>
              <div>
                <div
                  v-for="(ch, i) in channels"
                  :key="ch.channel"
                  class="flex items-center justify-between py-4"
                  :class="
                    i < channels.length - 1 ? 'border-b border-gray-100' : ''
                  "
                >
                  <div class="flex items-center gap-3">
                    <div
                      class="flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold"
                      :style="{ backgroundColor: ch.bg, color: ch.text }"
                    >
                      {{ ch.initials }}
                    </div>
                    <div>
                      <div class="text-sm font-medium text-gray-900">
                        {{ ch.name }}
                      </div>
                      <div class="mt-0.5 text-xs text-gray-400">
                        {{ ch.target_name }}
                      </div>
                    </div>
                  </div>
                  <span
                    class="flex items-center gap-1.5 text-xs font-medium"
                    :class="
                      ch.status === 'connected'
                        ? 'text-green-600'
                        : 'text-gray-400'
                    "
                  >
                    <span
                      class="inline-block h-1.5 w-1.5 rounded-full"
                      :class="
                        ch.status === 'connected'
                          ? 'bg-green-500'
                          : 'bg-gray-400'
                      "
                    ></span>
                    {{ ch.status_name }}
                  </span>
                </div>
              </div>
            </div>

            <!-- STATS -->
            <div class="rounded-2xl bg-white p-5 shadow-sm">
              <div class="mb-4 text-xs uppercase tracking-widest text-gray-400">
                Stats · 近 7 日触发统计
              </div>
              <div class="mb-5 flex items-end gap-2">
                <AnimatedCount
                  :value="totalTriggers"
                  class="text-5xl font-bold text-gray-900"
                />
                <div class="text-xs text-gray-400">次触发</div>
              </div>
              <div class="mb-6 grid grid-cols-3 gap-3">
                <div
                  v-for="item in statsItems"
                  :key="item.label"
                  class="rounded-xl bg-gray-100 p-3"
                >
                  <div
                    class="mb-2 text-xs font-medium"
                    :style="{ color: item.labelColor }"
                  >
                    {{ item.label }}
                  </div>
                  <AnimatedCount
                    :value="item.count"
                    class="text-2xl font-bold text-gray-800"
                  />
                  <div class="mt-1 text-xs text-gray-400">{{ item.avg }}</div>
                </div>
              </div>
              <!-- TOP 触发规则 -->
              <div class="mb-3 text-xs text-gray-400">TOP 触发规则</div>
              <div class="space-y-2">
                <div
                  v-for="rule in topRules"
                  :key="rule.rule_id"
                  class="flex items-center justify-between text-sm"
                >
                  <span class="text-gray-700">{{ rule.rule_name }}</span>
                  <span class="text-xs text-gray-400">{{ rule.count }} 次</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TabPane>

      <!-- ===== 触发记录 Tab ===== -->
      <TabPane key="records" tab="触发记录">
        <div class="rounded-xl bg-white">
          <!-- 筛选栏 -->
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <span class="mr-1 text-xs text-gray-400">筛选</span>
            <Select
              :value="recordsFilter.project_id"
              placeholder="项目"
              style="width: 160px"
              :options="projectOptions"
              allow-clear
              show-search
              :filter-option="filterProjectOption"
              @change="
                (val) => {
                  recordsFilter.project_id = val || undefined;
                }
              "
            />
            <Select
              :value="recordsFilter.status"
              placeholder="状态"
              style="width: 130px"
              :options="statusOptions"
              allow-clear
              @change="
                (val) => {
                  recordsFilter.status = val || undefined;
                }
              "
            />
            <Select
              :value="recordsFilter.severity"
              placeholder="等级"
              style="width: 130px"
              :options="severityOptions"
              allow-clear
              @change="
                (val) => {
                  recordsFilter.severity = val || undefined;
                }
              "
            />
            <Button type="primary" @click="applyRecordsFilter"> 搜索 </Button>
            <Button @click="resetRecordsFilter"> 重置 </Button>
          </div>

          <RecordsGrid />
        </div>
      </TabPane>
    </Tabs>
  </Page>
</template>
