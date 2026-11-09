<template>
  <el-dialog
    :model-value="modelValue"
    title="选择规则账户范围"
    width="min(1000px, 96vw)"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!locked"
    :show-close="!locked"
    @opened="focusSearch"
    @closed="restoreFocus"
    @update:model-value="requestClose"
  >
    <el-alert
      title="规则支持1至50000个账户。跨页全选由服务器冻结完整过滤结果，不下载全量ID；最终保存仍复核双方权限。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="!permitted"
      title="缺少当前规则创建或编辑动作，不能读取或冻结账户范围。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="!validContext"
      title="缺少真实拥有者、编辑上下文或当前规则版本，请先重新加载编辑上下文。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="pending"
      title="存在未确认冻结意图。可关闭并保留，不能另发新的范围冻结；恢复必须使用原请求。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="pending && pending.context !== fingerprint()"
      title="原请求所属认证或规则上下文已变化。请恢复原上下文后手动恢复；此处不展示旧对象数据。"
      type="warning"
      :closable="false"
    />
    <el-alert v-if="accessDenied" :title="accessError" type="error" :closable="false" />
    <el-button
      v-if="accessDenied && !pending"
      :disabled="!permitted || disabled || !validContext"
      @click="recheckAccess"
      >重新验证当前访问</el-button
    >
    <template v-if="!pending || pending.context === fingerprint()">
      <p class="wrap">
        规则拥有者 {{ ownership.owner_user_id }} · 团队 {{ ownership.owner_team_id }}
      </p>
      <el-form label-position="top" :disabled="controlsDisabled" class="filters">
        <el-form-item label="选择方式"
          ><el-radio-group v-model="mode" aria-label="范围选择方式"
            ><el-radio-button value="IDS">明确勾选账户</el-radio-button
            ><el-radio-button value="FILTER">全选过滤结果</el-radio-button></el-radio-group
          ></el-form-item
        >
        <el-form-item label="账户名称或完整平台ID"
          ><el-input
            ref="searchInput"
            v-model="filter.q"
            aria-label="规则账户搜索"
            clearable
            @keyup.enter="searchCandidates"
        /></el-form-item>
        <el-form-item label="账户状态"
          ><el-select
            v-model="filter.status"
            aria-label="规则账户状态"
            clearable
            :value-on-clear="null"
            ><el-option
              v-for="s in ['ACTIVE', 'DISABLED', 'UNKNOWN']"
              :key="s"
              :value="s"
              :label="s" /></el-select
        ></el-form-item>
        <el-form-item label="授权状态"
          ><el-select
            v-model="filter.auth_status"
            aria-label="规则账户授权状态"
            clearable
            :value-on-clear="null"
            ><el-option
              v-for="s in ['AUTHORIZED', 'EXPIRED', 'REVOKED', 'UNKNOWN']"
              :key="s"
              :value="s"
              :label="s" /></el-select
        ></el-form-item>
        <el-form-item label="操作者"
          ><el-select
            :model-value="filter.operator_user_id"
            @update:model-value="selectFilterOption('OPERATOR', $event)"
            aria-label="规则账户操作者"
            clearable
            :value-on-clear="null"
            :disabled="
              !operatorDisplay.length ||
              (remoteOptions && (optionStates.OPERATOR.loading || !!optionStates.OPERATOR.error))
            "
            :placeholder="operatorDisplay.length ? '请选择操作者' : '尚无真实候选'"
            ><el-option
              v-for="o in operatorDisplay"
              :key="o.id"
              :value="o.id"
              :label="`${o.label} · ${o.id}`" /></el-select
        ></el-form-item>
        <el-form-item label="户商"
          ><el-select
            :model-value="filter.vendor_id"
            @update:model-value="selectFilterOption('VENDOR', $event)"
            aria-label="规则账户户商"
            clearable
            :value-on-clear="null"
            :disabled="
              !vendorDisplay.length ||
              (remoteOptions && (optionStates.VENDOR.loading || !!optionStates.VENDOR.error))
            "
            :placeholder="vendorDisplay.length ? '请选择户商' : '尚无真实候选'"
            ><el-option
              v-for="o in vendorDisplay"
              :key="o.id"
              :value="o.id"
              :label="`${o.label} · ${o.id}`" /></el-select
        ></el-form-item>
      </el-form>
      <section v-if="remoteOptions" aria-label="远程筛选候选" class="remote-options">
        <p>
          候选按规则拥有者与当前账号的完整账户交集读取，与下方其它账户筛选独立。分页不是全量；已选项跨页保留，最终冻结仍重新核验。
        </p>
        <div v-for="kind in optionKinds" :key="kind" class="remote-option-panel">
          <h3>{{ optionTitle(kind) }}候选</h3>
          <el-input
            v-model="optionStates[kind].q"
            :aria-label="`${optionTitle(kind)}候选搜索`"
            placeholder="真实名称前缀或完整UUID"
            :disabled="controlsDisabled"
            @keyup.enter="searchOptions(kind)"
          />
          <div class="actions">
            <el-button
              :disabled="controlsDisabled || optionStates[kind].loading"
              @click="searchOptions(kind)"
              >查询{{ optionTitle(kind) }}候选</el-button
            >
            <el-select
              v-model="optionStates[kind].size"
              :aria-label="`${optionTitle(kind)}候选每页条数`"
              :disabled="controlsDisabled || optionStates[kind].loading"
              @change="searchOptions(kind)"
              ><el-option v-for="n in sizes" :key="n" :value="n" :label="`${n} 条`"
            /></el-select>
            <el-button
              :disabled="
                controlsDisabled || optionStates[kind].loading || !optionStates[kind].history.length
              "
              @click="optionPrevious(kind)"
              >上一页{{ optionTitle(kind) }}候选</el-button
            >
            <el-button
              :disabled="
                controlsDisabled ||
                optionStates[kind].loading ||
                !optionStates[kind].page?.next_cursor
              "
              @click="optionNext(kind)"
              >下一页{{ optionTitle(kind) }}候选</el-button
            >
          </div>
          <p v-if="optionStates[kind].loading" role="status">
            正在读取{{ optionTitle(kind) }}候选…
          </p>
          <el-alert
            v-if="optionStates[kind].error"
            :title="optionStates[kind].error"
            type="error"
            :closable="false"
          />
          <p v-if="optionStates[kind].error">
            读取失败；已知选择与已验证范围保留。请重试后再从此下拉新增选择。
          </p>
          <p v-else-if="optionStates[kind].page && !optionStates[kind].page!.items.length">
            当前{{ optionTitle(kind) }}候选查询没有匹配项；不是全量目录。
          </p>
          <p v-if="optionStates[kind].page">
            本页数据时间 {{ optionStates[kind].page!.data_as_of }} · 权限版本
            {{ optionStates[kind].page!.scope_version }}
          </p>
        </div>
      </section>
      <p v-else-if="!operatorOptions.length || !vendorOptions.length">
        未提供真实操作者或户商筛选候选时，对应筛选不可用；不借其它菜单权限加载。
      </p>
      <div class="actions">
        <el-button :disabled="controlsDisabled || candidateLoading" @click="searchCandidates"
          >查询账户</el-button
        ><el-select
          v-model="candidateSize"
          aria-label="候选每页条数"
          :disabled="controlsDisabled"
          @change="searchCandidates"
          ><el-option v-for="n in sizes" :key="n" :value="n" :label="`${n} 条`"
        /></el-select>
      </div>
      <p v-if="candidateLoading" role="status">正在读取规则账户候选…</p>
      <el-alert v-if="candidateError" :title="candidateError" type="error" :closable="false" />
      <p v-if="candidates && !candidates.items.length">当前条件零匹配；不能按这些条件冻结范围。</p>
      <el-table v-if="candidates?.items.length" :data="candidates.items" row-key="account_id">
        <el-table-column v-if="mode === 'IDS'" label="勾选" width="75"
          ><template #default="{ row }"
            ><el-checkbox
              :model-value="selected.has(row.account_id)"
              :disabled="
                controlsDisabled || (!selected.has(row.account_id) && selected.size >= 50000)
              "
              :aria-label="`选择规则账户 ${row.external_id}`"
              @change="toggle(row)" /></template
        ></el-table-column>
        <el-table-column prop="name" label="当前账户名称" min-width="180" /><el-table-column
          prop="external_id"
          label="平台账户ID"
          min-width="150"
        /><el-table-column prop="account_id" label="账户ID" min-width="280" />
      </el-table>
      <div class="actions">
        <el-button
          :disabled="controlsDisabled || candidateLoading || !candidateHistory.length"
          @click="candidatePrevious"
          >上一页账户</el-button
        ><el-button
          :disabled="controlsDisabled || candidateLoading || !candidates?.next_cursor"
          @click="candidateNext"
          >下一页账户</el-button
        ><span v-if="candidates"
          >数据时间 {{ candidates.data_as_of }} · 范围版本 {{ candidates.scope_version }}</span
        >
      </div>
      <template v-if="mode === 'IDS'"
        ><p>明确选择 {{ selected.size }} / 50000 个账户。只有显式勾选才进入选择。</p>
        <el-collapse
          ><el-collapse-item title="核对已选账户（每组50个，可移除）"
            ><p v-for="row in selectedRows" :key="row.account_id" class="selected-row">
              <span>{{ row.name }} · {{ row.external_id }}</span
              ><el-button :disabled="controlsDisabled" @click="remove(row.account_id)"
                >移除 {{ row.external_id }}</el-button
              >
            </p>
            <el-button :disabled="controlsDisabled || selectedPage === 0" @click="selectedPage--"
              >上一组已选</el-button
            ><el-button
              :disabled="controlsDisabled || (selectedPage + 1) * 50 >= selected.size"
              @click="selectedPage++"
              >下一组已选</el-button
            ></el-collapse-item
          ></el-collapse
        ></template
      >
      <p v-else>
        将冻结已查询的完整过滤结果，实际总数由服务端返回；不支持从全选结果逐个排除。更改筛选后请先查询。
      </p>
      <div class="actions">
        <el-button type="primary" :disabled="!canFreeze" :loading="writing" @click="freeze"
          >冻结所选范围</el-button
        ><el-button :disabled="controlsDisabled || !selected.size" @click="clearSelected"
          >清空明确选择</el-button
        >
      </div>
      <el-descriptions v-if="snapshot" :column="1" border
        ><el-descriptions-item label="真实快照ID">{{ snapshot.id }}</el-descriptions-item
        ><el-descriptions-item label="完整账户数">{{ snapshot.count }}</el-descriptions-item
        ><el-descriptions-item label="权限版本">{{ snapshot.scope_version }}</el-descriptions-item
        ><el-descriptions-item label="成员hash"
          ><span class="wrap">{{ snapshot.hash }}</span></el-descriptions-item
        ><el-descriptions-item label="冻结时间（UTC）">{{
          snapshot.created_at
        }}</el-descriptions-item></el-descriptions
      >
      <el-alert
        v-if="snapshot && snapshotBoundRevision !== currentRuleRevision"
        title="该回执绑定旧规则版本，仅供历史核对；即使成员读取成功也不能用于当前版本，请重新冻结。"
        type="warning"
        :closable="false"
      />
      <template v-if="snapshot">
        <p>成员查询只核对已冻结快照，不改变其成员；关闭或取消本地使用不会删除服务端快照。</p>
        <div class="actions">
          <el-input
            v-model="memberQ"
            aria-label="规则快照成员搜索"
            placeholder="名称前缀或完整平台ID"
            :disabled="locked"
            @keyup.enter="searchMembers"
          /><el-select
            v-model="memberSize"
            aria-label="成员每页条数"
            :disabled="locked"
            @change="searchMembers"
            ><el-option v-for="n in sizes" :key="n" :value="n" :label="`${n} 条`" /></el-select
          ><el-button :disabled="memberLoading || locked" @click="searchMembers"
            >查询冻结成员</el-button
          >
        </div>
        <p v-if="memberLoading" role="status">正在核对冻结成员…</p>
        <el-alert v-if="memberError" :title="memberError" type="error" :closable="false" />
        <el-table v-if="members" :data="members.items" empty-text="该成员查询没有匹配项"
          ><el-table-column prop="name" label="冻结时账户名称" min-width="180" /><el-table-column
            prop="external_id"
            label="平台账户ID"
            min-width="150" /><el-table-column prop="account_id" label="账户ID" min-width="280"
        /></el-table>
        <div class="actions">
          <el-button
            :disabled="locked || memberLoading || !memberHistory.length"
            @click="memberPrevious"
            >上一页成员</el-button
          ><el-button
            :disabled="locked || memberLoading || !members?.next_cursor"
            @click="memberNext"
            >下一页成员</el-button
          >
        </div>
      </template>
    </template>
    <el-alert v-if="writeError" :title="writeError" type="error" :closable="false" />
    <p v-if="unknown">
      原请求结果未知；关闭只保留待确认意图，不是取消服务端冻结。父未接管时只能在当前组件实例内恢复。
    </p>
    <div v-if="unknown && pending" class="recovery-actions">
      <a href="/login" target="_blank" rel="noopener">在新标签页重新登录</a>
      <p>请保留本页；登录后回此弹窗验证身份，不会自动提交原请求。</p>
      <el-button :loading="recoveryBusy" @click="emit('verifyIdentity')"
        >重新验证当前身份（不提交）</el-button
      >
      <p v-if="recoveryMessage" role="status">{{ recoveryMessage }}</p>
    </div>
    <template #footer
      ><el-button @click="requestClose(false)">{{
        pending ? '关闭并保留待确认请求' : '取消本地选择'
      }}</el-button
      ><el-button
        v-if="pending"
        type="warning"
        :disabled="writing || pending.context !== fingerprint() || !permitted || disabled"
        :loading="writing"
        @click="recover"
        >使用原请求恢复</el-button
      ><el-button type="primary" :disabled="!canApply" @click="apply"
        >应用真实范围</el-button
      ></template
    >
  </el-dialog>
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

import { computed, nextTick, onBeforeUnmount, reactive, ref, shallowRef, watch } from 'vue'
import { RuleApiError } from '@/api/orbit/rules'
import {
  ruleScopeOptionsApi,
  type ScopeOptionKind,
  type RuleOperatorOption,
  type RuleVendorOption,
  type RuleScopeOptionPage,
} from '@/api/orbit/rule-scope-options'
import {
  freezeRuleEditorScopeIntent,
  ruleEditorScopesApi as api,
  type FrozenRuleEditorScopeIntent,
  type ScopeFilter,
  type ScopeMemberPage,
  type ScopeSnapshot,
  type RuleEditorScopeWrite,
} from '@/api/orbit/rule-editor-scopes'
type Option = { id: string; label: string }
type Pending = {
  principal: RuleRecoveryPrincipal | null
  intent: FrozenRuleEditorScopeIntent
  context: string
}
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    action: 'CREATE' | 'UPDATE'
    ruleId: string | null
    ownership: { owner_user_id: string; owner_team_id: string }
    currentRuleRevision: number | null
    csrfToken: string
    nativeActorId?: number | null
    permissionCodes?: string[]
    contextKey?: string
    disabled?: boolean
    remoteOptions?: boolean
    operatorOptions?: Option[]
    vendorOptions?: Option[]
    recoveryBusy?: boolean
    recoveryMessage?: string
    pendingIntent?: Pending | null
  }>(),
  {
    recoveryBusy: false,
    recoveryMessage: '',
    nativeActorId: null,
    permissionCodes: () => [],
    contextKey: '',
    disabled: false,
    remoteOptions: false,
    operatorOptions: () => [],
    vendorOptions: () => [],
    pendingIntent: null,
  },
)
const emit = defineEmits<{
  'update:modelValue': [boolean]
  choose: [ScopeSnapshot]
  locked: [boolean]
  verifyIdentity: []
  'pending-intent': [Pending | null]
}>()
const sizes = [20, 50, 100, 200],
  mode = ref<'IDS' | 'FILTER'>('IDS')
const emptyFilter = (): ScopeFilter => ({
  q: '',
  status: null,
  auth_status: null,
  operator_user_id: null,
  vendor_id: null,
})
const filter = reactive<ScopeFilter>(emptyFilter()),
  selected = reactive(new Map<string, ScopeMemberPage['items'][number]>()),
  selectedPage = ref(0)
const selectedRows = computed(() =>
  [...selected.values()].slice(selectedPage.value * 50, (selectedPage.value + 1) * 50),
)
const candidateSize = ref<20 | 50 | 100 | 200>(50),
  candidates = ref<ScopeMemberPage | null>(null),
  candidateLoading = ref(false),
  candidateError = ref(''),
  candidateCursor = ref<string | undefined>(),
  candidateHistory = ref<(string | undefined)[]>([])
const appliedFilter = ref<ScopeFilter>(emptyFilter()),
  appliedCandidateSize = ref<20 | 50 | 100 | 200>(50)
type RemoteState = {
  q: string
  appliedQ: string
  size: 20 | 50 | 100 | 200
  appliedSize: 20 | 50 | 100 | 200
  cursor: string | undefined
  history: (string | undefined)[]
  page: RuleScopeOptionPage<RuleOperatorOption | RuleVendorOption> | null
  cache: Map<string, Option>
  loading: boolean
  error: string
  epoch: number
  abort: AbortController | undefined
}
const optionKinds: ScopeOptionKind[] = ['OPERATOR', 'VENDOR']
const newOptionState = (): RemoteState => ({
  q: '',
  appliedQ: '',
  size: 50,
  appliedSize: 50,
  cursor: undefined,
  history: [],
  page: null,
  cache: new Map(),
  loading: false,
  error: '',
  epoch: 0,
  abort: undefined,
})
const optionStates = reactive<Record<ScopeOptionKind, RemoteState>>({
  OPERATOR: newOptionState(),
  VENDOR: newOptionState(),
})
const operatorDisplay = computed(() =>
  props.remoteOptions ? [...optionStates.OPERATOR.cache.values()] : props.operatorOptions,
)
const vendorDisplay = computed(() =>
  props.remoteOptions ? [...optionStates.VENDOR.cache.values()] : props.vendorOptions,
)
const optionTitle = (kind: ScopeOptionKind) => (kind === 'OPERATOR' ? '操作者' : '户商')
function optionLabel(kind: ScopeOptionKind, item: RuleOperatorOption | RuleVendorOption): Option {
  if (kind === 'OPERATOR') {
    const value = item as RuleOperatorOption
    return {
      id: value.id,
      label: `${value.name} · ${value.team_name}${value.active ? '' : ' · 已停用（仅历史筛选）'}`,
    }
  }
  const value = item as RuleVendorOption
  return {
    id: value.id,
    label: `${value.alias ?? '未设置代称'} · 资料名称：${value.name}${value.availability === 'UNAVAILABLE' ? ' · 不可用（仅历史筛选）' : ''}`,
  }
}
function stopOptionReads() {
  for (const kind of optionKinds) {
    const state = optionStates[kind]
    ++state.epoch
    state.abort?.abort()
    state.loading = false
  }
}
function resetOptionData() {
  stopOptionReads()
  for (const kind of optionKinds) {
    const state = optionStates[kind]
    state.page = null
    state.cache.clear()
    state.cursor = undefined
    state.history = []
    state.error = ''
    state.q = ''
    state.appliedQ = ''
  }
}
function selectFilterOption(kind: ScopeOptionKind, value: unknown) {
  if (controlsDisabled.value) return
  if (
    props.remoteOptions &&
    value !== null &&
    value !== '' &&
    (optionStates[kind].loading || optionStates[kind].error)
  )
    return
  const options = kind === 'OPERATOR' ? operatorDisplay.value : vendorDisplay.value
  const key = kind === 'OPERATOR' ? 'operator_user_id' : 'vendor_id'
  if (value === null || value === '') filter[key] = null
  else if (typeof value === 'string' && options.some((item) => item.id === value))
    filter[key] = value
}
async function loadOptions(kind: ScopeOptionKind) {
  const state = optionStates[kind]
  state.abort?.abort()
  const current = ++state.epoch,
    started = selectionContext()
  state.abort = new AbortController()
  if (!props.remoteOptions || !props.modelValue || controlsDisabled.value) return
  state.loading = true
  state.error = ''
  try {
    const value = await ruleScopeOptionsApi.options(
      {
        kind,
        action: props.action,
        ...(props.action === 'UPDATE' ? { rule_id: props.ruleId! } : {}),
        ...props.ownership,
        q: state.appliedQ,
        page_size: state.appliedSize,
        ...(state.cursor ? { cursor: state.cursor } : {}),
      },
      state.abort.signal,
    )
    if (current !== state.epoch || started !== selectionContext()) return
    const selectedId = kind === 'OPERATOR' ? filter.operator_user_id : filter.vendor_id
    const kept = selectedId ? state.cache.get(selectedId) : undefined
    state.cache.clear()
    if (kept) state.cache.set(kept.id, kept)
    for (const item of value.items) {
      const option = optionLabel(kind, item)
      state.cache.set(option.id, option)
    }
    state.page = value
  } catch (e) {
    if (current !== state.epoch || aborted(e)) return
    if (denied(e) || (e instanceof RuleApiError && e.status === 409)) {
      denyAccess(e)
      filter.operator_user_id = null
      filter.vendor_id = null
    } else state.error = textError(e)
  } finally {
    if (current === state.epoch) state.loading = false
  }
}
function searchOptions(kind: ScopeOptionKind) {
  const state = optionStates[kind]
  state.appliedQ = state.q
  state.appliedSize = state.size
  state.cursor = undefined
  state.history = []
  void loadOptions(kind)
}
function optionNext(kind: ScopeOptionKind) {
  const state = optionStates[kind]
  if (!state.page?.next_cursor || state.loading || controlsDisabled.value) return
  state.history.push(state.cursor)
  state.cursor = state.page.next_cursor
  void loadOptions(kind)
}
function optionPrevious(kind: ScopeOptionKind) {
  const state = optionStates[kind]
  if (!state.history.length || state.loading || controlsDisabled.value) return
  state.cursor = state.history.pop()
  void loadOptions(kind)
}
function startOptions() {
  if (props.remoteOptions) for (const kind of optionKinds) searchOptions(kind)
}
const snapshot = ref<ScopeSnapshot | null>(null),
  snapshotContext = ref(''),
  snapshotBusinessContext = ref(''),
  snapshotBoundRevision = ref<number | null>(null),
  staleSnapshot = ref(false)
const memberQ = ref(''),
  memberSize = ref<20 | 50 | 100 | 200>(50),
  members = ref<ScopeMemberPage | null>(null),
  memberLoading = ref(false),
  memberError = ref(''),
  memberCursor = ref<string | undefined>(),
  memberHistory = ref<(string | undefined)[]>([])
const appliedMemberQ = ref(''),
  appliedMemberSize = ref<20 | 50 | 100 | 200>(50)
const pending = shallowRef<Pending | null>(props.pendingIntent),
  writing = ref(false),
  unknown = ref(!!props.pendingIntent),
  writeError = ref('')
const accessDenied = ref(false),
  accessError = ref('')
const searchInput = ref<{ focus: () => void }>(),
  opener = shallowRef<HTMLElement | null>(null)
let candidateEpoch = 0,
  memberEpoch = 0,
  writeEpoch = 0,
  candidateAbort: AbortController | undefined,
  memberAbort: AbortController | undefined,
  writeAbort: AbortController | undefined
const permitted = computed(
  () =>
    props.permissionCodes.includes('*:*:*') ||
    props.permissionCodes.includes(props.action === 'CREATE' ? 'rules.create' : 'rules.edit'),
)
const uuid = (value: unknown) =>
  typeof value === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value)
const validContext = computed(
  () =>
    uuid(props.ownership.owner_user_id) &&
    uuid(props.ownership.owner_team_id) &&
    props.csrfToken.length >= 16 &&
    (props.action === 'CREATE'
      ? props.ruleId === null && props.currentRuleRevision === null
      : uuid(props.ruleId) &&
        Number.isSafeInteger(props.currentRuleRevision) &&
        props.currentRuleRevision! > 0),
)
const fingerprint = () =>
  JSON.stringify([
    props.contextKey,
    props.action,
    props.ruleId,
    props.ownership.owner_user_id,
    props.ownership.owner_team_id,
  ])
const selectionContext = () =>
  JSON.stringify([fingerprint(), [...props.permissionCodes].sort(), props.currentRuleRevision])
const locked = computed(() => writing.value || !!pending.value),
  controlsDisabled = computed(
    () =>
      locked.value ||
      props.disabled ||
      !permitted.value ||
      !validContext.value ||
      accessDenied.value,
  )
const filterCurrent = computed(() => JSON.stringify(filter) === JSON.stringify(appliedFilter.value))
const canFreeze = computed(
  () =>
    props.modelValue &&
    !controlsDisabled.value &&
    !candidateLoading.value &&
    (mode.value === 'IDS'
      ? selected.size >= 1 && selected.size <= 50000
      : !!candidates.value?.items.length && !candidateError.value && filterCurrent.value),
)
const canApply = computed(
  () =>
    props.modelValue &&
    !!snapshot.value &&
    !locked.value &&
    !props.disabled &&
    permitted.value &&
    validContext.value &&
    snapshotContext.value === selectionContext() &&
    !staleSnapshot.value &&
    !accessDenied.value &&
    snapshotBoundRevision.value === props.currentRuleRevision &&
    !memberLoading.value,
)
const textError = (e: unknown) =>
  e instanceof RuleApiError
    ? `${e.message}（${e.code}）${e.field_errors.map((f) => ` ${f.path}: ${f.message}`).join('')}`
    : '请求失败，请重新读取。'
const aborted = (e: unknown) => e instanceof Error && e.name === 'AbortError'
function stopReads() {
  stopOptionReads()
  ++candidateEpoch
  ++memberEpoch
  candidateAbort?.abort()
  memberAbort?.abort()
  candidateLoading.value = false
  memberLoading.value = false
}
function invalidateSnapshot() {
  snapshot.value = null
  snapshotContext.value = ''
  snapshotBusinessContext.value = ''
  snapshotBoundRevision.value = null
  members.value = null
  staleSnapshot.value = false
}
function clearCursors() {
  candidateCursor.value = undefined
  candidateHistory.value = []
  memberCursor.value = undefined
  memberHistory.value = []
}
function denyAccess(error: unknown) {
  resetOptionData()
  filter.operator_user_id = null
  filter.vendor_id = null
  accessDenied.value = true
  accessError.value = textError(error)
  clearCursors()
  stopReads()
  candidates.value = null
  selected.clear()
  selectedPage.value = 0
  candidateError.value = ''
  memberError.value = ''
  writeError.value = ''
  invalidateSnapshot()
  // 当前读权限被拒不清除原未确认业务意图，恢复仍须服务器当前授权。
}
function recheckAccess() {
  if (pending.value || !permitted.value || props.disabled || !validContext.value) return
  accessDenied.value = false
  accessError.value = ''
  searchCandidates()
  startOptions()
}
function denied(error: unknown) {
  return error instanceof RuleApiError && (error.status === 401 || error.status === 403)
}
function clearSelected() {
  if (controlsDisabled.value) return
  selected.clear()
  selectedPage.value = 0
  invalidateSnapshot()
}
function toggle(row: ScopeMemberPage['items'][number]) {
  if (controlsDisabled.value) return
  if (selected.has(row.account_id)) selected.delete(row.account_id)
  else if (selected.size < 50000) selected.set(row.account_id, { ...row })
  invalidateSnapshot()
}
function remove(id: string) {
  if (controlsDisabled.value) return
  selected.delete(id)
  selectedPage.value = Math.min(selectedPage.value, Math.max(0, Math.ceil(selected.size / 50) - 1))
  invalidateSnapshot()
}
async function loadCandidates() {
  candidateAbort?.abort()
  const token = ++candidateEpoch,
    started = selectionContext()
  candidateAbort = new AbortController()
  candidates.value = null
  candidateError.value = ''
  if (!props.modelValue || controlsDisabled.value) return
  candidateLoading.value = true
  const current = appliedFilter.value
  try {
    const value = await api.accounts(
      {
        ...(props.action === 'CREATE'
          ? { action: 'CREATE' as const }
          : { action: 'UPDATE' as const, rule_id: props.ruleId! }),
        ...props.ownership,
        q: current.q,
        ...(current.status ? { status: current.status } : {}),
        ...(current.auth_status ? { auth_status: current.auth_status } : {}),
        ...(current.operator_user_id ? { operator_user_id: current.operator_user_id } : {}),
        ...(current.vendor_id ? { vendor_id: current.vendor_id } : {}),
        page_size: appliedCandidateSize.value,
        ...(candidateCursor.value ? { cursor: candidateCursor.value } : {}),
      },
      candidateAbort.signal,
    )
    if (token === candidateEpoch && started === selectionContext() && props.modelValue)
      candidates.value = value
  } catch (e) {
    if (token === candidateEpoch && started === selectionContext() && !aborted(e)) {
      if (denied(e)) denyAccess(e)
      else candidateError.value = textError(e)
    }
  } finally {
    if (token === candidateEpoch) candidateLoading.value = false
  }
}
function searchCandidates() {
  if (controlsDisabled.value) return
  appliedFilter.value = { ...filter }
  appliedCandidateSize.value = candidateSize.value
  candidateCursor.value = undefined
  candidateHistory.value = []
  void loadCandidates()
}
function candidateNext() {
  if (!candidates.value?.next_cursor || candidateLoading.value || controlsDisabled.value) return
  candidateHistory.value.push(candidateCursor.value)
  candidateCursor.value = candidates.value.next_cursor
  void loadCandidates()
}
function candidatePrevious() {
  if (!candidateHistory.value.length || candidateLoading.value || controlsDisabled.value) return
  candidateCursor.value = candidateHistory.value.pop()
  void loadCandidates()
}
function remember(value: Pending | null) {
  pending.value = value
  emit('pending-intent', value)
}
async function send(fixed: Pending, recovering: boolean) {
  if (fixed.context !== fingerprint() || writing.value || !permitted.value || props.disabled) return
  let created = false,
    attempted = false
  const token = ++writeEpoch
  writeAbort = new AbortController()
  writing.value = true
  writeError.value = ''
  try {
    const current = await ruleRecoveryApi.get(fixed.intent.body.action, writeAbort.signal)
    if (token !== writeEpoch || fixed.context !== fingerprint() || !props.modelValue) return
    if (recovering) requireRecoveryPrincipal(fixed.principal, current)
    else {
      requireInitialRuleActor(props.nativeActorId, current)
      fixed = { ...fixed, principal: recoveryPrincipal(current) }
      remember(fixed)
    }
    refreshCookieCsrfForRecovery(current.csrf_token)
    const transportAuth = { ...fixed.intent.auth, csrf_token: current.csrf_token }
    attempted = true
    const value = await api.create(fixed.intent.body, transportAuth, writeAbort.signal)
    if (token !== writeEpoch || fixed.context !== fingerprint() || !props.modelValue) return
    snapshot.value = value
    snapshotBoundRevision.value =
      fixed.intent.body.action === 'UPDATE' && 'if_match' in fixed.intent.auth
        ? Number(fixed.intent.auth.if_match.slice(1, -1))
        : null
    snapshotBusinessContext.value = fixed.context
    snapshotContext.value = JSON.stringify([
      fixed.context,
      [...props.permissionCodes].sort(),
      snapshotBoundRevision.value,
    ])
    staleSnapshot.value = true
    unknown.value = false
    remember(null)
    created = true
  } catch (e) {
    if (token !== writeEpoch) return
    if (denied(e)) denyAccess(e)
    writeError.value = textError(e)
    unknown.value = recovering || (attempted && (!(e instanceof RuleApiError) || e.unknown_result))
    if (!unknown.value) remember(null)
  } finally {
    if (token === writeEpoch) {
      writing.value = false
      if (created) searchMembers()
    }
  }
}
function freeze() {
  if (!canFreeze.value) return
  try {
    const body: RuleEditorScopeWrite = {
      action: props.action,
      rule_id: props.ruleId,
      ownership: { ...props.ownership },
      selection:
        mode.value === 'IDS'
          ? { mode: 'IDS', account_ids: [...selected.keys()], filter: null }
          : { mode: 'FILTER', account_ids: [], filter: { ...appliedFilter.value } },
    } as RuleEditorScopeWrite
    const fixed = {
      principal: null,
      intent: freezeRuleEditorScopeIntent(body, {
        csrf_token: props.csrfToken,
        idempotency_key: crypto.randomUUID(),
        ...(props.action === 'UPDATE' ? { if_match: `"${props.currentRuleRevision}"` } : {}),
      }),
      context: fingerprint(),
    }
    void send(fixed, false)
  } catch (e) {
    writeError.value = textError(e)
  }
}
function recover() {
  if (pending.value) void send(pending.value, true)
}
async function loadMembers() {
  if (
    !snapshot.value ||
    !props.modelValue ||
    locked.value ||
    snapshotBusinessContext.value !== fingerprint()
  )
    return
  memberAbort?.abort()
  const token = ++memberEpoch,
    started = selectionContext(),
    id = snapshot.value.id
  memberAbort = new AbortController()
  members.value = null
  memberError.value = ''
  memberLoading.value = true
  try {
    const value = await api.members(
      id,
      {
        q: appliedMemberQ.value,
        page_size: appliedMemberSize.value,
        ...(memberCursor.value ? { cursor: memberCursor.value } : {}),
      },
      memberAbort.signal,
    )
    if (token === memberEpoch && started === selectionContext()) {
      members.value = value
      staleSnapshot.value = snapshotBoundRevision.value !== props.currentRuleRevision
      accessDenied.value = false
      accessError.value = ''
    }
  } catch (e) {
    if (token === memberEpoch && started === selectionContext() && !aborted(e)) {
      if (denied(e)) denyAccess(e)
      else {
        memberError.value = textError(e)
        staleSnapshot.value = true
      }
    }
  } finally {
    if (token === memberEpoch) memberLoading.value = false
  }
}
function searchMembers() {
  appliedMemberQ.value = memberQ.value
  appliedMemberSize.value = memberSize.value
  memberCursor.value = undefined
  memberHistory.value = []
  void loadMembers()
}
function memberNext() {
  if (!members.value?.next_cursor || memberLoading.value || locked.value) return
  memberHistory.value.push(memberCursor.value)
  memberCursor.value = members.value.next_cursor
  void loadMembers()
}
function memberPrevious() {
  if (!memberHistory.value.length || memberLoading.value || locked.value) return
  memberCursor.value = memberHistory.value.pop()
  void loadMembers()
}
function markInterrupted() {
  if (pending.value) {
    unknown.value = true
    ++writeEpoch
    writeAbort?.abort()
    writing.value = false
    emit('pending-intent', pending.value)
  }
}
function requestClose(value = false) {
  if (value) return
  stopReads()
  if (writing.value && !pending.value) {
    ++writeEpoch
    writeAbort?.abort()
    writing.value = false
  } else if (writing.value) markInterrupted()
  emit('update:modelValue', false)
}
function apply() {
  if (!canApply.value || !snapshot.value) return
  emit('choose', { ...snapshot.value })
  requestClose(false)
}
function focusSearch() {
  if (!controlsDisabled.value) searchInput.value?.focus()
}
function restoreFocus() {
  if (opener.value?.isConnected) opener.value.focus()
}
watch(locked, (value) => emit('locked', value), { immediate: true })
watch(
  () => props.pendingIntent,
  (value) => {
    if (
      value &&
      (value.intent !== pending.value?.intent || value.context !== pending.value?.context)
    ) {
      stopReads()
      pending.value = value
      unknown.value = true
    }
  },
)
watch(
  selectionContext,
  () => {
    stopReads()
    clearCursors()
    markInterrupted()
    selected.clear()
    selectedPage.value = 0
    candidates.value = null
    candidateError.value = ''
    memberError.value = ''
    writeError.value = ''
    accessDenied.value = false
    accessError.value = ''
    invalidateSnapshot()
    Object.assign(filter, emptyFilter())
    resetOptionData()
    if (props.modelValue && !pending.value) {
      searchCandidates()
      startOptions()
    }
  },
  { flush: 'sync' },
)
watch(
  () => props.modelValue,
  async (value) => {
    if (value) {
      opener.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
      await nextTick()
      if (!pending.value) {
        searchCandidates()
        startOptions()
        if (snapshot.value) {
          staleSnapshot.value = true
          searchMembers()
        }
      }
    } else {
      stopReads()
      if (writing.value) markInterrupted()
    }
  },
  { immediate: true },
)
watch(
  () => props.remoteOptions,
  () => {
    resetOptionData()
    if (props.modelValue && !pending.value) startOptions()
  },
)
watch(mode, invalidateSnapshot)
watch(filter, invalidateSnapshot, { deep: true })
onBeforeUnmount(() => {
  stopReads()
  markInterrupted()
  restoreFocus()
})
</script>

<style scoped>
.remote-option-panel {
  margin: 16px 0;
}
.remote-option-panel h3 {
  font-size: 14px;
}
.remote-options p {
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 16px;
  margin-top: 20px;
}
.actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin: 16px 0;
}
.actions .el-select {
  width: 130px;
}
.actions .el-input {
  width: 260px;
}
.wrap,
p {
  overflow-wrap: anywhere;
}
.selected-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.el-alert {
  margin: 12px 0;
}
@media (max-width: 700px) {
  .filters {
    grid-template-columns: 1fr;
  }
  .actions .el-input {
    width: 100%;
  }
}
</style>
