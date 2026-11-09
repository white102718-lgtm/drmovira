<script setup lang="ts">
import type {
  MaterialOrderDetail,
  MaterialReviewAsset,
} from '#/api/requirement';
import type { TreeSelection } from '#/views/materials/components/MaterialFolderTree.vue';

import { computed, nextTick, ref, watch } from 'vue';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Empty,
  Input,
  message,
  Modal,
  Spin,
  Tabs,
  Tag,
} from 'ant-design-vue';
import {
  assignMaterialsApi,
  ORDER_STATUS_MAP,
  downloadMaterialOrderZip,
  getMaterialOrderDetail,
  getMaterialOrderThumbs,
  getMaterialReviewAssets,
  getMaterialReviewSummary,
  getMaterialRequirementSelection,
  reviewMaterialRequirement,
} from '#/api/requirement';
import { downloadFileByUrl } from '#/utils/download';
import MediaPreview from '#/views/components/MediaPreview.vue';
import PushMaterialModal from '#/views/components/PushMaterialModal.vue';
import MaterialFolderTree from '#/views/materials/components/MaterialFolderTree.vue';

const props = withDefaults(
  defineProps<{ open: boolean; orderId?: string; readOnly?: boolean }>(),
  { readOnly: false },
);
const emit = defineEmits<{ 'update:open': [boolean]; changed: [] }>();
const detail = ref<MaterialOrderDetail>();
const readOnly = computed(
  () =>
    props.readOnly ||
    Boolean(detail.value?.permissions.shared_read_only) ||
    ['paused', 'cancelled'].includes(detail.value?.status ?? ''),
);
const counts = ref<Record<string, number>>({});
const total = ref(0);
const activeReqId = ref('');
const items = ref<MaterialReviewAsset[]>([]);
const selected = ref(new Map<string, MaterialReviewAsset>());
const thumbs = ref<Record<string, string | null>>({});
const cursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const pageLoading = ref(false);
const selecting = ref(false);
const downloading = ref(false);
const submitting = ref(false);
const error = ref('');
const pageError = ref('');
const viewport = ref<HTMLElement>();
const previewOpen = ref(false);
const previewIndex = ref(0);
const pushOpen = ref(false);
const folderOpen = ref(false);
const folder = ref<TreeSelection>({ type: 'all' });
const reviewAction = ref<'pass' | 'reject'>('pass');
const reviewOpen = ref(false);
const reason = ref('');
const reviewError = ref('');
let sequence = 0;
let pageSequence = 0;

const requirements = computed(() => detail.value?.requirements ?? []);
const currentRequirement = computed(() =>
  requirements.value.find((row) => row.id === activeReqId.value),
);
const currentAssignments = computed(() =>
  (detail.value?.assignments ?? []).filter(
    (row) => row.req_id === activeReqId.value && row.status !== 'cancelled',
  ),
);
const requirementAccepted = computed(
  () =>
    currentAssignments.value.length > 0 &&
    currentAssignments.value.every((row) => row.status === 'accepted'),
);
const canReview = computed(
  () =>
    !readOnly.value &&
    Boolean(detail.value?.permissions.review) &&
    !loading.value &&
    !error.value &&
    currentAssignments.value.length > 0 &&
    currentAssignments.value.every((row) =>
      ['submitted', 'accepted'].includes(row.status),
    ) &&
    !requirementAccepted.value,
);
const selectedItems = computed(() => [...selected.value.values()]);
const selectedCount = computed(() => selected.value.size);
const currentTotal = computed(() => counts.value[activeReqId.value] ?? 0);
const allSelected = computed(
  () => currentTotal.value > 0 && selectedCount.value === currentTotal.value,
);
const previewItems = computed(() =>
  items.value
    .filter((item) => Boolean(item.url))
    .map((item) => ({
      id: item.id,
      filetype: item.filetype,
      url: item.url || undefined,
    })),
);
const pushItems = computed(() =>
  selectedItems.value
    .filter((item) => item.review_status === 'in_library')
    .map((item) => ({
      id: item.id,
      title: item.name,
      filetype: item.filetype,
    })),
);
const canFile = computed(
  () =>
    !readOnly.value &&
    Boolean(detail.value?.permissions.review) &&
    requirementAccepted.value &&
    !loading.value &&
    !error.value &&
    selectedCount.value > 0 &&
    selectedItems.value.every((item) =>
      ['accepted', 'in_library'].includes(item.review_status ?? ''),
    ),
);
const busy = computed(
  () => submitting.value || selecting.value || downloading.value,
);

function errorText(value: unknown, fallback: string) {
  return value instanceof Error ? value.message : fallback;
}
function formatSize(size: number) {
  return size >= 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)} MB`
    : `${(size / 1024).toFixed(1)} KB`;
}
function formatResolution(item: MaterialReviewAsset) {
  const { width, height } = item;
  return typeof width === 'number' &&
    Number.isFinite(width) &&
    width > 0 &&
    typeof height === 'number' &&
    Number.isFinite(height) &&
    height > 0
    ? `${width}×${height}`
    : '';
}
function formatDuration(seconds?: number | null) {
  return typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0
    ? `${Math.round(seconds)}s`
    : '';
}
function close() {
  if (!busy.value) emit('update:open', false);
}
function toggleSelected(item: MaterialReviewAsset) {
  const next = new Map(selected.value);
  if (next.has(item.id)) next.delete(item.id);
  else next.set(item.id, item);
  selected.value = next;
}
function openPreview(item: MaterialReviewAsset) {
  const index = previewItems.value.findIndex((value) => value.id === item.id);
  if (index < 0) return;
  previewIndex.value = index;
  previewOpen.value = true;
}

async function loadOrder() {
  const token = ++sequence;
  ++pageSequence;
  loading.value = true;
  error.value = '';
  pageLoading.value = false;
  items.value = [];
  selected.value = new Map();
  thumbs.value = {};
  hasMore.value = false;
  const orderId = props.orderId;
  if (!orderId) {
    loading.value = false;
    error.value = '缺少素材工单编号';
    return;
  }
  try {
    const [order, summary] = await Promise.all([
      getMaterialOrderDetail(orderId),
      getMaterialReviewSummary(orderId),
    ]);
    if (!props.open || token !== sequence) return;
    detail.value = order;
    counts.value = summary.counts;
    total.value = summary.total;
    activeReqId.value = order.requirements.some(
      (row) => row.id === activeReqId.value,
    )
      ? activeReqId.value
      : (order.requirements[0]?.id ?? '');
    loading.value = false;
    if (activeReqId.value) await resetPage();
  } catch (value) {
    if (token === sequence)
      error.value = errorText(value, '验收详情加载失败，请重试');
  } finally {
    if (token === sequence) loading.value = false;
  }
}

async function loadThumbs(ids: string[], token: number) {
  try {
    const result = await getMaterialOrderThumbs(ids);
    if (token === pageSequence && props.open)
      thumbs.value = { ...thumbs.value, ...result };
  } catch {
    // 缩略图失败时保留类型占位和预览入口，不阻断素材列表。
  }
}

async function loadMore() {
  if (
    !props.orderId ||
    !activeReqId.value ||
    pageLoading.value ||
    !hasMore.value ||
    loading.value
  )
    return;
  const token = pageSequence;
  const reqId = activeReqId.value;
  pageLoading.value = true;
  pageError.value = '';
  try {
    const result = await getMaterialReviewAssets(
      props.orderId,
      reqId,
      cursor.value,
    );
    if (!props.open || token !== pageSequence) return;
    const seen = new Set(items.value.map((item) => item.id));
    items.value.push(...result.items.filter((item) => !seen.has(item.id)));
    cursor.value = result.next_cursor;
    hasMore.value = Boolean(result.next_cursor);
    void loadThumbs(
      result.items.map((item) => item.id),
      token,
    );
  } catch (value) {
    if (token === pageSequence)
      pageError.value = errorText(value, '素材加载失败，请重试');
  } finally {
    if (token === pageSequence) pageLoading.value = false;
  }
  await nextTick();
  if (token === pageSequence && !pageError.value) onScroll();
}

async function resetPage() {
  ++pageSequence;
  items.value = [];
  selected.value = new Map();
  thumbs.value = {};
  cursor.value = null;
  hasMore.value = true;
  pageLoading.value = false;
  pageError.value = '';
  if (viewport.value) viewport.value.scrollTop = 0;
  await loadMore();
}
function changeRequirement(value: string | number) {
  if (busy.value || loading.value) return;
  activeReqId.value = String(value);
  previewOpen.value = false;
  void resetPage();
}
function onScroll() {
  const el = viewport.value;
  if (
    el &&
    el.clientHeight > 0 &&
    el.scrollHeight - el.scrollTop - el.clientHeight < 280 &&
    !pageError.value
  )
    void loadMore();
}
async function selectAll() {
  if (allSelected.value) {
    selected.value = new Map();
    return;
  }
  if (!props.orderId) return;
  selecting.value = true;
  const token = pageSequence;
  try {
    const result = await getMaterialRequirementSelection(
      props.orderId,
      activeReqId.value,
    );
    if (token === pageSequence)
      selected.value = new Map(result.items.map((item) => [item.id, item]));
  } catch (value) {
    message.error(errorText(value, '全选失败，请重试'));
  } finally {
    selecting.value = false;
  }
}
async function downloadSelected() {
  if (!selectedCount.value) return;
  downloading.value = true;
  try {
    const result = await downloadMaterialOrderZip([...selected.value.keys()]);
    if (!result?.url) throw new Error('未获取到下载地址，请重试');
    downloadFileByUrl(result.url, result.filename);
  } catch (value) {
    message.error(errorText(value, '打包下载失败'));
  } finally {
    downloading.value = false;
  }
}
function openPush() {
  if (readOnly.value) return;
  if (pushItems.value.length < selectedCount.value)
    message.info('仅上传选中素材中已入库的素材');
  pushOpen.value = true;
}
function openReview(action: 'pass' | 'reject') {
  if (!canReview.value) return;
  reviewAction.value = action;
  reason.value = '';
  reviewError.value = '';
  reviewOpen.value = true;
}
async function submitReview() {
  if (!props.orderId || !detail.value || !canReview.value || submitting.value)
    return;
  if (reviewAction.value === 'reject' && !reason.value.trim()) {
    reviewError.value = '请填写打回原因';
    return;
  }
  submitting.value = true;
  reviewError.value = '';
  try {
    // 请求只提交子需求 ID；已加载多少页、勾选哪些素材均不改变验收范围。
    const result = await reviewMaterialRequirement(
      props.orderId,
      activeReqId.value,
      {
        action: reviewAction.value,
        version: detail.value.version,
        reason: reason.value.trim(),
      },
    );
    reviewOpen.value = false;
    message.success(
      reviewAction.value === 'reject'
        ? '当前子需求已打回重新交付'
        : result.status === 'accepted'
          ? '全部子需求验收通过，工单已完成'
          : '当前子需求验收通过',
    );
    emit('changed');
    await loadOrder();
  } catch (value) {
    reviewError.value = errorText(value, '验收失败，请刷新详情后重试');
  } finally {
    submitting.value = false;
  }
}
async function fileSelected() {
  if (
    !canFile.value ||
    !props.orderId ||
    folder.value.type !== 'folder' ||
    !folder.value.folderId
  )
    return;
  submitting.value = true;
  try {
    // 文件夹操作沿用现有入库接口，不通过添加文件夹隐式验收其他子需求。
    await assignMaterialsApi(props.orderId, {
      ids: [...selected.value.keys()],
      scope: 'personal',
      folder_id: folder.value.folderId,
    });
    folderOpen.value = false;
    message.success('已添加到文件夹');
    emit('changed');
    await loadOrder();
  } catch (value) {
    message.error(errorText(value, '添加到文件夹失败'));
  } finally {
    submitting.value = false;
  }
}

watch(
  () => [props.open, props.orderId] as const,
  ([open]) => {
    ++sequence;
    ++pageSequence;
    reviewOpen.value = false;
    previewOpen.value = false;
    pushOpen.value = false;
    folderOpen.value = false;
    detail.value = undefined;
    activeReqId.value = '';
    if (open) void loadOrder();
  },
  { immediate: true },
);
</script>

<template>
  <Drawer
    :open="open"
    width="100%"
    title="验收任务交付"
    :closable="!busy"
    :mask-closable="!busy"
    :keyboard="!busy"
    :body-style="{ padding: 0, overflow: 'hidden' }"
    @close="close"
    @after-open-change="onScroll"
  >
    <div class="material-review">
      <Alert
        v-if="error"
        type="error"
        show-icon
        :message="error"
        class="review-error"
        ><template #action
          ><Button @click="loadOrder">重新加载</Button></template
        ></Alert
      >
      <Spin v-if="loading" class="review-loading" tip="加载验收详情…" />
      <template v-else-if="detail && !error">
        <header class="review-banner">
          <div class="review-heading">
            <div>
              <Tag color="purple">素材验收</Tag
              ><Tag
                :color="
                  detail.status === 'accepted' || detail.status === 'archived'
                    ? 'green'
                    : 'orange'
                "
                >{{ ORDER_STATUS_MAP[detail.status] || detail.status }}</Tag
              >
            </div>
            <h2>{{ detail.title }}</h2>
            <p>
              {{ detail.order_no }} · {{ detail.project }} ·
              {{ detail.creator }}
            </p>
          </div>
          <dl class="review-stats">
            <div>
              <dt>计划数量</dt>
              <dd>{{ detail.quantity ?? 0 }} 条</dd>
            </div>
            <div>
              <dt>实际上传</dt>
              <dd>{{ total }} 条</dd>
            </div>
            <div>
              <dt>已选择</dt>
              <dd>{{ selectedCount }} 条</dd>
            </div>
          </dl>
        </header>
        <Tabs
          :active-key="activeReqId"
          class="review-tabs"
          @change="changeRequirement"
        >
          <Tabs.TabPane
            v-for="(req, index) in requirements"
            :key="req.id"
            :disabled="busy"
          >
            <template #tab
              ><span
                >{{ index + 1 }}.
                {{ req.seq_label || `需求${index + 1}` }}</span
              ><Tag class="review-tab-count"
                >{{ counts[req.id] ?? 0 }} / {{ req.quantity }} 条</Tag
              ></template
            >
          </Tabs.TabPane>
        </Tabs>
        <div v-if="currentRequirement" class="review-toolbar">
          <div class="review-description">
            <strong>{{ currentRequirement.seq_label }}</strong>
            <p>{{ currentRequirement.description }}</p>
          </div>
          <div class="review-tools">
            <Button
              :loading="selecting"
              :disabled="busy || !currentTotal"
              @click="selectAll"
              >{{ allSelected ? '取消全选' : '全选本需求' }}</Button
            >
            <Button
              :loading="downloading"
              :disabled="busy || !selectedCount"
              @click="downloadSelected"
              >打包下载</Button
            >
            <Button
              v-if="!readOnly"
              :disabled="busy || !pushItems.length"
              @click="openPush"
              >上传到广告账户</Button
            >
            <Button
              v-if="!readOnly"
              :disabled="busy || !canFile"
              title="当前子需求验收通过后，可将选中素材添加到文件夹"
              @click="folderOpen = true"
              >添加到文件夹</Button
            >
          </div>
        </div>
        <div ref="viewport" class="review-scroll" @scroll.passive="onScroll">
          <div class="review-grid">
            <article
              v-for="item in items"
              :key="item.id"
              class="review-card"
              :class="{ 'is-selected': selected.has(item.id) }"
            >
              <div class="review-media">
                <button
                  class="review-preview"
                  :disabled="!item.url"
                  :aria-label="`预览 ${item.name}`"
                  @click="openPreview(item)"
                >
                  <img
                    v-if="thumbs[item.id]"
                    :src="`data:image/jpeg;base64,${thumbs[item.id]}`"
                    :alt="item.name"
                    loading="lazy"
                  />
                  <span v-else class="review-placeholder"
                    ><IconifyIcon
                      :icon="
                        item.filetype === 'image'
                          ? 'lucide:image'
                          : 'lucide:video'
                      "
                    /><span>{{
                      item.filetype === 'image' ? '图片' : '视频'
                    }}</span></span
                  >
                  <span
                    v-if="item.url && thumbs[item.id]"
                    class="review-preview-action"
                    aria-hidden="true"
                  >
                    <IconifyIcon
                      :class="{
                        'review-preview-play': item.filetype === 'video',
                      }"
                      :icon="
                        item.filetype === 'image'
                          ? 'ant-design:eye-outlined'
                          : 'ant-design:caret-right-filled'
                      "
                    />
                  </span>
                  <span
                    v-if="
                      item.filetype === 'video' && formatDuration(item.duration)
                    "
                    class="review-duration"
                    :title="`时长 ${formatDuration(item.duration)}`"
                    >{{ formatDuration(item.duration) }}</span
                  >
                </button>
                <Checkbox
                  class="review-select"
                  :checked="selected.has(item.id)"
                  :disabled="busy"
                  :aria-label="`选择 ${item.name}`"
                  @change="toggleSelected(item)"
                  >选择</Checkbox
                >
              </div>
              <div class="review-card-info">
                <strong :title="item.name">{{ item.name }}</strong>
                <div class="review-card-meta">
                  <span
                    v-if="formatResolution(item)"
                    :title="`分辨率 ${formatResolution(item)}`"
                    >{{ formatResolution(item) }}</span
                  >
                  <span>{{ item.filetype === 'image' ? '图片' : '视频' }}</span>
                  <span>{{ formatSize(item.size) }}</span>
                </div>
                <Tag
                  v-if="item.review_status"
                  :color="item.review_status === 'rejected' ? 'red' : 'green'"
                  >{{
                    item.review_status === 'in_library'
                      ? '已入库'
                      : item.review_status === 'accepted'
                        ? '已验收'
                        : '已打回'
                  }}</Tag
                >
              </div>
            </article>
          </div>
          <div class="review-page-state">
            <Spin v-if="pageLoading" tip="正在加载素材…" />
            <Alert
              v-else-if="pageError"
              type="error"
              show-icon
              :message="pageError"
              ><template #action
                ><Button @click="loadMore">重试</Button></template
              ></Alert
            >
            <Empty
              v-else-if="!items.length"
              :description="
                requirements.length ? '当前子需求暂无交付素材' : '暂无子需求'
              "
            />
            <Button v-else-if="hasMore" @click="loadMore">继续加载</Button>
            <span v-else>已展示全部 {{ items.length }} 条素材</span>
          </div>
        </div>
      </template>
    </div>
    <template #footer>
      <div class="review-footer">
        <span v-if="readOnly">查看工单交付素材</span
        ><span v-else-if="requirementAccepted">当前子需求已验收通过</span
        ><span v-else-if="currentRequirement"
          >验收操作作用于当前子需求的全部交付素材</span
        >
        <div>
          <Button :disabled="busy" @click="close">取消</Button
          ><Button
            v-if="!readOnly"
            danger
            :disabled="!canReview || busy"
            @click="openReview('reject')"
            >打回重新交付</Button
          ><Button
            v-if="!readOnly"
            type="primary"
            :disabled="!canReview || busy"
            @click="openReview('pass')"
            >验收通过</Button
          >
        </div>
      </div>
    </template>
  </Drawer>
  <Modal
    :open="reviewOpen"
    :title="reviewAction === 'pass' ? '验收当前子需求' : '打回当前子需求'"
    :ok-text="reviewAction === 'pass' ? '验收通过' : '打回重新交付'"
    cancel-text="取消"
    :confirm-loading="submitting"
    :closable="!submitting"
    :mask-closable="!submitting"
    :cancel-button-props="{ disabled: submitting }"
    @ok="submitReview"
    @cancel="reviewOpen = false"
  >
    <p>
      {{ currentRequirement?.seq_label }}：{{ currentRequirement?.description }}
    </p>
    <p>
      本次{{ reviewAction === 'pass' ? '验收' : '打回' }}该子需求全部
      {{ currentTotal }} 条交付素材。
    </p>
    <template v-if="reviewAction === 'reject'"
      ><label for="material-review-reason"
        >打回原因 <span class="text-red-500">*</span></label
      ><Input.TextArea
        id="material-review-reason"
        v-model:value="reason"
        :maxlength="1000"
        :rows="4"
        show-count
        :disabled="submitting"
    /></template>
    <Alert
      v-if="reviewError"
      class="mt-4"
      :message="reviewError"
      type="error"
      show-icon
    />
  </Modal>
  <Modal
    :open="folderOpen"
    title="添加到文件夹"
    ok-text="确认添加"
    cancel-text="取消"
    :confirm-loading="submitting"
    :ok-button-props="{ disabled: folder.type !== 'folder' || !canFile }"
    :closable="!submitting"
    :mask-closable="!submitting"
    @ok="fileSelected"
    @cancel="folderOpen = false"
    ><div class="review-folder-tree">
      <MaterialFolderTree
        v-if="folderOpen"
        v-model="folder"
        auto-height
        :allow-create="canFile && !submitting"
        :show-library="false"
        :show-effectiveness="false"
      /></div
  ></Modal>
  <PushMaterialModal v-model:open="pushOpen" :materials="pushItems" />
  <MediaPreview
    v-model:open="previewOpen"
    v-model:current-index="previewIndex"
    :items="previewItems"
    :z-index="2200"
  />
</template>

<style scoped>
.material-review {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  color: hsl(var(--foreground));
  background: hsl(var(--background));
}

.review-error {
  margin: 20px;
}

.review-loading {
  margin: auto;
}

.review-banner {
  display: flex;
  flex: none;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: linear-gradient(110deg, white 55%, #edf4ff);
  border-bottom: 1px solid hsl(var(--border));
}

.review-heading {
  min-width: 0;
}

.review-heading h2 {
  margin: 10px 0;
  font-size: 22px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.review-heading p,
.review-description p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
}

.review-stats {
  display: flex;
  flex: none;
  gap: 8px;
  margin: 0;
}

.review-stats div {
  min-width: 120px;
  padding: 12px;
  background: rgb(255 255 255 / 80%);
  border: 1px solid #dbe8fc;
  border-radius: 10px;
}

.review-stats dt {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.review-stats dd {
  margin: 6px 0 0;
  font-size: 16px;
  font-weight: 600;
}

.review-tabs {
  flex: none;
  padding: 0 20px;
  background: hsl(var(--card));
}

.review-tab-count {
  margin-left: 8px;
}

.review-toolbar {
  display: flex;
  flex: none;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid hsl(var(--border));
}

.review-description {
  min-width: 0;
}

.review-description p {
  max-height: 64px;
  overflow: auto;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.review-tools {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  gap: 8px;
}

.review-scroll {
  flex: 1;
  min-height: 0;
  padding: 16px 20px;
  overflow: auto;
  overscroll-behavior: contain;
}

.review-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr));
  gap: 14px;
}

.review-card {
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.review-card.is-selected {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 1px hsl(var(--primary));
}

.review-media {
  position: relative;
  height: 180px;
  background: #10182b;
}

.review-preview {
  position: relative;
  width: 100%;
  height: 100%;
  padding: 0;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.review-preview:focus-visible {
  outline: 3px solid #60a5fa;
  outline-offset: -3px;
}

.review-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.review-placeholder {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #c2d0e7;
}

.review-placeholder > :first-child {
  width: 32px;
  height: 32px;
}

.review-preview-action {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: hsl(var(--background));
  pointer-events: none;
}

.review-preview-action > :first-child {
  width: 40px;
  height: 40px;
  padding: 4px;
  background: hsl(var(--overlay));
  border-radius: 50%;
}

.review-preview-action > .review-preview-play {
  padding: 10px;
  color: #fff;
  background: rgb(255 255 255 / 30%);
}

.review-duration {
  position: absolute;
  right: 8px;
  bottom: 8px;
  padding: 2px 4px;
  font-size: 12px;
  color: hsl(var(--background));
  pointer-events: none;
  background: hsl(var(--overlay));
  border-radius: 4px;
}

.review-select {
  position: absolute;
  top: 10px;
  left: 10px;
  padding: 4px 8px;
  background: hsl(var(--card));
  border-radius: 5px;
}

.review-card-info {
  padding: 12px;
}

.review-card-info strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  white-space: nowrap;
}

.review-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 6px 0;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.review-card-meta > span {
  padding: 2px 4px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.review-page-state {
  padding: 24px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.review-footer {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.review-footer > span {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.review-footer > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  margin-left: auto;
}

.review-folder-tree {
  /* 为弹窗标题、底部按钮及上下边距留空间，较矮屏幕只滚动目录内容。 */
  max-height: min(70dvh, var(--adpulse-table-viewport-height));
  overflow-y: auto;
}

@media (max-width: 1100px) {
  .review-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (max-width: 767px) {
  .review-banner {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
    padding: 16px;
  }

  .review-stats div {
    flex: 1;
    min-width: 0;
  }

  .review-heading h2 {
    font-size: 18px;
  }

  .review-toolbar,
  .review-scroll {
    padding: 12px;
  }

  .review-description p {
    max-height: 42px;
  }

  .review-tools {
    gap: 6px;
  }

  .review-footer {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
