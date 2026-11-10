<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import {
  metricPublicationApi,
  type PublicationOptions,
  type PublicationSelection,
} from '@/api/orbit/meta-metric-publication'
import { metaConnectionApi, type MetaAccountCandidate } from '@/api/orbit/meta-connections'
import { ReferenceApiError } from '@/api/orbit/references'
const props = defineProps<{ active: boolean; configurationId: string; contextKey: string }>()
const options = ref<PublicationOptions | null>(null),
  accounts = ref<MetaAccountCandidate[]>([]),
  connection = ref(''),
  account = ref(''),
  windows = ref<string[]>([]),
  reportTime = ref(''),
  maturity = ref<number | undefined>(),
  busy = ref(false),
  notice = ref('')
const pending = ref<{ value: PublicationSelection; key: string } | null>(null)
const selected = computed(() =>
  options.value?.configurations.find((c) => c.id === props.configurationId),
)
let generation = 0,
  abort: AbortController | undefined
async function load() {
  const n = ++generation
  abort?.abort()
  abort = new AbortController()
  busy.value = true
  notice.value = ''
  try {
    const result = await metricPublicationApi.options(abort.signal)
    if (n === generation) options.value = result
  } catch {
    if (n === generation) notice.value = '无法读取发布权限或来源配置，请刷新。'
  } finally {
    if (n === generation) busy.value = false
  }
}
watch(
  () => [props.active, props.configurationId, props.contextKey],
  () => {
    generation++
    abort?.abort()
    options.value = null
    accounts.value = []
    pending.value = null
    connection.value = ''
    account.value = ''
    windows.value = []
    reportTime.value = ''
    maturity.value = undefined
    if (props.active) void load()
  },
  { immediate: true },
)
watch(connection, async (id) => {
  account.value = ''
  accounts.value = []
  if (!id) return
  const n = ++generation
  busy.value = true
  notice.value = ''
  try {
    const result = await metaConnectionApi.accounts(id)
    if (n === generation) {
      if (result.next_cursor) {
        notice.value = '账户枚举未完成，暂不能发布。'
        return
      }
      accounts.value = result.items
    }
  } catch {
    if (n === generation) notice.value = '连接账户未通过读取验证，请检查授权。'
  } finally {
    if (n === generation) busy.value = false
  }
})
const ready = computed(
  () =>
    !!options.value?.configured &&
    !!selected.value &&
    !!account.value &&
    !!connection.value &&
    windows.value.length > 0 &&
    !!reportTime.value &&
    Number.isInteger(maturity.value),
)
async function publish() {
  if (busy.value) return
  if (!pending.value) {
    const config = selected.value,
      source = options.value?.connections.find((c) => c.id === connection.value)
    if (!ready.value || !config || !source) return
    pending.value = {
      value: {
        configuration_id: config.id,
        configuration_revision: config.revision,
        connection_id: source.id,
        connection_revision: source.revision,
        account_id: account.value,
        attribution_windows: [...windows.value],
        action_report_time: reportTime.value,
        maturity_days: maturity.value!,
        expected_revision: config.head_revision,
      },
      key: crypto.randomUUID(),
    }
  }
  const frozen = pending.value,
    n = generation
  busy.value = true
  notice.value = ''
  try {
    const current = await metricPublicationApi.options()
    if (n !== generation) return
    const result = await metricPublicationApi.publish(frozen.value, current.csrf_token, frozen.key)
    if (n !== generation) return
    pending.value = null
    notice.value = `口径 ${result.version} 已发布。可在 Meta 采集设置中选择该口径。`
    options.value = await metricPublicationApi.options()
  } catch (error) {
    if (n !== generation) return
    if (error instanceof ReferenceApiError && error.status >= 400 && error.status < 500) {
      pending.value = null
      notice.value = '配置或授权已变化，请刷新后检查选择。'
    } else notice.value = '尚未确认发布成功，请保留当前选择并重试原请求；未验证来源不会发布。'
  } finally {
    if (n === generation) busy.value = false
  }
}
onBeforeUnmount(() => {
  generation++
  abort?.abort()
})
</script>
<template>
  <section v-loading="busy">
    <el-alert v-if="notice" :title="notice" type="info" :closable="false" show-icon />
    <el-alert
      v-if="options && !options.configured"
      title="平台 Graph 版本或加密配置尚未就绪，口径保持待验证。"
      type="warning"
      :closable="false"
    />
    <p>
      沿用已保存的指标版本和三个动作标识。服务端真实读取所选账户后才发布；动作按原字符串精确匹配，未返回的数值保持未知。发布不代表已采集历史数据。
    </p>
    <el-descriptions v-if="selected" :column="1" border>
      <el-descriptions-item label="配置 / 版本"
        >{{ selected.name }} / {{ selected.settings.profileVersion }}</el-descriptions-item
      >
      <el-descriptions-item label="注册动作">{{
        selected.settings.registerActionType
      }}</el-descriptions-item>
      <el-descriptions-item label="购物动作">{{
        selected.settings.purchaseActionType
      }}</el-descriptions-item>
      <el-descriptions-item label="购物价值动作">{{
        selected.settings.valueActionType
      }}</el-descriptions-item>
    </el-descriptions>
    <el-empty v-else-if="options" description="当前启用配置不可用，请先保存完整 METRICS 配置。" />
    <el-form
      label-position="top"
      :disabled="busy || !!pending || !options?.configured"
      class="publication-form"
    >
      <el-form-item label="真实 Meta 连接"
        ><el-select v-model="connection" placeholder="明确选择读取来源"
          ><el-option
            v-for="c in options?.connections"
            :key="c.id"
            :value="c.id"
            :label="`${c.kind} · ${c.id} · v${c.revision}`" /></el-select
      ></el-form-item>
      <el-form-item label="验证广告账户"
        ><el-select v-model="account" filterable placeholder="先读取连接账户"
          ><el-option
            v-for="a in accounts"
            :key="a.external_id"
            :value="a.external_id"
            :label="`${a.name || '名称未知'} · ${a.external_id}`" /></el-select
      ></el-form-item>
      <el-form-item label="显式归因窗口"
        ><el-select v-model="windows" multiple placeholder="请选择，不使用默认口径"
          ><el-option
            v-for="w in options?.attribution_windows"
            :key="w"
            :value="w"
            :label="w" /></el-select
      ></el-form-item>
      <el-form-item label="报告时间口径"
        ><el-select v-model="reportTime" placeholder="请选择"
          ><el-option
            v-for="t in options?.action_report_times"
            :key="t"
            :value="t"
            :label="t" /></el-select
      ></el-form-item>
      <el-form-item label="归因成熟天数"
        ><el-input-number v-model="maturity" :min="1" :max="90" :precision="0"
      /></el-form-item>
    </el-form>
    <el-button :disabled="busy || !!pending" @click="load">刷新来源</el-button>
    <el-button type="primary" :loading="busy" :disabled="!pending && !ready" @click="publish">{{
      pending ? '重试原发布请求' : '真实验证并发布口径'
    }}</el-button>
  </section>
</template>
<style scoped>
.publication-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
  margin-top: 16px;
}
.publication-form .el-select {
  width: 100%;
}
p {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
@media (max-width: 600px) {
  .publication-form {
    grid-template-columns: 1fr;
  }
}
</style>
