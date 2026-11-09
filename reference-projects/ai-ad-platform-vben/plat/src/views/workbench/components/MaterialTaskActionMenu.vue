<script setup lang="ts">
import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Dropdown, Menu, MenuItem } from 'ant-design-vue';

/** 桌面列表直接展示操作；移动列表和看板保留折叠菜单，权限由父级统一判断。 */
const props = defineProps<{
  actions: {
    key: string;
    label: string;
    shortLabel: string;
    danger?: boolean;
  }[];
  disabled?: boolean;
  inline?: boolean;
  loading?: boolean;
}>();
const emit = defineEmits<{ select: [key: string] }>();
const primary = computed(() => props.actions[0]);
const more = computed(() => props.actions.slice(1));
</script>

<template>
  <div
    class="material-task-actions"
    :class="{ 'material-task-actions-inline': inline }"
    :aria-busy="loading"
  >
    <template v-if="inline">
      <!-- 加载图标替换首个按钮文字，保持列宽不变。 -->
      <Button
        v-for="(action, index) in actions"
        :key="action.key"
        class="material-task-action"
        type="link"
        :aria-label="action.label"
        :title="action.label"
        :danger="action.danger"
        :disabled="disabled || loading"
        :loading="loading && index === 0"
        @click="emit('select', action.key)"
      >
        <span v-if="!loading || index !== 0">{{ action.shortLabel }}</span>
      </Button>
    </template>
    <template v-else>
      <Button
        v-if="primary"
        type="link"
        :aria-label="primary.label"
        :title="primary.label"
        :disabled="disabled || loading"
        @click="emit('select', primary.key)"
      >
        {{ primary.shortLabel }}
      </Button>
      <Dropdown
        v-if="more.length"
        :trigger="['click']"
        :disabled="disabled || loading"
      >
        <Button
          aria-label="更多操作"
          title="更多操作"
          :loading="loading"
          :disabled="disabled || loading"
        >
          <IconifyIcon v-if="!loading" icon="lucide:ellipsis" />
        </Button>
        <template #overlay>
          <Menu>
            <MenuItem
              v-for="action in more"
              :key="action.key"
              :danger="action.danger"
              :title="action.label"
              @click="emit('select', action.key)"
            >
              {{ action.shortLabel }}
            </MenuItem>
          </Menu>
        </template>
      </Dropdown>
    </template>
  </div>
</template>

<style scoped>
.material-task-actions {
  display: flex;
  flex: none;
  gap: 8px;
  align-items: center;
  white-space: nowrap;
}

.material-task-actions-inline {
  gap: 4px;
}

.material-task-action {
  flex: none;
  width: 40px;
  padding-inline: 0;
}
</style>
