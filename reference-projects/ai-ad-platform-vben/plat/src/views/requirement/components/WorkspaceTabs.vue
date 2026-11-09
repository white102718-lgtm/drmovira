<script setup lang="ts">
import type { OrderWorkspace } from '../composables/useOrderWorkspace';

defineProps<{
  listLabel?: string;
  showForm?: boolean;
  ws: OrderWorkspace;
}>();
</script>

<template>
  <div class="sticky top-0 z-10 w-48 flex-shrink-0 self-start overflow-hidden rounded-lg border border-gray-200 bg-white shadow">
    <div class="border-b border-gray-200 bg-gray-50 px-4 py-2.5 text-sm font-semibold text-gray-700">页面导航</div>
    <div class="flex flex-col gap-1 p-2">
    <button
      class="rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
      :class="ws.tabClass(ws.view === 'list')"
      @click="ws.view = 'list'"
    >{{ listLabel ?? '需求列表' }}</button>
    <button
      v-if="ws.detailOpen"
      class="flex items-center rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
      :class="ws.tabClass(ws.view === 'detail')"
      :title="ws.currentTitle"
      @click="ws.openDetailTab()"
    ><span class="truncate">需求详情{{ ws.currentTitle ? ` · ${ws.currentTitle}` : '' }}</span></button>
    <button
      v-if="ws.acceptTabVisible"
      class="flex items-center rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
      :class="ws.tabClass(ws.view === 'accept')"
      :title="ws.currentTitle"
      @click="ws.openAcceptTab()"
    ><span class="truncate">验收详情{{ ws.currentTitle ? ` · ${ws.currentTitle}` : '' }}</span></button>
    <button
      v-if="showForm && ws.formOpen"
      class="flex items-center rounded-md px-3 py-2 text-left text-sm font-medium transition-colors"
      :class="ws.tabClass(ws.view === 'form')"
      @click="ws.view = 'form'"
    >
      <span class="min-w-0 flex-1 truncate">{{ ws.formTabLabel }}</span>
      <span
        class="ml-1 flex-shrink-0 rounded px-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
        title="关闭"
        @click.stop="ws.closeForm()"
      >✕</span>
    </button>
    </div>
  </div>
</template>

<style>
/* 全局 4px 滚动条规则(global.css html:not([data-platform='macOs']))优先级高, 此处同前缀加权覆盖 */
html:not([data-platform='macOs']) .requirement-workspace-scroll::-webkit-scrollbar {
  width: 10px;
}
html:not([data-platform='macOs']) .requirement-workspace-scroll::-webkit-scrollbar-thumb {
  background: #94a3b8;
  border-radius: 5px;
}
</style>
