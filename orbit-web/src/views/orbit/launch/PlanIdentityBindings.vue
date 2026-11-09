<template>
  <section class="identity-bindings">
    <el-alert
      title="身份资源是最近一次观察；保存时由服务端核验当前账户的主页、像素和应用引用。优化事件与商店URL仍须正式预检，保存草稿不代表已获执行授权。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-if="!canRead"
      title="当前未确认 accounts.read 权限；身份读取关闭，已有配置仍完整保留。"
      type="warning"
      :closable="false"
    />
    <p v-if="!accounts.length">
      请先选择账户。范围快照须先由服务端解析为真实账户，不能用列表游标代替。
    </p>
    <p v-if="orphanCount" role="status">
      {{ orphanCount }} 个绑定的账户已移出选择；原配置保留，请重新选择该账户或明确移除绑定。
    </p>
    <el-table :data="accountRows" row-key="id" empty-text="暂无逐账户身份">
      <el-table-column label="账户" min-width="240"
        ><template #default="{ row }"
          ><span>{{ row.id }}</span
          ><el-tag v-if="!row.selected" type="warning">已移出选择</el-tag></template
        ></el-table-column
      >
      <el-table-column label="默认主页" min-width="160"
        ><template #default="{ row }">{{
          binding(row.id)?.page_id || '未配置'
        }}</template></el-table-column
      >
      <el-table-column label="配置" min-width="150"
        ><template #default="{ row }"
          >组 {{ binding(row.id)?.groups.length || 0 }} · 广告覆盖
          {{ binding(row.id)?.ad_overrides.length || 0 }}</template
        ></el-table-column
      >
      <el-table-column label="操作" width="190"
        ><template #default="{ row }"
          ><el-button :disabled="disabled" @click="open(row.id)">{{
            readOnly ? '查看身份' : '配置身份'
          }}</el-button
          ><el-button
            v-if="binding(row.id)"
            :disabled="disabled || readOnly"
            @click="removeAccount(row.id)"
            >移除</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="accounts.length"
      v-model:current-page="accountPage"
      :page-size="20"
      :total="accounts.length"
      layout="total, prev, pager, next"
    />
    <el-dialog
      :model-value="!!editing"
      title="逐账户身份配置"
      width="min(1100px, 96vw)"
      append-to-body
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :before-close="close"
      @open-auto-focus="identityFocusReady"
    >
      <template v-if="draft">
        <p class="account-label">账户 {{ editing }}</p>
        <el-alert
          v-if="contextChanged"
          title="账户、负责人或配置树已变化；本弹窗输入仍保留，取消后重新打开再处理，不能覆盖新配置。"
          type="warning"
          :closable="false"
        />
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
        <el-alert
          v-if="staleCount"
          :title="`${staleCount} 条组或广告绑定已不在当前树中；保留原值，请在失效绑定页明确移除。`"
          type="warning"
          :closable="false"
        />
        <el-button
          :disabled="!canRead || disabled || loading || !selectedAccount || contextChanged"
          :loading="loading"
          @click="load"
          >{{ observation ? '刷新身份观察' : '读取本账户身份' }}</el-button
        >
        <p v-if="observation" role="status">
          能力版本 {{ observation.capability_version }} · 观察时间 {{ observation.observed_at }} ·
          {{ observation.resources.length }} 项资源（仅观察，不是写授权）
        </p>
        <p v-else>尚无本次资源观察。不会自动读取全部账户，不提供示例资源。</p>
        <el-form
          ref="identityFields"
          label-position="top"
          :disabled="disabled || readOnly || contextChanged"
        >
          <el-form-item label="默认主页 page_id"
            ><el-select-v2
              :model-value="draft.page_id"
              :options="options('PAGE', draft.page_id)"
              filterable
              :disabled="disabled || readOnly || contextChanged || !observation || !selectedAccount"
              @update:model-value="setPage($event)"
          /></el-form-item>
          <el-tabs v-model="tab">
            <el-tab-pane label="广告组身份" name="groups">
              <p>
                优化事件和商店URL为待服务端能力核验的草稿值；不会默认填入
                PURCHASE。切换目标不会自动删除旧值。
              </p>
              <el-table :data="groupRows" row-key="id">
                <el-table-column label="广告组 / 目标" min-width="230"
                  ><template #default="{ row }"
                    >{{ row.label }}<br /><code>{{ row.id }}</code
                    ><br />{{ row.objective || '目标未配置，身份输入关闭' }}</template
                  ></el-table-column
                >
                <el-table-column label="身份字段" min-width="330"
                  ><template #default="{ row }">
                    <template v-if="editingGroup === row.id && row.objective === 'OUTCOME_SALES'">
                      <el-form-item :label="`像素 ${row.id}`"
                        ><el-select-v2
                          :model-value="group(row.id)?.pixel_id ?? ''"
                          :options="options('PIXEL', group(row.id)?.pixel_id)"
                          filterable
                          :disabled="
                            disabled ||
                            readOnly ||
                            contextChanged ||
                            !observation ||
                            !selectedAccount
                          "
                          @update:model-value="setGroup(row.id, 'pixel_id', $event)"
                      /></el-form-item>
                      <el-form-item :label="`优化事件 ${row.id}（待能力核验）`"
                        ><el-input
                          :model-value="group(row.id)?.conversion_event ?? ''"
                          :disabled="disabled || readOnly || contextChanged || !selectedAccount"
                          @update:model-value="setGroup(row.id, 'conversion_event', $event || null)"
                        /><span
                          >{{ [...(group(row.id)?.conversion_event ?? '')].length }}/64 码点</span
                        ></el-form-item
                      >
                    </template>
                    <template
                      v-else-if="
                        editingGroup === row.id && row.objective === 'OUTCOME_APP_PROMOTION'
                      "
                    >
                      <el-form-item :label="`应用 ${row.id}`"
                        ><el-select-v2
                          :model-value="group(row.id)?.application_id ?? ''"
                          :options="options('APPLICATION', group(row.id)?.application_id)"
                          filterable
                          :disabled="
                            disabled ||
                            readOnly ||
                            contextChanged ||
                            !observation ||
                            !selectedAccount
                          "
                          @update:model-value="setGroup(row.id, 'application_id', $event)"
                      /></el-form-item>
                      <el-form-item :label="`应用商店HTTPS URL ${row.id}（域名待核验）`"
                        ><el-input
                          :model-value="group(row.id)?.object_store_url ?? ''"
                          :disabled="disabled || readOnly || contextChanged || !selectedAccount"
                          @update:model-value="
                            setGroup(row.id, 'object_store_url', $event || null)
                          "
                      /></el-form-item>
                    </template>
                    <p v-else>
                      {{ group(row.id) ? JSON.stringify(group(row.id)) : '此组尚无身份配置' }}
                    </p>
                    <p v-if="groupConflict(row)">
                      旧字段与当前目标不符，原值仍保留：{{
                        JSON.stringify(group(row.id))
                      }}。请明确移除后重新配置。
                    </p>
                  </template></el-table-column
                >
                <el-table-column label="操作" width="160"
                  ><template #default="{ row }"
                    ><button
                      type="button"
                      class="el-button"
                      :aria-label="`查看组身份 ${row.id}`"
                      @click="editingGroup = row.id"
                    >
                      查看字段</button
                    ><el-button v-if="group(row.id)" @click="removeEntry('groups', row.id)"
                      >移除组绑定</el-button
                    ></template
                  ></el-table-column
                >
              </el-table>
              <el-pagination
                v-model:current-page="groupPage"
                :page-size="20"
                :total="groups.length"
                layout="total, prev, pager, next"
              />
            </el-tab-pane>
            <el-tab-pane label="广告主页覆盖" name="ads" lazy>
              <p>
                未设置时继承本账户默认主页；这里以广告 local_id 关联，不按显示名称或复制序号混绑。
              </p>
              <el-table :data="adRows" row-key="id"
                ><el-table-column label="广告" min-width="240"
                  ><template #default="{ row }"
                    >{{ row.label }}<br /><code>{{ row.id }}</code></template
                  ></el-table-column
                ><el-table-column label="覆盖主页" min-width="280"
                  ><template #default="{ row }"
                    ><div :data-identity-ad="row.id">
                      <el-select-v2
                        v-if="editingAd === row.id"
                        :model-value="override(row.id)"
                        :options="options('PAGE', override(row.id))"
                        filterable
                        clearable
                        :disabled="
                          disabled || readOnly || contextChanged || !observation || !selectedAccount
                        "
                        @update:model-value="setOverride(row.id, $event)"
                      />
                      <p v-else>{{ override(row.id) || '继承默认主页' }}</p>
                      <button
                        type="button"
                        class="el-button"
                        :aria-label="`查看广告覆盖 ${row.id}`"
                        @click="editingAd = row.id"
                      >
                        查看字段
                      </button>
                    </div></template
                  ></el-table-column
                ></el-table
              >
              <el-pagination
                v-model:current-page="adPage"
                :page-size="20"
                :total="ads.length"
                layout="total, prev, pager, next"
              />
            </el-tab-pane>
            <el-tab-pane :label="`失效绑定（${staleCount}）`" name="stale" lazy>
              <el-table :data="staleRows" row-key="key"
                ><el-table-column label="原绑定（完整保留）" min-width="280"
                  ><template #default="{ row }"
                    ><code>{{ row.id }}</code>
                    <pre>{{ JSON.stringify(row.value, null, 2) }}</pre>
                  </template></el-table-column
                ><el-table-column label="操作" width="130"
                  ><template #default="{ row }"
                    ><el-button @click="removeEntry(row.kind, row.id)"
                      >明确移除此绑定</el-button
                    ></template
                  ></el-table-column
                ></el-table
              >
              <el-pagination
                v-model:current-page="stalePage"
                :page-size="20"
                :total="staleCount"
                layout="total, prev, pager, next"
              />
            </el-tab-pane>
          </el-tabs>
        </el-form>
        <ul v-if="issues.length" role="alert">
          <li v-for="issue in issues" :key="issue.path">
            <code>{{ issue.path }}</code
            >：{{ issue.message }}
          </li>
        </ul>
      </template>
      <template #footer
        ><el-button @click="close">{{ readOnly ? '关闭身份详情' : '取消身份编辑' }}</el-button
        ><el-button
          v-if="!readOnly"
          type="primary"
          :disabled="disabled || contextChanged || !selectedAccount || loading"
          @click="apply"
          >应用到本地草稿</el-button
        ></template
      >
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { accountIdentitiesApi } from '@/api/orbit/account-identities'
import type { AccountIdentities } from '@/api/orbit/account-details'
import type { CampaignConfig, GroupIdentity, IdentityBinding } from '@/api/orbit/launch'
import { cloneValue } from '@/api/orbit/launch-form'
const props = withDefaults(
  defineProps<{
    modelValue: IdentityBinding[]
    accountIds: string[]
    campaigns: CampaignConfig[]
    ownershipKey?: string
    canRead?: boolean
    disabled?: boolean
    readOnly?: boolean
  }>(),
  { canRead: false },
)
const emit = defineEmits<{
  'update:modelValue': [value: IdentityBinding[]]
  editing: [value: boolean]
}>()
const accountPage = ref(1),
  groupPage = ref(1),
  adPage = ref(1),
  stalePage = ref(1),
  tab = ref('groups')
// 万节点仅分页摘要；同一层同时挂载一组字段，避免为隐藏行构建成千上万个选择器。
const editingGroup = ref(''),
  editingAd = ref('')
const identityFields = ref<{ $el: HTMLElement }>()
let trapReady = Promise.resolve(true),
  resolveTrap: ((ready: boolean) => void) | undefined
async function identityFocusReady() {
  await nextTick()
  await nextTick()
  resolveTrap?.(!!editing.value)
  resolveTrap = undefined
}
const editing = ref(''),
  draft = ref<IdentityBinding>(),
  initial = ref(''),
  frozen = ref(''),
  error = ref(''),
  loading = ref(false),
  issues = ref<{ path: string; message: string }[]>([]),
  observation = ref<AccountIdentities>()
let controller: AbortController | undefined,
  epoch = 0
const binding = (id: string) => props.modelValue.find((row) => row.account_id === id)
const accounts = computed(() => [
  ...new Set([...props.accountIds, ...props.modelValue.map((row) => row.account_id)]),
])
const accountRows = computed(() =>
  accounts.value
    .slice((accountPage.value - 1) * 20, accountPage.value * 20)
    .map((id) => ({ id, selected: props.accountIds.includes(id) })),
)
const orphanCount = computed(
  () => props.modelValue.filter((row) => !props.accountIds.includes(row.account_id)).length,
)
const context = computed(() =>
  JSON.stringify([props.accountIds, props.campaigns, props.ownershipKey]),
)
const contextChanged = computed(() => !!editing.value && frozen.value !== context.value)
const selectedAccount = computed(() => props.accountIds.includes(editing.value))
const groups = computed(() =>
  props.campaigns.flatMap((campaign, ci) =>
    campaign.adsets.map((row, gi) => ({
      id: row.local_id,
      label: row.name || `系列${ci + 1} / 组${gi + 1}`,
      objective: campaign.objective,
    })),
  ),
)
const ads = computed(() =>
  props.campaigns.flatMap((campaign, ci) =>
    campaign.adsets.flatMap((group, gi) =>
      group.ads.map((row, ai) => ({
        id: row.local_id,
        label: row.name || `系列${ci + 1} / 组${gi + 1} / 广告${ai + 1}`,
      })),
    ),
  ),
)
const groupRows = computed(() =>
  groups.value.slice((groupPage.value - 1) * 20, groupPage.value * 20),
)
const adRows = computed(() => ads.value.slice((adPage.value - 1) * 20, adPage.value * 20))
const groupMap = computed(
  () => new Map(draft.value?.groups.map((row) => [row.adset_local_id, row]) ?? []),
)
const overrideMap = computed(
  () => new Map(draft.value?.ad_overrides.map((row) => [row.ad_local_id, row.page_id]) ?? []),
)
const group = (id: string) => groupMap.value.get(id)
const override = (id: string) => overrideMap.value.get(id) ?? ''
const stale = computed(() => {
  const groupIds = new Set(groups.value.map((row) => row.id)),
    adIds = new Set(ads.value.map((row) => row.id))
  return [
    ...(draft.value?.groups
      .filter((row) => !groupIds.has(row.adset_local_id))
      .map((value) => ({
        kind: 'groups' as const,
        id: value.adset_local_id,
        key: `g:${value.adset_local_id}`,
        value,
      })) ?? []),
    ...(draft.value?.ad_overrides
      .filter((row) => !adIds.has(row.ad_local_id))
      .map((value) => ({
        kind: 'ad_overrides' as const,
        id: value.ad_local_id,
        key: `a:${value.ad_local_id}`,
        value,
      })) ?? []),
  ]
})
const staleCount = computed(() => stale.value.length)
const staleRows = computed(() =>
  stale.value.slice((stalePage.value - 1) * 20, stalePage.value * 20),
)
function options(kind: 'PAGE' | 'PIXEL' | 'APPLICATION', current?: string | null) {
  const rows = (observation.value?.resources ?? [])
    .filter((row) => row.kind === kind)
    .map((row) => ({
      value: row.external_id,
      label: `${row.name || row.external_id} · ${row.external_id}${row.usable ? '' : `（不可用：${row.reason_code || '原因未知'}）`}`,
      disabled: !row.usable,
    }))
  if (current && !rows.some((row) => row.value === current))
    rows.unshift({ value: current, label: `${current}（原值，当前观察未确认）`, disabled: true })
  return rows
}
function groupConflict(row: (typeof groups.value)[number]) {
  const value = group(row.id)
  return (
    !!value &&
    (row.objective === 'OUTCOME_SALES'
      ? !!(value.application_id || value.object_store_url)
      : row.objective === 'OUTCOME_APP_PROMOTION'
        ? !!(value.pixel_id || value.conversion_event)
        : true)
  )
}
function cancelRead() {
  epoch++
  controller?.abort()
  controller = undefined
  loading.value = false
}
function open(id: string) {
  if (props.disabled || editing.value) return
  trapReady = new Promise<boolean>((resolve) => {
    resolveTrap = resolve
  })
  cancelRead()
  observation.value = undefined
  error.value = ''
  issues.value = []
  editing.value = id
  draft.value = cloneValue(
    binding(id) ?? { account_id: id, page_id: '', groups: [], ad_overrides: [] },
  )
  initial.value = JSON.stringify(draft.value)
  frozen.value = context.value
  groupPage.value = adPage.value = stalePage.value = 1
  editingGroup.value = groups.value[0]?.id ?? ''
  editingAd.value = ads.value[0]?.id ?? ''
  tab.value = 'groups'
  emit('editing', true)
}
async function load() {
  if (
    !editing.value ||
    !props.canRead ||
    props.disabled ||
    contextChanged.value ||
    !selectedAccount.value ||
    loading.value
  )
    return
  cancelRead()
  const token = epoch
  controller = new AbortController()
  loading.value = true
  error.value = ''
  observation.value = undefined
  try {
    const value = await accountIdentitiesApi.get(editing.value, controller.signal)
    if (token === epoch) observation.value = value
  } catch (cause) {
    if (token === epoch) error.value = cause instanceof Error ? cause.message : '身份观察读取失败'
  } finally {
    if (token === epoch) loading.value = false
  }
}
const editable = () =>
  !!draft.value &&
  !props.disabled &&
  !props.readOnly &&
  !contextChanged.value &&
  selectedAccount.value
function setPage(value: string) {
  if (editable() && observation.value) draft.value!.page_id = value
}
function setGroup(
  id: string,
  key: Exclude<keyof GroupIdentity, 'adset_local_id'>,
  value: string | null,
) {
  if (!editable()) return
  let row = group(id)
  if (!row) {
    row = {
      adset_local_id: id,
      pixel_id: null,
      conversion_event: null,
      application_id: null,
      object_store_url: null,
    }
    draft.value!.groups.push(row)
  }
  row[key] = value
}
function setOverride(id: string, value: string | undefined) {
  if (!editable()) return
  draft.value!.ad_overrides = draft.value!.ad_overrides.filter((row) => row.ad_local_id !== id)
  if (value) draft.value!.ad_overrides.push({ ad_local_id: id, page_id: value })
}
async function removeEntry(kind: 'groups' | 'ad_overrides', id: string) {
  if (!editable()) return
  try {
    await ElMessageBox.confirm('仅明确移除此绑定，其他账户和树节点输入保留。', '移除身份绑定', {
      type: 'warning',
    })
  } catch {
    return
  }
  if (!editable()) return
  if (kind === 'groups')
    draft.value!.groups = draft.value!.groups.filter((row) => row.adset_local_id !== id)
  else draft.value!.ad_overrides = draft.value!.ad_overrides.filter((row) => row.ad_local_id !== id)
}
async function removeAccount(id: string) {
  if (props.disabled || props.readOnly || editing.value) return
  try {
    await ElMessageBox.confirm(
      '此账户的默认主页、广告组身份和广告覆盖将从本地草稿移除。是否继续？',
      '移除账户身份',
      { type: 'warning' },
    )
  } catch {
    return
  }
  if (!props.disabled && !props.readOnly && !editing.value)
    emit(
      'update:modelValue',
      props.modelValue.filter((row) => row.account_id !== id),
    )
}
function apply() {
  if (!editable() || loading.value) return
  issues.value = []
  const value = draft.value!,
    index = Math.max(
      0,
      props.modelValue.findIndex((row) => row.account_id === editing.value),
    ),
    root = `/identity_bindings/${index}`
  const issue = (path: string, message: string) =>
    issues.value.push({ path: `${root}${path}`, message })
  const usable = (kind: string, id: string | null) =>
    !!id &&
    observation.value?.resources.some(
      (row) => row.kind === kind && row.external_id === id && row.usable,
    )
  if (!usable('PAGE', value.page_id))
    issue('/page_id', '请读取当前账户观察并选择可用主页；原值不会被自动替换')
  if (staleCount.value) issue('', '存在已不属于当前树的绑定，请明确处理')
  value.groups.forEach((row, i) => {
    const source = groups.value.find((item) => item.id === row.adset_local_id),
      path = `/groups/${i}`
    if (source?.objective === 'OUTCOME_SALES') {
      if (!usable('PIXEL', row.pixel_id)) issue(`${path}/pixel_id`, '网站目标请选择当前可用像素')
      if (!row.conversion_event?.trim() || [...row.conversion_event].length > 64)
        issue(`${path}/conversion_event`, '优化事件需1至64码点；值仅是待能力核验的草稿')
      if (row.application_id || row.object_store_url)
        issue(path, '网站配置不能混用应用字段；原值保留待明确移除')
    } else if (source?.objective === 'OUTCOME_APP_PROMOTION') {
      if (!usable('APPLICATION', row.application_id))
        issue(`${path}/application_id`, '应用目标请选择当前可用应用')
      try {
        const url = new URL(row.object_store_url ?? '')
        if (
          url.protocol !== 'https:' ||
          [...(row.object_store_url ?? '')].length > 2048 ||
          url.username ||
          url.password
        )
          throw new Error()
      } catch {
        issue(`${path}/object_store_url`, '请输入1至2048字符HTTPS商店URL；域名仍待能力核验')
      }
      if (row.pixel_id || row.conversion_event)
        issue(path, '应用配置不能混用网站字段；原值保留待明确移除')
    } else issue(`${path}/adset_local_id`, '广告组目标未配置或关联已失效')
  })
  value.ad_overrides.forEach((row, i) => {
    if (!usable('PAGE', row.page_id))
      issue(`/ad_overrides/${i}/page_id`, '广告覆盖主页未在当前账户观察中确认可用')
  })
  if (issues.value.length) return
  const result = cloneValue(props.modelValue),
    position = result.findIndex((row) => row.account_id === editing.value)
  if (position < 0) result.push(cloneValue(value))
  else result[position] = cloneValue(value)
  emit('update:modelValue', result)
  finish()
}
function finish() {
  resolveTrap?.(false)
  resolveTrap = undefined
  cancelRead()
  editing.value = ''
  draft.value = undefined
  observation.value = undefined
  issues.value = []
  emit('editing', false)
}
async function close(done?: () => void) {
  if (!props.readOnly && draft.value && initial.value !== JSON.stringify(draft.value)) {
    try {
      await ElMessageBox.confirm(
        '尚未应用的身份输入将丢弃，已在草稿中的绑定保持不变。是否取消？',
        '取消身份编辑',
        { type: 'warning' },
      )
    } catch {
      return
    }
  }
  finish()
  if (typeof done === 'function') done()
}
watch([context, () => props.canRead, () => props.disabled], () => {
  cancelRead()
  observation.value = undefined
})
watch(
  () => props.modelValue,
  () => {
    if (editing.value && !props.readOnly) frozen.value = '外部绑定已变化，需重新打开'
  },
  { deep: true },
)
watch(accounts, () => {
  accountPage.value = Math.min(
    accountPage.value,
    Math.max(1, Math.ceil(accounts.value.length / 20)),
  )
})
onBeforeUnmount(() => {
  resolveTrap?.(false)
  resolveTrap = undefined
  cancelRead()
  emit('editing', false)
})
/** 由同版本Plan错误定位触发一次按需观察；严格按真实binding/local_id解析，不按显示序号猜账户。 */
async function focusBinding(index: number, path: string[]): Promise<boolean> {
  const source = props.modelValue[index]
  if (
    !source ||
    props.disabled ||
    props.readOnly ||
    (editing.value && editing.value !== source.account_id)
  )
    return false
  if (!props.accountIds.includes(source.account_id)) return false
  let label = '',
    adId = '',
    needsObservation = false
  let targetGroup: { id: string; position: number } | undefined,
    targetAd: { id: string; position: number } | undefined
  const integer = (value: string | undefined) =>
    value && /^(0|[1-9]\d*)$/.test(value) && Number.isSafeInteger(Number(value))
      ? Number(value)
      : -1
  if (path.length === 1 && path[0] === 'page_id') {
    label = '默认主页 page_id'
    needsObservation = true
  } else if (path.length === 3 && path[0] === 'groups') {
    const row = source.groups[integer(path[1])],
      position = groups.value.findIndex((item) => item.id === row?.adset_local_id)
    if (!row || position < 0) return false
    targetGroup = { id: row.adset_local_id, position }
    const labels: Record<string, string> = {
      pixel_id: `像素 ${row.adset_local_id}`,
      conversion_event: `优化事件 ${row.adset_local_id}（待能力核验）`,
      application_id: `应用 ${row.adset_local_id}`,
      object_store_url: `应用商店HTTPS URL ${row.adset_local_id}（域名待核验）`,
    }
    label = labels[path[2]]
    needsObservation = ['pixel_id', 'application_id'].includes(path[2])
    if (!label) return false
  } else if (path.length === 3 && path[0] === 'ad_overrides' && path[2] === 'page_id') {
    const row = source.ad_overrides[integer(path[1])],
      position = ads.value.findIndex((item) => item.id === row?.ad_local_id)
    if (!row || position < 0) return false
    adId = row.ad_local_id
    targetAd = { id: adId, position }
    needsObservation = true
  } else return false
  if (!editing.value) open(source.account_id)
  if (contextChanged.value || !selectedAccount.value) return false
  if (targetGroup) {
    tab.value = 'groups'
    groupPage.value = Math.floor(targetGroup.position / 20) + 1
    editingGroup.value = targetGroup.id
  }
  if (targetAd) {
    tab.value = 'ads'
    adPage.value = Math.floor(targetAd.position / 20) + 1
    editingAd.value = targetAd.id
  }
  if (needsObservation && !observation.value && props.canRead) await load()
  if (!(await trapReady)) return false
  await nextTick()
  await nextTick()
  if (
    props.disabled ||
    props.readOnly ||
    contextChanged.value ||
    editing.value !== source.account_id
  )
    return false
  const root = identityFields.value?.$el
  const item = adId
    ? [...(root?.querySelectorAll<HTMLElement>('[data-identity-ad]') ?? [])].find(
        (item) => item.dataset.identityAd === adId,
      )
    : [...(root?.querySelectorAll('label') ?? [])]
        .find((row) => row.textContent?.trim() === label)
        ?.closest('.el-form-item')
  const target = item?.querySelector<HTMLElement>(
    'input:not([disabled]):not([type="hidden"]),textarea:not([disabled])',
  )
  if (!target) {
    error.value = '此字段目前没有可用的真实控件或身份观察，未假定授权；请保留原配置并检查读取提示。'
    return false
  }
  target.scrollIntoView?.({ block: 'nearest' })
  target.focus()
  return document.activeElement === target
}
defineExpose({ focusBinding })
</script>

<style scoped>
.identity-bindings {
  min-width: 0;
}
.identity-bindings :deep(.el-pagination) {
  margin: 14px 0;
  max-width: 100%;
  overflow: auto;
}
.account-label,
code,
pre {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.identity-bindings :deep(.el-alert) {
  margin: 12px 0;
}
:deep(.el-select-v2) {
  width: 100%;
}
:deep(.el-table__cell) {
  vertical-align: top;
}
li {
  margin: 8px 0;
}
</style>
