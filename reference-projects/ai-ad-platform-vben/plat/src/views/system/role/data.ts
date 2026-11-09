import type { VbenFormSchema } from '#/adapter/form';
import type { OnActionClickFn, VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemRoleApi, SystemUserApi } from '#/api';

import { h } from 'vue';

import { Tag } from 'ant-design-vue';
import { z } from '#/adapter/form';

/** 新增和编辑角色均允许维护唯一编码。 */
export function useFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { maxLength: 64, placeholder: '请输入角色编码' },
      fieldName: 'roleCode',
      label: '角色编码',
      rules: z
        .string()
        .trim()
        .min(1, '请输入角色编码')
        .max(64, '角色编码不能超过64个字符'),
    },
    {
      component: 'Input',
      fieldName: 'roleName',
      label: '角色名称',
      rules: 'required',
    },
    {
      component: 'InputNumber',
      componentProps: { class: 'w-full', min: 0 },
      defaultValue: 0,
      fieldName: 'sortOrder',
      label: '排序',
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
    {
      component: 'Input',
      fieldName: 'menuIds',
      formItemClass: 'items-start',
      label: '菜单权限',
      modelPropName: 'modelValue',
    },
  ];
}

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '编码或名称' },
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
  onActionClick: OnActionClickFn<SystemRoleApi.Role>,
): VxeTableGridOptions<SystemRoleApi.Role>['columns'] {
  return [
    { field: 'roleName', minWidth: 150, title: '角色名称' },
    { field: 'roleCode', minWidth: 180, title: '角色编码' },
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
    { field: 'sortOrder', title: '排序', width: 80 },
    { field: 'remark', minWidth: 180, title: '备注' },
    { field: 'createdAt', minWidth: 180, title: '创建时间' },
    {
      align: 'center',
      cellRender: {
        attrs: {
          nameField: 'roleName',
          nameTitle: '角色',
          onClick: onActionClick,
        },
        name: 'CellOperation',
        options: [{ code: 'members', text: '成员' }, 'edit', 'delete'],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 140,
    },
  ];
}

/** 角色成员页只维护当前角色关系，不提供用户账号维护操作。 */
export function useMemberColumns(
  onActionClick: OnActionClickFn<SystemUserApi.User>,
): VxeTableGridOptions<SystemUserApi.User>['columns'] {
  return [
    { field: 'displayName', minWidth: 150, title: '显示名称' },
    { field: 'realName', minWidth: 120, title: '真实姓名' },
    { field: 'phone', minWidth: 150, title: '手机号' },
    { field: 'email', minWidth: 180, title: '邮箱' },
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
    { field: 'createdAt', minWidth: 180, title: '创建时间' },
    {
      align: 'center',
      cellRender: {
        attrs: {
          nameField: 'displayName',
          nameTitle: '用户',
          onClick: onActionClick,
        },
        name: 'CellOperation',
        options: [{ code: 'removeRole', text: '移除角色' }],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 120,
    },
  ];
}
