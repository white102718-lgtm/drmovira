<script setup lang="ts">
import type {
  ProjectOperatingOverview,
  ProjectOperatingTask,
} from '#/api/fusion/types';
import type { AgencyLine } from '#/domain/agency-line';

import { IconifyIcon } from '@vben/icons';
import { computed, ref, watch } from 'vue';

import {
  Alert,
  Checkbox,
  Input,
  message,
  Modal,
  Pagination,
  Select,
  Tag,
} from 'ant-design-vue';

import Button from 'ant-design-vue/es/button';
import AntDataTable from '#/components/ui/AntDataTable.vue';
import { agencyLineService } from '#/domain/agency-line';
import {
  agencyLinesCsv,
  listAllProjectAgencyLines,
  listCompletedProjectTasks,
  setProjectAgencyLineStatus,
} from '#/domain/project/operating-detail';
import ProjectAgencyLineSyncModal from './ProjectAgencyLineSyncModal.vue';

const props = defineProps<{
  overview: ProjectOperatingOverview;
  agencyLineRevision?: number;
  canManage: boolean;
  regionLabel: (value: string) => string;
}>();
const emit = defineEmits<{
  adPanel: [];
  agencyAdPanel: [id: string, name: string];
  closure: [];
  comparison: [];
  createLine: [];
  createTask: [];
  statusChanged: [];
}>();

const project = computed(() => props.overview.project);
const mutable = computed(
  () =>
    props.canManage && !['ended', 'archived'].includes(project.value.status),
);
const platformLabels: Record<string, string> = {
  facebook: 'Facebook',
  google: 'Google',
  kwai: 'Kwai',
  tiktok: 'TikTok',
};
const statusLabels: Record<string, string> = {
  active: '进行中',
  archived: '已归档',
  draft: '草稿',
  ended: '已结束',
  paused: '已暂停',
  pending: '待启动',
};
const priorityLabels: Record<string, string> = {
  high: '高优先级',
  low: '低优先级',
  normal: '普通',
};
const lines = ref<AgencyLine[]>([]);
const linePage = ref(1);
const lineNameInput = ref('');
const lineNameFilter = ref('');
const lineTotal = ref(0);
const lineLoading = ref(false);
const lineError = ref('');
const selected = ref<string[]>([]);
const batchStatus = ref<'active' | 'stopped'>('stopped');
const updating = ref(false);
const exporting = ref(false);
const agencyLineSyncOpen = ref(false);
const tasks = ref<ProjectOperatingTask[]>([]);
const taskPage = ref(1);
const taskTotal = ref(0);
const taskLoading = ref(false);
const taskError = ref('');
let lineRequest = 0;
let taskRequest = 0;

const lineColumns = [
  { key: 'select', title: '选择', width: 56 },
  { key: 'optimizerName', title: '投手' },
  { key: 'platform', title: '投放平台' },
  { key: 'name', title: '代理线' },
  { key: 'pixelName', title: '像素名称' },
  { key: 'status', title: '状态' },
  { key: 'actions', title: '操作' },
];
const kpiColumns = [
  { key: 'metric', title: '指标' },
  { key: 'comparator', title: '条件' },
  { key: 'target', title: '目标' },
];
const kpis = computed(() =>
  (project.value.kpiRequirements ?? []).map((item, index) => ({
    ...item,
    key: index,
  })),
);
const productLinks = computed(() =>
  (project.value.productLinks ?? []).filter((link) => {
    try {
      return ['http:', 'https:'].includes(new URL(link).protocol);
    } catch {
      return false;
    }
  }),
);
const dailyReportLink = computed(() => {
  const link = project.value.customerDailyReportUrl;
  if (!link) return '';
  try {
    return ['http:', 'https:'].includes(new URL(link).protocol) ? link : '';
  } catch {
    return '';
  }
});
const amNames = computed(() => {
  const names = (project.value.amUsers ?? [])
    .map((item) => item.userName)
    .filter(Boolean);
  return names.length ? names.join('、') : project.value.amName || '未配置';
});
const dataSpecialistNames = computed(() => {
  const names = (project.value.dataSpecialists ?? [])
    .map((item) => item.userName)
    .filter(Boolean);
  return names.length
    ? names.join('、')
    : project.value.dataSpecialist || '未配置';
});
const walletAssets = computed(() => [
  { address: project.value.wallet?.ethAddress, label: 'ETH' },
  { address: project.value.wallet?.usdtAddress, label: 'USDT-TRC20' },
]);
const allSelected = computed(
  () =>
    lines.value.length > 0 &&
    lines.value.every((line) => selected.value.includes(line.id)),
);
const money = (amount: number) =>
  `${props.overview.currency || 'USD'} ${amount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
const dateTime = (value?: string) =>
  value ? value.replace('T', ' ').slice(0, 19) : '未记录';
const mask = (value?: string) =>
  !value
    ? '地址尚未同步'
    : value.length <= 12
      ? value
      : `${value.slice(0, 6)}••••••${value.slice(-6)}`;

async function copyAddress(address?: string) {
  if (!address) return;
  try {
    await navigator.clipboard.writeText(address);
    message.success('地址已复制');
  } catch {
    message.error('复制失败，请重试');
  }
}

/** 切换项目或翻页时只接受最新响应，避免旧项目数据覆盖新抽屉。 */
async function loadLines(page = linePage.value) {
  const request = ++lineRequest;
  lineLoading.value = true;
  lineError.value = '';
  selected.value = [];
  try {
    const result = await agencyLineService.list({
      lineName: lineNameFilter.value || undefined,
      projectId: project.value.id,
      page,
      pageSize: 10,
    });
    if (request !== lineRequest) return;
    lines.value = result.items;
    linePage.value = result.page;
    lineTotal.value = result.total;
  } catch (error) {
    if (request === lineRequest)
      lineError.value =
        error instanceof Error ? error.message : '代理线加载失败';
  } finally {
    if (request === lineRequest) lineLoading.value = false;
  }
}

/** 查询条件提交后从第一页加载，翻页和状态更新沿用已提交的名称。 */
function searchLines() {
  lineNameFilter.value = lineNameInput.value.trim();
  linePage.value = 1;
  void loadLines(1);
}

function resetLineSearch() {
  lineNameInput.value = '';
  searchLines();
}

async function loadTasks(page = taskPage.value) {
  const request = ++taskRequest;
  taskLoading.value = true;
  taskError.value = '';
  try {
    const result = await listCompletedProjectTasks(project.value.id, page, 10);
    if (request !== taskRequest) return;
    tasks.value = result.items;
    taskTotal.value = result.total;
    taskPage.value = result.page;
  } catch (error) {
    if (request === taskRequest)
      taskError.value = error instanceof Error ? error.message : '任务加载失败';
  } finally {
    if (request === taskRequest) taskLoading.value = false;
  }
}

function selectLine(id: string, checked: boolean) {
  selected.value = checked
    ? [...new Set([...selected.value, id])]
    : selected.value.filter((value) => value !== id);
}

function confirmStatus(ids: string[], status: 'active' | 'stopped') {
  if (!mutable.value || updating.value || !ids.length) return;
  const projectId = project.value.id;
  const submittedIds = [...ids];
  Modal.confirm({
    title: `将 ${submittedIds.length} 条代理线标记为${status === 'stopped' ? '已停投' : '进行中'}？`,
    content: '此操作仅更新项目内业务状态，不会暂停或启动媒体平台上的广告。',
    async onOk() {
      updating.value = true;
      try {
        await setProjectAgencyLineStatus(projectId, submittedIds, status);
        message.success('代理线状态已更新');
        if (projectId === project.value.id) await loadLines();
        emit('statusChanged');
      } finally {
        updating.value = false;
      }
    },
  });
}

async function exportLines() {
  exporting.value = true;
  const { id, projectCode } = project.value;
  try {
    const all = await listAllProjectAgencyLines(id);
    const url = URL.createObjectURL(
      new Blob([agencyLinesCsv(all)], { type: 'text/csv;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `${projectCode.replaceAll(/[\\/:*?"<>|]/g, '_')}-代理线.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导出失败');
  } finally {
    exporting.value = false;
  }
}

async function handleAgencyLineSynchronized() {
  await loadLines(1);
  emit('statusChanged');
}

watch(
  () => [project.value.id, props.agencyLineRevision] as const,
  ([projectId], previous) => {
    if (projectId !== previous?.[0]) {
      lineNameInput.value = '';
      lineNameFilter.value = '';
    }
    void loadLines(1);
  },
  { immediate: true },
);

watch(
  () => project.value.id,
  () => {
    lines.value = [];
    tasks.value = [];
    lineTotal.value = 0;
    taskTotal.value = 0;
    void loadTasks(1);
  },
  { immediate: true },
);
</script>

<template>
  <div class="text-foreground min-w-0 space-y-6">
    <section class="bg-muted/30 rounded-lg border p-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 class="m-0 break-words text-lg font-semibold">
            {{ project.name }}
          </h2>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            {{ project.projectCode }}
          </p>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            投放负责人：{{ project.deliveryLeaderName || '未记录' }}
          </p>
        </div>
        <Tag :color="project.status === 'active' ? 'green' : undefined">{{
          statusLabels[project.status] || project.status
        }}</Tag>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <Tag v-for="platform in project.platforms" :key="platform">{{
          platformLabels[platform] || platform
        }}</Tag>
        <Tag v-for="region in project.countryRegions" :key="region">{{
          regionLabel(region)
        }}</Tag>
      </div>
      <dl
        class="bg-card/70 mt-4 grid grid-cols-1 gap-x-6 gap-y-4 rounded-md border p-4 text-sm sm:grid-cols-2"
      >
        <div>
          <dt class="text-muted-foreground">负责团队</dt>
          <dd class="mb-0 mt-1 break-words font-medium">
            {{ project.responsibleTeam || '未配置' }}
          </dd>
        </div>
        <div>
          <dt class="text-muted-foreground">AM</dt>
          <dd class="mb-0 mt-1 break-words font-medium">{{ amNames }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground">数据专员</dt>
          <dd class="mb-0 mt-1 break-words font-medium">
            {{ dataSpecialistNames }}
          </dd>
        </div>
        <div>
          <dt class="text-muted-foreground">优先级</dt>
          <dd class="mb-0 mt-1 font-medium">
            {{ priorityLabels[project.priority ?? ''] || '未配置' }}
          </dd>
        </div>
        <div>
          <dt class="text-muted-foreground">是否外包</dt>
          <dd class="mb-0 mt-1 font-medium">
            {{ project.isOutsourced ? '是' : '否' }}
          </dd>
        </div>
        <div v-if="project.isOutsourced">
          <dt class="text-muted-foreground">外包团队</dt>
          <dd class="mb-0 mt-1 break-words font-medium">
            {{ project.outsourcingTeams?.join('、') || '未配置' }}
          </dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-muted-foreground">项目基础信息</dt>
          <dd class="mb-0 mt-1 whitespace-pre-wrap break-words font-medium">
            {{ project.productInfo ?? project.productName }}
          </dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-muted-foreground">产品链接</dt>
          <dd
            v-if="productLinks.length"
            class="mb-0 mt-1 flex flex-col items-start gap-1.5"
          >
            <div
              v-for="(link, index) in productLinks"
              :key="`${index}-${link}`"
              class="flex min-w-0 max-w-full items-center gap-1"
            >
              <span class="min-w-0 truncate" :title="link">{{ link }}</span>
              <Button
                type="link"
                :href="link"
                target="_blank"
                rel="noopener noreferrer"
                class="w-7 shrink-0 p-0"
                :aria-label="`打开产品链接 ${index + 1}`"
                :title="`打开产品链接 ${index + 1}`"
              >
                <IconifyIcon icon="lucide:external-link" class="size-4" />
              </Button>
            </div>
          </dd>
          <dd v-else class="text-muted-foreground mb-0 mt-1">未配置</dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-muted-foreground">产品日报链接</dt>
          <dd
            v-if="dailyReportLink"
            class="mb-0 mt-1 flex min-w-0 items-center gap-1"
          >
            <span class="min-w-0 truncate" :title="dailyReportLink">
              {{ dailyReportLink }}
            </span>
            <Button
              type="link"
              :href="dailyReportLink"
              target="_blank"
              rel="noopener noreferrer"
              class="w-7 shrink-0 p-0"
              aria-label="打开产品日报链接"
              title="打开产品日报链接"
            >
              <IconifyIcon icon="lucide:external-link" class="size-4" />
            </Button>
          </dd>
          <dd v-else class="text-muted-foreground mb-0 mt-1">未配置</dd>
        </div>
      </dl>
      <Button class="mt-3" @click="emit('comparison')">查看环比分析</Button>
    </section>

    <section class="bg-card overflow-hidden rounded-lg border">
      <h3 class="m-0 border-b px-4 py-3 text-base font-semibold">预算与 KPI</h3>
      <div class="space-y-4 p-4">
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div class="bg-muted/40 rounded-md p-3">
            <div class="text-muted-foreground text-xs">日预算</div>
            <div class="mt-1 font-medium">{{ money(0) }}</div>
          </div>
          <div class="bg-muted/40 rounded-md p-3">
            <div class="text-muted-foreground text-xs">归因窗口</div>
            <div class="mt-1 font-medium">未接入</div>
          </div>
        </div>
        <AntDataTable
          :columns="kpiColumns"
          :data="kpis"
          row-key="key"
          :paginate="false"
          empty-text="暂未配置 KPI"
        >
          <template #cell-comparator="{ record }">{{
            record.comparator === 'between' ? '介于' : record.comparator
          }}</template>
          <template #cell-target="{ record }"
            >{{ record.target ?? '待设置'
            }}<template v-if="record.comparator === 'between'">
              ～ {{ record.targetMax ?? '待设置' }}</template
            ></template
          >
        </AntDataTable>
      </div>
    </section>

    <section class="bg-card rounded-lg border">
      <h3 class="m-0 border-b px-4 py-3 text-base font-semibold">钱包信息</h3>
      <div v-if="project.wallet" class="space-y-3 p-4">
        <div
          v-for="asset in walletAssets"
          :key="asset.label"
          class="flex flex-wrap items-center gap-2 rounded-md border p-3"
        >
          <Tag>{{ asset.label }}</Tag
          ><span class="min-w-0 flex-1 break-all font-mono text-xs">{{
            mask(asset.address)
          }}</span>
          <Tag>手续费：{{ project.wallet.feeUnit }}</Tag>
          <Button
            :disabled="!asset.address"
            :aria-label="`复制 ${asset.label} 地址`"
            @click="copyAddress(asset.address)"
            >复制</Button
          >
        </div>
      </div>
      <p v-else class="text-muted-foreground m-0 p-4 text-sm">
        该项目尚未创建钱包。
      </p>
    </section>

    <section class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <article class="bg-card flex flex-col items-start rounded-lg border p-4">
        <div class="text-muted-foreground text-xs">累计消耗</div>
        <div class="mt-2 text-lg font-semibold">
          {{
            overview.dataQualityStatus === 'missing'
              ? '—'
              : money(overview.actualSpend)
          }}
        </div>
        <div class="text-muted-foreground mt-1 text-xs">
          {{
            overview.dataQualityStatus === 'missing'
              ? '暂未接入'
              : '累计广告消耗（USD）'
          }}
        </div>
        <div class="mt-auto pt-2">
          <Button
            type="link"
            class="justify-start px-0"
            @click="emit('adPanel')"
            >查看广告面板数据 ↗</Button
          >
        </div>
      </article>
      <article class="bg-card rounded-lg border p-4">
        <div class="text-muted-foreground text-xs">项目服务费已收</div>
        <div class="mt-2 text-lg font-semibold">{{ money(0) }}</div>
        <div class="text-muted-foreground mt-2 text-xs">
          服务费比例 {{ project.serviceFeePercent ?? 0 }}%
        </div>
        <div class="text-muted-foreground mt-1 text-xs">
          待收 {{ money(0) }} · 暂未接入
        </div>
      </article>
      <article class="bg-card flex flex-col items-start rounded-lg border p-4">
        <div class="text-muted-foreground text-xs">结算状态</div>
        <div
          v-if="overview.settledAmounts === undefined"
          class="text-muted-foreground mt-2 text-xs"
        >
          已结算：汇总暂不可用
        </div>
        <div
          v-else-if="!overview.settledAmounts.length"
          class="text-muted-foreground mt-2 text-xs"
        >
          已结算 {{ money(0) }} · 暂无已完成结项记录
        </div>
        <div
          v-for="item in overview.settledAmounts"
          :key="item.currency"
          class="text-muted-foreground mt-2 text-xs"
        >
          已结算 {{ item.currency }}
          {{
            Number(item.amount).toLocaleString('zh-CN', {
              maximumFractionDigits: 2,
            })
          }}
        </div>
        <div class="mt-auto pt-2">
          <Button
            type="link"
            class="justify-start px-0"
            @click="emit('closure')"
            >发起结项结算 ↗</Button
          >
        </div>
      </article>
    </section>

    <section class="bg-card min-w-0 rounded-lg border">
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-b p-4"
      >
        <h3 class="m-0 text-base font-semibold">代理线</h3>
        <div class="flex flex-wrap items-center gap-2">
          <Button @click="agencyLineSyncOpen = true">代理线链接</Button>
          <Button v-if="mutable" @click="emit('createLine')"
            >＋ 新建代理线</Button
          >
          <Button
            :loading="exporting"
            :disabled="lineTotal === 0 || lineLoading || !!lineError"
            @click="exportLines"
            >导出</Button
          >
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2 border-b p-4">
        <label for="project-agency-line-name" class="whitespace-nowrap text-sm"
          >代理线名称</label
        >
        <Input
          id="project-agency-line-name"
          v-model:value="lineNameInput"
          placeholder="输入代理线名称关键词"
          class="w-full sm:w-64"
          @press-enter="searchLines"
        />
        <Button :loading="lineLoading" @click="searchLines">查询</Button>
        <Button @click="resetLineSearch">重置</Button>
      </div>
      <div
        v-if="mutable && selected.length"
        class="flex flex-wrap items-center gap-2 border-b p-4"
      >
        <span class="text-sm">已选 {{ selected.length }} 条</span>
        <Select
          v-model:value="batchStatus"
          aria-label="批量代理线状态"
          :disabled="updating"
          :options="[
            { label: '进行中', value: 'active' },
            { label: '已停投', value: 'stopped' },
          ]"
          class="w-32"
        />
        <Button
          :loading="updating"
          @click="confirmStatus(selected, batchStatus)"
          >批量修改状态</Button
        >
      </div>
      <div v-if="lineError" class="p-4">
        <Alert type="error" :message="lineError" /><Button
          class="mt-3"
          @click="loadLines()"
          >重新加载</Button
        >
      </div>
      <AntDataTable
        v-else
        :columns="lineColumns"
        :data="lines"
        :loading="lineLoading"
        :paginate="false"
        row-key="id"
        :empty-text="lineNameFilter ? '未找到匹配的代理线' : '暂未绑定代理线'"
      >
        <template #header-select
          ><Checkbox
            :checked="allSelected"
            :disabled="!mutable || updating || lineLoading || !lines.length"
            :indeterminate="selected.length > 0 && !allSelected"
            aria-label="选择当前页全部代理线"
            @change="
              selected = $event.target.checked
                ? lines.map((line) => line.id)
                : []
            "
        /></template>
        <template #cell-select="{ record }"
          ><Checkbox
            :checked="selected.includes(record.id)"
            :disabled="!mutable || updating"
            :aria-label="`选择代理线 ${record.name}`"
            @change="selectLine(record.id, !!$event.target.checked)"
        /></template>
        <template #cell-platform="{ record }"
          ><Tag>{{
            platformLabels[record.platform] || record.platform
          }}</Tag></template
        >
        <template #cell-name="{ record }"
          ><Button
            class="ux-table-link"
            type="link"
            @click="emit('agencyAdPanel', record.id, record.name)"
            >{{ record.name }} ↗</Button
          ></template
        >
        <template #cell-optimizerName="{ record }">
          {{ record.optimizerName || '未分配' }}
          <span v-if="record.optimizerStatus === 0">（已停用）</span>
        </template>
        <template #cell-pixelName="{ record }">{{
          record.pixelName || '未配置'
        }}</template>
        <template #cell-status="{ record }"
          ><Tag :color="record.status === 'stopped' ? undefined : 'green'">{{
            record.status === 'stopped' ? '已停投' : '进行中'
          }}</Tag></template
        >
        <template #cell-actions="{ record }"
          ><Button
            :disabled="!mutable || updating"
            @click="
              confirmStatus(
                [record.id],
                record.status === 'stopped' ? 'active' : 'stopped',
              )
            "
            >{{ record.status === 'stopped' ? '恢复进行中' : '停投' }}</Button
          ></template
        >
      </AntDataTable>
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-t p-4"
      >
        <span class="text-muted-foreground text-xs"
          >共 {{ lineTotal }} 条代理线</span
        ><Pagination
          :current="linePage"
          :total="lineTotal"
          :page-size="10"
          :show-size-changer="false"
          :disabled="lineLoading || updating"
          @change="loadLines"
        />
      </div>
    </section>

    <ProjectAgencyLineSyncModal
      v-model:open="agencyLineSyncOpen"
      :project-id="project.id"
      :link="project.agencyLineUrl"
      :can-synchronize="mutable"
      @synchronized="handleAgencyLineSynchronized"
    />

    <section class="bg-card rounded-lg border">
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-b p-4"
      >
        <h3 class="m-0 text-base font-semibold">已完成任务</h3>
        <Button v-if="mutable" type="primary" @click="emit('createTask')"
          >＋ 创建投放任务</Button
        >
      </div>
      <div v-if="taskError" class="p-4">
        <Alert type="error" :message="taskError" /><Button
          class="mt-3"
          @click="loadTasks()"
          >重新加载</Button
        >
      </div>
      <div
        v-else-if="taskLoading"
        class="text-muted-foreground p-6 text-center text-sm"
        role="status"
      >
        正在加载任务…
      </div>
      <div v-else-if="tasks.length" class="divide-y px-4">
        <article v-for="task in tasks" :key="task.id" class="py-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="break-words font-medium">{{ task.title }}</div>
              <div class="text-muted-foreground mt-1 break-words text-xs">
                {{ task.taskCode || task.id }} ·
                {{ task.ownerName || '未分配' }}
              </div>
            </div>
            <Tag class="shrink-0">{{
              task.kind === 'delivery' ? '投放任务' : '素材任务'
            }}</Tag>
          </div>
          <div class="text-muted-foreground mt-2 text-xs">
            完成于 {{ dateTime(task.completedAt) }}
          </div>
        </article>
      </div>
      <p v-else class="text-muted-foreground m-0 p-6 text-center text-sm">
        暂无已完成的投放任务或素材任务
      </p>
      <div
        class="flex flex-wrap items-center justify-between gap-3 border-t p-4"
      >
        <span class="text-muted-foreground text-xs"
          >共 {{ taskTotal }} 条已完成任务</span
        ><Pagination
          :current="taskPage"
          :total="taskTotal"
          :page-size="10"
          :show-size-changer="false"
          :disabled="taskLoading"
          @change="loadTasks"
        />
      </div>
    </section>
  </div>
</template>
