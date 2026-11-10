<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import {
  saveConfiguration,
  type Configuration,
  type ConfigurationWrite,
  type ConfigSection,
  ConfigurationApiError,
} from '@/api/orbit/configuration'
import { ConfigurationSaveIntent } from '@/api/orbit/configuration-intent'
import { configurationSecretError, configurationTextError } from './validation'
import MaterialScannerProfileSelect from './MaterialScannerProfileSelect.vue'

const props = defineProps<{
  sections: ConfigSection[]
  configurations: Configuration[]
  encryptionReady: boolean
}>()
const emit = defineEmits<{ saved: [] }>()
const visible = ref(false)
const saving = ref(false)
const saveIntent = new ConfigurationSaveIntent()
const existing = ref<Configuration>()
const formRef = ref<FormInstance>()
const form = reactive<ConfigurationWrite>({
  section: 'AI_GPT',
  name: '',
  enabled: false,
  settings: {},
  secrets: {},
  reason: '',
})
const section = computed(() => props.sections.find((item) => item.key === form.section))
const publicFields = computed(
  () => section.value?.fields.filter((field) => field.type !== 'secret') ?? [],
)
const secretFields = computed(
  () => section.value?.fields.filter((field) => field.type === 'secret') ?? [],
)
const providers = computed(() =>
  props.configurations.filter(
    (item) => item.enabled && ['AI_GPT', 'AI_CLAUDE'].includes(item.section),
  ),
)

/** Element Plus表单使用与Python一致的文本计数和控制符规则。 */
function textRules(maximum: number, required: boolean) {
  return [
    {
      validator: (_rule: unknown, value: unknown, done: (error?: Error) => void) => {
        const message = configurationTextError(value, maximum, required)
        done(message ? new Error(message) : undefined)
      },
      trigger: 'blur',
    },
  ]
}

function secretRules(key: string, required: boolean) {
  return [
    {
      validator: (_rule: unknown, _value: unknown, done: (error?: Error) => void) => {
        const change = form.secrets[key]
        let message = change?.operation === 'REPLACE' ? configurationSecretError(change.value) : ''
        if (form.enabled && required && change?.operation !== 'REPLACE') {
          if (change?.operation === 'CLEAR') message = '启用配置不能清除所需凭据，请先停用'
          else if (!existing.value?.secrets[key]?.configured) message = '启用配置必须提供此凭据'
        }
        done(message ? new Error(message) : undefined)
      },
      trigger: 'blur',
    },
  ]
}

/** 新建切换配置类型时清空旧提供商的设置及凭据，避免串用。 */
function resetSection() {
  form.settings = {}
  form.secrets = {}
  for (const field of section.value?.fields ?? []) {
    if (field.type === 'secret') {
      form.secrets[field.key] = { operation: 'KEEP', value: '' }
    } else {
      form.settings[field.key] = field.defaultValue ?? ''
    }
  }
}

watch(
  () => form.section,
  () => {
    if (!existing.value) resetSection()
  },
)

/** 对话框使用公开数据回填，不尝试读取或回显已保存Token。 */
async function open(value?: Configuration, initialSection?: string) {
  saveIntent.reset()
  existing.value = value
  form.section = value?.section ?? initialSection ?? props.sections[0]?.key ?? 'AI_GPT'
  resetSection()
  form.name = value?.name ?? ''
  form.enabled = value?.enabled ?? initialSection === 'META_APP'
  form.reason = ''
  // 新增字段只在编辑表单补默认值，确认保存后才写入新版本，不改变历史GET快照。
  if (value) form.settings = { ...form.settings, ...value.settings }
  visible.value = true
  await nextTick()
  formRef.value?.clearValidate()
}

/** 关闭、成功和失败都释放密钥输入，业务请求不会写浏览器缓存。 */
function clearSecrets() {
  for (const key of Object.keys(form.secrets)) {
    form.secrets[key] = { operation: 'KEEP', value: '' }
  }
}

/** 提交前明确确认清除；启用所需字段由服务端再次校验。 */
async function submit() {
  if (!(await formRef.value?.validate().catch(() => false))) return
  const cleared = secretFields.value.filter(
    (field) => form.secrets[field.key]?.operation === 'CLEAR',
  )
  if (cleared.length) {
    try {
      await ElMessageBox.confirm(
        `将清除以下凭据：${cleared.map((field) => field.label).join('、')}。相关功能可能不可用，是否继续？`,
        '确认清除凭据',
        { type: 'warning', confirmButtonText: '清除并保存', cancelButtonText: '返回检查' },
      )
    } catch {
      return
    }
  }
  saving.value = true
  try {
    const secrets: ConfigurationWrite['secrets'] = {}
    for (const [key, change] of Object.entries(form.secrets)) {
      secrets[key] =
        change.operation === 'REPLACE'
          ? { operation: change.operation, value: change.value }
          : { operation: change.operation }
    }
    const value = { ...form, settings: { ...form.settings }, secrets }
    const requestKey = await saveIntent.prepare(value, existing.value)
    await saveConfiguration(value, existing.value, requestKey)
    saveIntent.reset()
    ElMessage.success('配置已保存；连接状态需重新验证')
    visible.value = false
    emit('saved')
  } catch (error) {
    // 4xx明确拒绝可结束意图；超时、网关及网络失败保留摘要，重输相同凭据后仍可安全重放。
    if (
      error instanceof ConfigurationApiError &&
      error.status >= 400 &&
      error.status < 500 &&
      error.status !== 408
    )
      saveIntent.reset()
    ElMessage.error(error instanceof Error ? error.message : '配置保存失败')
  } finally {
    saving.value = false
    clearSecrets()
  }
}

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="existing ? '编辑系统配置' : '新增系统配置'"
    width="720px"
    :style="{ maxWidth: 'calc(100vw - 32px)' }"
    destroy-on-close
    :close-on-click-modal="false"
    :close-on-press-escape="!saving"
    :before-close="
      (done: () => void) => {
        if (!saving) done()
      }
    "
    @closed="
      () => {
        clearSecrets()
        saveIntent.reset()
      }
    "
  >
    <el-alert
      v-if="form.section === 'MATERIAL_SCANNER'"
      title="保存或测试会更新扫描配置版本，正在处理的素材可能需要重新检查"
      type="warning"
      :closable="false"
      show-icon
      class="configuration-notice"
    />
    <el-alert
      title="凭据只写不读。留空并保持表示沿用已有凭据；替换或清除需明确选择。保存不会开启广告写入能力。"
      type="info"
      :closable="false"
      class="configuration-notice"
    />
    <el-form ref="formRef" :model="form" label-position="top" :disabled="saving" autocomplete="off">
      <el-form-item label="配置类型" prop="section" required>
        <el-select v-model="form.section" :disabled="!!existing" class="configuration-control">
          <el-option
            v-for="item in sections"
            :key="item.key"
            :label="item.label"
            :value="item.key"
          />
        </el-select>
      </el-form-item>
      <el-alert
        v-if="form.section === 'META_APP'"
        type="info"
        :closable="false"
        title="OAuth回调：https://drmovira.com/api/v1/integrations/meta/callback。当前不使用JavaScript SDK，SDK网域可留空。市场营销Token仅加密保存，不代替客户授权。"
      />
      <template v-if="form.section === 'META_APP' && existing">
        <el-form-item label="取消授权回调">
          <el-input
            readonly
            :model-value="`https://drmovira.com/api/v1/integrations/meta/applications/${existing.id}/deauthorization`"
          />
        </el-form-item>
        <el-form-item label="数据删除请求回调">
          <el-input
            readonly
            :model-value="`https://drmovira.com/api/v1/integrations/meta/applications/${existing.id}/data-deletion`"
          />
        </el-form-item>
      </template>
      <el-form-item
        :label="form.section === 'META_APP' ? '应用名称' : '配置名称'"
        prop="name"
        :rules="textRules(100, true)"
      >
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="启用配置">
        <el-switch v-model="form.enabled" active-text="可被业务选择" inactive-text="停用" />
      </el-form-item>
      <el-form-item
        v-for="field in publicFields"
        :key="field.key"
        :label="field.label"
        :prop="`settings.${field.key}`"
        :rules="
          field.type === 'text' && field.key !== 'providerConfigId'
            ? textRules(field.maximum ?? 500, form.enabled && field.required)
            : [{ required: form.enabled && field.required, message: `请填写${field.label}` }]
        "
      >
        <MaterialScannerProfileSelect
          v-if="form.section === 'MATERIAL_SCANNER' && field.key === 'profileId'"
          v-model="form.settings[field.key]"
        />
        <el-select
          v-else-if="field.key === 'providerConfigId'"
          v-model="form.settings[field.key]"
          class="configuration-control"
          placeholder="选择本租户已启用的GPT或Claude配置"
        >
          <el-option
            v-for="provider in providers"
            :key="provider.id"
            :label="provider.name"
            :value="provider.id"
          />
        </el-select>
        <el-input-number
          v-else-if="field.type === 'integer'"
          v-model="form.settings[field.key] as number"
          :precision="0"
          :min="field.minimum ?? undefined"
          :max="field.maximum ?? undefined"
          controls-position="right"
        />
        <el-select
          v-else-if="field.type === 'select'"
          v-model="form.settings[field.key]"
          class="configuration-control"
        >
          <el-option
            v-for="option in field.options"
            :key="option"
            :label="option"
            :value="option"
          />
        </el-select>
        <el-input v-else v-model="form.settings[field.key]" />
      </el-form-item>
      <template v-for="field in secretFields" :key="field.key">
        <el-form-item
          :label="field.label"
          :required="
            form.enabled && field.required && form.secrets[field.key]?.operation === 'REPLACE'
          "
          :prop="`secrets.${field.key}.value`"
          :rules="secretRules(field.key, field.required)"
        >
          <div class="configuration-secret">
            <el-tag :type="existing?.secrets[field.key]?.configured ? 'success' : 'info'">
              {{ existing?.secrets[field.key]?.hint ?? '未配置' }}
            </el-tag>
            <el-select
              v-model="form.secrets[field.key].operation"
              :aria-label="`${field.label}操作`"
              @change="form.secrets[field.key].value = ''"
            >
              <el-option label="保持不变" value="KEEP" />
              <el-option label="替换凭据" value="REPLACE" :disabled="!encryptionReady" />
              <el-option label="清除凭据" value="CLEAR" />
            </el-select>
            <el-input
              v-if="form.secrets[field.key].operation === 'REPLACE'"
              v-model="form.secrets[field.key].value"
              type="password"
              autocomplete="new-password"
              :aria-label="field.label"
              placeholder="请输入新凭据，保存后不回显"
            />
          </div>
        </el-form-item>
      </template>
      <el-form-item label="变更原因" prop="reason" :rules="textRules(500, true)">
        <el-input
          v-model="form.reason"
          placeholder="说明配置用途或本次变更原因，请勿填写任何密钥"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="saving" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.configuration-notice {
  margin-bottom: 20px;
}
.configuration-control {
  width: 100%;
}
.configuration-secret {
  display: flex;
  width: 100%;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.configuration-secret > .el-select {
  width: 160px;
}
</style>
