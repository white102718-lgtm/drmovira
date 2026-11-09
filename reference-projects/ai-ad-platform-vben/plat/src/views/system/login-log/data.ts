import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemLoginLogApi } from '#/api';

import { h } from 'vue';

import { Tag, Tooltip } from 'ant-design-vue';

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '账号或显示名称' },
      fieldName: 'keyword',
      label: '关键词',
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
      fieldName: 'loginResult',
      label: '结果',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '密码认证', value: 1 },
          { label: '首次绑定 MFA', value: 2 },
          { label: '验证 MFA', value: 3 },
          { label: '飞书授权', value: 4 },
        ],
      },
      fieldName: 'authStage',
      label: '认证阶段',
    },
    {
      component: 'Input',
      componentProps: { allowClear: true },
      fieldName: 'clientIp',
      label: '客户端 IP',
    },
    { component: 'RangePicker', fieldName: 'timeRange', label: '登录时间' },
  ];
}

export function useColumns(): VxeTableGridOptions<SystemLoginLogApi.LoginLog>['columns'] {
  const stages: Record<SystemLoginLogApi.LoginLog['authStage'], string> = {
    1: '密码认证',
    2: '首次绑定 MFA',
    3: '验证 MFA',
    4: '飞书授权',
  };
  return [
    { field: 'loginAt', title: '登录时间', width: 180 },
    { field: 'displayName', title: '显示名称', width: 140 },
    { field: 'username', title: '登录账号', width: 150 },
    { field: 'loginIdentifier', title: '登录标识', width: 180 },
    {
      field: 'authStage',
      formatter: ({ row }) => stages[row.authStage] ?? String(row.authStage),
      title: '认证阶段',
      width: 150,
    },
    {
      field: 'loginResult',
      slots: {
        default: ({ row }) =>
          h(Tag, { color: row.loginResult === 1 ? 'success' : 'error' }, () =>
            row.loginResult === 1 ? '成功' : '失败',
          ),
      },
      title: '结果',
      width: 90,
    },
    { field: 'clientIp', title: '客户端 IP', width: 150 },
    { field: 'failureCode', title: '失败码', width: 100 },
    {
      field: 'failureReason',
      slots: {
        default: ({ row }) =>
          h(Tooltip, { title: row.failureReason }, () =>
            h('span', { class: 'line-clamp-1' }, row.failureReason ?? '-'),
          ),
      },
      title: '失败原因',
      width: 280,
    },
    {
      field: 'userAgent',
      title: 'User-Agent',
      width: 320,
    },
  ];
}
