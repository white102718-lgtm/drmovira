<template>
  <el-drawer
    v-model="visible"
    title="标签与分类管理"
    size="min(760px, 100%)"
    :close-on-click-modal="false"
  >
    <el-tabs v-model="kind" :before-leave="() => !busy" @tab-change="load"
      ><el-tab-pane label="标签" name="tags" /><el-tab-pane label="分类" name="categories"
    /></el-tabs>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form label-position="top" @submit.prevent="save"
      ><el-form-item label="名称（1至30字符）"
        ><el-input v-model="name" maxlength="60" :disabled="busy" /></el-form-item
      ><el-form-item v-if="kind === 'tags'" label="标签分组（可选）"
        ><el-input v-model="group" maxlength="60" :disabled="busy" /></el-form-item
      ><el-button
        type="primary"
        :disabled="!can(existing ? 'tags.edit' : 'tags.create') || busy"
        @click="save"
        >{{ existing ? '保存修改' : '新增' }}</el-button
      ><el-button :disabled="busy" @click="reset">取消编辑</el-button></el-form
    >
    <el-form :inline="true" @submit.prevent="load">
      <el-form-item label="目录搜索"
        ><el-input v-model="q" maxlength="200" clearable aria-label="目录搜索" :disabled="busy"
      /></el-form-item>
      <el-form-item label="目录状态"
        ><el-select
          v-model="status"
          clearable
          aria-label="目录状态"
          style="width: 110px"
          :disabled="busy"
          ><el-option label="启用" value="ENABLED" /><el-option
            label="停用"
            value="DISABLED" /></el-select
      ></el-form-item>
      <el-form-item label="每页数量"
        ><el-select
          v-model="pageSize"
          aria-label="每页目录数量"
          style="width: 100px"
          :disabled="busy"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="String(size)"
            :value="size" /></el-select
      ></el-form-item>
      <el-button :disabled="busy || loading" @click="load">查询目录</el-button>
    </el-form>
    <el-table v-loading="loading" :data="items" style="margin-top: 20px"
      ><el-table-column prop="name" label="名称" min-width="160" /><el-table-column
        v-if="kind === 'tags'"
        prop="group"
        label="分组"
        min-width="100"
      /><el-table-column label="可见素材引用数" width="130"
        ><template #default="{ row }">{{
          row.visible_asset_count ?? '未知'
        }}</template></el-table-column
      ><el-table-column label="状态" width="80"
        ><template #default="{ row }">{{
          row.state === 'ENABLED' ? '启用' : '停用'
        }}</template></el-table-column
      ><el-table-column label="操作" width="130"
        ><template #default="{ row }"
          ><el-button link :disabled="busy || !can('tags.edit')" @click="edit(row)">编辑</el-button
          ><el-button
            link
            type="danger"
            :disabled="busy || row.state === 'DISABLED' || !can('tags.archive')"
            @click="archive(row)"
            >停用</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <el-button v-if="cursor" :loading="loading" @click="loadMore">加载更多</el-button>
    <p>引用数仅统计当前可读且未归档的素材，不代表广告使用次数。日期及广告事实筛选尚未接入。</p>
    <p>停用标签会保留旧关联，不能新增关联。系统“未分类”不可改名或停用。</p>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { materialApi, type MaterialTaxonomy } from '@/api/orbit/materials'
const props = defineProps<{
  modelValue: boolean
  csrf: string
  can: (permission: string) => boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; changed: [] }>()
const visible = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const kind = ref<'tags' | 'categories'>('tags'),
  items = ref<MaterialTaxonomy[]>([]),
  cursor = ref<string | null>(null)
const existing = ref<MaterialTaxonomy>(),
  name = ref(''),
  group = ref(''),
  error = ref(''),
  busy = ref(false),
  loading = ref(false)
const q = ref(''),
  status = ref(''),
  pageSize = ref(50)
let activeFilters = { q: '', status: '', page_size: 50 }
let key = ''
let generation = 0
function reset() {
  existing.value = undefined
  name.value = ''
  group.value = ''
  key = ''
}
function edit(row: MaterialTaxonomy) {
  existing.value = row
  name.value = row.name
  group.value = row.group ?? ''
  key = ''
}
async function load() {
  activeFilters = { q: q.value.trim(), status: status.value, page_size: pageSize.value }
  const epoch = ++generation
  reset()
  cursor.value = null
  items.value = []
  await fetchPage('', epoch)
}
async function fetchPage(after: string, epoch = generation) {
  loading.value = true
  error.value = ''
  try {
    const page = await materialApi.taxonomy(kind.value, after, activeFilters)
    if (epoch !== generation) return
    items.value.push(...page.items)
    cursor.value = page.next_cursor
  } catch (e) {
    if (epoch === generation) error.value = e instanceof Error ? e.message : '目录加载失败'
  } finally {
    if (epoch === generation) loading.value = false
  }
}
async function loadMore() {
  if (cursor.value) await fetchPage(cursor.value)
}
async function save() {
  if (busy.value) return
  error.value = ''
  if (
    !name.value.trim() ||
    [...name.value.trim()].length > 30 ||
    [...group.value.trim()].length > 30
  ) {
    error.value = '名称必填且不超过30字符，分组最多30字符'
    return
  }
  busy.value = true
  key ||= crypto.randomUUID()
  try {
    await materialApi.saveTaxonomy(
      kind.value,
      { name: name.value.trim(), ...(kind.value === 'tags' ? { group: group.value.trim() } : {}) },
      props.csrf,
      key,
      existing.value,
    )
    reset()
    emit('changed')
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
    if ((e as { status?: number }).status) key = ''
  } finally {
    busy.value = false
  }
}
async function archive(row: MaterialTaxonomy) {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入停用原因。分类仍有关联素材时不能停用。',
      '停用确认',
      { inputValidator: (v: string) => !!v?.trim() || '请输入原因' },
    )
    busy.value = true
    await materialApi.archiveTaxonomy(
      kind.value,
      row,
      value.trim(),
      props.csrf,
      crypto.randomUUID(),
    )
    emit('changed')
    await load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') error.value = e instanceof Error ? e.message : '停用失败'
  } finally {
    busy.value = false
  }
}
watch(
  () => props.modelValue,
  (v) => {
    if (v) void load()
  },
  { immediate: true },
)
</script>
