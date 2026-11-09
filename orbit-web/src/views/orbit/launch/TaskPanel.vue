<template>
  <section v-show="active" class="task-panel" aria-label="任务列表">
    <h3>任务列表</h3>
    <TaskReadError v-if="readError" :error="readError" />
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
    <el-form inline class="task-tools" @submit.prevent="loadFirst">
      <el-form-item label="任务状态"
        ><el-select v-model="status" clearable aria-label="任务状态" :disabled="loading"
          ><el-option
            v-for="state in taskStates"
            :key="state"
            :label="taskStateLabels[state]"
            :value="state" /></el-select
      ></el-form-item>
      <el-form-item label="每页任务"
        ><el-select v-model="pageSize" aria-label="每页任务数量" :disabled="loading"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="`${size}个`"
            :value="size" /></el-select
      ></el-form-item>
      <el-form-item label="冻结任务拥有者UUID">
        <el-input
          v-model="operatorId"
          clearable
          aria-label="冻结任务拥有者UUID"
          placeholder="完整UUID，非执行操作人"
          :disabled="loading"
        />
      </el-form-item>
      <el-button native-type="submit" :disabled="loading">查询任务</el-button>
      <el-button :disabled="loading" @click="loadFirst">重新读取首页</el-button>
      <el-button v-if="operatorId" :disabled="loading" @click="clearOwner"
        >清除拥有者筛选</el-button
      >
    </el-form>
    <p class="task-secondary">
      按任务冻结的拥有者UUID精确筛选，不是执行操作人；留空查询当前权限范围。
    </p>
    <p v-if="applied.operator_user_id" class="task-full-text">
      已应用拥有者筛选：{{ applied.operator_user_id }}
    </p>
    <p class="task-secondary" aria-live="polite">
      {{
        dataAsOf ? `数据时刻 ${dataAsOf}（UTC）。` : ''
      }}总节点数包含全部分页；打开详情查看节点处理与核验结果。{{
        error && tasks.length ? '当前保留上次成功读取的列表。' : ''
      }}
    </p>
    <el-table v-loading="loading" :data="tasks" row-key="id" class="task-list" :aria-busy="loading">
      <el-table-column label="任务 ID" min-width="300"
        ><template #default="scope"
          ><span class="task-full-text">{{ scope.row.id }}</span></template
        ></el-table-column
      >
      <el-table-column label="状态 / 版本" min-width="160"
        ><template #default="scope"
          ><el-tag :type="taskTag(scope.row.state)">{{
            taskStateLabels[scope.row.state as TaskState]
          }}</el-tag>
          · {{ scope.row.revision }}
          <p v-if="scope.row.needs_manual_reconciliation">需要人工对账</p></template
        ></el-table-column
      >
      <el-table-column prop="node_count" label="总节点数" min-width="110" />
      <el-table-column label="拥有者 / 团队" min-width="300"
        ><template #default="scope"
          ><div class="task-full-text">
            {{ scope.row.ownership.owner_user_id }}<br />{{ scope.row.ownership.owner_team_id }}
          </div>
          <el-button link @click="filterOwner(scope.row.ownership.owner_user_id)"
            >仅查看此拥有者</el-button
          ></template
        ></el-table-column
      >
      <el-table-column prop="created_at" label="创建时间（UTC）" min-width="210" />
      <el-table-column label="操作" width="105"
        ><template #default="scope"
          ><el-button link @click="open(scope.row.id)">任务详情</el-button></template
        ></el-table-column
      >
      <template #empty
        ><span>{{
          loading
            ? '正在读取任务'
            : error
              ? '任务读取未完成，请重新读取'
              : '当前范围没有符合条件的任务'
        }}</span></template
      >
    </el-table>
    <div class="task-tools">
      <el-button :disabled="loading || historyIndex === 0 || dirty" @click="previous"
        >上一页任务</el-button
      ><el-button :disabled="loading || !nextCursor || dirty" @click="next">下一页任务</el-button
      ><span v-if="dirty" class="task-secondary">筛选已更改，请查询任务。</span>
    </div>
    <TaskDetails
      v-model="detailOpen"
      :task-id="taskId"
      :active="active"
      :context-key="contextKey"
      @revoked="revoked"
      @updated="updated"
    />
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  isTaskAbort,
  taskMessage,
  tasksApi,
  taskStateLabels,
  taskStates,
  taskTag,
  TaskApiError,
  type Task,
  type TaskPageSize,
  type TaskState,
  type TaskListQuery,
} from '@/api/orbit/tasks'
import TaskDetails from './TaskDetails.vue'
import TaskReadError from './TaskReadError.vue'
const props = withDefaults(defineProps<{ active: boolean; contextKey?: string }>(), {
  contextKey: '',
})
const tasks = ref<Task[]>([]),
  readError = ref<TaskApiError | null>(null),
  error = ref(''),
  notice = ref(''),
  loading = ref(false),
  dataAsOf = ref(''),
  nextCursor = ref<string | null>(null),
  status = ref<TaskState | ''>(''),
  pageSize = ref<TaskPageSize>(20),
  operatorId = ref(''),
  applied = ref({
    status: '' as TaskState | '',
    page_size: 20 as TaskPageSize,
    operator_user_id: '',
  }),
  history = ref<(string | null)[]>([null]),
  historyIndex = ref(0),
  taskId = ref<string | null>(null),
  detailOpen = ref(false)
const dirty = computed(
  () =>
    applied.value.status !== status.value ||
    applied.value.page_size !== pageSize.value ||
    applied.value.operator_user_id !== operatorId.value.trim().toLowerCase(),
)
let epoch = 0,
  controller: AbortController | null = null
function stop() {
  ++epoch
  controller?.abort()
  controller = null
  loading.value = false
}
function clear() {
  tasks.value = []
  nextCursor.value = null
  dataAsOf.value = ''
  detailOpen.value = false
  taskId.value = null
}
function revoked(cause: TaskApiError) {
  stop()
  clear()
  clearOwnerContext()
  error.value = taskMessage(cause)
  readError.value = cause
  // 撤权控制帧没有HTTP请求编号；原错误原样保留，完整清理说明独立展示。
  notice.value =
    cause.code === 'SCOPE_REVOKED'
      ? '当前任务读取权限已撤销，旧数据已清除。恢复权限后可重新查询。'
      : '任务读取权限已变化，旧数据已清除。恢复权限后可重新查询。'
}
async function read(cursor: string | null, index: number) {
  if (!props.active) return
  stop()
  const readEpoch = epoch
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  error.value = ''
  readError.value = null
  notice.value = ''
  const filters: TaskListQuery = {
    page_size: applied.value.page_size,
    ...(applied.value.status ? { status: applied.value.status } : {}),
    ...(applied.value.operator_user_id ? { operator_user_id: applied.value.operator_user_id } : {}),
    ...(cursor ? { cursor } : {}),
  }
  try {
    const page = await tasksApi.list(filters, signal)
    if (readEpoch !== epoch || signal.aborted || !props.active) return
    tasks.value = page.items
    dataAsOf.value = page.data_as_of
    nextCursor.value = page.next_cursor
    historyIndex.value = index
  } catch (cause) {
    if (readEpoch !== epoch || signal.aborted || isTaskAbort(cause)) return
    if (cause instanceof TaskApiError && [401, 403, 404].includes(cause.status)) revoked(cause)
    else {
      error.value = taskMessage(cause)
      readError.value = cause instanceof TaskApiError ? cause : null
      if (cause instanceof TaskApiError && [400, 409, 410].includes(cause.status)) {
        clear()
        notice.value = '任务快照或游标已变化，请重新读取首页。'
      }
    }
  } finally {
    if (readEpoch === epoch) loading.value = false
  }
}
async function loadFirst() {
  // 先废弃原游标与在途读取，再校验精确UUID；无效输入不发送查询。
  stop()
  error.value = ''
  readError.value = null
  notice.value = ''
  nextCursor.value = null
  history.value = [null]
  historyIndex.value = 0
  const owner = operatorId.value.trim().toLowerCase()
  if (owner && !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(owner)) {
    error.value = '冻结任务拥有者UUID格式无效，请输入带连字符的完整UUID。'
    return
  }
  operatorId.value = owner
  applied.value = {
    status: status.value,
    page_size: pageSize.value,
    operator_user_id: owner,
  }
  await read(null, 0)
}
function clearOwnerContext() {
  operatorId.value = ''
  applied.value.operator_user_id = ''
  history.value = [null]
  historyIndex.value = 0
}
async function next() {
  if (!nextCursor.value || dirty.value) return
  const index = historyIndex.value + 1
  history.value = history.value.slice(0, index)
  history.value.push(nextCursor.value)
  await read(nextCursor.value, index)
}
async function previous() {
  if (!historyIndex.value || dirty.value) return
  const index = historyIndex.value - 1
  await read(history.value[index], index)
}
async function filterOwner(id: string) {
  operatorId.value = id
  await loadFirst()
}
async function clearOwner() {
  operatorId.value = ''
  await loadFirst()
}
function open(id: string) {
  taskId.value = id
  detailOpen.value = true
}
function updated(task: Task) {
  const old = tasks.value.find((row) => row.id === task.id)
  if (!old || task.revision < old.revision) return
  if (old.revision !== task.revision) {
    // 详情已观察到更新版本，取消更早发出的列表读取，防止迟到结果覆盖。
    stop()
    nextCursor.value = null
    notice.value = '任务版本已更新；继续翻页前请重新读取列表。'
  }
  tasks.value = tasks.value.map((row) => (row.id === task.id ? { ...task, nodes: [] } : row))
}
let ownerContext = props.contextKey
watch(
  () => [props.active, props.contextKey] as const,
  ([active, context]) => {
    stop()
    clear()
    error.value = ''
    readError.value = null
    notice.value = ''
    if (context !== ownerContext) {
      ownerContext = context
      clearOwnerContext()
    }
    if (active) void loadFirst()
  },
  { immediate: true },
)
watch(detailOpen, (open) => {
  if (!open) taskId.value = null
})
onBeforeUnmount(stop)
</script>
<style scoped>
.task-panel {
  min-width: 0;
  width: 100%;
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
  width: 170px;
}
.task-tools :deep(.el-input) {
  min-width: 240px;
}
.task-full-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.task-secondary {
  color: var(--el-text-color-secondary);
}
.task-list {
  width: 100%;
}
@media (max-width: 600px) {
  .task-tools .el-form-item {
    width: 100%;
  }
  .task-tools :deep(.el-form-item__content),
  .task-tools :deep(.el-select) {
    width: 100%;
  }
}
</style>
