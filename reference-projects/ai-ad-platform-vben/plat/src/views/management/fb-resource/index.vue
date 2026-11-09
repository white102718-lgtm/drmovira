<script lang="ts" setup>
import type { EffectiveAppIdItem } from '#/api/management/platform-config';

import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Button, message, Modal, Radio } from 'ant-design-vue';

import {
  getAdvertisingLogin,
  getEffectiveAppIds,
} from '#/api/management/platform-config';
import FullHeightTabs from '#/views/components/FullHeightTabs.vue';

import AdAccountsTab from './components/AdAccountsTab.vue';
import BusinessManagersTab from './components/BusinessManagersTab.vue';
import PagesTab from './components/PagesTab.vue';
import PersonalAccountsTab from './components/PersonalAccountsTab.vue';
import PixelsTab from './components/PixelsTab.vue';
import SystemAccountsTab from './components/SystemAccountsTab.vue';

const route = useRoute();
const router = useRouter();
const routePath = route.path;

const VALID_TABS = ['personal', 'system', 'bm', 'account', 'page', 'pixel'];
const tabs = [
  { key: 'personal', label: '个号' },
  { key: 'system', label: '系统' },
  { key: 'bm', label: 'BM' },
  { key: 'account', label: '户' },
  { key: 'page', label: '主页' },
  { key: 'pixel', label: '像素' },
];

function resolveRouteTab(value: unknown) {
  const tab = Array.isArray(value) ? value[0] : value;
  return typeof tab === 'string' && VALID_TABS.includes(tab) ? tab : 'personal';
}

// 在子列表创建前恢复主 Tab，避免深链接先加载默认“个号”列表。
const activeTab = ref(resolveRouteTab(route.query.tab));

watch(
  () => route.fullPath,
  () => {
    if (route.path !== routePath) return;
    const resolvedTab = resolveRouteTab(route.query.tab);
    if (activeTab.value !== resolvedTab) activeTab.value = resolvedTab;
    if (route.query.tab === resolvedTab) return;
    void router.replace({
      path: routePath,
      query: { ...route.query, tab: resolvedTab },
    });
  },
  { immediate: true },
);

watch(activeTab, (newKey) => {
  if (route.path !== routePath) return;
  if (route.query.tab === newKey) return;
  void router.replace({
    path: routePath,
    query: {
      ...route.query,
      tab: newKey,
    },
  });
});

const appSelectModalVisible = ref(false);
const selectedAppId = ref<string>('');
const appOptions = ref<EffectiveAppIdItem[]>([]);
const appOptionsLoading = ref(false);

async function openAppSelectModal() {
  selectedAppId.value = '';
  appSelectModalVisible.value = true;
  appOptionsLoading.value = true;
  try {
    const data = await getEffectiveAppIds();
    appOptions.value = Object.entries(data).map(([name, app]) => ({
      ...app,
      name,
    }));
  } catch {
    appOptions.value = [];
  } finally {
    appOptionsLoading.value = false;
  }
}

function closeAppSelectModal() {
  appSelectModalVisible.value = false;
  selectedAppId.value = '';
}

async function handleAppSelectConfirm() {
  if (!selectedAppId.value) {
    message.warning('请选择应用');
    return;
  }

  const selected = appOptions.value.find(
    (o) => o.app_id === selectedAppId.value,
  );
  if (!selected) return;

  try {
    const authorizationUrl = await getAdvertisingLogin(
      selected.app_id,
      selected.config_id,
    );
    if (authorizationUrl) {
      closeAppSelectModal();
      window.location.href = authorizationUrl;
    }
  } catch {
    message.error('授权失败，请重试');
  }
}
</script>

<template>
  <div
    class="adpulse-section-page adpulse-tabs-page adpulse-full-height-tabs-page platform-resources-page bg-background h-full min-h-0"
  >
    <div class="platform-resources-workspace flex h-full min-h-0 flex-col">
      <FullHeightTabs
        v-model:active-key="activeTab"
        class="min-h-0 flex-1"
        :tabs="tabs"
      >
        <div
          v-show="activeTab === 'personal'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <PersonalAccountsTab />
        </div>
        <div
          v-show="activeTab === 'system'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <SystemAccountsTab />
        </div>
        <div
          v-show="activeTab === 'bm'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <BusinessManagersTab />
        </div>
        <div
          v-show="activeTab === 'account'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <AdAccountsTab />
        </div>
        <div
          v-show="activeTab === 'page'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <PagesTab />
        </div>
        <div
          v-show="activeTab === 'pixel'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <PixelsTab />
        </div>
        <template #rightExtra>
          <Button type="primary" @click="openAppSelectModal">授权账户</Button>
        </template>
      </FullHeightTabs>
    </div>

    <Modal
      :open="appSelectModalVisible"
      title="选择应用"
      ok-text="确定"
      cancel-text="取消"
      @ok="handleAppSelectConfirm"
      @cancel="closeAppSelectModal"
    >
      <div class="py-4">
        <div class="mb-2 text-sm text-gray-600">
          <span class="text-red-500">*</span> 应用
        </div>
        <div
          v-if="appOptionsLoading"
          class="py-4 text-center text-sm text-gray-400"
        >
          加载中...
        </div>
        <Radio.Group
          v-else
          :value="selectedAppId"
          @change="(e) => (selectedAppId = e.target.value)"
          class="w-full"
        >
          <div class="space-y-3">
            <Radio
              v-for="app in appOptions"
              :key="app.app_id"
              :value="app.app_id"
              class="w-full"
            >
              {{ app.name }}
            </Radio>
          </div>
        </Radio.Group>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.platform-resources-workspace {
  box-sizing: border-box;
  padding: var(--adpulse-card-padding);
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--adpulse-page-radius);
  box-shadow: var(--adpulse-card-shadow);
}

/* 工具栏仅承载右侧刷新按钮，不应绘制一整条与内容竞争的背景色块。 */
.platform-resources-page :deep(.vxe-toolbar) {
  background-color: transparent;
}
</style>
