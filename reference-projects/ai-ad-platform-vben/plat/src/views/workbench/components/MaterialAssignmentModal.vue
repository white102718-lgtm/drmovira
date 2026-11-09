<script setup lang="ts">
import type {
  MaterialAssignment,
  MaterialAssignmentInput,
  MaterialOrderDetail,
  MaterialOrderOrganization,
} from '#/api/requirement';

import { computed, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Spin,
  Tag,
  theme,
} from 'ant-design-vue';

import {
  batchAssignMaterialOrders,
  getCreators,
  getMaterialOrderDetail,
  getMaterialOrderOrganization,
  ORDER_STATUS_MAP,
} from '#/api/requirement';

type AssignmentDraft = Omit<MaterialAssignmentInput, 'quantity'> & {
  quantity: number | null;
};

const props = defineProps<{ open: boolean; orderId?: string }>();
const emit = defineEmits<{ 'update:open': [value: boolean]; assigned: [] }>();
const { token } = theme.useToken();
const loading = ref(false);
const submitting = ref(false);
const loadError = ref('');
const detail = ref<MaterialOrderDetail>();
const users = ref<MaterialOrderOrganization['users']>([]);
const workloads = ref(new Map<string, number>());
const records = ref<AssignmentDraft[]>([]);
let loadRequest = 0;

const requirements = computed(() => detail.value?.requirements ?? []);
const originalRecords = computed(
  () =>
    new Map((detail.value?.assignments ?? []).map((item) => [item.id, item])),
);
const warningStyle = computed(() => ({
  '--assignment-warning-bg': `color-mix(in srgb, ${token.value.colorWarningBg} 50%, ${token.value.colorBgContainer})`,
  '--assignment-warning-text': `color-mix(in srgb, ${token.value.colorWarningTextActive} 65%, ${token.value.colorText})`,
}));

/** 每条分配仍属于一位素材师；按子需求汇总多人、多条分配的数量。 */
const requirementGroups = computed(() =>
  requirements.value.map((requirement, index) => {
    const assignments = records.value.filter(
      (item) => item.req_id === requirement.id,
    );
    const quantity = requirement.quantity ?? 0;
    const allocated = assignments.reduce(
      (sum, item) =>
        sum +
        (item.designer_user_id && isValidQuantity(item.quantity)
          ? item.quantity
          : 0),
      0,
    );
    return {
      ...requirement,
      index: index + 1,
      assignments,
      singleAssignment: assignments.length === 1 ? assignments[0] : undefined,
      quantity,
      allocated,
      excess: Math.max(allocated - quantity, 0),
      remaining: Math.max(quantity - allocated, 0),
    };
  }),
);
const requiredQuantity = computed(() =>
  requirementGroups.value.reduce((sum, group) => sum + group.quantity, 0),
);
const allocatedQuantity = computed(() =>
  requirementGroups.value.reduce((sum, group) => sum + group.allocated, 0),
);
// 各子需求的超额独立累加，不能被其他子需求尚未分配的数量抵消。
const excessQuantity = computed(() =>
  requirementGroups.value.reduce((sum, group) => sum + group.excess, 0),
);
const designerCount = computed(
  () =>
    new Set(records.value.map((item) => item.designer_user_id).filter(Boolean))
      .size,
);
const formDisabled = computed(
  () =>
    loading.value ||
    submitting.value ||
    Boolean(loadError.value) ||
    !requirements.value.length,
);
const canSubmit = computed(
  () =>
    !formDisabled.value &&
    detail.value?.permissions.assign &&
    detail.value.id === props.orderId &&
    (records.value.length > 0 || originalRecords.value.size > 0) &&
    records.value.every(
      (item) =>
        requirements.value.some(
          (requirement) => requirement.id === item.req_id,
        ) &&
        item.designer_user_id &&
        isValidQuantity(item.quantity),
    ),
);

function isValidQuantity(value: number | null): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0;
}

function personOptions(role: string) {
  const names = new Map<string, string>();
  for (const item of originalRecords.value.values()) {
    const id =
      role === 'CREATOR'
        ? item.designer_user_id
        : item.creative_planner_user_id;
    const name =
      role === 'CREATOR' ? item.designer_name : item.creative_planner_name;
    if (id) names.set(id, name || id);
  }
  const eligible = users.value.filter((user) => user.roles.includes(role));
  for (const user of eligible) names.set(user.id, user.full_name);
  return [...names].map(([id, name]) => ({
    value: id,
    label:
      role === 'CREATOR' ? `${name}(${workloads.value.get(id) ?? 0})` : name,
    disabled: !eligible.some((user) => user.id === id),
  }));
}
const designerOptions = computed(() => personOptions('CREATOR'));
// 创意策划候选人按独立岗位角色筛选，与后端分配校验一致。
const plannerOptions = computed(() => personOptions('CREATIVE_PLANNER'));

function isProtected(id: string) {
  const original = originalRecords.value.get(id);
  return Boolean(
    original?.has_outputs ||
      ['submitted', 'accepted'].includes(original?.status ?? ''),
  );
}

/** 在所属子需求内新增，不再允许通过下拉框更换子需求。 */
function addRecord(requirementId: string) {
  const group = requirementGroups.value.find(
    (item) => item.id === requirementId,
  );
  if (!group || formDisabled.value) return;
  records.value.push({
    id: globalThis.crypto.randomUUID(),
    req_id: requirementId,
    designer_user_id: '',
    creative_planner_user_id: null,
    quantity: Math.max(group.remaining, 1),
    remark: '',
  });
}

function removeRecord(id: string) {
  if (!formDisabled.value && !isProtected(id)) {
    records.value = records.value.filter((item) => item.id !== id);
  }
}

function setQuantity(record: AssignmentDraft, value: unknown) {
  record.quantity = typeof value === 'number' ? value : null;
}

function setPlanner(record: AssignmentDraft, value: unknown) {
  record.creative_planner_user_id = typeof value === 'string' ? value : null;
}

function toInput(item: MaterialAssignment): AssignmentDraft {
  return {
    id: item.id,
    req_id: item.req_id,
    designer_user_id: item.designer_user_id,
    creative_planner_user_id: item.creative_planner_user_id || null,
    quantity: item.quantity,
    remark: item.remark || '',
  };
}

async function loadAssignment() {
  const request = ++loadRequest;
  detail.value = undefined;
  records.value = [];
  users.value = [];
  workloads.value = new Map();
  loadError.value = '';
  if (!props.orderId) {
    loading.value = false;
    loadError.value = '缺少素材工单编号，请刷新列表后重试';
    return;
  }
  loading.value = true;
  try {
    const [order, organization, creators] = await Promise.all([
      getMaterialOrderDetail(props.orderId),
      getMaterialOrderOrganization(),
      getCreators(),
    ]);
    if (request !== loadRequest) return;
    if (order.id !== props.orderId)
      throw new Error('工单信息不一致，请刷新列表后重试');
    if (!order.permissions.assign)
      throw new Error('当前工单不可分配，请刷新列表确认状态和权限');
    detail.value = order;
    users.value = organization.users;
    workloads.value = new Map(
      creators.map((user) => [user.user_id, user.in_production_count]),
    );
    records.value = order.assignments
      .filter((item) => item.status !== 'cancelled')
      .map(toInput);
  } catch (error) {
    if (request === loadRequest) {
      loadError.value =
        error instanceof Error ? error.message : '分配信息加载失败';
    }
  } finally {
    if (request === loadRequest) {
      loading.value = false;
      const firstRequirement = requirements.value[0];
      if (!loadError.value && !records.value.length && firstRequirement)
        addRecord(firstRequirement.id);
    }
  }
}

watch(
  () => [props.open, props.orderId] as const,
  ([open]) => {
    if (open) void loadAssignment();
    else {
      ++loadRequest;
      loading.value = false;
    }
  },
  { immediate: true },
);

async function submitAssignment() {
  if (!canSubmit.value || !detail.value) return;
  submitting.value = true;
  try {
    await batchAssignMaterialOrders([
      {
        id: detail.value.id,
        version: detail.value.version,
        assignments: records.value.map((item) => ({
          ...item,
          quantity: Number(item.quantity),
          creative_planner_user_id: item.creative_planner_user_id || null,
        })),
      },
    ]);
    message.success('分配已保存，素材师可直接开始制作');
    emit('update:open', false);
    emit('assigned');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '分配保存失败，请重试',
    );
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal
    :open="open"
    :title="detail?.assignments.length ? '修改分配' : '分配任务'"
    :width="760"
    :closable="!submitting"
    :mask-closable="!submitting"
    :keyboard="!submitting"
    :body-style="{ maxHeight: '72vh', overflowY: 'auto' }"
    @cancel="emit('update:open', false)"
  >
    <Spin :spinning="loading">
      <div class="assignment-content" :style="warningStyle">
        <Alert v-if="loadError" type="error" :message="loadError" show-icon>
          <template #action>
            <Button :loading="loading" @click="loadAssignment">重试</Button>
          </template>
        </Alert>
        <template v-else-if="detail">
          <div class="assignment-summary bg-muted text-foreground">
            <strong
              >{{ detail.title }} ·
              {{ ORDER_STATUS_MAP[detail.status] || detail.status }}</strong
            >
            <p>分配后直接进入制作中；支持部分保存，超额仅作数量提示。</p>
          </div>
          <div class="assignment-counts" aria-live="polite">
            <Tag color="blue">子需求：{{ requirements.length }}</Tag>
            <Tag color="purple">
              素材需求：{{ allocatedQuantity }} / {{ requiredQuantity }}
            </Tag>
            <Tag color="cyan">已分配素材师：{{ designerCount }} 位</Tag>
          </div>
          <Alert
            v-if="!requirements.length"
            type="warning"
            show-icon
            message="此工单暂无子需求，请先补充需求描述后再分配。"
          />
          <Form layout="vertical" :disabled="formDisabled">
            <section
              v-for="group in requirementGroups"
              :key="group.id"
              class="assignment-card border-border"
              :aria-labelledby="`requirement-heading-${group.id}`"
            >
              <div class="assignment-card-title">
                <span class="assignment-index bg-muted">{{ group.index }}</span>
                <strong :id="`requirement-heading-${group.id}`"
                  >子需求 {{ group.index }}</strong
                >
                <Tag
                  :color="group.excess > 0 ? 'warning' : 'blue'"
                  :class="{ 'assignment-warning-tag': group.excess > 0 }"
                >
                  已分配 {{ group.allocated }} / {{ group.quantity }} 条
                </Tag>
                <Button
                  v-if="group.singleAssignment"
                  type="text"
                  class="assignment-remove"
                  :disabled="
                    formDisabled || isProtected(group.singleAssignment.id)
                  "
                  :aria-label="`删除子需求 ${group.index} 的分配`"
                  @click="removeRecord(group.singleAssignment.id)"
                  >删除</Button
                >
              </div>
              <p
                v-if="group.description"
                class="assignment-description text-muted-foreground"
              >
                {{ group.description }}
              </p>
              <div
                v-for="(record, index) in group.assignments"
                :key="record.id"
                class="assignment-record"
              >
                <div
                  v-if="group.assignments.length > 1"
                  class="assignment-record-title"
                >
                  <span class="text-muted-foreground"
                    >分配 {{ index + 1 }}</span
                  >
                  <Button
                    type="text"
                    :disabled="formDisabled || isProtected(record.id)"
                    :aria-label="`删除子需求 ${group.index} 的分配 ${index + 1}`"
                    @click="removeRecord(record.id)"
                    >删除</Button
                  >
                </div>
                <div class="assignment-form-row">
                  <FormItem
                    label="本分配项素材师"
                    :html-for="`designer-${record.id}`"
                    :validate-status="
                      record.designer_user_id ? undefined : 'error'
                    "
                    :help="record.designer_user_id ? undefined : '请选择素材师'"
                    required
                  >
                    <Select
                      :id="`designer-${record.id}`"
                      v-model:value="record.designer_user_id"
                      :options="designerOptions"
                      :disabled="formDisabled || isProtected(record.id)"
                      :aria-invalid="!record.designer_user_id"
                      show-search
                      option-filter-prop="label"
                      placeholder="请选择素材师"
                    />
                  </FormItem>
                  <FormItem
                    label="分配数量"
                    :html-for="`quantity-${record.id}`"
                    :validate-status="
                      isValidQuantity(record.quantity) ? undefined : 'error'
                    "
                    :help="
                      isValidQuantity(record.quantity)
                        ? undefined
                        : '请填写正整数'
                    "
                    required
                  >
                    <InputNumber
                      :id="`quantity-${record.id}`"
                      :value="record.quantity ?? undefined"
                      @change="setQuantity(record, $event)"
                      :step="1"
                      :disabled="formDisabled || isProtected(record.id)"
                      :status="
                        isValidQuantity(record.quantity) ? undefined : 'error'
                      "
                      :aria-invalid="!isValidQuantity(record.quantity)"
                      :aria-describedby="
                        group.excess > 0
                          ? `allocation-hint-${group.id}`
                          : undefined
                      "
                      class="w-full"
                      placeholder="请输入正整数"
                    />
                  </FormItem>
                </div>
                <div class="assignment-form-row">
                  <FormItem
                    label="创意策划（可选）"
                    :html-for="`planner-${record.id}`"
                  >
                    <Select
                      :id="`planner-${record.id}`"
                      :value="record.creative_planner_user_id || undefined"
                      :options="plannerOptions"
                      :disabled="formDisabled"
                      show-search
                      allow-clear
                      option-filter-prop="label"
                      placeholder="请选择创意策划"
                      @change="setPlanner(record, $event)"
                    />
                  </FormItem>
                  <FormItem
                    label="备注（可选）"
                    :html-for="`remark-${record.id}`"
                  >
                    <Input
                      :id="`remark-${record.id}`"
                      v-model:value="record.remark"
                      :maxlength="200"
                      placeholder="填写本次分配说明"
                    />
                  </FormItem>
                </div>
                <p
                  v-if="isProtected(record.id)"
                  class="assignment-help text-muted-foreground"
                >
                  已有素材或已提交，素材师和数量已锁定。
                </p>
              </div>
              <p
                :id="`allocation-hint-${group.id}`"
                class="assignment-help"
                :class="
                  group.excess > 0
                    ? 'assignment-warning-text'
                    : 'text-muted-foreground'
                "
                aria-live="polite"
              >
                <template v-if="group.excess > 0"
                  >分配数量超过该子需求数量（超出
                  {{ group.excess }} 条），仍可保存</template
                >
                <template v-else-if="group.remaining > 0"
                  >该子需求剩余 {{ group.remaining }} 条可分配</template
                >
                <template v-else>该子需求已分配完成</template>
              </p>
              <Button
                block
                type="dashed"
                class="assignment-add"
                :disabled="formDisabled"
                :aria-label="`为子需求 ${group.index} 新增分配项`"
                @click="addRecord(group.id)"
                ><span class="icon-[lucide--plus]" aria-hidden="true"></span
                >新增分配项</Button
              >
            </section>
          </Form>
          <div
            v-if="excessQuantity > 0"
            class="assignment-overflow-summary"
            role="status"
          >
            <strong>分配数量已超出需求数量 {{ excessQuantity }} 条。</strong>
            <span>仅作数量提示，仍可保存</span>
          </div>
        </template>
      </div>
    </Spin>
    <template #footer>
      <Button :disabled="submitting" @click="emit('update:open', false)"
        >取消</Button
      >
      <Button
        type="primary"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submitAssignment"
        >保存分配</Button
      >
    </template>
  </Modal>
</template>

<style scoped>
.assignment-content {
  min-height: 120px;
}

.assignment-summary {
  padding: 12px 16px;
  border-radius: 8px;
}

.assignment-summary p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.6;
}

.assignment-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.assignment-card {
  padding: 16px;
  margin-bottom: 16px;
  border-style: solid;
  border-width: 1px;
  border-radius: 12px;
}

.assignment-card-title,
.assignment-record-title {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.assignment-card-title {
  margin-bottom: 12px;
}

.assignment-card-title strong {
  white-space: nowrap;
}

.assignment-remove {
  margin-left: auto;
}

.assignment-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 8px;
}

.assignment-description {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.assignment-record + .assignment-record {
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid hsl(var(--border));
}

.assignment-record-title {
  margin-bottom: 8px;
  font-size: 12px;
}

.assignment-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.assignment-help {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.assignment-warning-text {
  font-weight: 500;
  color: var(--assignment-warning-text);
}

.assignment-warning-tag {
  color: var(--assignment-warning-text);
  background: var(--assignment-warning-bg);
  border-color: transparent;
}

.assignment-add {
  margin-top: 12px;
}

.assignment-overflow-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--assignment-warning-text);
  background: var(--assignment-warning-bg);
  border-radius: 8px;
}

@media (max-width: 560px) {
  .assignment-card {
    padding: 12px;
  }

  .assignment-form-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
