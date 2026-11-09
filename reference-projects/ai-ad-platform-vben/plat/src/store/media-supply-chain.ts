import { computed, ref } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

export const MEDIA_SUPPLY_CHAIN_STORAGE_KEY =
  'fusion:media-resource:supply-chain:v1';

export type SupplyChainCooperationMode = 'prepaid' | 'prepaid_actual';
export type SupplyChainStatus = 'active' | 'not_started' | 'suspended';

export interface SupplyChainCustomer {
  cooperationMode: SupplyChainCooperationMode;
  createWallet?: boolean;
  createdAt: string;
  endDate: string;
  id: string;
  name: string;
  note: string;
  policy: string;
  sheetUrl: string;
  startDate: string;
  status: SupplyChainStatus;
  updatedAt: string;
  walletAddress?: string;
}

export type SupplyChainCustomerInput = Omit<
  SupplyChainCustomer,
  'createdAt' | 'id' | 'updatedAt'
>;

interface SupplyChainStorageEnvelope {
  items: SupplyChainCustomer[];
  schemaVersion: 1;
}

const seedCustomers: readonly SupplyChainCustomer[] = [
  {
    cooperationMode: 'prepaid',
    createWallet: true,
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-0609',
    name: 'MPower0609-TGM-北美户群',
    note: '',
    policy: '1.5',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-0609',
    startDate: '2026-06-09',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
    walletAddress: '0x8Ff4A7d3cB7E1a9B40eC2f163b7A93Cd4A5e2F18',
  },
  {
    cooperationMode: 'prepaid',
    createWallet: true,
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-0605',
    name: 'Mpower0605-FB-越南户群',
    note: '',
    policy: '3+1',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-0605',
    startDate: '2026-06-05',
    status: 'not_started',
    updatedAt: '2026-06-16 14:03:20',
    walletAddress: '0x4b73D9E0A1cF94a8Ee2dB6725C3A8f19B64E0C2A',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-0518',
    name: 'MPower0518-FB-三方户群',
    note: '5月账单已更新',
    policy: '2+1 LuAnt 5%',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-0518',
    startDate: '2026-05-18',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-xh-0508',
    name: 'XH023群Mpower05-海外户群',
    note: '',
    policy: '2',
    sheetUrl: 'https://docs.example.com/spreadsheets/xh-0508',
    startDate: '2026-05-08',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid_actual',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-1125',
    name: 'MPower1125-B++F-中东户群',
    note: '5月没消耗',
    policy: '2',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-1125',
    startDate: '2026-11-25',
    status: 'suspended',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-dg-0114',
    name: '奈亚&DG-0114-FB户群',
    note: '5月账单已更新',
    policy: '3',
    sheetUrl: 'https://docs.example.com/spreadsheets/dg-0114',
    startDate: '2026-01-14',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid_actual',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-1119',
    name: 'MPower1119-A+++F-日本户群',
    note: '5月没消耗',
    policy: '1+1',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-1119',
    startDate: '2025-11-19',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-1219',
    name: 'MPower1219-MAD-欧洲户群',
    note: '5月账单已更新',
    policy: '1+1',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-1219',
    startDate: '2026-02-01',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-muyin-0123',
    name: '沐言科技&MPower01-东南亚户群',
    note: '5月账单已更新',
    policy: '3',
    sheetUrl: 'https://docs.example.com/spreadsheets/muyin-0123',
    startDate: '2026-01-23',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
  {
    cooperationMode: 'prepaid',
    createdAt: '2026-06-16 14:03:20',
    endDate: '',
    id: 'supply-mpower-0226',
    name: 'MPower0226-海外直客户群',
    note: '5月账单已更新',
    policy: '3+1',
    sheetUrl: 'https://docs.example.com/spreadsheets/mpower-0226',
    startDate: '2026-02-26',
    status: 'active',
    updatedAt: '2026-06-16 14:03:20',
  },
];

function cloneSeedCustomers(): SupplyChainCustomer[] {
  return seedCustomers.map((customer) => ({ ...customer }));
}

function dateTimeNow() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

function createWalletAddress() {
  const segment = () => Math.random().toString(16).slice(2).padEnd(8, '0');
  return `0x${segment()}${segment()}${segment()}${segment()}${segment()}`.slice(
    0,
    42,
  );
}

function isCooperationMode(
  value: unknown,
): value is SupplyChainCooperationMode {
  return ['prepaid', 'prepaid_actual'].includes(String(value));
}

function isStatus(value: unknown): value is SupplyChainStatus {
  return ['active', 'not_started', 'suspended'].includes(String(value));
}

function normalizeCustomer(value: unknown): SupplyChainCustomer | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const source = value as Partial<SupplyChainCustomer>;
  if (!source.id || !source.name?.trim()) return undefined;
  const seeded = seedCustomers.find((item) => item.id === source.id);
  const walletAddress =
    source.walletAddress?.trim() || seeded?.walletAddress || '';

  return {
    cooperationMode: isCooperationMode(source.cooperationMode)
      ? source.cooperationMode
      : 'prepaid',
    createWallet: Boolean(
      source.createWallet ?? source.walletAddress ?? seeded?.walletAddress,
    ),
    createdAt: source.createdAt || dateTimeNow(),
    endDate: source.endDate || '',
    id: source.id,
    name: source.name.trim(),
    note: source.note?.trim() || '',
    policy: source.policy?.trim() || '',
    sheetUrl: source.sheetUrl?.trim() || '',
    startDate: source.startDate || '',
    status: isStatus(source.status) ? source.status : 'not_started',
    updatedAt: source.updatedAt || source.createdAt || dateTimeNow(),
    walletAddress,
  };
}

function normalizeStoredCustomers(value: unknown): SupplyChainStorageEnvelope {
  const source = value as { items?: unknown } | undefined;
  const items = Array.isArray(value)
    ? value
    : Array.isArray(source?.items)
      ? source.items
      : undefined;

  return {
    items: items
      ? items
          .map((item) => normalizeCustomer(item))
          .filter((item): item is SupplyChainCustomer => item !== undefined)
      : cloneSeedCustomers(),
    schemaVersion: 1,
  };
}

function createCustomerId() {
  return `supply-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useMediaSupplyChainStore = defineStore(
  'media-supply-chain',
  () => {
    const stored = useStorage<unknown>(MEDIA_SUPPLY_CHAIN_STORAGE_KEY, {
      items: cloneSeedCustomers(),
      schemaVersion: 1,
    });
    const state = ref<SupplyChainStorageEnvelope>(
      normalizeStoredCustomers(stored.value),
    );

    stored.value = state.value;

    const customers = computed(() => state.value.items);

    function persist(items: SupplyChainCustomer[]) {
      state.value = { items, schemaVersion: 1 };
      stored.value = state.value;
    }

    function validate(input: SupplyChainCustomerInput) {
      const name = input.name.trim();
      if (!name) throw new Error('请输入客户群名');
      if (!input.cooperationMode) throw new Error('请选择合作模式');
      if (!input.status) throw new Error('请选择状态');
      return name;
    }

    function create(input: SupplyChainCustomerInput) {
      const name = validate(input);
      const duplicate = customers.value.some(
        (item) =>
          item.name.localeCompare(name, 'zh-CN', { sensitivity: 'base' }) === 0,
      );
      if (duplicate) throw new Error('客户群名已存在');

      const now = dateTimeNow();
      const createWallet = Boolean(input.createWallet);
      const customer: SupplyChainCustomer = {
        ...input,
        createWallet,
        createdAt: now,
        id: createCustomerId(),
        name,
        note: input.note.trim(),
        policy: input.policy.trim(),
        sheetUrl: input.sheetUrl.trim(),
        updatedAt: now,
        walletAddress: createWallet
          ? input.walletAddress?.trim() || createWalletAddress()
          : '',
      };
      persist([customer, ...customers.value]);
      return customer;
    }

    function update(id: string, input: SupplyChainCustomerInput) {
      const name = validate(input);
      const current = customers.value.find((item) => item.id === id);
      if (!current) throw new Error('该客户记录不存在或已删除');
      const duplicate = customers.value.some(
        (item) =>
          item.id !== id &&
          item.name.localeCompare(name, 'zh-CN', { sensitivity: 'base' }) === 0,
      );
      if (duplicate) throw new Error('客户群名已存在');

      const next: SupplyChainCustomer = {
        ...current,
        ...input,
        createWallet: Boolean(input.createWallet),
        name,
        note: input.note.trim(),
        policy: input.policy.trim(),
        sheetUrl: input.sheetUrl.trim(),
        updatedAt: dateTimeNow(),
        walletAddress: input.createWallet
          ? input.walletAddress?.trim() ||
            current.walletAddress ||
            createWalletAddress()
          : '',
      };
      persist(customers.value.map((item) => (item.id === id ? next : item)));
      return next;
    }

    function remove(id: string) {
      const next = customers.value.filter((item) => item.id !== id);
      if (next.length === customers.value.length) return false;
      persist(next);
      return true;
    }

    return { create, customers, remove, update };
  },
);
