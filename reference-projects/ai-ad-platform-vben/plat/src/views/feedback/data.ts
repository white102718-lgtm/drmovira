import type { VbenFormSchema } from '#/adapter/form';
import type { OnActionClickFn, VxeTableGridOptions } from '#/adapter/vxe-table';
import type { FeedbackListItem } from '#/api';

import { h } from 'vue';

import { Tag, Tooltip } from 'ant-design-vue';

const categoryLabels = {
  BUG: '问题反馈',
  EXPERIENCE: '体验建议',
  FEATURE: '功能需求',
};

const statusMeta = {
  CLOSED: { color: 'default', label: '已关闭' },
  PENDING: { color: 'warning', label: '待跟进' },
  PROCESSING: { color: 'processing', label: '跟进中' },
  RESOLVED: { color: 'success', label: '已解决' },
};

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '编号、标题、内容、提交人、负责人或 IP',
      },
      fieldName: 'keyword',
      label: '关键词',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: Object.entries(categoryLabels).map(([value, label]) => ({
          label,
          value,
        })),
      },
      fieldName: 'category',
      label: '反馈类型',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: Object.entries(statusMeta).map(([value, meta]) => ({
          label: meta.label,
          value,
        })),
      },
      fieldName: 'status',
      label: '跟进状态',
    },
  ];
}

export function useColumns(
  onActionClick: OnActionClickFn<FeedbackListItem>,
): VxeTableGridOptions<FeedbackListItem>['columns'] {
  return [
    { field: 'createdAt', minWidth: 180, title: '提交时间' },
    {
      field: 'category',
      slots: {
        default: ({ row }) =>
          h(Tag, {}, () => categoryLabels[row.category] ?? row.category),
      },
      title: '类型',
      width: 110,
    },
    {
      field: 'title',
      minWidth: 240,
      showOverflow: 'tooltip',
      title: '反馈标题',
    },
    {
      field: 'status',
      slots: {
        default: ({ row }) => {
          const meta = statusMeta[row.status] ?? {
            color: 'default',
            label: row.status,
          };
          return h(Tag, { color: meta.color }, () => meta.label);
        },
      },
      title: '状态',
      width: 100,
    },
    {
      field: 'ownerName',
      minWidth: 120,
      slots: {
        default: ({ row }) => row.ownerName || '未分配',
      },
      title: '负责人',
    },
    {
      field: 'submittedByName',
      minWidth: 150,
      slots: {
        default: ({ row }) =>
          h(
            Tooltip,
            { title: row.submittedByUsername || undefined },
            () => row.submittedByName,
          ),
      },
      title: '提交账号',
    },
    { field: 'clientIp', minWidth: 140, title: '客户端 IP' },
    { field: 'deviceType', title: '设备', width: 100 },
    {
      align: 'right',
      field: 'attachmentCount',
      title: '附件数',
      width: 90,
    },
    {
      align: 'center',
      cellRender: {
        attrs: { onClick: onActionClick },
        name: 'CellOperation',
        options: [{ code: 'view', text: '查看' }],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 90,
    },
  ];
}

export { categoryLabels, statusMeta };
