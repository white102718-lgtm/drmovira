/**
 * 该文件可自行根据业务逻辑进行调整
 */
import type { AxiosResponseHeaders, RequestClientOptions } from '@vben/request';

import { LOGIN_PATH } from '@vben/constants';
import { useAppConfig } from '@vben/hooks';
import { preferences } from '@vben/preferences';
import {
  authenticateResponseInterceptor,
  defaultResponseInterceptor,
  errorMessageResponseInterceptor,
  RequestClient,
} from '@vben/request';
import { useAccessStore } from '@vben/stores';
import { cloneDeep } from '@vben/utils';

import { message } from 'ant-design-vue';
import JSONBigInt from 'json-bigint';

import {
  ApiBusinessError,
  resolveBackendHttpResponse,
} from './backend-response';
import { refreshTokenApi } from './core';
import { isDemoMockEnabled, resolveDemoMock } from './demo-mock';

const { apiURL, backendURL, otherURL, adpulseURL } = useAppConfig(
  import.meta.env,
  import.meta.env.PROD,
);

// 多个请求同时 401 时,只跑一次倒计时跳转
let reauthStarted = false;

function createRequestClient(
  baseURL: string,
  options?: RequestClientOptions,
  responseKind: 'backend' | 'default' = 'default',
  authenticated = true,
) {
  const client = new RequestClient({
    ...options,
    baseURL,
    transformResponse: (data: any, header: AxiosResponseHeaders) => {
      // storeAsString指示将BigInt存储为字符串，设为false则会存储为内置的BigInt类型
      return header.getContentType()?.toString().includes('application/json')
        ? cloneDeep(
            JSONBigInt({ storeAsString: true, strict: true }).parse(data),
          )
        : data;
    },
  });

  /**
   * 重新认证逻辑
   */
  async function doReAuthenticate() {
    console.warn('Access token or refresh token is invalid or expired. ');
    const accessStore = useAccessStore();
    accessStore.setAccessToken(null);
    if (
      preferences.app.loginExpiredMode === 'modal' &&
      accessStore.isAccessChecked
    ) {
      accessStore.setLoginExpired(true);
      return;
    }
    if (reauthStarted) return;
    reauthStarted = true;
    // 弹一个带倒计时的提示，2 秒后只跳当前前端的本地登录页。
    let seconds = 2;
    message.error({
      content: `登录已失效,${seconds}秒后重新登录`,
      key: 'reauth',
      duration: 0,
    });
    const timer = setInterval(() => {
      seconds -= 1;
      if (seconds <= 0) {
        clearInterval(timer);
        const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const redirect = encodeURIComponent(currentPath);
        window.location.replace(`${LOGIN_PATH}?redirect=${redirect}`);
        return;
      }
      message.error({
        content: `登录已失效,${seconds}秒后重新登录`,
        key: 'reauth',
        duration: 0,
      });
    }, 1000);
  }

  /**
   * 刷新token逻辑
   */
  async function doRefreshToken() {
    const accessStore = useAccessStore();
    const resp = await refreshTokenApi();
    const newToken = resp.data;
    accessStore.setAccessToken(newToken);
    return newToken;
  }

  function formatToken(token: null | string) {
    return token ? `Bearer ${token}` : null;
  }

  // 请求头处理
  client.addRequestInterceptor({
    fulfilled: async (config) => {
      const accessStore = useAccessStore();

      const demoMock = resolveDemoMock({
        baseURL: config.baseURL,
        data: config.data,
        method: config.method,
        params: config.params,
        url: config.url,
      });
      if (demoMock.matched) {
        config.adapter = async () => {
          await new Promise((resolve) => window.setTimeout(resolve, 120));
          const data = cloneDeep(demoMock.data);
          return {
            config,
            data: { code: 0, data, message: '演示数据' },
            headers: { 'content-type': 'application/x-demo-mock' },
            status: 200,
            statusText: 'OK',
          } as any;
        };
      }

      // 只有 authenticated=true 的客户端才附加 Authorization 头
      if (authenticated) {
        config.headers.Authorization = formatToken(accessStore.accessToken);
      }
      config.headers['Accept-Language'] = preferences.app.locale;
      return config;
    },
  });

  if (responseKind === 'backend') {
    // AdPulse System Server：HTTP 恒为 200，必须读取业务 code。
    // 在 defaultResponseInterceptor 之前校验业务码：
    // - code=200：原样透传，由 defaultResponseInterceptor 按 responseReturn='data' 解包
    // - 业务失败：抛出 ApiBusinessError，由错误拦截器按 silent/code 处理
    client.addResponseInterceptor({
      fulfilled: (response) => resolveBackendHttpResponse(response as any),
    });
  }

  // 处理返回的响应数据格式
  client.addResponseInterceptor(
    defaultResponseInterceptor({
      codeField: 'code',
      dataField: 'data',
      successCode: (code: any) => code === 0 || code === 200,
    }),
  );

  // 只有 authenticated=true 的客户端才注册 token 刷新和 401 重新认证
  if (authenticated && !isDemoMockEnabled) {
    // token过期的处理
    client.addResponseInterceptor(
      authenticateResponseInterceptor({
        client,
        doReAuthenticate,
        doRefreshToken,
        enableRefreshToken: preferences.app.enableRefreshToken,
        formatToken,
      }),
    );
  }

  // 通用的错误处理,如果没有进入上面的错误处理逻辑，就会进入这里
  client.addResponseInterceptor(
    errorMessageResponseInterceptor((msg: string, error) => {
      // AdPulse System Server 业务错误：依据 silent/code 处理
      if (error instanceof ApiBusinessError) {
        const skipError = Boolean((error as any).config?.skipErrorMessage);
        // 调用方声明自行处理提示
        if (skipError) return;
        // 4xx、401：全局静默，由调用页面或认证流程处理
        if (error.silent) {
          // 已认证客户端业务 401：触发重新登录（与 HTTP 401 行为一致）
          // 匿名客户端业务 401（登录/MFA 流程）：交给页面处理，这里不弹也不跳转
          if (error.code === 401 && authenticated && !isDemoMockEnabled) {
            void doReAuthenticate();
          }
          return;
        }
        // 5xx、6xx：全局展示一次（6xx 的 message 已替换为兜底文案）
        // 使用 key 去重，避免多个请求同时失败时弹出多条相同提示
        message.error({ content: error.message, key: error.message });
        return;
      }

      // 其他错误（mpower、网络异常、HTTP 错误等）按原有逻辑处理
      // 这里可以根据业务进行定制,你可以拿到 error 内的信息进行定制化处理，根据不同的 code 做不同的提示，而不是直接使用 message.error 提示 msg
      // 当前mock接口返回的错误字段是 error 或者 message
      const responseData = error?.response?.data ?? {};
      const errorMessage =
        responseData?.error ?? responseData?.message ?? responseData?.msg ?? '';
      const status = error?.response?.status;

      // 调用方传入 skipErrorMessage: true 时，由调用方自行处理错误提示
      if ((error.config as any)?.skipErrorMessage) return;

      // authenticated=true: 401 的提示 + 倒计时跳转由 doReAuthenticate 统一处理,这里不重复弹
      // authenticated=false: 匿名接口(登录/MFA)的401交给业务页面处理,这里不弹全局提示
      if (status === 401) return;

      // 500/502 错误(服务不可达)且没有业务错误信息时,显示自定义提示
      let finalMsg = errorMessage || msg;
      if (!errorMessage && (status === 500 || status === 502)) {
        finalMsg = '无法连接至服务器，请检查网络或联系网站管理员。';
      }

      // 如果没有错误信息，则会根据状态码进行提示
      // 使用 key 去重，避免多个请求同时失败时弹出多条相同提示
      message.error({ content: finalMsg, key: finalMsg });
    }),
  );

  return client;
}

export const requestClient = createRequestClient(apiURL, {
  responseReturn: 'data',
});
export const backendClient = createRequestClient(
  backendURL,
  {
    responseReturn: 'data',
    paramsSerializer: 'comma', // 使用逗号分隔数组参数
  },
  'backend',
);
// 广告数据服务（独立容器；默认由 Vite /adpulse-api 代理至 :8000）。
// 响应信封与 Java 一致，只是业务成功码是 0，故复用 'backend' 这一套解析。
export const adpulseClient = createRequestClient(
  adpulseURL,
  {
    responseReturn: 'data',
    paramsSerializer: 'comma',
  },
  'backend',
);
// AdPulse 主业务服务；本地及测试环境使用完整地址直接连接后端。
export const mainBackendClient = createRequestClient(
  import.meta.env.VITE_GLOB_MAIN_API_URL || '/main',
  {
    responseReturn: 'data',
    paramsSerializer: 'comma',
  },
  'backend',
);
// 匿名认证客户端：登录、MFA绑定/验证接口使用，不附加JWT、不触发刷新Token和全局401跳转
export const publicBackendClient = createRequestClient(
  backendURL,
  {
    responseReturn: 'data',
    paramsSerializer: 'comma',
  },
  'backend',
  false,
);
export const otherClient = createRequestClient(otherURL, {
  responseReturn: 'data',
});
// 不带前缀的 client，路径直接发出（用于 /aiReport 等独立代理）
export const plainClient = createRequestClient('', {
  responseReturn: 'data',
});
// export const backendClient = new RequestClient({ baseURL: backendURL });
// export const baseRequestClient = new RequestClient({ baseURL: apiURL });
export const baseBackendClient = new RequestClient({ baseURL: backendURL });

export interface PageFetchParams {
  [key: string]: any;
  pageNo?: number;
  pageSize?: number;
}
