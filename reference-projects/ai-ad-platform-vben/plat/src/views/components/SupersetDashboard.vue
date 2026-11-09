<script setup lang="ts">
import { computed, onMounted, ref, withDefaults } from 'vue';

import { Alert, Button, Spin, Tag } from 'ant-design-vue';

import { isDemoMockEnabled } from '#/api/demo-mock';
import { backendClient } from '#/api/request';
import AntDataTable from '#/components/ui/AntDataTable.vue';

interface Props {
  expandedFilters?: boolean;
  name: string;
  showFilters?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showFilters: false,
  expandedFilters: false,
});

const SUPERSET_URL = 'https://superset.adpulse.biz';
const containerId = ref(`superset-container-${Date.now()}`);
const loading = ref(!isDemoMockEnabled);
const embedError = ref(false);
let sdkId = '';

const dashboardTitle = computed(() =>
  props.name === 'af_data' ? '归因效果分析' : '广告投放数据',
);

const metrics = computed(() =>
  props.name === 'af_data'
    ? [
        { label: '激活用户', value: '13,482', change: '+12.6%' },
        { label: '付费用户', value: '1,706', change: '+8.4%' },
        { label: '整体 CVR', value: '12.65%', change: '+1.2%' },
        { label: '归因 ROAS', value: '3.18', change: '+0.26' },
      ]
    : [
        { label: '今日消耗', value: 'US$18,620', change: '+4.37%' },
        { label: '展示次数', value: '428.7K', change: '+9.2%' },
        { label: '平均 CTR', value: '2.94%', change: '+0.18%' },
        { label: '整体 ROAS', value: '2.84', change: '+0.21' },
      ],
);

const trend = [42, 55, 49, 68, 63, 78, 86];
const reportRows = [
  {
    name: 'ID_RewardHook_AEO',
    platform: 'Facebook',
    spend: '$6,284.00',
    result: '426',
    cpa: '$12.80',
    roas: '3.26',
    status: '投放中',
  },
  {
    name: 'US_Packshot_Value',
    platform: 'Google',
    spend: '$4,936.70',
    result: '238',
    cpa: '$21.40',
    roas: '2.82',
    status: '投放中',
  },
  {
    name: 'BR_UGC_LocalVoice',
    platform: 'Facebook',
    spend: '$3,172.20',
    result: '196',
    cpa: '$10.60',
    roas: '3.74',
    status: '已暂停',
  },
  {
    name: 'TH_Returning_Player',
    platform: 'TikTok',
    spend: '$2,842.10',
    result: '151',
    cpa: '$14.20',
    roas: '2.46',
    status: '投放中',
  },
];
const reportColumns = [
  { dataIndex: 'name', key: 'name', title: '广告系列', width: 240 },
  { dataIndex: 'platform', key: 'platform', title: '平台', width: 120 },
  {
    dataIndex: 'spend',
    key: 'spend',
    title: '消耗',
    width: 140,
    align: 'right' as const,
  },
  {
    dataIndex: 'result',
    key: 'result',
    title: '结果数',
    width: 120,
    align: 'right' as const,
  },
  {
    dataIndex: 'cpa',
    key: 'cpa',
    title: '单次成本',
    width: 140,
    align: 'right' as const,
  },
  {
    dataIndex: 'roas',
    key: 'roas',
    title: 'ROAS',
    width: 110,
    align: 'right' as const,
  },
  { dataIndex: 'status', key: 'status', title: '状态', width: 120 },
];

onMounted(async () => {
  if (isDemoMockEnabled) return;
  try {
    sdkId = await backendClient.get(`/superset/${props.name}`);
    await embedExternalDashboard();
  } catch {
    embedError.value = true;
  } finally {
    loading.value = false;
  }
});

async function fetchGuestToken(): Promise<string> {
  const tokenResult = await backendClient.get(
    `/superset/fetchGuestToken/${sdkId}`,
  );
  return tokenResult.token;
}

async function embedExternalDashboard() {
  const mountPoint = document.querySelector<HTMLElement>(
    `#${containerId.value}`,
  );
  if (!mountPoint) return;
  // SDK 仅在真实报表需要挂载时加载；演示模式不会产生这笔网络与解析开销。
  const { embedDashboard } = await import('@superset-ui/embedded-sdk');
  await embedDashboard({
    id: sdkId,
    supersetDomain: SUPERSET_URL,
    mountPoint,
    fetchGuestToken,
    dashboardUiConfig: {
      hideTitle: false,
      hideChartControls: true,
      hideTab: true,
      filters: {
        expanded: props.showFilters && props.expandedFilters,
        visible: props.showFilters,
      },
    },
  });
  const iframe = mountPoint.querySelector('iframe');
  if (iframe) {
    iframe.style.width = '100%';
    iframe.style.height = '100%';
  }
}
</script>

<template>
  <div v-if="isDemoMockEnabled" class="demo-dashboard">
    <section class="dashboard-heading">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <span class="demo-badge">实时演示数据</span>
          <span class="text-xs text-slate-400">更新于 16:30</span>
        </div>
        <h1>{{ dashboardTitle }}</h1>
        <p>统一查看广告消耗、转化和归因表现，数据口径使用项目时区与 USD。</p>
      </div>
      <Button class="shrink-0">导出报表</Button>
    </section>

    <section class="metric-grid" aria-label="核心指标">
      <article v-for="item in metrics" :key="item.label" class="metric-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.change }} 较昨日</small>
      </article>
    </section>

    <section class="chart-card">
      <div class="section-title">
        <div>
          <h2>近 7 日表现趋势</h2>
          <p>8 月 1 日 — 8 月 7 日</p>
        </div>
        <span>消耗 / 转化</span>
      </div>
      <div class="trend-chart" role="img" aria-label="近七日表现趋势柱状图">
        <div v-for="(height, index) in trend" :key="index" class="trend-column">
          <div class="bar-track">
            <div class="bar-fill" :style="{ height: `${height}%` }"></div>
          </div>
          <span>08-0{{ index + 1 }}</span>
        </div>
      </div>
    </section>

    <section class="table-card">
      <div class="section-title">
        <div>
          <h2>广告系列效果明细</h2>
          <p>按今日消耗从高到低排列</p>
        </div>
        <Button type="link">查看完整明细</Button>
      </div>
      <AntDataTable
        :columns="reportColumns"
        :data="reportRows"
        :paginate="false"
        row-key="name"
      >
        <template #cell-name="{ record }">
          <span class="text-foreground font-medium">{{ record.name }}</span>
        </template>
        <template #cell-roas="{ record }">
          <span class="font-semibold text-emerald-700">{{ record.roas }}</span>
        </template>
        <template #cell-status="{ record }">
          <Tag :color="record.status === '已暂停' ? 'default' : 'success'">
            {{ record.status }}
          </Tag>
        </template>
      </AntDataTable>

      <div v-if="false" class="table-scroll" tabindex="0">
        <table>
          <thead>
            <tr>
              <th>广告系列</th>
              <th>平台</th>
              <th>消耗</th>
              <th>结果数</th>
              <th>单次成本</th>
              <th>ROAS</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in reportRows" :key="row.name">
              <td class="font-medium text-slate-900">{{ row.name }}</td>
              <td>{{ row.platform }}</td>
              <td>{{ row.spend }}</td>
              <td>{{ row.result }}</td>
              <td>{{ row.cpa }}</td>
              <td class="font-semibold text-emerald-600">{{ row.roas }}</td>
              <td>
                <span
                  class="status-pill"
                  :class="{ paused: row.status === '已暂停' }"
                  >{{ row.status }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <div v-else class="external-dashboard-shell">
    <div v-if="loading" class="dashboard-state">
      <Spin /><span>正在加载数据看板…</span>
    </div>
    <Alert
      v-else-if="embedError"
      message="数据看板暂时无法加载"
      description="请检查网络连接或稍后重试。"
      type="warning"
      show-icon
    />
    <div :id="containerId" class="h-full w-full"></div>
  </div>
</template>

<style scoped>
.demo-dashboard {
  min-width: 0;
  padding: 24px;
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
}
.dashboard-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 20px;
}
.dashboard-heading h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.3;
}
.dashboard-heading p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 14px;
}
.demo-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 9px;
  border-radius: 999px;
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
  font-size: 12px;
  font-weight: 600;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
.metric-card,
.chart-card,
.table-card {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  box-shadow: none;
}
.metric-card {
  min-width: 0;
  padding: 18px 20px;
}
.metric-card span {
  display: block;
  color: #64748b;
  font-size: 13px;
}
.metric-card strong {
  display: block;
  margin-top: 10px;
  overflow-wrap: anywhere;
  font-size: clamp(22px, 2vw, 30px);
  line-height: 1.2;
}
.metric-card small {
  display: block;
  margin-top: 9px;
  color: #059669;
}
.chart-card,
.table-card {
  min-width: 0;
  padding: 20px;
}
.chart-card {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.section-title h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
}
.section-title p {
  margin: 5px 0 0;
  color: #94a3b8;
  font-size: 12px;
}
.section-title > span {
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  font-weight: 600;
}
.trend-chart {
  display: grid;
  grid-template-columns: repeat(7, minmax(28px, 1fr));
  align-items: end;
  gap: clamp(8px, 2vw, 24px);
  height: 245px;
  margin-top: 20px;
  padding: 10px 8px 0;
  border-bottom: 1px solid #e2e8f0;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent 53px,
    #f1f5f9 54px
  );
}
.trend-column {
  display: flex;
  min-width: 0;
  height: 100%;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}
.bar-track {
  display: flex;
  width: min(100%, 44px);
  height: 190px;
  align-items: flex-end;
  border-radius: 8px 8px 3px 3px;
  background: hsl(var(--muted));
  overflow: hidden;
}
.bar-fill {
  width: 100%;
  border-radius: 8px 8px 3px 3px;
  background: hsl(var(--foreground));
}
.trend-column span {
  flex: none;
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}
.table-scroll {
  max-width: 100%;
  margin-top: 16px;
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}
table {
  width: 100%;
  min-width: 780px;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  padding: 13px 14px;
  border-bottom: 1px solid #eef2f7;
  text-align: left;
  white-space: nowrap;
}
th {
  color: #64748b;
  background: #f8fafc;
  font-size: 12px;
  font-weight: 600;
}
tbody tr:last-child td {
  border-bottom: 0;
}
.status-pill {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 999px;
  color: #047857;
  background: #d1fae5;
  font-size: 12px;
}
.status-pill.paused {
  color: #64748b;
  background: #f1f5f9;
}
.external-dashboard-shell {
  min-height: 600px;
  height: 90vh;
  width: 100%;
  padding: 16px;
}
.dashboard-state {
  display: flex;
  min-height: 420px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: #64748b;
}

@media (max-width: 1023px) {
  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 639px) {
  .demo-dashboard {
    padding: 16px;
  }
  .dashboard-heading {
    flex-direction: column;
    gap: 14px;
  }
  .dashboard-heading h1 {
    font-size: 21px;
  }
  .metric-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }
  .metric-card,
  .chart-card,
  .table-card {
    border-radius: 12px;
  }
  .trend-chart {
    gap: 5px;
    height: 210px;
    padding-inline: 0;
  }
  .bar-track {
    height: 158px;
  }
  .trend-column span {
    font-size: 10px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bar-fill {
    transition: none;
  }
}
</style>
