<script lang="ts" setup>
import type { VxeGridProps } from '#/adapter/vxe-table';

import { Page } from '@vben/common-ui';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getMaterialRecommend } from '#/api/dashboard';
import PlatformSelect from '#/views/components/PlatformSelect.vue';

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
    return title === 'thumbnail'
      ? {
          field: col,
          minWidth: 150,
          slots: { default: 'image-url' },
          title: '缩略图',
        }
      : {
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
  pagerConfig: {
    pageSize: 200,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues: Record<string, any>) => {
        try {
          gridApi.setGridOptions({ loading: true });

          const currentPage = page?.currentPage || 1;
          const pageSize = page?.pageSize || 200;

          const response = await getMaterialRecommend({
            game_platform: formValues.game_platform,
            filetype: formValues.filetype,
            performance_grade: formValues.performance_grade,
            cluster_region: formValues.cluster_region,
            material_status: formValues.material_status,
            show_options: formValues.show_options,
            page: currentPage,
            pageSize,
          });

          // 根据返回的columns动态设置列配置
          const dynamicColumns = generateColumns(response.columns);
          gridApi.setGridOptions({ columns: dynamicColumns });
          return {
            page: currentPage,
            pageSize,
            total:
              response.total !== undefined && response.total !== null
                ? response.total
                : response.data.length,
            items: response.data,
          };
        } catch (error) {
          return {
            page: 1,
            pageSize: 200,
            total: 0,
            result: [],
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
      component: PlatformSelect,
      componentProps: {
        placeholder: '请选择项目名称',
      },
      fieldName: 'game_platform',
      label: '项目名称',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '图片', value: 'image' },
          { label: '视频', value: 'video' },
        ],
      },
      fieldName: 'filetype',
      label: '文件类型',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '1', value: '1' },
          { label: '2', value: '2' },
          { label: 'test', value: 'test' },
        ],
      },
      fieldName: 'performance_grade',
      label: '成效',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '顶级表现区', value: '顶级表现区' },
          { label: '改进必要区', value: '改进必要区' },
          { label: '稳定表现区', value: '稳定表现区' },
        ],
      },
      fieldName: 'cluster_region',
      label: '聚类区域',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '新', value: 'new' },
          { label: '已存在', value: 'existing' },
          { label: '未使用', value: 'unpublished' },
        ],
      },
      fieldName: 'material_status',
      label: '素材状态',
    },
  ],
  showCollapseButton: false,
  wrapperClass: 'grid grid-cols-6',
};

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions,
  gridOptions: materialStatsGridOptions,
  tableTitle: '素材统计数据',
});
</script>

<template>
  <Page
    class="bg-muted/40 flex h-full min-h-0 flex-col [&>div]:m-0 [&>div]:p-0"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden"
    description="根据历史表现筛选可复用素材，为新一轮投放提供参考。"
    title="素材推荐"
  >
    <div class="ux-fill-grid-host min-h-0 min-w-0 flex-1 overflow-hidden">
      <Grid class="h-full">
      <template #image-url="{ row }">
        <img
          v-if="row && row.thumbnail"
          v-tippy="{
            content: `<img src='data:image/png;base64,${row.thumbnail}' alt='推荐素材预览' style='min-width: 200px; min-height: 200px; width: auto; height: auto;' />`,
            allowHTML: true,
            placement: 'right',
            theme: 'light',
            hideOnClick: false,
            arrow: true,
            delay: [0, 0],
            duration: [0, 0],
          }"
          :src="`data:image/png;base64,${row.thumbnail}`"
          alt="推荐素材缩略图"
          style="
            width: 120px;
            height: 120px;
            cursor: pointer;
            object-fit: cover;
          "
        />
      </template>
      </Grid>
    </div>
  </Page>
</template>
