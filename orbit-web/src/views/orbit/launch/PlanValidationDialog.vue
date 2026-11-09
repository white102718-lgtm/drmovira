<template>
  <el-dialog
    :model-value="modelValue"
    title="投放预检与展开结果"
    width="min(1120px, 100vw)"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!locked"
    :before-close="beforeClose"
  >
    <el-alert v-if="dependencyReason" :title="dependencyReason" type="warning" :closable="false" />
    <el-alert
      v-if="validationAvailable && !executeAvailable"
      title="执行依赖尚未就绪；可查看预检结果，当前不会提交任务。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="notice" :title="notice" type="info" :closable="false" />
    <el-alert
      v-if="uncertain"
      title="原请求结果尚未确认；本次请求已保留，只能重试原意图，确认前不能关闭或重新分配。"
      type="warning"
      :closable="false"
    />
    <p role="status" aria-label="预检处理阶段">{{ stage }}</p>
    <p>
      计划 {{ plan.name || '未命名草稿' }} · 已保存版本
      {{ plan.revision }}。预检和任务受理均不代表平台创建成功。
    </p>
    <template v-if="currentView">
      <el-descriptions v-if="reservation || allocation" :column="1" border>
        <el-descriptions-item v-if="reservation" label="冻结命名"
          ><span class="full"
            >{{ reservation.id }} · {{ reservation.naming_date }} · 配置版本
            {{ reservation.plan_revision }}</span
          ></el-descriptions-item
        >
        <el-descriptions-item v-if="allocation" label="分配状态"
          ><span class="full"
            >{{ allocation.id }} · {{ allocation.state }} · seed {{ allocation.seed }}</span
          ></el-descriptions-item
        >
      </el-descriptions>
      <p v-if="allocation && ['QUEUED', 'RUNNING'].includes(allocation.state)">
        分配仍在服务端处理；停止等待不会取消服务端任务。分配任务引用：{{
          allocation.task_id ?? '无独立任务引用'
        }}。
      </p>
      <el-alert
        v-for="(warning, index) in allocation?.warnings ?? []"
        :key="index"
        :title="warning"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="previousAllocation && allocation?.id !== previousAllocation.id"
        title="重新分配尚未确认完整结果，原分配不会因本地取消确认而被删除；服务端完成新发布后旧映射可能失效。"
        type="info"
        :closable="false"
      />
      <div class="actions">
        <el-button v-if="waiting" @click="stopWaiting">停止等待分配</el-button
        ><el-button
          v-else-if="allocation && ['QUEUED', 'RUNNING'].includes(allocation.state)"
          :disabled="running || locked"
          @click="continueWaiting"
          >继续读取分配</el-button
        ><el-button
          v-if="allocation"
          :disabled="running || locked || Boolean(dependencyReason)"
          @click="reallocate"
          >重新分配（需确认）</el-button
        ><el-button
          v-if="allocation?.state === 'SUCCEEDED' && reservation"
          @click="previewOpen = true"
          >查看全部冻结展开</el-button
        >
      </div>
      <template v-if="validation">
        <h3>服务端预检结果</h3>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="是否有效">{{
            validation.valid ? '预检通过' : '预检未通过'
          }}</el-descriptions-item>
          <el-descriptions-item label="预检摘要"
            ><span class="full">{{ validation.hash ?? '无有效摘要' }}</span></el-descriptions-item
          >
          <el-descriptions-item label="有效期（UTC）">{{
            validation.expires_at ?? '无有效期'
          }}</el-descriptions-item>
          <el-descriptions-item label="系列 / 广告组 / 广告数量"
            >{{ validation.campaign_count }} / {{ validation.adset_count }} /
            {{ validation.ad_count }}</el-descriptions-item
          >
          <el-descriptions-item label="全部DAG节点数">{{
            validation.total_dag_node_count
          }}</el-descriptions-item>
          <el-descriptions-item label="范围版本">{{
            validation.scope_version
          }}</el-descriptions-item>
          <el-descriptions-item label="字段错误数">{{
            validation.errors.length
          }}</el-descriptions-item>
        </el-descriptions>
        <h3>预算汇总（按币种独立）</h3>
        <el-table :data="validation.budget_totals" class="budget-totals"
          ><el-table-column prop="currency" label="币种" /><el-table-column
            prop="amount"
            label="原始十进制金额"
        /></el-table>
        <p v-if="!validation.budget_totals.length">服务端未返回预算汇总。</p>
        <p v-if="headReady">
          已重新读取当前状态版本 {{ head.revision }}，执行将使用此版本，不推算预检后版本。
        </p>
        <el-button
          v-else-if="validation.valid"
          :disabled="running || locked || Boolean(dependencyReason)"
          @click="flow"
          >重新读取计划版本</el-button
        >
      </template>
    </template>
    <template v-if="allErrors.length"
      ><h3>全部字段错误（{{ allErrors.length }}）</h3>
      <el-table :data="errorRows" class="validation-errors"
        ><el-table-column label="JSON Pointer路径" min-width="250"
          ><template #default="{ row }"
            ><span class="full">{{ row.path }}</span
            ><el-button link :disabled="!pointer(row.path)" @click="locate(row.path)"
              >定位字段</el-button
            ></template
          ></el-table-column
        ><el-table-column prop="code" label="错误码" min-width="180" /><el-table-column
          prop="message"
          label="说明"
          min-width="260"
        /><el-table-column label="约束" min-width="180"
          ><template #default="{ row }"
            ><span class="full">{{ row.constraint ?? '未提供约束说明' }}</span></template
          ></el-table-column
        ></el-table
      >
      <div class="actions">
        <el-button :disabled="errorPage === 1" @click="errorPage--">上一页错误</el-button
        ><span>第 {{ errorPage }} / {{ errorPages }} 页</span
        ><el-button :disabled="errorPage >= errorPages" @click="errorPage++">下一页错误</el-button
        ><el-button :disabled="errorPage >= errorPages" @click="errorPage = errorPages"
          >末页错误</el-button
        >
      </div></template
    >
    <template #footer
      ><div class="actions">
        <el-button :disabled="locked" @click="close">关闭预检</el-button
        ><el-button
          v-if="pending && uncertain"
          :disabled="pending.context !== context || writeBusy"
          :loading="writeBusy"
          type="warning"
          @click="retry"
          >重试原预检请求</el-button
        ><el-button
          v-else
          :disabled="Boolean(dependencyReason) || running || locked || accepted"
          :loading="running"
          @click="begin"
          >{{ validation ? '重新预检' : '开始预检' }}</el-button
        ><el-button
          type="primary"
          :disabled="!canExecute || running || locked"
          @click="confirmOpen = true"
          >查看提交确认</el-button
        >
      </div></template
    >
    <PlanExpansionPreview
      v-if="currentView && allocation && reservation"
      v-model="previewOpen"
      :allocation="allocation"
      :reservation="reservation"
      :asset-ids="plan.asset_ids"
    />
    <PlanExecuteConfirm
      v-if="(currentView || executeLocked) && validation && allocation && reservation && headReady"
      v-model="confirmOpen"
      :plan="head"
      :capabilities="capabilities"
      :validation="validation"
      :allocation="allocation"
      :reservation="reservation"
      :available="executeAvailable"
      :context-version="context"
      @locked="executeLocked = $event"
      @accepted="taskAccepted"
    />
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { launchApi, type LaunchCapabilities, type LaunchPlan } from '@/api/orbit/launch'
import {
  launchValidationApi,
  LaunchValidationError,
  type Allocation,
  type AllocationRequest,
  type FrozenMutation,
  type NameReservation,
  type PlanHttpFieldError,
  type PlanValidation,
  type ValidatePlan,
} from '@/api/orbit/launch-validation'
import type { Task } from '@/api/orbit/tasks'
import PlanExpansionPreview from './PlanExpansionPreview.vue'
import PlanExecuteConfirm from './PlanExecuteConfirm.vue'
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    plan: LaunchPlan
    capabilities: LaunchCapabilities
    validationAvailable?: boolean
    executeAvailable?: boolean
  }>(),
  { validationAvailable: false, executeAvailable: false },
)
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  locked: [value: boolean]
  locate: [path: string, segments: string[]]
  accepted: [task: Task]
}>()
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const context = computed(() =>
  JSON.stringify([
    props.plan,
    props.capabilities,
    props.validationAvailable,
    props.executeAvailable,
  ]),
)
const preparedContext = ref(''),
  currentView = computed(() => preparedContext.value === context.value)
const head = ref<LaunchPlan>(copy(props.plan)),
  reservation = ref<NameReservation | null>(null),
  allocation = ref<Allocation | null>(null),
  previousAllocation = ref<Allocation | null>(null),
  validation = ref<PlanValidation | null>(null)
const error = ref(''),
  notice = ref(''),
  stage = ref('尚未开始预检'),
  running = ref(false),
  writeBusy = ref(false),
  waiting = ref(false),
  uncertain = ref(false),
  denied = ref(false),
  headReady = ref(false),
  accepted = ref(false),
  executeLocked = ref(false),
  previewOpen = ref(false),
  confirmOpen = ref(false),
  seed = ref(0),
  now = ref(Date.now()),
  httpErrors = ref<PlanHttpFieldError[]>([]),
  errorPage = ref(1)
type Pending = {
  kind: 'names' | 'allocation' | 'validate'
  context: string
  planId: string
  mutation: FrozenMutation
  body?: AllocationRequest | ValidatePlan
}
// 未知结果仅保留在组件内存中；父调用方必须遵守locked，不能强制卸载或另开新意图。
const pending = ref<Pending | null>(null),
  locked = computed(() => writeBusy.value || uncertain.value || executeLocked.value)
let generation = 0,
  readController: AbortController | null = null,
  clock: ReturnType<typeof setInterval> | undefined,
  alive = true
const day = () =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(now.value))
const dependencyReason = computed(() => {
  if (!props.validationAvailable) return '预检依赖尚未就绪，不会发起命名、分配或预检请求。'
  if (denied.value || !props.capabilities.actions.includes('edit'))
    return '当前账号没有可用的计划编辑及预检权限。'
  if (
    !props.capabilities.csrf_token ||
    !props.plan.id ||
    !Number.isSafeInteger(props.plan.revision)
  )
    return '尚未取得已保存计划和有效写入上下文。'
  if (!['DRAFT', 'VALIDATED'].includes(props.plan.state))
    return '计划状态不允许新预检，请读取已提交任务。'
  if (
    !props.plan.account_ids.length ||
    !props.plan.asset_ids.length ||
    !props.plan.campaigns.length
  )
    return '请先保存包含账户、配置树和素材池的计划。'
  return ''
})
const validTime = computed(
  () =>
    validation.value?.expires_at &&
    Number.isFinite(Date.parse(validation.value.expires_at)) &&
    Date.parse(validation.value.expires_at) > now.value,
)
const canExecute = computed(
  () =>
    currentView.value &&
    props.executeAvailable &&
    props.capabilities.actions.includes('execute') &&
    !accepted.value &&
    headReady.value &&
    ['DRAFT', 'VALIDATED'].includes(head.value.state) &&
    validation.value?.valid &&
    validation.value.errors.length === 0 &&
    /^[a-f\d]{64}$/.test(validation.value.hash ?? '') &&
    validTime.value &&
    reservation.value?.naming_date === day() &&
    allocation.value?.state === 'SUCCEEDED',
)
const allErrors = computed(() =>
  currentView.value ? [...(validation.value?.errors ?? []), ...httpErrors.value] : [],
)
const errorRows = computed(() =>
    allErrors.value.slice((errorPage.value - 1) * 50, errorPage.value * 50),
  ),
  errorPages = computed(() => Math.max(1, Math.ceil(allErrors.value.length / 50)))
function pointer(path: string): string[] | null {
  if (!path.startsWith('/') || /~(?![01])/u.test(path)) return null
  return path
    .slice(1)
    .split('/')
    .map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'))
}
function locate(path: string) {
  const segments = pointer(path)
  if (segments) emit('locate', path, segments)
}
watch(locked, (value) => emit('locked', value), { immediate: true })
function stopRead() {
  ++generation
  readController?.abort()
  readController = null
  waiting.value = false
}
function clearResults() {
  reservation.value = allocation.value = previousAllocation.value = null
  validation.value = null
  httpErrors.value = []
  headReady.value = false
  previewOpen.value = confirmOpen.value = false
  errorPage.value = 1
}
watch(context, () => {
  stopRead()
  denied.value = false
  accepted.value = false
  if (executeLocked.value) {
    error.value = '当前配置已变化，原任务提交结果仍须确认，不能丢弃原意图。'
    return
  }
  headReady.value = false
  if (pending.value && locked.value)
    error.value = '配置或权限已变化，原写入意图仍保留；不能将旧结果应用到当前配置。'
  else {
    clearResults()
    error.value = ''
    notice.value = '配置、版本或权限已变化，原预检失效。'
  }
})
watch(
  () => props.modelValue,
  (open) => {
    if (clock) clearInterval(clock)
    now.value = Date.now()
    if (open)
      clock = setInterval(() => {
        now.value = Date.now()
      }, 1000)
    else stopRead()
  },
  { immediate: true },
)
watch(now, () => {
  if (!currentView.value || locked.value) return
  if (reservation.value && reservation.value.naming_date !== day()) {
    stopRead()
    clearResults()
    notice.value = '已跨上海命名日，冻结名称和预检已失效，请重新预检。'
  } else if (validation.value?.valid && !validTime.value) {
    validation.value = null
    headReady.value = false
    confirmOpen.value = false
    notice.value = '预检有效期已结束，请重新预检。'
  }
})
function mutation(): FrozenMutation {
  return {
    csrf_token: props.capabilities.csrf_token,
    idempotency_key: crypto.randomUUID(),
    if_match: `"${head.value.revision}"`,
  }
}
function make(kind: Pending['kind'], body?: Pending['body']) {
  pending.value = {
    kind,
    body: body ? copy(body) : undefined,
    context: context.value,
    planId: props.plan.id,
    mutation: mutation(),
  }
}
function fail(cause: unknown) {
  error.value = cause instanceof Error ? cause.message : '请求结果尚未确认，请保留原操作。'
  httpErrors.value = cause instanceof LaunchValidationError ? cause.field_errors : []
  errorPage.value = 1
  if (cause instanceof LaunchValidationError && [401, 403, 404].includes(cause.status)) {
    denied.value = true
    clearResults()
  }
  if (cause instanceof LaunchValidationError && [409, 410].includes(cause.status)) {
    headReady.value = false
    validation.value = null
    notice.value = '版本或冻结引用已变化，请重新读取计划后重新预检。'
  }
}
async function send(): Promise<boolean> {
  // 同一pending持有原body、CSRF、key和CAS；重试不从新表单拼装另一笔写入。
  const intent = pending.value
  if (!intent || writeBusy.value || intent.context !== context.value) return false
  writeBusy.value = true
  error.value = ''
  httpErrors.value = []
  try {
    const result =
      intent.kind === 'names'
        ? await launchValidationApi.reserveNames(intent.planId, intent.mutation)
        : intent.kind === 'allocation'
          ? await launchValidationApi.allocate(
              intent.planId,
              intent.body as AllocationRequest,
              intent.mutation,
            )
          : await launchValidationApi.validate(
              intent.planId,
              intent.body as ValidatePlan,
              intent.mutation,
            )
    if (!alive) return false
    pending.value = null
    uncertain.value = false
    if (intent.context !== context.value) {
      error.value = '先前请求已收到响应，当前配置已变化，请重新读取后开始新预检。'
      return false
    }
    if (intent.kind === 'names') reservation.value = result as NameReservation
    else if (intent.kind === 'allocation') allocation.value = result as Allocation
    else validation.value = result as PlanValidation
    return true
  } catch (cause) {
    if (!alive) return false
    fail(cause)
    uncertain.value = !(cause instanceof LaunchValidationError) || cause.unknown_result
    if (!uncertain.value) pending.value = null
    return false
  } finally {
    if (alive) writeBusy.value = false
  }
}
function pause(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const stop = () => {
      clearTimeout(timer)
      reject(new DOMException('已停止等待', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', stop)
      resolve()
    }, 1000)
    signal.addEventListener('abort', stop, { once: true })
    if (signal.aborted) stop()
  })
}
async function poll(): Promise<boolean> {
  // 每轮最多60次只读等待；停止本地等待不会发送不存在的服务端取消指令。
  if (!allocation.value) return false
  readController?.abort()
  readController = new AbortController()
  const signal = readController.signal,
    currentGeneration = generation
  waiting.value = true
  try {
    for (let n = 0; n < 60 && ['QUEUED', 'RUNNING'].includes(allocation.value!.state); n++) {
      await pause(signal)
      const result = await launchValidationApi.allocation(
        props.plan.id,
        allocation.value!.id,
        signal,
      )
      if (!alive || signal.aborted || currentGeneration !== generation || !currentView.value)
        return false
      allocation.value = result
    }
    if (allocation.value.state === 'FAILED') {
      error.value = '素材分配失败，未生成可用映射；请查看警告并明确重新分配。'
      return false
    }
    if (allocation.value.state !== 'SUCCEEDED') {
      notice.value = '本轮等待已结束，分配仍在服务端处理，可继续读取；未伪造失败或完成。'
      return false
    }
    return true
  } catch (cause) {
    if (!(cause instanceof Error && cause.name === 'AbortError')) fail(cause)
    return false
  } finally {
    if (alive && currentGeneration === generation) waiting.value = false
  }
}
function configuration(value: LaunchPlan) {
  const {
    id: _id,
    revision: _rev,
    state: _state,
    created_at: _created,
    updated_at: _updated,
    ...input
  } = value
  return JSON.stringify(input)
}
async function flow() {
  if (running.value || dependencyReason.value || locked.value) return
  running.value = true
  const capture = context.value
  try {
    if (!reservation.value) {
      stage.value = '正在预留真实系列名称'
      make('names')
      if (!(await send())) return
    }
    if (
      capture !== context.value ||
      !reservation.value ||
      reservation.value.naming_date !== day()
    ) {
      notice.value = '命名日期或当前配置已变化，请重新预检。'
      return
    }
    if (!allocation.value) {
      stage.value = '正在请求素材分配'
      make('allocation', {
        asset_ids: [...props.plan.asset_ids],
        allow_repeat: props.plan.allow_repeat,
        seed: seed.value,
        algorithm_version: 'allocation-v1',
      })
      if (!(await send())) return
    }
    if (allocation.value?.state !== 'SUCCEEDED') {
      stage.value = '等待完整分配结果'
      if (!(await poll())) return
    }
    if (capture !== context.value || !allocation.value || !reservation.value) return
    if (!validation.value) {
      stage.value = '正在执行服务端预检'
      make('validate', {
        allocation_id: allocation.value.id,
        name_reservation_id: reservation.value.id,
      })
      if (!(await send())) return
    }
    if (!validation.value?.valid) {
      stage.value = '预检未通过，请逐项处理字段错误'
      return
    }
    stage.value = '正在重读当前计划状态版本'
    const currentGeneration = generation
    // 预检响应没有head revision，必须读真实Plan；不能拿配置source版本猜测CAS。
    const fresh = await launchApi.get(props.plan.id)
    if (!alive || capture !== context.value || currentGeneration !== generation) return
    if (fresh.id !== props.plan.id || configuration(fresh) !== configuration(props.plan)) {
      headReady.value = false
      validation.value = null
      error.value = '服务端配置已变化，原预检不能用于提交，请重新读取计划。'
      return
    }
    head.value = copy(fresh)
    headReady.value = true
    stage.value = '预检已返回，当前状态版本已重新读取'
  } catch (cause) {
    if (alive) fail(cause)
  } finally {
    if (alive) running.value = false
  }
}
async function begin() {
  if (running.value || locked.value || dependencyReason.value) return
  if (!currentView.value) {
    clearResults()
    head.value = copy(props.plan)
    seed.value = 0
  }
  preparedContext.value = context.value
  validation.value = null
  headReady.value = false
  error.value = notice.value = ''
  await flow()
}
async function retry() {
  if (!pending.value || pending.value.context !== context.value || running.value) return
  if (await send()) await flow()
}
async function continueWaiting() {
  if (!running.value && !locked.value) await flow()
}
function stopWaiting() {
  stopRead()
  notice.value = '已停止本地等待，服务端分配仍可能继续；请继续读取以确认实际结果。'
}
async function reallocate() {
  if (running.value || locked.value || dependencyReason.value) return
  try {
    await ElMessageBox.confirm(
      '重新分配将使用新的seed并使旧预检失效；取消将保留原映射。确认继续？',
      '确认重新分配',
      { confirmButtonText: '确认重新分配', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const next = Math.max(seed.value, allocation.value?.seed ?? 0) + 1
  if (next > 2147483647) {
    error.value = 'seed已达到上限，不能继续重新分配。'
    return
  }
  previousAllocation.value = allocation.value
  allocation.value = null
  validation.value = null
  headReady.value = false
  seed.value = next
  await flow()
}
function beforeClose(done: () => void) {
  if (locked.value) {
    error.value = '请先确认原写入结果，当前窗口不能直接关闭。'
    return
  }
  stopRead()
  emit('update:modelValue', false)
  done()
}
function close() {
  if (!locked.value) {
    stopRead()
    emit('update:modelValue', false)
  }
}
function taskAccepted(task: Task) {
  executeLocked.value = false
  if (!currentView.value) {
    clearResults()
    notice.value = '先前提交已收到受理响应，当前配置已变化，请在任务列表按当前权限查询。'
    return
  }
  accepted.value = true
  validation.value = null
  headReady.value = false
  confirmOpen.value = false
  notice.value = '任务已受理，请在任务页面跟踪实际回读结果。'
  emit('accepted', task)
}
onBeforeUnmount(() => {
  alive = false
  stopRead()
  if (clock) clearInterval(clock)
})
</script>
<style scoped>
.full {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  margin: 14px 0;
}
.validation-errors {
  width: 100%;
}
</style>
