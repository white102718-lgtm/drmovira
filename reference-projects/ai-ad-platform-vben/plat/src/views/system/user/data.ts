import type { VbenFormSchema } from '#/adapter/form';
import type { OnActionClickFn, VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemUserApi } from '#/api';

import { h } from 'vue';

import { Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

import { z } from '#/adapter/form';

import PhoneNumberInput from './modules/phone-number-input.vue';

const SHANGHAI_TIME_ZONE = 'Asia/Shanghai';

function formatShanghaiDateTime(value: unknown) {
  if (!value) return '';
  return dayjs
    .tz(String(value), SHANGHAI_TIME_ZONE)
    .format('YYYY-MM-DD HH:mm:ss');
}

export function useFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      fieldName: 'displayName',
      label: '显示名称',
      rules: 'required',
    },
    {
      component: PhoneNumberInput,
      componentProps: { countryCodeMode: 'input' },
      fieldName: 'phone',
      label: '手机号',
      modelPropName: 'value',
      rules: z
        .string()
        .min(1, { message: '请输入手机号' })
        .regex(/^\+[1-9]\d{7,14}$/, '请输入正确的国际手机号'),
    },
    {
      component: 'InputPassword',
      componentProps: { autocomplete: 'new-password' },
      fieldName: 'password',
      help: '新建时必填，8–72 位；编辑时留空表示不修改',
      label: '密码',
    },
    {
      component: 'Input',
      fieldName: 'realName',
      label: '真实姓名',
    },
    {
      component: 'Input',
      fieldName: 'englishNickname',
      label: '英文昵称',
    },
    {
      component: 'Input',
      fieldName: 'email',
      label: '邮箱',
      rules: z.string().email('请输入正确的邮箱').or(z.literal('')).optional(),
    },
    {
      component: 'TreeSelect',
      componentProps: {
        allowClear: true,
        placeholder: '请选择主部门',
        treeDefaultExpandAll: true,
      },
      fieldName: 'primaryDepartmentId',
      label: '主部门',
    },
    {
      component: 'Select',
      componentProps: { allowClear: true, mode: 'multiple' },
      fieldName: 'roleIds',
      label: '角色',
    },
    {
      component: 'RadioGroup',
      componentProps: {
        buttonStyle: 'solid',
        options: [
          { label: '启用', value: 1 },
          { label: '停用', value: 0 },
        ],
        optionType: 'button',
      },
      defaultValue: 1,
      fieldName: 'status',
      label: '状态',
    },
    {
      component: 'Textarea',
      fieldName: 'remark',
      label: '备注',
    },
  ];
}

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '手机号或名称',
      },
      fieldName: 'keyword',
      label: '关键词',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '启用', value: 1 },
          { label: '停用', value: 0 },
        ],
      },
      fieldName: 'status',
      label: '状态',
    },
  ];
}

export function useColumns(
  onActionClick: OnActionClickFn<SystemUserApi.User>,
  getDepartmentName: (id: null | string | undefined) => string,
): VxeTableGridOptions<SystemUserApi.User>['columns'] {
  return [
    { field: 'id', minWidth: 90, title: 'ID' },
    { field: 'displayName', minWidth: 130, title: '显示名称' },
    { field: 'phone', minWidth: 125, title: '手机号' },
    { field: 'realName', minWidth: 120, title: '真实姓名' },
    {
      field: 'englishNickname',
      minWidth: 130,
      showOverflow: 'tooltip',
      title: '英文昵称',
    },
    {
      field: 'primaryDepartmentId',
      minWidth: 160,
      showOverflow: 'tooltip',
      slots: {
        default: ({ row }) => getDepartmentName(row.primaryDepartmentId),
      },
      title: '所属部门',
    },
    {
      field: 'status',
      slots: {
        default: ({ row }) =>
          h(Tag, { color: row.status === 1 ? 'success' : 'default' }, () =>
            row.status === 1 ? '启用' : '停用',
          ),
      },
      title: '状态',
      width: 90,
    },
    {
      field: 'mfaStatus',
      slots: {
        default: ({ row }) =>
          h(Tag, { color: row.mfaStatus === 1 ? 'blue' : 'default' }, () =>
            row.mfaStatus === 1 ? '已绑定' : '未绑定',
          ),
      },
      title: 'MFA',
      width: 100,
    },
    {
      field: 'lastLoginIp',
      minWidth: 130,
      title: '最后登录 IP',
      visible: false,
    },
    {
      field: 'lastLoginAt',
      formatter: ({ cellValue }) => formatShanghaiDateTime(cellValue),
      minWidth: 180,
      title: '最后登录时间',
      visible: false,
    },
    {
      field: 'createdAt',
      formatter: ({ cellValue }) => formatShanghaiDateTime(cellValue),
      minWidth: 180,
      title: '创建时间',
    },
    {
      align: 'center',
      cellRender: {
        attrs: {
          nameField: 'displayName',
          nameTitle: '用户',
          onClick: onActionClick,
        },
        name: 'CellOperation',
        options: [
          'edit',
          { code: 'resetPassword', text: '重置密码' },
          { code: 'resetMfa', text: '重置 MFA' },
          'delete',
        ],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 150,
    },
  ];
}
