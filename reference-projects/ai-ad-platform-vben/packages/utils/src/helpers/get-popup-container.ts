const POPUP_SCROLL_HOST_SELECTOR = '[data-popup-scroll-host]';
const POPUP_SCROLL_HOST_CLASS = 'vben-popup-scroll-host';
const POPUP_CLOSE_ON_SCROLL_ATTRIBUTE = 'data-popup-close-on-scroll';
const SCROLLABLE_OVERFLOW_VALUES = new Set(['auto', 'overlay', 'scroll']);
const scrollCloseHosts = new WeakSet<HTMLElement>();

/** 判断元素是否建立了可滚动坐标系。 */
function isScrollableContainer(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element);
  return (
    SCROLLABLE_OVERFLOW_VALUES.has(style.overflowX) ||
    SCROLLABLE_OVERFLOW_VALUES.has(style.overflowY)
  );
}

/** 让静态滚动容器成为浮层绝对定位的包含块。 */
function preparePopupScrollHost(element: HTMLElement): HTMLElement {
  if (window.getComputedStyle(element).position === 'static') {
    element.classList.add(POPUP_SCROLL_HOST_CLASS);
  }
  return element;
}

/** 判断触发控件是否位于当前滚动容器的 sticky/fixed 定位子树中。 */
function hasStickyPositionedAncestor(
  node: HTMLElement,
  scrollHost: HTMLElement,
): boolean {
  let current: HTMLElement | null = node;

  while (current && current !== scrollHost) {
    const position = window.getComputedStyle(current).position;
    if (position === 'fixed' || position === 'sticky') {
      return true;
    }
    current = current.parentElement;
  }

  return false;
}

/**
 * sticky 触发器与其滚动容器不共享普通内容位移，纯 CSS 无法同时跟随两个坐标系。
 * 这类浮层挂到外层滚动宿主，并在内层容器滚动时关闭，避免菜单与按钮错位。
 */
function closePopupWhenStickyHostScrolls(
  scrollHost: HTMLElement,
  trigger: HTMLElement,
): void {
  trigger.setAttribute(POPUP_CLOSE_ON_SCROLL_ATTRIBUTE, '');

  if (scrollCloseHosts.has(scrollHost)) {
    return;
  }

  scrollCloseHosts.add(scrollHost);
  scrollHost.addEventListener(
    'scroll',
    () => {
      const openTrigger = scrollHost.querySelector<HTMLElement>(
        `[${POPUP_CLOSE_ON_SCROLL_ATTRIBUTE}].ant-dropdown-open, ` +
          `[${POPUP_CLOSE_ON_SCROLL_ATTRIBUTE}].ant-select-open, ` +
          `[${POPUP_CLOSE_ON_SCROLL_ATTRIBUTE}].ant-picker-open, ` +
          `[${POPUP_CLOSE_ON_SCROLL_ATTRIBUTE}].ant-popover-open, ` +
          `[${POPUP_CLOSE_ON_SCROLL_ATTRIBUTE}].ant-tooltip-open`,
      );
      if (!openTrigger) {
        return;
      }

      openTrigger.blur();
      document.body.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, cancelable: true }),
      );
    },
    { passive: true },
  );
}

/**
 * 为 Ant Design Vue 浮层选择与触发控件最近的真实滚动宿主。
 *
 * @remarks
 * Page、表格、Modal 和 Drawer 可能各自建立滚动坐标系。固定挂到 body 或
 * Vben 主内容节点会让内层滚动时的触发控件与浮层分离；挂到普通父节点又可能
 * 被卡片的 overflow:hidden 裁切。这里只选择显式宿主或真正可滚动的祖先，
 * 没有局部滚动上下文时才回退到 body。
 */
export function getPopupContainer(node?: HTMLElement): HTMLElement {
  let current = node?.parentElement;

  while (current && current !== document.body) {
    if (current.matches(POPUP_SCROLL_HOST_SELECTOR)) {
      return preparePopupScrollHost(current);
    }

    if (isScrollableContainer(current)) {
      if (node && hasStickyPositionedAncestor(node, current)) {
        closePopupWhenStickyHostScrolls(current, node);
        current = current.parentElement;
        continue;
      }
      return preparePopupScrollHost(current);
    }
    current = current.parentElement;
  }

  return document.body;
}
