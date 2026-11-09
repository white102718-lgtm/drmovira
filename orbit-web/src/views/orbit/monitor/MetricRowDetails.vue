<template>
  <el-drawer
    :model-value="row !== null"
    title="指标实体详情"
    size="min(720px, 100vw)"
    @update:model-value="!$event && emit('close')"
  >
    <template v-if="row">
      <p>查看本次查询的指标详情。未知值不表示零，此页面不会修改广告。</p>
      <dl class="metric-fields">
        <template v-for="(label, key) in labels" :key="key"
          ><dt>{{ label }}</dt>
          <dd>{{ row[key] === null ? '未知' : row[key] }}</dd></template
        >
      </dl>
      <h3>完整指标值</h3>
      <dl class="metric-fields">
        <template v-for="key in metricValueKeys" :key="key"
          ><dt>{{ valueLabels[key] }}</dt>
          <dd>{{ row.values[key] ?? '未知' }}</dd></template
        >
      </dl>
    </template>
  </el-drawer>
</template>
<script setup lang="ts">
import { metricValueKeys, type MetricRow } from '@/api/orbit/metrics'
defineProps<{ row: MetricRow | null }>()
const emit = defineEmits<{ close: [] }>()
const labels: Record<Exclude<keyof MetricRow, 'values'>, string> = {
  tenant_id: '租户ID',
  owner_team_id: '拥有团队ID',
  operator_user_id: '投放师ID',
  entity_id: '实体ID',
  name: '历史名称',
  channel_id: '渠道ID',
  product_name_snapshot: '产品名称快照',
  currency: '原币种',
  metric_profile_id: '指标配置ID',
  business_date: '账户当地业务日',
  account_count: '账户数',
  ad_count: '去重广告数',
  quality: '质量',
  coverage: '覆盖率',
}
const valueLabels = {
  spend: '消耗',
  impressions: '曝光',
  clicks: '点击',
  registrations: '注册',
  purchases: '购物',
  purchase_value: '转化价值',
  roas: 'ROAS',
  cpm: 'CPM',
  ctr: 'CTR',
  cpc: 'CPC',
  cpa: 'CPA',
  usage: '素材使用量',
}
</script>
<style scoped>
.metric-fields {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) minmax(0, 3fr);
  gap: 12px;
  margin: 20px 0;
}
.metric-fields dt {
  color: var(--el-text-color-regular);
}
.metric-fields dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-variant-numeric: tabular-nums;
}
</style>
