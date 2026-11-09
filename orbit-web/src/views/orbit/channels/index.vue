<template>
  <div class="app-container channels-page">
    <el-card shadow="never">
      <template #header
        ><div class="toolbar">
          <strong>渠道管理</strong
          ><el-button v-if="can('create')" type="primary" @click="openCreate">新增渠道</el-button>
        </div></template
      >
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-form inline @submit.prevent="reload">
        <el-form-item label="名称 / 渠道ID"
          ><el-input v-model="query" clearable @keyup.enter="reload"
        /></el-form-item>
        <el-form-item label="产品"
          ><el-select
            v-model="productFilter"
            clearable
            filterable
            placeholder="全部产品"
            class="filter"
            ><el-option
              v-for="item in products"
              :key="item.value.id"
              :label="item.value.name"
              :value="item.value.id" /></el-select
        ></el-form-item>
        <el-form-item label="状态"
          ><el-select v-model="status" clearable placeholder="全部状态" class="filter"
            ><el-option label="启用" value="ENABLED" /><el-option
              label="停用"
              value="DISABLED" /></el-select
        ></el-form-item>
        <el-form-item
          ><el-button type="primary" :loading="loading" @click="reload">查询</el-button
          ><el-button @click="reset">重置</el-button></el-form-item
        >
      </el-form>
      <el-table
        v-loading="loading"
        :data="items"
        empty-text="暂无可见渠道；请先由管理员导入引用资料，再新增渠道"
        border
      >
        <el-table-column prop="code" label="渠道ID" min-width="140" />
        <el-table-column label="渠道名称" min-width="160">
          <template #default="{ row }">{{ row.name || row.code }}</template>
        </el-table-column>
        <el-table-column label="产品" min-width="180"
          ><template #default="{ row }">{{
            labels[row.id]?.product_name || productName(row.product_id)
          }}</template></el-table-column
        >
        <el-table-column label="总代" min-width="180"
          ><template #default="{ row }">{{
            labels[row.id]?.agent_name || row.agent_id
          }}</template></el-table-column
        >
        <el-table-column label="类型" width="100"
          ><template #default="{ row }">{{
            types[row.type as keyof typeof types]
          }}</template></el-table-column
        >
        <el-table-column prop="media" label="媒体" width="110" />
        <el-table-column prop="url" label="投放链接" min-width="300" />
        <el-table-column label="状态" width="90"
          ><template #default="{ row }"
            ><el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'">{{
              row.status === 'ENABLED' ? '启用' : '停用'
            }}</el-tag></template
          ></el-table-column
        >
        <el-table-column label="分配用户" min-width="280"
          ><template #default="{ row }">{{
            ownerNames(row.ownership.data_owner_user_ids, row.id)
          }}</template></el-table-column
        >
        <el-table-column prop="revision" label="版本" width="80" />
        <el-table-column label="操作" min-width="260" fixed="right"
          ><template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="can('edit')" link type="primary" @click="openEdit(row)"
              >编辑</el-button
            >
            <el-button v-if="can('assign')" link type="primary" @click="openAction(row, 'owners')"
              >分配</el-button
            >
            <el-button
              v-if="can('archive') && row.status === 'ENABLED'"
              link
              type="danger"
              @click="openAction(row, 'archive')"
              >停用</el-button
            >
          </template></el-table-column
        >
      </el-table>
      <div class="toolbar pager">
        <span>稳定游标分页 · {{ page + 1 }} 页</span
        ><el-select v-model="pageSize" class="page-size" aria-label="每页数量" @change="reload"
          ><el-option
            v-for="size in [20, 50, 100, 200]"
            :key="size"
            :label="`${size} 条/页`"
            :value="size" /></el-select
        ><el-button :disabled="!page || loading" @click="previous">上一页</el-button
        ><el-button :disabled="!nextCursor || loading" @click="next">下一页</el-button>
      </div>
    </el-card>

    <el-dialog
      v-model="dialog"
      :title="existing ? '编辑渠道' : '新增渠道'"
      width="760px"
      class="channel-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving && !retryIntent"
      :show-close="!saving && !retryIntent"
      :before-close="closeDialog"
    >
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" show-icon />
      <el-alert
        v-if="retryIntent"
        title="上次提交结果未知。正文与幂等键已冻结，请重试本次保存，确认前不能关闭或另建意图。"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="!products.length"
        title="请由管理员在系统管理 → 字典与引用资料导入产品及总代，不能用自由文本绕过关联。"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="editContext?.product_locked"
        title="历史马甲包绑定：产品不可修改，需要其他产品请新建渠道。"
        type="info"
        :closable="false"
      />
      <el-form label-position="top" :disabled="blocked">
        <div class="form-grid">
          <el-form-item label="渠道ID（必填，同租户唯一）"
            ><el-input v-model="form.code" maxlength="64" show-word-limit
          /></el-form-item>
          <el-form-item label="渠道名称"
            ><el-input v-model="form.name"
              ><template #append>{{ nameCount }}/100</template></el-input
            ></el-form-item
          >
          <el-form-item label="归属团队"
            ><el-select
              v-model="form.ownership.owner_team_id"
              filterable
              :disabled="blocked || !!existing"
              @change="teamChanged"
              ><el-option
                v-for="team in teamOptions"
                :key="team.id"
                :label="team.name"
                :value="team.id" /></el-select
          ></el-form-item>
          <el-form-item label="分配用户（1—500名）"
            ><el-select
              v-model="form.ownership.data_owner_user_ids"
              filterable
              multiple
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="3"
              :multiple-limit="500"
              :disabled="blocked || !!existing"
              ><el-option
                v-for="owner in owners.filter(
                  (item) => item.team_id === form.ownership.owner_team_id,
                )"
                :key="owner.id"
                :label="owner.display_name || owner.id"
                :value="owner.id" /></el-select
          ></el-form-item>
          <el-form-item v-if="!existing" label="批量选择已加载候选">
            <div>
              <el-button :disabled="blocked || ownerLoading" @click="selectLoadedOwners('create')"
                >选择当前团队已加载用户</el-button
              >
              <p role="status" data-testid="create-owner-summary" :aria-busy="ownerLoading">
                已加载当前团队 {{ loadedOwnerCount(form.ownership.owner_team_id) }} 人；已选择
                {{ form.ownership.data_owner_user_ids.length }} / 500 人
              </p>
            </div>
          </el-form-item>
          <el-form-item label="产品（必填）"
            ><el-select
              v-model="form.product_id"
              filterable
              :disabled="blocked || editContext?.product_locked"
              @change="productChanged"
              ><el-option
                v-for="item in productOptions"
                :key="item.value.id"
                :label="`${item.value.name}${item.value.availability !== 'AVAILABLE' ? '（已失效）' : ''}`"
                :value="item.value.id"
                :disabled="item.value.availability !== 'AVAILABLE'" /></el-select
            ><el-button v-if="productCursor" link @click="loadProducts(true)"
              >加载更多产品</el-button
            ></el-form-item
          >
          <el-form-item label="总代（仅限产品已关联）"
            ><el-select
              v-model="form.agent_id"
              filterable
              :loading="agentLoading"
              :disabled="!form.product_id"
              ><el-option
                v-for="item in agentOptions"
                :key="item.value.id"
                :label="`${item.value.name}${item.value.availability !== 'AVAILABLE' ? '（已失效）' : ''}`"
                :value="item.value.id"
                :disabled="item.value.availability !== 'AVAILABLE'" /></el-select
            ><el-button v-if="agentCursor" link @click="loadAgents(true)"
              >加载更多总代</el-button
            ></el-form-item
          >
          <el-form-item label="类型"
            ><el-select v-model="form.type"
              ><el-option
                v-for="(label, value) in types"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
          <el-form-item label="媒体"
            ><el-select v-model="form.media"
              ><el-option
                v-for="media in ['META', 'GOOGLE', 'TIKTOK', 'OTHER']"
                :key="media"
                :label="media"
                :value="media" /></el-select
          ></el-form-item>
        </div>
        <el-form-item label="HTTPS投放链接（不自动追加参数，不覆盖已保存计划）"
          ><el-input v-model="form.url" type="textarea" :rows="3"
        /></el-form-item>
        <el-form-item label="状态"
          ><el-radio-group v-model="form.status"
            ><el-radio value="ENABLED">启用</el-radio
            ><el-radio value="DISABLED">停用</el-radio></el-radio-group
          ></el-form-item
        >
        <el-button
          v-if="ownerAfter"
          :loading="ownerLoading"
          :disabled="blocked"
          @click="loadOwners(true)"
          >加载更多可分配用户</el-button
        >
      </el-form>
      <el-alert v-if="ownerError" :title="ownerError" type="error" :closable="false" />
      <el-button v-if="ownerError" :loading="ownerLoading" :disabled="blocked" @click="loadOwners()"
        >重试候选读取</el-button
      >
      <template #footer
        ><el-button :disabled="saving || retryIntent" @click="dialog = false">取消</el-button
        ><el-button v-if="revisionConflict" :loading="saving" @click="refreshCurrent"
          >重新读取当前渠道</el-button
        >
        <el-button type="primary" :loading="saving" :disabled="revisionConflict" @click="save">{{
          retryIntent ? '重试本次保存' : '保存'
        }}</el-button></template
      >
    </el-dialog>

    <el-drawer v-model="detailOpen" title="渠道详情" size="min(760px, 100%)">
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <el-alert
        v-if="detailContext?.product_locked"
        title="历史马甲包绑定：产品为只读关系；需要其他产品时请新建渠道，保留原历史绑定。"
        type="info"
        :closable="false"
      />
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item v-for="(value, label) in detailFields" :key="label" :label="label">{{
          value
        }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>

    <el-dialog
      v-model="actionOpen"
      :title="actionMode === 'owners' ? '分配渠道' : '停用渠道'"
      width="620px"
      class="channel-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving && !retryIntent"
      :show-close="!saving && !retryIntent"
      :before-close="closeDialog"
    >
      <el-alert v-if="formError" :title="formError" type="error" :closable="false" />
      <el-alert
        v-if="retryIntent"
        title="上次操作结果未知。正文与幂等键已冻结，请重试本次操作，确认前不能关闭或另建意图。"
        type="warning"
        :closable="false"
      />
      <el-alert
        v-if="actionMode === 'archive'"
        title="停用保留历史记录，新的引用与待执行任务须重新检查可用性；不会修改既有广告落地页。"
        type="warning"
        :closable="false"
      />
      <el-form label-position="top" :disabled="blocked">
        <template v-if="actionMode === 'owners'">
          <el-form-item label="归属团队"
            ><el-select
              v-model="assignment.owner_team_id"
              filterable
              @change="assignment.data_owner_user_ids = []"
              ><el-option
                v-for="team in teamOptions"
                :key="team.id"
                :label="team.name"
                :value="team.id" /></el-select
          ></el-form-item>
          <el-form-item label="分配用户"
            ><el-select
              v-model="assignment.data_owner_user_ids"
              filterable
              multiple
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="3"
              :multiple-limit="500"
              ><el-option
                v-for="owner in owners.filter((item) => item.team_id === assignment.owner_team_id)"
                :key="owner.id"
                :label="owner.display_name || owner.id"
                :value="owner.id" /></el-select
          ></el-form-item>
          <el-button :disabled="blocked || ownerLoading" @click="selectLoadedOwners('owners')"
            >选择当前团队已加载用户</el-button
          >
          <p role="status" data-testid="assignment-owner-summary" :aria-busy="ownerLoading">
            已加载当前团队 {{ loadedOwnerCount(assignment.owner_team_id) }} 人；已选择
            {{ assignment.data_owner_user_ids.length }} / 500 人
          </p>
          <el-button
            v-if="ownerAfter"
            :loading="ownerLoading"
            :disabled="blocked"
            @click="loadOwners(true)"
            >加载更多用户</el-button
          >
          <el-alert v-if="ownerError" :title="ownerError" type="error" :closable="false" />
          <el-button
            v-if="ownerError"
            :loading="ownerLoading"
            :disabled="blocked"
            @click="loadOwners()"
            >重试候选读取</el-button
          >
        </template>
        <el-form-item label="原因（必填）"
          ><el-input v-model="reason" type="textarea" :rows="3"
        /></el-form-item>
      </el-form>
      <template #footer
        ><el-button :disabled="saving || retryIntent" @click="actionOpen = false">取消</el-button
        ><el-button v-if="revisionConflict" :loading="saving" @click="refreshCurrent"
          >重新读取当前渠道</el-button
        >
        <el-button
          :type="actionMode === 'archive' ? 'danger' : 'primary'"
          :loading="saving"
          :disabled="revisionConflict"
          @click="submitAction"
          >{{ retryIntent ? '重试本次操作' : '确认' }}</el-button
        ></template
      >
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  channelApi,
  type Channel,
  type ChannelWrite,
  type ChannelCapabilities,
  type ChannelEditContext,
  type ChannelOwner,
  type ChannelLabels,
} from '@/api/orbit/channels'
import {
  referenceApi,
  ReferenceApiError,
  type ReferenceRecord,
  type Ownership,
} from '@/api/orbit/references'

const types = { APP: '应用', WEBSITE: '网站', OTHER: '其他' }
const labels = ref<Record<string, ChannelLabels>>({})
const items = ref<Channel[]>([]),
  products = ref<ReferenceRecord[]>([]),
  agents = ref<ReferenceRecord[]>([]),
  owners = ref<ChannelOwner[]>([])
const loading = ref(false),
  saving = ref(false),
  error = ref(''),
  formError = ref(''),
  detailError = ref('')
const query = ref(''),
  status = ref(''),
  productFilter = ref(''),
  pageSize = ref(50),
  page = ref(0),
  nextCursor = ref<string | null>(null)
const cursors = ref<(string | null)[]>([null]),
  productCursor = ref<string | null>(null),
  agentCursor = ref<string | null>(null),
  ownerAfter = ref<string | null>(null)
const capabilities = ref<ChannelCapabilities | null>(null),
  dialog = ref(false),
  detailOpen = ref(false),
  actionOpen = ref(false),
  agentLoading = ref(false)
const ownerLoading = ref(false)
const ownerError = ref('')
const existing = ref<Channel>(),
  detail = ref<Channel>(),
  editContext = ref<ChannelEditContext>(),
  detailContext = ref<ChannelEditContext>(),
  actionTarget = ref<Channel>(),
  actionMode = ref<'owners' | 'archive'>('owners')
const reason = ref(''),
  assignment = reactive<Ownership>({ owner_team_id: '', data_owner_user_ids: [] })
const fresh = (): ChannelWrite => ({
  ownership: { owner_team_id: '', data_owner_user_ids: [] },
  code: '',
  name: '',
  product_id: '',
  agent_id: '',
  type: 'APP',
  media: 'META',
  url: '',
  status: 'ENABLED',
})
const form = reactive<ChannelWrite>(fresh())
// 发生网络未知结果时冻结原意图，重试复用键及正文；后续编辑不会悄悄改变同键payload。
let intent: { key: string; signature: string; run: () => Promise<Channel> } | undefined
const retryIntent = ref(false)
const revisionConflict = ref(false)
const blocked = computed(() => saving.value || retryIntent.value || revisionConflict.value)
const nameCount = computed(() => [...form.name.normalize('NFC')].length)
const can = (action: string) => capabilities.value?.actions.includes(action)
const teamOptions = computed(() => [
  ...new Map(
    owners.value.map((owner) => [owner.team_id, { id: owner.team_id, name: owner.team_name }]),
  ).values(),
])
const productName = (id: string) =>
  products.value.find((item) => item.value.id === id)?.value.name || id
const ownerNames = (ids: string[], channelId?: string) =>
  ids
    .map(
      (id) =>
        labels.value[channelId || '']?.owners.find((owner) => owner.id === id)?.name ||
        owners.value.find((owner) => owner.id === id)?.display_name ||
        id,
    )
    .join('、')
function withHistorical(options: ReferenceRecord[], type: 'product' | 'agent') {
  const historical = editContext.value?.references[type]
  if (!historical || options.some((item) => item.value.id === historical.id)) return options
  return [
    ...options,
    {
      value: {
        ...historical,
        kind: type === 'product' ? 'PRODUCT' : 'BUSINESS_AGENT',
        source_key: '',
        owner_team_id: '',
        data_owner_user_ids: [],
      },
      revision: 1,
      catalog_revision: 1,
      updated_at: '',
    } as ReferenceRecord,
  ]
}
const productOptions = computed(() => withHistorical(products.value, 'product'))
const agentOptions = computed(() => withHistorical(agents.value, 'agent'))
const detailFields = computed(() =>
  detail.value
    ? {
        业务UUID: detail.value.id,
        渠道ID: detail.value.code,
        渠道名称: detail.value.name || detail.value.code,
        产品: labels.value[detail.value.id]?.product_name || productName(detail.value.product_id),
        总代: labels.value[detail.value.id]?.agent_name || detail.value.agent_id,
        产品UUID: detail.value.product_id,
        总代UUID: detail.value.agent_id,
        产品引用状态: detailContext.value?.references.product?.availability ?? '未知',
        总代引用状态: detailContext.value?.references.agent?.availability ?? '未知',
        历史产品绑定: detailContext.value?.product_locked ? '只读，换产品请新建渠道' : '当前未锁定',
        类型: types[detail.value.type],
        媒体: detail.value.media,
        投放链接: detail.value.url,
        状态: detail.value.status === 'ENABLED' ? '启用' : '停用',
        归属团队UUID: detail.value.ownership.owner_team_id,
        分配用户: ownerNames(detail.value.ownership.data_owner_user_ids, detail.value.id),
        版本: String(detail.value.revision),
        创建UTC时间: detail.value.created_at,
        更新UTC时间: detail.value.updated_at,
      }
    : {},
)
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '请求失败，请重试')
async function loadProducts(more = false) {
  const result = await referenceApi.list(
    'PRODUCT',
    new URLSearchParams({
      page_size: '200',
      ...(more && productCursor.value ? { cursor: productCursor.value } : {}),
    }),
  )
  products.value = more ? [...products.value, ...result.items] : result.items
  productCursor.value = result.next_cursor
}
async function loadOwners(more = false) {
  if (ownerLoading.value) return
  ownerLoading.value = true
  ownerError.value = ''
  if (!more) {
    // 弹窗首次读取不能沿用上一弹窗已到末页的null游标或旧候选数量。
    owners.value = []
    ownerAfter.value = null
  }
  try {
    const result = await channelApi.owners(more ? ownerAfter.value || '' : '')
    owners.value = more
      ? [...new Map([...owners.value, ...result.items].map((owner) => [owner.id, owner])).values()]
      : result.items
    ownerAfter.value = result.next_after
  } catch (cause) {
    ownerError.value = message(cause)
  } finally {
    ownerLoading.value = false
  }
}
function loadedOwnerCount(team: string) {
  return owners.value.filter((owner) => owner.team_id === team).length
}
function selectLoadedOwners(mode: 'create' | 'owners') {
  if (blocked.value || ownerLoading.value || (mode === 'create' && existing.value)) return
  const ownership = mode === 'create' ? form.ownership : assignment
  const eligible = owners.value.filter((owner) => owner.team_id === ownership.owner_team_id)
  const merged = [
    ...new Set([...ownership.data_owner_user_ids, ...eligible.map((owner) => owner.id)]),
  ]
  if (!ownership.owner_team_id || !eligible.length) {
    formError.value = '请先选择团队并加载其可分配用户'
    return
  }
  if (merged.length > 500) {
    formError.value = '最多分配500名用户，请减少已选项；本次没有截断或改变选择'
    return
  }
  ownership.data_owner_user_ids = merged
  formError.value = ''
}
async function loadAgents(more = false) {
  if (!form.product_id) return
  agentLoading.value = true
  try {
    const result = await referenceApi.list(
      'BUSINESS_AGENT',
      new URLSearchParams({
        product_id: form.product_id,
        page_size: '200',
        ...(more && agentCursor.value ? { cursor: agentCursor.value } : {}),
      }),
    )
    agents.value = more ? [...agents.value, ...result.items] : result.items
    agentCursor.value = result.next_cursor
  } catch (cause) {
    formError.value = message(cause)
  } finally {
    agentLoading.value = false
  }
}
async function productChanged() {
  form.agent_id = ''
  agents.value = []
  agentCursor.value = null
  await loadAgents()
}
function teamChanged() {
  form.ownership.data_owner_user_ids = []
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ page_size: String(pageSize.value) })
    if (query.value) params.set('q', query.value)
    if (status.value) params.set('status', status.value)
    if (productFilter.value) params.set('product_id', productFilter.value)
    const cursor = cursors.value[page.value]
    if (cursor) params.set('cursor', cursor)
    const result = await channelApi.list(params)
    items.value = result.items
    nextCursor.value = result.next_cursor
    if (result.items.length) {
      const names = await channelApi.labels(result.items.map((item) => item.id))
      labels.value = Object.fromEntries(names.items.map((item) => [item.id, item]))
    } else labels.value = {}
  } catch (cause) {
    error.value = message(cause)
    if (cause instanceof ReferenceApiError && cause.status === 409) {
      page.value = 0
      cursors.value = [null]
      nextCursor.value = null
    }
  } finally {
    loading.value = false
  }
}
async function reload() {
  page.value = 0
  cursors.value = [null]
  await load()
}
async function next() {
  if (!nextCursor.value) return
  cursors.value.push(nextCursor.value)
  page.value++
  await load()
}
async function previous() {
  if (!page.value) return
  page.value--
  cursors.value = cursors.value.slice(0, page.value + 1)
  await load()
}
async function reset() {
  query.value = ''
  status.value = ''
  productFilter.value = ''
  await reload()
}
function resetIntent() {
  intent = undefined
  retryIntent.value = false
  revisionConflict.value = false
  formError.value = ''
}
async function openCreate() {
  existing.value = undefined
  editContext.value = undefined
  Object.assign(form, fresh())
  agents.value = []
  resetIntent()
  dialog.value = true
  await loadOwners()
  if (owners.value.length) {
    form.ownership.owner_team_id = owners.value[0].team_id
    if (capabilities.value?.data_role === 'USER')
      form.ownership.data_owner_user_ids = [owners.value[0].id]
  }
}
async function openEdit(row: Channel) {
  resetIntent()
  try {
    const [current, context] = await Promise.all([
      channelApi.get(row.id),
      channelApi.context(row.id),
    ])
    existing.value = current
    editContext.value = context
    const { id, revision, created_at, updated_at, ...value } = current
    Object.assign(form, structuredClone(value))
    dialog.value = true
    await Promise.all([loadOwners(), loadAgents()])
    return true
  } catch (cause) {
    error.value = message(cause)
    return false
  }
}
async function openDetail(row: Channel) {
  detail.value = undefined
  detailContext.value = undefined
  detailError.value = ''
  detailOpen.value = true
  try {
    const [current, context, names] = await Promise.all([
      channelApi.get(row.id),
      channelApi.context(row.id),
      channelApi.labels([row.id]),
    ])
    detail.value = current
    detailContext.value = context
    for (const name of names.items) labels.value[name.id] = name
  } catch (cause) {
    detailError.value = message(cause)
  }
}
async function openAction(row: Channel, mode: 'owners' | 'archive') {
  resetIntent()
  reason.value = ''
  try {
    actionTarget.value = await channelApi.get(row.id)
    Object.assign(assignment, {
      owner_team_id: actionTarget.value.ownership.owner_team_id,
      data_owner_user_ids: [...actionTarget.value.ownership.data_owner_user_ids],
    })
    actionMode.value = mode
    actionOpen.value = true
    if (mode === 'owners') await loadOwners()
    return true
  } catch (cause) {
    error.value = message(cause)
    return false
  }
}
function closeDialog(done: () => void) {
  if (!saving.value && !retryIntent.value) done()
}
async function refreshCurrent() {
  if (saving.value || retryIntent.value) return
  saving.value = true
  try {
    capabilities.value = await channelApi.capabilities()
    const restored =
      dialog.value && existing.value
        ? await openEdit(existing.value)
        : actionOpen.value && actionTarget.value
          ? await openAction(actionTarget.value, actionMode.value)
          : false
    if (!restored) {
      revisionConflict.value = true
      formError.value = '重新读取失败，请重试读取当前渠道，不能提交旧版本'
    }
  } catch (cause) {
    revisionConflict.value = true
    formError.value = message(cause)
  } finally {
    saving.value = false
  }
}
async function perform(signature: string, run: (key: string) => Promise<Channel>) {
  if (saving.value) return
  saving.value = true
  formError.value = ''
  if (!retryIntent.value && (!intent || intent.signature !== signature)) {
    const key = crypto.randomUUID()
    intent = { key, signature, run: () => run(key) }
    retryIntent.value = false
  }
  try {
    await intent!.run()
    dialog.value = false
    actionOpen.value = false
    resetIntent()
    ElMessage.success('操作已保存')
    await reload()
  } catch (cause) {
    formError.value = message(cause)
    retryIntent.value =
      cause instanceof ReferenceApiError && (cause.status === 0 || cause.status >= 500)
    revisionConflict.value =
      cause instanceof ReferenceApiError && cause.code === 'REVISION_CONFLICT'
  } finally {
    saving.value = false
  }
}
async function save() {
  if (revisionConflict.value) return
  const normalizedName = form.name.normalize('NFC').trim()
  if (
    !retryIntent.value &&
    ([...normalizedName].length > 100 || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(form.name))
  ) {
    formError.value = '渠道名称最多100个字符，不能包含控制字符'
    return
  }
  const value: ChannelWrite = structuredClone({
    ...form,
    name: normalizedName,
    ownership: { ...form.ownership, data_owner_user_ids: [...form.ownership.data_owner_user_ids] },
  })
  const current = existing.value
  const csrf = capabilities.value?.csrf_token || ''
  await perform(JSON.stringify(['save', current?.id, current?.revision, value]), (key) =>
    channelApi.save(value, csrf, key, current),
  )
}
async function submitAction() {
  if (revisionConflict.value) return
  const current = actionTarget.value
  const normalizedReason = reason.value.normalize('NFC').trim()
  if (
    !current ||
    !normalizedReason ||
    [...normalizedReason].length > 1000 ||
    /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(reason.value)
  ) {
    formError.value = '请填写1至1000字符的操作原因，不能包含控制字符'
    return
  }
  const ownership = { ...assignment, data_owner_user_ids: [...assignment.data_owner_user_ids] }
  const why = normalizedReason
  const mode = actionMode.value
  const csrf = capabilities.value?.csrf_token || ''
  await perform(JSON.stringify([mode, current.id, current.revision, ownership, why]), (key) =>
    mode === 'owners'
      ? channelApi.assign(current, ownership, why, csrf, key)
      : channelApi.archive(current, why, csrf, key),
  )
}
onMounted(async () => {
  try {
    capabilities.value = await channelApi.capabilities()
    await Promise.all([load(), loadProducts(), loadOwners()])
  } catch (cause) {
    error.value = message(cause)
  }
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: space-between;
}
.pager {
  justify-content: flex-end;
  margin-top: 16px;
}
.filter {
  width: 180px;
}
.page-size {
  width: 130px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.el-alert {
  margin-bottom: 16px;
}
.el-select {
  width: 100%;
}
.el-form {
  margin-top: 16px;
}
:global(.channel-dialog) {
  max-width: calc(100vw - 24px);
  margin-top: 5vh;
}
:global(.channel-dialog .el-dialog__body) {
  max-height: calc(90vh - 150px);
  overflow: auto;
}
:deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
  .pager {
    justify-content: flex-start;
  }
  .filter {
    width: 160px;
  }
}
</style>
