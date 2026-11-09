<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Drawer,
  Form,
  FormItem,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  message,
} from 'ant-design-vue';

import { getOperationsApi, type OperationRecord } from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

import AdgenOperationsPanel from './adgen-operations-panel.vue';

const route = useRoute();
const loading = ref(false);
const records = ref<OperationRecord[]>([]);
const keyword = ref('');
const activeCategory = ref('all');
const selectedRecord = ref<OperationRecord>();
const detailOpen = ref(false);
const createOpen = ref(false);
const createForm = reactive({ category: '', metric: '', name: '', owner: '' });
const routeState = createListRouteStateTarget({
  category: activeCategory,
  keyword,
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  state: routeState,
});
watch([keyword, activeCategory], () => {
  void commitQueryState();
});

const isAdgen = computed(() => route.path === '/fusion/adgen-operations');
const domain = computed(() => (isAdgen.value ? 'adgen' : 'business'));

const pageMeta = computed(() =>
  isAdgen.value
    ? {
        description:
          '管理模型密钥、用量成本、媒体模型、Worker、错误日志与 Java 权限映射。',
        eyebrow: 'ADGEN OPERATIONS',
        icon: 'lucide:server-cog',
        title: 'AdGen 模型与运维',
      }
    : {
        description:
          '管理渠道与代理账户、项目交付审批、媒介资源和项目经营报表。',
        eyebrow: 'MPOWER OPERATIONS',
        icon: 'lucide:landmark',
        title: 'MPower 运营支撑',
      },
);

const categories = computed(() => [
  'all',
  ...new Set(records.value.map((item) => item.category)),
]);

const filteredRecords = computed(() => {
  const search = keyword.value.trim().toLowerCase();
  return records.value.filter((item) => {
    const categoryMatches =
      activeCategory.value === 'all' || item.category === activeCategory.value;
    const keywordMatches =
      !search ||
      `${item.name}${item.category}${item.owner}${item.status}${item.metric}`
        .toLowerCase()
        .includes(search);
    return categoryMatches && keywordMatches;
  });
});

const healthyCount = computed(
  () => records.value.filter((item) => item.health === 'healthy').length,
);
const warningCount = computed(
  () => records.value.filter((item) => item.health === 'warning').length,
);
const offlineCount = computed(
  () => records.value.filter((item) => item.health === 'offline').length,
);

const columns: TableColumnsType<OperationRecord> = [
  { key: 'name', title: '名称', width: 300 },
  { dataIndex: 'category', key: 'category', title: '类型', width: 140 },
  { key: 'health', title: '健康状态', width: 120 },
  { dataIndex: 'metric', key: 'metric', title: '关键指标', width: 170 },
  { dataIndex: 'owner', key: 'owner', title: '负责人', width: 110 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 170 },
  { fixed: 'right', key: 'action', title: '操作', width: 190 },
];

const healthMeta = {
  healthy: { color: 'green', label: '正常' },
  offline: { color: 'red', label: '异常' },
  warning: { color: 'orange', label: '预警' },
} as const;

function getHealthMeta(health: unknown) {
  return healthMeta[health as OperationRecord['health']] ?? healthMeta.warning;
}

async function loadRecords() {
  loading.value = true;
  try {
    records.value = await getOperationsApi(domain.value);
  } catch (error) {
    records.value = [];
    message.error(
      error instanceof Error ? error.message : '运维数据加载失败，请稍后重试',
    );
  } finally {
    loading.value = false;
  }
}

function showDetail(record: Record<string, any>) {
  selectedRecord.value = record as OperationRecord;
  detailOpen.value = true;
}

function primaryAction(recordValue: Record<string, any>) {
  const record = recordValue as OperationRecord;
  if (record.health === 'offline') {
    record.health = 'warning';
    record.status = '正在重试';
    record.updatedAt = new Date().toLocaleString('zh-CN', { hour12: false });
    message.success('已创建重试任务，可在后台任务中查看进度');
    return;
  }
  if (record.category === '审批') {
    record.health = 'healthy';
    record.status = '已审批';
    record.updatedAt = new Date().toLocaleString('zh-CN', { hour12: false });
    message.success('审批已完成并写入操作记录');
    return;
  }
  message.success(`${record.name} 已完成健康检查`);
}

function createRecord() {
  if (!createForm.name.trim() || !createForm.category.trim()) {
    message.warning('请填写名称和类型');
    return;
  }
  records.value.unshift({
    category: createForm.category,
    health: 'healthy',
    id: `${domain.value}-${Date.now()}`,
    metric: createForm.metric || '待采集',
    name: createForm.name,
    owner: createForm.owner || '当前用户',
    status: '已创建',
    updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
  });
  Object.assign(createForm, { category: '', metric: '', name: '', owner: '' });
  createOpen.value = false;
  message.success('记录已创建');
}

function categoryLabel(category: string) {
  return category === 'all' ? '全部' : category;
}

onMounted(async () => {
  await restoreFromRoute();
  await loadRecords();
});
watch(domain, async () => {
  activeCategory.value = 'all';
  await commitQueryState();
  await loadRecords();
});
</script>

<template>
  <Page class="bg-slate-50" content-class="pb-6">
    <AdgenOperationsPanel
      v-if="isAdgen"
      :loading="loading"
      :records="records"
      @action="primaryAction"
      @inspect="showDetail"
      @refresh="loadRecords"
    />

    <div v-else class="w-full min-w-0 space-y-4">
      <header class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 items-start gap-3">
          <div
            class="bg-primary/10 text-primary flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--adpulse-card-radius)] text-lg"
          >
            <IconifyIcon :icon="pageMeta.icon" />
          </div>
          <div>
            <h1
              class="text-foreground mb-0 font-semibold text-[var(--adpulse-page-title-size)]"
            >
              {{ pageMeta.title }}
            </h1>
            <p class="mb-0 mt-1 max-w-3xl text-sm leading-6 text-slate-600">
              {{ pageMeta.description }}
            </p>
          </div>
        </div>
        <Space wrap>
          <Button :loading="loading" @click="loadRecords"
            ><template #icon><IconifyIcon icon="lucide:refresh-cw" /></template
            >刷新</Button
          >
          <Button type="primary" @click="createOpen = true"
            ><template #icon><IconifyIcon icon="lucide:plus" /></template
            >{{ isAdgen ? '新增资源' : '新增运营记录' }}</Button
          >
        </Space>
      </header>

      <Alert
        v-if="isAdgen"
        message="身份与页面权限由 Java 统一签发；此页只保留 AdGen 的模型、密钥、Worker 与运行态管理。"
        type="info"
        show-icon
      />
      <Alert
        v-else
        message="MPower 的 Task/Subtask 在统一模型中映射为 Project/DeliveryLine；租户、用户和角色不在此重复维护。"
        type="info"
        show-icon
      />

      <section class="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Card class="border-slate-200" :body-style="{ padding: '15px 16px' }"
          ><Statistic title="管理对象" :value="records.length"
        /></Card>
        <Card class="border-slate-200" :body-style="{ padding: '15px 16px' }"
          ><Statistic
            title="运行正常"
            :value="healthyCount"
            :value-style="{ color: '#047857' }"
        /></Card>
        <Card class="border-slate-200" :body-style="{ padding: '15px 16px' }"
          ><Statistic
            title="需要关注"
            :value="warningCount"
            :value-style="{ color: '#b45309' }"
        /></Card>
        <Card class="border-slate-200" :body-style="{ padding: '15px 16px' }"
          ><Statistic
            title="异常 / 待处理"
            :value="offlineCount"
            :value-style="{ color: '#b91c1c' }"
        /></Card>
      </section>

      <Card class="border-slate-200" :body-style="{ padding: 0 }">
        <div class="border-b border-slate-200 px-4 pt-2 sm:px-5">
          <Tabs v-model:active-key="activeCategory">
            <Tabs.TabPane
              v-for="category in categories"
              :key="category"
              :tab="categoryLabel(category)"
            />
          </Tabs>
        </div>
        <div
          class="flex flex-wrap items-center justify-between gap-3 p-4 sm:px-5"
        >
          <Input.Search
            v-model:value="keyword"
            allow-clear
            class="max-w-[420px] flex-1"
            placeholder="搜索名称、负责人、状态或指标"
          />
          <div class="text-xs text-slate-500">
            显示 {{ filteredRecords.length }} / {{ records.length }} 条
          </div>
        </div>
        <Table
          :columns="columns"
          :data-source="filteredRecords"
          :loading="loading"
          :pagination="{
            pageSize: 10,
            showTotal: (total: number) => `共 ${total} 条`,
          }"
          :scroll="{ x: 1200 }"
          row-key="id"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="flex min-w-0 items-center gap-3">
                <div
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
                >
                  <IconifyIcon
                    :icon="
                      isAdgen ? 'lucide:server' : 'lucide:briefcase-business'
                    "
                  />
                </div>
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-slate-900">
                    {{ record.name }}
                  </div>
                  <div class="mt-0.5 truncate text-xs text-slate-500">
                    {{ record.status }}
                  </div>
                </div>
              </div>
            </template>
            <template v-else-if="column.key === 'health'">
              <Tag :color="getHealthMeta(record.health).color">{{
                getHealthMeta(record.health).label
              }}</Tag>
            </template>
            <template v-else-if="column.key === 'action'">
              <Space :size="4">
                <Button type="link" @click="showDetail(record)">详情</Button>
                <Button type="link" @click="primaryAction(record)">
                  {{
                    record.health === 'offline'
                      ? '重试'
                      : record.category === '审批'
                        ? '审批'
                        : '检查'
                  }}
                </Button>
                <Button
                  v-if="
                    record.category === '交付报表' ||
                    record.category === '用量统计'
                  "
                  type="link"
                  @click="message.success('报表导出任务已创建')"
                  >导出</Button
                >
              </Space>
            </template>
          </template>
        </Table>
      </Card>

      <div class="grid gap-3 xl:grid-cols-2">
        <Card
          :title="isAdgen ? '运行态与成本' : '审批与交付'"
          class="border-slate-200"
        >
          <div class="space-y-4">
            <div
              v-for="metric in isAdgen
                ? [
                    { label: '模型调用成功率', value: 98 },
                    { label: 'Worker 在线率', value: 86 },
                    { label: '今日预算使用率', value: 63 },
                  ]
                : [
                    { label: '本周交付完成率', value: 92 },
                    { label: '账户审批及时率', value: 84 },
                    { label: '媒介资源可用率', value: 96 },
                  ]"
              :key="metric.label"
            >
              <div class="mb-1 flex justify-between text-xs text-slate-600">
                <span>{{ metric.label }}</span
                ><span>{{ metric.value }}%</span>
              </div>
              <Progress :percent="metric.value" :show-info="false" />
            </div>
          </div>
        </Card>
        <Card title="操作边界" class="border-slate-200">
          <div class="space-y-3 text-sm leading-6 text-slate-600">
            <div class="flex gap-2">
              <IconifyIcon
                icon="lucide:check-circle-2"
                class="mt-1 shrink-0 text-emerald-600"
              /><span>{{
                isAdgen
                  ? '模型与密钥仅保存脱敏标识，明文由安全存储管理。'
                  : '客户、项目、产品和正式广告账户均引用 Java 主数据。'
              }}</span>
            </div>
            <div class="flex gap-2">
              <IconifyIcon
                icon="lucide:check-circle-2"
                class="mt-1 shrink-0 text-emerald-600"
              /><span>{{
                isAdgen
                  ? '错误重试、Worker 扩缩容和模型切换均记录审计日志。'
                  : '审批、分配和交付动作必须保留操作人、时间与变更前后值。'
              }}</span>
            </div>
            <div class="flex gap-2">
              <IconifyIcon
                icon="lucide:shield-alert"
                class="mt-1 shrink-0 text-amber-600"
              /><span>{{
                isAdgen
                  ? 'Java 权限未映射的管理员能力默认不可用。'
                  : '不在 MPower 侧再创建第二套用户、租户与角色数据。'
              }}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>

    <Drawer
      v-model:open="detailOpen"
      :title="selectedRecord?.name"
      width="min(560px, 92vw)"
    >
      <template v-if="selectedRecord">
        <div class="flex items-center justify-between gap-3">
          <Tag :color="healthMeta[selectedRecord.health].color">{{
            healthMeta[selectedRecord.health].label
          }}</Tag>
          <span class="text-xs text-slate-500">{{
            selectedRecord.updatedAt
          }}</span>
        </div>
        <Divider />
        <Descriptions :column="1" bordered>
          <DescriptionsItem label="类型">{{
            selectedRecord.category
          }}</DescriptionsItem>
          <DescriptionsItem label="状态">{{
            selectedRecord.status
          }}</DescriptionsItem>
          <DescriptionsItem label="关键指标">{{
            selectedRecord.metric
          }}</DescriptionsItem>
          <DescriptionsItem label="负责人">{{
            selectedRecord.owner
          }}</DescriptionsItem>
          <DescriptionsItem label="资源 ID">{{
            selectedRecord.id
          }}</DescriptionsItem>
        </Descriptions>
        <h4 class="mb-2 mt-5 text-sm font-semibold text-slate-800">
          {{ isAdgen ? '运行配置' : '流程记录' }}
        </h4>
        <div
          class="rounded-lg bg-slate-50 p-4 text-sm leading-7 text-slate-600"
        >
          <template v-if="isAdgen">
            <div>作用域：production / {{ selectedRecord.category }}</div>
            <div>访问凭据：••••••••••••••91A2</div>
            <div>限流策略：每分钟 120 次，失败退避 3 次</div>
            <div>最近检查：{{ selectedRecord.updatedAt }}</div>
          </template>
          <template v-else>
            <div>创建：运营提交申请并绑定客户与项目</div>
            <div>审批：媒介负责人确认账户、额度与交付范围</div>
            <div>交付：写入广告资源并通知项目负责人</div>
            <div>审计：保留申请、审批与资源变更记录</div>
          </template>
        </div>
        <Button
          class="mt-5"
          block
          type="primary"
          @click="primaryAction(selectedRecord)"
          >{{
            selectedRecord.health === 'offline'
              ? '重试任务'
              : selectedRecord.category === '审批'
                ? '通过审批'
                : '立即健康检查'
          }}</Button
        >
      </template>
    </Drawer>

    <Modal
      v-model:open="createOpen"
      :title="isAdgen ? '新增运维资源' : '新增运营记录'"
      @ok="createRecord"
    >
      <Form layout="vertical">
        <FormItem label="名称" required
          ><Input
            v-model:value="createForm.name"
            placeholder="输入可识别的名称"
        /></FormItem>
        <FormItem label="类型" required>
          <Select
            v-model:value="createForm.category"
            :options="
              (isAdgen
                ? [
                    'Gemini Key',
                    '百炼 Key',
                    '系统访问 Key',
                    '用量统计',
                    '错误日志',
                    '媒体模型',
                    'Worker',
                  ]
                : ['渠道账户', '审批', '交付报表', '媒介资源']
              ).map((item) => ({ label: item, value: item }))
            "
          />
        </FormItem>
        <FormItem label="负责人"
          ><Input v-model:value="createForm.owner" placeholder="默认当前用户"
        /></FormItem>
        <FormItem label="指标或说明"
          ><Input
            v-model:value="createForm.metric"
            placeholder="例如剩余额度、账户数或审批事项"
        /></FormItem>
      </Form>
    </Modal>
  </Page>
</template>

<style scoped></style>
