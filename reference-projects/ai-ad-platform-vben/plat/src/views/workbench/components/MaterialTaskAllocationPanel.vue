<script setup lang="ts">
import type {
  MaterialAllocationAsset,
  MaterialAllocationRequirement,
  MaterialAllocationUser,
  MaterialTaskAllocationState,
} from '#/domain/task-material-allocation';

import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Empty, message, Tag } from 'ant-design-vue';

import {
  buildBalancedProductionSlots,
  buildOversendAssignments,
  moveOrderedItem,
  normalizeMaterialOrder,
  sortMaterialRequirements,
} from '#/domain/task-material-allocation';

const props = defineProps<{
  designers: readonly MaterialAllocationUser[];
  materials: readonly MaterialAllocationAsset[];
  projectId: string;
  projectMembers: readonly MaterialAllocationUser[];
  requirements: readonly MaterialAllocationRequirement[];
  state?: MaterialTaskAllocationState;
  taskId: string;
}>();

const emit = defineEmits<{
  save: [state: MaterialTaskAllocationState];
}>();

const draftRequirements = ref<MaterialAllocationRequirement[]>([]);
const productionSlots = ref<MaterialTaskAllocationState['productionSlots']>([]);
const materialOrderIds = ref<string[]>([]);
const oversendAssignments = ref<
  MaterialTaskAllocationState['oversendAssignments']
>([]);
const confirmedAt = ref<string>();

const materialById = computed(
  () => new Map(props.materials.map((material) => [material.id, material])),
);
const requirementById = computed(
  () =>
    new Map(
      draftRequirements.value.map((requirement) => [
        requirement.id,
        requirement,
      ]),
    ),
);
const plannedTotal = computed(() =>
  draftRequirements.value.reduce(
    (total, requirement) => total + requirement.quantity,
    0,
  ),
);
const acceptedMaterialCount = computed(
  () => props.materials.filter((material) => material.accepted).length,
);
const designerLoads = computed(() => {
  const loads = new Map(
    props.designers.map((designer) => [designer.userId, 0]),
  );
  for (const slot of productionSlots.value) {
    if (slot.status === 'cancelled' || slot.overPlan) continue;
    loads.set(slot.designerUserId, (loads.get(slot.designerUserId) ?? 0) + 1);
  }
  return loads;
});
const maxLoadDifference = computed(() => {
  const loads = [...designerLoads.value.values()];
  return loads.length > 0 ? Math.max(...loads) - Math.min(...loads) : 0;
});
const orderedMaterials = computed(() =>
  materialOrderIds.value.flatMap((materialId) => {
    const material = materialById.value.get(materialId);
    return material ? [material] : [];
  }),
);
const oversendMaterialIds = computed(
  () => new Set(oversendAssignments.value.map((item) => item.materialId)),
);

function resetDraft() {
  const storedRequirements = new Map(
    (props.state?.requirements ?? []).map((requirement) => [
      requirement.id,
      requirement,
    ]),
  );
  draftRequirements.value = sortMaterialRequirements(
    props.requirements.map((requirement, index) => ({
      ...requirement,
      designerUserIds:
        storedRequirements.get(requirement.id)?.designerUserIds ??
        requirement.designerUserIds,
      sortOrder:
        storedRequirements.get(requirement.id)?.sortOrder ??
        requirement.sortOrder ??
        (index + 1) * 1000,
    })),
  );
  productionSlots.value = [...(props.state?.productionSlots ?? [])];
  materialOrderIds.value = normalizeMaterialOrder(
    props.materials,
    props.state?.materialOrderIds,
  );
  oversendAssignments.value = [...(props.state?.oversendAssignments ?? [])];
  confirmedAt.value = props.state?.confirmedAt;
}

watch(
  () => [
    props.taskId,
    props.requirements,
    props.materials,
    props.designers,
    props.state,
  ],
  resetDraft,
  { deep: true, immediate: true },
);

function requirementLabel(requirementId: string | undefined) {
  return requirementId
    ? (requirementById.value.get(requirementId)?.label ?? requirementId)
    : '未关联子需求';
}

function moveRequirement(requirementId: string, direction: -1 | 1) {
  const ids = moveOrderedItem(
    draftRequirements.value.map((requirement) => requirement.id),
    requirementId,
    direction,
  );
  const order = new Map(ids.map((id, index) => [id, (index + 1) * 1000]));
  draftRequirements.value = draftRequirements.value
    .map((requirement) => ({
      ...requirement,
      sortOrder: order.get(requirement.id) ?? requirement.sortOrder,
    }))
    .sort((left, right) => left.sortOrder - right.sortOrder);
}

function moveMaterial(materialId: string, direction: -1 | 1) {
  materialOrderIds.value = moveOrderedItem(
    materialOrderIds.value,
    materialId,
    direction,
  );
}

function autoBalance() {
  if (props.designers.length === 0) {
    message.warning('请先为素材任务分配至少一位素材师');
    return;
  }
  const preview = buildBalancedProductionSlots({
    designers: props.designers,
    existingSlots: productionSlots.value,
    requirements: draftRequirements.value,
    taskId: props.taskId,
  });
  productionSlots.value = preview.slots;
  message.success(
    preview.maxLoadDifference <= 1
      ? '已按子需求顺序完成均分预览'
      : '已保留锁定项，并对剩余名额完成均分预览',
  );
}

function autoAssignOversend() {
  if (acceptedMaterialCount.value <= plannedTotal.value) {
    oversendAssignments.value = [];
    message.info('当前没有超过需求数量的已验收素材');
    return;
  }
  const preview = buildOversendAssignments({
    existingAssignments: oversendAssignments.value,
    materials: props.materials,
    projectId: props.projectId,
    recipients: props.projectMembers,
    requirements: draftRequirements.value,
    taskId: props.taskId,
  });
  oversendAssignments.value = preview.assignments;
  if (preview.materialIds.length > 0 && preview.assignments.length === 0) {
    message.warning('存在超送素材，但当前项目没有可接收的有效人员');
    return;
  }
  message.success(`已均分 ${preview.assignments.length} 条超送素材`);
}

function requirementDesignerCount(requirementId: string, designerId: string) {
  return productionSlots.value.filter(
    (slot) =>
      !slot.overPlan &&
      slot.status !== 'cancelled' &&
      slot.requirementId === requirementId &&
      slot.designerUserId === designerId,
  ).length;
}

function saveAllocation() {
  if (
    plannedTotal.value > 0 &&
    productionSlots.value.filter((slot) => !slot.overPlan).length !==
      plannedTotal.value
  ) {
    message.warning('请先执行自动均分，确保每个生产名额都有素材师');
    return;
  }
  const timestamp = new Date().toLocaleString('zh-CN', { hour12: false });
  emit('save', {
    confirmedAt: timestamp,
    materialOrderIds: [...materialOrderIds.value],
    oversendAssignments: [...oversendAssignments.value],
    productionSlots: productionSlots.value.map((slot) => ({ ...slot })),
    requirements: draftRequirements.value.map((requirement) => ({
      ...requirement,
    })),
    version: (props.state?.version ?? 0) + 1,
  });
  confirmedAt.value = timestamp;
}
</script>

<template>
  <section class="allocation-panel">
    <header class="allocation-panel__header">
      <div>
        <div class="allocation-panel__title">
          <IconifyIcon icon="lucide:workflow" />
          素材生产与超送分配
        </div>
        <p>子需求和素材均按固定顺序处理；自动均分只调整未锁定的生产名额。</p>
      </div>
      <div class="allocation-panel__actions">
        <Button @click="autoBalance">自动均分</Button>
        <Button type="primary" @click="saveAllocation">确认并保存</Button>
      </div>
    </header>

    <div class="allocation-metrics">
      <div>
        <span>计划数量</span><strong>{{ plannedTotal }}</strong>
      </div>
      <div>
        <span>素材师</span><strong>{{ designers.length }}</strong>
      </div>
      <div>
        <span>最大负载差</span>
        <strong :class="{ 'text-amber-600': maxLoadDifference > 1 }">
          {{ maxLoadDifference }}
        </strong>
      </div>
      <div>
        <span>可排列素材</span><strong>{{ materials.length }}</strong>
      </div>
    </div>

    <div class="allocation-block">
      <div class="allocation-block__heading">
        <div>
          <strong>1. 子需求顺序</strong>
          <span>投放取材将遵循该顺序</span>
        </div>
      </div>
      <div v-if="draftRequirements.length > 0" class="allocation-order-list">
        <div
          v-for="(requirement, index) in draftRequirements"
          :key="requirement.id"
          class="allocation-order-row"
        >
          <span class="allocation-order-index">{{ index + 1 }}</span>
          <div class="min-w-0 flex-1">
            <strong>{{ requirement.label }}</strong>
            <span>计划 {{ requirement.quantity }} 条</span>
          </div>
          <Button
            aria-label="上移子需求"
            :disabled="index === 0"
            type="text"
            @click="moveRequirement(requirement.id, -1)"
          >
            <IconifyIcon icon="lucide:arrow-up" />
          </Button>
          <Button
            aria-label="下移子需求"
            :disabled="index === draftRequirements.length - 1"
            type="text"
            @click="moveRequirement(requirement.id, 1)"
          >
            <IconifyIcon icon="lucide:arrow-down" />
          </Button>
        </div>
      </div>
      <Empty
        v-else
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="暂无子需求"
      />
    </div>

    <div class="allocation-block">
      <div class="allocation-block__heading">
        <div>
          <strong>2. 素材师负载</strong>
          <span>同条件下总量及单个子需求差值不超过 1</span>
        </div>
        <Tag :color="maxLoadDifference <= 1 ? 'success' : 'warning'">
          {{ maxLoadDifference <= 1 ? '分配均衡' : '含锁定差异' }}
        </Tag>
      </div>
      <div v-if="designers.length > 0" class="ux-native-table-viewport">
        <table class="allocation-table">
          <thead>
            <tr>
              <th>子需求</th>
              <th v-for="designer in designers" :key="designer.userId">
                {{ designer.userName }}
                <small>共 {{ designerLoads.get(designer.userId) ?? 0 }}</small>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="requirement in draftRequirements" :key="requirement.id">
              <td>{{ requirement.label }}</td>
              <td v-for="designer in designers" :key="designer.userId">
                {{ requirementDesignerCount(requirement.id, designer.userId) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Empty
        v-else
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="尚未分配素材师"
      />
    </div>

    <div class="allocation-block">
      <div class="allocation-block__heading">
        <div>
          <strong>3. 素材排列顺序</strong>
          <span>已锁定的投放归属不会随排序改变</span>
        </div>
      </div>
      <div v-if="orderedMaterials.length > 0" class="allocation-order-list">
        <div
          v-for="(material, index) in orderedMaterials"
          :key="material.id"
          class="allocation-order-row"
        >
          <span class="allocation-order-index">{{ index + 1 }}</span>
          <div class="min-w-0 flex-1">
            <strong>{{ material.name }}</strong>
            <span>{{ requirementLabel(material.requirementId) }}</span>
          </div>
          <Tag v-if="oversendMaterialIds.has(material.id)" color="orange">
            超送
          </Tag>
          <Button
            aria-label="上移素材"
            :disabled="index === 0"
            type="text"
            @click="moveMaterial(material.id, -1)"
          >
            <IconifyIcon icon="lucide:arrow-up" />
          </Button>
          <Button
            aria-label="下移素材"
            :disabled="index === orderedMaterials.length - 1"
            type="text"
            @click="moveMaterial(material.id, 1)"
          >
            <IconifyIcon icon="lucide:arrow-down" />
          </Button>
        </div>
      </div>
      <Empty
        v-else
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="暂无已验收素材"
      />
    </div>

    <div class="allocation-block">
      <div class="allocation-block__heading">
        <div>
          <strong>4. 超送同项目人员</strong>
          <span>一条素材默认只分给一位同项目人员</span>
        </div>
        <Button @click="autoAssignOversend">同项目人员均分</Button>
      </div>
      <div v-if="oversendAssignments.length > 0" class="allocation-order-list">
        <div
          v-for="assignment in oversendAssignments"
          :key="assignment.id"
          class="allocation-order-row"
        >
          <IconifyIcon class="text-orange-500" icon="lucide:package-plus" />
          <div class="min-w-0 flex-1">
            <strong>
              {{
                materialById.get(assignment.materialId)?.name ??
                assignment.materialId
              }}
            </strong>
            <span>{{ requirementLabel(assignment.requirementId) }}</span>
          </div>
          <Tag color="blue">{{ assignment.recipientUserName }}</Tag>
        </div>
      </div>
      <p v-else class="allocation-empty-text">
        没有已分配的超送素材；素材超过子需求计划后可在这里均分。
      </p>
    </div>

    <footer v-if="confirmedAt" class="allocation-panel__footer">
      <IconifyIcon icon="lucide:shield-check" />
      最近确认：{{ confirmedAt }} · 版本
      {{ (state?.version ?? 0) + (confirmedAt === state?.confirmedAt ? 0 : 1) }}
    </footer>
  </section>
</template>

<style scoped>
.allocation-panel {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid #ddd6fe;
  border-radius: 12px;
  background: linear-gradient(180deg, #faf8ff 0%, #fff 30%);
}

.allocation-panel__header,
.allocation-block__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.allocation-panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #4c1d95;
  font-size: 15px;
  font-weight: 700;
}

.allocation-panel__header p,
.allocation-block__heading span,
.allocation-order-row span,
.allocation-empty-text {
  color: #64748b;
  font-size: 12px;
}

.allocation-panel__header p {
  margin: 4px 0 0;
}

.allocation-panel__actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.allocation-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.allocation-metrics > div {
  padding: 10px 12px;
  border: 1px solid #ede9fe;
  border-radius: 9px;
  background: rgb(255 255 255 / 85%);
}

.allocation-metrics span,
.allocation-metrics strong {
  display: block;
}

.allocation-metrics span {
  color: #64748b;
  font-size: 11px;
}

.allocation-metrics strong {
  margin-top: 2px;
  color: #1e293b;
  font-size: 20px;
}

.allocation-block {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.allocation-block__heading {
  align-items: center;
  margin-bottom: 10px;
}

.allocation-block__heading strong,
.allocation-block__heading span {
  display: block;
}

.allocation-order-list {
  display: grid;
  gap: 6px;
}

.allocation-order-row {
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #f8fafc;
}

.allocation-order-row strong,
.allocation-order-row span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.allocation-order-row strong {
  color: #334155;
  font-size: 13px;
}

.allocation-order-index {
  display: grid !important;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 6px;
  background: #ede9fe;
  color: #6d28d9 !important;
  font-weight: 700;
}

.allocation-table {
  width: 100%;
  min-width: 480px;
  border-collapse: collapse;
  font-size: 12px;
}

.allocation-table th,
.allocation-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #f1f5f9;
  color: #475569;
  text-align: center;
}

.allocation-table th:first-child,
.allocation-table td:first-child {
  text-align: left;
}

.allocation-table th small {
  display: block;
  margin-top: 2px;
  color: #94a3b8;
  font-weight: 400;
}

.allocation-empty-text {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: #f8fafc;
  text-align: center;
}

.allocation-panel__footer {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #047857;
  font-size: 12px;
}

@media (max-width: 720px) {
  .allocation-panel__header,
  .allocation-block__heading {
    flex-direction: column;
  }

  .allocation-panel__actions {
    width: 100%;
  }

  .allocation-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
