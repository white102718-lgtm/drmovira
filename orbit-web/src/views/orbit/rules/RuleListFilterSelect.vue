<template>
  <div class="rule-filter-select">
    <el-select
      :model-value="modelValue || undefined"
      :aria-label="title"
      :placeholder="`全部${title}`"
      :disabled="disabled"
      clearable
      @visible-change="opened"
      @update:model-value="choose"
    >
      <el-option
        v-if="selected && !items.some((x) => x.id === selected?.id)"
        :value="selected.id"
        :label="label(selected)"
      />
      <el-option v-for="item in items" :key="item.id" :value="item.id" :label="label(item)" />
      <template #footer>
        <span v-if="loading" role="status">正在读取候选…</span>
        <span v-else-if="!error && !items.length">当前可见规则未引用候选</span>
        <p v-if="error" role="alert">{{ error }}</p>
        <div class="candidate-actions">
          <el-button size="small" :disabled="loading" @click="restart">重新读取</el-button>
          <el-button size="small" :disabled="loading || !history.length" @click="previous"
            >上一页候选</el-button
          >
          <el-button size="small" :disabled="loading || !nextCursor" @click="next"
            >下一页候选</el-button
          >
        </div>
      </template>
    </el-select>
  </div>
</template>
<script setup lang="ts">
/** 只保留一页候选；上下文变化取消迟到读取，撤权立即清空显示资料。 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  ruleListFilterApi,
  type RuleFilterItem,
  type RuleFilterKind,
} from '@/api/orbit/rule-list-filters'
import { RuleApiError } from '@/api/orbit/rules'
const props = defineProps<{
  kind: RuleFilterKind
  modelValue: string
  contextKey: string
  disabled?: boolean
  refreshKey: number
}>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; denied: [error: RuleApiError] }>()
const title = computed(() =>
  props.kind === 'OPERATOR' ? '投放师' : props.kind === 'CHANNEL' ? '渠道' : '指标配置',
)
const items = ref<RuleFilterItem[]>([]),
  selected = ref<RuleFilterItem | null>(null)
const loading = ref(false),
  error = ref(''),
  loaded = ref(false)
const cursor = ref<string>(),
  nextCursor = ref<string | null>(null),
  history = ref<(string | undefined)[]>([])
let epoch = 0,
  controller: AbortController | undefined
const label = (item: RuleFilterItem) =>
  `${item.label ?? (props.kind === 'OPERATOR' ? '未记录投放师姓名' : props.kind === 'CHANNEL' ? '渠道ID' : '指标配置ID')} · ${item.id}`
function clear(clearSelection = false) {
  ++epoch
  controller?.abort()
  loading.value = false
  loaded.value = false
  items.value = []
  error.value = ''
  cursor.value = undefined
  nextCursor.value = null
  history.value = []
  if (clearSelection) {
    selected.value = null
    emit('update:modelValue', '')
  }
}
async function load() {
  if (props.disabled) return
  controller?.abort()
  controller = new AbortController()
  const token = ++epoch,
    context = props.contextKey
  loading.value = true
  items.value = []
  error.value = ''
  nextCursor.value = null
  try {
    const result = await ruleListFilterApi.list(props.kind, cursor.value, controller.signal)
    if (token !== epoch || context !== props.contextKey) return
    items.value = result.items
    nextCursor.value = result.next_cursor
    loaded.value = true
    const match = items.value.find((x) => x.id === props.modelValue)
    if (match) selected.value = match
  } catch (e) {
    if (token !== epoch || (e instanceof Error && e.name === 'AbortError')) return
    items.value = []
    nextCursor.value = null
    if (e instanceof RuleApiError && [401, 403, 404].includes(e.status)) {
      clear(true)
      emit('denied', e)
    }
    if (e instanceof RuleApiError && [400, 409].includes(e.status)) {
      cursor.value = undefined
      history.value = []
      loaded.value = false
    }
    error.value = e instanceof RuleApiError ? `${e.message}（${e.code}）` : '候选读取失败，请重试'
  } finally {
    if (token === epoch) loading.value = false
  }
}
function opened(value: boolean) {
  if (value && !loaded.value && !loading.value) void load()
}
function choose(value: string | undefined) {
  selected.value =
    items.value.find((x) => x.id === value) ??
    (selected.value?.id === value ? selected.value : null)
  emit('update:modelValue', value || '')
}
function restart() {
  clear()
  void load()
}
function next() {
  if (!loading.value && nextCursor.value) {
    history.value.push(cursor.value)
    cursor.value = nextCursor.value
    void load()
  }
}
function previous() {
  if (!loading.value && history.value.length) {
    cursor.value = history.value.pop()
    void load()
  }
}
watch(
  () => [props.contextKey, props.kind, props.disabled],
  () => clear(true),
)
watch(
  () => props.refreshKey,
  () => clear(),
)
watch(
  () => props.modelValue,
  (value) => {
    if (!value) selected.value = null
  },
)
onBeforeUnmount(() => clear())
</script>
<style scoped>
.rule-filter-select {
  width: 240px;
  min-width: 0;
}
.el-select {
  width: 100%;
}
.candidate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
p {
  white-space: normal;
  overflow-wrap: anywhere;
  max-width: 340px;
}
@media (max-width: 600px) {
  .rule-filter-select {
    width: 100%;
  }
}
</style>
