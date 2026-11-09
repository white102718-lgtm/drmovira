import type { CSSProperties, Ref } from 'vue';

import type { AdDashboardField } from '#/domain/ad-dashboard';

import { computed, ref, watch } from 'vue';

/** 自动列宽可能被金额和汇总撑大，以实际表头宽度计算三处共用的固定偏移。 */
export function useAdDashboardFixedColumns(fields: Ref<AdDashboardField[]>) {
  const headerRow = ref<HTMLTableRowElement | null>(null);
  const offsets = ref<Record<string, number>>({});

  watch(
    [headerRow, fields],
    ([header, currentFields], _previous, onCleanup) => {
      if (!header) return;
      const viewport = header.closest('.ad-panel-table-viewport');
      const measure = () => {
        const widths = new Map(
          [...header.cells].map((cell) => [
            cell.dataset.fieldKey,
            cell.getBoundingClientRect().width,
          ]),
        );
        const fixedFields = currentFields.filter(
          (field) => field.fixed === 'left',
        );
        const widthOf = (field: AdDashboardField) =>
          widths.get(field.key) || field.width;
        const fixedWidth = fixedFields.reduce(
          (total, field) => total + widthOf(field),
          0,
        );
        // 窄视区给指标留下滚动空间；名称仍固定，避免固定区占满屏幕后无法查看其余列。
        const compact = Boolean(
          viewport?.clientWidth && fixedWidth + 160 > viewport.clientWidth,
        );
        const next: Record<string, number> = {};
        let left = 0;
        for (const field of fixedFields) {
          if (compact && field.key !== 'name') continue;
          next[field.key] = left;
          left += widthOf(field);
        }
        offsets.value = next;
      };
      const observer = new ResizeObserver(measure);
      for (const cell of header.cells) observer.observe(cell);
      if (viewport) observer.observe(viewport);
      measure();
      onCleanup(() => observer.disconnect());
    },
    { flush: 'post', immediate: true },
  );

  const lastFixedKey = computed(() => Object.keys(offsets.value).at(-1));
  function isFixed(field: AdDashboardField) {
    return offsets.value[field.key] !== undefined;
  }
  function cellStyle(field: AdDashboardField): CSSProperties {
    return {
      minWidth: `${field.width}px`,
      width: `${field.width}px`,
      left: isFixed(field) ? `${offsets.value[field.key]}px` : undefined,
    };
  }
  return { cellStyle, headerRow, isFixed, lastFixedKey };
}
