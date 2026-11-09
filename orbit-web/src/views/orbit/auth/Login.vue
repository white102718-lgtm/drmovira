<template>
  <main class="orbit-auth-page">
    <el-card class="orbit-auth-panel" shadow="never">
      <h2>{{ callback ? '登录验证' : invited ? '接受人员邀请' : 'ORBIT 企业登录' }}</h2>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-skeleton v-if="loading" :rows="3" animated />
      <template v-else-if="!callback">
        <p v-if="invited">请使用收到邀请的邮箱对应的企业账号验证身份。验证成功后才能启用账号。</p>
        <el-form v-if="!invited && providers.length" label-position="top" @submit.prevent="start">
          <el-form-item label="企业登录提供者">
            <el-select v-model="selected" placeholder="请选择登录提供者" class="provider-select">
              <el-option
                v-for="provider in providers"
                :key="provider.id"
                :value="provider.id"
                :label="provider.name"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <el-alert
          v-if="!invited && !providers.length && !error"
          title="尚未配置企业登录，请联系管理员"
          type="info"
          :closable="false"
        />
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="invited ? !invitationReady : !selected"
          @click="start"
          >{{ invited ? '验证身份并接受邀请' : '使用企业账号登录' }}</el-button
        >
        <el-button v-if="!invited" :disabled="submitting" @click="loadProviders"
          >重新读取</el-button
        >
      </template>
      <template v-else-if="error">
        <p>本次回调不能重复使用。请重新发起企业登录；首次邀请验证失败时，请重新打开邀请链接。</p>
        <el-button type="primary" @click="router.replace('/orbit-login')">重新发起登录</el-button>
      </template>
      <p class="auth-native-link"><router-link to="/login">使用原账号密码登录</router-link></p>
    </el-card>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  finishEnterpriseLogin,
  loginProviders,
  safeReturnTo,
  startEnterpriseLogin,
  type LoginProvider,
} from '@/api/orbit/authentication'
import { takeAuthEntry } from '@/api/orbit/auth-entry'
import { removeToken } from '@/utils/auth'
import useUserStore from '@/store/modules/user'

const route = useRoute(),
  router = useRouter()
const callback = computed(() => route.path === '/auth/callback'),
  invited = computed(() => route.path === '/invite')
const providers = ref<LoginProvider[]>([]),
  selected = ref(''),
  error = ref(''),
  loading = ref(false),
  submitting = ref(false),
  invitationReady = ref(false)
let invitation: string | undefined,
  generation = 0
async function loadProviders() {
  const sequence = ++generation
  loading.value = true
  error.value = ''
  providers.value = []
  selected.value = ''
  try {
    const result = await loginProviders()
    if (sequence !== generation) return
    providers.value = result
    if (result.length === 1) selected.value = result[0].id
  } catch (cause) {
    if (sequence === generation)
      error.value = cause instanceof Error ? cause.message : '登录提供者读取失败'
  } finally {
    if (sequence === generation) loading.value = false
  }
}
async function start() {
  if (submitting.value || (invited.value ? !invitation : !selected.value)) return
  const sequence = generation
  submitting.value = true
  error.value = ''
  try {
    const url = await startEnterpriseLogin(
      invited.value ? '/index' : safeReturnTo(route.query.redirect),
      selected.value || undefined,
      invitation,
    )
    // 用户离开或切换入口后，不允许迟到的授权响应把浏览器带离当前页面。
    if (sequence !== generation) return
    invitation = undefined
    invitationReady.value = false
    window.location.assign(url)
  } catch (cause) {
    if (sequence !== generation) return
    error.value = cause instanceof Error ? cause.message : '登录发起失败，请重试'
    submitting.value = false
  }
}
watch(
  () => route.path,
  async () => {
    const sequence = ++generation
    error.value = ''
    loading.value = false
    submitting.value = false
    invitation = undefined
    invitationReady.value = false
    const entry = takeAuthEntry()
    if (invited.value) {
      invitation = entry?.invitation
      invitationReady.value = Boolean(invitation)
      if (!invitation) error.value = '邀请凭据缺失或格式无效，请重新打开管理员发送的完整链接'
      return
    }
    if (!callback.value) {
      await loadProviders()
      return
    }
    loading.value = true
    try {
      if (!entry?.callback) throw new Error('登录回调参数缺失，请重新发起登录')
      const destination = await finishEnterpriseLogin(entry.callback)
      if (sequence !== generation) return
      // 仅Cookie验证成功后清理旧账号，不能制造假JWT来绕过原路由守卫。
      removeToken()
      const user = useUserStore()
      user.token = ''
      user.roles = []
      user.permissions = []
      await router.replace(destination)
    } catch (cause) {
      if (sequence === generation)
        error.value = cause instanceof Error ? cause.message : '登录验证失败，请重新发起登录'
    } finally {
      if (sequence === generation) loading.value = false
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  generation++
  invitation = undefined
})
</script>

<style scoped>
.orbit-auth-page {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  background: var(--el-fill-color-light);
}
.orbit-auth-panel {
  width: min(440px, 100%);
}
.orbit-auth-panel h2 {
  margin: 0 0 24px;
}
.orbit-auth-panel .el-alert {
  margin-bottom: 16px;
}
.provider-select {
  width: 100%;
}
.auth-native-link {
  margin-top: 24px;
}
.auth-native-link a {
  color: var(--el-color-primary);
}
</style>
