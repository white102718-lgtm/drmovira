<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { CreativeHistory } from '#/api/advertisement/creativeHistory';

import { ref, watch } from 'vue';

import { Button, message, Modal, Table, Tag, Tooltip } from 'ant-design-vue';

import {
  deleteCreativeHistory,
  getCreativeHistories,
} from '#/api/advertisement/creativeHistory';

const props = defineProps<{
  hasCurrentMaterials?: boolean;
  visible: boolean;
}>();

const emit = defineEmits<{
  reuse: [historyId: string, mode: 'append' | 'replace'];
  'update:visible': [value: boolean];
}>();

// 历史记录列表
const historyList = ref<CreativeHistory[]>([]);
const loadingHistory = ref(false);

// 分页
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条记录`,
});

// 复用操作状态：记录当前正在复用的行ID和模式
const reusingId = ref<string>('');
const reusingMode = ref<'append' | 'replace' | null>(null);

// 表格列定义
const columns: TableColumnsType = [
  {
    title: '素材数量',
    dataIndex: 'creatives_count',
    key: 'creatives_count',
    width: 100,
    align: 'center',
  },
  {
    title: '创建时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 180,
    align: 'center',
  },
];

// 加载历史记录列表
async function loadHistoryList() {
  try {
    loadingHistory.value = true;

    const params = {
      page: pagination.value.current,
      size: pagination.value.pageSize,
    };

    const res: any = await getCreativeHistories(params);

    // 后端直接返回数组（data: [...]），不是 {items, total} 格式
    if (Array.isArray(res)) {
      historyList.value = res;
      pagination.value.total = res.length;
    } else if (res && Array.isArray(res.items)) {
      historyList.value = res.items;
      pagination.value.total =
        res.total !== undefined && res.total !== null
          ? res.total
          : res.items.length;
    } else {
      historyList.value = [];
      pagination.value.total = 0;
    }
  } catch (error: any) {
  } finally {
    loadingHistory.value = false;
  }
}

// 复用历史记录
function handleReuse(historyId: string, mode: 'append' | 'replace') {
  reusingId.value = historyId;
  reusingMode.value = mode;
  emit('reuse', historyId, mode);
}

// 完成复用（由父组件调用）
function finishReuse() {
  reusingId.value = '';
  reusingMode.value = null;
}

defineExpose({
  finishReuse,
});

// 删除历史记录
function handleDelete(historyId: string) {
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该创意历史记录吗？此操作不可恢复。',
    okText: '确认',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        await deleteCreativeHistory(historyId);
        historyList.value = historyList.value.filter((h) => h.id !== historyId);
        pagination.value.total = Math.max(0, pagination.value.total - 1);
        message.success('删除成功');
      } catch (error: any) {}
    },
  });
}

// 表格分页变化
function handleTableChange(paginationData: any) {
  pagination.value.current = paginationData.current;
  pagination.value.pageSize = paginationData.pageSize;
  loadHistoryList();
}

// 关闭弹窗
function handleClose() {
  if (reusingMode.value) return;
  emit('update:visible', false);
}

// 监听弹窗显示状态
watch(
  () => props.visible,
  (val) => {
    if (val) {
      pagination.value.current = 1;
      loadHistoryList();
    }
  },
);
</script>

<template>
  <Modal
    :open="visible"
    title="创意历史"
    width="700px"
    :footer="null"
    :closable="!reusingMode"
    :mask-closable="!reusingMode"
    @cancel="handleClose"
  >
    <div class="py-4">
      <Table
        :columns="columns"
        :data-source="historyList"
        :loading="loadingHistory"
        :pagination="pagination"
        :scroll="{ y: 400 }"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <!-- 素材数量 -->
          <template v-if="column.key === 'creatives_count'">
            <Tag color="blue">{{ record.creatives_count }} 个</Tag>
          </template>

          <!-- 创建时间 -->
          <template v-if="column.key === 'created_at'">
            <span class="text-sm text-gray-600">
              {{
                record.created_at
                  ? record.created_at.slice(0, 19).replace('T', ' ')
                  : '-'
              }}
            </span>
          </template>

          <!-- 操作 -->
          <template v-if="column.key === 'action'">
            <div class="flex items-center justify-center gap-1">
              <Tooltip title="将历史创意配置追加到当前素材">
                <Button
                  type="link"
                  :loading="reusingId === record.id && reusingMode === 'append'"
                  :disabled="!!reusingMode"
                  @click="handleReuse(record.id, 'append')"
                >
                  追加到当前
                </Button>
              </Tooltip>
              <Tooltip title="清空当前素材，使用历史记录中的素材">
                <Button
                  type="link"
                  :loading="
                    reusingId === record.id && reusingMode === 'replace'
                  "
                  :disabled="!!reusingMode"
                  @click="handleReuse(record.id, 'replace')"
                >
                  全部替换
                </Button>
              </Tooltip>
              <Tooltip title="删除此历史记录">
                <Button
                  type="link"
                  danger
                  :disabled="!!reusingMode"
                  @click="handleDelete(record.id)"
                >
                  <span class="icon-[ant-design--delete-outlined]"></span>
                </Button>
              </Tooltip>
            </div>
          </template>
        </template>
      </Table>

      <div
        class="border-border bg-muted text-foreground mt-4 rounded-lg border p-3 text-sm"
      >
        <div class="mb-1 flex items-center gap-2">
          <span
            class="icon-[ant-design--info-circle-outlined] text-blue-500"
          ></span>
          <span class="font-medium">说明：</span>
        </div>
        <ul class="ml-6 list-disc space-y-1">
          <li>
            每次点击「创建广告」时，当前素材的创意配置（标题、正文、行动号召）将自动保存
          </li>
          <li>
            追加到当前：将历史素材配置合并至当前列表，已存在的素材仅更新配置
          </li>
          <li>全部替换：清空当前素材列表，载入历史记录中的素材配置</li>
          <li>系统最多保留最近 100 条历史记录</li>
        </ul>
      </div>
    </div>
  </Modal>
</template>

<style lang="scss" scoped>
/* 样式*/
</style>
