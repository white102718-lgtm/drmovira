<script setup lang="ts">
import type { TableColumnsType, UploadProps } from 'ant-design-vue';
import type { AgencyLine } from '#/domain/agency-line';
import type { DeliveryTaskItem } from '#/domain/task/delivery-items';
import {
  Alert,
  Button,
  Input,
  Modal,
  Select,
  Table,
  Tag,
  Upload,
  message,
} from 'ant-design-vue';
import { computed, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { agencyLineService } from '#/domain/agency-line';
import {
  deliveryItemFields,
  emptyDeliveryItem,
  isDeliveryItemFieldRequired,
  parseDeliveryWorkbook,
} from '#/domain/task/delivery-items';
import StableUserSelect from '../../components/StableUserSelect.vue';

const props = defineProps<{
  readOnly?: boolean;
  operatorNames?: Record<string, string>;
  platforms?: string[];
  projectId?: string;
}>();
const items = defineModel<DeliveryTaskItem[]>({ default: () => [] });
const importing = ref(false);
const importModalOpen = ref(false);
const selectedImportFile = ref<File>();
const agencyLineModalOpen = ref(false);
const agencyLineLoading = ref(false);
const agencyLineKeyword = ref('');
const agencyLinePage = ref(1);
const agencyLinePageSize = ref(20);
const agencyLineTotal = ref(0);
const agencyLineRows = ref<AgencyLine[]>([]);
const selectedAgencyLineKeys = ref<string[]>([]);
const selectedAgencyLines = new Map<string, AgencyLine>();

const platformOptions = computed(() =>
  (props.platforms ?? []).map((platform) => ({
    label: platform,
    value: platform.toLowerCase(),
  })),
);

const agencyLineColumns: TableColumnsType<AgencyLine> = [
  { dataIndex: 'name', key: 'name', title: '代理线名称', width: 220 },
  { dataIndex: 'platform', key: 'platform', title: '投放平台', width: 120 },
  { dataIndex: 'type', key: 'type', title: '类型', width: 120 },
  { dataIndex: 'pixelName', key: 'pixelName', title: '像素名称', width: 180 },
  { dataIndex: 'pixelId', key: 'pixelId', title: '像素 ID', width: 180 },
  {
    dataIndex: 'optimizerName',
    key: 'optimizerName',
    title: '投手',
    width: 140,
  },
  {
    dataIndex: 'projectId',
    key: 'projectId',
    title: '所属项目 ID',
    width: 140,
  },
  { dataIndex: 'status', key: 'status', title: '状态', width: 100 },
];

const existingAgencyLineNames = computed(
  () =>
    new Set(
      items.value
        .map((item) => (item.agencyLineName ?? '').trim().toLowerCase())
        .filter(Boolean),
    ),
);

const agencyLineRowSelection = computed(() => ({
  getCheckboxProps: (record: AgencyLine) => ({
    disabled: existingAgencyLineNames.value.has(
      record.name.trim().toLowerCase(),
    ),
  }),
  onChange: (keys: Array<number | string>, rows: AgencyLine[]) => {
    selectedAgencyLineKeys.value = keys.map(String);
    for (const row of rows) selectedAgencyLines.set(row.id, row);
    const retained = new Set(selectedAgencyLineKeys.value);
    for (const key of selectedAgencyLines.keys()) {
      if (!retained.has(key)) selectedAgencyLines.delete(key);
    }
  },
  preserveSelectedRowKeys: true,
  selectedRowKeys: selectedAgencyLineKeys.value,
}));

async function downloadTemplate() {
  try {
    const { Workbook } = await import('exceljs');
    const workbook = new Workbook();
    const sheet = workbook.addWorksheet('投放任务明细');
    const columnWidths: Partial<Record<keyof DeliveryTaskItem, number>> = {
      agencyLineName: 26,
      cloakUrl: 48,
      deliveryUrl: 48,
      operatorId: 20,
      pixelId: 26,
      pixelName: 26,
      platform: 16,
      testCode: 24,
      token: 36,
      type: 18,
    };
    // 整列按文本生成，用户新增数据行时长 ID 也不会被 Excel 转成科学计数法。
    sheet.columns = deliveryItemFields.map(([key, label]) => ({
      header: label,
      key,
      style: { numFmt: '@' },
      width: columnWidths[key] ?? 20,
    }));
    sheet.views = [{ state: 'frozen', ySplit: 1 }];
    const bytes = new Uint8Array(await workbook.xlsx.writeBuffer());
    const url = URL.createObjectURL(
      new Blob([bytes], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = '投放任务明细模板.xlsx';
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    message.error('模板生成失败，请重试');
  }
}

const selectImportFile: UploadProps['beforeUpload'] = (file) => {
  if (!/\.(csv|xlsx)$/i.test(file.name)) {
    message.error('请选择 XLSX 或 CSV 文件');
    return Upload.LIST_IGNORE;
  }
  selectedImportFile.value = file;
  return Upload.LIST_IGNORE;
};

function openImportModal() {
  selectedImportFile.value = undefined;
  importModalOpen.value = true;
}

function closeImportModal() {
  if (importing.value) return;
  selectedImportFile.value = undefined;
  importModalOpen.value = false;
}

/** 所有有表头的工作表合并；确认且解析成功后才替换已填写内容。 */
async function confirmImport() {
  const file = selectedImportFile.value;
  if (!file) {
    message.warning('请先选择导入文件');
    return;
  }
  if (importing.value) return;
  importing.value = true;
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('导入文件不能超过 10 MB');
    const XLSX = await import('xlsx');
    const isCsv = file.name.toLowerCase().endsWith('.csv');
    const workbook = XLSX.read(
      isCsv ? await file.text() : await file.arrayBuffer(),
      {
        type: isCsv ? 'string' : 'array',
        raw: true,
      },
    );
    const parsed = parseDeliveryWorkbook(workbook, XLSX.utils);
    const invalidNameIndex = parsed.findIndex(
      (item) => !item.agencyLineName || item.agencyLineName.length > 80,
    );
    if (invalidNameIndex >= 0)
      throw new Error(
        `第 ${invalidNameIndex + 1} 行：请填写不超过 80 个字符的代理线名称`,
      );
    const allowedPlatforms = new Set(
      platformOptions.value.map((option) => option.value),
    );
    const names = new Set<string>();
    for (const [index, item] of parsed.entries()) {
      item.platform = item.platform.trim().toLowerCase();
      if (!allowedPlatforms.has(item.platform)) {
        throw new Error(`第 ${index + 1} 行：投放平台不在当前项目投放范围内`);
      }
      const name = item.agencyLineName.trim().toLowerCase();
      if (names.has(name)) {
        throw new Error(`第 ${index + 1} 行：同一任务中代理线不能重复`);
      }
      names.add(name);
    }
    if (items.value.length) {
      const replace = await new Promise<boolean>((resolve) =>
        Modal.confirm({
          title: '替换当前投放明细？',
          content: `导入的 ${parsed.length} 条明细将替换当前内容。`,
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        }),
      );
      if (!replace) return;
    }
    items.value = parsed;
    selectedImportFile.value = undefined;
    importModalOpen.value = false;
    message.success(`已导入 ${parsed.length} 条明细，请核对后提交`);
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '导入失败，请检查文件',
    );
  } finally {
    importing.value = false;
  }
}

async function loadAgencyLines() {
  agencyLineLoading.value = true;
  try {
    const result = await agencyLineService.list({
      keyword: agencyLineKeyword.value.trim() || undefined,
      page: agencyLinePage.value,
      pageSize: agencyLinePageSize.value,
      projectId: props.projectId,
    });
    agencyLineRows.value = result.items;
    agencyLineTotal.value = result.total;
    for (const row of result.items) {
      if (selectedAgencyLineKeys.value.includes(row.id)) {
        selectedAgencyLines.set(row.id, row);
      }
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : '代理线加载失败');
  } finally {
    agencyLineLoading.value = false;
  }
}

function openAgencyLineModal() {
  if (!props.projectId) {
    message.warning('请先选择关联项目');
    return;
  }
  agencyLineKeyword.value = '';
  agencyLinePage.value = 1;
  selectedAgencyLineKeys.value = [];
  selectedAgencyLines.clear();
  agencyLineModalOpen.value = true;
  void loadAgencyLines();
}

function searchAgencyLines() {
  agencyLinePage.value = 1;
  void loadAgencyLines();
}

function changeAgencyLinePage(pagination: {
  current?: number;
  pageSize?: number;
}) {
  agencyLinePage.value = pagination.current ?? 1;
  agencyLinePageSize.value = pagination.pageSize ?? 20;
  void loadAgencyLines();
}

function toDeliveryItem(line: AgencyLine): DeliveryTaskItem {
  return {
    agencyLineId: line.id,
    agencyLineName: line.name,
    cloakUrl: line.cloakUrl,
    deliveryUrl: line.deliveryUrl,
    operatorId: line.optimizerId ?? '',
    pixelId: line.pixelId,
    pixelName: line.pixelName,
    platform: line.platform.toLowerCase(),
    testCode: line.testCode,
    token: line.token,
    type: line.type,
  };
}

function addSelectedAgencyLines() {
  const selected = selectedAgencyLineKeys.value
    .map((key) => selectedAgencyLines.get(key))
    .filter((line): line is AgencyLine => Boolean(line));
  if (!selected.length) {
    message.warning('请至少选择一条代理线');
    return;
  }
  if (items.value.length + selected.length > 1000) {
    message.error('投放任务明细最多 1000 条');
    return;
  }
  items.value = [...items.value, ...selected.map(toDeliveryItem)];
  agencyLineModalOpen.value = false;
  message.success(`已添加 ${selected.length} 条代理线`);
}
</script>

<template>
  <div class="min-w-0 space-y-3">
    <div v-if="!props.readOnly" class="flex flex-wrap justify-end gap-2">
      <Button @click="openImportModal">导入任务</Button>
      <Button @click="openAgencyLineModal">选择代理线</Button>
      <Button
        :disabled="items.length >= 1000 || importing"
        @click="items.push(emptyDeliveryItem())"
        >添加一行</Button
      >
    </div>
    <Alert
      v-if="!props.readOnly"
      type="info"
      show-icon
      message="支持 XLSX / CSV；导入将替换当前明细，不预先匹配代理线。正式提交时类型、像素名称、斗篷链接选填，其余字段必填；同一任务中代理线不能重复。投放平台必须属于当前项目，投手使用系统用户 ID，像素 ID 请在 Excel 中设为文本。"
    />
    <div class="text-muted-foreground text-sm">
      共 {{ items.length }} 条明细
    </div>
    <div class="ux-native-table-viewport max-w-full">
      <table class="w-full text-sm">
        <thead>
          <tr class="bg-muted">
            <th class="bg-muted sticky left-0 z-10 whitespace-nowrap p-2">
              行
            </th>
            <th
              v-for="[key, label] in deliveryItemFields"
              :key="key"
              class="min-w-44 whitespace-nowrap p-2 text-left"
            >
              {{ label === '投手 ID' ? '投手' : label
              }}{{
                !isDeliveryItemFieldRequired(key) || props.readOnly ? '' : ' *'
              }}
            </th>
            <th v-if="!props.readOnly" class="bg-muted sticky right-0 z-10 p-2">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in items" :key="index" class="border-t">
            <td class="bg-card sticky left-0 z-10 p-2">{{ index + 1 }}</td>
            <td
              v-for="[key, label, max] in deliveryItemFields"
              :key="key"
              class="p-2"
            >
              <template v-if="props.readOnly">
                <Input.Password
                  v-if="key === 'token'"
                  :value="item.token"
                  readonly
                  :aria-label="label"
                />
                <span v-else class="block max-w-80 break-all">{{
                  key === 'operatorId'
                    ? props.operatorNames?.[item.operatorId] || item.operatorId
                    : key === 'agencyLineName' &&
                        !item.agencyLineName &&
                        item.channelName
                      ? `历史渠道：${item.channelName}（待选择代理线）`
                      : item[key]
                }}</span>
              </template>
              <Select
                v-else-if="key === 'platform'"
                v-model:value="item.platform"
                :options="platformOptions"
                :aria-label="`第 ${index + 1} 行投放平台`"
                placeholder="请选择投放平台"
              />
              <StableUserSelect
                v-else-if="key === 'operatorId'"
                v-model="item.operatorId"
                :aria-label="`第 ${index + 1} 行投手`"
                placeholder="选择投手"
              />
              <Input.Password
                v-else-if="key === 'token'"
                v-model:value="item.token"
                :maxlength="max"
                autocomplete="new-password"
                :aria-label="`第 ${index + 1} 行${label}`"
              />
              <Input
                v-else
                v-model:value="item[key]"
                :maxlength="max"
                :aria-label="`第 ${index + 1} 行${label}`"
              />
            </td>
            <td v-if="!props.readOnly" class="bg-card sticky right-0 z-10 p-2">
              <Button
                danger
                :aria-label="`删除第 ${index + 1} 行`"
                @click="items.splice(index, 1)"
                >删除</Button
              >
            </td>
          </tr>
          <tr v-if="!items.length">
            <td
              :colspan="deliveryItemFields.length + (props.readOnly ? 1 : 2)"
              class="text-muted-foreground p-6 text-center"
            >
              暂无明细
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Modal
      v-model:open="importModalOpen"
      title="导入任务明细"
      :closable="!importing"
      :confirm-loading="importing"
      :mask-closable="!importing"
      :ok-button-props="{ disabled: !selectedImportFile }"
      :cancel-button-props="{ disabled: importing }"
      ok-text="确认导入"
      cancel-text="取消"
      width="860px"
      @cancel="closeImportModal"
      @ok="confirmImport"
    >
      <div class="mb-4">
        <Button :disabled="importing" @click="downloadTemplate">
          <IconifyIcon icon="lucide:download" class="mr-1 size-4" />
          下载 Excel 模板
        </Button>
      </div>
      <Upload.Dragger
        accept=".xlsx,.csv"
        :before-upload="selectImportFile"
        :disabled="importing"
        :height="132"
        :multiple="false"
        :show-upload-list="false"
      >
        <p class="text-primary flex justify-center text-2xl">
          <IconifyIcon icon="lucide:file-spreadsheet" />
        </p>
        <p class="mt-2 font-medium text-slate-800">
          {{
            selectedImportFile
              ? `已选择：${selectedImportFile.name}`
              : '点击或拖拽 XLSX / CSV 文件到这里'
          }}
        </p>
        <p class="text-sm text-slate-500">一次最多导入一个文件</p>
      </Upload.Dragger>
    </Modal>

    <Modal
      v-model:open="agencyLineModalOpen"
      title="选择代理线"
      width="1080px"
      :confirm-loading="agencyLineLoading"
      :mask-closable="false"
      ok-text="确认添加"
      cancel-text="取消"
      @ok="addSelectedAgencyLines"
    >
      <div class="mb-3 flex items-center justify-between gap-3">
        <Input.Search
          v-model:value="agencyLineKeyword"
          allow-clear
          class="max-w-md"
          placeholder="搜索代理线、平台或投手"
          @search="searchAgencyLines"
        />
        <span class="text-muted-foreground whitespace-nowrap text-sm">
          已选 {{ selectedAgencyLineKeys.length }} 条
        </span>
      </div>
      <Table
        row-key="id"
        :columns="agencyLineColumns"
        :data-source="agencyLineRows"
        :loading="agencyLineLoading"
        :row-selection="agencyLineRowSelection"
        :scroll="{ x: 1200, y: 480 }"
        :pagination="{
          current: agencyLinePage,
          pageSize: agencyLinePageSize,
          total: agencyLineTotal,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
        }"
        @change="changeAgencyLinePage"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'projectId'">
            {{ record.projectId || '未绑定' }}
          </template>
          <template v-else-if="column.key === 'status'">
            <Tag :color="record.status === 'stopped' ? 'default' : 'green'">
              {{ record.status === 'stopped' ? '已停投' : '进行中' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'platform'">
            {{ record.platform || '-' }}
          </template>
        </template>
      </Table>
      <div class="text-muted-foreground mt-2 text-xs">
        当前明细中已存在的同名代理线不可重复选择。
      </div>
    </Modal>
  </div>
</template>
