<template>
  <div class="app-container launch-page prototype-page">
    <header class="prototype-heading">
      <h2>创建广告</h2>
      <div>
        <el-button @click="switchSection('templates')">选择模板</el-button
        ><el-button v-if="canReadTasks" @click="switchSection('tasks')">执行任务</el-button>
      </div>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="taskFallback && canReadTasks"
      title="当前账号可读取任务，计划读取权限尚未授予，已切换任务查询。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="recovery"
      :title="
        recovery.pendingKey
          ? '发现一次结果待确认的草稿保存。恢复后将重试原操作，不能另建重复计划。'
          : '发现当前账号的本机未保存草稿。服务器草稿始终为准。'
      "
      type="warning"
      :closable="false"
      ><el-button :disabled="pageBusy" @click="restore">恢复本机配置</el-button
      ><el-button v-if="!recovery.pendingKey" :disabled="pageBusy" @click="discardRecovery"
        >清除恢复缓存</el-button
      ></el-alert
    >
    <el-tabs v-model="active" :before-leave="beforeTab">
      <el-tab-pane label="创建广告" name="plans" :disabled="planTabDisabled">
        <div v-if="!editorOpen" class="draft-management">
          <div class="launch-tools">
            <el-input
              v-model="q"
              placeholder="搜索计划名称"
              clearable
              :disabled="loading || pageBusy"
              @keyup.enter="load('')"
            /><el-select
              v-model="status"
              clearable
              placeholder="全部状态"
              :disabled="loading || pageBusy"
              ><el-option
                v-for="state in states"
                :key="state.value"
                :label="state.label"
                :value="state.value" /></el-select
            ><el-date-picker
              v-model="dates"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="创建日期起（UTC）"
              end-placeholder="创建日期止（UTC）"
              :disabled="loading || pageBusy"
            /><el-button :disabled="loading || pageBusy" @click="load('')">查询计划</el-button
            ><el-button
              v-if="capabilities?.actions.includes('create')"
              type="primary"
              :disabled="pageBusy || Boolean(recovery?.pendingKey)"
              @click="create"
              >创建广告</el-button
            >
          </div>
          <p class="quiet">
            保存草稿不会创建广告；启用和执行须完成独立核验。{{
              dataAsOf ? `本页数据时刻 ${dataAsOf}（UTC）` : ''
            }}
          </p>
          <el-alert
            v-if="!validationAvailable"
            title="预检依赖尚未就绪或当前账号没有计划编辑权限；预检入口关闭，不会发起命名、分配或预检请求。"
            type="info"
            :closable="false"
          />
          <el-alert
            v-else-if="!executionAvailable"
            title="可按当前服务端能力预检；执行依赖尚未就绪，不会提交广告任务。"
            type="info"
            :closable="false"
          />
          <p v-if="validationLoading" role="status">
            正在读取服务器当前计划与预检权限。<el-button @click="cancelValidationRead"
              >取消本地读取</el-button
            >
          </p>
          <el-table v-loading="loading" :data="plans" row-key="id" style="width: 100%"
            ><el-table-column prop="name" label="计划名称" min-width="180"
              ><template #default="scope">{{
                scope.row.name || '未命名草稿'
              }}</template></el-table-column
            ><el-table-column label="账户 / 素材" width="140"
              ><template #default="scope"
                >{{ scope.row.account_ids.length }} / {{ scope.row.asset_ids.length }}</template
              ></el-table-column
            ><el-table-column label="状态 / 版本" width="160"
              ><template #default="scope"
                ><el-tag>{{ label(scope.row.state) }}</el-tag> · {{ scope.row.revision }}</template
              ></el-table-column
            ><el-table-column
              prop="updated_at"
              label="最近保存（UTC）"
              min-width="210"
            /><el-table-column label="操作" min-width="270"
              ><template #default="scope"
                ><el-button link :disabled="pageBusy" @click="open(scope.row, true)">详情</el-button
                ><el-button
                  v-if="
                    capabilities?.actions.includes('edit') &&
                    ['DRAFT', 'VALIDATED'].includes(scope.row.state)
                  "
                  link
                  :disabled="pageBusy"
                  @click="open(scope.row, false)"
                  >编辑草稿</el-button
                ><el-button
                  v-if="['DRAFT', 'VALIDATED'].includes(scope.row.state)"
                  link
                  :disabled="pageBusy || !validationAvailable || Boolean(recovery?.pendingKey)"
                  @click="openValidation(scope.row)"
                  >投放预检</el-button
                ></template
              ></el-table-column
            ></el-table
          >
          <div class="launch-tools">
            <el-select
              v-model="pageSize"
              aria-label="每页计划数量"
              :disabled="loading || pageBusy"
              @change="load('')"
              ><el-option
                v-for="size in [20, 50, 100, 200]"
                :key="size"
                :label="`${size}个`"
                :value="size"
            /></el-select>
            <el-button :disabled="loading || pageBusy" @click="load('')">重新读取首页</el-button
            ><el-button
              :disabled="loading || pageBusy || pageDirty || historyIndex === 0"
              @click="previousPlanPage"
              >上一页计划</el-button
            ><el-button
              v-if="nextCursor"
              :disabled="loading || pageBusy || pageDirty"
              @click="nextPlanPage"
              >下一页计划</el-button
            >
            <span role="status"
              >第 {{ historyIndex + 1 }} 页 · 当前返回 {{ plans.length }} 项。{{
                pageDirty ? '条件已变化，请查询后翻页。' : ''
              }}{{ error && plans.length ? '保留上次成功读取的数据。' : '' }}</span
            >
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="模板管理" name="templates" :disabled="templateTabDisabled" />
      <el-tab-pane v-if="canReadTasks" label="执行任务" name="tasks" />
    </el-tabs>
    <TaskPanel v-if="canReadTasks" :active="active === 'tasks'" :context-key="accountContextKey" />
    <TemplatesPanel
      ref="templatesPanel"
      :active="active === 'templates'"
      :metric-read-allowed="has('monitor.read')"
      :metric-context-key="accountContextKey"
      @applied="applied"
      @blocked="templateBlocked = $event"
      @failure="showFailure"
    />
    <DraftEditor
      ref="draftEditor"
      prototype
      :validation-available="validationAvailable"
      @validate="validateInline"
      v-model="editorOpen"
      :plan="editing"
      :read-only="readOnly"
      :capabilities="capabilities"
      :recovery="editingRecovery"
      :identity-read-allowed="has('accounts.read')"
      :metric-read-allowed="has('monitor.read')"
      :account-context-key="accountContextKey"
      :focus-field="fieldLocation"
      @saved="saved"
      @template="saveAsTemplate"
      @locked="draftBlocked = $event"
      @closed="closed"
    />
    <PlanValidationDialog
      v-if="validationPlan && validationCapabilities"
      :key="validationSession"
      :model-value="validationOpen"
      :plan="validationPlan"
      :capabilities="validationCapabilities"
      :validation-available="validationCapabilities.validation_available === true"
      :execute-available="validationCapabilities.execution_available === true"
      @update:model-value="setValidationOpen"
      @locked="validationBlocked = $event"
      @locate="locateValidationField"
      @accepted="validationAccepted"
    />
    <TaskDetails
      v-if="canReadTasks"
      v-model="acceptedTaskOpen"
      :task-id="acceptedTaskId"
      :active="active === 'tasks'"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  launchApi,
  type CampaignConfig,
  type LaunchCapabilities,
  type LaunchPlan,
} from '@/api/orbit/launch'
import {
  readDraftRecovery,
  clearDraftRecovery,
  type DraftRecovery,
} from '@/api/orbit/launch-recovery'
import DraftEditor from './DraftEditor.vue'
import TemplatesPanel from './TemplatesPanel.vue'
import TaskPanel from './TaskPanel.vue'
import TaskDetails from './TaskDetails.vue'
import PlanValidationDialog from './PlanValidationDialog.vue'
import { parseTask, type Task } from '@/api/orbit/tasks'
import useUserStore from '@/store/modules/user'
import { ReferenceApiError } from '@/api/orbit/references'
const draftEditor = ref<InstanceType<typeof DraftEditor>>()
const user = useUserStore()
// 若依当前会话权限控制入口；数据每次GET仍由服务端即时复核，不借launch.read读取任务。
const has = (permission: string) =>
  user.permissions.includes('*:*:*') || user.permissions.includes(permission)
const canReadTasks = computed(() => has('tasks.read'))
// 仅传公开身份/权限与非敏感会话代次；CSRF变化只递增代次，凭据不进入context字符串或缓存。
const accountSessionEpoch = ref(0)
const accountContextKey = computed(() =>
  JSON.stringify([
    user.id ?? '',
    capabilities.value?.actor_user_id ?? '',
    [...(user.roles ?? [])].sort(),
    [...user.permissions].sort(),
    accountSessionEpoch.value,
  ]),
)
// 原若依父菜单可能包含launch.read字样；动作权限以Python实际403为准，不能把父菜单当读取授权。
const taskFallback = ref(false)
const planTabDisabled = computed(
  () => canReadTasks.value && (taskFallback.value || !has('launch.read')),
)
const templateTabDisabled = computed(() => canReadTasks.value && !has('templates.read'))
const active = ref(planTabDisabled.value ? 'tasks' : 'plans'),
  error = ref(''),
  loading = ref(false),
  plans = ref<LaunchPlan[]>([]),
  nextCursor = ref<string | null>(null),
  dataAsOf = ref(''),
  capabilities = ref<LaunchCapabilities>(),
  q = ref(''),
  status = ref(''),
  dates = ref<string[] | null>(null)
watch(
  () => capabilities.value?.csrf_token,
  () => {
    accountSessionEpoch.value++
  },
)
const editorOpen = ref(false),
  editing = ref<LaunchPlan>(),
  readOnly = ref(false),
  editingRecovery = ref<DraftRecovery | null>(null),
  recovery = ref<DraftRecovery | null>(null),
  draftBlocked = ref(false),
  templateBlocked = ref(false),
  templatesPanel = ref<InstanceType<typeof TemplatesPanel>>()
const validationOpen = ref(false),
  validationBlocked = ref(false),
  validationLoading = ref(false),
  editorLoading = ref(false),
  validationPlan = ref<LaunchPlan>(),
  validationCapabilities = ref<LaunchCapabilities>(),
  validationSession = ref(0)
const acceptedTaskOpen = ref(false),
  acceptedTaskId = ref<string | null>(null)
const fieldLocation = ref<{ path: string; segments: string[]; revision: number } | undefined>()
const validationAvailable = computed(
  () =>
    capabilities.value?.validation_available === true &&
    capabilities.value.actions.includes('edit'),
)
const executionAvailable = computed(
  () =>
    capabilities.value?.execution_available === true &&
    capabilities.value.actions.includes('execute'),
)
const pageBusy = computed(
  () =>
    editorOpen.value ||
    draftBlocked.value ||
    templateBlocked.value ||
    validationOpen.value ||
    validationBlocked.value ||
    validationLoading.value ||
    editorLoading.value,
)
let validationEpoch = 0,
  alive = true
const pageSize = ref<20 | 50 | 100 | 200>(20),
  pageHistory = ref<string[]>(['']),
  historyIndex = ref(0),
  appliedFilters = ref('')
const filterSignature = computed(() =>
  JSON.stringify([q.value.normalize('NFC').trim(), status.value, dates.value, pageSize.value]),
)
const pageDirty = computed(() => appliedFilters.value !== filterSignature.value)
// 仅后端已确认的模板apply允许内部切页；普通未保存/待确认意图仍受离开门禁约束。
const switchingAppliedDraft = ref(false)
const states = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'VALIDATED', label: '已预检' },
  { value: 'SUBMITTED', label: '已提交' },
  { value: 'ARCHIVED', label: '已归档' },
]
let readEpoch = 0,
  debounce: ReturnType<typeof setTimeout> | undefined
function label(state: string) {
  return states.find((item) => item.value === state)?.label ?? state
}
async function load(cursor: string, index = 0) {
  if (debounce) clearTimeout(debounce)
  if (
    planTabDisabled.value ||
    validationOpen.value ||
    validationBlocked.value ||
    validationLoading.value ||
    editorLoading.value ||
    (cursor && pageDirty.value)
  )
    return
  const epoch = ++readEpoch
  const signature = filterSignature.value
  const filters = new URLSearchParams({
    page_size: String(pageSize.value),
    ...(q.value.trim() ? { q: q.value.normalize('NFC').trim() } : {}),
    ...(status.value ? { status: status.value } : {}),
    ...(dates.value?.[0] ? { date_from: dates.value[0], date_to: dates.value[1] } : {}),
    ...(cursor ? { cursor } : {}),
  })
  loading.value = true
  error.value = ''
  try {
    const currentCapabilities = await launchApi.capabilities()
    if (epoch !== readEpoch) return
    capabilities.value = currentCapabilities
    const page = await launchApi.list(filters)
    if (epoch !== readEpoch) return
    plans.value = page.items
    nextCursor.value = page.next_cursor
    dataAsOf.value = page.data_as_of
    appliedFilters.value = signature
    pageHistory.value = cursor ? [...pageHistory.value.slice(0, index), cursor] : ['']
    historyIndex.value = cursor ? index : 0
    recovery.value = readDraftRecovery(capabilities.value.actor_user_id)
  } catch (cause) {
    if (epoch === readEpoch) {
      if (cause instanceof ReferenceApiError && [400, 401, 403, 409, 410].includes(cause.status)) {
        plans.value = []
        nextCursor.value = null
        dataAsOf.value = ''
        pageHistory.value = ['']
        historyIndex.value = 0
        appliedFilters.value = ''
        if ([401, 403].includes(cause.status)) capabilities.value = undefined
      }
      if (cause instanceof ReferenceApiError && cause.status === 403 && canReadTasks.value) {
        taskFallback.value = true
        plans.value = []
        nextCursor.value = null
        dataAsOf.value = ''
        capabilities.value = undefined
        recovery.value = null
        // 只撤下计划数据；现有未确认编辑意图仍受原离开门禁保护，不清除本机恢复缓存。
        if (!editorOpen.value && !draftBlocked.value && !templateBlocked.value)
          active.value = 'tasks'
      } else
        error.value =
          cause instanceof Error
            ? `${cause.message}${cause instanceof ReferenceApiError && [400, 409, 410].includes(cause.status) ? '；旧分页已清除，请重新读取首页。' : ''}`
            : '计划读取失败，请重试'
    }
  } finally {
    if (epoch === readEpoch) loading.value = false
  }
}
function nextPlanPage() {
  if (nextCursor.value && !pageBusy.value && !loading.value && !pageDirty.value)
    void load(nextCursor.value, historyIndex.value + 1)
}
function previousPlanPage() {
  if (historyIndex.value > 0 && !pageBusy.value && !loading.value && !pageDirty.value) {
    const index = historyIndex.value - 1
    void load(pageHistory.value[index], index)
  }
}
async function create() {
  if (
    !capabilities.value ||
    editorOpen.value ||
    editorLoading.value ||
    draftBlocked.value ||
    templateBlocked.value ||
    validationOpen.value ||
    validationBlocked.value ||
    validationLoading.value ||
    recovery.value?.pendingKey
  )
    return
  editing.value = undefined
  fieldLocation.value = undefined
  editingRecovery.value = null
  readOnly.value = false
  editorOpen.value = true
}
async function open(plan: LaunchPlan, readonly: boolean) {
  if (pageBusy.value) return
  const epoch = ++validationEpoch
  editorLoading.value = true
  try {
    const fresh = await launchApi.get(plan.id)
    if (!alive || epoch !== validationEpoch) return
    editing.value = fresh
    fieldLocation.value = undefined
    editingRecovery.value = null
    readOnly.value = readonly
    editorOpen.value = true
  } catch (cause) {
    if (alive && epoch === validationEpoch)
      error.value = cause instanceof Error ? cause.message : '草稿详情读取失败'
  } finally {
    if (epoch === validationEpoch) editorLoading.value = false
  }
}
async function restore() {
  if (!recovery.value || pageBusy.value) return
  const epoch = ++validationEpoch
  editorLoading.value = true
  try {
    const fresh = recovery.value.existing
      ? await launchApi.get(recovery.value.existing.id)
      : undefined
    if (!alive || epoch !== validationEpoch) return
    editing.value = fresh
    editingRecovery.value = recovery.value
    fieldLocation.value = undefined
    readOnly.value = false
    editorOpen.value = true
  } catch (cause) {
    if (alive && epoch === validationEpoch)
      error.value = cause instanceof Error ? cause.message : '恢复前服务器版本读取失败，原缓存保留'
  } finally {
    if (epoch === validationEpoch) editorLoading.value = false
  }
}
async function discardRecovery() {
  if (!capabilities.value || recovery.value?.pendingKey || pageBusy.value) return
  try {
    await ElMessageBox.confirm('仅清除本机未保存配置，不影响服务器草稿。是否继续？', '清除恢复缓存')
    clearDraftRecovery(capabilities.value.actor_user_id)
    recovery.value = null
  } catch {
    /* 取消保留恢复数据。 */
  }
}
async function saved(plan: LaunchPlan) {
  editing.value = plan
  fieldLocation.value = undefined
  recovery.value = null
  editingRecovery.value = null
  await load('')
}
function closed() {
  if (capabilities.value) recovery.value = readDraftRecovery(capabilities.value.actor_user_id)
}
function saveAsTemplate(campaigns: CampaignConfig[]) {
  void templatesPanel.value?.createFrom(campaigns)
}
function showFailure(message: string) {
  error.value = message
  ElMessage.error(message)
}
async function applied(plan: LaunchPlan) {
  fieldLocation.value = undefined
  switchingAppliedDraft.value = true
  try {
    active.value = 'plans'
    // Element Plus也会对外部modelValue调用beforeLeave；先完成内部选中状态，再开编辑抽屉。
    await nextTick()
  } finally {
    switchingAppliedDraft.value = false
  }
  editing.value = plan
  editingRecovery.value = null
  readOnly.value = false
  editorOpen.value = true
  await load('')
}
async function switchSection(name: string) {
  if (await beforeTab()) active.value = name
}
async function beforeTab() {
  if (switchingAppliedDraft.value) return true
  if (editorOpen.value && !draftBlocked.value) await draftEditor.value?.requestClose?.()
  return !pageBusy.value
}
async function validateInline(plan: LaunchPlan) {
  editorOpen.value = false
  await nextTick()
  await openValidation(plan)
}
onBeforeRouteLeave(() => {
  if (editorOpen.value && !draftBlocked.value && draftEditor.value?.requestClose)
    return draftEditor.value
      .requestClose()
      .then(() => !editorOpen.value && !validationBlocked.value && !validationOpen.value)
  if (
    editorOpen.value ||
    draftBlocked.value ||
    templateBlocked.value ||
    validationOpen.value ||
    validationBlocked.value
  ) {
    error.value = '请先关闭当前编辑窗口；待确认保存必须先重试确认，避免丢失操作意图。'
    return false
  }
  cancelValidationRead()
  return true
})
onMounted(() => {
  window.addEventListener('beforeunload', protectPendingValidation)
  if (!planTabDisabled.value) {
    const initialEpoch = readEpoch + 1
    void load('').then(() => {
      if (
        readEpoch === initialEpoch &&
        active.value === 'plans' &&
        !error.value &&
        capabilities.value?.actions.includes('create') &&
        !recovery.value
      )
        void create()
    })
  }
})
watch(canReadTasks, (allowed) => {
  if (!allowed && active.value === 'tasks') {
    acceptedTaskOpen.value = false
    acceptedTaskId.value = null
    active.value = 'plans'
    error.value = '当前任务读取权限已撤销，旧任务数据已清除。'
  }
})
watch(active, (value) => {
  if (value !== 'plans') {
    readEpoch++
    loading.value = false
    if (debounce) clearTimeout(debounce)
  }
})
watch(
  [q, status, dates],
  () => {
    if (debounce) clearTimeout(debounce)
    debounce = setTimeout(() => {
      if (!pageBusy.value) void load('')
    }, 300)
  },
  { deep: true },
)
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', protectPendingValidation)
  alive = false
  cancelValidationRead()
  readEpoch++
  if (debounce) clearTimeout(debounce)
})
function cancelValidationRead() {
  validationEpoch++
  validationLoading.value = false
  editorLoading.value = false
}
function protectPendingValidation(event: BeforeUnloadEvent) {
  if (!validationBlocked.value) return
  // 写入意图只在组件内存；浏览器原生离开提示保护它，不能把CSRF或请求头持久化。
  event.preventDefault()
  event.returnValue = ''
}
async function openValidation(plan: LaunchPlan) {
  if (pageBusy.value || !validationAvailable.value || recovery.value?.pendingKey) return
  const epoch = ++validationEpoch
  validationLoading.value = true
  error.value = ''
  try {
    const current = await launchApi.capabilities()
    if (!alive || epoch !== validationEpoch) return
    capabilities.value = current
    if (current.validation_available !== true || !current.actions.includes('edit')) {
      error.value = '预检依赖或编辑权限已变化，未发起预检。'
      return
    }
    const fresh = await launchApi.get(plan.id)
    if (!alive || epoch !== validationEpoch) return
    if (fresh.id !== plan.id || !['DRAFT', 'VALIDATED'].includes(fresh.state)) {
      error.value = '服务器当前计划状态不允许预检，请重新读取列表。'
      return
    }
    // 独立冻结本次已保存head与写上下文；不因列表刷新替换未知请求的CSRF/键或配置。
    validationPlan.value = JSON.parse(JSON.stringify(fresh))
    validationCapabilities.value = JSON.parse(JSON.stringify(current))
    validationSession.value++
    validationOpen.value = true
  } catch (cause) {
    if (alive && epoch === validationEpoch)
      error.value = cause instanceof Error ? cause.message : '预检前读取当前计划失败'
  } finally {
    if (epoch === validationEpoch) validationLoading.value = false
  }
}
function setValidationOpen(value: boolean) {
  if (!value && validationBlocked.value) {
    error.value = '原预检或提交结果尚未确认，不能关闭或丢弃原写入意图。'
    return
  }
  validationOpen.value = value
}
async function locateValidationField(path: string, segments: string[]) {
  if (validationBlocked.value || !validationPlan.value || editorOpen.value) return
  const decoded =
    path.startsWith('/') && !/~(?![01])/u.test(path)
      ? path
          .slice(1)
          .split('/')
          .map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'))
      : null
  if (!decoded || JSON.stringify(decoded) !== JSON.stringify(segments)) {
    error.value = '错误字段路径不符合JSON Pointer，未自动定位。'
    return
  }
  const source = validationPlan.value,
    epoch = ++validationEpoch
  validationLoading.value = true
  error.value = ''
  try {
    const fresh = await launchApi.get(source.id)
    if (!alive || epoch !== validationEpoch || validationBlocked.value) return
    if (fresh.id !== source.id) {
      error.value = '错误字段不属于当前服务器计划，未定位。'
      return
    }
    if (fresh.revision !== source.revision) {
      error.value = `错误来自已保存版本 ${source.revision}，服务器已是版本 ${fresh.revision}；旧字段位置可能陈旧，未按旧索引定位。原路径：${path}`
      return
    }
    validationOpen.value = false
    editing.value = fresh
    editingRecovery.value = null
    readOnly.value =
      !capabilities.value?.actions.includes('edit') || !['DRAFT', 'VALIDATED'].includes(fresh.state)
    fieldLocation.value = { path, segments: [...decoded], revision: fresh.revision }
    editorOpen.value = true
  } catch (cause) {
    if (alive && epoch === validationEpoch)
      error.value = cause instanceof Error ? cause.message : '字段定位前读取失败，原预检结果保留'
  } finally {
    if (epoch === validationEpoch) validationLoading.value = false
  }
}
async function validationAccepted(value: Task) {
  let task: Task
  try {
    task = parseTask(value)
  } catch {
    error.value = '任务受理响应不符合原Task合同，未打开伪任务。'
    return
  }
  validationBlocked.value = false
  validationOpen.value = false
  if (!canReadTasks.value) {
    error.value = `任务已受理：${task.id}。当前没有 tasks.read 权限，不能读取任务详情。`
    return
  }
  switchingAppliedDraft.value = true
  try {
    active.value = 'tasks'
    await nextTick()
  } finally {
    switchingAppliedDraft.value = false
  }
  acceptedTaskId.value = task.id
  acceptedTaskOpen.value = true
}
</script>

<style scoped>
.launch-tools {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0;
}
.launch-tools :deep(.el-input) {
  width: min(280px, 100%);
}
.launch-tools :deep(.el-select) {
  width: 160px;
}
.launch-tools :deep(.el-date-editor) {
  max-width: 100%;
}
.quiet {
  color: var(--el-text-color-secondary);
}
@media (max-width: 700px) {
  .launch-tools {
    align-items: stretch;
  }
  .launch-tools :deep(.el-date-editor) {
    width: 100%;
  }
}
</style>

<style scoped>
.prototype-page {
  background: #f2f4f8;
  min-height: 100vh;
  padding: 22px 24px;
  --el-color-primary: #3b5bdb;
}
.prototype-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1280px;
  margin: auto;
}
.prototype-heading > h2 {
  font-size: 23px;
  max-width: 1280px;
  margin: 0 0 18px;
}
.prototype-page > :deep(.el-tabs) {
  max-width: 1280px;
  margin: auto;
}
.prototype-page :deep(.el-tabs__header) {
  background: white;
  border-radius: 8px;
  padding: 0 16px;
  margin-bottom: 0;
}
.prototype-page :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}
.draft-management {
  background: white;
  padding: 20px;
  border-radius: 8px;
}
@media (max-width: 700px) {
  .prototype-page {
    padding: 14px 10px;
  }
}
</style>
