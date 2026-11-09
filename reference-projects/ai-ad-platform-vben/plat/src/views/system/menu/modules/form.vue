<script lang="ts" setup>
import type { VbenFormSchema } from '#/adapter/form';
import type { SystemMenuApi } from '#/api';

import { computed, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { z, useVbenForm } from '#/adapter/form';
import { createMenu, getMenuList, updateMenu } from '#/api';

const emit = defineEmits(['success']);
const editingId = ref<string>();

type TreeOption = {
  children?: TreeOption[];
  label: string;
  value: string;
};

function toOptions(nodes: SystemMenuApi.Menu[]): TreeOption[] {
  return nodes.map((node) => ({
    children: toOptions(node.children ?? []),
    label: `${node.menuName}（${node.menuType === 1 ? '目录' : node.menuType === 2 ? '菜单' : '按钮'}）`,
    value: node.id,
  }));
}

function schema(treeData: TreeOption[]): VbenFormSchema[] {
  return [
    {
      component: 'TreeSelect',
      componentProps: { treeData, treeDefaultExpandAll: true },
      defaultValue: '0',
      fieldName: 'parentId',
      label: '上级节点',
      rules: 'required',
    },
    {
      component: 'RadioGroup',
      componentProps: {
        buttonStyle: 'solid',
        options: [
          { label: '目录', value: 1 },
          { label: '菜单', value: 2 },
          { label: '按钮', value: 3 },
        ],
        optionType: 'button',
      },
      defaultValue: 2,
      fieldName: 'menuType',
      label: '节点类型',
      rules: 'required',
    },
    {
      component: 'Input',
      fieldName: 'menuName',
      label: '菜单名称',
      rules: 'required',
    },
    {
      component: 'Input',
      componentProps: { placeholder: '例如 SYSTEM_USER' },
      fieldName: 'menuCode',
      label: '菜单编码',
      rules: 'required',
    },
    {
      component: 'Input',
      dependencies: {
        rules: (values) => (values.menuType === 2 ? 'required' : null),
        show: (values) => values.menuType !== 3,
        triggerFields: ['menuType'],
      },
      fieldName: 'routePath',
      label: '路由路径',
      rules: z
        .string()
        .refine((value) => value.startsWith('/'), '路由路径必须以 / 开头')
        .optional(),
    },
    {
      component: 'AutoComplete',
      componentProps: {
        class: 'w-full',
        options: Object.keys(import.meta.glob('../../../**/*.vue')).map(
          (path) => ({
            value: path
              .replace(/^\.\.\/\.\.\/\.\.\//, '')
              .replace(/\.vue$/, ''),
          }),
        ),
      },
      dependencies: {
        rules: (values) => (values.menuType === 2 ? 'required' : null),
        show: (values) => values.menuType === 2,
        triggerFields: ['menuType'],
      },
      fieldName: 'component',
      help: '相对于 views 的组件路径，例如 system/user/list',
      label: '组件路径',
    },
    {
      component: 'Input',
      fieldName: 'permissionCode',
      help: '例如 system:user:list',
      label: '权限标识',
    },
    {
      component: 'IconPicker',
      componentProps: { prefix: 'carbon' },
      dependencies: {
        show: (values) => values.menuType !== 3,
        triggerFields: ['menuType'],
      },
      fieldName: 'icon',
      label: '图标',
    },
    {
      component: 'Input',
      dependencies: {
        show: (values) => values.menuType === 2,
        triggerFields: ['menuType'],
      },
      fieldName: 'externalLink',
      label: '外链地址',
    },
    {
      component: 'RadioGroup',
      componentProps: {
        options: [
          { label: '显示', value: 1 },
          { label: '隐藏', value: 0 },
        ],
        optionType: 'button',
      },
      defaultValue: 1,
      dependencies: {
        show: (values) => values.menuType !== 3,
        triggerFields: ['menuType'],
      },
      fieldName: 'visible',
      label: '菜单可见',
    },
    {
      component: 'RadioGroup',
      componentProps: {
        options: [
          { label: '缓存', value: 1 },
          { label: '不缓存', value: 0 },
        ],
        optionType: 'button',
      },
      defaultValue: 0,
      dependencies: {
        show: (values) => values.menuType === 2,
        triggerFields: ['menuType'],
      },
      fieldName: 'cacheable',
      label: '页面缓存',
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

const [Form, formApi] = useVbenForm({
  schema: [],
  showDefaultActions: false,
});

const title = computed(() => (editingId.value ? '编辑菜单' : '新增菜单'));

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;
    const values = await formApi.getValues<SystemMenuApi.SaveRequest>();
    const payload: SystemMenuApi.SaveRequest = {
      ...values,
      cacheable: values.menuType === 2 ? (values.cacheable ?? 0) : 0,
      component: values.component?.trim() || undefined,
      externalLink: values.externalLink?.trim() || undefined,
      icon: values.icon?.trim() || undefined,
      permissionCode: values.permissionCode?.trim() || undefined,
      remark: values.remark?.trim() || undefined,
      routePath: values.routePath?.trim() || undefined,
      sortOrder: values.sortOrder ?? 0,
      visible: values.menuType === 3 ? 0 : (values.visible ?? 1),
    };
    drawerApi.lock();
    try {
      if (editingId.value) {
        await updateMenu(editingId.value, payload);
      } else {
        await createMenu(payload);
      }
      drawerApi.close();
      emit('success');
    } finally {
      drawerApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;
    drawerApi.lock();
    try {
      formApi.resetForm();
      const tree = await getMenuList();
      formApi.setState({
        schema: schema([{ label: '根节点', value: '0' }, ...toOptions(tree)]),
      });
      const data = drawerApi.getData<
        Partial<SystemMenuApi.Menu> & { parentId?: string }
      >();
      editingId.value = data?.id;
      await formApi.setValues(
        data?.id
          ? data
          : {
              cacheable: 0,
              menuType: 2,
              parentId: data?.parentId ?? '0',
              sortOrder: 0,
              status: 1,
              visible: 1,
            },
      );
    } finally {
      drawerApi.unlock();
    }
  },
});
</script>

<template>
  <Drawer class="w-full max-w-[640px]" :title="title">
    <Form />
  </Drawer>
</template>
