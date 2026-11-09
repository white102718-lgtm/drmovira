<script setup lang="ts">
import type { ChooseDevOption } from '#/api/dashboard';
import type { PendingDashboardStatusChange } from '#/domain/ad-dashboard/operations';
import type { DashboardDeveloperSelection } from '../use-ad-dashboard-operations';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { Alert, Button, Modal, Select, Tag } from 'ant-design-vue';

import { getChooseDevOptions } from '#/api/dashboard';
import { getAdDashboardSchema } from '#/domain/ad-dashboard';

const props = defineProps<{
  changes: PendingDashboardStatusChange[];
  open: boolean;
  saving: boolean;
}>();
const emit = defineEmits<{
  remove: [key: string];
  submit: [selections: DashboardDeveloperSelection[]];
  'update:open': [open: boolean];
}>();

const loading = ref(false);
const loadError = ref('');
const choices = ref<Record<string, ChooseDevOption[]>>({});
const selected = ref<Record<string, string>>({});
let loadVersion = 0;

function developerKey(developer: ChooseDevOption) {
  return `${developer.type}:${developer.id}`;
}
function selectedDeveloper(key: string) {
  return choices.value[key]?.find(
    (option) => developerKey(option) === selected.value[key],
  );
}
const canSubmit = computed(
  () =>
    !loading.value &&
    !loadError.value &&
    props.changes.length > 0 &&
    props.changes.every((change) => selectedDeveloper(change.key)?.type),
);

/** 旧版默认选择每个对象的首个可用开发者；弹窗重试和移除行时保留仍有效的选择。 */
async function loadDevelopers() {
  const currentVersion = ++loadVersion;
  const changes = [...props.changes];
  if (!props.open || changes.length === 0) {
    loading.value = false;
    return;
  }
  loading.value = true;
  loadError.value = '';
  try {
    const result = await getChooseDevOptions({
      campaign_ids: changes
        .filter((change) => change.level === 'campaign')
        .map((change) => change.id),
      adset_ids: changes
        .filter((change) => change.level === 'adset')
        .map((change) => change.id),
      ad_ids: changes
        .filter((change) => change.level === 'ad')
        .map((change) => change.id),
    });
    if (currentVersion !== loadVersion || !props.open) return;
    const next: Record<string, ChooseDevOption[]> = {};
    for (const change of changes) {
      const options = (result[change.id] ?? []).filter((option) => option.type);
      next[change.key] = options;
      if (
        !options.some(
          (option) => developerKey(option) === selected.value[change.key],
        )
      ) {
        selected.value[change.key] = options[0] ? developerKey(options[0]) : '';
      }
    }
    choices.value = next;
  } catch {
    if (currentVersion === loadVersion)
      loadError.value = '开发者加载失败，请重试';
  } finally {
    if (currentVersion === loadVersion) loading.value = false;
  }
}

function confirm() {
  if (!canSubmit.value || props.saving) return;
  emit(
    'submit',
    props.changes.flatMap((change) => {
      const developer = selectedDeveloper(change.key);
      return developer ? [{ key: change.key, developer }] : [];
    }),
  );
}

watch(
  () => [props.open, props.changes.map((change) => change.key).join('|')],
  () => {
    if (!props.saving) void loadDevelopers();
  },
  { immediate: true },
);
watch(
  () => props.saving,
  (saving, previous) => {
    if (previous && !saving && props.open) void loadDevelopers();
  },
);
onBeforeUnmount(() => {
  loadVersion += 1;
});
</script>

<template>
  <Modal
    :open="open"
    wrap-class-name="ux-fixed-modal"
    title="变更确认"
    :width="860"
    :closable="!saving"
    :mask-closable="!saving"
    :keyboard="!saving"
    @cancel="emit('update:open', false)"
  >
    <p class="text-muted-foreground mb-4 text-sm">
      共 {{ changes.length }} 项状态变更。选择执行开发者，确认提交后生效。
    </p>
    <Alert
      v-if="loadError"
      class="mb-4"
      type="error"
      :message="loadError"
      show-icon
    >
      <template #action>
        <Button :loading="loading" @click="loadDevelopers">重试</Button>
      </template>
    </Alert>
    <div class="space-y-3" :aria-busy="loading || saving">
      <p
        v-if="changes.length === 0"
        class="text-muted-foreground py-6 text-center"
      >
        暂无待提交变更
      </p>
      <article
        v-for="change in changes"
        :key="change.key"
        class="space-y-3 rounded-md border p-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <Tag>{{ getAdDashboardSchema(change.category).label }}</Tag>
              <span class="min-w-0 break-all font-medium">{{
                change.name
              }}</span>
            </div>
            <p class="text-muted-foreground mt-1 break-all text-xs">
              ID：{{ change.id }}
            </p>
            <p
              v-if="change.row.accountName || change.row.projectName"
              class="text-muted-foreground mt-1 break-all text-xs"
            >
              {{
                [change.row.projectName, change.row.accountName]
                  .filter(Boolean)
                  .join(' / ')
              }}
            </p>
          </div>
          <Button
            type="text"
            :disabled="saving"
            :aria-label="`撤销${change.name}的状态变更`"
            @click="emit('remove', change.key)"
            >撤销</Button
          >
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <span class="shrink-0 text-sm">
            {{ change.before === 'ACTIVE' ? '已开启' : '已暂停' }}
            → <strong>{{ change.after === 'ACTIVE' ? '开启' : '暂停' }}</strong>
          </span>
          <div class="flex min-w-0 flex-1 items-center gap-2">
            <label :for="`developer-${change.key}`" class="shrink-0 text-sm"
              >开发者</label
            >
            <Select
              :id="`developer-${change.key}`"
              v-model:value="selected[change.key]"
              class="min-w-0 flex-1"
              :loading="loading"
              :disabled="loading || saving"
              :options="
                (choices[change.key] ?? []).map((option) => ({
                  label: option.name,
                  value: developerKey(option),
                }))
              "
              option-filter-prop="label"
              show-search
              placeholder="请选择执行开发者"
              :aria-label="`${change.name}的执行开发者`"
            />
          </div>
        </div>
        <p
          v-if="!loading && !loadError && !choices[change.key]?.length"
          class="text-destructive text-sm"
          role="alert"
        >
          该对象没有可用开发者，请配置后重试或撤销此项。
        </p>
        <p v-if="change.error" class="text-destructive text-sm" role="alert">
          {{ change.error }}
        </p>
      </article>
    </div>
    <template #footer>
      <Button
        v-if="!loadError"
        :disabled="saving"
        :loading="loading"
        @click="loadDevelopers"
        >刷新开发者</Button
      >
      <Button :disabled="saving" @click="emit('update:open', false)"
        >取消</Button
      >
      <Button
        type="primary"
        :disabled="!canSubmit"
        :loading="saving"
        @click="confirm"
        >确认提交</Button
      >
    </template>
  </Modal>
</template>
