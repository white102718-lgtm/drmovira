import type { RequestClientConfig } from '@vben/request';

import { backendClient } from '#/api/request';

export namespace SystemDictionaryApi {
  export type Status = 0 | 1;

  export interface DictionaryType {
    createdAt: string;
    dictCode: string;
    dictName: string;
    id: string;
    remark?: null | string;
    status: Status;
    updatedAt: string;
  }

  export interface DictionaryItem {
    createdAt: string;
    dictTypeId: string;
    id: string;
    label: string;
    remark?: null | string;
    sortOrder: number;
    status: Status;
    updatedAt: string;
    value: string;
  }

  export interface DictionaryDetail {
    items: DictionaryItem[];
    type: DictionaryType;
  }

  export interface TypeSaveRequest {
    dictCode: string;
    dictName: string;
    remark?: string;
    status: Status;
  }

  export interface ItemSaveRequest {
    label: string;
    remark?: string;
    sortOrder?: number;
    status: Status;
    value: string;
  }

  export interface Option {
    label: string;
    value: string;
  }
}

function getDictionaryTypes(params?: { keyword?: string; status?: number }) {
  return backendClient.get<SystemDictionaryApi.DictionaryType[]>(
    '/dictionaries',
    { params },
  );
}

function getDictionaryDetail(id: string) {
  return backendClient.get<SystemDictionaryApi.DictionaryDetail>(
    `/dictionaries/types/${id}`,
  );
}

function createDictionaryType(data: SystemDictionaryApi.TypeSaveRequest) {
  return backendClient.post<SystemDictionaryApi.DictionaryDetail>(
    '/dictionaries/types',
    data,
  );
}

function updateDictionaryType(
  id: string,
  data: SystemDictionaryApi.TypeSaveRequest,
) {
  return backendClient.put<SystemDictionaryApi.DictionaryDetail>(
    `/dictionaries/types/${id}`,
    data,
  );
}

function deleteDictionaryType(id: string) {
  return backendClient.delete(`/dictionaries/types/${id}`);
}

function createDictionaryItem(
  dictTypeId: string,
  data: SystemDictionaryApi.ItemSaveRequest,
) {
  return backendClient.post<SystemDictionaryApi.DictionaryItem>(
    `/dictionaries/types/${dictTypeId}/items`,
    data,
  );
}

function updateDictionaryItem(
  id: string,
  data: SystemDictionaryApi.ItemSaveRequest,
) {
  return backendClient.put<SystemDictionaryApi.DictionaryItem>(
    `/dictionaries/items/${id}`,
    data,
  );
}

function deleteDictionaryItem(id: string) {
  return backendClient.delete(`/dictionaries/items/${id}`);
}

function getDictionaryOptions(dictCode: string, config?: RequestClientConfig) {
  return backendClient.get<SystemDictionaryApi.Option[]>(
    `/dictionaries/${encodeURIComponent(dictCode)}/options`,
    config,
  );
}

export {
  createDictionaryItem,
  createDictionaryType,
  deleteDictionaryItem,
  deleteDictionaryType,
  getDictionaryDetail,
  getDictionaryOptions,
  getDictionaryTypes,
  updateDictionaryItem,
  updateDictionaryType,
};
