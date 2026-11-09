<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="min(1000px, 96vw)"
    :close-on-click-modal="false"
    :before-close="close"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="kind === 'accounts'"
      title="只可选择当前负责人同团队账户；保存时服务端再次验证双方读取权限和单一币种。"
      type="info"
      :closable="false"
    />
    <div class="picker-tools">
      <el-input
        v-model="q"
        placeholder="搜索名称"
        clearable
        :disabled="loading || disabled"
        @keyup.enter="read('')"
      /><el-button :disabled="loading || disabled" @click="read('')">搜索</el-button
      ><el-switch v-model="onlySelected" active-text="仅看已选" :disabled="disabled" /><el-button
        :disabled="loading || disabled || onlySelected"
        @click="selectPage"
        >选择本页可用项</el-button
      >
    </div>
    <p role="status" :aria-busy="loading">
      已选 {{ selection.size }}/{{ limit }} · 当前页 {{ rows.length }} 项
    </p>
    <el-table v-loading="loading" :data="displayRows" row-key="id" height="360" style="width: 100%">
      <el-table-column label="选择" width="64"
        ><template #default="scope"
          ><el-checkbox
            :model-value="selection.has(scope.row.id)"
            :disabled="disabled || (!scope.row.eligible && !selection.has(scope.row.id))"
            :aria-label="`选择${scope.row.label}`"
            @change="toggle(scope.row, Boolean($event))" /></template
      ></el-table-column>
      <el-table-column prop="label" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="summary" label="当前资料" min-width="180" show-overflow-tooltip />
      <el-table-column label="可选状态" width="120"
        ><template #default="scope"
          ><el-tag :type="scope.row.eligible ? 'success' : 'info'">{{
            scope.row.eligible ? '候选可选' : '当前不可选'
          }}</el-tag></template
        ></el-table-column
      >
    </el-table>
    <div class="picker-tools">
      <el-button :disabled="loading || disabled" @click="read('')">重新读取首页</el-button
      ><el-button
        v-if="nextCursor && !onlySelected"
        :disabled="loading || disabled"
        @click="read(nextCursor)"
        >下一页候选</el-button
      ><el-button v-if="selection.size" :disabled="disabled" @click="selection = new Set()"
        >清除全部已选</el-button
      >
    </div>
    <template #footer
      ><el-button :disabled="disabled" @click="emit('update:modelValue', false)">取消</el-button
      ><el-button :disabled="disabled || loading" type="primary" @click="confirm"
        >确认选择 {{ selection.size }} 项</el-button
      ></template
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { OrbitAccount } from '@/api/orbit/accounts'
import type { Channel } from '@/api/orbit/channels'
import type { MaterialAsset } from '@/api/orbit/materials'
import type { PlanOwnership } from '@/api/orbit/launch'
import { referenceRequest } from '@/api/orbit/references'
export interface PickedSource {
  id: string
  label: string
  summary: string
  eligible: boolean
}
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    kind: 'accounts' | 'assets' | 'channels'
    selected: string[]
    ownership: PlanOwnership
    disabled?: boolean
  }>(),
  { disabled: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; choose: [ids: string[]] }>()
const title = computed(
  () => ({ accounts: '选择账户', assets: '选择素材池', channels: '选择渠道' })[props.kind],
)
const limit = computed(() => (props.kind === 'channels' ? 1 : 500))
const q = ref(''),
  rows = ref<PickedSource[]>([]),
  labels = ref(new Map<string, PickedSource>()),
  selection = ref(new Set<string>()),
  nextCursor = ref<string | null>(null),
  onlySelected = ref(false),
  loading = ref(false),
  error = ref('')
let epoch = 0
const displayRows = computed(() =>
  onlySelected.value
    ? [...selection.value].map(
        (id) =>
          labels.value.get(id) ?? {
            id,
            label: '已保存关联（名称尚未加载）',
            summary: id,
            eligible: false,
          },
      )
    : rows.value,
)
watch(
  () => props.modelValue,
  async (open) => {
    if (!open) {
      epoch++
      return
    }
    q.value = ''
    selection.value = new Set(props.selected)
    labels.value = new Map()
    onlySelected.value = false
    await read('')
  },
  { immediate: true },
)
async function read(cursor: string) {
  if (props.disabled) return
  const ownEpoch = ++epoch
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({
      page_size: '50',
      ...(q.value.trim() ? { q: q.value.normalize('NFC').trim() } : {}),
      ...(cursor ? { cursor } : {}),
    })
    const result = await referenceRequest<{
      items: (OrbitAccount | MaterialAsset | Channel)[]
      next_cursor: string | null
    }>(`/${props.kind}?${params}`)
    if (ownEpoch !== epoch || !props.modelValue) return
    rows.value = result.items.map((item) => {
      if (props.kind === 'accounts') {
        const row = item as OrbitAccount
        return {
          id: row.id,
          label: row.name || row.external_id,
          summary: `${row.external_id} · ${row.currency} · ${row.auth_status}`,
          eligible:
            row.ownership.owner_user_id === props.ownership.owner_user_id &&
            row.ownership.owner_team_id === props.ownership.owner_team_id,
        }
      }
      if (props.kind === 'assets') {
        const row = item as MaterialAsset
        return {
          id: row.id,
          label: row.name,
          summary: `${row.kind} · ${row.state}`,
          eligible:
            row.state === 'READY' && row.ownership.owner_team_id === props.ownership.owner_team_id,
        }
      }
      const row = item as Channel
      return {
        id: row.id,
        label: row.name || row.code,
        summary: `${row.code} · ${row.type} · ${row.status}`,
        eligible:
          row.status === 'ENABLED' &&
          row.ownership.owner_team_id === props.ownership.owner_team_id &&
          row.ownership.data_owner_user_ids.includes(props.ownership.owner_user_id),
      }
    })
    const cache = new Map([...labels.value].filter(([id]) => selection.value.has(id)))
    rows.value.forEach((row) => cache.set(row.id, row))
    labels.value = cache
    nextCursor.value = result.next_cursor
  } catch (cause) {
    if (ownEpoch === epoch) {
      error.value = cause instanceof Error ? cause.message : '候选读取失败，请重试'
      nextCursor.value = null
    }
  } finally {
    if (ownEpoch === epoch) loading.value = false
  }
}
function toggle(row: PickedSource, checked: boolean) {
  if (props.disabled) return
  const ids = new Set(selection.value)
  if (!checked) ids.delete(row.id)
  else {
    if (!row.eligible) return
    if (limit.value === 1) ids.clear()
    ids.add(row.id)
  }
  if (ids.size > limit.value) {
    error.value = `最多选择${limit.value}项，原选择未被截断`
    return
  }
  selection.value = ids
  error.value = ''
}
function selectPage() {
  if (props.disabled) return
  const ids = new Set(selection.value)
  rows.value.filter((row) => row.eligible).forEach((row) => ids.add(row.id))
  if (ids.size > limit.value) {
    error.value = `本页合并后超过${limit.value}项，请逐项选择，原选择保持不变`
    return
  }
  selection.value = ids
}
function confirm() {
  if (props.disabled || loading.value) return
  emit('choose', [...selection.value])
  emit('update:modelValue', false)
}
function close(done: () => void) {
  if (!props.disabled) {
    epoch++
    done()
  }
}
</script>

<style scoped>
.picker-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0;
}
.picker-tools :deep(.el-input) {
  width: min(300px, 100%);
}
</style>
