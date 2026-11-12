<template>
  <section
    v-for="(tier, i) in tiers"
    :key="tier.kind"
    class="prototype-card"
    :data-launch-section="tier.kind"
  >
    <h3>
      {{ i + 2 }}. {{ tier.title
      }}<small v-if="i"
        >属于 {{ campaignName }}{{ i === 2 ? ' / ' + (group?.name || '广告组') : '' }}</small
      >
    </h3>
    <slot v-if="i === 0" name="channel" />
    <div class="prototype-tabs" role="tablist" :aria-label="tier.title">
      <button
        v-for="(n, j) in tier.rows"
        :key="n.local_id"
        type="button"
        role="tab"
        :aria-selected="tier.current?.local_id === n.local_id"
        :class="{ active: tier.current?.local_id === n.local_id }"
        :disabled="disabled"
        @click="ids[i] = n.local_id"
      >
        {{ tier.short }} {{ j + 1 }} · {{ 'name' in n ? n.name : '系列 ' + (j + 1) }}
      </button>
      <button type="button" :disabled="disabled || (i > 0 && !campaign)" @click="add(i)">
        ＋ 新增</button
      ><button type="button" :disabled="disabled || !tier.current" @click="copy(i)">
        复制当前{{ tier.short }}</button
      ><button type="button" :disabled="disabled || tier.rows.length < 2" @click="remove(i)">
        删除
      </button>
    </div>
    <el-form label-width="145px" :disabled="disabled" class="prototype-form">
      <template v-if="i === 0 && campaign">
        <el-form-item label="系列名称 *"
          ><el-input :model-value="campaignName" aria-label="自动生成的系列名称" readonly /><small
            >渠道名称 + 用户昵称 + 年月日 + 自动编号，最终名称由预检生成。</small
          ></el-form-item
        >
        <el-form-item label="购买类型"><el-tag>竞拍</el-tag></el-form-item>
        <el-form-item label="广告系列目标 *"
          ><el-radio-group v-model="campaign.objective"
            ><el-radio-button value="OUTCOME_SALES">销量</el-radio-button
            ><el-radio-button value="OUTCOME_APP_PROMOTION">应用推广</el-radio-button
            ><el-radio-button v-if="campaign.objective === 'OUTCOME_LEADS'" value="OUTCOME_LEADS"
              >潜在客户（已保存）</el-radio-button
            ></el-radio-group
          ></el-form-item
        >
        <el-form-item v-if="campaign.objective === 'OUTCOME_APP_PROMOTION'" label="应用 ID *"
          ><el-input
            :model-value="applicationId"
            :disabled="!form.account_ids.length"
            placeholder="请先选择账户"
            @input="setApplication(String($event))"
          /><small>按已选账户保存应用身份；主页与商店链接在账户身份中核对。</small></el-form-item
        >
        <el-form-item label="预算归属 *"
          ><el-radio-group
            :model-value="campaign.budget ? 'CAMPAIGN' : 'ADSET'"
            @change="setBudgetOwner(campaign, $event as 'CAMPAIGN' | 'ADSET')"
            ><el-radio-button value="CAMPAIGN">广告系列预算</el-radio-button
            ><el-radio-button value="ADSET">广告组预算</el-radio-button></el-radio-group
          ></el-form-item
        >
        <el-form-item v-if="campaign.budget" label="预算金额 *"
          ><div class="inline-fields">
            <el-select v-model="campaign.budget.type" aria-label="预算类型"
              ><el-option label="单日预算" value="DAILY" /><el-option
                label="总预算"
                value="LIFETIME" /></el-select
            ><el-input
              v-model="campaign.budget.amount"
              inputmode="decimal"
              aria-label="预算金额"
            /><span>{{ campaign.budget.currency }}</span>
          </div>
          <small>这是单个系列的预算，复制份数会计入最终合计。</small></el-form-item
        >
        <el-form-item v-if="campaign.budget?.type === 'LIFETIME'" label="结束时间 *"
          ><el-input
            :model-value="campaign.adsets[0]?.end_time || ''"
            placeholder="含时区的时间，例如 2027-01-01T00:00:00+08:00"
            @input="campaign.adsets.forEach((g) => (g.end_time = String($event) || null))"
        /></el-form-item>
        <el-form-item label="竞价策略"
          ><el-tag>{{
            campaign.bid_strategy === 'LOWEST_COST_WITHOUT_CAP'
              ? '最高数量或价值'
              : campaign.bid_strategy || '最高数量或价值'
          }}</el-tag></el-form-item
        >
        <el-form-item label="投放类型"><el-tag>标准</el-tag></el-form-item>
        <el-form-item label="系列花费限额"
          ><el-input
            :model-value="
              campaign.budget?.spend_cap ?? campaign.meta_settings?.spending_limit ?? '0'
            "
            inputmode="decimal"
            @input="setCap(String($event))"
          /><small>0 表示不设限额；限额不是预算。</small></el-form-item
        >
      </template>
      <template v-if="i === 1 && group && campaign">
        <el-form-item label="广告组名称 *"><el-input v-model="group.name" /></el-form-item>
        <el-form-item label="投放地区 *"
          ><el-input
            :model-value="group.country_codes?.join(', ') || ''"
            placeholder="例如 US, CA"
            @input="
              group.country_codes = String($event)
                .split(/[,，\s]+/)
                .filter(Boolean)
                .map((s) => s.toUpperCase())
            "
        /></el-form-item>
        <el-form-item label="年龄范围 *"
          ><div class="inline-fields">
            <el-input-number
              v-model="group.age_min"
              :min="18"
              :max="65"
              :precision="0"
              aria-label="最低年龄"
            /><span>至</span
            ><el-input-number
              v-model="group.age_max"
              :min="18"
              :max="65"
              :precision="0"
              aria-label="最高年龄"
            /></div
        ></el-form-item>
        <el-form-item v-if="!campaign.budget" label="单个组预算 *"
          ><el-input
            :model-value="group.budget?.amount || ''"
            @input="setGroupBudget(String($event))"
          /><span>{{ group.budget?.currency || 'USD' }}</span></el-form-item
        >
        <el-form-item v-else label="预算">由上方广告系列统一分配</el-form-item>
        <el-form-item label="版位"
          ><el-radio-group v-model="group.placements"
            ><el-radio-button value="AUTO">自动版位</el-radio-button
            ><el-radio-button value="MANUAL">手动版位</el-radio-button></el-radio-group
          ></el-form-item
        >
        <el-form-item v-if="group.placements === 'MANUAL'" label="版位配置 *"
          ><el-select :model-value="placementValues" multiple @change="setPlacements"
            ><el-option
              v-for="x in placementOptions"
              :key="x[0]"
              :value="x[0]"
              :label="x[1]" /></el-select
        ></el-form-item>
        <details>
          <summary>更多广告组配置：定向、排期与归因</summary>
          <el-form-item label="性别"
            ><el-radio-group
              :model-value="group.meta_settings?.genders?.[0] || 'ALL'"
              @change="groupMeta().genders = $event === 'ALL' ? [] : [$event as 'MALE' | 'FEMALE']"
              ><el-radio-button value="ALL">不限</el-radio-button
              ><el-radio-button value="MALE">男性</el-radio-button
              ><el-radio-button value="FEMALE">女性</el-radio-button></el-radio-group
            ></el-form-item
          >
          <el-form-item label="语言"
            ><el-input
              :model-value="group.locales?.join(', ') || ''"
              placeholder="语言编号，逗号分隔"
              @input="
                group.locales = String($event)
                  .split(/[,，\s]+/)
                  .filter(Boolean)
              "
          /></el-form-item>
          <el-form-item label="设备"
            ><el-radio-group
              :model-value="
                group.meta_settings?.devices?.platforms?.length === 1 ? 'MOBILE' : 'ALL'
              "
              @change="
                groupMeta().devices = {
                  ...group.meta_settings?.devices,
                  platforms: $event === 'MOBILE' ? ['MOBILE'] : ['MOBILE', 'DESKTOP'],
                }
              "
              ><el-radio-button value="ALL">全部</el-radio-button
              ><el-radio-button value="MOBILE">移动端</el-radio-button></el-radio-group
            ></el-form-item
          >
          <el-form-item label="优化目标"
            ><el-select v-model="group.optimization_goal" filterable
              ><el-option label="转化量最大化" value="OFFSITE_CONVERSIONS" /><el-option
                label="转化价值最大化"
                value="VALUE" /><el-option label="应用安装" value="APP_INSTALLS" /></el-select
          ></el-form-item>
          <el-form-item label="归因窗口"
            ><div class="inline-fields">
              <el-select
                :model-value="group.meta_settings?.attribution_click_days ?? 7"
                @change="groupMeta().attribution_click_days = $event"
                ><el-option :value="1" label="点击1天" /><el-option
                  :value="7"
                  label="点击7天" /></el-select
              ><el-select
                :model-value="group.meta_settings?.attribution_view_days ?? 1"
                @change="groupMeta().attribution_view_days = $event"
                ><el-option :value="0" label="浏览无" /><el-option :value="1" label="浏览1天"
              /></el-select></div
          ></el-form-item>
          <el-form-item label="开始时间"
            ><el-date-picker
              v-model="group.start_time"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              placeholder="选择开始时间" /></el-form-item
          ><el-form-item label="结束时间"
            ><el-date-picker
              v-model="group.end_time"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ssZ"
              placeholder="选择结束时间"
          /></el-form-item>
        </details>
      </template>
      <template v-if="i === 2 && ad">
        <el-form-item label="广告名称 *"><el-input v-model="ad.name" /></el-form-item
        ><el-form-item label="广告标题 *"><el-input v-model="ad.title" /></el-form-item
        ><el-form-item label="正文"
          ><el-input v-model="ad.body" type="textarea" :rows="4" /></el-form-item
        ><el-form-item label="落地页 *"
          ><el-input v-model="ad.url" placeholder="https://"
        /></el-form-item>
        <el-form-item label="行动号召"
          ><el-radio-group v-model="ad.cta"
            ><el-radio-button value="LEARN_MORE">了解更多</el-radio-button
            ><el-radio-button value="SHOP_NOW">立即购买</el-radio-button
            ><el-radio-button
              v-if="ad.cta && !['LEARN_MORE', 'SHOP_NOW'].includes(ad.cta)"
              :value="ad.cta"
              >{{ ad.cta }}（已保存）</el-radio-button
            ></el-radio-group
          ></el-form-item
        >
        <el-form-item label="素材类型要求"
          ><el-select v-model="ad.asset_type"
            ><el-option value="ANY" label="图片或视频" /><el-option
              value="IMAGE"
              label="仅图片" /><el-option value="VIDEO" label="仅视频" /></el-select
          ><small>分配时先满足类型兼容，再尽量均匀。</small></el-form-item
        >
      </template>
    </el-form>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type {
  PlanWrite,
  CampaignConfig,
  AdSetConfig,
  AdConfig,
  ManualPlacements,
} from '@/api/orbit/launch'
import { cloneBranch, newAdSet, newAd } from '@/api/orbit/launch-form'
import { prototypeCampaign, setBudgetOwner } from '@/api/orbit/launch-prototype'
const props = defineProps<{ form: PlanWrite; disabled?: boolean; campaignName: string }>()
const emit = defineEmits<{
  'clone-branch': [Record<string, string>]
  'remove-branch': [string[]]
}>()
const ids = ref(['', '', ''])
const campaign = computed(
  () => props.form.campaigns.find((n) => n.local_id === ids.value[0]) ?? props.form.campaigns[0],
)
const group = computed(
  () =>
    campaign.value?.adsets.find((n) => n.local_id === ids.value[1]) ?? campaign.value?.adsets[0],
)
const ad = computed(
  () => group.value?.ads.find((n) => n.local_id === ids.value[2]) ?? group.value?.ads[0],
)
const tiers = computed(() => [
  {
    kind: 'campaign',
    title: '广告系列设置',
    short: '系列',
    rows: props.form.campaigns,
    current: campaign.value,
  },
  {
    kind: 'adset',
    title: '广告组设置',
    short: '组',
    rows: campaign.value?.adsets ?? [],
    current: group.value,
  },
  { kind: 'ad', title: '广告设置', short: '广告', rows: group.value?.ads ?? [], current: ad.value },
])
type Node = CampaignConfig | AdSetConfig | AdConfig
function children(n: Node): Node[] {
  return 'adsets' in n ? n.adsets : 'ads' in n ? n.ads : []
}
function add(i: number) {
  if (props.disabled) return
  let n: Node
  if (i === 0) {
    n = prototypeCampaign()
    if (n.budget)
      n.budget.currency =
        campaign.value?.budget?.currency ||
        campaign.value?.adsets.find((g) => g.budget)?.budget?.currency ||
        'USD'
  } else if (i === 1) {
    if (!campaign.value) return
    const g = newAdSet(campaign.value.objective)
    g.name = '广告组 ' + (campaign.value.adsets.length + 1)
    g.ads = [newAd()]
    delete g.ads[0].meta_settings
    g.ads[0].cta = 'LEARN_MORE'
    delete g.meta_settings
    if (!campaign.value.budget)
      g.budget = {
        owner: 'ADSET',
        type: 'DAILY',
        amount: '50',
        currency: campaign.value.adsets.find((g) => g.budget)?.budget?.currency || 'USD',
        spend_cap: null,
      }
    n = g
  } else {
    if (!group.value) return
    n = newAd()
    delete n.meta_settings
    n.cta = 'LEARN_MORE'
    n.name = '广告 ' + (group.value.ads.length + 1)
  }
  ;(tiers.value[i].rows as Node[]).push(n)
  ids.value[i] = n.local_id
}
function copy(i: number) {
  const t = tiers.value[i]
  if (props.disabled || !t.current) return
  const n = cloneBranch(t.current)
  n.copies = 1
  const mapping: Record<string, string> = {}
  function map(a: Node, b: Node) {
    mapping[a.local_id] = b.local_id
    children(a).forEach((x, j) => map(x, children(b)[j]))
  }
  map(t.current, n)
  ;(t.rows as Node[]).push(n)
  ids.value[i] = n.local_id
  emit('clone-branch', mapping)
}
async function remove(i: number) {
  const t = tiers.value[i]
  if (props.disabled || !t.current || t.rows.length < 2) return
  try {
    await ElMessageBox.confirm('删除当前配置及其下级配置？素材分配与预览将失效。', '删除当前配置')
  } catch {
    return
  }
  const removed: string[] = []
  function visit(n: Node) {
    removed.push(n.local_id)
    children(n).forEach(visit)
  }
  visit(t.current)
  ;(t.rows as Node[]).splice(t.rows.indexOf(t.current as never), 1)
  emit('remove-branch', removed)
}
function groupMeta() {
  return group.value!.meta_settings ?? (group.value!.meta_settings = {})
}
function setGroupBudget(amount: string) {
  if (group.value)
    group.value.budget = {
      owner: 'ADSET',
      type: 'DAILY',
      currency: 'USD',
      spend_cap: null,
      ...group.value.budget,
      amount,
    }
}
function setCap(value: string) {
  const c = campaign.value
  if (!c) return
  if (c.budget) c.budget.spend_cap = value === '0' ? null : value
  else {
    c.meta_settings ??= {}
    c.meta_settings.spending_limit = value === '0' ? null : value
  }
}
const applicationId = computed(
  () =>
    props.form.identity_bindings
      .flatMap((b) => b.groups)
      .find((g) => campaign.value?.adsets.some((a) => a.local_id === g.adset_local_id))
      ?.application_id || '',
)
function setApplication(value: string) {
  if (!campaign.value) return
  for (const id of props.form.account_ids) {
    let b = props.form.identity_bindings.find((b) => b.account_id === id)
    if (!b) {
      b = { account_id: id, page_id: '', groups: [], ad_overrides: [] }
      props.form.identity_bindings.push(b)
    }
    for (const g of campaign.value.adsets) {
      let row = b.groups.find((x) => x.adset_local_id === g.local_id)
      if (!row) {
        row = {
          adset_local_id: g.local_id,
          pixel_id: null,
          conversion_event: null,
          application_id: null,
          object_store_url: null,
        }
        b.groups.push(row)
      }
      row.application_id = value || null
    }
  }
}
const placementOptions = [
  ['facebook:FEED', 'Facebook Feed'],
  ['facebook:STORY', 'Facebook 快拍'],
  ['facebook:REELS', 'Facebook Reels'],
  ['facebook:RIGHT_COLUMN', 'Facebook 右边栏'],
  ['instagram:STREAM', 'Instagram 动态'],
  ['instagram:STORY', 'Instagram 快拍'],
  ['instagram:REELS', 'Instagram Reels'],
  ['audience_network:CLASSIC', 'Audience Network'],
  ['messenger:INBOX', 'Messenger 收件箱'],
]
const placementValues = computed(() =>
  Object.entries(group.value?.meta_settings?.manual_placements ?? {}).flatMap(([k, v]) =>
    (v as string[]).map((x) => k + ':' + x),
  ),
)
function setPlacements(values: string[]) {
  const result: Record<string, string[]> = {}
  for (const v of values) {
    const [k, x] = v.split(':')
    ;(result[k] ??= []).push(x)
  }
  groupMeta().manual_placements = result as ManualPlacements
}
</script>
