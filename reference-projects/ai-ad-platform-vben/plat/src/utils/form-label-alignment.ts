/**
 * Keep each side-label form compact while aligning its labels and input starts.
 * The width is calculated per form from its longest visible field label, including
 * Ant Design vertical forms that the global baseline renders as side-label forms.
 */
const FORM_LABEL_ALIGNMENT_SELECTOR = [
  'form',
  '.ant-form-horizontal',
  '.ant-form-inline',
  '.ant-form-vertical:not(.ux-form-label-top)',
  '.ux-filter-form',
  '.channel-filter',
  '.material-filter-form',
].join(',');

function getFormLabels(form: HTMLElement): HTMLLabelElement[] {
  const vbenLabels = Array.from(
    form.querySelectorAll<HTMLLabelElement>(
      ':scope > .grid > .flex-row.items-center > label',
    ),
  );

  if (vbenLabels.length > 0) {
    return vbenLabels;
  }

  if (
    !form.classList.contains('ant-form-horizontal') &&
    !form.classList.contains('ant-form-inline') &&
    !(
      form.classList.contains('ant-form-vertical') &&
      !form.classList.contains('ux-form-label-top')
    ) &&
    !form.classList.contains('ux-filter-form') &&
    !form.classList.contains('channel-filter') &&
    !form.classList.contains('material-filter-form')
  ) {
    return [];
  }

  return Array.from(
    form.querySelectorAll<HTMLLabelElement>('.ant-form-item-label > label'),
  ).filter(
    // 只测量当前容器自己的标签，避免嵌套表单把父级标签列意外撑宽。
    (label) => label.closest(FORM_LABEL_ALIGNMENT_SELECTOR) === form,
  );
}

function getLabelContentWidth(label: HTMLLabelElement): number {
  const range = document.createRange();
  range.selectNodeContents(label);
  // Ant Design 的必填星号和冒号由伪元素绘制，不包含在 Range 宽度中。
  // 仅按文字内容测量，不能读取已被变量撑宽的 scrollWidth，否则动态表单每次刷新都会继续放大标签列。
  const contentWidth = Math.ceil(range.getBoundingClientRect().width + 10);
  return Math.min(160, Math.max(56, contentWidth));
}

function alignFormLabels() {
  const forms = new Set<HTMLElement>(
    Array.from(
      document.querySelectorAll<HTMLElement>(FORM_LABEL_ALIGNMENT_SELECTOR),
    ),
  );

  for (const form of forms) {
    const labelWidth = Math.max(
      0,
      ...getFormLabels(form).map(getLabelContentWidth),
    );

    if (labelWidth > 0) {
      form.style.setProperty('--adpulse-form-label-width', `${labelWidth}px`);
    }
  }
}

/** Install once after the application mounts so dynamic dialogs are covered. */
export function installFormLabelAlignment() {
  let frameId = 0;
  const scheduleAlignment = () => {
    cancelAnimationFrame(frameId);
    frameId = requestAnimationFrame(alignFormLabels);
  };

  const observer = new MutationObserver(scheduleAlignment);
  observer.observe(document.body, {
    characterData: true,
    childList: true,
    subtree: true,
  });
  window.addEventListener('resize', scheduleAlignment, { passive: true });
  window.addEventListener('adpulse:ui-scale-change', scheduleAlignment);
  document.fonts?.ready.then(scheduleAlignment).catch(() => undefined);
  scheduleAlignment();
}
