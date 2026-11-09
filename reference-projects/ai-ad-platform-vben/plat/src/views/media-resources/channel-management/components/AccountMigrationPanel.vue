<script setup lang="ts">
import type { AssetMigrationItem, AssetMigrationJob } from '#/api/main';
import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { Button, Checkbox, Input, Select, Tag } from 'ant-design-vue';
import {
  createAssetMigrationPlan,
  executeAssetMigration,
  getAssetMigrationItems,
  getAssetMigrationJob,
  listAssetMigrationJobs,
} from '#/api/main';
import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';

defineProps<{ environment: 'PRODUCTION' | 'TEST' }>();
const emit = defineEmits<{ success: [] }>();
const job = ref<AssetMigrationJob>();
const jobs = ref<AssetMigrationJob[]>([]);
const taskId = ref('');
const busy = ref(false);
const error = ref('');
const detailError = ref('');
const inventory = ref(false);
const automatic = ref(false);
const rows = ref<AssetMigrationItem[]>([]);
const detailLoading = ref(false);
const filter = ref('');
const cursors = ref(['0']);
const next = ref<null | string>(null);
let timer: ReturnType<typeof setTimeout> | undefined;
let generation = 0;
let detailGeneration = 0;
let refreshSequence = 0;
let disposed = false;
const labels: Record<string, string> = {
  QUEUED: '预检中',
  READY: '待确认执行',
  VALIDATING: '执行前复核',
  APPLYING: '同步中',
  DONE: '已完成',
  DONE_WITH_ISSUES: '已完成，含隔离项',
  FAILED: '失败',
};
const actions: Record<string, string> = {
  INSERT: '新增',
  UPDATE: '更新',
  NOOP: '无需变更',
  UNCHANGED: '无需变更',
  ISOLATE: '隔离',
};
const itemStates: Record<string, string> = {
  PENDING: '待处理',
  DONE: '已完成',
  ISOLATED: '隔离',
};
const running = computed(() =>
  ['QUEUED', 'VALIDATING', 'APPLYING'].includes(job.value?.state ?? ''),
);
const canExecute = computed(
  () =>
    job.value?.state === 'READY' &&
    !!job.value.planHash &&
    inventory.value &&
    automatic.value &&
    !busy.value &&
    !error.value,
);
const columns: ShadcnDataTableColumn[] = [
  { key: 'accountId', title: '账户 ID', width: 170 },
  { key: 'desired', title: '计划写入的渠道 / 类型 / 属性', width: 260 },
  { key: 'before', title: '原有数据', width: 230 },
  { key: 'result', title: '处理结果', width: 220 },
];
function failure(value: unknown) {
  return value instanceof Error ? value.message : '请求失败，请重试';
}
function values(raw: null | string) {
  if (!raw) return '—';
  try {
    const value = JSON.parse(raw);
    return `渠道 ${value.channelId ?? '—'} · ${value.channelName ?? '—'} / ${value.accountType ?? '—'} / ${value.accountAttribute ?? '—'}`;
  } catch {
    return '明细无法解析';
  }
}
function stopPoll() {
  if (timer) clearTimeout(timer);
  timer = undefined;
}
async function history() {
  try {
    const result = await listAssetMigrationJobs();
    if (!disposed) jobs.value = result;
  } catch (e) {
    if (!disposed) error.value = failure(e);
  }
}
async function details(reset = false) {
  if (!job.value) return;
  if (reset) cursors.value = ['0'];
  const id = job.value.id;
  const token = ++detailGeneration;
  detailLoading.value = true;
  detailError.value = '';
  rows.value = [];
  next.value = null;
  try {
    const result = await getAssetMigrationItems(
      id,
      cursors.value.at(-1) ?? '0',
      filter.value || undefined,
    );
    if (disposed || token !== detailGeneration) return;
    rows.value = result.items;
    next.value = result.nextAfterId;
  } catch (e) {
    if (!disposed && token === detailGeneration) detailError.value = failure(e);
  } finally {
    if (!disposed && token === detailGeneration) detailLoading.value = false;
  }
}
function schedule(token: number) {
  if (disposed || token !== generation) return;
  stopPoll();
  if (!disposed && running.value && token === generation)
    timer = setTimeout(() => refresh(token), 3000);
}
async function refresh(token = generation) {
  if (!job.value || disposed) return;
  const id = job.value.id;
  const sequence = ++refreshSequence;
  stopPoll();
  try {
    const result = await getAssetMigrationJob(id);
    if (disposed || token !== generation) return;
    if (sequence !== refreshSequence) return;
    const changed = result.state !== job.value?.state;
    job.value = result;
    error.value = '';
    if (changed) {
      await details(true);
      if (['DONE', 'DONE_WITH_ISSUES'].includes(result.state)) emit('success');
      await history();
    }
  } catch (e) {
    if (!disposed && token === generation) error.value = failure(e);
  } finally {
    if (sequence === refreshSequence) schedule(token);
  }
}
async function choose(id: string) {
  if (busy.value || !id.trim()) return;
  const token = ++generation;
  ++detailGeneration;
  stopPoll();
  busy.value = true;
  error.value = '';
  job.value = undefined;
  rows.value = [];
  inventory.value = automatic.value = false;
  try {
    const result = await getAssetMigrationJob(id.trim());
    if (disposed || token !== generation) return;
    job.value = result;
    taskId.value = result.id;
    await details(true);
    schedule(token);
  } catch (e) {
    if (!disposed) error.value = failure(e);
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function create() {
  if (busy.value || running.value) return;
  const token = ++generation;
  stopPoll();
  busy.value = true;
  error.value = '';
  inventory.value = automatic.value = false;
  try {
    const result = await createAssetMigrationPlan();
    if (disposed || token !== generation) return;
    job.value = result;
    taskId.value = result.id;
    rows.value = [];
    await history();
    schedule(token);
  } catch (e) {
    if (!disposed) error.value = failure(e);
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function execute() {
  if (!canExecute.value || !job.value?.planHash) return;
  const token = generation;
  busy.value = true;
  error.value = '';
  try {
    const result = await executeAssetMigration(
      job.value.id,
      job.value.planHash,
    );
    if (disposed || token !== generation) return;
    job.value = result;
    inventory.value = automatic.value = false;
    schedule(token);
  } catch (e) {
    if (!disposed) {
      error.value = failure(e);
      // 请求超时时先查询持久化任务，避免误认为后台没有启动。
      await refresh(token);
    }
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function page(forward: boolean) {
  if (forward && next.value) cursors.value.push(next.value);
  else if (!forward && cursors.value.length > 1) cursors.value.pop();
  await details();
}
onMounted(async () => {
  await history();
  if (!disposed && jobs.value[0]) await choose(jobs.value[0].id);
});
onBeforeUnmount(() => {
  disposed = true;
  ++generation;
  ++detailGeneration;
  stopPoll();
});
</script>

<template>
  <section class="space-y-4">
    <Tag :color="environment === 'PRODUCTION' ? 'orange' : 'blue'"
      >目标：{{ environment === 'PRODUCTION' ? '生产' : '测试' }}环境</Tag
    >
    <p class="text-muted-foreground text-sm">
      先完成渠道同步，再预检账户。仅同步渠道 ID、渠道名称、账户
      ID、账户类型及账户属性。任务在后台执行，关闭页面后可通过任务记录继续查看。
    </p>
    <div class="flex flex-wrap gap-2">
      <Button :disabled="busy || running" @click="create">新建账户预检</Button>
      <Select
        class="min-w-64 flex-1"
        placeholder="最近 20 个任务"
        :value="job?.id"
        :disabled="busy"
        :options="
          jobs.map((item) => ({
            value: item.id,
            label: `${labels[item.state] ?? item.state} · ${item.id}`,
          }))
        "
        @change="(value) => choose(String(value))"
      />
      <Button :disabled="busy" @click="history">刷新记录</Button>
    </div>
    <div class="flex gap-2">
      <Input
        v-model:value="taskId"
        placeholder="输入已有任务 ID 找回进度"
        :disabled="busy"
        @press-enter="choose(taskId)"
      />
      <Button :disabled="busy || !taskId.trim()" @click="choose(taskId)"
        >查询任务</Button
      >
    </div>
    <p v-if="error" role="alert" class="text-destructive text-sm">
      {{ error }} <Button @click="refresh()">重查状态</Button>
    </p>
    <template v-if="job">
      <div class="bg-muted/30 space-y-3 rounded-lg border p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <Tag
            :color="
              job.state === 'FAILED'
                ? 'red'
                : job.state === 'DONE'
                  ? 'green'
                  : 'orange'
            "
            >{{ labels[job.state] ?? job.state }}</Tag
          >
          <span class="text-muted-foreground break-all text-xs">{{
            job.id
          }}</span>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
          <div>
            来源记录 <strong>{{ job.sourceCount }}</strong>
          </div>
          <div>
            计划账户 <strong>{{ job.total }}</strong>
          </div>
          <div>
            已处理 <strong>{{ job.completed }}</strong>
          </div>
          <div>
            隔离 <strong>{{ job.isolated }}</strong>
          </div>
          <div>
            重复来源 <strong>{{ job.duplicates }}</strong>
          </div>
        </div>
        <p v-if="job.error" role="alert" class="text-destructive text-sm">
          {{ job.error }}
        </p>
        <p v-if="job.state === 'FAILED'" class="text-muted-foreground text-sm">
          修复原因后重新预检。已提交的数据保留；新计划会重新比较当前数据。
        </p>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-2">
        <Select
          v-model:value="filter"
          class="w-40"
          :options="[
            { value: '', label: '全部明细' },
            { value: 'ISOLATED', label: '隔离明细' },
            { value: 'PENDING', label: '待处理' },
            { value: 'DONE', label: '已完成' },
          ]"
          @change="details(true)"
        />
        <Button :disabled="detailLoading" @click="details()">刷新明细</Button>
      </div>
      <p v-if="detailError" role="alert" class="text-destructive text-sm">
        {{ detailError }}
      </p>
      <div class="max-h-80 overflow-auto rounded-lg border">
        <div class="min-w-[880px]">
          <ShadcnDataTable
            :columns="columns"
            :data="rows"
            :loading="detailLoading"
            :paginate="false"
            row-key="id"
            empty-text="暂无符合条件的明细"
          >
            <template #cell-desired="{ record }"
              ><span class="whitespace-pre-wrap text-xs">{{
                values(record.desiredJson)
              }}</span></template
            >
            <template #cell-before="{ record }"
              ><span class="whitespace-pre-wrap text-xs">{{
                values(record.beforeJson)
              }}</span></template
            >
            <template #cell-result="{ record }"
              ><span class="text-xs"
                >{{ actions[record.action] ?? record.action }} ·
                {{ itemStates[record.state] ?? record.state }}<br />{{
                  record.reason
                }}</span
              ></template
            >
          </ShadcnDataTable>
        </div>
      </div>
      <div class="flex items-center justify-end gap-2 text-sm">
        <span>第 {{ cursors.length }} 页，每页最多 250 条</span>
        <Button
          :disabled="detailLoading || cursors.length <= 1"
          @click="page(false)"
          >上一页</Button
        >
        <Button :disabled="detailLoading || !next" @click="page(true)"
          >下一页</Button
        >
      </div>
      <div
        v-if="job.state === 'READY'"
        class="space-y-3 rounded-lg border p-4 text-sm"
      >
        <label class="flex items-start gap-2"
          ><Checkbox v-model:checked="inventory" :disabled="busy" /><span
            >确认写入{{
              environment === 'PRODUCTION' ? '生产' : '测试'
            }}环境；接受新增账户的默认库存状态 AVAILABLE（可用）。</span
          ></label
        >
        <label class="flex items-start gap-2"
          ><Checkbox v-model:checked="automatic" :disabled="busy" /><span
            >已审阅计划及隔离项，接受后续自动同步可能覆盖账户数据。</span
          ></label
        >
        <Button
          type="primary"
          :disabled="!canExecute"
          :loading="busy"
          @click="execute"
          >执行账户同步</Button
        >
      </div>
    </template>
  </section>
</template>
