<script lang="ts" setup>
import type { SyncTargetAccount } from '#/api';

import { computed, ref, watch } from 'vue';

import { Button, Input, message, Modal } from 'ant-design-vue';

import { syncPersonalAccount } from '#/api';

import IdParseButton from './parts/IdParseButton.vue';

interface Props {
  open: boolean;
  personalId: string;
  personalType: 'personal' | 'system';
}

interface Emits {
  (e: 'update:open', value: boolean): void;
}

interface AccountRow {
  account: string;
  pixels: string[];
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const rows = ref<AccountRow[]>([{ account: '', pixels: [''] }]);
const pageInputs = ref<string[]>(['']);
const submitting = ref(false);

watch(
  () => props.open,
  (val) => {
    if (val) {
      rows.value = [{ account: '', pixels: [''] }];
      pageInputs.value = [''];
    }
  },
);

const removeRow = (index: number) => {
  rows.value.splice(index, 1);
};

// 最后一行户有内容时自动补一行空行
const handleAccountInput = (index: number) => {
  if (index === rows.value.length - 1 && rows.value[index]!.account.trim()) {
    rows.value.push({ account: '', pixels: [''] });
  }
};

// 列表末尾有内容时自动补一个空输入
const autoExtend = (list: string[]) => {
  if (list.at(-1)!.trim()) {
    list.push('');
  }
};

// 粘贴多个 ID 时拆成多行
const handleMultiPaste = (
  list: string[],
  index: number,
  event: ClipboardEvent,
) => {
  const ids = event.clipboardData?.getData('text').match(/\d{10,}/g) ?? [];
  if (ids.length <= 1) return;
  event.preventDefault();
  list.splice(index, 1, ...ids);
  autoExtend(list);
};

// 解析出的 ID 合并进列表(去重,保持末尾空行)
const mergeIds = (list: string[], ids: string[]) => {
  const existing = new Set(list.map((item) => item.trim()).filter(Boolean));
  const fresh = ids.filter((id) => !existing.has(id));
  list.splice(
    0,
    list.length,
    ...list.filter((item) => item.trim()),
    ...fresh,
    '',
  );
  message.success(`已加入 ${fresh.length} 个 ID`);
};

const handleAccountsParsed = (ids: string[]) => {
  const existing = new Set(
    rows.value.map((row) => row.account.trim()).filter(Boolean),
  );
  const fresh = ids
    .filter((id) => !existing.has(id))
    .map((id) => ({ account: id, pixels: [''] }));
  const filled = rows.value.filter(
    (row) => row.account.trim() || row.pixels.some((pixel) => pixel.trim()),
  );
  rows.value = [...filled, ...fresh, { account: '', pixels: [''] }];
  message.success(`已加入 ${fresh.length} 个账户`);
};

const handleOk = async () => {
  const filled = rows.value.map((row) => ({
    account: row.account.trim().replace(/^act_/, ''),
    pixels: row.pixels.map((pixel) => pixel.trim()).filter(Boolean),
  }));
  const badRow = filled.findIndex(
    (row) => !row.account && row.pixels.length > 0,
  );
  if (badRow !== -1) {
    message.warning(`第 ${badRow + 1} 行填了像素但没填户`);
    return;
  }
  const accounts: SyncTargetAccount[] = filled
    .filter((row) => row.account)
    .map((row) => ({ account_id: row.account, pixel_ids: row.pixels }));
  const page_ids = pageInputs.value.map((item) => item.trim()).filter(Boolean);
  if (accounts.length === 0 && page_ids.length === 0) {
    message.warning('请至少填写一个户或主页');
    return;
  }
  submitting.value = true;
  try {
    await syncPersonalAccount(props.personalId, props.personalType, {
      accounts,
      page_ids,
    });
    message.success('定向同步任务提交成功');
    modalOpen.value = false;
  } catch {
    message.error('提交失败');
  } finally {
    submitting.value = false;
  }
};
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    :confirm-loading="submitting"
    title="定向同步"
    width="680px"
    ok-text="提交"
    cancel-text="取消"
    @ok="handleOk"
  >
    <div class="space-y-4 py-2">
      <div>
        <div class="mb-1 flex items-center justify-between">
          <span class="text-sm">
            户 + 像素
            <span class="text-xs text-gray-400">
              （右侧像素合并进同行的户；留空则只拉户信息）
            </span>
          </span>
          <IdParseButton label="批量添加账户" @parsed="handleAccountsParsed" />
        </div>
        <div class="space-y-2">
          <div
            v-for="(row, index) in rows"
            :key="index"
            class="grid grid-cols-1 items-start gap-2 rounded border border-gray-200 p-2 sm:grid-cols-[1fr_1fr_max-content] dark:border-gray-700"
          >
            <Input
              v-model:value="row.account"
              placeholder="户ID"
              @input="handleAccountInput(index)"
            />
            <div class="space-y-1">
              <div
                v-for="(_, pixelIndex) in row.pixels"
                :key="pixelIndex"
                class="flex items-center gap-1"
              >
                <Input
                  v-model:value="row.pixels[pixelIndex]"
                  placeholder="像素ID"
                  @input="autoExtend(row.pixels)"
                  @paste="handleMultiPaste(row.pixels, pixelIndex, $event)"
                />
                <Button
                  v-if="pixelIndex < row.pixels.length - 1"
                  type="text"
                  danger
                  @click="row.pixels.splice(pixelIndex, 1)"
                >
                  ✕
                </Button>
              </div>
              <div class="text-right">
                <IdParseButton
                  label="批量添加像素"
                  @parsed="(ids) => mergeIds(row.pixels, ids)"
                />
              </div>
            </div>
            <Button
              v-if="rows.length > 1"
              type="text"
              size="small"
              danger
              @click="removeRow(index)"
            >
              删除
            </Button>
          </div>
        </div>
      </div>
      <div>
        <div class="mb-1 flex items-center justify-between">
          <span class="text-sm">主页</span>
          <IdParseButton
            label="批量添加主页"
            @parsed="(ids) => mergeIds(pageInputs, ids)"
          />
        </div>
        <div class="space-y-1">
          <div
            v-for="(_, index) in pageInputs"
            :key="index"
            class="flex items-center gap-1"
          >
            <Input
              v-model:value="pageInputs[index]"
              placeholder="主页ID"
              @input="autoExtend(pageInputs)"
              @paste="handleMultiPaste(pageInputs, index, $event)"
            />
            <Button
              v-if="index < pageInputs.length - 1"
              type="text"
              danger
              @click="pageInputs.splice(index, 1)"
            >
              ✕
            </Button>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
