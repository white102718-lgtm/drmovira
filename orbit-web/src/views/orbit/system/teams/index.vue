<template>
  <div class="app-container team-page">
    <el-form :inline="true" @submit.prevent="reload">
      <el-form-item label="团队名称"
        ><el-input v-model="query" clearable placeholder="按名称查询" @keyup.enter="reload"
      /></el-form-item>
      <el-form-item label="状态"
        ><el-select v-model="status" clearable placeholder="全部状态" style="width: 140px"
          ><el-option label="启用" value="ENABLED" /><el-option
            label="停用"
            value="DISABLED" /></el-select
      ></el-form-item>
      <el-form-item label="创建日期（UTC）"
        ><el-date-picker
          v-model="dates"
          type="daterange"
          popper-class="orbit-directory-date-popper"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
      /></el-form-item>
      <el-form-item
        ><el-button type="primary" :disabled="loading" @click="reload">查询</el-button
        ><el-button :disabled="loading" @click="reset">重置</el-button></el-form-item
      >
    </el-form>
    <div class="team-toolbar">
      <h2>团队管理</h2>
      <el-button v-if="capabilities?.can_create" type="primary" @click="openEditor()"
        >新增团队</el-button
      >
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
      class="team-error"
    />
    <el-table v-loading="loading" :data="rows" empty-text="暂无符合条件的团队">
      <el-table-column prop="name" label="团队名称" min-width="220" show-overflow-tooltip />
      <el-table-column label="状态" width="100"
        ><template #default="{ row }"
          ><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'">{{
            row.status === 'ENABLED' ? '启用' : '停用'
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="id" label="团队ID" min-width="300" />
      <el-table-column prop="revision" label="版本" width="90" />
      <el-table-column label="操作" width="150" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row)">详情</el-button
          ><el-button v-if="canEdit(row)" link type="primary" @click="openEditor(row)"
            >编辑</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="team-pagination">
      <el-select
        v-model="pageSize"
        aria-label="每页数量"
        style="width: 120px"
        :disabled="loading"
        @change="reload"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :label="`${size}条/页`"
          :value="size"
      /></el-select>
      <span>第{{ page + 1 }}页</span
      ><el-button :disabled="loading || page === 0" @click="previous">上一页</el-button
      ><el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button>
    </div>
    <el-dialog
      v-model="editorVisible"
      :title="existing ? '编辑团队' : '新增团队'"
      width="560px"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :before-close="closeEditor"
    >
      <el-form ref="form" :model="draft" label-position="top" :rules="rules" :disabled="saving">
        <el-form-item label="团队名称" prop="name"
          ><el-input v-model="draft.name" placeholder="1至100个字符"
        /></el-form-item>
        <el-form-item label="团队状态" prop="status"
          ><el-radio-group v-model="draft.status"
            ><el-radio value="ENABLED">启用</el-radio
            ><el-radio value="DISABLED">停用</el-radio></el-radio-group
          ></el-form-item
        >
        <el-alert
          v-if="draft.status === 'DISABLED'"
          title="停用后，该团队成员的业务访问将立即失效。已有资源和历史记录保留。"
          type="warning"
          :closable="false"
        />
        <el-alert
          v-if="saveError"
          :title="saveError"
          type="error"
          :closable="false"
          class="team-error"
        />
      </el-form>
      <template #footer
        ><el-button :disabled="saving" @click="editorVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="submit">保存</el-button></template
      >
    </el-dialog>
    <el-drawer v-model="detailVisible" title="团队详情" size="min(560px, 100vw)">
      <el-descriptions v-if="detail" :column="1" border
        ><el-descriptions-item label="团队名称">{{ detail.name }}</el-descriptions-item
        ><el-descriptions-item label="团队ID">{{ detail.id }}</el-descriptions-item
        ><el-descriptions-item label="状态">{{
          detail.status === 'ENABLED' ? '启用' : '停用'
        }}</el-descriptions-item
        ><el-descriptions-item label="版本">{{
          detail.revision
        }}</el-descriptions-item></el-descriptions
      >
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import '../directory-date.scss'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { teamApi, TeamApiError, type Team, type TeamCapabilities } from '@/api/orbit/teams'

const rows = ref<Team[]>([]),
  loading = ref(false),
  error = ref('')
const capabilities = ref<TeamCapabilities>(),
  query = ref(''),
  status = ref(''),
  dates = ref<string[]>([])
const pageSize = ref(50),
  page = ref(0),
  cursors = ref<(string | null)[]>([null]),
  nextCursor = ref<string | null>(null)
const activeFilters = ref(new URLSearchParams())
const editorVisible = ref(false),
  saving = ref(false),
  saveError = ref(''),
  existing = ref<Team>()
const draft = reactive<Pick<Team, 'name' | 'status'>>({ name: '', status: 'ENABLED' })
const form = ref<FormInstance>(),
  detail = ref<Team>(),
  detailVisible = ref(false)
// 无秘密团队DTO可用规范字符串比较保存意图；不进入localStorage或若依请求缓存。
let lastIntent = '',
  requestKey = ''
const rules: FormRules = {
  name: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value)
        if (/[\p{Cc}\p{Cs}\u2028\u2029]/u.test(text))
          return callback(new Error('名称不能包含控制字符'))
        const size = [...text.trim().normalize('NFC')].length
        callback(size >= 1 && size <= 100 ? undefined : new Error('请输入1至100个字符的团队名称'))
      },
      trigger: 'blur',
    },
  ],
}
const message = (reason: unknown) =>
  reason instanceof Error ? reason.message : '请求失败，请稍后重试'
const canEdit = (team: Team) =>
  capabilities.value?.data_role === 'SUPER_ADMIN' ||
  (capabilities.value?.data_role === 'TEAM_ADMIN' &&
    capabilities.value.managed_team_ids.includes(team.id))
async function load() {
  loading.value = true
  error.value = ''
  try {
    capabilities.value = await teamApi.capabilities()
    const filters = new URLSearchParams(activeFilters.value)
    const cursor = cursors.value[page.value]
    if (cursor) filters.set('cursor', cursor)
    const result = await teamApi.list(filters)
    rows.value = result.items
    nextCursor.value = result.next_cursor
  } catch (reason) {
    rows.value = []
    nextCursor.value = null
    error.value = message(reason)
    if (reason instanceof TeamApiError && reason.code === 'CURSOR_STALE') {
      page.value = 0
      cursors.value = [null]
    }
  } finally {
    loading.value = false
  }
}
async function reload() {
  activeFilters.value = new URLSearchParams({ page_size: String(pageSize.value) })
  if (query.value) activeFilters.value.set('q', query.value)
  if (status.value) activeFilters.value.set('status', status.value)
  if (dates.value?.length === 2) {
    activeFilters.value.set('date_from', dates.value[0])
    activeFilters.value.set('date_to', dates.value[1])
  }
  page.value = 0
  cursors.value = [null]
  await load()
}
function reset() {
  query.value = ''
  status.value = ''
  dates.value = []
  void reload()
}
function previous() {
  page.value--
  void load()
}
function next() {
  if (!nextCursor.value) return
  cursors.value[++page.value] = nextCursor.value
  void load()
}
async function showDetail(team: Team) {
  try {
    detail.value = await teamApi.get(team.id)
    detailVisible.value = true
  } catch (reason) {
    ElMessage.error(message(reason))
  }
}
async function openEditor(team?: Team) {
  try {
    capabilities.value = await teamApi.capabilities()
    existing.value = team ? await teamApi.get(team.id) : undefined
    draft.name = existing.value?.name ?? ''
    draft.status = existing.value?.status ?? 'ENABLED'
    saveError.value = ''
    lastIntent = ''
    requestKey = ''
    editorVisible.value = true
    form.value?.clearValidate()
  } catch (reason) {
    ElMessage.error(message(reason))
  }
}
function closeEditor(done: () => void) {
  if (!saving.value) done()
}
async function submit() {
  if (saving.value || !(await form.value?.validate().catch(() => false))) return
  saving.value = true
  saveError.value = ''
  try {
    if (draft.status === 'DISABLED' && existing.value?.status !== 'DISABLED') {
      try {
        await ElMessageBox.confirm('确认停用该团队？成员的业务访问将立即失效。', '停用团队', {
          type: 'warning',
          confirmButtonText: '确认停用',
          cancelButtonText: '取消',
        })
      } catch {
        return
      }
    }
    const value = { name: draft.name.trim().normalize('NFC'), status: draft.status }
    const intent = JSON.stringify([existing.value?.id, existing.value?.revision, value])
    if (intent !== lastIntent) {
      lastIntent = intent
      requestKey = crypto.randomUUID()
    }
    capabilities.value = await teamApi.capabilities()
    await teamApi.save(value, capabilities.value.csrf_token, requestKey, existing.value)
    editorVisible.value = false
    ElMessage.success('团队已保存')
    await reload()
  } catch (reason) {
    saveError.value = message(reason)
    if (
      reason instanceof TeamApiError &&
      reason.status >= 400 &&
      reason.status < 500 &&
      reason.status !== 408
    ) {
      lastIntent = ''
      requestKey = ''
    }
  } finally {
    saving.value = false
  }
}
onMounted(reload)
</script>

<style scoped>
.team-toolbar,
.team-pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.team-toolbar {
  justify-content: space-between;
  margin-bottom: 16px;
}
.team-toolbar h2 {
  margin: 0;
  font-size: 20px;
}
.team-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
.team-error {
  margin: 12px 0;
}
.team-page :deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}
.team-page :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .team-page :deep(.el-date-editor) {
    width: 100%;
    max-width: calc(100vw - 48px);
  }
  .team-pagination {
    justify-content: flex-start;
  }
}
</style>
