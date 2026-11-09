<script lang="ts" setup>
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { AutoComplete, Empty, Input } from 'ant-design-vue';

import type { PlatformConfigItem } from '#/api/management/platform-config';
import { getAgentOptions } from '#/api/management/platform-config';

import AgentLinesKpiConfig from './agent-lines-kpi-config.vue';
import { usePlatformFromRoute } from './usePlatformFromRoute';

const props = defineProps<{
  platforms: PlatformConfigItem[];
}>();

const route = useRoute();
const router = useRouter();

const platformInput = ref('');
const selectedPlatform = ref<string | undefined>(undefined);

const platformOptions = computed(() => {
  const keyword = platformInput.value.trim().toLowerCase();
  const list = keyword
    ? props.platforms.filter((p) =>
        (p._id || p.game_platform || '').toLowerCase().includes(keyword),
      )
    : props.platforms;
  return list.map((item) => ({
    label: item._id || item.game_platform,
    value: item._id || item.game_platform,
  }));
});

const agentOptionsData = ref<Array<{ label: string; value: string }>>([]);
const agentSearchInput = ref('');
const agentSearchKeyword = ref('');

function handleInputChange(value: string) {
  platformInput.value = value || '';
}

// 选中平台
function handleSelect(value: string) {
  platformInput.value = value;
  selectedPlatform.value = value;
  router.push({
    query: {
      ...route.query,
      platform: value,
    },
  });
}

// 清空平台
function handleClear() {
  platformInput.value = '';
  selectedPlatform.value = undefined;
  agentOptionsData.value = [];
  agentSearchInput.value = '';
  agentSearchKeyword.value = '';
  const { platform, ...restQuery } = route.query as Record<string, any>;
  router.push({
    query: {
      ...restQuery,
    },
  });
}

// 代理线搜索
function handleAgentSearch() {
  agentSearchKeyword.value = agentSearchInput.value;
}

// 选择平台后加载代理线选项 & 重置搜索
watch(selectedPlatform, async (newPlatform) => {
  if (!newPlatform) {
    agentOptionsData.value = [];
    return;
  }
  try {
    const res = await getAgentOptions(newPlatform);
    if (Array.isArray(res)) {
      const platformData = res.find(
        (item: any) =>
          item._id === newPlatform || item.game_platform === newPlatform,
      );
      agentOptionsData.value =
        platformData && Array.isArray(platformData.agent_lines)
          ? platformData.agent_lines.map((line: string) => ({
              label: line,
              value: line,
            }))
          : [];
    }
  } catch {
    agentOptionsData.value = [];
  }
});

usePlatformFromRoute({
  selectedPlatform,
  platformInputRef: platformInput,
});
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 顶部搜索栏 -->
    <div class="mb-3 flex items-center gap-3 px-2 pt-2">
      <span class="whitespace-nowrap text-sm font-medium">选择平台：</span>
      <AutoComplete
        :value="platformInput"
        allow-clear
        placeholder="请搜索并选择平台"
        style="width: 300px"
        :options="platformOptions"
        :filter-option="false"
        @change="handleInputChange"
        @select="handleSelect"
        @clear="handleClear"
      />
      <span class="whitespace-nowrap text-sm font-medium">搜索代理线：</span>
      <Input
        v-model:value="agentSearchInput"
        placeholder="输入代理线名称"
        style="width: 200px"
        allow-clear
        @press-enter="handleAgentSearch"
        @clear="
          () => {
            agentSearchInput = '';
            agentSearchKeyword = '';
          }
        "
      >
        <template #suffix>
          <span
            class="icon-[ant-design--search-outlined] cursor-pointer text-lg"
            @click="handleAgentSearch"
          ></span>
        </template>
      </Input>
    </div>

    <!-- KPI配置内容 -->
    <div v-if="selectedPlatform || agentSearchKeyword" class="flex-1 overflow-auto">
      <AgentLinesKpiConfig
        :key="`kpi-${selectedPlatform || ''}`"
        :platform-name="selectedPlatform || ''"
        :agent-options="agentOptionsData"
        :agent-search="agentSearchKeyword"
      />
    </div>

    <!-- 未选择平台且无搜索关键字时的空状态 -->
    <div v-else class="flex flex-1 items-center justify-center">
      <Empty description="请选择平台或输入代理线名称搜索" />
    </div>
  </div>
</template>
