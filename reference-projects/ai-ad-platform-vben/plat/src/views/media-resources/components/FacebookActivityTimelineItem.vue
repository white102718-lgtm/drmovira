<script setup lang="ts">
import type {
  AdAccountFacebookActivityCategory,
  AdAccountFacebookActivitySummaryItem,
  AssetLifecycleDetail,
} from '#/api';

import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { Tag } from 'ant-design-vue';

type LifecycleEvent = AssetLifecycleDetail['events'][number];

const props = defineProps<{
  event: LifecycleEvent;
  occurredAt: string;
}>();

const categoryLabels: Record<AdAccountFacebookActivityCategory, string> = {
  ACCOUNT: '账户',
  ACCESS: '权限',
  AD: '广告',
  AD_SET: '广告组',
  AUDIENCE: '受众',
  BILLING: '支付与额度',
  CAMPAIGN: '广告系列',
  CREATIVE: '素材',
  DELIVERY: '投放',
  OTHER: '其他',
};

function categoryLabel(category?: AdAccountFacebookActivityCategory) {
  return category
    ? (categoryLabels[category] ?? categoryLabels.OTHER)
    : categoryLabels.OTHER;
}

function hasDisplayValue(value?: null | string) {
  return value !== undefined && value !== null && value.trim() !== '';
}

function hasChange(item: AdAccountFacebookActivitySummaryItem) {
  return hasDisplayValue(item.before) || hasDisplayValue(item.after);
}

function displayValue(value?: null | string) {
  return value === undefined || value === null || value === ''
    ? '未设置'
    : value;
}

function formatExtraData(value: string) {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

const visibleSummaryItems = computed(() =>
  (props.event.facebookSummaryItems ?? []).filter(
    (item) =>
      hasDisplayValue(item.before) ||
      hasDisplayValue(item.after) ||
      hasDisplayValue(item.value),
  ),
);
</script>

<template>
  <div class="min-w-0">
    <div class="flex flex-wrap items-center gap-2">
      <Tag class="!m-0" color="default">
        Facebook · {{ categoryLabel(event.facebookCategory) }}
      </Tag>
      <span class="text-foreground font-medium">
        {{ event.description || 'Facebook 操作' }}
      </span>
      <time class="text-muted-foreground text-xs" :datetime="event.occurredAt">
        {{ occurredAt }}
      </time>
    </div>

    <div
      class="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs"
    >
      <span v-if="event.actorName">
        操作人：<span class="text-foreground">{{ event.actorName }}</span>
      </span>
      <span v-if="event.objectName || event.objectId" class="min-w-0">
        对象：<span class="text-foreground break-words">{{
          event.objectName || event.objectId
        }}</span>
        <span
          v-if="event.objectName && event.objectId"
          class="ml-1 break-all font-mono"
        >
          {{ event.objectId }}
        </span>
      </span>
      <span v-if="event.platformApplicationName || event.tool">
        来源：<span class="text-foreground">{{
          [event.platformApplicationName, event.tool]
            .filter(Boolean)
            .join(' / ')
        }}</span>
      </span>
      <span v-if="event.localOccurredAt">
        当地时间：<span class="text-foreground">{{
          event.localOccurredAt
        }}</span>
      </span>
    </div>

    <dl
      v-if="visibleSummaryItems.length"
      class="border-border bg-muted/40 mt-3 divide-y rounded-md border px-3"
    >
      <div
        v-for="(item, index) in visibleSummaryItems"
        :key="`${item.label}-${index}`"
        class="grid min-w-0 gap-1 py-2 sm:grid-cols-[112px_minmax(0,1fr)] sm:gap-3"
      >
        <dt class="text-muted-foreground text-xs font-medium">
          {{ item.label }}
        </dt>
        <dd class="m-0 min-w-0 text-sm">
          <div
            v-if="hasChange(item)"
            class="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2"
          >
            <span class="text-muted-foreground min-w-0 break-words">
              {{ displayValue(item.before) }}
            </span>
            <IconifyIcon
              aria-hidden="true"
              class="text-muted-foreground shrink-0"
              icon="lucide:arrow-right"
            />
            <span class="text-foreground min-w-0 break-words font-medium">
              {{ displayValue(item.after) }}
            </span>
          </div>
          <span v-else class="text-foreground break-words">
            {{ displayValue(item.value) }}
          </span>
        </dd>
      </div>
    </dl>

    <p
      v-else-if="event.extraData"
      class="text-muted-foreground mb-0 mt-2 text-sm"
    >
      Meta 未提供可识别的变更字段，可查看原始数据确认具体内容。
    </p>

    <details v-if="event.extraData" class="mt-2 text-sm">
      <summary
        class="text-muted-foreground hover:text-foreground focus-visible:ring-ring cursor-pointer select-none rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
      >
        查看原始数据
      </summary>
      <pre
        class="border-border bg-muted text-foreground mt-2 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-md border p-3 text-xs"
        >{{ formatExtraData(event.extraData) }}</pre
      >
    </details>
  </div>
</template>
