<template>
  <section class="app-container metric-profiles">
    <h2>指标配置目录</h2>
    <el-alert
      title="目录只展示当前租户可读的版本化指标配置。FIXTURE是测试来源；verified字段及目录读取均不表示广告已创建或生产执行已获授权。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="!canRead"
      title="当前缺少monitor.read权限，指标目录读取已关闭，旧数据已清除。"
      type="warning"
      :closable="false"
    />
    <el-alert
      v-if="error"
      :title="error"
      :type="errorStatus === 503 ? 'warning' : 'error'"
      :closable="false"
    />
    <p v-if="errorStatus === 409" role="status">
      当前权限或目录版本已变化，旧游标已清除，请重新读取首页。
    </p>
    <p v-if="errorStatus === 503" role="status">
      指标配置服务或权威来源尚未就绪；未将失败显示为没有配置。
    </p>
    <el-form
      label-position="top"
      class="profile-filters"
      :disabled="!canRead || !active"
      @submit.prevent="query"
    >
      <el-form-item label="指标UUID搜索（精确匹配）"
        ><el-input
          v-model="q"
          placeholder="完整指标UUID；不按名称或版本模糊搜索"
          clearable
          @keyup.enter="query"
      /></el-form-item>
      <el-form-item label="指标配置ID筛选（精确匹配）"
        ><el-input
          v-model="profileId"
          placeholder="可选完整UUID；与搜索条件取交集"
          clearable
          @keyup.enter="query"
      /></el-form-item>
      <el-form-item label="每页条数"
        ><el-select v-model="pageSize" aria-label="指标配置每页条数"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="String(size)"
            :value="size" /></el-select
      ></el-form-item>
      <el-form-item
        ><el-button native-type="submit" type="primary" :loading="loading"
          >查询指标配置</el-button
        ></el-form-item
      >
    </el-form>
    <div class="profile-actions">
      <el-button :disabled="!canRead || !active || loading" @click="query">重新读取首页</el-button
      ><el-button
        v-if="error && lastIntent"
        :disabled="!canRead || !active || loading"
        @click="retry"
        >重试上次读取</el-button
      >
    </div>
    <p v-if="loaded" role="status">
      第{{ history.length + 1 }}页 · 当前返回{{ items.length }}项 · 数据时间{{ dataAsOf }} ·
      权限版本{{ scopeVersion }}
    </p>
    <el-table
      :data="items"
      row-key="id"
      v-loading="loading"
      :empty-text="loaded ? '当前筛选没有指标配置' : '尚无成功读取的指标配置'"
    >
      <el-table-column prop="id" label="指标ID" min-width="300" /><el-table-column
        prop="version"
        label="配置版本"
        min-width="160"
      />
      <el-table-column label="来源" min-width="160"
        ><template #default="{ row }">{{
          row.source === 'FIXTURE' ? 'FIXTURE（测试配置）' : 'META'
        }}</template></el-table-column
      >
      <el-table-column label="verified声明" width="130"
        ><template #default="{ row }">{{ row.verified ? '是' : '否' }}</template></el-table-column
      >
      <el-table-column prop="maturity_days" label="成熟期（账户当地日）" min-width="170" />
      <el-table-column label="操作" width="120"
        ><template #default="{ row }"
          ><el-button @click="detail = row">查看全部字段</el-button></template
        ></el-table-column
      >
    </el-table>
    <div class="profile-actions">
      <el-button :disabled="!canRead || !active || loading || !history.length" @click="previous"
        >上一页</el-button
      ><el-button :disabled="!canRead || !active || loading || !nextCursor" @click="next"
        >下一页</el-button
      >
    </div>
    <el-dialog
      :model-value="!!detail"
      title="指标配置全部字段"
      width="min(900px, 100vw)"
      append-to-body
      @update:model-value="detail = null"
    >
      <template v-if="detail">
        <el-alert
          :title="
            detail.source === 'FIXTURE'
              ? '此项为FIXTURE测试配置，不能视为Meta生产验证或执行许可。'
              : '此项来源为META；读取配置不代替当前账户、能力、政策及执行授权核验。'
          "
          :type="detail.source === 'FIXTURE' ? 'warning' : 'info'"
          :closable="false"
        />
        <el-descriptions :column="1" border>
          <el-descriptions-item label="id / 指标ID"
            ><span class="profile-wrap">{{ detail.id }}</span></el-descriptions-item
          >
          <el-descriptions-item label="version / 配置版本"
            ><span class="profile-wrap">{{ detail.version }}</span></el-descriptions-item
          >
          <el-descriptions-item label="source / 来源">{{ detail.source }}</el-descriptions-item>
          <el-descriptions-item label="register_action_type / 注册事件"
            ><span class="profile-wrap">{{
              nullable(detail.register_action_type)
            }}</span></el-descriptions-item
          >
          <el-descriptions-item label="purchase_action_type / 购物事件"
            ><span class="profile-wrap">{{
              nullable(detail.purchase_action_type)
            }}</span></el-descriptions-item
          >
          <el-descriptions-item label="value_action_type / 价值事件"
            ><span class="profile-wrap">{{
              nullable(detail.value_action_type)
            }}</span></el-descriptions-item
          >
          <el-descriptions-item label="attribution_windows / 归因窗口"
            ><ul>
              <li
                v-for="(window, index) in detail.attribution_windows"
                :key="index"
                class="profile-wrap"
              >
                {{ window }}
              </li>
            </ul></el-descriptions-item
          >
          <el-descriptions-item label="action_report_time / 行为报告时间"
            ><span class="profile-wrap">{{ detail.action_report_time }}</span></el-descriptions-item
          >
          <el-descriptions-item label="timezone_policy / 时区政策"
            >{{ detail.timezone_policy }}（账户当地时区）</el-descriptions-item
          >
          <el-descriptions-item label="breakdown / 拆分"
            >{{ detail.breakdown }}（总计）</el-descriptions-item
          >
          <el-descriptions-item label="maturity_days / 成熟期"
            >{{ detail.maturity_days }}个账户当地日</el-descriptions-item
          >
          <el-descriptions-item label="verified / 验证声明">{{
            detail.verified ? 'true（是）' : 'false（否）'
          }}</el-descriptions-item>
        </el-descriptions>
      </template>
      <template #footer><el-button @click="detail = null">关闭详情</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import {
  metricProfilesApi,
  MetricProfileError,
  type MetricProfile,
  type MetricProfileQuery,
} from '@/api/orbit/metric-profiles'
const props = withDefaults(defineProps<{ active?: boolean; contextKey?: string }>(), {
  active: true,
  contextKey: '',
})
const user = useUserStore()
const canRead = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('monitor.read'),
)
const context = computed(() =>
  JSON.stringify([
    user.id ?? '',
    [...(user.roles ?? [])].sort(),
    [...user.permissions].sort(),
    props.contextKey,
  ]),
)
const q = ref(''),
  profileId = ref(''),
  pageSize = ref(50),
  items = ref<MetricProfile[]>([]),
  detail = ref<MetricProfile | null>(null),
  loading = ref(false),
  loaded = ref(false),
  error = ref(''),
  errorStatus = ref(0),
  dataAsOf = ref(''),
  scopeVersion = ref<number | null>(null)
const currentCursor = ref<string | null>(null),
  nextCursor = ref<string | null>(null),
  history = ref<(string | null)[]>([])
interface ReadIntent {
  query: MetricProfileQuery
  history: (string | null)[]
  context: string
}
const lastIntent = ref<ReadIntent | null>(null)
let epoch = 0,
  controller: AbortController | undefined
function stop() {
  epoch++
  controller?.abort()
  controller = undefined
  loading.value = false
}
function clear() {
  items.value = []
  detail.value = null
  loaded.value = false
  dataAsOf.value = ''
  scopeVersion.value = null
  currentCursor.value = null
  nextCursor.value = null
  history.value = []
}
const nullable = (value: string | null) =>
  value === null ? '未知（null；未映射，不补默认事件）' : value
function intent(cursor: string | null, previous: (string | null)[]): ReadIntent {
  return {
    query: {
      q: q.value.trim(),
      metric_profile_id: profileId.value.trim() || null,
      page_size: pageSize.value,
      cursor,
    },
    history: [...previous],
    context: context.value,
  }
}
async function read(request: ReadIntent) {
  if (!canRead.value || !props.active || request.context !== context.value) return
  stop()
  const run = epoch
  controller = new AbortController()
  loading.value = true
  error.value = ''
  errorStatus.value = 0
  lastIntent.value = request
  try {
    const result = await metricProfilesApi.list(request.query, controller.signal)
    if (run !== epoch || request.context !== context.value || !canRead.value || !props.active)
      return
    items.value = result.items
    detail.value = null
    dataAsOf.value = result.data_as_of
    scopeVersion.value = result.scope_version
    currentCursor.value = request.query.cursor
    nextCursor.value = result.next_cursor
    history.value = [...request.history]
    loaded.value = true
  } catch (cause) {
    if (run !== epoch || (cause instanceof DOMException && cause.name === 'AbortError')) return
    clear()
    errorStatus.value = cause instanceof MetricProfileError ? cause.status : 0
    error.value =
      errorStatus.value === 403
        ? '当前指标目录读取权限已撤销，请联系管理员或重新登录'
        : errorStatus.value === 401
          ? '登录已失效，请重新登录'
          : errorStatus.value === 409
            ? '权限或指标目录版本已变化，请重新读取首页'
            : errorStatus.value === 503
              ? '指标配置服务或权威来源尚未就绪，请稍后重试'
              : cause instanceof Error
                ? cause.message
                : '指标目录读取失败，请重试'
    if ([401, 403].includes(errorStatus.value)) lastIntent.value = null
    if (errorStatus.value === 409) lastIntent.value = intent(null, [])
  } finally {
    if (run === epoch) loading.value = false
  }
}
function query() {
  return read(intent(null, []))
}
function retry() {
  if (lastIntent.value) return read(lastIntent.value)
}
function next() {
  if (nextCursor.value)
    return read(intent(nextCursor.value, [...history.value, currentCursor.value]))
}
function previous() {
  const previous = [...history.value],
    token = previous.pop()
  if (token !== undefined) return read(intent(token, previous))
}
watch([q, profileId], () => {
  stop()
  clear()
  lastIntent.value = null
  error.value = ''
  errorStatus.value = 0
})
watch(pageSize, () => {
  stop()
  clear()
  lastIntent.value = null
  void query()
})
watch(
  [canRead, context, () => props.active],
  () => {
    stop()
    clear()
    lastIntent.value = null
    error.value = ''
    errorStatus.value = 0
    if (canRead.value && props.active) void query()
  },
  { immediate: true },
)
onBeforeUnmount(stop)
</script>

<style scoped>
.profile-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) 140px auto;
  gap: 14px;
  align-items: end;
  margin-top: 20px;
}
.profile-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0;
}
.profile-wrap {
  overflow-wrap: anywhere;
}
.metric-profiles :deep(.el-alert) {
  margin: 12px 0;
}
.metric-profiles :deep(.el-descriptions) {
  margin-top: 16px;
}
.profile-filters :deep(.el-form-item) {
  margin-bottom: 0;
}
ul {
  margin: 0;
  padding-left: 20px;
}
@media (max-width: 800px) {
  .profile-filters {
    grid-template-columns: 1fr;
  }
  .profile-filters :deep(.el-select) {
    width: 100%;
  }
}
</style>
