<script lang="ts" setup>
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccessStore } from '@vben/stores';
import { LoaderCircle } from 'lucide-vue-next';

import { bindFeishuApi } from '#/api/core/auth';
import { ApiBusinessError } from '#/api/backend-response';
import Button from 'ant-design-vue/es/button';
import { useAuthStore } from '#/store';

defineOptions({ name: 'FeishuOAuthCallback' });

const BIND_RETURN_KEY = 'adpulse-agent-bind-return';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const accessStore = useAccessStore();

const processing = ref(true);
const errorMessage = ref('');
const bindAttempt = ref(false);
let callbackStarted = false;

function readQueryValue(value: unknown) {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function clearSensitiveQuery() {
  window.history.replaceState(window.history.state, '', route.path);
}

/** 网页授权失败时把历史扫码提示转换为当前可执行的操作。 */
function resolveLoginErrorMessage(error: unknown, isBind: boolean) {
  if (error instanceof ApiBusinessError) {
    return isBind
      ? error.message
      : error.message.replaceAll('重新扫码', '重新发起授权');
  }
  return isBind ? '飞书绑定失败，请重新扫码' : '飞书登录失败，请重新发起授权';
}

async function completeFeishuLogin() {
  if (callbackStarted) return;
  callbackStarted = true;

  const oauthError = readQueryValue(route.query.error);
  const oauthErrorDescription = readQueryValue(route.query.error_description);
  const code = readQueryValue(route.query.code);
  const state = readQueryValue(route.query.state);
  clearSensitiveQuery();

  if (oauthError) {
    errorMessage.value =
      oauthErrorDescription ?? '飞书授权未完成，请重新发起授权';
    processing.value = false;
    return;
  }

  if (!code || !state) {
    errorMessage.value = '飞书回调参数不完整，请重新发起授权';
    processing.value = false;
    return;
  }

  const isBind = Boolean(accessStore.accessToken);
  bindAttempt.value = isBind;

  try {
    if (isBind) {
      await bindFeishuApi({ code, state });
      await authStore.fetchUserInfo();
      const next = sessionStorage.getItem(BIND_RETURN_KEY) || '/home/ai-chat';
      sessionStorage.removeItem(BIND_RETURN_KEY);
      await router.replace(next);
      return;
    }
    await authStore.authFeishuLogin({ code, state });
  } catch (error: unknown) {
    errorMessage.value = resolveLoginErrorMessage(error, isBind);
    processing.value = false;
  }
}

function retryFeishuLogin() {
  if (bindAttempt.value) {
    void router.replace('/home/ai-chat');
    return;
  }
  void router.replace({
    path: '/auth/login',
    query: { loginMethod: 'feishu' },
  });
}

function returnToPhoneLogin() {
  if (bindAttempt.value) {
    void router.replace('/home/ai-chat');
    return;
  }
  void router.replace('/auth/login');
}

onMounted(() => {
  void completeFeishuLogin();
});
</script>

<template>
  <section class="feishu-callback" aria-labelledby="feishu-callback-title">
    <h1
      id="feishu-callback-title"
      class="auth-form-title m-0 font-semibold tracking-tight text-slate-800"
    >
      {{
        processing
          ? bindAttempt
            ? '正在绑定飞书'
            : '正在完成飞书登录'
          : bindAttempt
            ? '飞书绑定未完成'
            : '飞书登录未完成'
      }}
    </h1>

    <div
      v-if="processing"
      class="callback-status"
      role="status"
      aria-live="polite"
    >
      <LoaderCircle
        aria-hidden="true"
        class="size-8 animate-spin motion-reduce:animate-none"
      />
      <p class="mb-0 mt-5 text-sm leading-6 text-slate-500">
        正在验证飞书身份{{
          bindAttempt ? '并绑定到当前账号' : '并进入系统'
        }}，请稍候…
      </p>
    </div>

    <div v-else class="callback-error" role="alert">
      <div class="error-icon" aria-hidden="true">!</div>
      <p class="mb-0 text-sm leading-6 text-slate-600">
        {{ errorMessage }}
      </p>
      <p class="mb-0 mt-2 text-xs leading-5 text-slate-400">
        {{
          bindAttempt
            ? '授权码只能使用一次，请重新生成二维码后再试。'
            : '授权码只能使用一次，请返回登录页重新发起飞书授权。'
        }}
      </p>
      <div class="mt-6 flex flex-col gap-3">
        <Button type="primary" block @click="retryFeishuLogin">
          {{ bindAttempt ? '返回智能体' : '重新登录' }}
        </Button>
        <Button v-if="!bindAttempt" block @click="returnToPhoneLogin">
          返回手机登录
        </Button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.feishu-callback {
  width: 100%;
  max-width: 320px;
  margin-inline: auto;
  text-align: center;
}

.callback-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
}

.callback-error {
  margin-top: var(--adpulse-section-gap);
}

.error-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin: 0 auto var(--adpulse-section-gap);
  font-size: 20px;
  font-weight: 600;
  color: #dc2626;
  background: #fef2f2;
  border-radius: 50%;
}
</style>
