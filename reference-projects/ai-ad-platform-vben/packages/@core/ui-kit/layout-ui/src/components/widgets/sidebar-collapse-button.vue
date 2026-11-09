<script setup lang="ts">
import { ChevronsLeft, ChevronsRight } from '@vben-core/icons';

const collapsed = defineModel<boolean>('collapsed');

function handleCollapsed() {
  collapsed.value = !collapsed.value;
}
</script>

<template>
  <button
    type="button"
    :aria-expanded="!collapsed"
    :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
    :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
    class="flex-center hover:text-foreground text-foreground/60 hover:bg-accent-hover bg-accent focus-visible:ring-primary absolute bottom-1 right-1 z-10 size-8 cursor-pointer rounded-md border-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
    @click.stop="handleCollapsed"
  >
    <ChevronsRight v-if="collapsed" class="size-4" />
    <ChevronsLeft v-else class="size-4" />
  </button>
</template>
