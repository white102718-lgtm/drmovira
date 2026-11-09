<template>
  <section class="account-command-status" aria-label="原受理命令当前状态">
    <el-button :loading="loading" :disabled="loading" @click="refresh">
      {{ queried ? '刷新当前状态' : '查询当前状态' }}
    </el-button>
    <p>仅查询这次受理的当前命令状态，不会重新发送、取消或恢复执行。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-descriptions v-if="value" :column="1" border>
      <el-descriptions-item label="命令编号">{{ value.command_id }}</el-descriptions-item>
      <el-descriptions-item label="受理请求编号">{{
        value.accepted_request_id
      }}</el-descriptions-item>
      <el-descriptions-item label="当前命令状态"
        >{{ labels[value.state] }}（{{ value.state }}）</el-descriptions-item
      >
      <el-descriptions-item label="命令版本">{{ value.revision }}</el-descriptions-item>
      <el-descriptions-item label="已开始尝试次数">{{ value.attempt_count }}</el-descriptions-item>
      <el-descriptions-item label="已知错误分类">{{
        value.last_error_code ?? '未提供（null）'
      }}</el-descriptions-item>
      <el-descriptions-item v-for="field in times" :key="field.key" :label="field.label">
        {{ value[field.key] ?? '未提供（null）' }}
      </el-descriptions-item>
    </el-descriptions>
    <p v-if="value?.state === 'SUCCEEDED'">{{ completedMeaning }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { AccountAction } from '@/api/orbit/account-actions'
import {
  accountCommandApi,
  type AccountCommandDiagnostic,
  type AccountCommandState,
} from '@/api/orbit/account-command'
import { ReferenceApiError } from '@/api/orbit/references'

const props = defineProps<{ accountId: string; kind: AccountAction; requestId: string }>()
const value = ref<AccountCommandDiagnostic | null>(null)
const loading = ref(false),
  queried = ref(false),
  error = ref('')
let generation = 0,
  controller: AbortController | null = null
const labels: Record<AccountCommandState, string> = {
  SCHEDULED: '未来生效待激活',
  WAITING_EXECUTOR: '等待只读执行器',
  WAITING_RETRY: '只读退避等待',
  RUNNING: '执行中',
  BLOCKED: '已阻断',
  SUCCEEDED: '已完成',
  FAILED: '已失败',
}
const times = [
  { key: 'effective_from', label: '计划生效时间（UTC）' },
  { key: 'next_attempt_at', label: '最早再次读取时间（UTC）' },
  { key: 'created_at', label: '受理时间（UTC）' },
  { key: 'updated_at', label: '状态更新时间（UTC）' },
  { key: 'completed_at', label: '实际完成时间（UTC）' },
] as const
const completedMeaning = computed(() =>
  props.kind === 'SYNC'
    ? '只读元数据同步已完成，不表示金额采集或广告写入成功。'
    : props.kind === 'ASSIGNMENT'
      ? '当前分配投影已激活，历史事实保持原冻结归属。'
      : '仅本地解绑已完成，平台广告及历史事实保留。',
)

function reset() {
  ++generation
  controller?.abort()
  value.value = null
  error.value = ''
  queried.value = false
  loading.value = false
}
watch(() => [props.accountId, props.kind, props.requestId], reset)
async function refresh() {
  if (loading.value) return
  const token = ++generation
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  queried.value = true
  error.value = ''
  // 每次重新授权；失败后不继续显示上一份可能已失权的状态。
  value.value = null
  try {
    const result = await accountCommandApi.status(
      props.accountId,
      props.kind,
      props.requestId,
      controller.signal,
    )
    if (token === generation) value.value = result
  } catch (failure) {
    if (token === generation) {
      error.value =
        failure instanceof ReferenceApiError && [401, 403, 404].includes(failure.status)
          ? '当前身份或账户范围不允许读取此状态；原受理回执保留。'
          : '当前命令状态不可读，请稍后刷新；原受理回执保留，未重新执行。'
    }
  } finally {
    if (token === generation) loading.value = false
  }
}
onBeforeUnmount(reset)
</script>

<style scoped>
.account-command-status {
  margin-top: 12px;
  overflow-wrap: anywhere;
}
</style>
