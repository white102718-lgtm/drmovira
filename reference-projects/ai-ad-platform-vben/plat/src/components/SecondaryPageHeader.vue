<script lang="ts" setup>
import type { RouteLocationRaw } from 'vue-router';

import { useRoute, useRouter } from 'vue-router';

import { Card, PageHeader } from 'ant-design-vue';
import { useTabs } from '@vben/hooks';
import { getTabKey } from '@vben/stores';

interface Props {
  backTo?: RouteLocationRaw;
  card?: boolean;
  description?: string;
  title: string;
}

const props = withDefaults(defineProps<Props>(), {
  backTo: undefined,
  card: false,
  description: undefined,
});

const route = useRoute();
const router = useRouter();
const { closeTabByKey } = useTabs();

async function handleBack() {
  if (!props.backTo) return;

  // 先激活一级页，再移除当前二级页标签，防止标签栏自动跳转到相邻的无关页面。
  const currentTabKey = encodeURIComponent(getTabKey(route));
  await router.push(props.backTo);
  await closeTabByKey(currentTabKey);
}
</script>

<template>
  <Card v-if="card" :body-style="{ padding: 0 }">
    <PageHeader
      :ghost="false"
      :onBack="backTo ? handleBack : undefined"
      :sub-title="description"
      :title="title"
    >
      <template v-if="$slots.extra" #extra>
        <slot name="extra" />
      </template>
    </PageHeader>
  </Card>
  <PageHeader
    v-else
    :ghost="false"
    :onBack="backTo ? handleBack : undefined"
    :sub-title="description"
    :title="title"
  >
    <template v-if="$slots.extra" #extra>
      <slot name="extra" />
    </template>
  </PageHeader>
</template>
