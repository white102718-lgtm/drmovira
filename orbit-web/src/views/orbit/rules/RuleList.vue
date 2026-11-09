<template>
  <section class="rule-list" aria-label="规则列表">
    <div class="toolbar">
      <el-input
        v-model="q"
        aria-label="规则名称"
        placeholder="规则名称包含，最多100字符"
        aria-describedby="rule-name-query-limit"
        clearable
        @keyup.enter="search"
      />
      <el-select v-model="status" aria-label="规则状态" clearable placeholder="全部状态"
        ><el-option v-for="s in states" :key="s" :value="s" :label="stateLabel[s]"
      /></el-select>
      <el-select v-model="entity" aria-label="对象层级" clearable placeholder="全部层级"
        ><el-option v-for="s in ['CAMPAIGN', 'ADSET', 'AD']" :key="s" :value="s" :label="s"
      /></el-select>
      <el-date-picker
        v-model="effectiveFrom"
        type="date"
        aria-label="规则生效日起"
        placeholder="生效日从"
        value-format="YYYY-MM-DD"
      />
      <el-date-picker
        v-model="effectiveTo"
        type="date"
        aria-label="规则生效日止"
        placeholder="生效日到"
        value-format="YYYY-MM-DD"
      />
      <RuleListFilterSelect
        v-model="operatorFilter"
        kind="OPERATOR"
        :context-key="context()"
        :disabled="!allowed('SIMULATE')"
        :refresh-key="filterRefresh"
        @denied="denyRead"
      />
      <RuleListFilterSelect
        v-model="profileFilter"
        kind="METRIC_PROFILE"
        :context-key="context()"
        :disabled="!allowed('SIMULATE')"
        :refresh-key="filterRefresh"
        @denied="denyRead"
      />
      <RuleListFilterSelect
        v-model="channelFilter"
        kind="CHANNEL"
        :context-key="context()"
        :disabled="!allowed('SIMULATE')"
        :refresh-key="filterRefresh"
        @denied="denyRead"
      />
      <el-button :disabled="!allowed('SIMULATE') || loading" @click="search">查询</el-button>
      <el-button
        v-if="allowed('CREATE')"
        :disabled="entryBusy || !!intent || busy"
        @click="entry('CREATE')"
        >创建规则</el-button
      >
    </div>
    <p id="rule-name-query-limit">名称包含查询最多100字符（按规范化后的Unicode码点计算）。</p>
    <el-alert v-if="queryError" :title="queryError" type="error" :closable="false" />
    <el-alert
      v-if="intent && intent.context !== context()"
      title="原身份存在结果未知的请求；恢复原认证上下文后才能重试。"
      type="warning"
      :closable="false"
    />
    <el-alert v-if="entryError" :title="entryError" type="error" :closable="false" />
    <el-alert v-if="!allowed('SIMULATE')" title="缺少规则读取权限" type="info" :closable="false" />
    <el-alert v-if="listError" :title="listError" type="error" :closable="false" />
    <el-alert v-if="listMetadataError" :title="listMetadataError" type="error" :closable="false" />
    <el-button
      v-if="listMetadataError && page?.items.length"
      :disabled="listMetadataLoading"
      @click="loadListMetadata(page.items, listEpoch)"
      >重试列表显示资料</el-button
    >
    <p v-if="listMetadataLoading" role="status">正在读取创建人与归属资料…</p>
    <p v-if="loading" role="status">正在读取规则…</p>
    <el-table :data="page?.items ?? []" row-key="id" empty-text="暂无已读取的规则">
      <el-table-column prop="name" label="规则名称" min-width="170" />
      <el-table-column label="条件摘要" min-width="270">
        <template #default="{ row }">
          <details class="rule-condition-summary">
            <summary>
              <span
                >根 {{ row.logic }} ·
                {{
                  row.groups.reduce(
                    (count: number, group: Rule['groups'][number]) =>
                      count + group.conditions.length,
                    0,
                  )
                }}
                条条件</span
              >
              <small
                >{{
                  row.groups
                    .map(
                      (group: Rule['groups'][number], index: number) =>
                        `组${index + 1} ${group.logic}`,
                    )
                    .join(' · ')
                }}
                · 展开查看</small
              >
            </summary>
            <div
              v-for="(group, groupIndex) in row.groups"
              :key="groupIndex"
              class="rule-condition-group"
            >
              <strong>组{{ groupIndex + 1 }} · {{ group.logic }}</strong>
              <p
                v-for="(leaf, leafIndex) in group.conditions"
                :key="leafIndex"
                class="rule-condition-leaf"
              >
                {{ leaf.metric }} {{ leaf.operator }} {{ leaf.threshold }}
              </p>
            </div>
          </details>
        </template>
      </el-table-column>
      <el-table-column label="账户范围" min-width="245">
        <template #default="{ row }">
          <div class="rule-account-scope">
            <small>范围快照 · 查看详情</small>
            <el-button
              link
              type="primary"
              :aria-label="`查看账户范围 ${row.scope_snapshot_id}`"
              :disabled="!!intent || busy || listMetadataStale"
              @click="openDetail(row.id)"
              >{{ row.scope_snapshot_id }}</el-button
            >
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100"
        ><template #default="{ row }">{{
          stateLabel[row.state as RuleState]
        }}</template></el-table-column
      >
      <el-table-column prop="target_level" label="对象层级" width="110" />
      <el-table-column label="投放师 / 团队" min-width="260"
        ><template #default="{ row }"
          >{{
            listMetadata[row.id]?.owner_user_name ?? metadataPlaceholder('list', '未记录投放师姓名')
          }}
          /
          {{
            listMetadata[row.id]?.owner_team_name ?? metadataPlaceholder('list', '未记录团队名称')
          }}
          <small class="metadata-id"
            >{{ row.ownership.owner_user_id }} / {{ row.ownership.owner_team_id }}</small
          ></template
        ></el-table-column
      >
      <el-table-column label="执行频次 / 时区" min-width="200"
        ><template #default="{ row }"
          >{{ scheduleSummary(row.schedule) }} / {{ row.schedule.timezone }}</template
        ></el-table-column
      >
      <el-table-column label="创建人 / 创建时间（UTC）" min-width="220"
        ><template #default="{ row }"
          ><template v-if="listMetadata[row.id]"
            >{{ listMetadata[row.id].created_by_name ?? '未记录创建人姓名' }} · 用户ID
            {{ listMetadata[row.id].created_by }}
            <small class="metadata-id">{{ listMetadata[row.id].created_at }}</small></template
          ><template v-else>{{ metadataPlaceholder('list', '显示资料待读取') }}</template></template
        ></el-table-column
      >
      <el-table-column prop="window" label="统计窗口" width="120" />
      <el-table-column prop="revision" label="版本" width="80" />
      <el-table-column label="下次运行（UTC）" min-width="200"
        ><template #default="{ row }">{{ row.next_run_at ?? '未安排' }}</template></el-table-column
      >
      <el-table-column label="操作" width="90" fixed="right"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            :disabled="!!intent || busy || listMetadataStale"
            @click="openDetail(row.id)"
            >详情</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <div class="pagination">
      <el-select v-model="pageSize" aria-label="每页条数" @change="search"
        ><el-option v-for="n in [20, 50, 100, 200]" :key="n" :value="n" :label="`${n} 条`"
      /></el-select>
      <el-button :disabled="loading || history.length === 0" @click="previous">上一页</el-button>
      <el-button :disabled="loading || !page?.next_cursor" @click="next">下一页</el-button>
      <span v-if="page">数据时间 {{ page.data_as_of }} · 范围版本 {{ page.scope_version }}</span>
    </div>
    <el-drawer
      :model-value="drawer"
      title="规则详情"
      size="min(760px, 100%)"
      :show-close="!intent && !busy"
      :close-on-press-escape="!intent && !busy"
      :close-on-click-modal="!intent && !busy"
      @close="closeDetail"
    >
      <p v-if="detailLoading" role="status">正在读取详情…</p>
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <template v-if="detail">
        <p v-if="detailMetadataLoading" role="status">正在读取此规则创建人与归属资料…</p>
        <el-alert
          v-if="detailMetadataError"
          :title="detailMetadataError"
          type="error"
          :closable="false"
        />
        <el-button :disabled="!!intent || busy" @click="openDetail(detail.id)"
          >重新读取详情</el-button
        >
        <el-descriptions :column="1" border>
          <el-descriptions-item label="规则 ID">{{ detail.id }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="版本 / 状态"
            >{{ detail.revision }} / {{ stateLabel[detail.state] }}</el-descriptions-item
          >
          <el-descriptions-item label="投放师 / 团队"
            >{{
              detailMetadata?.owner_user_name ?? metadataPlaceholder('detail', '未记录投放师姓名')
            }}
            /
            {{ detailMetadata?.owner_team_name ?? metadataPlaceholder('detail', '未记录团队名称') }}
            <small class="metadata-id"
              >{{ detail.ownership.owner_user_id }} / {{ detail.ownership.owner_team_id }}</small
            ></el-descriptions-item
          >
          <el-descriptions-item label="创建人 / 创建时间（UTC）">
            <template v-if="detailMetadata"
              >{{ detailMetadata.created_by_name ?? '未记录创建人姓名' }} · 用户ID
              {{ detailMetadata.created_by }} · {{ detailMetadata.created_at }}</template
            >
            <template v-else>{{ metadataPlaceholder('detail', '显示资料待读取') }}</template>
          </el-descriptions-item>
          <el-descriptions-item label="对象层级">{{ detail.target_level }}</el-descriptions-item>
          <el-descriptions-item label="账户范围快照">{{
            detail.scope_snapshot_id
          }}</el-descriptions-item>
          <el-descriptions-item label="统计窗口 / 归因配置"
            >{{ detail.window }} / {{ detail.metric_profile_id }}</el-descriptions-item
          >
          <el-descriptions-item label="条件根逻辑">{{ detail.logic }}</el-descriptions-item>
          <el-descriptions-item label="冷却分钟 / 每日上限"
            >{{ detail.cooldown_minutes }} / {{ detail.max_daily }}</el-descriptions-item
          >
          <el-descriptions-item label="下次运行（UTC）">{{
            detail.next_run_at ?? '未安排'
          }}</el-descriptions-item>
          <el-descriptions-item label="调度">
            <dl class="schedule">
              <template v-for="(v, k) in detail.schedule" :key="k"
                ><dt>{{ scheduleLabel[k] }}</dt>
                <dd>{{ v === null ? '不适用' : v }}</dd></template
              >
            </dl>
          </el-descriptions-item>
        </el-descriptions>
        <section v-for="(group, i) in detail.groups" :key="i" class="conditions">
          <h3>条件组 {{ i + 1 }} · {{ group.logic }}</h3>
          <p v-for="(leaf, j) in group.conditions" :key="j">
            {{ leaf.metric }} {{ leaf.operator }} {{ leaf.threshold }}
          </p>
        </section>
        <div class="actions">
          <el-button
            v-if="allowed('UPDATE')"
            :disabled="!editable || entryBusy || !!intent"
            @click="entry('UPDATE')"
            >编辑规则</el-button
          >
          <el-button
            v-if="allowed('SIMULATE')"
            :disabled="busy || !!intent"
            @click="start('SIMULATE')"
            >模拟</el-button
          >
          <el-button
            v-if="allowed('ENABLE')"
            :disabled="!editable || !eligibleSimulation || busy || !!intent"
            @click="start('ENABLE')"
            >启用</el-button
          >
          <el-button
            v-if="allowed('PAUSE')"
            :disabled="detail.state !== 'ENABLED' || detailMetadataStale || busy || !!intent"
            @click="start('PAUSE')"
            >暂停</el-button
          >
          <el-button
            v-if="allowed('ARCHIVE')"
            :disabled="!editable || busy || !!intent"
            @click="start('ARCHIVE')"
            >归档</el-button
          >
          <el-button v-if="allowed('SIMULATE')" :disabled="runsOpen" @click="runsOpen = true"
            >运行记录</el-button
          >
        </div>
        <p v-if="detail.state === 'ENABLED'">启用中的规则须先暂停再编辑或归档。</p>
        <p v-if="allowed('ENABLE') && !eligibleSimulation">
          启用需要此规则当前版本的服务端有效模拟；服务端最终复核有效期。
        </p>
        <el-alert v-if="operationError" :title="operationError" type="error" :closable="false" />
        <div v-if="simulation" class="simulation">
          <h3>实际模拟结果</h3>
          <p>模拟 {{ simulation.id }} · 规则版本 {{ simulation.revision }}</p>
          <p>
            扫描 {{ simulation.scanned_count }} / 命中 {{ simulation.hit_count }} / 未知
            {{ simulation.unknown_count }} / 不命中 {{ simulation.false_count }} · 账户
            {{ simulation.account_count }}
          </p>
          <p>
            到期（UTC）{{ simulation.expires_at }} · 快照 {{ simulation.snapshot_id }} · hash
            {{ simulation.hash }}
          </p>
          <p
            v-for="(c, i) in simulation.conditions.slice(
              conditionPage * 50,
              (conditionPage + 1) * 50,
            )"
            :key="i"
          >
            {{ c.entity_id }} · {{ c.condition_index }} · {{ c.value ?? '未知值' }} ·
            {{ c.result }} · {{ c.reason_code ?? '无原因码' }}
          </p>
          <el-button :disabled="conditionPage === 0" @click="conditionPage--">上一组条件</el-button
          ><el-button
            :disabled="(conditionPage + 1) * 50 >= simulation.conditions.length"
            @click="conditionPage++"
            >下一组条件</el-button
          >
          <p v-if="simulation.next_cursor">
            存在后续结果；原续页读取接口尚未接通，当前结果不代表完整明细。
          </p>
        </div>
        <p v-if="runsOpen">以下为本规则运行记录；全局触发记录尚未提供。</p>
        <RuleRuns
          v-if="runsOpen"
          :rule-id="detail.id"
          :permission-codes="permissionCodes"
          :context-key="contextKey"
        />
      </template>
    </el-drawer>
    <el-dialog
      v-if="!intent || intent.context === context()"
      :model-value="!!action && (!intent || intent.context === context())"
      :title="action ? actionLabel[action] : ''"
      width="min(520px, 95vw)"
      :close-on-click-modal="false"
      :close-on-press-escape="!busy && !unknown"
      :show-close="!busy && !unknown"
      @close="cancelAction"
    >
      <p v-if="intent && !readDenied">
        规则 {{ intent.rule.name }} · 版本 {{ intent.rule.revision }}
      </p>
      <p v-else-if="detail">规则 {{ detail.name }} · 版本 {{ detail.revision }}</p>
      <p v-if="readDenied">当前读取授权已失效，旧对象内容已隐藏；已发请求仍保留原意图。</p>
      <el-input
        v-if="!readDenied && (action === 'PAUSE' || action === 'ARCHIVE')"
        v-model="reason"
        aria-label="操作原因"
        type="textarea"
        :disabled="busy || !!intent"
        placeholder="请输入操作原因"
      />
      <p v-if="action === 'SIMULATE'">仅请求实际模拟；未取得成功结果不会发行启用资格。</p>
      <p v-if="action === 'ENABLE'">服务端将复核当前版本、模拟有效期及执行依赖。</p>
      <el-alert v-if="operationError" :title="operationError" type="error" :closable="false" />
      <el-alert
        v-if="unknown"
        title="请求结果未知。请保留此回执并手动重试原请求；不会自动创建新意图。"
        type="warning"
        :closable="false"
      />
      <p v-if="intent">
        请求键 {{ intent.auth.idempotency_key }} · If-Match {{ intent.auth.if_match }}
      </p>
      <div v-if="unknown && intent" class="recovery-actions">
        <a href="/login" target="_blank" rel="noopener">在新标签页重新登录</a>
        <p>请保留本页；登录后回此弹窗验证身份，不会自动提交原请求。</p>
        <el-button :loading="recoveryBusy" @click="emit('verifyIdentity')"
          >重新验证当前身份（不提交）</el-button
        >
        <p v-if="recoveryMessage" role="status">{{ recoveryMessage }}</p>
      </div>
      <template #footer
        ><el-button :disabled="busy || unknown" @click="cancelAction">取消</el-button
        ><el-button type="primary" :loading="busy" :disabled="!canConfirm" @click="confirmAction">{{
          unknown ? '使用原请求重试' : '确认'
        }}</el-button></template
      >
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import {
  ruleRecoveryApi,
  recoveryPrincipal,
  requireRecoveryPrincipal,
  requireInitialRuleActor,
  type RuleRecoveryPrincipal,
} from '@/api/orbit/rule-recovery'
import { refreshCookieCsrfForRecovery } from '@/api/orbit/authentication'

import RuleRuns from './RuleRuns.vue'
import RuleListFilterSelect from './RuleListFilterSelect.vue'
import { ruleDisplayMetadataApi, type RuleDisplayMetadata } from '@/api/orbit/rule-display-metadata'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  RuleApiError,
  rulesApi,
  type Rule,
  type RuleAction,
  type RulePage,
  type RuleQuery,
  type RuleSimulation,
  type RuleSchedule,
  type RuleState,
  type RuleVersionMutation,
} from '@/api/orbit/rules'
const props = withDefaults(
  defineProps<{
    nativeActorId?: number | null
    permissionCodes?: string[]
    contextKey?: string
    recoveryBusy?: boolean
    recoveryMessage?: string
    pendingAction?: Intent | null
    filters?: Omit<RuleQuery, 'q' | 'status' | 'entity_type' | 'cursor' | 'page_size'>
  }>(),
  {
    recoveryBusy: false,
    recoveryMessage: '',
    nativeActorId: null,
    permissionCodes: () => [],
    contextKey: '',
    filters: () => ({}),
    pendingAction: null,
  },
)
const emit = defineEmits<{
  verifyIdentity: []
  pendingAction: [intent: Intent | null]
  create: [capability: { csrf_token: string }]
  edit: [rule: Rule, capability: { csrf_token: string }]
}>()
const states: RuleState[] = ['DRAFT', 'ENABLED', 'PAUSED', 'ARCHIVED']
const stateLabel: Record<RuleState, string> = {
  DRAFT: '草稿',
  ENABLED: '已启用',
  PAUSED: '已暂停',
  ARCHIVED: '已归档',
}
const actionLabel: Record<RuleAction, string> = {
  CREATE: '创建规则',
  UPDATE: '编辑规则',
  ENABLE: '确认启用',
  PAUSE: '确认暂停',
  ARCHIVE: '确认归档',
  SIMULATE: '确认模拟',
}
const scheduleLabel: Record<string, string> = {
  frequency: '频次',
  interval_minutes: '间隔分钟',
  time_of_day: '当地执行时刻',
  weekday: 'ISO星期',
  timezone: 'IANA时区',
  start_date: '生效日',
  end_date: '截止日',
}
function scheduleSummary(schedule: RuleSchedule): string {
  if (schedule.frequency === 'INTERVAL') return `每${schedule.interval_minutes}分钟`
  if (schedule.frequency === 'DAILY') return `每天 ${schedule.time_of_day}（当地时间）`
  const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  return `每周${weekdays[(schedule.weekday ?? 0) - 1]?.slice(1) ?? '未知星期'} ${schedule.time_of_day}（当地时间）`
}
const permission: Record<RuleAction, string> = {
  CREATE: 'rules.create',
  UPDATE: 'rules.edit',
  ENABLE: 'rules.enable',
  PAUSE: 'rules.pause',
  ARCHIVE: 'rules.archive',
  SIMULATE: 'rules.read',
}
const allowed = (a: RuleAction) =>
  props.permissionCodes.includes('*:*:*') || props.permissionCodes.includes(permission[a])
// 未知业务意图绑定actor生命周期；无关权限变动不改原payload身份。
const context = () => props.contextKey
const effectiveFrom = ref(props.filters.date_from ?? ''),
  effectiveTo = ref(props.filters.date_to ?? '')
const operatorFilter = ref(props.filters.operator_user_id ?? ''),
  profileFilter = ref(props.filters.metric_profile_id ?? ''),
  channelFilter = ref(props.filters.channel_id ?? ''),
  filterRefresh = ref(0)
const queryError = ref('')
const q = ref(''),
  status = ref<RuleState | ''>(''),
  entity = ref<NonNullable<RuleQuery['entity_type']> | ''>(''),
  pageSize = ref<20 | 50 | 100 | 200>(50)
const page = ref<RulePage | null>(null),
  cursor = ref<string | undefined>(),
  history = ref<(string | undefined)[]>([])
const loading = ref(false),
  listError = ref(''),
  readDenied = ref(!!props.pendingAction),
  drawer = ref(false),
  detailLoading = ref(false),
  detailError = ref(''),
  detail = ref<Rule | null>(null)
const listMetadata = ref<Record<string, RuleDisplayMetadata>>({}),
  detailMetadata = ref<RuleDisplayMetadata | null>(null)
const listMetadataLoading = ref(false),
  detailMetadataLoading = ref(false),
  listMetadataError = ref(''),
  detailMetadataError = ref(''),
  listMetadataStale = ref(false),
  detailMetadataStale = ref(false)
let listMetadataEpoch = 0,
  detailMetadataEpoch = 0,
  listMetadataAbort: AbortController | undefined,
  detailMetadataAbort: AbortController | undefined
const metadataPlaceholder = (kind: 'list' | 'detail', missing: string) => {
  const error = kind === 'list' ? listMetadataError.value : detailMetadataError.value
  const loading = kind === 'list' ? listMetadataLoading.value : detailMetadataLoading.value
  return loading ? '读取中…' : error ? '显示资料读取失败' : missing
}
function stopListMetadata() {
  ++listMetadataEpoch
  listMetadataAbort?.abort()
  listMetadata.value = {}
  listMetadataLoading.value = false
  listMetadataError.value = ''
  listMetadataStale.value = false
}
function stopDetailMetadata() {
  ++detailMetadataEpoch
  detailMetadataAbort?.abort()
  detailMetadata.value = null
  detailMetadataLoading.value = false
  detailMetadataError.value = ''
  detailMetadataStale.value = false
}
async function loadListMetadata(items: Rule[], parentEpoch: number) {
  stopListMetadata()
  if (!items.length) return
  const token = listMetadataEpoch,
    started = context()
  listMetadataLoading.value = true
  listMetadataAbort = new AbortController()
  try {
    const rows = await ruleDisplayMetadataApi.get(
      items.map((row) => row.id),
      listMetadataAbort.signal,
    )
    if (token !== listMetadataEpoch || parentEpoch !== listEpoch || started !== context()) return
    if (
      rows.length !== items.length ||
      rows.some((row, i) => row.rule_id !== items[i].id || row.revision !== items[i].revision)
    )
      throw new RuleApiError(409, 'RULE_DISPLAY_METADATA_CHANGED', '规则版本已变化，请重新查询列表')
    listMetadata.value = Object.fromEntries(rows.map((row) => [row.rule_id, row]))
  } catch (e) {
    if (token !== listMetadataEpoch || parentEpoch !== listEpoch || aborted(e)) return
    if (e instanceof RuleApiError && [401, 403, 404].includes(e.status)) {
      denyRead(e)
      listError.value = errorText(e)
    } else {
      listMetadataError.value = errorText(e)
      listMetadataStale.value = e instanceof RuleApiError && e.status === 409
    }
  } finally {
    if (token === listMetadataEpoch) listMetadataLoading.value = false
  }
}
async function loadDetailMetadata(row: Rule, parentEpoch: number) {
  stopDetailMetadata()
  const token = detailMetadataEpoch,
    started = context()
  detailMetadataLoading.value = true
  detailMetadataAbort = new AbortController()
  try {
    const rows = await ruleDisplayMetadataApi.get([row.id], detailMetadataAbort.signal)
    if (token !== detailMetadataEpoch || parentEpoch !== detailEpoch || started !== context())
      return
    if (rows.length !== 1 || rows[0].rule_id !== row.id || rows[0].revision !== row.revision)
      throw new RuleApiError(409, 'RULE_DISPLAY_METADATA_CHANGED', '规则版本已变化，请重新读取详情')
    detailMetadata.value = rows[0]
  } catch (e) {
    if (token !== detailMetadataEpoch || parentEpoch !== detailEpoch || aborted(e)) return
    if (e instanceof RuleApiError && [401, 403, 404].includes(e.status)) {
      denyRead(e)
      listError.value = errorText(e)
    } else {
      detailMetadataError.value = errorText(e)
      detailMetadataStale.value = e instanceof RuleApiError && e.status === 409
    }
  } finally {
    if (token === detailMetadataEpoch) detailMetadataLoading.value = false
  }
}
const entryBusy = ref(false),
  entryError = ref(''),
  operationError = ref(''),
  action = ref<RuleAction | null>(props.pendingAction?.action ?? null),
  reason = ref(''),
  busy = ref(false),
  unknown = ref(!!props.pendingAction)
const simulation = ref<RuleSimulation | null>(null),
  runsOpen = ref(false)
type Intent = {
  principal: RuleRecoveryPrincipal | null
  action: RuleAction
  rule: Rule
  auth: RuleVersionMutation
  body: { reason: string } | { simulation_id: string } | null
  context: string
}
const intent = ref<Intent | null>(props.pendingAction)
function rememberAction(value: Intent | null) {
  intent.value = value
  emit('pendingAction', value)
}
const appliedQuery = ref<RuleQuery>({ page_size: 50 }),
  conditionPage = ref(0),
  clockNow = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | undefined
let listEpoch = 0,
  detailEpoch = 0,
  operationEpoch = 0,
  entryEpoch = 0
let listAbort: AbortController | undefined,
  detailAbort: AbortController | undefined,
  operationAbort: AbortController | undefined,
  entryAbort: AbortController | undefined
const editable = computed(
  () =>
    !detailMetadataStale.value &&
    (detail.value?.state === 'DRAFT' || detail.value?.state === 'PAUSED'),
)
const eligibleSimulation = computed(
  () =>
    !!simulation.value &&
    simulation.value.rule_id === detail.value?.id &&
    simulation.value.revision === detail.value?.revision &&
    Date.parse(simulation.value.expires_at) > clockNow.value,
)
const confirmationReason = computed(() =>
  intent.value?.body && 'reason' in intent.value.body ? intent.value.body.reason : reason.value,
)
const canConfirm = computed(
  () =>
    !!action.value &&
    allowed(action.value) &&
    !busy.value &&
    (!intent.value || intent.value.context === context()) &&
    ((action.value !== 'PAUSE' && action.value !== 'ARCHIVE') ||
      (!!confirmationReason.value.trim() && [...confirmationReason.value.trim()].length <= 1000)) &&
    (action.value !== 'ENABLE' || !!intent.value || eligibleSimulation.value),
)
const errorText = (e: unknown) =>
  e instanceof RuleApiError
    ? `${e.message}（${e.code}）${e.field_errors.map((f) => ` ${f.path}: ${f.message}`).join('')}`
    : '请求失败，请重试。'
const cloneRule = (value: Rule): Rule => JSON.parse(JSON.stringify(value))
const aborted = (e: unknown) => e instanceof Error && e.name === 'AbortError'
async function loadList() {
  listAbort?.abort()
  stopListMetadata()
  const token = ++listEpoch
  listAbort = new AbortController()
  page.value = null
  listError.value = ''
  if (!allowed('SIMULATE')) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await rulesApi.list(
      {
        ...appliedQuery.value,
        ...(cursor.value ? { cursor: cursor.value } : {}),
      },
      listAbort.signal,
    )
    if (token === listEpoch) {
      page.value = result
      void loadListMetadata(result.items, token)
    }
  } catch (e) {
    if (token === listEpoch && !aborted(e)) {
      if (e instanceof RuleApiError && [401, 403].includes(e.status)) denyRead(e)
      listError.value = errorText(e)
    }
  } finally {
    if (token === listEpoch) loading.value = false
  }
}
// 配置写入改变列表clock：回到第一页，保留已提交查询及尚未提交的表单输入。
async function refresh() {
  ++filterRefresh.value
  cursor.value = undefined
  history.value = []
  await loadList()
}
function hideSensitiveForRecovery() {
  readDenied.value = true
  page.value = null
  stopListMetadata()
  closeDetail(true)
}
defineExpose({ refresh, hideSensitiveForRecovery })
function search() {
  const normalizedQ = q.value.normalize('NFC')
  if ([...normalizedQ].length > 100) {
    queryError.value = '规则名称查询最多100字符（/q）；请缩短后再查询。'
    return
  }
  queryError.value = ''
  // 游标必须绑定已提交的筛选，不受尚未点击查询的输入变化影响。
  const {
    operator_user_id: _operator,
    metric_profile_id: _profile,
    channel_id: _channel,
    date_from: _from,
    date_to: _to,
    ...otherFilters
  } = props.filters
  appliedQuery.value = {
    ...otherFilters,
    ...(effectiveFrom.value ? { date_from: effectiveFrom.value } : {}),
    ...(effectiveTo.value ? { date_to: effectiveTo.value } : {}),
    ...(operatorFilter.value ? { operator_user_id: operatorFilter.value } : {}),
    ...(profileFilter.value ? { metric_profile_id: profileFilter.value } : {}),
    ...(channelFilter.value ? { channel_id: channelFilter.value } : {}),
    ...(normalizedQ ? { q: normalizedQ } : {}),
    ...(status.value ? { status: status.value } : {}),
    ...(entity.value ? { entity_type: entity.value } : {}),
    page_size: pageSize.value,
  }
  cursor.value = undefined
  history.value = []
  void loadList()
}
function next() {
  if (!page.value?.next_cursor) return
  history.value.push(cursor.value)
  cursor.value = page.value.next_cursor
  void loadList()
}
function previous() {
  if (!history.value.length) return
  cursor.value = history.value.pop()
  void loadList()
}
function closeDetail(force = false) {
  if (!force && (intent.value || busy.value)) return
  ++entryEpoch
  entryAbort?.abort()
  entryBusy.value = false
  drawer.value = false
  stopDetailMetadata()
  ++detailEpoch
  detailAbort?.abort()
  detail.value = null
  simulation.value = null
  runsOpen.value = false
}
// 读端明确撤权立即收起旧详情/列表；不把普通503当撤权，原写意图不改键或正文。
function denyRead(error: RuleApiError) {
  effectiveFrom.value = ''
  effectiveTo.value = ''
  operatorFilter.value = ''
  profileFilter.value = ''
  channelFilter.value = ''
  ++filterRefresh.value
  readDenied.value = true
  ++listEpoch
  listAbort?.abort()
  loading.value = false
  page.value = null
  stopListMetadata()
  closeDetail(true)
  ++operationEpoch
  operationAbort?.abort()
  busy.value = false
  if (intent.value) {
    unknown.value = true
    operationError.value = errorText(error)
  } else {
    action.value = null
    reason.value = ''
  }
}
async function openDetail(id: string) {
  if (!allowed('SIMULATE') || intent.value || busy.value || listMetadataStale.value) return
  closeDetail()
  drawer.value = true
  detailError.value = ''
  operationError.value = ''
  detailLoading.value = true
  const token = ++detailEpoch
  detailAbort = new AbortController()
  try {
    const value = await rulesApi.get(id, detailAbort.signal)
    if (token === detailEpoch) {
      detail.value = value
      readDenied.value = false
      void loadDetailMetadata(value, token)
    }
  } catch (e) {
    if (token === detailEpoch && !aborted(e)) {
      if (e instanceof RuleApiError && [401, 403].includes(e.status)) {
        denyRead(e)
        listError.value = errorText(e)
      } else detailError.value = errorText(e)
    }
  } finally {
    if (token === detailEpoch) detailLoading.value = false
  }
}
async function entry(kind: 'CREATE' | 'UPDATE') {
  if (
    intent.value ||
    busy.value ||
    !allowed(kind) ||
    (kind === 'UPDATE' && (!detail.value || !editable.value))
  )
    return
  const token = ++entryEpoch,
    ctx = context(),
    original = detail.value ? cloneRule(detail.value) : null
  entryAbort?.abort()
  entryAbort = new AbortController()
  entryBusy.value = true
  entryError.value = ''
  try {
    const cap = await rulesApi.capabilities(kind, entryAbort.signal)
    if (token !== entryEpoch || ctx !== context() || intent.value || busy.value) return
    const canEnter = kind === 'CREATE' || (original && detail.value?.id === original.id)
    if (!canEnter) return
    // Drawer使用teleport，不会随父列表v-show隐藏；进入二级页前关闭真实详情。
    closeDetail(true)
    if (kind === 'CREATE') emit('create', cap)
    else if (original) emit('edit', original, cap)
  } catch (e) {
    if (token === entryEpoch && !aborted(e)) entryError.value = errorText(e)
  } finally {
    if (token === entryEpoch) entryBusy.value = false
  }
}
function start(kind: RuleAction) {
  if (!allowed(kind) || !detail.value || intent.value || detailMetadataStale.value) return
  action.value = kind
  reason.value = ''
  operationError.value = ''
  unknown.value = false
}
function cancelAction() {
  if (busy.value || unknown.value) return
  action.value = null
  intent.value = null
  operationError.value = ''
}
async function confirmAction() {
  if (!canConfirm.value || (!detail.value && !intent.value)) return
  const token = ++operationEpoch,
    ctx = context()
  operationAbort = new AbortController()
  busy.value = true
  operationError.value = ''
  const recovering = unknown.value
  if (recovering) hideSensitiveForRecovery()
  try {
    if (!intent.value) {
      const row = cloneRule(detail.value!),
        kind = action.value!,
        why = reason.value.trim(),
        simId = simulation.value?.id
      const cap = await rulesApi.capabilities(kind, operationAbort.signal)
      const current = await ruleRecoveryApi.get(kind, operationAbort.signal)
      requireInitialRuleActor(props.nativeActorId, current)
      refreshCookieCsrfForRecovery(current.csrf_token)
      if (token !== operationEpoch || ctx !== context()) return
      rememberAction({
        principal: recoveryPrincipal(current),
        action: kind,
        rule: row,
        auth: {
          ...cap,
          csrf_token: current.csrf_token,
          if_match: `"${row.revision}"`,
          idempotency_key: crypto.randomUUID(),
        },
        body:
          kind === 'PAUSE' || kind === 'ARCHIVE'
            ? { reason: why }
            : kind === 'ENABLE'
              ? { simulation_id: simId! }
              : null,
        context: ctx,
      })
    }
    const fixed = intent.value,
      signal = operationAbort.signal
    if (!fixed) return
    let transportAuth = fixed.auth
    if (recovering) {
      const current = await ruleRecoveryApi.get(fixed.action, signal)
      requireRecoveryPrincipal(fixed.principal, current)
      if (token !== operationEpoch || ctx !== context()) return
      refreshCookieCsrfForRecovery(current.csrf_token)
      transportAuth = { ...fixed.auth, csrf_token: current.csrf_token }
    }
    const result =
      fixed.action === 'PAUSE'
        ? await rulesApi.pause(
            fixed.rule.id,
            fixed.body as { reason: string },
            transportAuth,
            signal,
          )
        : fixed.action === 'ARCHIVE'
          ? await rulesApi.archive(
              fixed.rule.id,
              fixed.body as { reason: string },
              transportAuth,
              signal,
            )
          : fixed.action === 'ENABLE'
            ? await rulesApi.enable(
                fixed.rule.id,
                fixed.body as { simulation_id: string },
                transportAuth,
                signal,
              )
            : await rulesApi.simulate(fixed.rule.id, transportAuth, signal)
    if (token !== operationEpoch || ctx !== context()) return
    if (fixed.action === 'SIMULATE') {
      const value = result as RuleSimulation
      if (value.rule_id !== fixed.rule.id || value.revision !== fixed.rule.revision)
        throw new RuleApiError(
          502,
          'INVALID_RESPONSE',
          '模拟结果与请求版本不一致',
          [],
          false,
          null,
          true,
        )
      simulation.value = value
      conditionPage.value = 0
    } else {
      const value = result as Rule
      const expected =
        fixed.action === 'PAUSE' ? 'PAUSED' : fixed.action === 'ARCHIVE' ? 'ARCHIVED' : 'ENABLED'
      if (
        value.id !== fixed.rule.id ||
        value.revision !== fixed.rule.revision + 1 ||
        value.state !== expected
      )
        throw new RuleApiError(
          502,
          'INVALID_RESPONSE',
          '动作结果与请求不一致',
          [],
          false,
          null,
          true,
        )
      detail.value = value
      readDenied.value = false
      if (allowed('SIMULATE')) void loadDetailMetadata(value, detailEpoch)
      else stopDetailMetadata()
      simulation.value = null
    }
    unknown.value = false
    rememberAction(null)
    action.value = null
    if (fixed.action !== 'SIMULATE') void refresh()
  } catch (e) {
    if (token !== operationEpoch) return
    operationError.value = errorText(e)
    if (
      e instanceof RuleApiError &&
      ['RULE_RECOVERY_UI_ACTOR_CHANGED', 'RULE_RECOVERY_PRINCIPAL_CHANGED'].includes(e.code)
    )
      hideSensitiveForRecovery()
    unknown.value =
      !!intent.value && (recovering || !(e instanceof RuleApiError) || e.unknown_result)
    if (!unknown.value) rememberAction(null)
  } finally {
    if (token === operationEpoch) busy.value = false
  }
}
function resetContext() {
  effectiveFrom.value = ''
  effectiveTo.value = ''
  operatorFilter.value = ''
  profileFilter.value = ''
  channelFilter.value = ''
  ++filterRefresh.value
  ++listEpoch
  ++detailEpoch
  ++operationEpoch
  ++entryEpoch
  for (const controller of [listAbort, detailAbort, operationAbort, entryAbort]) controller?.abort()
  page.value = null
  stopListMetadata()
  closeDetail(true)
  loading.value = false
  busy.value = false
  entryBusy.value = false
  entryError.value = ''
  listError.value = ''
  // 已发出的写意图不跨身份重放，仍保留原键/正文，禁止另建新意图。
  if (intent.value) {
    readDenied.value = true
    unknown.value = true
    operationError.value =
      '当前权限或认证上下文已变化，原请求结果未知；请恢复原上下文后查询或使用原请求重试。'
  } else action.value = null
}
watch(
  () => [props.contextKey, [...props.permissionCodes].sort().join('|')],
  () => {
    resetContext()
    search()
  },
)
watch(
  () => props.pendingAction,
  (value) => {
    if (value && value !== intent.value) {
      intent.value = value
      action.value = value.action
      unknown.value = true
    }
  },
)
watch(
  () => props.filters,
  () => {
    effectiveFrom.value = props.filters.date_from ?? ''
    effectiveTo.value = props.filters.date_to ?? ''
    operatorFilter.value = props.filters.operator_user_id ?? ''
    profileFilter.value = props.filters.metric_profile_id ?? ''
    channelFilter.value = props.filters.channel_id ?? ''
    search()
  },
  { deep: true },
)
onMounted(() => {
  search()
  clockTimer = setInterval(() => {
    clockNow.value = Date.now()
  }, 1000)
})
onBeforeUnmount(() => {
  clearInterval(clockTimer)
  resetContext()
})
</script>

<style scoped>
.metadata-id {
  display: block;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rule-list {
  padding: 20px;
}
.toolbar,
.pagination,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar .el-input {
  width: 240px;
}
.toolbar .el-select,
.pagination .el-select {
  width: 140px;
}
.pagination {
  margin-top: 16px;
}
.schedule {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 2fr;
  gap: 8px;
  margin: 0;
}
.schedule dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.conditions,
.simulation {
  margin: 24px 0;
}
.conditions h3,
.simulation h3 {
  font-size: 16px;
}
.actions {
  margin-top: 24px;
}
:deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
.el-alert {
  margin: 12px 0;
}
@media (max-width: 600px) {
  .rule-list {
    padding: 12px;
  }
  .toolbar .el-input,
  .toolbar .el-select {
    width: 100%;
  }
  .schedule {
    grid-template-columns: 1fr;
  }
}

/* 原条件逐项保真；默认摘要收拢，键盘可展开全部条件，不把缺失范围数量猜成零。 */
.rule-condition-summary {
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.rule-condition-summary summary {
  cursor: pointer;
}
.rule-condition-summary summary small,
.rule-account-scope small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.rule-condition-group {
  margin-top: 8px;
}
.rule-condition-group strong {
  font-weight: 500;
}
.rule-condition-leaf {
  margin: 2px 0;
  font-variant-numeric: tabular-nums;
}
.rule-account-scope :deep(.el-button) {
  height: auto;
  padding: 3px 0;
  white-space: normal;
  text-align: left;
  line-height: 1.5;
}
.rule-account-scope :deep(.el-button span) {
  overflow-wrap: anywhere;
}
</style>
