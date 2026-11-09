<script lang="ts" setup>
import type { ProjectSummary } from '#/api';
import type { AntDataTableColumn } from '#/components/ui/AntDataTable.vue';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';

import AntDataTable from '#/components/ui/AntDataTable.vue';

import {
  Button,
  Card,
  Col,
  Drawer,
  InputNumber,
  Row,
  Statistic,
  Tag,
} from 'ant-design-vue';

import { isFusionDemoMode } from '#/api';
import { projectService } from '#/domain/project';
import {
  canDemoAction,
  filterDemoProjects,
  getCurrentDemoActor,
} from '#/mock/demo-access';

defineOptions({ name: 'FinanceOverview' });

interface FinanceRow extends ProjectSummary {
  estimatedCost: number;
  estimatedFee: number;
  estimatedProfit: number;
}

const route = useRoute();
const loading = ref(false);
const projects = ref<ProjectSummary[]>([]);
const costDrawerOpen = ref(false);
const selectedProject = ref<FinanceRow>();
const recordedCost = ref<number>();

const actor = computed(() =>
  isFusionDemoMode() ? getCurrentDemoActor() : undefined,
);
const canWrite = computed(
  () => !isFusionDemoMode() || canDemoAction(actor.value, 'finance.write'),
);

const pageConfig = computed(() => {
  const path = route.path;
  if (path.endsWith('/service-fees')) {
    return {
      description: '按项目预算与约定服务费比例核对收入。',
      title: '服务费管理',
    };
  }
  if (path.endsWith('/costs')) {
    return {
      description: '汇总渠道、账户、素材与人力成本。',
      title: '成本管理',
    };
  }
  if (path.endsWith('/reconciliation')) {
    return {
      description: '核对项目成本、服务费与结算状态。',
      title: '项目对账',
    };
  }
  return {
    description: '查看收入、成本和项目利润的 Mock 经营投影。',
    title: '项目利润',
  };
});

const rows = computed<FinanceRow[]>(() =>
  filterDemoProjects(actor.value, projects.value).map((project) => {
    const estimatedCost =
      recordedCost.value && selectedProject.value?.id === project.id
        ? recordedCost.value
        : Math.round(project.dailyBudget * 20 * 0.7);
    const estimatedFee = Math.round(
      project.dailyBudget * 20 * ((project.serviceFeePercent ?? 10) / 100),
    );
    return {
      ...project,
      estimatedCost,
      estimatedFee,
      estimatedProfit: estimatedFee - estimatedCost,
    };
  }),
);

const totals = computed(() => {
  const total = { cost: 0, fee: 0, profit: 0 };
  for (const item of rows.value) {
    total.cost += item.estimatedCost;
    total.fee += item.estimatedFee;
    total.profit += item.estimatedProfit;
  }
  return total;
});

const columns: AntDataTableColumn[] = [
  { dataIndex: 'name', key: 'name', title: '项目', width: 220 },
  { dataIndex: 'currency', key: 'currency', title: '币种', width: 90 },
  { key: 'fee', title: '预估服务费', width: 150 },
  { key: 'cost', title: '预估成本', width: 150 },
  { key: 'profit', title: '预估利润', width: 150 },
  { key: 'actions', title: '操作', width: 120 },
];

function formatMoney(value: number, currency: string) {
  return new Intl.NumberFormat('zh-CN', {
    currency,
    maximumFractionDigits: 0,
    style: 'currency',
  }).format(value);
}

function openCostDrawer(row: FinanceRow) {
  selectedProject.value = row;
  recordedCost.value = row.estimatedCost;
  costDrawerOpen.value = true;
}

function asFinanceRow(row: FinanceRow | Record<string, unknown>): FinanceRow {
  return row as FinanceRow;
}

function saveCost() {
  costDrawerOpen.value = false;
}

async function loadProjects() {
  loading.value = true;
  try {
    const result = await projectService.list({ page: 1, pageSize: 1000 });
    projects.value = result.items;
  } finally {
    loading.value = false;
  }
}

watch(
  () => route.path,
  () => void loadProjects(),
);
onMounted(() => void loadProjects());
</script>

<template>
  <Page
    auto-content-height
    class="adpulse-section-page bg-muted/40"
    content-class="p-4 pb-6"
  >
    <div class="flex w-full min-w-0 flex-col gap-4">
      <Card>
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="text-foreground m-0 text-xl font-semibold">
              {{ pageConfig.title }}
            </h1>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              {{ pageConfig.description }}
            </p>
          </div>
          <Tag v-if="isFusionDemoMode()" color="blue">角色 Mock 数据范围</Tag>
        </div>

        <Row :gutter="16" class="my-6">
          <Col :xs="24" :md="8">
            <div class="border-border bg-muted/50 rounded-lg border p-4">
              <Statistic title="预估服务费" :value="totals.fee" prefix="US$" />
            </div>
          </Col>
          <Col :xs="24" :md="8">
            <div class="border-border bg-muted/50 rounded-lg border p-4">
              <Statistic title="预估成本" :value="totals.cost" prefix="US$" />
            </div>
          </Col>
          <Col :xs="24" :md="8">
            <div class="border-border bg-muted/50 rounded-lg border p-4">
              <Statistic title="预估利润" :value="totals.profit" prefix="US$" />
            </div>
          </Col>
        </Row>

        <h2 class="mb-4 text-base font-medium">项目经营明细</h2>
        <AntDataTable
          :columns="columns"
          :loading="loading"
          :data="rows"
          :paginate="false"
          row-key="id"
        >
          <template #cell-fee="{ record }">
            {{ formatMoney(record.estimatedFee, record.currency) }}
          </template>
          <template #cell-cost="{ record }">
            {{ formatMoney(record.estimatedCost, record.currency) }}
          </template>
          <template #cell-profit="{ record }">
            <span
              :class="
                record.estimatedProfit >= 0
                  ? 'text-emerald-600'
                  : 'text-rose-600'
              "
            >
              {{ formatMoney(record.estimatedProfit, record.currency) }}
            </span>
          </template>
          <template #cell-actions="{ record }">
            <Button
              v-if="canWrite"
              type="link"
              @click="openCostDrawer(asFinanceRow(record))"
            >
              录入成本
            </Button>
            <span v-else class="text-muted-foreground text-xs">只读</span>
          </template>
          <template #empty>当前角色暂无可见财务项目</template>
        </AntDataTable>
      </Card>
    </div>

    <Drawer v-model:open="costDrawerOpen" :width="420" title="录入项目成本">
      <div class="space-y-4">
        <div class="text-sm text-slate-500">
          {{ selectedProject?.name }} · {{ selectedProject?.currency }}
        </div>
        <InputNumber
          v-model:value="recordedCost"
          :min="0"
          class="w-full"
          :precision="2"
        />
        <Button type="primary" block @click="saveCost">保存 Mock 成本</Button>
      </div>
    </Drawer>
  </Page>
</template>
