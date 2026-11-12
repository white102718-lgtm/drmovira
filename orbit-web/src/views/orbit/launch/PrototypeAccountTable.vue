<template>
  <div class="prototype-accounts">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="account-search">
      <el-input
        v-model="q"
        aria-label="搜索可选账户"
        placeholder="搜索名称 / 完整账户ID"
        clearable
        @keyup.enter="load('')"
      /><el-button :disabled="loading || disabled" @click="load('')">查询</el-button
      ><el-button class="select-page" :disabled="loading || disabled" @click="selectPage"
        >选择当前筛选中的可用账户</el-button
      >
    </div>
    <el-checkbox v-model="onlySelected">只看已选</el-checkbox>
    <slot name="owner" />
    <div class="selected-tags">
      已选 {{ selected.length }} 个
      <el-tag v-for="id in selected" :key="id" :closable="!disabled" @close="toggle(id, false)">{{
        names.get(id)?.name || id
      }}</el-tag>
    </div>
    <el-table :data="visible" v-loading="loading" row-key="id">
      <el-table-column label="选择" width="60"
        ><template #default="{ row }"
          ><el-checkbox
            :model-value="selected.includes(row.id)"
            :aria-label="`选择 ${row.name}`"
            :disabled="disabled || (!eligible(row) && !selected.includes(row.id))"
            @change="toggle(row.id, Boolean($event))" /></template
      ></el-table-column>
      <el-table-column label="账户名称 / ID" min-width="190"
        ><template #default="{ row }"
          >{{ row.name }}<small>{{ row.external_id }}</small></template
        ></el-table-column
      >
      <el-table-column label="账户状态"
        ><template #default="{ row }"
          ><el-tag>{{
            row.account_status === 'ACTIVE'
              ? '正常'
              : row.account_status === 'DISABLED'
                ? '停用'
                : '未知'
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="授权"
        ><template #default="{ row }">{{
          row.auth_status === 'AUTHORIZED'
            ? '有效'
            : row.auth_status === 'EXPIRED'
              ? '过期'
              : row.auth_status === 'REVOKED'
                ? '已撤销'
                : '未知'
        }}</template></el-table-column
      >
      <el-table-column label="余额"
        ><template #default="{ row }"
          >{{ row.balance?.amount ?? '—' }} {{ row.balance?.currency || row.currency
          }}<small>{{ row.balance?.observed_at || '尚无余额观测' }}</small></template
        ></el-table-column
      >
      <el-table-column label="身份资产" width="115"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            :disabled="disabled || !selected.includes(row.id)"
            @click="$emit('identity')"
            >主页 / 像素</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-button v-if="cursor" :disabled="loading || disabled" @click="load(cursor)"
      >加载更多账户</el-button
    >
    <small>仅可选择当前负责人名下、授权有效的账户；余额未知时不补零。</small>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { accountApi, type OrbitAccount } from '@/api/orbit/accounts'
import type { PlanOwnership } from '@/api/orbit/launch'
const props = defineProps<{
  selected: string[]
  ownership: PlanOwnership
  disabled?: boolean
  canRead?: boolean
  contextKey?: string
}>()
const emit = defineEmits<{ 'update:selected': [string[], string | null]; identity: [] }>()
const q = ref(''),
  onlySelected = ref(false),
  rows = ref<OrbitAccount[]>([]),
  names = ref(new Map<string, OrbitAccount>()),
  cursor = ref<string | null>(null),
  loading = ref(false),
  error = ref('')
let epoch = 0
const visible = computed(() =>
  onlySelected.value
    ? [...names.value.values()].filter((r) => props.selected.includes(r.id))
    : rows.value,
)
const eligible = (r: OrbitAccount) =>
  r.ownership.owner_user_id === props.ownership.owner_user_id &&
  r.ownership.owner_team_id === props.ownership.owner_team_id &&
  r.auth_status === 'AUTHORIZED' &&
  r.account_status === 'ACTIVE'
function toggle(id: string, on: boolean) {
  if (props.disabled) return
  const row = names.value.get(id)
  if (on && (!row || !eligible(row) || props.selected.length >= 500)) return
  publish(on ? [...new Set([...props.selected, id])] : props.selected.filter((x) => x !== id))
}
function publish(ids: string[]) {
  const currencies = new Set(ids.map((id) => names.value.get(id)?.currency).filter(Boolean))
  emit('update:selected', ids, currencies.size === 1 ? [...currencies][0]! : null)
}
function selectPage() {
  if (props.disabled) return
  publish(
    [...new Set([...props.selected, ...rows.value.filter(eligible).map((r) => r.id)])].slice(
      0,
      500,
    ),
  )
}
async function load(after: string) {
  if (!props.canRead) return
  const own = ++epoch
  loading.value = true
  error.value = ''
  try {
    const p = await accountApi.list(
      new URLSearchParams({ page_size: '50', q: q.value, ...(after ? { cursor: after } : {}) }),
    )
    if (own !== epoch) return
    rows.value = after ? [...rows.value, ...p.items] : p.items
    p.items.forEach((r) => names.value.set(r.id, r))
    cursor.value = p.next_cursor
  } catch (e) {
    if (own === epoch) {
      error.value = e instanceof Error ? e.message : '账户读取失败'
      rows.value = []
      cursor.value = null
    }
  } finally {
    if (own === epoch) loading.value = false
  }
}
watch(
  () => [
    props.ownership.owner_user_id,
    props.ownership.owner_team_id,
    props.canRead,
    props.contextKey,
  ],
  () => {
    epoch++
    rows.value = []
    names.value = new Map()
    cursor.value = null
    loading.value = false
    void load('')
  },
  { immediate: true },
)
onBeforeUnmount(() => epoch++)
</script>
<style scoped>
.account-search {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.account-search .el-input {
  width: 280px;
}
.select-page {
  margin-left: auto;
}
.selected-tags {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin: 16px 0;
}
small {
  display: block;
  font-size: 12px;
  color: #8290a5;
  margin: 5px 0;
}
@media (max-width: 650px) {
  .account-search {
    flex-wrap: wrap;
  }
  .select-page {
    margin-left: 0;
  }
}
</style>
