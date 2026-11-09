<template>
  <section aria-label="指标查询结果">
    <p v-if="data" role="status">
      当前页{{ data.items.length }}项 · 数据时间{{ data.data_as_of }} · 缺失单元{{
        data.missing_count
      }}
      · 权限版本{{ data.scope_version }}
    </p>
    <el-table
      :data="data?.items ?? []"
      :empty-text="
        data ? '当前筛选没有实体；请同时查看全范围汇总与缺失信息' : '尚无成功查询，请填写筛选后查询'
      "
    >
      <el-table-column label="实体 / 名称" min-width="240"
        ><template #default="{ row }"
          ><span>{{ row.name }}</span>
          <p class="entity-id">{{ row.entity_id }}</p></template
        ></el-table-column
      >
      <el-table-column prop="business_date" label="当地业务日" min-width="140"
        ><template #default="{ row }">{{ row.business_date ?? '汇总' }}</template></el-table-column
      >
      <el-table-column prop="currency" label="币种" width="85" />
      <el-table-column
        v-for="key in metricValueKeys"
        :key="key"
        :label="valueLabels[key]"
        min-width="135"
        ><template #default="{ row }">{{ row.values[key] ?? '未知' }}</template></el-table-column
      >
      <el-table-column prop="quality" label="质量" min-width="125" /><el-table-column
        prop="coverage"
        label="覆盖率"
        min-width="125"
      />
      <el-table-column label="操作" width="100" fixed="right"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="emit('detail', row)"
            >只读详情</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <template v-if="data">
      <details class="snapshot">
        <summary>查询快照标识</summary>
        <dl>
          <dt>来源快照ID</dt>
          <dd>{{ data.snapshot_id }}</dd>
          <dt>查询快照ID</dt>
          <dd>{{ data.query_snapshot_id }}</dd>
        </dl>
      </details>
      <h3>全筛选范围汇总（按原币种分组）</h3>
      <p>包含本次筛选的全部可见数据，不限于当前页。各币种分别统计；请结合覆盖率与数据时间查看。</p>
      <el-table :data="data.totals" empty-text="没有可核验的预期单元汇总">
        <el-table-column prop="currency" label="币种" width="85" /><el-table-column
          prop="tenant_id"
          label="租户ID"
          min-width="300"
        /><el-table-column prop="metric_profile_id" label="指标配置ID" min-width="300" />
        <el-table-column
          v-for="key in metricValueKeys"
          :key="key"
          :label="valueLabels[key]"
          min-width="135"
          ><template #default="{ row }">{{ row.values[key] ?? '未知' }}</template></el-table-column
        >
        <el-table-column prop="account_count" label="账户数" min-width="100" /><el-table-column
          prop="ad_count"
          label="去重广告数"
          min-width="120"
        /><el-table-column prop="missing_count" label="缺失单元" min-width="100" /><el-table-column
          prop="coverage"
          label="覆盖率"
          min-width="125"
        />
      </el-table>
    </template>
  </section>
</template>
<script setup lang="ts">
import { metricValueKeys, type Metrics, type MetricRow } from '@/api/orbit/metrics'
defineProps<{ data: Metrics | null }>()
const emit = defineEmits<{ detail: [row: MetricRow] }>()
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
.entity-id,
.snapshot dd {
  overflow-wrap: anywhere;
}
.entity-id {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.snapshot {
  margin: 16px 0;
}
.snapshot dd {
  margin: 6px 0 16px;
}
p {
  line-height: 1.6;
}
</style>
