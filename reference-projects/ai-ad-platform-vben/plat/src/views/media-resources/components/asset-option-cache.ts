import { ref } from 'vue';

import {
  getAdAccountAttributes,
  getChannelOptions,
  isFusionDemoMode,
} from '#/api';
import { getAccountTypes } from '#/api/mpower';

export interface AssetOption {
  label: string;
  value: string;
}

const demoChannelOptions: AssetOption[] = [
  { label: 'Mpower SEA 核心代理', value: '1001' },
  { label: 'ZCLINK 北美企业户', value: '1002' },
  { label: 'Firefly 拉美号商', value: '1003' },
];

const accountAttributeOptions = ref<AssetOption[]>([]);
const accountTypeOptions = ref<AssetOption[]>([]);
const channelOptions = ref<AssetOption[]>([]);
const channelLoading = ref(false);

let accountAttributesLoaded = false;
let accountAttributesRequest: Promise<AssetOption[]> | undefined;
let accountTypesLoaded = false;
let accountTypesRequest: Promise<AssetOption[]> | undefined;
let channelsLoaded = false;
let channelsRequest: Promise<AssetOption[]> | undefined;

/**
 * 加载资产页面共用的有效渠道，并合并父子组件在同一时刻发起的请求。
 *
 * @param force 是否忽略已有成功缓存并重新请求
 */
async function loadChannels(force = false) {
  if (!force && channelsLoaded) return channelOptions.value;
  if (channelsRequest) return channelsRequest;

  channelLoading.value = true;
  channelsRequest = (
    isFusionDemoMode()
      ? Promise.resolve(demoChannelOptions)
      : getChannelOptions()
  )
    .then((options) => {
      channelOptions.value = options;
      channelsLoaded = true;
      return options;
    })
    .catch((error: unknown) => {
      channelsLoaded = false;
      throw error;
    })
    .finally(() => {
      channelLoading.value = false;
      channelsRequest = undefined;
    });
  return channelsRequest;
}

/** 加载广告户账户类型；失败不会写入成功标记，后续操作可以重新请求。 */
async function loadAccountTypes(force = false) {
  if (!force && accountTypesLoaded) return accountTypeOptions.value;
  if (accountTypesRequest) return accountTypesRequest;

  accountTypesRequest = getAccountTypes()
    .then((response) => {
      const options = response.data.map((item) => ({
        label: item.accountType,
        value: item.accountType,
      }));
      accountTypeOptions.value = options;
      accountTypesLoaded = true;
      return options;
    })
    .catch((error: unknown) => {
      accountTypesLoaded = false;
      throw error;
    })
    .finally(() => {
      accountTypesRequest = undefined;
    });
  return accountTypesRequest;
}

/** 加载广告户账户属性；失败不会写入成功标记，后续操作可以重新请求。 */
async function loadAccountAttributes(force = false) {
  if (!force && accountAttributesLoaded) return accountAttributeOptions.value;
  if (accountAttributesRequest) return accountAttributesRequest;

  accountAttributesRequest = getAdAccountAttributes()
    .then((attributes) => {
      const options = attributes.map((item) => ({
        label: item.accountAttribute,
        value: item.accountAttribute,
      }));
      accountAttributeOptions.value = options;
      accountAttributesLoaded = true;
      return options;
    })
    .catch((error: unknown) => {
      accountAttributesLoaded = false;
      throw error;
    })
    .finally(() => {
      accountAttributesRequest = undefined;
    });
  return accountAttributesRequest;
}

/** 首次需要渠道时加载，已有缓存或进行中请求则直接复用。 */
export function ensureAssetChannelOptions() {
  return loadChannels();
}

/** 广告户筛选、编辑与批量处理共用同一组账户及渠道选项。 */
export function ensureAdAccountOptions() {
  return Promise.all([
    loadAccountTypes(),
    loadAccountAttributes(),
    loadChannels(),
  ]);
}

/** 页面从 KeepAlive 返回时刷新当前资产类型需要的渠道快照。 */
export function refreshAssetChannelOptions() {
  return loadChannels(true);
}

/** 页面从 KeepAlive 返回时刷新广告户使用的全部字典快照。 */
export function refreshAdAccountOptions() {
  return Promise.all([
    loadAccountTypes(true),
    loadAccountAttributes(true),
    loadChannels(true),
  ]);
}

/** 返回资产页面共享的字典状态；调用方只消费选项，不直接改写缓存。 */
export function useAssetOptionCache() {
  return {
    accountAttributeOptions,
    accountTypeOptions,
    channelLoading,
    channelOptions,
  };
}
