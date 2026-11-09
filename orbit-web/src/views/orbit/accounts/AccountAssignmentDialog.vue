<template>
  <el-dialog
    v-model="visible"
    title="分配广告账户"
    class="account-assignment-dialog"
    width="min(680px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="closed"
  >
    <p>账户：{{ account?.name }}（{{ account?.external_id }}）</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert
      title="转移在账户当地下一业务日零点生效，边界前当前归属保留；历史事实按冻结归属保留。"
      type="info"
      :closable="false"
    />
    <el-form v-if="!ack" label-position="top" :disabled="loading || saving || uncertain">
      <el-form-item label="目标投手" required>
        <el-select
          v-model="ownerId"
          filterable
          remote
          clearable
          placeholder="选择本人或明确可管理的启用投手"
          :remote-method="searchOwners"
          :loading="ownersLoading"
          @change="ownerChanged"
        >
          <el-option
            v-for="person in ownerRows"
            :key="person.id"
            :value="person.id"
            :label="`${person.name}（${person.team_name}）`"
          />
        </el-select>
        <el-button v-if="ownerCursor" link :disabled="ownersLoading" @click="loadOwners(true)"
          >加载更多投手</el-button
        >
      </el-form-item>
      <p v-if="selectedOwner">目标团队：{{ selectedOwner.team_name }}</p>
      <el-alert v-if="ownersError" :title="ownersError" type="error" :closable="false" />
      <el-button v-if="ownersError" link @click="loadOwners(false)">重新读取投手候选</el-button>
      <el-form-item label="目标户商" required>
        <el-select
          v-model="vendorChoice"
          :disabled="!selectedOwner"
          filterable
          remote
          :remote-method="searchVendors"
          :loading="vendorsLoading"
          placeholder="请选择户商或明确不关联户商"
        >
          <el-option label="不关联户商" value="" />
          <el-option
            v-for="vendor in vendorRows"
            :key="vendor.id"
            :value="vendor.id"
            :label="
              vendor.alias ? `${vendor.alias}（${vendor.name}）` : `${vendor.name}（未设代称）`
            "
          />
        </el-select>
        <el-button v-if="vendorCursor" link :disabled="vendorsLoading" @click="loadVendors(true)"
          >加载更多户商</el-button
        >
      </el-form-item>
      <el-alert v-if="vendorsError" :title="vendorsError" type="error" :closable="false" />
      <el-button v-if="vendorsError" link @click="loadVendors(false)">重新读取户商候选</el-button>
      <p v-if="selectedOwner && !vendorsLoading && !vendorsError && !vendorRows.length">
        没有可用户商交集，可明确选择“不关联户商”。
      </p>
      <p>生效时间：{{ effectiveLabel }}</p>
      <p>时刻由服务端按账户时区 {{ account?.timezone.id }} 计算，不使用浏览器时区推算。</p>
      <el-form-item label="分配原因" required :error="reason ? reasonError : ''">
        <el-input
          v-model="reason"
          type="textarea"
          :rows="3"
          maxlength="2000"
          placeholder="请填写1至1000字，不包含换行或隐藏控制字符"
          aria-label="账户分配原因"
        />
        <span>{{ [...reason.normalize('NFC').trim()].length }} / 1000 字</span>
      </el-form-item>
      <p v-if="selectedOwner && vendorChoice !== undefined && !hasChange">
        目标投手、团队和户商均未变化。
      </p>
    </el-form>
    <el-alert
      v-if="uncertain"
      title="原分配请求结果尚未确认。原投手、户商、时刻、原因和幂等键已锁定；请重试原请求。"
      type="warning"
      :closable="false"
    />
    <div v-if="ack" role="status">
      <p>未来分配已受理；当前归属尚未因此提前转移，实际激活仍需重新核验。</p>
      <p>生效时间：{{ effectiveLabel }}</p>
      <p>账户版本：{{ ack.revision }}</p>
      <p>请求编号：{{ ack.request_id }}</p>
      <AccountCommandStatus :account-id="ack.id" kind="ASSIGNMENT" :request-id="ack.request_id" />
    </div>
    <template #footer>
      <el-button :disabled="saving" @click="visible = false">关闭</el-button>
      <el-button v-if="error && !uncertain" :disabled="saving || loading" @click="loadCapability"
        >重新读取动作权限与时刻</el-button
      >
      <el-button
        v-if="!ack"
        type="primary"
        :loading="saving"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ uncertain ? '重试原分配' : '确认未来分配' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { OrbitAccount } from '@/api/orbit/accounts'
import {
  accountActionsApi,
  type AccountActionCapability,
  type AccountActionAck,
} from '@/api/orbit/account-actions'
import {
  accountAssignmentApi,
  type AssignmentIntent,
  type AssignmentOwner,
  type AssignmentVendor,
} from '@/api/orbit/account-assignment'
import { ReferenceApiError } from '@/api/orbit/references'
import AccountCommandStatus from './AccountCommandStatus.vue'

const emit = defineEmits<{ accepted: [ack: AccountActionAck] }>()
const visible = ref(false),
  account = ref<OrbitAccount | null>(null),
  error = ref('')
const loading = ref(false),
  saving = ref(false),
  uncertain = ref(false)
const capability = ref<AccountActionCapability | null>(null),
  ack = ref<AccountActionAck | null>(null)
const ownerId = ref(''),
  ownerRows = ref<AssignmentOwner[]>([]),
  selectedOwner = ref<AssignmentOwner | null>(null)
const ownerCursor = ref<string | null>(null),
  ownerQuery = ref(''),
  ownersLoading = ref(false),
  ownersError = ref('')
// undefined表示尚未选择，''明确选择不关联→业务null；不把内部哨兵显示给使用者。
const vendorChoice = ref<string | undefined>(undefined),
  vendorRows = ref<AssignmentVendor[]>([])
const vendorCursor = ref<string | null>(null),
  vendorQuery = ref(''),
  vendorsLoading = ref(false),
  vendorsError = ref('')
const reason = ref('')
type SavedIntent = { intent: AssignmentIntent; owner: AssignmentOwner; vendors: AssignmentVendor[] }
const pending = new Map<string, SavedIntent>()
let generation = 0,
  ownerGeneration = 0,
  vendorGeneration = 0
let controller: AbortController | null = null
let ownerController: AbortController | null = null
let vendorController: AbortController | null = null
const reasonError = computed(() => {
  if (/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(reason.value))
    return '原因不能包含换行或隐藏控制字符'
  const value = reason.value.normalize('NFC').trim()
  return !value ? '请填写分配原因' : [...value].length > 1000 ? '原因最多1000字' : ''
})
const hasChange = computed(
  () =>
    !!account.value &&
    !!selectedOwner.value &&
    (selectedOwner.value.id !== account.value.ownership.owner_user_id ||
      selectedOwner.value.team_id !== account.value.ownership.owner_team_id ||
      (vendorChoice.value || null) !== account.value.vendor_id),
)
const effectiveLabel = computed(() => {
  if (!capability.value?.next_effective_from || !account.value) return '尚未取得可信生效时刻'
  try {
    return (
      new Intl.DateTimeFormat('zh-CN', {
        timeZone: account.value.timezone.id,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      }).format(new Date(capability.value.next_effective_from)) + `（${account.value.timezone.id}）`
    )
  } catch {
    return '生效时刻或账户时区无效'
  }
})
const canSubmit = computed(
  () =>
    !saving.value &&
    !loading.value &&
    !ack.value &&
    (uncertain.value ||
      (!!capability.value?.next_effective_from &&
        !!selectedOwner.value &&
        vendorChoice.value !== undefined &&
        !reasonError.value &&
        hasChange.value &&
        !ownersLoading.value &&
        !vendorsLoading.value &&
        !ownersError.value &&
        !vendorsError.value)),
)

/** 候选续页可与保留的当前选择重合，只按服务端业务UUID合并显示，不改用户原始导入数据。 */
function uniqueRows<T extends { id: string }>(rows: T[]) {
  return [...new Map(rows.map((row) => [row.id, row])).values()]
}

async function loadCapability() {
  if (!account.value || saving.value || uncertain.value) return
  const token = ++generation
  controller?.abort()
  controller = new AbortController()
  capability.value = null
  loading.value = true
  error.value = ''
  try {
    const value = await accountActionsApi.capabilities(
      account.value.id,
      'ASSIGNMENT',
      controller.signal,
    )
    if (!value.next_effective_from || !Number.isFinite(Date.parse(value.next_effective_from)))
      throw new ReferenceApiError(502, 'INVALID_RESPONSE', '服务端未提供可信生效时刻')
    if (token === generation && visible.value) capability.value = value
  } catch (failure) {
    if (token === generation && visible.value)
      error.value = failure instanceof Error ? failure.message : '分配权限读取失败'
  } finally {
    if (token === generation) loading.value = false
  }
}

async function loadOwners(more: boolean) {
  if (!account.value || uncertain.value || saving.value || (more && !ownerCursor.value)) return
  const token = ++ownerGeneration,
    dialogToken = generation
  ownerController?.abort()
  ownerController = new AbortController()
  ownersLoading.value = true
  ownersError.value = ''
  if (!more) ownerCursor.value = null
  const query = new URLSearchParams({ q: ownerQuery.value, page_size: '50' })
  if (more && ownerCursor.value) query.set('cursor', ownerCursor.value)
  try {
    const page = await accountAssignmentApi.owners(account.value.id, query, ownerController.signal)
    if (token !== ownerGeneration || dialogToken !== generation || !visible.value) return
    ownerRows.value = uniqueRows(more ? [...ownerRows.value, ...page.items] : page.items)
    if (selectedOwner.value && !ownerRows.value.some((row) => row.id === selectedOwner.value?.id))
      ownerRows.value.unshift(selectedOwner.value)
    ownerCursor.value = page.next_cursor
  } catch (failure) {
    if (token === ownerGeneration && dialogToken === generation)
      ownersError.value = failure instanceof Error ? failure.message : '投手候选读取失败'
  } finally {
    if (token === ownerGeneration) ownersLoading.value = false
  }
}
function searchOwners(value: string) {
  ownerQuery.value = value
  void loadOwners(false)
}

async function loadVendors(more: boolean) {
  if (
    !account.value ||
    !selectedOwner.value ||
    uncertain.value ||
    saving.value ||
    (more && !vendorCursor.value)
  )
    return
  const owner = selectedOwner.value.id,
    token = ++vendorGeneration,
    dialogToken = generation
  vendorController?.abort()
  vendorController = new AbortController()
  vendorsLoading.value = true
  vendorsError.value = ''
  if (!more) vendorCursor.value = null
  const query = new URLSearchParams({ q: vendorQuery.value, page_size: '50' })
  if (more && vendorCursor.value) query.set('cursor', vendorCursor.value)
  try {
    const page = await accountAssignmentApi.vendors(
      account.value.id,
      owner,
      query,
      vendorController.signal,
    )
    if (
      token !== vendorGeneration ||
      dialogToken !== generation ||
      owner !== selectedOwner.value?.id ||
      !visible.value
    )
      return
    vendorRows.value = uniqueRows(more ? [...vendorRows.value, ...page.items] : page.items)
    vendorCursor.value = page.next_cursor
  } catch (failure) {
    if (token === vendorGeneration && dialogToken === generation)
      vendorsError.value = failure instanceof Error ? failure.message : '户商候选读取失败'
  } finally {
    if (token === vendorGeneration) vendorsLoading.value = false
  }
}
function searchVendors(value: string) {
  vendorQuery.value = value
  void loadVendors(false)
}
function ownerChanged(value: string) {
  ++vendorGeneration
  vendorController?.abort()
  selectedOwner.value = ownerRows.value.find((row) => row.id === value) ?? null
  vendorChoice.value = undefined
  vendorRows.value = []
  vendorCursor.value = null
  vendorsLoading.value = false
  vendorsError.value = ''
  vendorQuery.value = ''
  if (selectedOwner.value) void loadVendors(false)
}

function open(value: OrbitAccount) {
  if (saving.value) return
  closed()
  account.value = value
  visible.value = true
  error.value = ''
  ack.value = null
  capability.value = null
  ownerRows.value = []
  ownerId.value = ''
  selectedOwner.value = null
  vendorRows.value = []
  vendorChoice.value = undefined
  ownerCursor.value = vendorCursor.value = null
  ownersError.value = vendorsError.value = ''
  ownerQuery.value = vendorQuery.value = ''
  reason.value = ''
  const saved = pending.get(value.id)
  uncertain.value = !!saved
  if (saved) {
    capability.value = saved.intent.capability
    selectedOwner.value = saved.owner
    ownerRows.value = [saved.owner]
    ownerId.value = saved.owner.id
    vendorChoice.value = saved.intent.body.vendor_id ?? ''
    vendorRows.value = saved.vendors
    reason.value = saved.intent.body.reason
  } else {
    // 能力和候选独立并发，generation必须在loadCapability创建后取，防迟到串账户。
    void loadCapability()
    void loadOwners(false)
  }
}

async function submit() {
  if (!canSubmit.value || !account.value || !capability.value || !selectedOwner.value) return
  const id = account.value.id
  const saved = pending.get(id) ?? {
    owner: { ...selectedOwner.value },
    vendors: [...vendorRows.value],
    intent: {
      accountId: id,
      key: crypto.randomUUID(),
      capability: { ...capability.value },
      body: {
        operator_user_id: selectedOwner.value.id,
        owner_team_id: selectedOwner.value.team_id,
        vendor_id: vendorChoice.value || null,
        effective_from: capability.value.next_effective_from!,
        reason: reason.value.normalize('NFC').trim(),
      },
    },
  }
  pending.set(id, saved)
  const wasUncertain = uncertain.value
  saving.value = true
  error.value = ''
  try {
    const value = await accountAssignmentApi.assign(saved.intent)
    pending.delete(id)
    uncertain.value = false
    ack.value = value
    emit('accepted', value)
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '分配提交失败'
    uncertain.value =
      wasUncertain ||
      !(failure instanceof ReferenceApiError) ||
      failure.status === 0 ||
      failure.status >= 500
    if (!uncertain.value) pending.delete(id)
  } finally {
    saving.value = false
  }
}
function closed() {
  ++generation
  ++ownerGeneration
  ++vendorGeneration
  controller?.abort()
  ownerController?.abort()
  vendorController?.abort()
  loading.value = ownersLoading.value = vendorsLoading.value = false
}
onBeforeUnmount(closed)
defineExpose({ open })
</script>

<style>
.account-assignment-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 32px);
  margin-top: 16px;
}
.account-assignment-dialog .el-dialog__body {
  overflow: auto;
}
.account-assignment-dialog .el-dialog__footer {
  flex-shrink: 0;
}
.account-assignment-dialog .el-alert {
  margin-bottom: 12px;
}
.account-assignment-dialog p {
  overflow-wrap: anywhere;
}
</style>
