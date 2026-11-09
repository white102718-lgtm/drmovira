<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Cascader, message, Modal, Popover } from 'ant-design-vue';

import { getAvailableAdAccounts, pushMaterialsToFbApi } from '#/api';

const route = useRoute();

const props = defineProps<{
  open: boolean;
  materials: Array<{ filetype?: string; id: string; title: string }>;
  initialPaths?: string[][];
}>();

const emit = defineEmits<{
  'update:open': [boolean];
  success: [];
}>();

interface CascaderLeaf {
  isLeaf: true;
  label: string;
  value: string;
}

interface CascaderPersonal {
  children: CascaderLeaf[];
  label: string;
  value: string;
}

const cascaderOptions = ref<CascaderPersonal[]>([]);
const cascaderLoading = ref(false);

async function loadOptions() {
  cascaderLoading.value = true;
  try {
    const data = await getAvailableAdAccounts();
    cascaderOptions.value = data.items.map((group) => ({
      value: group.personal_id,
      label: `${group.personal_name} (${group.personal_id})`,
      children: group.ad_accounts.map((acc) => ({
        value: acc.id,
        label: `${acc.name} (${acc.id})`,
        isLeaf: true as const,
      })),
    }));
  } finally {
    cascaderLoading.value = false;
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      loadOptions();
      if (props.initialPaths?.length) {
        selectedPaths.value = props.initialPaths;
      }
    }
  },
);

//  素材最大展示可见数量
const PREVIEW_COUNT = 17;

const selectedPaths = ref<string[][]>([]);
const pushLoading = ref(false);
const failedBasenames = ref<string[]>([]);

// 将选中路径展开
function expandPaths(paths: string[][]): Array<[string, string]> {
  const result: Array<[string, string]> = [];
  for (const path of paths) {
    const personalId = path[0] ?? '';
    if (path.length >= 2) {
      result.push([personalId, path[1]!]);
    } else {
      const personal = cascaderOptions.value.find(
        (o) => o.value === personalId,
      );
      for (const child of personal?.children ?? []) {
        result.push([personalId, child.value]);
      }
    }
  }
  return result;
}

// 将选中路径解析为可读名称
const selectedDetails = computed(() =>
  expandPaths(selectedPaths.value).map(([personalId, targetId]) => {
    const personal = cascaderOptions.value.find((o) => o.value === personalId);
    const target = personal?.children.find((c) => c.value === targetId);
    return {
      personalLabel: personal?.label ?? personalId,
      targetLabel: target?.label ?? targetId,
    };
  }),
);

// 按个号分组，供模板分组展示
const selectedGroups = computed(() => {
  const map = new Map<string, { personalLabel: string; targets: string[] }>();
  for (const { personalLabel, targetLabel } of selectedDetails.value) {
    if (!map.has(personalLabel)) {
      map.set(personalLabel, { personalLabel, targets: [] });
    }
    map.get(personalLabel)!.targets.push(targetLabel);
  }
  return [...map.values()];
});

function cascaderFilter(inputValue: string, path: any[]) {
  return path.some((option: any) =>
    String(option.label).toLowerCase().includes(inputValue.toLowerCase()),
  );
}

function onCascaderChange(v: unknown) {
  selectedPaths.value = v as string[][];
}

function handleUpdateOpen(v: boolean) {
  if (!v) handleCancel();
}

function handleCancel() {
  emit('update:open', false);
  selectedPaths.value = [];
}

async function handleConfirm() {
  if (!selectedPaths.value.length) {
    message.warning('请选择上传目标');
    return;
  }
  const basenames = [
    ...new Set([
      ...props.materials.map((m) => m.title),
      ...failedBasenames.value,
    ]),
  ];
  const expanded = expandPaths(selectedPaths.value);
  pushLoading.value = true;
  try {
    const results = await Promise.all(
      expanded.map(([personal_id, target_id]) =>
        pushMaterialsToFbApi({
          personal_id,
          target_id,
          basenames,
          ...(route.query.id ? { order_id: String(route.query.id) } : {}),
        }),
      ),
    );
    const totalSucceeded = results.reduce(
      (sum, r: any) => sum + (r?.succeeded ?? 0),
      0,
    );
    const totalFailed = results.reduce(
      (sum, r: any) => sum + (r?.failed ?? 0),
      0,
    );
    const skippedMsgs = results
      .map((r: any) => r?.skipped)
      .filter(Boolean) as string[];

    if (totalFailed > 0) {
      const failedItems = results.flatMap((r: any) =>
        (r?.items ?? []).filter((item: any) => item.status === 'failed'),
      );
      failedBasenames.value = failedItems.map((item: any) => item.basename);
      const parts: string[] = [];
      if (totalSucceeded > 0) parts.push(`成功 ${totalSucceeded} 个`);
      parts.push(`失败 ${totalFailed} 个：${failedBasenames.value.join('、')}`);
      message.error(`上传完成，${parts.join('，')}`);
    } else if (totalSucceeded > 0) {
      failedBasenames.value = [];
      message.success(`上传完成，成功 ${totalSucceeded} 个`);
      emit('success');
      handleCancel();
    }

    if (skippedMsgs.length > 0) {
      message.warning(skippedMsgs.join('\n'));
    }
  } catch {
  } finally {
    pushLoading.value = false;
  }
}
</script>

<template>
  <Modal
    :open="open"
    :width="860"
    :body-style="{ maxHeight: '72dvh', overflowY: 'auto' }"
    :ok-text="failedBasenames.length > 0 ? '重新上传' : '确认'"
    cancel-text="取消"
    :ok-button-props="{ disabled: selectedPaths.length === 0 }"
    :confirm-loading="pushLoading"
    @ok="handleConfirm"
    @cancel="handleCancel"
    @update:open="handleUpdateOpen"
  >
    <template #title>
      <div class="flex items-center">
        <span>上传素材到广告账户</span>
        <span class="pl-2 text-sm font-normal text-gray-400"
          >已选 {{ materials.length }} 条</span
        >
      </div>
    </template>

    <div class="mb-3 flex flex-wrap items-start gap-1.5">
      <span
        v-for="m in materials.slice(0, PREVIEW_COUNT)"
        :key="m.id"
        class="text-ms flex-shrink-0 whitespace-nowrap rounded bg-gray-100 px-2 py-0.5 text-gray-600"
        :title="m.title"
        >{{ m.title }}</span
      >
      <Popover
        v-if="materials.length > PREVIEW_COUNT"
        trigger="click"
        placement="bottomRight"
      >
        <template #content>
          <div class="grid max-h-48 w-80 grid-cols-3 overflow-y-auto py-1">
            <div
              v-for="m in materials.slice(PREVIEW_COUNT)"
              :key="m.id"
              class="text-ms truncate px-1 py-0.5 text-gray-600"
              :title="m.title"
            >
              {{ m.title }}
            </div>
          </div>
        </template>
        <button
          class="text-ms ml-4 flex-shrink-0 whitespace-nowrap text-blue-500 hover:text-blue-700"
        >
          +{{ materials.length - PREVIEW_COUNT }} 条 ▾
        </button>
      </Popover>
    </div>

    <p class="mb-4 text-sm text-gray-500">选择广告账户</p>
    <Cascader
      :value="selectedPaths"
      :options="cascaderOptions"
      :multiple="true"
      expand-trigger="click"
      :show-search="{ filter: cascaderFilter }"
      placeholder="请选择"
      :max-tag-count="1"
      style="width: 380px"
      @change="onCascaderChange"
    />

    <div
      v-if="failedBasenames.length > 0"
      class="mt-3 flex items-start justify-between rounded bg-red-50 px-3 py-2 text-xs text-red-600"
    >
      <span>
        {{
          failedBasenames.length
        }}
        个素材上次上传失败，将与当前选材合并重新上传：
        <span class="font-medium">{{ failedBasenames.join('、') }}</span>
      </span>
      <button
        class="ml-3 flex-shrink-0 text-red-400 hover:text-red-600"
        title="忽略失败记录"
        @click="failedBasenames = []"
      >
        ✕
      </button>
    </div>

    <div v-if="selectedDetails.length > 0" class="mt-6">
      <p class="mb-2 text-xs text-gray-500">
        已选 {{ selectedDetails.length }} 个广告账户：
      </p>
      <div class="flex max-h-[350px] flex-col gap-3 overflow-y-auto">
        <div v-for="group in selectedGroups" :key="group.personalLabel">
          <div class="mb-1 flex items-center gap-1.5">
            <span class="text-xs font-medium text-gray-600"
              >个号: {{ group.personalLabel }}</span
            >
            <span
              class="rounded-full bg-blue-100 px-1.5 py-px text-[10px] text-blue-600"
            >
              {{ group.targets.length }}个广告账户
            </span>
          </div>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="target in group.targets"
              :key="target"
              class="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
              >{{ target }}</span
            >
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
