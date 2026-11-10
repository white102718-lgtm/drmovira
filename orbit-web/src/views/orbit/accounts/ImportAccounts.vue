<template>
  <el-dialog
    v-model="visible"
    title="批量导入广告账户"
    class="account-import-dialog"
    width="min(760px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :show-close="!saving"
  >
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert
      title="导入只关联已有授权。排队不等于成功，消耗未取得时保留未知，不显示为0。"
      type="info"
      :closable="false"
    />
    <el-form label-position="top" :disabled="saving || uncertain">
      <el-form-item label="所属投手" required>
        <el-select
          v-model="ownerId"
          filterable
          remote
          :remote-method="searchOwners"
          :loading="loadingOwners"
          @change="ownerChanged"
          placeholder="按人员姓名搜索"
        >
          <el-option
            v-for="item in owners"
            :key="item.id"
            :value="item.id"
            :label="`${item.name}（${item.team_name}）`"
          />
        </el-select>
        <el-button v-if="ownerCursor" link @click="loadOwners(true)">加载更多人员</el-button>
      </el-form-item>
      <el-form-item label="户商（可留空后补）">
        <el-select
          v-model="vendorId"
          clearable
          :loading="loadingVendors"
          placeholder="请选择可用且对目标投手可读的户商"
        >
          <el-option
            v-for="item in vendors"
            :key="item.value.id"
            :value="item.value.id"
            :label="item.value.name"
            :disabled="item.value.availability !== 'AVAILABLE'"
          />
        </el-select>
        <el-button v-if="vendorCursor" link @click="loadVendors(true)">加载更多户商</el-button>
        <p v-if="ownerId && !loadingVendors && !vendors.length">
          暂无候选，请联系管理员导入并分配户商引用资料。
        </p>
      </el-form-item>
      <el-form-item label="Meta账户ID" required>
        <el-input
          v-model="text"
          type="textarea"
          :rows="7"
          placeholder="支持换行、空格、中英文逗号及分号。最多500项、20000个字符；重复项也计入上限。"
        />
        <span>{{ codepoints }} / 20000 字符，{{ tokenCount }} / 500 项</span>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="uncertain"
      title="本次提交结果尚未确认。请重试同一请求，避免重复创建导入批次。"
      type="warning"
      :closable="false"
    />
    <template #footer
      ><el-button :disabled="saving" @click="visible = false">关闭</el-button
      ><el-button
        type="primary"
        :loading="saving"
        :disabled="loading || (!uncertain && !canSubmit)"
        @click="submit"
        >{{ uncertain ? '重试本次导入' : '预检并提交导入' }}</el-button
      ></template
    >
  </el-dialog>
  <el-dialog
    v-model="resultVisible"
    title="账户导入结果"
    class="account-import-dialog"
    width="min(980px, calc(100vw - 24px))"
  >
    <el-alert v-if="resultError" :title="resultError" type="error" :closable="false" />
    <template v-if="batch">
      <p>
        状态：{{ batches[batch.state] }}；原始项{{ batch.total }}，成功或已存在{{
          batch.success_count
        }}，失败{{ batch.failed_count }}，重复{{ batch.duplicate_count }}。
      </p>
      <el-alert
        v-if="['QUEUED', 'RUNNING'].includes(batch.state)"
        title="批次尚未完成。请刷新查看真实处理结果，当前不代表账户绑定成功。"
        type="info"
        :closable="false"
      />
      <el-table :data="rows" max-height="420" empty-text="暂无导入项">
        <el-table-column label="原位置" width="110"
          ><template #default="{ row }"
            >第{{ row.line_no }}行 {{ row.column }}列</template
          ></el-table-column
        >
        <el-table-column prop="raw_display" label="原输入" min-width="160" show-overflow-tooltip />
        <el-table-column
          prop="normalized_id"
          label="数字ID"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column label="结果" min-width="150"
          ><template #default="{ row }"
            >{{ states[row.state as keyof typeof states]
            }}<span v-if="row.duplicate_of !== null"
              >（同第{{ row.duplicate_of + 1 }}项）</span
            ></template
          ></el-table-column
        >
        <el-table-column prop="name" label="平台名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="消耗" min-width="140"
          ><template #default="{ row }">{{
            row.spend.amount === null ? '未提供/未知' : `${row.spend.amount} ${row.spend.currency}`
          }}</template></el-table-column
        >
        <el-table-column prop="error_code" label="结果类别" min-width="160" />
      </el-table>
    </template>
    <template #footer
      ><el-button @click="resultVisible = false">关闭</el-button
      ><el-button :loading="reading" @click="readResult(false)">刷新状态</el-button
      ><el-button v-if="resultCursor" :loading="reading" @click="readResult(true)"
        >加载更多结果</el-button
      ></template
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  accountApi,
  type AccountImportBatch,
  type AccountImportInput,
  type AccountImportRow,
  type AccountOwnerOption,
} from '@/api/orbit/accounts'
import { referenceApi, ReferenceApiError, type ReferenceRecord } from '@/api/orbit/references'
const emit = defineEmits<{ accepted: [batch: AccountImportBatch] }>()
const visible = ref(false),
  resultVisible = ref(false),
  loading = ref(false),
  saving = ref(false),
  reading = ref(false),
  error = ref(''),
  resultError = ref(''),
  uncertain = ref(false)
const ownerId = ref(''),
  vendorId = ref(''),
  text = ref(''),
  owners = ref<AccountOwnerOption[]>([]),
  vendors = ref<ReferenceRecord[]>([])
const ownerCursor = ref<string | null>(null),
  vendorCursor = ref<string | null>(null),
  resultCursor = ref<string | null>(null),
  loadingOwners = ref(false),
  loadingVendors = ref(false)
const batch = ref<AccountImportBatch | null>(null),
  rows = ref<AccountImportRow[]>([])
let csrf = '',
  ownerQuery = '',
  ownerVersion = 0,
  vendorVersion = 0,
  resultVersion = 0
let intent: { value: AccountImportInput; key: string } | null = null
const codepoints = computed(() => [...text.value].length),
  tokenCount = computed(() => (text.value.match(/[^\s,，;；]+/gu) ?? []).length)
const canSubmit = computed(
  () =>
    ownerId.value &&
    codepoints.value > 0 &&
    codepoints.value <= 20000 &&
    tokenCount.value > 0 &&
    tokenCount.value <= 500,
)
const states = {
  WAITING: '等待平台读取',
  FETCHING: '读取中',
  SUCCEEDED: '绑定成功',
  ALREADY_EXISTS: '已存在，未重绑',
  DUPLICATE: '重复',
  INVALID: '格式无效',
  FORBIDDEN: '无读取权限',
  OWNERSHIP_CONFLICT: '归属冲突',
  FAILED: '失败',
}
const batches = {
  QUEUED: '已排队',
  RUNNING: '处理中',
  SUCCEEDED: '处理完成',
  PARTIAL_SUCCESS: '部分成功',
  FAILED: '失败',
}
async function loadOwners(more = false) {
  const version = ++ownerVersion
  loadingOwners.value = true
  try {
    const params = new URLSearchParams({ q: ownerQuery })
    if (more && ownerCursor.value) params.set('cursor', ownerCursor.value)
    const value = await accountApi.owners(params)
    if (version !== ownerVersion) return
    owners.value = more ? [...owners.value, ...value.items] : value.items
    ownerCursor.value = value.next_cursor
  } catch (cause) {
    if (version === ownerVersion)
      error.value = cause instanceof Error ? cause.message : '人员候选读取失败'
  } finally {
    if (version === ownerVersion) loadingOwners.value = false
  }
}
async function searchOwners(query: string) {
  ownerQuery = query
  await loadOwners()
}
async function ownerChanged() {
  vendorVersion++
  vendorId.value = ''
  vendors.value = []
  vendorCursor.value = null
  await loadVendors()
}
async function loadVendors(more = false) {
  if (!ownerId.value) return
  const version = ++vendorVersion
  loadingVendors.value = true
  try {
    const params = new URLSearchParams({ owner_user_id: ownerId.value, page_size: '50' })
    if (more && vendorCursor.value) params.set('cursor', vendorCursor.value)
    const value = await referenceApi.list('VENDOR', params)
    if (version !== vendorVersion) return
    vendors.value = more ? [...vendors.value, ...value.items] : value.items
    vendorCursor.value = value.next_cursor
  } catch (cause) {
    if (version === vendorVersion)
      error.value = cause instanceof Error ? cause.message : '户商读取失败'
  } finally {
    if (version === vendorVersion) loadingVendors.value = false
  }
}
async function open() {
  visible.value = true
  if (uncertain.value) return
  loading.value = true
  error.value = ''
  try {
    csrf = (await accountApi.capabilities()).csrf_token
    await loadOwners()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '导入能力读取失败'
  } finally {
    loading.value = false
  }
}
async function submit() {
  if (saving.value || (!uncertain.value && !canSubmit.value)) return
  const owner = owners.value.find((item) => item.id === ownerId.value)
  if (!intent) {
    if (!owner) {
      error.value = '请重新读取并选择有效投手'
      return
    }
    intent = {
      value: {
        vendor_id: vendorId.value || null,
        account_ids_text: text.value,
        owner_user_id: owner.id,
        owner_team_id: owner.team_id,
      },
      key: `account-import-${crypto.randomUUID()}`,
    }
  }
  saving.value = true
  error.value = ''
  try {
    const result = await accountApi.createImport(intent.value, csrf, intent.key)
    intent = null
    uncertain.value = false
    visible.value = false
    showResult(result)
    emit('accepted', result)
  } catch (cause) {
    const rejected =
      cause instanceof ReferenceApiError && [400, 401, 403, 404, 409, 422].includes(cause.status)
    uncertain.value = !rejected
    if (rejected) intent = null
    error.value = cause instanceof Error ? cause.message : '提交结果尚未确认，请重试本次导入'
  } finally {
    saving.value = false
  }
}
async function readResult(more: boolean) {
  if (!batch.value || reading.value) return
  const version = ++resultVersion
  reading.value = true
  resultError.value = ''
  try {
    const value = await accountApi.getImport(
      batch.value.id,
      more ? (resultCursor.value ?? undefined) : undefined,
    )
    if (version !== resultVersion) return
    batch.value = value
    rows.value = more ? [...rows.value, ...value.rows] : value.rows
    resultCursor.value = value.next_cursor
  } catch (cause) {
    if (version === resultVersion)
      resultError.value = cause instanceof Error ? cause.message : '结果读取失败'
  } finally {
    if (version === resultVersion) reading.value = false
  }
}
/** Meta连接接入复用同一逐项回执与刷新入口，不另造结果页。 */
function showResult(result: AccountImportBatch) {
  resultVersion++
  reading.value = false
  resultError.value = ''
  batch.value = result
  rows.value = result.rows
  resultCursor.value = result.next_cursor
  resultVisible.value = true
}
defineExpose({ open, showResult })
</script>
<style>
.account-import-dialog {
  max-height: calc(100dvh - 24px);
  display: flex;
  flex-direction: column;
}
.el-dialog.account-import-dialog:not(.is-fullscreen) {
  margin-top: 12px !important;
  margin-bottom: 12px;
}
.account-import-dialog .el-dialog__body {
  overflow-y: auto;
  min-height: 0;
  overflow-wrap: anywhere;
}
.account-import-dialog .el-dialog__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.account-import-dialog .el-dialog__footer .el-button {
  margin-left: 0;
}
.account-import-dialog .el-alert {
  margin-bottom: 12px;
}
.account-import-dialog .el-select {
  width: 100%;
}
</style>
