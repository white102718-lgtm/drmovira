<template>
  <el-dialog
    v-model="visible"
    :title="action === 'SYNC' ? '只读同步账户' : '本地解绑账户'"
    class="account-action-dialog"
    width="min(620px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="closed"
  >
    <p>账户：{{ account?.name }}（{{ account?.external_id }}）</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert
      :title="
        action === 'SYNC'
          ? '提交后仅受理只读同步任务；执行成功前，原资料和未知金额保持原状。'
          : '只解除本系统关联并结束当前归属区间，平台广告、凭据和历史事实保留。'
      "
      type="info"
      :closable="false"
    />
    <el-form v-if="!ack" label-position="top" :disabled="loading || saving || uncertain">
      <el-form-item label="操作原因" required :error="reason ? reasonError : ''">
        <el-input
          v-model="reason"
          type="textarea"
          :rows="4"
          maxlength="2000"
          placeholder="请填写1至1000字的明确原因"
          aria-label="账户操作原因"
        />
        <span>{{ [...reason.normalize('NFC').trim()].length }} / 1000 字</span>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="uncertain"
      title="原请求结果尚未确认。内容已锁定；关闭后再次打开同一账户动作仍保留原幂等键，请重试确认。"
      type="warning"
      :closable="false"
    />
    <div v-if="ack" role="status">
      <p>
        {{
          action === 'SYNC'
            ? '只读同步已受理，尚未确认执行结果。请刷新账户查看真实观测。'
            : '本地解绑已完成，平台广告及历史事实保留。'
        }}
      </p>
      <p>账户版本：{{ ack.revision }}</p>
      <p>请求编号：{{ ack.request_id }}</p>
      <AccountCommandStatus :account-id="ack.id" :kind="action" :request-id="ack.request_id" />
    </div>
    <template #footer>
      <el-button :disabled="saving" @click="visible = false">关闭</el-button>
      <el-button
        v-if="(loadingError || error) && !uncertain"
        :disabled="loading"
        @click="loadCapability"
      >
        重新读取动作权限
      </el-button>
      <el-button
        v-if="!ack"
        :type="action === 'UNBIND' ? 'danger' : 'primary'"
        :loading="saving"
        :disabled="loading || (!uncertain && (!capability || !validReason))"
        @click="submit"
        >{{
          uncertain ? '重试原请求' : action === 'SYNC' ? '确认受理只读同步' : '确认本地解绑'
        }}</el-button
      >
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { OrbitAccount } from '@/api/orbit/accounts'
import {
  accountActionsApi,
  type AccountActionAck,
  type AccountActionCapability,
  type AccountReasonIntent,
} from '@/api/orbit/account-actions'
import { ReferenceApiError } from '@/api/orbit/references'
import AccountCommandStatus from './AccountCommandStatus.vue'

const emit = defineEmits<{ accepted: [ack: AccountActionAck] }>()
const visible = ref(false)
const account = ref<Pick<OrbitAccount, 'id' | 'name' | 'external_id'> | null>(null)
const action = ref<'SYNC' | 'UNBIND'>('SYNC')
const reason = ref('')
const error = ref('')
const loading = ref(false)
const loadingError = ref(false)
const saving = ref(false)
const uncertain = ref(false)
const capability = ref<AccountActionCapability | null>(null)
const ack = ref<AccountActionAck | null>(null)
// 仅内存保留未确认请求；不持久化Token、原因、账户资料或会话信息。
const pending = new Map<string, AccountReasonIntent>()
let generation = 0
let controller: AbortController | null = null
const pendingId = () => `${account.value?.id}:${action.value}`
const reasonError = computed(() => {
  if (/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(reason.value))
    return '原因不能包含换行、控制字符或隐藏格式字符'
  const value = reason.value.normalize('NFC').trim()
  return !value ? '请填写操作原因' : [...value].length > 1000 ? '原因最多1000字' : ''
})
const validReason = computed(() => !reasonError.value)

async function loadCapability() {
  if (!account.value || saving.value || uncertain.value) return
  const token = ++generation
  controller?.abort()
  controller = new AbortController()
  capability.value = null
  loading.value = true
  loadingError.value = false
  error.value = ''
  try {
    const value = await accountActionsApi.capabilities(
      account.value.id,
      action.value,
      controller.signal,
    )
    if (token === generation && visible.value) capability.value = value
  } catch (failure) {
    if (token === generation && visible.value) {
      error.value = failure instanceof Error ? failure.message : '动作权限读取失败'
      loadingError.value = true
    }
  } finally {
    if (token === generation) loading.value = false
  }
}

function open(value: Pick<OrbitAccount, 'id' | 'name' | 'external_id'>, kind: 'SYNC' | 'UNBIND') {
  if (saving.value) return
  ++generation
  controller?.abort()
  account.value = { ...value }
  action.value = kind
  error.value = ''
  ack.value = null
  capability.value = null
  loading.value = false
  loadingError.value = false
  visible.value = true
  const prior = pending.get(pendingId())
  uncertain.value = !!prior
  reason.value = prior?.reason ?? ''
  if (prior) capability.value = prior.capability
  else void loadCapability()
}

async function submit() {
  if (saving.value || loading.value || !account.value || !capability.value || ack.value) return
  if (!uncertain.value && !validReason.value) return
  const id = pendingId()
  const intent = pending.get(id) ?? {
    accountId: account.value.id,
    action: action.value,
    capability: { ...capability.value },
    key: crypto.randomUUID(),
    reason: reason.value.normalize('NFC').trim(),
  }
  pending.set(id, intent)
  const wasUncertain = uncertain.value
  saving.value = true
  error.value = ''
  try {
    const value = await accountActionsApi.reason(intent)
    pending.delete(id)
    uncertain.value = false
    ack.value = value
    emit('accepted', value)
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '动作提交失败'
    const ambiguous =
      !(failure instanceof ReferenceApiError) || failure.status === 0 || failure.status >= 500
    uncertain.value = wasUncertain || ambiguous
    if (!uncertain.value) pending.delete(id)
  } finally {
    saving.value = false
  }
}

function closed() {
  ++generation
  controller?.abort()
  loading.value = false
}
onBeforeUnmount(closed)
defineExpose({ open })
</script>

<style>
.account-action-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 32px);
  margin-top: 16px;
}
.account-action-dialog .el-dialog__body {
  overflow: auto;
}
.account-action-dialog .el-dialog__footer {
  flex-shrink: 0;
}
.account-action-dialog .el-alert {
  margin-bottom: 12px;
}
.account-action-dialog p {
  overflow-wrap: anywhere;
}
</style>
