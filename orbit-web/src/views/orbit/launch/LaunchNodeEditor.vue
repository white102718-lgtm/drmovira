<template>
  <div class="campaign-editor">
    <section ref="nodePane" class="node-pane" tabindex="-1">
      <el-empty v-if="!selected" description="请选择或新增配置节点" :image-size="48" />
      <template v-else>
        <el-form label-position="top" :disabled="disabled">
          <el-form-item label="复制份数（1—50）"
            ><el-input-number
              v-model="selected.node.copies"
              :min="1"
              :max="50"
              :precision="0"
              @change="touch"
          /></el-form-item>
          <template v-if="selected.kind === 'campaign'">
            <el-alert
              title="最终系列名称由渠道、投手、项目日期及服务端序号生成；当前仅保存配置，名称将在预检前由服务端预留。"
              type="info"
              :closable="false"
            />
            <el-form-item label="投放目标"
              ><el-select
                v-model="selected.node.objective"
                clearable
                placeholder="草稿可暂不选择"
                @change="objectiveChanged"
                ><el-option label="销量" value="OUTCOME_SALES" /><el-option
                  label="潜在客户"
                  value="OUTCOME_LEADS" /><el-option
                  label="应用推广"
                  value="OUTCOME_APP_PROMOTION" /></el-select
            ></el-form-item>
            <el-form-item label="购买方式"
              ><el-select v-model="selected.node.buying_type" clearable @change="touch"
                ><el-option label="竞价 AUCTION" value="AUCTION" /></el-select
            ></el-form-item>
            <el-form-item label="特殊广告类别"
              ><el-select
                v-model="selected.node.special_ad_categories"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="10"
                @change="touch"
            /></el-form-item>
            <el-form-item label="竞价策略"
              ><el-select v-model="selected.node.bid_strategy" clearable @change="touch"
                ><el-option
                  label="最高数量 / 价值（不限竞价）"
                  value="LOWEST_COST_WITHOUT_CAP" /><el-option
                  label="单次成效费用目标"
                  value="COST_CAP" /><el-option
                  label="ROAS 目标"
                  value="LOWEST_COST_WITH_MIN_ROAS" /><el-option
                  label="竞价上限"
                  value="LOWEST_COST_WITH_BID_CAP" /></el-select
            ></el-form-item>
          </template>
          <template v-if="selected.kind === 'adset'">
            <el-form-item label="广告组名称（最多200码点）"
              ><el-input v-model="selected.node.name" @input="touch"
            /></el-form-item>
            <el-form-item label="国家（最多50个）"
              ><el-select
                v-model="selected.node.country_codes"
                multiple
                filterable
                :multiple-limit="50"
                @change="touch"
                ><el-option
                  v-for="country in launchCountries"
                  :key="country"
                  :label="country"
                  :value="country" /></el-select
            ></el-form-item>
            <div class="two-columns">
              <el-form-item label="最低年龄"
                ><el-input-number
                  v-model="selected.node.age_min"
                  :min="18"
                  :max="65"
                  :precision="0"
                  @change="touch" /></el-form-item
              ><el-form-item label="最高年龄"
                ><el-input-number
                  v-model="selected.node.age_max"
                  :min="18"
                  :max="65"
                  :precision="0"
                  @change="touch"
              /></el-form-item>
            </div>
            <el-form-item label="语言ID（最多20个）"
              ><el-select
                v-model="selected.node.locales"
                multiple
                filterable
                allow-create
                :multiple-limit="20"
                @change="touch"
            /></el-form-item>
            <el-form-item label="版位"
              ><el-select v-model="selected.node.placements" clearable @change="touch"
                ><el-option label="自动版位" value="AUTO" /><el-option
                  label="手动版位"
                  value="MANUAL" /></el-select
            ></el-form-item>
            <div class="two-columns">
              <el-form-item label="优化目标"
                ><el-select v-model="selected.node.optimization_goal" filterable @change="touch"
                  ><el-option
                    v-for="option in optimizationOptions"
                    :key="option.value"
                    :value="option.value"
                    :label="option.label" />
                  <el-option
                    v-if="selected.node.optimization_goal && !optimizationKnown"
                    :value="selected.node.optimization_goal"
                    :label="
                      selected.node.optimization_goal + '（已保存，与当前配置兼容性待核验）'
                    " /></el-select></el-form-item
              ><el-form-item label="计费事件"
                ><el-select v-model="selected.node.billing_event" @change="touch"
                  ><el-option label="展示次数" value="IMPRESSIONS" /><el-option
                    v-if="
                      selected.node.billing_event && selected.node.billing_event !== 'IMPRESSIONS'
                    "
                    :value="selected.node.billing_event"
                    :label="selected.node.billing_event + '（已保存）'" /></el-select
              ></el-form-item>
            </div>
            <el-form-item label="指标配置ID（草稿可空）">
              <PlanMetricProfileField
                :model-value="selected.node.metric_profile_id"
                :binding-key="selected.node.local_id"
                :can-read="metricReadAllowed"
                :context-key="metricContextKey"
                :disabled="disabled"
                @update:model-value="metricChanged"
                @browsing="emit('browsing', $event)"
              />
            </el-form-item>
            <el-form-item label="开始时间（含时区偏移）"
              ><el-input
                v-model="selected.node.start_time"
                placeholder="2027-01-01T00:00:00+08:00"
                @input="touch"
            /></el-form-item>
            <el-form-item label="结束时间（含时区偏移，可空）"
              ><el-input
                :model-value="selected.node.end_time ?? ''"
                placeholder="留空表示未设置，不推算生命周期预算"
                @input="endTime"
            /></el-form-item>
            <el-alert
              title="尚未完成指标及逐账户身份资源核验，草稿配置不代表资源已经授权。"
              type="info"
              :closable="false"
            />
          </template>
          <template v-if="selected.kind === 'ad'">
            <el-form-item label="广告名称（最多200码点）"
              ><el-input v-model="selected.node.name" @input="touch"
            /></el-form-item>
            <el-form-item label="标题（最多100码点）"
              ><el-input v-model="selected.node.title" @input="touch" /><span class="field-count"
                >{{ codePoints(selected.node.title ?? '') }}/100</span
              ></el-form-item
            >
            <el-form-item label="正文（最多2000码点，保留换行）"
              ><el-input
                v-model="selected.node.body"
                type="textarea"
                :rows="4"
                @input="touch"
              /><span class="field-count"
                >{{ codePoints(selected.node.body ?? '') }}/2000</span
              ></el-form-item
            >
            <el-form-item label="描述（最多300码点）"
              ><el-input v-model="selected.node.description" @input="touch"
            /></el-form-item>
            <el-form-item label="广告落地链接（HTTPS）"
              ><el-input
                :model-value="selected.node.url ?? ''"
                placeholder="不会被渠道链接静默覆盖"
                @input="adUrl"
            /></el-form-item>
            <el-form-item label="链接参数（key=value，不带问号）"
              ><el-input
                v-model="selected.node.url_tags"
                placeholder="source=orbit&campaign=test"
                @input="touch"
            /></el-form-item>
            <el-form-item label="行动号召 CTA"
              ><el-select v-model="selected.node.cta" filterable @change="touch"
                ><el-option label="立即订购" value="SHOP_NOW" /><el-option
                  label="立即注册"
                  value="SIGN_UP" /><el-option label="订阅" value="SUBSCRIBE" /><el-option
                  label="玩游戏"
                  value="PLAY_GAME" /><el-option
                  v-if="
                    selected.node.cta &&
                    !['SHOP_NOW', 'SIGN_UP', 'SUBSCRIBE', 'PLAY_GAME'].includes(selected.node.cta)
                  "
                  :value="selected.node.cta"
                  :label="selected.node.cta + '（已保存）'" /></el-select
            ></el-form-item>
            <el-form-item label="素材类型要求"
              ><el-select v-model="selected.node.asset_type" clearable @change="touch"
                ><el-option label="任意类型" value="ANY" /><el-option
                  label="图片"
                  value="IMAGE" /><el-option label="视频" value="VIDEO" /></el-select
            ></el-form-item>
          </template>
          <el-form-item v-if="selected.kind !== 'ad'" label="预算拥有者">
            <span>{{
              selected.node.budget
                ? `${selected.node.budget.owner} · ${selected.node.budget.type} · ${selected.node.budget.amount} ${selected.node.budget.currency}`
                : '尚未配置预算'
            }}</span>
            <el-button :disabled="disabled" @click="openBudget">配置预算</el-button
            ><el-button v-if="selected.node.budget" :disabled="disabled" @click="clearBudget"
              >移除预算</el-button
            >
          </el-form-item>
          <MetaSettingsFields
            ref="metaFields"
            :key="selected.node.local_id"
            :kind="selected.kind"
            :asset-ids="assetIds"
            :objective="objective"
            :bid-strategy="selected.kind === 'campaign' ? selected.node.bid_strategy : undefined"
            :placements="selected.kind === 'adset' ? selected.node.placements : undefined"
            :model-value="selected.node.meta_settings"
            :disabled="disabled"
            @update:model-value="metaChanged"
          />
        </el-form>
      </template>
    </section>
    <el-dialog
      v-model="budgetOpen"
      title="配置预算"
      width="min(540px, 95vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!disabled"
      :before-close="closeBudget"
      @open-auto-focus="budgetFocusReady"
    >
      <el-alert v-if="budgetError" :title="budgetError" type="error" :closable="false" />
      <el-form ref="budgetFields" label-position="top" :disabled="disabled">
        <el-form-item label="预算拥有者"
          ><el-input :model-value="budgetForm.owner" disabled
        /></el-form-item>
        <el-form-item label="预算类型"
          ><el-select v-model="budgetForm.type"
            ><el-option label="日预算" value="DAILY" /><el-option
              label="生命周期预算"
              value="LIFETIME" /></el-select
        ></el-form-item>
        <el-form-item label="金额（十进制字符串）"
          ><el-input
            v-model="budgetForm.amount"
            inputmode="decimal"
            placeholder="大于0，最多1000000，至多6位小数"
        /></el-form-item>
        <el-form-item label="币种"
          ><el-input v-model="budgetForm.currency" placeholder="与所选账户真实币种一致"
        /></el-form-item>
        <el-form-item label="消费上限（可空）"
          ><el-input
            :model-value="budgetForm.spend_cap ?? ''"
            inputmode="decimal"
            @input="budgetForm.spend_cap = String($event).trim() || null"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button :disabled="disabled" @click="budgetOpen = false">取消</el-button
        ><el-button type="primary" :disabled="disabled" @click="confirmBudget"
          >确认预算配置</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { AdConfig, AdSetConfig, Budget, CampaignConfig } from '@/api/orbit/launch'
import MetaSettingsFields from './MetaSettingsFields.vue'
import PlanMetricProfileField from './PlanMetricProfileField.vue'
import { launchCountries } from '@/api/orbit/launch-countries'
import { cloneValue, codePoints } from '@/api/orbit/launch-form'
const props = withDefaults(
  defineProps<{
    modelValue: CampaignConfig[]
    localId: string
    assetIds?: string[]
    objective?: CampaignConfig['objective']
    disabled?: boolean
    metricReadAllowed?: boolean
    metricContextKey?: string
  }>(),
  {
    disabled: false,
    metricReadAllowed: false,
    metricContextKey: '',
    assetIds: () => [],
  },
)
const emit = defineEmits<{
  'update:modelValue': [value: CampaignConfig[]]
  browsing: [value: boolean]
}>()
type Selection =
  | { kind: 'campaign'; node: CampaignConfig; siblings: CampaignConfig[] }
  | { kind: 'adset'; node: AdSetConfig; siblings: AdSetConfig[] }
  | { kind: 'ad'; node: AdConfig; siblings: AdConfig[] }
const selectedId = ref(props.localId)
watch(
  () => props.localId,
  (value) => {
    selectedId.value = value
  },
)
const nodePane = ref<HTMLElement>(),
  budgetFields = ref<{ $el: HTMLElement }>()
let budgetReady: ((value: boolean) => void) | undefined
async function budgetFocusReady() {
  await nextTick()
  await nextTick()
  budgetReady?.(budgetOpen.value)
  budgetReady = undefined
}
onBeforeUnmount(() => {
  budgetReady?.(false)
  budgetReady = undefined
})
function locate(id: string): Selection | null {
  for (const campaign of props.modelValue) {
    if (campaign.local_id === id)
      return { kind: 'campaign', node: campaign, siblings: props.modelValue }
    for (const group of campaign.adsets) {
      if (group.local_id === id) return { kind: 'adset', node: group, siblings: campaign.adsets }
      for (const ad of group.ads)
        if (ad.local_id === id) return { kind: 'ad', node: ad, siblings: group.ads }
    }
  }
  return null
}
const selected = computed(() => locate(selectedId.value))
const optimizationOptions = computed(() => {
  if (props.objective === 'OUTCOME_APP_PROMOTION')
    return [{ value: 'APP_INSTALLS', label: '应用安装' }]
  const options = [{ value: 'OFFSITE_CONVERSIONS', label: '最大转化数量' }]
  if (
    selected.value?.kind === 'adset' &&
    props.objective === 'OUTCOME_SALES' &&
    selected.value.node.meta_settings?.conversion_event === 'PURCHASE'
  )
    options.push({ value: 'VALUE', label: '最大转化价值' })
  return options
})
const optimizationKnown = computed(() => {
  const node = selected.value?.kind === 'adset' ? selected.value.node : undefined
  return optimizationOptions.value.some((option) => option.value === node?.optimization_goal)
})
const metaFields = ref<InstanceType<typeof MetaSettingsFields>>()
function metaChanged(
  value:
    | import('@/api/orbit/launch').CampaignMetaSettings
    | import('@/api/orbit/launch').AdSetMetaSettings
    | import('@/api/orbit/launch').AdMetaSettings,
) {
  if (props.disabled || !selected.value) return
  selected.value.node.meta_settings = value
  touch()
}
function objectiveChanged() {
  if (props.disabled || selected.value?.kind !== 'campaign') return
  const app = selected.value.node.objective === 'OUTCOME_APP_PROMOTION'
  for (const group of selected.value.node.adsets) {
    group.optimization_goal = app ? 'APP_INSTALLS' : 'OFFSITE_CONVERSIONS'
    group.meta_settings = { ...group.meta_settings, conversion_location: app ? 'APP' : 'WEBSITE' }
  }
  touch()
}
function metricChanged(value: string | undefined) {
  if (props.disabled || selected.value?.kind !== 'adset') return
  if (value === undefined) delete selected.value.node.metric_profile_id
  else selected.value.node.metric_profile_id = value
  touch()
}
function touch() {
  emit('update:modelValue', [...props.modelValue])
}
/** 定位只改变当前选中与焦点，不改节点值；未知字段不能回落到一个看似成功的控件。 */
async function focusField(localId: string, path: string[]): Promise<boolean> {
  if (budgetOpen.value || !locate(localId)) return false
  selectedId.value = localId
  await nextTick()
  if (!selected.value || selected.value.node.local_id !== localId) return false
  if (path[0] === 'meta_settings')
    return (await metaFields.value?.focusField(path.slice(1))) ?? false
  if (!path.length) {
    nodePane.value?.focus()
    nodePane.value?.scrollIntoView?.({ block: 'nearest' })
    return !!nodePane.value
  }
  const shared: Record<string, string> = { copies: '复制份数（1—50）' }
  const labels: Record<string, Record<string, string>> = {
    campaign: {
      objective: '投放目标',
      buying_type: '购买方式',
      special_ad_categories: '特殊广告类别',
      bid_strategy: '竞价策略',
    },
    adset: {
      name: '广告组名称（最多200码点）',
      country_codes: '国家（最多50个）',
      age_min: '最低年龄',
      age_max: '最高年龄',
      locales: '语言ID（最多20个）',
      placements: '版位',
      optimization_goal: '优化目标',
      billing_event: '计费事件',
      metric_profile_id: '指标配置ID（草稿可空）',
      start_time: '开始时间（含时区偏移）',
      end_time: '结束时间（含时区偏移，可空）',
    },
    ad: {
      name: '广告名称（最多200码点）',
      title: '标题（最多100码点）',
      body: '正文（最多2000码点，保留换行）',
      description: '描述（最多300码点）',
      url: '广告落地链接（HTTPS）',
      url_tags: '链接参数（key=value，不带问号）',
      cta: '行动号召 CTA',
      asset_type: '素材类型要求',
    },
  }
  let root = nodePane.value,
    label = shared[path[0]] ?? labels[selected.value!.kind][path[0]]
  if (path[0] === 'budget' && selected.value!.kind !== 'ad') {
    const budgetLabels: Record<string, string> = {
      type: '预算类型',
      amount: '金额（十进制字符串）',
      currency: '币种',
      spend_cap: '消费上限（可空）',
    }
    if (props.disabled || path.length > 2 || (!budgetLabels[path[1]] && path.length !== 1))
      return false
    const trapped = new Promise<boolean>((resolve) => {
      budgetReady = resolve
    })
    openBudget()
    if (!(await trapped)) return false
    root = budgetFields.value?.$el
    label = budgetLabels[path[1]] ?? '预算类型'
  } else if (path.length !== 1) {
    // 数组成员错误定位该真实数组控件，但拒绝任意深层未知字段。
    if (
      path.length !== 2 ||
      !['country_codes', 'locales', 'special_ad_categories'].includes(path[0]) ||
      !/^(0|[1-9]\d*)$/.test(path[1])
    )
      return false
  }
  if (!root || !label) return false
  const item = [...root.querySelectorAll('label')]
    .find((row) => row.textContent?.trim() === label)
    ?.closest('.el-form-item')
  const target = item?.querySelector<HTMLElement>(
    'input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), button:not([disabled])',
  )
  if (!target) return false
  target.scrollIntoView?.({ block: 'nearest' })
  target.focus()
  return document.activeElement === target
}
defineExpose({ focusField })
function endTime(value: string) {
  if (!props.disabled && selected.value?.kind === 'adset') {
    selected.value.node.end_time = value.trim() || null
    touch()
  }
}
function adUrl(value: string) {
  if (!props.disabled && selected.value?.kind === 'ad') {
    selected.value.node.url = value.trim() || null
    touch()
  }
}
const budgetOpen = ref(false),
  budgetError = ref(''),
  budgetTarget = ref('')
const budgetForm = ref<Budget>({
  owner: 'CAMPAIGN',
  type: 'DAILY',
  amount: '',
  currency: '',
  spend_cap: null,
})
function openBudget() {
  if (props.disabled || !selected.value || selected.value.kind === 'ad') return
  budgetTarget.value = selected.value.node.local_id
  budgetForm.value = selected.value.node.budget
    ? cloneValue(selected.value.node.budget)
    : {
        owner: selected.value.kind === 'campaign' ? 'CAMPAIGN' : 'ADSET',
        type: 'DAILY',
        amount: '',
        currency: '',
        spend_cap: null,
      }
  budgetError.value = ''
  budgetOpen.value = true
}
function clearBudget() {
  if (!props.disabled && selected.value && selected.value.kind !== 'ad') {
    selected.value.node.budget = null
    touch()
  }
}
function validMoney(value: string) {
  if (!/^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(value) || value.length > 28) return false
  const [integer, decimal = ''] = value.split('.')
  const scaled = BigInt(integer) * 1000000n + BigInt(decimal.padEnd(6, '0'))
  return scaled > 0n && scaled <= 1000000000000n
}
function confirmBudget() {
  if (props.disabled) return
  const target = locate(budgetTarget.value)
  if (!target || target.kind === 'ad') {
    budgetError.value = '原配置节点已变化，请取消后重新打开'
    return
  }
  const value = cloneValue(budgetForm.value)
  value.amount = value.amount.trim()
  value.currency = value.currency.trim().toUpperCase()
  value.spend_cap = value.spend_cap?.trim() || null
  if (
    !validMoney(value.amount) ||
    (value.spend_cap !== null && !validMoney(value.spend_cap)) ||
    !/^[A-Z]{3}$/.test(value.currency)
  ) {
    budgetError.value = '请填写合法十进制金额及三位币种，上限1000000'
    return
  }
  target.node.budget = value
  touch()
  budgetOpen.value = false
}
function closeBudget(done: () => void) {
  if (!props.disabled) done()
}
</script>

<style scoped>
.campaign-editor {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}
.tree-pane,
.node-pane {
  min-width: 0;
}
.tree-pane {
  border-right: 1px solid var(--el-border-color);
  padding-right: 12px;
}
.node-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.two-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.node-pane > .el-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 24px;
}
.node-pane > .el-form > .el-alert,
.node-pane > .el-form > .two-columns,
.node-pane > .el-form > .meta-fields {
  grid-column: 1 / -1;
}
.field-count {
  display: block;
  color: var(--el-text-color-secondary);
}
:deep(.el-select) {
  width: 100%;
}
@media (max-width: 700px) {
  .campaign-editor {
    grid-template-columns: 1fr;
  }
  .tree-pane {
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color);
    padding: 0 0 12px;
  }
  .node-pane > .el-form,
  .two-columns {
    grid-template-columns: 1fr;
  }
}
</style>
