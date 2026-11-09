<script setup lang="ts">
import type {
  MaterialAssignment,
  MaterialOrderDetail,
  MaterialOrderOutputSummary,
  MaterialOrderReviewRecord,
} from '#/api/requirement';
import type { UploadFileItem } from '#/views/components/RequirementUploadModal.vue';
import { computed, ref, watch } from 'vue';
import { useUserStore } from '@vben/stores';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Empty,
  Modal,
  Spin,
  Table,
  Tag,
  message,
} from 'ant-design-vue';
import {
  ASSIGNMENT_STATUS_MAP,
  ORDER_STATUS_MAP,
  completeMaterialOrder,
  deliverMaterialOrder,
  getMaterialOrderDetail,
  getMaterialOrderOutputs,
  getMaterialOrderReviewRecords,
} from '#/api/requirement';
import { useMaterialOrderAccess } from '#/composables/useMaterialOrderAccess';
import facebookCountries from '#/data/facebook_countries.json';
import {
  canEditRejectedMaterialOrder,
  canReeditMaterialOrder,
  canResubmitMaterialOrder,
} from '#/domain/task';
import UploadMaterialModal from '#/views/components/RequirementUploadModal.vue';
import MaterialAssignmentModal from './MaterialAssignmentModal.vue';
import MaterialReferenceFiles from './MaterialReferenceFiles.vue';
import { useMaterialOrderLifecycle } from '#/composables/useMaterialOrderLifecycle';

const props = withDefaults(
  defineProps<{
    open: boolean;
    orderId?: string;
    initialAction?: 'view' | 'deliver';
    readOnly?: boolean;
  }>(),
  { initialAction: 'view', readOnly: false },
);
const emit = defineEmits<{
  'update:open': [open: boolean];
  changed: [];
  edit: [orderId: string];
  reedit: [orderId: string];
  resubmit: [orderId: string];
}>();
const userStore = useUserStore();
const { canCreateMaterialOrder } = useMaterialOrderAccess();
const detail = ref<MaterialOrderDetail>();
const readOnly = computed(
  () =>
    props.readOnly ||
    Boolean(detail.value?.permissions.shared_read_only) ||
    ['paused', 'cancelled'].includes(detail.value?.status ?? ''),
);
const {
  pendingOrderId: lifecyclePendingId,
  pendingAction: lifecyclePendingAction,
  run: runLifecycle,
} = useMaterialOrderLifecycle(afterChange);
const lifecycleActions = computed(() => {
  const order = detail.value;
  if (!order || props.readOnly || order.permissions.shared_read_only) return [];
  return (
    [
      { key: 'pause', label: '暂停任务' },
      { key: 'resume', label: '开启任务' },
      { key: 'cancel', label: '取消任务' },
    ] as const
  ).filter((action) => order.permissions[action.key]);
});
const outputs = ref<MaterialOrderOutputSummary[]>([]);
const reviews = ref<MaterialOrderReviewRecord[]>([]);
const referencePreviewOpen = ref(false);
const attachmentPreviewOpen = ref(false);
const loading = ref(false);
const loadError = ref('');
const outputsError = ref('');
const reviewsError = ref('');
const assignmentExpanded = ref<string[]>([]);
const deliveryExpanded = ref<string[]>([]);
const assignmentOpen = ref(false);
const deliveryOpen = ref(false);
const completionIds = ref<string[]>([]);
const submitting = ref(false);
const uploadOpen = ref(false);
const uploading = ref(false);
const uploadAssignmentIds = ref<string[]>([]);
const uploadModal = ref<InstanceType<typeof UploadMaterialModal>>();
let requestSequence = 0;
function resubmitOrder() {
  if (
    !canCreateMaterialOrder.value ||
    readOnly.value ||
    !detail.value ||
    !canResubmitMaterialOrder(detail.value)
  )
    return;
  emit('resubmit', detail.value.id);
}

function editRejectedOrder() {
  if (
    readOnly.value ||
    !detail.value ||
    !(
      canReeditMaterialOrder(detail.value) ||
      canEditRejectedMaterialOrder(detail.value)
    )
  )
    return;
  if (canReeditMaterialOrder(detail.value)) emit('reedit', detail.value.id);
  else emit('edit', detail.value.id);
}
const userId = computed(() => String(userStore.userInfo?.userId ?? ''));
const requirements = computed(() => detail.value?.requirements ?? []);
const assignments = computed(() => detail.value?.assignments ?? []);
const ownWorkingAssignments = computed(() =>
  assignments.value.filter(
    (record) =>
      record.designer_user_id === userId.value &&
      ['in_production', 'rejected'].includes(record.status),
  ),
);
const ownUploadAssignments = computed(() =>
  assignments.value.filter(
    (record) =>
      record.designer_user_id === userId.value &&
      ['in_production', 'rejected', 'submitted', 'accepted'].includes(
        record.status,
      ),
  ),
);
const expandedRowKeys = computed(() => [
  ...new Set([...assignmentExpanded.value, ...deliveryExpanded.value]),
]);
const designerCount = computed(
  () =>
    new Set(assignments.value.map((record) => record.designer_user_id)).size,
);
const scopeLabel = computed(() =>
  detail.value?.task_scope === 'personal' ? '个人任务' : '部门任务',
);
const countryNames = Object.fromEntries(
  facebookCountries.map((country) => [country.code, country.name]),
);
const tagRows = computed(() => [
  {
    label: '国家',
    tags: (detail.value?.tags.country ?? []).map(
      (code) => countryNames[code] ?? code,
    ),
  },
  { label: '题材', tags: detail.value?.tags.theme ?? [] },
  { label: '玩法', tags: detail.value?.tags.gameplay ?? [] },
]);
const basicFields = computed(() => {
  const order = detail.value;
  if (!order) return [];
  return [
    { label: '需求标题', value: order.title, wide: true },
    { label: '项目', value: order.project },
    { label: '任务归属', value: scopeLabel.value },
    {
      label: '类型',
      value:
        ({ VIDEO: '视频', IMAGE: '图片' } as Record<string, string>)[
          order.demand_type.toUpperCase()
        ] ?? order.demand_type,
    },
    {
      label: '交付数量',
      value: order.quantity == null ? '' : `${order.quantity} 条`,
    },
    { label: '素材尺寸', value: order.sizes.join(' / ') },
    { label: '优先级', value: order.priority },
    { label: '创建部门', value: order.department },
    { label: '执行部门', value: order.execution_department },
    { label: '负责部门', value: order.responsible_department },
    { label: '抄送人', value: order.cc_user_name },
    { label: '语种', value: order.language },
    {
      label: '按绿通素材要求产出',
      value:
        order.is_green_material == null
          ? ''
          : order.is_green_material
            ? '是'
            : '否',
    },
    {
      label: '预期交付时间',
      value: formatDeliveryDate(order.expected_delivery_at),
    },
    { label: '任务编号', value: order.order_no },
    { label: '官方台子名称', value: order.product_info, wide: true },
    {
      label: '创建人／创建时间',
      value: `${order.creator || '—'} · ${formatDate(order.created_at)}`,
    },
  ];
});
const columns = [
  { title: '序号', key: 'sequence', width: 70 },
  {
    title: '需求描述',
    dataIndex: 'description',
    key: 'description',
    width: 300,
  },
  { title: '时长', dataIndex: 'duration', key: 'duration', width: 85 },
  { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 75 },
  { title: '相关链接', dataIndex: 'link', key: 'link', width: 130 },
  { title: '备注', dataIndex: 'remark', key: 'remark', width: 130 },
  { title: '合规要求', dataIndex: 'compliance', key: 'compliance', width: 140 },
  { title: '需求附件', key: 'attachments', width: 160 },
  { title: '操作', key: 'actions', width: 145, fixed: 'right' as const },
];

/** 预期交付按日期展示，兼容旧工单返回的日期时间。 */
function formatDeliveryDate(value?: string | null) {
  return value ? value.slice(0, 10) : '—';
}

function formatDate(value?: string | null) {
  return value ? value.slice(0, 19).replace('T', ' ') : '—';
}
function safeUrl(value: unknown) {
  return typeof value === 'string' && /^https?:\/\//i.test(value)
    ? value
    : undefined;
}
function requirementAssignments(id: string) {
  return assignments.value.filter((record) => record.req_id === id);
}
function requirementOutputs(id: string) {
  return outputs.value.filter((output) => output.req_id === id);
}
function assignmentName(record: MaterialAssignment) {
  return `${requirements.value.find((item) => item.id === record.req_id)?.seq_label || '子需求'} · 分配项 ${record.sort_order + 1}`;
}
function usableOutputCount(id: string) {
  return outputs.value.filter(
    (output) =>
      output.assignment_id === id &&
      !output.superseded &&
      output.review_status !== 'rejected',
  ).length;
}
function toggleExpanded(ids: string[], id: string) {
  return ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id];
}
function canUploadRequirement(id: string) {
  return (
    !readOnly.value &&
    detail.value?.permissions.upload &&
    ownUploadAssignments.value.some((record) => record.req_id === id)
  );
}
const uploadOptions = computed(() =>
  ownUploadAssignments.value
    .filter((record) => uploadAssignmentIds.value.includes(record.id))
    .map((record) => ({
      value: record.id,
      label: `${requirements.value.find((item) => item.id === record.req_id)?.seq_label || '子需求'} · ${record.quantity} 条`,
      designer: record.designer_name,
      creativePlanner: record.creative_planner_name || undefined,
      remark: record.remark,
    })),
);
const uploadKey = computed(
  () =>
    `material-detail:${props.orderId ?? ''}:${uploadAssignmentIds.value.join(',')}`,
);
const canSubmitCompletion = computed(
  () =>
    !readOnly.value &&
    Boolean(detail.value?.permissions.upload) &&
    completionIds.value.length > 0 &&
    completionIds.value.every(
      (id) =>
        ownWorkingAssignments.value.some((record) => record.id === id) &&
        usableOutputCount(id) > 0,
    ),
);

/** 每次打开重新读工单；关闭或切换订单后，旧请求不得覆盖当前抽屉。 */
async function reload() {
  const id = props.orderId;
  if (!props.open || !id) return false;
  const sequence = ++requestSequence;
  loading.value = true;
  loadError.value = '';
  const [orderResult, outputResult, reviewResult] = await Promise.allSettled([
    getMaterialOrderDetail(id),
    getMaterialOrderOutputs(id),
    getMaterialOrderReviewRecords(id),
  ]);
  if (sequence !== requestSequence || !props.open) return false;
  loading.value = false;
  if (orderResult.status === 'rejected') {
    loadError.value =
      orderResult.reason instanceof Error
        ? orderResult.reason.message
        : '任务详情加载失败';
    return false;
  }
  detail.value = orderResult.value;
  outputs.value =
    outputResult.status === 'fulfilled' ? outputResult.value.items : [];
  reviews.value =
    reviewResult.status === 'fulfilled' ? reviewResult.value.items : [];
  outputsError.value =
    outputResult.status === 'rejected' ? '交付记录加载失败，请重试' : '';
  reviewsError.value =
    reviewResult.status === 'rejected' ? '验收记录加载失败，请重试' : '';
  completionIds.value = completionIds.value.filter(
    (id) =>
      ownWorkingAssignments.value.some((record) => record.id === id) &&
      usableOutputCount(id) > 0,
  );
  return true;
}
watch(
  () => [props.open, props.orderId] as const,
  async ([open]) => {
    ++requestSequence;
    detail.value = undefined;
    referencePreviewOpen.value = false;
    attachmentPreviewOpen.value = false;
    outputs.value = [];
    reviews.value = [];
    assignmentExpanded.value = [];
    deliveryExpanded.value = [];
    completionIds.value = [];
    loadError.value = '';
    assignmentOpen.value = deliveryOpen.value = uploadOpen.value = false;
    if (open && (await reload()) && props.initialAction === 'deliver')
      openDelivery();
  },
  { immediate: true },
);

function openDelivery() {
  if (readOnly.value || !detail.value?.permissions.upload) return;
  if (!ownWorkingAssignments.value.length) {
    openUpload();
    return;
  }
  completionIds.value = ownWorkingAssignments.value
    .filter((record) => usableOutputCount(record.id) > 0)
    .map((record) => record.id);
  deliveryOpen.value = true;
}
function openUpload(reqId?: string, assignmentId?: string) {
  if (readOnly.value || !detail.value?.permissions.upload) return;
  uploadAssignmentIds.value = ownUploadAssignments.value
    .filter(
      (record) =>
        (!reqId || record.req_id === reqId) &&
        (!assignmentId || record.id === assignmentId),
    )
    .map((record) => record.id);
  if (!uploadAssignmentIds.value.length) {
    message.warning('该子需求暂无您已确认的分配记录');
    return;
  }
  uploadOpen.value = true;
}
async function afterChange() {
  await reload();
  emit('changed');
}

/** 上传只写当前登录人已确认的分配；上传和最终提交验收保持两个明确步骤。 */
async function submitUpload(
  key: string,
  files: UploadFileItem[],
  _designer?: string,
  assignmentId?: string,
) {
  const orderId = props.orderId;
  if (
    !orderId ||
    key !== uploadKey.value ||
    uploading.value ||
    readOnly.value ||
    !detail.value?.permissions.upload
  )
    return;
  if (
    !assignmentId ||
    !uploadAssignmentIds.value.includes(assignmentId) ||
    !ownUploadAssignments.value.some((record) => record.id === assignmentId)
  ) {
    message.warning('请选择您已确认的分配记录');
    return;
  }
  if (!files.length || files.some((file) => !file.uploadData)) {
    message.warning('请等待素材上传完成');
    return;
  }
  const materials = files.flatMap((file) =>
    file.uploadData
      ? [
          {
            filename: file.uploadData.name,
            basename: file.uploadData.basename,
            object_key: file.uploadData.object_key,
            url: file.uploadData.url,
            size: file.uploadData.size,
            content_type: file.uploadData.content_type,
            filetype: file.uploadData.filetype,
            file_md5: file.uploadData.file_md5,
            sha3_256: file.uploadData.sha3_256,
            img: file.uploadData.img,
            width: file.uploadData.width,
            height: file.uploadData.height,
            duration: file.uploadData.duration ?? 0,
            assignment_id: assignmentId,
          },
        ]
      : [],
  );
  uploading.value = true;
  try {
    await deliverMaterialOrder(orderId, materials);
    uploadModal.value?.showDeliverResult(key, '素材上传成功');
    uploadModal.value?.initFiles(key, []);
    if (props.orderId === orderId && props.open) {
      uploadOpen.value = false;
      await reload();
      if (
        props.open &&
        props.orderId === orderId &&
        deliveryOpen.value &&
        usableOutputCount(assignmentId) > 0
      )
        completionIds.value = [
          ...new Set([...completionIds.value, assignmentId]),
        ];
    }
    emit('changed');
    message.success('素材已上传，完成后可提交所选分配验收');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '素材提交失败，请重试',
    );
  } finally {
    uploading.value = false;
  }
}
async function submitCompletion() {
  const orderId = props.orderId;
  if (!orderId || submitting.value || !canSubmitCompletion.value) return;
  submitting.value = true;
  try {
    await completeMaterialOrder(orderId, [...completionIds.value]);
    if (props.orderId === orderId && props.open) {
      deliveryOpen.value = false;
      await reload();
    }
    emit('changed');
    message.success('所选分配已提交验收');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '提交验收失败，请重试',
    );
  } finally {
    submitting.value = false;
  }
}
defineExpose({ reload });
</script>

<template>
  <Drawer
    :open="open"
    :keyboard="!referencePreviewOpen && !attachmentPreviewOpen"
    width="100%"
    placement="right"
    :body-style="{ padding: '24px', background: '#f7f9fc' }"
    @close="emit('update:open', false)"
  >
    <template #title>
      <div class="drawer-title">
        {{ detail?.title || '素材任务详情'
        }}<span v-if="detail">
          · {{ ORDER_STATUS_MAP[detail.status] || detail.status }}</span
        >
      </div>
      <div class="drawer-order-number">{{ detail?.order_no || '—' }}</div>
    </template>
    <Spin :spinning="loading">
      <div class="material-detail-page">
        <Alert v-if="loadError" type="error" :message="loadError" show-icon
          ><template #action
            ><Button @click="reload">重试</Button></template
          ></Alert
        >
        <template v-else-if="detail">
          <section class="detail-banner">
            <div class="banner-heading">
              <div class="section-heading">
                <IconifyIcon icon="lucide:panels-top-left" />素材任务详情
                <Tag color="processing">{{
                  ORDER_STATUS_MAP[detail.status] || detail.status
                }}</Tag>
              </div>
              <h1>{{ detail.title }}</h1>
              <p>
                {{ detail.project || '—' }} · {{ scopeLabel }}
                <template v-if="detail.task_scope === 'department'">
                  · {{ detail.responsible_department || '—' }}
                </template>
              </p>
            </div>
            <dl class="summary-grid">
              <div>
                <dt>计划交付</dt>
                <dd>{{ detail.quantity ?? 0 }} 条</dd>
              </div>
              <div>
                <dt>子需求</dt>
                <dd>{{ requirements.length }} 条</dd>
              </div>
              <div>
                <dt>已分配素材师</dt>
                <dd>{{ designerCount }} 位</dd>
              </div>
              <div>
                <dt>截止时间</dt>
                <dd>{{ formatDeliveryDate(detail.expected_delivery_at) }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-section">
            <div class="section-header">
              <h2><IconifyIcon icon="lucide:clipboard-list" />原始需求详情</h2>
              <span>创建素材任务时填写的需求信息</span>
            </div>
            <dl class="basic-grid">
              <div
                v-for="field in basicFields"
                :key="field.label"
                :class="{ 'field-wide': field.wide }"
              >
                <dt>{{ field.label }}</dt>
                <dd>{{ field.value || '—' }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-section">
            <div class="section-header">
              <h2><IconifyIcon icon="lucide:tags" />素材标签</h2>
              <span>帮助素材中台分类与检索</span>
            </div>
            <div v-for="row in tagRows" :key="row.label" class="tag-row">
              <span>{{ row.label }}</span>
              <div>
                <Tag v-for="tag in row.tags" :key="tag">{{ tag }}</Tag
                ><span v-if="!row.tags.length" class="muted">—</span>
              </div>
            </div>
          </section>

          <section class="detail-section">
            <div class="section-header">
              <h2>
                <IconifyIcon icon="lucide:list-checks" />子需求明细
                <Tag>{{ requirements.length }} 条</Tag>
              </h2>
            </div>
            <Table
              :data-source="requirements"
              :columns="columns"
              row-key="id"
              :pagination="false"
              :scroll="{ x: 1235 }"
              :expanded-row-keys="expandedRowKeys"
              :show-expand-column="false"
              bordered
            >
              <template #bodyCell="{ column, record, index, text }">
                <template v-if="column.key === 'sequence'">{{
                  index + 1
                }}</template>
                <template v-else-if="column.key === 'link'"
                  ><a
                    v-if="safeUrl(record.link)"
                    :href="safeUrl(record.link)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="break-anywhere"
                    >{{ record.link }}</a
                  ><span v-else>{{ record.link || '—' }}</span></template
                >
                <template v-else-if="column.key === 'attachments'">
                  <MaterialReferenceFiles
                    :key="`${detail.id}:${record.id}`"
                    :references="record.attachments || []"
                    compact
                    @update:preview-open="attachmentPreviewOpen = $event"
                  />
                </template>
                <template v-else-if="column.key === 'actions'"
                  ><div class="row-actions">
                    <Button
                      type="link"
                      @click="
                        assignmentExpanded = toggleExpanded(
                          assignmentExpanded,
                          record.id,
                        )
                      "
                      >{{
                        assignmentExpanded.includes(record.id)
                          ? '收起分配'
                          : '查看分配'
                      }}<IconifyIcon
                        :icon="
                          assignmentExpanded.includes(record.id)
                            ? 'lucide:chevron-up'
                            : 'lucide:chevron-down'
                        " /></Button
                    ><Button
                      type="link"
                      @click="
                        deliveryExpanded = toggleExpanded(
                          deliveryExpanded,
                          record.id,
                        )
                      "
                      >{{
                        deliveryExpanded.includes(record.id)
                          ? '收起交付记录'
                          : '查看交付记录'
                      }}<IconifyIcon
                        :icon="
                          deliveryExpanded.includes(record.id)
                            ? 'lucide:chevron-up'
                            : 'lucide:chevron-down'
                        "
                    /></Button></div
                ></template>
                <template v-else
                  ><span class="multiline">{{
                    text === 0 ? 0 : text || '—'
                  }}</span></template
                >
              </template>
              <template #expandedRowRender="{ record }">
                <div
                  v-if="assignmentExpanded.includes(record.id)"
                  class="expanded-pane assignment-pane"
                >
                  <article
                    v-for="assignment in requirementAssignments(record.id)"
                    :key="assignment.id"
                    class="assignment-card"
                  >
                    <div class="section-header">
                      <h3>分配项 {{ assignment.sort_order + 1 }}</h3>
                      <Tag>{{ ASSIGNMENT_STATUS_MAP[assignment.status] }}</Tag>
                    </div>
                    <dl class="assignment-grid">
                      <div>
                        <dt>素材师</dt>
                        <dd>{{ assignment.designer_name }}</dd>
                      </div>
                      <div>
                        <dt>创意策划</dt>
                        <dd>{{ assignment.creative_planner_name || '—' }}</dd>
                      </div>
                      <div>
                        <dt>分配数量</dt>
                        <dd>{{ assignment.quantity }} 条</dd>
                      </div>
                      <div>
                        <dt>分配人</dt>
                        <dd>{{ assignment.assigned_by_name || '—' }}</dd>
                      </div>
                      <div>
                        <dt>开始制作</dt>
                        <dd>{{ formatDate(assignment.started_at) }}</dd>
                      </div>
                      <div class="field-wide">
                        <dt>备注</dt>
                        <dd>{{ assignment.remark || '—' }}</dd>
                      </div>
                    </dl>
                  </article>
                  <Empty
                    v-if="!requirementAssignments(record.id).length"
                    :image="Empty.PRESENTED_IMAGE_SIMPLE"
                    description="该子需求暂无分配记录"
                  />
                </div>
                <div
                  v-if="deliveryExpanded.includes(record.id)"
                  class="expanded-pane delivery-pane"
                >
                  <div class="section-header">
                    <h3>
                      交付记录 <span>仅展示当前子需求上传的素材名称</span>
                    </h3>
                    <div class="inline-actions">
                      <Tag
                        >{{ requirementOutputs(record.id).length }} 个素材</Tag
                      ><Button
                        v-if="canUploadRequirement(record.id)"
                        type="primary"
                        :disabled="uploading || loading"
                        @click="openUpload(record.id)"
                        >＋ 增加交付</Button
                      >
                    </div>
                  </div>
                  <Alert
                    v-if="outputsError"
                    :message="outputsError"
                    type="error"
                    show-icon
                    ><template #action
                      ><Button @click="reload">重试</Button></template
                    ></Alert
                  >
                  <ul
                    v-else-if="requirementOutputs(record.id).length"
                    class="output-names"
                  >
                    <li
                      v-for="output in requirementOutputs(record.id)"
                      :key="output.id"
                    >
                      {{ output.name }}
                    </li>
                  </ul>
                  <Empty
                    v-else
                    :image="Empty.PRESENTED_IMAGE_SIMPLE"
                    description="该子需求暂无交付记录"
                  />
                </div>
              </template>
            </Table>
          </section>

          <section class="detail-section">
            <MaterialReferenceFiles
              :key="detail.id"
              v-model:preview-open="referencePreviewOpen"
              :references="detail.references"
            />
          </section>

          <section class="detail-section">
            <div class="section-header">
              <h2>
                <IconifyIcon icon="lucide:clipboard-check" />验收记录
                <Tag>{{ reviews.length }} 条</Tag>
              </h2>
            </div>
            <Alert
              v-if="reviewsError"
              :message="reviewsError"
              type="error"
              show-icon
              ><template #action
                ><Button @click="reload">重试</Button></template
              ></Alert
            >
            <div v-else-if="reviews.length" class="review-list">
              <article v-for="review in reviews" :key="review.id">
                <div class="section-header">
                  <strong>{{ review.operator || '—' }}</strong
                  ><span>{{ formatDate(review.created_at) }}</span>
                </div>
                <p>{{ review.content }}</p>
              </article>
            </div>
            <Empty
              v-else
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
              description="暂无验收记录"
            />
          </section>
        </template>
      </div>
    </Spin>
    <template #footer
      ><div class="drawer-footer">
        <Button
          v-for="action in lifecycleActions"
          :key="action.key"
          :danger="action.key === 'cancel'"
          :loading="
            lifecyclePendingId === detail?.id &&
            lifecyclePendingAction === action.key
          "
          :disabled="loading || !!loadError || !!lifecyclePendingId"
          @click="detail && runLifecycle(detail, action.key)"
          >{{ action.label }}</Button
        >
        <Button @click="emit('update:open', false)">关闭</Button
        ><Button
          v-if="
            !readOnly &&
            canCreateMaterialOrder &&
            canResubmitMaterialOrder(detail)
          "
          :disabled="loading || !!loadError"
          @click="resubmitOrder"
          >再次提交</Button
        ><Button
          v-if="
            !readOnly &&
            (canReeditMaterialOrder(detail) ||
              canEditRejectedMaterialOrder(detail))
          "
          type="primary"
          :disabled="loading || !!loadError"
          @click="editRejectedOrder"
          >重新编辑</Button
        ><Button
          v-if="!readOnly && detail?.permissions.assign"
          :disabled="loading"
          @click="assignmentOpen = true"
          >分配任务</Button
        ><Button
          v-if="!readOnly && detail?.permissions.upload"
          type="primary"
          :disabled="loading || !!loadError"
          @click="openDelivery"
          >{{
            ownWorkingAssignments.length ? '填写交付并提交验收' : '上传素材'
          }}</Button
        >
      </div></template
    >
  </Drawer>

  <MaterialAssignmentModal
    v-model:open="assignmentOpen"
    :order-id="orderId"
    @assigned="afterChange"
  />
  <Modal
    v-model:open="deliveryOpen"
    title="填写交付并提交验收"
    :width="760"
    :body-style="{ maxHeight: '65vh', overflowY: 'auto' }"
    :confirm-loading="submitting"
    :ok-button-props="{
      disabled: !canSubmitCompletion || uploading || loading,
    }"
    ok-text="提交所选分配验收"
    cancel-text="取消"
    @ok="submitCompletion"
  >
    <p class="muted">按分配记录上传素材，勾选本次已完成的分配后提交验收。</p>
    <Alert v-if="outputsError" :message="outputsError" type="error" show-icon />
    <article
      v-for="assignment in ownWorkingAssignments"
      :key="assignment.id"
      class="completion-record"
    >
      <div class="section-header">
        <Checkbox
          :checked="completionIds.includes(assignment.id)"
          :disabled="!usableOutputCount(assignment.id) || submitting"
          @change="
            (event) =>
              (completionIds = event.target.checked
                ? [...new Set([...completionIds, assignment.id])]
                : completionIds.filter((id) => id !== assignment.id))
          "
          >{{ assignmentName(assignment) }}</Checkbox
        ><Button
          :disabled="submitting || uploading"
          @click="openUpload(assignment.req_id, assignment.id)"
          >上传素材</Button
        >
      </div>
      <p>
        {{ assignment.designer_name }} · 分配 {{ assignment.quantity }} 条 ·
        已上传 {{ usableOutputCount(assignment.id) }} 个素材
      </p>
      <p v-if="assignment.remark" class="muted multiline">
        {{ assignment.remark }}
      </p>
    </article>
    <Empty
      v-if="!ownWorkingAssignments.length"
      :image="Empty.PRESENTED_IMAGE_SIMPLE"
      description="暂无可提交的分配记录"
    />
  </Modal>
  <UploadMaterialModal
    ref="uploadModal"
    v-model:open="uploadOpen"
    :order-id="detail?.id"
    :demand-type="detail?.demand_type || ''"
    :persist-key="uploadKey"
    :description-options="uploadOptions"
    assignment-mode
    :show-designer="true"
    title="上传子需求素材"
    @all-done="submitUpload"
  />
</template>

<style scoped>
.material-detail-page,
.drawer-footer {
  max-width: 1384px;
  margin: 0 auto;
}

.material-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.drawer-title {
  font-size: 15px;
  font-weight: 600;
}

.drawer-order-number {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
}

.detail-section,
.detail-banner {
  padding: 16px;
  background: white;
  border: 1px solid #dfe7f3;
  border-radius: 12px;
}

.detail-banner {
  display: flex;
  gap: 24px;
  align-items: center;
  padding: 24px;
  background: #f8fbff;
  border-color: #bfdbfe;
}

.banner-heading {
  flex: 1;
  min-width: 0;
}

.banner-heading h1 {
  margin: 12px 0 4px;
  font-size: 26px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.banner-heading p {
  margin: 0;
  color: #64748b;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  width: 44%;
  margin: 0;
}

.summary-grid > div {
  padding: 12px;
  background: white;
  border-radius: 10px;
}

dt {
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
}

dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.summary-grid dd {
  font-size: 14px;
  font-weight: 600;
}

.section-header,
.section-heading,
.inline-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.section-header {
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h2,
.section-header h3 {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.section-header > span,
.section-header h3 span,
.muted {
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
}

.section-heading {
  font-size: 12px;
  font-weight: 600;
  color: #1677ff;
}

.basic-grid,
.assignment-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.basic-grid > div,
.assignment-grid > div {
  padding: 12px;
  border: 1px solid #dfe7f3;
  border-radius: 8px;
}

.basic-grid > div {
  background: #f8fafc;
}

.field-wide {
  grid-column: span 2;
}

.tag-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-top: 10px;
}

.tag-row > span {
  min-width: 46px;
  color: #64748b;
}

.tag-row > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.row-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.expanded-pane {
  padding: 12px;
  background: #f8fafc;
  border: 1px solid var(--adpulse-border);
  border-radius: var(--adpulse-radius);
}

.assignment-card {
  padding: 12px;
  margin-bottom: 12px;
  background: white;
  border: 1px solid #dfe7f3;
  border-radius: 8px;
}

.assignment-card:last-child {
  margin-bottom: 0;
}

.assignment-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.output-names {
  padding: 0;
  margin: 0;
  list-style: none;
}

.output-names li {
  padding: 10px 12px;
  overflow-wrap: anywhere;
  border-bottom: 1px solid #e2e8f0;
}

.review-list article,
.completion-record {
  padding: 12px;
  margin-top: 12px;
  border: 1px solid #dfe7f3;
  border-radius: 8px;
}

.review-list p,
.completion-record p {
  margin: 8px 0 0;
}

.multiline {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.break-anywhere {
  overflow-wrap: anywhere;
}

.drawer-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

@media (max-width: 1100px) {
  .detail-banner {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid {
    width: 100%;
  }

  .basic-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .detail-banner,
  .detail-section {
    padding: 12px;
  }

  .banner-heading h1 {
    font-size: 20px;
  }

  .basic-grid,
  .assignment-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .field-wide {
    grid-column: auto;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
