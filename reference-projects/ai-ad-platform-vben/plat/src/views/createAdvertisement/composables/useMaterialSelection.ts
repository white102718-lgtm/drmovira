import type { MaterialItem } from '../types';

import { computed, ref } from 'vue';

const view1SelectedIds = new Set<string>();
const view2SelectedIds = new Set<string>();
const view1SelectedRows = new Map<string, MaterialItem>();
const view2SelectedRows = new Map<string, MaterialItem>();
const view1Count = ref(0);
const view2Count = ref(0);

export function useMaterialSelection() {
  function getMaterialId(item: MaterialItem, view: 'view1' | 'view2'): string {
    return view === 'view1'
      ? String(item.id || item.key || item.materialId)
      : String(item.id || item.key || item.filename);
  }

  function syncSelectionsFromGrid(
    view: 'view1' | 'view2',
    rows: MaterialItem[],
  ): void {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    const rowMap = view === 'view1' ? view1SelectedRows : view2SelectedRows;
    selectedIds.clear();
    rowMap.clear();
    rows.forEach((row) => {
      const id = getMaterialId(row, view);
      selectedIds.add(id);
      rowMap.set(id, row);
    });
    updateCount(view);
  }

  function updatePageSelections(
    view: 'view1' | 'view2',
    allPageRows: MaterialItem[],
    selectedRows: MaterialItem[],
  ): void {
    const store = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    const rowMap = view === 'view1' ? view1SelectedRows : view2SelectedRows;
    const selectedSet = new Set(
      selectedRows.map((row) => getMaterialId(row, view)),
    );
    allPageRows.forEach((row) => {
      const id = getMaterialId(row, view);
      if (selectedSet.has(id)) {
        store.add(id);
        rowMap.set(id, row);
      } else {
        store.delete(id);
        rowMap.delete(id);
      }
    });
    updateCount(view);
  }

  function addSelection(view: 'view1' | 'view2', id: string): void {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    selectedIds.add(id);
    updateCount(view);
  }

  function removeSelection(view: 'view1' | 'view2', id: string): void {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    const rowMap = view === 'view1' ? view1SelectedRows : view2SelectedRows;
    selectedIds.delete(id);
    rowMap.delete(id);
    updateCount(view);
  }

  function updateCount(view: 'view1' | 'view2'): void {
    if (view === 'view1') {
      view1Count.value = view1SelectedIds.size;
    } else {
      view2Count.value = view2SelectedIds.size;
    }
  }

  function getSelectionCount(view: 'view1' | 'view2'): number {
    return view === 'view1' ? view1Count.value : view2Count.value;
  }

  function hasSelection(view: 'view1' | 'view2', id: string): boolean {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    return selectedIds.has(id);
  }

  function clearSelections(view: 'view1' | 'view2'): void {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    const rowMap = view === 'view1' ? view1SelectedRows : view2SelectedRows;
    selectedIds.clear();
    rowMap.clear();
    updateCount(view);
  }

  function clearAllSelections(): void {
    view1SelectedIds.clear();
    view2SelectedIds.clear();
    view1SelectedRows.clear();
    view2SelectedRows.clear();
    view1Count.value = 0;
    view2Count.value = 0;
  }

  function getSelectedIds(view: 'view1' | 'view2'): string[] {
    const selectedIds = view === 'view1' ? view1SelectedIds : view2SelectedIds;
    return [...selectedIds];
  }

  function getSelectedRows(view: 'view1' | 'view2'): MaterialItem[] {
    const rowMap = view === 'view1' ? view1SelectedRows : view2SelectedRows;
    return [...rowMap.values()];
  }

  const totalCount = computed(() => view1Count.value + view2Count.value);

  return {
    view1SelectedIds,
    view2SelectedIds,
    getMaterialId,
    syncSelectionsFromGrid,
    updatePageSelections,
    addSelection,
    removeSelection,
    getSelectionCount,
    hasSelection,
    clearSelections,
    clearAllSelections,
    getSelectedIds,
    getSelectedRows,
    totalCount,
  };
}
