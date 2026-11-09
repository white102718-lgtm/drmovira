<template>
  <section class="schedule-preview" aria-label="未来五次运行预览">
    <h3>未来五次运行</h3>
    <p>按当前填写的调度与服务端参考时间预览；不会保存规则，也不产生模拟或启用资格。</p>
    <div class="actions">
      <el-button ref="entryButton" :disabled="!canRequest" :loading="loading" @click="preview"
        >预览运行时间</el-button
      >
    </div>
    <p v-if="!permitted" role="status">没有当前创建或编辑动作，无法读取预览。</p>
    <p v-else-if="inputError" role="status">{{ inputError }}</p>
    <el-alert v-if="denied && error" :title="error" type="error" :closable="false" />
    <el-dialog
      :model-value="dialogOpen"
      title="预览未来5次运行"
      width="min(840px, 96vw)"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      :before-close="beforeDialogClose"
      @update:model-value="dialogVisibility"
      @closed="focusEntry"
    >
      <template v-if="dialogOpen">
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
        <p v-if="loading" role="status">正在读取未来运行时间…</p>
        <template v-if="result">
          <p>参考时间（UTC）：{{ result.reference_at }} · 调度时区：{{ result.timezone }}</p>
          <p v-if="!result.slots.length" role="status">
            当前起止日期与参考时间之后没有可运行时刻。
          </p>
          <el-table v-else :data="result.slots" row-key="utc_time"
            ><el-table-column
              prop="local_time"
              label="本地运行时间（含偏移）"
              min-width="260" /><el-table-column
              prop="utc_time"
              label="对应UTC时间"
              min-width="260"
          /></el-table>
          <section v-if="result.skipped_local_times.length" aria-label="跳过的夏令时时刻">
            <h4>已跳过的夏令时时刻</h4>
            <p v-for="item in result.skipped_local_times" :key="item.local_time">
              {{ item.local_time }}：夏令时切换导致该本地时刻不存在，已跳过。
            </p>
          </section>
        </template>
      </template>
      <template #footer
        ><el-button @click="cancel">{{ loading ? '取消预览' : '关闭预览' }}</el-button></template
      >
    </el-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RuleApiError, type RuleSchedule } from '@/api/orbit/rules'
import {
  ruleSchedulePreviewApi,
  parseSchedulePreviewRequest,
  type SchedulePreview,
} from '@/api/orbit/rule-schedule-preview'
const props = withDefaults(
  defineProps<{
    action: 'CREATE' | 'UPDATE'
    ruleId: string | null
    ruleRevision: number | null
    schedule: RuleSchedule
    csrfToken: string
    contextKey: string
    permissionCodes?: string[]
    disabled?: boolean
  }>(),
  { permissionCodes: () => [], disabled: false },
)
const emit = defineEmits<{ 'access-denied': [error: RuleApiError] }>()
const dialogOpen = ref(false),
  entryButton = ref<{ $el: HTMLButtonElement } | null>(null)
const result = ref<SchedulePreview | null>(null),
  error = ref(''),
  loading = ref(false),
  denied = ref(false)
let epoch = 0,
  controller: AbortController | undefined
const permitted = computed(
  () =>
    props.permissionCodes.includes('*:*:*') ||
    props.permissionCodes.includes(props.action === 'CREATE' ? 'rules.create' : 'rules.edit'),
)
const request = computed(() => {
  try {
    return parseSchedulePreviewRequest({
      action: props.action,
      rule_id: props.ruleId,
      rule_revision: props.ruleRevision,
      schedule: props.schedule,
    })
  } catch {
    return null
  }
})
const inputError = computed(() =>
  denied.value
    ? '当前会话不允许读取预览，请刷新编辑上下文。'
    : !request.value
      ? '请先完整填写合法的运行频率、时区和起止日期，并读取当前规则版本。'
      : !props.csrfToken
        ? '请先刷新当前编辑会话。'
        : '',
)
const canRequest = computed(
  () =>
    permitted.value &&
    !props.disabled &&
    !denied.value &&
    !loading.value &&
    !!request.value &&
    !!props.csrfToken,
)
const signature = computed(() =>
  JSON.stringify([
    props.contextKey,
    props.action,
    props.ruleId,
    props.ruleRevision,
    props.schedule,
    [...props.permissionCodes].sort(),
    props.disabled,
  ]),
)
function invalidate() {
  ++epoch
  controller?.abort()
  loading.value = false
  result.value = null
  error.value = ''
  dialogOpen.value = false
}
watch([signature, () => props.csrfToken], () => {
  invalidate()
})
watch([() => props.contextKey, () => props.csrfToken], () => {
  denied.value = false
})
async function preview() {
  if (!canRequest.value || !request.value) return
  invalidate()
  const current = epoch
  controller = new AbortController()
  loading.value = true
  dialogOpen.value = true
  try {
    const value = await ruleSchedulePreviewApi.preview(
      request.value,
      { csrf_token: props.csrfToken },
      controller.signal,
    )
    if (current === epoch) result.value = value
  } catch (e) {
    if (current !== epoch) return
    if (e instanceof RuleApiError) {
      if ([401, 403].includes(e.status)) {
        denied.value = true
        result.value = null
        dialogOpen.value = false
        emit('access-denied', e)
      }
      error.value = `${e.message}（${e.code}）${e.field_errors.map((item) => ` ${item.path}: ${item.message}`).join('')}`
    } else if (!(e instanceof Error && e.name === 'AbortError'))
      error.value = '预览读取失败，请重试。'
  } finally {
    if (current === epoch) loading.value = false
  }
}
function cancel() {
  invalidate()
}
// X/Escape在动画开始前就取消读取，不等after-leave的model更新。
function beforeDialogClose(done: () => void) {
  cancel()
  done()
}
function dialogVisibility(value: boolean) {
  if (!value) cancel()
}
function focusEntry() {
  if (!dialogOpen.value) entryButton.value?.$el?.focus()
}
onBeforeUnmount(invalidate)
</script>
<style scoped>
.schedule-preview {
  margin: 20px 0;
  padding: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}
h3 {
  margin: 0 0 8px;
  font-size: 16px;
}
h4 {
  font-size: 14px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 12px 0;
}
p {
  line-height: 1.6;
  overflow-wrap: anywhere;
}
</style>
