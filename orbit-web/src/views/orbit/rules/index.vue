<template>
  <main class="app-container rules-page">
    <header class="page-header">
      <h1>智能规则</h1>
      <p>定义、模拟与运行记录以各自真实服务端回执为准。</p>
    </header>
    <el-alert v-if="leaveBlocked" :title="leaveBlocked" type="warning" :closable="false" />
    <el-alert v-if="routeError" :title="routeError" type="error" :closable="false" />
    <el-alert
      v-if="pending"
      :title="
        samePendingActor
          ? '有未确认的规则请求，禁止新写入。请恢复原请求确认结果。'
          : '其它认证生命周期存在未确认请求，已隐藏其内容；当前身份不会重发。'
      "
      type="warning"
      :closable="false"
    />
    <div v-if="pending" class="recovery-panel">
      <a href="/login" target="_blank" rel="noopener">在新标签页重新登录</a>
      <p>请保留本页，登录完成后回到这里验证当前身份；不会自动提交原请求。</p>
      <el-button :loading="verifyingIdentity" @click="verifyPendingIdentity"
        >重新验证当前身份（不提交）</el-button
      >
      <p v-if="identityResult" role="status">{{ identityResult }}</p>
    </div>
    <div class="page-actions">
      <el-button v-if="mode !== 'LIST'" @click="returnToList">返回规则列表</el-button>
      <el-button
        v-if="canCreate && !canRead && mode === 'LIST'"
        :disabled="!!pending"
        @click="openCreate"
        >创建规则</el-button
      >
      <el-button v-if="pending && samePendingActor && mode === 'LIST'" @click="restore"
        >恢复原未确认请求</el-button
      >
      <el-button v-if="refreshNeeded && canRead && mode === 'LIST'" @click="refreshList"
        >刷新当前列表</el-button
      >
    </div>
    <section
      v-if="canRead || pending?.kind === 'ACTION'"
      v-show="mode === 'LIST'"
      :inert="pending?.kind === 'EDITOR' ? true : undefined"
      :aria-label="pending ? '规则列表（未确认请求期间只读）' : '规则列表区域'"
      @click.capture="guardListEvent"
      @keydown.capture="guardListEvent"
    >
      <RuleList
        :key="contextKey"
        ref="list"
        :permission-codes="permissions"
        :native-actor-id="nativeActorId"
        :context-key="contextKey"
        :pending-action="pending?.kind === 'ACTION' ? pending.value : null"
        @pending-action="rememberListAction"
        :recovery-busy="verifyingIdentity"
        :recovery-message="identityResult"
        @verify-identity="verifyPendingIdentity"
        @create="openCreate"
        @edit="openEdit"
      />
    </section>
    <el-alert
      v-else-if="mode === 'LIST'"
      title="当前没有规则读取权限；拥有创建或编辑动作时可从对应入口打开编辑器，不会借用读取动作。"
      type="info"
      :closable="false"
    />
    <RuleEditor
      v-if="editorVisible"
      :key="editorKey"
      ref="editor"
      :rule-id="editingId"
      :native-actor-id="nativeActorId"
      :context-key="contextKey"
      :permission-codes="permissions"
      :pending-intent="pending?.kind === 'EDITOR' ? pending.value : null"
      @pending-intent="remember"
      :recovery-busy="verifyingIdentity"
      :recovery-message="identityResult"
      @verify-identity="verifyPendingIdentity"
      @saved="saved"
      @close="returnToList"
    />
    <el-alert
      v-else-if="mode !== 'LIST' && !routeError"
      title="当前缺少此规则创建或编辑动作，或有其它未确认意图；不会读取或提交编辑数据。"
      type="warning"
      :closable="false"
    />
    <p class="unavailable">
      全局触发记录 /rule-hits 尚未接入；规则详情中的运行记录是原RuleRun，不代替全局触发记录。
    </p>
  </main>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import useUserStore from '@/store/modules/user'
import RuleList from './RuleList.vue'
import RuleEditor from './RuleEditor.vue'
import { RuleApiError, type Rule } from '@/api/orbit/rules'
import {
  ruleRecoveryApi,
  requireRecoveryPrincipal,
  requireInitialRuleActor,
} from '@/api/orbit/rule-recovery'
import { refreshCookieCsrfForRecovery } from '@/api/orbit/authentication'
type EditorPending = NonNullable<InstanceType<typeof RuleEditor>['$props']['pendingIntent']>
type ActionPending = NonNullable<InstanceType<typeof RuleList>['$props']['pendingAction']>
type Envelope =
  | {
      kind: 'EDITOR'
      context: string
      mode: 'CREATE' | 'EDIT'
      ruleId: string | null
      value: EditorPending
    }
  | { kind: 'ACTION'; context: string; mode: 'LIST'; ruleId: null; value: ActionPending }
const user = useUserStore(),
  route = useRoute(),
  router = useRouter()
const lifecycle = ref(crypto.randomUUID())
// 凭据只用于响应式生命周期变化检测，绝不进入context、路由、存储或日志。
watch(
  () => JSON.stringify([user.id, Boolean(user.token), user.permissions.length === 0]),
  () => {
    lifecycle.value = crypto.randomUUID()
  },
  { flush: 'sync' },
)
const contextKey = computed(() => JSON.stringify([String(user.id ?? ''), lifecycle.value]))
const nativeActorId = computed(() => {
  const value = String(user.id ?? '')
  const parsed = /^[1-9]\d*$/.test(value) ? Number(value) : NaN
  return Number.isSafeInteger(parsed) ? parsed : null
})
const verifyingIdentity = ref(false),
  identityResult = ref('')
const permissions = computed<string[]>(() => [...user.permissions])
const has = (code: string) =>
  permissions.value.includes('*:*:*') || permissions.value.includes(code)
const canRead = computed(() => has('rules.read')),
  canCreate = computed(() => has('rules.create'))
const pending = shallowRef<Envelope | null>(null),
  refreshNeeded = ref(false),
  leaveBlocked = ref('')
const list = ref<{ refresh: () => Promise<void>; hideSensitiveForRecovery?: () => void } | null>(
  null,
)
const editor = ref<{ hideSensitiveForRecovery?: () => void } | null>(null)
const scalar = (value: unknown) => (typeof value === 'string' ? value : null)
const mode = computed<'LIST' | 'CREATE' | 'EDIT' | 'INVALID'>(() => {
  if (route.query.mode === undefined && route.query.rule_id === undefined) return 'LIST'
  if (scalar(route.query.mode) === 'create' && route.query.rule_id === undefined) return 'CREATE'
  if (
    scalar(route.query.mode) === 'edit' &&
    typeof route.query.rule_id === 'string' &&
    /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(route.query.rule_id)
  )
    return 'EDIT'
  return 'INVALID'
})
const editingId = computed(() =>
  mode.value === 'EDIT' ? String(route.query.rule_id).toLowerCase() : null,
)
const routeError = computed(() =>
  mode.value === 'INVALID' ? '规则编辑地址无效：创建不带rule_id，编辑必须有唯一真实UUID。' : '',
)
const samePendingActor = computed(() => pending.value?.context === contextKey.value)
const pendingTargetMatches = computed(
  () =>
    !pending.value ||
    (pending.value.kind === 'EDITOR' &&
      samePendingActor.value &&
      pending.value.mode === mode.value &&
      pending.value.ruleId === editingId.value),
)
const editorVisible = computed(
  () =>
    (mode.value === 'CREATE' ? canCreate.value : mode.value === 'EDIT' && has('rules.edit')) &&
    pendingTargetMatches.value,
)
const editorKey = computed(() => JSON.stringify([contextKey.value, mode.value, editingId.value]))
async function navigate(modeValue: 'CREATE' | 'EDIT' | 'LIST', id: string | null = null) {
  const query = { ...route.query }
  delete query.mode
  delete query.rule_id
  if (modeValue !== 'LIST') query.mode = modeValue === 'CREATE' ? 'create' : 'edit'
  if (modeValue === 'EDIT' && id) query.rule_id = id
  await router.push({ path: route.path, query })
}
function openCreate() {
  if (canCreate.value && !pending.value) navigate('CREATE')
}
function openEdit(rule: Rule) {
  if (has('rules.edit') && !pending.value) navigate('EDIT', rule.id)
}
function returnToList() {
  navigate('LIST')
}
function remember(value: EditorPending | null) {
  if (value) {
    if (pending.value && !pendingTargetMatches.value) return
    if (mode.value !== 'CREATE' && mode.value !== 'EDIT') return
    const action = mode.value === 'CREATE' ? 'CREATE' : 'UPDATE'
    // 只接收当前子编辑器的原上下文，不能把迟到旧actor事件重新盖成当前身份。
    if (value.kind === 'SAVE') {
      if (
        value.intent.context !== JSON.stringify([contextKey.value, editingId.value]) ||
        value.intent.action !== action ||
        value.intent.ruleId !== editingId.value
      )
        return
    } else {
      const body = value.intent.intent.body
      if (
        body.action !== action ||
        body.rule_id !== editingId.value ||
        value.intent.context !==
          JSON.stringify([
            contextKey.value,
            action,
            editingId.value,
            body.ownership.owner_user_id,
            body.ownership.owner_team_id,
          ])
      )
        return
    }
    pending.value = {
      kind: 'EDITOR',
      context: contextKey.value,
      mode: mode.value,
      ruleId: editingId.value,
      value,
    }
  } else if (samePendingActor.value && pendingTargetMatches.value) pending.value = null
}
function rememberListAction(value: ActionPending | null) {
  if (value) {
    if (value.context !== contextKey.value || (pending.value && pending.value.kind !== 'ACTION'))
      return
    pending.value = { kind: 'ACTION', context: contextKey.value, mode: 'LIST', ruleId: null, value }
  } else if (pending.value?.kind === 'ACTION' && samePendingActor.value) {
    pending.value = null
    leaveBlocked.value = ''
  }
}
async function verifyPendingIdentity() {
  const original = pending.value
  if (!original || verifyingIdentity.value) return
  verifyingIdentity.value = true
  identityResult.value = ''
  list.value?.hideSensitiveForRecovery?.()
  editor.value?.hideSensitiveForRecovery?.()
  try {
    const action =
      original.kind === 'ACTION'
        ? original.value.action
        : original.value.kind === 'SAVE'
          ? original.value.intent.action
          : original.value.intent.intent.body.action
    const principal =
      original.kind === 'ACTION'
        ? original.value.principal
        : original.value.kind === 'SAVE'
          ? original.value.intent.principal
          : original.value.intent.principal
    let current = await ruleRecoveryApi.get(action)
    requireRecoveryPrincipal(principal, current)
    // 现getInfo尊重Cookie/Bearer模式；刷新实际UI身份后再次核验证据，不用nonce猜授权。
    await user.getInfo()
    current = await ruleRecoveryApi.get(action)
    requireRecoveryPrincipal(principal, current)
    requireInitialRuleActor(nativeActorId.value, current)
    if (pending.value !== original) return
    refreshCookieCsrfForRecovery(current.csrf_token)
    const clientContext = contextKey.value
    if (original.kind === 'ACTION')
      pending.value = {
        ...original,
        context: clientContext,
        value: { ...original.value, context: clientContext },
      }
    else if (original.value.kind === 'SAVE')
      pending.value = {
        ...original,
        context: clientContext,
        value: {
          kind: 'SAVE',
          intent: {
            ...original.value.intent,
            context: JSON.stringify([clientContext, original.ruleId]),
          },
        },
      }
    else {
      const body = original.value.intent.intent.body
      pending.value = {
        ...original,
        context: clientContext,
        value: {
          kind: 'SCOPE',
          intent: {
            ...original.value.intent,
            context: JSON.stringify([
              clientContext,
              body.action,
              body.rule_id,
              body.ownership.owner_user_id,
              body.ownership.owner_team_id,
            ]),
          },
        },
      }
    }
    identityResult.value = '已验证为原请求主体；请显式打开原请求并手动恢复。尚未提交。'
  } catch (e) {
    identityResult.value =
      e instanceof RuleApiError
        ? `${e.message}（${e.code}）`
        : '身份验证失败，原请求仍保留；请重试。'
  } finally {
    verifyingIdentity.value = false
  }
}
function restore() {
  if (pending.value && samePendingActor.value) navigate(pending.value.mode, pending.value.ruleId)
}
async function saved() {
  refreshNeeded.value = true
  await navigate('LIST')
  await nextTick()
  if (canRead.value && mode.value === 'LIST') await refreshList()
}
async function refreshList() {
  if (!pending.value && canRead.value && list.value) {
    await list.value.refresh()
    refreshNeeded.value = false
  }
}
function guardListEvent(event: Event) {
  if (pending.value?.kind === 'EDITOR') {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
}
onBeforeRouteLeave(() => {
  if (!pending.value) return true
  leaveBlocked.value = '存在未确认请求，已保留原请求；请先在本页确认结果后再离开。'
  return false
})
</script>
<style scoped>
.page-header h1 {
  font-size: 22px;
  margin: 0 0 8px;
}
.page-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 16px 0;
}
.unavailable {
  margin-top: 24px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
