<template>
  <el-form
    label-position="top"
    class="metric-query-form"
    :disabled="disabled"
    @submit.prevent="submit"
  >
    <el-form-item label="开始业务日"
      ><el-input v-model="form.date_from" type="date" aria-label="开始业务日"
    /></el-form-item>
    <el-form-item label="结束业务日"
      ><el-input v-model="form.date_to" type="date" aria-label="结束业务日"
    /></el-form-item>
    <el-form-item label="指标配置"
      ><el-select
        v-model="form.metric_profile_id"
        aria-label="指标配置"
        placeholder="选择版本与来源"
        filterable
        remote
        :remote-method="searchProfiles"
        :loading="profileLoading"
        @change="selectProfile"
        ><el-option
          v-for="profile in options"
          :key="profile.id"
          :label="profileLabel(profile)"
          :value="profile.id"
      /></el-select>
      <p class="query-note">输入版本筛选当前页；完整配置ID可精确查询。</p>
      <div class="profile-pages">
        <el-button
          :disabled="profileLoading || !profileIndex"
          @click="loadProfiles(profileHistory[profileIndex - 1] ?? null, profileIndex - 1)"
          >上一页配置</el-button
        ><el-button :disabled="profileLoading || !profileNext" @click="nextProfiles"
          >更多配置</el-button
        ><span>第{{ profileIndex + 1 }}页</span>
      </div>
      <p v-if="profileError" role="alert">{{ profileError }}</p>
      <el-button v-if="profileError" :disabled="profileLoading" @click="loadProfiles(null, 0)"
        >重新读取配置</el-button
      >
      <p v-if="selectedProfile?.source === 'FIXTURE'" role="status">
        此配置为隔离测试样本，请勿用于判断真实投放效果。
      </p>
    </el-form-item>
    <el-form-item label="账户范围"><span>全部当前可见账户</span></el-form-item>
    <el-form-item label="渠道ID（可选）"
      ><el-input
        :model-value="form.channel_id ?? ''"
        aria-label="渠道ID（可选）"
        clearable
        @update:model-value="form.channel_id = optional($event)"
    /></el-form-item>
    <el-form-item label="投放师UUID（可选）"
      ><el-input
        :model-value="form.operator_user_id ?? ''"
        aria-label="投放师UUID（可选）"
        clearable
        @update:model-value="form.operator_user_id = optional($event)"
    /></el-form-item>
    <el-form-item label="名称 / 平台ID"
      ><el-input
        v-model="form.q"
        aria-label="名称 / 平台ID"
        placeholder="名称包含匹配或完整平台ID；最多100码点"
        clearable
    /></el-form-item>
    <el-form-item label="汇总粒度"
      ><el-select v-model="form.granularity" aria-label="汇总粒度"
        ><el-option label="实体汇总" value="SUMMARY" /><el-option
          label="账户当地业务日"
          value="DAY" /></el-select
    ></el-form-item>
    <el-form-item label="排序字段"
      ><el-select v-model="form.sort" aria-label="排序字段"
        ><el-option
          v-for="key in metricSorts"
          :key="key"
          :value="key"
          :label="sortLabels[key]" /></el-select
    ></el-form-item>
    <el-form-item label="排序方向"
      ><el-select v-model="form.direction" aria-label="排序方向"
        ><el-option label="降序" value="DESC" /><el-option label="升序" value="ASC" /></el-select
    ></el-form-item>
    <el-form-item label="每页条数"
      ><el-select v-model="form.page_size" aria-label="指标每页条数"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="String(size)" /></el-select
    ></el-form-item>
    <el-form-item
      ><el-button type="primary" native-type="submit" :loading="loading"
        >查询指标</el-button
      ></el-form-item
    >
    <p v-if="localError" role="alert" class="query-error">{{ localError }}</p>
    <p class="query-note">
      日期为各账户当地业务日的同名日期，含首尾最多93天。未来日期由服务端按账户核验。
    </p>
  </el-form>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  metricProfilesApi,
  MetricProfileError,
  type MetricProfile,
} from '@/api/orbit/metric-profiles'
import {
  metricSorts,
  parseMetricQuery,
  type MetricDataset,
  type MetricQuery,
} from '@/api/orbit/metrics'
const props = withDefaults(
  defineProps<{
    dataset: MetricDataset
    disabled?: boolean
    loading?: boolean
    contextKey?: string
  }>(),
  { disabled: false, loading: false, contextKey: '' },
)
const emit = defineEmits<{ query: [value: MetricQuery]; changed: [] }>()
const initial = (): MetricQuery => ({
  date_from: '',
  date_to: '',
  dataset: props.dataset,
  metric_profile_id: '',
  scope_snapshot_id: null,
  channel_id: null,
  operator_user_id: null,
  q: '',
  sort: 'spend',
  direction: 'DESC',
  cursor: null,
  page_size: 20,
  granularity: 'SUMMARY',
})
const form = reactive<MetricQuery>(initial()),
  localError = ref('')
const profiles = ref<MetricProfile[]>([]),
  selectedProfile = ref<MetricProfile | null>(null)
const profileLoading = ref(false),
  profileLoaded = ref(false),
  profileError = ref(''),
  profileSearch = ref(''),
  profileNext = ref<string | null>(null)
const profileHistory = ref<(string | null)[]>([null]),
  profileIndex = ref(0)
let profileEpoch = 0,
  profileController: AbortController | null = null,
  remoteQuery = '',
  loadingFingerprint = ''
const isUuid = (value: string) => /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value)
const profileLabel = (profile: MetricProfile) =>
  `${profile.version} · ${profile.source === 'FIXTURE' ? '测试样本' : 'META'} · ${profile.verified ? '已登记' : '待核验'} · ${profile.id}`
const options = computed(() => {
  const visible = profiles.value.filter(
    (profile) =>
      !profileSearch.value ||
      isUuid(profileSearch.value) ||
      profileLabel(profile).toLowerCase().includes(profileSearch.value.toLowerCase()),
  )
  return selectedProfile.value &&
    !visible.some((profile) => profile.id === selectedProfile.value?.id)
    ? [selectedProfile.value, ...visible]
    : visible
})
function clearProfiles() {
  profileEpoch++
  profileController?.abort()
  profileController = null
  profileLoading.value = false
  profileLoaded.value = false
  profiles.value = []
  selectedProfile.value = null
  profileError.value = ''
  profileSearch.value = ''
  profileNext.value = null
  profileHistory.value = [null]
  profileIndex.value = 0
  remoteQuery = ''
  loadingFingerprint = ''
}
async function loadProfiles(cursor: string | null, index: number) {
  if (props.disabled) return
  const fingerprint = JSON.stringify([remoteQuery, cursor, index, props.contextKey])
  // ElSelect打开时可同时触发remote-method与visible-change，同意图只发一次GET。
  if (profileLoading.value && loadingFingerprint === fingerprint) return
  profileEpoch++
  profileController?.abort()
  profileController = new AbortController()
  const version = profileEpoch,
    identity = props.contextKey,
    signal = profileController.signal
  profileLoading.value = true
  loadingFingerprint = fingerprint
  profileError.value = ''
  try {
    const page = await metricProfilesApi.list(
      { q: remoteQuery, metric_profile_id: null, cursor, page_size: 50 },
      signal,
    )
    if (version !== profileEpoch || identity !== props.contextKey || signal.aborted) return
    profiles.value = page.items
    profileLoaded.value = true
    profileNext.value = page.next_cursor
    profileIndex.value = index
  } catch (caught) {
    if (version !== profileEpoch || signal.aborted) return
    profiles.value = []
    profileNext.value = null
    profileError.value =
      caught instanceof MetricProfileError && caught.status === 403
        ? '当前无法读取指标配置，请检查权限。'
        : caught instanceof MetricProfileError && caught.status === 409
          ? '配置列表已变化，请重新打开选择。'
          : '配置暂不可用，请重试。'
    if (caught instanceof MetricProfileError && [401, 403].includes(caught.status)) {
      selectedProfile.value = null
      form.metric_profile_id = ''
    }
  } finally {
    if (version === profileEpoch) {
      profileLoading.value = false
      loadingFingerprint = ''
    }
  }
}
function searchProfiles(value: string) {
  profileSearch.value = value
  if (value === '' && remoteQuery === '') return
  if (value === '' || isUuid(value)) {
    remoteQuery = isUuid(value) ? value.toLowerCase() : ''
    profileHistory.value = [null]
    profileIndex.value = 0
    void loadProfiles(null, 0)
  }
}
function nextProfiles() {
  if (!profileNext.value) return
  const index = profileIndex.value + 1
  profileHistory.value = [...profileHistory.value.slice(0, index), profileNext.value]
  void loadProfiles(profileNext.value, index)
}
function selectProfile(value: string) {
  selectedProfile.value =
    profiles.value.find((profile) => profile.id === value) ?? selectedProfile.value
}
const sortLabels = {
  spend: '消耗',
  impressions: '曝光',
  clicks: '点击',
  purchases: '购物',
  roas: 'ROAS',
  cpm: 'CPM',
  name: '名称',
}
const optional = (value: unknown) => (typeof value === 'string' && value !== '' ? value : null)
watch(form, () => {
  localError.value = ''
  emit('changed')
})
watch(
  () => props.dataset,
  (value) => {
    form.dataset = value
    form.cursor = null
  },
)
watch(
  () => props.contextKey,
  () => {
    Object.assign(form, initial())
    localError.value = ''
    clearProfiles()
  },
)
function submit() {
  if (props.disabled) return
  try {
    emit('query', parseMetricQuery({ ...form, dataset: props.dataset, cursor: null }))
  } catch {
    localError.value = '请选择指标配置并检查日期和筛选；日期范围须为1至93个业务日。'
  }
}
watch(
  () => [props.disabled, props.contextKey],
  (value) => {
    if (value[0]) {
      profileEpoch++
      profileController?.abort()
      profileLoading.value = false
    } else if (!profileLoaded.value) void loadProfiles(null, 0)
  },
  { immediate: true },
)
onBeforeUnmount(clearProfiles)
</script>
<style scoped>
.metric-query-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0 16px;
  margin: 20px 0;
}
.query-note,
.query-error {
  grid-column: 1/-1;
  margin: 4px 0;
  line-height: 1.65;
}
.query-note {
  color: var(--el-text-color-regular);
}
.query-error {
  color: var(--el-color-danger);
}
</style>
