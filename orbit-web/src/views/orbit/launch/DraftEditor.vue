<template>
  <el-drawer
    :model-value="modelValue"
    :title="readOnly ? '投放计划详情' : existing ? '编辑投放草稿' : '新建投放草稿'"
    size="min(1240px, 100%)"
    class="comfort-draft"
    :close-on-click-modal="false"
    :close-on-press-escape="
      !locked && !identityEditing && !sourceOpen && !accountOpen && !metricBrowsing
    "
    :before-close="beforeClose"
    @closed="emit('closed')"
    @open-auto-focus="locationFocusTrigger++"
  >
    <div ref="editorFields" class="draft-content">
      <nav class="draft-nav" aria-label="投放配置导航">
        <button
          v-for="section in sections"
          :key="section.key"
          type="button"
          @click="goToSection(section.key)"
        >
          {{ section.label }}
        </button>
      </nav>
      <p v-if="locationNotice" ref="locationAnchor" tabindex="-1" role="status">
        {{ locationNotice }}
      </p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div v-if="saveFieldErrors.length" class="save-field-errors" role="alert">
        <p v-for="(field, index) in saveFieldErrors" :key="index">
          {{ field.message }} · {{ field.path }}
          <el-button
            link
            type="primary"
            :disabled="locked || signature !== failedDraftSignature"
            @click="locateSaveError(field.path)"
            >定位字段</el-button
          >
        </p>
      </div>
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
        <h3 data-launch-section="accounts" tabindex="-1">1. 账户、负责人和渠道</h3>
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
        <p class="draft-intro">按从上到下的顺序配置。每层可切换和复制，复制后的配置独立修改。</p>
        <CampaignTree
          ref="campaignTree"
          v-model="form.campaigns"
          :asset-ids="form.asset_ids"
          :disabled="locked || sourceOpen || accountOpen || readOnly"
          :metric-read-allowed="metricReadAllowed"
          :metric-context-key="accountContextKey"
          @browsing="metricBrowsing = $event"
          @clone-branch="cloneIdentityReferences"
          @remove-branch="removeIdentityReferences"
        />
        <el-divider />
      </el-form>
      <h3 data-launch-section="identity" tabindex="-1">逐账户身份</h3>
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
        <h3 data-launch-section="assets" tabindex="-1">5. 素材池与分配</h3>
        <div class="source-fields">
          <el-button @click="pick('assets')"
            >选择素材池（{{ form.asset_ids.length }}/500）</el-button
          ><el-switch v-model="form.allow_repeat" active-text="允许重复使用素材" />
        </div>
        <el-alert
          title="选定素材池后，在投放预检中核对素材分配。轮播卡片需选择素材池内的素材，保存时不自动发布。"
          type="info"
          :closable="false"
        />
        <h3 data-launch-section="summary" tabindex="-1">6. 配置汇总与执行设置</h3>
        <el-alert
          v-if="hasExtendedConfiguration"
          title="本轮新增的 Meta 配置支持草稿保存和预览，尚未接通对应广告执行能力；投放预检会明确指出未支持的字段，不会忽略配置后创建广告。"
          type="warning"
          :closable="false"
        />
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
          title="保存只更新平台草稿。正式执行前，需从计划列表完成投放预检，检查身份、素材和当前账户支持的配置；保存或预览均不会创建广告。"
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
    <DraftConfigPreview v-model="previewOpen" :plan="form" :account-count="accountCount" />
    <template #footer
      ><div class="drawer-actions">
        <span class="footer-status"
          >{{ savedSignature === signature ? '更改已保存' : '更改尚未保存' }} ·
          {{ accountCount ?? '待解析' }} 个账户</span
        >
        <el-button
          :disabled="locked || sourceOpen || accountOpen || identityEditing || metricBrowsing"
          @click="previewOpen = true"
          >预览当前配置</el-button
        >
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
  LaunchDraftError,
  type LaunchCapabilities,
  type LaunchPlan,
  type OwnerOption,
  type PlanWrite,
  type CampaignConfig,
} from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
import type { PlanHttpFieldError } from '@/api/orbit/launch-validation'
import { cacheDraft, clearDraftRecovery, type DraftRecovery } from '@/api/orbit/launch-recovery'
import {
  cloneValue,
  codePoints,
  newDraft,
  normalizeDraft,
  treeCounts,
} from '@/api/orbit/launch-form'
import CampaignTree from './CampaignTree.vue'
import DraftConfigPreview from './DraftConfigPreview.vue'
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
/** 复制保留同账户身份关联，但新节点ID必须独立；移除只清理被删节点。 */
function cloneIdentityReferences(mapping: Record<string, string>) {
  if (locked.value || props.readOnly) return
  for (const binding of form.value.identity_bindings) {
    const groups = binding.groups
      .filter((row) => mapping[row.adset_local_id])
      .map((row) => ({ ...cloneValue(row), adset_local_id: mapping[row.adset_local_id] }))
    const ads = binding.ad_overrides
      .filter((row) => mapping[row.ad_local_id])
      .map((row) => ({ ...cloneValue(row), ad_local_id: mapping[row.ad_local_id] }))
    binding.groups.push(...groups)
    binding.ad_overrides.push(...ads)
  }
}
function removeIdentityReferences(ids: string[]) {
  if (locked.value || props.readOnly) return
  const removed = new Set(ids)
  for (const binding of form.value.identity_bindings) {
    binding.groups = binding.groups.filter((row) => !removed.has(row.adset_local_id))
    binding.ad_overrides = binding.ad_overrides.filter((row) => !removed.has(row.ad_local_id))
  }
}
const hasExtendedConfiguration = computed(() =>
  form.value.campaigns.some(
    (campaign) =>
      campaign.meta_settings ||
      campaign.objective === 'OUTCOME_LEADS' ||
      campaign.adsets.some(
        (group) =>
          group.meta_settings ||
          group.placements === 'MANUAL' ||
          group.ads.some((ad) => ad.meta_settings),
      ),
  ),
)
const previewOpen = ref(false)
const sections = [
  { key: 'accounts', label: '1 账户' },
  { key: 'campaign', label: '2 系列' },
  { key: 'adset', label: '3 广告组' },
  { key: 'ad', label: '4 广告' },
  { key: 'identity', label: '身份资源' },
  { key: 'assets', label: '5 素材' },
  { key: 'summary', label: '6 汇总' },
]
function goToSection(key: string) {
  const target = editorFields.value?.querySelector<HTMLElement>(`[data-launch-section="${key}"]`)
  target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
}
const identityEditing = ref(false)
const metricBrowsing = ref(false)
const editorFields = ref<HTMLElement>(),
  locationAnchor = ref<HTMLElement>(),
  campaignTree = ref<InstanceType<typeof CampaignTree>>(),
  identityBindings = ref<InstanceType<typeof PlanIdentityBindings>>(),
  locationNotice = ref('')
const locationFocusTrigger = ref(0)
const saveFieldErrors = ref<PlanHttpFieldError[]>([])
const failedDraftSignature = ref('')
const localFocus = ref<{ path: string; segments: string[]; revision: number; signature: string }>()
function locateSaveError(path: string) {
  if (
    locked.value ||
    signature.value !== failedDraftSignature.value ||
    !path.startsWith('/') ||
    /~(?![01])/u.test(path)
  )
    return
  localFocus.value = {
    path,
    segments: path
      .slice(1)
      .split('/')
      .map((x) => x.replaceAll('~1', '/').replaceAll('~0', '~')),
    revision: existing.value?.revision ?? 0,
    signature: failedDraftSignature.value,
  }
}

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
    saveFieldErrors.value = []
    localFocus.value = undefined
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
  saveFieldErrors.value = []
  localFocus.value = undefined
  const submittedSignature = signature.value
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
    if (cause instanceof LaunchDraftError) {
      saveFieldErrors.value = cause.field_errors
      failedDraftSignature.value = submittedSignature
    }
    const environmentUnavailable =
      cause instanceof LaunchDraftError &&
      cause.status === 503 &&
      cause.field_errors.some(
        (field) =>
          field.path === '/profile_binding_ids' || field.path.startsWith('/profile_binding_ids/'),
      )
    error.value = environmentUnavailable
      ? '账户环境绑定（profile_binding_ids）核验尚未接入；当前身份输入已保留，未保存成功。'
      : cause instanceof Error
        ? cause.message
        : '保存失败，当前配置未保存'
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
  () =>
    [props.modelValue, localFocus.value ?? props.focusField, locationFocusTrigger.value] as const,
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
    const fromSave = 'signature' in request
    if (
      locked.value ||
      (fromSave
        ? request.signature !== signature.value ||
          request.revision !== (existing.value?.revision ?? 0)
        : props.recovery || request.revision !== existing.value?.revision)
    ) {
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
.draft-content {
  max-width: 1120px;
  margin: 0 auto;
}
.draft-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 0 18px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 20px;
}
.draft-nav button {
  border: 0;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  padding: 8px 14px;
  cursor: pointer;
  font: inherit;
}
.draft-nav button:hover,
.draft-nav button:focus-visible {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.draft-intro {
  color: var(--el-text-color-secondary);
  margin: 28px 0 16px;
}
.footer-status {
  margin-right: auto;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
h3 {
  margin: 28px 0 18px;
  scroll-margin-top: 12px;
}
.drawer-actions {
  margin: 0;
  justify-content: flex-end;
}
@media (max-width: 700px) {
  .draft-nav {
    gap: 5px;
  }
  .draft-nav button {
    padding: 8px 10px;
  }
  .footer-status {
    width: 100%;
  }
  .drawer-actions {
    gap: 8px;
    justify-content: flex-start;
  }
  .drawer-actions :deep(.el-button) {
    margin-left: 0;
  }
}
:deep(.el-select) {
  width: min(600px, 100%);
}
:deep(.el-alert) {
  margin: 12px 0;
}
</style>
