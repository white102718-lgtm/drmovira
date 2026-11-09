import type { ComputedRef } from 'vue';

import type { DashboardColumnSetting } from '#/api/dashboard';
import type {
  AdDashboardField,
  AdDashboardSchema,
} from '#/domain/ad-dashboard';

import { computed, ref } from 'vue';

import { message } from 'ant-design-vue';

import { getColumnSettingApi, saveColumnSettingApi } from '#/api/dashboard';
import {
  resolveDashboardColumns,
  serializeDashboardColumns,
} from '#/domain/ad-dashboard/column-settings';

/** 列偏好只通过当前登录用户的接口持久化，失败时保留已生效配置。 */
export function useAdDashboardColumns(schema: ComputedRef<AdDashboardSchema>) {
  const settings = ref<Record<string, DashboardColumnSetting>>({});
  const loading = ref(true);
  const loadFailed = ref(false);
  const saving = ref(false);
  const columns = computed(() =>
    resolveDashboardColumns(
      schema.value,
      settings.value[schema.value.legacyTabKey],
    ),
  );

  async function load() {
    loading.value = true;
    loadFailed.value = false;
    try {
      settings.value = (await getColumnSettingApi()) ?? {};
    } catch {
      loadFailed.value = true;
      message.warning('列配置读取失败，请重试后再修改');
    } finally {
      loading.value = false;
    }
  }

  async function save(fields: AdDashboardField[], visibleKeys: string[]) {
    if (saving.value) throw new Error('列配置正在保存');
    // 请求期间切换 Tab 时，结果仍只写回提交时的 Tab。
    const targetSchema = schema.value;
    const tab = targetSchema.legacyTabKey;
    const setting = serializeDashboardColumns(
      targetSchema,
      fields,
      visibleKeys,
      settings.value[tab],
    );
    saving.value = true;
    try {
      await saveColumnSettingApi(tab, setting);
      settings.value[tab] = setting;
    } finally {
      saving.value = false;
    }
  }

  /** 表头拖动与弹窗共用持久化路径；隐藏列保留位置，固定列不参与移动。 */
  async function reorder(key: string, targetKey: string) {
    if (loading.value || loadFailed.value || saving.value || key === targetKey)
      return;
    const fields = [...columns.value.fields];
    const from = fields.findIndex((field) => field.key === key);
    const to = fields.findIndex((field) => field.key === targetKey);
    if (from === -1 || to === -1 || fields[from]?.fixed || fields[to]?.fixed)
      return;
    const [field] = fields.splice(from, 1);
    if (!field) return;
    fields.splice(to, 0, field);
    try {
      await save(
        fields,
        columns.value.visibleFields.map((item) => item.key),
      );
      message.success('列顺序已保存');
    } catch {
      // 成功后才更新已生效配置，失败时无需回滚，也不会留下未保存的新顺序。
      message.error('列顺序保存失败，请重新拖动');
    }
  }

  return {
    fields: computed(() => columns.value.fields),
    load,
    loadFailed,
    loading,
    reorder,
    save,
    saving,
    visibleFields: computed(() => columns.value.visibleFields),
  };
}
