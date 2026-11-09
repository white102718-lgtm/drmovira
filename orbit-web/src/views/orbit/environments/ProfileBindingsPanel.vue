<template>
  <el-drawer
    :model-value="modelValue"
    title="账户环境关联"
    size="88%"
    :close-on-click-modal="false"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    :before-close="closePanel"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      title="登记关联尚未验证 Profile、Meta 登录或账户身份，不能据此执行广告操作。无可信 Profile 盘点时请填写执行机的原始 Profile ID；不读取 Local API Key。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
    <div class="toolbar">
      <el-button
        v-if="manageable"
        type="primary"
        :disabled="busy || !!activePending"
        @click="create"
        >新增关联</el-button
      ><el-button v-if="activePending" :disabled="busy" @click="recover">恢复未确认关联</el-button
      ><el-button v-if="canRead" :loading="loading" :disabled="busy" @click="reload"
        >刷新关联</el-button
      >
    </div>
    <template v-if="canRead">
      <el-table :data="items" border v-loading="loading" empty-text="暂无当前可见的账户环境关联">
        <el-table-column prop="profile_external_id" label="Profile ID" min-width="140" />
        <el-table-column label="操作" width="190"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              :disabled="busy || !!activePending"
              @click="open(row.id, 'DETAIL')"
              >关联详情</el-button
            ><el-button
              v-if="manageable"
              link
              type="primary"
              :disabled="busy || !!activePending"
              @click="open(row.id, 'SAVE')"
              >编辑关联</el-button
            ><el-button
              v-if="manageable"
              link
              type="danger"
              :disabled="busy || !!activePending"
              @click="open(row.id, 'UNBIND')"
              >解绑</el-button
            ></template
          ></el-table-column
        >
        <el-table-column prop="account_id" label="账户 ID" min-width="290" /><el-table-column
          prop="agent_id"
          label="Agent ID"
          min-width="290"
        />
        <el-table-column label="身份核验" width="145"
          ><template #default="{ row }">{{
            identityLabels[row.identity_state as keyof typeof identityLabels]
          }}</template></el-table-column
        ><el-table-column label="核验时刻" min-width="160"
          ><template #default="{ row }">{{
            row.verified_at || '未知（未验证）'
          }}</template></el-table-column
        >
        <el-table-column
          prop="ownership.owner_user_id"
          label="归属用户 ID"
          min-width="290"
        /><el-table-column
          prop="ownership.owner_team_id"
          label="归属团队 ID"
          min-width="290"
        /><el-table-column prop="id" label="关联 ID" min-width="290" /><el-table-column
          prop="revision"
          label="版本"
          width="70"
        />
      </el-table>
      <div class="toolbar">
        <el-select
          v-model="pageSize"
          style="width: 120px"
          :disabled="loading || busy"
          @change="reload"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :value="size"
            :label="`${size} 条/页`" /></el-select
        ><el-button :disabled="loading || busy || index === 0" @click="move(-1)"
          >关联上一页</el-button
        ><span>第 {{ index + 1 }} 页</span
        ><el-button :disabled="loading || busy || !nextCursor" @click="move(1)"
          >关联下一页</el-button
        >
      </div>
    </template>
    <p v-else>没有关联读取权限；可独立登记允许的账户环境关联。</p>
    <el-dialog
      v-model="editing"
      :title="
        mode === 'DETAIL'
          ? '关联详情'
          : mode === 'UNBIND'
            ? '解绑账户环境'
            : selected
              ? '修改账户环境关联'
              : '新增账户环境关联'
      "
      width="680px"
      append-to-body
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      :before-close="closeOperation"
    >
      <el-alert v-if="dialogError" :title="dialogError" type="error" :closable="false" />
      <el-alert
        v-if="activePending"
        title="关联操作结果未确认，已在本页内存中保留原请求。可关闭弹窗后恢复；刷新或离开页面会丢失本次恢复信息。"
        type="warning"
        :closable="false"
      />
      <el-form v-if="mode !== 'UNBIND'" label-position="top" @submit.prevent="save">
        <el-form-item v-for="field in fields" :key="field.key" :label="field.label"
          ><el-input
            v-model="draft[field.key]"
            :aria-label="field.label"
            :disabled="busy || !!activePending || mode === 'DETAIL' || !manageable"
        /></el-form-item>
        <p v-if="selected">
          关联 ID：{{ selected.id }} · 版本 {{ selected.revision }} ·
          {{ identityLabels[selected.identity_state] }} · 核验时刻
          {{ selected.verified_at || '未知' }}
        </p>
        <el-button
          v-if="mode === 'SAVE'"
          type="primary"
          native-type="submit"
          :disabled="busy || !!activePending || !manageable"
          >保存关联</el-button
        >
      </el-form>
      <el-form v-else label-position="top" @submit.prevent="unbind"
        ><p>
          解绑
          {{
            selected?.profile_external_id || activePending?.id
          }}，将阻止后续使用此关联；不会代替远端任务或 Meta 状态核验。
        </p>
        <el-form-item label="解绑原因"
          ><el-input
            v-model="reason"
            type="textarea"
            aria-label="解绑原因"
            :disabled="busy || !!activePending" /></el-form-item
        ><el-button
          type="danger"
          native-type="submit"
          :disabled="busy || !!activePending || !manageable"
          >确认解绑</el-button
        ></el-form
      >
      <template #footer
        ><el-button :disabled="busy" @click="closeOperation()">关闭操作</el-button
        ><el-button v-if="activePending" type="warning" :loading="busy" @click="retry"
          >重试原关联请求</el-button
        ></template
      >
    </el-dialog>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { AgentApiError, environmentApi, type AgentCapability } from '@/api/orbit/environments'
import {
  bindingApi,
  parseBindingWrite,
  type BindingIntent,
  type BindingWrite,
  type ProfileBinding,
} from '@/api/orbit/environments-bindings'
const props = withDefaults(
  defineProps<{ modelValue: boolean; canRead: boolean; canWrite: boolean; contextKey?: string }>(),
  { contextKey: '' },
)
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const cap = ref<AgentCapability | null>(null),
  manageable = computed(() => props.canWrite && cap.value?.data_role === 'SUPER_ADMIN')
const identity = (value: { actor_id: number; tenant_id: string }) =>
  `${value.tenant_id}:${value.actor_id}`
const pending = reactive(new Map<string, BindingIntent>()),
  activePending = computed(() =>
    cap.value && manageable.value ? pending.get(identity(cap.value)) : undefined,
  )
const error = ref(''),
  notice = ref(''),
  dialogError = ref(''),
  loading = ref(false),
  busy = ref(false),
  editing = ref(false)
const items = ref<ProfileBinding[]>([]),
  selected = ref<ProfileBinding | null>(null),
  mode = ref<'SAVE' | 'UNBIND' | 'DETAIL'>('SAVE'),
  reason = ref('')
const nextCursor = ref<string | null>(null),
  pageSize = ref(20),
  index = ref(0)
let cursors: (string | undefined)[] = [undefined],
  generation = 0,
  controller: AbortController | undefined
const draft = reactive({
  account_id: '',
  agent_id: '',
  profile_external_id: '',
  owner_user_id: '',
  owner_team_id: '',
})
const fields = [
  { key: 'account_id', label: '账户 ID' },
  { key: 'agent_id', label: 'Agent ID' },
  { key: 'profile_external_id', label: 'Profile ID' },
  { key: 'owner_user_id', label: '归属用户 ID' },
  { key: 'owner_team_id', label: '归属团队 ID' },
] as const
const identityLabels = {
  UNKNOWN: '未验证',
  VALID: '身份有效（仍须执行前复核）',
  LOGIN_REQUIRED: '需要登录',
  CHALLENGE: '需要人工处理',
  IDENTITY_MISMATCH: '身份不匹配',
}
function fill(body?: BindingWrite) {
  Object.assign(draft, {
    account_id: body?.account_id ?? '',
    agent_id: body?.agent_id ?? '',
    profile_external_id: body?.profile_external_id ?? '',
    owner_user_id: body?.ownership.owner_user_id ?? '',
    owner_team_id: body?.ownership.owner_team_id ?? '',
  })
}
function clearVisible() {
  items.value = []
  selected.value = null
  editing.value = false
  fill()
  reason.value = ''
  error.value = ''
  notice.value = ''
  dialogError.value = ''
  nextCursor.value = null
}
const message = (e: unknown) => (e instanceof Error ? e.message : '账户环境请求失败')
async function initialize() {
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  cap.value = null
  clearVisible()
  if (!props.modelValue) return
  loading.value = true
  try {
    if (!props.canRead && !props.canWrite) throw new Error('没有账户环境读取或登记权限')
    const value = await environmentApi.capabilities(
      props.canRead ? 'READ' : 'ENROLL',
      controller.signal,
    )
    if (current !== generation) return
    cap.value = value
    if (props.canRead) {
      cursors = [undefined]
      await load(0)
    }
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    if (current === generation) loading.value = false
  }
}
async function load(page: number) {
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  items.value = []
  nextCursor.value = null
  error.value = ''
  loading.value = true
  try {
    const result = await bindingApi.list(
      { page_size: pageSize.value, cursor: cursors[page] },
      controller.signal,
    )
    if (current !== generation) return
    items.value = result.items
    nextCursor.value = result.next_cursor
    index.value = page
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    if (current === generation) loading.value = false
  }
}
function reload() {
  if (busy.value) return
  cursors = [undefined]
  void load(0)
}
function move(delta: number) {
  if (busy.value || loading.value) return
  if (delta > 0) {
    if (!nextCursor.value) return
    cursors[index.value + 1] = nextCursor.value
  }
  void load(index.value + delta)
}
function create() {
  if (!manageable.value || busy.value || activePending.value) return
  selected.value = null
  mode.value = 'SAVE'
  fill()
  dialogError.value = ''
  editing.value = true
}
async function open(id: string, next: 'DETAIL' | 'SAVE' | 'UNBIND') {
  if (activePending.value) return
  if (busy.value || (next !== 'DETAIL' && (!manageable.value || activePending.value))) return
  const current = generation
  busy.value = true
  try {
    const row = await bindingApi.get(id)
    if (current !== generation) return
    selected.value = row
    mode.value = next
    fill(row)
    reason.value = ''
    dialogError.value = ''
    editing.value = true
  } catch (e) {
    if (current === generation) error.value = message(e)
  } finally {
    busy.value = false
  }
}
function closeOperation(done?: () => void) {
  if (busy.value) return
  editing.value = false
  done?.()
}
function closePanel(done?: () => void) {
  if (busy.value) return
  emit('update:modelValue', false)
  done?.()
}
function recover() {
  const intent = activePending.value
  if (!intent || busy.value) return
  mode.value = intent.operation
  fill('account_id' in intent.body ? intent.body : undefined)
  reason.value = 'reason' in intent.body ? intent.body.reason : ''
  dialogError.value = ''
  editing.value = true
}
async function save() {
  if (!manageable.value || busy.value || activePending.value) return
  try {
    const body = parseBindingWrite({
      account_id: draft.account_id,
      agent_id: draft.agent_id,
      profile_external_id: draft.profile_external_id,
      ownership: { owner_user_id: draft.owner_user_id, owner_team_id: draft.owner_team_id },
    })
    await send({
      operation: 'SAVE',
      body,
      ...(selected.value ? { id: selected.value.id, revision: selected.value.revision } : {}),
    })
  } catch (e) {
    dialogError.value = message(e)
  }
}
async function unbind() {
  if (!manageable.value || busy.value || activePending.value || !selected.value) return
  const value = reason.value.normalize('NFC').trim()
  if (!value || [...value].length > 500 || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(reason.value)) {
    dialogError.value = '解绑原因需为 1 至 500 个字符且不能含控制字符'
    return
  }
  await send({
    operation: 'UNBIND',
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
  input: Pick<BindingIntent, 'operation' | 'body' | 'id' | 'revision'>,
  retrying = false,
) {
  if (busy.value || !manageable.value) return
  const old = retrying ? activePending.value : undefined
  if (retrying && !old) return
  busy.value = true
  dialogError.value = ''
  notice.value = ''
  const current = generation
  let intent: BindingIntent | undefined
  try {
    const fresh = await environmentApi.capabilities('ENROLL')
    if (current !== generation) return
    if (fresh.data_role !== 'SUPER_ADMIN') throw new Error('仅超级管理员可以登记或解绑账户环境')
    if (
      (old && identity(old) !== identity(fresh)) ||
      (cap.value && identity(cap.value) !== identity(fresh))
    ) {
      clearVisible()
      cap.value = fresh
      error.value = '身份已变化，不能用其他身份恢复原关联请求'
      return
    }
    cap.value = fresh
    intent = old ?? {
      ...input,
      actor_id: fresh.actor_id,
      tenant_id: fresh.tenant_id,
      key: crypto.randomUUID(),
      body: JSON.parse(JSON.stringify(input.body)),
    }
    pending.set(identity(intent), intent)
    const result = await bindingApi.write(JSON.parse(JSON.stringify(intent)), fresh.csrf_token!)
    pending.delete(identity(intent))
    if (current !== generation) return
    editing.value = false
    selected.value = null
    fill()
    reason.value = ''
    notice.value =
      intent.operation === 'UNBIND' ? '关联已解绑。' : '关联已保存，身份仍未验证，不代表可执行。'
    if (props.canRead) {
      try {
        if (intent.operation === 'UNBIND') {
          try {
            await bindingApi.get(result.id)
            throw new Error('解绑后关联仍可读取')
          } catch (e) {
            if (!(e instanceof AgentApiError && e.status === 404)) throw e
          }
        } else await bindingApi.get(result.id)
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
watch(() => [props.modelValue, props.canRead, props.canWrite, props.contextKey], initialize, {
  immediate: true,
})
onBeforeUnmount(() => {
  generation++
  controller?.abort()
  pending.clear()
})
</script>
<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin: 16px 0;
}
.el-alert {
  margin-bottom: 14px;
}
</style>
