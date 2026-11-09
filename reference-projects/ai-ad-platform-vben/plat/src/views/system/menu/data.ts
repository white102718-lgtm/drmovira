import type { OnActionClickFn, VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemMenuApi } from '#/api';

import { h } from 'vue';

import { Tag } from 'ant-design-vue';

const menuTypeMeta = {
  1: { color: 'blue', label: '目录' },
  2: { color: 'green', label: '菜单' },
  3: { color: 'orange', label: '按钮' },
} as const;

export function useColumns(
  onActionClick: OnActionClickFn<SystemMenuApi.Menu>,
): VxeTableGridOptions<SystemMenuApi.Menu>['columns'] {
  return [
    {
      field: 'menuName',
      minWidth: 230,
      title: '菜单名称',
      treeNode: true,
    },
    { field: 'menuCode', minWidth: 190, title: '菜单编码' },
    {
      field: 'menuType',
      slots: {
        default: ({ row }) => {
          const meta = menuTypeMeta[row.menuType];
          return h(Tag, { color: meta.color }, () => meta.label);
        },
      },
      title: '类型',
      width: 90,
    },
    { field: 'permissionCode', minWidth: 210, title: '权限标识' },
    { field: 'routePath', minWidth: 180, title: '路由路径' },
    { field: 'component', minWidth: 180, title: '组件路径' },
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
    {
      align: 'center',
      cellRender: {
        attrs: {
          nameField: 'menuName',
          nameTitle: '菜单',
          onClick: onActionClick,
        },
        name: 'CellOperation',
        options: [{ code: 'append', text: '新增下级' }, 'edit', 'delete'],
      },
      field: 'operation',
      fixed: 'right',
      title: '操作',
      width: 150,
    },
  ];
}
