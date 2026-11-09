<template>
  <el-dialog
    :model-value="modelValue"
    title="选择投放账户"
    width="min(1080px, 100vw)"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!locked"
    :before-close="beforeClose"
    @update:model-value="requestClose"
  >
    <el-alert
      title="手动选择支持跨页勾选，最多500个；按条件冻结由服务端生成完整范围，不会下载全量账户ID。最终保存仍会重新检查双方权限、归属及币种。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="!canRead"
      title="缺少账户读取权限，不能读取或应用账户范围。"
      type="warning"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="invalid"
      title="当前拥有者、权限上下文或范围已变化；旧选择保留供核对，不能应用，请重新选择或冻结。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="unknown"
      title="冻结结果未知。原请求及幂等键已保留，只能恢复同一次冻结，不能关闭或更换条件。"
      type="warning"
      :closable="false"
    />
    <el-form label-position="top" :disabled="controlsDisabled" class="scope-filter">
      <el-form-item label="选择方式"
        ><el-radio-group v-model="mode"
          ><el-radio-button value="IDS">手动勾选</el-radio-button
          ><el-radio-button value="FILTER">按条件冻结</el-radio-button></el-radio-group
        ></el-form-item
      >
      <el-form-item label="账户名称或平台账户ID"
        ><el-input v-model="filter.q" :maxlength="100" @keyup.enter="queryCandidates"
      /></el-form-item>
      <el-form-item label="账户状态"
        ><el-select v-model="filter.status" clearable :value-on-clear="null"
          ><el-option
            v-for="v in ['ACTIVE', 'DISABLED', 'UNKNOWN']"
            :key="v"
            :label="v"
            :value="v" /></el-select
      ></el-form-item>
      <el-form-item label="授权状态"
        ><el-select v-model="filter.auth_status" clearable :value-on-clear="null"
          ><el-option
            v-for="v in ['AUTHORIZED', 'EXPIRED', 'REVOKED', 'UNKNOWN']"
            :key="v"
            :label="v"
            :value="v" /></el-select
      ></el-form-item>
      <el-form-item v-if="mode === 'IDS'" label="每页账户数"
        ><el-select v-model="candidateSize"
          ><el-option v-for="v in sizes" :key="v" :label="String(v)" :value="v" /></el-select
      ></el-form-item>
    </el-form>
    <p class="scope-wrap">
      计划拥有者：{{ ownership.owner_user_id }} · 团队：{{ ownership.owner_team_id }}
    </p>
    <div class="scope-actions">
      <el-button
        v-if="mode === 'IDS'"
        :disabled="controlsDisabled || reading"
        @click="queryCandidates"
        >查询账户</el-button
      ><el-button :disabled="controlsDisabled" @click="resetSelection">重新选择</el-button
      ><el-button
        v-if="mode === 'FILTER'"
        type="primary"
        :disabled="controlsDisabled || reading"
        @click="freeze"
        >冻结并核对完整范围</el-button
      ><el-button
        v-if="unknown"
        type="warning"
        :loading="writing"
        :disabled="writing"
        @click="recover"
        >恢复原冻结</el-button
      >
    </div>
    <template v-if="mode === 'IDS'">
      <p role="status">已明确勾选 {{ selectedIds.length }} / 500 个账户</p>
      <el-table
        :data="candidates"
        row-key="id"
        empty-text="点击查询账户读取当前可见候选"
        v-loading="reading"
      >
        <el-table-column label="选择" width="70"
          ><template #default="{ row }"
            ><el-checkbox
              :model-value="selectedIds.includes(row.id)"
              :disabled="
                controlsDisabled ||
                !matchesOwner(row) ||
                (!selectedIds.includes(row.id) && selectedIds.length >= 500)
              "
              :aria-label="`选择账户 ${row.external_id}`"
              @change="toggle(row)" /></template
        ></el-table-column>
        <el-table-column prop="name" label="账户名称" min-width="170" /><el-table-column
          prop="external_id"
          label="平台账户ID"
          min-width="180"
        /><el-table-column prop="currency" label="币种" width="85" /><el-table-column
          prop="account_status"
          label="账户状态"
          min-width="110"
        /><el-table-column prop="auth_status" label="授权状态" min-width="120" /><el-table-column
          label="归属"
          min-width="200"
          ><template #default="{ row }"
            ><span class="scope-wrap"
              >{{ row.ownership.owner_user_id }} / {{ row.ownership.owner_team_id }}</span
            ></template
          ></el-table-column
        >
      </el-table>
      <div class="scope-actions">
        <el-button
          :disabled="controlsDisabled || reading || candidateHistory.length === 0"
          @click="candidatePrevious"
          >上一页账户</el-button
        ><el-button
          :disabled="controlsDisabled || reading || !candidateNext"
          @click="candidateForward"
          >下一页账户</el-button
        >
      </div>
      <el-collapse
        ><el-collapse-item title="查看已选账户（可逐个移除）" name="selected"
          ><div class="scope-actions">
            <el-tag
              v-for="id in selectedIds"
              :key="id"
              :closable="!controlsDisabled"
              @close="remove(id)"
              >{{ known.get(id)?.name ?? '名称尚未读取' }} · {{ id }}</el-tag
            >
          </div></el-collapse-item
        ></el-collapse
      >
    </template>
    <template v-else>
      <el-descriptions v-if="snapshot" :column="1" border
        ><el-descriptions-item label="快照ID">{{ snapshot.id }}</el-descriptions-item
        ><el-descriptions-item label="实际账户数">{{ snapshot.count }}</el-descriptions-item
        ><el-descriptions-item label="权限版本">{{ snapshot.scope_version }}</el-descriptions-item
        ><el-descriptions-item label="成员哈希"
          ><span class="scope-wrap">{{ snapshot.hash }}</span></el-descriptions-item
        ><el-descriptions-item label="冻结时间">{{
          snapshot.created_at
        }}</el-descriptions-item></el-descriptions
      >
      <el-alert
        v-if="snapshot && (snapshot.count < 1 || snapshot.count > 500)"
        title="计划只允许1至500个账户。此快照不会截断，请调整条件后重新冻结。"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="snapshot"
        title="成员搜索仅查看已冻结范围，不改变快照，也不支持从FILTER范围逐个排除。关闭仅取消本地使用，不会删除服务端快照。"
        type="info"
        :closable="false"
      />
      <div v-if="snapshot" class="scope-actions">
        <el-input
          v-model="memberQuery"
          aria-label="已冻结成员搜索"
          placeholder="账户名称前缀或完整平台ID"
          :disabled="controlsDisabled"
        /><el-select v-model="memberSize" aria-label="每页成员数" :disabled="controlsDisabled"
          ><el-option v-for="v in sizes" :key="v" :label="String(v)" :value="v" /></el-select
        ><el-button :disabled="controlsDisabled || reading || invalid" @click="queryMembers"
          >查询成员</el-button
        >
      </div>
      <el-table :data="members" empty-text="尚未读取冻结成员" v-loading="reading"
        ><el-table-column prop="name" label="冻结时账户名称" min-width="180" /><el-table-column
          prop="external_id"
          label="平台账户ID"
          min-width="180" /><el-table-column prop="account_id" label="账户UUID" min-width="300"
      /></el-table>
      <div class="scope-actions">
        <el-button
          :disabled="controlsDisabled || reading || invalid || !memberHistory.length"
          @click="memberPrevious"
          >上一页成员</el-button
        ><el-button
          :disabled="controlsDisabled || reading || invalid || !memberNext"
          @click="memberForward"
          >下一页成员</el-button
        >
      </div>
    </template>
    <template #footer
      ><el-button :disabled="locked" @click="requestClose(false)">取消本地选择</el-button
      ><el-button type="primary" :disabled="!canApply" @click="apply"
        >应用到账户选择</el-button
      ></template
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  launchAccountScopesApi as api,
  type AccountCandidate,
  type PlanAccountSelection,
  type ScopeFilter,
  type ScopeMemberPage,
  type ScopeMutation,
  type ScopeRequest,
  type ScopeSnapshot,
} from '@/api/orbit/launch-account-scopes'
import { LaunchValidationError } from '@/api/orbit/launch-validation'
import type { PlanOwnership } from '@/api/orbit/launch'
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    ownership: PlanOwnership
    selected?: PlanAccountSelection | null
    canRead?: boolean
    disabled?: boolean
    contextKey?: string
  }>(),
  { selected: null, canRead: false, disabled: false, contextKey: '' },
)
const emit = defineEmits<{
  'update:modelValue': [boolean]
  choose: [PlanAccountSelection]
  locked: [boolean]
}>()
const sizes = [20, 50, 100, 200],
  mode = ref<'IDS' | 'FILTER'>('IDS')
const filter = reactive<ScopeFilter>({
  q: '',
  status: null,
  auth_status: null,
  operator_user_id: null,
  vendor_id: null,
})
const selectedIds = ref<string[]>([]),
  known = reactive(new Map<string, AccountCandidate>()),
  candidates = ref<AccountCandidate[]>([])
const snapshot = ref<ScopeSnapshot | null>(null),
  members = ref<ScopeMemberPage['items']>([]),
  memberQuery = ref(''),
  memberSize = ref(50),
  candidateSize = ref(50)
const candidateHistory = ref<(string | null)[]>([]),
  candidateCurrent = ref<string | null>(null),
  candidateNext = ref<string | null>(null)
const memberHistory = ref<(string | null)[]>([]),
  memberCurrent = ref<string | null>(null),
  memberNext = ref<string | null>(null)
const reading = ref(false),
  writing = ref(false),
  unknown = ref(false),
  invalid = ref(false),
  error = ref(''),
  dirty = ref(false)
const locked = computed(() => writing.value || unknown.value),
  controlsDisabled = computed(() => locked.value || props.disabled || !props.canRead)
const canApply = computed(
  () =>
    props.canRead &&
    !props.disabled &&
    !locked.value &&
    !invalid.value &&
    !reading.value &&
    (mode.value === 'IDS'
      ? selectedIds.value.length > 0 && selectedIds.value.length <= 500
      : !!snapshot.value &&
        snapshot.value.count > 0 &&
        snapshot.value.count <= 500 &&
        verified.value),
)
const verified = ref(false)
let epoch = 0,
  controller: AbortController | undefined
let disposed = false
let intent: {
  body: ScopeRequest
  context: ScopeMutation
  fingerprint: string
  actorContext: string
} | null = null
const fingerprint = () => JSON.stringify([props.ownership, props.contextKey, props.canRead])
function stop() {
  epoch++
  controller?.abort()
  controller = undefined
  reading.value = false
}
function matchesOwner(row: AccountCandidate) {
  return (
    row.ownership.owner_user_id === props.ownership.owner_user_id &&
    row.ownership.owner_team_id === props.ownership.owner_team_id
  )
}
function remove(id: string) {
  if (controlsDisabled.value) return
  selectedIds.value = selectedIds.value.filter((x) => x !== id)
  dirty.value = true
}
function toggle(row: AccountCandidate) {
  if (controlsDisabled.value || !matchesOwner(row)) return
  if (selectedIds.value.includes(row.id)) {
    remove(row.id)
    return
  }
  if (selectedIds.value.length >= 500) return
  const currencies = new Set(selectedIds.value.map((id) => known.get(id)?.currency).filter(Boolean))
  if (currencies.size && !currencies.has(row.currency)) {
    error.value = '同一计划只能选择一种币种，请先移除其他币种账户'
    return
  }
  known.set(row.id, row)
  selectedIds.value.push(row.id)
  dirty.value = true
}
function clearCandidates() {
  candidates.value = []
  candidateHistory.value = []
  candidateCurrent.value = null
  candidateNext.value = null
}
function clearMembers() {
  members.value = []
  memberHistory.value = []
  memberCurrent.value = null
  memberNext.value = null
  verified.value = false
}
function resetSelection() {
  if (controlsDisabled.value) return
  stop()
  selectedIds.value = []
  known.clear()
  snapshot.value = null
  clearMembers()
  invalid.value = false
  error.value = ''
  dirty.value = true
}
function failure(cause: unknown, scope = false) {
  if (cause instanceof DOMException && cause.name === 'AbortError') return
  error.value = cause instanceof Error ? cause.message : '读取失败，请重试'
  if (cause instanceof LaunchValidationError && [401, 403, 404, 409, 410].includes(cause.status)) {
    if (scope) {
      invalid.value = true
      clearMembers()
    } else clearCandidates()
    if ([401, 403].includes(cause.status)) {
      invalid.value = true
      known.clear()
    }
  }
}
async function readCandidates(token: string | null, history: (string | null)[]) {
  if (controlsDisabled.value) return
  stop()
  const run = epoch
  controller = new AbortController()
  reading.value = true
  error.value = ''
  try {
    const page = await api.candidates(
      structuredClone({ ...filter, operator_user_id: props.ownership.owner_user_id }),
      candidateSize.value,
      token,
      controller.signal,
    )
    if (run !== epoch) return
    candidates.value = page.items
    for (const row of page.items) known.set(row.id, row)
    candidateCurrent.value = token
    candidateHistory.value = history
    candidateNext.value = page.next_cursor
  } catch (cause) {
    if (run === epoch) failure(cause)
  } finally {
    if (run === epoch) reading.value = false
  }
}
function queryCandidates() {
  if (mode.value !== 'IDS') return
  return readCandidates(null, [])
}
function candidateForward() {
  if (candidateNext.value)
    return readCandidates(candidateNext.value, [...candidateHistory.value, candidateCurrent.value])
}
function candidatePrevious() {
  const h = [...candidateHistory.value],
    token = h.pop()
  if (token !== undefined) return readCandidates(token, h)
}
async function readMembers(token: string | null, history: (string | null)[]) {
  if (controlsDisabled.value || !snapshot.value || invalid.value) return
  stop()
  const run = epoch,
    current = snapshot.value
  controller = new AbortController()
  reading.value = true
  verified.value = false
  error.value = ''
  try {
    const page = await api.members(
      current.id,
      memberQuery.value,
      memberSize.value,
      token,
      controller.signal,
    )
    if (run !== epoch) return
    if (page.scope_version !== current.scope_version)
      throw new LaunchValidationError(409, 'SCOPE_CHANGED', '范围权限版本已变化，请重新冻结')
    members.value = page.items
    memberCurrent.value = token
    memberHistory.value = history
    memberNext.value = page.next_cursor
    verified.value = true
  } catch (cause) {
    if (run === epoch) failure(cause, true)
  } finally {
    if (run === epoch) reading.value = false
  }
}
function queryMembers() {
  return readMembers(null, [])
}
function memberForward() {
  if (memberNext.value)
    return readMembers(memberNext.value, [...memberHistory.value, memberCurrent.value])
}
function memberPrevious() {
  const h = [...memberHistory.value],
    token = h.pop()
  if (token !== undefined) return readMembers(token, h)
}
async function freeze() {
  if (controlsDisabled.value || reading.value) return
  stop()
  writing.value = true
  invalid.value = true
  clearMembers()
  error.value = ''
  const original = fingerprint()
  try {
    controller = new AbortController()
    const cap = await api.capabilities(controller.signal)
    if (disposed || !props.modelValue || original !== fingerprint())
      throw new Error('当前上下文已变化，请重新冻结')
    intent = {
      body: {
        mode: 'FILTER',
        account_ids: [],
        filter: structuredClone({ ...filter, operator_user_id: props.ownership.owner_user_id }),
      },
      context: { csrf_token: cap.csrf_token, idempotency_key: crypto.randomUUID() },
      fingerprint: original,
      actorContext: props.contextKey,
    }
    await writeIntent()
  } catch (cause) {
    failure(cause)
  } finally {
    writing.value = false
  }
}
async function recover() {
  if (!intent || writing.value) return
  if (!props.canRead || intent.actorContext !== props.contextKey) {
    error.value =
      '登录身份或读取权限已变化，请恢复原身份上下文后核对原冻结结果；不能把旧意图转交其他身份'
    return
  }
  writing.value = true
  try {
    await writeIntent()
  } finally {
    writing.value = false
  }
}
async function writeIntent() {
  if (!intent) return
  try {
    const value = await api.create(intent.body, intent.context)
    if (disposed) return
    snapshot.value = value
    unknown.value = false
    invalid.value = intent.fingerprint !== fingerprint()
    intent = null
    clearMembers()
    dirty.value = true
    if (!invalid.value) {
      writing.value = false
      await queryMembers()
    }
  } catch (cause) {
    if (cause instanceof LaunchValidationError && cause.unknown_result) unknown.value = true
    else if (!unknown.value) intent = null
    failure(cause, true)
  }
}
async function apply() {
  if (!canApply.value) return
  if (mode.value === 'IDS') {
    const rows = selectedIds.value.map((id) => known.get(id))
    if (
      rows.some((row) => row && !matchesOwner(row)) ||
      new Set(rows.filter(Boolean).map((row) => row!.currency)).size > 1
    ) {
      invalid.value = true
      error.value = '已选账户归属或币种不一致，请重新选择'
      return
    }
    emit('choose', { kind: 'IDS', account_ids: [...selectedIds.value], snapshot: null })
  } else {
    await queryMembers()
    if (!canApply.value || !snapshot.value) return
    emit('choose', { kind: 'SNAPSHOT', account_ids: [], snapshot: { ...snapshot.value } })
  }
  dirty.value = false
  emit('update:modelValue', false)
}
async function requestClose(value: boolean) {
  if (value || locked.value) return
  if (dirty.value) {
    try {
      await ElMessageBox.confirm('取消本地选择？已冻结的服务端快照仍会保留。', '放弃本次选择', {
        type: 'warning',
        confirmButtonText: '放弃本地选择',
        cancelButtonText: '继续核对',
      })
    } catch {
      return
    }
  }
  dirty.value = false
  stop()
  emit('update:modelValue', false)
}
function beforeClose(done: () => void) {
  void requestClose(false).then(() => {
    if (!locked.value && !dirty.value) done()
  })
}
watch(locked, (value) => emit('locked', value), { immediate: true })
watch(
  () => [
    props.ownership.owner_user_id,
    props.ownership.owner_team_id,
    props.contextKey,
    props.canRead,
  ],
  () => {
    stop()
    clearCandidates()
    clearMembers()
    invalid.value = true
    known.clear()
  },
)
watch(
  () => [filter.q, filter.status, filter.auth_status, candidateSize.value],
  () => {
    stop()
    clearCandidates()
    if (snapshot.value) {
      invalid.value = true
      clearMembers()
    }
  },
)
watch(
  () => [memberQuery.value, memberSize.value],
  () => {
    stop()
    clearMembers()
  },
)
watch(mode, () => {
  stop()
  clearCandidates()
})
watch(
  () => props.modelValue,
  (open) => {
    stop()
    if (!open) return
    error.value = ''
    invalid.value = false
    dirty.value = false
    filter.operator_user_id = props.ownership.owner_user_id
    if (!locked.value) {
      intent = null
      unknown.value = false
      known.clear()
      selectedIds.value = props.selected?.kind === 'IDS' ? [...props.selected.account_ids] : []
      snapshot.value = props.selected?.kind === 'SNAPSHOT' ? { ...props.selected.snapshot } : null
      mode.value = snapshot.value ? 'FILTER' : 'IDS'
      clearCandidates()
      clearMembers()
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  disposed = true
  stop()
  emit('locked', false)
})
</script>

<style scoped>
.scope-filter {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.scope-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 14px 0;
}
.scope-actions :deep(.el-input) {
  max-width: 320px;
}
.scope-actions :deep(.el-select) {
  width: 110px;
}
.scope-wrap {
  overflow-wrap: anywhere;
}
.el-alert + .el-alert {
  margin-top: 12px;
}
:deep(.el-tag) {
  height: auto;
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
