<template>
  <section class="rule-definition-surface">
    <el-form
      class="rule-definition-form"
      label-position="top"
      :disabled="locked"
      @submit.prevent="submit"
    >
      <fieldset>
        <legend>基本信息与作用范围</legend>
        <div class="rule-grid">
          <el-form-item label="规则名称" required :error="errorAt('/name')">
            <el-input
              v-model="form.name"
              aria-label="规则名称"
              placeholder="1至80字，未归档名称不可重复"
              @blur="touch('/name')"
            />
          </el-form-item>
          <el-form-item label="作用对象" required :error="errorAt('/target_level')">
            <el-select v-model="form.target_level" aria-label="作用对象">
              <el-option label="广告系列" value="CAMPAIGN" /><el-option
                label="广告组"
                value="ADSET"
              /><el-option label="广告" value="AD" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属投放师" required :error="errorAt('/ownership')">
            <el-select
              v-model="form.ownership.owner_user_id"
              aria-label="所属投放师"
              filterable
              :loading="ownersLoading"
              :disabled="locked || !owners.length"
              placeholder="从当前可用归属中选择"
              @change="chooseOwner"
            >
              <el-option
                v-for="owner in owners"
                :key="owner.id"
                :label="`${owner.name} · ${owner.team_name}`"
                :value="owner.id"
                :disabled="owner.available === false"
              />
            </el-select>
            <p v-if="!owners.length" class="rule-note" role="status">
              当前没有可用归属人员，暂不能保存。
            </p>
            <p v-if="ownersError" class="rule-error" role="alert">{{ ownersError }}</p>
          </el-form-item>
          <el-form-item label="所属团队" required :error="errorAt('/ownership/owner_team_id')">
            <el-input
              :model-value="selectedOwner?.team_name ?? ''"
              aria-label="所属团队"
              readonly
              placeholder="随投放师显示实际所属团队"
            />
          </el-form-item>
        </div>
        <el-form-item label="作用账户" required :error="errorAt('/scope_snapshot_id')">
          <div class="rule-scope">
            <p v-if="selectedScope">
              {{ selectedScope.label }} · 已冻结 {{ selectedScope.count }} 个账户
            </p>
            <p v-else-if="scope">账户范围与当前归属不匹配或数量尚未核验，请重新选择。</p>
            <p v-else>尚未选择账户范围；未来新账户不会自动加入。</p>
            <slot
              name="scope-picker"
              :ownership="form.ownership"
              :disabled="locked || !selectedOwner"
              :scope="selectedScope"
            >
              <el-button
                :disabled="locked || !selectedOwner"
                @click="emit('choose-scope', { ...form.ownership })"
                >选择账户范围</el-button
              >
            </slot>
          </div>
        </el-form-item>
        <div class="rule-grid">
          <el-form-item label="归因指标配置" required :error="errorAt('/metric_profile_id')">
            <el-select
              v-model="form.metric_profile_id"
              aria-label="归因指标配置"
              filterable
              :loading="profilesLoading"
              :disabled="locked || !profiles.length"
              placeholder="选择当前可用的真实版本"
            >
              <el-option
                v-for="profile in profiles"
                :key="profile.id"
                :value="profile.id"
                :label="`${profile.label} · ${profile.version} · ${profile.id}`"
                :disabled="profile.available === false"
              />
            </el-select>
            <p v-if="selectedProfile" class="rule-note">
              配置版本：{{ selectedProfile.version }}；ID：{{ selectedProfile.id }}
            </p>
            <p v-if="!profiles.length" class="rule-note" role="status">
              当前没有可用指标配置，暂不能保存。
            </p>
            <p v-if="profilesError" class="rule-error" role="alert">{{ profilesError }}</p>
          </el-form-item>
          <el-form-item label="观察窗口" required :error="errorAt('/window')">
            <el-select v-model="form.window" aria-label="观察窗口">
              <el-option label="今天" value="TODAY" /><el-option label="昨天" value="YESTERDAY" />
              <el-option label="近3天（含今天）" value="LAST_3D" /><el-option
                label="近7天（含今天）"
                value="LAST_7D"
              />
            </el-select>
          </el-form-item>
        </div>
      </fieldset>
      <fieldset>
        <legend>命中条件</legend>
        <el-form-item label="组间关系" required :error="errorAt('/logic')">
          <el-select v-model="form.logic" aria-label="组间关系"
            ><el-option label="全部组满足（AND）" value="AND" /><el-option
              label="任意组满足（OR）"
              value="OR"
          /></el-select>
        </el-form-item>
        <p class="rule-note">
          {{ totalConditions }} / 20
          条条件。金额按每个对象的账户币种解释，不换汇、不跨币求和；未知指标不会按0处理。
        </p>
        <section
          v-for="(group, gi) in form.groups"
          :key="gi"
          class="condition-group"
          :aria-label="`条件组${gi + 1}`"
        >
          <div class="condition-heading">
            <h3>条件组 {{ gi + 1 }}</h3>
            <el-button :disabled="locked || form.groups.length <= 1" @click="removeGroup(gi)"
              >删除条件组 {{ gi + 1 }}</el-button
            >
          </div>
          <el-form-item :label="`第${gi + 1}组关系`" :error="errorAt(`/groups/${gi}/logic`)">
            <el-select v-model="group.logic" :aria-label="`第${gi + 1}组关系`"
              ><el-option label="全部满足（AND）" value="AND" /><el-option
                label="任意满足（OR）"
                value="OR"
            /></el-select>
          </el-form-item>
          <div v-for="(condition, ci) in group.conditions" :key="ci" class="condition-row">
            <el-form-item
              :label="`第${gi + 1}组第${ci + 1}条指标`"
              :error="errorAt(`/groups/${gi}/conditions/${ci}/metric`)"
            >
              <el-select v-model="condition.metric" :aria-label="`第${gi + 1}组第${ci + 1}条指标`"
                ><el-option
                  v-for="metric in ruleMetrics"
                  :key="metric"
                  :label="metricLabels[metric]"
                  :value="metric"
              /></el-select>
            </el-form-item>
            <el-form-item
              :label="`第${gi + 1}组第${ci + 1}条比较符`"
              :error="errorAt(`/groups/${gi}/conditions/${ci}/operator`)"
            >
              <el-select
                v-model="condition.operator"
                :aria-label="`第${gi + 1}组第${ci + 1}条比较符`"
                ><el-option
                  v-for="[value, label] in operators"
                  :key="value"
                  :label="label"
                  :value="value"
              /></el-select>
            </el-form-item>
            <el-form-item
              :label="`第${gi + 1}组第${ci + 1}条阈值`"
              :error="errorAt(`/groups/${gi}/conditions/${ci}/threshold`)"
            >
              <el-input
                v-model="condition.threshold"
                inputmode="decimal"
                :aria-label="`第${gi + 1}组第${ci + 1}条阈值`"
                placeholder="必填；非负，最多6位小数"
                @blur="touch(`/groups/${gi}/conditions/${ci}/threshold`)"
              />
            </el-form-item>
            <el-button
              class="remove-condition"
              :disabled="locked || group.conditions.length <= 1"
              @click="removeCondition(gi, ci)"
              >删除第{{ gi + 1 }}组第{{ ci + 1 }}条</el-button
            >
          </div>
          <el-button
            :disabled="locked || group.conditions.length >= 10 || totalConditions >= 20"
            @click="addCondition(gi)"
            >第{{ gi + 1 }}组添加条件</el-button
          >
        </section>
        <el-button
          :disabled="locked || form.groups.length >= 5 || totalConditions >= 20"
          @click="addGroup"
          >添加条件组</el-button
        >
      </fieldset>
      <fieldset>
        <legend>调度与分析额度</legend>
        <div class="rule-grid">
          <el-form-item label="运行方式" required :error="errorAt('/schedule/frequency')">
            <el-select
              v-model="form.schedule.frequency"
              aria-label="运行方式"
              @change="changeFrequency"
              ><el-option label="固定间隔" value="INTERVAL" /><el-option
                label="每天"
                value="DAILY" /><el-option label="每周" value="WEEKLY"
            /></el-select>
          </el-form-item>
          <el-form-item
            v-if="form.schedule.frequency === 'INTERVAL'"
            label="间隔分钟"
            required
            :error="errorAt('/schedule/interval_minutes')"
          >
            <el-input-number
              v-model="form.schedule.interval_minutes"
              aria-label="间隔分钟"
              :min="15"
              :max="1440"
              :precision="0"
            />
          </el-form-item>
          <el-form-item v-else label="执行时刻" required :error="errorAt('/schedule/time_of_day')">
            <el-input v-model="form.schedule.time_of_day" type="time" aria-label="执行时刻" />
          </el-form-item>
          <el-form-item
            v-if="form.schedule.frequency === 'WEEKLY'"
            label="执行星期"
            required
            :error="errorAt('/schedule/weekday')"
          >
            <el-select v-model="form.schedule.weekday" aria-label="执行星期"
              ><el-option v-for="(label, i) in weekdays" :key="i + 1" :label="label" :value="i + 1"
            /></el-select>
          </el-form-item>
          <el-form-item label="调度时区" required :error="errorAt('/schedule/timezone')">
            <el-select
              v-model="form.schedule.timezone"
              aria-label="调度时区"
              filterable
              :disabled="locked || !timezones.length"
              placeholder="请选择明确的调度时区"
              ><el-option
                v-for="zone in timezones"
                :key="zone.value"
                :label="zone.label"
                :value="zone.value"
            /></el-select>
            <p v-if="!timezones.length" class="rule-note">
              调度时区尚未提供，不使用浏览器时区推算。
            </p>
          </el-form-item>
          <el-form-item label="开始日期" required :error="errorAt('/schedule/start_date')"
            ><el-input v-model="form.schedule.start_date" type="date" aria-label="开始日期"
          /></el-form-item>
          <el-form-item label="截止日期" required :error="errorAt('/schedule/end_date')"
            ><el-input v-model="form.schedule.end_date" type="date" aria-label="截止日期"
          /></el-form-item>
          <el-form-item label="分析冷却分钟" required :error="errorAt('/cooldown_minutes')"
            ><el-input-number
              v-model="form.cooldown_minutes"
              aria-label="分析冷却分钟"
              :min="0"
              :max="10080"
              :precision="0"
          /></el-form-item>
          <el-form-item label="每日最多分析次数" required :error="errorAt('/max_daily')"
            ><el-input-number
              v-model="form.max_daily"
              aria-label="每日最多分析次数"
              :min="1"
              :max="1000"
              :precision="0"
          /></el-form-item>
        </div>
        <p class="rule-note">
          起止日期含首尾最多366天。调度时区与账户业务日时区独立；夏令时缺失时刻跳过，重复时刻只运行一次。
        </p>
        <p v-if="errorAt('/schedule')" class="rule-error" role="alert">
          {{ errorAt('/schedule') }}
        </p>
      </fieldset>
      <slot name="schedule-preview" :schedule="cloneSchedule()" />
      <p v-if="!sourcesReady && !readOnly" class="rule-note" role="status">
        保存前需要当前可用归属、指标配置与完整账户范围。
      </p>
      <p v-if="localMessage" class="rule-error" role="alert">{{ localMessage }}</p>
      <ul v-if="visibleServerErrors.length" class="rule-error" role="alert">
        <li v-for="(error, i) in visibleServerErrors" :key="i">{{ error.message }}</li>
      </ul>
    </el-form>
    <div class="rule-actions">
      <el-button :disabled="busy" @click="emit('cancel')">{{
        readOnly ? '关闭' : '取消'
      }}</el-button>
      <el-button
        v-if="!readOnly"
        type="primary"
        :disabled="locked || !sourcesReady"
        :loading="busy"
        @click="submit"
        >保存规则</el-button
      >
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  parseRuleCondition,
  parseRuleSchedule,
  parseRuleWrite,
  ruleMetrics,
  type RuleCondition,
  type RuleMetric,
  type RuleWrite,
} from '@/api/orbit/rules'
import type { PlanHttpFieldError } from '@/api/orbit/launch-validation'

type OwnerOption = {
  id: string
  name: string
  team_id: string
  team_name: string
  available?: boolean
}
type ProfileOption = { id: string; label: string; version: string; available?: boolean }
type ScopeContext = {
  id: string
  label: string
  count: number | null
  owner_user_id: string
  owner_team_id: string
}
const props = withDefaults(
  defineProps<{
    modelValue?: RuleWrite | null
    ownerOptions?: OwnerOption[]
    profileOptions?: ProfileOption[]
    scope?: ScopeContext | null
    savedContext?: { owner: OwnerOption; profile: ProfileOption } | null
    timezones?: { value: string; label: string }[]
    defaults?: { timezone: string; start_date: string; end_date: string }
    fieldErrors?: PlanHttpFieldError[]
    readOnly?: boolean
    disabled?: boolean
    busy?: boolean
    ownersLoading?: boolean
    profilesLoading?: boolean
    ownersError?: string
    profilesError?: string
  }>(),
  {
    modelValue: null,
    ownerOptions: () => [],
    profileOptions: () => [],
    scope: null,
    savedContext: null,
    timezones: () => [],
    fieldErrors: () => [],
    readOnly: false,
    disabled: false,
    busy: false,
    ownersLoading: false,
    profilesLoading: false,
    ownersError: '',
    profilesError: '',
  },
)
// 预览只读槽只获得当前Schedule副本，外部组件不能反向修改表单。
function cloneSchedule() {
  return JSON.parse(JSON.stringify(form.schedule)) as RuleWrite['schedule']
}
const emit = defineEmits<{
  submit: [value: RuleWrite]
  cancel: []
  change: []
  'choose-scope': [ownership: RuleWrite['ownership']]
  'ownership-change': [ownership: RuleWrite['ownership']]
}>()
const metricLabels: Record<RuleMetric, string> = {
  spend: '消耗（账户币种）',
  impressions: '展示次数',
  clicks: '点击次数',
  registrations: '注册次数',
  purchases: '购物次数',
  purchase_value: '购物价值（账户币种）',
  roas: 'ROAS',
  cpm: 'CPM（账户币种）',
  ctr: 'CTR（%）',
  cpc: 'CPC（账户币种）',
  cpa: 'CPA（账户币种）',
}
const operators = [
  ['GT', '大于（>）'],
  ['GTE', '大于等于（≥）'],
  ['LT', '小于（<）'],
  ['LTE', '小于等于（≤）'],
  ['EQ', '等于（=）'],
  ['NEQ', '不等于（≠）'],
]
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const leaf = (): RuleCondition => ({ metric: 'spend', operator: 'GTE', threshold: '' })
const initial = (): RuleWrite => ({
  name: '新建规则',
  ownership: { owner_user_id: '', owner_team_id: '' },
  target_level: 'AD',
  scope_snapshot_id: '',
  logic: 'AND',
  groups: [{ logic: 'AND', conditions: [leaf()] }],
  window: 'LAST_3D',
  metric_profile_id: '',
  schedule: {
    frequency: 'INTERVAL',
    interval_minutes: 30,
    time_of_day: null,
    weekday: null,
    timezone: props.defaults?.timezone ?? '',
    start_date: props.defaults?.start_date ?? '',
    end_date: props.defaults?.end_date ?? '',
  },
  cooldown_minutes: 60,
  max_daily: 5,
})
const form = reactive(initial())
const attempted = ref(false),
  touched = reactive(new Set<string>()),
  localMessage = ref(''),
  ignoreRemote = ref(false)
let hydrating = false
watch(
  () => props.modelValue,
  (value) => {
    hydrating = true
    Object.assign(form, value ? JSON.parse(JSON.stringify(value)) : initial())
    attempted.value = false
    touched.clear()
    localMessage.value = ''
    ignoreRemote.value = false
    hydrating = false
  },
  { immediate: true, deep: true },
)
watch(
  form,
  () => {
    if (!hydrating) {
      ignoreRemote.value = true
      localMessage.value = ''
      emit('change')
    }
  },
  { deep: true, flush: 'sync' },
)
watch(
  () => props.fieldErrors,
  () => {
    ignoreRemote.value = false
  },
  { deep: true },
)
watch(
  () => props.scope,
  (value) => {
    if (
      value &&
      value.owner_user_id === form.ownership.owner_user_id &&
      value.owner_team_id === form.ownership.owner_team_id
    )
      form.scope_snapshot_id = value.id
  },
  { deep: true, immediate: true },
)
const locked = computed(() => props.readOnly || props.disabled || props.busy)
const owners = computed(() => {
  const values = [...props.ownerOptions]
  if (
    props.savedContext &&
    props.modelValue?.ownership.owner_user_id === props.savedContext.owner.id &&
    !values.some((v) => v.id === props.savedContext!.owner.id)
  )
    values.push(props.savedContext.owner)
  return values
})
const profiles = computed(() => {
  const values = [...props.profileOptions]
  if (
    props.savedContext &&
    props.modelValue?.metric_profile_id === props.savedContext.profile.id &&
    !values.some((v) => v.id === props.savedContext!.profile.id)
  )
    values.push(props.savedContext.profile)
  return values
})
const selectedOwner = computed(() => {
  const found = owners.value.filter(
    (v) =>
      v.id === form.ownership.owner_user_id &&
      v.team_id === form.ownership.owner_team_id &&
      v.available !== false,
  )
  return found.length === 1 ? found[0] : null
})
const selectedProfile = computed(() => {
  const found = profiles.value.filter(
    (v) => v.id === form.metric_profile_id && v.available !== false,
  )
  return found.length === 1 ? found[0] : null
})
const selectedScope = computed(() =>
  props.scope &&
  props.scope.id === form.scope_snapshot_id &&
  props.scope.owner_user_id === form.ownership.owner_user_id &&
  props.scope.owner_team_id === form.ownership.owner_team_id &&
  Number.isSafeInteger(props.scope.count) &&
  props.scope.count! >= 1 &&
  props.scope.count! <= 50000
    ? props.scope
    : null,
)
const sourcesReady = computed(
  () =>
    !!selectedOwner.value &&
    !!selectedProfile.value &&
    !!selectedScope.value &&
    props.timezones.some((zone) => zone.value === form.schedule.timezone) &&
    !props.ownersLoading &&
    !props.profilesLoading &&
    !props.ownersError &&
    !props.profilesError,
)
const totalConditions = computed(() =>
  form.groups.reduce((sum, group) => sum + group.conditions.length, 0),
)
const visibleServerErrors = computed(() => (ignoreRemote.value ? [] : props.fieldErrors))
const localErrors = computed(() => {
  const errors: Record<string, string> = {}
  if (
    !form.name.normalize('NFC').trim() ||
    [...form.name.normalize('NFC').trim()].length > 80 ||
    /[\p{Cc}\p{Cf}\p{Cs}]/u.test(form.name)
  )
    errors['/name'] = '规则名称须为1至80字，不能包含控制字符。'
  if (!selectedOwner.value) errors['/ownership'] = '请选择当前可用的归属人员与团队。'
  if (!selectedProfile.value) errors['/metric_profile_id'] = '请选择当前可用的真实指标配置。'
  if (!selectedScope.value) errors['/scope_snapshot_id'] = '请确认1至50000个账户的完整范围。'
  try {
    parseRuleSchedule(form.schedule)
  } catch {
    errors['/schedule'] = '请检查运行频率、时区与起止日期；含首尾最多366天。'
  }
  form.groups.forEach((group, gi) =>
    group.conditions.forEach((condition, ci) => {
      try {
        parseRuleCondition(condition)
      } catch {
        errors[`/groups/${gi}/conditions/${ci}/threshold`] =
          '阈值必填且为非负Decimal；最多6位小数，计数须为整数，并符合指标上限。'
      }
    }),
  )
  if (
    !Number.isInteger(form.cooldown_minutes) ||
    form.cooldown_minutes < 0 ||
    form.cooldown_minutes > 10080
  )
    errors['/cooldown_minutes'] = '冷却分钟须为0至10080的整数。'
  if (!Number.isInteger(form.max_daily) || form.max_daily < 1 || form.max_daily > 1000)
    errors['/max_daily'] = '每日最多分析须为1至1000的整数。'
  return errors
})
function errorAt(path: string) {
  const remote = visibleServerErrors.value.find(
    (v) => v.path === path || (path === '/ownership' && v.path.startsWith(path + '/')),
  )
  return (
    remote?.message ?? (attempted.value || touched.has(path) ? (localErrors.value[path] ?? '') : '')
  )
}
function touch(path: string) {
  touched.add(path)
}
function chooseOwner(value: string) {
  if (locked.value) return
  const option = owners.value.find((v) => v.id === value && v.available !== false)
  form.ownership.owner_team_id = option?.team_id ?? ''
  form.scope_snapshot_id = ''
  emit('ownership-change', { ...form.ownership })
}
function changeFrequency() {
  if (locked.value) return
  const schedule = form.schedule
  if (schedule.frequency === 'INTERVAL') {
    schedule.interval_minutes = 30
    schedule.time_of_day = null
    schedule.weekday = null
  } else {
    schedule.interval_minutes = null
    // DAILY/WEEKLY共用时刻仍适用时保留用户值，只清理不适用字段。
    if (schedule.time_of_day === null) schedule.time_of_day = '10:00'
    schedule.weekday = schedule.frequency === 'WEEKLY' ? (schedule.weekday ?? 1) : null
  }
}
function addGroup() {
  if (!locked.value && form.groups.length < 5 && totalConditions.value < 20)
    form.groups.push({ logic: 'AND', conditions: [leaf()] })
}
function removeGroup(index: number) {
  if (!locked.value && form.groups.length > 1) form.groups.splice(index, 1)
}
function addCondition(index: number) {
  const group = form.groups[index]
  if (!locked.value && group && group.conditions.length < 10 && totalConditions.value < 20)
    group.conditions.push(leaf())
}
function removeCondition(gi: number, ci: number) {
  const group = form.groups[gi]
  if (!locked.value && group?.conditions.length > 1) group.conditions.splice(ci, 1)
}
function submit() {
  if (locked.value) return
  attempted.value = true
  if (!sourcesReady.value) {
    localMessage.value = '当前候选或账户范围尚未完整就绪，请重新选择后保存。'
    return
  }
  try {
    const value = parseRuleWrite(JSON.parse(JSON.stringify(form)))
    if (!props.timezones.some((zone) => zone.value === value.schedule.timezone))
      throw new Error('timezone')
    emit('submit', value)
  } catch {
    localMessage.value = '请修正规则字段后再保存；空阈值不会按0处理。'
  }
}
</script>

<style scoped>
.rule-definition-form {
  min-width: 0;
}
fieldset {
  min-width: 0;
  margin: 0 0 28px;
  padding: 0;
  border: 0;
}
legend {
  margin-bottom: 16px;
  padding: 0;
  color: var(--el-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}
.rule-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}
.el-select,
.el-input-number {
  width: 100%;
}
.rule-note {
  margin: 8px 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.rule-error {
  color: var(--el-color-danger);
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.rule-scope {
  width: 100%;
}
.condition-group {
  margin: 20px 0;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.condition-heading,
.rule-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.condition-heading {
  justify-content: space-between;
  margin-bottom: 12px;
}
h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 14px;
}
.condition-row {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1.2fr) auto;
  gap: 12px;
  align-items: start;
}
.remove-condition {
  margin-top: 30px;
}
.rule-actions {
  justify-content: flex-end;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 20px;
}
@media (max-width: 700px) {
  .rule-grid,
  .condition-row {
    grid-template-columns: minmax(0, 1fr);
  }
  .remove-condition {
    margin-top: 0;
    justify-self: start;
  }
  .condition-row {
    padding-bottom: 16px;
  }
}
</style>
