<script setup lang="ts">
import type {
  DeliveryExecutionUnit,
  DeliveryMaterialAllocationState,
  MaterialAllocationAsset,
} from '#/domain/task-material-allocation';

import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Empty, message, Tag } from 'ant-design-vue';

import { buildUniqueDeliveryDistribution } from '#/domain/task-material-allocation';

const props = defineProps<{
  executionUnits: readonly DeliveryExecutionUnit[];
  materials: readonly MaterialAllocationAsset[];
  state?: DeliveryMaterialAllocationState;
  taskId: string;
}>();

const emit = defineEmits<{
  save: [state: DeliveryMaterialAllocationState];
}>();

const allowReuse = ref(false);
const items = ref<DeliveryMaterialAllocationState['items']>([]);
const missingExecutionUnitIds = ref<string[]>([]);
const canConfirm = ref(false);
const confirmedAt = ref<string>();

const executionUnitById = computed(
  () => new Map(props.executionUnits.map((unit) => [unit.id, unit])),
);
const duplicateCount = computed(
  () => items.value.filter((item) => item.repeated).length,
);

function generatePreview(showMessage = true) {
  const preview = buildUniqueDeliveryDistribution({
    allowReuse: allowReuse.value,
    executionUnits: props.executionUnits,
    materials: props.materials,
    preferredMaterialIds: props.materials.map((material) => material.id),
    taskId: props.taskId,
  });
  items.value = preview.items;
  missingExecutionUnitIds.value = preview.missingExecutionUnitIds;
  canConfirm.value = preview.canConfirm;
  if (!showMessage) return;
  if (preview.canConfirm) {
    message.success(
      preview.duplicateMaterialIds.length > 0
        ? '已生成循环复用预览，重复项已标记'
        : '已生成不重复素材分配预览',
    );
  } else {
    message.warning(
      `素材不足，还缺 ${preview.missingExecutionUnitIds.length} 条`,
    );
  }
}

function resetDraft() {
  allowReuse.value = props.state?.allowReuse ?? false;
  items.value = [...(props.state?.items ?? [])];
  confirmedAt.value = props.state?.confirmedAt;
  if (items.value.length === 0) generatePreview(false);
  else {
    missingExecutionUnitIds.value = [];
    canConfirm.value = true;
  }
}

watch(
  () => [props.taskId, props.executionUnits, props.materials, props.state],
  resetDraft,
  { deep: true, immediate: true },
);

function toggleReuse(event: Event) {
  allowReuse.value = (event.target as HTMLInputElement).checked;
  generatePreview(false);
}

function saveDistribution() {
  if (!canConfirm.value) {
    message.warning(
      `素材不足，还缺 ${missingExecutionUnitIds.value.length} 条`,
    );
    return;
  }
  const timestamp = new Date().toLocaleString('zh-CN', { hour12: false });
  emit('save', {
    allowReuse: allowReuse.value,
    confirmedAt: timestamp,
    items: items.value.map((item) => ({ ...item, status: 'reserved' })),
    version: (props.state?.version ?? 0) + 1,
  });
  confirmedAt.value = timestamp;
}
</script>

<template>
  <section class="distribution-panel">
    <header class="distribution-panel__header">
      <div>
        <div class="distribution-panel__title">
          <IconifyIcon icon="lucide:shuffle" />
          投放素材去重分配
        </div>
        <p>每个投放执行单元绑定一条素材；素材不足时默认禁止确认。</p>
      </div>
      <div class="distribution-panel__actions">
        <Button @click="generatePreview()">重新分配</Button>
        <Button
          :disabled="!canConfirm"
          type="primary"
          @click="saveDistribution"
        >
          确认分配
        </Button>
      </div>
    </header>

    <div class="distribution-metrics">
      <div>
        <span>投放执行单元</span><strong>{{ executionUnits.length }}</strong>
      </div>
      <div>
        <span>可用素材</span><strong>{{ materials.length }}</strong>
      </div>
      <div>
        <span>素材缺口</span>
        <strong>{{ missingExecutionUnitIds.length }}</strong>
      </div>
      <div>
        <span>重复项</span><strong>{{ duplicateCount }}</strong>
      </div>
    </div>

    <Alert
      v-if="missingExecutionUnitIds.length > 0"
      banner
      :message="`素材不足，还缺 ${missingExecutionUnitIds.length} 条；补充素材或由授权人员开启循环复用。`"
      show-icon
      type="warning"
    />

    <label class="distribution-reuse-control">
      <input type="checkbox" :checked="allowReuse" @change="toggleReuse" />
      <span>
        <strong>允许循环复用</strong>
        <small>全部素材至少使用一轮后才复用，重复项会明确标记。</small>
      </span>
    </label>

    <div v-if="items.length > 0" class="distribution-list">
      <div v-for="item in items" :key="item.id" class="distribution-row">
        <span class="distribution-row__icon">
          <IconifyIcon icon="lucide:megaphone" />
        </span>
        <div class="min-w-0 flex-1">
          <strong>
            {{
              executionUnitById.get(item.executionUnitId)?.label ??
              item.executionUnitId
            }}
          </strong>
          <span>{{ item.materialName }}</span>
        </div>
        <Tag :color="item.repeated ? 'error' : 'success'">
          {{ item.repeated ? '循环复用' : '唯一素材' }}
        </Tag>
      </div>
    </div>
    <Empty
      v-else
      :image="Empty.PRESENTED_IMAGE_SIMPLE"
      description="暂无可分配的投放素材"
    />

    <footer v-if="confirmedAt" class="distribution-panel__footer">
      <IconifyIcon icon="lucide:shield-check" />
      最近确认：{{ confirmedAt }}
    </footer>
  </section>
</template>

<style scoped>
.distribution-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: linear-gradient(180deg, #f5f9ff 0%, #fff 32%);
}

.distribution-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.distribution-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1e40af;
  font-size: 15px;
  font-weight: 700;
}

.distribution-panel__header p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
}

.distribution-panel__actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.distribution-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.distribution-metrics > div {
  padding: 10px 12px;
  border: 1px solid #dbeafe;
  border-radius: 9px;
  background: rgb(255 255 255 / 88%);
}

.distribution-metrics span,
.distribution-metrics strong {
  display: block;
}

.distribution-metrics span {
  color: #64748b;
  font-size: 11px;
}

.distribution-metrics strong {
  margin-top: 2px;
  color: #1e293b;
  font-size: 20px;
}

.distribution-reuse-control {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #f8fafc;
  cursor: pointer;
}

.distribution-reuse-control input {
  margin-top: 3px;
}

.distribution-reuse-control strong,
.distribution-reuse-control small {
  display: block;
}

.distribution-reuse-control strong {
  color: #334155;
  font-size: 13px;
}

.distribution-reuse-control small {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
}

.distribution-list {
  display: grid;
  gap: 7px;
}

.distribution-row {
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 9px;
  background: #fff;
}

.distribution-row__icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 8px;
  background: #dbeafe;
  color: #2563eb;
}

.distribution-row strong,
.distribution-row span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.distribution-row strong {
  color: #334155;
  font-size: 13px;
}

.distribution-row .min-w-0 > span {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
}

.distribution-panel__footer {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #047857;
  font-size: 12px;
}

@media (max-width: 720px) {
  .distribution-panel__header {
    flex-direction: column;
  }

  .distribution-panel__actions {
    width: 100%;
  }

  .distribution-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
