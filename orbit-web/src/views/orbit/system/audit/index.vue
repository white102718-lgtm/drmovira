<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  AuditApiError,
  listAuditEvents,
  type AuditFilters,
  type AuditItem,
  type AuditPage,
} from '@/api/orbit/audit'

const filters = reactive<AuditFilters>({ q: '', operator_user_id: '', date_from: '', date_to: '' })
const size = ref(50)
const loading = ref(false)
const error = ref('')
const requestId = ref('')
const result = ref<AuditPage>()
const page = ref(0)
const cursors = ref<(string | null)[]>([null])
const detail = ref<AuditItem>()
const detailOpen = ref(false)
const rows = computed(() => result.value?.items || [])
let applied: AuditFilters = { ...filters }
let abort: AbortController | undefined
let generation = 0

function action(value: string) {
  return value === 'SCOPE_FROZEN' ? '冻结账户范围' : value
}
function showDetail(row: AuditItem) {
  detail.value = row
  detailOpen.value = true
}
/** 新请求替换旧请求；权限/版本失败立即释放旧数据和详情，网络失败保留上次合法读取结果。 */
async function load(index: number) {
  abort?.abort()
  abort = new AbortController()
  const current = ++generation
  loading.value = true
  error.value = ''
  requestId.value = ''
  try {
    const value = await listAuditEvents(
      applied,
      size.value,
      cursors.value[index] || null,
      abort.signal,
    )
    if (current !== generation) return
    result.value = value
    page.value = index
    detailOpen.value = false
    detail.value = undefined
  } catch (failure) {
    if (
      current !== generation ||
      (failure instanceof DOMException && failure.name === 'AbortError')
    )
      return
    error.value = failure instanceof Error ? failure.message : '审计查询失败，请重试'
    if (failure instanceof AuditApiError) {
      requestId.value = failure.requestId || ''
      if ([401, 403, 404, 409].includes(failure.status)) {
        result.value = undefined
        cursors.value = [null]
        page.value = 0
        detail.value = undefined
        detailOpen.value = false
      }
    }
  } finally {
    if (current === generation) loading.value = false
  }
}
function search() {
  applied = { ...filters }
  cursors.value = [null]
  void load(0)
}
function reset() {
  Object.assign(filters, { q: '', operator_user_id: '', date_from: '', date_to: '' })
  search()
}
function next() {
  if (!result.value?.next_cursor) return
  cursors.value[page.value + 1] = result.value.next_cursor
  void load(page.value + 1)
}
onMounted(search)
onBeforeUnmount(() => {
  generation++
  abort?.abort()
})
</script>

<template>
  <div class="app-container audit-page">
    <h2>审计日志</h2>
    <p class="audit-description">
      查询当前权限内的操作记录，时间统一显示为 UTC。当前已接入账户范围冻结事件。
    </p>
    <el-form :inline="true" label-position="top" @submit.prevent="search">
      <el-form-item label="动作代码"
        ><el-input v-model="filters.q" clearable placeholder="如 SCOPE_FROZEN" maxlength="100"
      /></el-form-item>
      <el-form-item label="操作者UUID"
        ><el-input v-model="filters.operator_user_id" clearable placeholder="精确匹配历史操作者"
      /></el-form-item>
      <el-form-item label="开始日期（UTC）"
        ><el-date-picker
          v-model="filters.date_from"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="开始日期"
      /></el-form-item>
      <el-form-item label="结束日期（UTC）"
        ><el-date-picker
          v-model="filters.date_to"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="结束日期"
      /></el-form-item>
      <el-form-item label="操作"
        ><el-button type="primary" native-type="submit" :loading="loading">查询</el-button
        ><el-button :disabled="loading" @click="reset">重置</el-button
        ><el-button :disabled="loading" @click="load(page)">刷新</el-button></el-form-item
      >
    </el-form>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
      show-icon
      class="audit-error"
      ><template #default
        ><span v-if="requestId">请求编号：{{ requestId }}</span
        ><span v-if="result"> · 保留上一次读取结果</span></template
      ></el-alert
    >
    <el-table
      v-loading="loading"
      :data="rows"
      row-key="id"
      border
      empty-text="暂无符合条件的审计记录"
    >
      <el-table-column prop="occurred_at" label="发生时间（UTC）" min-width="220" />
      <el-table-column label="动作" min-width="160"
        ><template #default="{ row }">{{ action(row.action_code) }}</template></el-table-column
      >
      <el-table-column
        prop="actor_user_id"
        label="操作者UUID"
        min-width="200"
        show-overflow-tooltip
      />
      <el-table-column
        prop="tenant_id"
        label="目标租户UUID"
        min-width="200"
        show-overflow-tooltip
      />
      <el-table-column prop="target_id" label="对象UUID" min-width="200" show-overflow-tooltip />
      <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
      <el-table-column prop="request_id" label="请求UUID" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="90" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="showDetail(row)">详情</el-button></template
        ></el-table-column
      >
    </el-table>
    <div class="audit-pagination">
      <span v-if="result">读取截止 {{ result.data_as_of }} · 当前页 {{ rows.length }} 条</span>
      <el-select
        v-model="size"
        aria-label="每页条数"
        class="audit-size"
        :disabled="loading"
        @change="search"
        ><el-option
          v-for="value in [20, 50, 100, 200]"
          :key="value"
          :label="String(value)"
          :value="value"
      /></el-select>
      <el-button :disabled="loading || page === 0" @click="load(page - 1)">上一页</el-button
      ><span>第 {{ page + 1 }} 页</span
      ><el-button :disabled="loading || !result?.next_cursor" @click="next">下一页</el-button>
    </div>
    <el-drawer
      v-model="detailOpen"
      title="审计详情"
      size="560px"
      :style="{ maxWidth: '100vw' }"
      destroy-on-close
    >
      <el-descriptions v-if="detail" :column="1" border direction="vertical">
        <el-descriptions-item label="审计UUID"
          ><span class="audit-id">{{ detail.id }}</span></el-descriptions-item
        >
        <el-descriptions-item label="动作"
          >{{ action(detail.action_code) }}（{{ detail.action_code }}）</el-descriptions-item
        >
        <el-descriptions-item label="操作者UUID"
          ><span class="audit-id">{{ detail.actor_user_id }}</span></el-descriptions-item
        >
        <el-descriptions-item label="目标租户UUID"
          ><span class="audit-id">{{ detail.tenant_id }}</span></el-descriptions-item
        >
        <el-descriptions-item label="对象UUID"
          ><span class="audit-id">{{ detail.target_id || '无' }}</span></el-descriptions-item
        >
        <el-descriptions-item label="原因">{{ detail.reason || '未填写' }}</el-descriptions-item>
        <el-descriptions-item label="证据引用"
          ><span class="audit-id">{{ detail.evidence_ref || '无' }}</span></el-descriptions-item
        >
        <el-descriptions-item label="发生时间（UTC）">{{
          detail.occurred_at
        }}</el-descriptions-item>
        <el-descriptions-item label="请求UUID"
          ><span class="audit-id">{{ detail.request_id }}</span></el-descriptions-item
        >
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<style scoped>
.audit-page h2 {
  margin-top: 0;
}
.audit-description {
  color: var(--el-text-color-regular);
  margin-bottom: 20px;
}
.audit-error {
  margin-bottom: 16px;
}
.audit-pagination {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}
.audit-size {
  width: 90px;
}
.audit-id {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .audit-page :deep(.el-form-item) {
    display: block;
    margin-right: 0;
  }
  .audit-page :deep(.el-date-editor) {
    max-width: 100%;
  }
  .audit-page :deep(.el-form-item__content) {
    width: 100%;
  }
}
</style>
