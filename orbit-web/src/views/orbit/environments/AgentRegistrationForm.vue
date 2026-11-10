<template>
  <el-form label-position="top" @submit.prevent="submit">
    <el-alert
      title="登记仅保存机器资料，不代表机器在线或具备广告操作能力。"
      type="info"
      :closable="false"
    />
    <el-form-item label="机器名称" :error="fieldError('name')">
      <el-input
        v-model="form.name"
        aria-label="机器名称"
        :disabled="disabled"
        placeholder="1 至 80 个字符"
      />
    </el-form-item>
    <el-form-item label="本地 API 地址" :error="fieldError('endpoint')">
      <el-input
        v-model="form.endpoint"
        aria-label="本地 API 地址"
        :disabled="disabled"
        placeholder="填写执行机发现的本地地址"
      />
      <div class="agent-help">
        支持 HTTP/HTTPS、域名、IP、自定义端口及代理路径。地址由 AdsPower 所在执行机访问；Local API
        Key 只留在执行机。
      </div>
    </el-form-item>
    <el-form-item label="探测周期（秒）" :error="fieldError('probe_interval')">
      <el-input-number
        v-model="form.probe_interval"
        aria-label="探测周期（秒）"
        :min="10"
        :max="300"
        :step="1"
        :disabled="disabled"
      />
      <span class="agent-help">10 至 300 秒；实际探测仍受每台机器限流约束。</span>
    </el-form-item>
    <el-descriptions title="登记后的验证层次" :column="1" border size="small">
      <el-descriptions-item label="设备证书"
        >未知，须通过独立登记流程签发并绑定 Agent；此表单不签发或展示密钥。</el-descriptions-item
      >
      <el-descriptions-item label="心跳">未知，以服务端接收的可信心跳为准。</el-descriptions-item>
      <el-descriptions-item label="Meta 登录"
        >未知，需逐 Profile 核验登录及账户身份。</el-descriptions-item
      >
      <el-descriptions-item label="操作能力"
        >未知，需按动作、通道和版本分别验证。</el-descriptions-item
      >
    </el-descriptions>
    <el-alert v-if="error && !error.field" :title="error.message" type="error" :closable="false" />
    <p v-if="disabled && disabledReason" role="status">{{ disabledReason }}</p>
    <el-button class="agent-submit" type="primary" native-type="submit" :disabled="disabled">{{
      submitLabel
    }}</el-button>
  </el-form>
</template>
<script setup lang="ts">
import { reactive, ref } from 'vue'
import { AgentFieldError, parseAgentWrite, type AgentWrite } from '@/api/orbit/environments'
const props = withDefaults(
  defineProps<{
    disabled?: boolean
    disabledReason?: string
    submitLabel?: string
    initialValue?: AgentWrite
  }>(),
  { disabled: false, disabledReason: '', submitLabel: '登记机器' },
)
const emit = defineEmits<{ submit: [value: AgentWrite] }>()
const form = reactive({
  name: props.initialValue?.name ?? '',
  endpoint: props.initialValue?.endpoint ?? '',
  probe_interval: (props.initialValue?.probe_interval ?? 30) as number | undefined,
})
const error = ref<AgentFieldError | null>(null)
function fieldError(field: string) {
  return error.value?.field === field ? error.value.message : undefined
}
function submit() {
  if (props.disabled) return
  error.value = null
  try {
    emit('submit', parseAgentWrite(form))
  } catch (cause) {
    error.value =
      cause instanceof AgentFieldError ? cause : new AgentFieldError('', '请核对登记字段')
  }
}
</script>
<style scoped>
.agent-help {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.agent-submit {
  margin-top: 16px;
}
.el-alert {
  margin-bottom: 16px;
}
</style>
