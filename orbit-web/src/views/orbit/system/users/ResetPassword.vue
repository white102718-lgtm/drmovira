<template>
  <el-dialog
    v-model="visible"
    title="重置登录密码"
    width="min(560px, calc(100vw - 24px))"
    :close-on-click-modal="false"
    :close-on-press-escape="!saving && !uncertain"
    :show-close="!saving && !uncertain"
    @closed="clear"
  >
    <p>{{ person?.display_name }} · 登录账号 {{ person?.login_account }}</p>
    <el-alert
      title="保存后旧密码立即失效，已有登录会话将被撤销。停用人员仍保持停用。"
      type="info"
      :closable="false"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form label-position="top" :disabled="saving || uncertain" @submit.prevent="save">
      <el-form-item label="新密码" required
        ><el-input
          v-model="password"
          type="password"
          show-password
          autocomplete="new-password"
          maxlength="64"
          placeholder="8至64个字符"
      /></el-form-item>
      <el-form-item label="确认新密码" required
        ><el-input
          v-model="confirmation"
          type="password"
          show-password
          autocomplete="new-password"
          maxlength="64"
          @keyup.enter="save"
      /></el-form-item>
    </el-form>
    <template #footer
      ><el-button :disabled="saving || uncertain" @click="visible = false">取消</el-button
      ><el-button type="primary" :loading="saving" @click="save">{{
        uncertain ? '重试本次重置' : '重置并撤销旧会话'
      }}</el-button></template
    >
  </el-dialog>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { userApi, UserRequestError, type OrbitUser } from '@/api/orbit/users'
const emit = defineEmits<{ changed: [] }>()
const visible = ref(false),
  saving = ref(false),
  uncertain = ref(false)
const person = ref<OrbitUser>(),
  password = ref(''),
  confirmation = ref(''),
  error = ref(''),
  csrf = ref('')
let intent: { password: string; key: string } | undefined
function clear() {
  password.value = ''
  confirmation.value = ''
  error.value = ''
  intent = undefined
  uncertain.value = false
}
async function open(row: OrbitUser) {
  clear()
  try {
    const caps = await userApi.capabilities()
    if (
      !caps.can_create ||
      row.id === caps.actor_user_id ||
      caps.protected_user_ids.includes(row.id)
    )
      throw new Error('本人及基础管理员请通过个人中心修改密码')
    person.value = await userApi.get(row.id)
    csrf.value = caps.csrf_token
    visible.value = true
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '读取人员失败')
  }
}
async function save() {
  if (saving.value || !person.value) return
  if (
    !uncertain.value &&
    (password.value.length < 8 ||
      password.value.length > 64 ||
      password.value !== confirmation.value)
  ) {
    error.value = '请输入8至64个字符的新密码，并确认两次输入一致'
    return
  }
  if (!uncertain.value && intent?.password !== password.value)
    intent = { password: password.value, key: `user-password-${crypto.randomUUID()}` }
  saving.value = true
  error.value = ''
  try {
    await userApi.resetPassword(
      person.value.id,
      intent!.password,
      person.value.revision,
      csrf.value,
      intent!.key,
    )
    uncertain.value = false
    visible.value = false
    clear()
    ElMessage.success('登录密码已重置，旧会话已撤销')
    emit('changed')
  } catch (cause) {
    uncertain.value = !(cause instanceof UserRequestError) || cause.status >= 500
    error.value =
      (cause instanceof Error ? cause.message : '重置失败') +
      (uncertain.value ? '；结果未知，请重试本次重置。' : '')
  } finally {
    saving.value = false
  }
}
defineExpose({ open })
</script>
