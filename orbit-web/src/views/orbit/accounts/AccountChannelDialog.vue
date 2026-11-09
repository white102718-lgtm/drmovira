<template>
  <el-dialog
    v-model="visible"
    title="账户当前渠道"
    width="min(620px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
    @closed="invalidate"
  >
    <p>账户：{{ account?.name }}（{{ account?.external_id }}）</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <p v-if="current">
      当前渠道：{{ current.channel_id || '未关联' }} · 账户版本 {{ current.revision }}
    </p>
    <p>调整立即影响规则的当前渠道筛选，历史投放与指标事实保留原记录。</p>
    <el-form label-position="top">
      <el-form-item label="当前渠道（清空表示解除关联）">
        <el-select
          v-model="selected"
          clearable
          placeholder="未关联渠道"
          aria-label="账户当前渠道"
          :disabled="locked"
          @visible-change="opened"
        >
          <el-option
            v-if="selected && !options.some((x) => x.id === selected)"
            :value="selected"
            :label="`当前渠道 ID · ${selected}`"
          />
          <el-option
            v-for="item in options"
            :key="item.id"
            :value="item.id"
            :label="`${item.name || item.code} · ${item.code}`"
          />
          <template #footer>
            <p v-if="optionsError" role="alert">{{ optionsError }}</p>
            <span v-if="optionsLoading">正在读取渠道…</span>
            <el-button size="small" :disabled="optionsLoading" @click="loadOptions()"
              >重新读取渠道</el-button
            >
            <el-button
              size="small"
              :disabled="optionsLoading || !nextCursor"
              @click="loadOptions(nextCursor!)"
              >下一页渠道</el-button
            >
          </template>
        </el-select>
      </el-form-item>
      <el-form-item label="变更原因" required>
        <el-input
          v-model="reason"
          aria-label="渠道变更原因"
          type="textarea"
          :disabled="locked"
          :rows="3"
          maxlength="2000"
        />
        <span>{{ [...reason.trim()].length }} / 1000 字</span>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="uncertain"
      title="原请求结果未确认，内容已锁定。请显式重试原请求；关闭后重新打开同一账户仍保留本次意图。"
      type="warning"
      :closable="false"
    />
    <p v-if="current && !current.csrf_token">当前仅可查看；修改需要账户分配权限。</p>
    <p v-if="success" role="status">渠道关联已保存，已重新读取当前关联。</p>
    <template #footer>
      <el-button :disabled="saving" @click="visible = false">关闭</el-button>
      <el-button v-if="!saving" :disabled="loading || saving" @click="load">重新读取关联</el-button>
      <el-button
        type="primary"
        :loading="saving"
        :disabled="loading || !current?.csrf_token || (!uncertain && !validReason)"
        @click="submit"
        >{{ uncertain ? '重试原请求' : '保存关联' }}</el-button
      >
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  accountChannelApi,
  accountChannelContext,
  type AccountChannel,
  type AccountChannelIntent,
} from '@/api/orbit/account-channel'
import { channelApi, type Channel } from '@/api/orbit/channels'
import type { OrbitAccount } from '@/api/orbit/accounts'
import { ReferenceApiError } from '@/api/orbit/references'
const props = defineProps<{ contextKey?: string }>()
const emit = defineEmits<{ accepted: [] }>()
const visible = ref(false),
  loading = ref(false),
  saving = ref(false),
  uncertain = ref(false),
  success = ref(false)
const account = ref<Pick<OrbitAccount, 'id' | 'name' | 'external_id'> | null>(null)
const current = ref<AccountChannel | null>(null),
  selected = ref(''),
  reason = ref(''),
  error = ref('')
const options = ref<Channel[]>([]),
  optionsLoading = ref(false),
  optionsError = ref(''),
  nextCursor = ref<string | null>(null)
const pending = new Map<string, AccountChannelIntent>()
let epoch = 0,
  optionEpoch = 0,
  context = ''
const key = () => `${context}:${account.value?.id}`
const validReason = computed(() => {
  const s = reason.value.normalize('NFC').trim()
  return [...s].length > 0 && [...s].length <= 1000 && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(s)
})
const locked = computed(
  () => loading.value || saving.value || uncertain.value || !current.value?.csrf_token,
)
function invalidate() {
  loading.value = false
  optionsLoading.value = false
  epoch++
  optionEpoch++
  options.value = []
  current.value = null
  selected.value = ''
  reason.value = ''
  error.value = ''
  optionsError.value = ''
  nextCursor.value = null
}
function sameContext() {
  if (context === accountChannelContext()) return true
  invalidate()
  uncertain.value = false
  error.value = '认证上下文已变化，请关闭后重新打开账户'
  return false
}
async function load() {
  if (!account.value || !sameContext()) return
  const token = ++epoch
  loading.value = true
  error.value = ''
  current.value = null
  try {
    const v = await accountChannelApi.get(account.value.id)
    if (token !== epoch || !sameContext()) return
    current.value = v
    if (!uncertain.value) selected.value = v.channel_id || ''
  } catch (e) {
    if (token === epoch) error.value = e instanceof Error ? e.message : '关联读取失败'
  } finally {
    if (token === epoch) loading.value = false
  }
}
async function open(value: Pick<OrbitAccount, 'id' | 'name' | 'external_id'>) {
  if (saving.value) return
  invalidate()
  account.value = value
  context = accountChannelContext()
  visible.value = true
  success.value = false
  const original = pending.get(key())
  uncertain.value = !!original
  if (original) {
    selected.value = original.body.channel_id || ''
    reason.value = original.body.reason
  }
  await load()
}
async function loadOptions(cursor?: string) {
  if (locked.value || !sameContext()) return
  const token = ++optionEpoch
  optionsLoading.value = true
  optionsError.value = ''
  options.value = []
  nextCursor.value = null
  try {
    const v = await channelApi.list(
      new URLSearchParams({ page_size: '50', status: 'ENABLED', ...(cursor ? { cursor } : {}) }),
    )
    if (token !== optionEpoch || !sameContext()) return
    options.value = v.items
    nextCursor.value = v.next_cursor
  } catch (e) {
    if (token === optionEpoch)
      optionsError.value =
        e instanceof ReferenceApiError && [401, 403].includes(e.status)
          ? '没有渠道读取权限或会话已失效，请联系管理员授权后重新读取'
          : e instanceof Error
            ? e.message
            : '渠道读取失败'
  } finally {
    if (token === optionEpoch) optionsLoading.value = false
  }
}
function opened(show: boolean) {
  if (show && !options.value.length && !optionsLoading.value) void loadOptions()
}
async function submit() {
  if (
    saving.value ||
    loading.value ||
    !account.value ||
    !current.value?.csrf_token ||
    !sameContext()
  )
    return
  let intent = pending.get(key())
  if (!intent) {
    if (!current.value?.csrf_token || !validReason.value) return
    intent = {
      accountId: account.value.id,
      revision: current.value.revision,
      csrf: current.value.csrf_token,
      key: crypto.randomUUID(),
      body: { channel_id: selected.value || null, reason: reason.value.normalize('NFC').trim() },
    }
    pending.set(key(), intent)
  }
  // 同一认证上下文重新读取后只更新CSRF，不改原键、正文或CAS。
  intent = { ...intent, csrf: current.value.csrf_token }
  pending.set(key(), intent)
  const wasUncertain = uncertain.value
  const token = epoch
  saving.value = true
  error.value = ''
  success.value = false
  try {
    await accountChannelApi.save(intent)
    if (token !== epoch || !sameContext()) return
    pending.delete(key())
    uncertain.value = false
    reason.value = ''
    emit('accepted')
    await load()
    success.value = !!current.value
  } catch (e) {
    if (token !== epoch) return
    const known =
      !wasUncertain &&
      e instanceof ReferenceApiError &&
      e.status >= 400 &&
      e.status < 500 &&
      e.code !== 'SESSION_CONTEXT_CHANGED'
    uncertain.value = !known
    if (known) pending.delete(key())
    error.value = e instanceof Error ? e.message : '渠道保存结果未确认'
    if (e instanceof ReferenceApiError && [401, 403, 404].includes(e.status)) {
      current.value = null
      options.value = []
      selected.value = ''
    }
  } finally {
    saving.value = false
  }
}
watch(
  () => props.contextKey,
  () => {
    invalidate()
    visible.value = false
  },
)
onBeforeUnmount(() => {
  invalidate()
  pending.clear()
})
defineExpose({ open })
</script>
<style scoped>
.el-select {
  width: 100%;
}
p {
  overflow-wrap: anywhere;
}
.el-alert {
  margin-bottom: 12px;
}
</style>
