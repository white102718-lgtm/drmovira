<script setup lang="ts">
import { computed, h, nextTick, ref, watch } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  AutoComplete,
  Button,
  Modal,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getUserNameOptions } from '#/api';
import { getOperationHistory } from '#/api/advertisement';
import { getAgentOptions } from '#/api/management/platform-config';
import DateRangePicker from '#/views/components/DateRangePicker.vue';

interface Props {
  open: boolean;
}

interface Emits {
  (e: 'update:open', value: boolean): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const userStore = useUserStore();

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const filterUser = ref<string | undefined>(undefined);
const filterLevel = ref<string | undefined>(undefined);
const filterOperateTypes = ref<string[]>([]);
const filterDateRange = ref<[number, number] | undefined>(undefined);
const loading = ref(false);
const listData = ref<any[]>([]);
const page = ref(1);
const pageSize = ref(50);
const total = ref(0);
const userSelectOptions = ref<Array<{ label: string; value: string }>>([]);

const platformInput = ref('');
const selectedPlatform = ref<string | undefined>(undefined);
const platformOptions = ref<Array<{ label: string; value: string }>>([]);
const filteredPlatformOptions = ref<Array<{ label: string; value: string }>>(
  [],
);
const agentLineSelected = ref<string | undefined>(undefined);
const agentLineOptions = ref<Array<{ label: string; value: string }>>([]);

function handlePlatformInputChange(value: any) {
  const str = String(value || '');
  platformInput.value = str;
  const kw = str.trim().toLowerCase();
  filteredPlatformOptions.value = kw
    ? platformOptions.value.filter((p) => p.value.toLowerCase().includes(kw))
    : platformOptions.value;
}

function handlePlatformSelect(value: any) {
  const str = String(value || '');
  platformInput.value = str;
  selectedPlatform.value = str;
}

function handlePlatformClear() {
  platformInput.value = '';
  selectedPlatform.value = undefined;
  filteredPlatformOptions.value = platformOptions.value;
}

const statusMap: Record<string, { color: string; text: string }> = {
  INVALID: { text: '无效任务', color: 'gray' },
  ABORT: { text: '已中止', color: 'orange' },
  SENDING: { text: '发送中', color: 'blue' },
  STARTED: { text: '操作中', color: 'blue' },
  PENDING: { text: '等待中', color: 'default' },
  COMPLETED: { text: '已完成', color: 'green' },
  RETRY: { text: '重试中', color: 'cyan' },
  FAILED: { text: '操作失败', color: 'red' },
  pending: { text: '等待中', color: 'orange' },
  MANUAL: { text: '人工处理', color: 'purple' },
};

const levelOptions = [
  { label: '广告系列', value: 'campaign' },
  { label: '广告组', value: 'adset' },
  { label: '广告', value: 'ad' },
];

const operateTypeOptions = [
  { label: '预算', value: 'budget' },
  { label: '状态开启', value: 'start' },
  { label: '状态暂停', value: 'pause' },
];

const optionsLoaded = ref(false);

async function loadSelectOptions() {
  if (optionsLoaded.value) return;
  try {
    const users = await getUserNameOptions(['operator', 'operator_leader']);
    userSelectOptions.value = users.map((user) => ({
      label: user.full_name,
      value: user.real_name,
    }));
  } catch {}
  try {
    const res = await getAgentOptions();
    if (Array.isArray(res)) {
      platformOptions.value = res.map((item: any) => ({
        label: item._id || item.game_platform,
        value: item._id || item.game_platform,
      }));
      filteredPlatformOptions.value = platformOptions.value;
      const lines = res.flatMap((item: any) =>
        Array.isArray(item.agent_lines) ? item.agent_lines : [],
      );
      agentLineOptions.value = [...new Set(lines)].map((line: string) => ({
        label: line,
        value: line,
      }));
    }
  } catch {}
  optionsLoaded.value = true;
}

const displayData = computed(() => listData.value);

async function fetchData() {
  if (!filterDateRange.value || filterDateRange.value.length !== 2) return;
  const start = dayjs(filterDateRange.value[0]).format('YYYY-MM-DD HH');
  const end = dayjs(filterDateRange.value[1]).format('YYYY-MM-DD HH');
  const operateTypes =
    filterOperateTypes.value.length > 0
      ? filterOperateTypes.value
      : ['budget', 'start', 'pause'];
  try {
    loading.value = true;
    const result = await getOperationHistory({
      start,
      end,
      current_user: filterUser.value || undefined,
      operate_type: operateTypes,
      operte_level: filterLevel.value || undefined,
      game_platform: selectedPlatform.value || undefined,
      agent_line: agentLineSelected.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    });
    listData.value = Array.isArray(result?.items) ? result.items : [];
    total.value = result?.total ?? 0;
  } catch {
    listData.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  fetchData();
}

function handlePageChange(p: number, ps: number) {
  page.value = p;
  pageSize.value = ps;
  fetchData();
}

watch(
  () => props.open,
  (newVal) => {
    if (newVal) {
      const todayStr = dayjs.tz().format('YYYY-MM-DD');
      filterDateRange.value = [
        dayjs(todayStr).valueOf(),
        dayjs(todayStr).endOf('day').valueOf(),
      ];
      // /users/names 的选项值是英文昵称，登录资料的 realName 可能是中文姓名。
      filterUser.value = userStore.userInfo?.englishNickname || undefined;
      page.value = 1;
      loadSelectOptions();
      nextTick(() => fetchData());
    }
  },
  { immediate: true },
);

function filterUserOption(input: string, option: any) {
  return option.label.toLowerCase().includes(input.toLowerCase());
}

const columns = [
  {
    title: '层级',
    key: 'level',
    width: 90,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) =>
      record.data?.level
        ? (levelOptions.find((o) => o.value === record.data.level)?.label ??
          record.data.level)
        : '-',
  },
  {
    title: '名称',
    key: 'name',
    width: 100,
    align: 'center' as const,
    ellipsis: true,
    customRender: ({ record }: { record: any }) => record.data?.name || '-',
  },
  {
    title: '状态',
    key: 'status',
    width: 105,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) => {
      // 失败但之后重试已成功的,按最终结果显示为已完成
      const s =
        record.status === 'FAILED' && record.retried_success
          ? 'COMPLETED'
          : record.status;
      const cfg = statusMap[s] ?? { text: s || '未知', color: 'default' };
      const tag = h(Tag, { color: cfg.color }, () => cfg.text);
      if (s === 'FAILED' && record.error) {
        return h(
          Tooltip,
          {},
          {
            default: () => tag,
            title: () =>
              h(
                'div',
                { style: 'max-height:240px;overflow-y:auto' },
                record.error,
              ),
          },
        );
      }
      return tag;
    },
  },
  {
    title: '操作结果',
    key: 'type',
    width: 160,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) => {
      const type = record.data?.type;
      const value = record.data?.value;
      if (type === 'budget') {
        return h('span', {}, `预算：${value ?? ''}`);
      }
      if (type === 'start' || type === 'pause') {
        const isStart = type === 'start';
        return h(
          'div',
          {
            style:
              'display:flex;align-items:center;justify-content:center;gap:6px',
          },
          [
            h('span', {}, '状态：'),
            h(Tag, { color: isStart ? 'green' : 'orange' }, () =>
              isStart ? '启用' : '暂停',
            ),
          ],
        );
      }
      return h('span', {}, type || '-');
    },
  },
  {
    title: '操作人',
    key: 'real_name',
    width: 100,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) =>
      record.data?.real_name || '-',
  },
  {
    title: '创建时间',
    key: 'start_time',
    width: 165,
    align: 'center' as const,
    customRender: ({ record }: { record: any }) => {
      const t = record.start_time;
      if (!t) return '-';
      return t.slice(0, 19).replace('T', ' ');
    },
  },
  {
    title: 'ID',
    dataIndex: 'id',
    key: 'id',
    width: 200,
    align: 'center' as const,
    ellipsis: true,
    customRender: ({ record }: { record: any }) => record.data?.id || '-',
  },
];
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    title="操作历史"
    :footer="null"
    width="1400px"
    :body-style="{ maxHeight: '78vh', overflowY: 'auto' }"
  >
    <div class="space-y-3">
      <div
        class="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3"
      >
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">平台</span>
          <AutoComplete
            :value="platformInput"
            allow-clear
            show-search
            placeholder="请选择"
            style="width: 100px"
            :options="filteredPlatformOptions"
            :filter-option="false"
            @change="handlePlatformInputChange"
            @select="handlePlatformSelect"
            @clear="handlePlatformClear"
          />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">代理线</span>
          <Select
            :value="agentLineSelected"
            :options="agentLineOptions"
            allow-clear
            show-search
            placeholder="请选择"
            style="width: 130px"
            @update:value="
              (v) => {
                agentLineSelected = v ? String(v) : undefined;
              }
            "
          />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">操作人</span>
          <Select
            :value="filterUser"
            :options="userSelectOptions"
            show-search
            :filter-option="filterUserOption"
            placeholder="请选择"
            style="width: 100px"
            allow-clear
            @update:value="filterUser = $event"
          />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">层级</span>
          <Select
            :value="filterLevel"
            :options="levelOptions"
            placeholder="全部"
            style="width: 95px"
            allow-clear
            @update:value="filterLevel = $event"
          />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">操作类型</span>
          <Select
            :value="filterOperateTypes"
            mode="multiple"
            :max-tag-count="1"
            :options="operateTypeOptions"
            placeholder="全部"
            style="min-width: 100px"
            allow-clear
            @update:value="filterOperateTypes = $event"
          />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="text-sm font-medium text-gray-600">修改日期</span>
          <DateRangePicker
            :value="filterDateRange"
            type="datetimerange"
            format="yyyy-MM-dd HH"
            time-picker-format="HH"
            width="270px"
            @update:value="filterDateRange = $event ?? undefined"
          />
        </div>
        <Button type="primary" :loading="loading" @click="handleSearch">
          查询
        </Button>
      </div>

      <Table
        :columns="columns"
        :data-source="displayData"
        :loading="loading"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: handlePageChange,
        }"
        row-key="_id"
        bordered
        :scroll="{ x: 'max-content', y: 460 }"
      />
    </div>
  </Modal>
</template>
