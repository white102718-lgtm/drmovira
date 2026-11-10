<template>
  <div class="app-container account-page">
    <h2>广告账户</h2>
    <el-alert
      v-if="metaReturnNotice"
      :title="metaReturnNotice"
      type="info"
      :closable="true"
      @close="metaReturnNotice = ''"
    />
    <el-form inline @submit.prevent="reload">
      <el-form-item label="名称或完整账户ID"
        ><el-input
          v-model="query"
          clearable
          maxlength="100"
          placeholder="名称前缀或完整数字ID"
          @keyup.enter="reload"
      /></el-form-item>
      <el-form-item label="投放师"
        ><el-select
          v-model="owner"
          filterable
          remote
          clearable
          :remote-method="searchOwners"
          :loading="ownersLoading"
          placeholder="全部可读投手"
          style="width: 180px"
          @change="reload"
        >
          <el-option
            v-for="person in owners"
            :key="person.id"
            :value="person.id"
            :label="person.name"
          />
          <template #footer
            ><el-button v-if="ownerCursor" :loading="ownersLoading" @click="moreOwners"
              >加载更多投手</el-button
            ></template
          >
        </el-select></el-form-item
      >
      <el-form-item label="账户状态"
        ><el-select v-model="status" clearable style="width: 140px" @change="reload"
          ><el-option
            v-for="(label, code) in accountStates"
            :key="code"
            :value="code"
            :label="label" /></el-select
      ></el-form-item>
      <el-form-item label="消耗时间"
        ><el-button @click="openDates">{{ periodLabel }}</el-button></el-form-item
      >
      <el-form-item
        ><el-button type="primary" :disabled="loading" @click="reload">查询</el-button
        ><el-button :disabled="loading" @click="reset">重置</el-button
        ><el-button @click="openColumns">列设置</el-button
        ><el-button @click="router.push('/orbit/account-scopes')">账户范围</el-button
        ><el-button v-if="can('system.integrations.manage')" @click="metaOpen = true"
          >Meta 连接</el-button
        ><el-button v-if="canImport" @click="importer?.open()">批量导入</el-button></el-form-item
      >
    </el-form>
    <el-alert v-if="ownersError" :title="ownersError" type="warning" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button v-if="error" @click="reload">重新查询</el-button>
    <el-alert v-if="preferenceError" :title="preferenceError" type="warning" :closable="false" />
    <p>
      日期只影响各账户当地业务日消耗；余额、账单和累计总花费独立展示。缺失覆盖显示未知，无消费账户仍保留。
    </p>
    <p v-if="dataAsOf">读取时间：{{ accountTime(dataAsOf) }}。左右滚动查看全部18列。</p>
    <el-table
      v-loading="loading"
      :data="rows"
      empty-text="暂无符合条件的可读账户"
      class="account-table"
    >
      <el-table-column
        v-for="column in shownColumns"
        :key="column.id"
        :label="column.label"
        :min-width="column.width"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <template v-if="column.id === 'name'"
            ><div>{{ row.account.name }}</div>
            <small>{{ row.account.external_id }}</small></template
          >
          <template v-else>{{ cell(row, column.id) }}</template>
        </template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="180"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="details?.open(row.account.id, windowQuery())"
            >详情</el-button
          >
          <el-button link type="primary" @click="channelDialog?.open(row.account)">渠道</el-button>
          <el-dropdown
            v-if="can('accounts.assign') || can('accounts.sync') || can('accounts.unbind')"
            trigger="click"
            @command="(kind: string) => openAction(row.account, kind)"
          >
            <el-button link type="primary">更多操作</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-if="can('accounts.assign')" command="ASSIGNMENT"
                  >分配投手</el-dropdown-item
                >
                <el-dropdown-item v-if="can('accounts.sync')" command="SYNC"
                  >只读同步</el-dropdown-item
                >
                <el-dropdown-item v-if="can('accounts.unbind')" command="UNBIND"
                  >本地解绑</el-dropdown-item
                >
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template></el-table-column
      >
    </el-table>
    <div class="account-pages">
      <el-select v-model="pageSize" aria-label="每页数量" style="width: 120px" @change="reload"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="`${size}条/页`" /></el-select
      ><el-button :disabled="loading || page === 0" @click="previous">上一页</el-button
      ><span>第{{ page + 1 }}页</span
      ><el-button :disabled="loading || !nextCursor" @click="next">下一页</el-button>
    </div>
    <p>
      同步与未来分配的受理回执不代表已执行；当前资料和归属以真实完成观察为准。备注编辑尚未接通。
    </p>
    <ImportAccounts ref="importer" @accepted="reload" />
    <el-dialog
      v-model="metaOpen"
      title="Meta 连接与账户接入"
      width="min(1200px, calc(100vw - 24px))"
      class="meta-connections-dialog"
    >
      <MetaConnectionsPanel
        :active="metaOpen"
        :context-key="JSON.stringify([user.id, user.permissions])"
        @accepted="metaAccepted"
      />
    </el-dialog>
    <AccountDetailsDrawer ref="details" />
    <AccountChannelDialog
      ref="channelDialog"
      :context-key="JSON.stringify([user.id, user.permissions])"
      @accepted="reload"
    />
    <AccountActionDialog ref="actionDialog" @accepted="reload" />
    <AccountAssignmentDialog ref="assignmentDialog" @accepted="reload" />
    <el-dialog
      v-model="columnsVisible"
      class="account-column-dialog"
      title="账户字段显示"
      width="min(600px, calc(100vw - 24px))"
    >
      <el-checkbox-group v-model="columnDraft" class="account-column-options"
        ><el-checkbox
          v-for="column in columns"
          :key="column.id"
          :value="column.id"
          :disabled="column.id === 'name'"
          >{{ column.label }}</el-checkbox
        ></el-checkbox-group
      >
      <p>账户名称/ID和操作始终显示。</p>
      <template #footer
        ><el-button @click="columnDraft = columns.map((x) => x.id)">恢复默认</el-button
        ><el-button @click="columnsVisible = false">取消</el-button
        ><el-button type="primary" @click="applyColumns">应用字段设置</el-button></template
      >
    </el-dialog>
    <el-dialog v-model="datesVisible" title="账户消耗时间" width="min(660px, calc(100vw - 24px))">
      <p>快捷范围由服务器按每个账户当地日期计算；自定义选择同名业务日。</p>
      <el-radio-group v-model="dateDraftMode" class="account-date-options"
        ><el-radio-button v-for="(label, key) in accountDateModes" :key="key" :value="key">{{
          label
        }}</el-radio-button></el-radio-group
      >
      <el-date-picker
        v-if="dateDraftMode === 'CUSTOM'"
        v-model="dateDraftRange"
        type="daterange"
        popper-class="account-date-range-panel"
        value-format="YYYY-MM-DD"
        start-placeholder="开始业务日"
        end-placeholder="结束业务日"
        aria-label="自定义消耗业务日范围"
        style="max-width: 100%; margin-top: 16px"
      />
      <el-alert v-if="dateError" :title="dateError" type="error" :closable="false" />
      <template #footer
        ><el-button @click="datesVisible = false">取消</el-button
        ><el-button type="primary" @click="applyDates">确认日期</el-button></template
      >
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { accountApi, type AccountOwnerOption } from '@/api/orbit/accounts'
import type { OrbitAccount } from '@/api/orbit/accounts'
import {
  accountDetailsApi,
  accountAmount,
  accountAuthorizations,
  accountDateModes,
  accountPeriod,
  accountSpendStatus,
  accountStates,
  accountText,
  accountTime,
  type ExtendedAccount,
} from '@/api/orbit/account-details'
import ImportAccounts from './ImportAccounts.vue'
import MetaConnectionsPanel from './components/MetaConnectionsPanel.vue'
import type { AccountImportBatch } from '@/api/orbit/accounts'
import AccountDetailsDrawer from './AccountDetailsDrawer.vue'
import AccountActionDialog from './AccountActionDialog.vue'
import AccountAssignmentDialog from './AccountAssignmentDialog.vue'
import AccountChannelDialog from './AccountChannelDialog.vue'
const metaOpen = ref(false)
const metaReturnNotice = ref('')
function metaAccepted(batch: AccountImportBatch) {
  metaOpen.value = false
  importer.value?.showResult(batch)
  void reload()
}
const router = useRouter()
const user = useUserStore()
// 若依当前权限仅控制入口展示；打开弹窗/提交时仍由Python当前动作和对象范围复验。
const can = (permission: string) =>
  user.permissions.includes('*:*:*') || user.permissions.includes(permission)
const actionDialog = ref<InstanceType<typeof AccountActionDialog>>()
const assignmentDialog = ref<InstanceType<typeof AccountAssignmentDialog>>()
const channelDialog = ref<InstanceType<typeof AccountChannelDialog>>()
function openAction(account: OrbitAccount, kind: string) {
  const permission = (
    { ASSIGNMENT: 'accounts.assign', SYNC: 'accounts.sync', UNBIND: 'accounts.unbind' } as Record<
      string,
      string
    >
  )[kind]
  if (!permission || !can(permission)) return
  if (kind === 'ASSIGNMENT') assignmentDialog.value?.open(account)
  else if (kind === 'SYNC' || kind === 'UNBIND') actionDialog.value?.open(account, kind)
}
const columns = [
  { id: 'owner', label: '投放师', width: 140 },
  { id: 'name', label: '账户名称 / ID', width: 230 },
  { id: 'vendor', label: '所属户商代称', width: 180 },
  { id: 'profile', label: '个号名称', width: 160 },
  { id: 'business', label: '所属主体', width: 180 },
  { id: 'state', label: '账户状态', width: 110 },
  { id: 'auth', label: '授权状态', width: 120 },
  { id: 'paymentType', label: '付费类型', width: 140 },
  { id: 'balance', label: '账户余额', width: 180 },
  { id: 'payable', label: '应付账单', width: 180 },
  { id: 'lifetime', label: '总花费', width: 180 },
  { id: 'paymentMethod', label: '付费方式', width: 160 },
  { id: 'spend', label: '消耗', width: 180 },
  { id: 'period', label: '消耗时间', width: 280 },
  { id: 'identities', label: 'BM / 主页 / 像素', width: 190 },
  { id: 'timezone', label: '账户时区', width: 260 },
  { id: 'blocked', label: '被封原因', width: 180 },
]
const importer = ref<InstanceType<typeof ImportAccounts>>(),
  details = ref<InstanceType<typeof AccountDetailsDrawer>>()
const rows = ref<ExtendedAccount[]>([]),
  loading = ref(false),
  error = ref(''),
  query = ref(''),
  status = ref(''),
  owner = ref(''),
  canImport = ref(false),
  dataAsOf = ref('')
const pageSize = ref(50),
  page = ref(0),
  nextCursor = ref<string | null>(null),
  cursors = ref<(string | null)[]>([null])
const owners = ref<AccountOwnerOption[]>([]),
  ownersLoading = ref(false),
  ownersError = ref(''),
  ownerCursor = ref<string | null>(null)
const mode = ref('TODAY'),
  range = ref<string[]>([]),
  datesVisible = ref(false),
  dateDraftMode = ref('TODAY'),
  dateDraftRange = ref<string[]>([]),
  dateError = ref('')
const columnsVisible = ref(false),
  visibleColumns = ref(columns.map((x) => x.id)),
  columnDraft = ref<string[]>([]),
  preferenceError = ref('')
let version = 0,
  ownerVersion = 0,
  ownerQuery = '',
  controller: AbortController | undefined,
  ownerController: AbortController | undefined,
  timer: ReturnType<typeof setTimeout> | undefined
const periodLabel = computed(() =>
  mode.value === 'CUSTOM' ? range.value.join(' 至 ') : accountDateModes[mode.value],
)
const shownColumns = computed(() => columns.filter((x) => visibleColumns.value.includes(x.id)))
function cell(row: ExtendedAccount, id: string) {
  const a = row.account,
    d = row.details
  switch (id) {
    case 'owner':
      return d.owner_display ?? a.ownership.owner_user_id
    case 'vendor':
      return a.vendor_alias ?? '尚未提供真实代称'
    case 'profile':
      return accountText(d.personal_profile)
    case 'business':
      return accountText(d.business_entity)
    case 'state':
      return accountStates[a.account_status]
    case 'auth':
      return accountAuthorizations[a.auth_status]
    case 'paymentType':
      return accountText(d.payment_type)
    case 'paymentMethod':
      return accountText(d.payment_method)
    case 'balance':
      return accountAmount(a.balance)
    case 'payable':
      return accountAmount(d.payable)
    case 'lifetime':
      return accountAmount(d.lifetime_spend)
    case 'spend':
      return a.spend.amount !== null || !d.spend_sync?.reason_code
        ? accountAmount(a.spend)
        : accountSpendStatus(d)
    case 'period':
      return accountPeriod(row)
    case 'identities':
      return `${d.business_managers === null ? 'BM未提供' : d.business_managers.map((x) => x.name || x.external_id).join('、') || '本次观测无BM'}；${d.identity_count === null ? '尚未同步身份资源（主页/像素/应用）' : `${d.identity_count}项已观测资源`}`
    case 'timezone':
      return a.timezone.display_label
    case 'blocked':
      return accountText(d.blocked_reason)
    default:
      return '未提供'
  }
}
function windowQuery() {
  const q = new URLSearchParams({ mode: mode.value })
  if (mode.value === 'CUSTOM') {
    q.set('date_from', range.value[0])
    q.set('date_to', range.value[1])
  }
  return q
}
async function read() {
  controller?.abort()
  controller = new AbortController()
  const current = ++version
  loading.value = true
  error.value = ''
  try {
    const q = windowQuery()
    q.set('q', query.value)
    q.set('page_size', String(pageSize.value))
    if (status.value) q.set('status', status.value)
    if (owner.value) q.set('operator_user_id', owner.value)
    if (cursors.value[page.value]) q.set('cursor', cursors.value[page.value]!)
    const result = await accountDetailsApi.list(q, controller.signal)
    if (current !== version) return
    rows.value = result.items
    nextCursor.value = result.next_cursor
    dataAsOf.value = result.data_as_of
  } catch (cause) {
    if (current === version) {
      rows.value = []
      nextCursor.value = null
      dataAsOf.value = ''
      error.value = cause instanceof Error ? cause.message : '账户读取失败'
    }
  } finally {
    if (current === version) loading.value = false
  }
}
async function reload() {
  clearTimeout(timer)
  page.value = 0
  cursors.value = [null]
  await read()
}
async function reset() {
  query.value = ''
  status.value = ''
  owner.value = ''
  mode.value = 'TODAY'
  range.value = []
  await reload()
}
async function next() {
  if (!nextCursor.value || loading.value) return
  cursors.value[page.value + 1] = nextCursor.value
  page.value++
  await read()
}
async function previous() {
  if (!page.value || loading.value) return
  page.value--
  await read()
}
function openDates() {
  dateDraftMode.value = mode.value
  dateDraftRange.value = [...range.value]
  dateError.value = ''
  datesVisible.value = true
}
function applyDates() {
  if (
    dateDraftMode.value === 'CUSTOM' &&
    (dateDraftRange.value?.length !== 2 || dateDraftRange.value[0] > dateDraftRange.value[1])
  ) {
    dateError.value = '请选择按顺序排列的开始和结束业务日'
    return
  }
  mode.value = dateDraftMode.value
  range.value = dateDraftMode.value === 'CUSTOM' ? [...dateDraftRange.value] : []
  datesVisible.value = false
  void reload()
}
function openColumns() {
  columnDraft.value = [...visibleColumns.value]
  columnsVisible.value = true
}
function applyColumns() {
  visibleColumns.value = columns
    .filter((x) => x.id === 'name' || columnDraft.value.includes(x.id))
    .map((x) => x.id)
  preferenceError.value = ''
  try {
    localStorage.setItem('orbit-account-columns-v1', JSON.stringify(visibleColumns.value))
  } catch {
    preferenceError.value = '列设置仅在当前页面生效，浏览器未能保存'
  }
  columnsVisible.value = false
}
async function readOwners(append = false) {
  ownerController?.abort()
  ownerController = new AbortController()
  const current = ++ownerVersion
  ownersLoading.value = true
  ownersError.value = ''
  try {
    const q = new URLSearchParams({ q: ownerQuery })
    if (append && ownerCursor.value) q.set('cursor', ownerCursor.value)
    const result = await accountDetailsApi.owners(q, ownerController.signal)
    if (current !== ownerVersion) return
    owners.value = append ? [...owners.value, ...result.items] : result.items
    ownerCursor.value = result.next_cursor
  } catch (cause) {
    if (current === ownerVersion) {
      if (!append) owners.value = []
      ownerCursor.value = null
      ownersError.value =
        cause instanceof Error ? `投手选项读取失败：${cause.message}` : '投手选项读取失败'
    }
  } finally {
    if (current === ownerVersion) ownersLoading.value = false
  }
}
function searchOwners(value: string) {
  ownerQuery = value
  void readOwners()
}
function moreOwners() {
  void readOwners(true)
}
watch(
  query,
  () => {
    clearTimeout(timer)
    timer = setTimeout(() => void reload(), 300)
  },
  { flush: 'sync' },
)
onMounted(() => {
  const returned = router.currentRoute?.value?.query?.meta_result
  if (returned === 'connected' || returned === 'cancelled') {
    metaReturnNotice.value =
      returned === 'cancelled'
        ? '本次 Meta 授权已取消；可在 Meta 连接中查看现有状态。'
        : '已从 Meta 返回；请查看连接列表确认当前状态。'
    if (can('system.integrations.manage')) metaOpen.value = true
  }
  try {
    const saved = JSON.parse(localStorage.getItem('orbit-account-columns-v1') || 'null')
    if (Array.isArray(saved) && saved.every((x) => typeof x === 'string'))
      visibleColumns.value = columns
        .filter((x) => x.id === 'name' || saved.includes(x.id))
        .map((x) => x.id)
  } catch {
    preferenceError.value = '无法恢复已保存列设置，已使用默认字段'
  }
  void read()
  void readOwners()
  void accountApi
    .capabilities()
    .then(() => (canImport.value = true))
    .catch(() => (canImport.value = false))
})
onBeforeUnmount(() => {
  version++
  ownerVersion++
  controller?.abort()
  ownerController?.abort()
  clearTimeout(timer)
})
</script>
<style scoped>
.account-page {
  min-width: 0;
  max-width: 100%;
}
.account-table {
  width: 100%;
}
.account-pages {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 16px;
}
.account-column-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.account-date-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
:deep(.el-alert) {
  margin: 12px 0;
}
:deep(.el-form--inline .el-form-item) {
  max-width: 100%;
}
:deep(.el-table .cell) {
  font-variant-numeric: tabular-nums;
}
small {
  display: block;
}
:global(.account-column-dialog) {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 24px);
  margin: 12px auto;
}
:global(.account-column-dialog .el-dialog__body) {
  overflow-y: auto;
}
:global(.account-date-range-panel) {
  max-width: calc(100vw - 24px);
  overflow-x: auto;
}
:global(.account-date-range-panel .el-picker-panel__body) {
  min-width: 640px;
}
@media (max-width: 600px) {
  .account-column-options {
    grid-template-columns: 1fr;
  }
  :deep(.el-form-item) {
    margin-right: 12px;
  }
  .account-pages {
    gap: 8px;
  }
}
</style>
