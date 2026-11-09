<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, nextTick, ref, watch } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  Button,
  message,
  Modal,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getOperationHistory } from '#/api/advertisement';
import { adpulseClient } from '#/api/request';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';

import { conversionEventOptions } from '../constants';

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
  set: (value) => emit('update:open', value),
});

const userOptions = ref<Array<{ label: string; value: string }>>([]);
let userOptionsLoaded = false;
async function loadUserOptions() {
  if (userOptionsLoaded) return;
  try {
    // 分开读取展示名和业务值，保留角色及部门范围筛选。
    const users = await adpulseClient.get<
      Array<{ full_name: string; real_name: string }>
    >('/users/names?roles=operator&roles=operator_leader&scoped=true');
    userOptions.value = users.map((user) => ({
      label: user.full_name,
      value: user.real_name,
    }));
    userOptionsLoaded = true;
  } catch {}
}

const progressDateRange = ref<[number, number] | undefined>(undefined);
const progressLoading = ref(false);
const progressSelectedUser = ref<string | undefined>(undefined);
const progressSelectedStatus = ref<string | undefined>(undefined);
const progressData = ref<any[]>([]);
const progressTotal = ref<null | number>(null);
const progressSuccessRate = ref<null | number>(null);
const progressFailureRate = ref<null | number>(null);
const progressUnprocessedCount = ref<null | number>(null);
const hasOpenedOnce = ref(false);

const statusOptions = [
  { value: 'success', label: '成功', color: 'green' },
  { value: 'failed', label: '失败', color: 'red' },
  { value: 'partial', label: '部分失败', color: 'orange' },
  { value: 'started', label: '执行中', color: 'blue' },
  { value: 'pending', label: '等待中', color: 'default' },
];

const statusMap = Object.fromEntries(
  statusOptions.map((o) => [o.value, { text: o.label, color: o.color }]),
);

interface StatSegment {
  color: 'blue' | 'green' | 'red';
  failedNames?: string[];
  text: string;
}

function buildStatSegments(
  label: string,
  stats?: { failed?: number; in_progress?: number; success?: number },
  failedNames?: string[],
): StatSegment[] {
  if (!stats) return [];
  const segments: StatSegment[] = [];
  if ((stats.success ?? 0) > 0) {
    segments.push({ text: `${stats.success}个${label}成功`, color: 'green' });
  }
  if ((stats.failed ?? 0) > 0) {
    segments.push({
      text: `${stats.failed}个${label}失败`,
      color: 'red',
      failedNames:
        Array.isArray(failedNames) && failedNames.length > 0
          ? failedNames
          : undefined,
    });
  }
  if ((stats.in_progress ?? 0) > 0) {
    segments.push({
      text: `${stats.in_progress}个${label}进行中`,
      color: 'blue',
    });
  }
  return segments;
}

function getCampaignSegments(record: any): StatSegment[] {
  const adset = record?.adset_stats || {};
  const success = adset.success ?? 0;
  const failed = adset.failed ?? 0;
  const inProgress = adset.in_progress ?? 0;

  if (success > 0) {
    return [{ text: '1个系列成功', color: 'green' }];
  }
  if (inProgress > 0) {
    return [{ text: '1个系列进行中', color: 'blue' }];
  }
  if (failed > 0) {
    return [{ text: '1个系列失败', color: 'red' }];
  }

  switch (record?.status) {
    case 'failed': {
      return [{ text: '1个系列失败', color: 'red' }];
    }
    case 'partial':
    case 'success': {
      return [{ text: '1个系列成功', color: 'green' }];
    }
    case 'pending':
    case 'started': {
      return [{ text: '1个系列进行中', color: 'blue' }];
    }
    default: {
      return [];
    }
  }
}

const segmentColorClass: Record<StatSegment['color'], string> = {
  green: 'text-green-600',
  red: 'text-red-500',
  blue: 'text-blue-500',
};

const conversionEventMap = Object.fromEntries(
  conversionEventOptions.map((o) => [o.value, o.label]),
);

async function executeQueryProgress() {
  if (!progressDateRange.value || progressDateRange.value.length !== 2) {
    message.warning('请选择日期时间范围');
    return;
  }
  try {
    progressLoading.value = true;
    const startTime = dayjs(progressDateRange.value[0]).format('YYYY-MM-DD HH');
    const endTime = dayjs(progressDateRange.value[1]).format('YYYY-MM-DD HH');
    const currentUser = progressSelectedUser.value || undefined;
    const result = await getOperationHistory({
      start: startTime,
      end: endTime,
      current_user: currentUser,
      operate_type: ['create'],
      ad_status: progressSelectedStatus.value || undefined,
    });
    progressData.value = Array.isArray(result?.items) ? result.items : [];
    progressTotal.value = result?.total ?? null;
    progressSuccessRate.value = result?.success_rate ?? null;
    progressFailureRate.value = result?.failure_rate ?? null;
    progressUnprocessedCount.value = result?.unprocessed_rate ?? null;
  } catch {
    progressData.value = [];
  } finally {
    progressLoading.value = false;
  }
}

watch(
  () => props.open,
  (newVal) => {
    if (newVal && !hasOpenedOnce.value) {
      hasOpenedOnce.value = true;
      const today = dayjs.tz();
      const todayStr = today.format('YYYY-MM-DD');
      progressDateRange.value = [
        dayjs(todayStr).valueOf(),
        dayjs(todayStr).endOf('day').valueOf(),
      ];
      // 默认查询值与选项的 real_name 一致，使用登录会话的英文昵称。
      progressSelectedUser.value =
        userStore.userInfo?.englishNickname || undefined;
      loadUserOptions();
      nextTick(() => {
        executeQueryProgress();
      });
    }
  },
);

const progressColumns: TableColumnsType = [
  {
    title: '平台',
    dataIndex: 'game_platform',
    key: 'game_platform',
    width: 100,
    customRender: ({ text }: { text: string }) => text || '-',
  },
  {
    title: '账户',
    dataIndex: 'account_name',
    key: 'account_name',
    width: 170,
  },
  {
    title: '系列',
    dataIndex: 'campaign_name',
    key: 'campaign_name',
    width: 180,
  },
  {
    title: '转化事件',
    dataIndex: 'custom_event_type',
    key: 'custom_event_type',
    align: 'center',
    width: 95,
    customRender: ({ text }: { text: string }) =>
      conversionEventMap[text] || text || '-',
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 320,
  },
  {
    title: '投手',
    key: 'real_name',
    align: 'center',
    width: 90,
    customRender: ({ record }: { record: any }) => {
      const realName = record?.data?.real_name;
      // 历史记录保存业务名；展示时映射姓名，已离职等无选项人员保留原值。
      return (
        userOptions.value.find((user) => user.value === realName)?.label ||
        realName ||
        '-'
      );
    },
  },
  {
    title: '创建时间',
    dataIndex: 'start_time',
    align: 'center',
    key: 'start_time',
    width: 135,
    customRender: ({ text }: { text: string }) =>
      text ? text.slice(0, 19).replace('T', ' ') : '-',
  },
];
</script>

<template>
  <div>
    <!-- 查询进度弹窗 -->
    <Modal
      v-model:open="modalOpen"
      title="查询发布进度"
      :footer="null"
      width="1400px"
      :body-style="{ maxHeight: '75vh', overflowY: 'auto' }"
    >
      <div class="space-y-1">
        <div
          class="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3"
        >
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-600">投手</span>
            <Select
              v-model:value="progressSelectedUser"
              :options="userOptions"
              show-search
              :filter-option="
                (input: any, option: any) =>
                  option.label.toLowerCase().includes(input.toLowerCase())
              "
              placeholder="请选择"
              style="width: 130px"
              allow-clear
            />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-600">状态</span>
            <Select
              v-model:value="progressSelectedStatus"
              :options="statusOptions"
              placeholder="全部"
              style="width: 120px"
              allow-clear
            />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-gray-600">时间范围</span>
            <DateRangePicker
              v-model:value="progressDateRange"
              type="datetimerange"
              format="yyyy-MM-dd HH"
              time-picker-format="HH"
              width="300px"
              @update:value="progressDateRange = $event"
            />
          </div>
          <Button
            type="primary"
            :loading="progressLoading"
            @click="executeQueryProgress"
          >
            查询
          </Button>
          <div
            v-if="progressUnprocessedCount !== null"
            class="ml-auto flex items-center gap-1.5"
          >
            <span class="text-sm text-gray-500"
              >未处理数量：<span class="font-semibold text-gray-800">{{
                progressUnprocessedCount
              }}</span></span
            >
          </div>
        </div>
        <!-- 统计摘要 -->
        <div
          v-if="progressTotal !== null"
          class="flex items-center justify-end gap-4 pt-4"
        >
          <div class="flex items-center gap-1.5">
            <span class="text-sm text-gray-500"
              >总数
              <span class="font-semibold text-gray-800">{{
                progressTotal
              }}</span>
              条</span
            >
          </div>
          <div class="h-4 w-px bg-gray-200"></div>
          <div class="flex items-center gap-1.5">
            <span class="text-sm text-gray-500"
              >成功率：<span class="font-semibold text-gray-800">
                {{
                  progressSuccessRate !== null
                    ? `${progressSuccessRate.toFixed(2)}%`
                    : '-'
                }}
              </span></span
            >
          </div>
          <div class="h-4 w-px bg-gray-200"></div>
          <div class="flex items-center gap-1.5">
            <span class="text-sm text-gray-500"
              >失败率：<span class="font-semibold text-gray-800">
                {{
                  progressFailureRate !== null
                    ? `${progressFailureRate.toFixed(2)}%`
                    : '-'
                }}
              </span></span
            >
          </div>
        </div>

        <Table
          v-if="progressData.length > 0"
          :columns="progressColumns"
          :data-source="progressData"
          :pagination="false"
          :loading="progressLoading"
          bordered
          :scroll="{ y: 500 }"
          row-key="_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'account_name'">
              <div class="flex flex-col">
                <OverflowTooltip :text="record.account_name || '-'" />
                <span class="text-gray-500">{{ record.account_id || '' }}</span>
              </div>
            </template>
            <template v-else-if="column.key === 'campaign_name'">
              <OverflowTooltip :text="record.campaign_name || '-'" />
            </template>
            <template v-else-if="column.key === 'status'">
              <div class="flex flex-col items-start gap-2">
                <div class="w-full shrink-0">
                  <Tag :color="statusMap[record.status]?.color || 'default'">
                    {{
                      statusMap[record.status]?.text || record.status || '-'
                    }}
                  </Tag>
                </div>
                <div class="flex min-w-0 flex-col gap-0.5 text-xs leading-5">
                  <div
                    v-for="(line, idx) in [
                      getCampaignSegments(record),
                      buildStatSegments('组', record.adset_stats),
                      buildStatSegments(
                        '广告',
                        record.ad_stats,
                        record.failed_ad_names,
                      ),
                    ]"
                    :key="idx"
                  >
                    <span
                      v-for="(seg, sIdx) in line"
                      :key="sIdx"
                      :class="segmentColorClass[seg.color]"
                    >
                      {{ seg.text
                      }}<template
                        v-if="seg.failedNames && seg.failedNames.length > 0"
                        >：{{ seg.failedNames.join('、') }}</template
                      ><span
                        v-if="sIdx < line.length - 1"
                        class="text-gray-300"
                        >·</span
                      >
                    </span>
                  </div>
                  <Tooltip
                    v-if="
                      (record.status === 'failed' ||
                        record.status === 'partial') &&
                      record.error
                    "
                    :title="record.error"
                    placement="topLeft"
                    :overlay-style="{ maxWidth: '420px' }"
                  >
                    <div class="line-clamp-1 break-all text-red-500">
                      {{ record.error }}
                    </div>
                  </Tooltip>
                </div>
              </div>
            </template>
          </template>
        </Table>
        <div
          v-else-if="!progressLoading"
          class="flex items-center justify-center py-10 text-gray-400"
        >
          暂无数据
        </div>
      </div>
    </Modal>
  </div>
</template>
