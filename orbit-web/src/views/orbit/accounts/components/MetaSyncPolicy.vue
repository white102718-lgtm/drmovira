<template>
  <section v-if="canConfigure" class="meta-sync-policy" aria-label="Meta采集设置">
    <el-button
      size="small"
      :disabled="!active || saving || !!pending"
      @click="expanded ? close() : open()"
      >{{ expanded ? '收起采集设置' : '采集设置' }}</el-button
    >
    <template v-if="expanded">
      <el-alert v-if="error" :title="error" type="error" :closable="false" role="alert" />
      <p v-if="connectionId" class="policy-help">
        当前连接：{{ connectionLabel || connectionId }} ·
        {{ connectionId }}。仅此连接独立生效；首次默认关闭。
      </p>
      <p v-else class="policy-help">租户默认设置仅用于尚未保存独立设置的连接。</p>
      <p class="policy-help">
        选择已发布的指标口径。自动采集由已运行的采集服务执行，保存设置不会启动服务。
      </p>
      <p v-if="connectionId && settings?.revision === 0" class="policy-help">
        尚未保存独立设置，运行时仍使用租户默认策略；保存后以本连接设置为准。
      </p>
      <el-form label-position="top" :disabled="loading || saving || !!pending">
        <el-form-item label="指标口径与适配版本"
          ><el-select v-model="selected" placeholder="选择已验证的指标口径" style="width: 100%"
            ><el-option
              v-for="choice in choices"
              :key="choiceKey(choice)"
              :value="choiceKey(choice)"
              :label="`口径 ${choice.profile_version} · ${choice.profile_id.slice(-6)} / ${choice.adapter_version}`" /></el-select
        ></el-form-item>
        <el-form-item label="自动采集"
          ><el-switch v-model="enabled" active-text="开启" inactive-text="关闭"
        /></el-form-item>
      </el-form>
      <p v-if="settings && !settings.choices.length" class="policy-help">
        暂无已验证指标口径，请先在系统配置中发布。
      </p>
      <p v-if="notice" role="status">{{ notice }}</p>
      <div class="policy-actions">
        <el-button
          v-if="!pending"
          type="primary"
          :disabled="!selected || !settings || loading"
          :loading="saving"
          @click="save"
          >保存采集设置</el-button
        ><el-button v-else type="primary" :loading="saving" @click="retry">用原请求重试</el-button
        ><el-button :disabled="saving || !!pending" :loading="loading" @click="reload"
          >重新读取设置</el-button
        >
      </div>
      <p v-if="pending" class="policy-help">尚未确认保存结果；重试会使用原请求，避免重复修改。</p>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import {
  metaSyncApi,
  type MetaSyncSettings,
  type MetaSyncChoice,
  type MetaSyncPolicyValue,
} from '@/api/orbit/meta-sync'
import { ReferenceApiError } from '@/api/orbit/references'
const props = defineProps<{
  active: boolean
  contextKey: string
  connectionId?: string
  connectionLabel?: string
}>()
const user = useUserStore()
const canConfigure = computed(
  () =>
    user.permissions.includes('*:*:*') ||
    ['system.integrations.manage', 'accounts.sync'].every((p) => user.permissions.includes(p)),
)
const expanded = ref(false),
  settings = ref<MetaSyncSettings | null>(null),
  loading = ref(false),
  saving = ref(false),
  error = ref(''),
  notice = ref(''),
  selected = ref(''),
  enabled = ref(false)
const pending = ref<{ key: string; value: MetaSyncPolicyValue } | null>(null)
let epoch = 0,
  controller: AbortController | undefined
function choiceKey(value: Pick<MetaSyncChoice, 'profile_id' | 'adapter_version'>) {
  return JSON.stringify([value.profile_id, value.adapter_version])
}
const choices = computed(() => {
  const rows = [...(settings.value?.choices ?? [])],
    current = settings.value
  if (
    current?.profile_id &&
    current.adapter_version &&
    !rows.some(
      (c) => c.profile_id === current.profile_id && c.adapter_version === current.adapter_version,
    )
  )
    rows.push({
      profile_id: current.profile_id,
      adapter_version: current.adapter_version,
      profile_version: '原设置（需重新验证，可关闭）',
    })
  return rows
})
function stop() {
  epoch++
  controller?.abort()
  loading.value = false
}
function close() {
  stop()
  expanded.value = false
  settings.value = null
  error.value = ''
  notice.value = ''
  pending.value = null
  saving.value = false
  selected.value = ''
  enabled.value = false
}
async function reload() {
  if (!props.active || !canConfigure.value || pending.value) return
  stop()
  const own = epoch
  controller = new AbortController()
  loading.value = true
  settings.value = null
  error.value = ''
  notice.value = ''
  try {
    const result = await metaSyncApi.settings(
      controller.signal,
      ...(props.connectionId ? [props.connectionId] : []),
    )
    if (own !== epoch) return
    settings.value = result
    selected.value =
      result.profile_id && result.adapter_version
        ? choiceKey({ profile_id: result.profile_id, adapter_version: result.adapter_version })
        : ''
    enabled.value = result.scheduler_enabled
  } catch (e) {
    if (own === epoch)
      error.value = e instanceof ReferenceApiError ? e.message : '采集设置读取失败，请重试'
  } finally {
    if (own === epoch) loading.value = false
  }
}
function open() {
  expanded.value = true
  void reload()
}
async function submit(intent: { key: string; value: MetaSyncPolicyValue }) {
  if (!settings.value || saving.value || !props.active || !canConfigure.value) return
  const own = epoch
  saving.value = true
  pending.value = intent
  error.value = ''
  notice.value = ''
  try {
    const result = await metaSyncApi.save(
      intent.value,
      settings.value.csrf_token,
      intent.key,
      ...(props.connectionId ? [props.connectionId] : []),
    )
    if (own !== epoch) return
    settings.value = { ...settings.value, ...result }
    pending.value = null
    notice.value = '采集设置已保存。'
  } catch (e) {
    if (own !== epoch) return
    error.value = e instanceof ReferenceApiError ? e.message : '保存结果尚未确认，请使用原请求重试'
    if (e instanceof ReferenceApiError && [400, 401, 403, 404, 409, 422].includes(e.status)) {
      pending.value = null
      if ([401, 403].includes(e.status)) settings.value = null
    }
  } finally {
    if (own === epoch) saving.value = false
  }
}
function save() {
  const choice = choices.value.find((c) => choiceKey(c) === selected.value)
  if (!choice || !settings.value) return
  void submit({
    key: crypto.randomUUID(),
    value: {
      profile_id: choice.profile_id,
      adapter_version: choice.adapter_version,
      scheduler_enabled: enabled.value,
      revision: settings.value.revision,
    },
  })
}
function retry() {
  if (pending.value) void submit(pending.value)
}
watch(() => [props.active, props.contextKey, props.connectionId, canConfigure.value], close)
onBeforeUnmount(stop)
</script>
<style scoped>
.meta-sync-policy {
  padding: 12px 0;
  min-width: 0;
}
.policy-help {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.policy-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.meta-sync-policy :deep(.el-form) {
  max-width: 640px;
  margin-top: 12px;
}
.meta-sync-policy :deep(.el-alert) {
  margin-top: 10px;
}
@media (max-width: 600px) {
  .policy-actions .el-button {
    margin-left: 0;
    flex: 1;
  }
}
</style>
