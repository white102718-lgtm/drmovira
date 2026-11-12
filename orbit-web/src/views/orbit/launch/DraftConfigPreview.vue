<template>
  <el-dialog
    :model-value="modelValue"
    title="当前配置预览"
    width="min(980px, 96vw)"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      title="这是当前表单的配置预览，包含尚未保存的更改；不代表已通过投放预检，也不会创建广告。"
      type="info"
      :closable="false"
    />
    <div class="preview-totals">
      <span
        >账户 <strong>{{ accountCount ?? '待解析' }}</strong></span
      >
      <span
        >系列配置 <strong>{{ plan.campaigns.length }}</strong></span
      >
      <span
        >素材池 <strong>{{ plan.asset_ids.length }}</strong></span
      >
      <span>创建后 {{ plan.activate_after_create ? '申请启用（需另行确认）' : '保持暂停' }}</span>
    </div>
    <el-empty v-if="!plan.campaigns.length" description="尚未添加广告系列" :image-size="60" />
    <section
      v-for="(campaign, ci) in plan.campaigns.slice(0, 50)"
      :key="campaign.local_id"
      class="preview-campaign"
    >
      <h3>
        系列 {{ ci + 1 }} · {{ objective(campaign.objective) }}
        <small>× {{ campaign.copies }} 份</small>
      </h3>
      <p>
        {{ campaign.budget ? '广告系列统一预算' : '广告组预算' }} · {{ budget(campaign.budget) }} ·
        {{ strategy(campaign.bid_strategy) }}
      </p>
      <p v-if="campaign.meta_settings?.spending_limit">
        系列花费限额 {{ campaign.meta_settings.spending_limit }}（账户币种）
      </p>
      <p v-if="!campaign.adsets.length" class="quiet">尚未添加广告组</p>
      <article
        v-for="(group, gi) in campaign.adsets.slice(0, 50)"
        :key="group.local_id"
        class="preview-group"
      >
        <h4>
          {{ group.name || `广告组 ${gi + 1}` }} <small>× {{ group.copies }} 份</small>
        </h4>
        <dl>
          <dt>预算</dt>
          <dd>{{ campaign.budget ? '由系列统一分配' : budget(group.budget) }}</dd>
          <dt>受众</dt>
          <dd>
            {{ group.country_codes?.join('、') || '地区待选择' }} · {{ group.age_min ?? '待填' }}—{{
              group.age_max === 65 ? '65+' : (group.age_max ?? '待填')
            }}
            ·
            {{ group.meta_settings?.audience_mode === 'ADVANTAGE' ? '进阶赋能型受众' : '普通受众' }}
          </dd>
          <dt>成效目标</dt>
          <dd>
            {{ goal(group.optimization_goal) }} ·
            {{
              group.placements === 'MANUAL'
                ? '手动版位'
                : group.placements === 'AUTO'
                  ? '自动版位'
                  : '版位待选择'
            }}
          </dd>
          <dt>排期</dt>
          <dd>
            {{ group.start_time || '开始时间待填写' }} → {{ group.end_time || '未设置结束时间' }}
          </dd>
        </dl>
        <div v-for="(ad, ai) in group.ads.slice(0, 50)" :key="ad.local_id" class="preview-ad">
          <strong>{{ ad.name || `广告 ${ai + 1}` }}</strong
          ><span
            >× {{ ad.copies }} ·
            {{ ad.meta_settings?.format === 'CAROUSEL' ? '轮播' : '单图片或视频' }} ·
            {{ cta(ad.cta) }}</span
          >
          <p v-if="ad.title">{{ ad.title }}</p>
          <p v-if="ad.body" class="body-copy">{{ ad.body }}</p>
          <p v-if="ad.url" class="quiet">{{ ad.url }}</p>
        </div>
        <p v-if="!group.ads.length" class="quiet">尚未添加广告</p>
        <p v-if="group.ads.length > 50" class="quiet">
          预览仅展示前 50 份广告配置，其余请返回配置区查看。
        </p>
      </article>
      <p v-if="campaign.adsets.length > 50" class="quiet">预览仅展示前 50 份组配置。</p>
    </section>
    <p v-if="plan.campaigns.length > 50" class="quiet">预览仅展示前 50 份系列配置。</p>
    <template #footer
      ><el-button @click="emit('update:modelValue', false)">返回配置</el-button></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import type { Budget, PlanWrite } from '@/api/orbit/launch'
defineProps<{ modelValue: boolean; plan: PlanWrite; accountCount: number | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const objective = (value?: string) =>
  ({ OUTCOME_SALES: '销售', OUTCOME_LEADS: '潜在客户', OUTCOME_APP_PROMOTION: '应用推广' })[
    value ?? ''
  ] ?? '目标待选择'
const strategy = (value?: string) =>
  ({
    LOWEST_COST_WITHOUT_CAP: '最高数量或价值',
    COST_CAP: '单次成效费用目标',
    LOWEST_COST_WITH_MIN_ROAS: '广告花费回报目标',
    LOWEST_COST_WITH_BID_CAP: '竞价上限',
  })[value ?? ''] ?? '竞价策略待选择'
const goal = (value?: string) =>
  ({
    OFFSITE_CONVERSIONS: '转化量最大化',
    VALUE: '转化价值最大化',
    APP_INSTALLS: '应用安装最大化',
  })[value ?? ''] ??
  value ??
  '待选择'
const cta = (value?: string) =>
  ({ SHOP_NOW: '立即订购', SIGN_UP: '立即注册', SUBSCRIBE: '订阅', PLAY_GAME: '玩游戏' })[
    value ?? ''
  ] ??
  value ??
  '行动号召待选择'
const budget = (value?: Budget | null) =>
  value
    ? `${value.type === 'DAILY' ? '每日' : '总预算'} ${value.amount} ${value.currency}`
    : '预算待填写'
</script>
<style scoped>
.preview-totals {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  padding: 20px 0;
}
.preview-campaign {
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 16px;
}
h3,
h4 {
  margin: 0 0 12px;
}
small,
.quiet {
  color: var(--el-text-color-secondary);
  font-weight: normal;
}
.preview-group {
  background: var(--el-fill-color-lighter);
  padding: 16px;
  margin-top: 16px;
  border-radius: 8px;
}
dl {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 8px;
}
dt {
  color: var(--el-text-color-secondary);
}
dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.preview-ad {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 14px 0 4px;
}
.preview-ad span {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}
p {
  overflow-wrap: anywhere;
}
.body-copy {
  white-space: pre-wrap;
}
@media (max-width: 600px) {
  .preview-campaign {
    padding: 12px;
  }
  .preview-group {
    padding: 12px;
  }
  .preview-ad span {
    display: block;
    margin: 6px 0;
  }
}
</style>
