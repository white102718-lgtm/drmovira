<script setup lang="ts">
import type {
  MaterialFolderSummary,
  MaterialFolderVisibility,
} from '#/domain/material';

import { computed, nextTick, ref, useId, watch } from 'vue';

import {
  Alert,
  Button,
  Input,
  message,
  Popover,
  Select,
  theme,
} from 'ant-design-vue';

import { httpFolderService } from '#/domain/material';

const props = defineProps<{
  disabled?: boolean;
  folder?: MaterialFolderSummary;
  parentFolder?: MaterialFolderSummary;
}>();
const emit = defineEmits<{
  created: [folder: Pick<MaterialFolderSummary, 'id' | 'name' | 'parentId'>];
}>();

type CreationMode = 'child' | 'root' | 'sibling';

const { token } = theme.useToken();
const actionTheme = computed(() => ({
  '--folder-action-color': token.value.colorPrimary,
  '--folder-action-background': token.value.colorBgContainer,
  '--folder-action-border': token.value.colorBorderSecondary,
  '--folder-action-selected-background': token.value.colorPrimaryBg,
  '--folder-action-selected-border': token.value.colorPrimaryBorder,
  '--folder-action-disabled-color': token.value.colorTextDisabled,
  '--folder-action-disabled-background': token.value.colorBgContainerDisabled,
}));
const instanceId = useId();
const open = ref(false);
const mode = ref<CreationMode>('root');
const name = ref('');
const visibility = ref<MaterialFolderVisibility>('private');
const submitting = ref(false);
const error = ref('');
const nameInput = ref<{ focus: () => void }>();
let trigger: HTMLElement | undefined;

const visibilityOptions = [
  { label: '仅自己可见', value: 'private' },
  { label: '本部门可见', value: 'department' },
  { label: '全员可见', value: 'organization' },
];
const visibilityLabels: Record<MaterialFolderVisibility, string> = {
  private: '仅自己可见',
  department: '本部门可见',
  organization: '全员可见',
};
const canCreateSibling = computed(
  () =>
    props.folder?.isOwner === true &&
    (!props.folder.parentId || props.parentFolder?.isOwner === true),
);
const canCreateChild = computed(
  () => props.folder?.isOwner === true && props.folder.level < 2,
);
const parentId = computed(() =>
  mode.value === 'child' ? props.folder?.id : props.folder?.parentId,
);
const locationDescription = computed(() => {
  if (mode.value === 'child')
    return `将在「${props.folder?.name}」下创建子文件夹`;
  if (mode.value === 'sibling')
    return `将创建与「${props.folder?.name}」同级的文件夹`;
  return '创建根文件夹，并设置查看权限。';
});

watch(open, async (value) => {
  if (value) {
    await nextTick();
    nameInput.value?.focus();
  }
});

function startCreate(nextMode: CreationMode, event: MouseEvent) {
  if (props.disabled || submitting.value) return;
  if (nextMode === 'child' && !canCreateChild.value) return;
  if (nextMode === 'sibling' && !canCreateSibling.value) return;
  trigger = event.currentTarget as HTMLElement;
  mode.value = nextMode;
  name.value = '';
  visibility.value = props.folder?.visibility ?? 'private';
  error.value = '';
  open.value = true;
}

function closeCreate(restoreFocus = false) {
  if (submitting.value) return;
  open.value = false;
  if (restoreFocus) trigger?.focus();
}

function handleOpenChange(value: boolean) {
  // 创建入口决定层级，点击浮层外部只负责关闭。
  if (!value) closeCreate();
}

async function createFolder() {
  if (props.disabled || submitting.value) return;
  const folderName = name.value.trim();
  if (!folderName) {
    error.value = '请输入文件夹名称';
    nameInput.value?.focus();
    return;
  }
  if (mode.value === 'child' && !canCreateChild.value) return;
  if (mode.value === 'sibling' && !canCreateSibling.value) return;

  // 行内创建沿用对应目录的空间和可见性；子级最终由服务端强制继承父级。
  const inheritedFolder = mode.value === 'root' ? undefined : props.folder;
  const folderVisibility = inheritedFolder?.visibility ?? visibility.value;
  const targetParentId = parentId.value;
  submitting.value = true;
  error.value = '';
  try {
    const id = await httpFolderService.create({
      name: folderName,
      parentId: targetParentId,
      scope:
        inheritedFolder?.scope ??
        (folderVisibility === 'private' ? 'personal' : 'department'),
      visibility: folderVisibility,
    });
    open.value = false;
    message.success('文件夹已创建');
    emit('created', { id, name: folderName, parentId: targetParentId });
    trigger?.focus();
  } catch (value) {
    error.value = value instanceof Error ? value.message : '创建失败，请重试';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Popover
    :open="open"
    trigger="click"
    placement="bottomRight"
    :destroy-tooltip-on-hide="true"
    @open-change="handleOpenChange"
  >
    <template #content>
      <section
        :id="`${instanceId}-dialog`"
        role="dialog"
        :aria-labelledby="`${instanceId}-title`"
        class="folder-create-panel"
        @click.stop
        @keydown.esc.stop.prevent="closeCreate(true)"
        @keydown.stop
      >
        <h3
          :id="`${instanceId}-title`"
          class="text-foreground text-sm font-medium"
        >
          新建文件夹
        </h3>
        <p class="text-muted-foreground mt-1 break-words text-xs">
          {{ locationDescription }}
        </p>
        <form class="mt-4 space-y-4" @submit.prevent="createFolder">
          <div>
            <label :for="`${instanceId}-name`" class="mb-1.5 block text-sm">
              文件夹名称
            </label>
            <Input
              :id="`${instanceId}-name`"
              ref="nameInput"
              v-model:value="name"
              :maxlength="40"
              :disabled="submitting"
              :aria-invalid="!!error"
              :aria-describedby="error ? `${instanceId}-error` : undefined"
              placeholder="输入文件夹名称"
              autocomplete="off"
            />
          </div>
          <div v-if="!folder">
            <label
              :for="`${instanceId}-visibility`"
              class="mb-1.5 block text-sm"
            >
              查看权限
            </label>
            <Select
              :id="`${instanceId}-visibility`"
              v-model:value="visibility"
              class="w-full"
              :disabled="submitting"
              :options="visibilityOptions"
            />
          </div>
          <p v-else class="text-muted-foreground text-xs">
            查看权限：{{ visibilityLabels[folder.visibility] }}（继承目录权限）
          </p>
          <Alert
            v-if="error"
            :id="`${instanceId}-error`"
            type="error"
            show-icon
            :message="error"
          />
          <div class="flex justify-end gap-2">
            <Button :disabled="submitting" @click="closeCreate(true)">
              取消
            </Button>
            <Button
              type="primary"
              html-type="submit"
              :loading="submitting"
              :disabled="!name.trim() || disabled"
            >
              创建文件夹
            </Button>
          </div>
        </form>
      </section>
    </template>
    <span
      class="inline-flex shrink-0 items-center gap-1"
      :style="actionTheme"
      @click.stop
    >
      <template v-if="folder">
        <Button
          type="text"
          class="folder-level-button"
          :disabled="disabled || submitting || !canCreateSibling"
          :aria-label="`在 ${folder.name} 同级新建文件夹`"
          :aria-controls="`${instanceId}-dialog`"
          :aria-expanded="open && mode === 'sibling'"
          aria-haspopup="dialog"
          @click.stop="startCreate('sibling', $event)"
        >
          同级
        </Button>
        <Button
          type="text"
          class="folder-level-button"
          :disabled="disabled || submitting || !canCreateChild"
          :title="folder.level >= 2 ? '文件夹最多支持三层' : '新建子文件夹'"
          :aria-label="`在 ${folder.name} 下新建子文件夹`"
          :aria-controls="`${instanceId}-dialog`"
          :aria-expanded="open && mode === 'child'"
          aria-haspopup="dialog"
          @click.stop="startCreate('child', $event)"
        >
          子级
        </Button>
      </template>
      <Button
        v-else
        type="primary"
        class="folder-create-trigger"
        :disabled="disabled || submitting"
        :aria-controls="`${instanceId}-dialog`"
        :aria-expanded="open"
        aria-haspopup="dialog"
        @click.stop="startCreate('root', $event)"
      >
        <template #icon>
          <span
            class="folder-create-trigger-icon icon-[lucide--folder-plus] mr-2"
            aria-hidden="true"
          ></span>
        </template>
        新建文件夹
      </Button>
    </span>
  </Popover>
</template>

<style scoped>
/* 行内操作复用当前弹窗的 Ant 主题色，选中态与主按钮保持一致。 */

.folder-create-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.folder-create-trigger-icon {
  display: block;
  flex: none;
  width: 14px;
  height: 14px;
}

.folder-create-panel {
  width: min(280px, calc(100vw - 64px));
  max-height: calc(100dvh - 96px);
  overflow-y: auto;
}
</style>
