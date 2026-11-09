<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onDeactivated,
  ref,
  watch,
} from 'vue';

import { Textarea, theme } from 'ant-design-vue';

/** 需求表格的浮出式编辑框：值实时同步，保存/取消仍由所在行负责。 */
const props = withDefaults(
  defineProps<{
    label: string;
    disabled?: boolean;
    maxlength?: number;
    zIndex?: number;
    placement?: 'auto' | 'bottom' | 'top';
    placeholder?: string;
    value: string;
  }>(),
  { disabled: false, placement: 'auto', placeholder: '' },
);
const emit = defineEmits<{ 'update:value': [value: string] }>();
const { token } = theme.useToken();
const anchor = ref<HTMLDivElement>();
const popup = ref<HTMLDivElement>();
const expanded = ref(false);
const positioned = ref(false);
const bounds = ref({ height: 96, left: 0, top: 0, width: 0 });
const editorId = `description-editor-${crypto.randomUUID()}`;
// 初始容纳约四行；长文随内容增高，达到视口可用空间或 400px 后才滚动。
const MIN_EDITOR_HEIGHT = 96;
const MAX_EDITOR_HEIGHT = 400;
const VIEWPORT_GAP = 8;
let frame: number | undefined;
let resizeObserver: ResizeObserver | undefined;
let restoringFocus = false;

const popupStyle = computed(() => ({
  height: `${bounds.value.height}px`,
  left: `${bounds.value.left}px`,
  top: `${bounds.value.top}px`,
  width: `${bounds.value.width}px`,
  borderRadius: `${token.value.borderRadius}px`,
  boxShadow: token.value.boxShadowSecondary,
  visibility: positioned.value ? ('visible' as const) : ('hidden' as const),
  zIndex: props.zIndex ?? token.value.zIndexPopupBase + 1,
}));

function inlineInput() {
  return anchor.value?.querySelector('textarea');
}

function expandedInput() {
  return popup.value?.querySelector('textarea');
}

function updateBounds() {
  frame = undefined;
  const origin = anchor.value;
  const container = popup.value;
  const input = expandedInput();
  if (!expanded.value || !origin || !container || !input) return;

  const rect = origin.getBoundingClientRect();
  const viewport = window.visualViewport;
  const leftEdge = (viewport?.offsetLeft ?? 0) + VIEWPORT_GAP;
  const topEdge = (viewport?.offsetTop ?? 0) + VIEWPORT_GAP;
  const rightEdge =
    leftEdge + (viewport?.width ?? window.innerWidth) - VIEWPORT_GAP * 2;
  const bottomEdge =
    topEdge + (viewport?.height ?? window.innerHeight) - VIEWPORT_GAP * 2;

  // 锚点滚出可见区域时收起，避免编辑框悬停在无关位置。
  let visibleLeft = Math.max(rect.left, leftEdge);
  let visibleRight = Math.min(rect.right, rightEdge);
  let visibleTop = Math.max(rect.top, topEdge);
  let visibleBottom = Math.min(rect.bottom, bottomEdge);
  for (
    let parent = origin.parentElement;
    parent;
    parent = parent.parentElement
  ) {
    const style = getComputedStyle(parent);
    const parentRect = parent.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      visibleLeft = Math.max(visibleLeft, parentRect.left);
      visibleRight = Math.min(visibleRight, parentRect.right);
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      visibleTop = Math.max(visibleTop, parentRect.top);
      visibleBottom = Math.min(visibleBottom, parentRect.bottom);
    }
  }
  if (visibleRight <= visibleLeft || visibleBottom <= visibleTop) {
    closeEditor();
    return;
  }

  const width = Math.min(rect.width, rightEdge - leftEdge);
  // 先按实际宽度测量换行高度，同一帧内恢复高度及滚动位置，避免撑高表格行。
  container.style.width = `${width}px`;
  const scrollTop = input.scrollTop;
  input.style.height = '0px';
  const style = getComputedStyle(input);
  const naturalHeight =
    input.scrollHeight +
    parseFloat(style.borderTopWidth) +
    parseFloat(style.borderBottomWidth);
  const desiredHeight = Math.min(
    MAX_EDITOR_HEIGHT,
    Math.max(MIN_EDITOR_HEIGHT, naturalHeight),
  );
  const below = bottomEdge - Math.max(rect.top, topEdge);
  const above = Math.min(rect.bottom, bottomEdge) - topEdge;
  let placement =
    props.placement === 'auto'
      ? below >= desiredHeight || below >= above
        ? 'bottom'
        : 'top'
      : props.placement;
  // 首末行只指定优先方向；该方向放不下时使用空间更充足的一侧。
  if (placement === 'bottom' && below < desiredHeight && above > below)
    placement = 'top';
  else if (placement === 'top' && above < desiredHeight && below > above)
    placement = 'bottom';

  const height = Math.min(desiredHeight, placement === 'top' ? above : below);
  const top = placement === 'top' ? rect.bottom - height : rect.top;
  bounds.value = {
    height,
    left: Math.max(leftEdge, Math.min(rect.left, rightEdge - width)),
    top: Math.max(topEdge, Math.min(top, bottomEdge - height)),
    width,
  };
  input.style.height = `${height}px`;
  input.scrollTop = scrollTop;
  positioned.value = true;
}

function scheduleLayout() {
  if (expanded.value && frame === undefined)
    frame = requestAnimationFrame(updateBounds);
}

function handleScroll(event: Event) {
  if (event.target instanceof Node && popup.value?.contains(event.target))
    return;
  scheduleLayout();
}

function handleOutsidePointer(event: PointerEvent) {
  if (!(event.target instanceof Node)) return;
  if (
    !anchor.value?.contains(event.target) &&
    !popup.value?.contains(event.target)
  )
    closeEditor();
}

function stopTracking() {
  if (frame !== undefined) cancelAnimationFrame(frame);
  frame = undefined;
  resizeObserver?.disconnect();
  resizeObserver = undefined;
  document.removeEventListener('scroll', handleScroll, true);
  document.removeEventListener('pointerdown', handleOutsidePointer, true);
  window.removeEventListener('resize', scheduleLayout);
  window.visualViewport?.removeEventListener('resize', scheduleLayout);
  window.visualViewport?.removeEventListener('scroll', scheduleLayout);
}

async function openEditor() {
  if (props.disabled || expanded.value || restoringFocus) return;
  expanded.value = true;
  await nextTick();
  if (!expanded.value) return;
  updateBounds();
  if (!expanded.value) return;
  await nextTick();
  if (!expanded.value) return;
  const input = expandedInput();
  input?.focus({ preventScroll: true });
  input?.setSelectionRange(input.value.length, input.value.length);
  if (!expanded.value) return;
  resizeObserver = new ResizeObserver(scheduleLayout);
  if (anchor.value) resizeObserver.observe(anchor.value);
  document.addEventListener('scroll', handleScroll, true);
  document.addEventListener('pointerdown', handleOutsidePointer, true);
  window.addEventListener('resize', scheduleLayout);
  window.visualViewport?.addEventListener('resize', scheduleLayout);
  window.visualViewport?.addEventListener('scroll', scheduleLayout);
}

function closeEditor(restoreFocus = false) {
  expanded.value = false;
  positioned.value = false;
  stopTracking();
  if (restoreFocus) {
    restoringFocus = true;
    inlineInput()?.focus({ preventScroll: true });
    restoringFocus = false;
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.isComposing) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    closeEditor(true);
  } else if (event.key === 'Tab') {
    // 浮层挂在 body 下，Tab 仍沿原单元格的表单顺序移动。
    const input = inlineInput();
    // 在弹窗内复用时，Tab 只遍历所属弹窗，避免焦点跳到底层工单。
    const focusRoot =
      anchor.value?.closest<HTMLElement>('[role="dialog"]') ?? document;
    const focusable = [
      ...focusRoot.querySelectorAll<HTMLElement>(
        'a[href], button, input, textarea, select, [tabindex]',
      ),
    ].filter(
      (element) =>
        element.tabIndex >= 0 &&
        !element.matches(':disabled') &&
        !element.closest('[inert]') &&
        element.getClientRects().length > 0 &&
        getComputedStyle(element).visibility !== 'hidden' &&
        !popup.value?.contains(element),
    );
    const index = input ? focusable.indexOf(input) : -1;
    const target =
      index >= 0 ? focusable[index + (event.shiftKey ? -1 : 1)] : undefined;
    if (target) {
      event.preventDefault();
      event.stopPropagation();
      closeEditor();
      target.focus();
    } else closeEditor(true);
  }
}

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) closeEditor();
  },
  { flush: 'sync' },
);
watch(() => props.value, scheduleLayout, { flush: 'post' });
watch(() => props.placement, scheduleLayout);
onBeforeUnmount(() => closeEditor());
onDeactivated(() => closeEditor());
</script>

<template>
  <div ref="anchor" class="description-input-anchor">
    <Textarea
      :value="value"
      :disabled="disabled"
      :maxlength="maxlength"
      :aria-label="label"
      :aria-controls="expanded ? editorId : undefined"
      aria-haspopup="dialog"
      :placeholder="placeholder"
      :auto-size="false"
      :rows="1"
      readonly
      @focus="openEditor"
      @click="openEditor"
    />
    <Teleport to="body">
      <div
        v-if="expanded"
        :id="editorId"
        ref="popup"
        role="dialog"
        :aria-label="label"
        class="description-input-popup"
        :style="popupStyle"
      >
        <Textarea
          :value="value"
          :disabled="disabled"
          :maxlength="maxlength"
          :aria-label="label"
          :placeholder="placeholder"
          :auto-size="false"
          @update:value="emit('update:value', $event)"
          @input="scheduleLayout"
          @blur="closeEditor()"
          @keydown="handleKeydown"
        />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.description-input-anchor {
  width: 100%;
  height: var(--adpulse-control-height);
}

.description-input-popup {
  position: fixed;
  background: var(--adpulse-surface);
}
</style>
