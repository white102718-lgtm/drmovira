<template>
  <section v-if="error" class="task-read-error" aria-label="任务读取错误详情" role="alert">
    <p>{{ error.message }}</p>
    <dl>
      <dt>错误代码</dt>
      <dd>{{ error.code }}</dd>
      <dt>请求编号</dt>
      <dd>{{ error.request_id ?? '未取得服务端请求编号' }}</dd>
      <dt>读取重试标记</dt>
      <dd>
        {{
          error.source === 'server'
            ? error.retryable
              ? '服务端允许重新读取'
              : '服务端未标记可重试'
            : '本地错误，无服务端重试结论'
        }}
      </dd>
    </dl>
    <p>此标记仅说明本次读取请求；不授权重发广告操作。结果待核实（UNKNOWN）的任务仍须核验。</p>
    <details v-if="error.field_errors.length">
      <summary>字段错误（{{ error.field_errors.length }}条）</summary>
      <ol>
        <li v-for="(field, index) in error.field_errors" :key="index">
          <dl>
            <dt>字段路径</dt>
            <dd>{{ field.path }}</dd>
            <dt>字段错误代码</dt>
            <dd>{{ field.code }}</dd>
            <dt>说明</dt>
            <dd>{{ field.message }}</dd>
            <dt>约束</dt>
            <dd>{{ field.constraint || '未提供约束说明' }}</dd>
          </dl>
        </li>
      </ol>
    </details>
    <p v-else>没有字段错误详情。</p>
  </section>
</template>
<script setup lang="ts">
import type { TaskApiError } from '@/api/orbit/tasks'
import type { TaskEventError } from '@/api/orbit/task-events'
// 仅文本插值展示合同字段，不将JSON Pointer当HTML或可执行定位指令。
defineProps<{ error: TaskApiError | TaskEventError | null }>()
</script>
<style scoped>
.task-read-error {
  padding: 12px;
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 4px;
  color: var(--el-text-color-regular);
  background: var(--el-color-danger-light-9);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
dl {
  display: grid;
  grid-template-columns: minmax(80px, 120px) minmax(0, 1fr);
  gap: 6px;
}
dt {
  font-weight: 600;
}
dd {
  margin: 0;
  min-width: 0;
}
ol {
  padding-left: 24px;
}
</style>
