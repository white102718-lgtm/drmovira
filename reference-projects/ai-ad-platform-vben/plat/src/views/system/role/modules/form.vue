<script lang="ts" setup>
import type { SystemMenuApi, SystemRoleApi } from '#/api';

import { computed, ref } from 'vue';

import { useVbenDrawer, VbenTree } from '@vben/common-ui';

import { Spin } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { createRole, getMenuList, getRoleDetail, updateRole } from '#/api';

import { useFormSchema } from '../data';

const emit = defineEmits(['success']);
const editingId = ref<string>();
const menus = ref<SystemMenuApi.Menu[]>([]);
const loading = ref(false);

const [Form, formApi] = useVbenForm({
  schema: useFormSchema(),
  showDefaultActions: false,
});

const title = computed(() => (editingId.value ? '编辑角色' : '新增角色'));

/** 停用父菜单不连带隐藏仍启用的子菜单，子菜单会提升到当前层级。 */
function filterEnabledMenus(
  tree: SystemMenuApi.Menu[],
): SystemMenuApi.Menu[] {
  return tree.flatMap((menu) => {
    const children = filterEnabledMenus(menu.children ?? []);
    if (menu.status !== 1) return children;
    return [{ ...menu, children }];
  });
}

function collectMenuIds(tree: SystemMenuApi.Menu[]): Set<string> {
  const ids = new Set<string>();
  const visit = (items: SystemMenuApi.Menu[]) => {
    items.forEach((menu) => {
      ids.add(menu.id);
      visit(menu.children ?? []);
    });
  };
  visit(tree);
  return ids;
}

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;
    const values = await formApi.getValues<SystemRoleApi.SaveRequest>();
    const payload: SystemRoleApi.SaveRequest = {
      menuIds: values.menuIds ?? [],
      remark: values.remark?.trim() || undefined,
      roleCode: values.roleCode.trim(),
      roleName: values.roleName,
      sortOrder: values.sortOrder ?? 0,
      status: values.status,
    };
    drawerApi.lock();
    try {
      if (editingId.value) {
        await updateRole(editingId.value, payload);
      } else {
        await createRole(payload);
      }
      drawerApi.close();
      emit('success');
    } finally {
      drawerApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;
    formApi.resetForm();
    const row = drawerApi.getData<SystemRoleApi.Role>();
    editingId.value = row?.id;
    loading.value = true;
    try {
      if (row?.id) {
        const [tree, detail] = await Promise.all([
          getMenuList(),
          getRoleDetail(row.id),
        ]);
        menus.value = filterEnabledMenus(tree);
        const enabledMenuIds = collectMenuIds(menus.value);
        // 编辑时同步剔除历史授权中已停用的菜单，避免再次保存被后端拒绝。
        await formApi.setValues({
          ...detail.role,
          menuIds: detail.menuIds.filter((id) => enabledMenuIds.has(id)),
        });
      } else {
        menus.value = filterEnabledMenus(await getMenuList());
        await formApi.setValues({ menuIds: [], sortOrder: 0, status: 1 });
      }
    } finally {
      loading.value = false;
    }
  },
});
</script>

<template>
  <Drawer class="w-full max-w-[640px]" :title="title">
    <Form>
      <template #menuIds="slotProps">
        <Spin :spinning="loading" class="w-full">
          <VbenTree
            :tree-data="menus"
            bordered
            :default-expanded-level="3"
            label-field="menuName"
            multiple
            value-field="id"
            v-bind="slotProps"
          />
        </Spin>
      </template>
    </Form>
  </Drawer>
</template>
