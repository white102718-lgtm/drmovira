<template>
  <el-dialog
    :model-value="modelValue"
    title="确认提交投放任务"
    width="min(860px, 100vw)"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!locked"
    :before-close="beforeClose"
  >
    <el-alert
      title="提交只表示任务受理；对象创建、配置核验及实际投放结果由任务后续回读确认。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="reason" :title="reason" type="warning" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="pending && uncertain"
      title="本次提交结果尚未确认。原请求已保留，只能重试同一次提交，不能新建重复操作或直接关闭。"
      type="warning"
      :closable="false"
    />
    <template v-if="!contextChanged">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="计划 / 当前状态版本"
          ><span class="full"
            >{{ plan.name }} · {{ plan.id }} · {{ plan.revision }}</span
          ></el-descriptions-item
        >
        <el-descriptions-item label="拥有者 / 团队"
          ><span class="full"
            >{{ plan.ownership.owner_user_id }} / {{ plan.ownership.owner_team_id }}</span
          ></el-descriptions-item
        >
        <el-descriptions-item label="渠道"
          ><span class="full">{{ plan.channel_id ?? '未选择' }}</span></el-descriptions-item
        >
        <el-descriptions-item label="执行通道">{{
          plan.execution_mode === 'META_API' ? 'Meta API' : 'AdsPower UI'
        }}</el-descriptions-item>
        <el-descriptions-item label="系列 / 组 / 广告 / 全部DAG节点"
          >{{ validation.campaign_count }} / {{ validation.adset_count }} /
          {{ validation.ad_count }} / {{ validation.total_dag_node_count }}</el-descriptions-item
        >
        <el-descriptions-item label="预检有效期（UTC）">{{
          validation.expires_at ?? '未取得有效期'
        }}</el-descriptions-item>
        <el-descriptions-item label="预检范围版本">{{
          validation.scope_version
        }}</el-descriptions-item>
        <el-descriptions-item label="预检摘要"
          ><span class="full">{{ validation.hash ?? '未取得摘要' }}</span></el-descriptions-item
        >
        <el-descriptions-item label="命名 / 分配版本"
          >{{ reservation.naming_date }} · {{ reservation.plan_revision }} /
          {{ allocation.plan_revision }}</el-descriptions-item
        >
        <el-descriptions-item label="创建后启用">{{
          plan.activate_after_create ? '启用，需要独立发布权限及再次确认' : '默认暂停创建'
        }}</el-descriptions-item>
      </el-descriptions>
      <details>
        <summary>全部账户 ID（{{ plan.account_ids.length }}）</summary>
        <ul class="ids">
          <li v-for="id in plan.account_ids" :key="id" class="full">{{ id }}</li>
        </ul>
      </details>
      <h3>服务端预算汇总（按币种独立）</h3>
      <el-table :data="validation.budget_totals"
        ><el-table-column prop="currency" label="币种" /><el-table-column
          prop="amount"
          label="预算金额"
      /></el-table>
      <p v-if="!validation.budget_totals.length">服务端未返回预算汇总，不能推算预算。</p>
      <el-checkbox
        v-if="plan.activate_after_create"
        v-model="activateAck"
        :disabled="locked || !canPublish"
        aria-label="确认创建后启用"
        >我确认按本次账户、冻结配置及预算范围创建后启用</el-checkbox
      >
    </template>
    <el-table v-if="!contextChanged && fieldErrors.length" :data="fieldErrors" class="submit-errors"
      ><el-table-column prop="path" label="字段路径" min-width="220" /><el-table-column
        prop="code"
        label="错误码"
        min-width="160" /><el-table-column
        prop="message"
        label="说明"
        min-width="240" /><el-table-column prop="constraint" label="约束" min-width="150"
    /></el-table>
    <template #footer
      ><div class="actions">
        <el-button :disabled="locked" @click="cancel">取消提交</el-button
        ><el-button
          v-if="pending && uncertain"
          type="warning"
          :loading="busy"
          :disabled="pending.context !== context"
          @click="send"
          >重试本次提交</el-button
        ><el-button
          v-else
          type="primary"
          :disabled="Boolean(reason) || busy"
          :loading="busy"
          @click="submit"
          >确认提交任务</el-button
        >
      </div></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { LaunchCapabilities, LaunchPlan } from '@/api/orbit/launch'
import {
  launchValidationApi,
  LaunchValidationError,
  type Allocation,
  type ExecutePlan,
  type FrozenMutation,
  type NameReservation,
  type PlanHttpFieldError,
  type PlanValidation,
} from '@/api/orbit/launch-validation'
import type { Task } from '@/api/orbit/tasks'
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    plan: LaunchPlan
    capabilities: LaunchCapabilities
    validation: PlanValidation
    allocation: Allocation
    reservation: NameReservation
    available?: boolean
    contextVersion?: string
  }>(),
  { available: false, contextVersion: '' },
)
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  accepted: [task: Task]
  locked: [value: boolean]
}>()
const now = ref(Date.now()),
  activateAck = ref(false),
  busy = ref(false),
  uncertain = ref(false),
  error = ref(''),
  fieldErrors = ref<PlanHttpFieldError[]>([])
const context = computed(() =>
  JSON.stringify([
    props.plan,
    props.capabilities,
    props.validation,
    props.allocation,
    props.reservation,
    props.available,
    props.contextVersion,
  ]),
)
const canPublish = computed(() => props.capabilities.actions.includes('publish'))
const shanghaiDay = () =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(now.value))
const reason = computed(() => {
  if (!props.available) return '执行依赖尚未就绪，本窗口不会提交请求。'
  if (
    !props.capabilities.csrf_token ||
    !Number.isSafeInteger(props.plan.revision) ||
    props.plan.revision < 1
  )
    return '尚未取得有效的当前计划版本及写入上下文。'
  if (!props.capabilities.actions.includes('execute')) return '当前账号没有执行计划权限。'
  if (
    !props.validation.valid ||
    props.validation.errors.length ||
    !props.validation.hash ||
    !/^[a-f\d]{64}$/.test(props.validation.hash)
  )
    return '预检未通过或未取得有效摘要，请重新预检。'
  if (
    !props.validation.expires_at ||
    !Number.isFinite(Date.parse(props.validation.expires_at)) ||
    Date.parse(props.validation.expires_at) <= now.value
  )
    return '预检已过期，请重新预检。'
  if (props.reservation.naming_date !== shanghaiDay()) return '已跨上海命名日，请重新命名并预检。'
  if (
    props.allocation.state !== 'SUCCEEDED' ||
    props.allocation.plan_id !== props.plan.id ||
    props.allocation.plan_revision !== props.reservation.plan_revision
  )
    return '冻结名称与分配不一致，请重新预检。'
  if (!['DRAFT', 'VALIDATED'].includes(props.plan.state))
    return '计划状态不允许新提交，请读取已有任务。'
  if (props.plan.activate_after_create && (!canPublish.value || !activateAck.value))
    return '创建后启用还需发布权限和单独确认。'
  return ''
})
const pending = ref<{
  context: string
  planId: string
  body: ExecutePlan
  mutation: FrozenMutation
} | null>(null)
const locked = computed(() => busy.value || Boolean(pending.value && uncertain.value))
const contextChanged = computed(() =>
  Boolean(pending.value && pending.value.context !== context.value),
)
let clock: ReturnType<typeof setInterval> | undefined,
  alive = true
watch(locked, (value) => emit('locked', value), { immediate: true })
watch(context, () => {
  activateAck.value = false
  if (pending.value && locked.value)
    error.value = '当前配置或权限已变化，原提交意图仍保留，不能将旧结果应用到新配置。'
  else {
    error.value = ''
    fieldErrors.value = []
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
    else activateAck.value = false
  },
  { immediate: true },
)
async function submit() {
  if (reason.value || locked.value) return
  pending.value = {
    context: context.value,
    planId: props.plan.id,
    body: {
      hash: props.validation.hash!,
      activate_ack: props.plan.activate_after_create && activateAck.value,
    },
    mutation: {
      csrf_token: props.capabilities.csrf_token,
      idempotency_key: crypto.randomUUID(),
      if_match: `"${props.plan.revision}"`,
    },
  }
  await send()
}
async function send() {
  const intent = pending.value
  if (!intent || busy.value || intent.context !== context.value) return
  busy.value = true
  error.value = ''
  fieldErrors.value = []
  try {
    const task = await launchValidationApi.execute(intent.planId, intent.body, intent.mutation)
    if (!alive) return
    pending.value = null
    uncertain.value = false
    if (intent.context !== context.value) {
      error.value = '先前请求已收到任务受理响应；当前配置已变化，请从任务列表按当前权限查询。'
      return
    }
    busy.value = false
    emit('locked', false)
    emit('accepted', task)
    emit('update:modelValue', false)
  } catch (cause) {
    if (!alive) return
    error.value = cause instanceof Error ? cause.message : '提交结果尚未确认，请重试本次请求。'
    fieldErrors.value = cause instanceof LaunchValidationError ? cause.field_errors : []
    uncertain.value = !(cause instanceof LaunchValidationError) || cause.unknown_result
    if (!uncertain.value) pending.value = null
  } finally {
    if (alive) busy.value = false
  }
}
function beforeClose(done: () => void) {
  if (locked.value) {
    error.value = '请先确认原提交结果，不能直接关闭或另建提交。'
    return
  }
  done()
}
function cancel() {
  if (!locked.value) emit('update:modelValue', false)
}
onBeforeUnmount(() => {
  alive = false
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
  flex-wrap: wrap;
  justify-content: flex-end;
}
.ids {
  max-height: 240px;
  overflow: auto;
}
.submit-errors {
  margin-top: 16px;
}
</style>
