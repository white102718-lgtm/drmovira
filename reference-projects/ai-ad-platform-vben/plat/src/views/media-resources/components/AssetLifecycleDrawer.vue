<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type {
  AdAccountFacebookActivity,
  AssetLifecycleDetail,
  LifecycleChangeValue,
  LifecycleFieldChange,
} from '#/api';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { Alert, Button, Drawer, Empty, Table, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAdAccountFacebookActivities } from '#/api';

import {
  findInventoryAssetTypeBySubtype,
  getInventoryAssetEditorFieldKeys,
} from './asset-types';
import FacebookActivityTimelineItem from './FacebookActivityTimelineItem.vue';
import { ASSET_MODAL_TABLE_BODY_HEIGHT } from './asset-table-layout';

const props = defineProps<{
  accountId?: string;
  assetSubtype?: string;
  detail?: AssetLifecycleDetail;
  loading?: boolean;
  open: boolean;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  application: [id: string];
}>();

const usageColumns: TableColumnsType = [
  { dataIndex: 'startedAt', key: 'startedAt', title: '使用时间', width: 185 },
  { dataIndex: 'userName', key: 'userName', title: '使用人', width: 120 },
  { dataIndex: 'projectName', key: 'projectName', title: '项目 / 团队' },
  { align: 'right', key: 'spend', title: '区间账户消耗', width: 150 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 100 },
];

const eventMeta: Record<string, { color: string; label: string }> = {
  APPLICATION_DECIDED: { color: 'processing', label: '审批结果' },
  APPLICATION_SUBMITTED: { color: 'processing', label: '申请' },
  APPROVED: { color: 'success', label: '审批通过' },
  ASSIGNED: { color: 'processing', label: '发放' },
  DELETED: { color: 'default', label: '归档' },
  DISABLED: { color: 'error', label: '停用' },
  FACEBOOK_ACCOUNT_BANNED: { color: 'error', label: 'Facebook 封户' },
  FACEBOOK_ACTIVITY: { color: 'default', label: 'Facebook 操作' },
  OPERATION_COMPLETED: { color: 'success', label: '办理完成' },
  RECHARGE_COMPLETED: { color: 'success', label: '充值完成' },
  REJECTED: { color: 'error', label: '审批驳回' },
  RELEASED: { color: 'default', label: '释放' },
  RETURN_COMPLETED: { color: 'success', label: '回收完成' },
  RETURN_REQUESTED: { color: 'warning', label: '回收' },
  STOCKED: { color: 'default', label: '入库' },
  TRANSFERRED: { color: 'warning', label: '审批转交' },
  UPDATED: { color: 'default', label: '资料更新' },
};

function formatLifecycleDateTime(value?: string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—';
}

function assetStatusLabel(status: string) {
  if (status === 'AVAILABLE') return '可用';
  if (status === 'ASSIGNED') return '已分配';
  if (status === 'RETURN_PENDING') return '待回收';
  if (status === 'DISABLED') return '已停用';
  return status;
}

function formatLifecycleMoney(value?: number, currency = 'USD') {
  if (value === undefined) return '—';
  return `${currency} ${value.toLocaleString('zh-CN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
}

function hasApplicationAmountField(
  event: AssetLifecycleDetail['events'][number],
) {
  return event.formFields?.some((field) =>
    ['amount', 'rechargeAmount'].includes(field.key),
  );
}

const usageRows = computed(() =>
  (props.detail?.usagePeriods ?? []).map((period) => ({
    ...period,
    projectName:
      [period.projectName, period.teamName].filter(Boolean).join(' · ') ||
      '未关联',
    startedAt: period.endedAt
      ? `${formatLifecycleDateTime(period.startedAt)} 至 ${formatLifecycleDateTime(period.endedAt)}`
      : `${formatLifecycleDateTime(period.startedAt)} 至今`,
  })),
);

function eventLabel(eventType: string) {
  return eventMeta[eventType]?.label ?? eventType;
}

const updateSourceLabels: Record<string, string> = {
  BATCH_EDIT: '批量编辑',
  CHANNEL_IMPORT: '渠道导入',
  CHANNEL_MANUAL: '渠道手工绑定',
  EXCEL_BATCH: 'Excel 批量处理',
  EXCEL_IMPORT: 'Excel 导入',
  FEISHU_SYNC: '飞书同步',
  MANUAL_CREATE: '手工新增',
  MANUAL_EDIT: '编辑抽屉',
  MONGO_SYNC: 'Mongo 同步',
  OPEN_ACCOUNT: '开户办理',
  SPREADSHEET_CREATE: '电子表格新增',
};

interface LifecycleVisibleField {
  fieldKey: string;
  label: string;
}

const commonLifecycleFields: Partial<Record<string, LifecycleVisibleField>> = {
  channel: { fieldKey: 'channel', label: '渠道' },
  inventoryStatus: { fieldKey: 'status', label: '库存状态' },
  project: { fieldKey: 'project', label: '项目' },
  remark: { fieldKey: 'remark', label: '备注' },
  usageTeam: { fieldKey: 'usageTeam', label: '使用团队' },
  usageUsers: { fieldKey: 'usageUsers', label: '使用人' },
};

const lifecycleVisibleFields = computed<LifecycleVisibleField[] | undefined>(
  () => {
    const subtype = props.assetSubtype?.trim();
    if (!subtype || subtype === 'ad_account') return undefined;

    const assetType = findInventoryAssetTypeBySubtype(subtype);
    if (!assetType) return undefined;

    const detailLabels = new Map(
      assetType.fields.map((field) => [field.key, field.label]),
    );
    return getInventoryAssetEditorFieldKeys(assetType).flatMap((editorKey) => {
      if (editorKey.startsWith('detail.')) {
        const fieldKey = editorKey.slice('detail.'.length);
        return [{ fieldKey, label: detailLabels.get(fieldKey) ?? fieldKey }];
      }
      const field = commonLifecycleFields[editorKey];
      return field ? [field] : [];
    });
  },
);

function updateSourceLabel(source?: string) {
  if (!source) return '历史更新';
  return updateSourceLabels[source] ?? source;
}

/** 入库和资料更新只展示当前资产编辑抽屉中真实可见的业务字段。 */
function filterLifecycleChanges(
  event: AssetLifecycleDetail['events'][number],
  visibleFields?: readonly LifecycleVisibleField[],
) {
  const changes = event.changes ?? [];
  if (!['STOCKED', 'UPDATED'].includes(event.eventType) || !visibleFields) {
    return changes;
  }

  const fieldsByKey = new Map(
    visibleFields.map((field) => [field.fieldKey, field]),
  );
  const changesByKey = new Map<string, LifecycleFieldChange>();
  for (const change of changes) {
    const field = fieldsByKey.get(change.fieldKey);
    if (!field) continue;
    changesByKey.set(change.fieldKey, {
      ...change,
      fieldLabel: field.label,
    });
  }

  return visibleFields.flatMap((field) => {
    const change = changesByKey.get(field.fieldKey);
    return change ? [change] : [];
  });
}

function displayedLifecycleChanges(
  event: AssetLifecycleDetail['events'][number],
) {
  return filterLifecycleChanges(event, lifecycleVisibleFields.value);
}

function changeValuePrimary(value?: LifecycleChangeValue) {
  if (value?.display?.trim()) return value.display.trim();
  const names = (value?.references ?? [])
    .map((item) => item.name?.trim())
    .filter(Boolean);
  return names.length > 0 ? names.join('、') : '未设置';
}

function changeValueSecondary(value?: LifecycleChangeValue) {
  const ids = (value?.references ?? [])
    .map((item) => item.id?.trim())
    .filter(Boolean);
  return ids.length > 0 ? ids.join('、') : undefined;
}

const facebookActivities = ref<AdAccountFacebookActivity[]>([]);
const facebookAfter = ref<string>();
const facebookUntil = ref<number>();
const facebookHasMore = ref(false);
const facebookLoading = ref(false);
const facebookLoaded = ref(false);
const facebookError = ref('');
let facebookRequestVersion = 0;
let facebookAbortController: AbortController | undefined;

function resetFacebookActivities() {
  facebookRequestVersion += 1;
  facebookAbortController?.abort();
  facebookAbortController = undefined;
  facebookActivities.value = [];
  facebookAfter.value = undefined;
  facebookUntil.value = undefined;
  facebookHasMore.value = false;
  facebookLoading.value = false;
  facebookLoaded.value = false;
  facebookError.value = '';
}

async function loadFacebookActivities() {
  const accountId = props.accountId?.trim();
  if (!props.open || !accountId || facebookLoading.value) return;

  const requestVersion = facebookRequestVersion;
  const requestController = new AbortController();
  facebookAbortController = requestController;
  facebookLoading.value = true;
  facebookError.value = '';
  try {
    const page = await getAdAccountFacebookActivities(
      accountId,
      {
        after: facebookAfter.value,
        pageSize: 50,
        until: facebookUntil.value,
      },
      {
        signal: requestController.signal,
        skipErrorMessage: true,
      },
    );
    if (requestVersion !== facebookRequestVersion) return;
    const activityMap = new Map(
      facebookActivities.value.map((activity) => [activity.id, activity]),
    );
    page.items.forEach((activity) => activityMap.set(activity.id, activity));
    facebookActivities.value = [...activityMap.values()];
    facebookAfter.value = page.nextAfter;
    facebookUntil.value = page.until;
    facebookHasMore.value = page.hasMore;
    facebookLoaded.value = true;
  } catch (error) {
    if (
      requestVersion !== facebookRequestVersion ||
      requestController.signal.aborted
    ) {
      return;
    }
    facebookError.value =
      error instanceof Error && error.message
        ? error.message
        : 'Facebook 操作记录暂时无法获取，请稍后重试。';
  } finally {
    if (requestVersion === facebookRequestVersion) {
      facebookLoading.value = false;
    }
  }
}

function facebookEvent(
  activity: AdAccountFacebookActivity,
): AssetLifecycleDetail['events'][number] {
  return {
    actorName: activity.actorName,
    description:
      activity.translatedEventType || activity.eventType || 'Facebook 操作',
    eventType: 'FACEBOOK_ACTIVITY',
    extraData: activity.extraData,
    facebookCategory: activity.category,
    facebookSummaryItems: activity.summaryItems,
    id: activity.id,
    localOccurredAt: activity.localOccurredAt,
    objectId: activity.objectId,
    objectName: activity.objectName,
    objectType: activity.objectType,
    occurredAt: activity.occurredAt,
    platformApplicationName: activity.applicationName,
    source: 'FACEBOOK' as const,
    tool: activity.tool,
  };
}

const timelineEvents = computed(() =>
  [
    ...(props.detail?.events ?? []),
    ...facebookActivities.value.map(facebookEvent),
  ].sort(
    (left, right) =>
      dayjs(right.occurredAt).valueOf() - dayjs(left.occurredAt).valueOf(),
  ),
);

function formatExtraData(value: string) {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

watch(
  () => [props.open, props.accountId] as const,
  ([open, accountId]) => {
    resetFacebookActivities();
    if (open && accountId?.trim()) void loadFacebookActivities();
  },
  { immediate: true },
);

onBeforeUnmount(resetFacebookActivities);
</script>

<template>
  <Drawer
    :open="open"
    placement="right"
    title="资产使用生命周期"
    width="min(860px, 100vw)"
    @update:open="emit('update:open', $event)"
  >
    <div v-if="loading" class="text-muted-foreground py-16 text-center">
      正在加载生命周期…
    </div>
    <Empty v-else-if="!detail" description="暂无可展示的生命周期记录" />
    <div v-else class="flex flex-col gap-6">
      <section class="border-border bg-card rounded-lg border p-4">
        <p class="text-muted-foreground mb-1 text-sm">
          {{ detail.asset.assetType }}
        </p>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-foreground m-0 text-lg font-semibold">
              {{ detail.asset.assetName }}
            </h2>
            <p class="text-muted-foreground mb-0 mt-1 font-mono text-xs">
              {{ detail.asset.assetCode || detail.asset.id }}
            </p>
          </div>
          <Tag class="!m-0">{{ assetStatusLabel(detail.asset.status) }}</Tag>
        </div>
        <div class="text-muted-foreground mt-4 flex flex-wrap gap-2 text-sm">
          <span v-if="detail.asset.currentUserName"
            >当前使用人：{{ detail.asset.currentUserName }}</span
          >
          <span v-if="detail.asset.projectName"
            >项目：{{ detail.asset.projectName }}</span
          >
          <span v-if="detail.asset.teamName"
            >团队：{{ detail.asset.teamName }}</span
          >
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <div class="border-border bg-background rounded-md border p-3">
            <div class="text-muted-foreground text-xs">生命周期累计消耗</div>
            <div
              class="text-foreground mt-1 text-lg font-semibold tabular-nums"
            >
              {{
                formatLifecycleMoney(
                  detail.asset.spend?.cumulative,
                  detail.asset.spend?.currency,
                )
              }}
            </div>
          </div>
          <div class="border-border bg-background rounded-md border p-3">
            <div class="text-muted-foreground text-xs">当日消耗</div>
            <div
              class="text-foreground mt-1 text-lg font-semibold tabular-nums"
            >
              {{
                formatLifecycleMoney(
                  detail.asset.spend?.today,
                  detail.asset.spend?.currency,
                )
              }}
            </div>
          </div>
        </div>
        <p class="text-muted-foreground mb-0 mt-2 text-xs">
          消耗复用广告面板账户维度“花费金额”口径，按广告账户时区的自然日汇总<span
            v-if="detail.asset.spend?.dataCutoff"
            >；数据更新至
            {{ formatLifecycleDateTime(detail.asset.spend.dataCutoff) }}</span
          >。
        </p>
        <Alert
          v-if="detail.asset.spend?.unavailable"
          class="mt-3"
          message="部分消耗暂时不可用，生命周期操作记录仍可正常查看。"
          show-icon
          type="warning"
        />
      </section>

      <section>
        <h3 class="text-foreground mb-1 text-base font-semibold">使用区间</h3>
        <p class="text-muted-foreground mb-3 text-sm">
          记录已确认的分配、使用与释放情况。区间消耗表示该账户在该日期范围内的花费；多人同时使用时不作为个人贡献拆分。
        </p>
        <Table
          class="asset-dialog-fixed-table"
          :columns="usageColumns"
          :data-source="usageRows"
          :pagination="false"
          :row-key="
            (record, index) => `${record.userId}-${record.startedAt}-${index}`
          "
          size="small"
          :scroll="{ x: 840, y: ASSET_MODAL_TABLE_BODY_HEIGHT }"
          :style="{
            '--asset-dialog-table-height': `${ASSET_MODAL_TABLE_BODY_HEIGHT}px`,
          }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <Tag class="!m-0">{{
                record.status === 'ACTIVE' ? '使用中' : '已结束'
              }}</Tag>
            </template>
            <template v-else-if="column.key === 'spend'">
              <span class="tabular-nums">
                {{
                  record.spendUnavailable
                    ? '暂不可用'
                    : formatLifecycleMoney(record.spend, record.spendCurrency)
                }}
              </span>
            </template>
          </template>
        </Table>
      </section>

      <section>
        <h3 class="text-foreground mb-1 text-base font-semibold">关联事件</h3>
        <p class="text-muted-foreground mb-3 text-sm">
          展示已成功办理的账户申请，以及发放、释放、封户、状态变更与 Facebook
          平台操作。
        </p>
        <Alert
          v-if="facebookError"
          class="mb-3"
          :message="facebookError"
          role="alert"
          show-icon
          type="warning"
        >
          <template #action>
            <Button :disabled="facebookLoading" @click="loadFacebookActivities"
              >重试</Button
            >
          </template>
        </Alert>
        <p
          v-else-if="facebookLoading && !facebookLoaded"
          aria-live="polite"
          class="text-muted-foreground mb-3 text-sm"
        >
          正在加载 Facebook 操作记录…
        </p>
        <ol class="border-border m-0 list-none border-l pl-5">
          <li
            v-for="event in timelineEvents"
            :key="event.id"
            class="relative pb-5 last:pb-0"
          >
            <span
              class="bg-primary absolute -left-[25px] top-1.5 h-2.5 w-2.5 rounded-full"
            />
            <FacebookActivityTimelineItem
              v-if="event.source === 'FACEBOOK'"
              :event="event"
              :occurred-at="formatLifecycleDateTime(event.occurredAt)"
            />
            <template v-else>
              <div class="flex flex-wrap items-center gap-2">
                <Tag :color="eventMeta[event.eventType]?.color" class="!m-0">{{
                  eventLabel(event.eventType)
                }}</Tag>
                <span class="text-foreground font-medium">{{
                  event.description || event.actorName || '系统事件'
                }}</span>
                <span class="text-muted-foreground text-xs">{{
                  formatLifecycleDateTime(event.occurredAt)
                }}</span>
                <Tag
                  v-if="event.updateSource || event.eventType === 'UPDATED'"
                  class="!m-0"
                  color="default"
                >
                  {{ updateSourceLabel(event.updateSource) }}
                </Tag>
                <span
                  v-if="
                    ['STOCKED', 'UPDATED'].includes(event.eventType) &&
                    displayedLifecycleChanges(event).length
                  "
                  class="text-muted-foreground text-xs tabular-nums"
                >
                  {{ displayedLifecycleChanges(event).length }} 项{{
                    event.eventType === 'STOCKED' ? '初始资料' : '变更'
                  }}
                </span>
              </div>
              <p
                v-if="event.actorName"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                操作人：{{ event.actorName }}
              </p>
              <div
                v-if="
                  ['STOCKED', 'UPDATED'].includes(event.eventType) &&
                  displayedLifecycleChanges(event).length
                "
                class="border-border mt-2 divide-y border-y"
              >
                <div
                  v-for="change in displayedLifecycleChanges(event)"
                  :key="change.fieldKey"
                  class="grid grid-cols-[minmax(76px,0.55fr)_minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 px-1 py-1.5 sm:grid-cols-[minmax(108px,0.6fr)_minmax(0,1fr)_auto_minmax(0,1fr)] sm:gap-x-3"
                >
                  <div class="min-w-0">
                    <span
                      class="text-foreground text-xs font-medium sm:text-sm"
                      >{{ change.fieldLabel }}</span
                    >
                  </div>
                  <div class="min-w-0">
                    <p
                      class="text-muted-foreground m-0 flex flex-wrap items-baseline gap-x-1 break-words text-sm"
                    >
                      <span>{{ changeValuePrimary(change.before) }}</span>
                      <span
                        v-if="changeValueSecondary(change.before)"
                        class="break-all text-xs"
                      >
                        （{{ changeValueSecondary(change.before) }}）
                      </span>
                    </p>
                  </div>
                  <IconifyIcon
                    aria-hidden="true"
                    class="text-muted-foreground shrink-0 text-xs"
                    icon="lucide:arrow-right"
                  />
                  <div class="min-w-0">
                    <p
                      class="text-foreground m-0 flex flex-wrap items-baseline gap-x-1 break-words text-sm font-medium"
                    >
                      <span>{{ changeValuePrimary(change.after) }}</span>
                      <span
                        v-if="changeValueSecondary(change.after)"
                        class="text-muted-foreground break-all text-xs font-normal"
                      >
                        （{{ changeValueSecondary(change.after) }}）
                      </span>
                    </p>
                  </div>
                </div>
              </div>
              <p
                v-else-if="event.eventType === 'UPDATED'"
                class="text-muted-foreground mb-0 mt-2 text-sm"
              >
                历史资料更新事件暂无字段明细
              </p>
              <p
                v-if="event.targetUserName"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                接收人：{{ event.targetUserName }}
              </p>
              <p
                v-if="event.objectName || event.objectId"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                操作对象：{{ event.objectName || event.objectId
                }}<span v-if="event.objectType"
                  >（{{ event.objectType }}）</span
                >
              </p>
              <p
                v-if="event.platformApplicationName || event.tool"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                来源：{{
                  [event.platformApplicationName, event.tool]
                    .filter(Boolean)
                    .join(' · ')
                }}
              </p>
              <p
                v-if="event.localOccurredAt"
                class="text-muted-foreground mb-0 mt-1 text-xs"
              >
                广告账户当地时间：{{ event.localOccurredAt }}
              </p>
              <p
                v-if="
                  event.amount !== undefined &&
                  !hasApplicationAmountField(event)
                "
                class="text-foreground mb-0 mt-1 text-sm font-medium tabular-nums"
              >
                金额：{{ formatLifecycleMoney(event.amount, event.currency) }}
              </p>
              <dl
                v-if="event.formFields?.length"
                class="border-border bg-muted/40 mt-3 grid grid-cols-1 gap-x-4 gap-y-3 rounded-md border p-3 sm:grid-cols-2"
              >
                <div
                  v-for="field in event.formFields"
                  :key="field.key"
                  :class="{ 'sm:col-span-2': field.fullWidth }"
                  class="min-w-0"
                >
                  <dt class="text-muted-foreground text-xs">
                    {{ field.label }}
                  </dt>
                  <dd
                    class="text-foreground mb-0 mt-1 whitespace-pre-wrap break-words text-sm"
                  >
                    {{ field.value }}
                  </dd>
                </div>
              </dl>
              <p
                v-if="event.nodeName"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                节点：{{ event.nodeName }}
              </p>
              <p
                v-if="event.remark"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                意见：{{ event.remark }}
              </p>
              <p
                v-if="event.projectName || event.teamName"
                class="text-muted-foreground mb-0 mt-1 text-sm"
              >
                {{
                  [event.projectName, event.teamName]
                    .filter(Boolean)
                    .join(' · ')
                }}
              </p>
              <Button
                v-if="event.applicationId"
                class="mt-1 !px-0"
                type="link"
                @click="emit('application', event.applicationId)"
                >查看原申请</Button
              >
              <details v-if="event.extraData" class="mt-2 text-sm">
                <summary
                  class="text-muted-foreground cursor-pointer select-none"
                >
                  查看变更详情
                </summary>
                <pre
                  class="border-border bg-muted text-foreground mt-2 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-md border p-3 text-xs"
                  >{{ formatExtraData(event.extraData) }}</pre
                >
              </details>
            </template>
          </li>
        </ol>
        <div v-if="facebookHasMore" class="mt-4 flex justify-center">
          <Button
            :loading="facebookLoading"
            :disabled="facebookLoading"
            @click="loadFacebookActivities"
          >
            加载更早的 Facebook 记录
          </Button>
        </div>
        <p
          v-else-if="facebookLoaded && facebookActivities.length === 0"
          class="text-muted-foreground mb-0 mt-4 text-center text-sm"
        >
          该账户入库以来暂无 Facebook 操作记录。
        </p>
      </section>
    </div>
  </Drawer>
</template>

<style scoped></style>
