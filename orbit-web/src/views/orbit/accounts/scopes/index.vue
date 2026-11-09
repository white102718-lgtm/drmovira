<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  createScope,
  getScopeCsrf,
  ScopeApiError,
  type ScopeFilter,
  type ScopeRequest,
  type ScopeSnapshot,
} from '@/api/orbit/scopes'
import ScopeMembers from './ScopeMembers.vue'

const mode = ref<'FILTER' | 'IDS'>('FILTER')
const ids = ref('')
const filter = reactive<ScopeFilter>({
  q: '',
  status: null,
  auth_status: null,
  operator_user_id: null,
  vendor_id: null,
})
const loading = ref(false)
const error = ref('')
const preview = ref<ScopeSnapshot | null>(null)
const selected = ref<ScopeSnapshot | null>(null)
const opened = ref(false)
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
let intent: { canonical: string; key: string } | undefined
let controller: AbortController | undefined
let generation = 0

/** 本地拦截明显格式错误；权限、上限和最终成员以服务端事务结果为准。 */
function requestValue(): ScopeRequest {
  if (mode.value === 'IDS') {
    const raw = ids.value
      .trim()
      .split(/[\s,，]+/)
      .filter(Boolean)
    if (!raw.length || raw.length > 50000 || raw.some((id) => !uuid.test(id)))
      throw new Error('请输入1至50000个有效账户ID，以换行或逗号分隔')
    const normalized = raw.map((id) => id.toLowerCase())
    if (new Set(normalized).size !== normalized.length)
      throw new ScopeApiError(422, 'DUPLICATE_VALUE', '账户ID清单包含重复项，请移除重复ID')
    return {
      mode: 'IDS',
      account_ids: normalized.sort(),
      filter: null,
    }
  }
  const q = filter.q.normalize('NFC').trim()
  if ([...q].length > 100 || /[\u0000-\u001f\u007f-\u009f]/.test(q))
    throw new Error('搜索词最多100个字符，不能包含控制字符')
  for (const id of [filter.operator_user_id, filter.vendor_id])
    if (id && !uuid.test(id)) throw new Error('投手ID和户商ID必须是有效账户系统UUID')
  return {
    mode: 'FILTER',
    account_ids: [],
    filter: {
      ...filter,
      q,
      operator_user_id: filter.operator_user_id?.toLowerCase() || null,
      vendor_id: filter.vendor_id?.toLowerCase() || null,
    },
  }
}
async function freeze() {
  if (loading.value) return
  error.value = ''
  let value: ScopeRequest
  try {
    value = requestValue()
  } catch (failure) {
    error.value = (failure as Error).message
    return
  }
  const canonical = JSON.stringify(value)
  if (!intent || canonical !== intent.canonical) intent = { canonical, key: crypto.randomUUID() }
  controller = new AbortController()
  const ticket = ++generation
  loading.value = true
  try {
    const { csrf_token } = await getScopeCsrf(controller.signal)
    const result = await createScope(value, intent.key, csrf_token, controller.signal)
    if (ticket !== generation) return
    preview.value = result
    opened.value = true
  } catch (failure) {
    if (ticket === generation) {
      error.value = failure instanceof Error ? failure.message : '范围冻结失败，请重试'
      if (failure instanceof ScopeApiError && failure.status === 409) intent = undefined
    }
  } finally {
    if (ticket === generation) loading.value = false
  }
}
function reopen() {
  preview.value = selected.value
  opened.value = true
}
/** 页面条件变化后原选择立即失效，旧写请求的迟到响应也不能恢复原范围。 */
watch(
  () => [mode.value, ids.value, { ...filter }],
  () => {
    generation++
    controller?.abort()
    loading.value = false
    selected.value = null
    preview.value = null
    opened.value = false
    intent = undefined
  },
  { deep: true },
)
onBeforeUnmount(() => {
  generation++
  controller?.abort()
})
</script>

<template>
  <div class="app-container scope-page">
    <h2>账户范围</h2>
    <p>按条件冻结当前可见账户，或指定账户ID。确认前可分页核对成员。</p>
    <el-form label-position="top" :disabled="loading" @submit.prevent="freeze">
      <el-form-item label="选择方式">
        <el-radio-group v-model="mode" aria-label="选择方式"
          ><el-radio-button value="FILTER">按筛选条件</el-radio-button
          ><el-radio-button value="IDS">指定账户ID</el-radio-button></el-radio-group
        >
      </el-form-item>
      <template v-if="mode === 'FILTER'">
        <div class="scope-fields">
          <el-form-item label="账户名称或外部ID"
            ><el-input v-model="filter.q" aria-label="账户名称或外部ID" clearable
          /></el-form-item>
          <el-form-item label="账户状态"
            ><el-select
              v-model="filter.status"
              aria-label="账户状态"
              clearable
              :value-on-clear="null"
              ><el-option label="正常" value="ACTIVE" /><el-option
                label="已停用"
                value="DISABLED" /><el-option label="未知" value="UNKNOWN" /></el-select
          ></el-form-item>
          <el-form-item label="授权状态"
            ><el-select
              v-model="filter.auth_status"
              aria-label="授权状态"
              clearable
              :value-on-clear="null"
              ><el-option label="已授权" value="AUTHORIZED" /><el-option
                label="已过期"
                value="EXPIRED" /><el-option label="已撤销" value="REVOKED" /><el-option
                label="未知"
                value="UNKNOWN" /></el-select
          ></el-form-item>
          <el-form-item label="投手ID"
            ><el-input v-model="filter.operator_user_id" aria-label="投手ID" clearable
          /></el-form-item>
          <el-form-item label="户商ID"
            ><el-input v-model="filter.vendor_id" aria-label="户商ID" clearable
          /></el-form-item>
        </div>
      </template>
      <el-form-item v-else label="账户ID清单"
        ><el-input
          v-model="ids"
          aria-label="账户ID清单"
          type="textarea"
          :rows="6"
          placeholder="填写系统账户ID（UUID），以换行或逗号分隔"
      /></el-form-item>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-button type="primary" native-type="submit" :loading="loading">{{
        error ? '重试冻结范围' : '冻结并查看成员'
      }}</el-button>
    </el-form>
    <section v-if="selected" class="scope-selected" aria-label="已选择范围">
      <h3>已选择 {{ selected.count }} 个账户</h3>
      <p>冻结时间：{{ selected.created_at }}；权限版本：{{ selected.scope_version }}</p>
      <el-button @click="reopen">查看成员</el-button>
      <el-button @click="selected = null">清除选择</el-button>
    </section>
    <ScopeMembers v-model="opened" :snapshot="preview" @confirm="selected = $event" />
  </div>
</template>

<style scoped>
.scope-page {
  max-width: 1200px;
}
.scope-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: 0 20px;
}
.scope-selected {
  margin-top: 32px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color);
}
.el-alert {
  margin-bottom: 16px;
}
</style>
