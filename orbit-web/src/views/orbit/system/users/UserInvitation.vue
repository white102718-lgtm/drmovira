<template>
  <el-dialog
    v-model="visible"
    title="人员邀请"
    width="min(580px, calc(100vw - 24px))"
    class="user-invitation-dialog"
    :close-on-click-modal="!saving"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="invalidate"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert
      v-if="queued"
      title="邀请已排队，尚未确认通知渠道接收"
      type="success"
      :closable="false"
      show-icon
    />
    <el-skeleton v-if="loading" :rows="5" animated />
    <template v-else-if="person && status">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="姓名">{{ person.display_name }}</el-descriptions-item>
        <el-descriptions-item label="邀请邮箱">{{ person.email }}</el-descriptions-item>
        <el-descriptions-item label="邀请状态">{{
          status.invitation ? states[status.invitation.state] : '尚未创建邀请'
        }}</el-descriptions-item>
        <el-descriptions-item label="通知状态">{{ deliveryLabel }}</el-descriptions-item>
        <el-descriptions-item v-if="status.invitation" label="有效期至">{{
          dateLabel(status.invitation.expires_at)
        }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="status.blocked_reason"
        :title="status.blocked_reason"
        type="warning"
        :closable="false"
        show-icon
      />
      <p>邀请有效期为24小时。重新发送将撤销旧邀请；接收人需使用已验证的邀请邮箱登录。</p>
      <p>通知渠道接受请求后仍需确认实际送达；结果未知时，请先核对通知渠道再决定是否重发。</p>
    </template>
    <template #footer>
      <el-button :disabled="saving" @click="visible = false">关闭</el-button>
      <el-button :disabled="loading || saving" @click="refresh">刷新状态</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="loading || (!retry && !status?.can_invite) || !person"
        @click="send"
      >
        {{ retry ? '重试本次邀请' : status?.invitation ? '重新发送邀请' : '发送邀请' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { userApi, UserRequestError, type InvitationStatus, type OrbitUser } from '@/api/orbit/users'

const emit = defineEmits<{ changed: [] }>()
const visible = ref(false),
  loading = ref(false),
  saving = ref(false),
  error = ref(''),
  queued = ref(false)
const person = ref<OrbitUser | null>(null),
  status = ref<InvitationStatus | null>(null)
const states = { ACTIVE: '等待验证', CONSUMED: '已完成验证', REVOKED: '已撤销', EXPIRED: '已过期' }
const deliveries = {
  QUEUED: '等待处理',
  SENDING: '发送中',
  ACCEPTED: '通知渠道已接受',
  FAILED: '发送失败',
  UNKNOWN: '发送结果未知',
}
const deliveryLabel = computed(() => {
  const state = status.value?.invitation?.delivery_state
  return state ? deliveries[state] : '暂无通知记录'
})
let userId = '',
  csrf = '',
  generation = 0
/** 响应丢失时保留相同版本及幂等键；刷新、关闭或切换人员不能静默制造新写意图。 */
const retry = ref<{ key: string; revision: number } | null>(null)
const pending = new Map<string, { key: string; revision: number }>()
function invalidate() {
  generation++
  person.value = null
  status.value = null
  retry.value = null
  csrf = ''
}
function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? '时间未知' : `${date.toLocaleString('zh-CN')}（本地时间）`
}
async function read() {
  const current = ++generation,
    id = userId
  loading.value = true
  error.value = ''
  // 清空旧能力，读取失败不能继续用上一次的权限或人员版本提交。
  person.value = null
  status.value = null
  try {
    const [user, result, capabilities] = await Promise.all([
      userApi.get(id),
      userApi.invitationStatus(id),
      userApi.capabilities(),
    ])
    if (current !== generation) return
    person.value = user
    status.value = result
    csrf = capabilities.csrf_token
  } catch (cause) {
    if (current === generation)
      error.value = cause instanceof Error ? cause.message : '邀请信息读取失败，请刷新状态'
  } finally {
    if (current === generation) loading.value = false
  }
}
async function open(user: OrbitUser) {
  if (saving.value) return
  invalidate()
  userId = user.id
  retry.value = pending.get(user.id) ?? null
  queued.value = false
  visible.value = true
  await read()
}
async function refresh() {
  if (retry.value) {
    error.value = '本次邀请结果尚未确认；请先重试本次邀请，避免生成重复通知'
    return
  }
  await read()
}
async function send() {
  if (saving.value || loading.value || !person.value || (!retry.value && !status.value?.can_invite))
    return
  const current = generation
  if (!retry.value && status.value?.invitation) {
    try {
      await ElMessageBox.confirm(
        '重新发送会撤销旧邀请。确认向当前邮箱创建新的邀请？',
        '重新发送邀请',
        { type: 'warning', confirmButtonText: '确认重发', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  if (current !== generation || !visible.value) return
  retry.value ??= { key: `invitation-${crypto.randomUUID()}`, revision: person.value.revision }
  pending.set(userId, retry.value)
  saving.value = true
  error.value = ''
  queued.value = false
  try {
    await userApi.invite(userId, retry.value.revision, csrf, retry.value.key)
    pending.delete(userId)
    retry.value = null
    queued.value = true
    emit('changed')
    await read()
  } catch (cause) {
    // 明确拒绝没有未知提交结果；允许刷新人员版本或权限后重新发起。
    if (cause instanceof UserRequestError && [400, 403, 404, 409, 422].includes(cause.status)) {
      pending.delete(userId)
      retry.value = null
    }
    error.value = cause instanceof Error ? cause.message : '邀请未确认，请重试本次邀请'
  } finally {
    saving.value = false
  }
}
defineExpose({ open })
</script>

<style>
.user-invitation-dialog {
  max-height: calc(100dvh - 24px);
  display: flex;
  flex-direction: column;
}
.el-dialog.user-invitation-dialog:not(.is-fullscreen) {
  /* 对长弹窗预留固定边距，内容在内部滚动，页脚始终留在视口内。 */
  margin-top: 12px !important;
  margin-bottom: 12px;
}
.user-invitation-dialog .el-dialog__header,
.user-invitation-dialog .el-dialog__footer {
  flex-shrink: 0;
}
.user-invitation-dialog .el-dialog__body {
  min-height: 0;
  overflow-y: auto;
  overflow-wrap: anywhere;
}
.user-invitation-dialog .el-alert {
  margin-bottom: 12px;
}
.user-invitation-dialog .el-dialog__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.user-invitation-dialog .el-dialog__footer .el-button {
  margin-left: 0;
}
</style>
