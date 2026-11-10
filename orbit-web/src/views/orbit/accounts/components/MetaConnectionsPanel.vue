<template>
  <section class="meta-connections">
    <MetaSyncPolicy :active="active" :context-key="contextKey" />
    <el-alert
      title="连接 Meta 仅用于读取账户、广告结构和投放数据，不授予广告写入权限。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="capability && !capability.configured"
      title="Meta 平台应用尚未配置完整。请由管理员配置应用、登录配置和固定回调后再授权；现有页面不会模拟连接成功。"
      type="warning"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="notice" :title="notice" type="success" :closable="false" />
    <div class="meta-toolbar">
      <el-button :loading="loading" :disabled="busy" @click="reload">刷新连接</el-button>
      <el-select
        v-if="capability?.applications?.length"
        v-model="selectedApplication"
        aria-label="选择授权应用"
        placeholder="选择授权应用"
        :disabled="locked"
        style="width: 280px"
      >
        <el-option
          v-for="app in capability?.applications || []"
          :key="app.id"
          :value="app.id"
          :label="`${app.name} · ${app.app_id}`"
        />
      </el-select>
      <el-button
        type="primary"
        :disabled="!canAuthorize || (!!capability?.applications?.length && !selectedApplication)"
        :loading="busy"
        @click="authorize()"
        >连接 Meta</el-button
      >
      <el-button
        v-if="pending"
        type="warning"
        :disabled="busy || !capability"
        @click="executePending"
        >重试原请求</el-button
      >
    </div>
    <div v-if="authorization" class="authorization-ready">
      <span
        >授权链接已准备，请前往 Meta 选择账户并确认读取授权。链接到期：{{
          authorization.expires_at
        }}</span
      >
      <el-button type="primary" @click="continueAuthorization">继续前往 Meta</el-button>
    </div>
    <el-table
      class="meta-desktop-table"
      :data="connections"
      v-loading="loading"
      border
      max-height="320"
      empty-text="暂无可管理的 Meta 连接"
    >
      <el-table-column label="连接类型" min-width="115"
        ><template #default="{ row }">{{
          row.kind === 'LOGIN' ? 'Meta 登录' : 'BM 系统用户'
        }}</template></el-table-column
      >
      <el-table-column label="状态" min-width="120"
        ><template #default="{ row }">{{
          statusLabels[row.status as keyof typeof statusLabels]
        }}</template></el-table-column
      >
      <el-table-column prop="principal_id" label="Meta 主体 ID" min-width="170"
        ><template #default="{ row }">{{ row.principal_id || '未知' }}</template></el-table-column
      >
      <el-table-column label="授权有效期" min-width="210"
        ><template #default="{ row }">{{
          row.expires_at || '平台未返回到期时间'
        }}</template></el-table-column
      >
      <el-table-column label="数据访问有效期" min-width="210"
        ><template #default="{ row }">{{
          row.data_access_expires_at || '平台未返回到期时间'
        }}</template></el-table-column
      >
      <el-table-column prop="updated_at" label="更新时间" min-width="210" />
      <el-table-column prop="revision" label="版本" width="75" />
      <el-table-column prop="id" label="连接 ID" min-width="280" />
      <el-table-column label="操作" fixed="right" width="220"
        ><template #default="{ row }">
          <el-button
            link
            type="primary"
            :disabled="locked || row.status !== 'ACTIVE'"
            @click="openAccounts(row)"
            >选择账户</el-button
          >
          <el-button v-if="canManageSync" link :disabled="locked" @click="openPolicy(row)"
            >采集设置</el-button
          >
          <el-button
            v-if="row.kind === 'LOGIN'"
            link
            :disabled="!canAuthorize"
            @click="authorize(row.id)"
            >重新授权</el-button
          >
          <el-button v-if="row.kind === 'BM'" link :disabled="locked" @click="showBmGuidance"
            >重新验证</el-button
          >
          <el-button
            link
            type="danger"
            :disabled="locked || row.status === 'DISCONNECTED'"
            @click="openDisconnect(row)"
            >断开</el-button
          >
        </template></el-table-column
      >
    </el-table>
    <div class="meta-mobile-cards">
      <p v-if="!connections.length">暂无可管理的 Meta 连接</p>
      <el-card v-for="row in connections" :key="row.id" shadow="never">
        <div class="connection-heading">
          <strong>{{ row.kind === 'LOGIN' ? 'Meta 登录' : 'BM 系统用户' }}</strong
          ><span>{{ statusLabels[row.status] }}</span>
        </div>
        <dl>
          <dt>Meta 主体 ID</dt>
          <dd>{{ row.principal_id || '未知' }}</dd>
          <dt>授权有效期</dt>
          <dd>{{ row.expires_at || '平台未返回到期时间' }}</dd>
          <dt>数据访问有效期</dt>
          <dd>{{ row.data_access_expires_at || '平台未返回到期时间' }}</dd>
          <dt>更新时间</dt>
          <dd>{{ row.updated_at }}</dd>
          <dt>版本</dt>
          <dd>{{ row.revision }}</dd>
          <dt>连接 ID</dt>
          <dd>{{ row.id }}</dd>
        </dl>
        <div class="connection-actions">
          <el-button
            link
            type="primary"
            :disabled="locked || row.status !== 'ACTIVE'"
            @click="openAccounts(row)"
            >选择账户</el-button
          >
          <el-button v-if="canManageSync" link :disabled="locked" @click="openPolicy(row)"
            >采集设置</el-button
          >
          <el-button
            v-if="row.kind === 'LOGIN'"
            link
            :disabled="!canAuthorize"
            @click="authorize(row.id)"
            >重新授权</el-button
          >
          <el-button v-if="row.kind === 'BM'" link :disabled="locked" @click="showBmGuidance"
            >重新验证</el-button
          >
          <el-button
            link
            type="danger"
            :disabled="locked || row.status === 'DISCONNECTED'"
            @click="openDisconnect(row)"
            >断开</el-button
          >
        </div>
      </el-card>
    </div>
    <el-card v-if="disconnectTarget" shadow="never" class="meta-subpanel">
      <template #header>断开连接确认</template>
      <p>断开后停止使用此连接继续读取数据，已保存的历史数据保留。连接：{{ disconnectTarget.id }}</p>
      <el-input
        v-model="reason"
        type="textarea"
        maxlength="500"
        show-word-limit
        :disabled="locked"
        aria-label="断开原因"
        placeholder="请填写断开原因"
      />
      <div class="meta-toolbar">
        <el-button :disabled="busy || !!pending" @click="disconnectTarget = null">取消</el-button
        ><el-button type="danger" :disabled="locked || !reason.trim()" @click="disconnect"
          >确认断开</el-button
        >
      </div>
    </el-card>
    <el-card v-if="selectedConnection" shadow="never" class="meta-subpanel">
      <template #header>选择接入账户与归属</template>
      <el-alert v-if="selectionError" :title="selectionError" type="warning" :closable="false" />
      <p>
        仅列出当前连接有权读取的账户。选择后仍由服务端重新验证平台权限、投手、团队、户商和渠道。
      </p>
      <el-form label-position="top" :disabled="locked || candidatesLoading">
        <div class="meta-ownership">
          <el-form-item label="投放师"
            ><el-select
              v-model="ownerId"
              filterable
              remote
              :remote-method="searchOwners"
              :loading="optionsLoading"
              placeholder="选择可分配投手"
              @change="ownerChanged"
            >
              <el-option
                v-for="owner in owners"
                :key="owner.id"
                :value="owner.id"
                :label="owner.name + ' · ' + owner.team_name"
              />
              <template #footer
                ><el-button v-if="ownerCursor" :loading="optionsLoading" @click="loadOwners(true)"
                  >加载更多投手</el-button
                ></template
              >
            </el-select></el-form-item
          >
          <el-form-item label="所属团队"
            ><el-input :model-value="selectedOwner?.team_name || '选择投放师后确定'" readonly
          /></el-form-item>
          <el-form-item label="所属户商"
            ><el-select
              v-model="vendorId"
              :disabled="!ownerId"
              :loading="optionsLoading"
              placeholder="选择投手可用的户商"
            >
              <el-option
                v-for="vendor in vendors"
                :key="vendor.value.id"
                :value="vendor.value.id"
                :label="vendor.value.name"
              />
              <template #footer
                ><el-button v-if="vendorCursor" @click="loadVendors(true)"
                  >加载更多户商</el-button
                ></template
              >
            </el-select></el-form-item
          >
          <el-form-item label="当前渠道（可暂不关联）"
            ><el-select
              v-model="channelId"
              clearable
              placeholder="选择已启用的 Meta 渠道"
              @visible-change="channelsVisible"
            >
              <el-option
                v-for="channel in channels"
                :key="channel.id"
                :value="channel.id"
                :label="channel.name"
              />
              <template #footer
                ><el-button v-if="channelCursor" @click="loadChannels(true)"
                  >加载更多渠道</el-button
                ></template
              >
            </el-select></el-form-item
          >
        </div>
        <el-form-item label="账户名称或 ID"
          ><el-input v-model="candidateQuery" clearable @input="candidatePage = 1"
        /></el-form-item>
      </el-form>
      <div class="meta-toolbar">
        <span>已选择 {{ selectedIds.length }} 个账户（最多 500 个）</span
        ><el-button :disabled="locked" @click="selectedIds = []">清空选择</el-button
        ><el-button :disabled="locked" @click="openAccounts(selectedConnection)"
          >重新读取账户</el-button
        >
      </div>
      <el-table
        :data="shownCandidates"
        border
        max-height="330"
        v-loading="candidatesLoading"
        empty-text="没有可接入的账户"
      >
        <el-table-column label="选择" width="70"
          ><template #default="{ row }"
            ><el-checkbox
              :model-value="selectedIds.includes(row.external_id)"
              :disabled="
                locked || (!selectedIds.includes(row.external_id) && selectedIds.length >= 500)
              "
              :aria-label="'选择账户 ' + row.external_id"
              @change="toggle(row.external_id, !!$event)" /></template
        ></el-table-column>
        <el-table-column prop="external_id" label="广告账户 ID" min-width="180" />
        <el-table-column label="账户名称" min-width="180"
          ><template #default="{ row }">{{ row.name ?? '未知' }}</template></el-table-column
        >
        <el-table-column label="币种" width="90"
          ><template #default="{ row }">{{ row.currency ?? '未知' }}</template></el-table-column
        >
        <el-table-column label="账户时区" min-width="200"
          ><template #default="{ row }">{{ row.timezone ?? '未知' }}</template></el-table-column
        >
      </el-table>
      <el-pagination
        v-model:current-page="candidatePage"
        :page-size="50"
        :total="filteredCandidates.length"
        layout="prev,pager,next"
      />
      <div class="meta-toolbar">
        <el-button :disabled="busy || !!pending" @click="selectedConnection = null"
          >取消选择</el-button
        ><el-button type="primary" :disabled="!canSelect" @click="selectAccounts"
          >确认接入所选账户</el-button
        >
      </div>
    </el-card>
    <el-dialog
      v-model="policyOpen"
      title="连接专属采集设置"
      width="min(680px, calc(100vw - 24px))"
      append-to-body
    >
      <MetaSyncPolicy
        v-if="policyConnection"
        :active="active && policyOpen"
        :context-key="contextKey"
        :connection-id="policyConnection.id"
        :connection-label="`${policyConnection.kind} · 主体 ${policyConnection.principal_id || '未知'}`"
      />
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import MetaSyncPolicy from './MetaSyncPolicy.vue'
import useUserStore from '@/store/modules/user'
import {
  metaConnectionApi,
  type MetaConnection,
  type MetaCapabilities,
  type MetaAuthorization,
  type MetaAccountCandidate,
  type MetaAccountSelection,
} from '@/api/orbit/meta-connections'
import { accountApi, type AccountOwnerOption, type AccountImportBatch } from '@/api/orbit/accounts'
import { referenceApi, ReferenceApiError, type ReferenceRecord } from '@/api/orbit/references'
import { channelApi, type Channel } from '@/api/orbit/channels'
const props = defineProps<{ active: boolean; contextKey: string }>()
const syncUser = useUserStore()
const canManageSync = computed(
  () =>
    syncUser.permissions.includes('*:*:*') ||
    ['system.integrations.manage', 'accounts.sync'].every((p) => syncUser.permissions.includes(p)),
)
const policyConnection = ref<MetaConnection | null>(null)
const policyOpen = ref(false)
function openPolicy(row: MetaConnection) {
  policyConnection.value = row
  policyOpen.value = true
}
watch(
  () => [props.active, props.contextKey],
  () => {
    policyOpen.value = false
    policyConnection.value = null
  },
)
const emit = defineEmits<{ accepted: [batch: AccountImportBatch] }>()
const selectedApplication = ref('')
const connections = ref<MetaConnection[]>([]),
  capability = ref<MetaCapabilities | null>(null),
  authorization = ref<MetaAuthorization | null>(null)
const loading = ref(false),
  busy = ref(false),
  error = ref(''),
  notice = ref('')
const statusLabels = { ACTIVE: '可读取', REAUTH_REQUIRED: '需要重新授权', DISCONNECTED: '已断开' }
type Pending = (
  | { kind: 'AUTH'; id?: string; applicationId?: string }
  | { kind: 'DISCONNECT'; id: string; revision: number; reason: string }
  | { kind: 'IMPORT'; id: string; value: MetaAccountSelection }
) & { key: string }
const pending = ref<Pending | null>(null),
  disconnectTarget = ref<MetaConnection | null>(null),
  reason = ref('')
const selectedConnection = ref<MetaConnection | null>(null),
  candidates = ref<MetaAccountCandidate[]>([]),
  candidatesLoading = ref(false),
  selectionError = ref(''),
  selectedIds = ref<string[]>([]),
  candidateQuery = ref(''),
  candidatePage = ref(1),
  importAllowed = ref(false)
const owners = ref<AccountOwnerOption[]>([]),
  vendors = ref<ReferenceRecord[]>([]),
  channels = ref<Channel[]>([]),
  ownerId = ref(''),
  vendorId = ref(''),
  channelId = ref(''),
  optionsLoading = ref(false)
const ownerCursor = ref<string | null>(null),
  vendorCursor = ref<string | null>(null),
  channelCursor = ref<string | null>(null)
let ownerQuery = '',
  generation = 0,
  selectionGeneration = 0,
  ownerGeneration = 0,
  vendorGeneration = 0,
  channelGeneration = 0,
  controller: AbortController | undefined
const locked = computed(() => busy.value || loading.value || !!pending.value || !capability.value)
const canAuthorize = computed(() => !locked.value && capability.value?.configured === true)
const selectedOwner = computed(() => owners.value.find((o) => o.id === ownerId.value))
const canSelect = computed(
  () =>
    !locked.value &&
    !candidatesLoading.value &&
    importAllowed.value &&
    selectedIds.value.length > 0 &&
    selectedIds.value.length <= 500 &&
    !!selectedOwner.value &&
    vendors.value.some((v) => v.value.id === vendorId.value),
)
const filteredCandidates = computed(() =>
  candidates.value.filter(
    (c) =>
      !candidateQuery.value ||
      (c.name ?? '').toLowerCase().includes(candidateQuery.value.toLowerCase()) ||
      c.external_id.includes(candidateQuery.value),
  ),
)
const shownCandidates = computed(() =>
  filteredCandidates.value.slice((candidatePage.value - 1) * 50, candidatePage.value * 50),
)
function explain(cause: unknown) {
  if (cause instanceof Error && 'code' in cause && cause.code === 'DIRECTORY_MAPPING_REQUIRED')
    return '业务资料或角色映射尚未补全，请先在个人中心核对邮箱，再由管理员核对人员与角色目录。'
  return cause instanceof ReferenceApiError && cause.status === 403
    ? '没有此操作权限，请联系管理员。'
    : cause instanceof ReferenceApiError && cause.status === 401
      ? '登录已失效，请重新登录。'
      : '连接操作未完成，请刷新或重试原请求。'
}
async function reload() {
  const epoch = ++generation
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  capability.value = null
  connections.value = []
  try {
    const cap = await metaConnectionApi.capabilities(controller.signal)
    if (epoch !== generation) return
    capability.value = cap
    if (!cap.applications?.some((app) => app.id === selectedApplication.value))
      selectedApplication.value = ''
    const p = await metaConnectionApi.list(controller.signal)
    if (epoch === generation) connections.value = p.items
  } catch (cause) {
    if (epoch === generation) error.value = explain(cause)
  } finally {
    if (epoch === generation) loading.value = false
  }
}
function authorize(id?: string) {
  if (!canAuthorize.value) return
  authorization.value = null
  pending.value = {
    kind: 'AUTH',
    id,
    applicationId: id ? undefined : selectedApplication.value || undefined,
    key: 'meta-auth-' + crypto.randomUUID(),
  }
  void executePending()
}
function openDisconnect(row: MetaConnection) {
  if (locked.value) return
  disconnectTarget.value = row
  reason.value = ''
  selectedConnection.value = null
}
function disconnect() {
  if (locked.value || !disconnectTarget.value || !reason.value.trim()) return
  pending.value = {
    kind: 'DISCONNECT',
    id: disconnectTarget.value.id,
    revision: disconnectTarget.value.revision,
    reason: reason.value.trim(),
    key: 'meta-disconnect-' + crypto.randomUUID(),
  }
  void executePending()
}
async function executePending() {
  if (!pending.value || busy.value) return
  const intent = pending.value,
    context = props.contextKey
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const cap = await metaConnectionApi.capabilities()
    if (context !== props.contextKey) return
    capability.value = cap
    if (intent.kind === 'AUTH') {
      if (!cap.configured) throw new ReferenceApiError(422, 'META_APP_UNCONFIGURED', '未配置')
      const result = await metaConnectionApi.authorize(
        cap.csrf_token,
        intent.key,
        intent.id,
        intent.applicationId,
      )
      if (context !== props.contextKey) return
      authorization.value = result
      pending.value = null
    } else if (intent.kind === 'DISCONNECT') {
      await metaConnectionApi.disconnect(
        intent.id,
        intent.revision,
        intent.reason,
        cap.csrf_token,
        intent.key,
      )
      if (context !== props.contextKey) return
      pending.value = null
      disconnectTarget.value = null
      notice.value = '已断开连接。'
      await reload()
    } else {
      await accountApi.capabilities()
      const result = await metaConnectionApi.select(
        intent.id,
        intent.value,
        cap.csrf_token,
        intent.key,
      )
      if (context !== props.contextKey) return
      pending.value = null
      selectedConnection.value = null
      notice.value = '账户接入已受理，请查看逐项处理结果。'
      emit('accepted', result)
    }
  } catch (cause) {
    if (context !== props.contextKey) return
    const rejected =
      cause instanceof ReferenceApiError &&
      [400, 401, 403, 404, 409, 410, 422].includes(cause.status)
    if (rejected) pending.value = null
    error.value =
      explain(cause) + (rejected ? '' : '提交结果尚未确认；请使用“重试原请求”，不要重复新建。')
  } finally {
    if (context === props.contextKey) busy.value = false
  }
}
function showBmGuidance() {
  notice.value = ''
  error.value =
    'BM 系统用户连接请前往“系统配置”，在对应 Meta/BM 配置行重新验证并接入读取；不能使用个人登录授权替代。'
}
function continueAuthorization() {
  if (!authorization.value) return
  try {
    metaConnectionApi.navigate(authorization.value)
  } catch {
    authorization.value = null
    error.value = '授权链接已过期，请重新发起。'
  }
}
function resetSelection() {
  selectionGeneration++
  ownerGeneration++
  vendorGeneration++
  channelGeneration++
  candidates.value = []
  selectedIds.value = []
  owners.value = []
  vendors.value = []
  channels.value = []
  ownerId.value = ''
  vendorId.value = ''
  channelId.value = ''
  ownerCursor.value = null
  vendorCursor.value = null
  channelCursor.value = null
  candidatePage.value = 1
  candidateQuery.value = ''
  selectionError.value = ''
  importAllowed.value = false
}
async function openAccounts(row: MetaConnection) {
  if (locked.value || row.status !== 'ACTIVE') return
  resetSelection()
  selectedConnection.value = row
  disconnectTarget.value = null
  const epoch = selectionGeneration
  candidatesLoading.value = true
  try {
    await accountApi.capabilities()
    if (epoch !== selectionGeneration) return
    importAllowed.value = true
    const result = await metaConnectionApi.accounts(row.id)
    if (epoch !== selectionGeneration) return
    if (result.next_cursor) throw new Error('INCOMPLETE_ACCOUNT_SCOPE')
    candidates.value = result.items
    await loadOwners()
  } catch (cause) {
    if (epoch === selectionGeneration) {
      selectionError.value = explain(cause)
      candidates.value = []
      importAllowed.value = false
    }
  } finally {
    if (epoch === selectionGeneration) candidatesLoading.value = false
  }
}
async function loadOwners(more = false) {
  const epoch = ++ownerGeneration
  optionsLoading.value = true
  try {
    const q = new URLSearchParams({ q: ownerQuery })
    if (more && ownerCursor.value) q.set('cursor', ownerCursor.value)
    const result = await accountApi.owners(q)
    if (epoch !== ownerGeneration) return
    owners.value = more ? [...owners.value, ...result.items] : result.items
    ownerCursor.value = result.next_cursor
  } catch {
    if (epoch === ownerGeneration) {
      owners.value = []
      selectionError.value = '投放师候选读取失败，请重新读取账户。'
    }
  } finally {
    if (epoch === ownerGeneration) optionsLoading.value = false
  }
}
async function searchOwners(q: string) {
  ownerQuery = q
  await loadOwners()
}
async function ownerChanged() {
  vendorGeneration++
  vendorId.value = ''
  vendors.value = []
  vendorCursor.value = null
  channelId.value = ''
  await loadVendors()
}
async function loadVendors(more = false) {
  if (!ownerId.value) return
  const epoch = ++vendorGeneration
  optionsLoading.value = true
  try {
    const q = new URLSearchParams({ owner_user_id: ownerId.value, page_size: '50' })
    if (more && vendorCursor.value) q.set('cursor', vendorCursor.value)
    const result = await referenceApi.list('VENDOR', q)
    if (epoch !== vendorGeneration) return
    const valid = result.items.filter((v) => v.value.availability === 'AVAILABLE')
    vendors.value = more ? [...vendors.value, ...valid] : valid
    vendorCursor.value = result.next_cursor
  } catch {
    if (epoch === vendorGeneration) {
      vendors.value = []
      selectionError.value = '户商候选读取失败，请重新选择投放师。'
    }
  } finally {
    if (epoch === vendorGeneration) optionsLoading.value = false
  }
}
function channelsVisible(visible: boolean) {
  if (visible) void loadChannels()
}
async function loadChannels(more = false) {
  if (channels.value.length && !more) return
  const epoch = ++channelGeneration
  try {
    const q = new URLSearchParams({ page_size: '50', status: 'ENABLED' })
    if (more && channelCursor.value) q.set('cursor', channelCursor.value)
    const result = await channelApi.list(q)
    if (epoch !== channelGeneration) return
    const valid = result.items.filter((c) => c.media === 'META' && c.status === 'ENABLED')
    channels.value = more ? [...channels.value, ...valid] : valid
    channelCursor.value = result.next_cursor
  } catch {
    if (epoch === channelGeneration) {
      channels.value = []
      channelId.value = ''
      selectionError.value = '渠道候选不可用，可暂不关联渠道。'
    }
  }
}
function toggle(id: string, checked: boolean) {
  if (locked.value) return
  if (checked && !selectedIds.value.includes(id) && selectedIds.value.length < 500)
    selectedIds.value.push(id)
  else if (!checked) selectedIds.value = selectedIds.value.filter((v) => v !== id)
}
function selectAccounts() {
  if (!canSelect.value || !selectedConnection.value || !selectedOwner.value) return
  pending.value = {
    kind: 'IMPORT',
    id: selectedConnection.value.id,
    key: 'meta-accounts-' + crypto.randomUUID(),
    value: {
      account_ids: [...selectedIds.value],
      operator_user_id: selectedOwner.value.id,
      owner_team_id: selectedOwner.value.team_id,
      vendor_id: vendorId.value,
      channel_id: channelId.value || null,
    },
  }
  void executePending()
}
watch(
  () => props.active,
  (active) => {
    if (active) void reload()
    else {
      controller?.abort()
      generation++
      loading.value = false
      resetSelection()
      selectedConnection.value = null
      authorization.value = null
    }
  },
  { immediate: true },
)
watch(
  () => props.contextKey,
  () => {
    controller?.abort()
    generation++
    resetSelection()
    connections.value = []
    capability.value = null
    authorization.value = null
    pending.value = null
    busy.value = false
    selectedConnection.value = null
    disconnectTarget.value = null
    if (props.active) void reload()
  },
)
onBeforeUnmount(() => {
  controller?.abort()
  generation++
  selectionGeneration++
  ownerGeneration++
  vendorGeneration++
  channelGeneration++
})
</script>
<style scoped>
.meta-mobile-cards {
  display: none;
}
@media (max-width: 640px) {
  .meta-desktop-table {
    display: none;
  }
  .meta-mobile-cards {
    display: grid;
    gap: 12px;
  }
  .connection-heading {
    display: flex;
    gap: 12px;
    justify-content: space-between;
  }
  .meta-mobile-cards dl {
    display: grid;
    grid-template-columns: 100px minmax(0, 1fr);
    gap: 8px;
    font-size: 13px;
  }
  .meta-mobile-cards dt {
    color: var(--el-text-color-secondary);
  }
  .meta-mobile-cards dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .connection-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .connection-actions .el-button {
    margin-left: 0;
  }
}

.meta-connections {
  min-width: 0;
}
.meta-toolbar,
.authorization-ready {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin: 12px 0;
}
.authorization-ready {
  overflow-wrap: anywhere;
}
.meta-subpanel {
  margin-top: 16px;
}
.meta-ownership {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.meta-ownership .el-select {
  width: 100%;
}
.meta-connections .el-alert {
  margin-bottom: 10px;
}
.meta-connections .el-pagination {
  margin-top: 12px;
  max-width: 100%;
  overflow-x: auto;
}
@media (max-width: 600px) {
  .meta-ownership {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
