<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Progress,
  Row,
  Segmented,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { useProjectContextStore, useWorkflowStore } from '#/store';

interface ExperimentRow {
  id: string;
  name: string;
  parentVersion: string;
  platforms: string[];
  result: string;
  roasLift: number;
  status: 'draft' | 'learning' | 'won';
  variants: number;
  winner: string;
}

const router = useRouter();
const projectStore = useProjectContextStore();
const workflowStore = useWorkflowStore();
const period = ref('近 7 天');

const experiments = ref<ExperimentRow[]>([
  {
    id: 'exp-1048',
    name: '首充福利开场结构裂变',
    parentVersion: 'MAT-2088 / V4',
    platforms: ['Facebook', 'TikTok'],
    result: '短开场 + 价格锚点胜出',
    roasLift: 18.6,
    status: 'won',
    variants: 12,
    winner: 'MAT-2088 / V7',
  },
  {
    id: 'exp-1047',
    name: '日本像素角色卖点测试',
    parentVersion: 'MAT-1992 / V2',
    platforms: ['TikTok'],
    result: '仍在学习，样本量 63%',
    roasLift: 4.2,
    status: 'learning',
    variants: 8,
    winner: '-',
  },
  {
    id: 'exp-1046',
    name: '末日基地素材二次创意',
    parentVersion: 'MAT-1831 / V5',
    platforms: ['Google', 'Facebook'],
    result: '等待确认变量与预算',
    roasLift: 0,
    status: 'draft',
    variants: 6,
    winner: '-',
  },
]);

const statusMeta = {
  draft: { color: 'default', label: '草稿' },
  learning: { color: 'blue', label: '学习中' },
  won: { color: 'green', label: '已选胜出版本' },
};

const projectEvents = computed(() =>
  workflowStore.getProjectEvents(projectStore.selectedProjectId),
);

const secondCreativeEventIndex = computed(() =>
  projectEvents.value.findIndex(
    (event) => event.type === 'second_creative_started',
  ),
);

const eventsAfterSecondCreative = computed(() =>
  secondCreativeEventIndex.value < 0
    ? []
    : projectEvents.value.slice(0, secondCreativeEventIndex.value),
);

const hasSecondApproval = computed(() =>
  eventsAfterSecondCreative.value.some(
    (event) => event.type === 'material_approved',
  ),
);

const hasSecondPublish = computed(() => {
  return (
    hasSecondApproval.value &&
    eventsAfterSecondCreative.value.some(
      (event) => event.type === 'ad_published',
    )
  );
});

const closureSteps = computed(() => [
  { done: true, label: '效果回流' },
  {
    done: experiments.value.some((item) => item.status === 'won'),
    label: '选出胜者',
  },
  {
    done: projectEvents.value.some(
      (event) => event.type === 'second_creative_started',
    ),
    label: '二次创意',
  },
  {
    done: hasSecondApproval.value,
    label: '审核可投',
  },
  {
    done: hasSecondPublish.value,
    label: '二次投放',
  },
]);

const closurePercent = computed(() =>
  Math.round(
    (closureSteps.value.filter((item) => item.done).length /
      closureSteps.value.length) *
      100,
  ),
);

const stats = computed(() => [
  { label: '在途实验', value: 7, suffix: '个' },
  { label: '已选胜出素材', value: 16, suffix: '个' },
  { label: '平均 ROAS 提升', value: 13.8, suffix: '%' },
  {
    label: '当前项目发布任务',
    value: projectEvents.value.filter((event) => event.type === 'ad_published')
      .length,
    suffix: '个',
  },
]);

const columns: TableColumnsType<ExperimentRow> = [
  { key: 'experiment', title: '实验', width: 270 },
  {
    dataIndex: 'parentVersion',
    key: 'parentVersion',
    title: '父素材版本',
    width: 170,
  },
  { dataIndex: 'variants', key: 'variants', title: '变体数', width: 90 },
  { key: 'platforms', title: '投放平台', width: 190 },
  { key: 'result', title: '当前结论', width: 250 },
  { key: 'status', title: '状态', width: 150 },
  { key: 'actions', title: '下一步', width: 220, fixed: 'right' },
];

function startSecondCreative(row: ExperimentRow | Record<string, any>) {
  const current = row as ExperimentRow;
  router.push({
    path: '/fusion/ai-studio',
    query: {
      capability: 'material-replicate',
      sourceVersion:
        current.winner === '-' ? current.parentVersion : current.winner,
    },
  });
}

function publishWinner(row: ExperimentRow | Record<string, any>) {
  const current = row as ExperimentRow;
  if (current.winner === '-') return;
  router.push({
    path: '/fusion/ads/create',
    query: {
      materialVersion: current.winner,
      source: 'winning-experiment',
    },
  });
}
</script>

<template>
  <Page class="adpulse-section-page bg-slate-50" content-class="pb-6">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section
        class="flex flex-col justify-between gap-4 lg:flex-row lg:items-end"
      >
        <div>
          <h1 class="m-0 text-2xl font-semibold text-slate-950">复盘与实验</h1>
          <p class="mb-0 mt-2 text-sm leading-6 text-slate-600">
            从具体 MaterialVersion
            的真实投放表现选出胜出版本，发起二次创意并完成二次投放。
          </p>
        </div>
        <Segmented
          v-model:value="period"
          :options="['近 7 天', '近 14 天', '近 30 天']"
        />
      </section>

      <Alert
        message="归因必须绑定广告与具体素材版本；动态创意需保存平台回传的 creative asset 映射，不能只看 Material 累计值。"
        type="info"
        show-icon
      />

      <Row :gutter="[12, 12]">
        <Col v-for="item in stats" :key="item.label" :xs="12" :lg="6">
          <Card class="border-slate-200" :body-style="{ padding: '16px' }">
            <Statistic
              :title="item.label"
              :value="item.value"
              :suffix="item.suffix"
            />
          </Card>
        </Col>
      </Row>

      <Row :gutter="[16, 16]">
        <Col :xs="24" :xl="16">
          <Card title="二次创意闭环" class="h-full border-slate-200">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div
                v-for="(item, index) in closureSteps"
                :key="item.label"
                class="rounded-lg border p-4"
                :class="
                  item.done
                    ? 'border-green-200 bg-green-50'
                    : 'border-slate-200 bg-slate-50'
                "
              >
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold text-sky-700"
                    >0{{ index + 1 }}</span
                  >
                  <IconifyIcon
                    :icon="
                      item.done
                        ? 'lucide:circle-check-big'
                        : 'lucide:circle-dashed'
                    "
                    :class="item.done ? 'text-green-600' : 'text-slate-400'"
                  />
                </div>
                <div class="mt-3 text-sm font-semibold text-slate-900">
                  {{ item.label }}
                </div>
                <div
                  class="mt-1 text-xs"
                  :class="item.done ? 'text-green-700' : 'text-slate-500'"
                >
                  {{ item.done ? '已完成' : '待完成' }}
                </div>
              </div>
            </div>
            <div class="mt-5">
              <div class="mb-2 flex justify-between text-xs text-slate-600">
                <span>当前前端演示链路完成度</span>
                <span>{{ closurePercent }}%</span>
              </div>
              <Progress
                :percent="closurePercent"
                :show-info="false"
                stroke-color="#0369a1"
              />
            </div>
          </Card>
        </Col>
        <Col :xs="24" :xl="8">
          <Card title="本期建议" class="h-full border-slate-200">
            <div class="space-y-3">
              <div class="rounded-lg bg-green-50 p-3">
                <div class="text-sm font-semibold text-green-900">
                  扩大胜出结构
                </div>
                <div class="mt-1 text-xs leading-5 text-green-800">
                  “短开场 + 价格锚点”已超过样本门槛，可进入二次裂变。
                </div>
              </div>
              <div class="rounded-lg bg-amber-50 p-3">
                <div class="text-sm font-semibold text-amber-900">
                  继续收集样本
                </div>
                <div class="mt-1 text-xs leading-5 text-amber-800">
                  日本像素角色实验尚未达到正式结论所需样本量。
                </div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Card
        v-if="projectEvents.length"
        title="当前项目最近闭环动作"
        class="border-slate-200"
      >
        <div class="grid gap-2 lg:grid-cols-3">
          <div
            v-for="event in projectEvents.slice(0, 6)"
            :key="event.id"
            class="rounded-lg border border-slate-200 bg-slate-50 p-3"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="text-sm font-medium text-slate-900">
                {{ event.title }}
              </div>
              <Tag :color="event.status === 'completed' ? 'green' : 'blue'">{{
                event.status === 'completed' ? '已完成' : '处理中'
              }}</Tag>
            </div>
            <div class="mt-1 text-xs leading-5 text-slate-600">
              {{ event.description }}
            </div>
            <div class="mt-2 text-[11px] text-slate-400">
              {{ event.createdAt }}
            </div>
          </div>
        </div>
      </Card>

      <Card
        title="素材实验列表"
        class="border-slate-200"
        :body-style="{ padding: 0 }"
      >
        <Table
          :columns="columns"
          :data-source="experiments"
          :pagination="false"
          :row-key="(row: ExperimentRow) => row.id"
          :scroll="{ x: 1350 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'experiment'">
              <div class="font-medium text-slate-900">{{ record.name }}</div>
              <div class="mt-1 text-xs text-slate-500">{{ record.id }}</div>
            </template>
            <template v-else-if="column.key === 'platforms'">
              <Tag
                v-for="platform in record.platforms"
                :key="platform"
                color="blue"
              >
                {{ platform }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'result'">
              <div class="text-sm text-slate-700">{{ record.result }}</div>
              <div
                v-if="record.roasLift"
                class="mt-1 text-xs font-medium text-green-700"
              >
                ROAS +{{ record.roasLift }}%
              </div>
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag
                :color="
                  statusMeta[record.status as ExperimentRow['status']].color
                "
              >
                {{ statusMeta[record.status as ExperimentRow['status']].label }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'actions'">
              <Button type="link" @click="startSecondCreative(record)"
                >二次创意</Button
              >
              <Tooltip
                :title="
                  record.winner === '-'
                    ? '需先达到样本门槛并确认胜出素材版本'
                    : ''
                "
              >
                <span>
                  <Button
                    :disabled="record.winner === '-'"
                    type="link"
                    @click="publishWinner(record)"
                    >二次投放</Button
                  >
                </span>
              </Tooltip>
            </template>
          </template>
        </Table>
      </Card>
    </div>
  </Page>
</template>
