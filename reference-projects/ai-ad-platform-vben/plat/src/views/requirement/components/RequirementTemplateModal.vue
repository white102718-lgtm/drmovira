<script setup lang="ts">
import type {
  RequirementTemplate,
  RequirementTemplateAttachment,
  RequirementTemplateItem,
  RequirementTemplatePayload,
  RequirementTemplateSummary,
} from '#/api/requirement/templates';

import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Empty,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Spin,
  Upload,
  message,
} from 'ant-design-vue';
import {
  REQUIREMENT_TEMPLATE_ATTACHMENT_EXTS,
  createRequirementTemplate,
  deleteRequirementTemplate,
  getRequirementTemplate,
  getRequirementTemplateAttachmentUrl,
  listRequirementTemplates,
  updateRequirementTemplate,
  uploadRequirementTemplateAttachment,
} from '#/api/requirement/templates';
import { downloadFileByUrl } from '#/utils/download';
import ShadcnDataTable, {
  type ShadcnDataTableColumn,
} from '#/components/ui/ShadcnDataTable.vue';
import ExpandableDescriptionInput from './ExpandableDescriptionInput.vue';

interface EditorRow extends RequirementTemplateItem {
  key: string;
}
interface Editor {
  id?: string;
  version?: number;
  name: string;
  description: string;
  requirements: EditorRow[];
}
const props = withDefaults(
  defineProps<{
    open: boolean;
    mode?: 'manage' | 'use';
    canManage?: boolean;
  }>(),
  { mode: 'use', canManage: false },
);
const emit = defineEmits<{
  'update:open': [value: boolean];
  apply: [items: RequirementTemplateItem[], mode: 'append' | 'replace'];
}>();

const managing = ref(false);
const serverCanManage = ref(false);
const listLoading = ref(false);
const detailLoading = ref(false);
const saving = ref(false);
const error = ref('');
const keyword = ref('');
const items = ref<RequirementTemplateSummary[]>([]);
const nextCursor = ref<string | null>(null);
const editor = ref<Editor>();
const original = ref('');
const pendingUploads = ref<Record<string, number>>({});
const writable = computed(
  () => managing.value && props.canManage && serverCanManage.value,
);
const uploadCount = computed(() =>
  Object.values(pendingUploads.value).reduce((sum, count) => sum + count, 0),
);
const busy = computed(
  () => saving.value || detailLoading.value || uploadCount.value > 0,
);
const dirty = computed(
  () =>
    writable.value &&
    !!editor.value &&
    JSON.stringify(payload()) !== original.value,
);
const accept = REQUIREMENT_TEMPLATE_ATTACHMENT_EXTS.map(
  (ext) => `.${ext}`,
).join(',');
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let requestSequence = 0;
let selectionSequence = 0;
const controllers = new Set<AbortController>();

const columns = computed<ShadcnDataTableColumn[]>(() => [
  { align: 'left', key: 'description', title: '需求描述', width: '14%' },
  { align: 'left', key: 'duration', title: '时长', width: '14%' },
  { align: 'left', key: 'quantity', title: '数量', width: '9%' },
  { align: 'left', key: 'link', title: '相关链接', width: '14%' },
  { align: 'left', key: 'remark', title: '备注', width: '14%' },
  { align: 'left', key: 'compliance', title: '合规要求', width: '14%' },
  { align: 'left', key: 'attachments', title: '需求附件', width: '14%' },
  ...(writable.value
    ? [{ align: 'left' as const, key: 'actions', title: '操作', width: '7%' }]
    : []),
]);
const rowNumbers = computed(
  () =>
    new Map(
      (editor.value?.requirements ?? []).map((row, index) => [
        row.key,
        index + 1,
      ]),
    ),
);

function rowEditorPlacement(key: string) {
  // 与工单外层需求描述一致：首行优先向下，末行优先向上展开。
  const rowNumber = rowNumbers.value.get(key);
  if (rowNumber === 1) return 'bottom';
  return rowNumber === editor.value?.requirements.length ? 'top' : 'auto';
}

function payload(): RequirementTemplatePayload {
  const draft = editor.value;
  return {
    name: draft?.name.trim() ?? '',
    description: draft?.description.trim() ?? '',
    requirements: (draft?.requirements ?? []).map((row) => ({
      description: row.description.trim(),
      duration: row.duration.trim(),
      quantity: row.quantity,
      link: row.link.trim(),
      remark: row.remark.trim(),
      compliance: row.compliance.trim(),
      attachments: row.attachments.map((file) => ({
        attachment_id: file.attachment_id,
      })),
    })),
  };
}

function installTemplate(template: RequirementTemplate) {
  editor.value = {
    id: template.id,
    version: template.version,
    name: template.name,
    description: template.description,
    requirements: template.requirements.map((row) => ({
      ...row,
      key: crypto.randomUUID(),
      attachments: row.attachments.map((file) => ({ ...file })),
    })),
  };
  original.value = JSON.stringify(payload());
}

function discardChanges(): Promise<boolean> {
  if (busy.value) return Promise.resolve(false);
  if (!dirty.value) return Promise.resolve(true);
  return new Promise((resolve) =>
    Modal.confirm({
      title: '放弃未保存的模板修改？',
      zIndex: 2300,
      content: '已保存的模板不会受到影响。',
      okText: '放弃修改',
      cancelText: '继续编辑',
      onOk: () => {
        resolve(true);
      },
      onCancel: () => {
        resolve(false);
      },
    }),
  );
}

async function loadList(append = false) {
  const sequence = ++requestSequence;
  listLoading.value = true;
  error.value = '';
  try {
    const data = await listRequirementTemplates({
      keyword: keyword.value.trim(),
      cursor: append ? (nextCursor.value ?? undefined) : undefined,
      page_size: 20,
    });
    if (sequence !== requestSequence || !props.open) return;
    serverCanManage.value = data.can_manage;
    items.value = append ? [...items.value, ...data.items] : data.items;
    nextCursor.value = data.next_cursor;
  } catch (cause) {
    if (sequence === requestSequence)
      error.value =
        cause instanceof Error ? cause.message : '模板加载失败，请重试';
  } finally {
    if (sequence === requestSequence) listLoading.value = false;
  }
}

async function selectTemplate(
  item: RequirementTemplateSummary,
  duplicate = false,
) {
  if (!(await discardChanges())) return;
  const sequence = ++selectionSequence;
  detailLoading.value = true;
  error.value = '';
  try {
    const data = await getRequirementTemplate(item.id);
    if (sequence !== selectionSequence || !props.open) return;
    installTemplate(data);
    if (duplicate && writable.value && editor.value) {
      editor.value.id = undefined;
      editor.value.version = undefined;
      editor.value.name = `${data.name.slice(0, 94)}（副本）`;
      original.value = '';
    }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '模板详情加载失败';
    editor.value = undefined;
  } finally {
    if (sequence === selectionSequence) detailLoading.value = false;
  }
}

async function createDraft() {
  if (!writable.value || !(await discardChanges())) return;
  editor.value = { name: '', description: '', requirements: [] };
  addRow();
  original.value = JSON.stringify(payload());
}

function addRow() {
  if (
    !writable.value ||
    !editor.value ||
    editor.value.requirements.length >= 100
  )
    return;
  editor.value.requirements.push({
    key: crypto.randomUUID(),
    description: '',
    duration: '',
    quantity: 1,
    link: '',
    remark: '',
    compliance: '',
    attachments: [],
  });
}

async function save() {
  if (!writable.value || !editor.value || busy.value) return;
  const data = payload();
  if (!data.name) {
    message.warning('请输入模板名称');
    return;
  }
  if (
    !data.requirements.length ||
    data.requirements.some(
      (row) => !row.description || !row.quantity || row.quantity < 1,
    )
  ) {
    message.warning('每条子需求都需要填写描述和大于 0 的数量');
    return;
  }
  saving.value = true;
  error.value = '';
  try {
    const saved =
      editor.value.id && editor.value.version
        ? await updateRequirementTemplate(editor.value.id, {
            ...data,
            version: editor.value.version,
          })
        : await createRequirementTemplate(data);
    installTemplate(saved);
    message.success('模板已保存');
    await loadList();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '保存失败，请重试';
  } finally {
    saving.value = false;
  }
}

async function removeTemplate(item: RequirementTemplateSummary) {
  if (!writable.value || !(await discardChanges())) return;
  saving.value = true;
  try {
    await deleteRequirementTemplate(item.id, item.version);
    if (editor.value?.id === item.id) editor.value = undefined;
    message.success('模板已删除');
    await loadList();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '删除失败，请重试';
  } finally {
    saving.value = false;
  }
}

function removeAttachment(row: EditorRow, attachmentId: string) {
  if (!writable.value || busy.value) return;
  row.attachments = row.attachments.filter(
    (file) => file.attachment_id !== attachmentId,
  );
}

function removeRow(key: string) {
  if (!writable.value || busy.value || !editor.value) return;
  editor.value.requirements = editor.value.requirements.filter(
    (row) => row.key !== key,
  );
}

function beforeUpload(file: File, row: EditorRow) {
  if (!writable.value) return false;
  if (row.attachments.length + (pendingUploads.value[row.key] ?? 0) >= 5) {
    message.warning('每条子需求最多 5 个附件');
    return false;
  }
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!REQUIREMENT_TEMPLATE_ATTACHMENT_EXTS.includes(ext)) {
    message.error('不支持该附件格式');
    return false;
  }
  if (!file.size || file.size > 10 * 1024 ** 3) {
    message.error('附件不能为空，且单文件不能超过 10 GB');
    return false;
  }
  pendingUploads.value[row.key] = (pendingUploads.value[row.key] ?? 0) + 1;
  const controller = new AbortController();
  controllers.add(controller);
  void uploadRequirementTemplateAttachment(file, controller.signal)
    .then((uploaded) => {
      row.attachments.push(uploaded);
    })
    .catch((cause: unknown) => {
      if (!controller.signal.aborted)
        message.error(
          cause instanceof Error ? cause.message : `${file.name} 上传失败`,
        );
    })
    .finally(() => {
      pendingUploads.value[row.key] = Math.max(
        0,
        (pendingUploads.value[row.key] ?? 1) - 1,
      );
      controllers.delete(controller);
    });
  return false;
}

async function download(file: RequirementTemplateAttachment) {
  try {
    const result = await getRequirementTemplateAttachmentUrl(
      file.attachment_id,
    );
    downloadFileByUrl(result.url, result.name);
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : '附件下载失败');
  }
}

async function close() {
  if (await discardChanges()) emit('update:open', false);
}

async function switchMode(manage: boolean) {
  if (manage && (!props.canManage || !serverCanManage.value)) return;
  if (!(await discardChanges())) return;
  const selectedId = editor.value?.id;
  managing.value = manage;
  editor.value = undefined;
  const selected = items.value.find((item) => item.id === selectedId);
  if (selected) await selectTemplate(selected);
}

function apply(mode: 'append' | 'replace') {
  if (managing.value || busy.value || !editor.value?.id) return;
  // 仅复制内容快照；调用方为工单子需求分配新 ID，不能共享编辑引用。
  const rows = editor.value.requirements.map(({ key: _key, ...row }) => ({
    ...row,
    attachments: row.attachments.map((file) => ({ ...file })),
  }));
  emit('apply', rows, mode);
  emit('update:open', false);
}

function cancelUploads() {
  for (const controller of controllers) controller.abort();
}

function safeLink(value: string) {
  return /^https?:\/\//i.test(value) ? value : undefined;
}

watch(keyword, () => {
  clearTimeout(searchTimer);
  // 立即作废旧结果，避免防抖期间旧查询覆盖新关键词。
  ++requestSequence;
  searchTimer = setTimeout(() => {
    if (props.open) void loadList();
  }, 300);
});
watch(
  () => props.open,
  (open) => {
    ++selectionSequence;
    if (!open) {
      ++requestSequence;
      clearTimeout(searchTimer);
      return;
    }
    managing.value = props.mode === 'manage';
    serverCanManage.value = false;
    editor.value = undefined;
    keyword.value = '';
    items.value = [];
    nextCursor.value = null;
    original.value = '';
    void loadList();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  ++requestSequence;
  ++selectionSequence;
  clearTimeout(searchTimer);
  for (const controller of controllers) controller.abort();
});
</script>

<template>
  <Modal
    :open="open"
    wrap-class-name="ux-fixed-modal"
    :title="managing ? '管理子需求模板' : '使用子需求模板'"
    width="min(1360px, 96vw)"
    :mask-closable="false"
    :closable="!busy"
    :keyboard="!busy"
    :z-index="2200"
    @cancel="close"
  >
    <Alert v-if="error" class="mb-3" type="error" :message="error" show-icon>
      <template #action><Button @click="loadList()">重试列表</Button></template>
    </Alert>
    <Alert
      v-if="managing && !listLoading && !writable"
      type="warning"
      message="只有素材负责人可以管理子需求模板"
      show-icon
    />
    <div v-else class="grid min-h-0 gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside
        class="lg:border-border min-w-0 space-y-3 lg:border-r lg:pr-4"
        aria-label="模板列表"
      >
        <div class="template-search-controls">
          <Input
            v-model:value="keyword"
            class="min-w-0 flex-1"
            aria-label="搜索模板名称或说明"
            :placeholder="managing ? '搜索模板' : '搜索模板名称或说明'"
            :maxlength="100"
            allow-clear
          />
          <Button
            v-if="writable"
            type="primary"
            class="template-create-button"
            :disabled="busy"
            @click="createDraft"
          >
            <IconifyIcon
              icon="lucide:plus"
              class="size-3 shrink-0"
              aria-hidden="true"
            />
            <span>新建</span>
          </Button>
        </div>
        <Spin :spinning="listLoading">
          <div class="space-y-2">
            <div
              v-for="item in items"
              :key="item.id"
              class="flex items-end gap-2 rounded-md border p-3"
              :class="
                editor?.id === item.id
                  ? 'border-primary bg-accent'
                  : 'border-border bg-background'
              "
            >
              <button
                type="button"
                class="focus-visible:ring-ring min-w-0 flex-1 rounded text-left focus-visible:outline-none focus-visible:ring-2"
                :disabled="busy"
                :aria-pressed="editor?.id === item.id"
                @click="selectTemplate(item)"
              >
                <strong
                  class="block truncate font-medium leading-5"
                  :title="item.name"
                  >{{ item.name }}</strong
                >
                <span
                  class="text-muted-foreground mt-1 block h-6 truncate text-xs leading-6"
                  :title="item.description"
                  >{{ item.description }}</span
                >
              </button>
              <div v-if="writable" class="flex shrink-0 items-center gap-1">
                <Button
                  type="text"
                  :disabled="busy"
                  :aria-label="`复制模板 ${item.name}`"
                  @click="selectTemplate(item, true)"
                  ><IconifyIcon icon="lucide:copy"
                /></Button>
                <Popconfirm
                  title="删除此模板？已应用到工单的内容和附件会保留。"
                  :z-index="2300"
                  ok-text="删除"
                  cancel-text="取消"
                  @confirm="removeTemplate(item)"
                >
                  <Button
                    type="text"
                    danger
                    :disabled="busy"
                    :aria-label="`删除模板 ${item.name}`"
                    ><IconifyIcon icon="lucide:trash-2"
                  /></Button>
                </Popconfirm>
              </div>
            </div>
            <Empty
              v-if="!listLoading && !items.length"
              description="暂无模板"
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
            />
            <Button
              v-if="nextCursor"
              block
              :loading="listLoading"
              @click="loadList(true)"
              >加载更多</Button
            >
          </div>
        </Spin>
      </aside>
      <Spin :spinning="detailLoading" class="min-w-0">
        <div v-if="editor" class="min-w-0 space-y-4">
          <template v-if="writable">
            <div>
              <label
                class="mb-2 block font-medium"
                for="requirement-template-name"
                >模板名称 <span class="text-destructive">*</span></label
              ><Input
                id="requirement-template-name"
                v-model:value="editor.name"
                :maxlength="100"
                :disabled="saving"
                placeholder="请输入模板名称"
              />
            </div>
            <div>
              <label
                class="mb-2 block font-medium"
                for="requirement-template-description"
                >模板说明</label
              ><Input.TextArea
                id="requirement-template-description"
                v-model:value="editor.description"
                :maxlength="500"
                :auto-size="{ minRows: 2, maxRows: 5 }"
                :disabled="saving"
                placeholder="说明模板的适用场景"
              />
            </div>
          </template>
          <div v-else>
            <h3 class="text-base font-semibold">{{ editor.name }}</h3>
            <p
              class="text-muted-foreground mt-1 whitespace-pre-wrap break-words"
            >
              {{ editor.description }}
            </p>
          </div>
          <div class="flex items-center justify-between gap-3">
            <strong>模板子需求 {{ editor.requirements.length }} 条</strong
            ><Button
              v-if="writable"
              :disabled="busy || editor.requirements.length >= 100"
              @click="addRow"
              >新增子需求</Button
            >
          </div>
          <div class="border-border overflow-x-auto rounded-md border">
            <ShadcnDataTable
              :data="editor.requirements"
              :columns="columns"
              row-key="key"
              :paginate="false"
              empty-text="请新增子需求"
              class="template-requirements-table"
              aria-label="模板子需求明细"
            >
              <template #cell-description="{ record: row }">
                <ExpandableDescriptionInput
                  v-if="writable"
                  v-model:value="row.description"
                  :label="`子需求 ${rowNumbers.get(row.key)} 描述`"
                  :placement="rowEditorPlacement(row.key)"
                  :maxlength="5000"
                  :disabled="saving || !open"
                  :z-index="2250"
                />
                <span v-else class="whitespace-pre-wrap break-words">{{
                  row.description
                }}</span>
              </template>
              <template #cell-duration="{ record: row }">
                <Input
                  v-if="writable"
                  v-model:value="row.duration"
                  :aria-label="`子需求 ${rowNumbers.get(row.key)} 时长`"
                  :maxlength="100"
                  :disabled="saving"
                  placeholder="如 15 秒"
                />
                <span v-else>{{ row.duration || '—' }}</span>
              </template>
              <template #cell-quantity="{ record: row }">
                <InputNumber
                  v-if="writable"
                  v-model:value="row.quantity"
                  :aria-label="`子需求 ${rowNumbers.get(row.key)} 数量`"
                  :min="1"
                  :max="100000"
                  :precision="0"
                  :disabled="saving"
                  class="w-full"
                />
                <span v-else>{{ row.quantity }}</span>
              </template>
              <template #cell-link="{ record: row }">
                <ExpandableDescriptionInput
                  v-if="writable"
                  v-model:value="row.link"
                  :label="`子需求 ${rowNumbers.get(row.key)} 相关链接`"
                  :placement="rowEditorPlacement(row.key)"
                  :maxlength="2000"
                  :disabled="saving || !open"
                  :z-index="2250"
                />
                <a
                  v-else-if="safeLink(row.link)"
                  :href="safeLink(row.link)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-primary break-all underline"
                  >{{ row.link }}</a
                >
                <span v-else class="break-all">{{ row.link || '—' }}</span>
              </template>
              <template #cell-remark="{ record: row }">
                <ExpandableDescriptionInput
                  v-if="writable"
                  v-model:value="row.remark"
                  :label="`子需求 ${rowNumbers.get(row.key)} 备注`"
                  :placement="rowEditorPlacement(row.key)"
                  :maxlength="5000"
                  :disabled="saving || !open"
                  :z-index="2250"
                />
                <span v-else class="whitespace-pre-wrap break-words">{{
                  row.remark || '—'
                }}</span>
              </template>
              <template #cell-compliance="{ record: row }">
                <ExpandableDescriptionInput
                  v-if="writable"
                  v-model:value="row.compliance"
                  :label="`子需求 ${rowNumbers.get(row.key)} 合规要求`"
                  :placement="rowEditorPlacement(row.key)"
                  :maxlength="5000"
                  :disabled="saving || !open"
                  :z-index="2250"
                />
                <span v-else class="whitespace-pre-wrap break-words">{{
                  row.compliance || '—'
                }}</span>
              </template>
              <template #cell-attachments="{ record: row }">
                <ul class="m-0 list-none space-y-2 p-0">
                  <li
                    v-for="file in row.attachments"
                    :key="file.attachment_id"
                    class="flex items-start gap-1"
                  >
                    <button
                      type="button"
                      class="text-primary min-w-0 break-all text-left underline"
                      @click="download(file)"
                    >
                      {{ file.name }}
                    </button>
                    <Button
                      v-if="writable"
                      type="text"
                      danger
                      :disabled="busy"
                      :aria-label="`移除附件 ${file.name}`"
                      @click="removeAttachment(row, file.attachment_id)"
                      ><IconifyIcon icon="lucide:x"
                    /></Button>
                  </li>
                </ul>
                <Upload
                  v-if="writable"
                  :accept="accept"
                  :multiple="true"
                  :show-upload-list="false"
                  :before-upload="(file) => beforeUpload(file, row)"
                >
                  <Button
                    class="mt-2"
                    :disabled="
                      saving ||
                      row.attachments.length + (pendingUploads[row.key] ?? 0) >=
                        5
                    "
                    :loading="(pendingUploads[row.key] ?? 0) > 0"
                    >上传附件</Button
                  >
                </Upload>
                <span
                  v-if="!writable && !row.attachments.length"
                  class="text-muted-foreground"
                  >—</span
                >
              </template>
              <template #cell-actions="{ record: row }">
                <Popconfirm
                  title="移除此条子需求？"
                  :z-index="2300"
                  ok-text="移除"
                  cancel-text="取消"
                  @confirm="removeRow(row.key)"
                >
                  <Button
                    type="text"
                    danger
                    :disabled="busy"
                    :aria-label="`移除子需求 ${rowNumbers.get(row.key)}`"
                    ><IconifyIcon icon="lucide:trash-2"
                  /></Button>
                </Popconfirm>
              </template>
            </ShadcnDataTable>
          </div>
          <p v-if="writable" class="text-muted-foreground text-xs">
            每条子需求最多 5 个附件，单文件不超过 10
            GB。支持图片（PNG/JPG/JPEG/GIF）、视频（MP4/MOV）和 ZIP/7Z。
          </p>
        </div>
        <Empty
          v-else
          class="py-12"
          description="选择一个模板查看子需求明细"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />
      </Spin>
    </div>
    <template #footer>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Button
            v-if="!managing && canManage && serverCanManage"
            type="text"
            class="template-manager-link"
            :disabled="busy"
            @click="switchMode(true)"
          >
            <IconifyIcon
              icon="lucide:sliders-horizontal"
              class="size-3 shrink-0"
              aria-hidden="true"
            />
            <span>管理模板</span> </Button
          ><Button
            v-else-if="managing && mode === 'use'"
            type="text"
            :disabled="busy"
            @click="switchMode(false)"
            >返回使用模板</Button
          >
        </div>
        <div class="flex flex-wrap justify-end gap-2">
          <Button v-if="uploadCount > 0" @click="cancelUploads"
            >取消上传</Button
          >
          <Button :disabled="busy" @click="close">取消</Button
          ><Button
            v-if="writable"
            type="primary"
            :loading="saving"
            :disabled="!editor || uploadCount > 0 || detailLoading"
            @click="save"
            >保存模板</Button
          ><template v-else-if="!managing"
            ><Button
              type="primary"
              :disabled="!editor?.id || busy"
              @click="apply('append')"
              >追加至明细</Button
            ><Button
              danger
              :disabled="!editor?.id || busy"
              @click="apply('replace')"
              >替换全部明细</Button
            ></template
          >
        </div>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.template-search-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.template-create-button,
.template-manager-link {
  display: inline-flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: center;
  white-space: nowrap;
}

.template-manager-link {
  font-size: 12px;
}

.template-manager-link:not(:disabled) {
  color: var(--adpulse-text-muted);
}

/* 列宽按可用区域分配；仅窄屏保留表格内横向滚动，展开编辑不会撑宽列。 */
.template-requirements-table :deep(table) {
  min-width: 920px;
  table-layout: fixed;
}
</style>
