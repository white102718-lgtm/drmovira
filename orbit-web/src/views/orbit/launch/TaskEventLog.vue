<template>
  <section class="task-event-log" aria-label="本次订阅观察记录">
    <h3>本次订阅观察记录</h3>
    <p>仅显示当前订阅在内存保留的最近200条记录，不是完整历史或平台执行成功证明。</p>
    <p role="status">{{ segmentNotice }}</p>
    <p v-if="dropped">较早的{{ dropped }}条记录已移出本地缓存，不能从此处读取。</p>
    <p v-if="pageNotice" role="status">{{ pageNotice }}</p>
    <div class="event-tools">
      <el-select v-model="pageSize" aria-label="每页观察记录" @change="first">
        <el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :label="`${size}条`"
          :value="size"
        />
      </el-select>
      <el-button :disabled="!offset" @click="newer">较新记录</el-button>
      <el-button :disabled="offset + pageSize >= ordered.length" @click="older">较早记录</el-button>
      <el-button :disabled="anchor === null" @click="first">回到最新记录</el-button>
      <span>本地缓存{{ events.length }}条，本页{{ page.length }}条。</span>
    </div>
    <p v-if="!events.length">本次订阅尚未收到观察事件；不代表任务没有历史事件。</p>
    <ol v-else class="event-list">
      <li v-for="event in page" :key="`${segment}:${event.event_id}`">
        <details>
          <summary>
            序号{{ event.sequence }} · {{ event.occurred_at }} · {{ event.state }} · 任务版本{{
              event.task_revision
            }}
          </summary>
          <dl>
            <dt>事件 ID（event_id）</dt>
            <dd>{{ event.event_id }}</dd>
            <dt>事件序号（sequence）</dt>
            <dd>{{ event.sequence }}</dd>
            <dt>结构版本（schema_version）</dt>
            <dd>{{ event.schema_version }}</dd>
            <dt>任务 ID（task_id）</dt>
            <dd>{{ event.task_id }}</dd>
            <dt>任务版本（task_revision）</dt>
            <dd>{{ event.task_revision }}</dd>
            <dt>节点 ID（node_id）</dt>
            <dd>{{ event.node_id ?? '任务级事件（null）' }}</dd>
            <dt>观察状态（state）</dt>
            <dd>{{ event.state }}</dd>
            <dt>发生时间（occurred_at）</dt>
            <dd>{{ event.occurred_at }}</dd>
            <dt>请求编号（request_id）</dt>
            <dd>{{ event.request_id }}</dd>
          </dl>
        </details>
      </li>
    </ol>
  </section>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TaskEvent } from '@/api/orbit/task-events'
const props = defineProps<{
  events: readonly TaskEvent[]
  dropped: number
  segment: number
  segmentNotice: string
}>()
const pageSize = ref(20),
  anchor = ref<number | null>(null),
  pageNotice = ref('')
// observer只交付已校验的连续事件；本地排序和翻页不发额外请求，不解读事件凭证。
const ordered = computed(() => [...props.events].reverse())
const offset = computed(() =>
  anchor.value === null
    ? 0
    : Math.max(
        0,
        ordered.value.findIndex((event) => event.sequence === anchor.value),
      ),
)
const page = computed(() => ordered.value.slice(offset.value, offset.value + pageSize.value))
function first() {
  anchor.value = null
  pageNotice.value = ''
}
function older() {
  anchor.value = ordered.value[offset.value + pageSize.value]?.sequence ?? anchor.value
}
function newer() {
  const position = Math.max(0, offset.value - pageSize.value)
  anchor.value = position ? ordered.value[position].sequence : null
}
watch(
  () => props.segment,
  () => {
    first()
    pageSize.value = 20
  },
)
watch(
  () => props.events,
  () => {
    if (anchor.value !== null && !props.events.some((event) => event.sequence === anchor.value)) {
      first()
      pageNotice.value = '正在查看的较早记录已移出200条缓存，已回到最新记录。'
    }
  },
)
</script>
<style scoped>
.task-event-log {
  min-width: 0;
  margin: 18px 0;
  overflow-wrap: anywhere;
}
.event-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.event-tools :deep(.el-select) {
  width: 150px;
}
.event-list {
  padding-left: 24px;
}
li {
  margin: 12px 0;
}
summary {
  cursor: pointer;
  white-space: pre-wrap;
}
dl {
  display: grid;
  grid-template-columns: minmax(120px, 190px) minmax(0, 1fr);
  gap: 6px;
  white-space: pre-wrap;
}
dt {
  font-weight: 600;
}
dd {
  margin: 0;
  min-width: 0;
}
@media (max-width: 600px) {
  dl {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
