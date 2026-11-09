import type { OrderFilters } from '../components/OrderFilterBar.vue';

function defaultFilters(defaultStatus?: string, sortBy?: string): OrderFilters {
  return {
    project: undefined,
    priority: [],
    type: undefined,
    status: defaultStatus ?? 'all',
    operator: undefined,
    department: undefined,
    keyword: '',
    sortOption: `${sortBy ?? 'created_at'}_desc`,
    designers: [],
    creativePlanners: [],
    country: undefined,
    isGreenMaterial: undefined,
  };
}

export function usePersistedFilters(storageKey: string, defaultStatus?: string, sortBy?: string) {
  function load(): OrderFilters {
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (!Object.prototype.hasOwnProperty.call(parsed, 'status')) {
          parsed.status = 'all';
        }
        if (!parsed.sortOption && parsed.sortOrder) {
          parsed.sortOption = `${sortBy ?? 'created_at'}_${parsed.sortOrder}`;
        }
        return { ...defaultFilters(defaultStatus, sortBy), ...parsed };
      }
    } catch {}
    return defaultFilters(defaultStatus, sortBy);
  }

  function save(filters: OrderFilters) {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({ ...filters, status: filters.status ?? 'all' }));
    } catch {}
  }

  return { initialFilters: load(), save };
}
