<template>
  <el-drawer
    :model-value="modelValue && active"
    title="任务详情"
    size="min(1100px, 100vw)"
    append-to-body
    destroy-on-close
    @close="close"
  >
    <div v-loading="loading" class="task-detail" :aria-busy="loading">
      <TaskReadError v-if="readError" :error="readError" />
      <el-alert v-else-if="error" :title="error" type="error" :closable="false" />
      <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
      <el-alert v-if="observerNotice" :title="observerNotice" type="info" :closable="false" />
      <div class="task-tools">
        <el-button :disabled="loading || !active" @click="manualRefresh">重新读取任务</el-button
        ><span class="task-secondary" role="status" aria-label="任务观察状态">{{
          observerLabel
        }}</span>
      </div>
      <template v-if="task">
        <el-alert
          v-if="task.needs_manual_reconciliation"
          title="该任务需要人工对账。本页仅提供结果查询。"
          type="warning"
          :closable="false"
        />
        <el-descriptions :column="1" border>
          <el-descriptions-item label="任务 ID"
            ><span class="task-full-text">{{ task.id }}</span></el-descriptions-item
          >
          <el-descriptions-item label="任务状态"
            ><el-tag :type="taskTag(task.state)">{{
              taskStateLabels[task.state]
            }}</el-tag></el-descriptions-item
          >
          <el-descriptions-item label="任务版本 / 总节点数"
            >{{ task.revision }} / {{ task.node_count }}</el-descriptions-item
          >
          <el-descriptions-item label="拥有者 / 团队"
            ><span class="task-full-text"
              >{{ task.ownership.owner_user_id }}<br />{{ task.ownership.owner_team_id }}</span
            ></el-descriptions-item
          >
          <el-descriptions-item label="创建时间（UTC）">{{ task.created_at }}</el-descriptions-item>
          <el-descriptions-item label="执行通道">{{
            task.execution_mode ? executionLabels[task.execution_mode] : '未提供'
          }}</el-descriptions-item>
          <el-descriptions-item label="最近事件 ID"
            ><span class="task-full-text">{{
              task.latest_event_id ?? '暂无事件'
            }}</span></el-descriptions-item
          >
          <el-descriptions-item label="需要人工对账">{{
            task.needs_manual_reconciliation ? '是' : '否'
          }}</el-descriptions-item>
        </el-descriptions>
        <TaskEventLog
          :events="observedEvents"
          :dropped="droppedEvents"
          :segment="eventSegment"
          :segment-notice="eventSegmentNotice"
        />
        <h3>任务节点</h3>
        <el-form inline class="task-tools" @submit.prevent="filterNodes">
          <el-form-item label="节点键前缀"
            ><el-input v-model="prefix" clearable aria-label="节点键前缀" :disabled="loading"
          /></el-form-item>
          <el-form-item label="节点状态"
            ><el-select v-model="status" clearable aria-label="节点状态" :disabled="loading"
              ><el-option
                v-for="state in nodeStates"
                :key="state"
                :label="taskStateLabels[state]"
                :value="state" /></el-select
          ></el-form-item>
          <el-form-item label="分页大小"
            ><el-select
              v-model="pageSize"
              aria-label="节点分页大小"
              :disabled="loading"
              @change="filterNodes"
              ><el-option
                v-for="size in [20, 50, 100, 200]"
                :key="size"
                :label="`${size}个`"
                :value="size" /></el-select
          ></el-form-item>
          <el-button native-type="submit" :disabled="loading">查询节点</el-button>
        </el-form>
        <p class="task-secondary" aria-live="polite">
          {{
            source === 'detail'
              ? `详情展示前${nodes.length}个节点，后续按每页${pageSize}个读取。`
              : `本页${nodes.length}个节点。`
          }}
          总节点数 {{ task.node_count }}，不是本页行数。{{
            nodeAsOf ? `数据时刻 ${nodeAsOf}（UTC）。` : ''
          }}
        </p>
        <el-table :data="nodes" row-key="id" class="task-node-table">
          <el-table-column label="节点类型 / 键" min-width="260"
            ><template #default="scope"
              ><div>{{ nodeKindLabels[scope.row.kind as TaskNode['kind']] }}</div>
              <span class="task-full-text">{{ scope.row.node_key }}</span></template
            ></el-table-column
          >
          <el-table-column label="处理状态" min-width="135"
            ><template #default="scope"
              ><el-tag :type="taskTag(scope.row.state)">{{
                taskStateLabels[scope.row.state as TaskNodeState]
              }}</el-tag></template
            ></el-table-column
          >
          <el-table-column label="配置 / 投放" min-width="160"
            ><template #default="scope"
              >{{
                configurationLabels[
                  scope.row.configuration_state as keyof typeof configurationLabels
                ]
              }}
              /
              {{
                deliveryLabels[scope.row.delivery_state as keyof typeof deliveryLabels]
              }}</template
            ></el-table-column
          >
          <el-table-column label="尝试 / 父节点" min-width="115"
            ><template #default="scope"
              >{{ scope.row.attempt }} / {{ scope.row.parent_ids.length }}</template
            ></el-table-column
          >
          <el-table-column label="操作" width="90"
            ><template #default="scope"
              ><el-button link @click="selectedNode = scope.row">节点详情</el-button></template
            ></el-table-column
          >
          <template #empty
            ><span>{{
              loading ? '正在读取节点' : error ? '读取未完成，请重新读取' : '没有符合条件的节点'
            }}</span></template
          >
        </el-table>
        <div class="task-tools">
          <el-button :disabled="loading" @click="filterNodes">节点首页</el-button
          ><el-button :disabled="loading || historyIndex === 0 || dirty" @click="previous"
            >上一段节点</el-button
          ><el-button :disabled="loading || !nextCursor || dirty" @click="next"
            >下一段节点</el-button
          ><span v-if="dirty" class="task-secondary">筛选已更改，请查询节点。</span>
        </div>
      </template>
    </div>
    <TaskNodeDetails
      :node="selectedNode"
      :visible-node-ids="nodes.map((node) => node.id)"
      @close="selectedNode = null"
    />
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  configurationLabels,
  deliveryLabels,
  executionLabels,
  isTaskAbort,
  nodeKindLabels,
  nodeStates,
  taskMessage,
  tasksApi,
  taskStateLabels,
  taskTag,
  TaskApiError,
  type Task,
  type TaskNode,
  type TaskNodeQuery,
  type TaskNodeState,
  type TaskPageSize,
} from '@/api/orbit/tasks'
import TaskNodeDetails from './TaskNodeDetails.vue'
import TaskReadError from './TaskReadError.vue'
import TaskEventLog from './TaskEventLog.vue'
import {
  observeTaskEvents,
  TaskEventError,
  type TaskObserverState,
  type TaskEvent,
} from '@/api/orbit/task-events'
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    taskId: string | null
    active: boolean
    contextKey?: string
  }>(),
  { contextKey: '' },
)
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  revoked: [error: TaskApiError]
  updated: [task: Task]
}>()
const task = ref<Task | null>(null),
  nodes = ref<TaskNode[]>([]),
  selectedNode = ref<TaskNode | null>(null),
  error = ref(''),
  readError = ref<TaskApiError | TaskEventError | null>(null),
  notice = ref(''),
  loading = ref(false),
  nextCursor = ref<string | null>(null),
  nodeAsOf = ref(''),
  prefix = ref(''),
  status = ref<TaskNodeState | ''>(''),
  pageSize = ref<TaskPageSize>(50),
  source = ref<'detail' | 'nodes'>('detail'),
  history = ref<(string | null)[]>([null]),
  historyIndex = ref(0),
  applied = ref({ q: '', status: '' as TaskNodeState | '', page_size: 50 as TaskPageSize })
const visible = ref(document.visibilityState !== 'hidden'),
  denied = ref(false)
const origin = ref<'detail' | 'nodes'>('detail')
const observerState = ref<TaskObserverState>('stopped'),
  observerNotice = ref('')
const observedEvents = ref<TaskEvent[]>([]),
  droppedEvents = ref(0),
  eventSegment = ref(0),
  eventSegmentNotice = ref('记录从当前快照之后开始，不包含快照之前的历史事件。')
function clearObservedEvents(notice = '记录从当前快照之后开始，不包含快照之前的历史事件。') {
  observedEvents.value = []
  droppedEvents.value = 0
  ++eventSegment.value
  eventSegmentNotice.value = notice
}
const observerLabel = computed(
  () =>
    ({
      snapshot: '正在读取任务快照',
      connecting: '正在连接任务更新',
      live: '任务更新已连接',
      reconnecting: '连接中断，正在重连；每10秒读取最新结果',
      resynchronizing: '正在重新读取快照',
      revoked: '读取权限已撤销',
      failed: '实时更新已暂停，可重新读取；每10秒读取最新结果',
      stopped: '自动查询已暂停',
    })[observerState.value],
)
const polling = computed(
  () => props.modelValue && props.active && visible.value && !denied.value && Boolean(task.value),
)
const dirty = computed(
  () =>
    prefix.value.normalize('NFC').trim() !== applied.value.q ||
    status.value !== applied.value.status ||
    pageSize.value !== applied.value.page_size,
)
let epoch = 0,
  controller: AbortController | null = null,
  timer: ReturnType<typeof setTimeout> | undefined
let observationEpoch = 0,
  observer: ReturnType<typeof observeTaskEvents> | undefined
let eventTimer: ReturnType<typeof setTimeout> | undefined,
  pendingEvent = false
function stop() {
  ++epoch
  controller?.abort()
  controller = null
  if (timer) clearTimeout(timer)
  timer = undefined
  loading.value = false
}
function suspend() {
  ++observationEpoch
  observer?.stop()
  observer = undefined
  if (eventTimer) clearTimeout(eventTimer)
  eventTimer = undefined
  pendingEvent = false
  observerState.value = 'stopped'
  stop()
  clearObservedEvents('观察已暂停；恢复后从新快照开始记录，不拼接缺失历史。')
}
function eventRefresh() {
  if (!pendingEvent || loading.value || !polling.value || eventTimer) return
  const number = observationEpoch
  eventTimer = setTimeout(() => {
    eventTimer = undefined
    if (number !== observationEpoch || !pendingEvent || loading.value || !polling.value) return
    pendingEvent = false
    void refresh(true)
  }, 1000)
}
function startObservation() {
  if (!props.taskId || !props.modelValue || !props.active || !visible.value) return
  suspend()
  const number = observationEpoch,
    id = props.taskId
  const valid = () =>
    number === observationEpoch &&
    id === props.taskId &&
    props.modelValue &&
    props.active &&
    visible.value
  denied.value = false
  error.value = ''
  readError.value = null
  observerNotice.value = ''
  observer = observeTaskEvents({
    taskId: id,
    onSnapshot: (snapshot) => {
      if (!valid()) return
      clearObservedEvents(
        observerState.value === 'resynchronizing'
          ? '已重新取得快照，以下为新订阅段；缺失事件未恢复，旧观察记录已清除。'
          : '记录从当前快照之后开始，不包含快照之前的历史事件。',
      )
      pendingEvent = false
      if (eventTimer) clearTimeout(eventTimer)
      eventTimer = undefined
      if (observerState.value === 'resynchronizing')
        observerNotice.value = '任务更新已重新取得快照，节点已回到当前条件的首页。'
      void refresh(false, false, snapshot.task)
    },
    onEvent: (event) => {
      if (valid()) {
        // 仅接收observer已通过UUID/序号/schema校验的记录；保留完整九字段且内存有界。
        if (observedEvents.value.length === 200) ++droppedEvents.value
        observedEvents.value = [...observedEvents.value.slice(-199), event]
        pendingEvent = true
        eventRefresh()
      }
    },
    onState: (state, cause) => {
      if (!valid()) return
      observerState.value = state
      if (timer) clearTimeout(timer)
      timer = undefined
      if (state === 'snapshot' || state === 'resynchronizing') {
        clearObservedEvents(
          state === 'resynchronizing'
            ? '事件连接出现缺口，正在重新取得快照；旧观察记录已清除。'
            : '正在读取新快照，旧观察记录已清除。',
        )
        stop()
        loading.value = true
      }
      if (state === 'failed') {
        observerNotice.value = cause?.message ?? '实时更新暂不可用，可重新读取任务。'
      }
      if (cause && ['failed', 'reconnecting', 'revoked'].includes(state)) {
        readError.value = cause
        if (state === 'revoked') failed(cause)
      }
      if (state === 'live') readError.value = null
      if (['failed', 'reconnecting'].includes(state) && !controller) loading.value = false
      if (state === 'reconnecting' || state === 'failed') schedule()
    },
    onRevoked: () => {
      if (!valid()) return
      suspend()
      observerState.value = 'revoked'
      failed(new TaskApiError(403, 'SCOPE_REVOKED', '当前任务读取权限已撤销，旧数据已清除。'))
    },
  })
  void observer.done.catch((cause) => {
    if (!valid() || isTaskAbort(cause)) return
    observerState.value = 'failed'
    if (!controller) loading.value = false
    observerNotice.value = taskMessage(cause)
    readError.value = cause instanceof TaskEventError ? cause : null
    schedule()
  })
}
function manualRefresh() {
  startObservation()
}
function reset() {
  task.value = null
  nodes.value = []
  selectedNode.value = null
  nextCursor.value = null
  nodeAsOf.value = ''
  history.value = [null]
  historyIndex.value = 0
  error.value = ''
  readError.value = null
  notice.value = ''
  observerNotice.value = ''
  source.value = 'detail'
}
function start() {
  stop()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  readError.value = null
  return { id: props.taskId!, number: epoch, signal: controller.signal }
}
function current(read: ReturnType<typeof start>) {
  return (
    read.number === epoch &&
    read.id === props.taskId &&
    props.modelValue &&
    props.active &&
    !read.signal.aborted
  )
}
function failed(cause: unknown) {
  if (isTaskAbort(cause)) return
  error.value = taskMessage(cause)
  readError.value = cause instanceof TaskApiError || cause instanceof TaskEventError ? cause : null
  if (
    (cause instanceof TaskApiError || cause instanceof TaskEventError) &&
    [401, 403, 404].includes(cause.status)
  ) {
    suspend()
    observerState.value = 'revoked'
    task.value = null
    nodes.value = []
    selectedNode.value = null
    nextCursor.value = null
    denied.value = true
    if (cause.status !== 404) emit('revoked', cause)
  } else if (cause instanceof TaskApiError && cause.status === 409) {
    nodes.value = []
    selectedNode.value = null
    nextCursor.value = null
    notice.value = '任务或权限快照已变化，请重新读取任务或节点首页。'
  }
}
function schedule() {
  if (timer) clearTimeout(timer)
  if (polling.value && ['reconnecting', 'failed'].includes(observerState.value))
    timer = setTimeout(() => {
      timer = undefined
      if (!loading.value) void refresh(true)
      else schedule()
    }, 10000)
}
async function refresh(poll: boolean, forceNodes = false, snapshot?: Task) {
  if (!props.modelValue || !props.taskId || !props.active || !visible.value) return
  const read = start()
  try {
    const fresh = snapshot ?? (await tasksApi.get(read.id, read.signal))
    if (!current(read)) return
    const changed = task.value !== null && task.value.revision !== fresh.revision
    const keepPage = poll && !changed && task.value !== null
    task.value = fresh
    denied.value = false
    emit('updated', fresh)
    if (!keepPage) {
      selectedNode.value = null
      nodes.value = []
      nextCursor.value = null
      history.value = [null]
      historyIndex.value = 0
      if (forceNodes || applied.value.q || applied.value.status || applied.value.page_size !== 50) {
        const page = await tasksApi.nodes(read.id, nodeQuery(null), read.signal)
        if (!current(read)) return
        nodes.value = page.items
        nextCursor.value = page.next_cursor
        nodeAsOf.value = page.data_as_of
        source.value = 'nodes'
        origin.value = 'nodes'
      } else {
        nodes.value = fresh.nodes
        nextCursor.value = fresh.next_node_cursor
        nodeAsOf.value = ''
        source.value = 'detail'
        origin.value = 'detail'
      }
      notice.value = changed ? '任务版本已变化，已重新读取首段节点。' : ''
    }
  } catch (cause) {
    if (current(read)) failed(cause)
  } finally {
    if (current(read)) {
      loading.value = false
      controller = null
      schedule()
      eventRefresh()
    }
  }
}
function nodeQuery(cursor: string | null): TaskNodeQuery {
  return {
    page_size: applied.value.page_size,
    ...(applied.value.q ? { q: applied.value.q } : {}),
    ...(applied.value.status ? { status: applied.value.status } : {}),
    ...(cursor ? { cursor } : {}),
  }
}
async function readNodes(cursor: string | null, index: number) {
  if (!props.taskId || !props.modelValue || !props.active || !visible.value) return
  const read = start()
  try {
    const page = await tasksApi.nodes(read.id, nodeQuery(cursor), read.signal)
    if (!current(read)) return
    nodes.value = page.items
    selectedNode.value = null
    nextCursor.value = page.next_cursor
    nodeAsOf.value = page.data_as_of
    historyIndex.value = index
    source.value = 'nodes'
    notice.value = ''
  } catch (cause) {
    if (current(read)) failed(cause)
  } finally {
    if (current(read)) {
      loading.value = false
      controller = null
      schedule()
      eventRefresh()
    }
  }
}
async function filterNodes() {
  if ([...prefix.value.normalize('NFC').trim()].length > 100) {
    stop()
    error.value = '节点键前缀最多100个码点'
    readError.value = null
    return
  }
  applied.value = {
    q: prefix.value.normalize('NFC').trim(),
    status: status.value,
    page_size: pageSize.value,
  }
  origin.value = 'nodes'
  nodes.value = []
  selectedNode.value = null
  nextCursor.value = null
  history.value = [null]
  historyIndex.value = 0
  // 无游标查询之前同步当前任务元数据，不能把新节点配到旧版本任务标题上。
  await refresh(false, true)
}
async function next() {
  if (!nextCursor.value || dirty.value) return
  const index = historyIndex.value + 1
  history.value = history.value.slice(0, index)
  history.value.push(nextCursor.value)
  await readNodes(nextCursor.value, index)
}
async function previous() {
  if (!historyIndex.value || dirty.value) return
  const index = historyIndex.value - 1
  if (index === 0) await refresh(false, origin.value === 'nodes')
  else await readNodes(history.value[index], index)
}
function close() {
  suspend()
  reset()
  emit('update:modelValue', false)
}
function visibility() {
  visible.value = document.visibilityState !== 'hidden'
  if (!visible.value) suspend()
  else if (props.modelValue && props.active) startObservation()
}
document.addEventListener('visibilitychange', visibility)
let viewedId: string | null = null,
  viewedContext = props.contextKey
watch(
  () => [props.taskId, props.modelValue, props.active, props.contextKey] as const,
  ([id, open, active, context]) => {
    suspend()
    readError.value = null
    error.value = ''
    if (id !== viewedId || context !== viewedContext) {
      viewedContext = context
      viewedId = id
      reset()
      denied.value = false
      prefix.value = ''
      status.value = ''
      pageSize.value = 50
      applied.value = { q: '', status: '', page_size: 50 }
    }
    if (id && open && active && visible.value) startObservation()
    else if (!open) reset()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  suspend()
  document.removeEventListener('visibilitychange', visibility)
})
</script>
<style scoped>
.task-detail {
  min-width: 0;
}
.task-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin: 14px 0;
}
.task-tools .el-form-item {
  margin: 0;
}
.task-tools :deep(.el-select) {
  width: 160px;
}
.task-tools :deep(.el-input) {
  width: min(280px, 100%);
}
.task-full-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.task-secondary {
  color: var(--el-text-color-secondary);
}
.task-node-table {
  width: 100%;
}
@media (max-width: 600px) {
  .task-tools {
    align-items: stretch;
  }
  .task-tools .el-form-item {
    width: 100%;
  }
  .task-tools :deep(.el-form-item__content),
  .task-tools :deep(.el-input),
  .task-tools :deep(.el-select) {
    width: 100%;
  }
}
</style>
