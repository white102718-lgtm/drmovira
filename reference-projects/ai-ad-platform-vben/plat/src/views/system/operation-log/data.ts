import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemOperationLogApi } from '#/api';

import { h } from 'vue';

import { Tag, Tooltip } from 'ant-design-vue';

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '操作人、目标或路径' },
      fieldName: 'keyword',
      label: '关键词',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '用户', value: 'USER' },
          { label: '角色', value: 'ROLE' },
          { label: '部门', value: 'DEPARTMENT' },
          { label: '菜单', value: 'MENU' },
          { label: 'IP 规则', value: 'IP_RULE' },
        ],
      },
      fieldName: 'moduleCode',
      label: '模块',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '新增', value: 'CREATE' },
          { label: '修改', value: 'UPDATE' },
          { label: '删除', value: 'DELETE' },
          { label: '重置密码', value: 'RESET_PASSWORD' },
          { label: '重置 MFA', value: 'RESET_MFA' },
        ],
      },
      fieldName: 'operationType',
      label: '操作类型',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '成功', value: 1 },
          { label: '失败', value: 0 },
        ],
      },
      fieldName: 'operationResult',
      label: '结果',
    },
    {
      component: 'Input',
      componentProps: { allowClear: true },
      fieldName: 'clientIp',
      label: '客户端 IP',
    },
    { component: 'RangePicker', fieldName: 'timeRange', label: '操作时间' },
  ];
}

export function useColumns(): VxeTableGridOptions<SystemOperationLogApi.OperationLog>['columns'] {
  return [
    { field: 'operatedAt', minWidth: 180, title: '操作时间' },
    { field: 'operatorDisplayName', minWidth: 130, title: '操作人' },
    { field: 'moduleCode', minWidth: 115, title: '模块' },
    { field: 'operationName', minWidth: 140, title: '操作名称' },
    { field: 'operationType', minWidth: 145, title: '操作类型' },
    {
      field: 'operationResult',
      slots: {
        default: ({ row }) =>
          h(
            Tag,
            { color: row.operationResult === 1 ? 'success' : 'error' },
            () => (row.operationResult === 1 ? '成功' : '失败'),
          ),
      },
      title: '结果',
      width: 90,
    },
    { field: 'targetType', minWidth: 130, title: '目标类型' },
    { field: 'targetId', minWidth: 100, title: '目标 ID' },
    { field: 'clientIp', minWidth: 140, title: '客户端 IP' },
    { field: 'requestMethod', title: '方法', width: 80 },
    { field: 'requestPath', minWidth: 220, title: '请求路径' },
    { field: 'failureCode', title: '失败码', width: 90 },
    {
      field: 'failureReason',
      minWidth: 210,
      slots: {
        default: ({ row }) =>
          h(Tooltip, { title: row.failureReason }, () =>
            h('span', { class: 'line-clamp-1' }, row.failureReason ?? '-'),
          ),
      },
      title: '失败原因',
    },
  ];
}
