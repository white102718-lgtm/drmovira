import type { VbenFormSchema } from '#/adapter/form';
import type { OnActionClickFn, VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemDepartmentApi } from '#/api';

import { h } from 'vue';

import { Tag } from 'ant-design-vue';

import { z } from '#/adapter/form';

export function useFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'TreeSelect',
      componentProps: {
        allowClear: false,
        treeDefaultExpandAll: true,
      },
      defaultValue: '0',
      fieldName: 'parentId',
      label: '上级部门',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: { placeholder: '例如 SALES_EAST' },
      fieldName: 'deptCode',
      label: '部门编码',
      rules: z
        .string()
        .trim()
        .toUpperCase()
        .regex(
          /^[A-Z][A-Z0-9_]{1,63}$/,
          '请输入2–64位部门编码，仅支持字母、数字和下划线，且以字母开头',
        ),
    },
    {
      component: 'Input',
      fieldName: 'deptName',
      label: '部门名称',
      rules: 'required',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        // 选项值是用户 ID，搜索应匹配展示的姓名和手机号。
        optionFilterProp: 'label',
        showSearch: true,
      },
      fieldName: 'leaderUserId',
      label: '部门负责人',
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
  ];
}

export function useColumns(
  onActionClick: OnActionClickFn<SystemDepartmentApi.Department>,
): VxeTableGridOptions<SystemDepartmentApi.Department>['columns'] {
  return [
    {
      field: 'deptName',
      minWidth: 220,
      title: '部门名称',
      treeNode: true,
    },
    { field: 'deptCode', minWidth: 180, title: '部门编码' },
    {
      field: 'sourceType',
      formatter: ({ row }) =>
        row.sourceType === 'FEISHU' ? '飞书同步维护' : '手工维护',
      minWidth: 130,
      title: '来源',
    },
    { field: 'level', title: '层级', width: 80 },
    { field: 'leaderUserId', minWidth: 130, title: '负责人用户 ID' },
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
    { field: 'remark', minWidth: 160, title: '备注' },
    {
      align: 'center',
      cellRender: {
        attrs: {
          nameField: 'deptName',
          nameTitle: '部门',
          onClick: onActionClick,
        },
        name: 'CellOperation',
        // 与后端同步维护规则保持一致，飞书部门不进入手工编码校验流程。
        options: [
          { code: 'append', text: '新增下级' },
          {
            code: 'edit',
            show: (row: SystemDepartmentApi.Department) =>
              row.sourceType !== 'FEISHU',
          },
          {
            code: 'delete',
            show: (row: SystemDepartmentApi.Department) =>
              row.sourceType !== 'FEISHU',
          },
        ],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 150,
    },
  ];
}
