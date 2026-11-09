<script setup lang="ts">
import { ref } from 'vue'
import {
  getConfigurationHistory,
  type Configuration,
  type ConfigurationAudit,
} from '@/api/orbit/configuration'

const visible = ref(false)
const selected = ref<Configuration>()
const items = ref<ConfigurationAudit[]>([])
const cursor = ref<number | null>(null)
const loading = ref(false)
const errorMessage = ref('')
// 切换配置或关闭抽屉后忽略旧请求，避免串入另一配置的历史。
let generation = 0
const actions: Record<string, string> = {
  CREATE: '新增配置',
  UPDATE: '修改配置',
  READ_TEST: '只读认证测试',
}

async function load(more = false) {
  if (!selected.value || loading.value) return
  const current = generation
  loading.value = true
  errorMessage.value = ''
  try {
    const page = await getConfigurationHistory(
      selected.value.id,
      more ? (cursor.value ?? undefined) : undefined,
    )
    if (current !== generation) return
    items.value = more ? [...items.value, ...page.items] : page.items
    cursor.value = page.nextBeforeRevision
  } catch (error) {
    if (current === generation)
      errorMessage.value = error instanceof Error ? error.message : '变更历史读取失败'
  } finally {
    if (current === generation) loading.value = false
  }
}
function open(configuration: Configuration) {
  generation++
  selected.value = configuration
  items.value = []
  cursor.value = null
  loading.value = false
  visible.value = true
  void load()
}
function close() {
  generation++
  loading.value = false
  items.value = []
  selected.value = undefined
  errorMessage.value = ''
}
defineExpose({ open })
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="`${selected?.name ?? '配置'} · 变更历史`"
    size="min(920px, 100vw)"
    @close="close"
  >
    <p>记录操作人、变更字段及原因，凭据内容不回显。时间均为 UTC。</p>
    <el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon>
      <el-button text type="primary" @click="load(items.length > 0)">重试加载</el-button>
    </el-alert>
    <el-table v-loading="loading" :data="items" row-key="id" border empty-text="暂无变更记录">
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-descriptions :column="1" border class="history-details">
            <el-descriptions-item label="摘要规则">{{
              row.hashAlgorithm ?? '历史记录未采集'
            }}</el-descriptions-item>
            <el-descriptions-item label="变更前摘要"
              ><span class="history-hash">{{
                row.beforeHash ??
                (row.beforeRevision === 0 ? '新增配置，无旧状态' : '历史记录未采集')
              }}</span></el-descriptions-item
            >
            <el-descriptions-item label="变更后摘要"
              ><span class="history-hash">{{
                row.afterHash ?? '历史记录未采集'
              }}</span></el-descriptions-item
            >
          </el-descriptions>
        </template>
      </el-table-column>
      <el-table-column label="版本变化" width="130"
        ><template #default="{ row }"
          >{{ row.beforeRevision ?? '未知' }} → {{ row.revision }}</template
        ></el-table-column
      >
      <el-table-column label="操作" min-width="140"
        ><template #default="{ row }">{{
          actions[row.action] ?? row.action
        }}</template></el-table-column
      >
      <el-table-column prop="actorId" label="操作人ID" width="110" />
      <el-table-column label="变更字段" min-width="220"
        ><template #default="{ row }">{{
          row.changedFields.join('、') || '无字段变更'
        }}</template></el-table-column
      >
      <el-table-column prop="reason" label="变更原因" min-width="240" />
      <el-table-column prop="createdAt" label="操作时间（UTC）" min-width="220" />
    </el-table>
    <el-button v-if="cursor !== null" :loading="loading" class="history-more" @click="load(true)"
      >继续加载</el-button
    >
  </el-drawer>
</template>
<style scoped>
.history-details {
  margin: 12px;
}
.history-hash {
  overflow-wrap: anywhere;
}
.history-more {
  margin-top: 16px;
}
</style>
