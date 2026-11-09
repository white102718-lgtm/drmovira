<script lang="ts" setup>
import type { AdvertiserItem } from '../types';

import type { FbAssetRef } from '#/api';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { Button, Input, message, Modal, Select, Table } from 'ant-design-vue';

import { getSyncProgress, syncPersonalAccount } from '#/api';
import AssetMultiSelect from '#/views/management/fb-resource/components/parts/AssetMultiSelect.vue';
import OverflowTooltip from '../../components/OverflowTooltip.vue';
import { useAdvertiser } from '../composables/useAdvertiser';

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// 批量修改
const batchPersonAccountName = ref<string | undefined>(undefined);
const batchPublicPageId = ref<string | undefined>(undefined);
const batchPixelId = ref<string | undefined>(undefined);

interface Props {
  open: boolean;
  taskData?: any;
  taskIndex?: number;
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'confirm', advertisers: AdvertiserItem[]): void;
}

const {
  advertiserSearchName,
  advertiserSearchAccountId,
  advertiserSearchStatus,
  advertiserSearchPixel,
  advertiserSearchPersonAccount,
  selectedAdvertisers,
  advertisers,
  filteredAdvertisers,
  pixelSearchOptions,
  pixelSearchLoading,
  loadPixelOptions,
  handlePixelSearch,
  personAccountFilterOptions,
  advertiserPage,
  advertiserPageSize,
  advertiserTotal,
  loadPageAccounts,
  resetSelection,
  filterOption,
  handleSelectionChange,
  handlePersonAccountChange,
  tableLoading,
  applyBatchPersonAccountById,
  applyBatchPublicPageById,
  applyBatchPixelById,
} = useAdvertiser();

const parsedAccounts = ref<FbAssetRef[]>([]);

watch(parsedAccounts, (accounts) => {
  advertiserSearchName.value = accounts
    .map((a) => a.name)
    .filter(Boolean)
    .join(',');
  advertiserSearchAccountId.value = accounts.map((a) => a.id).join(',');
});

const personalAuthColumns = [
  { title: '广告账户名称', dataIndex: 'accountName', width: 280 },
  { title: '广告账户ID', dataIndex: 'accountId', width: 150 },
  { title: '个号', key: 'personAccountSelect', width: 160 },
  { title: '公共主页', key: 'publicPageSelect', width: 220 },
  { title: '像素', key: 'pixelSelect', width: 220 },
  { title: '账户限额', dataIndex: 'spendCap', width: 100 },
  { title: '账户余额', dataIndex: 'balance', width: 100 },
  { title: '状态', key: 'statusBadge', width: 80 },
];

const modalOpen = ref(false);

watch(
  () => props.open,
  (newVal) => {
    if (newVal) {
      modalOpen.value = true;
      if (props.taskData) {
        // 不展示预载数据,打开即按代理线像素自动搜索;未配像素则查全部
        const pixelName =
          props.taskData.pixel_name ||
          props.taskData.pixelName ||
          props.taskData.pixel;
        advertiserSearchPixel.value = pixelName || '全部';
        handleTablePageChange(1);
      }
    } else {
      stopSyncPolling();
    }
  },
);

// 获取过滤后的公共主页选项（根据选中的个号）
function getFilteredPublicPages(record: any) {
  if (!record.publicPageOptions) {
    return [];
  }
  if (!record.selectedPersonAccount) {
    return [];
  }
  return record.publicPageOptions.filter(
    (page: any) => page.personName === record.selectedPersonAccount,
  );
}

// 批量公共主页：主页归属个号，只列选中个号名下的，不跨个号共用
const batchPublicPageOptions = computed(() => {
  if (!batchPersonAccountName.value) return [];
  const map = new Map<string, any>();
  advertisers.value.forEach((adv) => {
    adv.publicPageOptions?.forEach((opt: any) => {
      if (opt.personName !== batchPersonAccountName.value) return;
      if (opt.id && !map.has(opt.id)) {
        map.set(opt.id, opt);
      }
    });
  });
  return [...map.values()];
});

// 批量像素选项
const allPixelOptions = computed(() => {
  const map = new Map<string, string>();
  advertisers.value.forEach((adv) => {
    adv.pixelOptions?.forEach((opt: any) => {
      if (opt.id && opt.name) map.set(opt.id, opt.name);
    });
  });
  return [...map.entries()].map(([id, name]) => ({ id, name }));
});

function handleConfirm() {
  if (selectedAdvertisers.value.length === 0) {
    message.warning('请至少选择一个广告账户');
    return;
  }

  const selectedData = advertisers.value.filter((adv) =>
    selectedAdvertisers.value.includes(adv.id || ''),
  );

  const result: AdvertiserItem[] = selectedData.map((adv) => {
    const selectedPageOption = adv.publicPageOptions?.find(
      (opt: any) => opt.id === adv.selectedPublicPage,
    );
    const selectedPixelOption = adv.pixelOptions?.find(
      (opt: any) => opt.id === adv.selectedPixel,
    );
    return {
      ...adv,
      id: adv.id || '',
      name: adv.accountName || adv.taskName || adv.projectName || '',
      account: adv.accountId || '',
      status: adv.status || '-',
      publicPage: selectedPageOption?.name,
      pixel: selectedPixelOption?.name,
      personAccountName: adv.selectedPersonAccount,
      personId: adv.selectedPersonId,
    };
  });

  emit('confirm', result);
  handleCancel();
}

function handleCancel() {
  resetSelection();
  parsedAccounts.value = [];
  batchPersonAccountName.value = undefined;
  batchPublicPageId.value = undefined;
  batchPixelId.value = undefined;
  stopSyncPolling();
  modalOpen.value = false;
  emit('update:open', false);
}

onBeforeUnmount(stopSyncPolling);

function handlePersonAccountFilterChange(val: any) {
  advertiserSearchPersonAccount.value = val;
}

async function handleTablePageChange(page: number, pageSize?: number) {
  if (pageSize && pageSize !== advertiserPageSize.value) {
    advertiserPageSize.value = pageSize;
    page = 1;
  }
  await loadPageAccounts(props.taskData, page, {
    account_name: advertiserSearchName.value
      ? advertiserSearchName.value.split(',')
      : undefined,
    account_id: advertiserSearchAccountId.value
      ? advertiserSearchAccountId.value.split(',')
      : undefined,
    pixel_name_filter:
      advertiserSearchPixel.value === '全部'
        ? undefined
        : advertiserSearchPixel.value,
    status:
      advertiserSearchStatus.value === '全部'
        ? undefined
        : advertiserSearchStatus.value,
  });
}

function handleAccountIdInput(e: any) {
  advertiserSearchAccountId.value = e.target?.value ?? e;
}

// 像素筛选：选中/清除即触发后端搜索
function handlePixelFilterSelect(val: any) {
  advertiserSearchPixel.value = val || '全部';
  handleTablePageChange(1);
}

function triggerBackendSearch() {
  handleTablePageChange(1);
}

// 批量个号改变时清空批量主页选择
function handleBatchPersonAccountChange(val: any) {
  batchPersonAccountName.value = val as string | undefined;
  batchPublicPageId.value = undefined;
}

// 批量个号 -> 资产同步
const SYNC_POLL_INTERVAL = 3000;

const SYNC_NO_DATA_MESSAGE = '暂无同步资产数据';

// syncingPersonIds 驱动按钮状态
const syncingPersonIds = ref<Set<string>>(new Set());
const syncPersonNameMap = new Map<string, string>();
// 记下每个个号最近一次真实拿到的进度，用于在进度接口回"暂无同步资产数据"时，
// 区分是"确实同步过、数据被后端清掉了（视为已完成）"还是"压根还没起量"
const lastSeenProgress = new Map<
  string,
  { processed: number; total: number }
>();
const syncSubmitting = ref(false);
let syncPollTimer: ReturnType<typeof setInterval> | null = null;

function markPersonSyncDone(id: string) {
  message.success(`个号「${syncPersonNameMap.get(id) || id}」资产同步已完成`);
  syncingPersonIds.value.delete(id);
  lastSeenProgress.delete(id);
}

function findPersonIdByName(personName?: string): string | undefined {
  if (!personName) return undefined;
  for (const adv of advertisers.value) {
    const matched = adv.personAccountOptions?.find(
      (p: any) => p.name === personName,
    );
    if (matched?.person_id) return matched.person_id;
  }
  return undefined;
}

const batchSyncPersonId = computed(() =>
  findPersonIdByName(batchPersonAccountName.value),
);

// 提交后即入 syncingPersonIds，直到进度回报 processed === total 才移除
const batchSyncInProgress = computed(() => {
  const id = batchSyncPersonId.value;
  return !!id && syncingPersonIds.value.has(id);
});

function stopSyncPolling() {
  if (syncPollTimer) {
    clearInterval(syncPollTimer);
    syncPollTimer = null;
  }
}

function startSyncPolling() {
  if (syncPollTimer || syncingPersonIds.value.size === 0) return;
  syncPollTimer = setInterval(pollSyncProgress, SYNC_POLL_INTERVAL);
}

async function pollSyncProgress() {
  const ids = [...syncingPersonIds.value];
  if (ids.length === 0) {
    stopSyncPolling();
    return;
  }
  try {
    const res = await getSyncProgress(ids);
    if (typeof res === 'string') {
      if (res === SYNC_NO_DATA_MESSAGE) {
        ids.forEach((id) => {
          if (lastSeenProgress.has(id)) markPersonSyncDone(id);
        });
      } else {
        message.warning(res);
        // 进度接口本身不可用，无法再判断这些个号是否同步完成，直接复位按钮状态
        ids.forEach((id) => {
          syncingPersonIds.value.delete(id);
          lastSeenProgress.delete(id);
        });
      }
    } else {
      ids.forEach((id) => {
        const p = res[id];
        if (!p) return;
        if (p.processed === p.total) {
          markPersonSyncDone(id);
        } else {
          lastSeenProgress.set(id, p);
        }
      });
    }
    if (syncingPersonIds.value.size === 0) {
      stopSyncPolling();
    }
  } catch {}
}

async function handleBatchSync() {
  const personName = batchPersonAccountName.value;
  if (!personName) {
    message.warning('请先选择要同步的个号');
    return;
  }
  const personId = batchSyncPersonId.value;
  if (!personId) {
    message.warning('未找到该个号对应的标识，无法同步');
    return;
  }
  syncSubmitting.value = true;
  try {
    await syncPersonalAccount(personId, 'personal');
    message.success('同步任务提交成功');
    syncingPersonIds.value.add(personId);
    syncPersonNameMap.set(personId, personName);
    await pollSyncProgress();
    startSyncPolling();
  } catch {
    message.error('同步失败');
  } finally {
    syncSubmitting.value = false;
  }
}

function applyBatchAll() {
  if (selectedAdvertisers.value.length === 0) {
    message.warning('请先选择要应用的行');
    return;
  }
  if (
    !batchPersonAccountName.value &&
    !batchPublicPageId.value &&
    !batchPixelId.value
  ) {
    message.warning('请至少选择一项修改内容');
    return;
  }
  if (batchPersonAccountName.value) {
    const r = applyBatchPersonAccountById(
      batchPersonAccountName.value,
      selectedAdvertisers.value,
    );
    r.success ? message.success(r.message) : message.warning(r.message);
  }
  if (batchPublicPageId.value) {
    const r = applyBatchPublicPageById(
      batchPublicPageId.value,
      selectedAdvertisers.value,
    );
    r.success ? message.success(r.message) : message.warning(r.message);
  }
  if (batchPixelId.value) {
    const r = applyBatchPixelById(
      batchPixelId.value,
      selectedAdvertisers.value,
    );
    r.success ? message.success(r.message) : message.warning(r.message);
  }
}
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    title="选择广告账户"
    width="1450px"
    class="advertiser-selection-modal"
    :destroy-on-close="true"
    @cancel="handleCancel"
  >
    <div class="mb-4 flex flex-col items-start gap-4 rounded-lg bg-gray-50 p-4">
      <div class="flex items-center gap-4">
        <span
          class="whitespace-nowrap border-r border-gray-300 pr-3 text-sm font-semibold text-gray-500"
          >筛选条件</span
        >
        <!-- 广告账户名称 -->
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">广告账户名称:</span>
          <Input
            v-model:value="advertiserSearchName"
            class="ant-input"
            allow-clear
            placeholder="请输入"
            style="width: 170px"
            @press-enter="triggerBackendSearch"
          />
        </div>

        <!-- 广告账户ID -->
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">广告账户ID:</span>
          <Input
            :value="advertiserSearchAccountId"
            allow-clear
            placeholder="请输入"
            style="width: 170px"
            @input="handleAccountIdInput"
            @press-enter="triggerBackendSearch"
          />
          <AssetMultiSelect
            v-model="parsedAccounts"
            asset-type="ad_account"
            button-type="primary"
            hide-search
            placeholder="解析账户ID"
          />
        </div>

        <!-- 个号筛选 -->
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">个号:</span>
          <Select
            :value="advertiserSearchPersonAccount"
            style="width: 150px"
            show-search
            :filter-option="filterOption"
            @change="handlePersonAccountFilterChange"
          >
            <Select.Option value="全部">全部</Select.Option>
            <Select.Option
              v-for="person in personAccountFilterOptions"
              :key="person"
              :value="person"
              :label="person"
            >
              {{ person }}
            </Select.Option>
          </Select>
        </div>

        <!-- 像素筛选（后端模糊搜索） -->
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">像素:</span>
          <Select
            :value="advertiserSearchPixel"
            style="width: 160px"
            show-search
            allow-clear
            :loading="pixelSearchLoading"
            :filter-option="false"
            @dropdown-visible-change="(open) => open && loadPixelOptions()"
            @search="handlePixelSearch"
            @change="handlePixelFilterSelect"
          >
            <Select.Option value="全部">全部</Select.Option>
            <Select.Option
              v-for="pixel in pixelSearchOptions"
              :key="pixel"
              :value="pixel"
              :label="pixel"
            >
              <OverflowTooltip :text="pixel" />
            </Select.Option>
          </Select>
        </div>

        <!-- 状态 -->
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">状态:</span>
          <Select v-model:value="advertiserSearchStatus" style="width: 100px">
            <Select.Option value="全部">全部</Select.Option>
            <Select.Option value="活跃">活跃</Select.Option>
            <Select.Option value="异常">异常</Select.Option>
          </Select>
        </div>

        <Button type="primary" @click="triggerBackendSearch">搜索</Button>
      </div>

      <div class="flex items-center gap-3">
        <span
          class="whitespace-nowrap border-r border-gray-300 pr-3 text-sm font-semibold text-gray-500"
          >批量修改</span
        >

        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">个号:</span>
          <Select
            :value="batchPersonAccountName"
            style="width: 150px"
            show-search
            allow-clear
            :filter-option="filterOption"
            placeholder="请选择个号"
            @change="handleBatchPersonAccountChange"
          >
            <Select.Option
              v-for="person in personAccountFilterOptions"
              :key="person"
              :value="person"
              :label="person"
            >
              {{ person }}
            </Select.Option>
          </Select>
          <Button
            :disabled="!batchPersonAccountName || batchSyncInProgress"
            :loading="syncSubmitting || batchSyncInProgress"
            @click="handleBatchSync"
          >
            {{ batchSyncInProgress ? '同步中' : '同步资产' }}
          </Button>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">公共主页:</span>
          <Select
            v-model:value="batchPublicPageId"
            style="width: 160px"
            show-search
            allow-clear
            :filter-option="filterOption"
            :disabled="!batchPersonAccountName"
            :placeholder="
              batchPersonAccountName ? '请选择主页' : '请先选择个号'
            "
          >
            <Select.Option
              v-for="opt in batchPublicPageOptions"
              :key="opt.id"
              :value="opt.id"
              :label="opt.name"
            >
              <div style="display: flex; gap: 6px; align-items: center">
                <img
                  v-if="opt.picture"
                  alt=""
                  :src="opt.picture"
                  style="
                    flex-shrink: 0;
                    width: 18px;
                    height: 18px;
                    object-fit: cover;
                    border-radius: 50%;
                  "
                />
                <OverflowTooltip :text="opt.name" />
              </div>
            </Select.Option>
          </Select>
        </div>

        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-700">像素:</span>
          <Select
            v-model:value="batchPixelId"
            style="width: 160px"
            show-search
            allow-clear
            :filter-option="filterOption"
            placeholder="请选择像素"
          >
            <Select.Option
              v-for="opt in allPixelOptions"
              :key="opt.id"
              :value="opt.id"
              :label="opt.name"
            >
              <OverflowTooltip :text="opt.name" />
            </Select.Option>
          </Select>
        </div>

        <Button type="primary" @click="applyBatchAll">
          修改{{
            selectedAdvertisers.length > 0
              ? `(${selectedAdvertisers.length})`
              : ''
          }}
        </Button>
      </div>
    </div>

    <Table
      :columns="personalAuthColumns"
      :data-source="filteredAdvertisers"
      :loading="tableLoading"
      :pagination="{
        current: advertiserPage,
        pageSize: advertiserPageSize,
        total: advertiserTotal,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 个账户`,
        onChange: handleTablePageChange,
      }"
      :row-selection="{
        selectedRowKeys: selectedAdvertisers,
        onChange: handleSelectionChange,
      }"
      :scroll="{ x: 'max-content', y: 'calc(85vh - 350px)' }"
      row-key="id"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'personAccountSelect'">
          <Select
            :value="record.selectedPersonAccount"
            style="width: 100%"
            show-search
            allow-clear
            :filter-option="filterOption"
            placeholder="请选择个号"
            @change="handlePersonAccountChange(record, $event)"
          >
            <Select.Option
              v-for="person in record.personAccountOptions"
              :key="person.name"
              :value="person.name"
              :label="person.name"
            >
              {{ person.name }}
            </Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'publicPageSelect'">
          <Select
            v-model:value="record.selectedPublicPage"
            style="width: 100%"
            show-search
            allow-clear
            :filter-option="filterOption"
            placeholder="请选择公共主页"
            :disabled="!record.selectedPersonAccount"
            :loading="!!record.pageLoading"
          >
            <Select.Option
              v-for="option in getFilteredPublicPages(record)"
              :key="option.id"
              :value="option.id"
              :label="option.name"
            >
              <div style="display: flex; gap: 6px; align-items: center">
                <img
                  v-if="option.picture"
                  alt=""
                  :src="option.picture"
                  style="
                    flex-shrink: 0;
                    width: 18px;
                    height: 18px;
                    object-fit: cover;
                    border-radius: 50%;
                  "
                />
                <OverflowTooltip :text="option.name" />
              </div>
            </Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'pixelSelect'">
          <Select
            v-model:value="record.selectedPixel"
            style="width: 100%"
            show-search
            allow-clear
            :filter-option="filterOption"
            placeholder="请选择像素"
          >
            <Select.Option
              v-for="option in record.pixelOptions"
              :key="option.id"
              :value="option.id"
              :label="option.name"
            >
              {{ option.name }}
            </Select.Option>
          </Select>
        </template>
        <template v-else-if="column.key === 'statusBadge'">
          <span
            :style="{
              color: (record.状态 || record.status || '活跃').includes('活跃')
                ? '#16a34a'
                : '#dc2626',
              fontWeight: 600,
            }"
          >
            {{ record.状态 || record.status || '-' }}
          </span>
        </template>
      </template>
    </Table>

    <template #footer>
      <div class="flex justify-end gap-3">
        <Button class="rounded-md" @click="handleCancel">取消</Button>
        <Button type="primary" class="rounded-md" @click="handleConfirm">
          确认
        </Button>
      </div>
    </template>
  </Modal>
</template>
