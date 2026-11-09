<template>
  <div class="app-container environment-page">
    <el-card shadow="never">
      <template #header
        ><div class="toolbar">
          <strong>AdsPower 监测</strong>
          <div>
            <el-button
              v-if="can('read') || canManage('enroll')"
              :disabled="busy"
              @click="bindingsOpen = true"
              >账户环境关联</el-button
            >
            <el-button v-if="activePending" @click="recover" :disabled="busy"
              >恢复未确认操作</el-button
            >
            <el-button
              v-if="canManage('enroll')"
              type="primary"
              :disabled="busy || !!activePending"
              @click="openCreate"
              >登记机器</el-button
            >
          </div>
        </div></template
      >
      <el-alert
        :title="
          capability?.data_role === 'SUPER_ADMIN'
            ? '设备由超级管理员统一管理；登记不代表在线或已授权广告操作。'
            : '仅展示当前可见、已绑定账户的环境；设备登记与撤销由超级管理员统一管理。'
        "
        type="info"
        :closable="false"
      />
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
      <el-button v-if="!capability" @click="initialize" :loading="loading">重新读取权限</el-button>
      <template v-if="can('read')">
        <el-form inline @submit.prevent="search">
          <el-form-item label="机器名称"
            ><el-input v-model="filters.q" clearable aria-label="查询机器名称"
          /></el-form-item>
          <el-form-item label="状态"
            ><el-select
              v-model="filters.status"
              clearable
              class="status-filter"
              aria-label="机器状态"
              ><el-option
                v-for="(label, key) in states"
                :key="key"
                :value="key"
                :label="label" /></el-select
          ></el-form-item>
          <el-form-item label="登记起日（北京）"
            ><el-date-picker v-model="filters.date_from" type="date" value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item label="登记止日（北京）"
            ><el-date-picker v-model="filters.date_to" type="date" value-format="YYYY-MM-DD"
          /></el-form-item>
          <el-form-item
            ><el-button type="primary" :loading="loading" @click="search">查询</el-button
            ><el-button :disabled="loading" @click="reset">重置</el-button></el-form-item
          >
        </el-form>
        <details class="advanced-filters">
          <summary>关联筛选</summary>
          <el-form inline @submit.prevent="search"
            ><el-form-item label="当前投手 UUID"
              ><el-input
                v-model="filters.operator_user_id"
                aria-label="当前投手 UUID"
                placeholder="当前绑定账户的投手 UUID" /></el-form-item
            ><el-form-item label="渠道"
              ><el-input disabled placeholder="尚无关联事实来源" /></el-form-item
            ><el-form-item label="指标配置"
              ><el-input disabled placeholder="尚无关联事实来源" /></el-form-item
            ><el-form-item label="实体类型"
              ><el-select disabled placeholder="尚无关联事实来源" style="width: 180px"
                ><el-option label="系列" value="CAMPAIGN" /><el-option
                  label="广告组"
                  value="ADSET" /><el-option label="广告" value="AD" /></el-select></el-form-item
          ></el-form>
          <p class="muted">
            渠道、指标配置与实体类型尚无关联事实来源，暂不可筛选；不会忽略筛选并展示全部数据。
          </p>
        </details>
        <el-table v-loading="loading" :data="items" border empty-text="暂无当前可见设备">
          <el-table-column prop="name" label="机器名称" min-width="140" />
          <el-table-column label="操作" width="185"
            ><template #default="{ row }"
              ><el-button
                link
                type="primary"
                :disabled="busy || !!activePending"
                @click="openDetail(row.id)"
                >详情</el-button
              ><el-button
                v-if="canManage('enroll')"
                link
                type="primary"
                :disabled="busy || !!activePending || row.state === 'REVOKED'"
                @click="openEdit(row.id)"
                >修改</el-button
              ><el-button
                v-if="canManage('revoke')"
                link
                type="danger"
                :disabled="busy || !!activePending || row.state === 'REVOKED'"
                @click="openRevoke(row.id)"
                >撤销</el-button
              ></template
            ></el-table-column
          >
          <el-table-column label="机器状态" width="100"
            ><template #default="{ row }">{{
              states[row.state as keyof typeof states]
            }}</template></el-table-column
          >
          <el-table-column prop="endpoint" label="本地 API 地址" min-width="210" />
          <el-table-column prop="probe_interval" label="探测周期（秒）" width="130" />
          <el-table-column label="最近可信心跳" min-width="180"
            ><template #default="{ row }">{{
              row.last_heartbeat || '未知（未收到可信心跳）'
            }}</template></el-table-column
          >
          <el-table-column label="登录 / 身份 / 能力" min-width="180"
            ><template #default>未知，查看分层详情</template></el-table-column
          >
          <el-table-column prop="id" label="Agent ID" min-width="290" />
          <el-table-column prop="revision" label="版本" width="80" />
        </el-table>
        <div class="pagination">
          <el-select v-model="pageSize" class="page-size" :disabled="loading" @change="search"
            ><el-option
              v-for="size in [20, 50, 100, 200]"
              :key="size"
              :label="`${size} 条/页`"
              :value="size" /></el-select
          ><el-button :disabled="loading || pageIndex === 0" @click="move(-1)">上一页</el-button
          ><span>第 {{ pageIndex + 1 }} 页</span
          ><el-button :disabled="loading || !nextCursor" @click="move(1)">下一页</el-button
          ><span v-if="dataAsOf" class="muted">数据时刻 {{ dataAsOf }}</span>
        </div>
      </template>
      <p v-else>当前无设备读取权限；允许的登记操作仍可独立使用。</p>
    </el-card>
    <el-dialog
      v-model="dialog"
      :title="dialogTitle"
      width="760px"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      :before-close="closeDialog"
      destroy-on-close
    >
      <el-alert v-if="dialogError" :title="dialogError" type="error" :closable="false" />
      <el-alert
        v-if="activePending"
        title="上次操作结果尚未确认。原内容、版本和请求标识已在本页内存中保留；请勿重复新建。关闭弹窗后可恢复，刷新或离开页面会丢失本次恢复信息。"
        type="warning"
        :closable="false"
      />
      <template v-if="mode === 'DETAIL' && selected">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="机器名称">{{ selected.name }}</el-descriptions-item
          ><el-descriptions-item label="机器状态">{{
            states[selected.state]
          }}</el-descriptions-item>
          <el-descriptions-item label="Agent ID" :span="2">{{ selected.id }}</el-descriptions-item
          ><el-descriptions-item label="版本">{{ selected.revision }}</el-descriptions-item>
          <el-descriptions-item label="探测周期（秒）">{{
            selected.probe_interval
          }}</el-descriptions-item
          ><el-descriptions-item label="本地 API 地址" :span="2">{{
            selected.endpoint
          }}</el-descriptions-item>
          <el-descriptions-item label="最近可信心跳" :span="2">{{
            selected.last_heartbeat || '未知，未收到可信心跳'
          }}</el-descriptions-item>
          <el-descriptions-item
            v-for="layer in layers"
            :key="layer.name"
            :label="layer.name"
            :span="2"
            >{{ layer.value }}</el-descriptions-item
          >
        </el-descriptions>
        <el-button class="probe" disabled>主动探测尚未接通</el-button>
      </template>
      <AgentRegistrationForm
        v-else-if="mode === 'CREATE' || mode === 'EDIT'"
        :key="formKey"
        :initial-value="formInitial"
        :disabled="busy || !!activePending || !canManage('enroll')"
        :submit-label="mode === 'EDIT' ? '保存修改' : '登记机器'"
        @submit="save"
      />
      <el-form v-else-if="mode === 'REVOKE'" label-position="top" @submit.prevent="revoke">
        <p>
          撤销
          {{ selected?.name || activePending?.id }}
          的设备登记；此操作不会伪造设备证书签发或远端回执。
        </p>
        <el-form-item label="撤销原因"
          ><el-input
            v-model="reason"
            type="textarea"
            aria-label="撤销原因"
            :disabled="busy || !!activePending"
        /></el-form-item>
        <el-button
          type="danger"
          native-type="submit"
          :disabled="busy || !!activePending || !canManage('revoke')"
          >确认撤销</el-button
        >
      </el-form>
      <template #footer
        ><el-button :disabled="busy" @click="closeDialog()">关闭</el-button
        ><el-button v-if="activePending" type="warning" :loading="busy" @click="retry"
          >重试原请求</el-button
        ></template
      >
    </el-dialog>
    <ProfileBindingsPanel
      v-model="bindingsOpen"
      :can-read="can('read')"
      :can-write="canManage('enroll')"
      :context-key="JSON.stringify([user.id, user.permissions])"
    />
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import AgentRegistrationForm from './AgentRegistrationForm.vue'
import ProfileBindingsPanel from './ProfileBindingsPanel.vue'
import {
  environmentApi,
  AgentApiError,
  type Agent,
  type AgentCapability,
  type AgentIntent,
  type AgentQuery,
  type AgentWrite,
} from '@/api/orbit/environments'
const user = useUserStore()
const bindingsOpen = ref(false)
const can = (action: string) =>
  user.permissions.includes('*:*:*') || user.permissions.includes(`environments.${action}`)
const capability = ref<AgentCapability | null>(null)
const canManage = (action: string) => capability.value?.data_role === 'SUPER_ADMIN' && can(action)
const states = { READY: '心跳正常', SUSPECT: '心跳疑似中断', OFFLINE: '离线', REVOKED: '已撤销' }
const layers = [
  { name: '设备证书', value: '未知；设备证书签发与校验尚未接通。' },
  { name: '客户端/API', value: '未知；控制面不会探测用户 localhost。' },
  { name: 'Profile', value: '未知；请通过独立账户环境绑定记录核对。' },
  { name: '代理', value: '未知；尚无可信代理探测结果。' },
  { name: 'Meta 登录', value: '未知；没有可信登录探测结果。' },
  { name: '账户身份', value: '未知；登记及关联不代表账户身份已核验。' },
  { name: '操作能力', value: '未知；各动作、通道、层级及版本需独立验证。' },
  { name: '租约', value: '未知；无可验证的租约或 fencing 数据。' },
  { name: '当前任务', value: '未知；未接入可信任务状态。' },
  { name: '故障', value: '未知；没有可信故障观察数据。' },
]
const loading = ref(false),
  busy = ref(false),
  error = ref(''),
  notice = ref(''),
  dialogError = ref('')
const items = ref<Agent[]>([]),
  dataAsOf = ref(''),
  nextCursor = ref<string | null>(null),
  pageIndex = ref(0),
  pageSize = ref(20)
const filters = reactive({ q: '', status: '', date_from: '', date_to: '', operator_user_id: '' })
let applied: AgentQuery = { page_size: 20 },
  cursors: (string | undefined)[] = [undefined]
let generation = 0,
  controller: AbortController | undefined
const pending = reactive(new Map<string, AgentIntent>())
const identity = (cap: Pick<AgentCapability, 'actor_id' | 'tenant_id'>) =>
  `${cap.tenant_id}:${cap.actor_id}`
const activePending = computed(() =>
  capability.value ? pending.get(identity(capability.value)) : undefined,
)
const dialog = ref(false),
  mode = ref<'CREATE' | 'EDIT' | 'REVOKE' | 'DETAIL'>('CREATE'),
  selected = ref<Agent | null>(null),
  reason = ref(''),
  formKey = ref(0),
  formInitial = ref<AgentWrite | undefined>()
const dialogTitle = computed(
  () =>
    ({ CREATE: '登记机器', EDIT: '修改设备登记', REVOKE: '撤销设备登记', DETAIL: '环境监测详情' })[
      mode.value
    ],
)
function clearVisible() {
  items.value = []
  selected.value = null
  dialog.value = false
  formInitial.value = undefined
  reason.value = ''
  error.value = ''
  notice.value = ''
  dialogError.value = ''
  nextCursor.value = null
  dataAsOf.value = ''
}
async function initialize() {
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  capability.value = null
  clearVisible()
  loading.value = true
  const operation = can('read')
    ? 'READ'
    : can('enroll')
      ? 'ENROLL'
      : can('revoke')
        ? 'REVOKE'
        : can('probe')
          ? 'PROBE'
          : null
  if (!operation) {
    error.value = '没有环境模块权限'
    loading.value = false
    return
  }
  try {
    const cap = await environmentApi.capabilities(operation, controller.signal)
    if (current !== generation) return
    capability.value = cap
    if (can('read')) {
      applied = { page_size: pageSize.value }
      cursors = [undefined]
      await load(0)
    }
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    if (current === generation) loading.value = false
  }
}
const message = (e: unknown) => (e instanceof Error ? e.message : '设备请求失败')
async function load(index: number) {
  dataAsOf.value = ''
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  items.value = []
  nextCursor.value = null
  try {
    const result = await environmentApi.list(
      { ...applied, cursor: cursors[index] },
      controller.signal,
    )
    if (current !== generation) return
    items.value = result.items
    nextCursor.value = result.next_cursor
    dataAsOf.value = result.data_as_of
    pageIndex.value = index
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    if (current === generation) loading.value = false
  }
}
function search() {
  if (busy.value) return
  const q = filters.q.normalize('NFC').trim()
  if (
    filters.operator_user_id &&
    !/^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(filters.operator_user_id)
  ) {
    error.value = '当前投手需填写完整 UUID'
    return
  }
  if ([...q].length > 100 || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(filters.q)) {
    error.value = '名称查询最多 100 个字符且不能含控制字符'
    return
  }
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    error.value = '登记起日不能晚于止日'
    return
  }
  applied = {
    page_size: pageSize.value,
    ...(filters.operator_user_id ? { operator_user_id: filters.operator_user_id } : {}),
    ...(q ? { q } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.date_from ? { date_from: filters.date_from } : {}),
    ...(filters.date_to ? { date_to: filters.date_to } : {}),
  }
  cursors = [undefined]
  void load(0)
}
function reset() {
  if (busy.value) return
  Object.assign(filters, { q: '', status: '', date_from: '', date_to: '', operator_user_id: '' })
  search()
}
function move(delta: number) {
  if (loading.value || busy.value) return
  if (delta > 0) {
    if (!nextCursor.value) return
    cursors[pageIndex.value + 1] = nextCursor.value
  }
  void load(pageIndex.value + delta)
}
function openCreate() {
  if (!canManage('enroll') || activePending.value || busy.value) return
  mode.value = 'CREATE'
  selected.value = null
  formInitial.value = undefined
  dialogError.value = ''
  formKey.value++
  dialog.value = true
}
async function openRecord(id: string, next: 'DETAIL' | 'EDIT' | 'REVOKE') {
  if (activePending.value) return
  if (
    busy.value ||
    (next !== 'DETAIL' &&
      (activePending.value || !canManage(next === 'EDIT' ? 'enroll' : 'revoke')))
  )
    return
  const current = generation
  busy.value = true
  error.value = ''
  try {
    const row = await environmentApi.get(id)
    if (current !== generation) return
    selected.value = row
    mode.value = next
    formInitial.value = {
      name: row.name,
      endpoint: row.endpoint,
      probe_interval: row.probe_interval,
    }
    reason.value = ''
    dialogError.value = ''
    formKey.value++
    dialog.value = true
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    busy.value = false
  }
}
const openDetail = (id: string) => openRecord(id, 'DETAIL'),
  openEdit = (id: string) => openRecord(id, 'EDIT'),
  openRevoke = (id: string) => openRecord(id, 'REVOKE')
function closeDialog(done?: () => void) {
  if (busy.value) return
  dialog.value = false
  done?.()
}
function recover() {
  const intent = activePending.value
  if (!intent || busy.value) return
  mode.value = intent.operation === 'REVOKE' ? 'REVOKE' : intent.id ? 'EDIT' : 'CREATE'
  formInitial.value = 'name' in intent.body ? { ...intent.body } : undefined
  reason.value = 'reason' in intent.body ? intent.body.reason : ''
  formKey.value++
  dialogError.value = ''
  dialog.value = true
}
async function save(body: AgentWrite) {
  if (!canManage('enroll') || activePending.value || busy.value) return
  await send({
    operation: 'ENROLL',
    body,
    ...(mode.value === 'EDIT' && selected.value
      ? { id: selected.value.id, revision: selected.value.revision }
      : {}),
  })
}
async function revoke() {
  if (!canManage('revoke') || activePending.value || busy.value || !selected.value) return
  const value = reason.value.normalize('NFC').trim()
  if (
    !value ||
    [...value].length > 1000 ||
    /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(reason.value)
  ) {
    dialogError.value = '撤销原因需为 1 至 1000 个字符且不能含控制字符'
    return
  }
  await send({
    operation: 'REVOKE',
    id: selected.value.id,
    revision: selected.value.revision,
    body: { reason: value },
  })
}
async function retry() {
  const intent = activePending.value
  if (intent && !busy.value) await send(intent, true)
}
async function send(
  input: Pick<AgentIntent, 'operation' | 'body' | 'id' | 'revision'>,
  retrying = false,
) {
  if (busy.value) return
  const old = retrying ? activePending.value : undefined
  if (retrying && !old) return
  if (!can(input.operation === 'ENROLL' ? 'enroll' : 'revoke')) {
    dialogError.value = '当前无此操作权限；未确认请求仍保留'
    return
  }
  busy.value = true
  dialogError.value = ''
  notice.value = ''
  const current = generation
  let intent: AgentIntent | undefined
  try {
    const cap = await environmentApi.capabilities(input.operation)
    if (current !== generation) return
    if (cap.data_role !== 'SUPER_ADMIN') throw new Error('仅超级管理员可以管理设备')
    if (
      (old && identity(old) !== identity(cap)) ||
      (capability.value && identity(capability.value) !== identity(cap))
    ) {
      clearVisible()
      capability.value = cap
      error.value = '身份已变化，已隐藏原操作内容；不能使用其他身份重试'
      return
    }
    capability.value = cap
    intent = old ?? {
      ...input,
      actor_id: cap.actor_id,
      tenant_id: cap.tenant_id,
      key: crypto.randomUUID(),
      body: JSON.parse(JSON.stringify(input.body)),
    }
    pending.set(identity(intent), intent)
    const result = await environmentApi.write(JSON.parse(JSON.stringify(intent)), cap.csrf_token!)
    pending.delete(identity(intent))
    if (current !== generation) return
    dialog.value = false
    selected.value = null
    formInitial.value = undefined
    reason.value = ''
    notice.value = '设备资料已保存；登记不代表在线、登录有效或可执行。'
    if (can('read')) {
      try {
        await environmentApi.get(result.id)
        if (current !== generation) return
        cursors = [undefined]
        await load(0)
      } catch {
        notice.value = '操作已保存，但回读未完成。请重新查询，不要重复写入。'
      }
    }
  } catch (e) {
    if (intent && !old && !(e instanceof AgentApiError && e.unknown_result))
      pending.delete(identity(intent))
    if (current === generation) dialogError.value = message(e)
  } finally {
    busy.value = false
  }
}
watch(
  () => JSON.stringify([user.id, user.permissions]),
  () => {
    void initialize()
  },
)
onMounted(initialize)
onBeforeUnmount(() => {
  generation++
  controller?.abort()
  pending.clear()
})
</script>
<style scoped>
.toolbar,
.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar {
  justify-content: space-between;
}
.pagination {
  margin-top: 16px;
}
.status-filter {
  width: 150px;
}
.page-size {
  width: 120px;
}
.el-alert {
  margin-bottom: 14px;
}
.el-form {
  margin-top: 16px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.probe {
  margin-top: 16px;
}
</style>
