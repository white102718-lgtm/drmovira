<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Input, Select } from 'ant-design-vue';

import type { PlatformConfigItem } from '#/api/management/platform-config';
import {
  getAgentOptions,
  getDepartmentOptions,
} from '#/api/management/platform-config';

import AgentLinesConfig from './agent-lines-config.vue';
import { usePlatformFromRoute } from './usePlatformFromRoute';

const props = defineProps<{
  platforms: PlatformConfigItem[];
}>();

const route = useRoute();
const router = useRouter();

const selectedPlatform = ref<string | undefined>(undefined);

const platformOptions = computed(() =>
  props.platforms.map((item) => ({
    label: item._id || item.game_platform,
    value: item._id || item.game_platform,
  })),
);

function filterPlatformOption(input: string, option: any) {
  return (option?.label ?? '').toLowerCase().includes(input.toLowerCase());
}

const gridLoading = ref(false);
const agentOptionsData = ref<Array<{ label: string; value: string }>>([]);
const agentSearchInput = ref('');
const agentSearchKeyword = ref('');

const departmentOptions = ref<Array<{ label: string; value: string }>>([]);
const selectedDepartment = ref<string | undefined>(undefined);

function departmentFilterOption(input: string, option: any) {
  return (option?.label ?? '').toLowerCase().includes(input.toLowerCase());
}

const fetchDepartmentOptions = async () => {
  try {
    const res = await getDepartmentOptions();
    if (Array.isArray(res)) {
      departmentOptions.value = res.map((item: string) => ({
        label: item,
        value: item,
      }));
    }
  } catch {}
};

onMounted(() => {
  fetchDepartmentOptions();
});

// 选中平台
function handleSelect(value: string) {
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
});
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- 顶部搜索栏 -->
    <div class="flex items-center gap-3 px-2 pt-2">
      <span class="whitespace-nowrap text-sm font-medium">选择平台：</span>
      <Select
        :value="selectedPlatform"
        allow-clear
        show-search
        placeholder="请搜索并选择平台"
        style="width: 300px"
        :options="platformOptions"
        :filter-option="filterPlatformOption"
        :disabled="gridLoading"
        @change="(val) => val && handleSelect(String(val))"
        @clear="handleClear"
      />
      <span class="whitespace-nowrap text-sm font-medium">部门：</span>
      <Select
        :value="selectedDepartment"
        placeholder="请选择部门"
        style="width: 180px"
        allow-clear
        show-search
        :options="departmentOptions"
        :disabled="gridLoading"
        :filter-option="departmentFilterOption"
        @change="(val) => (selectedDepartment = val || undefined)"
      />
      <span class="whitespace-nowrap text-sm font-medium">搜索代理线：</span>
      <Input
        v-model:value="agentSearchInput"
        placeholder="支持按前缀搜索"
        style="width: 200px"
        allow-clear
        :disabled="gridLoading"
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

    <!-- 代理线配置内容 -->
    <div class="flex-1 overflow-auto">
      <AgentLinesConfig
        :key="`agent-${selectedPlatform || ''}`"
        :platform-name="selectedPlatform || ''"
        :agent-options="agentOptionsData"
        :agent-search="agentSearchKeyword"
        :department="selectedDepartment"
        @update:loading="gridLoading = $event"
      />
    </div>
  </div>
</template>
