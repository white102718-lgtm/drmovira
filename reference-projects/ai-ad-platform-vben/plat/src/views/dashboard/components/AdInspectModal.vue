<script lang="ts">
import { ref } from 'vue';

// 模块级: 页面不整刷时记住上次查看的是配置/记录/下钻, 默认下钻
const mode = ref<'config' | 'drill' | 'records'>('drill');
// 模块级: 下钻日期范围跨弹窗保留, 首次打开才用行所在日期初始化
const drillRange = ref<[number, number] | null>(null);
</script>

<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';

import type { AdConfigLevel, AdOperationRecord } from '#/api';

import { computed } from 'vue';

import {
  Button,
  Checkbox,
  message,
  Modal,
  RadioButton,
  RadioGroup,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAdDrill, viewAdConfig, viewAdOperations } from '#/api';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import ListLoading from '#/views/components/ListLoading.vue';

// 状态/投放状态 tag 配色, 复用广告面板同款文案与颜色(三级映射的并集)
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  ACTIVE: { text: '投放中', color: 'green' },
  PAUSED: { text: '已暂停', color: 'orange' },
  CAMPAIGN_PAUSED: { text: '系列暂停', color: 'orange' },
  ADSET_PAUSED: { text: '组暂停', color: 'orange' },
  IN_PROCESS: { text: '处理中', color: 'blue' },
  WITH_ISSUES: { text: '有问题', color: 'red' },
  DISAPPROVED: { text: '已拒绝', color: 'red' },
  PENDING_REVIEW: { text: '待审核', color: 'cyan' },
  PENDING_BILLING_INFO: { text: '待结算信息', color: 'orange' },
  PREAPPROVED: { text: '预审通过', color: 'blue' },
  ARCHIVED: { text: '已归档', color: 'gray' },
  DELETED: { text: '已删除', color: 'gray' },
};

// 学习期状态 → 文案, 与广告面板 learningStageMap 同款配色
const LEARNING_STAGE_TAG: Record<string, { color: string; text: string }> = {
  LEARNING: { text: '学习中', color: 'blue' },
  SUCCESS: { text: '学习结束', color: 'green' },
  FAIL: { text: '机器学习受限', color: 'orange' },
  WAIVING: { text: '不适用', color: 'default' },
};

// 账户状态数字码 → 文案, 复用广告面板 accountStatusMap 同款
const ACCOUNT_STATUS_TAG: Record<string, { color: string; text: string }> = {
  1: { text: '正常', color: 'green' },
  2: { text: '已停用', color: 'red' },
  3: { text: '账单未结清', color: 'red' },
  7: { text: '待风险审核', color: 'orange' },
  8: { text: '待结算', color: 'orange' },
  9: { text: '宽限期', color: 'orange' },
  100: { text: '待关闭', color: 'gray' },
  101: { text: '已关闭', color: 'gray' },
};

const MODE_TITLE = {
  config: '对象配置',
  records: '操作记录',
  drill: '半小时明细',
} as const;

const open = ref(false);
const show1d = ref(true);
const target = ref<null | {
  date: string;
  level: AdConfigLevel;
  object_id: string;
}>(null);

// 配置
const cfgLoading = ref(false);
const cfgPending = ref(false);
const cfgFetched = ref(false);
const objectData = ref<any>(null);
// 整棵树:附带展示下级组/广告的配置(仅系列/组层级有下级)
const showTree = ref(false);
const childrenData = ref<any[]>([]);

// 记录
const recLoading = ref(false);
const recPending = ref(false);
const recFetched = ref(false);
const records = ref<AdOperationRecord[]>([]);
const snapshotColumns = ref<string[]>([]);
const lastPull = ref<null | string>(null);
const foundDate = ref<null | string>(null);
const probeDate = ref<null | string>(null);
const noRecentDays = ref<null | number>(null);
let recPollTimer: null | ReturnType<typeof setTimeout> = null;

// 下钻(后端分页, 每页固定 100)
const DRILL_PAGE_SIZE = 100;
const drillLoading = ref(false);
const drillFetched = ref(false);
const drillRows = ref<Record<string, any>[]>([]);
const drillColumns = ref<string[]>([]);
const drillPage = ref(1);
const drillTotal = ref(0);

const fetchConfig = async () => {
  if (!target.value) return;
  cfgLoading.value = true;
  try {
    const res = await viewAdConfig({
      level: target.value.level,
      object_id: target.value.object_id,
      include_children: showTree.value,
    });
    cfgFetched.value = true;
    if (res?.status === 'done') {
      cfgPending.value = false;
      objectData.value = res.object;
      childrenData.value = res.children ?? [];
    } else {
      cfgPending.value = true;
      objectData.value = null;
      childrenData.value = [];
    }
  } finally {
    cfgLoading.value = false;
  }
};

// 常规查询从所选天逐天回溯到最近有操作的天; 回溯中遇到未缓存的天后端返回 pending, 轮询推进
const fetchRecords = async (force = false) => {
  if (!target.value) return;
  recLoading.value = true;
  try {
    const res = await viewAdOperations({
      level: target.value.level,
      object_id: target.value.object_id,
      // 强制重拉针对当前展示的那天
      date: force ? (foundDate.value ?? target.value.date) : target.value.date,
      force,
      find_latest: !force,
    });
    recFetched.value = true;
    lastPull.value = res.updated_at ?? null;
    if (res?.status === 'done') {
      recPending.value = false;
      probeDate.value = null;
      records.value = res.records ?? [];
      snapshotColumns.value = res.snapshot_columns ?? [];
      if (!force) {
        foundDate.value = res.found_date ?? null;
        noRecentDays.value = res.found_date
          ? null
          : (res.searched_days ?? null);
      }
    } else {
      recPending.value = true;
      probeDate.value = res.probe_date ?? null;
      records.value = [];
      scheduleRecordsPoll();
    }
    if (force) message.success('已强制触发重新拉取,请稍后点刷新');
  } finally {
    recLoading.value = false;
  }
};

const scheduleRecordsPoll = () => {
  if (recPollTimer) clearTimeout(recPollTimer);
  recPollTimer = setTimeout(() => {
    recPollTimer = null;
    if (open.value && mode.value === 'records' && recPending.value)
      fetchRecords();
  }, 4000);
};

const fetchDrill = async (page = 1) => {
  if (!target.value || !drillRange.value) return;
  drillLoading.value = true;
  try {
    const res = await getAdDrill({
      level: target.value.level,
      object_id: target.value.object_id,
      date: dayjs(drillRange.value[0]).format('YYYY-MM-DD'),
      end_date: dayjs(drillRange.value[1]).format('YYYY-MM-DD'),
      page,
      page_size: DRILL_PAGE_SIZE,
      show_1d: show1d.value,
    });
    drillFetched.value = true;
    drillPage.value = page;
    drillTotal.value = res.total ?? 0;
    drillRows.value = res.data ?? [];
    drillColumns.value = res.columns ?? [];
  } finally {
    drillLoading.value = false;
  }
};

// 切换 radio 时: 当前 mode 的数据没拉过就拉一次
const ensureData = () => {
  if (mode.value === 'config') {
    if (!cfgFetched.value) fetchConfig();
  } else if (mode.value === 'records') {
    if (!recFetched.value) fetchRecords();
  } else if (!drillFetched.value) {
    fetchDrill();
  }
};

const openModal = (
  level: AdConfigLevel,
  objectId: string,
  date: string,
  show_1d = true,
) => {
  target.value = { level, object_id: objectId, date };
  show1d.value = show_1d;
  objectData.value = null;
  childrenData.value = [];
  cfgPending.value = false;
  cfgFetched.value = false;
  records.value = [];
  snapshotColumns.value = [];
  lastPull.value = null;
  recPending.value = false;
  recFetched.value = false;
  foundDate.value = null;
  probeDate.value = null;
  noRecentDays.value = null;
  if (recPollTimer) {
    clearTimeout(recPollTimer);
    recPollTimer = null;
  }
  drillRows.value = [];
  drillColumns.value = [];
  drillFetched.value = false;
  drillPage.value = 1;
  drillTotal.value = 0;
  if (!drillRange.value) {
    drillRange.value = [dayjs(date).valueOf(), dayjs(date).valueOf()];
  }
  // 配置/记录打开不自动查(记录首查会真实提交 FB 拉取任务), 点页签或查询按钮才触发;
  // 下钻是纯 Doris 读, 停留在下钻页签时打开即自动查
  open.value = true;
  if (mode.value === 'drill') fetchDrill();
};

defineExpose({ openModal });

// 勾选整棵树时补拉 children;取消时只清掉展示,不重新请求
const onTreeToggle = () => {
  if (!cfgFetched.value) return;
  if (showTree.value) {
    fetchConfig();
  } else {
    childrenData.value = [];
  }
};

const LEVEL_NAME: Record<string, string> = {
  campaign: '系列',
  adset: '组',
  ad: '广告',
};

// 配置展示块:非整棵树 = 只有对象自己;整棵树 = 自己 + 下级(后端按 组→广告 排好)
const configBlocks = computed(() => {
  if (!objectData.value) return [];
  const objs = showTree.value
    ? [objectData.value, ...childrenData.value]
    : [objectData.value];
  return objs.map((o: any) => ({
    key: `${o.level}-${o.object_id}`,
    title: `${LEVEL_NAME[o.level] ?? o.level} ${o.config?.name ?? ''} (${o.object_id})`,
    text: JSON.stringify(o.config ?? o, null, 2),
  }));
});

// 时点快照按记录平铺进行,操作元信息固定列 + 快照列(和面板同款指标)
const dataSource = computed(() =>
  records.value.map((r, idx) => ({
    key: idx,
    时间:
      r.event_time_china ??
      r.date_time_in_timezone ??
      String(r.event_time ?? ''),
    当地时间: r.date_time_in_timezone ?? '',
    操作类型: r.translated_event_type ?? r.event_type ?? '',
    操作人: r.actor_name ?? '',
    变更前: r.change_before ?? '',
    变更后: r.change_after ?? '',
    变更: r.change ?? '',
    ...(r.snapshot ?? {}),
  })),
);

// pin 的列必须连续排在左侧, 否则中间没 pin 的列会被挤出空隙
const columns = computed<TableColumnsType>(() => [
  { title: '时间(中国)', dataIndex: '时间', width: 180, fixed: 'left' },
  { title: '操作类型', dataIndex: '操作类型', width: 140, fixed: 'left' },
  { title: '变更前', dataIndex: '变更前', width: 120, fixed: 'left' },
  { title: '变更后', dataIndex: '变更后', width: 120, fixed: 'left' },
  ...snapshotColumns.value.map((c) => ({ title: c, dataIndex: c, width: 110 })),
  { title: '操作人', dataIndex: '操作人', width: 100 },
  { title: '变更', dataIndex: '变更', width: 200, ellipsis: true },
]);

const drillDataSource = computed(() =>
  drillRows.value.map((r, idx) => ({ key: idx, ...r })),
);

// 后端英文列名 → 面板同款中文标题
const DRILL_COL_TITLE: Record<string, string> = {
  name: '名称',
  status: '状态',
  effective_status: '投放状态',
  learning_stage: '学习期',
  account_status: '账户状态',
};

// 时间列提到最前并 pin, 其余列按面板小时模式原序
const drillTableColumns = computed<TableColumnsType>(() => [
  { title: '时间', dataIndex: '时间', width: 130, fixed: 'left' },
  ...drillColumns.value
    .filter((c) => c !== '时间')
    .map((c) => ({
      title: DRILL_COL_TITLE[c] ?? c,
      dataIndex: c,
      width: c === 'name' ? 240 : 110,
      ellipsis: c === 'name' || c === '投放链接',
    })),
]);
</script>

<template>
  <Modal
    v-model:open="open"
    :footer="null"
    :title="MODE_TITLE[mode]"
    :width="mode === 'config' ? '720px' : '90%'"
    :body-style="{ padding: '12px' }"
  >
    <div class="mb-2 flex items-center gap-2 text-gray-500">
      <RadioGroup
        v-model:value="mode"
        button-style="solid"
        @change="ensureData"
      >
        <RadioButton value="config">配置</RadioButton>
        <RadioButton value="records">记录</RadioButton>
        <RadioButton value="drill">下钻</RadioButton>
      </RadioGroup>
      <span>{{ target?.object_id }}</span>
      <template v-if="mode === 'config'">
        <Button :loading="cfgLoading" @click="fetchConfig"> 刷新 </Button>
        <Checkbox
          v-if="target?.level !== 'ad'"
          v-model:checked="showTree"
          @change="onTreeToggle"
        >
          整棵树
        </Checkbox>
      </template>
      <template v-else-if="mode === 'records'">
        <span>{{ target?.date }}</span>
        <Tag v-if="foundDate && foundDate !== target?.date" color="blue">
          最近操作日 {{ foundDate }}
        </Tag>
        <span class="text-xs"> 上次拉取(中国): {{ lastPull ?? '—' }} </span>
        <Button :loading="recLoading" @click="fetchRecords()"> 刷新 </Button>
        <Button danger :loading="recLoading" @click="fetchRecords(true)">
          强制触发
        </Button>
      </template>
      <template v-else>
        <DateRangePicker
          :value="drillRange"
          :clearable="false"
          width="240px"
          @update:value="
            (v) => {
              drillRange = v;
              if (v && drillFetched) fetchDrill();
            }
          "
        />
        <Button :loading="drillLoading" @click="fetchDrill()"> 刷新 </Button>
      </template>
    </div>
    <template v-if="mode === 'config'">
      <div v-if="!cfgFetched && !cfgLoading" class="py-8 text-center">
        <Button type="primary" @click="fetchConfig">查询</Button>
      </div>
      <div v-else-if="cfgPending" class="py-4 text-center text-gray-400">
        配置拉取已提交,正在拉取中,请稍后点击刷新
      </div>
      <div v-else-if="objectData" class="max-h-[60vh] overflow-auto">
        <div v-for="b in configBlocks" :key="b.key" class="mb-2">
          <div v-if="showTree" class="mb-1 text-xs font-medium">
            {{ b.title }}
          </div>
          <pre class="bg-card overflow-auto rounded-md border p-3 text-xs">{{
            b.text
          }}</pre>
        </div>
      </div>
      <div v-else class="py-4 text-center">查询中…</div>
    </template>
    <template v-else-if="mode === 'records'">
      <div v-if="!recFetched && !recLoading" class="py-8 text-center">
        <Button type="primary" @click="fetchRecords()">查询</Button>
      </div>
      <div v-else-if="recPending" class="py-4 text-center text-gray-400">
        正在拉取 {{ probeDate ?? target?.date }} 的操作记录,完成后自动继续回溯…
      </div>
      <div
        v-else-if="noRecentDays && records.length === 0"
        class="py-4 text-center text-gray-400"
      >
        最近 {{ noRecentDays }} 天没有该对象的操作记录
      </div>
      <Table
        v-else
        :columns="columns"
        :data-source="dataSource"
        :loading="recLoading"
        :pagination="false"
        :scroll="{ x: 'max-content', y: '60vh' }"
        bordered
      >
        <template #bodyCell="{ column, text, record }">
          <template v-if="column.dataIndex === '时间'">
            <div>{{ text }}</div>
            <div v-if="record.当地时间" class="text-xs text-gray-400">
              当地 {{ record.当地时间 }}
            </div>
          </template>
          <template
            v-else-if="
              column.dataIndex === '状态' || column.dataIndex === '投放状态'
            "
          >
            <Tag v-if="text" :color="STATUS_TAG[text]?.color">
              {{ STATUS_TAG[text]?.text ?? text }}
            </Tag>
            <span v-else>—</span>
          </template>
          <template v-else-if="column.dataIndex === '变更'">
            <Tooltip :title="text || undefined">
              <span class="line-clamp-1">{{ text }}</span>
            </Tooltip>
          </template>
        </template>
      </Table>
    </template>
    <template v-else>
      <div v-if="!drillFetched && !drillLoading" class="py-8 text-center">
        <Button type="primary" @click="fetchDrill()">查询</Button>
      </div>
      <div v-else class="relative min-w-0" :aria-busy="drillLoading">
        <!-- 保留表格高度，刷新及翻页时用同一加载动画覆盖内容，避免弹窗跳动。 -->
        <ListLoading
          v-if="drillLoading"
          fill
          class="bg-muted absolute inset-0 z-10 rounded-md"
        />
        <Table
          :class="{ invisible: drillLoading }"
          :aria-hidden="drillLoading"
          :columns="drillTableColumns"
          :data-source="drillDataSource"
          :pagination="{
            current: drillPage,
            pageSize: DRILL_PAGE_SIZE,
            total: drillTotal,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 条`,
          }"
          :scroll="{ x: 'max-content', y: '60vh' }"
          size="small"
          bordered
          @change="(pag) => fetchDrill(pag.current ?? 1)"
        >
          <template #bodyCell="{ column, text }">
            <template
              v-if="
                column.dataIndex === 'status' ||
                column.dataIndex === 'effective_status'
              "
            >
              <Tag v-if="text" :color="STATUS_TAG[text]?.color">
                {{ STATUS_TAG[text]?.text ?? text }}
              </Tag>
              <span v-else>—</span>
            </template>
            <template v-else-if="column.dataIndex === 'learning_stage'">
              <Tag v-if="text" :color="LEARNING_STAGE_TAG[text]?.color">
                {{ LEARNING_STAGE_TAG[text]?.text ?? text }}
              </Tag>
              <span v-else>—</span>
            </template>
            <template v-else-if="column.dataIndex === 'account_status'">
              <Tag v-if="text" :color="ACCOUNT_STATUS_TAG[text]?.color">
                {{ ACCOUNT_STATUS_TAG[text]?.text ?? text }}
              </Tag>
              <span v-else>—</span>
            </template>
          </template>
        </Table>
      </div>
    </template>
  </Modal>
</template>
