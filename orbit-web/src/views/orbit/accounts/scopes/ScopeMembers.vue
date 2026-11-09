<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import {
  getScopeMembers,
  ScopeApiError,
  type ScopeMemberPage,
  type ScopeSnapshot,
} from '@/api/orbit/scopes'

const props = defineProps<{ modelValue: boolean; snapshot: ScopeSnapshot | null }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [snapshot: ScopeSnapshot]
}>()
const search = ref('')
const size = ref(50)
const loading = ref(false)
const error = ref('')
const invalid = ref(false)
const page = ref<ScopeMemberPage | null>(null)
const cursor = ref<string | null>(null)
const previous = ref<(string | null)[]>([])
let active = { q: '', size: 50 }
let controller: AbortController | undefined
let generation = 0
let retry: (() => void) | undefined

/** 即使底层已返回，也只允许当前打开弹窗的最新请求更新页面。 */
function cancel() {
  generation++
  controller?.abort()
  loading.value = false
}
async function load(target: string | null, movement: 'reset' | 'next' | 'previous' = 'reset') {
  if (!props.snapshot || !props.modelValue || invalid.value) return
  cancel()
  const ticket = generation
  controller = new AbortController()
  loading.value = true
  error.value = ''
  retry = () => {
    void load(target, movement)
  }
  try {
    const result = await getScopeMembers(
      props.snapshot.id,
      active.q,
      active.size,
      target,
      controller.signal,
    )
    if (ticket !== generation) return
    if (result.scope_version !== props.snapshot.scope_version)
      throw new ScopeApiError(409, 'SCOPE_CHANGED', '权限版本已变化，请重新冻结范围')
    if (movement === 'next') previous.value.push(cursor.value)
    else if (movement === 'previous') previous.value.pop()
    else previous.value = []
    cursor.value = target
    page.value = result
  } catch (failure) {
    if (ticket !== generation) return
    error.value = failure instanceof Error ? failure.message : '成员读取失败，请重试'
    if (failure instanceof ScopeApiError && [401, 403, 404, 409].includes(failure.status)) {
      invalid.value = true
      page.value = null
    }
  } finally {
    if (ticket === generation) loading.value = false
  }
}
function searchMembers() {
  cancel()
  page.value = null
  previous.value = []
  cursor.value = null
  active = { q: search.value, size: size.value }
  void load(null)
}
function close() {
  cancel()
  emit('update:modelValue', false)
}
function confirmSelection() {
  if (props.snapshot && page.value && !loading.value && !error.value && props.snapshot.count > 0) {
    emit('confirm', props.snapshot)
    close()
  }
}
watch(
  () => [props.modelValue, props.snapshot?.id] as const,
  ([opened]) => {
    cancel()
    page.value = null
    error.value = ''
    invalid.value = false
    search.value = ''
    size.value = 50
    previous.value = []
    cursor.value = null
    active = { q: '', size: 50 }
    if (opened) void load(null)
  },
  { immediate: true },
)
onBeforeUnmount(cancel)
</script>

<template>
  <el-dialog
    class="scope-members-dialog"
    :model-value="modelValue"
    title="账户范围成员"
    width="min(900px, calc(100vw - 32px))"
    top="16px"
    destroy-on-close
    @update:model-value="close"
  >
    <template v-if="snapshot">
      <p>冻结账户 {{ snapshot.count }} 个。搜索仅查看成员，不改变已冻结范围。</p>
      <el-form inline @submit.prevent="searchMembers">
        <el-form-item label="成员搜索">
          <el-input
            v-model="search"
            aria-label="成员搜索"
            placeholder="名称或完整外部账户ID"
            clearable
          />
        </el-form-item>
        <el-form-item label="每页条数">
          <el-select
            v-model="size"
            aria-label="每页条数"
            style="width: 100px"
            @change="searchMembers"
          >
            <el-option
              v-for="value in [20, 50, 100, 200]"
              :key="value"
              :label="String(value)"
              :value="value"
            />
          </el-select>
        </el-form-item>
        <el-button native-type="submit" :disabled="invalid">搜索成员</el-button>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-button v-if="error && !invalid" :disabled="loading" @click="retry?.()"
        >重试本次查询</el-button
      >
      <el-table
        v-loading="loading"
        :data="page?.items || []"
        empty-text="没有匹配的账户"
        max-height="420"
        aria-label="范围成员列表"
      >
        <el-table-column prop="name" label="账户名称" min-width="180" />
        <el-table-column prop="external_id" label="外部账户ID" min-width="260" />
        <el-table-column prop="account_id" label="账户ID" min-width="320" />
      </el-table>
      <p v-if="page">范围数据时间：{{ page.data_as_of }}；权限版本：{{ page.scope_version }}</p>
      <div class="scope-pager">
        <el-button
          :disabled="loading || invalid || !previous.length"
          @click="load(previous[previous.length - 1], 'previous')"
          >上一页</el-button
        >
        <span>第 {{ previous.length + 1 }} 页</span>
        <el-button
          :disabled="loading || invalid || !page?.next_cursor"
          @click="load(page!.next_cursor, 'next')"
          >下一页</el-button
        >
      </div>
    </template>
    <template #footer>
      <el-button @click="close">关闭</el-button>
      <el-button
        type="primary"
        :disabled="loading || !!error || !page || !snapshot?.count"
        @click="confirmSelection"
        >使用此范围</el-button
      >
    </template>
  </el-dialog>
</template>

<style scoped>
/* 弹窗可被传送到body；唯一类名只约束本组件，让页脚在小屏仍可操作。 */
:global(.scope-members-dialog) {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 32px);
  margin-bottom: 16px;
}
:global(.scope-members-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
:global(.scope-members-dialog .el-dialog__header),
:global(.scope-members-dialog .el-dialog__footer) {
  flex-shrink: 0;
}
.scope-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}
</style>
