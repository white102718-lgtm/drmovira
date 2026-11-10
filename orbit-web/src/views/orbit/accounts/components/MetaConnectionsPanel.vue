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
    <p>
      授权完成后自动接入本次授权可访问的全部账户，投放师为发起授权的用户；户商可留空后补。已有连接需重新授权才会启动自动接入。
    </p>
    <el-card
      v-for="row in connections.filter((item) => item.auto_import)"
      :key="row.id"
      class="meta-subpanel"
      shadow="never"
    >
      <template v-if="row.auto_import">
        <p>
          自动接入：{{ importStates[row.auto_import.state] }} · 主体
          {{ row.principal_id || '未知' }}
        </p>
        <p>
          已发现 {{ row.auto_import.total }} 个账户；成功 {{ row.auto_import.success_count }}，失败
          {{ row.auto_import.failed_count }}，重复 {{ row.auto_import.duplicate_count }}
        </p>
        <p v-if="['QUEUED', 'DISCOVERING', 'IMPORTING'].includes(row.auto_import.state)">
          处理尚未完成，数量以服务端实际进度为准。
        </p>
        <p v-if="row.auto_import.error_code">
          接入未完成：{{ row.auto_import.error_code }}。请刷新核对；如需重新接入，请重新授权。
        </p>
        <el-button
          v-for="(batch, index) in row.auto_import.batches"
          :key="batch.id"
          :disabled="busy"
          @click="showImportResult(batch.id)"
          >{{
            row.auto_import.batches.length > 1 ? `查看第 ${index + 1} 批结果` : '查看逐项结果'
          }}</el-button
        >
      </template>
    </el-card>
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
} from '@/api/orbit/meta-connections'
import { accountApi, type AccountImportBatch } from '@/api/orbit/accounts'
import { ReferenceApiError } from '@/api/orbit/references'
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
  capability = ref<MetaCapabilities | null>(null)
const loading = ref(false),
  busy = ref(false),
  error = ref(''),
  notice = ref('')
const statusLabels = { ACTIVE: '可读取', REAUTH_REQUIRED: '需要重新授权', DISCONNECTED: '已断开' }
type Pending = (
  | { kind: 'AUTH'; id?: string; applicationId?: string }
  | { kind: 'DISCONNECT'; id: string; revision: number; reason: string }
) & { key: string }
const pending = ref<Pending | null>(null),
  disconnectTarget = ref<MetaConnection | null>(null),
  reason = ref('')
let generation = 0,
  controller: AbortController | undefined
const locked = computed(() => busy.value || loading.value || !!pending.value || !capability.value)
const canAuthorize = computed(() => !locked.value && capability.value?.configured === true)
const importStates = {
  QUEUED: '已排队',
  DISCOVERING: '读取授权账户中',
  IMPORTING: '接入中',
  SUCCEEDED: '已完成',
  PARTIAL_SUCCESS: '部分成功',
  FAILED: '失败',
}
let pollTimer: ReturnType<typeof setTimeout> | undefined
async function showImportResult(id: string) {
  const context = props.contextKey
  busy.value = true
  try {
    const result = await accountApi.getImport(id)
    if (context === props.contextKey) emit('accepted', result)
  } catch (cause) {
    if (context === props.contextKey) error.value = explain(cause)
  } finally {
    if (context === props.contextKey) busy.value = false
  }
}
function explain(cause: unknown) {
  if (cause instanceof Error && 'code' in cause && cause.code === 'DIRECTORY_MAPPING_REQUIRED')
    return '业务资料或角色映射尚未补全，请先在个人中心核对邮箱，再由管理员核对人员与角色目录。'
  return cause instanceof ReferenceApiError && cause.status === 403
    ? '没有此操作权限，请联系管理员。'
    : cause instanceof ReferenceApiError && cause.status === 401
      ? '登录已失效，请重新登录。'
      : '连接操作未完成，请刷新或重试原请求。'
}
async function reload(background: unknown = false) {
  clearTimeout(pollTimer)
  const epoch = ++generation
  controller?.abort()
  controller = new AbortController()
  // 后台轮询保留正在操作的下拉框和已展示结果，避免每三秒中断选择。
  if (background !== true) {
    loading.value = true
    capability.value = null
    connections.value = []
  }
  error.value = ''
  try {
    const cap = await metaConnectionApi.capabilities(controller.signal)
    if (epoch !== generation) return
    capability.value = cap
    if (!cap.applications?.some((app) => app.id === selectedApplication.value))
      selectedApplication.value = ''
    const p = await metaConnectionApi.list(controller.signal)
    if (epoch === generation) {
      connections.value = p.items
      if (
        props.active &&
        p.items.some(
          (row) =>
            row.auto_import &&
            (['QUEUED', 'DISCOVERING', 'IMPORTING'].includes(row.auto_import.state) ||
              row.auto_import.batches.some((batch) => ['QUEUED', 'RUNNING'].includes(batch.state))),
        )
      )
        pollTimer = setTimeout(() => void reload(true), 3000)
    }
  } catch (cause) {
    if (epoch === generation) error.value = explain(cause)
  } finally {
    if (epoch === generation) loading.value = false
  }
}
function authorize(id?: string) {
  if (!canAuthorize.value) return
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
      pending.value = null
      metaConnectionApi.navigate(result)
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
watch(
  () => props.active,
  (active) => {
    if (active) void reload()
    else {
      clearTimeout(pollTimer)
      controller?.abort()
      generation++
      loading.value = false
    }
  },
  { immediate: true },
)
watch(
  () => props.contextKey,
  () => {
    clearTimeout(pollTimer)
    controller?.abort()
    generation++
    connections.value = []
    capability.value = null
    pending.value = null
    busy.value = false
    disconnectTarget.value = null
    if (props.active) void reload()
  },
)
onBeforeUnmount(() => {
  clearTimeout(pollTimer)
  controller?.abort()
  generation++
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
