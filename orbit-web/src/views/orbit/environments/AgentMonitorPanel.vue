<template>
  <section class="agent-monitor" aria-label="可信设备观察">
    <div class="monitor-toolbar">
      <strong>可信设备观察</strong
      ><el-button :loading="loading" :disabled="!active" @click="refresh">刷新监测结果</el-button
      ><el-button :disabled="!active" @click="toggle">{{
        automatic ? '暂停自动刷新' : '恢复自动刷新'
      }}</el-button
      ><span class="muted">{{
        automatic
          ? '每 15 秒读取最近上报，不触发设备探测；机器状态以服务端判定为准'
          : '已暂停，以下为上次报告，不能代表当前可用状态'
      }}</span>
    </div>
    <el-alert v-if="monitorError" :title="monitorError" type="warning" :closable="false" />
    <el-descriptions v-if="report" border :column="2" size="small">
      <el-descriptions-item label="机器状态">{{
        machineLabels[report.machine_state]
      }}</el-descriptions-item
      ><el-descriptions-item label="客户端/API">{{
        apiLabels[report.api_status]
      }}</el-descriptions-item>
      <el-descriptions-item label="最近可信心跳">{{
        report.last_heartbeat || '未知，未收到可信心跳'
      }}</el-descriptions-item
      ><el-descriptions-item label="报告接收时刻">{{
        report.received_at || '未知，尚无报告'
      }}</el-descriptions-item>
      <el-descriptions-item label="Profile 覆盖" :span="2">{{
        coverageLabels[report.inventory_coverage]
      }}</el-descriptions-item>
      <el-descriptions-item label="故障报告" :span="2">{{
        report.last_error || '未报告错误；不代表全部功能正常'
      }}</el-descriptions-item>
    </el-descriptions>
    <el-alert
      v-if="!report"
      title="覆盖范围未知；不能将当前返回的 Profile 当作完整清单。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-else-if="report.inventory_coverage !== 'FULL'"
      :title="coverageLabels[report.inventory_coverage]"
      type="info"
      :closable="false"
    />
    <el-form inline class="profile-query" @submit.prevent="search">
      <el-form-item label="Profile 查询"
        ><el-input v-model="query.q" aria-label="Profile 查询" clearable /></el-form-item
      ><el-form-item label="进程状态"
        ><el-select v-model="query.status" style="width: 140px" clearable
          ><el-option
            v-for="(label, key) in processLabels"
            :key="key"
            :label="label"
            :value="key" /></el-select></el-form-item
      ><el-form-item
        ><el-button :disabled="loading || !active" @click="search"
          >查询 Profile</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert v-if="profilesError" :title="profilesError" type="warning" :closable="false" />
    <el-button v-if="pageStale" :disabled="loading || !active" @click="search"
      >重新读取第一页</el-button
    >
    <el-table
      :data="profiles"
      border
      size="small"
      v-loading="loading"
      empty-text="本次覆盖范围内没有当前可见的 Profile；不代表设备上没有其他 Profile"
    >
      <el-table-column prop="external_profile_id" label="Profile ID" min-width="145" />
      <el-table-column v-if="selectable" label="选择" width="130"
        ><template #default="{ row }"
          ><el-button link type="primary" :disabled="loading || !active" @click="select(row)"
            >选择此 Profile</el-button
          ></template
        ></el-table-column
      >
      <el-table-column label="最近报告进程" width="120"
        ><template #default="{ row }">{{
          processLabels[row.process_state as keyof typeof processLabels]
        }}</template></el-table-column
      >
      <el-table-column label="最近报告身份" min-width="190"
        ><template #default="{ row }">{{
          identityLabels[row.identity_state as keyof typeof identityLabels]
        }}</template></el-table-column
      >
      <el-table-column label="账户 ID" min-width="260"
        ><template #default="{ row }">{{
          row.account_ids.length ? row.account_ids.join('、') : '无当前可见账户关联'
        }}</template></el-table-column
      >
      <el-table-column prop="observed_at" label="观察时刻" min-width="200" /><el-table-column
        prop="id"
        label="Profile 内部 ID"
        min-width="290"
      /><el-table-column prop="agent_id" label="Agent ID" min-width="290" />
    </el-table>
    <div class="monitor-toolbar">
      <el-select
        v-model="pageSize"
        style="width: 120px"
        :disabled="loading || !active"
        @change="search"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :value="size"
          :label="`${size} 条/页`" /></el-select
      ><el-button :disabled="loading || !active || index === 0 || pageStale" @click="move(-1)"
        >Profile 上一页</el-button
      ><span>第 {{ index + 1 }} 页</span
      ><el-button :disabled="loading || !active || !nextCursor || pageStale" @click="move(1)"
        >Profile 下一页</el-button
      ><span v-if="dataAsOf" class="muted">读取时刻 {{ dataAsOf }}</span>
    </div>
    <p class="muted">
      UNKNOWN：未取得新鲜身份核验结果。看到 Meta 登录主页或 Profile
      存在，都不能证明广告账户、币种或操作能力匹配。身份结果由服务端按独立可信报告和时效判定，选择
      Profile 不会改变核验状态。
    </p>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { AgentApiError } from '@/api/orbit/environments'
import {
  monitorApi,
  type AgentMonitor,
  type ObservedProfile,
  type ProfileQuery,
} from '@/api/orbit/environments-monitor'
const props = withDefaults(
  defineProps<{
    agentId: string
    active?: boolean
    selectable?: boolean
    contextKey?: string
    refreshKey?: number
  }>(),
  { active: true, selectable: false, contextKey: '', refreshKey: 0 },
)
const emit = defineEmits<{ select: [externalProfileId: string]; monitor: [report: AgentMonitor] }>()
const machineLabels = {
  READY: '心跳正常',
  SUSPECT: '心跳疑似中断',
  OFFLINE: '离线',
  REVOKED: '已撤销',
}
const apiLabels = {
  READY: '本地 API 可达',
  UNREACHABLE: '本地 API 不可达',
  AUTH_FAILED: '本地 API 认证失败',
  UNKNOWN: '未知，缺少新鲜报告',
}
const coverageLabels = {
  FULL: '完整清单（仍按当前权限裁剪）',
  ACTIVE_ONLY: '仅活跃 Profile，不代表完整清单；完整盘点可能受客户端套餐或权限限制。',
  UNAVAILABLE: 'Profile 盘点不可用或报告已过期，覆盖范围未知。',
}
const processLabels = { ACTIVE: '活跃', INACTIVE: '未活跃', UNKNOWN: '未知' }
const identityLabels = {
  VALID: '身份有效（服务端核验）',
  LOGIN_REQUIRED: '需要登录',
  CHALLENGE: '需要人工处理',
  IDENTITY_MISMATCH: '账户身份不匹配',
  UNKNOWN: '未取得新鲜身份核验',
}
const report = ref<AgentMonitor | null>(null),
  profiles = ref<ObservedProfile[]>([]),
  monitorError = ref(''),
  profilesError = ref(''),
  dataAsOf = ref(''),
  loading = ref(false),
  automatic = ref(true),
  pageStale = ref(false)
const query = reactive({ q: '', status: '' }),
  pageSize = ref(20),
  index = ref(0),
  nextCursor = ref<string | null>(null)
let cursors: (string | undefined)[] = [undefined],
  applied: ProfileQuery = { page_size: 20 },
  generation = 0,
  controller: AbortController | undefined,
  timer: ReturnType<typeof setTimeout> | undefined
function cancel() {
  generation++
  controller?.abort()
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
  loading.value = false
}
function readableError(e: unknown, kind: 'monitor' | 'profiles') {
  const area = kind === 'monitor' ? '监测' : 'Profile'
  if (e instanceof AgentApiError) {
    if (e.status === 401) return '登录已失效，请重新登录后读取'
    if (e.status === 403) return kind === 'monitor' ? '无监测读取权限' : '无 Profile 读取权限'
    if (e.status === 404) return `${area}不存在或已不在当前账户绑定范围`
    if (e.status === 409) return 'Profile 数据或授权范围已变化，请重新读取第一页'
  }
  return e instanceof Error ? e.message : `${area}读取失败，当前状态未知`
}
async function refresh() {
  if (!props.active || loading.value) return
  if (timer !== undefined) clearTimeout(timer)
  timer = undefined
  const current = ++generation
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  const results = await Promise.allSettled([
    monitorApi.get(props.agentId, signal),
    monitorApi.profiles(props.agentId, { ...applied, cursor: cursors[index.value] }, signal),
  ])
  if (current !== generation) return
  const [monitorResult, profileResult] = results
  if (monitorResult.status === 'fulfilled') {
    report.value = monitorResult.value
    monitorError.value = ''
    emit('monitor', monitorResult.value)
  } else {
    report.value = null
    monitorError.value = readableError(monitorResult.reason, 'monitor')
  }
  if (profileResult.status === 'fulfilled') {
    profiles.value = profileResult.value.items
    dataAsOf.value = profileResult.value.data_as_of
    nextCursor.value = profileResult.value.next_cursor
    profilesError.value = ''
    pageStale.value = false
  } else {
    profiles.value = []
    dataAsOf.value = ''
    nextCursor.value = null
    profilesError.value = readableError(profileResult.reason, 'profiles')
    pageStale.value =
      profileResult.reason instanceof AgentApiError && profileResult.reason.status === 409
  }
  loading.value = false
  if (props.active && automatic.value)
    timer = setTimeout(() => {
      void refresh()
    }, 15000)
}
function toggle() {
  automatic.value = !automatic.value
  if (!automatic.value) cancel()
  else void refresh()
}
function search() {
  if (!props.active || loading.value) return
  const q = query.q.normalize('NFC').trim()
  if ([...q].length > 100 || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(query.q)) {
    profilesError.value = 'Profile 查询最多 100 个字符且不能含控制字符'
    return
  }
  applied = {
    page_size: pageSize.value,
    ...(q ? { q } : {}),
    ...(query.status ? { status: query.status } : {}),
  }
  index.value = 0
  cursors = [undefined]
  pageStale.value = false
  void refresh()
}
function move(delta: number) {
  if (loading.value || !props.active || pageStale.value) return
  if (delta > 0) {
    if (!nextCursor.value) return
    cursors[index.value + 1] = nextCursor.value
  }
  index.value += delta
  void refresh()
}
function select(row: ObservedProfile) {
  if (props.selectable && props.active && !loading.value) emit('select', row.external_profile_id)
}
watch(
  () => [props.agentId, props.active, props.contextKey],
  () => {
    cancel()
    report.value = null
    profiles.value = []
    monitorError.value = ''
    profilesError.value = ''
    dataAsOf.value = ''
    nextCursor.value = null
    pageStale.value = false
    index.value = 0
    cursors = [undefined]
    applied = { page_size: pageSize.value }
    query.q = ''
    query.status = ''
    if (props.active) void refresh()
  },
  { immediate: true },
)
// 探测完成只刷新当前查询，不把查询条件误当成身份上下文而清空。
watch(
  () => props.refreshKey,
  () => {
    if (props.active) void refresh()
  },
)
onBeforeUnmount(cancel)
</script>
<style scoped>
.agent-monitor {
  margin-top: 20px;
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.monitor-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin: 14px 0;
}
.profile-query {
  margin-top: 16px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.el-alert {
  margin: 12px 0;
}
@media (max-width: 600px) {
  .profile-query :deep(.el-form-item) {
    display: flex;
    margin-right: 0;
  }
  .profile-query :deep(.el-form-item__content) {
    min-width: 0;
  }
}
</style>
