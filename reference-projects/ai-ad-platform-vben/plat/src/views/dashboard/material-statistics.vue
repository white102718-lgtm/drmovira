<script lang="ts" setup>
import type { Dayjs } from 'dayjs';

import type { VxeGridProps } from '#/adapter/vxe-table';

import { computed } from 'vue';

import { Page } from '@vben/common-ui';

import { Alert, Button } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getMaterialStatistics } from '#/api/dashboard';
import { useMaterialFilterOptions } from '#/composables/useMaterialFilterOptions';

const { filterOptions, optionsError, optionsLoading, reloadOptions } =
  useMaterialFilterOptions();

const rangePresets = computed(() => [
  { label: '今天', value: [dayjs.tz(), dayjs.tz()] },
  {
    label: '昨天',
    value: [dayjs.tz().subtract(1, 'd'), dayjs.tz().subtract(1, 'd')],
  },
  { label: '过去 7 天', value: [dayjs.tz().subtract(6, 'd'), dayjs.tz()] },
  { label: '过去 14 天', value: [dayjs.tz().subtract(13, 'd'), dayjs.tz()] },
  { label: '过去 30 天', value: [dayjs.tz().subtract(29, 'd'), dayjs.tz()] },
  { label: '本周', value: [dayjs.tz().startOf('isoWeek'), dayjs.tz()] },
  {
    label: '上周',
    value: [
      dayjs.tz().subtract(1, 'week').startOf('isoWeek'),
      dayjs.tz().subtract(1, 'week').endOf('isoWeek'),
    ],
  },
  { label: '本月', value: [dayjs.tz().startOf('month'), dayjs.tz()] },
  {
    label: '上个月',
    value: [
      dayjs.tz().subtract(1, 'month').startOf('month'),
      dayjs.tz().subtract(1, 'month').endOf('month'),
    ],
  },
  { label: '90天', value: [dayjs.tz().subtract(90, 'd'), dayjs.tz()] },
]);

// 根据API返回的列名动态生成列配置
const generateColumns = (columns: string[]) => {
  // 计算字符串宽度：中文字符计20px，英文字符计8px
  const calculateWidth = (str: string): number => {
    if (!str) return 80; // 如果是空字符串，返回默认宽度

    let width = 0;
    for (let i = 0; i < str.length; i++) {
      // 判断是否为中文字符（包括中日韩统一表意文字）
      const isChinese = /[\u4E00-\u9FFF]/.test(str.charAt(i));
      width += isChinese ? 20 : 8;
    }
    return width;
  };

  return columns.map((col) => {
    const title = String(col || '');
    return {
      field: col,
      minWidth: Math.max(calculateWidth(title), 90),
      showOverflow: true,
      sortable: true,
      title: col,
    };
  });
};

// 设置表格选项
const materialStatsGridOptions: VxeGridProps<Record<string, any>> = {
  columns: [],
  height: '100%',
  keepSource: true,
  layouts: ['Top', 'Form', 'Toolbar', 'Table', 'Bottom'],
  minHeight: 0,
  pagerConfig: {
    enabled: true,
    pageSize: 100_000,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues: Record<string, any>) => {
        try {
          gridApi.setGridOptions({ loading: true });

          const currentPage = page?.currentPage || 1;
          const pageSize = page?.pageSize || 10_000;

          const response = await getMaterialStatistics(
            formValues.dateRange?.[0],
            formValues.dateRange?.[1],
            formValues.game_platform,
            formValues.ad_platform,
            formValues.agent_line,
            formValues.ad_name,
            currentPage,
            pageSize,
          );

          // 根据返回的columns动态设置列配置
          const dynamicColumns = generateColumns(response.columns);
          gridApi.setGridOptions({ columns: dynamicColumns });
          return {
            page: currentPage,
            page_size: pageSize,
            total: response.total ?? response.data.length,
            items: response.data,
          };
        } catch {
          return {
            page: 1,
            page_size: 100_000,
            total: 0,
            items: [],
          };
        } finally {
          gridApi.setGridOptions({ loading: false });
        }
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: {
    refresh: true,
  },
  virtualYConfig: {
    enabled: false,
  },
};

// 表单配置
const formOptions = {
  schema: [
    {
      component: 'RangePicker',
      componentProps: {
        allowClear: true,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: 'YYYY-MM-DD',
        placeholder: ['开始日期', '结束日期'],
        style: { width: '100%' },
        valueFormat: 'YYYY-MM-DD',
        presets: rangePresets,
      },
      defaultValue: [
        dayjs.tz().format('YYYY-MM-DD'),
        dayjs.tz().format('YYYY-MM-DD'),
      ],
      fieldName: 'dateRange',
      label: '日期范围',
    },
    {
      component: 'Select',
      componentProps: () => ({
        allowClear: true,
        loading: optionsLoading.value,
        showSearch: true,
        optionFilterProp: 'label',
        options: (filterOptions.value?.projects ?? []).map((name) => ({
          label: name,
          value: name,
        })),
        placeholder: '全部项目',
        style: { width: '100%' },
      }),
      fieldName: 'game_platform',
      label: '项目名称',
    },
    // 旧成效接口支持这两个文本条件；公共接口的渠道商不等于广告平台或代理线。
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入广告平台',
        style: { width: '100%' },
      },
      fieldName: 'ad_platform',
      label: '广告平台',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入代理线',
        style: { width: '100%' },
      },
      fieldName: 'agent_line',
      label: '代理线',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入广告名称',
        style: { width: '100%' },
      },
      fieldName: 'ad_name',
      label: '广告名称',
    },
  ],
  showCollapseButton: false,
  wrapperClass: 'grid grid-cols-3',
};

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions,
  gridOptions: materialStatsGridOptions,
  tableTitle: '素材统计数据',
});
</script>

<template>
  <Page
    class="bg-muted/40 flex h-full min-h-0 flex-col"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden"
    description="按素材维度查看投放表现，快速定位高效与待优化内容。"
    title="素材效果统计"
  >
    <Alert
      v-if="optionsError"
      class="mb-4"
      type="error"
      show-icon
      message="筛选项加载失败，请重新加载。"
    >
      <template #action>
        <Button :loading="optionsLoading" @click="reloadOptions">
          重新加载
        </Button>
      </template>
    </Alert>
    <div class="ux-fill-grid-host min-h-0 min-w-0 flex-1 overflow-hidden">
      <Grid class="h-full" />
    </div>
  </Page>
</template>
