<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import useUserStore from '@/store/modules/user'
import MetaConnectionsPanel from '../../accounts/components/MetaConnectionsPanel.vue'
import ImportAccounts from '../../accounts/ImportAccounts.vue'
import { metaConnectionApi } from '@/api/orbit/meta-connections'
import { ReferenceApiError } from '@/api/orbit/references'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getConfigurationMetadata,
  listConfigurations,
  testConfiguration,
  type Configuration,
  type ConfigSection,
} from '@/api/orbit/configuration'
import ConfigurationDialog from './ConfigurationDialog.vue'
import MetricPublicationPanel from './MetricPublicationPanel.vue'
import ConfigurationHistory from './ConfigurationHistory.vue'
import { configurationTextError } from './validation'

const user = useUserStore()
const metaOpen = ref(false)
const publicationOpen = ref(false)
const publicationId = ref('')
function openPublication(id: string) {
  publicationId.value = id
  publicationOpen.value = true
}
const canPublish = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('system.release.manage'),
)
const importResult = ref<InstanceType<typeof ImportAccounts>>()
const bmBusy = ref(false)
const bmNotice = ref('')
const bmPending = ref<{ id: string; revision: number; name: string; key: string } | null>(null)
const contextKey = computed(() => JSON.stringify([user.id, user.permissions]))
watch(contextKey, () => {
  bmPending.value = null
  bmBusy.value = false
  bmNotice.value = ''
})
async function connectBm(row?: Configuration) {
  if (bmBusy.value) return
  if (!bmPending.value) {
    if (!row || row.section !== 'META_BM' || !row.enabled) return
    try {
      await ElMessageBox.confirm(
        `配置：${row.name}（版本${row.revision}）。验证系统用户权限并枚举可读账户，成功后登记读取连接；不创建或修改广告。`,
        '接入 Meta/BM 读取',
        {
          confirmButtonText: '验证并接入',
          cancelButtonText: '取消',
          type: 'info',
          closeOnClickModal: false,
        },
      )
    } catch {
      return
    }
    bmPending.value = {
      id: row.id,
      revision: row.revision,
      name: row.name,
      key: 'meta-bm-' + crypto.randomUUID(),
    }
  }
  const intent = bmPending.value,
    context = contextKey.value
  bmBusy.value = true
  bmNotice.value = ''
  try {
    const cap = await metaConnectionApi.capabilities()
    if (context !== contextKey.value) return
    if (!cap.configured)
      throw new ReferenceApiError(422, 'META_APP_UNCONFIGURED', '平台应用未配置完整')
    const result = await metaConnectionApi.connectBm(
      intent.id,
      intent.revision,
      cap.csrf_token,
      intent.key,
    )
    if (context !== contextKey.value) return
    bmPending.value = null
    bmNotice.value = `BM 读取连接已登记，实际可读账户 ${result.accessible_account_count} 个。请在 Meta 连接中选择要接入的平台账户。`
    metaOpen.value = true
  } catch (error) {
    if (context !== contextKey.value) return
    const rejected =
      error instanceof ReferenceApiError &&
      [400, 401, 403, 404, 409, 410, 422].includes(error.status)
    if (rejected) bmPending.value = null
    bmNotice.value = rejected
      ? 'BM 接入未通过，请检查配置版本、权限和平台应用后重试。'
      : 'BM 接入结果尚未确认，请使用重试原请求，保留原配置版本和幂等键。'
  } finally {
    if (context === contextKey.value) bmBusy.value = false
  }
}

const history = ref<InstanceType<typeof ConfigurationHistory>>()
const loading = ref(false)
const errorMessage = ref('')
const configurations = ref<Configuration[]>([])
const sections = ref<ConfigSection[]>([])
const encryptionReady = ref(false)
const sectionFilter = ref('')
const nameFilter = ref('')
const testingId = ref('')
const dialog = ref<InstanceType<typeof ConfigurationDialog>>()
let loadVersion = 0
const rows = computed(() =>
  configurations.value.filter(
    (item) =>
      (!sectionFilter.value || item.section === sectionFilter.value) &&
      item.name.toLocaleLowerCase().includes(nameFilter.value.trim().toLocaleLowerCase()),
  ),
)
const statusNames: Record<string, string> = {
  UNTESTED: '尚未验证',
  READ_VERIFIED: '只读认证通过',
  FAILED: '验证失败',
  BLOCKED: '待连接器实测',
}

/** 请求失败保留筛选与旧数据，页面明确展示重试，不伪装为空列表。 */
async function load() {
  const currentVersion = ++loadVersion
  loading.value = true
  errorMessage.value = ''
  try {
    const [metadata, list] = await Promise.all([getConfigurationMetadata(), listConfigurations()])
    // 刷新与保存后的读取可能重叠；只接受最后发起的请求，旧响应不能抹掉已保存的新配置。
    if (currentVersion !== loadVersion) return
    sections.value = metadata.sections
    encryptionReady.value = metadata.encryptionReady
    configurations.value = list
  } catch (error) {
    if (currentVersion === loadVersion) {
      errorMessage.value = error instanceof Error ? error.message : '系统配置读取失败'
    }
  } finally {
    if (currentVersion === loadVersion) loading.value = false
  }
}

/** 只读测试不会解锁AI建议自动提交或广告平台写能力。 */
async function test(row: Configuration) {
  testingId.value = row.id
  try {
    let reason: string
    try {
      const answer = await ElMessageBox.prompt(
        `配置：${row.name}（版本${row.revision}）。仅进行只读认证，不会创建或修改广告。`,
        '只读连接测试',
        {
          confirmButtonText: '开始测试',
          cancelButtonText: '取消',
          inputPlaceholder: '填写测试原因，请勿填写密钥或Token',
          inputValidator(value) {
            return configurationTextError(value || '', 500, true) || true
          },
          closeOnClickModal: false,
        },
      )
      reason = answer.value
    } catch {
      // 取消确认只关闭弹窗，不发起测试，不写版本或审计。
      return
    }
    const { configuration, result } = await testConfiguration(row, reason)
    configurations.value = configurations.value.map((item) =>
      item.id === row.id ? configuration : item,
    )
    if (result.status === 'READ_VERIFIED') ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '连接测试失败')
  } finally {
    testingId.value = ''
  }
}

function label(key: string) {
  return sections.value.find((item) => item.key === key)?.label ?? key
}

/** 凭据列使用业务名称，不直接展示内部字段名。 */
function secretLabel(section: string, key: string | number) {
  return (
    sections.value
      .find((item) => item.key === section)
      ?.fields.find((field) => field.key === String(key))?.label ?? '凭据'
  )
}

onMounted(load)
onBeforeUnmount(() => {
  loadVersion++
})
</script>

<template>
  <div class="app-container">
    <h2>系统配置</h2>
    <el-alert v-if="bmNotice" :title="bmNotice" type="info" :closable="false" />
    <div class="configuration-meta-toolbar">
      <el-button
        type="primary"
        :disabled="!sections.length"
        @click="dialog?.open(undefined, 'META_APP')"
        >绑定 Meta 应用</el-button
      >
      <el-button @click="metaOpen = true">Meta 连接与授权状态</el-button>
      <el-button v-if="bmPending" :loading="bmBusy" @click="connectBm()"
        >重试 BM 接入原请求</el-button
      >
    </div>
    <p class="configuration-summary">
      集中维护AI建议、GPT、Claude、Meta/BM及业务集成配置。凭据加密保存，页面只展示脱敏状态。
    </p>
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
      class="configuration-notice"
    >
      <el-button text type="primary" @click="load">重新加载</el-button>
    </el-alert>
    <el-alert
      v-else-if="!encryptionReady && !loading"
      title="服务端尚未配置独立凭据主密钥，新增或替换密钥已禁用。请由管理员配置服务端密钥后继续。"
      type="warning"
      :closable="false"
      show-icon
      class="configuration-notice"
    />
    <el-form inline @submit.prevent>
      <el-form-item label="配置类型">
        <el-select v-model="sectionFilter" clearable placeholder="全部类型" style="width: 240px">
          <el-option
            v-for="item in sections"
            :key="item.key"
            :label="item.label"
            :value="item.key"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="配置名称">
        <el-input v-model="nameFilter" clearable maxlength="100" placeholder="搜索配置名称" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :disabled="!sections.length" @click="dialog?.open()"
          >新增配置</el-button
        >
        <el-button :loading="loading" @click="load">刷新</el-button>
      </el-form-item>
    </el-form>
    <el-table
      v-loading="loading"
      :data="rows"
      row-key="id"
      border
      empty-text="暂无符合条件的配置，可新增GPT、Claude或Meta/BM等配置"
    >
      <el-table-column prop="name" label="配置名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="配置类型" min-width="180"
        ><template #default="{ row }">{{ label(row.section) }}</template></el-table-column
      >
      <el-table-column label="启用状态" width="110"
        ><template #default="{ row }"
          ><el-tag :type="row.enabled ? 'success' : 'info'">{{
            row.enabled ? '已启用' : '已停用'
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column label="凭据状态" min-width="190">
        <template #default="{ row }">
          <template v-if="Object.keys(row.secrets).length">
            <el-tag
              v-for="(secret, key) in row.secrets"
              :key="key"
              :type="secret.configured ? 'success' : 'warning'"
              class="configuration-tag"
              >{{ secretLabel(row.section, key) }}：{{ secret.hint }}</el-tag
            >
          </template>
          <span v-else>无需云端凭据</span>
        </template>
      </el-table-column>
      <el-table-column label="只读验证" min-width="160"
        ><template #default="{ row }">{{
          statusNames[row.verificationStatus] ?? '未知状态'
        }}</template></el-table-column
      >
      <el-table-column prop="revision" label="版本" width="80" />
      <el-table-column prop="updatedAt" label="最近更新（UTC）" min-width="220" />
      <el-table-column label="操作" width="390" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="dialog?.open(row)">编辑</el-button>
          <el-button link type="primary" @click="history?.open(row)">变更历史</el-button>
          <el-button
            link
            type="primary"
            :loading="testingId === row.id"
            :disabled="!!testingId && testingId !== row.id"
            @click="test(row)"
            >只读连接测试</el-button
          >
          <el-button
            v-if="row.section === 'META_BM'"
            link
            type="primary"
            :disabled="!row.enabled || !encryptionReady || bmBusy || !!bmPending"
            @click="connectBm(row)"
            >接入账户读取</el-button
          >
          <el-button
            v-if="row.section === 'METRICS' && canPublish"
            link
            type="primary"
            :disabled="!row.enabled"
            @click="openPublication(row.id)"
            >发布指标口径</el-button
          >
        </template>
      </el-table-column>
    </el-table>
    <el-dialog
      v-model="metaOpen"
      title="Meta 连接与授权状态"
      width="min(1200px, calc(100vw - 24px))"
    >
      <MetaConnectionsPanel
        :active="metaOpen"
        :context-key="contextKey"
        @accepted="
          (batch) => {
            metaOpen = false
            importResult?.showResult(batch)
          }
        "
      />
    </el-dialog>
    <el-dialog
      v-model="publicationOpen"
      title="验证并发布指标口径"
      width="min(800px, calc(100vw - 24px))"
    >
      <MetricPublicationPanel
        :active="publicationOpen"
        :configuration-id="publicationId"
        :context-key="contextKey"
      />
    </el-dialog>
    <ImportAccounts ref="importResult" />
    <ConfigurationHistory ref="history" />
    <ConfigurationDialog
      ref="dialog"
      :sections="sections"
      :configurations="configurations"
      :encryption-ready="encryptionReady"
      @saved="load"
    />
  </div>
</template>

<style scoped>
.configuration-meta-toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.configuration-summary {
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.configuration-notice {
  margin-bottom: 20px;
}
.configuration-tag {
  margin: 3px 6px 3px 0;
}
</style>
