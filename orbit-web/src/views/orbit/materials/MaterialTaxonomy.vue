<template>
  <el-drawer
    v-model="visible"
    title="标签与分类管理"
    size="min(760px, 100%)"
    :close-on-click-modal="false"
    :close-on-press-escape="!busy"
    :show-close="!busy"
  >
    <el-tabs v-model="kind" :before-leave="() => !busy && !intent" @tab-change="changeKind">
      <el-tab-pane label="标签" name="tags" /><el-tab-pane label="分类" name="categories" />
    </el-tabs>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="intent"
      title="原请求结果未确认，内容已锁定。关闭重开仍保留同一主体的原意图，只有显式重试才会再次发送。"
      type="warning"
      :closable="false"
    />
    <p v-if="notice" role="status">{{ notice }}</p>
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="名称（1至30字符）" required
        ><el-input v-model="name" aria-label="标签分类名称" maxlength="60" :disabled="locked"
      /></el-form-item>
      <el-form-item v-if="kind === 'tags'" label="标签分组（可选）"
        ><el-input v-model="group" aria-label="标签分组" maxlength="60" :disabled="locked"
      /></el-form-item>
      <el-button
        type="primary"
        :disabled="!can(existing ? 'tags.edit' : 'tags.create') || locked || !identity"
        @click="save"
        >{{ existing ? '保存修改' : '新增' }}</el-button
      >
      <el-button :disabled="locked" @click="reset">取消编辑</el-button>
      <el-button
        v-if="intent"
        type="warning"
        :disabled="busy || !identity || !can(permission(intent.operation))"
        @click="retry"
        >重试原请求</el-button
      >
      <el-button :disabled="busy" @click="initialize">重新核对目录权限</el-button>
    </el-form>
    <template v-if="can('tags.read')">
      <el-form :inline="true" class="taxonomy-filters" @submit.prevent="search">
        <el-form-item label="目录搜索"
          ><el-input v-model="q" maxlength="200" clearable aria-label="目录搜索" :disabled="locked"
        /></el-form-item>
        <el-form-item label="目录状态"
          ><el-select
            v-model="status"
            clearable
            aria-label="目录状态"
            style="width: 110px"
            :disabled="locked"
            ><el-option label="启用" value="ENABLED" /><el-option
              label="停用"
              value="DISABLED" /></el-select
        ></el-form-item>
        <el-form-item label="每页数量"
          ><el-select
            v-model="pageSize"
            aria-label="每页目录数量"
            style="width: 100px"
            :disabled="locked"
            ><el-option
              v-for="size in [20, 50, 100, 200]"
              :key="size"
              :label="String(size)"
              :value="size" /></el-select
        ></el-form-item>
        <el-button :disabled="locked || loading" @click="search">查询目录</el-button>
      </el-form>
      <el-table v-loading="loading" :data="items" empty-text="暂无符合条件的目录项">
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column
          v-if="kind === 'tags'"
          prop="group"
          label="分组"
          min-width="100"
          show-overflow-tooltip
        />
        <el-table-column label="可见素材引用数" width="130"
          ><template #default="{ row }">{{
            row.visible_asset_count ?? '未知'
          }}</template></el-table-column
        >
        <el-table-column label="状态" width="80"
          ><template #default="{ row }">{{
            row.state === 'ENABLED' ? '启用' : '停用'
          }}</template></el-table-column
        >
        <el-table-column label="操作" width="120" fixed="right"
          ><template #default="{ row }">
            <el-button link :disabled="locked || !can('tags.edit')" @click="edit(row)"
              >编辑</el-button
            >
            <el-button
              link
              type="danger"
              :disabled="locked || row.state === 'DISABLED' || !can('tags.archive')"
              @click="beginArchive(row)"
              >停用</el-button
            >
          </template></el-table-column
        >
      </el-table>
      <div class="taxonomy-pagination">
        <el-button :disabled="locked || loading || !history.length" @click="previous"
          >上一页目录</el-button
        ><span>第{{ history.length + 1 }}页</span
        ><el-button :disabled="locked || loading || !cursor" @click="next">下一页目录</el-button>
      </div>
    </template>
    <p v-else>无读取权限；不会读取目录或素材引用数，已授权的新建动作仍可单独使用。</p>
    <p>引用数仅统计当前可读且未归档的素材，不代表广告使用次数。日期及广告事实筛选尚未接入。</p>
    <p>停用标签会保留旧关联，不能新增关联。系统“未分类”不可改名或停用。</p>
    <el-dialog
      v-model="archiveVisible"
      title="停用确认"
      append-to-body
      width="min(500px, calc(100vw - 24px))"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy"
      :show-close="!busy"
    >
      <p>停用 {{ archiveTarget?.name }}；分类仍有关联素材时不能停用。</p>
      <el-input
        v-model="reason"
        type="textarea"
        :rows="3"
        aria-label="停用原因"
        maxlength="2000"
        :disabled="busy"
      />
      <p v-if="archiveError" role="alert">{{ archiveError }}</p>
      <template #footer
        ><el-button :disabled="busy" @click="archiveVisible = false">取消</el-button
        ><el-button type="danger" :loading="busy" @click="archive">确认停用</el-button></template
      >
    </el-dialog>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { MaterialTaxonomy } from '@/api/orbit/materials'
import {
  taxonomyApi,
  taxonomyAuthContext,
  TaxonomyApiError,
  type TaxonomyCapability,
  type TaxonomyIntent,
  type TaxonomyKind,
  type TaxonomyOperation,
} from '@/api/orbit/material-taxonomy'
const props = defineProps<{
  modelValue: boolean
  can: (permission: string) => boolean
  contextKey?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; changed: [] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const kind = ref<TaxonomyKind>('tags'),
  items = ref<MaterialTaxonomy[]>([]),
  cursor = ref<string | null>(null),
  history = ref<string[]>([])
const existing = ref<MaterialTaxonomy>(),
  name = ref(''),
  group = ref(''),
  error = ref(''),
  notice = ref(''),
  busy = ref(false),
  loading = ref(false)
const q = ref(''),
  status = ref(''),
  pageSize = ref(50),
  currentCursor = ref('')
const identity = ref<TaxonomyCapability | null>(null),
  intent = ref<TaxonomyIntent | null>(null)
const archiveVisible = ref(false),
  archiveTarget = ref<MaterialTaxonomy>(),
  reason = ref(''),
  archiveError = ref('')
const pending = new Map<string, TaxonomyIntent>()
const locked = computed(() => busy.value || !!intent.value)
const permission = (operation: TaxonomyOperation) =>
  `tags.${{ READ: 'read', CREATE: 'create', EDIT: 'edit', ARCHIVE: 'archive' }[operation]}`
const identityKey = (value: TaxonomyCapability | TaxonomyIntent) =>
  `${value.tenant_id}:${value.actor_id}`
let generation = 0,
  readGeneration = 0,
  controller: AbortController | undefined,
  auth = '',
  activeFilters = { q: '', status: '', page_size: 50 }
function reset() {
  if (locked.value) return
  existing.value = undefined
  name.value = ''
  group.value = ''
}
function clear() {
  generation++
  readGeneration++
  controller?.abort()
  loading.value = false
  items.value = []
  cursor.value = null
  history.value = []
  currentCursor.value = ''
  identity.value = null
  intent.value = null
  name.value = ''
  group.value = ''
  existing.value = undefined
  archiveVisible.value = false
  archiveTarget.value = undefined
  reason.value = ''
  archiveError.value = ''
  error.value = ''
  notice.value = ''
}
function current(token: number) {
  return token === generation && props.modelValue && auth === taxonomyAuthContext()
}
function denied(e: unknown) {
  if (e instanceof TaxonomyApiError && [401, 403, 404].includes(e.status)) {
    items.value = []
    identity.value = null
    name.value = ''
    group.value = ''
    existing.value = undefined
    archiveVisible.value = false
  }
}
async function initialize() {
  if (busy.value) return
  clear()
  if (!props.modelValue) return
  const operation = (['READ', 'CREATE', 'EDIT', 'ARCHIVE'] as const).find((x) =>
    props.can(permission(x)),
  )
  if (!operation) {
    error.value = '没有标签分类动作权限'
    return
  }
  auth = taxonomyAuthContext()
  const token = generation
  controller = new AbortController()
  loading.value = true
  try {
    const result = await taxonomyApi.capabilities(operation, controller.signal)
    if (!current(token)) return
    identity.value = result
    intent.value = pending.get(identityKey(result)) ?? null
    if (intent.value) {
      kind.value = intent.value.kind
      if ('name' in intent.value.body) {
        name.value = intent.value.body.name
        group.value = intent.value.body.group ?? ''
      }
    }
    if (props.can('tags.read')) await fetchPage('')
  } catch (e) {
    if (current(token)) {
      error.value = e instanceof Error ? e.message : '目录权限读取失败'
      denied(e)
    }
  } finally {
    if (current(token)) loading.value = false
  }
}
async function fetchPage(after: string) {
  if (!props.can('tags.read') || !identity.value) return
  const token = generation,
    read = ++readGeneration
  loading.value = true
  items.value = []
  cursor.value = null
  error.value = ''
  try {
    const page = await taxonomyApi.list(
      kind.value,
      { ...activeFilters, ...(after ? { cursor: after } : {}) },
      controller?.signal,
    )
    if (!current(token) || read !== readGeneration) return
    items.value = page.items
    cursor.value = page.next_cursor
    currentCursor.value = after
  } catch (e) {
    if (current(token) && read === readGeneration) {
      error.value = e instanceof Error ? e.message : '目录读取失败'
      denied(e)
      if (e instanceof TaxonomyApiError && e.status === 409) {
        history.value = []
        currentCursor.value = ''
      }
    }
  } finally {
    if (current(token) && read === readGeneration) loading.value = false
  }
}
async function search() {
  if (locked.value || loading.value) return
  if ([...q.value.normalize('NFC').trim()].length > 100) {
    error.value = '目录搜索最多100字符'
    return
  }
  activeFilters = {
    q: q.value.normalize('NFC').trim(),
    status: status.value,
    page_size: pageSize.value,
  }
  history.value = []
  reset()
  await fetchPage('')
}
async function next() {
  if (locked.value || loading.value || !cursor.value) return
  history.value.push(currentCursor.value)
  await fetchPage(cursor.value)
}
async function previous() {
  if (locked.value || loading.value || !history.value.length) return
  await fetchPage(history.value.pop()!)
}
async function changeKind() {
  if (locked.value) return
  reset()
  history.value = []
  await fetchPage('')
}
function edit(row: MaterialTaxonomy) {
  if (locked.value || !props.can('tags.edit')) return
  existing.value = { ...row }
  name.value = row.name
  group.value = row.group ?? ''
  error.value = ''
  notice.value = ''
}
const validText = (value: string, max: number, min = 0) =>
  [...value].length >= min &&
  [...value].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(value)
async function save() {
  if (locked.value || !identity.value) return
  const operation = existing.value ? 'EDIT' : 'CREATE'
  if (!props.can(permission(operation))) return
  const n = name.value.normalize('NFC').trim(),
    g = group.value.normalize('NFC').trim()
  if (!validText(n, 30, 1) || !validText(g, 30)) {
    error.value = '名称必填且最多30字符；分组最多30字符，不允许控制或隐藏字符'
    return
  }
  await send(
    {
      kind: kind.value,
      operation,
      actor_id: identity.value.actor_id,
      tenant_id: identity.value.tenant_id,
      ...(existing.value ? { id: existing.value.id, revision: existing.value.revision } : {}),
      key: crypto.randomUUID(),
      body: { name: n, ...(kind.value === 'tags' ? { group: g } : {}) },
    },
    false,
  )
}
function beginArchive(row: MaterialTaxonomy) {
  if (locked.value || !props.can('tags.archive')) return
  archiveTarget.value = { ...row }
  reason.value = ''
  archiveError.value = ''
  archiveVisible.value = true
}
async function archive() {
  if (busy.value || !identity.value || !archiveTarget.value || !props.can('tags.archive')) return
  const r = reason.value.normalize('NFC').trim()
  if (!validText(r, 1000, 1)) {
    archiveError.value = '原因须为1至1000字符，不允许控制或隐藏字符'
    return
  }
  const target = archiveTarget.value
  archiveVisible.value = false
  await send(
    {
      kind: kind.value,
      operation: 'ARCHIVE',
      actor_id: identity.value.actor_id,
      tenant_id: identity.value.tenant_id,
      id: target.id,
      revision: target.revision,
      key: crypto.randomUUID(),
      body: { reason: r },
    },
    false,
  )
}
async function retry() {
  if (intent.value && !busy.value) await send(intent.value, true)
}
async function send(original: TaxonomyIntent, recovery: boolean) {
  if (busy.value || !identity.value || !props.can(permission(original.operation))) return
  const token = generation
  busy.value = true
  error.value = ''
  notice.value = ''
  let dispatched = false
  let committed = false
  try {
    const cap = await taxonomyApi.capabilities(original.operation, controller?.signal)
    if (!current(token)) return
    if (identityKey(cap) !== identityKey(original)) {
      clear()
      error.value = '当前登录主体或租户已变化，未发送原请求'
      return
    }
    if (!cap.csrf_token) throw new Error('当前动作没有有效会话校验')
    // 仅在真正发送前保存完整原意图；恢复只更新会话CSRF，不改变正文、键或版本。
    pending.set(identityKey(original), JSON.parse(JSON.stringify(original)) as TaxonomyIntent)
    intent.value = original
    dispatched = true
    const receipt = await taxonomyApi.write(original, cap.csrf_token)
    committed = true
    if (!current(token)) return
    pending.delete(identityKey(original))
    intent.value = null
    existing.value = undefined
    name.value = ''
    group.value = ''
    emit('changed')
    notice.value = props.can('tags.read')
      ? '操作已保存，正在回读当前记录。'
      : '操作已保存；当前无读取权限，未回读目录。'
    if (props.can('tags.read')) {
      const fresh = await taxonomyApi.get(original.kind, receipt.id, controller?.signal)
      if (!current(token)) return
      if (fresh.revision < receipt.revision)
        throw new Error('操作已保存，但回读版本落后，请重新查询')
      notice.value = `已保存并回读：${fresh.name}，版本 ${fresh.revision}，${fresh.state === 'DISABLED' ? '停用' : '启用'}`
      history.value = []
      await fetchPage('')
    }
  } catch (e) {
    if (!current(token)) return
    if (
      dispatched &&
      !recovery &&
      e instanceof TaxonomyApiError &&
      !e.unknown_result &&
      e.status >= 400 &&
      e.status < 500
    ) {
      pending.delete(identityKey(original))
      intent.value = null
    }
    if (committed) notice.value = '操作已保存，但回读未完成。请重新查询，不要重复写入。'
    error.value = e instanceof Error ? e.message : '目录操作结果未确认'
    denied(e)
  } finally {
    busy.value = false
  }
}
watch(
  () => props.modelValue,
  (v) => {
    if (v) void initialize()
    else clear()
  },
  { immediate: true },
)
watch(
  () => [
    props.contextKey,
    ...(['READ', 'CREATE', 'EDIT', 'ARCHIVE'] as const).map((x) => props.can(permission(x))),
  ],
  () => {
    clear()
    if (props.modelValue) void initialize()
  },
)
onBeforeUnmount(() => {
  clear()
  pending.clear()
})
</script>
<style scoped>
.taxonomy-filters {
  margin-top: 20px;
}
.taxonomy-pagination {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 14px;
}
.el-alert {
  margin-bottom: 12px;
}
p {
  overflow-wrap: anywhere;
}
.el-form > .el-button {
  margin-bottom: 8px;
}
</style>
