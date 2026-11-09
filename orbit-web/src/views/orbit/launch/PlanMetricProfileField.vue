<template>
  <div class="metric-field">
    <el-input
      :model-value="modelValue ?? ''"
      aria-label="指标配置ID（草稿可空）"
      :disabled="disabled"
      placeholder="可填写已有指标配置UUID；草稿可空"
      @update:model-value="manual"
    />
    <el-button :disabled="disabled || !canRead" @click="browse">从指标目录选择</el-button>
    <p v-if="!canRead" class="metric-note">没有指标目录读取权限；仍可填写已有UUID保存草稿。</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <el-dialog
      :model-value="open"
      title="选择广告组指标配置"
      width="min(1080px, 96vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @update:model-value="close"
    >
      <el-alert
        title="仅选择指标配置引用，不代表平台授权或执行验证。FIXTURE为隔离样本，即使verified=true也不代表真实平台验证。"
        type="warning"
        :closable="false"
      />
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <div class="metric-tools">
        <el-input
          v-model="q"
          aria-label="目录指标UUID"
          placeholder="完整指标UUID精确查询"
          :disabled="loading"
        />
        <el-button :disabled="loading" @click="query">查询指标目录</el-button>
        <el-select
          v-model="pageSize"
          aria-label="每页指标候选数量"
          :disabled="loading"
          @change="query"
        >
          <el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="`${size}条`"
            :value="size"
          />
        </el-select>
      </div>
      <p v-if="dirty" role="status">查询条件已变化，请重新查询后翻页。</p>
      <el-table
        v-if="!error"
        v-loading="loading"
        :data="rows"
        max-height="300"
        :empty-text="loading ? '正在读取指标配置' : '本次查询没有指标配置'"
      >
        <el-table-column prop="id" label="指标配置ID" min-width="290" />
        <el-table-column prop="version" label="版本" min-width="160" />
        <el-table-column label="来源" min-width="150"
          ><template #default="scope">
            {{ scope.row.source === 'FIXTURE' ? 'FIXTURE（隔离样本）' : 'META（服务端登记）' }}
          </template></el-table-column
        >
        <el-table-column label="操作" width="110"
          ><template #default="scope">
            <el-button link :disabled="loading" @click="candidate = scope.row"
              >查看并选择</el-button
            >
          </template></el-table-column
        >
      </el-table>
      <div class="metric-tools">
        <el-button
          :disabled="loading || dirty || historyIndex === 0"
          @click="page(historyIndex - 1)"
          >上一页指标</el-button
        >
        <el-button :disabled="loading || dirty || !nextCursor" @click="next">下一页指标</el-button>
        <span>第{{ historyIndex + 1 }}页 · 当前返回{{ rows.length }}项</span>
      </div>
      <p v-if="dataAsOf" class="metric-note">
        数据时刻 {{ dataAsOf }} · 权限版本{{ scopeVersion }}
      </p>
      <el-descriptions v-if="candidate" :column="1" border class="metric-detail">
        <el-descriptions-item v-for="item in details" :key="item.label" :label="item.label">
          <span class="metric-full">{{ item.value }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="close">取消指标选择</el-button>
        <el-button
          type="primary"
          :disabled="loading || dirty || !candidate || disabled || !canRead"
          @click="apply"
          >使用此指标配置</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  metricProfilesApi,
  MetricProfileError,
  type MetricProfile,
} from '@/api/orbit/metric-profiles'
const props = withDefaults(
  defineProps<{
    modelValue?: string
    disabled?: boolean
    canRead?: boolean
    /** 当前实际广告组local_id；不能把迟到候选应用到另一节点。 */
    bindingKey: string
    /** 当前真实身份/权限非敏感代次，不含Token。 */
    contextKey?: string
  }>(),
  { disabled: false, canRead: false, contextKey: '' },
)
const emit = defineEmits<{
  'update:modelValue': [value: string | undefined]
  browsing: [value: boolean]
}>()
const open = ref(false),
  loading = ref(false),
  q = ref(''),
  pageSize = ref(50)
const rows = ref<MetricProfile[]>([]),
  candidate = ref<MetricProfile>()
const history = ref<(string | null)[]>([null]),
  historyIndex = ref(0),
  nextCursor = ref<string | null>(null)
const error = ref(''),
  notice = ref(''),
  dataAsOf = ref(''),
  scopeVersion = ref<number>()
const appliedQuery = ref('')
const dirty = computed(
  () => appliedQuery.value !== JSON.stringify([q.value.trim(), pageSize.value]),
)
let epoch = 0,
  controller: AbortController | undefined,
  openedBinding = '',
  openedContext = ''
const details = computed(() => {
  const value = candidate.value
  if (!value) return []
  const nullable = (item: string | null) => (item === null ? '未知（null）' : item)
  return [
    { label: '指标配置ID', value: value.id },
    { label: '版本', value: value.version },
    {
      label: '来源',
      value:
        value.source === 'FIXTURE' ? 'FIXTURE（隔离样本，非真实平台验证）' : 'META（服务端登记）',
    },
    { label: '注册事件', value: nullable(value.register_action_type) },
    { label: '购物事件', value: nullable(value.purchase_action_type) },
    { label: '价值事件', value: nullable(value.value_action_type) },
    { label: '归因窗口', value: value.attribution_windows.join('、') },
    { label: '动作报告时间', value: value.action_report_time },
    { label: '时区策略', value: value.timezone_policy },
    { label: '分解口径', value: value.breakdown },
    { label: '成熟期（账户当地日）', value: String(value.maturity_days) },
    { label: '登记verified值', value: String(value.verified) },
  ]
})
function abort() {
  epoch++
  controller?.abort()
  controller = undefined
  loading.value = false
}
function clear() {
  rows.value = []
  candidate.value = undefined
  history.value = [null]
  historyIndex.value = 0
  nextCursor.value = null
  dataAsOf.value = ''
  scopeVersion.value = undefined
  error.value = ''
}
function close() {
  abort()
  open.value = false
  clear()
}
function manual(value: string | number) {
  if (!props.disabled) emit('update:modelValue', String(value) === '' ? undefined : String(value))
}
function browse() {
  if (props.disabled || !props.canRead) return
  notice.value = ''
  openedBinding = props.bindingKey
  openedContext = props.contextKey
  q.value = ''
  clear()
  open.value = true
  void query()
}
async function query() {
  history.value = [null]
  historyIndex.value = 0
  await load(null, 0)
}
async function page(index: number) {
  await load(history.value[index] ?? null, index)
}
async function next() {
  if (!nextCursor.value || dirty.value) return
  const index = historyIndex.value + 1
  history.value = [...history.value.slice(0, index), nextCursor.value]
  await load(nextCursor.value, index)
}
async function load(cursor: string | null, index: number) {
  if (!open.value || !props.canRead || props.disabled) return
  abort()
  const current = epoch,
    binding = props.bindingKey,
    context = props.contextKey
  const signal = (controller = new AbortController()).signal
  const sentQuery = {
    q: q.value.trim(),
    metric_profile_id: null,
    cursor,
    page_size: pageSize.value,
  }
  loading.value = true
  error.value = ''
  candidate.value = undefined
  try {
    const response = await metricProfilesApi.list(sentQuery, signal)
    if (
      current !== epoch ||
      !open.value ||
      signal.aborted ||
      binding !== props.bindingKey ||
      context !== props.contextKey
    )
      return
    rows.value = response.items
    nextCursor.value = response.next_cursor
    historyIndex.value = index
    dataAsOf.value = response.data_as_of
    scopeVersion.value = response.scope_version
    appliedQuery.value = JSON.stringify([sentQuery.q, sentQuery.page_size])
  } catch (cause) {
    if (current !== epoch || signal.aborted) return
    rows.value = []
    nextCursor.value = null
    if (cause instanceof MetricProfileError && cause.status === 409) {
      history.value = [null]
      historyIndex.value = 0
      error.value = '指标目录或权限版本已变化，请重新查询首页；原UUID保留。'
    } else if (cause instanceof MetricProfileError && [401, 403].includes(cause.status)) {
      error.value = '当前身份无权读取指标目录；这不是空目录。原UUID保留，可手填已有ID保存草稿。'
    } else
      error.value =
        cause instanceof Error
          ? `指标目录读取失败：${cause.message}`
          : '指标目录暂不可用，请重新查询；原UUID保留。'
  } finally {
    if (current === epoch) loading.value = false
  }
}
function apply() {
  if (
    !open.value ||
    props.disabled ||
    !props.canRead ||
    loading.value ||
    dirty.value ||
    props.bindingKey !== openedBinding ||
    props.contextKey !== openedContext ||
    !candidate.value
  )
    return
  emit('update:modelValue', candidate.value.id)
  close()
}
watch(open, (value) => emit('browsing', value), { flush: 'sync' })
watch(
  () => [props.bindingKey, props.contextKey, props.canRead, props.disabled],
  () => {
    if (open.value) {
      notice.value = '节点、身份权限或编辑状态已变化，指标选择已取消；原UUID保留。'
      close()
    }
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  abort()
  emit('browsing', false)
})
</script>

<style scoped>
.metric-field {
  width: 100%;
  min-width: 0;
}
.metric-field > .el-button {
  margin-top: 8px;
}
.metric-note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.metric-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}
.metric-tools .el-input {
  width: min(460px, 100%);
}
.metric-tools .el-select {
  width: 110px;
}
.metric-full {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-all;
}
.metric-detail {
  margin-top: 12px;
}
</style>
