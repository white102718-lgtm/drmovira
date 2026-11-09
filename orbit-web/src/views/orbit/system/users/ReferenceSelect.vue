<template>
  <div class="reference-select">
    <el-select
      :model-value="modelValue"
      :multiple="multiple"
      :multiple-limit="limit"
      filterable
      remote
      :remote-method="search"
      :loading="loading"
      :disabled="disabled"
      :aria-label="label"
      :placeholder="`搜索${label}名称`"
      collapse-tags
      collapse-tags-tooltip
      @visible-change="(visible: boolean) => visible && load(false)"
      @update:model-value="(value: string | string[]) => emit('update:modelValue', value)"
    >
      <el-option v-for="item in options" :key="item.id" :label="item.name" :value="item.id" />
      <template #footer>
        <el-button v-if="cursor" :loading="loading" @click="load(true)">加载更多</el-button>
        <span v-else>已显示当前查询的全部选项</span>
      </template>
    </el-select>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
  </div>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { userApi } from '@/api/orbit/users'
const props = withDefaults(
  defineProps<{
    modelValue: string | string[]
    kind: 'TEAM' | 'ROLE'
    label: string
    multiple?: boolean
    limit?: number
    disabled?: boolean
  }>(),
  { multiple: false, limit: 0 },
)
const emit = defineEmits<{ 'update:modelValue': [value: string | string[]] }>()
const options = ref<{ id: string; name: string }[]>([])
const cursor = ref<string | null>(null),
  query = ref(''),
  loading = ref(false),
  error = ref('')
let generation = 0
let resolution = 0
watch(
  () => props.modelValue,
  async (value) => {
    const sequence = ++resolution
    const selected = (Array.isArray(value) ? value : [value]).filter(Boolean)
    const known = new Set(options.value.map((item) => item.id))
    const missing = selected.filter((id) => !known.has(id))
    try {
      for (let start = 0; start < missing.length; start += 100) {
        const result = await userApi.options(
          new URLSearchParams({
            kind: props.kind,
            page_size: '200',
            ids: missing.slice(start, start + 100).join(','),
          }),
        )
        if (sequence !== resolution) return
        options.value = [
          ...new Map([...options.value, ...result.items].map((item) => [item.id, item])).values(),
        ]
      }
    } catch (cause) {
      if (sequence === resolution)
        error.value = cause instanceof Error ? cause.message : '已选名称读取失败'
    }
  },
  { immediate: true, deep: true },
)
function search(value: string) {
  query.value = value
  return load(false)
}
async function load(more: boolean) {
  const current = ++generation
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ kind: props.kind, q: query.value, page_size: '50' })
  if (more && cursor.value) params.set('cursor', cursor.value)
  try {
    const result = await userApi.options(params)
    if (current !== generation) return
    const selected = new Set(
      Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue],
    )
    // 搜索或翻页不丢失已选名称；每次查询最多增加一页，不能无界预取目录。
    const retained = more ? options.value : options.value.filter((item) => selected.has(item.id))
    options.value = [
      ...new Map([...retained, ...result.items].map((item) => [item.id, item])).values(),
    ]
    cursor.value = result.next_cursor
  } catch (cause) {
    if (current !== generation) return
    error.value = cause instanceof Error ? cause.message : '选项读取失败，请重新搜索'
    cursor.value = null
  } finally {
    if (current === generation) loading.value = false
  }
}
</script>
<style scoped>
.reference-select,
.reference-select :deep(.el-select) {
  width: 100%;
  min-width: 0;
}
</style>
