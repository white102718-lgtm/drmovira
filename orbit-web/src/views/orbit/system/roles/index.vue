<template>
  <div class="app-container roles-page">
    <el-form :inline="true" @submit.prevent="reload">
      <el-form-item label="角色名称"
        ><el-input v-model="query" clearable placeholder="按角色名称查询" @keyup.enter="reload"
      /></el-form-item>
      <el-form-item label="状态"
        ><el-select v-model="status" clearable placeholder="全部状态" style="width: 140px"
          ><el-option label="启用" value="ENABLED" /><el-option
            label="停用"
            value="DISABLED" /></el-select
      ></el-form-item>
      <el-form-item label="登记日期（UTC）"
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
    <div class="roles-toolbar">
      <h2>功能角色</h2>
      <el-button v-if="capabilities" type="primary" @click="openEditor()">新增角色</el-button>
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
      class="roles-message"
    />
    <el-table v-loading="loading" :data="rows" empty-text="暂无符合条件的角色">
      <el-table-column prop="name" label="角色名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="类型" width="110"
        ><template #default="{ row }"
          ><el-tag v-if="isBuiltIn(row)" type="info">内置只读</el-tag
          ><span v-else>自定义</span></template
        ></el-table-column
      >
      <el-table-column label="业务菜单" min-width="230"
        ><template #default="{ row }">{{
          row.menu_codes.map((code: string) => menuLabels[code] ?? code).join('、') || '未授予菜单'
        }}</template></el-table-column
      >
      <el-table-column label="动作数量" width="100"
        ><template #default="{ row }">{{ row.permission_codes.length }}</template></el-table-column
      >
      <el-table-column prop="revision" label="版本" width="80" />
      <el-table-column label="操作" width="180" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row)">详情</el-button
          ><el-button v-if="!isBuiltIn(row)" link type="primary" @click="openEditor(row)"
            >编辑</el-button
          ><el-button link type="primary" @click="openEditor(row, true)">复制</el-button></template
        ></el-table-column
      >
    </el-table>
    <div class="roles-pagination">
      <el-select
        v-model="pageSize"
        aria-label="每页数量"
        style="width: 120px"
        :disabled="loading"
        @change="reload"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="`${size}条/页`" /></el-select
      ><span>第{{ page + 1 }}页</span
      ><el-button :disabled="loading || page === 0" @click="previous">上一页</el-button
      ><el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button>
    </div>
    <el-dialog
      v-model="editorVisible"
      :title="copying ? '复制角色' : existing ? '编辑角色' : '新增角色'"
      width="860px"
      top="5vh"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :before-close="closeEditor"
    >
      <el-form
        ref="form"
        :model="draft"
        :rules="rules"
        label-position="top"
        :disabled="saving"
        class="role-editor"
        :style="{ maxHeight: saveError ? '55vh' : '65vh' }"
      >
        <el-form-item label="角色名称" prop="name"
          ><el-input v-model="draft.name" placeholder="1至50个字符"
        /></el-form-item>
        <el-alert
          title="菜单和动作可分别授予。用户的全部功能角色合并后，仍受数据范围限制。"
          type="info"
          :closable="false"
        />
        <el-form-item label="业务菜单" class="role-grants"
          ><el-checkbox-group v-model="draft.menu_codes" aria-label="业务菜单"
            ><el-checkbox v-for="code in capabilities?.menus ?? []" :key="code" :value="code">{{
              menuLabels[code] ?? code
            }}</el-checkbox></el-checkbox-group
          ></el-form-item
        >
        <div class="roles-toolbar">
          <h3>动作权限</h3>
          <el-button link type="primary" :disabled="saving" @click="draft.permission_codes = []"
            >清空动作</el-button
          >
        </div>
        <section v-for="group in actionGroups" :key="group.code" class="role-action-group">
          <h4>{{ menuLabels[group.code] ?? group.code }}</h4>
          <el-checkbox-group
            v-model="draft.permission_codes"
            :aria-label="`${menuLabels[group.code]}动作`"
            ><el-checkbox v-for="code in group.actions" :key="code" :value="code"
              ><el-tooltip :content="code"
                ><span>{{ permissionLabels[code] ?? code }}</span></el-tooltip
              ></el-checkbox
            ></el-checkbox-group
          >
        </section>
      </el-form>
      <template #footer>
        <el-alert
          v-if="saveError"
          :title="saveError"
          type="error"
          :closable="false"
          class="roles-message"
        />
        <el-button :disabled="saving" @click="editorVisible = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="submit">保存角色</el-button></template
      >
    </el-dialog>
    <el-drawer v-model="detailVisible" title="角色详情" size="min(600px, 100vw)">
      <el-descriptions v-if="detail" :column="1" border
        ><el-descriptions-item label="角色名称">{{ detail.name }}</el-descriptions-item
        ><el-descriptions-item label="角色ID">{{ detail.id }}</el-descriptions-item
        ><el-descriptions-item label="版本">{{ detail.revision }}</el-descriptions-item
        ><el-descriptions-item label="业务菜单">{{
          detail.menu_codes.map((code) => menuLabels[code] ?? code).join('、') || '未授予菜单'
        }}</el-descriptions-item
        ><el-descriptions-item label="动作权限"
          ><ul v-if="detail.permission_codes.length" class="role-detail-actions">
            <li v-for="code in detail.permission_codes" :key="code">
              {{ permissionLabels[code] ?? code }}<span class="role-code">{{ code }}</span>
            </li>
          </ul>
          <span v-else>未授予动作</span></el-descriptions-item
        ></el-descriptions
      >
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import '../directory-date.scss'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import {
  roleApi,
  RoleApiError,
  type BusinessRole,
  type RoleCapabilities,
  type RoleWrite,
} from '@/api/orbit/roles'
import { menuLabels, permissionLabels, permissionMenu } from './labels'

const rows = ref<BusinessRole[]>([]),
  capabilities = ref<RoleCapabilities>()
const query = ref(''),
  status = ref(''),
  dates = ref<string[]>([]),
  activeFilters = ref(new URLSearchParams()),
  loading = ref(false),
  error = ref('')
const pageSize = ref(50),
  page = ref(0),
  cursors = ref<(string | null)[]>([null]),
  nextCursor = ref<string | null>(null)
const editorVisible = ref(false),
  detailVisible = ref(false),
  saving = ref(false),
  copying = ref(false),
  saveError = ref('')
const existing = ref<BusinessRole>(),
  detail = ref<BusinessRole>(),
  form = ref<FormInstance>()
const draft = reactive<RoleWrite>({ name: '', menu_codes: [], permission_codes: [] })
let lastIntent = '',
  requestKey = ''
const actionGroups = computed(() =>
  Object.keys(menuLabels).map((code) => ({
    code,
    actions: (capabilities.value?.permissions ?? []).filter(
      (action) => permissionMenu(action) === code,
    ),
  })),
)
const isBuiltIn = (role: BusinessRole) => capabilities.value?.built_in_role_ids.includes(role.id)
const message = (reason: unknown) =>
  reason instanceof Error ? reason.message : '请求失败，请稍后重试'
const rules: FormRules = {
  name: [
    {
      validator: (_rule, value, callback) => {
        const text = String(value)
        if (/[\p{Cc}\p{Cs}\u2028\u2029]/u.test(text))
          return callback(new Error('名称不能包含控制字符'))
        const count = [...text.trim().normalize('NFC')].length
        callback(count >= 1 && count <= 50 ? undefined : new Error('请输入1至50个字符的角色名称'))
      },
      trigger: 'blur',
    },
  ],
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    capabilities.value = await roleApi.capabilities()
    const filters = new URLSearchParams(activeFilters.value)
    if (cursors.value[page.value]) filters.set('cursor', cursors.value[page.value]!)
    const result = await roleApi.list(filters)
    rows.value = result.items
    nextCursor.value = result.next_cursor
  } catch (reason) {
    rows.value = []
    nextCursor.value = null
    error.value = message(reason)
    if (reason instanceof RoleApiError && reason.code === 'CURSOR_STALE') {
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
async function showDetail(role: BusinessRole) {
  try {
    detail.value = await roleApi.get(role.id)
    detailVisible.value = true
  } catch (reason) {
    ElMessage.error(message(reason))
  }
}
async function openEditor(role?: BusinessRole, copy = false) {
  try {
    capabilities.value = await roleApi.capabilities()
    const source = role ? await roleApi.get(role.id) : undefined
    existing.value = copy ? undefined : source
    copying.value = copy
    draft.name = source ? `${source.name}${copy ? '副本' : ''}` : ''
    draft.menu_codes = [...(source?.menu_codes ?? [])]
    draft.permission_codes = [...(source?.permission_codes ?? [])]
    lastIntent = ''
    requestKey = ''
    saveError.value = ''
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
    const source = existing.value
    if (
      source &&
      (source.menu_codes.some((code) => !draft.menu_codes.includes(code)) ||
        source.permission_codes.some((code) => !draft.permission_codes.includes(code)))
    ) {
      try {
        await ElMessageBox.confirm(
          '保存后将立即撤销成员对应的访问权限，确认继续？',
          '撤销角色授权',
          { type: 'warning', confirmButtonText: '确认保存', cancelButtonText: '返回检查' },
        )
      } catch {
        return
      }
    }
    const value = {
      name: draft.name.trim().normalize('NFC'),
      menu_codes: [...draft.menu_codes].sort(),
      permission_codes: [...draft.permission_codes].sort(),
    }
    const intent = JSON.stringify([source?.id, source?.revision, value])
    if (lastIntent !== intent) {
      lastIntent = intent
      requestKey = crypto.randomUUID()
    }
    capabilities.value = await roleApi.capabilities()
    await roleApi.save(value, capabilities.value.csrf_token, requestKey, source)
    editorVisible.value = false
    ElMessage.success('角色已保存')
    await reload()
  } catch (reason) {
    saveError.value = message(reason)
    if (
      reason instanceof RoleApiError &&
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
.roles-toolbar,
.roles-pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.roles-toolbar {
  justify-content: space-between;
  margin-bottom: 16px;
}
.roles-toolbar h2 {
  margin: 0;
  font-size: 20px;
}
.roles-toolbar h3 {
  margin: 16px 0 0;
  font-size: 16px;
}
.roles-pagination {
  justify-content: flex-end;
  margin-top: 20px;
}
.roles-message {
  margin: 12px 0;
}
.role-editor {
  max-height: 65vh;
  overflow-y: auto;
  padding: 0 8px 0 0;
}
.role-grants {
  margin-top: 20px;
}
.role-action-group h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.role-editor :deep(.el-checkbox-group) {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px 12px;
}
.role-editor :deep(.el-checkbox) {
  margin-right: 0;
  min-width: 0;
}
.role-editor :deep(.el-checkbox__label) {
  white-space: normal;
}
.roles-page :deep(.el-dialog) {
  max-width: calc(100vw - 24px);
}
.roles-page :deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
.role-detail-actions {
  margin: 0;
  padding-left: 16px;
}
.role-code {
  display: block;
  font-size: 12px;
}
@media (max-width: 600px) {
  .roles-page :deep(.el-date-editor) {
    width: 100%;
    max-width: calc(100vw - 48px);
  }
  .role-editor :deep(.el-checkbox-group) {
    grid-template-columns: 1fr;
  }
  .roles-pagination {
    justify-content: flex-start;
  }
}
</style>
