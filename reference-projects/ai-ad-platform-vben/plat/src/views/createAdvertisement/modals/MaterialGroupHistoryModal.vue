<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { MaterialGroupHistory } from '#/api/advertisement/materialGroup';

import { ref, watch } from 'vue';

import { Button, message, Modal, Table, Tag, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getMaterialGroupHistories } from '#/api/advertisement/materialGroup';

const props = defineProps<{
  hasCurrentMaterials?: boolean; // 当前是否有素材
  visible: boolean;
}>();

const emit = defineEmits<{
  reapply: [historyId: string, mode: 'append' | 'replace'];
  'update:visible': [value: boolean];
}>();

// 历史记录列表
const historyList = ref<MaterialGroupHistory[]>([]);
const loadingHistory = ref(false);

// 分页
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条记录`,
});

// 表格列定义
const columns: TableColumnsType = [
  {
    title: '素材组名称',
    dataIndex: 'group_name',
    key: 'group_name',
    width: 200,
  },
  {
    title: '素材数量',
    dataIndex: 'materials_count',
    key: 'materials_count',
    width: 100,
    align: 'center',
  },
  {
    title: '应用时间',
    dataIndex: 'applied_at',
    key: 'applied_at',
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

    const res: any = await getMaterialGroupHistories(params);

    if (res && res.items) {
      historyList.value = res.items || [];
      pagination.value.total = res.total || 0;
    } else {
      historyList.value = [];
      pagination.value.total = 0;
    }
  } catch (error: any) {
  } finally {
    loadingHistory.value = false;
  }
}

// 格式化时间
function formatTime(time: string) {
  return dayjs.tz(time).format('YYYY-MM-DD HH:mm:ss');
}

const applying = ref(false);
const applyingId = ref<string>('');

// 重新应用历史
function handleReapply(historyId: string, mode: 'append' | 'replace') {
  applying.value = true;
  applyingId.value = historyId;
  emit('reapply', historyId, mode);
}

// 完成应用（由父组件调用）
function finishApply() {
  applying.value = false;
  applyingId.value = '';
}

defineExpose({
  finishApply,
});

// 表格分页变化
function handleTableChange(paginationData: any) {
  pagination.value.current = paginationData.current;
  pagination.value.pageSize = paginationData.pageSize;
  loadHistoryList();
}

// 关闭弹窗
function handleClose() {
  if (applying.value) return;
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
    title="应用历史"
    width="800px"
    :footer="null"
    :closable="!applying"
    :mask-closable="!applying"
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
        <!-- 素材组名称 -->
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'group_name'">
            <div class="font-medium text-gray-800">
              {{ record.group_name }}
            </div>
          </template>

          <!-- 素材数量 -->
          <template v-if="column.key === 'materials_count'">
            <Tag color="blue">{{ record.materials_count }} 个</Tag>
          </template>

          <!-- 应用时间 -->
          <template v-if="column.key === 'applied_at'">
            <span class="text-sm text-gray-600">
              {{ formatTime(record.applied_at) }}
            </span>
          </template>

          <!-- 操作 -->
          <template v-if="column.key === 'action'">
            <div class="flex items-center justify-center gap-1">
              <Tooltip title="将历史素材追加到当前列表">
                <Button
                  type="link"
                  :loading="applying && applyingId === record.id"
                  :disabled="applying"
                  @click="handleReapply(record.id, 'append')"
                >
                  追加到当前
                </Button>
              </Tooltip>
              <Tooltip title="清空当前素材，使用历史记录中的素材">
                <Button
                  type="link"
                  :loading="applying && applyingId === record.id"
                  :disabled="applying"
                  @click="handleReapply(record.id, 'replace')"
                >
                  全部替换
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
            历史记录保存了应用素材组时的快照，即使原素材组被修改，历史记录也不受影响
          </li>
          <li>追加到当前：将历史素材合并至当前列表，已存在的素材仅更新配置</li>
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
