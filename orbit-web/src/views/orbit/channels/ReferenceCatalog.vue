<template>
  <div class="app-container reference-page">
    <el-card shadow="never">
      <template #header
        ><div class="toolbar">
          <strong>字典与引用资料</strong>
          <div>
            <el-button @click="downloadTemplate">下载当前类别模板</el-button
            ><el-button type="primary" @click="startImport">导入预检</el-button>
          </div>
        </div></template
      >
      <el-alert
        title="维护户商引用资料；预检不会写入目录，审核差异后再原子提交。失效资料保留历史显示。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-form inline>
        <el-form-item label="类别"
          ><el-select v-model="kind" class="filter" @change="reload"
            ><el-option
              v-for="(label, value) in labels"
              :key="value"
              :label="label"
              :value="value" /></el-select
        ></el-form-item>
        <el-form-item><el-button :loading="loading" @click="reload">刷新</el-button></el-form-item>
      </el-form>
      <el-table
        v-loading="loading"
        :data="items"
        border
        empty-text="暂无可见户商资料；可通过导入预检创建"
      >
        <el-table-column prop="value.id" label="稳定UUID" min-width="290" />
        <el-table-column prop="value.name" label="名称" min-width="180" />
        <el-table-column prop="value.source_key" label="来源键" min-width="180" />
        <el-table-column label="可用状态" width="120"
          ><template #default="{ row }"
            ><el-tag :type="row.value.availability === 'AVAILABLE' ? 'success' : 'info'">{{
              row.value.availability === 'AVAILABLE' ? '可新增引用' : '已失效'
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column prop="value.owner_team_id" label="归属团队UUID" min-width="290" />
        <el-table-column label="拥有者UUID" min-width="300"
          ><template #default="{ row }">{{
            row.value.data_owner_user_ids.join('、')
          }}</template></el-table-column
        >
        <el-table-column prop="revision" label="资料版本" width="100" /><el-table-column
          prop="catalog_revision"
          label="目录版本"
          width="100"
        /><el-table-column prop="updated_at" label="更新UTC时间" min-width="200" />
      </el-table>
      <VendorAliases v-if="kind === 'VENDOR'" :vendors="items" @changed="reload" />
      <div class="toolbar pager">
        <span>当前目录版本 {{ catalogRevision }} · 第 {{ page + 1 }} 页</span
        ><el-select v-model="pageSize" class="size" aria-label="每页数量" @change="reload"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="`${size} 条/页`"
            :value="size" /></el-select
        ><el-button :disabled="!page || loading" @click="previous">上一页</el-button
        ><el-button :disabled="!nextCursor || loading" @click="next">下一页</el-button>
      </div>
    </el-card>

    <el-dialog
      v-model="importOpen"
      title="引用资料导入预检"
      width="880px"
      class="reference-dialog"
      :close-on-click-modal="false"
    >
      <el-alert v-if="importError" :title="importError" type="error" :closable="false" show-icon />
      <el-alert
        v-if="preview?.state === 'COMMITTED'"
        title="目录已原子提交成功；本次导入未出现的资料保持原样，历史快照未回写。"
        type="success"
        :closable="false"
      />
      <el-form label-position="top" :disabled="busy || !!preview || uncertain">
        <div class="grid">
          <el-form-item label="类别"
            ><el-select v-model="importKind"
              ><el-option
                v-for="(label, value) in labels"
                :key="value"
                :label="label"
                :value="value" /></el-select></el-form-item
          ><el-form-item label="来源（必填，可追溯）"
            ><el-input v-model="source" maxlength="255"
          /></el-form-item>
        </div>
        <el-form-item label="导入原因（必填）"
          ><el-input v-model="reason" type="textarea" :rows="2" maxlength="1000" show-word-limit
        /></el-form-item>
        <el-form-item label="JSON资料数组（1—500行，总正文不超过2MiB）"
          ><el-input
            v-model="jsonText"
            type="textarea"
            :rows="9"
            placeholder="粘贴模板中的资料数组，替换稳定UUID、真实团队及拥有者；不要按名称重建已有资料"
        /></el-form-item>
        <label class="file-input"
          >从JSON文件读取：<input
            type="file"
            accept=".json,application/json"
            :disabled="busy || !!preview || uncertain"
            @change="readFile"
        /></label>
      </el-form>
      <template v-if="preview">
        <el-descriptions :column="2" border
          ><el-descriptions-item label="预览状态">{{ states[preview.state] }}</el-descriptions-item
          ><el-descriptions-item label="基础目录版本">{{
            preview.base_catalog_revision
          }}</el-descriptions-item
          ><el-descriptions-item label="预计新增 / 更新"
            >{{ preview.created_count }} / {{ preview.updated_count }}</el-descriptions-item
          ><el-descriptions-item label="到期UTC时间">{{
            preview.expires_at
          }}</el-descriptions-item></el-descriptions
        >
        <h3>逐行问题</h3>
        <el-table :data="preview.issues" border empty-text="未发现行错误"
          ><el-table-column label="行号" width="80"
            ><template #default="{ row }">{{ row.row + 1 }}</template></el-table-column
          ><el-table-column prop="code" label="错误代码" min-width="180" /><el-table-column
            prop="message"
            label="问题说明"
            min-width="260"
        /></el-table>
        <h3>本次变更差异</h3>
        <el-alert
          v-if="differenceError"
          :title="differenceError"
          type="error"
          :closable="false"
        /><el-table :data="differences" border empty-text="暂无可提交差异"
          ><el-table-column label="行号" width="80"
            ><template #default="{ row }">{{ row.row + 1 }}</template></el-table-column
          ><el-table-column label="动作" width="90"
            ><template #default="{ row }">{{
              row.action === 'CREATE' ? '新增' : '更新'
            }}</template></el-table-column
          ><el-table-column prop="id" label="UUID" min-width="280" /><el-table-column
            label="变更前"
            min-width="300"
            ><template #default="{ row }">
              <pre>{{ row.before ? JSON.stringify(row.before, null, 2) : '无' }}</pre>
            </template></el-table-column
          ><el-table-column label="变更后" min-width="300"
            ><template #default="{ row }">
              <pre>{{ JSON.stringify(row.after, null, 2) }}</pre>
            </template></el-table-column
          ></el-table
        >
      </template>
      <template #footer
        ><el-button :disabled="busy" @click="importOpen = false">关闭</el-button
        ><el-button
          v-if="preview && preview.state !== 'COMMITTED'"
          :disabled="busy || uncertain"
          @click="editAgain"
          >修改后重新预检</el-button
        ><el-button v-if="!preview" type="primary" :loading="busy" @click="precheck">{{
          uncertain ? '重试本次预检' : '开始预检'
        }}</el-button
        ><el-button
          v-if="preview?.state === 'VALIDATED'"
          type="primary"
          :loading="busy"
          :disabled="!!differenceError || !differences.length"
          @click="commit"
          >{{ uncertain ? '重试本次提交' : '确认差异并原子提交' }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import VendorAliases from './VendorAliases.vue'
import { onMounted, ref } from 'vue'
import {
  referenceApi,
  ReferenceApiError,
  type ReferenceKind,
  type ReferenceRecord,
  type ReferenceResult,
  type ReferenceImportInput,
  type ReferenceDifference,
} from '@/api/orbit/references'
const labels = { VENDOR: '户商' }
const states = {
  VALIDATED: '预检通过，尚未提交',
  REJECTED: '预检拒绝，请修正问题',
  COMMITTED: '已提交',
  EXPIRED: '已过期，请重新预检',
}
const kind = ref<ReferenceKind>('VENDOR'),
  importKind = ref<ReferenceKind>('VENDOR'),
  items = ref<ReferenceRecord[]>([])
const loading = ref(false),
  busy = ref(false),
  error = ref(''),
  importError = ref(''),
  differenceError = ref(''),
  importOpen = ref(false),
  uncertain = ref(false)
const pageSize = ref(50),
  page = ref(0),
  cursors = ref<(string | null)[]>([null]),
  nextCursor = ref<string | null>(null)
const catalogRevision = ref(0),
  csrf = ref(''),
  source = ref(''),
  reason = ref(''),
  jsonText = ref(''),
  preview = ref<ReferenceResult>(),
  differences = ref<ReferenceDifference[]>([])
let previewKey = '',
  commitKey = '',
  frozenInput: ReferenceImportInput | undefined
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '请求失败，请重试')
const unknown = (cause: unknown) =>
  cause instanceof ReferenceApiError && (cause.status === 0 || cause.status >= 500)
async function load() {
  loading.value = true
  error.value = ''
  try {
    const caps = await referenceApi.capabilities()
    catalogRevision.value = caps.catalog_revision
    csrf.value = caps.csrf_token
    const query = new URLSearchParams({ page_size: String(pageSize.value) })
    if (cursors.value[page.value]) query.set('cursor', cursors.value[page.value]!)
    const result = await referenceApi.list(kind.value, query)
    items.value = result.items
    nextCursor.value = result.next_cursor
    catalogRevision.value = result.catalog_revision
  } catch (cause) {
    error.value = message(cause)
    if (cause instanceof ReferenceApiError && cause.status === 409) {
      page.value = 0
      cursors.value = [null]
      nextCursor.value = null
    }
  } finally {
    loading.value = false
  }
}
async function reload() {
  page.value = 0
  cursors.value = [null]
  await load()
}
async function next() {
  if (!nextCursor.value) return
  cursors.value.push(nextCursor.value)
  page.value++
  await load()
}
async function previous() {
  if (!page.value) return
  page.value--
  cursors.value = cursors.value.slice(0, page.value + 1)
  await load()
}
function startImport() {
  importKind.value = kind.value
  source.value = ''
  reason.value = ''
  jsonText.value = ''
  preview.value = undefined
  differences.value = []
  importError.value = ''
  differenceError.value = ''
  frozenInput = undefined
  previewKey = ''
  commitKey = ''
  uncertain.value = false
  importOpen.value = true
}
function editAgain() {
  preview.value = undefined
  differences.value = []
  frozenInput = undefined
  previewKey = ''
  commitKey = ''
  importError.value = ''
  differenceError.value = ''
  uncertain.value = false
}
async function readFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 2 * 1024 * 1024) {
    importError.value = '文件超过2MiB，请拆分后导入'
    return
  }
  jsonText.value = await file.text()
  ;(event.target as HTMLInputElement).value = ''
}
async function precheck() {
  if (busy.value) return
  busy.value = true
  importError.value = ''
  try {
    if (!uncertain.value || !frozenInput) {
      const values = JSON.parse(jsonText.value)
      if (!Array.isArray(values) || values.length < 1 || values.length > 500)
        throw new Error('JSON必须为1至500项资料数组')
      if (!source.value.trim() || !reason.value.trim()) throw new Error('请填写来源及导入原因')
      const caps = await referenceApi.capabilities()
      csrf.value = caps.csrf_token
      catalogRevision.value = caps.catalog_revision
      frozenInput = {
        kind: importKind.value,
        source: source.value,
        reason: reason.value,
        base_catalog_revision: catalogRevision.value,
        items: values,
      }
      if (new TextEncoder().encode(JSON.stringify(frozenInput)).length > 2 * 1024 * 1024)
        throw new Error('完整导入正文超过2MiB')
      previewKey = crypto.randomUUID()
    }
    preview.value = await referenceApi.preview(frozenInput!, csrf.value, previewKey)
    uncertain.value = false
    await loadDifferences()
  } catch (cause) {
    importError.value = message(cause)
    uncertain.value = unknown(cause)
  } finally {
    busy.value = false
  }
}
async function loadDifferences() {
  if (!preview.value) return
  try {
    differences.value = (await referenceApi.differences(preview.value.id)).items
    differenceError.value = ''
  } catch (cause) {
    differenceError.value = message(cause)
  }
}
async function commit() {
  if (!preview.value || busy.value) return
  busy.value = true
  importError.value = ''
  commitKey ||= crypto.randomUUID()
  try {
    preview.value = await referenceApi.commit(preview.value, csrf.value, commitKey)
    uncertain.value = false
    await reload()
  } catch (cause) {
    importError.value = message(cause)
    uncertain.value = unknown(cause)
    if (cause instanceof ReferenceApiError && cause.status === 410) preview.value.state = 'EXPIRED'
  } finally {
    busy.value = false
  }
}
function downloadTemplate() {
  const item = {
    kind: kind.value,
    id: crypto.randomUUID(),
    name: '请填写真实名称',
    availability: 'AVAILABLE',
    owner_team_id: '00000000-0000-4000-8000-000000000001',
    data_owner_user_ids: ['00000000-0000-4000-8000-000000000002'],
    source_key: '请填写稳定来源键',
  }
  const url = URL.createObjectURL(
    new Blob([JSON.stringify([item], null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `ORBIT-${kind.value}-引用资料模板.json`
  link.click()
  URL.revokeObjectURL(url)
}
onMounted(async () => {
  await load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.el-alert {
  margin-bottom: 16px;
}
.el-form {
  margin-top: 16px;
}
.filter {
  width: 230px;
}
.size {
  width: 130px;
}
.pager {
  justify-content: flex-end;
  margin-top: 16px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.el-select {
  width: 100%;
}
.file-input {
  display: block;
  margin-bottom: 16px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 0;
  font: 12px/1.5 monospace;
}
h3 {
  font-size: 15px;
  font-weight: 600;
}
:global(.reference-dialog) {
  max-width: calc(100vw - 24px);
  margin-top: 5vh;
}
:global(.reference-dialog .el-dialog__body) {
  max-height: calc(90vh - 150px);
  overflow: auto;
}
@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .pager {
    justify-content: flex-start;
  }
}
</style>
