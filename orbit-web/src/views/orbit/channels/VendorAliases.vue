<template>
  <section class="vendor-alias-section" aria-label="当前户商代称">
    <div class="alias-toolbar">
      <h3>当前户商代称</h3>
      <el-button :loading="loading" @click="load">刷新代称</el-button>
    </div>
    <el-alert
      title="代称来自单独维护的真实值，未设置显示未知。修改后当前账户显示同步更新，历史日志保留原快照。完整名称不会自动截断为代称。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-table v-loading="loading" :data="vendors" border>
      <el-table-column prop="value.name" label="户商完整名称" min-width="180" />
      <el-table-column label="当前代称" min-width="150"
        ><template #default="{ row }">{{
          aliases[row.value.id]?.alias ?? '未知'
        }}</template></el-table-column
      >
      <el-table-column label="代称版本" width="100"
        ><template #default="{ row }">{{
          aliases[row.value.id]?.revision ?? '未读取'
        }}</template></el-table-column
      >
      <el-table-column label="维护UTC时间" min-width="200"
        ><template #default="{ row }">{{
          aliases[row.value.id]?.updated_at ?? '尚未维护'
        }}</template></el-table-column
      >
      <el-table-column v-if="canManage" label="代称操作" width="120"
        ><template #default="{ row }"
          ><el-button link type="primary" :disabled="loading" @click="open(row)"
            >维护代称</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-dialog
      v-model="opened"
      title="维护户商代称"
      width="600px"
      class="vendor-alias-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy && !uncertain"
      :show-close="!busy && !uncertain"
      :before-close="close"
    >
      <el-alert v-if="dialogError" :title="dialogError" type="error" :closable="false" />
      <el-alert
        v-if="uncertain"
        title="上次提交结果未知。请保留当前正文和幂等键重试，确认结果前不要新建维护请求。"
        type="warning"
        :closable="false"
      />
      <el-descriptions :column="1" border>
        <el-descriptions-item label="户商完整名称">{{ targetName }}</el-descriptions-item>
        <el-descriptions-item label="当前代称">{{ target?.alias ?? '未知' }}</el-descriptions-item>
        <el-descriptions-item label="当前代称版本">{{
          target?.revision ?? '读取中'
        }}</el-descriptions-item>
      </el-descriptions>
      <el-form label-position="top" :disabled="busy || uncertain || conflict">
        <el-form-item label="真实代称（1至30字符）"
          ><el-input
            v-model="draft"
            :disabled="clear || busy || uncertain || conflict"
            placeholder="请填写真实代称，不从名称推算"
        /></el-form-item>
        <el-checkbox v-model="clear">清除代称（设为未知）</el-checkbox>
        <el-form-item label="维护原因（必填）"
          ><el-input v-model="reason" type="textarea" :rows="3"
        /></el-form-item>
      </el-form>
      <el-alert
        v-if="clear"
        title="清除后当前读取显示未知，已保存的历史快照不改写。"
        type="warning"
        :closable="false"
      />
      <template #footer>
        <el-button :disabled="busy || uncertain" @click="opened = false">关闭</el-button>
        <el-button v-if="conflict" :loading="busy" @click="refreshTarget">重新读取当前值</el-button>
        <el-button type="primary" :loading="busy" :disabled="!target || conflict" @click="save">{{
          uncertain ? '使用原幂等键重试' : '确认维护代称'
        }}</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ReferenceApiError, type ReferenceRecord } from '@/api/orbit/references'
import {
  aliasIntent,
  vendorAliasApi,
  type VendorAlias,
  type VendorAliasResult,
  type VendorAliasWrite,
} from '@/api/orbit/vendor-aliases'

const props = defineProps<{ vendors: ReferenceRecord[] }>()
const emit = defineEmits<{ changed: [] }>()
const aliases = ref<Record<string, VendorAlias>>({})
const loading = ref(false),
  error = ref(''),
  canManage = ref(false)
const opened = ref(false),
  busy = ref(false),
  uncertain = ref(false),
  conflict = ref(false)
const target = ref<VendorAliasResult>(),
  targetName = ref(''),
  dialogError = ref('')
const draft = ref(''),
  reason = ref(''),
  clear = ref(false)
let loadGeneration = 0,
  openGeneration = 0
let intent: VendorAliasWrite | undefined,
  requestKey = '',
  csrf = ''

async function load() {
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const [caps, values] = await Promise.all([
      vendorAliasApi.capabilities(),
      props.vendors.length
        ? vendorAliasApi.batch(props.vendors.map((row) => row.value.id))
        : Promise.resolve({ items: [] }),
    ])
    if (generation !== loadGeneration) return
    canManage.value = caps.can_manage
    csrf = caps.csrf_token
    aliases.value = Object.fromEntries(values.items.map((row) => [row.vendor_id, row]))
  } catch (caught) {
    if (generation === loadGeneration) {
      aliases.value = {}
      error.value = (caught as Error).message
    }
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}
async function open(row: ReferenceRecord) {
  ++openGeneration
  target.value = {
    vendor_id: row.value.id,
    alias: null,
    revision: 1,
    updated_at: null,
    catalog_revision: 0,
  }
  targetName.value = row.value.name
  opened.value = true
  await refreshTarget()
}
async function refreshTarget() {
  if (!target.value) return
  const generation = ++openGeneration,
    id = target.value.vendor_id
  busy.value = true
  dialogError.value = ''
  try {
    const [current, caps] = await Promise.all([
      vendorAliasApi.get(id),
      vendorAliasApi.capabilities(),
    ])
    if (generation !== openGeneration) return
    target.value = current
    csrf = caps.csrf_token
    draft.value = current.alias ?? ''
    reason.value = ''
    clear.value = false
    uncertain.value = false
    conflict.value = false
    intent = undefined
    requestKey = ''
  } catch (caught) {
    if (generation === openGeneration) {
      dialogError.value = (caught as Error).message
      conflict.value = true
    }
  } finally {
    if (generation === openGeneration) busy.value = false
  }
}
function close(done: () => void) {
  if (!busy.value && !uncertain.value) done()
}
async function save() {
  if (!target.value || busy.value || conflict.value) return
  dialogError.value = ''
  try {
    intent = intent ?? aliasIntent(draft.value, clear.value, reason.value)
    requestKey = requestKey || crypto.randomUUID()
  } catch (caught) {
    dialogError.value = (caught as Error).message
    return
  }
  busy.value = true
  try {
    const result = await vendorAliasApi.save(
      target.value.vendor_id,
      intent,
      target.value.revision,
      csrf,
      requestKey,
    )
    aliases.value[result.vendor_id] = result
    opened.value = false
    uncertain.value = false
    ElMessage.success('代称维护已确认；历史快照保持原值')
    emit('changed')
  } catch (caught) {
    dialogError.value = (caught as Error).message
    uncertain.value =
      caught instanceof ReferenceApiError && (caught.status === 0 || caught.status >= 500)
    if (!uncertain.value) {
      intent = undefined
      requestKey = ''
      conflict.value = true
    }
  } finally {
    busy.value = false
  }
}
watch(() => props.vendors, load, { immediate: true })
</script>

<style scoped>
.vendor-alias-section {
  margin-top: 20px;
}
.alias-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.vendor-alias-section .el-alert {
  margin-bottom: 12px;
}
</style>
<style>
.vendor-alias-dialog.el-dialog {
  max-width: calc(100vw - 24px);
  margin-top: 5vh;
}
.vendor-alias-dialog .el-dialog__body {
  max-height: 68vh;
  overflow: auto;
}
</style>
