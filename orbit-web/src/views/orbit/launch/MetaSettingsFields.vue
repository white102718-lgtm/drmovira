<template>
  <div ref="root" class="meta-fields">
    <p v-if="!modelValue" class="legacy-note">
      此配置未设置 Meta 扩展选项。展开查看不会修改原草稿。
    </p>
    <div v-for="advanced in [false, true]" :key="String(advanced)" class="meta-group">
      <button
        v-if="advanced"
        type="button"
        class="advanced-toggle"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : '展开' }}高级配置{{
          kind === 'adset' ? ' · 版位与设备' : kind === 'campaign' ? ' · 花费限额' : ' · 广告排期'
        }}
      </button>
      <div v-if="!advanced || expanded" class="meta-grid">
        <el-form-item
          v-for="field in fields.filter((item) => item.advanced === advanced && visible(item))"
          :key="field.path"
          :label="field.label"
          :data-meta-path="field.path"
        >
          <el-switch
            v-if="field.type === 'switch'"
            :model-value="read(field.path) === true"
            :disabled="disabled"
            @change="write(field.path, $event)"
          />
          <el-select
            v-else-if="field.type === 'select' || field.type === 'multi'"
            :model-value="read(field.path) as string | number | string[] | number[] | undefined"
            :multiple="field.type === 'multi'"
            :multiple-limit="field.limit ?? 100"
            :allow-create="
              field.type === 'multi' &&
              !field.options &&
              !field.countries &&
              field.path !== 'carousel_asset_ids'
            "
            filterable
            clearable
            :disabled="disabled"
            placeholder="未设置"
            @update:model-value="write(field.path, $event)"
          >
            <el-option
              v-for="option in options(field)"
              :key="String(option.value)"
              :value="option.value"
              :label="option.label"
            />
          </el-select>
          <el-input
            v-else
            :model-value="(read(field.path) as string) ?? ''"
            :disabled="disabled"
            :placeholder="field.path.includes('time') ? '2027-01-01T00:00:00+08:00' : '未设置'"
            @update:model-value="write(field.path, $event)"
          />
        </el-form-item>
      </div>
    </div>
    <p v-if="kind === 'adset'" class="legacy-note">
      手动版位请在上方选择“手动版位”。版位与设备型号须经账户能力核验；历史或撤销选项保留展示。事件须与逐账户身份绑定一致。
    </p>
    <p v-if="kind === 'adset' && read('audience_mode') === 'ADVANTAGE'" class="legacy-note">
      Advantage 受众的建议项与严格限制范围须经当前账户能力核验，保存草稿不代表平台已采用这些限制。
    </p>
    <p v-if="kind === 'campaign'" class="legacy-note">
      CBO 使用系列预算；ABO
      使用广告组预算。切换后已有预算保留，请在预算配置中显式调整，冲突会阻止保存。
    </p>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { CampaignMetaSettings, AdSetMetaSettings, AdMetaSettings } from '@/api/orbit/launch'
import { launchCountries } from '@/api/orbit/launch-countries'
type Meta = CampaignMetaSettings | AdSetMetaSettings | AdMetaSettings
type Field = {
  path: string
  label: string
  type: string
  advanced: boolean
  options?: { value: string | number; label: string }[]
  limit?: number
  countries?: boolean
}
const props = defineProps<{
  kind: 'campaign' | 'adset' | 'ad'
  modelValue?: Meta | null
  disabled?: boolean
  bidStrategy?: string
  placements?: string
  assetIds?: string[]
  objective?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [Meta] }>()
const root = ref<HTMLElement>(),
  expanded = ref(false),
  revealed = ref('')
const definitions: Record<string, Field[]> = {
  campaign: [
    {
      path: 'spending_limit',
      label: '系列花费限额',
      type: 'input',
      advanced: true,
    },
    {
      path: 'advantage_campaign_budget',
      label: 'Advantage 系列预算（CBO）',
      type: 'switch',
      advanced: false,
    },
    {
      path: 'bid_amount',
      label: '单次成效费用目标 / 竞价上限',
      type: 'input',
      advanced: false,
    },
    {
      path: 'roas_goal',
      label: 'ROAS 目标',
      type: 'input',
      advanced: false,
    },
  ],
  adset: [
    {
      path: 'conversion_location',
      label: '转化位置',
      type: 'select',
      options: [
        {
          value: 'WEBSITE',
          label: '网站',
        },
        {
          value: 'APP',
          label: '应用',
        },
      ],
      advanced: false,
    },
    {
      path: 'conversion_event',
      label: '转化事件',
      type: 'select',
      options: [
        {
          value: 'ADD_TO_CART',
          label: '加入购物车',
        },
        {
          value: 'PURCHASE',
          label: '购物',
        },
        {
          value: 'COMPLETE_REGISTRATION',
          label: '完成注册',
        },
        {
          value: 'LEAD',
          label: '潜在客户',
        },
        {
          value: 'SUBSCRIBE',
          label: '订阅',
        },
      ],
      advanced: false,
    },
    {
      path: 'attribution_click_days',
      label: '点击归因窗口（天）',
      type: 'select',
      options: [
        {
          value: 1,
          label: '1',
        },
        {
          value: 7,
          label: '7',
        },
      ],
      advanced: false,
    },
    {
      path: 'attribution_view_days',
      label: '浏览归因窗口（天）',
      type: 'select',
      options: [
        {
          value: 0,
          label: '0',
        },
        {
          value: 1,
          label: '1',
        },
      ],
      advanced: false,
    },
    {
      path: 'audience_mode',
      label: '受众模式',
      type: 'select',
      options: [
        {
          value: 'ORIGINAL',
          label: '普通受众',
        },
        {
          value: 'ADVANTAGE',
          label: 'Advantage 受众',
        },
      ],
      advanced: false,
    },
    {
      path: 'excluded_country_codes',
      label: '排除地区（国家）',
      type: 'multi',
      countries: true,
      limit: 50,
      advanced: false,
    },
    {
      path: 'genders',
      label: '性别（留空不限）',
      type: 'multi',
      options: [
        {
          value: 'MALE',
          label: '男性',
        },
        {
          value: 'FEMALE',
          label: '女性',
        },
      ],
      limit: 2,
      advanced: false,
    },
    {
      path: 'excluded_custom_audience_ids',
      label: '排除自定义受众 ID',
      type: 'multi',
      limit: 100,
      advanced: true,
    },
    {
      path: 'manual_placements.facebook',
      label: 'Facebook 版位',
      type: 'multi',
      options: [
        {
          value: 'FEED',
          label: '动态',
        },
        {
          value: 'STORY',
          label: '快拍',
        },
        {
          value: 'REELS',
          label: 'Reels 短视频',
        },
        {
          value: 'RIGHT_COLUMN',
          label: '右侧栏',
        },
        {
          value: 'MARKETPLACE',
          label: 'Marketplace',
        },
        {
          value: 'VIDEO_FEEDS',
          label: '视频动态（待核验）',
        },
        {
          value: 'SEARCH',
          label: '搜索结果',
        },
        {
          value: 'INSTREAM_VIDEO',
          label: '插播视频（待核验）',
        },
        {
          value: 'PROFILE_FEED',
          label: '个人主页动态',
        },
        {
          value: 'REELS_OVERLAY',
          label: 'Reels 覆盖广告（待核验）',
        },
      ],
      limit: 10,
      advanced: true,
    },
    {
      path: 'manual_placements.instagram',
      label: 'Instagram 版位',
      type: 'multi',
      options: [
        {
          value: 'STREAM',
          label: '动态',
        },
        {
          value: 'STORY',
          label: '快拍',
        },
        {
          value: 'REELS',
          label: 'Reels 短视频',
        },
        {
          value: 'EXPLORE',
          label: '探索',
        },
        {
          value: 'EXPLORE_HOME',
          label: '探索首页',
        },
        {
          value: 'PROFILE_FEED',
          label: '个人主页动态',
        },
        {
          value: 'SEARCH',
          label: '搜索结果',
        },
        {
          value: 'PROFILE_REELS',
          label: '个人主页 Reels',
        },
      ],
      limit: 8,
      advanced: true,
    },
    {
      path: 'manual_placements.messenger',
      label: 'Messenger 版位',
      type: 'multi',
      options: [
        {
          value: 'INBOX',
          label: '收件箱',
        },
        {
          value: 'STORY',
          label: '快拍',
        },
        {
          value: 'SPONSORED_MESSAGES',
          label: '赞助消息（待核验）',
        },
      ],
      limit: 3,
      advanced: true,
    },
    {
      path: 'manual_placements.audience_network',
      label: 'Audience Network 版位',
      type: 'multi',
      options: [
        {
          value: 'CLASSIC',
          label: '原生、横幅与插屏',
        },
        {
          value: 'REWARDED_VIDEO',
          label: '激励视频',
        },
        {
          value: 'INSTREAM_VIDEO',
          label: '插播视频（待核验）',
        },
      ],
      limit: 3,
      advanced: true,
    },
    {
      path: 'manual_placements.threads',
      label: 'Threads 版位',
      type: 'multi',
      limit: 1,
      options: [{ value: 'FEED', label: '动态' }],
      advanced: true,
    },
    {
      path: 'inventory_filter',
      label: 'Facebook / Instagram 内容库存',
      type: 'select',
      options: [
        {
          value: 'FULL',
          label: '全部库存',
        },
        {
          value: 'STANDARD',
          label: '标准库存',
        },
        {
          value: 'LIMITED',
          label: '有限库存',
        },
      ],
      advanced: true,
    },
    {
      path: 'audience_network_inventory_filter',
      label: 'Audience Network 内容库存',
      type: 'select',
      options: [
        {
          value: 'FULL',
          label: '全部库存',
        },
        {
          value: 'STANDARD',
          label: '标准库存',
        },
        {
          value: 'LIMITED',
          label: '有限库存',
        },
      ],
      advanced: true,
    },
    {
      path: 'devices.platforms',
      label: '设备平台（留空不限）',
      type: 'multi',
      options: [
        {
          value: 'MOBILE',
          label: '移动设备',
        },
        {
          value: 'DESKTOP',
          label: '桌面设备',
        },
      ],
      limit: 2,
      advanced: true,
    },
    {
      path: 'devices.operating_systems',
      label: '操作系统（留空不限）',
      type: 'multi',
      options: [
        {
          value: 'ANDROID',
          label: 'Android',
        },
        {
          value: 'IOS',
          label: 'iOS',
        },
      ],
      limit: 2,
      advanced: true,
    },
    {
      path: 'devices.android_models',
      label: '包含 Android 型号',
      type: 'multi',
      limit: 100,
      advanced: true,
    },
    {
      path: 'devices.excluded_android_models',
      label: '排除 Android 型号',
      type: 'multi',
      limit: 100,
      advanced: true,
    },
    {
      path: 'devices.excluded_ios_models',
      label: '排除 iOS 型号',
      type: 'multi',
      limit: 100,
      advanced: true,
    },
    {
      path: 'devices.ios_models',
      label: '包含 iOS 型号',
      type: 'multi',
      limit: 100,
      advanced: true,
    },
    {
      path: 'devices.android_min_version',
      label: 'Android 最低版本',
      type: 'input',
      advanced: true,
    },
    {
      path: 'devices.android_max_version',
      label: 'Android 最高版本',
      type: 'input',
      advanced: true,
    },
    {
      path: 'devices.ios_min_version',
      label: 'iOS 最低版本',
      type: 'input',
      advanced: true,
    },
    {
      path: 'devices.ios_max_version',
      label: 'iOS 最高版本',
      type: 'input',
      advanced: true,
    },
  ],
  ad: [
    {
      path: 'format',
      label: '广告格式',
      type: 'select',
      options: [
        {
          value: 'SINGLE',
          label: '单图片 / 视频',
        },
        {
          value: 'CAROUSEL',
          label: '轮播',
        },
      ],
      advanced: false,
    },
    {
      path: 'start_time',
      label: '广告开始时间（含时区）',
      type: 'input',
      advanced: true,
    },
    {
      path: 'end_time',
      label: '广告结束时间（含时区）',
      type: 'input',
      advanced: true,
    },
    {
      path: 'carousel_asset_ids',
      label: '轮播素材 ID（按顺序 2—10 个）',
      type: 'multi',
      limit: 10,
      advanced: false,
    },
  ],
}
const fields = computed(() => definitions[props.kind])
function visible(field: Field) {
  if (revealed.value === field.path) return true
  if (field.path === 'bid_amount')
    return ['COST_CAP', 'LOWEST_COST_WITH_BID_CAP'].includes(props.bidStrategy ?? '')
  if (field.path === 'roas_goal') return props.bidStrategy === 'LOWEST_COST_WITH_MIN_ROAS'
  if (field.path.startsWith('manual_placements.')) return props.placements === 'MANUAL'
  if (field.path === 'carousel_asset_ids') return read('format') === 'CAROUSEL'
  if (/devices\.(excluded_)?android_/.test(field.path))
    return (read('devices.operating_systems') as string[] | undefined)?.includes('ANDROID') ?? false
  if (/devices\.(excluded_)?ios_/.test(field.path))
    return (read('devices.operating_systems') as string[] | undefined)?.includes('IOS') ?? false
  return true
}
function read(path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (value, key) =>
        value && typeof value === 'object' ? (value as Record<string, unknown>)[key] : undefined,
      props.modelValue,
    )
}
function options(field: Field) {
  const choices =
    field.path === 'carousel_asset_ids'
      ? (props.assetIds ?? []).map((value) => ({ value, label: value }))
      : field.countries
        ? launchCountries.map((value) => ({ value, label: value }))
        : [...(field.options ?? [])]
  if (field.path === 'conversion_event') {
    for (let index = choices.length - 1; index >= 0; index--) {
      const value = choices[index].value
      if (
        (value === 'PURCHASE' && props.objective !== 'OUTCOME_SALES') ||
        (value === 'LEAD' && props.objective !== 'OUTCOME_LEADS') ||
        props.objective === 'OUTCOME_APP_PROMOTION'
      )
        choices.splice(index, 1)
    }
  }
  const value = read(field.path)
  for (const item of Array.isArray(value)
    ? value
    : value === undefined || value === null
      ? []
      : [value]) {
    if (!choices.some((option) => option.value === item))
      choices.push({ value: item, label: `${item}（已保存，待能力核验）` })
  }
  return choices
}
function write(path: string, value: unknown) {
  if (props.disabled || !fields.value.some((field) => field.path === path)) return
  const result = JSON.parse(JSON.stringify(props.modelValue ?? {})) as Record<string, unknown>
  const keys = path.split('.')
  let node = result
  for (const key of keys.slice(0, -1)) {
    node[key] ??= {}
    node = node[key] as Record<string, unknown>
  }
  const key = keys[keys.length - 1]
  if (value === '' || value === undefined || value === null) delete node[key]
  else node[key] = value
  emit('update:modelValue', result as Meta)
}
async function focusField(path: string[]) {
  let key = path.join('.')
  if (key === 'manual_placements') key = 'manual_placements.facebook'
  if (key === 'devices') key = 'devices.platforms'
  const arrayMember = /^(0|[1-9]\d*)$/.test(path[path.length - 1] ?? '')
  if (arrayMember) key = path.slice(0, -1).join('.')
  const field = fields.value.find((item) => item.path === key)
  if (!field || props.disabled || (arrayMember && field.type !== 'multi')) return false
  revealed.value = field.path
  if (field.advanced) expanded.value = true
  await nextTick()
  const target = root.value?.querySelector<HTMLElement>(
    `[data-meta-path="${key}"] input:not([disabled]), [data-meta-path="${key}"] button:not([disabled])`,
  )
  target?.scrollIntoView?.({ block: 'nearest' })
  target?.focus()
  return !!target && document.activeElement === target
}
defineExpose({ focusField })
</script>
<style scoped>
.meta-fields {
  margin-top: 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 20px;
}
.meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 24px;
}
.advanced-toggle {
  border: 0;
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
  border-radius: 8px;
  padding: 12px 16px;
  margin: 4px 0 20px;
  cursor: pointer;
  text-align: left;
  width: 100%;
}
.legacy-note {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
  font-size: 12px;
}
@media (max-width: 700px) {
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
