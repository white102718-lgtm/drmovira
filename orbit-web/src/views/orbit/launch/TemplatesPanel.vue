<template>
  <section v-show="active" class="template-panel">
    <el-alert
      v-if="recovered"
      title="发现当前账号待确认的模板操作。可重试原操作，确认前不能开始另一项模板变更。"
      type="warning"
      :closable="false"
    >
      <el-button :loading="busy" @click="resume">恢复并重试待确认操作</el-button>
    </el-alert>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="cacheWarning" :title="cacheWarning" type="warning" :closable="false" />
    <div class="template-tools">
      <el-input
        v-model="q"
        placeholder="搜索模板名称"
        clearable
        :disabled="loading || listBlocked"
        @keyup.enter="load('')"
      /><el-select
        v-model="status"
        clearable
        placeholder="全部状态"
        :disabled="loading || listBlocked"
        ><el-option label="启用" value="ACTIVE" /><el-option
          label="归档"
          value="ARCHIVED" /></el-select
      ><el-date-picker
        v-model="dates"
        type="daterange"
        value-format="YYYY-MM-DD"
        start-placeholder="模板创建日期起（UTC）"
        end-placeholder="模板创建日期止（UTC）"
        :disabled="loading || listBlocked"
      />
      <el-button :disabled="loading || listBlocked" @click="load('')">查询模板</el-button
      ><el-button
        v-if="can('create')"
        type="primary"
        :disabled="loading || listBlocked"
        @click="createFrom([])"
        >新建配置模板</el-button
      >
    </div>
    <p class="template-page-status" role="status">
      日期按服务器创建时间的UTC自然日过滤，结束日包含当日。{{
        dataAsOf ? `数据时刻 ${dataAsOf}（UTC）。` : ''
      }}{{ pageDirty ? '条件已变化，请查询后翻页。' : ''
      }}{{ error && rows.length ? '保留上次成功读取的数据。' : '' }}
    </p>
    <el-table v-loading="loading" :data="rows" row-key="id" style="width: 100%"
      ><el-table-column prop="name" label="模板名称" min-width="180" /><el-table-column
        label="范围"
        width="100"
        ><template #default="scope">{{
          scope.row.visibility === 'TEAM' ? '明确共享' : '私有'
        }}</template></el-table-column
      ><el-table-column label="版本 / 状态" width="150"
        ><template #default="scope"
          >{{ scope.row.revision }} / {{ scope.row.state }}</template
        ></el-table-column
      ><el-table-column label="操作" min-width="320"
        ><template #default="scope"
          ><el-button link :disabled="listBlocked || loading" @click="open(scope.row, true)"
            >详情</el-button
          ><el-button
            v-if="own(scope.row) && can('edit') && scope.row.state === 'ACTIVE'"
            link
            :disabled="listBlocked || loading"
            @click="open(scope.row, false)"
            >编辑</el-button
          ><el-button
            v-if="scope.row.state === 'ACTIVE'"
            link
            :disabled="listBlocked || loading"
            @click="applyTemplate(scope.row)"
            >加载为新草稿</el-button
          ><el-button
            v-if="own(scope.row) && can('share') && scope.row.state === 'ACTIVE'"
            link
            :disabled="listBlocked || loading"
            @click="shareTemplate(scope.row)"
            >分享</el-button
          ><el-button
            v-if="own(scope.row) && can('archive') && scope.row.state === 'ACTIVE'"
            link
            type="danger"
            :disabled="listBlocked || loading"
            @click="archiveTemplate(scope.row)"
            >归档</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <div class="template-tools">
      <el-select
        v-model="pageSize"
        aria-label="每页模板数量"
        :disabled="loading || listBlocked"
        @change="load('')"
        ><el-option
          v-for="size in [20, 50, 100, 200]"
          :key="size"
          :label="`${size}个`"
          :value="size"
      /></el-select>
      <el-button :disabled="loading || listBlocked" @click="load('')">重新读取模板首页</el-button>
      <el-button
        :disabled="loading || listBlocked || pageDirty || historyIndex === 0"
        @click="previousPage"
        >上一页模板</el-button
      >
      <el-button v-if="nextCursor" :disabled="loading || listBlocked || pageDirty" @click="nextPage"
        >下一页模板</el-button
      >
      <span>第 {{ historyIndex + 1 }} 页 · 当前返回 {{ rows.length }} 项</span>
    </div>
  </section>
  <el-dialog
    v-model="editorOpen"
    :title="readOnly ? '模板详情' : target ? '编辑配置模板' : '保存配置模板'"
    width="min(1200px, 96vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!metricBrowsing"
    :before-close="beforeEditorClose"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="cacheWarning" :title="cacheWarning" type="warning" :closable="false" />
    <el-alert
      v-if="uncertain"
      title="本次操作结果尚未确认，请重试同一次操作，确认前不能关闭或修改。"
      type="warning"
      :closable="false"
    />
    <el-descriptions v-if="target" :column="1" border class="template-metadata"
      ><el-descriptions-item label="模板 ID"
        ><span class="template-full">{{ target.id }}</span></el-descriptions-item
      ><el-descriptions-item label="版本 / 状态"
        >{{ target.revision }} / {{ target.state }}</el-descriptions-item
      ><el-descriptions-item label="拥有者 ID"
        ><span class="template-full">{{ target.ownership.owner_user_id }}</span
        >（名称未读取）</el-descriptions-item
      ><el-descriptions-item label="团队 ID"
        ><span class="template-full">{{ target.ownership.owner_team_id }}</span
        >（名称未读取）</el-descriptions-item
      ></el-descriptions
    >
    <el-form label-position="top" :disabled="busy || uncertain || readOnly"
      ><el-form-item label="模板名称（1—80码点）"
        ><el-input v-model="form.name" /><span>{{ codePoints(form.name) }}/80</span></el-form-item
      ><el-form-item label="说明（最多500码点，允许LF）"
        ><el-input v-model="form.description" type="textarea" :rows="3" /><span
          >{{ codePoints(form.description) }}/500</span
        ></el-form-item
      ><el-form-item label="可见范围"
        ><el-select
          v-model="form.visibility"
          :disabled="!can('share') && Boolean(target?.visibility === 'TEAM')"
          @change="visibilityChanged"
          ><el-option label="私有" value="PRIVATE" /><el-option
            label="团队明确共享"
            value="TEAM"
            :disabled="!can('share')" /></el-select></el-form-item
      ><template v-if="form.visibility === 'TEAM'"
        ><el-alert
          title="接收者只获得查看和使用权；新团队成员不会自动加入。未指定接收者时，保存将冻结当前团队全部启用成员（最多500）。"
          type="warning"
          :closable="false"
        /><el-form-item label="明确接收者（最多500）"
          ><el-select
            v-model="form.recipient_user_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :max-collapse-tags="3"
            :disabled="!can('share')"
            ><el-option
              v-for="person in recipientChoices"
              :key="person.id"
              :label="person.name"
              :value="person.id" /></el-select
          ><el-button
            v-if="recipientCursor && can('share')"
            :disabled="recipientLoading || busy"
            @click="loadRecipients(true)"
            >更多成员</el-button
          ></el-form-item
        ></template
      ></el-form
    >
    <CampaignTree
      v-model="form.campaigns"
      :disabled="busy || uncertain || readOnly"
      :metric-read-allowed="metricReadAllowed"
      :metric-context-key="metricContextKey"
      @browsing="metricBrowsing = $event"
    />
    <template #footer
      ><el-button :disabled="busy || uncertain || metricBrowsing" @click="requestEditorClose"
        >关闭</el-button
      ><el-button v-if="uncertain" type="warning" :loading="busy" @click="retry"
        >重试本次操作</el-button
      ><template v-else-if="!readOnly"
        ><el-button v-if="target" :disabled="busy || metricBrowsing" @click="refreshEditor"
          >重新读取服务器版本</el-button
        ><el-button type="primary" :disabled="busy || metricBrowsing" @click="saveTemplate"
          >保存模板</el-button
        ></template
      ></template
    >
  </el-dialog>
  <el-dialog
    v-model="actionOpen"
    :title="
      action === 'share' ? '分享配置模板' : action === 'archive' ? '归档模板' : '从模板创建新草稿'
    "
    width="min(700px, 95vw)"
    :close-on-click-modal="false"
    :before-close="beforeActionClose"
  >
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="cacheWarning" :title="cacheWarning" type="warning" :closable="false" /><el-alert
      v-if="uncertain"
      title="操作结果待确认，请重试原操作，不能关闭丢失意图。"
      type="warning"
      :closable="false"
    />
    <p role="status" aria-label="操作候选读取状态" :aria-busy="recipientLoading">
      {{ recipientLoading ? '正在读取当前候选，请稍候' : '当前候选读取已结束' }}
    </p>
    <el-form label-position="top" :disabled="busy || uncertain || recipientLoading"
      ><p>{{ target?.name }} · 当前版本 {{ target?.revision }}</p>
      <el-form-item v-if="action === 'share'" label="明确接收者（至少1人）"
        ><el-select
          v-model="actionRecipients"
          multiple
          filterable
          collapse-tags
          collapse-tags-tooltip
          :max-collapse-tags="3"
          ><el-option
            v-for="person in recipientChoices"
            :key="person.id"
            :value="person.id"
            :label="person.name" /></el-select
        ><el-button
          v-if="recipientCursor"
          :disabled="recipientLoading"
          @click="loadRecipients(true)"
          >更多共享成员</el-button
        ></el-form-item
      ><el-form-item v-if="action === 'apply'" label="新草稿负责人"
        ><el-select v-model="applyOwnerId" filterable
          ><el-option
            v-for="person in applyOwners"
            :key="person.id"
            :value="person.id"
            :label="person.name + (person.team_name ? ' · ' + person.team_name : '')" /></el-select
        ><el-button
          v-if="applyOwnerCursor"
          :disabled="recipientLoading"
          @click="loadApplyOwners(true)"
          >更多负责人</el-button
        ><el-alert
          title="账户、身份、渠道和素材分配全部剥离；生成新草稿后须重新选择，不沿用旧执行结果。"
          type="info"
          :closable="false" /></el-form-item
      ><el-form-item label="操作原因（1—1000码点）"
        ><el-input v-model="reason" type="textarea" :rows="3" />
        <span role="status" aria-label="操作原因输入状态"
          >已输入 {{ codePoints(reason) }}/1000 码点</span
        >
      </el-form-item></el-form
    >
    <template #footer
      ><el-button :disabled="busy || uncertain" @click="actionOpen = false">取消</el-button
      ><el-button v-if="uncertain" type="warning" :loading="busy" @click="retry"
        >重试本次操作</el-button
      ><el-button v-else type="primary" :disabled="busy || recipientLoading" @click="confirmAction"
        >确认{{
          action === 'share' ? '分享' : action === 'archive' ? '归档' : '创建草稿'
        }}</el-button
      ></template
    >
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  launchApi,
  type CampaignConfig,
  type LaunchCapabilities,
  type LaunchPlan,
  type OwnerOption,
} from '@/api/orbit/launch'
import { templateApi, type LaunchTemplate, type TemplateWrite } from '@/api/orbit/templates'
import { ReferenceApiError } from '@/api/orbit/references'
import { cloneValue, codePoints, newDraft, normalizeDraft } from '@/api/orbit/launch-form'
import CampaignTree from './CampaignTree.vue'
import {
  cacheTemplateIntent,
  clearTemplateIntent,
  readTemplateIntent,
  type TemplateMutation,
  type TemplateRecovery,
} from '@/api/orbit/launch-recovery'
const props = defineProps<{
  active: boolean
  metricReadAllowed?: boolean
  metricContextKey?: string
}>()
const emit = defineEmits<{
  applied: [plan: LaunchPlan]
  blocked: [value: boolean]
  failure: [message: string]
}>()
const caps = ref<LaunchCapabilities>(),
  rows = ref<LaunchTemplate[]>([]),
  q = ref(''),
  status = ref(''),
  nextCursor = ref<string | null>(null),
  loading = ref(false),
  error = ref('')
const editorOpen = ref(false),
  actionOpen = ref(false),
  readOnly = ref(false),
  target = ref<LaunchTemplate>(),
  busy = ref(false),
  uncertain = ref(false),
  form = ref<TemplateWrite>({
    name: '',
    description: '',
    visibility: 'PRIVATE',
    recipient_user_ids: [],
    campaigns: [],
  }),
  initialForm = ref('')
const recipientRows = ref<OwnerOption[]>([]),
  recipientCursor = ref<string | null>(null),
  recipientLoading = ref(false),
  recipientCsrf = ref(''),
  action = ref<'share' | 'archive' | 'apply'>('share'),
  actionRecipients = ref<string[]>([]),
  reason = ref(''),
  applyOwners = ref<OwnerOption[]>([]),
  applyOwnerCursor = ref<string | null>(null),
  applyOwnerId = ref('')
const recovered = ref<TemplateRecovery | null>(null)
const cacheWarning = ref('')
const metricBrowsing = ref(false)
const dates = ref<string[] | null>(null),
  pageSize = ref<20 | 50 | 100 | 200>(20),
  pageHistory = ref<string[]>(['']),
  historyIndex = ref(0),
  dataAsOf = ref(''),
  appliedFilters = ref('')
const filterSignature = computed(() =>
  JSON.stringify([q.value.normalize('NFC').trim(), status.value, dates.value, pageSize.value]),
)
const pageDirty = computed(() => appliedFilters.value !== filterSignature.value)
const listBlocked = computed(
  () => editorOpen.value || actionOpen.value || busy.value || uncertain.value,
)
let readEpoch = 0,
  alive = true
let pending: {
  run: (key: string) => Promise<LaunchTemplate | LaunchPlan>
  key: string
  success: (result: LaunchTemplate | LaunchPlan) => void
} | null = null
const recipientChoices = computed(() => {
  const map = new Map(recipientRows.value.map((person) => [person.id, person]))
  ;[...form.value.recipient_user_ids, ...actionRecipients.value].forEach((id) => {
    if (!map.has(id))
      map.set(id, { id, name: '已冻结成员（当前名称尚未加载）', team_id: '', team_name: '' })
  })
  return [...map.values()]
})
const can = (name: string) => Boolean(caps.value?.actions.includes(name))
const own = (row: LaunchTemplate) => row.ownership.owner_user_id === caps.value?.actor_user_id
watch(
  () => props.active,
  async (active) => {
    readEpoch++
    loading.value = false
    if (active) {
      try {
        await load('')
      } catch (cause) {
        error.value = message(cause)
      }
    }
  },
  { immediate: true },
)
watch([editorOpen, actionOpen, busy, uncertain], () => {
  emit('blocked', editorOpen.value || actionOpen.value || busy.value || uncertain.value)
})
watch(listBlocked, (blocked) => {
  if (blocked) {
    readEpoch++
    loading.value = false
  }
})
watch(error, (value) => {
  if (value && !props.active && !editorOpen.value && !actionOpen.value) emit('failure', value)
})
function message(cause: unknown) {
  return cause instanceof Error ? cause.message : '操作失败，请重试'
}
async function ensureCaps() {
  caps.value = await templateApi.capabilities()
  recovered.value = readTemplateIntent(caps.value.actor_user_id)
  return caps.value
}
async function load(cursor: string, index = 0, confirmed = false) {
  if (!props.active || (!confirmed && listBlocked.value) || (cursor && pageDirty.value)) return
  const epoch = ++readEpoch,
    signature = filterSignature.value
  const query = new URLSearchParams({
    page_size: String(pageSize.value),
    ...(q.value.trim() ? { q: q.value.normalize('NFC').trim() } : {}),
    ...(status.value ? { status: status.value } : {}),
    ...(dates.value?.[0] ? { date_from: dates.value[0], date_to: dates.value[1] } : {}),
    ...(cursor ? { cursor } : {}),
  })
  loading.value = true
  error.value = ''
  try {
    const current = await templateApi.capabilities()
    if (!alive || epoch !== readEpoch) return
    caps.value = current
    recovered.value = readTemplateIntent(current.actor_user_id)
    const page = await templateApi.list(query)
    if (!alive || epoch !== readEpoch) return
    rows.value = page.items
    nextCursor.value = page.next_cursor
    dataAsOf.value = page.data_as_of
    appliedFilters.value = signature
    pageHistory.value = cursor ? [...pageHistory.value.slice(0, index), cursor] : ['']
    historyIndex.value = cursor ? index : 0
  } catch (cause) {
    if (!alive || epoch !== readEpoch) return
    if (cause instanceof ReferenceApiError && [400, 401, 403, 409, 410].includes(cause.status)) {
      rows.value = []
      nextCursor.value = null
      dataAsOf.value = ''
      pageHistory.value = ['']
      historyIndex.value = 0
      appliedFilters.value = ''
      if ([401, 403].includes(cause.status)) caps.value = undefined
    }
    error.value = `${message(cause)}${cause instanceof ReferenceApiError && [400, 409, 410].includes(cause.status) ? '；旧分页已清除，请重新读取模板首页。' : ''}`
  } finally {
    if (epoch === readEpoch) loading.value = false
  }
}
function nextPage() {
  if (nextCursor.value && !loading.value && !listBlocked.value && !pageDirty.value)
    void load(nextCursor.value, historyIndex.value + 1)
}
function previousPage() {
  if (historyIndex.value > 0 && !loading.value && !listBlocked.value && !pageDirty.value) {
    const index = historyIndex.value - 1
    void load(pageHistory.value[index], index)
  }
}
onBeforeUnmount(() => {
  alive = false
  readEpoch++
})
async function createFrom(campaigns: CampaignConfig[]) {
  if (busy.value || uncertain.value) return
  try {
    await ensureCaps()
    if (recovered.value) {
      error.value = '请先恢复并确认之前的模板操作，原操作仍保留。'
      return
    }
    if (!can('create')) {
      error.value = '当前未授予模板创建权限'
      return
    }
    target.value = undefined
    readOnly.value = false
    form.value = {
      name: '',
      description: '',
      visibility: 'PRIVATE',
      recipient_user_ids: [],
      campaigns: cloneValue(campaigns),
    }
    initialForm.value = JSON.stringify(form.value)
    pending = null
    error.value = ''
    recipientRows.value = []
    recipientCursor.value = null
    editorOpen.value = true
  } catch (cause) {
    error.value = message(cause)
  }
}
async function open(row: LaunchTemplate, readonly: boolean) {
  if (busy.value || uncertain.value) return
  try {
    target.value = await templateApi.get(row.id)
    readOnly.value = readonly
    const value = target.value
    form.value = {
      name: value.name,
      description: value.description,
      visibility: value.visibility,
      recipient_user_ids: [...value.recipient_user_ids],
      campaigns: cloneValue(value.campaigns),
    }
    initialForm.value = JSON.stringify(form.value)
    pending = null
    error.value = ''
    recipientRows.value = []
    recipientCursor.value = null
    editorOpen.value = true
    if (value.visibility === 'TEAM' && can('share') && !readonly) await loadRecipients(false)
  } catch (cause) {
    error.value = message(cause)
  }
}
async function visibilityChanged() {
  if (form.value.visibility === 'PRIVATE') form.value.recipient_user_ids = []
  else if (can('share')) await loadRecipients(false)
}
async function loadRecipients(more: boolean) {
  if (recipientLoading.value || !can('share')) return
  recipientLoading.value = true
  try {
    const page = await templateApi.recipients(
      target.value?.id,
      more ? (recipientCursor.value ?? '') : '',
    )
    const map = new Map((more ? recipientRows.value : []).map((item) => [item.id, item]))
    page.items.forEach((item) => map.set(item.id, item))
    recipientRows.value = [...map.values()]
    recipientCursor.value = page.next_cursor
    recipientCsrf.value = page.csrf_token
  } catch (cause) {
    error.value = message(cause)
  } finally {
    recipientLoading.value = false
  }
}
async function perform(
  run: (key: string) => Promise<LaunchTemplate | LaunchPlan>,
  success: (result: LaunchTemplate | LaunchPlan) => void,
  mutation: TemplateMutation,
) {
  if (busy.value || uncertain.value) return
  if (recovered.value) {
    error.value = '请先恢复并确认之前的模板操作，原操作仍保留。'
    return
  }
  pending = { run, success, key: crypto.randomUUID() }
  if (caps.value) {
    try {
      cacheTemplateIntent({ actor: caps.value.actor_user_id, key: pending.key, mutation })
      cacheWarning.value = ''
    } catch {
      cacheWarning.value = '浏览器恢复缓存不可用。操作仍在本页保留，结果确认前请勿刷新。'
    }
  }
  await send()
}
async function send() {
  if (!pending || busy.value) return
  const wasUncertain = uncertain.value
  busy.value = true
  error.value = ''
  try {
    const result = await pending.run(pending.key)
    const callback = pending.success
    pending = null
    uncertain.value = false
    if (caps.value) {
      try {
        clearTemplateIntent(caps.value.actor_user_id)
      } catch {
        cacheWarning.value = '服务器操作已确认，但本机旧缓存未清除；再次恢复仍会重放同一次操作。'
      }
    }
    recovered.value = null
    callback(result)
    if (props.active) await load('', 0, true)
  } catch (cause) {
    uncertain.value =
      wasUncertain ||
      (cause instanceof ReferenceApiError && (cause.status === 0 || cause.status >= 500))
    if (!uncertain.value) {
      pending = null
      if (caps.value) {
        try {
          clearTemplateIntent(caps.value.actor_user_id)
        } catch {
          /* 当前结果已明确，保留旧缓存不重复创建。 */
        }
      }
    } else if (caps.value) recovered.value = readTemplateIntent(caps.value.actor_user_id)
    error.value = message(cause)
  } finally {
    busy.value = false
  }
}
async function retry() {
  await send()
}
async function resume() {
  if (busy.value) return
  try {
    await ensureCaps()
    const value = recovered.value
    if (!value || !caps.value) return
    const mutation = cloneValue(value.mutation),
      csrf = caps.value.csrf_token
    const run = (key: string) => {
      if (mutation.kind === 'save')
        return templateApi.save(mutation.body, csrf, key, mutation.existing)
      if (mutation.kind === 'share')
        return templateApi.share(mutation.existing, mutation.recipients, mutation.reason, csrf, key)
      if (mutation.kind === 'archive')
        return templateApi.archive(mutation.existing, mutation.reason, csrf, key)
      return templateApi.apply(mutation.existing, mutation.ownership, mutation.reason, csrf, key)
    }
    pending = {
      key: value.key,
      run,
      success: (result) => {
        editorOpen.value = false
        actionOpen.value = false
        if (mutation.kind === 'apply') emit('applied', result as LaunchPlan)
      },
    }
    uncertain.value = true
    await send()
  } catch (cause) {
    error.value = message(cause)
  }
}
async function saveTemplate() {
  if (!caps.value || busy.value || uncertain.value || readOnly.value || metricBrowsing.value) return
  const name = form.value.name.normalize('NFC').trim(),
    description = form.value.description.normalize('NFC').trim()
  if (
    !codePoints(name) ||
    codePoints(name) > 80 ||
    codePoints(description) > 500 ||
    !form.value.campaigns.length
  ) {
    error.value = '请填写1—80码点名称、最多500码点说明，以及至少1个系列配置'
    return
  }
  if (form.value.recipient_user_ids.length > 500) {
    error.value = '明确共享成员最多500人'
    return
  }
  const base = newDraft({
    owner_user_id: caps.value.actor_user_id,
    owner_team_id: caps.value.actor_team_id,
  })
  base.campaigns = cloneValue(form.value.campaigns)
  const body: TemplateWrite = {
    name,
    description,
    visibility: form.value.visibility,
    recipient_user_ids: [...form.value.recipient_user_ids],
    campaigns: normalizeDraft(base).campaigns,
  }
  const current = target.value
    ? { id: target.value.id, revision: target.value.revision }
    : undefined
  const csrf = caps.value.csrf_token
  await perform(
    (key) => templateApi.save(body, csrf, key, current),
    () => {
      editorOpen.value = false
    },
    { kind: 'save', body: cloneValue(body), existing: current },
  )
}
async function shareTemplate(row: LaunchTemplate) {
  if (!(await prepareAction(row))) return
  action.value = 'share'
  actionRecipients.value = [...target.value!.recipient_user_ids]
  reason.value = ''
  pending = null
  error.value = ''
  actionOpen.value = true
  await loadRecipients(false)
}
async function archiveTemplate(row: LaunchTemplate) {
  if (!(await prepareAction(row))) return
  action.value = 'archive'
  reason.value = ''
  pending = null
  error.value = ''
  actionOpen.value = true
}
async function loadApplyOwners(more: boolean) {
  recipientLoading.value = true
  try {
    const page = await launchApi.owners(more ? (applyOwnerCursor.value ?? '') : '')
    const initial: OwnerOption[] = caps.value
      ? [
          {
            id: caps.value.actor_user_id,
            team_id: caps.value.actor_team_id,
            name: caps.value.actor_label,
            team_name: '',
          },
        ]
      : []
    const map = new Map((more ? applyOwners.value : initial).map((item) => [item.id, item]))
    page.items.forEach((person) => map.set(person.id, person))
    applyOwners.value = [...map.values()]
    applyOwnerCursor.value = page.next_cursor
  } catch (cause) {
    error.value = message(cause)
  } finally {
    recipientLoading.value = false
  }
}
async function applyTemplate(row: LaunchTemplate) {
  if (!(await prepareAction(row))) return
  action.value = 'apply'
  reason.value = ''
  pending = null
  error.value = ''
  applyOwnerId.value = caps.value?.actor_user_id ?? ''
  actionOpen.value = true
  await loadApplyOwners(false)
}
async function prepareAction(row: LaunchTemplate) {
  if (busy.value || uncertain.value || recovered.value) {
    error.value = '请先确认此前的模板操作，不能丢失待确认意图。'
    return false
  }
  try {
    target.value = await templateApi.get(row.id)
    return true
  } catch (cause) {
    error.value = message(cause)
    return false
  }
}
async function confirmAction() {
  if (!target.value || !caps.value || busy.value || uncertain.value) return
  const why = reason.value.normalize('NFC').trim()
  if (!codePoints(why) || codePoints(why) > 1000) {
    error.value = '请填写1—1000码点操作原因'
    return
  }
  const current = cloneValue(target.value),
    csrf = caps.value.csrf_token
  if (action.value === 'share') {
    if (!actionRecipients.value.length || actionRecipients.value.length > 500) {
      error.value = '分享需要1—500个明确接收者'
      return
    }
    const ids = [...actionRecipients.value]
    await perform(
      (key) => templateApi.share(current, ids, why, recipientCsrf.value || csrf, key),
      () => {
        actionOpen.value = false
      },
      {
        kind: 'share',
        existing: { id: current.id, revision: current.revision },
        recipients: ids,
        reason: why,
      },
    )
  } else if (action.value === 'archive')
    await perform(
      (key) => templateApi.archive(current, why, csrf, key),
      () => {
        actionOpen.value = false
      },
      { kind: 'archive', existing: { id: current.id, revision: current.revision }, reason: why },
    )
  else {
    const owner = applyOwners.value.find((person) => person.id === applyOwnerId.value)
    if (!owner) {
      error.value = '请从当前可用负责人候选中选择'
      return
    }
    const ownership = { owner_user_id: owner.id, owner_team_id: owner.team_id }
    await perform(
      (key) => templateApi.apply(current, ownership, why, csrf, key),
      (result) => {
        actionOpen.value = false
        emit('applied', result as LaunchPlan)
      },
      {
        kind: 'apply',
        existing: { id: current.id, revision: current.revision },
        ownership,
        reason: why,
      },
    )
  }
}
async function refreshEditor() {
  if (!target.value || busy.value || uncertain.value || metricBrowsing.value) return
  try {
    await ElMessageBox.confirm('当前未保存模板配置将被服务器版本替换，是否继续？', '读取当前版本')
    await open(target.value, false)
  } catch {
    /* 取消保留当前配置。 */
  }
}
async function beforeEditorClose(done: () => void) {
  if (busy.value || uncertain.value || metricBrowsing.value) return
  if (!readOnly.value && JSON.stringify(form.value) !== initialForm.value) {
    try {
      await ElMessageBox.confirm('模板配置尚未保存，是否放弃本次编辑？', '未保存模板', {
        type: 'warning',
      })
    } catch {
      return
    }
  }
  done()
}
function requestEditorClose() {
  void beforeEditorClose(() => {
    editorOpen.value = false
  })
}
function beforeActionClose(done: () => void) {
  if (!busy.value && !uncertain.value) done()
}
defineExpose({ createFrom })
</script>

<style scoped>
.template-tools {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.template-tools :deep(.el-input) {
  width: min(300px, 100%);
}
.template-tools :deep(.el-select) {
  width: 150px;
}
.template-tools :deep(.el-date-editor) {
  max-width: 100%;
}
.template-metadata {
  margin: 12px 0;
}
.template-full {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.template-page-status {
  color: var(--el-text-color-secondary);
}
:deep(.el-select) {
  width: 100%;
}
:deep(.el-alert) {
  margin: 12px 0;
}
</style>
