<script lang="ts" setup>
import type { VbenFormSchema } from '@vben/common-ui';
import type { Recordable } from '@vben/types';

import type { DemoRoleProfile } from '#/mock/demo-role-preview';

import { computed, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { AuthenticationLogin, z } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { $t } from '@vben/locales';
import { useAccessStore, useUserStore } from '@vben/stores';

import { useClipboard } from '@vueuse/core';
import { useQRCode } from '@vueuse/integrations/useQRCode';
import Input from 'ant-design-vue/es/input';
import message from 'ant-design-vue/es/message';
import Segmented from 'ant-design-vue/es/segmented';
import Tag from 'ant-design-vue/es/tag';

import { ApiBusinessError } from '#/api/backend-response';
import { isFusionDemoMode } from '#/api/fusion/mode';
import { getDemoAccessCodes } from '#/mock/demo-access';
import {
  demoRoleProfiles,
  getDemoRoleAccessToken,
  readSelectedDemoRole,
  selectDemoRole,
  toDemoRoleUserInfo,
} from '#/mock/demo-role-preview';
import { resetRoutes } from '#/router';
import { useAuthStore } from '#/store';
import PhoneNumberInput from '#/views/system/user/modules/phone-number-input.vue';

import FeishuQrLogin from './feishu-qr-login.vue';

defineOptions({ name: 'Login' });

const authStore = useAuthStore();
const accessStore = useAccessStore();
const userStore = useUserStore();
const route = useRoute();
const router = useRouter();
const { copy: copyToClipboard } = useClipboard({ legacy: true });

const isDemoRoleSelectorVisible = isFusionDemoMode();
const selectedDemoRoleId = ref(readSelectedDemoRole()?.id);

const mfaCode = ref('');
const mfaLoading = ref(false);
const qrUri = ref('');
const secretKey = ref('');
type LoginMethod = 'feishu' | 'phone';
const activeLoginMethod = ref<LoginMethod>(
  route.query.loginMethod === 'feishu' ? 'feishu' : 'phone',
);
const loginMethodOptions = [
  { label: '手机登录', value: 'phone' },
  { label: '飞书登录', value: 'feishu' },
];

type AppType = 'app' | 'miniprogram' | 'plugin';
const activeAppType = ref<AppType>('plugin');

interface AppItem {
  link?: {
    href: string;
    label: string;
  };
  name: string;
  usage: string;
}

const appTypes: { apps: AppItem[]; label: string; value: AppType }[] = [
  {
    value: 'plugin',
    label: '浏览器插件',
    apps: [
      {
        name: 'Authenticator',
        link: {
          href: 'https://chromewebstore.google.com/detail/authenticator/bhghoamapcdpbohphigoooaddinpkbai',
          label: 'authenticator',
        },
        usage:
          '打开页面 → 添加扩展 → 点击浏览器工具栏的身份验证器图标 → 点击扫码图标，扫描下方二维码即可完成绑定',
      },
    ],
  },
  {
    value: 'app',
    label: 'App',
    apps: [
      {
        name: 'Microsoft Authenticator（iOS / Android，全地区可用）',
        usage:
          '在 App Store 或 Google Play 搜索「Microsoft Authenticator」→ 安装打开 → 点击右上角「+」→ 选择「其他账户」→ 扫描下方二维码完成绑定',
      },
      {
        name: 'Duo Mobile',
        usage:
          '在 App Store 或 Google Play 搜索「Duo Mobile」→ 安装打开 → 点击「+」→ 选择「Use QR code」→ 扫描下方二维码绑定',
      },
    ],
  },
  {
    value: 'miniprogram',
    label: '小程序',
    apps: [
      {
        name: '二次验证码',
        usage:
          '搜索微信小程序「二次验证码」→ 进入后点击「+」→ 选择「扫码添加」，扫描下方二维码即可完成绑定',
      },
      {
        name: '2FA 动态验证器',
        usage:
          '搜索微信小程序「2FA动态验证器」→ 进入后点击「添加账户」→ 选择「扫描二维码」，扫描下方二维码完成绑定',
      },
    ],
  },
];

const currentApps = computed(
  () => appTypes.find((t) => t.value === activeAppType.value)?.apps ?? [],
);

const setupCountdownDisplay = computed(() => {
  const m = Math.floor(setupCountdown.value / 60)
    .toString()
    .padStart(2, '0');
  const s = (setupCountdown.value % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
});

const setupCountdown = ref(300);
let setupCountdownTimer: null | ReturnType<typeof setInterval> = null;

function clearSetupCountdown() {
  if (setupCountdownTimer !== null) {
    clearInterval(setupCountdownTimer);
    setupCountdownTimer = null;
  }
}

/**
 * 启动MFA挑战倒计时
 * @param seconds 后端返回的 challengeExpiresInSeconds
 */
function startSetupCountdown(seconds?: number) {
  clearSetupCountdown();
  // 优先使用后端返回的秒数，默认 300 秒(5分钟)
  setupCountdown.value =
    (seconds ?? authStore.challengeExpiresInSeconds) || 300;
  setupCountdownTimer = setInterval(() => {
    setupCountdown.value--;
    if (setupCountdown.value <= 0) {
      clearSetupCountdown();
      authStore.resetMfaState();
      message.warning('认证挑战已过期，请重新登录');
    }
  }, 1000);
}

const qrcode = useQRCode(qrUri, { errorCorrectionLevel: 'H', margin: 4 });

const formSchema = computed((): VbenFormSchema[] => {
  return [
    {
      component: PhoneNumberInput,
      componentProps: { controlSize: 'large', countryCodeMode: 'input' },
      defaultValue: '+86',
      fieldName: 'phone',
      label: '手机号',
      modelPropName: 'value',
      rules: z
        .string()
        .min(1, { message: '请输入手机号' })
        .regex(/^(?:1[3-9]\d{9}|\+[1-9]\d{7,14})$/, '请输入正确的手机号'),
    },
    {
      component: 'VbenInputPassword',
      componentProps: {
        placeholder: $t('authentication.password'),
      },
      fieldName: 'password',
      label: $t('authentication.password'),
      rules: z.string().min(1, { message: $t('authentication.passwordTip') }),
    },
  ];
});

async function onSubmit(params: Recordable<any>) {
  try {
    await authStore.authLogin(params);
  } catch (error: any) {
    // 全局拦截器对 4xx 静默（登录/MFA 流程错误），由页面展示后端消息。
    // 5xx/6xx 已由全局拦截器展示，这里不重复弹窗。
    if (error instanceof ApiBusinessError && error.silent) {
      message.error(error.message);
    }
  }
}

function resolveDemoRedirect(profile: DemoRoleProfile) {
  const redirect = route.query.redirect;
  if (
    typeof redirect === 'string' &&
    redirect.startsWith('/') &&
    !redirect.startsWith('//')
  ) {
    return redirect;
  }
  return profile.homePath;
}

async function enterDemoRole(profile: DemoRoleProfile) {
  selectedDemoRoleId.value = profile.id;
  selectDemoRole(profile.id);
  // A Demo role switch is a real front-end access boundary.  Remove prior
  // dynamic routes and cached menu facts before generating the new role tree.
  resetRoutes();
  accessStore.setAccessMenus([]);
  accessStore.setAccessRoutes([]);
  accessStore.setAccessToken(getDemoRoleAccessToken(profile));
  accessStore.setAccessCodes(getDemoAccessCodes(profile.id));
  accessStore.setIsAccessChecked(false);
  userStore.setUserInfo(toDemoRoleUserInfo(profile));
  await router.replace(resolveDemoRedirect(profile));
}

async function copySecret() {
  try {
    // 测试环境使用 HTTP，Clipboard API 受安全上下文限制时需回退到传统复制方式。
    await copyToClipboard(secretKey.value);
    message.success('密钥已复制');
  } catch {
    message.error('复制失败，请手动选择并复制密钥');
  }
}

/**
 * 监听 mfaStep 变化：
 * - setup(待绑定)：直接从 authStore 取 otpAuthUri 和 mfaSecret，不再调用后端 /auth/mfa/init
 * - verify(待验证)：只显示动态码输入，不显示密钥
 * - none：清理二维码和密钥
 */
watch(
  () => authStore.mfaStep,
  (step) => {
    if (step === 'setup') {
      // 直接使用登录响应中已返回的 otpAuthUri/mfaSecret
      qrUri.value = authStore.otpAuthUri;
      secretKey.value = authStore.mfaSecret;
      startSetupCountdown(authStore.challengeExpiresInSeconds);
    } else if (step === 'verify') {
      // 已绑定用户只需要输入动态码，不需要二维码和密钥
      qrUri.value = '';
      secretKey.value = '';
      startSetupCountdown(authStore.challengeExpiresInSeconds);
    } else {
      clearSetupCountdown();
      qrUri.value = '';
      secretKey.value = '';
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  clearSetupCountdown();
});

async function handleMfaSubmit(action: (code: string) => Promise<unknown>) {
  if (!mfaCode.value) return;
  // 必须是6位纯数字
  if (!/^\d{6}$/.test(mfaCode.value)) {
    message.warning('请输入6位数字动态码');
    return;
  }
  mfaLoading.value = true;
  try {
    await action(mfaCode.value);
    mfaCode.value = '';
  } catch (error: any) {
    // 4xx 静默错误（410/411/412/414 已在 store 中重置挑战）：
    // - 413 动态码错误：清空输入框，停留 MFA 页面允许重试
    // - 4xx 其他：展示后端消息，由页面提示
    // 5xx/6xx 已由全局拦截器展示，这里不重复弹窗。
    if (error instanceof ApiBusinessError && error.silent) {
      message.error(error.message);
      if (error.code === 413) {
        mfaCode.value = '';
      }
    }
  } finally {
    mfaLoading.value = false;
  }
}
</script>

<template>
  <div
    v-if="authStore.mfaStep === 'verify'"
    @keydown.enter.prevent="handleMfaSubmit(authStore.authMfaVerify)"
  >
    <div class="mb-7 sm:mx-auto sm:w-full sm:max-w-md">
      <h2 class="auth-form-title text-foreground mb-3 font-bold tracking-tight">
        两步验证
      </h2>
      <p
        v-if="setupCountdown > 0"
        class="flex items-center gap-1 text-sm font-medium tabular-nums"
        :class="setupCountdown <= 60 ? 'text-red-500' : 'text-muted-foreground'"
      >
        <IconifyIcon icon="lucide:clock" class="shrink-0 text-base" />
        <span>请在 {{ setupCountdownDisplay }} 内完成验证</span>
      </p>
    </div>
    <div class="mb-4">
      <label class="text-foreground mb-2 block text-sm font-medium">
        验证码 <span class="text-destructive">*</span>
      </label>
      <Input
        v-model:value="mfaCode"
        class="w-full"
        :maxlength="6"
        inputmode="numeric"
        pattern="\d*"
        placeholder="请输入 6 位数字动态码"
      />
    </div>
    <button
      :disabled="mfaLoading || !/^\d{6}$/.test(mfaCode)"
      class="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-6 py-2 text-sm font-medium transition-colors disabled:opacity-50"
      @click="handleMfaSubmit(authStore.authMfaVerify)"
    >
      验证
    </button>
  </div>

  <div
    v-else-if="authStore.mfaStep === 'setup'"
    @keydown.enter.prevent="handleMfaSubmit(authStore.authMfaBind)"
  >
    <div class="mb-5">
      <h2 class="auth-form-title text-foreground mb-1 font-bold tracking-tight">
        身份验证器应用
      </h2>
      <p class="text-muted-foreground mb-2 text-sm">
        虚拟 MFA 设备是运行在您设备上的应用程序，您可以通过扫描二维码进行配置。
      </p>
      <p
        class="flex items-center gap-1 text-sm font-medium tabular-nums"
        :class="setupCountdown <= 60 ? 'text-red-500' : 'text-muted-foreground'"
      >
        <IconifyIcon icon="lucide:clock" class="shrink-0 text-base" />
        <span>请在 {{ setupCountdownDisplay }} 内完成绑定</span>
      </p>
    </div>

    <div class="mb-4 flex gap-3">
      <div
        class="bg-primary text-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold"
      >
        1
      </div>
      <div class="text-foreground text-sm leading-6">
        <div class="mb-2 flex items-center gap-2">
          <span class="font-medium">认证工具类型：</span>
        </div>

        <div class="mb-3 flex w-fit gap-1 rounded-md bg-gray-100 p-0.5">
          <button
            v-for="tab in appTypes"
            :key="tab.value"
            class="rounded px-3 py-1 text-xs font-medium transition-all duration-150"
            :class="
              activeAppType === tab.value
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            "
            @click="activeAppType = tab.value"
          >
            {{ tab.label }}
          </button>
        </div>

        <ul class="list-disc space-y-2 pl-4">
          <li
            class="font-medium text-gray-700"
            v-for="app in currentApps"
            :key="app.name"
          >
            {{ app.name }}：
            <a
              v-if="app.link"
              :href="app.link.href"
              class="ml-1 text-[13px] font-normal text-blue-600 underline hover:text-blue-700"
              rel="noopener noreferrer"
              target="_blank"
            >
              {{ app.link.label }}
            </a>
            <span class="ml-1 text-[13px] font-normal text-gray-600">{{
              app.usage
            }}</span>
          </li>
        </ul>
      </div>
    </div>

    <div class="mb-5 flex gap-3">
      <div
        class="bg-primary text-primary-foreground flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold"
      >
        2
      </div>
      <div class="flex-1">
        <p class="text-foreground mb-2 text-sm leading-6">
          扫描下方二维码，或复制密钥手动输入到验证工具完成绑定。
        </p>
        <div
          class="border-border mb-2 flex h-44 w-44 items-center justify-center overflow-hidden rounded border"
        >
          <img v-if="qrcode" :src="qrcode" alt="二维码" class="h-full w-full" />
        </div>
        <div v-if="secretKey" class="flex items-center gap-2">
          <span class="text-muted-foreground text-xs">密钥：</span>
          <code class="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{{
            secretKey
          }}</code>
          <button
            class="text-primary hover:text-primary/80 text-xs transition-colors"
            @click="copySecret"
          >
            复制
          </button>
        </div>
      </div>
    </div>

    <div class="mb-4">
      <label class="text-foreground mb-2 block text-sm font-medium">
        验证码 <span class="text-destructive">*</span>
      </label>
      <Input
        v-model:value="mfaCode"
        class="w-full text-sm"
        :maxlength="6"
        inputmode="numeric"
        pattern="\d*"
        placeholder="请输入认证工具中显示的 6 位数字动态码"
      />
    </div>
    <button
      :disabled="mfaLoading || !/^\d{6}$/.test(mfaCode)"
      class="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-6 py-2 text-sm font-medium transition-colors disabled:opacity-50"
      @click="handleMfaSubmit(authStore.authMfaBind)"
    >
      验证并绑定
    </button>
  </div>

  <section
    v-else-if="isDemoRoleSelectorVisible"
    class="demo-role-selector w-full max-w-md"
    aria-labelledby="demo-role-selector-title"
  >
    <div class="mb-6 text-center">
      <Tag color="blue" class="mb-3">本地 Demo 角色视图</Tag>
      <h1
        id="demo-role-selector-title"
        class="text-foreground m-0 text-2xl font-semibold tracking-tight"
      >
        选择要查看的业务角色
      </h1>
      <p
        class="text-muted-foreground mx-auto mb-0 mt-2 max-w-xl text-sm leading-6"
      >
        每个角色使用独立的模拟身份、首页指标、待办和快捷入口。仅用于演示业务链路，不代表生产权限或数据范围。
      </p>
    </div>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <button
        v-for="profile in demoRoleProfiles"
        :key="profile.id"
        type="button"
        class="group flex min-h-32 w-full cursor-pointer flex-col rounded-xl border bg-white p-4 text-left transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        :class="
          selectedDemoRoleId === profile.id
            ? 'border-blue-500 ring-1 ring-blue-200'
            : 'border-slate-200 hover:border-blue-300 hover:shadow-sm'
        "
        :aria-pressed="selectedDemoRoleId === profile.id"
        @click="enterDemoRole(profile)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex min-w-0 items-center gap-2">
            <div
              class="flex size-9 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600 transition-colors group-hover:bg-blue-100"
            >
              <IconifyIcon icon="lucide:users-round" class="text-lg" />
            </div>
            <div class="min-w-0">
              <div class="truncate text-sm font-semibold text-slate-900">
                {{ profile.label }}
              </div>
              <div class="mt-0.5 truncate text-xs text-slate-500">
                {{ profile.realName }} · {{ profile.department }}
              </div>
            </div>
          </div>
          <IconifyIcon
            icon="lucide:arrow-right"
            class="mt-1 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-blue-600"
          />
        </div>

        <p class="mb-0 mt-3 line-clamp-2 text-xs leading-5 text-slate-600">
          {{ profile.summary }}
        </p>
        <div class="mt-auto pt-3 text-xs font-medium text-blue-600">
          点击进入该角色视图
        </div>
      </button>
    </div>
  </section>

  <template v-else>
    <AuthenticationLogin
      v-if="activeLoginMethod === 'phone'"
      class="login-form"
      :form-schema="formSchema"
      :loading="authStore.loginLoading"
      :show-code-login="false"
      :show-qrcode-login="false"
      :show-register="false"
      :show-third-party-login="false"
      @submit="onSubmit"
    >
      <template #title>
        <div class="mb-6 text-center">
          <div class="login-kicker mb-3">ADPULSE WORKSPACE</div>
          <h1
            class="auth-form-title m-0 font-semibold tracking-tight text-slate-950"
          >
            欢迎回来
          </h1>
          <p class="mb-0 mt-3 text-sm leading-6 text-slate-500">
            登录以继续管理您的广告业务
          </p>
          <Segmented
            v-model:value="activeLoginMethod"
            :options="loginMethodOptions"
            block
            class="login-method-tabs mt-5 w-full"
          />
        </div>
      </template>
    </AuthenticationLogin>

    <section v-else class="login-form" aria-label="飞书登录">
      <div class="mb-6 text-center">
        <h1
          class="auth-form-title m-0 font-semibold tracking-tight text-slate-950"
        >
          欢迎回来
        </h1>
        <p class="mb-0 mt-3 text-sm leading-6 text-slate-500">
          登录以继续管理您的广告业务
        </p>
        <Segmented
          v-model:value="activeLoginMethod"
          :options="loginMethodOptions"
          block
          class="login-method-tabs mt-5 w-full"
        />
      </div>

      <FeishuQrLogin />
    </section>
  </template>
</template>

<style scoped>
.login-kicker {
  font-size: 11px;
  font-weight: 700;
  color: #2563eb;
  letter-spacing: 0.18em;
}

.login-form {
  width: 100%;
  max-width: 320px;
  margin-inline: auto;
}

.login-form :deep(input:not(:disabled)) {
  font-size: 14px;
  background: hsl(var(--card));
}

.login-form :deep(input:not(:disabled):-webkit-autofill),
.login-form :deep(input:not(:disabled):-webkit-autofill:hover),
.login-form :deep(input:not(:disabled):-webkit-autofill:focus) {
  background: hsl(var(--card)) !important;
  box-shadow: inset 0 0 0 1000px hsl(var(--card)) !important;
}

:deep(.login-form button) {
  min-height: 40px;
  font-weight: 600;
  box-shadow: none;
}

:deep(.login-form [data-slot='form-item']) {
  margin-bottom: 16px;
}

.login-method-tabs {
  width: 100%;
  padding: 3px;
  background: hsl(var(--muted) / 55%);
  border-color: var(--adpulse-border);
  border-radius: 10px;
}

.demo-role-selector {
  max-height: min(65vh, 560px);
  overflow-y: auto;
  scrollbar-width: thin;
}

@media (max-width: 640px) {
  .demo-role-selector {
    max-height: 62vh;
  }
}
</style>
