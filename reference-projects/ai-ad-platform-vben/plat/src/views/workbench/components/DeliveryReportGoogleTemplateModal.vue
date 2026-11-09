<script setup lang="ts">
import type {
  DeliveryGoogleFieldDefinition,
  DeliveryGoogleDriveFile,
  DeliveryGoogleProjectTarget,
  DeliveryGoogleSheetTab,
  DeliveryGoogleTemplate,
  DeliveryGoogleTemplatePayload,
} from '#/api/delivery-report';

import { computed, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Spin,
  Switch,
  message,
} from 'ant-design-vue';

import { deliveryReportApi } from '#/api/delivery-report';

interface TemplateForm {
  enableFlag: number;
  headerRow: number;
  projectId: string;
  sheetId: string;
  spreadsheetId: string;
  templateName: string;
}

interface MappingRow {
  key: number;
  systemField?: string;
  targetColumn?: string;
  uniqueKey: boolean;
}

const emit = defineEmits<{ changed: [] }>();
const open = ref(false);
const loading = ref(false);
const saving = ref(false);
const targetLoading = ref(false);
const templates = ref<DeliveryGoogleTemplate[]>([]);
const fields = ref<DeliveryGoogleFieldDefinition[]>([]);
const serviceAccountEmail = ref('');
const files = ref<DeliveryGoogleDriveFile[]>([]);
const sheets = ref<DeliveryGoogleSheetTab[]>([]);
const columns = ref<string[]>([]);
const projects = ref<Array<{ label: string; value: string }>>([]);
const selectedTemplateId = ref<string>();
const creating = ref(false);
const mappingRows = ref<MappingRow[]>([]);
let mappingRowKey = 0;
const form = reactive<TemplateForm>({
  enableFlag: 1,
  headerRow: 1,
  projectId: '',
  sheetId: '',
  spreadsheetId: '',
  templateName: '',
});

const selectedFile = computed(() =>
  files.value.find((file) => file.id === form.spreadsheetId),
);
const selectedSheet = computed(() =>
  sheets.value.find((sheet) => sheet.id === form.sheetId),
);
const editorVisible = computed(
  () => creating.value || Boolean(selectedTemplateId.value),
);
const columnOptions = computed(() =>
  columns.value.map((header, index) => ({
    label: `${columnName(index + 1)} · ${header || '未命名列'}`,
    value: columnName(index + 1),
  })),
);
const configuredProjectIds = computed(
  () => new Set(templates.value.map((template) => template.projectId)),
);
const projectOptions = computed(() =>
  projects.value.map((project) => ({
    ...project,
    disabled:
      configuredProjectIds.value.has(project.value) &&
      templates.value.find((item) => item.projectId === project.value)?.id !==
        selectedTemplateId.value,
  })),
);

/** 打开模板管理并刷新服务端配置与Google账号。 */
async function show() {
  open.value = true;
  loading.value = true;
  try {
    const [templateList, fieldList, serviceAccount, projectList] =
      await Promise.all([
        deliveryReportApi.googleTemplates(),
        deliveryReportApi.googleFields(),
        deliveryReportApi.googleServiceAccount(),
        deliveryReportApi.options(),
      ]);
    templates.value = templateList;
    fields.value = fieldList;
    serviceAccountEmail.value = serviceAccount.email;
    projects.value = [
      ...new Map(
        projectList.map((line) => [
          line.projectId,
          { label: line.projectName, value: line.projectId },
        ]),
      ).values(),
    ];
    clearEditor();
  } catch {
    open.value = false;
  } finally {
    loading.value = false;
  }
}

function resetTargets() {
  files.value = [];
  sheets.value = [];
  columns.value = [];
  form.spreadsheetId = '';
  form.sheetId = '';
}

function createTemplate() {
  if (creating.value) return;
  creating.value = true;
  selectedTemplateId.value = undefined;
  Object.assign(form, {
    enableFlag: 1,
    headerRow: 1,
    projectId: '',
    sheetId: '',
    spreadsheetId: '',
    templateName: '',
  });
  resetMappingRows();
  resetTargets();
}

function clearEditor() {
  creating.value = false;
  selectedTemplateId.value = undefined;
  Object.assign(form, {
    enableFlag: 1,
    headerRow: 1,
    projectId: '',
    sheetId: '',
    spreadsheetId: '',
    templateName: '',
  });
  mappingRows.value = [];
  resetTargets();
}

async function selectTemplate(template: DeliveryGoogleTemplate) {
  creating.value = false;
  selectedTemplateId.value = template.id;
  if (!projects.value.some((project) => project.value === template.projectId)) {
    projects.value.unshift({
      label: template.projectName,
      value: template.projectId,
    });
  }
  resetTargets();
  Object.assign(form, {
    enableFlag: template.enableFlag,
    headerRow: template.headerRow,
    projectId: template.projectId,
    sheetId: '',
    spreadsheetId: '',
    templateName: template.templateName,
  });
  resetMappingRows(template.fieldMappings);
  targetLoading.value = true;
  try {
    const target = await deliveryReportApi.googleProjectTarget(
      template.projectId,
    );
    await applyProjectTarget(target);
  } finally {
    targetLoading.value = false;
  }
}

async function applyProjectTarget(target: DeliveryGoogleProjectTarget) {
  const spreadsheet = target.spreadsheet;
  const sheet = target.sheets.find((item) => item.id === target.sheetId);
  if (!target.configured || !spreadsheet || !sheet) {
    message.error(
      target.message || '无法根据项目日报链接确定Google表格和目标页签',
    );
    return false;
  }
  files.value = [spreadsheet];
  sheets.value = [sheet];
  form.spreadsheetId = spreadsheet.id;
  form.sheetId = sheet.id;
  columns.value = await deliveryReportApi.googleColumns(
    spreadsheet.id,
    sheet.title,
    form.headerRow,
  );
  autoMatchColumns();
  return true;
}

async function handleProjectChange() {
  const project = projects.value.find((item) => item.value === form.projectId);
  form.templateName = project ? `${project.label}-表格模板` : '';
  form.spreadsheetId = '';
  form.sheetId = '';
  sheets.value = [];
  columns.value = [];
  clearTargetColumns();
  if (!form.projectId) return;
  targetLoading.value = true;
  try {
    const target = await deliveryReportApi.googleProjectTarget(form.projectId);
    if (await applyProjectTarget(target)) message.success(target.message);
  } finally {
    targetLoading.value = false;
  }
}

async function loadColumns() {
  columns.value = [];
  clearTargetColumns();
  if (!selectedSheet.value || !form.headerRow) return;
  targetLoading.value = true;
  try {
    columns.value = await deliveryReportApi.googleColumns(
      form.spreadsheetId,
      selectedSheet.value.title,
      form.headerRow,
    );
    autoMatchColumns();
  } finally {
    targetLoading.value = false;
  }
}

async function handleHeaderRowChange() {
  await loadColumns();
}

function autoMatchColumns() {
  mappingRows.value.forEach((row) => {
    if (!row.systemField || row.targetColumn) return;
    const field = fields.value.find((item) => item.field === row.systemField);
    if (!field) return;
    const index = columns.value.findIndex(
      (header) => header.trim() === field.label,
    );
    const targetColumn = index >= 0 ? columnName(index + 1) : undefined;
    if (
      targetColumn &&
      !mappingRows.value.some(
        (item) => item.key !== row.key && item.targetColumn === targetColumn,
      )
    ) {
      row.targetColumn = targetColumn;
    }
  });
}

function newMappingRow(
  systemField?: string,
  targetColumn?: string,
  uniqueKey = false,
): MappingRow {
  return { key: ++mappingRowKey, systemField, targetColumn, uniqueKey };
}

function resetMappingRows(
  mappings: DeliveryGoogleTemplate['fieldMappings'] = [],
) {
  mappingRows.value = mappings.length
    ? mappings.map((mapping) =>
        newMappingRow(
          mapping.systemField,
          mapping.targetColumn,
          mapping.uniqueKey,
        ),
      )
    : [newMappingRow()];
}

function addMappingRow() {
  mappingRows.value.push(newMappingRow());
}

function removeMappingRow(key: number) {
  if (mappingRows.value.length === 1) {
    mappingRows.value = [newMappingRow()];
    return;
  }
  mappingRows.value = mappingRows.value.filter((row) => row.key !== key);
}

function clearTargetColumns() {
  mappingRows.value.forEach((row) => {
    row.targetColumn = undefined;
  });
}

function selectedField(row: MappingRow) {
  return fields.value.find((field) => field.field === row.systemField);
}

function fieldOptions(row: MappingRow) {
  const selected = new Set(
    mappingRows.value
      .filter((item) => item.key !== row.key)
      .map((item) => item.systemField)
      .filter((value): value is string => Boolean(value)),
  );
  return fields.value.map((field) => ({
    disabled: selected.has(field.field),
    label: `${field.label} · ${field.field}`,
    value: field.field,
  }));
}

function targetColumnOptions(row: MappingRow) {
  const selected = new Set(
    mappingRows.value
      .filter((item) => item.key !== row.key)
      .map((item) => item.targetColumn)
      .filter((value): value is string => Boolean(value)),
  );
  return columnOptions.value.map((option) => ({
    ...option,
    disabled: selected.has(option.value),
  }));
}

function handleSystemFieldChange(row: MappingRow) {
  row.targetColumn = undefined;
  if (!row.systemField) row.uniqueKey = false;
  autoMatchColumns();
}

function handleTargetColumnChange(row: MappingRow) {
  if (!row.targetColumn) row.uniqueKey = false;
}

function handleEnableChange(checked: boolean) {
  form.enableFlag = checked ? 1 : 0;
}

async function save() {
  if (!editorVisible.value) return;
  if (
    !form.projectId ||
    !form.templateName.trim() ||
    !form.headerRow ||
    !selectedFile.value ||
    !selectedSheet.value
  ) {
    message.warning(
      '请完整填写模板名称和表头行，并确保日报链接可确定表格和页签',
    );
    return;
  }
  const incompleteRow = mappingRows.value.find(
    (row) => Boolean(row.systemField) !== Boolean(row.targetColumn),
  );
  if (incompleteRow) {
    message.warning('请完整选择每一行的投放日报字段和Google目标列');
    return;
  }
  const configuredRows = mappingRows.value.filter(
    (row) => row.systemField && row.targetColumn,
  );
  if (configuredRows.length === 0) {
    message.warning('请至少配置一个投放日报字段映射');
    return;
  }
  if (!configuredRows.some((row) => row.uniqueKey)) {
    message.warning('请至少选择一个字段作为唯一值');
    return;
  }
  const fieldMappings = configuredRows.map((row) => {
    const field = selectedField(row)!;
    const targetColumn = row.targetColumn!;
    return {
      required: field.required,
      systemField: field.field,
      targetColumn,
      targetHeader: columns.value[columnIndex(targetColumn) - 1] || field.label,
      uniqueKey: row.uniqueKey,
    };
  });
  const payload: DeliveryGoogleTemplatePayload = {
    enableFlag: form.enableFlag,
    fieldMappings,
    headerRow: form.headerRow,
    projectId: form.projectId,
    templateName: form.templateName.trim(),
  };
  saving.value = true;
  try {
    if (selectedTemplateId.value) {
      await deliveryReportApi.updateGoogleTemplate(
        selectedTemplateId.value,
        payload,
      );
    } else {
      selectedTemplateId.value =
        await deliveryReportApi.createGoogleTemplate(payload);
    }
    templates.value = await deliveryReportApi.googleTemplates();
    const saved = templates.value.find(
      (template) => template.id === selectedTemplateId.value,
    );
    if (saved) await selectTemplate(saved);
    emit('changed');
    message.success('项目日报模板已保存');
  } finally {
    saving.value = false;
  }
}

function removeTemplate() {
  if (!selectedTemplateId.value) return;
  const id = selectedTemplateId.value;
  Modal.confirm({
    content: '删除后该项目将无法推送日报，历史推送日志不会删除。',
    okButtonProps: { danger: true },
    okText: '删除',
    title: '确认删除项目日报模板？',
    async onOk() {
      await deliveryReportApi.deleteGoogleTemplate(id);
      templates.value = await deliveryReportApi.googleTemplates();
      clearEditor();
      emit('changed');
      message.success('项目日报模板已删除');
    },
  });
}

function columnName(index: number) {
  let value = '';
  for (
    let current = index;
    current > 0;
    current = Math.floor((current - 1) / 26)
  ) {
    value = String.fromCharCode(65 + ((current - 1) % 26)) + value;
  }
  return value;
}

function columnIndex(column: string) {
  return [...column].reduce(
    (value, character) => value * 26 + character.charCodeAt(0) - 64,
    0,
  );
}

defineExpose({ show });
</script>

<template>
  <Modal
    v-model:open="open"
    :footer="null"
    :width="1180"
    destroy-on-close
    title="项目日报写入模板"
    wrap-class-name="ux-fixed-modal ux-modal-workspace-shell"
  >
    <div class="template-modal-workspace">
      <Spin :spinning="loading" class="w-full">
        <div class="template-layout">
          <aside class="template-list">
            <div class="flex items-center justify-between gap-2">
              <div>
                <strong>{{ templates.length }} 个模板</strong>
                <p class="text-muted-foreground mb-0 mt-1 text-xs">
                  一个项目只能配置一个模板
                </p>
              </div>
              <Button type="primary" @click="createTemplate">
                <IconifyIcon icon="lucide:plus" class="mr-1" />新建
              </Button>
            </div>
            <div class="template-list-scroll mt-4">
              <button
                v-for="template in templates"
                :key="template.id"
                class="template-item"
                :class="{
                  'template-item-active': template.id === selectedTemplateId,
                }"
                type="button"
                @click="selectTemplate(template)"
              >
                <strong>{{ template.templateName }}</strong>
                <span>{{ template.projectName }}</span>
                <small
                  >{{ template.spreadsheetName }} · {{ template.sheetTitle }} ·
                  第{{ template.headerRow }}行表头</small
                >
              </button>
              <button
                v-if="creating"
                class="template-item template-item-active"
                type="button"
              >
                <strong>新建模板</strong>
                <span>尚未保存</span>
              </button>
              <Empty
                v-if="templates.length === 0 && !creating"
                description="暂无模板"
              />
            </div>
          </aside>

          <section v-if="editorVisible" class="template-editor min-w-0">
            <div
              class="editor-header flex flex-wrap items-start justify-between gap-3"
            >
              <div>
                <h3 class="m-0 text-base font-semibold">
                  {{ selectedTemplateId ? '编辑模板' : '新建模板' }}
                </h3>
                <p class="text-muted-foreground mb-0 mt-1 text-sm">
                  目标表格和页签由项目日报链接唯一确定，请指定表头行并建立字段映射。
                </p>
              </div>
              <div class="flex gap-2">
                <Button
                  v-if="selectedTemplateId"
                  danger
                  :disabled="saving"
                  @click="removeTemplate"
                  >删除</Button
                >
                <Button
                  type="primary"
                  :disabled="!form.spreadsheetId || !form.sheetId"
                  :loading="saving"
                  @click="save"
                  >保存模板</Button
                >
              </div>
            </div>

            <Alert
              class="mt-4"
              show-icon
              type="info"
              :message="`请将目标表格以编辑者身份共享给服务账户 ${serviceAccountEmail}。请在字段映射中选择一列或多列作为联合唯一值，系统将据此匹配并更新原行。`"
            />

            <div class="form-grid mt-4">
              <label class="form-field"
                ><span class="form-label">适用项目</span
                ><Select
                  v-model:value="form.projectId"
                  class="w-full"
                  :options="projectOptions"
                  placeholder="请选择已关联代理线的项目"
                  show-search
                  option-filter-prop="label"
                  @change="handleProjectChange"
              /></label>
              <label class="form-field"
                ><span class="form-label">模板名称</span
                ><Input v-model:value="form.templateName"
              /></label>
              <label class="form-field"
                ><span class="form-label">Google表格</span
                ><Input
                  class="w-full"
                  placeholder="选择项目后根据日报链接自动确定"
                  readonly
                  :value="selectedFile?.name"
              /></label>
              <label class="form-field"
                ><span class="form-label">目标页签</span
                ><Input
                  class="w-full"
                  placeholder="选择项目后根据日报链接自动确定"
                  readonly
                  :value="selectedSheet?.title"
              /></label>
              <label class="form-field"
                ><span class="form-label">表头所在行</span
                ><InputNumber
                  v-model:value="form.headerRow"
                  class="w-full"
                  :min="1"
                  :max="100"
                  :precision="0"
                  placeholder="请输入表头行号"
                  @change="handleHeaderRowChange"
              /></label>
              <label class="form-field"
                ><span class="form-label">模板状态</span
                ><span class="status-control"
                  ><Switch
                    class="status-switch"
                    :checked="form.enableFlag === 1"
                    aria-label="模板状态"
                    @change="handleEnableChange"
                  /><span class="status-text">{{
                    form.enableFlag === 1 ? '启用' : '停用'
                  }}</span></span
                ></label
              >
            </div>

            <div class="mapping-spin">
              <Spin :spinning="targetLoading">
                <div class="mapping-toolbar mt-4">
                  <div>
                    <strong>字段映射</strong>
                    <span>按需添加字段，并勾选一列或多列作为联合唯一值</span>
                  </div>
                  <Button
                    :disabled="mappingRows.length >= fields.length"
                    @click="addMappingRow"
                  >
                    <IconifyIcon icon="lucide:plus" class="mr-1" />添加一行
                  </Button>
                </div>
                <div class="mapping-table mt-4">
                  <div class="mapping-header">
                    <span>投放日报字段</span><span>Google目标列</span
                    ><span>唯一值</span><span>操作</span>
                  </div>
                  <div
                    v-for="row in mappingRows"
                    :key="row.key"
                    class="mapping-row"
                  >
                    <Select
                      v-model:value="row.systemField"
                      allow-clear
                      class="w-full"
                      :options="fieldOptions(row)"
                      placeholder="请选择日报字段"
                      show-search
                      option-filter-prop="label"
                      @change="handleSystemFieldChange(row)"
                    />
                    <Select
                      v-model:value="row.targetColumn"
                      allow-clear
                      class="w-full"
                      :disabled="columns.length === 0"
                      :options="targetColumnOptions(row)"
                      :placeholder="
                        columns.length === 0 ? '请先选择目标页签' : '不写入'
                      "
                      show-search
                      option-filter-prop="label"
                      @change="handleTargetColumnChange(row)"
                    />
                    <Checkbox
                      v-model:checked="row.uniqueKey"
                      :disabled="!row.systemField || !row.targetColumn"
                    >
                      用于匹配
                    </Checkbox>
                    <Button
                      danger
                      type="link"
                      @click="removeMappingRow(row.key)"
                    >
                      移除
                    </Button>
                  </div>
                </div>
              </Spin>
            </div>
          </section>
          <section v-else class="editor-empty">
            <Empty description="请选择左侧模板，或点击“新建”创建模板" />
          </section>
        </div>
      </Spin>
    </div>
  </Modal>
</template>

<style scoped>
.template-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.template-modal-workspace {
  height: 100%;
  min-height: 0;
}

.template-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px;
  background: hsl(var(--muted) / 35%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.template-list-scroll {
  display: flex;
  flex: 1 1 0%;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow: hidden auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
}

.template-item {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 12px;
  text-align: left;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.template-item:hover,
.template-item-active {
  background: hsl(var(--accent));
}

.template-item span,
.template-item small {
  color: hsl(var(--muted-foreground));
}

.editor-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.form-field {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.form-label {
  text-align: right;
  white-space: nowrap;
}

.status-control {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-start;
}

.status-switch {
  width: 44px;
  min-width: 44px;
}

.status-text {
  color: hsl(var(--foreground));
}

.mapping-table {
  flex: 1 1 0%;
  min-height: min(var(--adpulse-table-body-min-height), 30vh);
  overflow: auto;
  scrollbar-width: thin;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  isolation: isolate;
}

.template-editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.mapping-spin {
  display: flex;
  flex: 1 1 0%;
  flex-direction: column;
  min-height: 0;
}

.mapping-toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.mapping-toolbar div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mapping-toolbar span {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.mapping-header,
.mapping-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(260px, 1.2fr) 64px 52px;
  gap: 16px;
  align-items: center;
  min-width: 700px;
  min-height: var(--adpulse-table-row-height);
  padding: var(--adpulse-table-cell-padding-block)
    var(--adpulse-table-cell-padding-inline);
  border-bottom: 1px solid hsl(var(--border));
}

.mapping-header {
  position: sticky;
  top: 0;
  z-index: 2;
  min-height: var(--adpulse-table-header-height);
  font-weight: 600;
  background: hsl(var(--muted));
}

.mapping-row:last-child {
  border-bottom: 0;
}

@media (max-width: 768px) {
  .template-layout {
    grid-template-rows: minmax(176px, 32%) minmax(0, 1fr);
    grid-template-columns: 1fr;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }

  .template-list {
    max-height: none;
  }

  .template-editor {
    overflow-y: auto;
    scrollbar-width: thin;
  }

  .editor-header {
    position: sticky;
    top: 0;
    z-index: 2;
    padding-bottom: var(--adpulse-content-gap);
    background: var(--ant-color-bg-elevated);
  }

  .form-field {
    grid-template-columns: 1fr;
  }

  .form-label {
    text-align: left;
  }

  .mapping-spin {
    flex: none;
  }

  .mapping-table {
    max-height: min(var(--adpulse-popup-table-height), 48vh);
  }
}
</style>
