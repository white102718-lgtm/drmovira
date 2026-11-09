<template>
  <el-drawer
    :model-value="modelValue"
    :title="readOnly ? '投放计划详情' : existing ? '编辑投放草稿' : '新建投放草稿'"
    size="96%"
    :close-on-click-modal="false"
    :close-on-press-escape="
      !locked && !identityEditing && !sourceOpen && !accountOpen && !metricBrowsing
    "
    :before-close="beforeClose"
    @closed="emit('closed')"
    @open-auto-focus="locationFocusTrigger++"
  >
    <div ref="editorFields">
      <p v-if="locationNotice" ref="locationAnchor" tabindex="-1" role="status">
        {{ locationNotice }}
      </p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-alert v-if="cacheWarning" :title="cacheWarning" type="warning" :closable="false" />
      <el-alert
        v-if="uncertain"
        title="本次保存结果暂未确认。请重试同一次保存；确认前不能修改或关闭。"
        type="warning"
        :closable="false"
      />
      <div class="draft-status">
        <el-tag :type="savedSignature === signature ? 'success' : 'warning'">{{
          savedSignature === signature ? '服务器已保存' : '有未保存配置'
        }}</el-tag
        ><span v-if="existing"
          >版本 {{ existing.revision }} · {{ existing.state }} · 最近保存
          {{ existing.updated_at }}（UTC）</span
        >
      </div>
      <el-form label-position="top" :disabled="locked || sourceOpen || accountOpen || readOnly">
        <h3>1. 账户、负责人和渠道</h3>
        <el-form-item label="计划名称（草稿可空，最多100码点）"
          ><el-input v-model="form.name" /><span
            >{{ codePoints(form.name) }}/100</span
          ></el-form-item
        >
        <el-form-item label="负责人"
          ><el-select :model-value="form.ownership.owner_user_id" filterable @change="changeOwner"
            ><el-option
              v-for="person in owners"
              :key="person.id"
              :value="person.id"
              :label="
                person.name + (person.team_name ? ' · ' + person.team_name : '')
              " /></el-select
          ><el-button
            v-if="ownerCursor"
            :disabled="ownerLoading || locked"
            @click="loadOwners(true)"
            >加载更多负责人</el-button
          ></el-form-item
        >
        <div class="source-fields">
          <el-button :disabled="!identityReadAllowed" @click="pick('accounts')"
            >选择账户（{{ accountCount === null ? '数量待解析' : accountCount }}/500）</el-button
          ><el-button
            v-if="form.account_ids.length || form.account_scope_snapshot_id"
            @click="clearAccounts"
            >清除账户选择</el-button
          ><el-button @click="pick('channels')">{{
            form.channel_id ? '更换已选择渠道' : '选择渠道（草稿可空）'
          }}</el-button
          ><el-button v-if="form.channel_id" @click="form.channel_id = null"
            >清除渠道选择</el-button
          >
        </div>
        <el-alert
          v-if="form.account_scope_snapshot_id"
          :title="
            scopeMetadata
              ? `已冻结${scopeMetadata.count}个账户，保存后由服务端解析实际ID并重新检查权限、归属及币种。身份编辑须等保存返回实际账户。`
              : '此恢复草稿仅有范围ID，没有真实数量和成员元数据；请先保存由服务端解析，或重新选择范围。当前数量未知，不伪造为0。'
          "
          type="warning"
          :closable="false"
        />
        <h3>2—4. 系列、广告组和广告</h3>
        <CampaignTree
          ref="campaignTree"
          v-model="form.campaigns"
          :disabled="locked || sourceOpen || accountOpen || readOnly"
          :metric-read-allowed="metricReadAllowed"
          :metric-context-key="accountContextKey"
          @browsing="metricBrowsing = $event"
        />
        <el-divider />
      </el-form>
      <h3>逐账户身份</h3>
      <el-alert
        v-if="form.account_scope_snapshot_id"
        title="账户范围尚未解析，请先保存服务器草稿，再按返回的实际账户编辑身份。已有身份绑定保留，不会静默删除。"
        type="warning"
        :closable="false"
      />
      <PlanIdentityBindings
        ref="identityBindings"
        v-model="form.identity_bindings"
        :account-ids="form.account_ids"
        :campaigns="form.campaigns"
        :ownership-key="JSON.stringify(form.ownership)"
        :can-read="identityReadAllowed"
        :disabled="locked || sourceOpen || accountOpen || !!form.account_scope_snapshot_id"
        :read-only="readOnly"
        @editing="identityEditing = $event"
      />
      <el-form label-position="top" :disabled="locked || sourceOpen || accountOpen || readOnly">
        <h3>5. 素材池与分配</h3>
        <div class="source-fields">
          <el-button @click="pick('assets')"
            >选择素材池（{{ form.asset_ids.length }}/500）</el-button
          ><el-switch v-model="form.allow_repeat" active-text="允许重复使用素材" />
        </div>
        <el-alert
          title="素材选择不等于完成分配；完整兼容图、全局求解和安全证据验证另行执行，当前不能假分配。"
          type="info"
          :closable="false"
        />
        <h3>6. 内部结构汇总与提交门禁</h3>
        <p v-if="counts" role="status">
          系列 {{ counts.campaignCount }} · 广告组 {{ counts.adsetCount }} · 广告
          {{ counts.adCount }}（按账户和每层复制份数展开）
        </p>
        <p v-else role="status">
          展开数量未知：恢复的账户范围尚无可信数量，请保存解析或重新选择。不会按0账户估算。
        </p>
        <el-alert
          v-if="counts && !counts.withinLimit"
          title="展开数量超过每层10000上限，请减少账户或复制份数。"
          type="error"
          :closable="false"
        />
        <el-form-item label="执行通道"
          ><el-radio-group v-model="form.execution_mode"
            ><el-radio value="META_API">Meta API</el-radio
            ><el-radio value="ADSPOWER_UI">AdsPower UI</el-radio></el-radio-group
          ></el-form-item
        >
        <el-switch
          v-model="form.activate_after_create"
          active-text="创建后启用（仍需独立权限与二次确认）"
        />
        <el-alert
          title="当前可保存草稿，尚不具备完整执行前置条件：身份授权、能力校验、命名、素材分配与命令服务。预检和执行保持关闭，保存不会创建广告。"
          type="warning"
          :closable="false"
        />
      </el-form>
      <SourcePicker
        v-model="sourceOpen"
        :kind="sourceKind"
        :selected="sourceSelection"
        :ownership="form.ownership"
        :disabled="locked"
        @choose="choose"
      />
      <PlanAccountScopePicker
        v-model="accountOpen"
        :ownership="form.ownership"
        :selected="accountSelection"
        :can-read="identityReadAllowed"
        :disabled="saving || uncertain || readOnly"
        :context-key="JSON.stringify([capabilities?.actor_user_id, accountContextKey])"
        @choose="chooseAccounts"
        @locked="accountScopeLocked = $event"
      />
    </div>
    <template #footer
      ><div class="drawer-actions">
        <el-button
          :disabled="locked || sourceOpen || accountOpen || identityEditing || metricBrowsing"
          @click="requestClose"
          >关闭</el-button
        ><el-button v-if="uncertain" type="warning" :loading="saving" @click="retry"
          >重试本次保存</el-button
        ><el-button
          v-else-if="!readOnly"
          type="primary"
          :loading="saving"
          :disabled="
            sourceOpen ||
            accountOpen ||
            identityEditing ||
            metricBrowsing ||
            (counts !== null && !counts.withinLimit) ||
            !capabilities
          "
          @click="save"
          >保存服务器草稿</el-button
        ><el-button
          :disabled="
            locked ||
            sourceOpen ||
            accountOpen ||
            identityEditing ||
            metricBrowsing ||
            !form.campaigns.length
          "
          @click="emit('template', cloneValue(form.campaigns))"
          >从当前配置另存模板</el-button
        >
      </div></template
    >
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  launchApi,
  type LaunchCapabilities,
  type LaunchPlan,
  type OwnerOption,
  type PlanWrite,
  type CampaignConfig,
} from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
import { cacheDraft, clearDraftRecovery, type DraftRecovery } from '@/api/orbit/launch-recovery'
import {
  cloneValue,
  codePoints,
  newDraft,
  normalizeDraft,
  treeCounts,
} from '@/api/orbit/launch-form'
import CampaignTree from './CampaignTree.vue'
import SourcePicker from './SourcePicker.vue'
import PlanIdentityBindings from './PlanIdentityBindings.vue'
import PlanAccountScopePicker from './PlanAccountScopePicker.vue'
import type { PlanAccountSelection, ScopeSnapshot } from '@/api/orbit/launch-account-scopes'
const props = defineProps<{
  modelValue: boolean
  plan?: LaunchPlan
  capabilities?: LaunchCapabilities
  recovery?: DraftRecovery | null
  readOnly?: boolean
  /** 父页面用真实accounts.read动作传入，launch动作不能代替来源读取权限。 */
  identityReadAllowed?: boolean
  metricReadAllowed?: boolean
  /** 非敏感登录代次及当前权限签名；不写入草稿恢复缓存。 */
  accountContextKey?: string
  focusField?: { path: string; segments: string[]; revision: number }
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [plan: LaunchPlan]
  template: [campaigns: CampaignConfig[]]
  locked: [value: boolean]
  closed: []
}>()
const form = ref<PlanWrite>(newDraft({ owner_user_id: '', owner_team_id: '' })),
  existing = ref<LaunchPlan>(),
  savedSignature = ref(''),
  error = ref(''),
  saving = ref(false),
  uncertain = ref(false),
  cacheWarning = ref('')
const owners = ref<OwnerOption[]>([]),
  ownerCursor = ref<string | null>(null),
  ownerLoading = ref(false)
const sourceOpen = ref(false),
  sourceKind = ref<'assets' | 'channels'>('assets')
const accountOpen = ref(false),
  accountScopeLocked = ref(false),
  scopeMetadata = ref<ScopeSnapshot | null>(null)
const identityEditing = ref(false)
const metricBrowsing = ref(false)
const editorFields = ref<HTMLElement>(),
  locationAnchor = ref<HTMLElement>(),
  campaignTree = ref<InstanceType<typeof CampaignTree>>(),
  identityBindings = ref<InstanceType<typeof PlanIdentityBindings>>(),
  locationNotice = ref('')
const locationFocusTrigger = ref(0)
const locked = computed(() => saving.value || uncertain.value || accountScopeLocked.value)
const signature = computed(() => JSON.stringify(form.value))
const accountCount = computed(() =>
  form.value.account_scope_snapshot_id
    ? scopeMetadata.value?.id === form.value.account_scope_snapshot_id
      ? scopeMetadata.value.count
      : null
    : form.value.account_ids.length,
)
const counts = computed(() =>
  accountCount.value === null ? null : treeCounts(accountCount.value, form.value.campaigns),
)
const accountSelection = computed<PlanAccountSelection | null>(() =>
  form.value.account_scope_snapshot_id
    ? scopeMetadata.value?.id === form.value.account_scope_snapshot_id
      ? { kind: 'SNAPSHOT', account_ids: [], snapshot: scopeMetadata.value }
      : null
    : { kind: 'IDS', account_ids: form.value.account_ids, snapshot: null },
)
const sourceSelection = computed(() =>
  sourceKind.value === 'channels'
    ? form.value.channel_id
      ? [form.value.channel_id]
      : []
    : form.value.asset_ids,
)
let pending: {
  key: string
  body: PlanWrite
  existing?: Pick<LaunchPlan, 'id' | 'revision'>
} | null = null
watch(
  [locked, identityEditing, sourceOpen, accountOpen, metricBrowsing],
  ([value, editing, source, account, metric]) =>
    emit('locked', value || editing || source || account || metric),
)
watch(
  () => props.modelValue,
  async (open) => {
    if (!open || !props.capabilities) return
    error.value = ''
    cacheWarning.value = ''
    pending = null
    uncertain.value = false
    sourceOpen.value = false
    accountOpen.value = false
    accountScopeLocked.value = false
    scopeMetadata.value = null
    existing.value = props.plan ? cloneValue(props.plan) : undefined
    form.value = props.plan
      ? normalizeDraft(props.plan)
      : newDraft({
          owner_user_id: props.capabilities.actor_user_id,
          owner_team_id: props.capabilities.actor_team_id,
        })
    stripReadOnlyFields(form.value)
    savedSignature.value = props.plan ? signature.value : ''
    if (props.recovery) {
      form.value = cloneValue(props.recovery.body)
      if (props.recovery.existing)
        existing.value = { ...props.plan, ...props.recovery.existing } as LaunchPlan
      if (props.recovery.pendingKey) {
        pending = {
          key: props.recovery.pendingKey,
          body: cloneValue(props.recovery.body),
          existing: props.recovery.existing,
        }
        uncertain.value = true
      }
    }
    owners.value = [
      {
        id: props.capabilities.actor_user_id,
        team_id: props.capabilities.actor_team_id,
        name: props.capabilities.actor_label,
        team_name: '',
      },
    ]
    if (form.value.ownership.owner_user_id !== props.capabilities.actor_user_id)
      owners.value.push({
        id: form.value.ownership.owner_user_id,
        team_id: form.value.ownership.owner_team_id,
        name: '草稿当前负责人（名称尚未读取）',
        team_name: '',
      })
    if (!props.readOnly) await loadOwners(false)
  },
  { immediate: true },
)
watch(
  form,
  () => {
    if (
      !props.modelValue ||
      !props.capabilities ||
      locked.value ||
      signature.value === savedSignature.value
    )
      return
    remember()
  },
  { deep: true },
)
function remember() {
  if (!props.capabilities) return
  try {
    cacheDraft({
      actor: props.capabilities.actor_user_id,
      body: cloneValue(pending?.body ?? form.value),
      existing:
        pending?.existing ??
        (existing.value ? { id: existing.value.id, revision: existing.value.revision } : undefined),
      ...(pending ? { pendingKey: pending.key } : {}),
    })
    cacheWarning.value = ''
  } catch {
    cacheWarning.value =
      '浏览器恢复缓存写入失败；当前配置仍在本页，关闭或刷新前请先保存服务器草稿。'
  }
}
async function loadOwners(more: boolean) {
  if (ownerLoading.value) return
  ownerLoading.value = true
  try {
    const result = await launchApi.owners(more ? (ownerCursor.value ?? '') : '')
    const map = new Map(owners.value.map((item) => [item.id, item]))
    result.items.forEach((item) => map.set(item.id, item))
    owners.value = [...map.values()]
    ownerCursor.value = result.next_cursor
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '负责人候选读取失败'
  } finally {
    ownerLoading.value = false
  }
}
async function changeOwner(id: string) {
  if (
    locked.value ||
    identityEditing.value ||
    metricBrowsing.value ||
    sourceOpen.value ||
    accountOpen.value ||
    props.readOnly
  )
    return
  const person = owners.value.find((person) => person.id === id)
  if (!person) return
  if (
    form.value.account_ids.length ||
    form.value.asset_ids.length ||
    form.value.channel_id ||
    form.value.identity_bindings.length ||
    form.value.account_scope_snapshot_id
  ) {
    try {
      await ElMessageBox.confirm(
        '变更负责人将清除账户、素材和渠道选择；配置树与原身份绑定保留，旧绑定将标为孤立项待明确处理。是否继续？',
        '重新选择来源',
        { type: 'warning' },
      )
    } catch {
      return
    }
  }
  form.value.ownership = { owner_user_id: person.id, owner_team_id: person.team_id }
  form.value.account_ids = []
  form.value.asset_ids = []
  form.value.channel_id = null
  scopeMetadata.value = null
  delete form.value.account_scope_snapshot_id
  delete form.value.profile_binding_ids
}
function pick(kind: 'accounts' | 'assets' | 'channels') {
  if (
    locked.value ||
    identityEditing.value ||
    metricBrowsing.value ||
    sourceOpen.value ||
    accountOpen.value ||
    props.readOnly
  )
    return
  if (kind === 'accounts') {
    if (props.identityReadAllowed) accountOpen.value = true
    return
  }
  sourceKind.value = kind
  sourceOpen.value = true
}
function choose(ids: string[]) {
  if (locked.value || identityEditing.value || metricBrowsing.value) return
  if (sourceKind.value === 'assets') form.value.asset_ids = ids
  else form.value.channel_id = ids[0] ?? null
}
function chooseAccounts(selection: PlanAccountSelection) {
  if (
    locked.value ||
    identityEditing.value ||
    metricBrowsing.value ||
    props.readOnly ||
    !props.identityReadAllowed
  )
    return
  // 只写原互斥字段；原身份绑定保留，由身份区域显示并显式处理孤立项。
  if (selection.kind === 'IDS') {
    form.value.account_ids = [...selection.account_ids]
    form.value.account_scope_snapshot_id = null
    scopeMetadata.value = null
  } else {
    form.value.account_ids = []
    form.value.account_scope_snapshot_id = selection.snapshot.id
    scopeMetadata.value = cloneValue(selection.snapshot)
  }
}
async function clearAccounts() {
  if (
    locked.value ||
    sourceOpen.value ||
    accountOpen.value ||
    identityEditing.value ||
    metricBrowsing.value ||
    props.readOnly
  )
    return
  try {
    await ElMessageBox.confirm(
      '清除账户选择及本地范围引用？原身份绑定将完整保留为孤立项；服务端已冻结快照不会被删除。',
      '清除账户选择',
      { type: 'warning' },
    )
  } catch {
    return
  }
  form.value.account_ids = []
  form.value.account_scope_snapshot_id = null
  scopeMetadata.value = null
}
function stripReadOnlyFields(value: PlanWrite) {
  const clean = value as PlanWrite & Record<string, unknown>
  for (const field of ['id', 'revision', 'state', 'created_at', 'updated_at']) delete clean[field]
}
async function save() {
  if (
    locked.value ||
    sourceOpen.value ||
    accountOpen.value ||
    identityEditing.value ||
    metricBrowsing.value ||
    props.readOnly ||
    !props.capabilities
  )
    return
  if (codePoints(form.value.name) > 100) {
    error.value = '计划名称最多100个Unicode码点'
    return
  }
  const body = normalizeDraft(form.value)
  pending = {
    key: crypto.randomUUID(),
    body,
    existing: existing.value
      ? { id: existing.value.id, revision: existing.value.revision }
      : undefined,
  }
  remember()
  await send()
}
async function retry() {
  if (!saving.value && pending) await send()
}
async function send() {
  if (!pending || !props.capabilities) return
  const wasUncertain = uncertain.value
  saving.value = true
  error.value = ''
  try {
    const result = await launchApi.save(
      cloneValue(pending.body),
      props.capabilities.csrf_token,
      pending.key,
      pending.existing,
    )
    existing.value = result
    // 服务端会解析scope并冻结真实ID；不能继续把已解析的scope请求正文当当前草稿。
    form.value = normalizeDraft(result)
    stripReadOnlyFields(form.value)
    scopeMetadata.value = null
    savedSignature.value = signature.value
    pending = null
    uncertain.value = false
    try {
      clearDraftRecovery(props.capabilities.actor_user_id)
    } catch {
      cacheWarning.value = '服务器已保存，但浏览器旧恢复缓存未清除；再次打开时以服务器版本为准。'
    }
    emit('saved', result)
  } catch (cause) {
    const definitiveDependency =
      cause instanceof ReferenceApiError &&
      [
        'ACCOUNT_SELECTION_SNAPSHOT_UNAVAILABLE',
        'LAUNCH_IDENTITY_DEPENDENCY_UNAVAILABLE',
        'METRIC_PROFILE_DEPENDENCY_UNAVAILABLE',
        'LAUNCH_INITIALIZATION_REQUIRED',
      ].includes(cause.code)
    uncertain.value =
      wasUncertain ||
      (cause instanceof ReferenceApiError &&
        !definitiveDependency &&
        (cause.status === 0 || cause.status >= 500))
    if (!uncertain.value) pending = null
    error.value = cause instanceof Error ? cause.message : '保存失败，当前配置未保存'
    remember()
  } finally {
    saving.value = false
  }
}
async function beforeClose(done: () => void) {
  if (
    locked.value ||
    sourceOpen.value ||
    accountOpen.value ||
    identityEditing.value ||
    metricBrowsing.value
  )
    return
  if (signature.value !== savedSignature.value) {
    try {
      await ElMessageBox.confirm(
        '配置尚未保存到服务器，关闭后可从本机恢复缓存继续。是否关闭？',
        '未保存配置',
        { type: 'warning' },
      )
    } catch {
      return
    }
  }
  emit('update:modelValue', false)
  done()
}
function requestClose() {
  void beforeClose(() => emit('update:modelValue', false))
}
function protectUnknownScope(event: BeforeUnloadEvent) {
  if (!props.modelValue || !accountScopeLocked.value) return
  // 范围POST原意图只在子组件内存中；未知结果时刷新会丢意图，必须交浏览器确认离开。
  event.preventDefault()
  event.returnValue = ''
}
onMounted(() => window.addEventListener('beforeunload', protectUnknownScope))
onBeforeUnmount(() => window.removeEventListener('beforeunload', protectUnknownScope))
let locationGeneration = 0
watch(
  () => [props.modelValue, props.focusField, locationFocusTrigger.value] as const,
  async ([open, request]) => {
    const generation = ++locationGeneration
    locationNotice.value = ''
    if (!open || !request) return
    await nextTick()
    await nextTick()
    if (generation !== locationGeneration || !props.modelValue) return
    const fail = (message: string) => {
      locationNotice.value = `${message} 原路径：${request.path}`
      void nextTick(() => locationAnchor.value?.focus())
    }
    if (locked.value || props.recovery || request.revision !== existing.value?.revision) {
      fail('错误来源版本或编辑意图已变化，未按旧索引定位。')
      return
    }
    const parts = request.segments
    const decoded =
      request.path.startsWith('/') && !/~(?![01])/u.test(request.path)
        ? request.path
            .slice(1)
            .split('/')
            .map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'))
        : null
    if (!decoded || JSON.stringify(decoded) !== JSON.stringify(parts)) {
      fail('字段路径不符合JSON Pointer，未自动定位。')
      return
    }
    const number = (value: string | undefined) =>
      value && /^(0|[1-9]\d*)$/.test(value) && Number.isSafeInteger(Number(value))
        ? Number(value)
        : -1
    let found = false
    if (parts[0] === 'campaigns') {
      const campaign = form.value.campaigns[number(parts[1])]
      let node:
          | CampaignConfig
          | CampaignConfig['adsets'][number]
          | CampaignConfig['adsets'][number]['ads'][number]
          | undefined = campaign,
        offset = 2
      if (parts[2] === 'adsets') {
        node = campaign?.adsets[number(parts[3])]
        offset = 4
        if (parts[4] === 'ads') {
          node = (node as CampaignConfig['adsets'][number] | undefined)?.ads[number(parts[5])]
          offset = 6
        }
      }
      if (node)
        found = (await campaignTree.value?.focusField(node.local_id, parts.slice(offset))) ?? false
    } else if (parts[0] === 'identity_bindings') {
      const index = number(parts[1])
      if (index >= 0)
        found = (await identityBindings.value?.focusBinding(index, parts.slice(2))) ?? false
    } else {
      const labels: Record<string, string> = {
        name: '计划名称（草稿可空，最多100码点）',
        'ownership/owner_user_id': '负责人',
        execution_mode: '执行通道',
      }
      const key = parts.join('/'),
        label = labels[key]
      const item = label
        ? [...(editorFields.value?.querySelectorAll('label') ?? [])]
            .find((row) => row.textContent?.trim() === label)
            ?.closest('.el-form-item')
        : undefined
      let target = item?.querySelector<HTMLElement>(
        'input:not([disabled]):not([type="hidden"]),textarea:not([disabled])',
      )
      const buttons: Record<string, string> = {
        account_ids: '选择账户',
        asset_ids: '选择素材池',
        channel_id: form.value.channel_id ? '更换已选择渠道' : '选择渠道',
      }
      const member =
        parts.length === 1 ||
        (['account_ids', 'asset_ids'].includes(parts[0]) &&
          number(parts[1]) >= 0 &&
          (parts[0] === 'account_ids' ? form.value.account_ids : form.value.asset_ids)[
            number(parts[1])
          ] !== undefined)
      if (!target && parts.length <= 2 && buttons[parts[0]] && member)
        target = [
          ...(editorFields.value?.querySelectorAll<HTMLButtonElement>('button') ?? []),
        ].find(
          (button) => !button.disabled && button.textContent?.trim().startsWith(buttons[parts[0]]),
        )
      if (target) {
        target.scrollIntoView?.({ block: 'nearest' })
        target.focus()
        found = document.activeElement === target
      }
    }
    if (generation !== locationGeneration) return
    if (found) locationNotice.value = `已定位当前版本的实际字段：${request.path}`
    else fail('当前字段没有可用的自动定位控件，未假定其他字段；请按原路径查看。')
  },
  { immediate: true },
)
</script>

<style scoped>
.draft-status,
.source-fields,
.drawer-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
}
h3 {
  margin-top: 24px;
}
:deep(.el-select) {
  width: min(600px, 100%);
}
:deep(.el-alert) {
  margin: 12px 0;
}
</style>
