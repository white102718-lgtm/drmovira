import type { Pinia } from 'pinia';

import type { App } from 'vue';

import { createPinia } from 'pinia';
import SecureLS from 'secure-ls';

let pinia: Pinia;

export interface InitStoreOptions {
  /**
   * @zh_CN 应用名,由于 @vben/stores 是公用的，后续可能有多个app，为了防止多个app缓存冲突，可在这里配置应用名,应用名将被用于持久化的前缀
   */
  namespace: string;
}

/**
 * @zh_CN 初始化pinia
 */
export async function initStores(app: App, options: InitStoreOptions) {
  const { createPersistedState } = await import('pinia-plugin-persistedstate');
  pinia = createPinia();
  const { namespace } = options;
  const ls = new SecureLS({
    encodingType: 'aes',
    encryptionSecret: import.meta.env.VITE_APP_STORE_SECURE_KEY,
    isCompression: true,
    // @ts-ignore secure-ls does not have a type definition for this
    metaKey: `${namespace}-secure-meta`,
  });
  pinia.use(
    createPersistedState({
      // key $appName-$store.id
      key: (storeKey) => `${namespace}-${storeKey}`,
      storage: import.meta.env.DEV
        ? localStorage
        : {
            getItem(key) {
              return ls.get(key);
            },
            setItem(key, value) {
              ls.set(key, value);
            },
          },
    }),
  );
  app.use(pinia);

  // 监听其他 Tab 对 localStorage 的修改，同步 accessToken 到当前 Tab 的 Pinia
  const accessKey = `${namespace}-core-access`;
  window.addEventListener('storage', async (event) => {
    if (event.key !== accessKey || event.newValue === null) return;
    try {
      const { useAccessStore } = await import('./modules/access');
      const raw = import.meta.env.DEV
        ? event.newValue
        : ls.get(accessKey);
      const newState = JSON.parse(raw);
      const accessStore = useAccessStore();
      if (newState.accessToken !== undefined) {
        accessStore.setAccessToken(newState.accessToken);
      }
      if (newState.refreshToken !== undefined) {
        accessStore.setRefreshToken(newState.refreshToken);
      }
    } catch {}
  });

  return pinia;
}

export function resetAllStores() {
  if (!pinia) {
    console.error('Pinia is not installed');
    return;
  }
  const allStores = (pinia as any)._s;
  for (const [_key, store] of allStores) {
    store.$reset();
  }
}
