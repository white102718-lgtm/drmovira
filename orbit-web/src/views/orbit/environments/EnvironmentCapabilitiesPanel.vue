<template>
  <section class="environment-capabilities" v-loading="loading">
    <el-alert
      title="按动作、对象层级和版本独立验收；身份匹配不代表可以操作广告。未验证或已失效的动作禁止执行。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="capability-toolbar">
      <el-button :disabled="loading" @click="load()">重新读取</el-button
      ><span>通道：AdsPower UI</span><span v-if="asOf">数据时间：{{ asOf }}</span>
    </div>
    <el-table
      :data="items"
      max-height="460"
      border
      empty-text="暂无动作验收回执；所有未列出动作均未验证，禁止执行。"
    >
      <el-table-column label="状态" min-width="100"
        ><template #default="{ row }"
          ><el-tag
            :type="
              row.state === 'VERIFIED' ? 'success' : row.state === 'REVOKED' ? 'danger' : 'warning'
            "
            >{{ states[row.state as keyof typeof states] }}</el-tag
          ></template
        ></el-table-column
      >
      <el-table-column prop="operation_kind" label="动作" min-width="125" />
      <el-table-column prop="entity_type" label="对象层级" min-width="120" />
      <el-table-column prop="agent_id" label="设备 ID" min-width="280" />
      <el-table-column prop="profile_binding_id" label="账户关联 ID" min-width="280" />
      <el-table-column prop="workflow_version" label="工作流版本" min-width="140" />
      <el-table-column prop="adapter_version" label="适配器版本" min-width="140" />
      <el-table-column prop="client_version" label="AdsPower 版本" min-width="145" />
      <el-table-column prop="browser_version" label="内核版本" min-width="140" />
      <el-table-column prop="page_language" label="页面语言" min-width="120" />
      <el-table-column prop="evidence_ref" label="验收证据" min-width="300" />
      <el-table-column prop="verified_at" label="验收时间" min-width="210" />
      <el-table-column prop="id" label="能力回执 ID" min-width="280" />
    </el-table>
    <el-button v-if="next" :disabled="loading" @click="load(next)">下一页</el-button>
  </section>
</template>
<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import {
  environmentCapabilityApi,
  type EnvironmentActionCapability,
} from '@/api/orbit/environment-capabilities'
const props = defineProps<{ active: boolean; contextKey: string }>()
const items = ref<EnvironmentActionCapability[]>([]),
  next = ref<string | null>(null),
  error = ref(''),
  loading = ref(false),
  asOf = ref('')
const states = { VERIFIED: '已验证', UNVERIFIED: '未验证 / 已失效', REVOKED: '已撤销' }
let controller: AbortController | undefined,
  generation = 0
async function load(cursor?: string) {
  controller?.abort()
  controller = new AbortController()
  const id = ++generation
  loading.value = true
  error.value = ''
  items.value = []
  next.value = null
  asOf.value = ''
  try {
    const p = await environmentCapabilityApi.list(cursor, controller.signal)
    if (id !== generation) return
    items.value = p.items
    next.value = p.next_cursor
    asOf.value = p.data_as_of
  } catch {
    if (id === generation) error.value = '能力读取失败，请重新读取。旧回执不能作为当前执行授权。'
  } finally {
    if (id === generation) loading.value = false
  }
}
watch(
  () => [props.active, props.contextKey],
  () => {
    controller?.abort()
    ++generation
    items.value = []
    next.value = null
    error.value = ''
    asOf.value = ''
    loading.value = false
    if (props.active) void load()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  controller?.abort()
  ++generation
})
</script>
<style scoped>
.environment-capabilities {
  min-width: 0;
}
.capability-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.capability-toolbar span {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
