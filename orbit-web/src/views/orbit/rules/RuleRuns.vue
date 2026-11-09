<template>
  <section class="rule-runs" aria-label="规则运行记录">
    <h3>运行记录</h3>
    <p>规则 {{ ruleId || '尚未选择' }}；时间按原接口返回的 UTC 显示。</p>
    <div class="filters">
      <el-select v-model="status" aria-label="运行状态" clearable placeholder="全部运行状态">
        <el-option v-for="state in states" :key="state" :value="state" :label="stateLabel[state]" />
      </el-select>
      <label
        >开始日期<el-date-picker
          v-model="dateFrom"
          aria-label="运行开始日期"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="未筛选"
      /></label>
      <label
        >截止日期<el-date-picker
          v-model="dateTo"
          aria-label="运行截止日期"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="未筛选"
      /></label>
      <el-button :disabled="!readable || loading" @click="search">查询记录</el-button>
    </div>
    <el-alert v-if="!allowed" title="缺少规则读取权限" type="info" :closable="false" />
    <el-alert v-else-if="!ruleId" title="尚未选择规则" type="info" :closable="false" />
    <p v-if="loading" role="status">正在读取运行记录…</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <p v-if="error">本次没有取得有效记录页；重新查询将从首页读取，不会自动重试。</p>
    <p v-if="page && !page.items.length">当前页无运行记录</p>
    <el-table v-if="page && page.items.length" :data="page.items" row-key="id">
      <el-table-column prop="id" label="记录 ID" min-width="260" />
      <el-table-column prop="rule_id" label="规则 ID" min-width="260" />
      <el-table-column prop="rule_revision" label="规则版本" width="100" />
      <el-table-column prop="schedule_slot" label="调度时刻（UTC）" min-width="210" />
      <el-table-column prop="snapshot_id" label="快照 ID" min-width="260" />
      <el-table-column label="运行状态" width="110"
        ><template #default="{ row }">{{
          stateLabel[row.state as RuleRunState]
        }}</template></el-table-column
      >
      <el-table-column prop="hit_count" label="命中数量" width="100" />
      <el-table-column label="原因码" min-width="180"
        ><template #default="{ row }">{{ row.reason_code ?? '未提供' }}</template></el-table-column
      >
    </el-table>
    <div class="pagination">
      <el-select v-model="pageSize" aria-label="记录每页条数" :disabled="!readable" @change="search"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="`${size} 条`"
      /></el-select>
      <el-button :disabled="loading || !history.length || !readable" @click="previous"
        >上一页记录</el-button
      >
      <el-button :disabled="loading || !page?.next_cursor || !readable" @click="next"
        >下一页记录</el-button
      >
      <span v-if="page">数据时间 {{ page.data_as_of }} · 范围版本 {{ page.scope_version }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  RuleApiError,
  rulesApi,
  type RulePage,
  type RuleRun,
  type RuleRunQuery,
  type RuleRunState,
} from '@/api/orbit/rules'
const props = withDefaults(
  defineProps<{
    ruleId: string
    permissionCodes?: string[]
    contextKey?: string
    filters?: Omit<RuleRunQuery, 'status' | 'date_from' | 'date_to' | 'page_size' | 'cursor'>
  }>(),
  { permissionCodes: () => [], contextKey: '', filters: () => ({}) },
)
const states: RuleRunState[] = ['RUNNING', 'SUCCEEDED', 'SKIPPED', 'UNKNOWN', 'FAILED']
const stateLabel: Record<RuleRunState, string> = {
  RUNNING: '运行中',
  SUCCEEDED: '已成功',
  SKIPPED: '已跳过',
  UNKNOWN: '结果未知',
  FAILED: '已失败',
}
const allowed = computed(
  () => props.permissionCodes.includes('rules.read') || props.permissionCodes.includes('*:*:*'),
)
const readable = computed(() => allowed.value && !!props.ruleId)
const status = ref<RuleRunState | ''>(''),
  dateFrom = ref<string | null>(''),
  dateTo = ref<string | null>(''),
  pageSize = ref<20 | 50 | 100 | 200>(50)
const page = ref<RulePage<RuleRun> | null>(null),
  error = ref(''),
  loading = ref(false),
  cursor = ref<string | undefined>(),
  history = ref<(string | undefined)[]>([])
const applied = ref<RuleRunQuery>({ page_size: 50 })
let epoch = 0,
  controller: AbortController | undefined
const context = () =>
  JSON.stringify([props.ruleId, props.contextKey, [...props.permissionCodes].sort()])
function cancel() {
  ++epoch
  controller?.abort()
  controller = undefined
  page.value = null
  error.value = ''
  loading.value = false
}
async function load() {
  cancel()
  if (!readable.value) return
  const token = epoch,
    started = context(),
    id = props.ruleId
  controller = new AbortController()
  loading.value = true
  try {
    const value = await rulesApi.runs(
      id,
      { ...applied.value, ...(cursor.value ? { cursor: cursor.value } : {}) },
      controller.signal,
    )
    if (token !== epoch || started !== context()) return
    // 原Page结构之外仍核本次所属规则，禁止错对象页流入详情抽屉。
    if (value.items.some((item) => item.rule_id.toLowerCase() !== id.toLowerCase()))
      throw new RuleApiError(502, 'INVALID_RESPONSE', '运行记录与当前规则不一致')
    page.value = value
  } catch (failure) {
    if (token !== epoch || started !== context()) return
    if (failure instanceof Error && failure.name === 'AbortError') return
    error.value =
      failure instanceof RuleApiError
        ? `${failure.message}（${failure.code}）${failure.field_errors.map((field) => ` ${field.path}: ${field.message}`).join('')}${failure.request_id ? ` · 请求 ${failure.request_id}` : ''}`
        : '运行记录读取失败，请重新查询。'
  } finally {
    if (token === epoch) loading.value = false
  }
}
function search() {
  applied.value = {
    ...props.filters,
    ...(status.value ? { status: status.value } : {}),
    ...(dateFrom.value ? { date_from: dateFrom.value } : {}),
    ...(dateTo.value ? { date_to: dateTo.value } : {}),
    page_size: pageSize.value,
  }
  cursor.value = undefined
  history.value = []
  void load()
}
function next() {
  if (!page.value?.next_cursor || loading.value) return
  history.value.push(cursor.value)
  cursor.value = page.value.next_cursor
  void load()
}
function previous() {
  if (!history.value.length || loading.value) return
  cursor.value = history.value.pop()
  void load()
}
watch(
  context,
  () => {
    cancel()
    status.value = ''
    dateFrom.value = ''
    dateTo.value = ''
    cursor.value = undefined
    history.value = []
    search()
  },
  { flush: 'sync' },
)
watch(() => props.filters, search, { deep: true })
onMounted(search)
onBeforeUnmount(cancel)
</script>

<style scoped>
.rule-runs {
  margin-top: 24px;
}
h3 {
  font-size: 16px;
  margin: 0 0 12px;
}
.filters,
.pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
.filters > .el-select,
.pagination > .el-select {
  width: 160px;
}
.filters label {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.el-alert {
  margin: 12px 0;
}
p,
.pagination span {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .filters > .el-select,
  .filters label {
    width: 100%;
  }
  .filters :deep(.el-date-editor) {
    width: 100%;
  }
}
</style>
