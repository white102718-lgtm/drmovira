<template>
  <section class="app-container metrics-page">
    <h2>广告投放数据</h2>
    <el-alert
      title="金额按币种分别展示。日期为各账户当地业务日；未知指标显示“未知”。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="!canRead"
      title="当前没有查看广告投放数据的权限，请联系管理员。"
      type="warning"
      :closable="false"
    />
    <el-tabs v-model="tab" aria-label="广告投放数据维度" :before-leave="confirmDiscard">
      <el-tab-pane v-for="item in tabs" :key="item.name" :name="item.name" :label="item.label" />
    </el-tabs>
    <template v-if="tab === 'overview'">
      <el-alert title="暂无可用监测数据，请稍后重试。" type="warning" :closable="false" />
      <p>可切换到广告账户、广告系列、广告组或广告，选择指标配置与日期查看数据。</p>
    </template>
    <template v-else>
      <el-alert
        v-if="tab === 'OPERATOR' || tab === 'CHANNEL'"
        title="此维度暂不可用，请稍后重试，或切换广告账户查看数据。"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="canRead && !csrf && !contextError"
        :title="contextLoading ? '正在准备查询…' : '查询准备尚未完成，请重试。'"
        type="warning"
        :closable="false"
      />
      <div v-if="contextError" role="alert">
        <el-alert :title="contextError.message" type="error" :closable="false" />
        <p>
          错误代码：{{ contextError.code }} · 请求ID：{{ contextError.request_id ?? '暂不可用' }}
        </p>
      </div>
      <el-button
        v-if="contextError || (canRead && !csrf && !contextLoading)"
        :disabled="!canRead || contextLoading"
        @click="prepareContext(true)"
        >重新准备查询</el-button
      >
      <MetricQueryForm
        :dataset="dataset"
        :disabled="
          !canRead ||
          !active ||
          !csrf ||
          contextBlocked ||
          loading ||
          Boolean(error?.unknown_result)
        "
        :loading="loading"
        :context-key="context"
        @query="query"
        @changed="conditionsChanged"
      />
      <div v-if="error" role="alert" class="metrics-error">
        <h3>
          {{
            error.status === 503
              ? '暂无可用数据，请稍后重试'
              : error.unknown_result
                ? '查询结果尚未确认'
                : '查询未完成'
          }}
        </h3>
        <p>{{ error.message }}</p>
        <dl>
          <dt>错误代码</dt>
          <dd>{{ error.code }}</dd>
          <dt>请求ID</dt>
          <dd>{{ error.request_id ?? '未收到可核验的服务端请求ID' }}</dd>
          <dt>服务端重读提示</dt>
          <dd>{{ error.retryable ? '可以重试查询' : '请检查筛选条件或稍后重试' }}</dd>
        </dl>
        <ul v-if="error.field_errors.length">
          <li v-for="(field, i) in error.field_errors" :key="i">
            <code>{{ field.path }}</code
            >：{{ field.message }}（{{ field.code }}；{{ field.constraint }}）
          </li>
        </ul>
        <p v-if="error.status === 409">数据范围已变化。请重新查询第一页。</p>
        <p v-if="error.unknown_result">
          连接已中断，暂时无法确认结果。请选择“使用原查询重试”，或确认后重新查询。
        </p>
      </div>
      <div class="metrics-actions">
        <el-button
          v-if="pending && error"
          :disabled="!canRead || !active || !csrf || loading || [401, 403].includes(error.status)"
          @click="retry"
          >使用原查询重试</el-button
        >
        <el-button v-if="error" :disabled="loading || !canRead || !active" @click="resetQuery"
          >确认并重新查询</el-button
        >
        <el-button
          :disabled="!data || !history.length || loading || Boolean(error) || !canRead || !active"
          @click="previous"
          >上一页</el-button
        >
        <span v-if="data">第{{ history.length + 1 }}页 · 当前{{ data.items.length }}项</span>
        <el-button
          :disabled="!data?.next_cursor || loading || Boolean(error) || !canRead || !active"
          @click="next"
          >下一页</el-button
        >
      </div>
      <p v-if="loading" role="status">正在读取完整查询结果，请稍候。不会显示旧条件的数据。</p>
      <MetricRows :data="data" @detail="detail = $event" />
      <MetricRowDetails :row="detail" @close="detail = null" />
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import { cookieCsrf } from '@/api/orbit/authentication'
import {
  metricsApi,
  MetricsError,
  type FrozenMetricsRequest,
  type MetricDataset,
  type MetricQuery,
  type MetricRow,
  type Metrics,
} from '@/api/orbit/metrics'
import MetricQueryForm from './MetricQueryForm.vue'
import MetricRows from './MetricRows.vue'
import MetricRowDetails from './MetricRowDetails.vue'
const props = withDefaults(
  defineProps<{ active?: boolean; contextKey?: string; csrfToken?: string }>(),
  { active: true, contextKey: '', csrfToken: '' },
)
const user = useUserStore(),
  canRead = computed(
    () => user.permissions.includes('*:*:*') || user.permissions.includes('monitor.read'),
  )
const context = computed(() =>
  JSON.stringify([
    user.id ?? '',
    [...(user.roles ?? [])].sort(),
    [...user.permissions].sort(),
    props.contextKey,
  ]),
)
const remoteCsrf = ref(''),
  contextLoading = ref(false),
  contextError = ref<MetricsError | null>(null)
const csrf = computed(() => props.csrfToken || cookieCsrf() || remoteCsrf.value)
const contextBlocked = computed(() =>
  Boolean(contextError.value && [401, 403].includes(contextError.value.status)),
)
const tabs = [
  { name: 'overview', label: '监测与规则优化' },
  { name: 'OPERATOR', label: '投放师' },
  { name: 'CHANNEL', label: '渠道' },
  { name: 'ACCOUNT', label: '广告账户' },
  { name: 'CAMPAIGN', label: '广告系列' },
  { name: 'ADSET', label: '广告组' },
  { name: 'AD', label: '广告' },
]
const tab = ref('overview'),
  dataset = computed(() => tab.value as MetricDataset)
const data = ref<Metrics | null>(null),
  detail = ref<MetricRow | null>(null),
  loading = ref(false),
  error = ref<MetricsError | null>(null)
const history = ref<(string | null)[]>([]),
  currentCursor = ref<string | null>(null)
interface Intent {
  body: MetricQuery
  frozen: FrozenMetricsRequest
  history: (string | null)[]
  cursor: string | null
}
const pending = shallowRef<Intent | null>(null)
let epoch = 0,
  controller: AbortController | null = null
let contextEpoch = 0,
  contextController: AbortController | null = null
function stop() {
  epoch++
  controller?.abort()
  controller = null
  loading.value = false
}
function clear() {
  stop()
  data.value = null
  detail.value = null
  error.value = null
  pending.value = null
  history.value = []
  currentCursor.value = null
}
function conditionsChanged() {
  if (!error.value?.unknown_result) clear()
}
async function prepareContext(force = false) {
  contextEpoch++
  contextController?.abort()
  contextController = null
  remoteCsrf.value = ''
  contextError.value = null
  contextLoading.value = false
  if (!canRead.value || !props.active || (!force && (props.csrfToken || cookieCsrf()))) return
  const version = contextEpoch,
    identity = context.value
  contextController = new AbortController()
  const signal = contextController.signal
  contextLoading.value = true
  try {
    const value = await metricsApi.capabilities(signal)
    if (version !== contextEpoch || identity !== context.value || signal.aborted) return
    remoteCsrf.value = value.csrf_token
  } catch (caught) {
    if (version !== contextEpoch || identity !== context.value || signal.aborted) return
    clear()
    contextError.value =
      caught instanceof MetricsError
        ? caught
        : new MetricsError(0, 'NETWORK_UNAVAILABLE', '暂时无法准备查询，请重试', [], true)
  } finally {
    if (version === contextEpoch) contextLoading.value = false
  }
}
watch(
  [context, canRead, () => props.active, () => props.csrfToken],
  () => {
    clear()
    void prepareContext()
  },
  { immediate: true },
)
watch(csrf, () => clear())
watch(tab, () => clear())
onBeforeUnmount(() => {
  clear()
  contextEpoch++
  contextController?.abort()
})
async function confirmDiscard() {
  if (!error.value?.unknown_result) return true
  try {
    await ElMessageBox.confirm(
      '原指标查询结果尚未确认。离开将丢失本页内存中的恢复意图；这不会取消服务端已建立的查询快照。确认离开？',
      '保留原查询',
      { type: 'warning', confirmButtonText: '确认放弃本页恢复', cancelButtonText: '继续保留' },
    )
    return true
  } catch {
    return false
  }
}
onBeforeRouteLeave(async () => await confirmDiscard())
async function send(intent: Intent) {
  if (!canRead.value || !props.active || !csrf.value || contextBlocked.value || loading.value)
    return
  stop()
  const version = epoch,
    requestContext = context.value
  controller = new AbortController()
  const signal = controller.signal
  pending.value = structuredClone(intent)
  error.value = null
  data.value = null
  detail.value = null
  loading.value = true
  try {
    const value = await metricsApi.query(structuredClone(intent.body), { ...intent.frozen }, signal)
    if (version !== epoch || requestContext !== context.value || signal.aborted) return
    data.value = value
    history.value = [...intent.history]
    currentCursor.value = intent.cursor
  } catch (caught) {
    if (version !== epoch || requestContext !== context.value || signal.aborted) return
    error.value =
      caught instanceof MetricsError
        ? caught
        : new MetricsError(
            0,
            'NETWORK_UNAVAILABLE',
            '指标读取中断，保留原查询后重试',
            [],
            true,
            null,
            true,
          )
    if ([401, 403].includes(error.value.status)) {
      contextError.value = error.value
      data.value = null
      detail.value = null
      pending.value = null
      history.value = []
      currentCursor.value = null
      remoteCsrf.value = ''
    }
    if (error.value.status === 409) {
      history.value = []
      currentCursor.value = null
    }
  } finally {
    if (version === epoch) loading.value = false
  }
}
function query(body: MetricQuery) {
  if (error.value?.unknown_result || !csrf.value) return
  void send({
    body: structuredClone(body),
    frozen: { csrf_token: csrf.value, idempotency_key: crypto.randomUUID() },
    history: [],
    cursor: null,
  })
}
function retry() {
  if (pending.value) void send(structuredClone(pending.value))
}
async function resetQuery() {
  if (await confirmDiscard()) clear()
}
function next() {
  if (data.value?.next_cursor && pending.value) {
    const cursor = data.value.next_cursor
    void send({
      body: { ...pending.value.body, cursor },
      frozen: { csrf_token: csrf.value, idempotency_key: crypto.randomUUID() },
      history: [...history.value, currentCursor.value],
      cursor,
    })
  }
}
function previous() {
  if (history.value.length && pending.value) {
    const previousHistory = [...history.value],
      cursor = previousHistory.pop() ?? null
    void send({
      body: { ...pending.value.body, cursor },
      frozen: { csrf_token: csrf.value, idempotency_key: crypto.randomUUID() },
      history: previousHistory,
      cursor,
    })
  }
}
</script>
<style scoped>
.metrics-page {
  min-width: 0;
}
.metrics-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 16px 0;
}
.metrics-actions .el-button + .el-button {
  margin-left: 0;
}
.metrics-error {
  margin: 16px 0;
  padding: 16px;
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);
}
.metrics-error dd,
.metrics-error code {
  overflow-wrap: anywhere;
}
.metrics-error dd {
  margin: 4px 0 12px;
}
.metrics-page p {
  line-height: 1.65;
}
</style>
