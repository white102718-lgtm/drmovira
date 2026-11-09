<script setup lang="ts">
/**
 * DateRangePicker 日期范围选择器组件
 *
 * 使用说明：
 * - 使用 v-model:value 进行双向绑定
 * - ⚠️ 推荐使用 @update:value 事件而不是 @confirm 事件
 * - 原因：@confirm 触发时 v-model 可能还未更新完成，会导致父组件读取到旧值
 * - @update:value 会在值更新后触发，确保父组件能获取到最新值
 *
 * 示例：
 * <DateRangePicker
 *   v-model:value="dateRange"
 *   @update:value="handleDateChange"  // ✅ 推荐
 * />
 *
 * 不推荐：
 * <DateRangePicker
 *   v-model:value="dateRange"
 *   @confirm="handleDateChange"  // ❌ 可能读取到旧值
 * />
 */
import { computed, ref } from 'vue';

import type { Dayjs } from 'dayjs';

import DatePicker from 'ant-design-vue/es/date-picker';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(isoWeek);
import { toLocalDayEnd, toLocalDayStart } from '#/utils/tz';

interface Props {
  clearable?: boolean;
  format?: string;
  isDateDisabled?: (ts: number) => boolean;
  size?: 'large' | 'middle' | 'small';
  shortcuts?: Record<string, [number, number]>;
  timePickerFormat?: string; // 时间选择器的格式
  type?: 'daterange' | 'datetimerange'; // 支持日期和日期时间范围
  value?: [number, number] | null;
  width?: string;
}

const props = withDefaults(defineProps<Props>(), {
  format: 'yyyy-MM-dd',
  width: '160px',
  type: 'daterange',
  clearable: true,
  value: () => [dayjs.tz().valueOf(), dayjs.tz().valueOf()],
});

// 面板打开时刷新当前时间
const now = ref(dayjs.tz());

const handleShowChange = (show: boolean) => {
  if (show) now.value = dayjs.tz();
};

const resolvedIsDateDisabled = computed(
  () => props.isDateDisabled ?? ((ts: number) => ts > toLocalDayEnd(now.value)),
);

const resolvedShortcuts = computed(
  () =>
    props.shortcuts ??
    ({
      今天: [toLocalDayStart(now.value), toLocalDayEnd(now.value)] as [
        number,
        number,
      ],
      昨天: [
        toLocalDayStart(now.value.subtract(1, 'd')),
        toLocalDayEnd(now.value.subtract(1, 'd')),
      ] as [number, number],
      过去7天: [
        toLocalDayStart(now.value.subtract(6, 'd')),
        toLocalDayEnd(now.value),
      ] as [number, number],
      过去14天: [
        toLocalDayStart(now.value.subtract(13, 'd')),
        toLocalDayEnd(now.value),
      ] as [number, number],
      过去30天: [
        toLocalDayStart(now.value.subtract(29, 'd')),
        toLocalDayEnd(now.value),
      ] as [number, number],
      本周: [
        toLocalDayStart(now.value.startOf('isoWeek')),
        toLocalDayEnd(now.value),
      ] as [number, number],
      上周: [
        toLocalDayStart(now.value.subtract(1, 'week').startOf('isoWeek')),
        toLocalDayEnd(now.value.subtract(1, 'week').endOf('isoWeek')),
      ] as [number, number],
      本月: [
        toLocalDayStart(now.value.startOf('month')),
        toLocalDayEnd(now.value),
      ] as [number, number],
      上个月: [
        toLocalDayStart(now.value.subtract(1, 'month').startOf('month')),
        toLocalDayEnd(now.value.subtract(1, 'month').endOf('month')),
      ] as [number, number],
      '90天': [
        toLocalDayStart(now.value.subtract(90, 'd')),
        toLocalDayEnd(now.value),
      ] as [number, number],
    } satisfies Record<string, [number, number]>),
);

const emit = defineEmits<{
  (e: 'update:value', value: [number, number] | null): void;
  (e: 'confirm', value: [number, number] | null): void;
}>();

// 动态生成 style，确保宽度在生产环境也生效
const inputStyle = computed(() => {
  const widthValue = Number.parseInt(props.width);
  const finalWidth = widthValue < 80 ? '80px' : props.width;
  return {
    width: finalWidth,
  };
});

const pickerValue = computed<[Dayjs, Dayjs] | null>({
  get: () =>
    props.value?.length === 2
      ? [dayjs(props.value[0]), dayjs(props.value[1])]
      : null,
  set: (value) => handleUpdate(value),
});

// 兼容旧日期格式：Day.js 用 DD 表示日期，小写 dd 会被格式化为星期简称。
const pickerFormat = computed(() =>
  props.format.replaceAll('yyyy', 'YYYY').replaceAll('dd', 'DD'),
);
const pickerPresets = computed(() =>
  Object.entries(resolvedShortcuts.value).map(([label, [start, end]]) => ({
    label,
    value: [dayjs(start), dayjs(end)] as [Dayjs, Dayjs],
  })),
);
const showTime = computed(() =>
  props.type === 'datetimerange' ? { format: props.timePickerFormat } : false,
);

function handleUpdate(value: [Dayjs, Dayjs] | null) {
  const nextValue = value
    ? ([value[0].valueOf(), value[1].valueOf()] as [number, number])
    : null;
  emit('update:value', nextValue);
  if (nextValue) emit('confirm', nextValue);
}

function disabledDate(current: Dayjs) {
  return resolvedIsDateDisabled.value(current.valueOf());
}
</script>

<template>
  <DatePicker.RangePicker
    v-model:value="pickerValue"
    :allow-clear="clearable"
    :disabled-date="disabledDate"
    :format="pickerFormat"
    :presets="pickerPresets"
    :size="size"
    :show-time="showTime"
    :style="inputStyle"
    @open-change="handleShowChange"
  >
    <template v-if="$slots.footer" #renderExtraFooter>
      <slot name="footer"></slot>
    </template>
  </DatePicker.RangePicker>
</template>
