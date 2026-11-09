<template>
  <section class="agent-probe" aria-label="主动只读探测">
    <div class="probe-toolbar">
      <strong>主动只读探测</strong>
      <el-button
        v-if="canProbe"
        type="primary"
        :disabled="!active || busy || pending || revoked"
        @click="confirming = true"
        >主动只读探测</el-button
      >
      <span v-else class="muted">仅具有探测权限的超级管理员可以发起。</span>
    </div>
    <p class="muted">
      请求设备重新检查本地 API、Profile
      和允许观察的现有页面。不打开浏览器窗口，不执行广告写入；完成不代表登录有效、账户匹配或获得操作能力。
    </p>
    <el-alert v-if="error" :title="error" type="warning" :closable="false" />
    <div v-if="confirming" class="probe-confirm">
      <p>确认让此设备执行一次新的只读检查？设备离线或未及时回报时，请求将在两分钟后过期。</p>
      <el-button :disabled="busy" @click="confirming = false">取消探测</el-button>
      <el-button
        type="primary"
        :loading="busy"
        :disabled="!active || !canProbe || revoked"
        @click="send(false)"
        >确认开始探测</el-button
      >
    </div>
    <el-alert
      v-if="session.intent && !session.requestId"
      title="探测请求结果尚未确认。原请求标识与版本仅保留在本页内存中，关闭详情后仍可恢复；刷新或离开页面会丢失恢复信息。请勿重新创建请求。"
      type="warning"
      :closable="false"
    />
    <el-button
      v-if="session.intent && !session.requestId && canProbe"
      :loading="busy"
      :disabled="!active"
      @click="send(true)"
      >重试原探测请求</el-button
    >
    <el-descriptions v-if="session.requestId" :column="1" border size="small">
      <el-descriptions-item label="探测请求">{{ session.requestId }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{
        session.result ? labels[session.result.state] : '已受理，尚未读取检查结果'
      }}</el-descriptions-item>
      <el-descriptions-item v-if="session.result" label="受理时间">{{
        session.result.created_at
      }}</el-descriptions-item>
      <el-descriptions-item v-if="session.result" label="过期时间">{{
        session.result.expires_at
      }}</el-descriptions-item>
      <el-descriptions-item v-if="session.result?.completed_at" label="完成时间">{{
        session.result.completed_at
      }}</el-descriptions-item>
      <el-descriptions-item v-if="session.result?.error_code" label="原因">{{
        session.result.error_code
      }}</el-descriptions-item>
    </el-descriptions>
    <el-button
      v-if="readFailed && session.requestId"
      :disabled="!active || reading"
      @click="readResult"
      >重新读取探测结果</el-button
    >
    <p v-if="session.result?.state === 'QUEUED'" class="muted">
      等待设备执行并提交新观察；此处只查询结果，不会重复发起探测。关闭详情停止查询，设备端请求仍保留。
    </p>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AgentApiError, environmentApi } from '@/api/orbit/environments'
import { probeApi, type ProbeSession } from '@/api/orbit/environments-probe'
const props = withDefaults(
  defineProps<{
    agentId: string
    revision: number
    actorId: number
    tenantId: string
    canProbe: boolean
    active: boolean
    revoked?: boolean
    session: ProbeSession
  }>(),
  { revoked: false },
)
const emit = defineEmits<{ completed: []; busy: [value: boolean] }>()
const confirming = ref(false),
  busy = ref(false),
  reading = ref(false),
  readFailed = ref(false),
  error = ref('')
const pending = computed(
  () =>
    !!props.session.intent ||
    (!!props.session.requestId &&
      (!props.session.result || props.session.result.state === 'QUEUED')),
)
const labels = {
  QUEUED: '等待设备执行',
  COMPLETED: '检查已完成，请查看最新监测与身份结果',
  FAILED: '检查失败，未确认设备可用',
  EXPIRED: '探测已超时，未收到及时结果',
}
let generation = 0,
  controller: AbortController | undefined,
  timer: ReturnType<typeof setTimeout> | undefined
function cancel() {
  generation++
  controller?.abort()
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
  reading.value = false
}
const message = (e: unknown) => (e instanceof Error ? e.message : '探测请求失败')
async function readResult() {
  if (!props.active || !props.session.requestId || reading.value) return
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
  const current = ++generation,
    state = props.session,
    request = state.requestId!
  controller?.abort()
  controller = new AbortController()
  reading.value = true
  readFailed.value = false
  error.value = ''
  try {
    const result = await probeApi.get(props.agentId, request, controller.signal)
    if (current !== generation) return
    state.result = result
    if (result.state === 'QUEUED') timer = setTimeout(() => void readResult(), 3000)
    else emit('completed')
  } catch (e) {
    if (current === generation) {
      state.result = null
      readFailed.value = true
      error.value = message(e)
    }
  } finally {
    if (current === generation) reading.value = false
  }
}
async function send(retrying: boolean) {
  if (busy.value || !props.active || !props.canProbe || props.revoked) return
  const state = props.session,
    old = retrying ? state.intent : null
  if ((retrying && !old) || (!retrying && pending.value)) return
  const current = generation,
    agent = props.agentId,
    actor = props.actorId,
    tenant = props.tenantId
  busy.value = true
  emit('busy', true)
  error.value = ''
  let submitted = false
  try {
    const cap = await environmentApi.capabilities('PROBE')
    if (current !== generation || !props.active) return
    if (cap.data_role !== 'SUPER_ADMIN') throw new Error('仅超级管理员可以发起探测')
    if (
      cap.actor_id !== actor ||
      cap.tenant_id !== tenant ||
      (old &&
        (old.actor_id !== cap.actor_id ||
          old.tenant_id !== cap.tenant_id ||
          old.agent_id !== agent))
    )
      throw new Error('身份已变化，不能使用其他身份重试原探测请求')
    const intent = old ?? {
      agent_id: agent,
      revision: props.revision,
      actor_id: actor,
      tenant_id: tenant,
      key: crypto.randomUUID(),
    }
    if (!old) {
      state.requestId = null
      state.result = null
    }
    state.intent = intent
    submitted = true
    const ack = await probeApi.submit({ ...intent }, cap.csrf_token!)
    state.requestId = ack.id
    state.intent = null
    state.result = null
    if (current !== generation) return
    confirming.value = false
    await readResult()
  } catch (e) {
    if (submitted && !old && !(e instanceof AgentApiError && e.unknown_result)) state.intent = null
    if (current === generation) {
      error.value = message(e)
      confirming.value = false
    }
  } finally {
    busy.value = false
    emit('busy', false)
  }
}
watch(
  () => [props.agentId, props.actorId, props.tenantId, props.active, props.canProbe, props.session],
  () => {
    cancel()
    confirming.value = false
    error.value = ''
    readFailed.value = false
    if (
      props.active &&
      props.session.requestId &&
      (!props.session.result || props.session.result.state === 'QUEUED')
    )
      void readResult()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  cancel()
  emit('busy', false)
})
</script>
<style scoped>
.agent-probe {
  margin-top: 20px;
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}
:deep(.el-descriptions__table) {
  width: 100%;
  table-layout: fixed;
}
:deep(.el-descriptions__cell) {
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
}
.probe-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.probe-confirm {
  padding: 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  margin: 12px 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.el-alert,
.el-descriptions {
  margin: 12px 0;
}
</style>
