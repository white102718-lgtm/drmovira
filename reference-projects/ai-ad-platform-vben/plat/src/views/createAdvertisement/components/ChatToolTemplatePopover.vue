<script lang="ts" setup>
import { ref } from 'vue';

import { Button, message, Popover } from 'ant-design-vue';

const STORAGE_KEY = 'chat_tool_templates';

interface ChatToolTemplate {
  data: {
    greeting: string;
    greetingType: string;
    questions: { autoReply: string; question: string }[];
    reengagementEnabled: boolean;
    reengagementText: string;
  };
  id: string;
  name: string;
}

interface Emits {
  (e: 'apply', tpl: ChatToolTemplate): void;
  (e: 'new'): void;
}

const emit = defineEmits<Emits>();

const open = ref(false);
const templates = ref<ChatToolTemplate[]>([]);

function loadTemplates() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    templates.value = raw ? JSON.parse(raw) : [];
  } catch {
    templates.value = [];
  }
}

function deleteTemplate(id: string) {
  templates.value = templates.value.filter((t) => t.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(templates.value));
  message.success('已删除');
}

function handleOpen(val: boolean) {
  open.value = val;
  if (val) loadTemplates();
}

function handleApply(tpl: ChatToolTemplate) {
  emit('apply', tpl);
  open.value = false;
}

function handleNew() {
  open.value = false;
  emit('new');
}
</script>

<template>
  <Popover
    v-model:open="open"
    trigger="click"
    placement="bottomLeft"
    @open-change="handleOpen"
  >
    <template #content>
      <div style="min-width: 220px; max-width: 280px">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-sm font-medium text-gray-700">聊天模板</span>
          <span
            class="icon-[ant-design--reload-outlined] cursor-pointer text-gray-400 hover:text-blue-500"
            @click="loadTemplates"
          ></span>
        </div>
        <Button type="primary" class="mb-2 w-full" @click="handleNew">
          + 新建模板
        </Button>
        <div
          v-if="templates.length === 0"
          class="py-4 text-center text-xs text-gray-400"
        >
          暂无数据
        </div>
        <div v-else class="max-h-[260px] space-y-1 overflow-y-auto">
          <div
            v-for="tpl in templates"
            :key="tpl.id"
            class="flex items-center justify-between rounded border border-gray-100 px-2 py-1.5 hover:border-blue-300 hover:bg-blue-50"
          >
            <span
              class="flex-1 cursor-pointer truncate text-sm text-gray-700"
              @click="handleApply(tpl)"
            >
              {{ tpl.name }}
            </span>
            <span
              class="icon-[ant-design--delete-outlined] ml-2 shrink-0 cursor-pointer text-gray-300 hover:text-red-400"
              @click.stop="deleteTemplate(tpl.id)"
            ></span>
          </div>
        </div>
      </div>
    </template>
    <slot />
  </Popover>
</template>
