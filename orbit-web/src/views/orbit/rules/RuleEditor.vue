<template>
  <section class="rule-editor" aria-label="规则编辑容器">
    <header class="actions">
      <h2>{{ ruleId ? '编辑规则' : '创建规则' }}</h2>
      <el-button @click="close">{{ pending ? '关闭并保留未确认请求' : '关闭编辑器' }}</el-button>
    </header>
    <p v-if="loading" role="status">正在读取实际编辑上下文与定义…</p>
    <el-alert
      v-if="!permitted"
      title="缺少当前规则创建或编辑动作；不会借用读取或其它菜单权限。"
      type="warning"
      :closable="false"
    />
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <el-alert v-if="saveError" :title="saveError" type="error" :closable="false" />
    <el-alert
      v-if="pending"
      title="存在未确认请求。可以关闭并交父组件保留；不能另发新保存或范围冻结。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="pending && !pendingMatches"
      title="原请求不属于当前认证或规则上下文；不能跨上下文恢复。"
      type="warning"
      :closable="false"
    />
    <div v-if="pending" class="recovery-actions">
      <a href="/login" target="_blank" rel="noopener">在新标签页重新登录</a>
      <p>请保留本页；登录后回此弹窗验证身份，不会自动提交原请求。</p>
      <el-button :loading="recoveryBusy" @click="emit('verifyIdentity')"
        >重新验证当前身份（不提交）</el-button
      >
      <p v-if="recoveryMessage" role="status">{{ recoveryMessage }}</p>
    </div>
    <div class="actions">
      <el-button :disabled="loading || saving || !!pending || !permitted" @click="reload()"
        >重新加载（丢弃未保存修改）</el-button
      ><el-button
        v-if="pending"
        :disabled="loading || saving || !permitted || !pendingMatches"
        @click="refreshRecoveryContext"
        >刷新恢复会话</el-button
      ><el-button
        v-if="pending?.kind === 'SAVE'"
        :disabled="!canRecoverSave"
        :loading="saving"
        @click="recoverSave"
        >使用原保存请求恢复</el-button
      >
      <el-button
        v-if="scopePending"
        :disabled="!pendingMatches || !permitted || loading"
        @click="scopeOpen = true"
        >打开原范围请求</el-button
      >
    </div>
    <el-alert
      v-if="definition && (!editorContext || !contextAgrees)"
      title="以下仅为已保存的定义；当前编辑来源未就绪或发生版本漂移，不能保存。"
      type="warning"
      :closable="false"
    />
    <p v-if="definition && !editableState">
      当前状态 {{ definition.rule.state }} 为只读；启用规则须先回列表暂停，归档规则不能编辑。
    </p>
    <p v-if="editorContext?.selected_profile">
      保存绑定版本 {{ editorContext.selected_profile.bound_version }} · 当前
      {{ editorContext.selected_profile.current?.version ?? '不可用' }} ·
      {{
        editorContext.selected_profile.status
      }}。版本变化后保存会由服务器重新绑定真实当前配置，须重新模拟。
    </p>
    <p v-if="savedResult">
      已取得保存回执 {{ savedResult.id }} · 版本 {{ savedResult.revision }} ·
      {{ savedResult.state }}。当前状态请重新读取。
    </p>
    <template v-if="seed && !accessDenied && (!pending || pendingMatches)">
      <div class="candidate-tools">
        <section>
          <h3>归属候选</h3>
          <el-input
            v-model="ownerQ"
            aria-label="规则归属姓名前缀"
            placeholder="按真实显示名称前缀加载"
            :disabled="locked"
            @keyup.enter="searchOwners"
          />
          <div class="actions">
            <el-button :disabled="locked || ownersLoading || !contextAgrees" @click="searchOwners"
              >加载归属候选</el-button
            ><el-select
              v-model="ownerSize"
              aria-label="归属每页条数"
              :disabled="locked"
              @change="searchOwners"
              ><el-option v-for="n in sizes" :key="n" :value="n" :label="`${n} 条`" /></el-select
            ><el-button
              :disabled="locked || ownersLoading || !ownerHistory.length"
              @click="ownerPrevious"
              >上一页归属</el-button
            ><el-button
              :disabled="locked || ownersLoading || !ownerPage?.next_cursor"
              @click="ownerNext"
              >下一页归属</el-button
            >
          </div>
          <p v-if="ownersError" role="alert">{{ ownersError }}</p>
        </section>
        <section>
          <h3>指标配置候选</h3>
          <p>
            原配置没有名称；按实际source / version /
            完整ID选择。分页加载保留已加载项，避免更改尚未保存的选择。
          </p>
          <div class="actions">
            <el-button
              :disabled="locked || profilesLoading || !contextAgrees"
              @click="searchProfiles"
              >加载指标候选</el-button
            ><el-button
              :disabled="locked || profilesLoading || !editorContext?.selected_profile"
              @click="locateStoredProfile"
              >定位已保存配置</el-button
            ><el-select
              v-model="profileSize"
              aria-label="指标每页条数"
              :disabled="locked"
              @change="searchProfiles"
              ><el-option v-for="n in sizes" :key="n" :value="n" :label="`${n} 条`" /></el-select
            ><el-button
              :disabled="locked || profilesLoading || !profileHistory.length"
              @click="profilePrevious"
              >上一页指标</el-button
            ><el-button
              :disabled="locked || profilesLoading || !profilePage?.next_cursor"
              @click="profileNext"
              >下一页指标</el-button
            >
          </div>
          <p v-if="profilesError" role="alert">{{ profilesError }}</p>
        </section>
      </div>
      <div class="actions">
        <el-input
          v-model="manualTimezone"
          aria-label="补充IANA时区"
          placeholder="明确输入IANA时区，例如Europe/Paris"
          :disabled="locked || !canEdit"
        /><el-button :disabled="locked || !canEdit" @click="addTimezone">加入时区候选</el-button
        ><span v-if="timezoneError" role="alert">{{ timezoneError }}</span>
      </div>
      <RuleDefinitionForm
        :key="formGeneration"
        :model-value="seed"
        :owner-options="ownerOptions"
        :profile-options="profileOptions"
        :scope="scopeForForm"
        :saved-context="savedContext"
        :timezones="timezoneOptions"
        :defaults="defaults"
        :field-errors="fieldErrors"
        :read-only="!canEdit"
        :disabled="locked || !!savedResult"
        :busy="saving"
        :owners-loading="ownersLoading"
        :profiles-loading="profilesLoading"
        :owners-error="ownersError"
        :profiles-error="profilesError"
        @ownership-change="ownershipChanged"
        @choose-scope="openScope"
        @submit="save"
        @cancel="close"
      >
        <template #schedule-preview="{ schedule }">
          <RuleSchedulePreview
            :action="action"
            :rule-id="ruleId"
            :rule-revision="editorContext?.rule_revision ?? null"
            :schedule="schedule"
            :csrf-token="editorContext?.csrf_token ?? ''"
            :context-key="JSON.stringify([contextKey, activeOwnership])"
            :permission-codes="permissionCodes"
            :disabled="
              locked ||
              !canEdit ||
              ownersLoading ||
              profilesLoading ||
              !!ownersError ||
              !!profilesError ||
              !!savedResult
            "
            @access-denied="deny"
          />
        </template>
      </RuleDefinitionForm>
      <p v-if="recoveredScope && !sameOwner(recoveredScope.ownership, activeOwnership)">
        原范围回执已恢复，但拥有者与当前表单不同；请先明确选择原拥有者，不能自动转移或应用。
      </p>
    </template>
    <RuleScopeSelector
      v-if="scopeOpen || scopePending"
      :model-value="scopeOpen"
      :action="action"
      :native-actor-id="nativeActorId"
      :rule-id="ruleId"
      :ownership="scopeOwnership"
      :current-rule-revision="editorContext?.rule_revision ?? null"
      :csrf-token="editorContext?.csrf_token ?? ''"
      :permission-codes="permissionCodes"
      :context-key="contextKey"
      :disabled="
        saving || pending?.kind === 'SAVE' || (!scopePending && (accessDenied || !editorContext))
      "
      :pending-intent="scopePending"
      :remote-options="true"
      @update:model-value="scopeOpen = $event"
      @pending-intent="scopePendingChanged"
      :recovery-busy="recoveryBusy"
      :recovery-message="recoveryMessage"
      @verify-identity="emit('verifyIdentity')"
      @choose="scopeChosen"
    />
  </section>
</template>

<script setup lang="ts">
import {
  ruleRecoveryApi,
  recoveryPrincipal,
  requireRecoveryPrincipal,
  requireInitialRuleActor,
  type RuleRecoveryPrincipal,
} from '@/api/orbit/rule-recovery'
import { refreshCookieCsrfForRecovery } from '@/api/orbit/authentication'

import { computed, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import RuleDefinitionForm from './RuleDefinitionForm.vue'
import RuleScopeSelector from './RuleScopeSelector.vue'
import RuleSchedulePreview from './RuleSchedulePreview.vue'
import {
  RuleApiError,
  parseRuleWrite,
  rulesApi,
  type Rule,
  type RuleWrite,
} from '@/api/orbit/rules'
import {
  ruleEditorApi,
  type RuleEditorContext,
  type RuleEditorPage,
  type RuleEditorTarget,
  type RuleOwnerOption,
} from '@/api/orbit/rule-editor'
import {
  ruleEditorDefinitionApi,
  type RuleEditorDefinition,
} from '@/api/orbit/rule-editor-definition'
import type { MetricProfile } from '@/api/orbit/metric-profiles'
import type { FrozenRuleEditorScopeIntent, ScopeSnapshot } from '@/api/orbit/rule-editor-scopes'
import type { PlanHttpFieldError } from '@/api/orbit/launch-validation'
type SaveIntent = {
  principal: RuleRecoveryPrincipal | null
  context: string
  action: 'CREATE' | 'UPDATE'
  ruleId: string | null
  body: RuleWrite
  key: string
  ifMatch: string | null
}
type ScopePending = {
  principal: RuleRecoveryPrincipal | null
  intent: FrozenRuleEditorScopeIntent
  context: string
}
type Pending = { kind: 'SAVE'; intent: SaveIntent } | { kind: 'SCOPE'; intent: ScopePending }
type ScopeForForm = {
  id: string
  label: string
  count: number
  owner_user_id: string
  owner_team_id: string
}
const props = withDefaults(
  defineProps<{
    ruleId: string | null
    contextKey: string
    nativeActorId?: number | null
    permissionCodes?: string[]
    defaults?: { timezone: string; start_date: string; end_date: string }
    timezones?: { value: string; label: string }[]
    recoveryBusy?: boolean
    recoveryMessage?: string
    pendingIntent?: Pending | null
  }>(),
  {
    recoveryBusy: false,
    recoveryMessage: '',
    nativeActorId: null,
    permissionCodes: () => [],
    timezones: () => [],
    pendingIntent: null,
  },
)
const emit = defineEmits<{
  verifyIdentity: []
  saved: [Rule]
  close: []
  pendingIntent: [Pending | null]
}>()
const sizes = [20, 50, 100, 200],
  action = computed(() => (props.ruleId ? 'UPDATE' : 'CREATE'))
const identity = () => JSON.stringify([props.contextKey, props.ruleId])
const permitted = computed(
  () =>
    props.permissionCodes.includes('*:*:*') ||
    props.permissionCodes.includes(props.ruleId ? 'rules.edit' : 'rules.create'),
)
const editorContext = ref<RuleEditorContext | null>(null),
  definition = ref<RuleEditorDefinition | null>(null),
  seed = ref<RuleWrite | null>(null),
  formGeneration = ref(0),
  activeOwnership = ref<RuleWrite['ownership']>({ owner_user_id: '', owner_team_id: '' })
const loading = ref(false),
  loadError = ref(''),
  accessDenied = ref(false),
  contextAgrees = ref(false),
  saving = ref(false),
  saveError = ref(''),
  savedResult = ref<Rule | null>(null),
  fieldErrors = ref<PlanHttpFieldError[]>([])
const pending = shallowRef<Pending | null>(props.pendingIntent)
const pendingMatches = computed(() => {
  const value = pending.value
  if (!value) return true
  if (value.kind === 'SAVE')
    return (
      value.intent.context === identity() &&
      value.intent.ruleId === props.ruleId &&
      value.intent.action === action.value
    )
  const body = value.intent.intent.body
  return (
    body.action === action.value &&
    body.rule_id === props.ruleId &&
    value.intent.context ===
      JSON.stringify([
        props.contextKey,
        action.value,
        props.ruleId,
        body.ownership.owner_user_id,
        body.ownership.owner_team_id,
      ])
  )
})
const scopeOpen = ref(false),
  scopeForForm = ref<ScopeForForm | null>(null),
  scopeTarget = ref<RuleWrite['ownership'] | null>(
    pending.value?.kind === 'SCOPE' ? { ...pending.value.intent.intent.body.ownership } : null,
  ),
  recoveredScope = ref<{
    snapshot: ScopeSnapshot
    ownership: RuleWrite['ownership']
    revision: number | null
  } | null>(null)
const scopePending = computed(() => (pending.value?.kind === 'SCOPE' ? pending.value.intent : null))
const scopeOwnership = computed(
  () => scopePending.value?.intent.body.ownership ?? scopeTarget.value ?? activeOwnership.value,
)
const editableState = computed(
  () => !definition.value || ['DRAFT', 'PAUSED'].includes(definition.value.rule.state),
)
const canEdit = computed(
  () =>
    permitted.value &&
    !!editorContext.value &&
    contextAgrees.value &&
    editorContext.value.editable &&
    editableState.value &&
    !accessDenied.value,
)
const locked = computed(
  () => loading.value || saving.value || !!pending.value || accessDenied.value,
)
const canRecoverSave = computed(
  () =>
    pending.value?.kind === 'SAVE' &&
    pendingMatches.value &&
    permitted.value &&
    !loading.value &&
    !saving.value,
)
const owners = reactive(new Map<string, RuleOwnerOption & { available?: boolean }>()),
  profiles = reactive(
    new Map<string, { id: string; label: string; version: string; available?: boolean }>(),
  )
const ownerOptions = computed(() => [...owners.values()]),
  profileOptions = computed(() => [...profiles.values()])
const savedContext = computed(() => {
  const c = editorContext.value
  if (!c?.selected_owner.item || !c.selected_profile || !definition.value) return null
  return {
    owner: { ...c.selected_owner.item, available: c.selected_owner.can_keep },
    profile: {
      id: c.selected_profile.id,
      version: c.selected_profile.bound_version,
      label: `已保存版本 ${c.selected_profile.bound_version} · ${c.selected_profile.id}`,
      available: c.selected_profile.status === 'CURRENT',
    },
  }
})
const ownerPage = ref<RuleEditorPage<RuleOwnerOption> | null>(null),
  profilePage = ref<RuleEditorPage<MetricProfile> | null>(null),
  ownersLoading = ref(false),
  profilesLoading = ref(false),
  ownersError = ref(''),
  profilesError = ref('')
const ownerQ = ref(''),
  appliedOwnerQ = ref(''),
  ownerSize = ref<20 | 50 | 100 | 200>(50),
  appliedOwnerSize = ref<20 | 50 | 100 | 200>(50),
  ownerCursor = ref<string | undefined>(),
  ownerHistory = ref<(string | undefined)[]>([])
const profileQ = ref(''),
  appliedProfileQ = ref(''),
  profileSize = ref<20 | 50 | 100 | 200>(50),
  appliedProfileSize = ref<20 | 50 | 100 | 200>(50),
  profileCursor = ref<string | undefined>(),
  profileHistory = ref<(string | undefined)[]>([])
const manualTimezone = ref(''),
  timezoneError = ref(''),
  addedTimezones = reactive(new Set<string>())
const timezoneOptions = computed(() => {
  const result = new Map(props.timezones.map((item) => [item.value, item]))
  for (const value of [
    definition.value?.rule.schedule.timezone,
    props.defaults?.timezone,
    ...addedTimezones,
  ])
    if (value && !result.has(value))
      result.set(value, { value, label: `${value}（已保存或明确指定）` })
  return [...result.values()]
})
let loadEpoch = 0,
  ownerEpoch = 0,
  profileEpoch = 0,
  saveEpoch = 0
let loadAbort: AbortController | undefined,
  ownerAbort: AbortController | undefined,
  profileAbort: AbortController | undefined,
  saveAbort: AbortController | undefined
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v))
const sameOwner = (a: RuleWrite['ownership'], b: RuleWrite['ownership']) =>
  a.owner_user_id === b.owner_user_id && a.owner_team_id === b.owner_team_id
const target = (): RuleEditorTarget =>
  props.ruleId ? { action: 'UPDATE', rule_id: props.ruleId } : { action: 'CREATE' }
const failed = (e: unknown) =>
  e instanceof RuleApiError ? `${e.message}（${e.code}）` : '编辑来源读取失败，请重新加载。'
const authFailure = (e: unknown) => e instanceof RuleApiError && [401, 403].includes(e.status)
const aborted = (e: unknown) => e instanceof Error && e.name === 'AbortError'
function notify(value: Pending | null) {
  pending.value = value
  emit('pendingIntent', value)
}
function stopReads() {
  ++loadEpoch
  ++ownerEpoch
  ++profileEpoch
  loadAbort?.abort()
  ownerAbort?.abort()
  profileAbort?.abort()
  loading.value = false
  ownersLoading.value = false
  profilesLoading.value = false
}
function clearData() {
  editorContext.value = null
  definition.value = null
  seed.value = null
  contextAgrees.value = false
  owners.clear()
  profiles.clear()
  ownerPage.value = null
  profilePage.value = null
  ownerHistory.value = []
  profileHistory.value = []
  ownerCursor.value = undefined
  profileCursor.value = undefined
  scopeForForm.value = null
  recoveredScope.value = null
  scopeOpen.value = false
  fieldErrors.value = []
  savedResult.value = null
  activeOwnership.value = { owner_user_id: '', owner_team_id: '' }
}
function deny(e: unknown) {
  stopReads()
  clearData()
  accessDenied.value = true
  loadError.value = failed(e)
}
defineExpose({
  hideSensitiveForRecovery: () =>
    deny(
      new RuleApiError(
        403,
        'RULE_RECOVERY_REVALIDATION_REQUIRED',
        '请验证当前身份后手动恢复原请求',
      ),
    ),
})
function writeOf(rule: Rule): RuleWrite {
  const {
    name,
    ownership,
    target_level,
    scope_snapshot_id,
    logic,
    groups,
    window,
    metric_profile_id,
    schedule,
    cooldown_minutes,
    max_daily,
  } = rule
  return parseRuleWrite({
    name,
    ownership,
    target_level,
    scope_snapshot_id,
    logic,
    groups,
    window,
    metric_profile_id,
    schedule,
    cooldown_minutes,
    max_daily,
  })
}
function createSeed(c: RuleEditorContext): RuleWrite {
  return {
    name: '新建规则',
    ownership: { ...c.default_ownership },
    target_level: 'AD',
    scope_snapshot_id: '',
    logic: 'AND',
    groups: [{ logic: 'AND', conditions: [{ metric: 'spend', operator: 'GTE', threshold: '' }] }],
    window: 'LAST_3D',
    metric_profile_id: '',
    schedule: {
      frequency: 'INTERVAL',
      interval_minutes: 30,
      time_of_day: null,
      weekday: null,
      timezone: props.defaults?.timezone ?? '',
      start_date: props.defaults?.start_date ?? '',
      end_date: props.defaults?.end_date ?? '',
    },
    cooldown_minutes: 60,
    max_daily: 5,
  }
}
function profileOption(p: MetricProfile) {
  return {
    id: p.id,
    version: p.version,
    label: `${p.source} / ${p.version} / ${p.id}`,
    available: true,
  }
}
async function reload(allowPending = false) {
  if (!permitted.value || (pending.value && !allowPending)) return
  stopReads()
  clearData()
  accessDenied.value = false
  loadError.value = ''
  saveError.value = ''
  savedResult.value = null
  const token = loadEpoch,
    started = identity()
  loadAbort = new AbortController()
  loading.value = true
  const [c, d] = await Promise.allSettled([
    ruleEditorApi.context(target(), loadAbort.signal),
    props.ruleId
      ? ruleEditorDefinitionApi.get(props.ruleId, loadAbort.signal)
      : Promise.resolve(null),
  ])
  if (token !== loadEpoch || started !== identity()) return
  for (const result of [c, d])
    if (result.status === 'rejected' && authFailure(result.reason)) {
      deny(result.reason)
      return
    }
  const errors = [c, d]
    .filter((result) => result.status === 'rejected')
    .map((result) => failed((result as PromiseRejectedResult).reason))
  loadError.value = errors.join('；')
  editorContext.value = c.status === 'fulfilled' ? c.value : null
  definition.value = d.status === 'fulfilled' ? d.value : null
  const context = editorContext.value,
    existing = definition.value
  contextAgrees.value =
    !!context &&
    (props.ruleId
      ? !!existing &&
        existing.rule.id === props.ruleId &&
        context.rule_id === props.ruleId &&
        existing.rule.revision === context.rule_revision &&
        sameOwner(existing.rule.ownership, context.default_ownership) &&
        existing.rule.metric_profile_id === context.selected_profile?.id &&
        context.editable === ['DRAFT', 'PAUSED'].includes(existing.rule.state)
      : context.action === 'CREATE')
  if (context && existing && !contextAgrees.value)
    loadError.value = '规则版本或归属在读取期间变化（409 EDITOR_CONTEXT_CHANGED），请显式重新加载。'
  if (existing) {
    seed.value = writeOf(existing.rule)
    scopeForForm.value = { ...existing.stored_scope, label: '已保存范围，保存时重新校验权限' }
  } else if (!props.ruleId && context) seed.value = createSeed(context)
  if (seed.value) activeOwnership.value = { ...seed.value.ownership }
  if (context?.selected_owner.item)
    owners.set(context.selected_owner.item.id, {
      ...context.selected_owner.item,
      available: context.selected_owner.can_keep,
    })
  if (context?.selected_profile?.current)
    profiles.set(
      context.selected_profile.current.id,
      profileOption(context.selected_profile.current),
    )
  formGeneration.value++
  loading.value = false
  if (contextAgrees.value && context?.editable) {
    searchOwners()
    searchProfiles()
  }
}
async function refreshRecoveryContext() {
  if (!pending.value || !pendingMatches.value || !permitted.value || saving.value) return
  stopReads()
  const token = loadEpoch,
    started = identity()
  loadAbort = new AbortController()
  loading.value = true
  loadError.value = ''
  try {
    const value = await ruleEditorApi.context(target(), loadAbort.signal)
    if (token === loadEpoch && started === identity()) {
      editorContext.value = value
      accessDenied.value = false
    }
  } catch (e) {
    if (token === loadEpoch && !aborted(e)) {
      if (authFailure(e)) deny(e)
      else loadError.value = failed(e)
    }
  } finally {
    if (token === loadEpoch) loading.value = false
  }
}
async function loadOwners() {
  if (!contextAgrees.value || !permitted.value || locked.value) return
  ownerAbort?.abort()
  const token = ++ownerEpoch,
    started = identity()
  ownerAbort = new AbortController()
  ownersLoading.value = true
  ownersError.value = ''
  try {
    const result = await ruleEditorApi.options(
      {
        ...target(),
        kind: 'OWNER',
        q: appliedOwnerQ.value,
        page_size: appliedOwnerSize.value,
        ...(ownerCursor.value ? { cursor: ownerCursor.value } : {}),
      },
      ownerAbort.signal,
    )
    if (token === ownerEpoch && started === identity()) {
      ownerPage.value = result
      for (const item of result.items) owners.set(item.id, { ...item, available: true })
    }
  } catch (e) {
    if (token === ownerEpoch && !aborted(e)) {
      if (authFailure(e)) deny(e)
      else {
        ownersError.value = failed(e)
        if (e instanceof RuleApiError && e.status === 409)
          for (const [id, item] of owners) owners.set(id, { ...item, available: false })
      }
    }
  } finally {
    if (token === ownerEpoch) ownersLoading.value = false
  }
}
function searchOwners() {
  appliedOwnerQ.value = ownerQ.value
  appliedOwnerSize.value = ownerSize.value
  ownerCursor.value = undefined
  ownerHistory.value = []
  void loadOwners()
}
function ownerNext() {
  if (!ownerPage.value?.next_cursor) return
  ownerHistory.value.push(ownerCursor.value)
  ownerCursor.value = ownerPage.value.next_cursor
  void loadOwners()
}
function ownerPrevious() {
  if (!ownerHistory.value.length) return
  ownerCursor.value = ownerHistory.value.pop()
  void loadOwners()
}
async function loadProfiles() {
  if (
    !contextAgrees.value ||
    !permitted.value ||
    locked.value ||
    !activeOwnership.value.owner_user_id
  )
    return
  profileAbort?.abort()
  const token = ++profileEpoch,
    started = JSON.stringify([identity(), activeOwnership.value])
  profileAbort = new AbortController()
  profilesLoading.value = true
  profilesError.value = ''
  try {
    const result = await ruleEditorApi.options(
      {
        ...target(),
        kind: 'PROFILE',
        ...activeOwnership.value,
        q: appliedProfileQ.value,
        page_size: appliedProfileSize.value,
        ...(profileCursor.value ? { cursor: profileCursor.value } : {}),
      },
      profileAbort.signal,
    )
    if (token === profileEpoch && started === JSON.stringify([identity(), activeOwnership.value])) {
      profilePage.value = result
      for (const item of result.items) profiles.set(item.id, profileOption(item))
    }
  } catch (e) {
    if (token === profileEpoch && !aborted(e)) {
      if (authFailure(e)) deny(e)
      else {
        profilesError.value = failed(e)
        if (e instanceof RuleApiError && e.status === 409)
          for (const [id, item] of profiles) profiles.set(id, { ...item, available: false })
      }
    }
  } finally {
    if (token === profileEpoch) profilesLoading.value = false
  }
}
function searchProfiles() {
  appliedProfileQ.value = profileQ.value
  appliedProfileSize.value = profileSize.value
  profileCursor.value = undefined
  profileHistory.value = []
  void loadProfiles()
}
function locateStoredProfile() {
  if (!editorContext.value?.selected_profile) return
  profileQ.value = editorContext.value.selected_profile.id
  searchProfiles()
}
function profileNext() {
  if (!profilePage.value?.next_cursor) return
  profileHistory.value.push(profileCursor.value)
  profileCursor.value = profilePage.value.next_cursor
  void loadProfiles()
}
function profilePrevious() {
  if (!profileHistory.value.length) return
  profileCursor.value = profileHistory.value.pop()
  void loadProfiles()
}
function ownershipChanged(value: RuleWrite['ownership']) {
  activeOwnership.value = { ...value }
  scopeForForm.value = null
  profiles.clear()
  profilePage.value = null
  profileQ.value = ''
  profileHistory.value = []
  profileCursor.value = undefined
  if (
    recoveredScope.value &&
    sameOwner(recoveredScope.value.ownership, value) &&
    recoveredScope.value.revision === editorContext.value?.rule_revision
  )
    scopeForForm.value = {
      id: recoveredScope.value.snapshot.id,
      count: recoveredScope.value.snapshot.count,
      ...value,
      label: '已恢复并核对的真实冻结范围',
    }
  searchProfiles()
}
function openScope(ownership: RuleWrite['ownership']) {
  if (!canEdit.value || saving.value || pending.value?.kind === 'SAVE') return
  activeOwnership.value = { ...ownership }
  scopeTarget.value = { ...ownership }
  scopeOpen.value = true
}
function scopePendingChanged(value: ScopePending | null) {
  if (value) {
    scopeTarget.value = { ...value.intent.body.ownership }
    notify({ kind: 'SCOPE', intent: value })
  } else if (pending.value?.kind === 'SCOPE') notify(null)
}
function scopeChosen(value: ScopeSnapshot) {
  const ownership = { ...scopeOwnership.value }
  recoveredScope.value = {
    snapshot: { ...value },
    ownership,
    revision: editorContext.value?.rule_revision ?? null,
  }
  if (sameOwner(ownership, activeOwnership.value))
    scopeForForm.value = {
      id: value.id,
      count: value.count,
      ...ownership,
      label: '已核对的真实冻结范围',
    }
  scopeOpen.value = false
}
function addTimezone() {
  try {
    const value = manualTimezone.value.trim()
    if (!/^[A-Za-z0-9_+./-]{1,64}$/.test(value)) throw new Error()
    new Intl.DateTimeFormat('en', { timeZone: value })
    addedTimezones.add(value)
    timezoneError.value = ''
    manualTimezone.value = ''
  } catch {
    timezoneError.value = '请输入浏览器可识别的IANA时区；最终由服务器复核。'
  }
}
function freezeBody(value: RuleWrite): RuleWrite {
  const body = parseRuleWrite(value)
  for (const group of body.groups) {
    group.conditions.forEach(Object.freeze)
    Object.freeze(group.conditions)
    Object.freeze(group)
  }
  Object.freeze(body.groups)
  Object.freeze(body.ownership)
  Object.freeze(body.schedule)
  return Object.freeze(body)
}
async function sendSave(intent: SaveIntent, recovering: boolean) {
  if (
    intent.context !== identity() ||
    !permitted.value ||
    (!recovering && (!editorContext.value || accessDenied.value)) ||
    saving.value
  )
    return
  const token = ++saveEpoch
  saveAbort = new AbortController()
  saving.value = true
  saveError.value = ''
  fieldErrors.value = []
  let attempted = false
  try {
    const current = await ruleRecoveryApi.get(intent.action, saveAbort.signal)
    if (token !== saveEpoch || intent.context !== identity()) return
    if (recovering) requireRecoveryPrincipal(intent.principal, current)
    else {
      requireInitialRuleActor(props.nativeActorId, current)
      intent = Object.freeze({ ...intent, principal: recoveryPrincipal(current) })
      notify({ kind: 'SAVE', intent })
    }
    refreshCookieCsrfForRecovery(current.csrf_token)
    const auth = { csrf_token: current.csrf_token, idempotency_key: intent.key }
    attempted = true
    const result =
      intent.action === 'CREATE'
        ? await rulesApi.create(intent.body, auth, saveAbort.signal)
        : await rulesApi.update(
            intent.ruleId!,
            intent.body,
            { ...auth, if_match: intent.ifMatch! },
            saveAbort.signal,
          )
    if (token !== saveEpoch || intent.context !== identity()) return
    if (
      (intent.action === 'UPDATE' && result.id !== intent.ruleId) ||
      JSON.stringify(writeOf(result)) !== JSON.stringify(intent.body)
    )
      throw new RuleApiError(
        502,
        'INVALID_RESPONSE',
        '保存回执与原业务意图不一致',
        [],
        false,
        null,
        true,
      )
    notify(null)
    savedResult.value = result
    emit('saved', result)
  } catch (e) {
    if (token !== saveEpoch) return
    if (authFailure(e)) deny(e)
    saveError.value = failed(e)
    fieldErrors.value = e instanceof RuleApiError ? e.field_errors : []
    const unknown = recovering || (attempted && (!(e instanceof RuleApiError) || e.unknown_result))
    if (unknown) notify({ kind: 'SAVE', intent })
    else notify(null)
  } finally {
    if (token === saveEpoch) saving.value = false
  }
}
function save(value: RuleWrite) {
  if (
    !canEdit.value ||
    locked.value ||
    !scopeForForm.value ||
    savedResult.value ||
    ownersLoading.value ||
    profilesLoading.value ||
    ownersError.value ||
    profilesError.value
  )
    return
  try {
    const body = freezeBody(value),
      scope = scopeForForm.value,
      owner = owners.get(body.ownership.owner_user_id),
      profile = profiles.get(body.metric_profile_id)
    if (
      !owner ||
      owner.available === false ||
      owner.team_id !== body.ownership.owner_team_id ||
      !profile ||
      profile.available === false ||
      body.scope_snapshot_id !== scope.id ||
      !sameOwner(body.ownership, scope) ||
      !sameOwner(body.ownership, activeOwnership.value)
    )
      throw new RuleApiError(
        422,
        'FIELD_VALIDATION_FAILED',
        '请重新确认真实归属、指标配置及完整范围',
      )
    const intent = Object.freeze({
      principal: null,
      context: identity(),
      action: action.value,
      ruleId: props.ruleId,
      body,
      key: crypto.randomUUID(),
      ifMatch: props.ruleId ? `"${editorContext.value!.rule_revision}"` : null,
    })
    void sendSave(intent, false)
  } catch (e) {
    saveError.value = failed(e)
    fieldErrors.value = e instanceof RuleApiError ? e.field_errors : []
  }
}
function recoverSave() {
  if (canRecoverSave.value && pending.value?.kind === 'SAVE')
    void sendSave(pending.value.intent, true)
}
function interruptSave() {
  if (!saving.value) return
  ++saveEpoch
  saveAbort?.abort()
  saving.value = false
}
function close() {
  interruptSave()
  stopReads()
  emit('close')
}
watch(
  () => props.pendingIntent,
  (value) => {
    if (value && value !== pending.value) pending.value = value
  },
)
watch(
  () => [props.contextKey, props.ruleId, [...props.permissionCodes].sort().join('|')],
  () => {
    interruptSave()
    stopReads()
    clearData()
    accessDenied.value = false
    if (!pending.value) void reload()
    else if (pendingMatches.value) {
      if (pending.value.kind === 'SCOPE') void reload(true)
      else void refreshRecoveryContext()
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  interruptSave()
  stopReads()
})
</script>

<style scoped>
.rule-editor {
  padding: 20px;
}
h2 {
  font-size: 20px;
  margin: 0;
}
h3 {
  font-size: 16px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 16px 0;
}
.actions .el-select {
  width: 130px;
}
.actions .el-input {
  width: 300px;
}
.candidate-tools {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.el-alert {
  margin: 12px 0;
}
p {
  overflow-wrap: anywhere;
}
@media (max-width: 750px) {
  .rule-editor {
    padding: 12px;
  }
  .candidate-tools {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .actions .el-input {
    width: 100%;
  }
}
</style>
