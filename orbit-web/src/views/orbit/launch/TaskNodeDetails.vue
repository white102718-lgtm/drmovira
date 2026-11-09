<template>
  <el-drawer
    :model-value="Boolean(node)"
    title="任务节点详情"
    size="min(720px, 100vw)"
    append-to-body
    destroy-on-close
    @close="$emit('close')"
  >
    <template v-if="node">
      <el-alert
        v-if="node.state === 'UNKNOWN'"
        title="结果尚未核实，不代表操作失败；本页不会重发操作。"
        type="warning"
        :closable="false"
      />
      <el-descriptions :column="1" border class="node-fields">
        <el-descriptions-item label="节点 ID"
          ><span class="task-full-text">{{ node.id }}</span></el-descriptions-item
        >
        <el-descriptions-item label="节点键"
          ><span class="task-full-text">{{ node.node_key }}</span></el-descriptions-item
        >
        <el-descriptions-item label="节点类型">{{
          nodeKindLabels[node.kind]
        }}</el-descriptions-item>
        <el-descriptions-item label="处理状态"
          ><el-tag :type="taskTag(node.state)">{{
            taskStateLabels[node.state]
          }}</el-tag></el-descriptions-item
        >
        <el-descriptions-item label="配置核验">{{
          configurationLabels[node.configuration_state]
        }}</el-descriptions-item>
        <el-descriptions-item label="投放状态">{{
          deliveryLabels[node.delivery_state]
        }}</el-descriptions-item>
        <el-descriptions-item label="平台对象 ID"
          ><span class="task-full-text">{{
            node.external_id ?? '暂无平台对象 ID'
          }}</span></el-descriptions-item
        >
        <el-descriptions-item label="尝试次数">{{ node.attempt }}</el-descriptions-item>
        <el-descriptions-item label="可安全重试标记">{{
          node.retryable ? '是（只读标记）' : '否'
        }}</el-descriptions-item>
        <el-descriptions-item label="错误码"
          ><span class="task-full-text">{{ node.error_code ?? '无' }}</span></el-descriptions-item
        >
        <el-descriptions-item label="错误说明"
          ><span class="task-full-text">{{
            node.error_message ?? '无'
          }}</span></el-descriptions-item
        >
        <el-descriptions-item label="执行通道">{{
          node.execution_mode ? executionLabels[node.execution_mode] : '未提供'
        }}</el-descriptions-item>
        <el-descriptions-item label="无须重复操作">{{
          node.no_op === undefined ? '未提供' : node.no_op ? '是' : '否'
        }}</el-descriptions-item>
        <el-descriptions-item label="更新时间（UTC）"
          ><span class="task-full-text">{{ node.updated_at }}</span></el-descriptions-item
        >
      </el-descriptions>
      <h3>父节点（{{ node.parent_ids.length }}）</h3>
      <p>父节点可能位于其他页；这里保留全部 ID，不将跨页依赖标成缺失。</p>
      <el-empty v-if="!node.parent_ids.length" description="没有父节点" :image-size="60" />
      <ul v-else class="parent-list" aria-label="完整父节点 ID" tabindex="0">
        <li v-for="(id, index) in node.parent_ids" :key="`${index}:${id}`">
          <span class="task-full-text">{{ id }}</span
          ><el-tag size="small" type="info">{{
            visibleNodeIds.includes(id) ? '本页节点' : '跨页节点'
          }}</el-tag>
        </li>
      </ul>
    </template>
  </el-drawer>
</template>
<script setup lang="ts">
import {
  configurationLabels,
  deliveryLabels,
  executionLabels,
  nodeKindLabels,
  taskStateLabels,
  taskTag,
  type TaskNode,
} from '@/api/orbit/tasks'
defineProps<{ node: TaskNode | null; visibleNodeIds: string[] }>()
defineEmits<{ close: [] }>()
</script>
<style scoped>
.node-fields {
  margin-top: 16px;
}
.task-full-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.parent-list {
  max-height: 360px;
  overflow: auto;
  padding-inline-start: 20px;
}
.parent-list li {
  padding: 6px 0;
}
.parent-list .el-tag {
  margin-inline-start: 8px;
}
</style>
