<template>
  <el-drawer
    :model-value="modelValue"
    title="冻结展开预览"
    size="min(1200px, 100vw)"
    append-to-body
    @close="$emit('update:modelValue', false)"
  >
    <el-alert
      title="这里只展示已取得的冻结名称与分配结果，不代表广告已经创建或投放。"
      type="info"
      :closable="false"
    />
    <el-descriptions :column="1" border>
      <el-descriptions-item label="分配 ID"
        ><span class="full">{{ allocation.id }}</span></el-descriptions-item
      >
      <el-descriptions-item label="配置版本 / 状态"
        >{{ allocation.plan_revision }} / {{ allocation.state }}</el-descriptions-item
      >
      <el-descriptions-item label="算法 / seed"
        >{{ allocation.algorithm_version }} / {{ allocation.seed }}</el-descriptions-item
      >
      <el-descriptions-item label="命名日期（上海）">{{
        reservation.naming_date
      }}</el-descriptions-item>
      <el-descriptions-item label="分配输入摘要"
        ><span class="full">{{ allocation.input_hash }}</span></el-descriptions-item
      >
    </el-descriptions>
    <el-alert
      v-for="(warning, index) in allocation.warnings"
      :key="index"
      :title="warning"
      type="warning"
      :closable="false"
    />
    <h3>广告与素材映射（共 {{ allocation.items.length }} 项）</h3>
    <p>页数只影响本地显示，全部映射仍保留。不能用本页行数代替完整广告数量。</p>
    <el-table :data="rows" class="mapping-table" row-key="ordinal">
      <el-table-column label="账户 / 系列 / 组 / 广告完整路径" min-width="320"
        ><template #default="{ row }"
          ><span class="full">{{ row.item.slot_key }}</span></template
        ></el-table-column
      >
      <el-table-column label="冻结系列名称 / 原始序号" min-width="220"
        ><template #default="{ row }"
          ><span class="full">{{ row.name?.name ?? '未匹配冻结系列名称' }}</span>
          <p class="full">{{ row.name?.sequence ?? '未知序号' }}</p></template
        ></el-table-column
      >
      <el-table-column label="账户 ID" min-width="260"
        ><template #default="{ row }"
          ><span class="full">{{ row.item.account_id }}</span></template
        ></el-table-column
      >
      <el-table-column label="素材 ID / 版本" min-width="260"
        ><template #default="{ row }"
          ><span class="full">{{ row.item.asset_id }}</span>
          <p>{{ row.item.asset_revision }}</p></template
        ></el-table-column
      >
    </el-table>
    <div class="tools">
      <el-button :disabled="page === 1" @click="page--">上一页映射</el-button
      ><span>第 {{ page }} / {{ pages }} 页</span
      ><el-button :disabled="page >= pages" @click="page++">下一页映射</el-button
      ><el-button :disabled="page >= pages" @click="page = pages">末页映射</el-button
      ><el-select v-model="size" aria-label="映射分页大小" @change="page = 1"
        ><el-option
          v-for="value in [20, 50, 100, 200]"
          :key="value"
          :value="value"
          :label="`${value}项`"
      /></el-select>
    </div>
    <h3>素材实际使用分布（{{ usage.length }} 项）</h3>
    <p>允许重复也受兼容约束，实际次数不承诺相差不超过 1；素材池内未使用项显示 0。</p>
    <el-table :data="usageRows" class="usage-table"
      ><el-table-column label="素材 ID" min-width="280"
        ><template #default="{ row }"
          ><span class="full">{{ row.id }}</span></template
        ></el-table-column
      ><el-table-column prop="count" label="使用次数" width="110"
    /></el-table>
    <div class="tools">
      <el-button :disabled="usagePage === 1" @click="usagePage--">上一页分布</el-button
      ><span>第 {{ usagePage }} / {{ usagePages }} 页</span
      ><el-button :disabled="usagePage >= usagePages" @click="usagePage++">下一页分布</el-button
      ><el-button :disabled="usagePage >= usagePages" @click="usagePage = usagePages"
        >末页分布</el-button
      >
    </div>
    <h3>全部冻结系列名称（共 {{ reservation.items.length }} 项）</h3>
    <el-table :data="nameRows" class="name-table"
      ><el-table-column label="系列路径" min-width="280"
        ><template #default="{ row }"
          ><span class="full">{{ row.slot_key }}</span></template
        ></el-table-column
      ><el-table-column label="名称" min-width="220"
        ><template #default="{ row }"
          ><span class="full">{{ row.name }}</span></template
        ></el-table-column
      ><el-table-column prop="sequence" label="原始序号" min-width="220"
    /></el-table>
    <div class="tools">
      <el-button :disabled="namePage === 1" @click="namePage--">上一页名称</el-button
      ><span>第 {{ namePage }} / {{ namePages }} 页</span
      ><el-button :disabled="namePage >= namePages" @click="namePage++">下一页名称</el-button
      ><el-button :disabled="namePage >= namePages" @click="namePage = namePages"
        >末页名称</el-button
      >
    </div>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Allocation, NameReservation } from '@/api/orbit/launch-validation'
const props = defineProps<{
  modelValue: boolean
  allocation: Allocation
  reservation: NameReservation
  assetIds: string[]
}>()
defineEmits<{ 'update:modelValue': [value: boolean] }>()
const page = ref(1),
  size = ref(20),
  usagePage = ref(1),
  namePage = ref(1)
const names = computed(() => new Map(props.reservation.items.map((item) => [item.slot_key, item])))
// 与服务端Slot.key七段及campaign_slots三段一致，仅用真实前缀关联，不按名称推断归属。
const rows = computed(() =>
  props.allocation.items
    .slice((page.value - 1) * size.value, page.value * size.value)
    .map((item, index) => ({
      item,
      ordinal: (page.value - 1) * size.value + index,
      name: names.value.get(item.slot_key.split('/').slice(0, 3).join('/')),
    })),
)
const pages = computed(() => Math.max(1, Math.ceil(props.allocation.items.length / size.value)))
const usage = computed(() => {
  const counts = new Map(props.assetIds.map((id) => [id, 0]))
  for (const item of props.allocation.items)
    counts.set(item.asset_id, (counts.get(item.asset_id) ?? 0) + 1)
  return [...counts].sort(([a], [b]) => a.localeCompare(b)).map(([id, count]) => ({ id, count }))
})
const usageRows = computed(() =>
  usage.value.slice((usagePage.value - 1) * 50, usagePage.value * 50),
)
const usagePages = computed(() => Math.max(1, Math.ceil(usage.value.length / 50)))
const nameRows = computed(() =>
  props.reservation.items.slice((namePage.value - 1) * 50, namePage.value * 50),
)
const namePages = computed(() => Math.max(1, Math.ceil(props.reservation.items.length / 50)))
watch(
  () => [props.allocation.id, props.reservation.id],
  () => {
    page.value = usagePage.value = namePage.value = 1
  },
)
</script>
<style scoped>
.full {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.tools {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin: 14px 0;
}
.tools :deep(.el-select) {
  width: 130px;
}
</style>
