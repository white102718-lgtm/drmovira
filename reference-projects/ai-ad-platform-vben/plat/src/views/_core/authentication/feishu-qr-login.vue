<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue';

import Spin from 'ant-design-vue/es/spin';
import Button from 'ant-design-vue/es/button';

import {
  initializeFeishuBindApi,
  initializeFeishuLoginApi,
} from '#/api/core/auth';

import { appendFeishuTmpCode } from './feishu-qr-sdk';

interface FeishuQrLoginInstance {
  matchData: (data: unknown) => boolean;
  matchOrigin: (origin: string) => boolean;
}

interface FeishuQrLoginOptions {
  goto: string;
  height?: string;
  id: string;
  style?: string;
  width?: string;
}

declare global {
  interface Window {
    QRLogin?: (options: FeishuQrLoginOptions) => FeishuQrLoginInstance;
  }
}

const FEISHU_QR_SDK_URL =
  'https://lf-package-cn.feishucdn.com/obj/feishu-static/lark/passport/qrcode/LarkSSOSDKWebQRCode-1.0.3.js';

const props = withDefaults(
  defineProps<{
    purpose?: 'bind' | 'login';
  }>(),
  { purpose: 'login' },
);

let sdkPromise: null | Promise<void> = null;
let containerSequence = 0;

const containerId = `feishu-login-container-${++containerSequence}`;
const loading = ref(false);
const errorMessage = ref('');
const authorizeUrl = ref('');
let qrLoginInstance: FeishuQrLoginInstance | null = null;

function loadFeishuQrSdk() {
  if (window.QRLogin) return Promise.resolve();
  if (sdkPromise) return sdkPromise;

  sdkPromise = new Promise<void>((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>(
      `script[src="${FEISHU_QR_SDK_URL}"]`,
    );
    const script = existingScript ?? document.createElement('script');
    const handleLoad = () => {
      window.QRLogin
        ? resolve()
        : reject(new Error('飞书二维码 SDK 加载不完整'));
    };
    const handleError = () => reject(new Error('飞书二维码 SDK 加载失败'));

    script.addEventListener('load', handleLoad, { once: true });
    script.addEventListener('error', handleError, { once: true });
    if (!existingScript) {
      script.src = FEISHU_QR_SDK_URL;
      script.async = true;
      document.head.append(script);
    }
  }).catch((error) => {
    sdkPromise = null;
    throw error;
  });
  return sdkPromise;
}

function handleSdkMessage(event: MessageEvent) {
  if (
    !qrLoginInstance?.matchOrigin(event.origin) ||
    !qrLoginInstance.matchData(event.data)
  ) {
    return;
  }
  const data = event.data as { tmp_code?: unknown };
  if (typeof data.tmp_code !== 'string' || !data.tmp_code) return;

  const gotoUrl = document
    .getElementById(containerId)
    ?.getAttribute('data-goto-url');
  if (!gotoUrl) return;
  window.location.assign(appendFeishuTmpCode(gotoUrl, data.tmp_code));
}

/** 初始化一次新的飞书扫码会话；重试时会生成新的 state。 */
async function initializeQrCode() {
  loading.value = true;
  errorMessage.value = '';
  authorizeUrl.value = '';
  qrLoginInstance = null;
  const container = document.getElementById(containerId);
  if (container) container.replaceChildren();

  try {
    const { gotoUrl } = await (props.purpose === 'bind'
      ? initializeFeishuBindApi()
      : initializeFeishuLoginApi());
    authorizeUrl.value = gotoUrl;
    await loadFeishuQrSdk();
    await nextTick();
    const currentContainer = document.getElementById(containerId);
    if (!currentContainer || !window.QRLogin) return;
    currentContainer.setAttribute('data-goto-url', gotoUrl);
    qrLoginInstance = window.QRLogin({
      goto: gotoUrl,
      height: '300',
      id: containerId,
      style: 'width:100%;height:300px',
      width: '320',
    });
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '飞书二维码初始化失败';
  } finally {
    loading.value = false;
  }
}

/** 使用后端生成的一次性地址跳转到飞书网页授权。 */
function handleWebAuthorization() {
  if (!authorizeUrl.value) return;
  window.location.assign(authorizeUrl.value);
}

onMounted(() => {
  window.addEventListener('message', handleSdkMessage, false);
  void initializeQrCode();
});

onUnmounted(() => {
  window.removeEventListener('message', handleSdkMessage, false);
  qrLoginInstance = null;
  document.getElementById(containerId)?.replaceChildren();
});
</script>

<template>
  <div class="feishu-qr-panel" aria-live="polite">
    <div v-if="errorMessage" class="py-12 text-center">
      <p class="mb-4 text-sm text-red-500">{{ errorMessage }}</p>
      <Button @click="initializeQrCode">重新加载</Button>
    </div>
    <Spin v-else :spinning="loading" tip="正在加载飞书二维码…">
      <div :id="containerId" class="feishu-qr-container"></div>
    </Spin>
    <p class="mb-0 mt-2 text-center text-sm text-slate-500">
      {{
        purpose === 'bind'
          ? '请使用飞书手机客户端扫码绑定，时报会发到你的飞书私聊'
          : '请使用飞书手机客户端扫码并确认登录'
      }}
    </p>
    <template v-if="purpose === 'login' && authorizeUrl">
      <div class="my-5 flex items-center gap-3" aria-hidden="true">
        <span class="bg-border h-px flex-1"></span>
        <span class="text-muted-foreground text-xs">或</span>
        <span class="bg-border h-px flex-1"></span>
      </div>
      <Button type="primary" block @click="handleWebAuthorization">
        飞书授权登录
      </Button>
      <p class="text-muted-foreground mb-0 mt-2 text-center text-xs leading-5">
        当前浏览器已登录飞书时，可直接跳转授权并返回系统
      </p>
    </template>
  </div>
</template>

<style scoped>
.feishu-qr-panel {
  min-height: 340px;
}

.feishu-qr-container {
  display: flex;
  min-height: 300px;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
</style>
