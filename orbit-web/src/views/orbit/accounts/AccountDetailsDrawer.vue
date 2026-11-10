<template>
  <el-drawer
    v-model="visible"
    title="广告账户详情"
    size="min(760px, calc(100vw - 24px))"
    @close="invalidate"
  >
    <el-skeleton v-if="loading" :rows="10" animated />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button v-if="error" @click="load">重新读取详情</el-button>
    <template v-if="item && !loading">
      <el-descriptions :column="1" border class="account-details-fields">
        <el-descriptions-item v-for="field in fields" :key="field[0]" :label="field[0]">{{
          field[1]
        }}</el-descriptions-item>
      </el-descriptions>
      <h3>金额来源与更新时间</h3>
      <el-descriptions :column="1" border>
        <el-descriptions-item v-for="field in moneyFields" :key="field.label" :label="field.label">
          {{ accountAmount(field.value) }}；来源 {{ field.value.source }}；观测
          {{ accountTime(field.value.observed_at) }}
        </el-descriptions-item>
      </el-descriptions>
      <h3>身份资源</h3>
      <el-descriptions :column="1" border class="account-identity-summary">
        <el-descriptions-item
          v-for="field in identitySummaryFields"
          :key="field[0]"
          :label="field[0]"
          >{{ field[1] }}</el-descriptions-item
        >
      </el-descriptions>
      <p>读取已观测的主页、像素与应用；有权查看资源不代表具备创建投放权限。</p>
      <el-button :loading="identityLoading" @click="loadIdentities">读取身份资源</el-button>
      <el-alert v-if="identityError" :title="identityError" type="error" :closable="false" />
      <template v-if="identities">
        <p>
          观测时间：{{ accountTime(identities.observed_at) }}；能力版本：{{
            identities.capability_version
          }}
        </p>
        <el-table :data="identities.resources" empty-text="本次已观测快照中没有身份资源">
          <el-table-column prop="kind" label="类型" width="130" />
          <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="external_id" label="外部ID" min-width="180" />
          <el-table-column label="可用性" min-width="180"
            ><template #default="{ row }">{{
              row.usable ? '可用' : row.reason_code || '不可用'
            }}</template></el-table-column
          >
        </el-table>
      </template>
      <p v-else-if="!identityLoading && !identityError">
        {{ item.details.identity_status === 'UNSYNCED' ? '尚未同步身份资源' : '尚未读取身份资源' }}
      </p>
    </template>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  accountDetailsApi,
  accountAmount,
  accountAuthorizations,
  accountPeriod,
  accountSpendStatus,
  accountStates,
  accountText,
  accountTime,
  type ExtendedAccount,
  type AccountIdentities,
} from '@/api/orbit/account-details'
const visible = ref(false),
  loading = ref(false),
  error = ref(''),
  item = ref<ExtendedAccount | null>(null)
const identities = ref<AccountIdentities | null>(null),
  identityLoading = ref(false),
  identityError = ref('')
let identifier = '',
  query = new URLSearchParams(),
  version = 0,
  identityVersion = 0
let controller: AbortController | undefined, identityController: AbortController | undefined
const identitySummaryFields = computed(() => {
  const details = item.value?.details
  if (!details) return []
  const synced = details.identity_status === 'SYNCED'
  return [
    [
      '身份同步状态',
      synced ? '已同步' : details.identity_status === 'UNSYNCED' ? '未同步' : '未知',
    ],
    [
      '身份资源数量',
      synced && Number.isSafeInteger(details.identity_count) && details.identity_count! >= 0
        ? String(details.identity_count)
        : '未知',
    ],
    [
      '身份摘要观测时间',
      synced && details.identity_observed_at
        ? accountTime(details.identity_observed_at)
        : '未提供/未知',
    ],
  ]
})
const fields = computed(() => {
  if (!item.value) return []
  const { account: a, details: d } = item.value
  return [
    ['账户名称', a.name],
    ['外部ID', a.external_id],
    ['投放师', d.owner_display ?? a.ownership.owner_user_id],
    ['所属团队ID', a.ownership.owner_team_id],
    ['户商代称', a.vendor_alias ?? '尚未提供真实代称'],
    ['户商资料名称', d.vendor_display.name ?? '未提供'],
    ['户商资料来源', d.vendor_display.source],
    [
      '代称来源与版本',
      `${d.vendor_display.alias_source ?? '未提供'}；${d.vendor_display.alias_revision ?? '未提供'}`,
    ],
    ['个号名称', accountText(d.personal_profile)],
    ['业务主体', accountText(d.business_entity)],
    [
      '关联BM',
      d.business_managers === null
        ? '未提供'
        : d.business_managers.map((x) => `${x.name} / ${x.external_id}`).join('；') ||
          '本次观测无BM',
    ],
    ['账户状态', accountStates[a.account_status]],
    ['授权状态', accountAuthorizations[a.auth_status]],
    ['付费类型', accountText(d.payment_type)],
    ['付费方式', accountText(d.payment_method)],
    ['币种', a.currency],
    ['账户时区', a.timezone.display_label],
    ['消耗时间', accountPeriod(item.value)],
    [
      '消耗覆盖',
      d.spend_window.coverage === 'COMPLETE'
        ? '完整'
        : d.spend_window.coverage === 'PARTIAL'
          ? '部分缺失，金额未知'
          : '尚未采集',
    ],
    ['消耗读取状态', accountSpendStatus(d)],
    ['消耗读取时间', accountTime(d.spend_sync?.observed_at ?? null)],
    ['封禁原因', accountText(d.blocked_reason)],
    ['封禁观测时间', accountTime(d.blocked_observed_at)],
    ['授权时间', accountTime(d.authorized_at)],
    ['本地解绑时间', accountTime(d.unbound_at)],
    ['最近同步', accountTime(a.synced_at)],
    ['备注', d.note ?? '未提供'],
    ...(
      [
        'personal_profile',
        'business_entity',
        'payment_type',
        'payment_method',
        'blocked_reason',
      ] as const
    ).map((key) => [
      `${{ personal_profile: '个号', business_entity: '主体', payment_type: '付费类型', payment_method: '付费方式', blocked_reason: '封禁原因' }[key]}来源与时间`,
      `${d[key].source}；${accountTime(d[key].observed_at)}`,
    ]),
  ]
})
const moneyFields = computed(() =>
  item.value
    ? [
        { label: '账户余额', value: item.value.account.balance },
        { label: '应付账单', value: item.value.details.payable },
        { label: '累计总花费', value: item.value.details.lifetime_spend },
        { label: '窗口消耗', value: item.value.account.spend },
      ]
    : [],
)
function invalidate() {
  version++
  identityVersion++
  controller?.abort()
  identityController?.abort()
  loading.value = false
  identityLoading.value = false
}
async function load() {
  controller?.abort()
  controller = new AbortController()
  const current = ++version
  loading.value = true
  error.value = ''
  item.value = null
  try {
    const value = await accountDetailsApi.get(identifier, query, controller.signal)
    if (current === version) item.value = value
  } catch (cause) {
    if (current === version)
      error.value = cause instanceof Error ? cause.message : '账户详情读取失败'
  } finally {
    if (current === version) loading.value = false
  }
}
async function loadIdentities() {
  identityController?.abort()
  identityController = new AbortController()
  const current = ++identityVersion
  identities.value = null
  identityError.value = ''
  identityLoading.value = true
  try {
    const value = await accountDetailsApi.identities(identifier, identityController.signal)
    if (current === identityVersion) identities.value = value
  } catch (cause) {
    if (current === identityVersion)
      identityError.value =
        cause instanceof Error ? cause.message : '身份资源未能读取，请重试或检查权限'
  } finally {
    if (current === identityVersion) identityLoading.value = false
  }
}
function open(id: string, windowQuery: URLSearchParams) {
  invalidate()
  identifier = id
  query = new URLSearchParams(windowQuery)
  identities.value = null
  identityError.value = ''
  visible.value = true
  void load()
}
onBeforeUnmount(invalidate)
defineExpose({ open })
</script>
<style scoped>
.account-details-fields {
  margin-bottom: 20px;
}
:deep(.el-descriptions__content) {
  overflow-wrap: anywhere;
}
:deep(.el-alert) {
  margin: 12px 0;
}
h3 {
  margin: 24px 0 12px;
}
</style>
