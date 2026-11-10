<template>
  <section class="meta-sync-status" aria-label="Meta采集状态">
    <div class="sync-toolbar">
      <strong>数据采集</strong>
      <el-button
        size="small"
        :disabled="!active"
        :loading="loading"
        @click="open ? reload() : show()"
        >{{ open ? '刷新采集状态' : '查看采集状态' }}</el-button
      >
      <el-button v-if="open" size="small" text @click="close">收起</el-button>
    </div>
    <template v-if="open">
      <p class="sync-hint">只有完整发布的数据才进入统计。采集失败不会清空上次已发布的数据。</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" role="alert" />
      <el-table
        v-loading="loading"
        :data="page?.items || []"
        size="small"
        empty-text="暂无关联Meta连接的可见账户"
        style="width: 100%"
      >
        <el-table-column prop="account_name" label="账户" min-width="160" show-overflow-tooltip />
        <el-table-column label="本次状态" width="150"
          ><template #default="{ row }"
            ><el-tag
              :type="
                row.latest_job?.state === 'FAILED'
                  ? 'danger'
                  : row.latest_job?.state === 'PUBLISHED'
                    ? 'success'
                    : 'info'
              "
              >{{
                row.latest_job ? labels[row.latest_job.state as MetaSyncState] : '尚未采集'
              }}</el-tag
            ></template
          ></el-table-column
        >
        <el-table-column label="最近完整发布" min-width="180"
          ><template #default="{ row }">{{
            formatTime(row.last_published_at)
          }}</template></el-table-column
        >
        <el-table-column label="本次更新时间" min-width="180"
          ><template #default="{ row }">{{
            formatTime(row.latest_job?.updated_at)
          }}</template></el-table-column
        >
        <el-table-column label="采集业务日" min-width="200"
          ><template #default="{ row }">{{
            row.latest_job ? `${row.latest_job.date_from} 至 ${row.latest_job.date_to}` : '未知'
          }}</template></el-table-column
        >
        <el-table-column label="进度与重试" min-width="180"
          ><template #default="{ row }"
            ><template v-if="row.latest_job"
              >已保存 {{ row.latest_job.page_number }} 页 · 第
              {{ row.latest_job.attempts }} 次尝试<span
                v-if="['WAIT_REPORT', 'RETRY_WAIT'].includes(row.latest_job.state)"
                >；下次 {{ formatTime(row.latest_job.next_run_at) }}</span
              ></template
            ><template v-else>未知</template></template
          ></el-table-column
        >
        <el-table-column label="指标口径 / 适配版本" min-width="210"
          ><template #default="{ row }">{{
            row.latest_job
              ? `${row.latest_job.profile_version} / ${row.latest_job.adapter_version}`
              : '未知'
          }}</template></el-table-column
        >
        <el-table-column label="失败原因" min-width="200"
          ><template #default="{ row }">{{
            row.latest_job?.last_error ? errors[row.latest_job.last_error] || '采集未通过验证' : '—'
          }}</template></el-table-column
        >
      </el-table>
      <div class="sync-toolbar sync-pager">
        <span>状态读取于 {{ formatTime(page?.data_as_of) }}</span
        ><el-button size="small" :disabled="loading || !history.length" @click="previous"
          >上一页</el-button
        ><el-button size="small" :disabled="loading || !page?.next_cursor" @click="next"
          >下一页</el-button
        >
      </div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { metaSyncApi, type MetaSyncState, type MetaSyncStatusPage } from '@/api/orbit/meta-sync'
import { ReferenceApiError } from '@/api/orbit/references'
const props = withDefaults(
  defineProps<{ active?: boolean; contextKey?: string; accountId?: string }>(),
  { active: true, contextKey: '' },
)
const open = ref(false),
  loading = ref(false),
  error = ref(''),
  page = ref<MetaSyncStatusPage | null>(null),
  history = ref<(string | null)[]>([]),
  cursor = ref<string | null>(null)
let controller: AbortController | undefined,
  epoch = 0
const labels: Record<MetaSyncState, string> = {
  INVENTORY: '核对账户与广告对象',
  CAPTURING: '采集中',
  SEALED: '等待完整发布',
  PUBLISHED: '已完整发布',
  RETRY_WAIT: '等待重试',
  WAIT_REPORT: '等待Meta报表',
  FAILED: '采集失败',
}
const errors: Record<string, string> = {
  META_RATE_LIMITED: 'Meta读取限流，等待重试',
  META_TRANSIENT_FAILURE: 'Meta暂时不可用',
  META_AUTH_FAILED: '连接授权已失效，请重新授权',
  META_READ_FORBIDDEN: '缺少Meta读取权限',
  META_RESPONSE_INVALID: 'Meta返回数据未通过校验',
  META_COLLECTION_UNVERIFIED: '采集范围或来源尚未验证',
}
function formatTime(v?: string | null) {
  return v ? new Date(v).toLocaleString() : '尚无记录'
}
function stop() {
  epoch++
  controller?.abort()
  loading.value = false
}
function close() {
  stop()
  open.value = false
  page.value = null
  error.value = ''
  history.value = []
  cursor.value = null
}
async function load(target: string | null, old: (string | null)[]) {
  if (!props.active) return
  stop()
  const own = epoch
  controller = new AbortController()
  loading.value = true
  error.value = ''
  page.value = null
  try {
    const result = await metaSyncApi.status(target, props.accountId, controller.signal)
    if (own !== epoch) return
    page.value = result
    cursor.value = target
    history.value = old
  } catch (e) {
    if (own !== epoch) return
    error.value = e instanceof ReferenceApiError ? e.message : '采集状态读取失败，请刷新'
    if (e instanceof ReferenceApiError && [401, 403, 409].includes(e.status)) {
      history.value = []
      cursor.value = null
    }
  } finally {
    if (own === epoch) loading.value = false
  }
}
function show() {
  open.value = true
  void reload()
}
function reload() {
  return load(null, [])
}
function next() {
  if (page.value?.next_cursor) void load(page.value.next_cursor, [...history.value, cursor.value])
}
function previous() {
  if (history.value.length) void load(history.value.at(-1) ?? null, history.value.slice(0, -1))
}
watch(() => [props.active, props.contextKey, props.accountId], close)
onBeforeUnmount(stop)
</script>
<style scoped>
.meta-sync-status {
  margin: 12px 0;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  min-width: 0;
}
.sync-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.sync-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 10px 0;
}
.sync-pager {
  margin-top: 10px;
}
.sync-pager span {
  margin-right: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 600px) {
  .meta-sync-status {
    padding: 10px;
  }
  .sync-pager span {
    flex-basis: 100%;
  }
}
</style>
